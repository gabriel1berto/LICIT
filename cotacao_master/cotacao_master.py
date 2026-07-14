#!/usr/bin/env python3
"""
cotacao_master.py — Orquestrador da COTAÇÃO MASTER (coleta diária de preço de
mercado por medida, 4 fornecedores já cadastrados, independente de edital).

Fluxo:
  1. Lê medidas_prioritarias.json (raiz do repo) — lista de medida a cotar.
  2. Roda os 4 scrapers *_master.py SEQUENCIAL (nunca paralelo): Bransales →
     Cantu → GP → Green. Cada um processa TODOS os itens do arquivo numa só
     sessão de browser (1 login por fornecedor).
  3. Pra cada produto retornado: extrai medida do nome via pneu_medida_matcher
     (reusado de analise/, não duplicado), compara com a medida de referência.
  4. Grava em cotacao_fornecedor.{medidas,aliases_medida,cotacoes} (Supabase).
     Alias novo (nunca visto pra aquele fornecedor) sempre entra como
     PENDENTE (aprovado_por_humano=false) e força confianca_match='parcial'
     na cotação, mesmo que o matcher classifique como exato — só decisão
     humana (revisar_aliases_pendentes.py) promove pra confiança plena.
  5. GP com cookie expirado é ESPERADO — pula, loga, não quebra o processo.
     Qualquer outra falha vira retry: até MAX_TENTATIVAS tentativas (delay
     entre elas), só conta como QUEBRA REAL se TODAS falharem — a maioria
     das falhas de scraping web é instabilidade passageira do site, não
     bug. Só depois de esgotar as tentativas o processo termina com
     exit(1), o que faz o GitHub Actions marcar o job como failed e
     disparar e-mail automático pro dono do repo — alerta só dispara
     quando o fornecedor rejeitou TODAS as tentativas, não na 1ª falha.

Uso: python cotacao_master.py
"""

import json
import os
import subprocess
import sys
import time

from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")

load_dotenv(os.path.join(ROOT, ".env"))

sys.path.insert(0, os.path.join(ROOT, "analise"))
import psycopg2
from pneu_medida_matcher import MedidaTupla, comparar_medidas, extrair_medida
from classificador_alias import classificar_alias

MEDIDAS_CFG = os.path.join(ROOT, "medidas_prioritarias.json")

SCRAPERS = [
    ("Bransales",   os.path.join(HERE, "bransales_scraper_master.py"), os.path.join(HERE, "results_master_bransales.json")),
    ("Cantu",       os.path.join(HERE, "cantu_scraper_master.py"),     os.path.join(HERE, "results_master_cantu.json")),
    ("GP",          os.path.join(HERE, "gp_scraper_master.py"),        os.path.join(HERE, "results_master_gp.json")),
    ("Green Pneus", os.path.join(HERE, "green_scraper_master.py"),     os.path.join(HERE, "results_master_green.json")),
]

# Assinatura de falha ESPERADA (cookie GP expirado) — não conta como quebra,
# não entra no retry (repetir não resolve cookie vencido).
GP_COOKIE_EXPIRADO_MSG = "Cookies expirados ou inválidos"

MAX_TENTATIVAS  = 3
DELAY_RETRY_SEG = 30


def _rodar_uma_vez(nome: str, script: str, out_path: str) -> tuple[str, list[dict]]:
    """1 tentativa isolada. Retorna (status, produtos). status: 'ok' | 'esperado_gp_cookie' | 'erro'."""
    result = subprocess.run(
        [sys.executable, script, MEDIDAS_CFG, out_path],
        cwd=HERE,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    sys.stderr.write(result.stderr)

    if result.returncode != 0:
        if GP_COOKIE_EXPIRADO_MSG in result.stderr:
            print(f"[{nome}] cookie expirado — ESPERADO, pulando (sem retry)", file=sys.stderr)
            return "esperado_gp_cookie", []
        return "erro", []

    if not os.path.exists(out_path):
        print(f"[{nome}] terminou OK mas não gerou {out_path}", file=sys.stderr)
        return "erro", []

    with open(out_path, encoding="utf-8") as f:
        produtos = json.load(f)
    return "ok", produtos


def rodar_scraper(nome: str, script: str, out_path: str) -> tuple[str, list[dict]]:
    """Roda 1 scraper master, com retry. Só marca 'erro' (quebra real, dispara
    alerta) se TODAS as MAX_TENTATIVAS falharem — 1 falha isolada costuma ser
    instabilidade passageira do site (já visto: Bransales/Cantu falharam na
    1ª tentativa e passaram limpo na 2ª, no mesmo dia, mesmo código)."""
    print(f"\n{'='*60}\n{nome}\n{'='*60}", file=sys.stderr)

    for tentativa in range(1, MAX_TENTATIVAS + 1):
        print(f"[{nome}] tentativa {tentativa}/{MAX_TENTATIVAS}", file=sys.stderr)
        status, produtos = _rodar_uma_vez(nome, script, out_path)

        if status in ("ok", "esperado_gp_cookie"):
            return status, produtos

        if tentativa < MAX_TENTATIVAS:
            print(f"[{nome}] tentativa {tentativa} falhou — aguardando {DELAY_RETRY_SEG}s antes de tentar de novo", file=sys.stderr)
            time.sleep(DELAY_RETRY_SEG)

    print(f"[{nome}] QUEBROU em todas as {MAX_TENTATIVAS} tentativas — quebra real", file=sys.stderr)
    return "erro", []


def carregar_medidas_cfg() -> dict:
    """item -> {medida_id, ref (MedidaTupla)} depois de upsert em cotacao_fornecedor.medidas."""
    with open(MEDIDAS_CFG, encoding="utf-8") as f:
        cfgs = json.load(f)

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = False
    cur = conn.cursor()

    item_para_medida = {}
    for cfg in cfgs:
        largura = int(cfg["largura"])
        perfil  = int(cfg["altura"])
        aro     = float(cfg["aro"])
        texto_canonico = f"{largura}/{perfil} R{aro:g}"

        cur.execute(
            """
            INSERT INTO cotacao_fornecedor.medidas (largura, perfil, construcao, aro, tipo_produto, texto_canonico)
            VALUES (%s,%s,'R',%s,'pneu',%s)
            ON CONFLICT (texto_canonico) DO UPDATE SET texto_canonico = EXCLUDED.texto_canonico
            RETURNING id
            """,
            (largura, perfil, aro, texto_canonico),
        )
        medida_id = cur.fetchone()[0]
        ref = MedidaTupla(largura=largura, perfil=perfil, construcao="R", aro=aro)
        item_para_medida[cfg["item"]] = {"medida_id": medida_id, "ref": ref, "texto_canonico": texto_canonico}

    conn.commit()
    conn.close()
    return item_para_medida


def gravar_cotacoes(fornecedor: str, produtos: list[dict], item_para_medida: dict, conn) -> int:
    cur = conn.cursor()
    gravados = 0

    for p in produtos:
        info = item_para_medida.get(p.get("item"))
        if info is None:
            print(f"  ! item {p.get('item')} sem medida de referência — pulando", file=sys.stderr)
            continue
        if p.get("preco_un") is None:
            continue  # "sem estoque" placeholder (Green) — nada pra gravar

        medida_id = info["medida_id"]
        ref = info["ref"]
        nome = p["nome"]

        extraida = extrair_medida(nome)
        if extraida is None or extraida.chave() != ref.chave():
            confianca = "sem_match"
        else:
            cur.execute(
                """SELECT aprovado_por_humano FROM cotacao_fornecedor.aliases_medida
                   WHERE fornecedor = %s AND texto_bruto = %s""",
                (fornecedor, nome),
            )
            row = cur.fetchone()
            if row is None:
                suspeita, motivo = classificar_alias(nome)
                cur.execute(
                    """INSERT INTO cotacao_fornecedor.aliases_medida
                       (medida_id, fornecedor, texto_bruto, inferido, aprovado_por_humano,
                        suspeita_reforcado, motivo_suspeita)
                       VALUES (%s,%s,%s,%s,FALSE,%s,%s)
                       ON CONFLICT (fornecedor, texto_bruto) DO NOTHING""",
                    (medida_id, fornecedor, nome, extraida.inferido_construcao, suspeita, motivo),
                )
                confianca = "parcial"
            elif row[0] is False:
                confianca = "parcial"
            else:
                # comparar_medidas() retorna "match_exato"/"match_parcial"/"sem_match"
                # (contrato de pneu_medida_matcher.py, ver seus testes) — a constraint
                # de cotacoes.confianca_match espera "exato"/"parcial"/"sem_match", sem
                # o prefixo "match_". Bug achado 14/jul/2026: só aparece quando um alias
                # JÁ está aprovado (1ª vez que esse branch roda de verdade, depois da
                # aprovação em massa dos 31 aliases limpos) — CheckViolation na hora
                # de gravar.
                confianca = comparar_medidas(extraida, ref).removeprefix("match_")

        cur.execute(
            """
            INSERT INTO cotacao_fornecedor.cotacoes
                (medida_id, fornecedor, preco, confianca_match, texto_bruto_origem, observacao,
                 marca, url, apto, ic, iv, treadwear, construcao, num_lonas, tipo_terreno, inmetro)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                medida_id, fornecedor, p["preco_un"], confianca, nome, p.get("obs", ""),
                p.get("marca"), p.get("url"), p.get("apto"),
                p.get("ic"), p.get("iv"), p.get("treadwear"), p.get("construcao"),
                p.get("num_lonas"), p.get("tipo_terreno"), p.get("inmetro"),
            ),
        )
        gravados += 1

    conn.commit()
    return gravados


def main():
    if not os.path.exists(MEDIDAS_CFG):
        print(f"ERRO: {MEDIDAS_CFG} não encontrado.", file=sys.stderr)
        sys.exit(1)

    item_para_medida = carregar_medidas_cfg()
    print(f"medidas carregadas: {len(item_para_medida)}", file=sys.stderr)

    houve_quebra_real = False
    conn = psycopg2.connect(os.environ["DATABASE_URL"])

    for fornecedor, script, out_path in SCRAPERS:
        status, produtos = rodar_scraper(fornecedor, script, out_path)

        if status == "erro":
            houve_quebra_real = True
            continue
        if status == "esperado_gp_cookie":
            continue

        try:
            n = gravar_cotacoes(fornecedor, produtos, item_para_medida, conn)
            print(f"[{fornecedor}] {n} cotação(ões) gravada(s)", file=sys.stderr)
        except Exception as e:
            # Achado 14/jul/2026: exceção na escrita (ex: CheckViolation) não tratada
            # derrubava o script inteiro — fornecedores seguintes (GP/Green) nem
            # chegavam a rodar, mesmo sem culpa deles. Isola por fornecedor, igual já
            # acontece pro scraper em si — 1 escrita ruim não impede os outros 3.
            conn.rollback()
            print(f"[{fornecedor}] ERRO ao gravar no banco: {e}", file=sys.stderr)
            houve_quebra_real = True

    conn.close()

    if houve_quebra_real:
        print("\nQUEBRA REAL detectada em pelo menos 1 fornecedor — encerrando com erro (dispara alerta).", file=sys.stderr)
        sys.exit(1)

    print("\nRodada concluída sem quebra real.", file=sys.stderr)


if __name__ == "__main__":
    main()
