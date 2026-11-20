"use strict";
const L = window.CompraLib;
const $ = (id) => document.getElementById(id);
let pacote = null;
let pacoteOk = false;

function esc(s) {
  return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

function atualizarBotoes() {
  $("simular").disabled = !pacoteOk;
  $("preencher").disabled = !(pacoteOk && $("conferi").checked);
}

async function carregarPacote(p) {
  pacote = p;
  const v = await L.verificarPacote(p);
  pacoteOk = v.ok;
  if (v.ok) {
    const linhas = p.itens.map((it) => `<tr><td>${esc(it.numero_item)}</td><td>R$ ${L.formatarBRL(it.valor_inicial)}</td>
      <td><b>R$ ${L.formatarBRL(it.valor_minimo)}</b></td><td>${esc(it.marca)} / ${esc(it.modelo)}</td></tr>`).join("");
    $("statusPacote").innerHTML = `<p class="ok">✅ ${esc(p.edital)}<br>UASG ${esc(p.uasg)} · compra ${esc(p.numero_compra)}/${esc(p.ano_compra)} · encerra ${esc(p.encerramento)}</p>
      <table><tr><th>Item</th><th>Inicial</th><th>Mínimo</th><th>Marca / Modelo</th></tr>${linhas}</table>`;
  } else {
    $("statusPacote").innerHTML = `<p class="erro">⛔ Pacote recusado:<br>${v.erros.map(esc).join("<br>")}</p>`;
  }
  atualizarBotoes();
}

$("arquivo").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  try {
    const p = JSON.parse(await f.text());
    await chrome.storage.local.set({ pacote: p });
    await carregarPacote(p);
  } catch (err) {
    pacoteOk = false;
    $("statusPacote").innerHTML = `<p class="erro">⛔ arquivo inválido: ${esc(err.message)}</p>`;
    atualizarBotoes();
  }
});

$("conferi").addEventListener("change", atualizarBotoes);

const HOSTS = [/^cnetmobile\.estaleiro\.serpro\.gov\.br$/, /(^|\.)compras\.gov\.br$/, /^www\.comprasnet\.gov\.br$/];

async function rodar(acao) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  let host = "";
  try { host = new URL(tab.url).hostname; } catch (_) { /* aba sem URL legível */ }
  if (!HOSTS.some((re) => re.test(host))) {
    $("saida").innerHTML = `<p class="erro">⛔ Aba atual (${esc(host || "?")}) não é do Compras.gov.br — não rodo aqui.</p>`;
    return;
  }
  $("saida").innerHTML = "<p>…</p>";
  try {
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["lib.js", "content.js"] });
    const r = await chrome.tabs.sendMessage(tab.id, { acao, pacote, sobrescrever: $("sobrescrever").checked });
    mostrar(acao, r);
  } catch (err) {
    $("saida").innerHTML = `<p class="erro">⛔ ${esc(err.message)} — a aba é do Compras.gov.br?</p>`;
  }
}

function mostrar(acao, r) {
  if (!r) { $("saida").innerHTML = `<p class="erro">⛔ Sem resposta da página — recarregue a aba e tente de novo.</p>`; return; }
  let h = "";
  if (r.pagina) h += `<p class="${r.pagina.ok ? "ok" : "erro"}">${r.pagina.ok ? "✅" : "⛔"} Página: ${esc(r.pagina.como)}</p>`;
  if (!r.ok) h += `<p class="erro">⛔ ${esc(r.erro)}</p>`;
  if (r.resultado) {
    const div = r.resultado.filter((x) => x.status !== "OK").length;
    h += `<p class="${div ? "erro" : "ok"}">${div ? `⚠️ ${div} campo(s) com problema — corrija à mão` : "✅ Tudo conferido na tela"}. Agora: revise, salve e envie você mesmo.</p>`;
    h += "<table><tr><th>Item</th><th>Campo</th><th>Status</th><th>Na tela</th></tr>" + r.resultado.map((x) =>
      `<tr><td>${esc(x.item)}</td><td>${esc(x.campo)}</td><td class="${x.status === "OK" ? "ok" : "erro"}">${esc(x.status)}</td><td>${esc(x.naTela ?? x.detalhe)}</td></tr>`).join("") + "</table>";
  }
  if (r.plano) {
    h += `<p>Simulação: ${r.plano.length} campo(s) seriam preenchidos.</p><table><tr><th>Item</th><th>Campo</th><th>Valor</th></tr>` +
      r.plano.map((x) => `<tr><td>${esc(x.item)}</td><td>${esc(x.campo)}</td><td>${esc(x.valor)}</td></tr>`).join("") + "</table>";
  }
  for (const a of r.avisos || []) h += `<p class="aviso">⚠️ ${esc(a)}</p>`;
  if (acao === "diagnosticar" || !r.ok) {
    h += `<p>${r.camposAchados?.length || 0} campo(s) reconhecidos, ${r.camposSemItem?.length || 0} sem item. Copie e mande pro Claude se algo não bateu:</p>
      <button id="copiar">Copiar diagnóstico</button><pre id="diag">${esc(JSON.stringify(r, null, 1))}</pre>`;
  }
  $("saida").innerHTML = h;
  const btn = $("copiar");
  if (btn) btn.addEventListener("click", () => navigator.clipboard.writeText($("diag").textContent));
}

$("diagnosticar").addEventListener("click", () => rodar("diagnosticar"));
$("simular").addEventListener("click", () => rodar("simular"));
$("preencher").addEventListener("click", () => rodar("preencher"));

chrome.storage.local.get("pacote").then(({ pacote: p }) => p && carregarPacote(p));
