import streamlit as st

from conectar_onco import cobertura_vocabulario

st.title("🔤 Cobertura de Termos")
st.caption(
    "Transparência do método: qual termo (genérico ou marca) trouxe quanto volume. "
    "Abreviação clínica foi testada e rejeitada — ver histórico de estudo (double/triple-check, 21/jul/2026)."
)

cov = cobertura_vocabulario()
if cov.empty:
    st.warning("Ainda sem termo buscado.")
    st.stop()

col1, col2 = st.columns(2)
col1.metric("Termos genéricos", (cov["tipo"] == "generico").sum())
col2.metric("Termos de marca", (cov["tipo"] == "marca").sum())

st.dataframe(cov, use_container_width=True, hide_index=True)
