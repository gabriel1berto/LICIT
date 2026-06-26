#!/usr/bin/env python3
"""
pncp_radar.py — Radar diário de licitações de pneu no PNCP.

Busca processos publicados ontem + vencendo em até 2 dias,
agrupa por portal e envia email HTML.

Variáveis de ambiente (GitHub Secrets):
  GMAIL_USER         — remetente (ex: seuemail@gmail.com)
  GMAIL_APP_PASSWORD — senha de app do Gmail (não a senha normal)
  EMAIL_TO           — destinatário (padrão: mesmo que GMAIL_USER)
"""

import os
import re
import smtplib
import time
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

# ── CONFIGURAÇÃO ───────────────────────────────────────────────────────────────

PNCP_SEARCH  = "https://pncp.gov.br/api/search/"
PNCP_DETAIL  = "https://pncp.gov.br/api/consulta/v1/orgaos/{cnpj}/compras/{ano}/{seq}"
PNCP_APP_URL = "https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}"

BRT = timezone(timedelta(hours=-3))

MODALIDADES = [6, 8]  # 6 = Pregão Eletrônico, 8 = Dispensa

SLEEP_BETWEEN_DETAIL = 0.6   # segundos entre chamadas ao endpoint de detalhe
SLEEP_BETWEEN_PAGES  = 0.8   # segundos entre páginas da busca
TAM_PAGINA           = 50
MAX_RETRIES          = 4     # tentativas por request

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer":         "https://pncp.gov.br/",
}

PORTAL_MAP = {
    "compras.gov":         "Compras.gov.br",
    "governançabrasil":    "BLL Compras",
    "ecustomize":          "Portal de Compras Públicas",
    "licitanet":           "LicitaNet",
    "licitar digital":     "Licitar Digital",
    "bbmnet":              "BBMNET",
    "embras":              "ProCompras",
    "megasoft":            "Megasoft",
    "elotech":             "Elotech",
    "betha":               "Betha Licitações",
    "publisol":            "Publisol",
    "softplan":            "Softplan",
}

# Portais sem URL externa — licitante precisa contatar órgão
SEM_PORTAL_EXTERNO = {"Megasoft", "Elotech", "Betha Licitações", "Softplan"}


# ── HELPERS ────────────────────────────────────────────────────────────────────

def resolve_portal(usuario_nome: str) -> str:
    lower = (usuario_nome or "").lower()
    for key, portal in PORTAL_MAP.items():
        if key in lower:
            return portal
    return usuario_nome or "Desconhecido"


def fmt_valor(v) -> str:
    if v is None:
        return "—"
    if v == 0:
        return "—"
    if v >= 1_000_000:
        return f"R$ {v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"R$ {v/1_000:.0f}K"
    return f"R$ {v:.0f}"


def fmt_valor_long(v) -> str:
    if v is None or v == 0:
        return "—"
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_date(s: str) -> str:
    if not s:
        return "—"
    try:
        return datetime.fromisoformat(s[:16]).strftime("%d/%m %H:%M")
    except Exception:
        return s[:10]


def fmt_date_short(s: str) -> str:
    if not s:
        return "—"
    try:
        return datetime.fromisoformat(s[:16]).strftime("%d/%m")
    except Exception:
        return s[:10]


def clean_objeto(desc: str, max_len: int = 130) -> str:
    if not desc:
        return "—"
    desc = re.sub(r"^\[.*?\]\s*[-–]?\s*", "", desc).strip()
    if len(desc) > max_len:
        desc = desc[:max_len].rstrip() + "…"
    return desc


def build_link(item: dict) -> str:
    return PNCP_APP_URL.format(
        cnpj=item.get("orgao_cnpj", ""),
        ano=item.get("ano", ""),
        seq=item.get("numero_sequencial", ""),
    )


def days_until(s: str) -> int | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s[:16]).replace(tzinfo=BRT)
        delta = (dt - datetime.now(BRT)).days
        return delta
    except Exception:
        return None


# ── FETCH ──────────────────────────────────────────────────────────────────────

def _get_with_retry(url: str, params: dict | None = None) -> requests.Response | None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=30)
            if r.status_code == 429:
                wait = 5 * attempt
                print(f"  rate limit — aguardando {wait}s (tentativa {attempt})")
                time.sleep(wait)
                continue
            return r
        except (requests.ConnectionError, requests.Timeout) as e:
            wait = 3 * attempt
            print(f"  conexão falhou ({e.__class__.__name__}) — aguardando {wait}s (tentativa {attempt})")
            time.sleep(wait)
    return None


def fetch_search_page(modalidade: int, pagina: int) -> dict:
    r = _get_with_retry(PNCP_SEARCH, params={
        "q":               "pneu",
        "tipos_documento": "edital",
        "ordenacao":       "-data",
        "pagina":          pagina,
        "tam_pagina":      TAM_PAGINA,
        "status":          "recebendo_proposta",
        "modalidades":     modalidade,
    })
    if r is None:
        raise RuntimeError(f"Falha ao buscar página {pagina} modalidade {modalidade}")
    r.raise_for_status()
    return r.json()


def collect_all_open(modalidade: int) -> list[dict]:
    all_items: list[dict] = []
    pagina = 1
    while True:
        data  = fetch_search_page(modalidade, pagina)
        items = data.get("items", [])
        total = data.get("total", 0)
        all_items.extend(items)
        print(f"  modalidade={modalidade} pág={pagina} ({len(all_items)}/{total})")
        if not items or len(all_items) >= total:
            break
        pagina += 1
        time.sleep(SLEEP_BETWEEN_PAGES)
    return all_items


def fetch_detail(cnpj: str, ano: str, seq: str) -> dict | None:
    url = PNCP_DETAIL.format(cnpj=cnpj, ano=ano, seq=seq)
    r   = _get_with_retry(url)
    if r is not None and r.status_code == 200:
        return r.json()
    return None


def enrich(items: list[dict]) -> list[dict]:
    for i, item in enumerate(items, 1):
        cnpj = item.get("orgao_cnpj", "")
        ano  = item.get("ano", "")
        seq  = item.get("numero_sequencial", "")
        if cnpj and ano and seq:
            detail = fetch_detail(cnpj, ano, seq)
            if detail:
                item["usuarioNome"]        = detail.get("usuarioNome", "")
                item["valorTotalEstimado"] = detail.get("valorTotalEstimado")
                item["portal"]             = resolve_portal(item["usuarioNome"])
            else:
                item["portal"] = resolve_portal("")
        print(f"  detalhe {i}/{len(items)}: {item.get('portal','?')} — {item.get('orgao_nome','')[:40]}")
        time.sleep(SLEEP_BETWEEN_DETAIL)
    return items


# ── FILTROS ────────────────────────────────────────────────────────────────────

def filter_published_yesterday(items: list[dict]) -> list[dict]:
    yesterday = (datetime.now(BRT) - timedelta(days=1)).date()
    return [
        i for i in items
        if i.get("data_publicacao_pncp", "")[:10] == str(yesterday)
    ]


def filter_expiring_soon(items: list[dict], days: int = 2) -> list[dict]:
    now     = datetime.now(BRT)
    cutoff  = now + timedelta(days=days)
    result  = []
    for item in items:
        fim = item.get("data_fim_vigencia", "")
        if not fim:
            continue
        try:
            dt = datetime.fromisoformat(fim[:16]).replace(tzinfo=BRT)
            if now <= dt <= cutoff:
                result.append(item)
        except Exception:
            pass
    return result


def group_by_portal(items: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for item in items:
        portal = item.get("portal") or resolve_portal(item.get("usuarioNome", ""))
        groups.setdefault(portal, []).append(item)
    return dict(sorted(groups.items(), key=lambda x: len(x[1]), reverse=True))


# ── HTML ───────────────────────────────────────────────────────────────────────

_ROW_ODD  = "#ffffff"
_ROW_EVEN = "#f8f9fb"

def _process_row(item: dict, bg: str) -> str:
    orgao   = item.get("orgao_nome", "")[:35]
    uf      = item.get("uf", "")
    objeto  = clean_objeto(item.get("description", ""))
    modal   = "Pregão" if item.get("modalidade_licitacao_id") == "6" else "Dispensa"
    prazo   = fmt_date_short(item.get("data_fim_vigencia", ""))
    valor   = fmt_valor(item.get("valorTotalEstimado"))
    link    = build_link(item)
    portal  = item.get("portal", "")
    sem_ext = portal in SEM_PORTAL_EXTERNO

    aviso = ""
    if sem_ext:
        aviso = ' <span style="color:#e67e22;font-size:11px;">⚠ sem portal externo</span>'

    return f"""
    <tr style="background:{bg};">
      <td style="padding:10px 12px;font-size:13px;color:#2c3e50;vertical-align:top;">
        <strong>{orgao}/{uf}</strong>{aviso}<br>
        <span style="color:#555;font-size:12px;">{objeto}</span>
      </td>
      <td style="padding:10px 8px;font-size:12px;color:#555;white-space:nowrap;vertical-align:top;">{modal}</td>
      <td style="padding:10px 8px;font-size:12px;color:#555;white-space:nowrap;vertical-align:top;">{prazo}</td>
      <td style="padding:10px 8px;font-size:13px;color:#27ae60;white-space:nowrap;vertical-align:top;font-weight:bold;">{valor}</td>
      <td style="padding:10px 8px;vertical-align:top;">
        <a href="{link}" style="background:#2980b9;color:#fff;padding:4px 10px;border-radius:4px;text-decoration:none;font-size:12px;white-space:nowrap;">Acessar →</a>
      </td>
    </tr>"""


def _urgency_row(item: dict, bg: str) -> str:
    orgao   = item.get("orgao_nome", "")[:35]
    uf      = item.get("uf", "")
    modal   = "Pregão" if item.get("modalidade_licitacao_id") == "6" else "Dispensa"
    portal  = item.get("portal", "")
    prazo   = fmt_date(item.get("data_fim_vigencia", ""))
    valor   = fmt_valor(item.get("valorTotalEstimado"))
    link    = build_link(item)
    d       = days_until(item.get("data_fim_vigencia", ""))
    urgency = "HOJE" if d == 0 else "AMANHÃ" if d == 1 else f"em {d}d"
    color   = "#c0392b" if d == 0 else "#e67e22" if d == 1 else "#f39c12"

    return f"""
    <tr style="background:{bg};">
      <td style="padding:10px 12px;font-size:13px;white-space:nowrap;">
        <span style="color:{color};font-weight:bold;">{urgency}</span>
      </td>
      <td style="padding:10px 8px;font-size:13px;color:#2c3e50;">{portal}</td>
      <td style="padding:10px 8px;font-size:13px;color:#2c3e50;">{orgao}/{uf}</td>
      <td style="padding:10px 8px;font-size:12px;color:#555;white-space:nowrap;">{modal}</td>
      <td style="padding:10px 8px;font-size:12px;color:#555;white-space:nowrap;">{prazo}</td>
      <td style="padding:10px 8px;font-size:13px;color:#27ae60;font-weight:bold;">{valor}</td>
      <td style="padding:10px 8px;">
        <a href="{link}" style="background:#c0392b;color:#fff;padding:4px 10px;border-radius:4px;text-decoration:none;font-size:12px;white-space:nowrap;">Acessar →</a>
      </td>
    </tr>"""


def build_html(yesterday_items: list[dict], expiring_items: list[dict]) -> str:
    brt_now     = datetime.now(BRT)
    yesterday   = (brt_now - timedelta(days=1)).strftime("%d/%m/%Y")
    run_at      = brt_now.strftime("%d/%m/%Y %H:%M")
    total_proc  = len(yesterday_items)
    total_valor = sum(i.get("valorTotalEstimado") or 0 for i in yesterday_items)

    # ── Seção urgência ─────────────────────────────────────────────────────────
    urgency_html = ""
    if expiring_items:
        rows = "".join(
            _urgency_row(i, _ROW_ODD if idx % 2 == 0 else _ROW_EVEN)
            for idx, i in enumerate(expiring_items)
        )
        urgency_html = f"""
        <tr><td style="padding:0 0 8px;">
          <table width="100%" cellpadding="0" cellspacing="0"
                 style="border-radius:6px;overflow:hidden;border:2px solid #e74c3c;">
            <tr style="background:#e74c3c;">
              <td colspan="7" style="padding:12px 16px;color:#fff;font-size:15px;font-weight:bold;">
                🚨 Vencem em até 2 dias — {len(expiring_items)} processo{'s' if len(expiring_items)>1 else ''}
              </td>
            </tr>
            <tr style="background:#fdf3f3;">
              <th style="padding:8px 12px;font-size:11px;color:#888;text-align:left;border-bottom:1px solid #eee;">Prazo</th>
              <th style="padding:8px 8px;font-size:11px;color:#888;text-align:left;border-bottom:1px solid #eee;">Portal</th>
              <th style="padding:8px 8px;font-size:11px;color:#888;text-align:left;border-bottom:1px solid #eee;">Órgão/UF</th>
              <th style="padding:8px 8px;font-size:11px;color:#888;text-align:left;border-bottom:1px solid #eee;">Tipo</th>
              <th style="padding:8px 8px;font-size:11px;color:#888;text-align:left;border-bottom:1px solid #eee;">Encerra</th>
              <th style="padding:8px 8px;font-size:11px;color:#888;text-align:left;border-bottom:1px solid #eee;">Valor</th>
              <th style="padding:8px 8px;font-size:11px;color:#888;border-bottom:1px solid #eee;"></th>
            </tr>
            {rows}
          </table>
        </td></tr>"""

    # ── Seções por portal ──────────────────────────────────────────────────────
    groups       = group_by_portal(yesterday_items)
    portals_html = ""

    for portal, items in groups.items():
        total_p = sum(i.get("valorTotalEstimado") or 0 for i in items)
        rows    = "".join(
            _process_row(i, _ROW_ODD if idx % 2 == 0 else _ROW_EVEN)
            for idx, i in enumerate(items)
        )
        sem_ext_note = ""
        if portal in SEM_PORTAL_EXTERNO:
            sem_ext_note = ' <span style="font-size:12px;opacity:0.8;">⚠ sem portal externo de licitação</span>'

        portals_html += f"""
        <tr><td style="padding:0 0 12px;">
          <table width="100%" cellpadding="0" cellspacing="0"
                 style="border-radius:6px;overflow:hidden;border:1px solid #dde3ea;">
            <tr style="background:#1a3a5c;">
              <td colspan="5" style="padding:12px 16px;color:#fff;">
                <span style="font-size:15px;font-weight:bold;">📋 {portal}{sem_ext_note}</span>
                <span style="float:right;font-size:13px;opacity:0.85;">
                  {len(items)} processo{'s' if len(items)>1 else ''} &nbsp;·&nbsp; {fmt_valor(total_p) if total_p else '—'}
                </span>
              </td>
            </tr>
            <tr style="background:#f0f4f8;">
              <th style="padding:8px 12px;font-size:11px;color:#888;text-align:left;border-bottom:1px solid #dde;">Órgão/UF · Objeto</th>
              <th style="padding:8px 8px;font-size:11px;color:#888;text-align:left;border-bottom:1px solid #dde;">Tipo</th>
              <th style="padding:8px 8px;font-size:11px;color:#888;text-align:left;border-bottom:1px solid #dde;">Prazo</th>
              <th style="padding:8px 8px;font-size:11px;color:#888;text-align:left;border-bottom:1px solid #dde;">Valor</th>
              <th style="padding:8px 8px;font-size:11px;color:#888;border-bottom:1px solid #dde;"></th>
            </tr>
            {rows}
          </table>
        </td></tr>"""

    # ── Monta HTML completo ────────────────────────────────────────────────────
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#eef1f5;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#eef1f5;padding:24px 0;">
<tr><td align="center">
<table width="720" cellpadding="0" cellspacing="0"
       style="background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,.08);">

  <!-- Header -->
  <tr><td style="background:#0d2137;padding:28px 32px;">
    <h1 style="margin:0;color:#fff;font-size:22px;letter-spacing:.5px;">PNCP Radar · Pneus</h1>
    <p style="margin:6px 0 0;color:#8fb3d4;font-size:14px;">
      Publicados em {yesterday} &nbsp;·&nbsp; {total_proc} processos &nbsp;·&nbsp; {fmt_valor(total_valor)} estimado
    </p>
  </td></tr>

  <!-- Conteúdo -->
  <tr><td style="padding:20px 24px;">
    <table width="100%" cellpadding="0" cellspacing="0">
      {urgency_html}
      {portals_html}
    </table>
  </td></tr>

  <!-- Footer -->
  <tr><td style="background:#f8f9fb;padding:16px 32px;border-top:1px solid #e8ecf0;">
    <p style="margin:0;font-size:11px;color:#aaa;text-align:center;">
      Gerado automaticamente em {run_at} (BRT) &nbsp;·&nbsp;
      <a href="https://pncp.gov.br" style="color:#aaa;">pncp.gov.br</a>
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


# ── EMAIL ──────────────────────────────────────────────────────────────────────

def send_email(html: str, subject: str) -> None:
    gmail_user = os.environ["GMAIL_USER"]
    gmail_pass = os.environ["GMAIL_APP_PASSWORD"]
    email_to   = os.environ.get("EMAIL_TO", gmail_user)

    msg             = MIMEMultipart("alternative")
    msg["Subject"]  = subject
    msg["From"]     = gmail_user
    msg["To"]       = email_to
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.ehlo()
        server.starttls()
        server.login(gmail_user, gmail_pass)
        server.sendmail(gmail_user, email_to, msg.as_string())
        print(f"Email enviado → {email_to}")


# ── MAIN ───────────────────────────────────────────────────────────────────────

def main() -> None:
    yesterday_str = (datetime.now(BRT) - timedelta(days=1)).strftime("%d/%m")

    # 1. Coleta todos os processos abertos
    print("Coletando processos abertos...")
    all_items: list[dict] = []
    for mod in MODALIDADES:
        all_items.extend(collect_all_open(mod))

    print(f"Total abertos: {len(all_items)}")

    # 2. Filtra
    yesterday_items = filter_published_yesterday(all_items)
    expiring_items  = filter_expiring_soon(all_items, days=2)

    # Remove da "urgência" os que já estão em "ontem" (evita duplicata)
    yesterday_ids  = {i["id"] for i in yesterday_items}
    expiring_items = [i for i in expiring_items if i["id"] not in yesterday_ids]

    print(f"Publicados ontem: {len(yesterday_items)}")
    print(f"Vencendo em 2 dias (excl. ontem): {len(expiring_items)}")

    if not yesterday_items and not expiring_items:
        print("Nenhum processo encontrado. Email não enviado.")
        return

    # 3. Enriquece com usuarioNome + valorTotalEstimado
    to_enrich = yesterday_items + expiring_items
    print(f"Buscando detalhes de {len(to_enrich)} processos...")
    enriched  = enrich(to_enrich)

    n = len(yesterday_items)
    yesterday_items = enriched[:n]
    expiring_items  = enriched[n:]

    # 4. Monta e envia
    total_valor = sum(i.get("valorTotalEstimado") or 0 for i in yesterday_items)
    subject     = (
        f"PNCP · pneu · {yesterday_str} · "
        f"{len(yesterday_items)} processos · {fmt_valor(total_valor)}"
    )

    html = build_html(yesterday_items, expiring_items)
    send_email(html, subject)


if __name__ == "__main__":
    main()
