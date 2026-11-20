/* sondar_compras.js — snippet de console (DevTools ou Claude in Chrome) pra testar o CAMINHO até a tela
 * "Cadastrar propostas" de várias dispensas, sem aceitar termo e sem preencher nada.
 * Uso: abrir https://cnetmobile.estaleiro.serpro.gov.br/comprasnet-web/seguro/fornecedor/compras (logado,
 * entrando pelo menu Compras → "Licitação e Dispensa (novo)" — link direto dá "acesso não autorizado"),
 * colar este arquivo no console e rodar:  await sondar('765704', '223/2026')
 * Retorna: chegou na tela?, prazo, nº de itens (página atual, 10 por página), se pede declaração ME/EPP,
 * critério e avisos de bloqueio. Só busca e navega — nunca marca termo nem clica em Salvar.
 * Validado 20/nov/2026 em 10 dispensas reais; favoritar() em 37 compras (CLAUDE.md §19).
 * Rodar em lotes de ~3 por chamada: o console/CDP corta execução longa (~45 s).
 */
/** Preenche "Número da compra" (máscara 5 dígitos + ano: 262/2026 → 002622026 — a busca pagina de 10 em
 *  10 e em UASG grande o edital some), pesquisa e devolve o card da compra (ou null). */
async function buscarCard(uasg, num) {
  const dorme = (ms) => new Promise((r) => setTimeout(r, ms));
  const ln = [...document.querySelectorAll("label")].find((x) => /Número da compra/.test(x.innerText));
  const cn = ln && ln.parentElement.querySelector("input");
  if (cn) {
    const [n, ano] = num.split("/");
    cn.focus();
    cn.value = n.padStart(5, "0") + ano;
    cn.dispatchEvent(new Event("input", { bubbles: true }));
    cn.dispatchEvent(new Event("change", { bubbles: true }));
  }
  [...document.querySelectorAll("button")].find((b) => b.innerText.trim() === "Pesquisar").click();
  for (let i = 0; i < 24; i++) { // até 6 s — a 1ª busca às vezes demora
    await dorme(250);
    const card = [...document.querySelectorAll("app-card-compra, app-card-item-compra, [class*=card]")]
      .find((c) => new RegExp(`N° ${num}\\b`).test(c.innerText) && c.innerText.includes(uasg) && c.querySelector("button"));
    if (card) return card;
  }
  return null;
}

/** Marca o coração ("Adicionar aos favoritos") da compra. Favoritos aparecem no app Compras.gov.br,
 *  não na web. Não registra participação. Uso: await favoritar('160089', '140/2026') */
async function favoritar(uasg, num) {
  const dorme = (ms) => new Promise((r) => setTimeout(r, ms));
  const aba = [...document.querySelectorAll("[role=tab]")].find((e) => /Todas as compras/.test(e.innerText));
  if (!aba) return { uasg, num, st: "sem aba Todas as compras" };
  aba.click();
  await dorme(700);
  const l = [...document.querySelectorAll("label")].find((x) => /Unidade compradora/.test(x.innerText));
  const campo = l && l.parentElement.querySelector("input");
  campo.focus();
  campo.value = uasg;
  campo.dispatchEvent(new Event("input", { bubbles: true }));
  campo.dispatchEvent(new Event("change", { bubbles: true }));
  const card = await buscarCard(uasg, num);
  const fav = card && card.querySelector('button[aria-label*="favoritos"]');
  if (!fav) return { uasg, num, st: "não achou na busca" };
  if (/Remover/.test(fav.getAttribute("aria-label"))) return { uasg, num, st: "já era favorito" };
  fav.click();
  await dorme(1200);
  return { uasg, num, st: /Remover/.test(fav.getAttribute("aria-label")) ? "FAVORITADO" : "cliquei, sem confirmação" };
}

async function sondar(uasg, num) {
  const dorme = (ms) => new Promise((r) => setTimeout(r, ms));
  const esperar = async (fn, t = 10000) => {
    for (let i = 0; i < t / 250; i++) { const v = fn(); if (v) return v; await dorme(250); }
    return null;
  };
  if (!location.pathname.endsWith("/seguro/fornecedor/compras")) { history.back(); await dorme(3000); }
  const aba = await esperar(() => [...document.querySelectorAll("[role=tab]")].find((e) => /Todas as compras/.test(e.innerText)));
  if (!aba) return { uasg, num, erro: "sem aba Todas as compras", url: location.pathname };
  aba.click();
  await dorme(800);
  const campo = await esperar(() => {
    const l = [...document.querySelectorAll("label")].find((x) => /Unidade compradora/.test(x.innerText));
    return l && l.parentElement.querySelector("input");
  });
  campo.focus();
  campo.value = uasg;
  campo.dispatchEvent(new Event("input", { bubbles: true }));
  campo.dispatchEvent(new Event("change", { bubbles: true }));
  const card = await buscarCard(uasg, num);
  if (!card) return { uasg, num, erro: "compra não apareceu na busca" };
  const btn = [...card.querySelectorAll("button")].find((b) => /Acompanhar|Participar/i.test(b.getAttribute("aria-label") || b.title || b.innerText));
  if (!btn) return { uasg, num, erro: "sem botão acompanhar" };
  btn.click();
  const ok = await esperar(() => location.pathname.includes("cadastro-propostas") && document.querySelectorAll("app-identificacao-item").length);
  const T = document.body.innerText;
  return {
    uasg, num, chegou: !!ok,
    titulo: (T.match(/Dispensa Eletrônica N° [\d/]+/) || [""])[0],
    limite: (T.match(/Data limite de entrega de propostas: [^\n]*/) || [""])[0].slice(-16),
    termo: /Termo de Aceitação/.test(T),
    meepp: /Declaro, sob as penas da Lei, que não ultrapassei/.test(T),
    itens_pagina: document.querySelectorAll("app-identificacao-item").length,
    criterio: [...new Set([...document.querySelectorAll("[data-test=criterio-julgamento-item]")].map((e) => e.innerText.trim()))],
    avisos: (T.match(/[^\n]*(não é possível|não possui|bloquead|impedid|encerrad|suspens|desconto|valor total|global)[^\n]*/gi) || []).slice(0, 4),
  };
}
