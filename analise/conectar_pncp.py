#!/usr/bin/env python3
"""
conectar_pncp.py — Base de itens de pneu a partir do Postgres/Supabase (coleta
direta da API do PNCP, ver coletor_pncp.py/coletor_pncp_detalhe.py). Antes era
pncp_raw.db local (SQLite) — migrado jul/2026, ver analise/schema_supabase.sql.

Diferente de conectar.py (ComprasGOV bulk): esta fonte cobre as 27 UFs sem o
gap de ~17x já documentado, mas a coleta por processo (fase 2) é gradual —
`cobertura_pct()` informa quanto já foi baixado.

Uso:
    from conectar_pncp import carregar_base_pncp, cobertura_pct
    df = carregar_base_pncp()
"""

import os
import re

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

# pool_pre_ping evita erro de "conexão morta" quando o pooler do Supabase
# derruba conexão idle entre reruns do Streamlit.
ENGINE = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)

# medida tipo "215/75 R17,5" ou "205/60 R16" — captura largura/perfil/aro. Só cobre o
# padrão passeio/caminhão/moto; agrícola ("18.4-30") e câmara de ar têm formato próprio,
# não capturados aqui — ficam como NaN em medida_extraida.
RE_MEDIDA_CAPTURA = re.compile(r"(\d{3})\s*/\s*(\d{2})\s*[Rr]\s*(\d{2}(?:[.,]\d)?)")


def _extrair_medida(descricao: str) -> str | None:
    if not isinstance(descricao, str):
        return None
    m = RE_MEDIDA_CAPTURA.search(descricao)
    if not m:
        return None
    return f"{m.group(1)}/{m.group(2)} R{m.group(3).replace(',', '.')}"


def carregar_concorrencia() -> pd.DataFrame:
    """1 linha por (processo, item, fornecedor ofertante) — TODOS os ofertantes, não só o
    vencedor. Base pra concorrência em 3 granularidades: edital, item, produto/medida.
    """
    return pd.read_sql_query(
        """
        SELECT r.numero_controle_pncp, r.numero_item, r.ni_fornecedor
        FROM resultados r
        JOIN itens i ON i.numero_controle_pncp = r.numero_controle_pncp AND i.numero_item = r.numero_item
        WHERE i.eh_pneu = TRUE
        """,
        ENGINE,
    )


def cobertura_por_uf() -> pd.DataFrame:
    """Cobertura de coleta (fase 2) por UF — feito/total/pct, pra normalizar leitura de
    volume geográfico (UF com mais % coletado aparece maior sem ser maior de verdade)."""
    cov = pd.read_sql_query(
        """
        SELECT e.uf, COUNT(DISTINCT d.numero_controle_pncp) AS feito, COUNT(DISTINCT e.numero_controle_pncp) AS total
        FROM editais e
        LEFT JOIN detalhes d ON d.numero_controle_pncp = e.numero_controle_pncp
        WHERE e.dentro_periodo_alvo = TRUE
        GROUP BY e.uf
        """,
        ENGINE,
    )
    cov["cobertura_pct"] = (cov["feito"] / cov["total"] * 100).round(1)
    return cov


def cobertura_pct() -> tuple[int, int, float]:
    """(processos com detalhe já baixado, total no período alvo, %)."""
    with ENGINE.connect() as con:
        feito = con.execute(text("SELECT COUNT(*) FROM detalhes")).fetchone()[0]
        total = con.execute(text("SELECT COUNT(*) FROM editais WHERE dentro_periodo_alvo = TRUE")).fetchone()[0]
    pct = (feito / total * 100) if total else 0.0
    return feito, total, pct


def _classificar_tipo(modalidade: str) -> str:
    if not isinstance(modalidade, str) or not modalidade:
        return "Outro"
    m = modalidade.lower()
    if m.startswith("pregão"):
        return "Pregão"
    if m.startswith("dispensa"):
        return "Dispensa"
    if m.startswith("concorrência") or m.startswith("concorrencia"):
        return "Concorrência"
    return "Outro"


VALOR_UNITARIO_TETO_SANIDADE = 50_000
# achado 08/jul/26 auditando outlier em "R$ MG Passeio": item de Coromandel/MG com
# valor_unitario_estimado = R$17,3 milhões (pneu não existe a esse preço — erro de
# digitação do órgão na fonte, PNCP não valida). p99 real de pneu Passeio é ~R$7,7k;
# nenhum pneu de venda unitária (mesmo OTR gigante de mineração) passa de R$50k — teto
# generoso o bastante pra nunca cortar item real, mas corta todo lixo visto na auditoria
# (R$17,3M, R$5,8M, R$2,1M, R$1,5M... todos exames manuais confirmaram erro de dado, não
# pneu caro de verdade).

# achado 08/jul/26: Araxá/MG, "Credenciamento", TODOS os 10 itens com quantidade
# implausível pro porte do município (ex: 30.114 unidades de PNEU 215/75R17.5 — nenhum
# item passa do teto de valor_unitario sozinho, preço parece razoável, o erro está na
# quantidade). Processo republicado 2x (-000101 e -000209, dedup mantém -000101) — exceção
# manual documentada em vez de teto genérico de item/processo, porque um teto que cortasse
# isso também cortaria demanda real grande e legítima (ex: RJ tem item de R$8,8M plausível
# — frota real de capital). Decisão explícita do usuário: excluir processo pontualmente.
PROCESSOS_EXCLUIDOS_DADO_RUIM = {"19493732000199-1-000101/2025", "19493732000199-1-000209/2025"}


def carregar_base_pncp() -> pd.DataFrame:
    """1 linha por item elegível (eh_pneu=1), mesmo shape de colunas da base ComprasGOV
    (base_pneu.sql) pra reusar a mesma lógica de gráfico se algum dia fizer sentido —
    mas o dashboard_pncp.py usa suas próprias abas, não compartilha código com dashboard.py.
    """
    itens = pd.read_sql_query(
        """
        SELECT numero_controle_pncp, numero_item, descricao, valor_total AS valor_item,
               valor_unitario_estimado, quantidade, tem_resultado, categoria
        FROM itens
        WHERE eh_pneu = TRUE
          AND (valor_unitario_estimado IS NULL OR valor_unitario_estimado <= 50000)
        """,
        ENGINE,
    )

    detalhes = pd.read_sql_query(
        """
        SELECT numero_controle_pncp, uf_sigla AS uf, municipio_nome AS municipio,
               codigo_ibge, modalidade_nome, srp, data_abertura_proposta,
               valor_total_estimado
        FROM detalhes
        WHERE valor_total_estimado IS NULL OR valor_total_estimado <= 300000000
        """,
        ENGINE,
    )
    # achado 08/jul/26: item com valor_unitario "razoável" (<50k) escapa o teto de item, mas
    # o PROCESSO inteiro pode estar corrompido na fonte — Coromandel/MG tinha
    # valor_total_estimado = R$7,48 BILHÕES (processo inteiro, não só o item já cortado
    # acima). Teto de R$300 milhões no processo: generoso o bastante pra nunca cortar
    # licitação real (mesmo consórcio estadual grande fica bem abaixo disso), mas corta
    # esse tipo de erro sistêmico de processo inteiro.

    # achado 08/jul/26: retificação de edital no PNCP gera numero_controle_pncp novo pro
    # MESMO processo (mesmo órgão, mesma data de abertura, mesmo valor total) — 500 grupos
    # duplicados achados (1.406 de 17.660 processos, ~8%), ex: Araxá/MG "-000101" e "-000209"
    # idênticos. Sem dedup, cada duplicata dobra o valor e a contagem de processo no
    # dashboard. Mantém só 1 por (órgão, data abertura, valor total) — o de menor
    # numero_controle_pncp (mais antigo, versão original antes da retificação).
    detalhes = detalhes.sort_values("numero_controle_pncp")
    _cnpj = detalhes["numero_controle_pncp"].str.split("-").str[0]
    chave_dedup = pd.DataFrame({
        "cnpj": _cnpj, "data": detalhes["data_abertura_proposta"], "valor": detalhes["valor_total_estimado"],
    }, index=detalhes.index)
    mantidos = ~chave_dedup.duplicated(keep="first") | chave_dedup["data"].isna() | chave_dedup["valor"].isna()
    detalhes = detalhes[mantidos]

    # achado 08/jul/26 auditando métricas de fornecedor/desconto: ordem_classificacao_srp=1
    # NÃO é único por item — 291 itens têm múltiplos fornecedores empatados em ordem=1.
    # Confirmado que é o comportamento normal de Registro de Preço (múltiplos fornecedores
    # registrados no mesmo item, ex: cota principal + cota reservada ME/EPP, cada um com
    # ordem=1 dentro da própria cota) — não é 1 vencedor por item, é potencialmente vários,
    # cada um genuíno. O erro estava em tentar reduzir isso a "1 por item" via MIN(ordem);
    # o filtro certo é excluir fornecedor "fantasma" (registrado mas sem contratação
    # efetiva, valor_total_homologado=0) — 210 de 291 itens tinham exatamente esse padrão
    # (1 fornecedor real + resto zerado). Preserva os casos de cota múltipla legítima (69
    # itens com 2+ fornecedores reais no mesmo item) em vez de escolher 1 arbitrariamente.
    resultados = pd.read_sql_query(
        """
        SELECT numero_controle_pncp, numero_item, ni_fornecedor AS cod_fornecedor,
               nome_fornecedor, valor_unitario_homologado AS valor_unitario_resultado,
               valor_total_homologado AS valor_total_resultado
        FROM resultados
        WHERE valor_total_homologado IS NOT NULL AND valor_total_homologado > 0
        """,
        ENGINE,
    )

    # achado 08/jul/26: quando o item tem 2+ fornecedores reais (cota principal + reservada),
    # o merge left item->resultados duplicava a linha do ITEM inteiro (valor_item incluso) —
    # inflava Valor Total/Ticket médio/Geografia/Sazonalidade em ~0,3% (185 linhas duplicadas
    # medido em 08/jul/26, cresce com a coleta). valor_item é atributo do ITEM, não do
    # fornecedor — não pode duplicar por causa de quantos fornecedores venceram aquele item.
    # Mantém só o fornecedor de MAIOR valor_total_resultado como representante do item aqui
    # (pra desconto/fornecedor cruzado com valor_item); granularidade fina de TODOS os
    # fornecedores reais fica em carregar_fornecedores_resultado(), usada separadamente nos
    # gráficos de fornecedor dominante/concentração (que não usam valor_item, então fan-out
    # ali é correto e não deve ser perdido).
    resultados_principal = (
        resultados.sort_values("valor_total_resultado", ascending=False)
                  .drop_duplicates(subset=["numero_controle_pncp", "numero_item"], keep="first")
    )

    itens = itens[~itens["numero_controle_pncp"].isin(PROCESSOS_EXCLUIDOS_DADO_RUIM)]

    # inner, não left — "detalhes" já teve a dedup de processo republicado acima; left
    # traria de volta os itens do numero_controle_pncp duplicado que a dedup removeu.
    df = itens.merge(detalhes, on="numero_controle_pncp", how="inner")
    df = df.merge(resultados_principal, on=["numero_controle_pncp", "numero_item"], how="left")

    df["codigo_ibge"] = pd.to_numeric(df["codigo_ibge"], errors="coerce")
    df["data_abertura_proposta"] = pd.to_datetime(df["data_abertura_proposta"], errors="coerce", utc=True)
    df["ano_mes"] = df["data_abertura_proposta"].dt.strftime("%Y-%m")
    df["tipo"] = df["modalidade_nome"].apply(_classificar_tipo)
    df["regime"] = df["srp"].apply(lambda v: "RP" if v else "CD")
    df["cod_compra"] = df["numero_controle_pncp"]
    df["tem_resultado"] = df["tem_resultado"].astype(bool)
    df["medida_extraida"] = df["descricao"].apply(_extrair_medida)

    return df


def carregar_fornecedores_resultado() -> pd.DataFrame:
    """1 linha por (item, fornecedor real vencedor) — granularidade fina, aceita fan-out
    de propósito (cota principal + reservada no mesmo item são 2 fornecedores diferentes,
    ambos legítimos). Não tem valor_item (evita a tentação de somar valor_item aqui, que
    duplicaria — ver comentário em carregar_base_pncp). Usar só pra métricas de fornecedor
    (dominante, concentração) — nunca pra Valor Total/Ticket médio/Geografia."""
    resultados = pd.read_sql_query(
        """
        SELECT r.numero_controle_pncp, r.numero_item, r.ni_fornecedor AS cnpj_fornecedor,
               r.nome_fornecedor,
               r.valor_unitario_homologado AS valor_unitario_resultado,
               r.valor_total_homologado AS valor_total_resultado,
               i.categoria, i.descricao, d.uf_sigla AS uf, d.modalidade_nome, d.srp,
               d.data_abertura_proposta
        FROM resultados r
        JOIN itens i ON i.numero_controle_pncp = r.numero_controle_pncp AND i.numero_item = r.numero_item
        JOIN detalhes d ON d.numero_controle_pncp = r.numero_controle_pncp
        WHERE i.eh_pneu = TRUE
          AND r.valor_total_homologado IS NOT NULL AND r.valor_total_homologado > 0
          AND (i.valor_unitario_estimado IS NULL OR i.valor_unitario_estimado <= 50000)
          AND (d.valor_total_estimado IS NULL OR d.valor_total_estimado <= 300000000)
        """,
        ENGINE,
    )
    resultados = resultados[~resultados["numero_controle_pncp"].isin(PROCESSOS_EXCLUIDOS_DADO_RUIM)]
    resultados["medida_extraida"] = resultados["descricao"].apply(_extrair_medida)
    resultados["tipo"] = resultados["modalidade_nome"].apply(_classificar_tipo)
    resultados["regime"] = resultados["srp"].apply(lambda v: "RP" if v else "CD")
    resultados["data_abertura_proposta"] = pd.to_datetime(resultados["data_abertura_proposta"], errors="coerce", utc=True)
    resultados["ano_mes"] = resultados["data_abertura_proposta"].dt.strftime("%Y-%m")

    # achado 08/jul/26: mesmo CNPJ aparece com até 6 grafias diferentes de nome no PNCP
    # (ex: "RAVI E-COMMERCE LTDA.", "RAVI E-COMMERCE LTDA - EPP", "RAVI E-COMMERCE"...) —
    # órgão digita o nome à mão a cada homologação, sem normalização. Agrupar por
    # nome_fornecedor (texto livre) fragmenta o mesmo fornecedor em várias linhas,
    # subestimando a concentração real de mercado. Agrupa por CNPJ (cnpj_fornecedor,
    # confiável) e usa a grafia mais frequente daquele CNPJ como rótulo de exibição.
    nome_mais_comum = (
        resultados.groupby(["cnpj_fornecedor", "nome_fornecedor"]).size()
                  .reset_index(name="n").sort_values("n", ascending=False)
                  .drop_duplicates(subset="cnpj_fornecedor", keep="first")
                  .set_index("cnpj_fornecedor")["nome_fornecedor"]
    )
    resultados["nome_fornecedor"] = resultados["cnpj_fornecedor"].map(nome_mais_comum).fillna(resultados["nome_fornecedor"])
    return resultados


if __name__ == "__main__":
    feito, total, pct = cobertura_pct()
    print(f"Cobertura: {feito}/{total} processos ({pct:.1f}%)")
    df = carregar_base_pncp()
    print(f"Itens elegíveis (eh_pneu=1): {len(df)}")
    print(df["uf"].value_counts())
