# Arsenal Jurídico — LICIT

Dono deste fato (CLAUDE.md §17.12): este arquivo, na raiz do repo (`licit/arsenal_juridico.md`).
CLAUDE.md aponta pra cá; Notion e memória apenas referenciam. Não duplicar conteúdo.

**Consumidores:** (1) `parecer_juridico.py` — Camada 2, script separado, roda manualmente
depois da Camada 1 (`analisa_edital.py`), recebe este arquivo inteiro como contexto;
(2) renderização determinística da checklist no card (Python usa os IDs);
(3) leitura humana antes de dar lance, assinar ata ou reagir a atraso de pagamento.

Este arquivo **não** entra no prompt de extração (Camada 1). Extração é fato com fonte;
arsenal é conhecimento estático.

**Escopo legal:** Lei 14.133/21 · Decreto 11.462/23 (SRP federal) · IN Seges/ME 77/2022
(pagamento federal) · LC 123/2006 (ME/EPP). Estados e municípios têm regulamentos
próprios de SRP e pagamento: os campos são sempre extraídos do edital concreto, nunca
assumidos da norma federal. Quando o edital invocar decreto municipal/estadual não anexado,
isso é flag bloqueante (mesma lógica do `validar_valor_total()`).

**Disclaimer:** referência operacional compilada com IA; não substitui parecer jurídico.
Última revisão: 14/07/2026.

---

## Índice rápido

| ID | Mecanismo | Fase | Gatilho em 1 linha |
|---|---|---|---|
| ARS-01 | Esclarecimento / impugnação | Pré-sessão | Edital com cláusula abusiva, omissa ou inexequível |
| ARS-02 | Cotação de quantidade parcial | Pré-sessão (SRP) | Fornecedor não garante o quantitativo total |
| ARS-03 | Teto matemático da ata | Pré-sessão (SRP) | Sempre — dimensionar pior cenário antes do lance |
| ARS-04 | Regularização fiscal tardia | Habilitação | Certidão fiscal/trabalhista com restrição no dia da sessão |
| ARS-05 | Empate ficto | Sessão | Lance ME até 5% acima do melhor (pregão) |
| ARS-06 | Exclusividade ≤80k / cota 25% | Triagem | Item ≤ R$80k ou cota reservada ME/EPP |
| ARS-07 | Revisão de preço pra cima | Ata vigente | Custo subiu acima do registrado |
| ARS-08 | Liberação sem penalidade | Ata vigente | Órgão exige redução e a margem não fecha |
| ARS-09 | Cancelamento a pedido | Ata vigente | Caso fortuito / força maior comprovados |
| ARS-10 | Veto a remanejamento/carona | Ata vigente | Pedido de órgão que não estava no edital |
| ARS-11 | Cadastro de reserva | Pós-sessão | Perdeu, mas o preço vencedor é executável |
| ARS-12 | Não-prorrogação da ata | Fim da vigência | Preço registrado deixou de ser vantajoso pra você |
| ARS-13 | Reequilíbrio econômico-financeiro | Contrato | Fato imprevisível (câmbio, tributo, força maior) |
| ARS-14 | Parcela incontroversa | Entrega | Órgão trava a NF inteira por questionamento parcial |
| ARS-15 | Matriz de riscos | Precificação | Edital contém matriz — ler antes de precificar |
| ARS-16 | Atualização monetária | Atraso (degrau 1) | Pagamento após o prazo do edital |
| ARS-17 | Auditoria da ordem cronológica | Atraso (degrau 2) | Suspeita de preterição na fila de pagamento |
| ARS-18 | Suspensão do fornecimento | Atraso (degrau 3) | Atraso > 2 meses da emissão da NF |
| ARS-19 | Extinção por culpa da Administração | Atraso (degrau 4) | Atraso > 2 meses persistente |
| ARS-B1 | Pagamento expresso pequeno valor | Ciclo de caixa | Despesa dentro do limite de pequeno valor |

---

## FASE A — Antes da sessão (único momento de negociação real com o órgão)

### ARS-01 · Pedido de esclarecimento e impugnação

**Base:** Lei 14.133, art. 164.

**O que é:** qualquer licitante (ou cidadão) pode impugnar o edital ou pedir esclarecimento;
a resposta é obrigatória e vincula o órgão.

**Gatilhos típicos em edital de pneu:**
- Prazo de entrega inexequível — referência objetiva: art. 6º, X define "compra imediata"
  como entrega em até 30 dias da ordem de fornecimento; prazo de poucos dias corridos para
  item de importadora é atacável.
- Edital sem condições/prazo de pagamento (o edital deve indicá-las).
- Edital sem critério de atualização financeira dos valores pagos com atraso.
- Exigência de habilitação sem amparo legal ou espec técnica que só 1 marca atende.

**Evidência prévia:** nenhuma. A resposta do órgão vira prova — arquivar no card.
Atenção ao prazo de impugnação do edital (curto; extrair do próprio edital).

### ARS-02 · Cotação de quantidade parcial (SRP)

**Base:** Decreto 11.462, art. 15, parágrafo único — quantidades parciais, inferiores à
demanda, desde que permitido no edital.

**Uso:** ofertar só a fatia que o distribuidor garante, em vez de não participar.

**Evidência prévia:** compromisso de disponibilidade do distribuidor pro quantitativo ofertado.
Se o edital for silente: pedir esclarecimento (ARS-01) — não presumir.

### ARS-03 · Teto matemático da ata

**Base:** Decreto 11.462 — vedado acréscimo nos quantitativos registrados; a ata obriga o
fornecedor a fornecer, mas não obriga a Administração a contratar.

**Uso:** pior cenário = quantitativo máximo × custo atual. Se o caixa não banca o pior
cenário, o filtro é não entrar — a negociação acontece na seleção da ata, não depois.

**Evidência prévia:** custo congelado com data (série dos scrapers) na decisão de participar.

---

## FASE B — Benefícios ME/EPP (valem independentemente de previsão no edital — art. 4º da 14.133)

### ARS-04 · Regularização fiscal/trabalhista tardia

**Base:** LC 123, art. 43, §1º — havendo restrição na regularidade fiscal/trabalhista,
prazo de 5 dias úteis a partir da declaração de vencedor, prorrogável por igual período,
para regularizar (inclui pagamento/parcelamento e emissão de certidões). Há jurisprudência
aplicando especificamente a CRF FGTS de EPP.

**Condições duras:**
- Apresentar TODA a documentação exigida na habilitação, mesmo com restrição — quem omite perde o benefício.
- Cobre APENAS regularidade fiscal e trabalhista (art. 68, I-V da 14.133). NÃO cobre
  habilitação jurídica, qualificação técnica nem econômico-financeira (certidão de
  falência fica de fora).

**Risco prático:** 5+5 dias úteis podem não bastar pra pendência cadastral (ex.: registro
de empregador na Caixa). Validar exequibilidade com a contabilidade ANTES de usar como estratégia.

### ARS-05 · Empate ficto

**Base:** LC 123, arts. 44-45 — no pregão, proposta de ME/EPP até 5% acima da melhor
proposta de empresa não-ME é empate; a ME mais bem classificada é convocada a cobrir
em até 5 minutos, sob pena de preclusão. (10% nas demais modalidades.)

**Implicação de pricing:** dá pra "perder" o leilão por até 5% e ainda vencer.

**Condições:** enquadramento ME declarado no portal + presença online na sessão (reação
em 5 minutos). Não se aplica se a melhor proposta já for de outra ME/EPP.

**Exceção** (14.133, art. 4º, §1º): benefícios não se aplicam a item cujo valor estimado
supere a receita bruta máxima de EPP.

### ARS-06 · Licitação exclusiva ≤ R$80k e cota reservada de 25%

**Base:** LC 123, art. 48, I e III.

**O que é:** itens de contratação até R$80.000 devem ser exclusivos ME/EPP; em bens
divisíveis, cota de até 25% do quantitativo reservada a ME/EPP (podendo disputar também
a cota ampla).

**Leitura de mercado (banco LICIT):** ticket mediano por edital de pneu ≈ R$9,3k e
p75 ≈ R$62k → a maioria do mercado é território exclusivo de pequenos.

**Pegadinha:** quem vence cota reservada E cota ampla iguala pelo menor preço ofertado.

**No pipeline:** `tipo_beneficio` já vem estruturado da API do PNCP — dado oficial, não extrair de texto.

---

## FASE C — Vida da ata SRP

### ARS-07 · Revisão de preço pra cima (custo subiu)

**Base:** Decreto 11.462, art. 27.

**Padrão de prova (o ponto que decide):** alegação genérica de aumento NÃO serve —
jurisprudência exige fato comprovado. Pedido indeferido sem prova → o compromisso se
preserva, sob pena de cancelamento do registro (art. 28) + sanções.

**Dossiê a manter por item registrado (montar ANTES de precisar):**
- Cotação do distribuidor datada do dia da proposta (evidência congelada dos scrapers);
- Tabela de preço do fabricante/importador com vigência;
- Série de câmbio (pneu é dolarizado);
- Série histórica de custo com timestamp (Supabase) — vantagem estrutural LICIT.

### ARS-08 · Liberação sem penalidade (mercado caiu)

**Base:** Decreto 11.462, art. 26, §1º — fornecedor que não aceita reduzir ao preço de
mercado é liberado do compromisso quanto ao item, sem penalidade; segue vinculado aos
demais itens da ata.

**Uso:** porta de saída legal e limpa de ata que ficou ruim, item a item.

### ARS-09 · Cancelamento a pedido do fornecedor

**Base:** Decreto 11.462, art. 29, II — condicionado a caso fortuito ou força maior
comprovados. Via difícil; preferir ARS-07/ARS-08.

### ARS-10 · Veto a remanejamento e carona

**Base:** Decreto 11.462, art. 30, §5º — remanejamento entre órgãos de entes distintos:
o fornecedor beneficiário OPTA por aceitar ou não. Mesma lógica para adesão de não
participante (carona): depende da aceitação do fornecedor.

**Uso:** pedido de órgão que não estava no edital pode ser recusado sem sanção. Grande
parte dos "pedidos absurdos" vem daqui.

### ARS-11 · Cadastro de reserva

**Base:** Decreto 11.462, art. 18.

**Uso:** perdeu o item, mas o preço do vencedor é executável → aceitar cotar pelo mesmo
preço e entrar na reserva. Convocação se o vencedor cair (frequente por documentação —
ver Ciclo de Aprendizado). Sem compromisso até ser convocado: participação com opcionalidade.

### ARS-12 · Não-prorrogação da ata

**Base:** Decreto 11.462 — vigência de 1 ano, prorrogável por igual período "desde que
comprovado que o preço é vantajoso".

**Uso:** prorrogação é escolha, não default. Preço ruim → não há vantajosidade → deixar vencer.

---

## FASE D — Contrato e execução

### ARS-13 · Reequilíbrio econômico-financeiro

**Base:** Lei 14.133, art. 124, II, "d" — fatos imprevisíveis ou previsíveis de
consequências incalculáveis (câmbio abrupto, tributo novo, força maior). Vale em qualquer
contrato, não só SRP. Mesmo padrão de prova do ARS-07.

### ARS-14 · Parcela incontroversa

**Base:** Lei 14.133, art. 143 — em controvérsia sobre dimensão/qualidade/quantidade,
a parcela incontroversa é liberada no prazo normal de pagamento.

**Uso:** órgão devolve a NF inteira por questionar parte do lote → ofício citando art. 143.

### ARS-15 · Matriz de riscos

**Base:** Lei 14.133, art. 22 — edital pode alocar riscos entre as partes.

**Uso:** quando existir, ler ANTES de precificar; define quem paga frete extra, variação
cambial, atraso de terceiros etc.

---

## FASE E — Atraso de pagamento (escada: subir 1 degrau por vez, tudo por escrito)

### ARS-16 · Degrau 1 — Atualização monetária

**Base:** o edital deve prever critério de atualização financeira do adimplemento até o
pagamento efetivo. Direito quase nunca exercido pelos fornecedores.

**Uso:** ofício educado cobrando o valor atualizado pelo critério do próprio edital.
Se o edital não prevê: era caso de ARS-01 na fase de edital; registrar pro próximo.

### ARS-17 · Degrau 2 — Auditoria da ordem cronológica

**Base:** Lei 14.133, art. 141 + IN 77/2022 — o órgão publica mensalmente na internet a
ordem cronológica de pagamentos e as justificativas de alteração.

**Uso:** verificar preterição. Preterição indevida → representação ao controle interno /
Tribunal de Contas (art. 170, §4º).

### ARS-18 · Degrau 3 — Suspensão do fornecimento

**Base:** Lei 14.133, art. 137, §2º, IV + §3º, II — atraso superior a 2 meses contado da
emissão da NF assegura o direito de OPTAR pela suspensão das obrigações até a
normalização, com direito a restabelecimento do equilíbrio (art. 124, II, "d").

**Uso:** você não é obrigado a continuar entregando pra órgão que não paga há 2 meses.
Notificar formalmente antes de suspender; contar o prazo da emissão da NF.

**Exceções** (§3º, I): calamidade pública, guerra, ou atraso causado por ato do próprio contratado.

### ARS-19 · Degrau 4 — Extinção por culpa da Administração

**Base:** art. 137, §2º, IV — direito subjetivo à extinção por atraso > 2 meses.

**Como exercer:** NÃO é unilateral — solicitar à Administração; recusada, pleitear
judicialmente (jurisprudência recente concede tutela de urgência determinando pagamento
e suspendendo penalidades). Culpa exclusiva da Administração → ressarcimento de prejuízos
comprovados + devolução da garantia atualizada + pagamentos devidos até a extinção.

### ARS-B1 · Bônus — Pagamento expresso de pequeno valor

**Base:** Lei 14.133, art. 141, §3º — despesas dentro do limite de pequeno valor
(referência do art. 24, II): pagamento em até 5 dias úteis da apresentação da fatura.

**Leitura estratégica:** dispensa eletrônica é a modalidade de pagamento mais rápido por
lei — ciclo de caixa curto enquanto o negócio constrói musculatura pra SRP.

---

## Regras de uso pela Camada 2 (parecer)

- Toda flag/risco/recomendação referencia (a) um ID deste arquivo e (b) o campo de fato
  da Camada 1 que a sustenta (`baseado_em`). Sem fato extraído, o máximo permitido é
  sugerir ARS-01 (esclarecimento) — nunca presumir o conteúdo do edital.
- Confiança obrigatória (alta/média/baixa) em cada item do parecer.
- Norma municipal/estadual identificada no edital ≠ norma federal deste arquivo:
  sinalizar a divergência, não aplicar o artigo federal como se valesse.
- Este arquivo não é fonte de fato sobre o edital — é lente de interpretação sobre os
  fatos que a Camada 1 extraiu.
