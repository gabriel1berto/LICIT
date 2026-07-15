#!/usr/bin/env python3
"""
parecer_juridico.py — Camada 2: parecer jurídico (arsenal) sobre um edital já analisado.

Roda DEPOIS da Camada 1 (analisa_edital.py), manualmente, só quando a seção "PRÓXIMO
PASSO" do card indicar que vale a pena evoluir (ou por decisão direta do usuário).
Nunca chamado automaticamente pelo pipeline de Camada 1.

Uso:
  python parecer_juridico.py <analise.json> <NOTION_PAGE_ID>
  python parecer_juridico.py <analise.json> --dry-run

<analise.json> é o arquivo salvo pela Camada 1 (analise_{cnpj}_{ano}_{seq}.json).

Requer (variáveis de ambiente):
  ANTHROPIC_API_KEY  — chave da API Claude
  NOTION_TOKEN       — token de integração Notion
"""

import json
import re
import sys
from pathlib import Path

import anthropic

from analisa_edital import (
    CLAUDE_MODEL,
    b_callout,
    b_divider,
    b_h2,
    b_para,
    b_table,
    notion_append,
    notion_delete,
    notion_get_children,
)

ARSENAL_PATH = Path(__file__).parent / "arsenal_juridico.md"
MARCADOR_SECAO = "⚖️ PARECER JURÍDICO"

# ─── PROMPT ───────────────────────────────────────────────────────────────────

PROMPT_SISTEMA = """\
Você é especialista em licitações públicas brasileiras (Lei 14.133/21) atuando como \
Camada 2 (parecer jurídico) de um pipeline de análise de editais. Você recebe:
(1) o arquivo ARSENAL JURÍDICO completo (catálogo de mecanismos ARS-01 a ARS-19/B1);
(2) os FATOS extraídos da Camada 1 deste edital específico (bloco "arsenal_fatos": \
pagamento, entrega, srp, matriz de riscos — cada um com "fonte" citando o trecho \
literal do documento, ou null se não encontrado), além de cabeçalho e alertas do edital.

Retorne SOMENTE JSON válido, sem texto adicional, markdown ou blocos de código, seguindo \
a estrutura abaixo.

Regras obrigatórias (não negociáveis):
- Toda recomendação referencia um "id" do arsenal (ex: "ARS-07") e "baseado_em" — o campo \
exato da Camada 1 que sustenta a recomendação (ex: "arsenal_fatos.pagamento.fonte") ou \
"geral" para benefícios que valem independente do edital (ex: ARS-04, ARS-05).
- Campo com "fonte": null na Camada 1 → NUNCA presuma o conteúdo. Se não há fato \
suficiente pra aplicar um mecanismo, ou sugira ARS-01 (esclarecimento) pedindo o dado que \
falta, ou não inclua o mecanismo na lista — nunca invente prazo/condição.
- "confianca" obrigatória em cada item: "alta" (fato com fonte literal clara), "media" \
(fato parcial ou inferido do contexto), "baixa" (fato ausente, recomendação \
condicional/genérica).
- Se o edital citar norma municipal/estadual específica não coberta pelo arsenal (que é só \
federal — Lei 14.133, Decreto 11.462 SRP, IN 77/2022, LC 123/2006), sinalize a divergência \
explicitamente em "divergencias_norma_local" — nunca aplique o artigo federal como se \
valesse sem checar.
- ARS-04 (regularização fiscal tardia) e ARS-05 (empate ficto) são benefícios ME/EPP \
gerais — inclua sempre que o edital não for vedado a ME/EPP, mesmo sem fato específico do \
arsenal (baseado_em="geral").
"""

PROMPT_ESTRUTURA = """\
{
  "recomendacoes": [
    {
      "id": "ARS-07",
      "titulo": "Revisão de preço pra cima",
      "recomendacao": "Montar dossiê de custo (cotação datada + câmbio) desde já, antes de precisar.",
      "baseado_em": "arsenal_fatos.srp.eh_srp",
      "confianca": "alta"
    }
  ],
  "divergencias_norma_local": [
    "Edital cita Decreto Municipal XX/2026 pra reajuste — não coberto pelo arsenal (só federal); confirmar regra local antes de aplicar ARS-07/08."
  ]
}
"""


def carregar_analise(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def gerar_parecer(analise: dict) -> dict:
    arsenal_texto = ARSENAL_PATH.read_text(encoding="utf-8")
    contexto = {
        "cabecalho":     analise.get("cabecalho", {}),
        "arsenal_fatos": analise.get("arsenal", {}),
        "alertas":       analise.get("alertas", {}),
    }
    cliente = anthropic.Anthropic()
    resp = cliente.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=PROMPT_SISTEMA,
        messages=[{"role": "user", "content":
            f"ARSENAL JURÍDICO:\n{arsenal_texto}\n\n"
            f"Estrutura esperada:\n{PROMPT_ESTRUTURA}\n\n"
            f"FATOS DO EDITAL (Camada 1):\n{json.dumps(contexto, ensure_ascii=False)}"}]
    )
    raw = resp.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)
    return json.loads(raw)


# ─── NOTION ───────────────────────────────────────────────────────────────────

def build_parecer_blocks(parecer: dict) -> list:
    bl = [b_divider(), b_h2(f"{MARCADOR_SECAO} (Camada 2)")]
    recs = parecer.get("recomendacoes", [])
    if recs:
        bl.append(b_table(
            ["ID", "Mecanismo", "Recomendação", "Baseado em", "Confiança"],
            [[r["id"], r.get("titulo", ""), r["recomendacao"], r["baseado_em"], r["confianca"]]
             for r in recs]
        ))
    else:
        bl.append(b_para("Nenhuma recomendação aplicável com os fatos extraídos até agora."))

    for d in parecer.get("divergencias_norma_local", []):
        bl.append(b_callout(d, "⚠️"))
    return bl


def remover_parecer_anterior(notion_id: str) -> None:
    """Remove só a seção de parecer de uma rodada anterior (identificada pelo heading
    marcador), sem tocar no resto do card gerado pela Camada 1 — diferente da limpeza
    de analisa_edital.py, que regenera o card inteiro."""
    children = notion_get_children(notion_id)
    idx_inicio = None
    for i, b in enumerate(children):
        if b["type"] == "heading_2":
            texto = "".join(rt.get("plain_text", "") for rt in b["heading_2"]["rich_text"])
            if texto.startswith(MARCADOR_SECAO):
                idx_inicio = i
                break
    if idx_inicio is None:
        return
    if idx_inicio > 0 and children[idx_inicio - 1]["type"] == "divider":
        idx_inicio -= 1
    idx_fim = len(children)
    for j in range(idx_inicio + 1, len(children)):
        if children[j]["type"] == "divider":
            idx_fim = j
            break
    for b in children[idx_inicio:idx_fim]:
        notion_delete(b["id"])


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main() -> None:
    dry_run = "--dry-run" in sys.argv
    args    = [a for a in sys.argv[1:] if not a.startswith("--")]

    if len(args) < 1 or (not dry_run and len(args) < 2):
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    analise_path = args[0]
    notion_id    = args[1].replace("-", "") if not dry_run else None

    print(f"📖 Lendo {analise_path}...", file=sys.stderr)
    analise = carregar_analise(analise_path)

    print("⚖️  Gerando parecer jurídico (Camada 2)...", file=sys.stderr)
    parecer = gerar_parecer(analise)
    print(f"   {len(parecer.get('recomendacoes', []))} recomendação(ões)", file=sys.stderr)

    if dry_run:
        sys.stdout.buffer.write(json.dumps(parecer, ensure_ascii=False, indent=2).encode("utf-8"))
        print("\n✅ Dry-run concluído — JSON impresso no stdout", file=sys.stderr)
        return

    print("✏️  Escrevendo parecer no Notion...", file=sys.stderr)
    remover_parecer_anterior(notion_id)
    novos = build_parecer_blocks(parecer)
    notion_append(notion_id, novos)
    print(f"   {len(novos)} blocos inseridos", file=sys.stderr)
    print(f"\n✅ https://app.notion.com/p/{notion_id}", file=sys.stderr)

    out = Path(analise_path).with_name(Path(analise_path).stem + "_parecer.json")
    out.write_text(json.dumps(parecer, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   JSON salvo em {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
