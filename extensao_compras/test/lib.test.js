// node --test extensao_compras/test
const test = require("node:test");
const assert = require("node:assert/strict");
const L = require("../lib.js");

// Mesmo pacote de test_ficha_proposta.py::test_canonico_fixo — checksum calculado pelo Python.
const PACOTE = {
  versao: 1, chave: "33287806000161-2026-40", edital: "CRC (RJ) — 40/2026", encerramento: "23/11/2026",
  hash_ficha: "x", uasg: "791190", numero_compra: "202", ano_compra: "2026", compra_id: "79119006002022026",
  modalidade: "Dispensa", link_compras: "",
  itens: [{ numero_item: "2", qtde: 2, valor_inicial: 3599.0, valor_minimo: 2387.0, marca: "GET", fabricante: "GET", modelo: "PROJ VISION 5 SMART" }],
  checksum: "8504cfbdc0f6e0dbf897e65be98875e57e13170147fc1386d0ad13d4ef96f0f3",
};
const HOJE = new Date(2026, 10, 20);
const copia = (mud = {}) => ({ ...structuredClone(PACOTE), ...mud });

test("checksum JS bate com o do Python (mesmo texto canônico)", async () => {
  assert.equal(L.canonico(PACOTE), "33287806000161-2026-40|791190|202|2026|79119006002022026|23/11/2026\n2|2|3599.00|2387.00|GET|GET|PROJ VISION 5 SMART");
  assert.deepEqual(await L.verificarPacote(PACOTE, HOJE), { ok: true, erros: [] });
});

test("pacote adulterado é recusado", async () => {
  const p = copia();
  p.itens[0].valor_minimo = 238.7; // vírgula no lugar errado
  const v = await L.verificarPacote(p, HOJE);
  assert.equal(v.ok, false);
  assert.match(v.erros.join(), /checksum/);
});

test("pacote expirado é recusado", async () => {
  const v = await L.verificarPacote(PACOTE, new Date(2026, 10, 24));
  assert.match(v.erros.join(), /encerrou/);
});

test("pacote inválido/sem campos é recusado", async () => {
  assert.equal((await L.verificarPacote(null)).ok, false);
  assert.equal((await L.verificarPacote({ versao: 2 })).ok, false);
  assert.equal((await L.verificarPacote(copia({ itens: [] }), HOJE)).ok, false);
});

test("mínimo acima do inicial é recusado mesmo com checksum refeito", async () => {
  const p = copia();
  p.itens[0].valor_minimo = 4000;
  p.checksum = await L.sha256Hex(L.canonico(p));
  assert.match((await L.verificarPacote(p, HOJE)).erros.join(), /acima do inicial/);
});

test("parseBRL / formatarBRL", () => {
  assert.equal(L.parseBRL("R$ 3.599,00"), 3599);
  assert.equal(L.parseBRL("3.599,00"), 3599);
  assert.equal(L.parseBRL("1,2,3"), null);
  assert.equal(L.parseBRL(""), null);
  assert.equal(L.formatarBRL(3599), "3.599,00");
  assert.equal(L.formatarBRL(1234567.5), "1.234.567,50");
  assert.equal(L.formatarBRL(0.1), "0,10");
  for (const v of [0.01, 9.99, 2387, 1234567.89]) assert.equal(L.parseBRL(L.formatarBRL(v)), v);
});

test("identificarPagina: id na URL, UASG+número no texto, ou recusa", () => {
  assert.equal(L.identificarPagina(PACOTE, "https://x/proposta?compra=79119006002022026", "").ok, true);
  assert.equal(L.identificarPagina(PACOTE, "https://x", "UASG 791190 - Dispensa Eletrônica Nº 00202/2026").ok, true);
  assert.equal(L.identificarPagina(PACOTE, "https://x", "UASG 791190 - Dispensa Nº 00203/2026").ok, false);
  assert.equal(L.identificarPagina(PACOTE, "https://x", "UASG 791191 - Dispensa Nº 202/2026").ok, false);
  assert.equal(L.identificarPagina(PACOTE, "https://x", "Dispensa Nº 202/2026 (UASG 1791190)").ok, false);
});

test("campoDoRotulo", () => {
  assert.equal(L.campoDoRotulo("Valor unitário (R$)"), "valor_inicial");
  assert.equal(L.campoDoRotulo("Valor final mínimo"), "valor_minimo");
  assert.equal(L.campoDoRotulo("Valor mínimo"), "valor_minimo");
  assert.equal(L.campoDoRotulo("Marca"), "marca");
  assert.equal(L.campoDoRotulo("Fabricante"), "fabricante");
  assert.equal(L.campoDoRotulo("Modelo / Versão"), "modelo");
  assert.equal(L.campoDoRotulo("Descrição detalhada do objeto ofertado pelo fornecedor com marca e modelo conforme edital"), null);
  assert.equal(L.campoDoRotulo("Quantidade"), null);
});

test("itemUnico só aceita texto com um nº de item", () => {
  assert.equal(L.itemUnico("Item 3 - Projetor"), "3");
  assert.equal(L.itemUnico("Item nº 03"), "3");
  assert.equal(L.itemUnico("Item 3 ... Item 4"), null);
  assert.equal(L.itemUnico("sem item"), null);
});

test("planejar: preenche o que achou, avisa valor mínimo ausente, recusa campo ambíguo", () => {
  const tela = [
    { item: "2", campo: "valor_inicial", ref: 0 },
    { item: "2", campo: "marca", ref: 1 },
    { item: "2", campo: "modelo", ref: 2 },
    { item: "2", campo: "modelo", ref: 3 }, // duplicado -> não preenche
    { item: "9", campo: "valor_inicial", ref: 4 }, // item fora da ficha -> ignora
  ];
  const { plano, avisos } = L.planejar(PACOTE, tela);
  assert.deepEqual(plano.map((p) => `${p.campo}=${p.valor}`), ["valor_inicial=3.599,00", "marca=GET"]);
  assert.match(avisos.join("|"), /VALOR MÍNIMO não achado/);
  assert.match(avisos.join("|"), /2 campos "modelo"/);
});

test("planejar avisa item da ficha que não está na tela", () => {
  assert.match(L.planejar(PACOTE, []).avisos.join(), /item 2 da ficha não apareceu/);
});

test("conferir leitura de volta", () => {
  assert.equal(L.conferir({ numero: 2387, valor: "2.387,00" }, "R$ 2.387,00"), true);
  assert.equal(L.conferir({ numero: 2387, valor: "2.387,00" }, "238,70"), false);
  assert.equal(L.conferir({ numero: null, valor: "GET" }, " get "), true);
  assert.equal(L.conferir({ numero: null, valor: "GET" }, ""), false);
});

test("fmtQtde igual ao Python", () => {
  assert.deepEqual([2, 2.5, 1e6, 100, 0.25].map(L.fmtQtde), ["2", "2.5", "1000000", "100", "0.25"]);
});

test("rótulo com total/global/desconto/estimado/referência nunca é campo", () => {
  for (const r of ["Valor total", "Valor total do item", "Valor global", "Valor mínimo total", "Percentual de desconto",
    "Valor unitário estimado", "Valor de referência", "Quantidade", "Valor do item"]) {
    assert.equal(L.campoDoRotulo(r), null, r);
  }
});

test("identificarPagina recusa página com várias compras (lista)", () => {
  const t = "UASG 791190 Dispensa Nº 00202/2026 ... Dispensa Nº 00305/2026";
  const r = L.identificarPagina(PACOTE, "https://x/?compra=79119006002022026", t);
  assert.equal(r.ok, false);
  assert.match(r.como, /2 compras/);
});

test("travasDaPagina: maior desconto e lance por valor total com qtde > 1", () => {
  assert.match(L.travasDaPagina(PACOTE, "Critério de julgamento: Maior desconto").join(), /DESCONTO/);
  assert.match(L.travasDaPagina(PACOTE, "Forma de envio de lances: valor total do item").join(), /TOTAL/);
  assert.deepEqual(L.travasDaPagina(PACOTE, "Critério: menor preço. Lances por valor unitário"), []);
  const um = { ...PACOTE, itens: [{ ...PACOTE.itens[0], qtde: 1 }] };
  assert.deepEqual(L.travasDaPagina(um, "Lances por valor total"), []); // qtde 1: total = unitário
});

test("pacote com qtde inválida é recusado", async () => {
  const p = copia();
  p.itens[0].qtde = 0;
  p.checksum = await L.sha256Hex(L.canonico(p));
  assert.match((await L.verificarPacote(p, HOJE)).erros.join(), /qtde/);
});
