#!/usr/bin/env python3
"""Página de vitrine — mostra funcionalidades que a plataforma LICIT já sabe construir
(validadas em produção em outro contexto) como POSSIBILIDADES pro oncológico, sem
referenciar o outro dashboard/vertical pelo nome — cada card se sustenta sozinho como
capacidade que pode ser trazida pra cá, não como "olha o que já existe ali". Conteúdo
institucional/estático, não puxa dado real de negócio (preço, margem, cliente)."""

import streamlit as st

from dashboard_common_onco import COR_STATUS_GOOD, COR_STATUS_WARNING

st.title("✨ Possibilidades pro LICIT Oncológico")
st.caption(
    "Essas são capacidades que a plataforma LICIT já sabe construir — validadas em "
    "produção, prontas pra serem trazidas pro oncológico como próxima prioridade, não "
    "como tecnologia nova a inventar."
)

st.divider()


def _cartao(icone: str, titulo: str, descricao: str, status: str = "ativo"):
    cor = COR_STATUS_GOOD if status == "ativo" else COR_STATUS_WARNING
    label = "💡 Possibilidade validada" if status == "ativo" else "🧪 Possibilidade em validação"
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
        "Vários distribuidores cotados **todo dia**, sem intervenção manual. Histórico "
        "de preço por produto, tendência ao longo do tempo, alerta de alias novo/"
        "suspeito filtrado automaticamente.",
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
        "🔬", "Verificação de registro/certificação automatizada",
        "Busca automática por registro oficial do órgão regulador competente, por marca/"
        "produto, antes de fechar proposta — confirma que o produto escolhido tem "
        "certificação válida, sem checar manualmente site por site.",
    )

with col2:
    _cartao(
        "📊", "Planilha de precificação dinâmica",
        "Blocos de cotação lado a lado, altura que se ajusta ao tamanho real do edital, "
        "coluna \"Vencedor\" calculada automaticamente comparando os distribuidores — "
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
        "5h da manhã, todo dia útil: edital novo cai na caixa de entrada antes de "
        "qualquer concorrente abrir o PNCP. Zero busca manual.",
    )
    _cartao(
        "💳", "CAPAG — confiabilidade do órgão",
        "Nota de capacidade de pagamento (Tesouro Nacional) direto no card do Radar de "
        "Editais — já ativa aqui no oncológico também.",
    )

st.divider()
st.markdown(
    "Tudo isso já foi construído e validado em produção pela plataforma LICIT — trazer "
    "essas possibilidades pro oncológico é questão de **prioridade**, não de tecnologia "
    "nova pra inventar."
)
