# LICIT

Venda de pneus para licitações públicas (pregão eletrônico e dispensa eletrônica, Lei 14.133/21). Empresa individual, CNPJ 46.552.201/0001-00.

## Fluxo do negócio

```
RADAR (pncp_radar.py)              → email diário com edital novo publicado no PNCP
ANÁLISE DE EDITAL (analisa_edital.py) → baixa docs do PNCP, Claude extrai critérios → card Notion
COTAÇÃO (*_scraper.py)             → busca preço em cada distribuidor
PRECIFICAÇÃO (preencher_planilha_precificacao.py) → planilha Sheets (modelo no Drive)
HABILITAÇÃO                        → checklist de documentação da empresa (Notion)
PROPOSTA                           → carta espelha linguagem do edital, preço = custo × 1.24
CICLO DE APRENDIZADO               → após sessão, compara nossa cotação vs resultado real (Notion)
```

Contexto completo do negócio (riscos, fórmulas, habilitação, Notion): `CLAUDE.md`.

## Estrutura

```
licit/
├── pncp_radar.py            Radar diário — busca edital novo no PNCP, envia email
├── analisa_edital.py        Baixa edital via API PNCP (pdf/docx/txt/html), Claude extrai JSON → card Notion.
│                            Trava (ExtracaoInsuficiente) se o documento não puder ser lido com confiança —
│                            nunca analisa sem base documental real. Usa valorTotalEstimado oficial do PNCP
│                            (api/consulta/v1), não o texto livre. Anexa os documentos originais no card.
├── bransales_scraper.py     Cotação — Bransales Atacadista
├── cantu_scraper.py         Cotação — Cantu / SpeedMax B2B
├── gp_scraper.py            Cotação — GP Fácil (cookies exportados — reCAPTCHA bloqueia login direto)
├── green_scraper.py         Cotação — PneuGreen (só ele valida se a medida do produto bate com a pedida
│                            antes de aceitar — os outros 3 usam URL estruturada por medida, mais seguro)
├── notion_upload.py         Upload resultado Bransales → Notion (REST API)
├── cantu_upload.py          Upload resultado Cantu → Notion (REST API)
├── preencher_planilha_precificacao.py  Preenche cópia da planilha modelo (Sheets) com resultado dos
│                            4 scrapers + referência do edital — ver seção "Precificação" abaixo
├── precificacao_gsheets.py  ⚠️ DEPRECADO — hardcoded pro Cantagalo (jun/2026), não usar em edital novo
├── sample_objeto.py         Script de exploração pontual da API PNCP (objetoCompra)
├── items_X.json / results_X_*.json / analise_X.json   Input/output de cotação por edital
│                            (gitignorado — dado local, nome muda por processo)
│
├── analise/                 Pipeline de análise de mercado (dado público PNCP)
│   ├── coletor_pncp.py         Fase 1 — descobre editais (API de busca), grava em Postgres
│   ├── coletor_pncp_detalhe.py Fase 2 — baixa detalhe+itens+resultado de cada edital da fila
│   ├── filtro_pneu.py          Filtro compartilhado "é pneu de verdade?" (regex + regras)
│   ├── conectar_pncp.py        Views/queries usadas pelo dashboard
│   ├── dashboard_pncp.py       Dashboard Streamlit (geografia, sazonalidade, fornecedores)
│   ├── recomputar_filtro.py    Reaplica filtro_pneu.py sem reraspar (quando o filtro muda)
│   ├── migrar_para_supabase.py Migração one-shot SQLite → Postgres (já rodada, mantida por histórico)
│   ├── schema_supabase.sql     Schema das 6 tabelas
│   └── requirements.txt        Deps desse pipeline (psycopg2, streamlit, plotly, curl_cffi...)
│
└── .github/workflows/        Automação (ver abaixo)
```

## Automação (GitHub Actions)

| Workflow | Quando roda | O que faz |
|---|---|---|
| `pncp_radar.yml` | dias úteis, 5h BRT | Radar diário → email |
| `pncp_coletor_editais.yml` | diário, ~meia-noite BRT (+ manual) | Fase 1 — reescaneia as 27 UFs pra achar edital novo (`--reset`, ver docstring de `coletor_pncp.py`) |
| `pncp_coletor_detalhe.yml` | a cada ~5h30 | Fase 2 — processa fila pendente (editais novos entram sozinhos) |

Fase 2 não descobre edital novo sozinha — só fase 1 faz isso (API não permite paginar por data). Rodar `coletor_pncp.py --reset` é a única forma de achar processo novo.

## Dados

- **Fonte:** API de busca do PNCP (não o export bulk do ComprasGOV — tem gap de ~17x, ver `analise/coletor_pncp.py` docstring)
- **Armazenamento:** Postgres no Supabase, projeto `LICIT` (`koqsgnvmnzkqzxnskzgq`, sa-east-1)
- **Dashboard público:** https://gsuh5zthgffvohk8xqbuhe.streamlit.app/
- **Documentação do achado/histórico de bugs de filtro:** Notion → [Dados públicos](https://app.notion.com/p/395ca98e9281806684a6c34186a520ca)

## Precificação (planilha)

- **Modelo mestre:** [pasta no Drive](https://drive.google.com/drive/folders/1Nf10IsY2Gzpf_1WXWuKBC0B58vAbnuXX) — nunca editar direto, sempre duplicar (`copy_file`) antes de preencher
- 4 blocos empilhados (Bransales/Cantu/GP/Green), colunas de entrada A-L (Item/Produto/Modelo/Especificação Técnica/Critérios/Distribuidor/Marca/Link/Observação/Preço UN/Ref. Edital/Qtde) + coluna Vencedor (fórmula, compara os 4 blocos). Colunas de cálculo (Investimento/Frete/Imposto/Preço de venda/Margem) são fórmula — nunca escrever nelas.
- `python preencher_planilha_precificacao.py <spreadsheet_id> <analise.json> --bransales X --cantu X --gp X --green X`
- Detalhe completo: `CLAUDE.md` §15.5

## Ciclo de Aprendizado

Depois de cada sessão de lances, comparar nossa cotação vs resultado real e registrar em [Ciclo de aprendizado](https://app.notion.com/p/392ca98e928180c6a1bbcef7942f583b) (4 pontos fixos: Concorrentes/Produto/Edital/Processo). Processo documentado em `CLAUDE.md` §15.6.

## Setup

Variáveis de ambiente (`.env`, nunca commitado):

```
NOTION_TOKEN, NOTION_DB_ID
ANTHROPIC_API_KEY
BRANSALES_EMAIL, BRANSALES_PASSWORD
CANTU_EMAIL, CANTU_PASSWORD
GREEN_EMAIL, GREEN_PASSWORD
DATABASE_URL              # Postgres/Supabase, pooler transaction mode
```

`credentials.json`/`token.json` (OAuth Google Sheets, gitignorados) — setup de 1x só, ver docstring de `preencher_planilha_precificacao.py`.

Radar (`requirements_radar.txt`) e pipeline de mercado (`analise/requirements.txt`) têm dependências separadas de propósito — o radar não precisa puxar `psycopg2`/`streamlit`.

## Segurança

- `.env`, `gp_cookies.json`, `credentials.json`/`token.json` (OAuth Google Sheets) — gitignorados, nunca commitados
- Credenciais dos distribuidores viveram hardcoded no código, repo público, entre 29/jun e 07/jul/2026 (commit `2456dcf` corrigiu, moveu pra `.env`) — histórico antigo do git ainda contém as senhas removidas; **trocar as 3 senhas nos portais (Bransales/Cantu/PneuGreen) e avaliar reescrever o histórico do git** enquanto o repo for público
- RLS habilitado nas 6 tabelas do Supabase (sem policy — acesso só via `DATABASE_URL`/service role, que faz bypass)
