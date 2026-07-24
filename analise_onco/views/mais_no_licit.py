#!/usr/bin/env python3
"""Página de vitrine — cada card é uma funcionalidade que a plataforma LICIT já sabe
construir (testada em produção em outro contexto) como possibilidade autocontida pro
oncológico, sem citar de onde ela vem. CAPAG é a única exceção: já roda de verdade aqui
(Radar de Editais), por isso fica separada da lista de possibilidades, não misturada
como se fosse só uma ideia. Conteúdo institucional/estático, não puxa dado real de
negócio (preço, margem, cliente).

Achado 24/jul/2026 (revisão de clareza): rótulo "Possibilidade validada/em validação"
era redundante com o título da página e não dizia nada de prático — trocado por rótulo
que responde a pergunta real do leitor ("dá pra portar já, ou precisa de ajuste
antes?")."""

import streamlit as st

from dashboard_common_onco import COR_STATUS_GOOD, COR_STATUS_WARNING

st.title("✨ Possibilidades pro LICIT Oncológico")
st.caption(
    "Cada card abaixo é uma funcionalidade que a plataforma LICIT já sabe construir e "
    "que **ainda não existe aqui** — descrita como capacidade pronta pra portar, não "
    "como tecnologia nova a inventar do zero."
)

st.success(
    "✅ **CAPAG (confiabilidade fiscal do órgão)** já roda de verdade aqui — aparece em "
    "cada card do Radar de Editais Oncológico. Não é possibilidade, já está pronta."
)

st.divider()


def _cartao(icone: str, titulo: str, descricao: str, status: str = "pronta"):
    cor = COR_STATUS_GOOD if status == "pronta" else COR_STATUS_WARNING
    label = "✅ Pronta pra portar" if status == "pronta" else "🧪 Precisa de ajuste antes de portar"
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
        "🏭", "Cotação de fornecedor em tempo real",
        "Vários distribuidores cotados **todo dia**, sem intervenção manual — histórico "
        "de preço por produto, tendência ao longo do tempo, alerta automático de item "
        "novo/suspeito antes de confiar no dado. **Pré-requisito das 2 possibilidades "
        "abaixo** — sem isso, elas não têm preço próprio pra comparar.",
    )
    _cartao(
        "🎯", "\"Meu preço\" x mercado, item por item",
        "Com a cotação de fornecedor em pé: cada item de cada edital aberto seria "
        "comparado contra o menor custo já cotado, e o card já nasceria dizendo se dá "
        "pra competir **bem posicionado, acima da média, ou sem cobertura de catálogo** "
        "naquele item — decisão em segundos, não em planilha manual.",
        status="teste",
    )
    _cartao(
        "📊", "Planilha de precificação dinâmica",
        "Com a cotação de fornecedor em pé: blocos de cotação lado a lado, altura que se "
        "ajusta ao tamanho real do edital, coluna \"Vencedor\" calculada automaticamente "
        "comparando os distribuidores — zero copy-paste, gerada do zero a cada rodada.",
        status="teste",
    )

with col2:
    _cartao(
        "⚖️", "Análise de edital + parecer jurídico por IA",
        "Documento do edital entra, sai item estruturado (quantidade, especificação "
        "técnica, critério de habilitação) + recomendação jurídica com nível de "
        "confiança — card pronto no Notion, já avisando qual o próximo passo.",
    )
    _cartao(
        "🔬", "Verificação de registro/certificação automatizada",
        "Antes de fechar proposta: busca automática por registro oficial do produto "
        "escolhido no órgão regulador competente, por marca/apresentação — confirma "
        "certificação válida sem checar site por site na mão.",
    )
    _cartao(
        "🧠", "Ciclo de Aprendizado",
        "Depois de cada sessão de lances: compara o candidato da LICIT contra quem "
        "realmente venceu, item por item, preço por preço — constrói histórico real de "
        "acerto/erro, não achismo.",
    )
    _cartao(
        "🤖", "Radar por email, todo dia útil",
        "5h da manhã, todo dia útil: edital novo cai na caixa de entrada antes de "
        "qualquer concorrente abrir o PNCP — zero busca manual.",
    )

st.divider()
st.markdown(
    "Tudo isso já foi construído e testado em produção — trazer pro oncológico é "
    "questão de **prioridade**, não de tecnologia nova pra inventar."
)
