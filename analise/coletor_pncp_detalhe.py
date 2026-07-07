#!/usr/bin/env python3
"""
coletor_pncp_detalhe.py — Fase 2: detalhe + itens + resultado de cada processo
já descoberto por coletor_pncp.py (fase 1, tabela `editais` em pncp_raw.db).

3 chamadas por processo, na API oficial de consulta do PNCP:
  1. Detalhe:   api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}
  2. Itens:     api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens
  3. Resultado: api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens/{n}/resultados
                (só pra item que passar no filtro de pneu E tiver resultado)

Endpoint confirmado testando ao vivo — `api/consulta/v1/...` (usado em
pncp_radar.py) dá 404 pros itens; `api/pncp/v1/...` (usado em analisa_edital.py)
funciona pros 3 níveis.

O filtro "é pneu de verdade?" aqui é o MESMO regex validado em base_pneu.sql
(histórico de 7 bugs corrigidos, ver README.md) — mas agora aplicado na
descrição REAL do item (`itens.descricao`), não no título/descrição fraco do
processo. Muito mais confiável que a classificação da fase 1.

Volume esperado: ~23 mil processos × 2 chamadas (detalhe+itens) + 1 chamada
por item que passar no filtro (resultado). Não cabe numa noite só — script é
resumível por processo individual, rodar de novo continua de onde parou.

Uso:
    python coletor_pncp_detalhe.py                # roda até esgotar a fila
    python coletor_pncp_detalhe.py --status        # progresso
    python coletor_pncp_detalhe.py --limite 100    # só os N primeiros (teste)
"""

import argparse
import json
import logging
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras
from curl_cffi import requests
from dotenv import load_dotenv

load_dotenv()

# ── Configuração ──────────────────────────────────────────────────────────

LOG_PATH = Path(__file__).parent / "coletor_pncp_detalhe.log"
MAX_TENTATIVAS_PROCESSO = 5  # teto de re-tentativa entre execuções de cron pra processo com erro persistente

PAUSA_ENTRE_CHAMADAS = 1.5
PAUSA_APOS_ERRO_BASE = 15.0
MAX_TENTATIVAS = 6
ESPACO_MINIMO_MB = 200

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer": "https://pncp.gov.br/",
}

PNCP_BASE = "https://pncp.gov.br/api/pncp/v1/orgaos"
PNCP_BASE_DETALHE = "https://pncp.gov.br/api/consulta/v1/orgaos"  # base diferente do de itens/resultado — testado ao vivo


# ── Logging ───────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("coletor_pncp_detalhe")


# ── Filtro "é pneu de verdade?" — mesmo regex validado de base_pneu.sql ────

RE_PNEU_INICIO = re.compile(r"^\s*pneus?\b", re.IGNORECASE)
RE_CAMARA_INICIO = re.compile(r"^\s*c[âa]mara\s+(de\s+)?ar\b", re.IGNORECASE)
RE_MEDIDA_R = re.compile(r"\d{3}\s*/\s*\d{2}\s*[Rr]\s*\d{2}\b")
# bug achado jul/2026: veículo inteiro (caminhão/ambulância/pick-up/van) que só CITA a
# medida do pneu de fábrica batia em RE_MEDIDA_R e virava "eh_pneu=1" — item de
# R$100k-800k/unidade (o veículo), não o pneu. Mesma lógica de âncora no início já usada
# pra pneu/câmara: se o produto começa com nome de veículo, medida solta não conta.
RE_VEICULO_INICIO = re.compile(
    r"^\s*(ve[íi]culo|caminh[ãa]o|ambul[âa]ncia|[ôo]nibus|micro[ -]?[ôo]nibus|van\b|"
    r"pick[ -]?up|caminhonete|loca[çc][ãa]o\s+(di[áa]ria\s+)?de\s+ve[íi]culo)",
    re.IGNORECASE,
)
RE_EXCLUSAO = re.compile(
    r"carregadeira|motoniveladora|retroescavadeira|escavadeira|rolo\s+compactador|"
    r"cadeira\s+de\s+rodas|recapagem|vulcaniza[çc][ãa]o|alinhamento|balanceamento|conserto|"
    r"presta[çc][aã]o\s+de\s+servi[çc]|servi[çc]os?\s+de\s+(borracharia|recauchutagem|vulcaniza|substitui)|"
    r"loca[çc][aã]o\s+de\s+(trator|m[áa]quina|equipamento)|"
    r"loca[çc][aã]o\s+(di[áa]ria\s+)?de.{0,40}(ve[íi]culo|van|minibus|micro[ -]?[ôo]nibus|[ôo]nibus|caminh[ãa]o|ambul[âa]ncia)|"
    r"manuten[çc][ãa]o\s+(preventiva|corretiva)?\s*(do|de)\s+ve[íi]culo|"
    r"n[úu]cleo.*v[áa]lvula|v[áa]lvula.*n[úu]cleo",
    re.IGNORECASE,
)
RE_CATEGORIA_CAMARA = RE_CAMARA_INICIO
RE_CATEGORIA_MOTO = re.compile(r"motocicleta|motoneta|ciclomotor", re.IGNORECASE)
RE_CATEGORIA_AGRICOLA = re.compile(r"trator|agr[íi]cola", re.IGNORECASE)
RE_CATEGORIA_CAMINHAO = re.compile(r"r2[2-9]\.?[05]?\b|r1[7-9]\.?5\b", re.IGNORECASE)


def eh_pneu_de_verdade(descricao: str) -> bool:
    if not descricao:
        return False
    if RE_VEICULO_INICIO.search(descricao):
        return False
    bate_produto = bool(RE_PNEU_INICIO.search(descricao) or RE_CAMARA_INICIO.search(descricao) or RE_MEDIDA_R.search(descricao))
    return bate_produto and not RE_EXCLUSAO.search(descricao)


def classificar_categoria(descricao: str) -> str:
    if RE_CATEGORIA_CAMARA.search(descricao):
        return "Câmara de ar"
    if RE_CATEGORIA_MOTO.search(descricao):
        return "Moto"
    if RE_CATEGORIA_AGRICOLA.search(descricao):
        return "Agrícola"
    if RE_CATEGORIA_CAMINHAO.search(descricao):
        return "Caminhão"
    return "Passeio"


# ── Banco (Supabase/Postgres) ────────────────────────────────────────────
# DDL vive em analise/schema_supabase.sql, aplicado uma única vez.

def conectar_db() -> tuple[psycopg2.extensions.connection, psycopg2.extensions.cursor]:
    con = psycopg2.connect(os.environ["DATABASE_URL"])
    return con, con.cursor()


def popular_fila_se_vazia(con: psycopg2.extensions.connection, cur: psycopg2.extensions.cursor,
                           limite: int | None) -> None:
    limite_sql = f" LIMIT {int(limite)}" if limite else ""
    query = f"""
        INSERT INTO progresso_detalhe (numero_controle_pncp, status, atualizado_em)
        SELECT numero_controle_pncp, 'pendente', %s
        FROM editais
        WHERE dentro_periodo_alvo = TRUE
        {limite_sql}
        ON CONFLICT (numero_controle_pncp) DO NOTHING
    """
    cur.execute(query, (datetime.now(timezone.utc).isoformat(),))
    con.commit()
    cur.execute("SELECT COUNT(*) FROM progresso_detalhe")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM progresso_detalhe WHERE status='pendente'")
    pendentes = cur.fetchone()[0]
    log.info(f"Fila de processos: {total} no total, {pendentes} pendentes.")


# ── Guarda de disco ───────────────────────────────────────────────────────

def espaco_livre_mb() -> float:
    return shutil.disk_usage(Path(__file__).parent).free / 1_000_000


def aguardar_espaco_em_disco() -> None:
    while espaco_livre_mb() < ESPACO_MINIMO_MB:
        log.warning(f"Espaço livre abaixo de {ESPACO_MINIMO_MB}MB ({espaco_livre_mb():.0f}MB). Pausando 2min.")
        time.sleep(120)


# ── Chamadas à API ────────────────────────────────────────────────────────

def get_com_retry(url: str, params: dict | None = None) -> dict | list | None:
    espera = PAUSA_APOS_ERRO_BASE
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=30,
                              impersonate="chrome120", verify=False)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None  # processo sem esse recurso (ex: sem itens) — não é erro transitório
            log.warning(f"{url}: HTTP {r.status_code} (tentativa {tentativa}/{MAX_TENTATIVAS})")
        except Exception as e:
            log.warning(f"{url}: erro '{e}' (tentativa {tentativa}/{MAX_TENTATIVAS})")
        time.sleep(espera)
        espera *= 1.6
    raise RuntimeError(f"Falhou {MAX_TENTATIVAS}x em {url}")


def parse_numero_controle(numero_controle: str) -> tuple[str, str, str]:
    # formato: "{cnpj}-1-{seq}/{ano}"
    cnpj, resto = numero_controle.split("-", 1)
    _, resto = resto.split("-", 1)
    seq, ano = resto.split("/")
    return cnpj, ano, str(int(seq))


# ── Processamento de 1 processo ───────────────────────────────────────────

def processar_processo(con: psycopg2.extensions.connection, cur: psycopg2.extensions.cursor,
                        numero_controle: str) -> None:
    cnpj, ano, seq = parse_numero_controle(numero_controle)

    # 1. Detalhe
    detalhe = get_com_retry(f"{PNCP_BASE_DETALHE}/{cnpj}/compras/{ano}/{seq}")
    if detalhe:
        oe = detalhe.get("orgaoEntidade") or {}
        uo = detalhe.get("unidadeOrgao") or {}
        cur.execute("""
            INSERT INTO detalhes (
                numero_controle_pncp, valor_total_estimado, valor_total_homologado, srp,
                objeto_compra, municipio_nome, codigo_ibge, uf_sigla, modalidade_nome,
                modo_disputa_nome, poder_id, esfera_id, situacao_compra_nome, existe_resultado,
                data_abertura_proposta, data_encerramento_proposta, link_sistema_origem,
                usuario_nome, coletado_em
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (numero_controle_pncp) DO UPDATE SET
                valor_total_estimado = excluded.valor_total_estimado,
                valor_total_homologado = excluded.valor_total_homologado,
                srp = excluded.srp,
                objeto_compra = excluded.objeto_compra,
                municipio_nome = excluded.municipio_nome,
                codigo_ibge = excluded.codigo_ibge,
                uf_sigla = excluded.uf_sigla,
                modalidade_nome = excluded.modalidade_nome,
                modo_disputa_nome = excluded.modo_disputa_nome,
                poder_id = excluded.poder_id,
                esfera_id = excluded.esfera_id,
                situacao_compra_nome = excluded.situacao_compra_nome,
                existe_resultado = excluded.existe_resultado,
                data_abertura_proposta = excluded.data_abertura_proposta,
                data_encerramento_proposta = excluded.data_encerramento_proposta,
                link_sistema_origem = excluded.link_sistema_origem,
                usuario_nome = excluded.usuario_nome,
                coletado_em = excluded.coletado_em
        """, (
            numero_controle, detalhe.get("valorTotalEstimado"), detalhe.get("valorTotalHomologado"),
            bool(detalhe.get("srp")), detalhe.get("objetoCompra"),
            uo.get("municipioNome"), uo.get("codigoIbge"), uo.get("ufSigla"),
            detalhe.get("modalidadeNome"), detalhe.get("modoDisputaNome"),
            oe.get("poderId"), oe.get("esferaId"), detalhe.get("situacaoCompraNome"),
            bool(detalhe.get("existeResultado")),
            detalhe.get("dataAberturaProposta"), detalhe.get("dataEncerramentoProposta"),
            detalhe.get("linkSistemaOrigem"), detalhe.get("usuarioNome"),
            datetime.now(timezone.utc).isoformat(),
        ))
    time.sleep(PAUSA_ENTRE_CHAMADAS)

    # 2. Itens
    itens = get_com_retry(f"{PNCP_BASE}/{cnpj}/compras/{ano}/{seq}/itens") or []
    itens_pneu = []
    for it in itens:
        descricao = it.get("descricao") or ""
        eh_pneu = eh_pneu_de_verdade(descricao)
        categoria = classificar_categoria(descricao) if eh_pneu else None
        cur.execute("""
            INSERT INTO itens (
                numero_controle_pncp, numero_item, descricao, material_ou_servico,
                valor_unitario_estimado, valor_total, quantidade, unidade_medida,
                situacao_item_nome, criterio_julgamento_nome, tipo_beneficio_nome,
                ncm_nbs_codigo, tem_resultado, eh_pneu, categoria
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (numero_controle_pncp, numero_item) DO UPDATE SET
                descricao = excluded.descricao,
                material_ou_servico = excluded.material_ou_servico,
                valor_unitario_estimado = excluded.valor_unitario_estimado,
                valor_total = excluded.valor_total,
                quantidade = excluded.quantidade,
                unidade_medida = excluded.unidade_medida,
                situacao_item_nome = excluded.situacao_item_nome,
                criterio_julgamento_nome = excluded.criterio_julgamento_nome,
                tipo_beneficio_nome = excluded.tipo_beneficio_nome,
                ncm_nbs_codigo = excluded.ncm_nbs_codigo,
                tem_resultado = excluded.tem_resultado,
                eh_pneu = excluded.eh_pneu,
                categoria = excluded.categoria
        """, (
            numero_controle, it.get("numeroItem"), descricao, it.get("materialOuServico"),
            it.get("valorUnitarioEstimado"), it.get("valorTotal"), it.get("quantidade"),
            it.get("unidadeMedida"), it.get("situacaoCompraItemNome"), it.get("criterioJulgamentoNome"),
            it.get("tipoBeneficioNome"), it.get("ncmNbsCodigo"),
            bool(it.get("temResultado")), eh_pneu, categoria,
        ))
        if eh_pneu and it.get("temResultado"):
            itens_pneu.append(it.get("numeroItem"))
    time.sleep(PAUSA_ENTRE_CHAMADAS)

    # 3. Resultado — só dos itens que são pneu de verdade E têm resultado
    for numero_item in itens_pneu:
        resultados = get_com_retry(f"{PNCP_BASE}/{cnpj}/compras/{ano}/{seq}/itens/{numero_item}/resultados") or []
        for res in resultados:
            cur.execute("""
                INSERT INTO resultados (
                    numero_controle_pncp, numero_item, ni_fornecedor, nome_fornecedor,
                    tipo_pessoa, porte_fornecedor_nome, valor_unitario_homologado,
                    valor_total_homologado, percentual_desconto, quantidade_homologada,
                    ordem_classificacao_srp, data_resultado
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (numero_controle_pncp, numero_item, ni_fornecedor) DO UPDATE SET
                    nome_fornecedor = excluded.nome_fornecedor,
                    tipo_pessoa = excluded.tipo_pessoa,
                    porte_fornecedor_nome = excluded.porte_fornecedor_nome,
                    valor_unitario_homologado = excluded.valor_unitario_homologado,
                    valor_total_homologado = excluded.valor_total_homologado,
                    percentual_desconto = excluded.percentual_desconto,
                    quantidade_homologada = excluded.quantidade_homologada,
                    ordem_classificacao_srp = excluded.ordem_classificacao_srp,
                    data_resultado = excluded.data_resultado
            """, (
                numero_controle, numero_item, res.get("niFornecedor"), res.get("nomeRazaoSocialFornecedor"),
                res.get("tipoPessoa"), res.get("porteFornecedorNome"), res.get("valorUnitarioHomologado"),
                res.get("valorTotalHomologado"), res.get("percentualDesconto"), res.get("quantidadeHomologada"),
                res.get("ordemClassificacaoSrp"), res.get("dataResultado"),
            ))
        time.sleep(PAUSA_ENTRE_CHAMADAS)

    con.commit()


# ── Loop principal ────────────────────────────────────────────────────────

def coletar(limite: int | None) -> None:
    con, cur = conectar_db()
    popular_fila_se_vazia(con, cur, limite)

    # status='erro' com poucas tentativas também entra — sem isso, processo que falhou
    # 1x numa execução de cron fica travado em erro pra sempre, nunca mais re-tentado
    # (rodando sem supervisão, ninguém vai notar e re-rodar manualmente como antes).
    cur.execute("""
        SELECT numero_controle_pncp FROM progresso_detalhe
        WHERE status='pendente' OR (status='erro' AND tentativas < %s)
        ORDER BY numero_controle_pncp
    """, (MAX_TENTATIVAS_PROCESSO,))
    pendentes = cur.fetchall()
    log.info(f"Iniciando fase 2 — {len(pendentes)} processos pendentes.")

    for i, (numero_controle,) in enumerate(pendentes, 1):
        aguardar_espaco_em_disco()
        try:
            processar_processo(con, cur, numero_controle)
            cur.execute(
                "UPDATE progresso_detalhe SET status='feito', atualizado_em=%s WHERE numero_controle_pncp=%s",
                (datetime.now(timezone.utc).isoformat(), numero_controle),
            )
        except RuntimeError as e:
            log.error(f"{numero_controle}: {e}")
            con.rollback()  # descarta writes parciais do processo que falhou, antes do próximo commit
            cur.execute("""
                UPDATE progresso_detalhe SET status='erro', tentativas=tentativas+1, atualizado_em=%s
                WHERE numero_controle_pncp=%s
            """, (datetime.now(timezone.utc).isoformat(), numero_controle))
        con.commit()

        if i % 50 == 0:
            log.info(f"Progresso: {i}/{len(pendentes)} processos ({i/len(pendentes)*100:.1f}%)")

    cur.execute("SELECT COUNT(*) FROM progresso_detalhe WHERE status='feito'")
    n_feito = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM progresso_detalhe WHERE status='erro'")
    n_erro = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM itens WHERE eh_pneu=TRUE")
    n_itens_pneu = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM resultados")
    n_resultados = cur.fetchone()[0]
    log.info(
        f"Fase 2 concluída (ou pausada). {n_feito} processos ok, {n_erro} com erro. "
        f"{n_itens_pneu} itens de pneu confirmados, {n_resultados} resultados coletados."
    )
    cur.close()
    con.close()


def mostrar_status() -> None:
    con, cur = conectar_db()
    print(f"Espaço livre em disco: {espaco_livre_mb():.0f}MB\n")

    print("Fila de processos (fase 2):")
    cur.execute("SELECT status, COUNT(*) FROM progresso_detalhe GROUP BY status")
    for status, n in cur.fetchall():
        print(f"  {status:10} {n}")
    print()

    cur.execute("SELECT COUNT(*) FROM itens")
    n_itens = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM itens WHERE eh_pneu=TRUE")
    n_itens_pneu = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM resultados")
    n_resultados = cur.fetchone()[0]
    print(f"Itens coletados: {n_itens} ({n_itens_pneu} confirmados como pneu de verdade)")
    print(f"Resultados (fornecedor/desconto) coletados: {n_resultados}")
    cur.close()
    con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--limite", type=int, default=None, help="processa só os N primeiros (teste)")
    args = parser.parse_args()

    if args.status:
        mostrar_status()
    else:
        coletar(args.limite)
