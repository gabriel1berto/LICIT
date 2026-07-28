---
name: analise-de-edital
description: >
  Processo padrão pra analisar edital de licitação (Camada 1) e gerar parecer
  jurídico (Camada 2) do projeto LICIT — SEMPRE as duas juntas, rodando
  localmente com Claude Code, sem chamar a API paga da Anthropic
  (analisa_edital.py/parecer_juridico.py usam anthropic.Anthropic()
  internamente; esse fluxo substitui essa chamada pela análise direta do
  Claude Code, reusando as mesmas funções puras de download/validação/escrita
  no Notion). Carrega quando o usuário pedir pra analisar edital (dispara
  Camada 1 + Camada 2 automaticamente), gerar parecer jurídico, ou rodar
  Camada 1/Camada 2 do LICIT.
tags: [licit, edital, business]
---

# Análise de Edital (Camada 1 + Camada 2, sem custo de API)

## Regra fixa: as duas camadas sempre juntas (28/jul/2026)

Rodar essa skill = rodar Camada 1 **e** Camada 2, sempre, sem esperar decisão
separada do usuário. Isso substitui a regra antiga de `parecer_juridico.py`
("só roda manualmente, decisão própria do usuário") — só valia pro script
pago via API; rodando localmente e de graça, não tem motivo pra gatear.
`evoluir_parecer_juridico` (campo da Camada 1) vira só um alerta de prioridade
dentro do parecer, não um gate de "roda ou não roda".

## Por que existe

Achado 28/jul/2026 (edital Marialva-PR): `analisa_edital.py` tinha 3 bugs reais
(paginação de itens faltando — 10 de 57 itens; `MAX_TEXT_CHARS` cortando 65% do
documento; `max_tokens` baixo demais pro output). Mesmo depois de corrigidos os
3, o crédito da API Anthropic acabou. Rodando a análise diretamente como Claude
Code (sem `anthropic.Anthropic()`) — mesmo schema, mesmas regras — achei ainda
2 erros que a Camada 1 automatizada tinha cometido 2x seguidas (data da sessão
e prazo de entrega, ambos citados claramente no edital, "não localizado" era
erro de extração, não ausência real). Zero custo, mais preciso. Isso vira
processo padrão, não fallback de emergência.

## Camada 1 — Análise do edital

**Nunca chame `analisar()` de `analisa_edital.py`** (é a função que invoca
Anthropic). Reuse todo o resto do módulo, que é puro Python/HTTP sem custo:

1. **Baixar dado** — script descartável importando de `analisa_edital`:
   `parse_pncp`, `pncp_get`, `pncp_get_itens` (⚠️ sempre essa, nunca `pncp_get`
   direto no endpoint de itens — API do PNCP pagina silenciosamente, status 200
   com só 10 de 57 itens sem aviso nenhum), `pncp_get_consulta`,
   `baixar_documentos`, `localizar_secoes_criticas`, `avisos_termos_ausentes`.
   Salva `itens_api` (lista completa, paginada) + `texto` (documento inteiro,
   Edital+TR concatenado) + `metadados_oficial` (valor oficial, srp) em arquivo
   temporário pra ler.

2. **Ler e montar o dict `analise`** — eu (Claude Code) leio o texto e os itens
   estruturados diretamente, sem resumir por cima. Regras (já escritas em
   `PROMPT_SISTEMA`/`PROMPT_ESTRUTURA` dentro de `analisa_edital.py`, não
   duplicar aqui — ler de lá antes de montar):
   - Todo campo do JSON vem do texto dos documentos (Edital+TR+anexos), nunca
     só de METADADOS PNCP/ITENS API — esses só cross-checam ou preenchem dado
     puramente administrativo (CNPJ, UASG, número do processo).
   - `itens_api` já vem com descrição completa por item (specs embutidas) —
     normalmente basta parsear esse campo pra tabela de item, sem precisar
     casar 1 a 1 com o texto do TR pra cada item.
   - `prazo_entrega`/`prazo_pagamento`: nunca "conforme edital/TR" — se não
     achou, `grep`/`Read` de novo procurando termos como "prazo de entrega",
     "dias úteis", "empenho", "nota fiscal", "liquidação" antes de desistir.
     Histórico mostra que "não localizado" foi errado 2 vezes seguidas.
   - Bloco `arsenal.*` sempre com `"fonte"` = trecho literal + nome do arquivo,
     nunca inferido.
   - Se o texto citar item além do que `itens_api` retornou (ou vice-versa),
     registrar em `alertas.atencao`, nunca escolher um dos dois calado.

3. **Validar** — `validar_valor_total(analise, metadados_oficial["valorTotalEstimado"])`
   + `propagar_beneficio_me_epp(analise, itens_api)`. Funções puras, sem custo.

4. **Escrever no Notion** — `notion_update_props`, `notion_get_children` +
   `notion_delete` (só blocos que NÃO são `pdf`/`image`/`file` — nunca apagar
   anexo existente se não for re-subir os bytes de novo), `build_blocks(analise, None)`,
   `notion_append`.

5. **Salvar** `analise_{cnpj}_{ano}_{seq}.json` (mesma convenção do script).

6. **Apagar os scripts/arquivos temporários** ao final — não sujar o repo.

## Camada 2 — Parecer jurídico

Mesma lógica, nunca chamar `gerar_parecer()` de `parecer_juridico.py`:

1. Ler `arsenal_juridico.md` inteiro (catálogo ARS-01 a ARS-19/B1) + o
   `analise_{...}.json` da Camada 1 (campos `arsenal`, `cabecalho`, `alertas`).
2. Aplicar as **"Regras de uso pela Camada 2"** (seção final de
   `arsenal_juridico.md`, ler de lá, não duplicar): toda recomendação cita um
   ID do arsenal + `baseado_em` (campo exato da Camada 1) + `confianca`
   (alta/média/baixa); campo com fonte `null` na Camada 1 nunca vira
   recomendação presumida (no máximo ARS-01, esclarecimento); ARS-04
   (regularização tardia) e ARS-05 (empate ficto) sempre entram se o edital
   não for vedado a ME/EPP, mesmo sem fato específico (`baseado_em="geral"`);
   norma municipal/estadual não coberta pelo arsenal (só federal) vira
   `divergencias_norma_local`, nunca aplicar artigo federal calado.
3. Montar dict `parecer` (schema `PROMPT_ESTRUTURA` de `parecer_juridico.py`:
   `recomendacoes[]`, `divergencias_norma_local[]`).
4. Escrever no Notion reusando `remover_parecer_anterior()` + `build_parecer_blocks()`
   + `notion_append()` (puras, sem custo).
5. Salvar `analise_..._parecer.json`.

## Não-negociáveis

- Nunca chamar `anthropic.Anthropic()` desses dois scripts — se um dia precisar
  comparar contra a versão via API (ex: validar que a automação em produção
  ainda funciona), só com pedido explícito do usuário, e avisando que tem custo.
- `itens_api` sempre paginado (`pncp_get_itens`) — nunca a chamada direta sem
  paginar.
- Todo fato de `arsenal.*` e toda recomendação jurídica cita a fonte/ID que a
  sustenta — igual já era exigido no prompt, não relaxar agora que não tem
  Claude-via-API pra "obrigar" a regra.
- Não deixar script temporário (`_baixar_*.py`, `_montar_*.py`, `_escrever_*.py`,
  `_contexto_manual.json`, `_texto_manual.txt`, etc.) no repo depois de rodar.
