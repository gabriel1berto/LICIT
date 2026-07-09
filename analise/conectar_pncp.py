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

# medida passeio/caminhão: "215/75 R17,5" ou "205/60 R16" — largura/perfil/aro com R.
RE_MEDIDA_CAPTURA = re.compile(r"(\d{3})\s*/\s*(\d{2})\s*[Rr]\s*(\d{2}(?:[.,]\d)?)")
# achado 08/jul/26 auditando cobertura de medida por categoria: regex acima só cobria
# Caminhão (76%) e Passeio (34%) — Agrícola 0%, Câmara de ar 3%, Moto 3%. 3 padrões novos
# pra cobrir formato real visto na amostra:
# - agrícola/câmara sem R, com hífen/X: "12.4-24", "12.4X24", "900 X 20", "12-16,5"
# (decimal em qualquer um dos 2 números, ou nenhum — "900 X 20" é 2 inteiros)
RE_MEDIDA_AGRICOLA = re.compile(r"\b(\d{1,4}(?:[.,]\d{1,2})?)\s*[-xX/]\s*(\d{2}(?:[.,]\d{1,2})?)\b")
# - câmara com R colado sem espaço: "1000R20", "750R16" (formato caminhão sem barra/espaço)
RE_MEDIDA_CAMARA_COLADA = re.compile(r"\b(\d{3,4})[Rr](\d{2})\b")
# - câmara/passeio sem a letra R: "165/70 14" (3 números) ou "1000/20", "750/16" (2 números,
# largura sem perfil separado — mesma notação do colado acima, só com barra em vez de R)
RE_MEDIDA_SEM_R = re.compile(r"\b(\d{3})\s*/\s*(\d{2})\s+(\d{2}(?:[.,]\d)?)\b")
RE_MEDIDA_BARRA_2NUM = re.compile(r"\b(\d{3,4})\s*/\s*(\d{2})\b")
# - moto: "referencia 120/80, aro 18" / "MEDIDAS: 90/90; ARO: 21" / "160/60; ARO: R17"
RE_MEDIDA_MOTO = re.compile(r"(\d{2,3})\s*/\s*(\d{2,3})[,;\s]+aro[:\s]*r?(\d{2})", re.IGNORECASE)


def _extrair_medida(descricao: str) -> str | None:
    """achado 08/jul/26: item de MA descrevia 3 produtos diferentes num "item" só
    ("Pneu ônibus 295/80R22.5 - 6un. Pneu Hilux 265/70R16 - 4un. Pneu van 195/75R16 -
    4un") — pegar só a 1ª medida encontrada atribui o valor errado à medida errada
    (203 itens têm 2+ medidas distintas na descrição). Se achar mais de 1 medida
    diferente, a descrição é ambígua — não confiável, retorna None em vez de chutar.
    Tenta os padrões na ordem: R-completo (mais confiável) → sem-R → colado → moto →
    agrícola (mais genérico, por último — maior risco de falso positivo com número
    solto tipo "5 ANOS DE GARANTIA")."""
    if not isinstance(descricao, str):
        return None
    medidas: set[str] = set()
    for a, b, c in RE_MEDIDA_CAPTURA.findall(descricao):
        medidas.add(f"{a}/{b} R{c.replace(',', '.')}")
    if not medidas:
        for a, b, c in RE_MEDIDA_SEM_R.findall(descricao):
            medidas.add(f"{a}/{b} R{c.replace(',', '.')}")
    if not medidas:
        for a, b in RE_MEDIDA_CAMARA_COLADA.findall(descricao):
            medidas.add(f"{a}-{b}")  # "1000R20" -> "1000-20" (sem perfil, notação caminhão)
    if not medidas:
        for a, b, c in RE_MEDIDA_MOTO.findall(descricao):
            medidas.add(f"{a}/{b} R{c}")
    if not medidas:
        for a, b in RE_MEDIDA_BARRA_2NUM.findall(descricao):
            medidas.add(f"{a}-{b}")  # "1000/20" -> "1000-20", mesma notação do colado
    if not medidas:
        for a, b in RE_MEDIDA_AGRICOLA.findall(descricao):
            medidas.add(f"{a.replace(',', '.')}-{b.replace(',', '.')}")
    if not medidas:
        return None
    if len(medidas) > 1:
        return None
    return medidas.pop()


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

    # achado 08/jul/26: 9 itens (2 processos inteiros de PE + 1 de PB) com
    # valor_unitario_resultado 10-40x o valor_unitario_estimado — vencedor não oferta MAIS
    # que a estimativa num processo competitivo, erro sistemático de escala na fonte
    # (confirmado: 275/80R22.5 na PB tinha resultado R$17.900 vs preço real nacional de
    # ~R$1.700-2.900). Só essa direção (resultado >> estimado) é tratada — resultado <<
    # estimado pode ser desconto real (estimativa ruim do órgão), não mexe. Invalida só o
    # resultado (vira "sem dado"), mantém o item — ele ainda é demanda real, só o preço
    # reportado é que não é confiável.
    resultado_suspeito = (
        df["valor_unitario_estimado"].notna() & (df["valor_unitario_estimado"] > 1)
        & df["valor_unitario_resultado"].notna()
        & (df["valor_unitario_resultado"] > 5 * df["valor_unitario_estimado"])
    )
    df.loc[resultado_suspeito, ["nome_fornecedor", "valor_unitario_resultado", "valor_total_resultado", "cod_fornecedor"]] = pd.NA
    df.loc[resultado_suspeito, "tem_resultado"] = False

    # achado 08/jul/26 auditando direção reversa (resultado << estimado): maioria dos
    # casos abaixo de R$10 é plausível (câmara de ar genuinamente é barata, R$10-40), mas
    # achado real de erro: "PNEU 60/100-17 DIANTEIRO DE HONDA BIZ" resultado=R$3,50 (pneu
    # de moto não existe a esse preço), "Pneu veículo automotivo" resultado=R$0,71/R$1,00
    # (placeholder de dado ruim, não preço real). Nenhum pneu ou câmara de ar genuína no
    # Brasil custa menos de R$5 — piso de sanidade abaixo do menor caso plausível
    # (carrinho de mão ~R$7) pra nunca cortar item real.
    resultado_baixo_demais = df["valor_unitario_resultado"].notna() & (df["valor_unitario_resultado"] < 5)
    df.loc[resultado_baixo_demais, ["nome_fornecedor", "valor_unitario_resultado", "valor_total_resultado", "cod_fornecedor"]] = pd.NA
    df.loc[resultado_baixo_demais, "tem_resultado"] = False

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
               i.categoria, i.descricao, i.quantidade, d.uf_sigla AS uf, d.modalidade_nome, d.srp,
               d.data_abertura_proposta, d.valor_total_estimado
        FROM resultados r
        JOIN itens i ON i.numero_controle_pncp = r.numero_controle_pncp AND i.numero_item = r.numero_item
        JOIN detalhes d ON d.numero_controle_pncp = r.numero_controle_pncp
        WHERE i.eh_pneu = TRUE
          AND r.valor_total_homologado IS NOT NULL AND r.valor_total_homologado > 0
          AND (i.valor_unitario_estimado IS NULL OR i.valor_unitario_estimado <= 50000)
          AND (d.valor_total_estimado IS NULL OR d.valor_total_estimado <= 300000000)
          AND (i.valor_unitario_estimado IS NULL OR i.valor_unitario_estimado <= 1
               OR r.valor_unitario_homologado <= 5 * i.valor_unitario_estimado)
          AND r.valor_unitario_homologado >= 5
        """,
        ENGINE,
    )
    resultados = resultados[~resultados["numero_controle_pncp"].isin(PROCESSOS_EXCLUIDOS_DADO_RUIM)]

    # achado 08/jul/26 auditando lógica de cálculo do dashboard: essa função não tinha a
    # dedup de processo retificado (mesmo processo republicado gera numero_controle_pncp
    # novo, ~8% dos processos, ver comentário em carregar_base_pncp) — inflava contagem de
    # editais ganhos/fornecedor dominante (310/18.674 linhas de resultado, ~1,7%). Mesma
    # lógica de dedup (cnpj+data+valor, mantém o numero_controle_pncp mais antigo) mas
    # calculada no nível PROCESSO (1 linha por numero_controle_pncp) antes de aplicar aqui —
    # rodar duplicated() direto na tabela fornecedor/item (múltiplas linhas por processo)
    # marcaria erroneamente o 2º item do MESMO processo como duplicata.
    _processos = resultados[["numero_controle_pncp", "data_abertura_proposta", "valor_total_estimado"]].drop_duplicates(subset="numero_controle_pncp").sort_values("numero_controle_pncp")
    _cnpj = _processos["numero_controle_pncp"].str.split("-").str[0]
    _chave_dedup = pd.DataFrame({
        "cnpj": _cnpj, "data": _processos["data_abertura_proposta"], "valor": _processos["valor_total_estimado"],
    }, index=_processos.index)
    _duplicado = _chave_dedup.duplicated(keep="first") & _chave_dedup["data"].notna() & _chave_dedup["valor"].notna()
    _processos_excluir = set(_processos.loc[_duplicado, "numero_controle_pncp"])
    resultados = resultados[~resultados["numero_controle_pncp"].isin(_processos_excluir)]
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
