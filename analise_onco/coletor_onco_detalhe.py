#!/usr/bin/env python3
"""
coletor_onco_detalhe.py — Fase 2: detalhe + itens + resultado de cada edital já
descoberto por coletor_onco.py (schema `oncologia`, isolado de `public`/pneu).

Espelha analise/coletor_pncp_detalhe.py (mesmos 3 endpoints, mesma lógica de
fila resumível com FOR UPDATE SKIP LOCKED) — só troca o filtro (filtro_onco.py
em vez de filtro_pneu.py) e a tabela de destino (oncologia.* em vez de public.*).

Progresso impresso por TEMPO (a cada ~60s), não por contagem — pedido do
usuário pra acompanhar minuto a minuto via Monitor.

Uso:
    python coletor_onco_detalhe.py
    python coletor_onco_detalhe.py --status
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import psycopg2
from curl_cffi import requests
from dotenv import load_dotenv

from filtro_onco import eh_medicamento_onco_de_verdade, principio_ativo_provavel

load_dotenv()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer": "https://pncp.gov.br/",
}

PNCP_BASE = "https://pncp.gov.br/api/pncp/v1/orgaos"
PNCP_BASE_DETALHE = "https://pncp.gov.br/api/consulta/v1/orgaos"

PAUSA_ENTRE_CHAMADAS = 1.5
PAUSA_APOS_ERRO_BASE = 12.0
MAX_TENTATIVAS = 5
MAX_TENTATIVAS_PROCESSO = 5
INTERVALO_PROGRESSO_S = 60


def conectar_db():
    con = psycopg2.connect(os.environ["DATABASE_URL"])
    return con, con.cursor()


def get_com_retry(url: str):
    espera = PAUSA_APOS_ERRO_BASE
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30, impersonate="chrome120", verify=False)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (404, 410):
                return None
        except Exception:
            pass
        time.sleep(espera)
        espera *= 1.6
    return None


def parse_numero_controle(numero_controle: str):
    cnpj, resto = numero_controle.split("-", 1)
    _, resto = resto.split("-", 1)
    seq, ano = resto.split("/")
    return cnpj, ano, str(int(seq))


def popular_fila(con, cur):
    cur.execute("""
        INSERT INTO oncologia.progresso_detalhe (numero_controle_pncp, status, atualizado_em)
        SELECT numero_controle_pncp, 'pendente', %s
        FROM oncologia.editais
        ON CONFLICT (numero_controle_pncp) DO NOTHING
    """, (datetime.now(timezone.utc).isoformat(),))
    con.commit()


def reivindicar_proximo(con, cur):
    cur.execute("""
        UPDATE oncologia.progresso_detalhe
        SET status='processando', atualizado_em=%s
        WHERE numero_controle_pncp = (
            SELECT numero_controle_pncp FROM oncologia.progresso_detalhe
            WHERE status='pendente'
               OR (status='erro' AND tentativas < %s)
               OR (status='processando' AND atualizado_em < %s)
            ORDER BY numero_controle_pncp
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING numero_controle_pncp
    """, (
        datetime.now(timezone.utc).isoformat(),
        MAX_TENTATIVAS_PROCESSO,
        (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat(),
    ))
    row = cur.fetchone()
    con.commit()
    return row[0] if row else None


def processar(con, cur, numero_controle: str):
    cnpj, ano, seq = parse_numero_controle(numero_controle)

    detalhe = get_com_retry(f"{PNCP_BASE_DETALHE}/{cnpj}/compras/{ano}/{seq}")
    if detalhe:
        uo = detalhe.get("unidadeOrgao") or {}
        cur.execute("""
            INSERT INTO oncologia.detalhes (
                numero_controle_pncp, valor_total_estimado, valor_total_homologado, srp,
                objeto_compra, municipio_nome, uf_sigla, codigo_ibge, modalidade_nome,
                situacao_compra_nome, existe_resultado, data_abertura_proposta,
                data_encerramento_proposta, coletado_em
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (numero_controle_pncp) DO UPDATE SET
                valor_total_estimado = excluded.valor_total_estimado,
                valor_total_homologado = excluded.valor_total_homologado,
                codigo_ibge = excluded.codigo_ibge,
                existe_resultado = excluded.existe_resultado
        """, (
            numero_controle, detalhe.get("valorTotalEstimado"), detalhe.get("valorTotalHomologado"),
            bool(detalhe.get("srp")), detalhe.get("objetoCompra"),
            uo.get("municipioNome"), uo.get("ufSigla"), uo.get("codigoIbge"), detalhe.get("modalidadeNome"),
            detalhe.get("situacaoCompraNome"), bool(detalhe.get("existeResultado")),
            detalhe.get("dataAberturaProposta"), detalhe.get("dataEncerramentoProposta"),
            datetime.now(timezone.utc).isoformat(),
        ))
    time.sleep(PAUSA_ENTRE_CHAMADAS)

    itens = get_com_retry(f"{PNCP_BASE}/{cnpj}/compras/{ano}/{seq}/itens") or []
    itens_onco = []
    for it in itens:
        descricao = it.get("descricao") or ""
        eh_onco = eh_medicamento_onco_de_verdade(descricao, it.get("materialOuServico"))
        principio = principio_ativo_provavel(descricao) if eh_onco else None
        cur.execute("""
            INSERT INTO oncologia.itens (
                numero_controle_pncp, numero_item, descricao, material_ou_servico,
                valor_unitario_estimado, valor_total, quantidade, unidade_medida,
                situacao_item_nome, criterio_julgamento_nome, tipo_beneficio_nome,
                tem_resultado, eh_medicamento_onco, principio_ativo_provavel
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (numero_controle_pncp, numero_item) DO UPDATE SET
                descricao = excluded.descricao,
                tem_resultado = excluded.tem_resultado,
                eh_medicamento_onco = excluded.eh_medicamento_onco,
                principio_ativo_provavel = excluded.principio_ativo_provavel
        """, (
            numero_controle, it.get("numeroItem"), descricao, it.get("materialOuServico"),
            it.get("valorUnitarioEstimado"), it.get("valorTotal"), it.get("quantidade"),
            it.get("unidadeMedida"), it.get("situacaoCompraItemNome"), it.get("criterioJulgamentoNome"),
            it.get("tipoBeneficioNome"), bool(it.get("temResultado")), eh_onco, principio,
        ))
        if eh_onco and it.get("temResultado"):
            itens_onco.append(it.get("numeroItem"))
    time.sleep(PAUSA_ENTRE_CHAMADAS)

    for numero_item in itens_onco:
        resultados = get_com_retry(f"{PNCP_BASE}/{cnpj}/compras/{ano}/{seq}/itens/{numero_item}/resultados") or []
        for res in resultados:
            cur.execute("""
                INSERT INTO oncologia.resultados (
                    numero_controle_pncp, numero_item, ni_fornecedor, nome_fornecedor,
                    tipo_pessoa, porte_fornecedor_nome, valor_unitario_homologado,
                    valor_total_homologado, percentual_desconto, quantidade_homologada,
                    data_resultado
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (numero_controle_pncp, numero_item, ni_fornecedor) DO UPDATE SET
                    valor_unitario_homologado = excluded.valor_unitario_homologado,
                    valor_total_homologado = excluded.valor_total_homologado
            """, (
                numero_controle, numero_item, res.get("niFornecedor"), res.get("nomeRazaoSocialFornecedor"),
                res.get("tipoPessoa"), res.get("porteFornecedorNome"), res.get("valorUnitarioHomologado"),
                res.get("valorTotalHomologado"), res.get("percentualDesconto"), res.get("quantidadeHomologada"),
                res.get("dataResultado"),
            ))
        time.sleep(PAUSA_ENTRE_CHAMADAS)

    con.commit()


def mostrar_status():
    con, cur = conectar_db()
    cur.execute("SELECT status, COUNT(*) FROM oncologia.progresso_detalhe GROUP BY status")
    for status, n in cur.fetchall():
        print(f"{status}: {n}")
    con.close()


def coletar():
    con, cur = conectar_db()
    popular_fila(con, cur)

    cur.execute("SELECT COUNT(*) FROM oncologia.progresso_detalhe")
    total = cur.fetchone()[0]
    print(f"INICIO total={total}", flush=True)

    feito = 0
    erro = 0
    ultimo_print = time.time()
    while True:
        # reconecta se o Supabase derrubou a conexao (pooler fecha conexao
        # ociosa/antiga) - achado real 22/jul: script morria depois de ~15min
        # com psycopg2.OperationalError/InterfaceError, sem isso a coleta parava.
        try:
            numero_controle = reivindicar_proximo(con, cur)
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            print("conexao caiu ao reivindicar; reconectando...", file=sys.stderr, flush=True)
            try:
                con.close()
            except Exception:
                pass
            time.sleep(3)
            con, cur = conectar_db()
            continue
        if numero_controle is None:
            break
        try:
            processar(con, cur, numero_controle)
            cur.execute(
                "UPDATE oncologia.progresso_detalhe SET status='feito', atualizado_em=%s WHERE numero_controle_pncp=%s",
                (datetime.now(timezone.utc).isoformat(), numero_controle),
            )
            feito += 1
            con.commit()
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
            print(f"conexao caiu processando {numero_controle} ({e}); reconectando...", file=sys.stderr, flush=True)
            try:
                con.close()
            except Exception:
                pass
            time.sleep(3)
            con, cur = conectar_db()
            # nao marca erro na fila - proxima rodada reivindica de novo (ainda 'processando',
            # o timeout de 15min em reivindicar_proximo libera pra retry natural)
            continue
        except Exception:
            con.rollback()
            cur.execute("""
                UPDATE oncologia.progresso_detalhe SET status='erro', tentativas=tentativas+1, atualizado_em=%s
                WHERE numero_controle_pncp=%s
            """, (datetime.now(timezone.utc).isoformat(), numero_controle))
            erro += 1
            con.commit()

        if time.time() - ultimo_print >= INTERVALO_PROGRESSO_S:
            pct = 100.0 * (feito + erro) / total if total else 0
            print(f"PROGRESSO feito={feito} erro={erro} total={total} pct={pct:.1f}", flush=True)
            ultimo_print = time.time()

    pct = 100.0 * (feito + erro) / total if total else 0
    print(f"FIM feito={feito} erro={erro} total={total} pct={pct:.1f}", flush=True)
    con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    if args.status:
        mostrar_status()
    else:
        coletar()
