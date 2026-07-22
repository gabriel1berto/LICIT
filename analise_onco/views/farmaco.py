import streamlit as st
import plotly.express as px

from conectar_onco import carregar_itens_onco, cobertura_detalhe

st.title("💊 Fármaco")

feito, total, pct = cobertura_detalhe()
st.caption(f"Coleta de detalhe: {feito:,}/{total:,} editais processados ({pct:.1f}%) — número cresce a cada rodada do coletor.")

df = carregar_itens_onco()

if df.empty:
    st.warning("Ainda sem item processado — coletor_onco_detalhe.py ainda não rodou o suficiente.")
    st.stop()

col1, col2, col3 = st.columns(3)
col1.metric("Itens de medicamento onco confirmados", f"{len(df):,}")
col2.metric("Princípios ativos distintos", df["principio_ativo_provavel"].nunique())
col3.metric("Itens com resultado homologado", f"{df['valor_unitario_homologado'].notna().sum():,}")

st.divider()

st.subheader("Princípio ativo mais citado (top 20)")
top_farmaco = df["principio_ativo_provavel"].value_counts().head(20).reset_index()
top_farmaco.columns = ["farmaco", "n"]
fig = px.bar(top_farmaco.sort_values("n"), x="n", y="farmaco", orientation="h")
st.plotly_chart(fig, use_container_width=True)

com_preco = df[df["valor_unitario_homologado"].notna()]
if not com_preco.empty:
    st.subheader("Preço homologado real por fármaco (top 15 por volume)")
    top15 = com_preco["principio_ativo_provavel"].value_counts().head(15).index
    fig = px.box(com_preco[com_preco["principio_ativo_provavel"].isin(top15)],
                 x="principio_ativo_provavel", y="valor_unitario_homologado")
    fig.update_layout(xaxis_title="", yaxis_title="R$ / unidade homologada")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Fornecedor/laboratório mais vencedor (top 15)")
    top_fornecedor = com_preco["nome_fornecedor"].value_counts().head(15).reset_index()
    top_fornecedor.columns = ["fornecedor", "n"]
    st.dataframe(top_fornecedor, use_container_width=True, hide_index=True)
else:
    st.info("Ainda sem resultado homologado coletado o suficiente pra gráfico de preço.")

st.divider()
st.subheader("Explorar itens")
farmaco_filtro = st.multiselect("Filtrar princípio ativo", sorted(df["principio_ativo_provavel"].dropna().unique()))
df_filtrado = df.copy()
if farmaco_filtro:
    df_filtrado = df_filtrado[df_filtrado["principio_ativo_provavel"].isin(farmaco_filtro)]
st.dataframe(
    df_filtrado[["uf", "orgao_nome", "principio_ativo_provavel", "descricao", "quantidade",
                 "valor_unitario_estimado", "nome_fornecedor", "valor_unitario_homologado"]],
    use_container_width=True, hide_index=True,
)
