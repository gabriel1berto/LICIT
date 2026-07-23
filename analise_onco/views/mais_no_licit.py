#!/usr/bin/env python3
"""Página de vitrine — mostra o que o LICIT já faz na vertical de pneus (a outra
vertical da empresa, além da oncológica) e ainda não foi trazido pro oncológico.
Nomenclatura pensada pra quem só conhece o dashboard de oncológico (não assume
familiaridade prévia com "pneu" como nome de projeto). Conteúdo institucional/
estático, não puxa dado real de negócio (preço, margem, cliente) — só descreve
capacidade da plataforma."""

import streamlit as st

from dashboard_common_onco import COR_STATUS_GOOD, COR_STATUS_WARNING

st.title("✨ Mais no LICIT")
st.caption(
    "Esse dashboard de oncológico é 1 fatia da plataforma LICIT. A LICIT também opera "
    "uma vertical de **venda de pneus para o governo via licitação** (o negócio original "
    "da empresa, hoje mais maduro) — já roda tudo isso abaixo nessa vertical de pneus."
)

st.divider()


def _cartao(icone: str, titulo: str, descricao: str, status: str = "ativo"):
    cor = COR_STATUS_GOOD if status == "ativo" else COR_STATUS_WARNING
    label = "🟢 Ativo na vertical de pneus" if status == "ativo" else "🟡 Em teste na vertical de pneus"
    with st.container(border=True):
        st.markdown(
            f'<div style="height:4px;background:{cor};border-radius:2px;margin-bottom:10px;"></div>',
            unsafe_allow_html=True,
        )
        st.markdown(f"### {icone} {titulo}")
        st.caption(label)
        st.markdown(descricao)


col1, col2 = st.columns(2)

with col1:
    _cartao(
        "🏭", "Cotação de Fornecedor em tempo real",
        "5 distribuidores (Bransales, Cantu, GP Fácil, PneuGreen, Della Via) cotados "
        "**todo dia**, sem intervenção manual. Histórico de preço por medida, tendência "
        "ao longo do tempo, alerta de alias novo/suspeito filtrado automaticamente.",
    )
    _cartao(
        "🎯", "\"Meu preço\" x mercado, item por item",
        "Cada item de cada edital aberto é comparado contra o menor custo já cotado "
        "entre os distribuidores — o card já nasce dizendo se a LICIT está **bem "
        "posicionada, acima da média, ou sem cobertura de catálogo** naquele item. "
        "Decisão de participar em segundos, não em planilha manual.",
    )
    _cartao(
        "⚖️", "Análise de edital + parecer jurídico por IA",
        "Documento do edital entra, sai item estruturado (medida, especificação técnica, "
        "critério de habilitação) + recomendação jurídica com nível de confiança — card "
        "pronto no Notion, com aviso de qual próximo passo tomar.",
    )
    _cartao(
        "🔬", "Verificação INMETRO automatizada",
        "Busca automática no ProdCert (Inmetro) por marca/medida antes de fechar proposta "
        "— confirma que o produto escolhido tem registro válido, sem checar manualmente "
        "site por site.",
    )

with col2:
    _cartao(
        "📊", "Planilha de precificação dinâmica",
        "4 blocos de cotação lado a lado, altura que se ajusta ao tamanho real do edital, "
        "coluna \"Vencedor\" calculada automaticamente comparando os 4 distribuidores — "
        "zero copy-paste, gerada do zero a cada rodada.",
    )
    _cartao(
        "🧠", "Ciclo de Aprendizado",
        "Depois de cada sessão de lances, compara o candidato da LICIT contra quem "
        "realmente venceu — item por item, preço por preço. Constrói histórico real de "
        "acerto/erro, não achismo.",
        status="teste",
    )
    _cartao(
        "🤖", "Radar por email, todo dia útil",
        "5h da manhã, todo dia útil: edital novo da vertical de pneus cai na caixa de "
        "entrada antes de qualquer concorrente abrir o PNCP. Zero busca manual.",
    )
    _cartao(
        "💳", "CAPAG — confiabilidade do órgão",
        "Nota de capacidade de pagamento (Tesouro Nacional) direto no card do Radar de "
        "Editais. **Essa aqui já chegou no oncológico também** — primeira funcionalidade "
        "cruzada entre as duas linhas.",
    )

st.divider()
st.markdown(
    "Tudo isso já roda em produção na vertical de pneus — trazer pro oncológico é questão "
    "de **prioridade**, não de tecnologia nova pra inventar. A base (coleta PNCP, radar, "
    "CAPAG) já é a mesma plataforma por trás das duas verticais."
)
