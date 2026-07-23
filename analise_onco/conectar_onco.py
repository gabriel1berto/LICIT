#!/usr/bin/env python3
"""
conectar_onco.py — Base de itens de medicamento oncológico a partir do
Postgres/Supabase (schema `oncologia`, isolado de `public`/`cotacao_fornecedor`
do pneu). Espelha analise/conectar_pncp.py — mesmo shape de coluna, mesma
lógica de agregação — pra reusar exatamente o mesmo código de dashboard.

Mapeamento de conceito (pneu → oncologia):
  medida_extraida  → principio_ativo_provavel (já computado no coletor_detalhe,
                      via filtro_onco.py — não precisa regex aqui)
  categoria        → classe_farmaco (Alquilante/Antimetabolito/Quimioterapico
                      classico/Inibidor de quinase/Anticorpo monoclonal/
                      Hormonal-endocrino/Outro — 6 classes fixas, mesmo padrão
                      de categoria fixa do pneu)

Uso:
    from conectar_onco import carregar_base_onco, cobertura_pct
    df = carregar_base_onco()
"""

import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from filtro_onco import classificar_classe_farmaco

load_dotenv()

ENGINE = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)


def cobertura_por_uf() -> pd.DataFrame:
    cov = pd.read_sql_query(
        """
        SELECT e.uf, COUNT(DISTINCT d.numero_controle_pncp) AS feito, COUNT(DISTINCT e.numero_controle_pncp) AS total
        FROM oncologia.editais e
        LEFT JOIN oncologia.detalhes d ON d.numero_controle_pncp = e.numero_controle_pncp
        GROUP BY e.uf
        """,
        ENGINE,
    )
    cov["cobertura_pct"] = (cov["feito"] / cov["total"] * 100).round(1)
    return cov


def cobertura_pct() -> tuple[int, int, float]:
    """(processos com detalhe já baixado, total de editais coletados, %)."""
    with ENGINE.connect() as con:
        feito = con.execute(text("SELECT COUNT(*) FROM oncologia.progresso_detalhe WHERE status='feito'")).fetchone()[0]
        total = con.execute(text("SELECT COUNT(*) FROM oncologia.progresso_detalhe")).fetchone()[0]
    pct = (feito / total * 100) if total else 0.0
    return feito, total, pct


def carregar_editais_abertos_onco() -> pd.DataFrame:
    """Espelha conectar_pncp.carregar_editais_abertos() do pneu — 1 linha por
    edital com proposta ainda aberta e pelo menos 1 item eh_medicamento_onco=TRUE.

    Diferença deliberada: SEM teto de valor por item (o do pneu era R$50k, calibrado
    pra bug de digitação em pneu/câmara de ar — medicamento oncológico legitimamente
    custa dezenas de milhares por unidade em biológico/alvo molecular, um teto copiado
    do pneu descartaria item real). Sem lista de PROCESSOS_EXCLUIDOS também — essa
    lista veio de auditoria manual específica do pneu, nunca feita aqui.
    """
    df = pd.read_sql_query(
        """
        SELECT e.numero_controle_pncp, e.orgao_cnpj, e.ano, e.numero_sequencial,
               e.uf, e.municipio_nome AS municipio, e.orgao_nome, e.modalidade_licitacao_nome,
               d.objeto_compra, d.valor_total_estimado, d.data_abertura_proposta,
               d.data_encerramento_proposta, d.codigo_ibge, d.srp,
               COUNT(i.numero_item) FILTER (WHERE i.eh_medicamento_onco) AS n_itens_onco,
               SUM(i.valor_total) FILTER (WHERE i.eh_medicamento_onco) AS valor_onco_estimado,
               (SELECT COUNT(*) FROM oncologia.itens i2 WHERE i2.numero_controle_pncp = e.numero_controle_pncp) AS n_itens_total
        FROM oncologia.editais e
        JOIN oncologia.detalhes d ON d.numero_controle_pncp = e.numero_controle_pncp
        JOIN oncologia.itens i ON i.numero_controle_pncp = e.numero_controle_pncp
        WHERE d.situacao_compra_nome = 'Divulgada no PNCP'
          AND d.data_encerramento_proposta IS NOT NULL
          AND d.data_encerramento_proposta::timestamp > (now() AT TIME ZONE 'America/Sao_Paulo')
          AND i.eh_medicamento_onco = TRUE
          AND e.modalidade_licitacao_nome NOT ILIKE '%%leil%%'
        GROUP BY e.numero_controle_pncp, e.orgao_cnpj, e.ano, e.numero_sequencial, e.uf,
                 e.municipio_nome, e.orgao_nome, e.modalidade_licitacao_nome,
                 d.objeto_compra, d.valor_total_estimado, d.data_abertura_proposta,
                 d.data_encerramento_proposta, d.codigo_ibge, d.srp
        """,
        ENGINE,
    )
    if df.empty:
        return df

    # mesmo achado de retificação do pneu (edital republicado gera numero_controle_pncp
    # novo) — mantém a versão mais recente, chave por valor+encerramento.
    df = df.sort_values("numero_controle_pncp")
    chave_dedup = (
        df["orgao_cnpj"] + "|" + df["valor_total_estimado"].astype(str) + "|"
        + df["data_encerramento_proposta"].astype(str)
    )
    df = df[~chave_dedup.duplicated(keep="last")]

    df["data_encerramento_proposta"] = pd.to_datetime(df["data_encerramento_proposta"])
    agora_brt = pd.Timestamp.now(tz="America/Sao_Paulo").tz_localize(None)
    df["dias_restantes"] = (df["data_encerramento_proposta"] - agora_brt).dt.total_seconds() / 86400
    df["regime"] = df["srp"].apply(lambda v: "RP" if v else "CD")
    df["pncp_url"] = (
        "https://pncp.gov.br/app/editais/" + df["orgao_cnpj"] + "/" + df["ano"] + "/" + df["numero_sequencial"]
    )
    df["codigo_ibge"] = pd.to_numeric(df["codigo_ibge"], errors="coerce")
    return df


def carregar_itens_onco_editais_abertos(numeros_controle: list[str]) -> pd.DataFrame:
    """Espelha carregar_itens_pneu_editais_abertos() do pneu."""
    if not numeros_controle:
        return pd.DataFrame(columns=["numero_controle_pncp", "descricao", "quantidade", "principio_ativo_provavel"])
    df = pd.read_sql_query(
        """
        SELECT numero_controle_pncp, descricao, quantidade, valor_unitario_estimado, principio_ativo_provavel
        FROM oncologia.itens
        WHERE eh_medicamento_onco = TRUE AND numero_controle_pncp = ANY(%(nums)s)
        """,
        ENGINE,
        params={"nums": list(numeros_controle)},
    )
    return df


def carregar_capag_municipios() -> pd.DataFrame:
    """Espelha conectar_pncp.carregar_capag_municipios() — mesmo schema `capag`
    (compartilhado entre pneu e oncológico, dado não é específico de negócio)."""
    df = pd.read_sql_query(
        "SELECT codigo_ibge, uf, capag FROM capag.municipios", ENGINE
    )
    df["codigo_ibge"] = pd.to_numeric(df["codigo_ibge"], errors="coerce")
    return df


def carregar_capag_estados() -> pd.DataFrame:
    return pd.read_sql_query("SELECT uf, capag FROM capag.estados", ENGINE)


def ultima_carga_detalhes() -> pd.Timestamp | None:
    """Timestamp (BRT) da coleta mais recente em oncologia.detalhes — espelha
    conectar_pncp.ultima_carga_detalhes() do pneu."""
    with ENGINE.connect() as con:
        v = con.execute(text("SELECT MAX(coletado_em) FROM oncologia.detalhes")).fetchone()[0]
    if v is None:
        return None
    return pd.Timestamp(v).tz_convert("America/Sao_Paulo")


def _classificar_tipo(modalidade: str) -> str:
    if not isinstance(modalidade, str) or not modalidade:
        return "Outro"
    m = modalidade.lower()
    if m.startswith("pregão") or m.startswith("pregao"):
        return "Pregão"
    if m.startswith("dispensa"):
        return "Dispensa"
    if m.startswith("concorrência") or m.startswith("concorrencia"):
        return "Concorrência"
    if m.startswith("inexigibilidade"):
        return "Inexigibilidade"
    return "Outro"


def carregar_base_onco() -> pd.DataFrame:
    """1 linha por item elegível (eh_medicamento_onco=TRUE), mesmo shape de
    coluna de carregar_base_pncp() do pneu (uf, municipio, regime, tipo,
    categoria, medida_extraida, valor_item, valor_unitario_estimado,
    valor_unitario_resultado, quantidade, tem_resultado, cod_compra, ano_mes)."""
    itens = pd.read_sql_query(
        """
        SELECT numero_controle_pncp, numero_item, descricao, valor_total AS valor_item,
               valor_unitario_estimado, quantidade, tem_resultado, principio_ativo_provavel
        FROM oncologia.itens
        WHERE eh_medicamento_onco = TRUE
        """,
        ENGINE,
    )

    detalhes = pd.read_sql_query(
        """
        SELECT d.numero_controle_pncp, d.uf_sigla AS uf, d.municipio_nome AS municipio,
               d.codigo_ibge, d.modalidade_nome, d.srp, d.data_abertura_proposta,
               d.valor_total_estimado, e.orgao_cnpj
        FROM oncologia.detalhes d
        JOIN oncologia.editais e ON e.numero_controle_pncp = d.numero_controle_pncp
        """,
        ENGINE,
    )

    # achado 23/jul/2026 (double-check "valor total parece inflado"): mesmo bug de
    # retificação já corrigido no pneu (08/jul/2026, ver conectar_pncp.carregar_base_pncp)
    # nunca foi portado pra cá — edital republicado no PNCP gera numero_controle_pncp
    # novo pro MESMO processo (mesmo órgão, mesma data de abertura, mesmo valor total).
    # Mantém só 1 por (órgão, data abertura, valor total) — o de menor numero_controle_pncp.
    detalhes = detalhes.sort_values("numero_controle_pncp")
    _chave_retificacao = pd.DataFrame({
        "cnpj": detalhes["orgao_cnpj"], "data": detalhes["data_abertura_proposta"],
        "valor": detalhes["valor_total_estimado"],
    }, index=detalhes.index)
    _mantidos = (
        ~_chave_retificacao.duplicated(keep="first")
        | _chave_retificacao["data"].isna() | _chave_retificacao["valor"].isna()
    )
    detalhes = detalhes[_mantidos].drop(columns="orgao_cnpj")

    resultados = pd.read_sql_query(
        """
        SELECT numero_controle_pncp, numero_item, ni_fornecedor AS cod_fornecedor,
               nome_fornecedor, valor_unitario_homologado AS valor_unitario_resultado,
               valor_total_homologado AS valor_total_resultado
        FROM oncologia.resultados
        WHERE valor_total_homologado IS NOT NULL AND valor_total_homologado > 0
        """,
        ENGINE,
    )
    resultados_principal = (
        resultados.sort_values("valor_total_resultado", ascending=False)
                  .drop_duplicates(subset=["numero_controle_pncp", "numero_item"], keep="first")
    )

    df = itens.merge(detalhes, on="numero_controle_pncp", how="inner")
    df = df.merge(resultados_principal, on=["numero_controle_pncp", "numero_item"], how="left")

    # achado 23/jul/2026: MESMA linha de item (fármaco+preço unitário+quantidade+data)
    # publicada sob 2 CNPJs diferentes do MESMO ente (ex: "Estado da Bahia" e "Fundo
    # Estadual de Saúde do Estado da Bahia" — 79 grupos, R$114,6 milhões, itens judiciais)
    # — a dedup por órgão acima não pega isso porque o CNPJ é diferente. Mantém 1 por
    # (fármaco, valor unitário, quantidade, data de abertura), menor numero_controle_pncp.
    # Risco aceito: colapsa também coincidência real (2 estados diferentes comprando a
    # mesma quantidade pelo mesmo preço no mesmo dia) — extremamente improvável dado
    # preço com 2-4 casas decimais, mas é uma escolha, não uma certeza matemática.
    df = df.sort_values("numero_controle_pncp")
    _chave_cross_cnpj = pd.DataFrame({
        "principio": df["principio_ativo_provavel"], "vu": df["valor_unitario_estimado"],
        "qtd": df["quantidade"], "data": df["data_abertura_proposta"],
    }, index=df.index)
    _mantidos_item = (
        ~_chave_cross_cnpj.duplicated(keep="first")
        | _chave_cross_cnpj["vu"].isna() | _chave_cross_cnpj["qtd"].isna() | _chave_cross_cnpj["data"].isna()
    )
    df = df[_mantidos_item]

    df["codigo_ibge"] = pd.to_numeric(df["codigo_ibge"], errors="coerce")
    df["data_abertura_proposta"] = pd.to_datetime(df["data_abertura_proposta"], errors="coerce", utc=True)
    df["ano_mes"] = df["data_abertura_proposta"].dt.strftime("%Y-%m")
    df["tipo"] = df["modalidade_nome"].apply(_classificar_tipo)
    df["regime"] = df["srp"].apply(lambda v: "RP" if v else "CD")
    df["cod_compra"] = df["numero_controle_pncp"]
    df["tem_resultado"] = df["tem_resultado"].astype(bool)
    df["medida_extraida"] = df["principio_ativo_provavel"]  # nome de coluna igual ao pneu, valor = fármaco
    df["categoria"] = df["principio_ativo_provavel"].apply(classificar_classe_farmaco)

    return df


def carregar_fornecedores_resultado() -> pd.DataFrame:
    """1 linha por (item, fornecedor real vencedor) — mesmo shape de
    carregar_fornecedores_resultado() do pneu."""
    resultados = pd.read_sql_query(
        """
        SELECT r.numero_controle_pncp, r.numero_item, r.ni_fornecedor AS cnpj_fornecedor,
               r.nome_fornecedor,
               r.valor_unitario_homologado AS valor_unitario_resultado,
               r.valor_total_homologado AS valor_total_resultado,
               i.principio_ativo_provavel, i.descricao, i.quantidade,
               d.uf_sigla AS uf, d.modalidade_nome, d.srp, d.data_abertura_proposta,
               d.valor_total_estimado
        FROM oncologia.resultados r
        JOIN oncologia.itens i ON i.numero_controle_pncp = r.numero_controle_pncp AND i.numero_item = r.numero_item
        JOIN oncologia.detalhes d ON d.numero_controle_pncp = r.numero_controle_pncp
        WHERE i.eh_medicamento_onco = TRUE
          AND r.valor_total_homologado IS NOT NULL AND r.valor_total_homologado > 0
        """,
        ENGINE,
    )
    resultados["medida_extraida"] = resultados["principio_ativo_provavel"]
    resultados["categoria"] = resultados["principio_ativo_provavel"].apply(classificar_classe_farmaco)
    resultados["tipo"] = resultados["modalidade_nome"].apply(_classificar_tipo)
    resultados["regime"] = resultados["srp"].apply(lambda v: "RP" if v else "CD")
    resultados["data_abertura_proposta"] = pd.to_datetime(resultados["data_abertura_proposta"], errors="coerce", utc=True)
    resultados["ano_mes"] = resultados["data_abertura_proposta"].dt.strftime("%Y-%m")
    return resultados


def carregar_lat_lon() -> pd.DataFrame:
    import pathlib
    ll = pd.read_csv(pathlib.Path(__file__).parent / "municipios_lat_lon.csv")
    return ll[["codigo_ibge", "latitude", "longitude"]]


def cobertura_vocabulario() -> pd.DataFrame:
    """1 linha por termo buscado — total real na API vs quando foi buscado."""
    return pd.read_sql_query(
        "SELECT termo, tipo, total_ultima_busca, ultima_busca_em FROM oncologia.vocabulario_termos ORDER BY total_ultima_busca DESC",
        ENGINE,
    )


if __name__ == "__main__":
    feito, total, pct = cobertura_pct()
    print(f"Cobertura: {feito}/{total} processos ({pct:.1f}%)")
    df = carregar_base_onco()
    print(f"Itens elegíveis (eh_medicamento_onco=1): {len(df)}")
    if not df.empty:
        print(df["uf"].value_counts())
