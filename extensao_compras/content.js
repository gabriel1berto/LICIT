/* content.js — roda SÓ quando você clica na extensão (injeção sob demanda, activeTab).
 * Ações: diagnosticar (só lê), simular (só lê), preencher (escreve nos campos e confere).
 * NUNCA clica em Salvar/Enviar/Confirmar: não existe código de clique aqui. Quem salva e
 * envia a proposta é você (CLAUDE.md §19).
 */
(function () {
  "use strict";
  const L = window.CompraLib;
  // Reinjeção (ex.: extensão recarregada): troca o ouvinte antigo pelo novo em vez de sair cedo.
  if (window.__compraOuvinte) {
    try { chrome.runtime.onMessage.removeListener(window.__compraOuvinte); } catch (_) { /* contexto antigo morto */ }
  }

  const VISIVEL = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const EDITAVEL = (el) => el && el.matches("input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=button]):not([type=submit]), textarea")
    && !el.disabled && !el.readOnly && VISIVEL(el);

  function textoProprio(el) {
    return Array.from(el.childNodes).filter((n) => n.nodeType === 3).map((n) => n.textContent).join(" ").trim()
      || (el.children.length === 0 ? el.textContent.trim() : "");
  }

  function seletor(el) {
    if (el.id) return `#${CSS.escape(el.id)}`;
    const partes = [];
    for (let e = el; e && e.nodeType === 1 && partes.length < 6; e = e.parentElement) {
      let s = e.tagName.toLowerCase();
      if (e.getAttribute("formcontrolname")) s += `[formcontrolname="${e.getAttribute("formcontrolname")}"]`;
      else if (e.parentElement) s += `:nth-of-type(${Array.from(e.parentElement.children).filter((x) => x.tagName === e.tagName).indexOf(e) + 1})`;
      partes.unshift(s);
    }
    return partes.join(" > ");
  }

  /** Input ligado a um rótulo, só por vínculo forte: label[for], input dentro do próprio rótulo, ou
   *  ÚNICO campo do bloco imediato do rótulo (até 2 níveis acima), vindo depois dele. Sem vínculo
   *  forte → null (vira aviso, nunca chute: campo trocado é o pior erro possível aqui). */
  function inputDoRotulo(rot) {
    if (rot.tagName === "LABEL" && rot.htmlFor) {
      const alvo = document.getElementById(rot.htmlFor);
      return EDITAVEL(alvo) ? alvo : null;
    }
    const dentro = rot.querySelector && rot.querySelector("input, textarea");
    if (EDITAVEL(dentro)) return dentro;
    for (let bloco = rot.parentElement, n = 0; bloco && n < 2; bloco = bloco.parentElement, n++) {
      const todos = Array.from(bloco.querySelectorAll("input, textarea, select")).filter(VISIVEL);
      if (todos.length > 1) return null; // bloco com mais de um campo: ambíguo
      if (todos.length === 1) {
        const el = todos[0];
        const depois = rot.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING;
        return EDITAVEL(el) && depois ? el : null;
      }
    }
    return null;
  }

  /** Nº do item do campo: menor ancestral que contém exatamente UM componente
   *  <app-identificacao-item> do Compras.gov.br (texto "1 PROJETOR MULTIMÍDIA", sem a palavra
   *  "Item" — visto na tela real cadastro-propostas, 20/nov/2026); fallback: texto com um único "Item N". */
  function itemDoCampo(el) {
    for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
      const ids = a.querySelectorAll("app-identificacao-item");
      if (ids.length > 1) return null; // bloco com mais de um item: ambíguo
      if (ids.length === 1) {
        const m = /^\s*(\d{1,4})\b/.exec(ids[0].innerText || "");
        return m ? String(Number(m[1])) : null;
      }
      const n = L.itemUnico(a.innerText || "");
      if (n) return n;
      if ((a.innerText || "").length > 20000) break;
    }
    return null;
  }

  // Identificadores estáveis da tela real cadastro-propostas (Compras.gov.br, vistos em 20/nov/2026).
  // "Marca/Fabricante" é UM campo só: recebe a marca (o pacote usa fabricante = marca).
  const DATA_TEST = {
    "input-valor-proposta": "valor_inicial",
    "input-marca-fabricante": "marca",
    "input-modelo-versao": "modelo",
  };

  function mapearCampos() {
    const refs = [], campos = [], semItem = [];
    const usados = new Set();
    // 1º: data-test (mais confiável que rótulo)
    for (const [dt, campo] of Object.entries(DATA_TEST)) {
      for (const input of document.querySelectorAll(`[data-test="${dt}"]`)) {
        if (!EDITAVEL(input)) continue;
        usados.add(input);
        const item = itemDoCampo(input);
        const info = { campo, rotulo: `(data-test ${dt})`, seletor: seletor(input), valorAtual: input.value };
        if (!item) { semItem.push(info); continue; }
        refs.push(input);
        campos.push({ ...info, item, ref: refs.length - 1 });
      }
    }
    // 2º: rótulo visível
    for (const el of document.querySelectorAll("label, span, div, td, th, p, mat-label, strong, b")) {
      if (!VISIVEL(el)) continue;
      const rotulo = textoProprio(el) || el.getAttribute("aria-label") || "";
      const campo = L.campoDoRotulo(rotulo);
      if (!campo) continue;
      const input = inputDoRotulo(el);
      if (!input || usados.has(input)) continue;
      usados.add(input);
      const item = itemDoCampo(input);
      const info = { campo, rotulo: rotulo.slice(0, 60), seletor: seletor(input), valorAtual: input.value };
      if (!item) { semItem.push(info); continue; }
      refs.push(input);
      campos.push({ ...info, item, ref: refs.length - 1 });
    }
    // placeholder / aria-label direto no input (campo sem rótulo visível)
    for (const input of document.querySelectorAll("input, textarea")) {
      if (usados.has(input) || !EDITAVEL(input)) continue;
      const campo = L.campoDoRotulo(input.getAttribute("placeholder") || input.getAttribute("aria-label") || "");
      const item = campo && itemDoCampo(input);
      if (!item) continue;
      usados.add(input);
      refs.push(input);
      campos.push({ campo, item, rotulo: "(placeholder)", seletor: seletor(input), valorAtual: input.value, ref: refs.length - 1 });
    }
    return { refs, campos, semItem };
  }

  // Setter nativo + eventos (Angular/React ouvem "input").
  function escreverSetter(input, valor) {
    const proto = input.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(input, valor);
    for (const ev of ["input", "change", "blur"]) input.dispatchEvent(new Event(ev, { bubbles: true }));
    return "setter";
  }

  function escrever(input, valor) {
    input.focus();
    input.select && input.select();
    // 1º: digitação "de verdade" (dispara beforeinput/input — funciona com máscara de moeda)
    if (document.execCommand("insertText", false, valor) && input.value !== "") {
      input.dispatchEvent(new Event("change", { bubbles: true }));
      input.dispatchEvent(new Event("blur", { bubbles: true }));
      return "digitado";
    }
    return escreverSetter(input, valor);
  }

  function marcar(input, ok) {
    input.style.outline = ok ? "3px solid #1a7f37" : "3px solid #cf222e";
    input.style.outlineOffset = "1px";
  }

  function identificar(pacote) {
    return L.identificarPagina(pacote, location.href, document.body.innerText);
  }

  async function executar(msg) {
    const pagina = msg.pacote ? identificar(msg.pacote) : null;
    const { refs, campos, semItem } = mapearCampos();
    const base = { url: location.href.split("?")[0], iframes: document.querySelectorAll("iframe").length,
      pagina, camposAchados: campos.map(({ ref, ...c }) => c), camposSemItem: semItem };

    if (msg.acao === "diagnosticar") return { ok: true, ...base };

    const ver = await L.verificarPacote(msg.pacote);
    if (!ver.ok) return { ok: false, erro: "pacote recusado: " + ver.erros.join("; "), ...base };
    if (!pagina.ok) return { ok: false, erro: pagina.como, ...base };
    const { plano, avisos } = L.planejar(msg.pacote, campos);
    const travas = L.travasDaPagina(msg.pacote, document.body.innerText);
    if (travas.length) return { ok: false, erro: travas.join("; "), ...base };
    if (msg.acao === "simular") return { ok: true, plano: plano.map(({ ref, ...p }) => p), avisos, ...base };

    if (msg.acao !== "preencher") return { ok: false, erro: "ação desconhecida" };
    const resultado = [];
    for (const p of plano) {
      const input = refs[p.ref];
      const antes = input.value;
      if (antes && !L.conferir(p, antes) && !msg.sobrescrever) {
        resultado.push({ item: p.item, campo: p.campo, status: "PULADO", detalhe: `já tinha "${antes}" (marque sobrescrever)` });
        marcar(input, false);
        continue;
      }
      let como = "já estava certo";
      if (!L.conferir(p, antes)) como = escrever(input, p.valor);
      await new Promise((r) => setTimeout(r, 150)); // máscara reformata depois do blur
      let ok = L.conferir(p, input.value);
      if (!ok && como === "digitado") { // máscara não aceitou a digitação: tenta o setter uma vez
        escreverSetter(input, p.valor);
        await new Promise((r) => setTimeout(r, 150));
        ok = L.conferir(p, input.value);
        como += "+setter";
      }
      marcar(input, ok);
      resultado.push({ item: p.item, campo: p.campo, esperado: p.valor, naTela: input.value, status: ok ? "OK" : "DIVERGENTE", como });
    }
    return { ok: true, resultado, avisos, ...base };
  }

  window.__compraOuvinte = (msg, _s, responder) => {
    executar(msg).then(responder).catch((e) => responder({ ok: false, erro: String(e && e.message || e) }));
    return true;
  };
  chrome.runtime.onMessage.addListener(window.__compraOuvinte);
})();
