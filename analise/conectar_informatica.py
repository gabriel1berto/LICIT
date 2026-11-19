#!/usr/bin/env python3
"""
conectar_informatica.py — Leitura da base de editais de informática (Supabase, schema
`informatica`, ver coletor_informatica.py). Categoria e cobertura GET de cada item são
calculadas AQUI, na leitura (filtro_informatica.py) — nada disso é gravado no banco,
então ajuste no filtro vale na próxima carga da página, sem recompute.
"""

import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

from filtro_informatica import classificar_item, item_valido_valor, objeto_eh_servico, selo_get

load_dotenv()

ENGINE = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)

SELO_PENDENTE = "Itens não coletados"

_FILTRO_ABERTO = """
    situacao_nome = 'Divulgada no PNCP'
    AND COALESCE(cancelado, FALSE) = FALSE
    AND COALESCE(modalidade_licitacao_nome, '') NOT ILIKE 'Leil%%'
    AND data_fim_vigencia IS NOT NULL
    AND data_fim_vigencia > to_char(now() AT TIME ZONE 'America/Sao_Paulo', 'YYYY-MM-DD"T"HH24:MI')
"""


def _datas(serie: pd.Series) -> pd.Series:
    # Mesmo tratamento do conectar_pecas.py: PNCP alterna formato com/sem segundos, e ano
    # digitado errado ("5026-...") estoura o Timestamp — vira data distante válida.
    return pd.to_datetime(serie, format="ISO8601", errors="coerce")


def carregar_itens_informatica() -> pd.DataFrame:
    df = pd.read_sql_query(
        f"""
        SELECT i.numero_controle_pncp, i.numero_item, i.descricao, i.quantidade, i.unidade_medida,
               i.valor_unitario_estimado, i.valor_total, i.material_ou_servico, i.beneficio_nome,
               COALESCE(e.descricao, e.titulo) AS objeto_edital
        FROM informatica.itens i
        JOIN informatica.editais e USING (numero_controle_pncp)
        WHERE i.numero_controle_pncp IN (
            SELECT numero_controle_pncp FROM informatica.editais WHERE {_FILTRO_ABERTO}
        )
        """,
        ENGINE,
    )
    if df.empty:
        return df.assign(categoria=None, cobertura_get=None)
    cls = df["descricao"].apply(classificar_item)
    df["categoria"] = cls.str[0]
    df["cobertura_get"] = cls.str[1]
    # Item deixa de contar como informática quando o EDITAL é serviço/locação ou o unitário
    # é absurdo (lote/erro) — ver filtro_informatica.py. Fica na base, só sem categoria.
    servico = df["objeto_edital"].apply(objeto_eh_servico)
    valor_ruim = ~df["valor_unitario_estimado"].apply(item_valido_valor)
    descarta = servico | valor_ruim
    df.loc[descarta, ["categoria", "cobertura_get"]] = None
    # valorTotal às vezes vem 0 com unitário preenchido — recalcula pra não sumir valor
    vt = df["valor_total"].where(df["valor_total"] > 0, df["valor_unitario_estimado"] * df["quantidade"])
    df["valor_item"] = vt.fillna(0)
    return df


def carregar_editais_informatica(itens: pd.DataFrame | None = None) -> pd.DataFrame:
    df = pd.read_sql_query(
        f"""
        SELECT numero_controle_pncp, orgao_cnpj, ano, numero_sequencial, uf, codigo_ibge,
               municipio_nome AS municipio, orgao_nome, unidade_nome, modalidade_licitacao_nome,
               titulo, descricao, srp, link_sistema_origem, data_inicio_vigencia,
               data_fim_vigencia, valor_total_estimado, termos, itens_coletados_em
        FROM informatica.editais
        WHERE {_FILTRO_ABERTO}
        """,
        ENGINE,
    )
    if df.empty:
        return df

    # Retificação/republicação: PNCP gera numero_controle novo pro mesmo processo (achado
    # 19/nov/2026: Caucaia/CE 196 e 197 idênticos). Mesmo órgão + mesmo prazo + mesmo valor
    # = mesmo edital; fica o de número maior (mais recente). Sem valor, não dá pra afirmar.
    df = df.sort_values("numero_controle_pncp", ascending=False)
    com_valor = df["valor_total_estimado"].fillna(0) > 0
    dup = df[com_valor].duplicated(["orgao_cnpj", "data_fim_vigencia", "valor_total_estimado"])
    df = df.drop(dup[dup].index)

    df["data_fim_vigencia"] = _datas(df["data_fim_vigencia"]).fillna(pd.Timestamp("2200-01-01"))
    df["data_inicio_vigencia"] = _datas(df["data_inicio_vigencia"])
    agora = pd.Timestamp.now(tz="America/Sao_Paulo").tz_localize(None)
    df["dias_restantes"] = (df["data_fim_vigencia"] - agora).dt.total_seconds() / 86400
    # Futuro = publicado, mas abertura de proposta ainda não chegou.
    df["futuro"] = df["data_inicio_vigencia"].notna() & (df["data_inicio_vigencia"] > agora)
    df["regime"] = df["srp"].map({True: "RP", False: "CD"})
    df["termos"] = df["termos"].apply(lambda t: ", ".join(sorted(t)) if t is not None else "")
    df["pncp_url"] = (
        "https://pncp.gov.br/app/editais/" + df["orgao_cnpj"] + "/" + df["ano"] + "/" + df["numero_sequencial"]
    )
    df["objeto"] = df["descricao"].fillna(df["titulo"]).fillna("")

    if itens is None:
        itens = carregar_itens_informatica()
    info = itens[itens["categoria"].notna()] if not itens.empty else itens
    n_total = itens.groupby("numero_controle_pncp").size() if not itens.empty else pd.Series(dtype=int)
    if info.empty:
        agg = pd.DataFrame()
    else:
        cob_ok = info["cobertura_get"].isin(["sim", "talvez"])
        agg = pd.DataFrame({
            "n_itens_info": info.groupby("numero_controle_pncp").size(),
            "n_get_sim": info[info["cobertura_get"] == "sim"].groupby("numero_controle_pncp").size(),
            "n_get_talvez": info[info["cobertura_get"] == "talvez"].groupby("numero_controle_pncp").size(),
            "n_get_nao": info[info["cobertura_get"] == "nao"].groupby("numero_controle_pncp").size(),
            "valor_info": info.groupby("numero_controle_pncp")["valor_item"].sum(),
            "valor_get": info[cob_ok].groupby("numero_controle_pncp")["valor_item"].sum(),
            "categorias": info.groupby("numero_controle_pncp")["categoria"].apply(
                lambda s: ", ".join(sorted(set(s)))),
            "selo": info.groupby("numero_controle_pncp")["cobertura_get"].apply(lambda s: selo_get(list(s))),
        })
    df = df.join(agg, on="numero_controle_pncp")
    df["n_itens_total"] = df["numero_controle_pncp"].map(n_total).fillna(0).astype(int)
    for c in ("n_itens_info", "n_get_sim", "n_get_talvez", "n_get_nao"):
        df[c] = df[c].fillna(0).astype(int) if c in df else 0
    for c in ("valor_info", "valor_get"):
        df[c] = df[c].fillna(0.0) if c in df else 0.0
    df["categorias"] = df["categorias"].fillna("") if "categorias" in df else ""
    if "selo" not in df:
        df["selo"] = None
    df["selo"] = df["selo"].where(df["itens_coletados_em"].notna(), SELO_PENDENTE)
    df["selo"] = df["selo"].fillna("Sem item de informática")
    return df


if __name__ == "__main__":
    it = carregar_itens_informatica()
    ed = carregar_editais_informatica(it)
    print(f"Editais abertos/futuros: {len(ed)} · itens: {len(it)}")
    if not ed.empty:
        print(ed["selo"].value_counts())
        print(ed.loc[ed["uf"].isin(["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"]), "selo"].value_counts())
