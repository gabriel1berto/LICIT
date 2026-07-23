#!/usr/bin/env python3
"""
preencher_planilha_precificacao.py — Preenche cópia da planilha modelo de
precificação com os resultados dos 4 scrapers (Bransales/Cantu/GP/Green).

A planilha modelo (sempre duplicada antes, nunca editada direto — ver
https://drive.google.com/drive/folders/1Nf10IsY2Gzpf_1WXWuKBC0B58vAbnuXX)
só tem o banner das linhas 1-2 — os 4 blocos (um por distribuidor) são
construídos do zero por este script a cada rodada (arquitetura dinâmica,
17/jul/2026 — substitui a versão anterior de 4 blocos fixos de 12 linhas
cada, que deixava linha em branco pra todo item não cotado e furava a
posição dos blocos seguintes quando um edital tinha menos itens).

Altura do bloco = número de itens do edital (mesmo N nos 4 blocos, mesma
lista de itens). Cada bloco: 1 linha de rótulo (distribuidor + timestamp),
1 linha de cabeçalho, N linhas de item, 1 linha de total, 2 linhas em
branco de respiro antes do próximo bloco. O script recalcula a linha
inicial de cada bloco a partir da altura do bloco anterior — não há mais
offset fixo tipo "Cantu sempre começa na linha 20".

A cada rodada a planilha inteira é limpa e reescrita (idempotente — rodar
2x com os mesmos itens dá o mesmo resultado, sem sobra de linha antiga de
uma rodada anterior com N diferente).

Colunas A-L são dado bruto (Item/Produto/Modelo/Especificação Técnica/
Critérios/Distribuidor/Marca/Link/Observação/Preço UN/Ref. Edital/Qtde).
Colunas N em diante são FÓRMULA, escritas pelo próprio script (não há mais
template estático pra copiar, já que a altura do bloco muda por edital):

  N Investimento em compra = Preço UN × Qtde
  O Frete                  = entrada MANUAL, script não escreve (nenhum
                              padrão de fórmula observado nas cotações
                              revisadas manualmente em 17/jul/2026 — preencher
                              à mão por enquanto até existir cotação de frete
                              real por distribuidor)
  P Imposto                = Investimento × 6%
  Q COGS UN                = (Investimento + Frete + Imposto) / Qtde
  R Preço de venda UN (20%) = COGS UN × 1,2
  T Vencedor               = 🏆 no item com o menor Preço UN entre os 4
                              blocos, mesma posição de item nos 4 (fórmula
                              cruza os blocos pelo número de linha calculado)
  V COGS TOTAL             = COGS UN × Qtde
  W Preço de venda (20%)   = COGS TOTAL × 1,2
  X Margem Líquida (20%)   = Preço de venda (20%) × 20%
  Y Margem (MÁX)           = Ref. Edital × Qtde (teto oficial do item, só
                              referência — não é o preço de venda proposto)

Especificação Técnica é texto (IC/IV/Treadwear/Construção/INMETRO
concatenados) lido direto do resultado do scraper — plano futuro (não
implementado ainda) é isso virar registro numa base Supabase em vez de
string solta na planilha.

Uso:
  python preencher_planilha_precificacao.py <spreadsheet_id> <analise.json> \
      --bransales results_X_bransales.json --cantu results_X_cantu.json \
      --gp results_X_gp.json --green results_X_green.json

Setup: ver credentials.json/token.json (mesmo OAuth do precificacao_gsheets.py).
"""

import argparse, json, os, sys
from datetime import datetime, timezone, timedelta
import gspread

SHEET_NAME = "Página1"
BRT = timezone(timedelta(hours=-3))

CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")
TOKEN_FILE       = os.path.join(os.path.dirname(__file__), "token.json")

DISTRIBUIDORES = ["Bransales", "Cantu", "GP", "Green Pneus"]
PRIMEIRO_BLOCO_LABEL_ROW = 3
GAP_APOS_TOTAL = 2  # linhas em branco entre o total de um bloco e o rótulo do próximo

HEADERS = [
    "Item", "Produto", "Modelo", "Especificação Técnica", "Critérios técnicos",
    "Distribuidor", "Marca", "Link", "Observação", "Preço UN", "Ref. Edital", "Qtde",
    "",
    "Investimento em compra", "Frete", "Imposto", "COGS UN", "Preço de venda UN (20%)",
    "",
    "Vencedor",
    "",
    "COGS TOTAL", "Preço de venda (20%)", "Margem Líquida (20%)", "Margem (MÁX)",
    "",
    "Produto Escolhido",
    "",
    "Nº Certificado INMETRO",
]
# Coluna AA — marcação MANUAL ("x"), nunca escrita pelo script. Define qual candidato
# (dentre os 4 blocos) vai pra frente no processo — só esses entram na busca de
# INMETRO (inmetro_lookup.py), não os 12 candidatos inteiros (achado 17/jul/2026:
# buscar todo mundo no ProdCert é lento — site ASP antigo sem API, cada resultado é
# reload completo do servidor — e a maioria dos candidatos nunca vira proposta real).


def carregar_json(path: str):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def formatar_especificacao(resultado_item: dict) -> str:
    """Concatena as specs técnicas que o scraper conseguiu ler. N/D pra ausente
    — nunca inventar valor que o scraper não confirmou."""
    def v(campo, label):
        val = resultado_item.get(campo)
        return f"{label} {val}" if val not in (None, "") else f"{label} N/D"

    return " · ".join([
        v("ic", "IC"),
        v("iv", "IV"),
        v("treadwear", "Treadwear"),
        v("construcao", "Construção"),
        v("inmetro", "INMETRO"),
    ])


SEM_ESTOQUE_SENTINELS = {"", "— Sem estoque", "-- Sem estoque"}


def linha_para_item(resultado_item: dict | None, distribuidor: str) -> dict:
    """Monta os valores de A-L pra 1 item, dado o resultado do scraper (ou None se sem estoque).
    'Produto' = medida pedida no edital (vem de fora). 'Marca' = nome do produto achado
    (segue o padrao da planilha original: essa coluna guarda o nome completo, tipo
    'Bransales B Van', nao so a marca pura).

    Bug achado 09/jul/2026: 'apto=False' NAO significa sem estoque — pode ser
    'achou produto mas tem criterio nao confirmado' (ex: lonas nao publicada).
    Antes esse caso virava 'Sem estoque' e o produto real achado sumia da
    planilha. Agora so trata como sem estoque quando o scraper de fato nao
    achou nome nenhum (sentinela 'Sem estoque' ou nome vazio)."""
    nome = (resultado_item or {}).get("nome", "")
    sem_estoque = resultado_item is None or nome in SEM_ESTOQUE_SENTINELS

    if sem_estoque:
        obs_sem_estoque = (resultado_item or {}).get("obs") or f"Nenhum produto disponível na {distribuidor}"
        return {
            "especificacao": "",
            "criterio": "— Sem estoque",
            "marca": "",
            "link": "",
            "obs": obs_sem_estoque,
            "preco_un": "",
        }
    return {
        "especificacao": formatar_especificacao(resultado_item),
        "criterio": "✅ Verificado" if resultado_item.get("apto") else "⚠️ Parcial",
        "marca": nome,
        "link": resultado_item.get("url", ""),
        "obs": resultado_item.get("obs", ""),
        "preco_un": resultado_item.get("preco_un", ""),
    }


def calcular_layout(n_itens: int) -> dict:
    """Calcula a linha inicial (rótulo/cabeçalho/item1/total) de cada bloco,
    empilhados um após o outro conforme a altura real de cada um (N itens)."""
    layout = {}
    label_row = PRIMEIRO_BLOCO_LABEL_ROW
    for distribuidor in DISTRIBUIDORES:
        header_row = label_row + 1
        item1_row = header_row + 1
        total_row = item1_row + n_itens
        layout[distribuidor] = {
            "label_row": label_row, "header_row": header_row,
            "item1_row": item1_row, "total_row": total_row,
        }
        label_row = total_row + 1 + GAP_APOS_TOTAL
    return layout


def formulas_item(r: int) -> list:
    return [
        f"=J{r}*L{r}",   # N Investimento em compra
        "",              # O Frete — manual
        f"=N{r}*0,06",   # P Imposto
        f"=SUM(N{r}:P{r})/L{r}",  # Q COGS UN
        f"=Q{r}*1,2",    # R Preço de venda UN (20%)
        "",              # S spacer
        "",              # T Vencedor — escrito à parte, depois dos 4 blocos
        "",              # U spacer
        f"=Q{r}*L{r}",   # V COGS TOTAL
        f"=V{r}*1,2",    # W Preço de venda (20%)
        f"=W{r}*0,2",    # X Margem Líquida (20%)
        f"=K{r}*L{r}",   # Y Margem (MÁX)
    ]


def preencher_bloco(distribuidor, itens_edital, resultados, pos):
    por_item = {}
    for r in (resultados or []):
        item_num = r["item"]
        preco = r.get("preco_un")
        atual = por_item.get(item_num)
        # cada scraper devolve até MAX_CHECK candidatos aprovados por item — sempre pega
        # o de menor preço, nunca o último da lista (bug achado 17/jul/2026: dict comprehension
        # {r["item"]: r for r in resultados} ficava com o último, que por acaso costuma ser o
        # mais caro já que os scrapers ordenam ascendente — planilha mostrava preço errado
        # tanto no CREF9-PR quanto no ESP-PENIT José Parada Neto)
        if atual is None or (preco is not None and (atual.get("preco_un") is None or preco < atual["preco_un"])):
            por_item[item_num] = r
    updates = []

    label_row, header_row, item1_row = pos["label_row"], pos["header_row"], pos["item1_row"]
    agora = datetime.now(BRT).strftime("%d/%m/%Y %H:%M")
    updates.append({"range": f"A{label_row}", "values": [[distribuidor]]})
    updates.append({"range": f"C{label_row}", "values": [[f"Última cotação: {agora}"]]})
    updates.append({"range": f"A{header_row}:AC{header_row}", "values": [HEADERS]})

    for i, edital_item in enumerate(itens_edital):
        row = item1_row + i
        item_num = edital_item["numero"]
        resultado_item = por_item.get(item_num)
        dados = linha_para_item(resultado_item, distribuidor)
        preco_leilao = edital_item.get("valor_unit", "")
        if isinstance(preco_leilao, str):
            preco_leilao = preco_leilao.replace("R$", "").strip().replace(".", "").replace(",", ".")
            try:
                preco_leilao = float(preco_leilao)
            except ValueError:
                preco_leilao = ""

        valores_a_l = [
            item_num, edital_item.get("produto", ""), edital_item.get("medida", ""),
            dados["especificacao"], dados["criterio"], distribuidor, dados["marca"],
            dados["link"], dados["obs"], dados["preco_un"], preco_leilao,
            edital_item.get("qtde", ""),
        ]
        updates.append({"range": f"A{row}:L{row}", "values": [valores_a_l]})
        updates.append({"range": f"N{row}:Y{row}", "values": [formulas_item(row)]})

    total_row = pos["total_row"]
    last_item_row = item1_row + len(itens_edital) - 1
    totais = [
        f"=SUM(N{item1_row}:N{last_item_row})", f"=SUM(O{item1_row}:O{last_item_row})",
        f"=SUM(P{item1_row}:P{last_item_row})", f"=SUM(Q{item1_row}:Q{last_item_row})",
        "", "", "", "",
        f"=SUM(V{item1_row}:V{last_item_row})", f"=SUM(W{item1_row}:W{last_item_row})",
        f"=SUM(X{item1_row}:X{last_item_row})", f"=SUM(Y{item1_row}:Y{last_item_row})",
    ]
    updates.append({"range": f"N{total_row}:Y{total_row}", "values": [totais]})

    return updates


def formulas_vencedor(layout, n_itens):
    """Cruza os 4 blocos na mesma posição de item e marca 🏆 no menor Preço UN (col J)."""
    updates = []
    for i in range(n_itens):
        js = [f"J{layout[d]['item1_row'] + i}" for d in DISTRIBUIDORES]
        for d in DISTRIBUIDORES:
            r = layout[d]["item1_row"] + i
            # PT-BR: ";" separa argumento de função, "," é só decimal (CLAUDE.md §15.5)
            formula = f'=IF(AND(J{r}<>"";J{r}=MIN({";".join(js)}));"🏆 Vencedor";"")'
            updates.append({"range": f"T{r}", "values": [[formula]]})
    return updates


MONEY_COLS_0IDX = [9, 10, 13, 14, 15, 16, 17, 21, 22, 23, 24]  # J,K,N,O,P,Q,R,V,W,X,Y
MONEDA = {"numberFormat": {"type": "CURRENCY", "pattern": "[$R$ -416]#,##0"}}
GRADE = {"style": "SOLID", "width": 1, "color": {"red": 0, "green": 0, "blue": 0}}


def _campo(sheet_id, r0, r1, c0, c1, fmt):
    return {"repeatCell": {
        "range": {"sheetId": sheet_id, "startRowIndex": r0, "endRowIndex": r1,
                   "startColumnIndex": c0, "endColumnIndex": c1},
        "cell": {"userEnteredFormat": fmt},
        "fields": "userEnteredFormat(" + ",".join(fmt.keys()) + ")",
    }}


def _borda(sheet_id, r0, r1, c0, c1):
    return {"updateBorders": {
        "range": {"sheetId": sheet_id, "startRowIndex": r0, "endRowIndex": r1,
                   "startColumnIndex": c0, "endColumnIndex": c1},
        "top": GRADE, "bottom": GRADE, "left": GRADE, "right": GRADE,
        "innerHorizontal": GRADE, "innerVertical": GRADE,
    }}


def limpar_formatacao(sheet_id, ate_linha):
    """Remove formatação órfã de rodadas anteriores com N de itens diferente
    (bloco dinâmico pode encolher/crescer — sem isso sobra caixa/borda fantasma
    de um bloco que existia numa posição que hoje está vazia).

    Nunca limpa VALORES das colunas AA (Produto Escolhido) e AC (Nº Certificado
    INMETRO) — só A:Y é limpo em main(). Ambas manuais/semi-automáticas (AC vem
    do inmetro_lookup.py, rodado à parte). Risco conhecido: se o Nº de itens
    mudar entre rodadas (edital que ganhou/perdeu item), marcação antiga fica
    na linha errada — usuário precisa remarcar/re-rodar depois."""
    return [{"repeatCell": {
        "range": {"sheetId": sheet_id, "startRowIndex": 2, "endRowIndex": max(ate_linha + 10, 300),
                   "startColumnIndex": 0, "endColumnIndex": 29},
        "cell": {"userEnteredFormat": {}},
        "fields": "userEnteredFormat",
    }}]


def formatar_bloco(sheet_id, pos, n_itens):
    label, header, item1, total = pos["label_row"], pos["header_row"], pos["item1_row"], pos["total_row"]
    reqs = [
        _campo(sheet_id, label - 1, label, 0, 1, {"textFormat": {"bold": True}}),
        _campo(sheet_id, header - 1, header, 0, 29, {"textFormat": {"bold": True}, "wrapStrategy": "WRAP"}),
        _borda(sheet_id, header - 1, total, 0, 25),
        _borda(sheet_id, header - 1, total, 26, 27),  # AA separado (Z é só respiro, sem borda)
        _borda(sheet_id, header - 1, total, 28, 29),  # AC separado (AB é só respiro, sem borda)
        _campo(sheet_id, total - 1, total, 0, 25, {"textFormat": {"bold": True}}),
    ]
    for c in MONEY_COLS_0IDX:
        reqs.append(_campo(sheet_id, item1 - 1, total, c, c + 1, MONEDA))
    return reqs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("spreadsheet_id")
    parser.add_argument("analise_json", help="JSON salvo por analisa_edital.py (tem os itens do edital)")
    parser.add_argument("--bransales")
    parser.add_argument("--cantu")
    parser.add_argument("--gp")
    parser.add_argument("--green")
    args = parser.parse_args()

    analise = carregar_json(args.analise_json)
    itens_edital = analise["itens"]
    n_itens = len(itens_edital)

    gc = gspread.oauth(credentials_filename=CREDENTIALS_FILE, authorized_user_filename=TOKEN_FILE)
    sh = gc.open_by_key(args.spreadsheet_id)
    ws = sh.worksheet(SHEET_NAME)

    layout = calcular_layout(n_itens)
    last_row = layout[DISTRIBUIDORES[-1]]["total_row"]
    ws.batch_clear([f"A3:Y{max(last_row, 200)}"])
    sh.batch_update({"requests": limpar_formatacao(ws.id, last_row)})

    fontes = {
        "Bransales":   args.bransales,
        "Cantu":       args.cantu,
        "GP":          args.gp,
        "Green Pneus": args.green,
    }

    fmt_requests = []
    updates = []
    for distribuidor in DISTRIBUIDORES:
        resultados = carregar_json(fontes[distribuidor]) if fontes[distribuidor] else None
        updates += preencher_bloco(distribuidor, itens_edital, resultados, layout[distribuidor])
        fmt_requests += formatar_bloco(ws.id, layout[distribuidor], n_itens)
        print(f"  [{distribuidor}] {n_itens} item(ns) do edital escrito(s)", file=sys.stderr)

    updates += formulas_vencedor(layout, n_itens)
    ws.batch_update(updates, value_input_option="USER_ENTERED")
    sh.batch_update({"requests": fmt_requests})

    print(f"\n✅ Planilha atualizada: https://docs.google.com/spreadsheets/d/{args.spreadsheet_id}/edit", file=sys.stderr)


if __name__ == "__main__":
    main()
