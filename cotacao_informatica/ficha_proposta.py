#!/usr/bin/env python3
"""ficha_proposta.py — F1 da automação de proposta (Compras.gov.br): lê a aba "Cotação" da
planilha de cotação de informática e gera uma ficha JSON por edital com o que vai em cada
campo da proposta: valor unitário inicial, valor mínimo (piso do robô de lances nativo,
IN 67/2021 dispensa · IN 73/2022 pregão), marca, fabricante e modelo.

Preço e produto vêm SÓ da aba principal (colunas "PREENCHIMENTO DO FORNECEDOR"). Nada é
inventado (CLAUDE.md §6.1: só participar com preço do fornecedor confirmado).

Preço (mesma base da fórmula do pneu, CLAUDE.md §5):
  COGS UN      = (Preço UN × Qtde + Frete total + Imposto 6% × Preço UN × Qtde) / Qtde
  Valor mínimo = COGS UN × (1 + margem mínima)           arredondado PRA CIMA no centavo
  Valor inicial= preço de referência do edital (teto); sem referência → COGS UN × 1,30 (margem-alvo)

Travas (regra de negócio em CLAUDE.md §19):
  item   PENDENTE  falta dado (Atende ≠ "Sim", preço, marca/modelo, frete, qtde)
         INVIAVEL  piso acima da referência do edital
         BLOQUEADO preço suspeito (custo < 20% da referência ou piso < 40% da mediana paga
                   em 12m — típico de erro de digitação); só libera com --aceitar-suspeito
         DUPLICADO mesmo nº de item 2× no edital
  ficha  EXPIRADA  encerramento já passou
         validade da cotação vazia/vencida → não fica pronta
  aprovação humana: --aprovar grava o hash da ficha em aprovacoes.json; se a planilha mudar
  qualquer campo da proposta depois, o hash muda e a aprovação cai sozinha. A F2 (extensão)
  só pode usar ficha com pronta_para_enviar E aprovada (conferir com verificar_ficha()).

Uso:
  python ficha_proposta.py <spreadsheet_id> [--margem-minima 0.20] [--dry-run]
  python ficha_proposta.py <spreadsheet_id> --aprovar <cnpj-ano-seq> [--aceitar-suspeito <item> ...]
  python ficha_proposta.py <spreadsheet_id> --exportar <cnpj-ano-seq>   → pacote_<chave>.json pra extensão (F2)
Saída: cotacao_informatica/dados/fichas/<cnpj>-<ano>-<seq>.json (gitignorado — preço é dado comercial)
"""
import argparse
import hashlib
import json
import math
import os
import re
import sys
from datetime import date, datetime

ABA_BASE = "Cotação"
LINHA_CABECALHO = 9  # índice 0-based: linha 10 da planilha
LINHA_VALIDADE = 5   # índice 0-based: linha 6 "Validade da cotação", valor em B:D
IMPOSTO = 0.06
MARGEM_ALVO = 0.30   # margem-alvo da vertical informática (usuário, 20/nov/2026)
MARGEM_MINIMA_PADRAO = 0.20  # provisória — usuário ainda não fixou o mínimo (20/nov/2026)
MARGEM_MINIMA_LIMITES = (0.0, 0.50)
CUSTO_MIN_VS_REF = 0.20     # custo abaixo de 20% da referência = suspeito
PISO_MIN_VS_MEDIANA = 0.40  # piso abaixo de 40% da mediana paga em 12m = suspeito
UNIDADES_UNITARIAS = re.compile(r"^(1(,00)?\s*)?(unidade|unid\.?|und\.?|un\.?|pe[çc]a|p[çc])$", re.I)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados", "fichas")
APROVACOES = "aprovacoes.json"

COLS = {
    "ref": "Ref. edital (órgão — nº/ano)",
    "encerra": "Encerramento do edital",
    "item": "Item nº",
    "link_pncp": "Link PNCP",
    "produto": "Produto",
    "desc": "Especificação técnica (descrição do item no PNCP)",
    "qtde": "Qtde",
    "unid": "Unid.",
    "ref_preco": "Preço referência do edital (R$/un)",
    "mediana_12m": "Preço pago no setor público — mediana 12m (R$/un)",
    "atende": "Atende a especificação? (Sim / Parcial / Não)",
    "marca_modelo": "Marca / Modelo",
    "ncm": "NCM",
    "preco_un": "Preço unitário (R$)",
    "frete": "Frete total até o CEP (R$)",
    "link_produto": "Link / catálogo do produto",
}

# Campos que viram proposta: mudou qualquer um, a aprovação humana cai.
CAMPOS_HASH = ("numero_item", "qtde", "valor_inicial", "valor_minimo", "marca", "fabricante", "modelo", "status")

RE_PNCP = re.compile(r"/editais/(\d{14})/(\d{4})/(\d+)")


def parse_brl(txt) -> float | None:
    """'R$ 3.599,00' / '3599' / '3.599,5' -> float. Vazio, negativo ou texto -> None."""
    if txt is None:
        return None
    if isinstance(txt, (int, float)):
        return float(txt) if txt >= 0 else None
    s = re.sub(r"[R$\s]", "", str(txt))
    if not s or not re.fullmatch(r"[\d.,]+", s):
        return None
    if "," in s:
        if s.count(",") > 1:
            return None
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1 or re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    return float(s)


def parse_qtde(txt) -> float | None:
    v = parse_brl(txt)
    return v if v and v > 0 else None


def parse_data(txt) -> date | None:
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", str(txt or ""))
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def chave_edital(link: str) -> str | None:
    m = RE_PNCP.search(link or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def separar_marca_modelo(txt: str) -> tuple[str, str, bool]:
    """'GET / PROJ VISION 5' -> (GET, PROJ VISION 5, ok). Sem separador -> (txt, txt, conferir)."""
    txt = (txt or "").strip()
    for sep in (" / ", "/", " - "):
        if sep in txt:
            marca, modelo = (p.strip() for p in txt.split(sep, 1))
            if marca and modelo:
                return marca, modelo, True
    return txt, txt, False


def teto_centavo(v: float) -> float:
    return math.ceil(round(v * 100, 6)) / 100


def validar_margem(margem_minima: float) -> None:
    lo, hi = MARGEM_MINIMA_LIMITES
    if not (lo <= margem_minima <= hi):
        raise ValueError(f"margem mínima {margem_minima} fora de [{lo}, {hi}] — use fração (0.10 = 10%)")


def calcular_precos(preco_un: float, qtde: float, frete_total: float, ref_preco: float | None,
                    margem_minima: float) -> dict:
    validar_margem(margem_minima)
    invest = preco_un * qtde
    cogs_un = (invest + frete_total + invest * IMPOSTO) / qtde
    piso = teto_centavo(cogs_un * (1 + margem_minima))
    inicial = round(ref_preco, 2) if ref_preco else teto_centavo(cogs_un * (1 + MARGEM_ALVO))
    inicial = max(inicial, piso) if not ref_preco else inicial  # sem referência, inicial nunca abaixo do piso
    if piso < cogs_un:  # trava dura (não usar assert: some com python -O)
        raise ValueError(f"piso {piso} abaixo do custo {cogs_un}")
    return {"cogs_un": round(cogs_un, 4), "valor_minimo": piso, "valor_inicial": inicial,
            "margem_no_inicial": round(inicial / cogs_un - 1, 4),
            "inviavel": bool(ref_preco) and piso > ref_preco}


def suspeitas(preco_un: float, piso: float, ref_preco: float | None, mediana: float | None) -> list[str]:
    out = []
    if ref_preco and preco_un < ref_preco * CUSTO_MIN_VS_REF:
        out.append(f"custo R$ {preco_un:.2f} < {CUSTO_MIN_VS_REF:.0%} da referência R$ {ref_preco:.2f} "
                   "(erro de digitação?)")
    if mediana and piso < mediana * PISO_MIN_VS_MEDIANA:
        out.append(f"piso R$ {piso:.2f} < {PISO_MIN_VS_MEDIANA:.0%} da mediana paga em 12m R$ {mediana:.2f}")
    return out


def montar_item(linha: dict, margem_minima: float, aceitos: set[str] = frozenset()) -> dict:
    item = {"numero_item": linha.get("item", "").strip(), "produto": linha.get("produto", ""),
            "qtde": parse_qtde(linha.get("qtde")), "unidade": linha.get("unid", ""),
            "ref_preco_edital": parse_brl(linha.get("ref_preco")),
            "mediana_12m": parse_brl(linha.get("mediana_12m")),
            "descricao_edital": linha.get("desc", ""), "link_produto": linha.get("link_produto", ""),
            "ncm": linha.get("ncm", "").strip(), "alertas": []}
    pend = []
    atende = (linha.get("atende") or "").strip().lower()
    if atende != "sim":
        pend.append(f"atende a especificação = '{linha.get('atende') or 'vazio'}' (precisa 'Sim')")
    preco_un = parse_brl(linha.get("preco_un"))
    if not preco_un:
        pend.append("falta preço unitário do fornecedor (ou valor inválido)")
    if not (linha.get("marca_modelo") or "").strip():
        pend.append("falta marca/modelo")
    if not item["qtde"]:
        pend.append("qtde inválida")
    frete = parse_brl(linha.get("frete"))
    if frete is None:
        pend.append("falta frete (escreva 0 se o frete está incluso no preço)")
    marca, modelo, ok_sep = separar_marca_modelo(linha.get("marca_modelo", ""))
    item.update({"marca": marca, "fabricante": marca, "modelo": modelo})
    if marca:
        item["alertas"].append(f"fabricante assumido = marca ({marca}) — conferir se o edital pede o fabricante real")
    if (linha.get("marca_modelo") or "").strip() and not ok_sep:
        item["alertas"].append("marca e modelo sem separador 'Marca / Modelo' — conferir antes de enviar")
    if item["unidade"] and not UNIDADES_UNITARIAS.match(item["unidade"].strip()):
        item["alertas"].append(f"unidade '{item['unidade']}' não é unitária — conferir se o preço é por essa unidade")
    if not item["ref_preco_edital"]:
        item["alertas"].append("edital sem preço de referência (sigiloso?) — valor inicial = custo + 30% (margem-alvo)")
    if pend:
        item.update({"status": "PENDENTE", "motivos": pend, "valor_inicial": None, "valor_minimo": None})
        return item
    p = calcular_precos(preco_un, item["qtde"], frete, item["ref_preco_edital"], margem_minima)
    item.update({"preco_fornecedor_un": preco_un, "frete_total": frete, **p, "status": "PRONTO", "motivos": []})
    if p["inviavel"]:
        item["status"] = "INVIAVEL"
        item["motivos"].append(f"piso R$ {p['valor_minimo']:.2f} acima da referência do edital "
                               f"R$ {item['ref_preco_edital']:.2f}")
        return item
    susp = suspeitas(preco_un, p["valor_minimo"], item["ref_preco_edital"], item["mediana_12m"])
    if susp and item["numero_item"] in aceitos:
        item["alertas"].append("preço suspeito ACEITO na aprovação humana: " + "; ".join(susp))
    elif susp:
        item.update({"status": "BLOQUEADO", "motivos": susp})
    return item


def hash_ficha(f: dict) -> str:
    base = {"edital": f["link_pncp"] or f["edital"], "encerramento": f["encerramento"],
            "margem_minima": f["margem_minima"],
            "itens": [{k: it.get(k) for k in CAMPOS_HASH} for it in f["itens"]]}
    return hashlib.sha256(json.dumps(base, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def checklist_f0(f: dict) -> list[str]:
    linhas = ["Login no Compras.gov.br com o CNPJ 46.552.201/0001-00 (B2G SUPPLY LTDA)."]
    for it in f["itens"]:
        if it["status"] == "PRONTO":
            linhas.append(f"Item {it['numero_item']}: valor unitário R$ {it['valor_inicial']:.2f} · "
                          f"VALOR MÍNIMO R$ {it['valor_minimo']:.2f} · marca {it['marca']} · modelo {it['modelo']}")
    linhas += ["ANTES de digitar: conferir no edital se o lance é por VALOR UNITÁRIO. Se for por valor total "
               "ou maior desconto, os valores desta ficha NÃO servem (são unitários em R$).",
               "Depois de salvar, reabrir a proposta e conferir cada VALOR MÍNIMO contra esta ficha "
               "(dígito a dígito — vírgula no lugar errado manda o robô ao chão).",
               "Modo aberto-fechado: alguém online na sessão pro lance final fechado (robô não cobre).",
               "Ficar de olho no chat do pregoeiro (pedido de proposta ajustada / documentos com prazo)."]
    return linhas


def montar_fichas(linhas: list[dict], margem_minima: float, hoje: date | None = None,
                  validade_cotacao: date | None = None, aprovacoes: dict | None = None) -> dict[str, dict]:
    validar_margem(margem_minima)
    hoje = hoje or date.today()
    aprovacoes = aprovacoes or {}
    grupos: dict[str, list[dict]] = {}
    for ln in linhas:
        if not (ln.get("ref") or "").strip():
            continue
        chave = chave_edital(ln.get("link_pncp", "")) or re.sub(r"\W+", "_", ln["ref"]).strip("_")
        grupos.setdefault(chave, []).append(ln)
    fichas = {}
    for chave, lns in grupos.items():
        aceitos = set(aprovacoes.get(chave, {}).get("suspeitos_aceitos", []))
        itens = [montar_item(ln, margem_minima, aceitos) for ln in lns]
        nums = [it["numero_item"] for it in itens]
        for it in itens:
            if nums.count(it["numero_item"]) > 1:
                it.update({"status": "DUPLICADO", "valor_inicial": None, "valor_minimo": None,
                           "motivos": [f"item {it['numero_item']} aparece {nums.count(it['numero_item'])}× no edital"]})
        f = {"edital": lns[0]["ref"], "encerramento": lns[0].get("encerra", ""),
             "link_pncp": lns[0].get("link_pncp", ""), "portal": "Compras.gov.br",
             "gerado_em": datetime.now().isoformat(timespec="seconds"), "margem_minima": margem_minima,
             "validade_cotacao": validade_cotacao.isoformat() if validade_cotacao else None,
             "itens": itens, "bloqueios": []}
        enc = parse_data(f["encerramento"])
        if enc is None:
            f["bloqueios"].append("data de encerramento ilegível")
        elif enc < hoje:
            f["bloqueios"].append(f"EXPIRADA — edital encerrou em {f['encerramento']}")
        if validade_cotacao is None:
            f["bloqueios"].append("validade da cotação vazia (célula B6 da aba Cotação)")
        elif validade_cotacao < hoje:
            f["bloqueios"].append(f"cotação vencida em {validade_cotacao:%d/%m/%Y}")
        elif enc and validade_cotacao < enc:
            f["bloqueios"].append(f"cotação vence ({validade_cotacao:%d/%m/%Y}) antes do encerramento — reconfirmar preço")
        st = [i["status"] for i in itens]
        f["resumo"] = {s: st.count(s) for s in ("PRONTO", "PENDENTE", "BLOQUEADO", "INVIAVEL", "DUPLICADO") if s in st}
        f["pronta_para_enviar"] = bool(st) and all(s == "PRONTO" for s in st) and not f["bloqueios"]
        f["hash"] = hash_ficha(f)
        ap = aprovacoes.get(chave)
        f["aprovada"] = bool(ap) and ap.get("hash") == f["hash"] and f["pronta_para_enviar"]
        if ap and ap.get("hash") and not f["aprovada"]:
            f["bloqueios"].append("aprovação anterior REVOGADA — ficha mudou desde a aprovação, revisar e aprovar de novo")
        f["checklist_f0"] = checklist_f0(f)
        fichas[chave] = f
    return fichas


def verificar_ficha(f: dict) -> tuple[bool, str]:
    """Trava pro consumidor (F2): só aceita ficha pronta, aprovada e íntegra (hash recalculado bate)."""
    if not f.get("pronta_para_enviar"):
        return False, "ficha não está pronta: " + "; ".join(f.get("bloqueios") or ["itens não PRONTO"])
    if not f.get("aprovada"):
        return False, "ficha não aprovada por humano (--aprovar)"
    if hash_ficha(f) != f.get("hash"):
        return False, "hash não bate — ficha editada depois de gerada"
    for it in f["itens"]:
        if not (it.get("valor_minimo") and it.get("valor_inicial")) or it["valor_minimo"] > it["valor_inicial"]:
            return False, f"item {it['numero_item']}: valor mínimo/inicial inconsistente"
        if it["valor_minimo"] < it["cogs_un"]:
            return False, f"item {it['numero_item']}: valor mínimo abaixo do custo"
    return True, "ok"


def aprovar(regerar, chave: str, aceitar: list[str]) -> str:
    """regerar(aprovacoes) -> fichas. Devolve o hash a gravar; SystemExit se a ficha não pode ser aprovada."""
    f = regerar({}).get(chave)
    if f is None:
        raise SystemExit(f"edital {chave} não está na planilha")
    bloq_itens = [it["numero_item"] for it in f["itens"] if it["status"] == "BLOQUEADO"]
    nao_aceitos = [n for n in bloq_itens if n not in aceitar]
    if nao_aceitos:
        raise SystemExit(f"itens com preço suspeito não aceitos: {nao_aceitos} — confira na planilha ou use "
                         f"--aceitar-suspeito {' '.join(nao_aceitos)}")
    f = regerar({chave: {"suspeitos_aceitos": aceitar}})[chave]
    if not f["pronta_para_enviar"]:
        raise SystemExit("não aprovo ficha que não está pronta: " + "; ".join(
            f["bloqueios"] + [f"item {i['numero_item']} {i['status']}" for i in f["itens"] if i["status"] != "PRONTO"]))
    return f["hash"]


PNCP_DETALHE = "https://pncp.gov.br/api/consulta/v1/orgaos/{cnpj}/compras/{ano}/{seq}"
RE_COMPRA_ID = re.compile(r"[?&]compra=(\d+)")


def meta_compra(detalhe: dict) -> dict:
    """Identificação da compra no Compras.gov.br a partir do detalhe PNCP (api/consulta/v1).
    A extensão (F2) só preenche se a página aberta bater com isso."""
    if (detalhe.get("usuarioNome") or "") != "Compras.gov.br":
        raise SystemExit(f"edital não roda no Compras.gov.br (sistema: {detalhe.get('usuarioNome')!r}) — F2 não cobre")
    m = RE_COMPRA_ID.search(detalhe.get("linkSistemaOrigem") or "")
    uasg = str((detalhe.get("unidadeOrgao") or {}).get("codigoUnidade") or "")
    if not (m and uasg and detalhe.get("numeroCompra")):
        raise SystemExit("PNCP não trouxe UASG / número da compra / link do Compras.gov.br — conferir à mão")
    num, ano, cid = str(detalhe["numeroCompra"]), str(detalhe.get("anoCompra")), m.group(1)
    # id do Compras.gov.br = UASG + modalidade (2) + nº da compra (5) + ano (4), ex 791190 06 00202 2026
    if not (cid.startswith(uasg) and cid.endswith(ano) and num.isdigit() and cid[len(uasg) + 2:-4] == num.zfill(5)):
        raise SystemExit(f"id da compra {cid} não bate com UASG {uasg} / nº {num}/{ano} — conferir à mão")
    return {"uasg": uasg, "numero_compra": num, "ano_compra": ano,
            "compra_id": cid, "modalidade": detalhe.get("modalidadeNome", ""),
            "link_compras": detalhe.get("linkSistemaOrigem")}


def fmt_qtde(q: float) -> str:
    """2.0 -> '2', 2.5 -> '2.5', 1e6 -> '1000000' (sem notação científica; igual ao JS)."""
    return f"{q:.4f}".rstrip("0").rstrip(".")


def canonico_pacote(p: dict) -> str:
    """Texto canônico que a extensão recalcula (SHA-256) — mesma fórmula em extensao_compras/lib.js."""
    linhas = [f"{p['chave']}|{p['uasg']}|{p['numero_compra']}|{p['ano_compra']}|{p['compra_id']}|{p['encerramento']}"]
    for it in p["itens"]:
        linhas.append(f"{it['numero_item']}|{fmt_qtde(it['qtde'])}|{it['valor_inicial']:.2f}|{it['valor_minimo']:.2f}|"
                      f"{it['marca']}|{it['fabricante']}|{it['modelo']}")
    return "\n".join(linhas)


def montar_pacote(f: dict, chave: str, meta: dict) -> dict:
    """Pacote mínimo pra extensão: só ficha pronta + aprovada + íntegra (verificar_ficha)."""
    ok, msg = verificar_ficha(f)
    if not ok:
        raise SystemExit(f"não exporto {chave}: {msg}")
    p = {"versao": 1, "chave": chave, "edital": f["edital"], "encerramento": f["encerramento"],
         "hash_ficha": f["hash"], **meta,
         "itens": [{k: it[k] for k in ("numero_item", "qtde", "valor_inicial", "valor_minimo", "marca", "fabricante", "modelo")}
                   for it in f["itens"]]}
    p["checksum"] = hashlib.sha256(canonico_pacote(p).encode("utf-8")).hexdigest()
    return p


def ler_planilha(spreadsheet_id: str) -> tuple[list[dict], date | None]:
    import gspread
    gc = gspread.oauth(credentials_filename=os.path.join(REPO, "credentials.json"),
                       authorized_user_filename=os.path.join(REPO, "token.json"))
    vals = gc.open_by_key(spreadsheet_id).worksheet(ABA_BASE).get_all_values()
    validade = next((d for d in map(parse_data, vals[LINHA_VALIDADE][1:4]) if d), None)
    cab = vals[LINHA_CABECALHO]
    faltando = [c for c in COLS.values() if c not in cab]
    if faltando:
        raise SystemExit(f"Colunas não encontradas na linha {LINHA_CABECALHO + 1} da aba '{ABA_BASE}': {faltando}")
    idx = {k: cab.index(c) for k, c in COLS.items()}
    linhas = [{k: (r[i] if i < len(r) else "") for k, i in idx.items()} for r in vals[LINHA_CABECALHO + 1:] if r and r[0]]
    return linhas, validade


def gravar_json(caminho: str, dados) -> None:
    tmp = caminho + ".tmp"  # escrita atômica: ficha nunca fica pela metade
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(dados, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, caminho)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spreadsheet_id")
    ap.add_argument("--margem-minima", type=float, default=MARGEM_MINIMA_PADRAO)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--aprovar", metavar="CNPJ-ANO-SEQ")
    ap.add_argument("--aceitar-suspeito", nargs="*", default=[], metavar="ITEM")
    ap.add_argument("--exportar", metavar="CNPJ-ANO-SEQ", help="gera pacote_<chave>.json pra extensão (F2)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # console Windows (cp1252) quebra nos emojis de status
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        validar_margem(a.margem_minima)
    except ValueError as e:
        raise SystemExit(str(e))
    os.makedirs(SAIDA, exist_ok=True)
    arq_ap = os.path.join(SAIDA, APROVACOES)
    aprovacoes = json.load(open(arq_ap, encoding="utf-8")) if os.path.exists(arq_ap) else {}
    linhas, validade = ler_planilha(a.spreadsheet_id)
    fichas = montar_fichas(linhas, a.margem_minima, validade_cotacao=validade, aprovacoes=aprovacoes)

    if a.aprovar:
        h = aprovar(lambda aps: montar_fichas(linhas, a.margem_minima, validade_cotacao=validade, aprovacoes=aps),
                    a.aprovar, a.aceitar_suspeito)
        if a.dry_run:
            print(f"--dry-run: {a.aprovar} PODE ser aprovada (hash {h}), nada gravado")
            return
        aprovacoes[a.aprovar] = {"hash": h, "aprovado_em": datetime.now().isoformat(timespec="seconds"),
                                 "margem_minima": a.margem_minima, "suspeitos_aceitos": a.aceitar_suspeito}
        gravar_json(arq_ap, aprovacoes)
        fichas = montar_fichas(linhas, a.margem_minima, validade_cotacao=validade, aprovacoes=aprovacoes)
        print(f"✅ {a.aprovar} aprovada (hash {h}). Qualquer mudança na planilha revoga.")

    if a.exportar:
        import requests
        if a.exportar not in fichas:
            raise SystemExit(f"edital {a.exportar} não está na planilha")
        if not re.fullmatch(r"\d{14}-\d{4}-\d+", a.exportar):
            raise SystemExit(f"chave {a.exportar} não é <cnpj>-<ano>-<seq> do PNCP — sem link PNCP não exporto")
        cnpj, ano, seq = a.exportar.split("-")
        r = requests.get(PNCP_DETALHE.format(cnpj=cnpj, ano=ano, seq=seq), timeout=30)
        r.raise_for_status()
        pac = montar_pacote(fichas[a.exportar], a.exportar, meta_compra(r.json()))
        destino = os.path.join(SAIDA, f"pacote_{a.exportar}.json")
        if not a.dry_run:
            gravar_json(destino, pac)
        print(f"📦 pacote {a.exportar}: UASG {pac['uasg']} · compra {pac['numero_compra']}/{pac['ano_compra']} · "
              f"{len(pac['itens'])} itens · checksum {pac['checksum'][:12]} → {destino}")
        return

    tot: dict[str, int] = {}
    for chave, f in sorted(fichas.items(), key=lambda kv: (parse_data(kv[1]["encerramento"]) or date.max)):
        for s, n in f["resumo"].items():
            tot[s] = tot.get(s, 0) + n
        marca = "🟢" if f["aprovada"] else ("✅" if f["pronta_para_enviar"] else "⏳")
        print(f"{marca} {f['encerramento']} {f['edital']} [{chave}] — {f['resumo']}")
        for b in f["bloqueios"]:
            print(f"     ⛔ {b}")
        for it in f["itens"]:
            if it["status"] == "PRONTO":
                print(f"     item {it['numero_item']}: inicial R$ {it['valor_inicial']:.2f} · "
                      f"VALOR MÍNIMO R$ {it['valor_minimo']:.2f} · {it['marca']} / {it['modelo']}")
            else:
                print(f"     item {it['numero_item']}: {it['status']} — {'; '.join(it['motivos'])}")
            for al in it["alertas"]:
                print(f"        ⚠️ {al}")
        if not a.dry_run:
            gravar_json(os.path.join(SAIDA, f"{chave}.json"), f)
    print(f"\n{len(fichas)} editais · itens {tot} · validade da cotação: "
          f"{validade:%d/%m/%Y}" if validade else f"\n{len(fichas)} editais · itens {tot} · validade da cotação: VAZIA")
    if not a.dry_run:
        print(f"fichas em {SAIDA}")


if __name__ == "__main__":
    main()
