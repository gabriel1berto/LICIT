/* lib.js — funções puras da extensão (sem DOM), usadas pelo popup, pelo content script e
 * pelos testes (node --test). Regra de negócio: CLAUDE.md §19. Pacote gerado por
 * cotacao_informatica/ficha_proposta.py --exportar (mesmo texto canônico de canonico_pacote()).
 */
(function (root) {
  "use strict";

  // Rótulo com essas palavras NUNCA é preenchido: o pacote só tem valor unitário em R$.
  const ROTULO_PROIBIDO = /total|global|desconto|percentual|%|estimad|refer[eê]ncia|quantidade/i;

  const CAMPOS = ["valor_inicial", "valor_minimo", "marca", "fabricante", "modelo"];

  // Rótulo da tela -> campo do pacote. Ordem importa: "valor mínimo" antes de "valor".
  const ROTULOS = [
    ["valor_minimo", /valor\s+(final\s+)?m[ií]nimo|lance\s+m[ií]nimo|m[ií]nimo\s+aceit/i],
    ["valor_inicial", /valor\s+(unit[aá]rio|da\s+proposta|ofertado)|pre[cç]o\s+unit[aá]rio/i],
    ["fabricante", /fabricante/i],
    ["marca", /\bmarca\b/i],
    ["modelo", /\bmodelo\b|\bvers[aã]o\b/i],
  ];

  function parseBRL(txt) {
    if (txt === null || txt === undefined) return null;
    let s = String(txt).replace(/[R$\s ]/g, "");
    if (!s || !/^[\d.,]+$/.test(s)) return null;
    if (s.includes(",")) {
      if ((s.match(/,/g) || []).length > 1) return null;
      s = s.replace(/\./g, "").replace(",", ".");
    } else if ((s.match(/\./g) || []).length > 1 || /^\d{1,3}(\.\d{3})+$/.test(s)) {
      s = s.replace(/\./g, "");
    }
    const v = Number(s);
    return Number.isFinite(v) ? v : null;
  }

  function formatarBRL(v) {
    // 3599 -> "3.599,00" (formato que os campos com máscara do Compras.gov.br esperam)
    const [int, dec] = Number(v).toFixed(2).split(".");
    return int.replace(/\B(?=(\d{3})+(?!\d))/g, ".") + "," + dec;
  }

  function mesmoValor(a, b) {
    return a !== null && b !== null && Math.abs(a - b) < 0.005;
  }

  function parseData(txt) {
    const m = /(\d{2})\/(\d{2})\/(\d{4})/.exec(String(txt || ""));
    if (!m) return null;
    const d = new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1]));
    return d.getDate() === Number(m[1]) ? d : null;
  }

  function fmtQtde(q) {
    // igual ao fmt_qtde() do Python: 2 -> "2", 2.5 -> "2.5", sem notação científica
    return Number(q).toFixed(4).replace(/\.?0+$/, "");
  }

  function canonico(p) {
    const linhas = [[p.chave, p.uasg, p.numero_compra, p.ano_compra, p.compra_id, p.encerramento].join("|")];
    for (const it of p.itens) {
      linhas.push([it.numero_item, fmtQtde(it.qtde), Number(it.valor_inicial).toFixed(2), Number(it.valor_minimo).toFixed(2),
        it.marca, it.fabricante, it.modelo].join("|"));
    }
    return linhas.join("\n");
  }

  async function sha256Hex(texto) {
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(texto));
    return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, "0")).join("");
  }

  /** Trava de entrada: pacote íntegro, consistente e não expirado. Retorna {ok, erros[]}. */
  async function verificarPacote(p, hoje = new Date()) {
    const erros = [];
    if (!p || p.versao !== 1) return { ok: false, erros: ["pacote inválido ou de versão desconhecida"] };
    for (const k of ["chave", "uasg", "numero_compra", "ano_compra", "compra_id", "encerramento", "checksum"]) {
      if (!p[k]) erros.push(`campo ausente: ${k}`);
    }
    if (!Array.isArray(p.itens) || !p.itens.length) erros.push("pacote sem itens");
    if (erros.length) return { ok: false, erros };
    if ((await sha256Hex(canonico(p))) !== p.checksum) {
      erros.push("checksum não bate — pacote editado depois de exportado. Gere de novo com --exportar");
    }
    const enc = parseData(p.encerramento);
    const dia = new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate());
    if (!enc) erros.push("data de encerramento ilegível");
    else if (enc < dia) erros.push(`edital encerrou em ${p.encerramento}`);
    const vistos = new Set();
    for (const it of p.itens) {
      if (vistos.has(it.numero_item)) erros.push(`item ${it.numero_item} duplicado`);
      vistos.add(it.numero_item);
      if (!(it.qtde > 0)) erros.push(`item ${it.numero_item}: qtde inválida`);
      if (!(it.valor_minimo > 0)) erros.push(`item ${it.numero_item}: valor mínimo inválido`);
      if (!(it.valor_inicial >= it.valor_minimo)) erros.push(`item ${it.numero_item}: valor mínimo acima do inicial`);
      for (const c of ["marca", "fabricante", "modelo"]) if (!String(it[c] || "").trim()) erros.push(`item ${it.numero_item}: ${c} vazio`);
    }
    return { ok: erros.length === 0, erros };
  }

  /** A página aberta é desta compra? URL com o id da compra = forte; UASG + nº/ano no texto = ok. */
  function identificarPagina(p, url, texto) {
    const t = String(texto || "").replace(/\s+/g, " ");
    const compras = new Set();
    const reCompra = /(dispensa|preg[aã]o|compra)[^\d]{0,40}?(\d{1,5})\s*\/\s*(\d{4})/gi;
    let m;
    while ((m = reCompra.exec(t))) compras.add(`${Number(m[2])}/${m[3]}`);
    if (compras.size > 1) return { ok: false, como: `página cita ${compras.size} compras (${[...compras].slice(0, 4).join(", ")}) — abra a tela de UMA compra` };
    if (String(url || "").includes(p.compra_id)) return { ok: true, como: "id da compra na URL" };
    const temUasg = new RegExp(`\\b${p.uasg}\\b`).test(t);
    const num = String(Number(p.numero_compra));
    const temNumero = new RegExp(`\\b0*${num}\\s*/\\s*${p.ano_compra}\\b`).test(t);
    if (temUasg && temNumero) return { ok: true, como: "UASG e nº da compra no texto da página" };
    return { ok: false, como: `página não é da UASG ${p.uasg} compra ${num}/${p.ano_compra} — não preencho` };
  }

  /** Travas pelo texto da página: critério/forma de lance incompatível com valor unitário em R$. */
  function travasDaPagina(p, texto) {
    const t = String(texto || "").replace(/\s+/g, " ");
    const erros = [];
    if (/maior\s+(percentual\s+de\s+)?desconto/i.test(t)) erros.push("critério MAIOR DESCONTO — pacote tem valor em R$, não %. Preencha à mão");
    const qtdeMaiorQue1 = p.itens.some((it) => Number(it.qtde) !== 1);
    if (qtdeMaiorQue1 && /lances?[^.]{0,60}valor\s+(total|global)|valor\s+global|menor\s+pre[cç]o\s+global/i.test(t)) {
      erros.push("lance por VALOR TOTAL/GLOBAL e item com qtde > 1 — pacote é unitário. Preencha à mão");
    }
    return erros;
  }

  function campoDoRotulo(texto) {
    const t = String(texto || "").trim();
    if (!t || t.length > 60 || ROTULO_PROIBIDO.test(t)) return null;
    for (const [campo, re] of ROTULOS) if (re.test(t)) return campo;
    return null;
  }

  /** Nº do item num trecho de texto, só se houver exatamente um ("Item 3", "Item: 3", "Item nº 3"). */
  function itemUnico(texto) {
    const nums = new Set();
    const re = /\bitem\s*(?:n[º°o.]*\s*)?:?\s*(\d{1,4})\b/gi;
    let m;
    while ((m = re.exec(String(texto || "")))) nums.add(String(Number(m[1])));
    return nums.size === 1 ? [...nums][0] : null;
  }

  /** Plano de preenchimento: cruza campos achados na tela com o pacote. Nada é escrito aqui. */
  function planejar(p, camposTela) {
    const porItem = new Map(p.itens.map((it) => [String(Number(it.numero_item)), it]));
    const plano = [], avisos = [];
    const achados = new Map();
    for (const c of camposTela) {
      const it = porItem.get(c.item);
      if (!it) continue;
      const k = `${c.item}|${c.campo}`;
      if (achados.has(k)) { avisos.push(`item ${c.item}: 2 campos "${c.campo}" na tela — não preencho esse campo`); achados.set(k, null); continue; }
      achados.set(k, c);
    }
    for (const [num, it] of porItem) {
      for (const campo of CAMPOS) {
        const c = achados.get(`${num}|${campo}`);
        if (c === null) continue;
        if (!c) {
          // A tela de proposta da dispensa no Compras.gov.br NÃO tem valor mínimo (vista 20/nov/2026):
          // o piso do robô é configurado em outro momento — lembrar o usuário, não é erro de mapeamento.
          if (campo === "valor_minimo") avisos.push(`item ${num}: sem campo de valor mínimo nesta tela — configure o piso R$ ${formatarBRL(it.valor_minimo)} onde o sistema pedir (sala de disputa)`);
          else if (campo !== "fabricante") avisos.push(`item ${num}: campo ${campo} não achado`);
          continue;
        }
        const valor = campo.startsWith("valor") ? formatarBRL(it[campo]) : String(it[campo]);
        plano.push({ item: num, campo, ref: c.ref, valor, numero: campo.startsWith("valor") ? it[campo] : null });
      }
    }
    const naTela = new Set(camposTela.map((c) => c.item));
    for (const num of porItem.keys()) if (!naTela.has(num)) avisos.push(`item ${num} da ficha não apareceu na tela`);
    return { plano, avisos };
  }

  /** Confere o que ficou escrito na tela contra o plano (leitura de volta). */
  function conferir(planoItem, valorNaTela) {
    if (planoItem.numero !== null) return mesmoValor(parseBRL(valorNaTela), planoItem.numero);
    return String(valorNaTela || "").trim().toUpperCase() === String(planoItem.valor).trim().toUpperCase();
  }

  const L = { CAMPOS, parseBRL, formatarBRL, mesmoValor, parseData, fmtQtde, canonico, sha256Hex, verificarPacote,
    identificarPagina, travasDaPagina, campoDoRotulo, itemUnico, planejar, conferir };
  if (typeof module !== "undefined" && module.exports) module.exports = L;
  else root.CompraLib = L;
})(typeof self !== "undefined" ? self : this);
