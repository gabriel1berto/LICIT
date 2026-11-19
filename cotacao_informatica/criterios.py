"""criterios.py — Extrai critérios técnicos do ITEM do edital (descrição do PNCP, padrão CATMAT
ou texto livre do TR) e do PRODUTO do fornecedor (ficha técnica), e compara um contra o outro.

Regra de ouro (CLAUDE.md §6.1: só participar com produto confirmado): na dúvida, nunca
"atende". Cada critério volta como:
  OK    — produto cumpre o que o item pede (com o valor dos dois lados no motivo)
  FALHA — produto descumpre (ex: item pede saída 220V, nobreak é 115V)
  ?     — item pede, mas a ficha do produto não informa → vendedor precisa confirmar
Critério que o item NÃO pede não entra na conta.
"""
import re
import unicodedata


def norm(s) -> str:
    # aspas de polegada em várias grafias (23,8´´, 24”, 21.5″) somem no NFKD — vira " antes
    s = re.sub(r"´´|''|’’|‘‘|[”″“]", '"', str(s or ""))
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s)


def num(s: str) -> float:
    s = s.strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    return float(s)


# --------------------------------------------------------------------------- escopo
# Itens que o filtro do radar classificou como informática, mas que não são produto de
# informática pra cotar (achado 19/nov/2026 ao montar a 1ª planilha de cotação).
FORA_ESCOPO = re.compile(
    r"aspirador|fita impressora|bobina papel|peca / acessorio|filamento|pedestal|apoio punho|"
    r"microfone tipo|tipo: passiva|caixa acustica tipo: passiva|intra auricular|monitor imagem tamanho tela: (4\d|5\d|6\d|7\d)", re.I)


def fora_de_escopo(desc: str) -> str | None:
    m = FORA_ESCOPO.search(norm(desc))
    return f"não é produto de informática pra cotar ('{m.group(0)}')" if m else None


# --------------------------------------------------------------------------- utilidades
def faixa(t: str, rotulo: str):
    """Lê 'rotulo: 23 a 30' / 'superior a 8' / 'até 22' / 'mínimo 4' / '8' do padrão CATMAT.
    Devolve (min, max) com None quando aberto."""
    m = re.search(rotulo + r"\s*:?\s*(superior a|acima de|minimo de|minimo|ate|no minimo|pelo menos)?\s*(\d+(?:[.,]\d+)?)\s*(a\s*(\d+(?:[.,]\d+)?))?\s*(tb|gb)?", t)
    if not m:
        return None
    q, a, b, unid = m.group(1), num(m.group(2)), m.group(4), m.group(5)
    mult = 1000 if unid == "tb" else 1
    a *= mult
    if b:
        return (a, num(b) * mult)
    if q in ("ate",):
        return (None, a)
    if q == "superior a" or q == "acima de":
        return (a + 0.001, None)
    return (a, None)


def dentro(v, fx) -> bool:
    lo, hi = fx
    return (lo is None or v >= lo - 1e-9) and (hi is None or v <= hi + 1e-9)


def fmt_fx(fx) -> str:
    lo, hi = fx
    if lo is not None and hi is not None:
        return f"{lo:g} a {hi:g}"
    return f"≥ {lo:g}" if lo is not None else f"≤ {hi:g}"


class Comparacao:
    def __init__(self):
        self.res: list[tuple[str, str, str]] = []  # (status, criterio, detalhe)

    def add(self, status, crit, det):
        self.res.append((status, crit, det))

    def ok(self, c, d): self.add("OK", c, d)
    def falha(self, c, d): self.add("FALHA", c, d)
    def duvida(self, c, d): self.add("?", c, d)

    excesso = 0.0  # quanto o produto passa do mínimo pedido (desempate: o mais próximo ganha)

    def check_num(self, crit, fx_item, v_prod, unid="", teto_flexivel=False):
        """teto_flexivel: faixa CATMAT tipo 'SSD 110 a 300' / 'RAM 4 a 8' — produto ACIMA do teto é
        especificação superior (costuma ser aceita), então vira '?' a confirmar no TR, não FALHA.
        Abaixo do mínimo é sempre FALHA."""
        if fx_item is None:
            return
        lo, hi = fx_item
        if v_prod is None:
            self.duvida(crit, f"item pede {fmt_fx(fx_item)}{unid}; ficha não informa")
        elif dentro(v_prod, fx_item):
            if lo:
                self.excesso += (v_prod - lo) / lo
            self.ok(crit, f"pede {fmt_fx(fx_item)}{unid}, produto {v_prod:g}{unid}")
        elif teto_flexivel and hi is not None and v_prod > hi and (lo is None or v_prod >= lo):
            self.excesso += 1.0
            self.duvida(crit, f"pede {fmt_fx(fx_item)}{unid}, produto {v_prod:g}{unid} — ACIMA da faixa (superior; confirmar se o TR aceita)")
        else:
            self.falha(crit, f"pede {fmt_fx(fx_item)}{unid}, produto {v_prod:g}{unid}")

    def check_bool(self, crit, pede: bool, tem: bool | None, det_tem="tem", det_nao="não tem"):
        if not pede:
            return
        if tem is None:
            self.duvida(crit, "item pede; ficha não informa")
        elif tem:
            self.ok(crit, det_tem)
        else:
            self.falha(crit, det_nao)

    @property
    def n_falha(self): return sum(1 for s, _, _ in self.res if s == "FALHA")
    @property
    def n_ok(self): return sum(1 for s, _, _ in self.res if s == "OK")
    @property
    def n_duv(self): return sum(1 for s, _, _ in self.res if s == "?")


def _primeiro(rx, t, f=float):
    m = re.search(rx, t)
    return f(num(m.group(1))) if m else None


# --------------------------------------------------------------------------- por categoria
def tensoes(t: str) -> set:
    out = set()
    for v in re.findall(r"(?<!\d)(110|115|120|127|220|230)\s*v?(?!\d)", t):
        out.add("115" if v in ("110", "115", "120", "127") else "220")
    if re.search(r"bivolt|full ?range|automatic", t):
        out |= {"115", "220", "bivolt"}
    return out


def _campo(t, *rotulos):
    for r in rotulos:
        m = re.search(r + r"\s*:?\s*([^,;|]{1,60})", t)
        if m:
            return m.group(1)
    return None


def cmp_nobreak(item: str, prod: str, specs: dict, estabilizador=False) -> Comparacao:
    c = Comparacao()
    # potência VA do item: 'capacidade nominal: 1.5 kva' / 'capacidade nominal: 600' / '1500va'
    va_i = None
    m = re.search(r"capacidade(?: nominal)?\s*:\s*(\d+(?:[.,]\d+)?)\s*(kva|va)?", item)
    if m:
        v = num(m.group(1))
        va_i = v * 1000 if (m.group(2) == "kva" or v < 10) else v
    else:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(k?va)\b", item)
        if m:
            va_i = num(m.group(1)) * (1000 if m.group(2) == "kva" else 1)
    pv = norm(" | ".join(f"{k}: {v}" for k, v in specs.items())) + " | " + prod
    va_p = None
    m = re.search(r"(?:potencia(?: va)?|capacidade)\s*:\s*(\d+(?:[.,]\d+)?)\s*(k?va)", pv) or re.search(r"(\d+(?:[.,]\d+)?)\s*(k?va)\b", pv)
    if m:
        va_p = num(m.group(1)) * (1000 if m.group(2) == "kva" else 1)
    if va_i:
        c.check_num("potência (VA)", (va_i, None), va_p, " VA")
    elif va_p:
        c.excesso += va_p / 10000  # item não pede VA: desempate prefere o menor (mais barato)
    # potência real W (item: 'potência saída: contínua 250w')
    w_i = _primeiro(r"potencia (?:saida|real|ativa)[^,;]{0,25}?(\d+(?:[.,]\d+)?)\s*w\b", item)
    if w_i:
        w_p = _primeiro(r"(?:potencia w|potencia nominal ativa|potencia real|potencia ativa)[^:]*:\s*(\d+(?:[.,]\d+)?)\s*w", pv) \
              or _primeiro(r"(\d{3,4})\s*w\b", pv)
        c.check_num("potência real (W)", (w_i, None), w_p, " W")
    # entrada
    ent_i = _campo(item, r"tensao (?:de )?(?:alimentacao )?entrada", r"entrada")
    ent_p = _campo(pv, r"tensao (?:de )?entrada", r"entrada")
    if ent_i:
        ti, tp = tensoes(ent_i), tensoes(ent_p or "")
        if not tp:
            c.duvida("tensão de entrada", f"item pede '{ent_i.strip()}'; ficha não informa")
        elif ("bivolt" in ti or {"115", "220"} <= ti) and not ("bivolt" in tp or {"115", "220"} <= tp):
            c.falha("tensão de entrada", f"item pede bivolt ({ent_i.strip()}); produto '{ent_p.strip()}'")
        elif ti & tp:
            c.ok("tensão de entrada", f"pede '{ent_i.strip()}', produto '{ent_p.strip()}'")
        else:
            c.falha("tensão de entrada", f"pede '{ent_i.strip()}', produto '{ent_p.strip()}'")
    # saída — crítico: GET é quase toda 115V
    # só "tensão saída" — "saida" solto casa com "quantidade tomadas saída: 4"
    sai_i = _campo(item, r"tensao (?:de )?saida", r"(?<!tomadas )saida(?= (?:monovolt|bivolt|\d{3}))")
    sai_p = _campo(pv, r"tensao (?:de )?saida", r"saida")
    if sai_i:
        ti, tp = tensoes(sai_i), tensoes(sai_p or "")
        if not tp:
            c.duvida("tensão de saída", f"item pede '{sai_i.strip()}'; ficha não informa")
        elif ("115" in ti and "220" in ti) and not ({"115", "220"} <= tp):
            # CATMAT "tensão saída: 110/220" é ambíguo (saída bivolt selecionável ou qualquer uma das
            # duas?) — não reprova, manda confirmar no TR
            c.duvida("tensão de saída", f"item pede saída '{sai_i.strip()}' — se o TR exigir saída bivolt/selecionável, "
                     f"produto (só '{sai_p.strip()}') NÃO atende; conferir no TR")
        elif ti & tp:
            c.ok("tensão de saída", f"pede '{sai_i.strip()}', produto '{sai_p.strip()}'")
        else:
            c.falha("tensão de saída", f"pede '{sai_i.strip()}', produto '{sai_p.strip()}'")
    # tomadas
    tom_i = _primeiro(r"(?:quantidade tomadas(?: saida)?\s*:\s*(?:minimo de )?|)(\d+)\s*tomadas", item) \
        or _primeiro(r"quantidade tomadas(?: saida)?\s*:\s*(?:minimo de )?(\d+)", item)
    if tom_i:
        tom_p = _primeiro(r"(\d+)\s*tomadas", pv) or _primeiro(r"(?:saidas|numero de tomadas|quantidade de tomadas)\s*:\s*0?(\d+)", pv)
        c.check_num("nº de tomadas", (tom_i, None), tom_p)
    # forma de onda
    onda = _campo(item, r"tipo onda", r"forma de onda")
    if onda and not estabilizador:
        pura = "senoidal" in onda and not re.search(r"semi|aproxima|pwm|retangular", onda)
        if pura:
            p_onda = _campo(pv, r"forma (?:da |de )?onda(?: no inversor| de saida)?", r"tipo onda")
            if not p_onda:
                c.duvida("onda senoidal pura", "item pede senoidal; ficha não informa")
            elif re.search(r"semi|aproxima|pwm|retangular|trapez", p_onda):
                c.falha("onda senoidal pura", f"item pede senoidal; produto '{p_onda.strip()}'")
            else:
                c.ok("onda senoidal pura", p_onda.strip())
    if re.search(r"dupla conversao|online", item) and not estabilizador:
        c.check_bool("online/dupla conversão", True,
                     True if re.search(r"dupla conversao: sim|online dupla conversao: sim|tecnologia: online|\bonline\b", pv) else
                     (False if re.search(r"interativ|line interactive|dupla conversao: nao", pv) else None))
    return c


def cmp_monitor(item, prod, specs):
    c = Comparacao()
    pv = norm(" | ".join(f"{k}: {v}" for k, v in specs.items())) + " | " + prod
    fx = faixa(item, r"tamanho (?:da )?tela") or faixa(item, r"tela")
    if not fx:
        m = re.search(r"(\d{2}(?:[.,]\d)?)\s*(?:a\s*(\d{2}(?:[.,]\d)?))?\s*(?:\"|''|´´|pol)", item)
        if m:
            fx = (num(m.group(1)), num(m.group(2)) if m.group(2) else None)
    pol = _primeiro(r"tamanho (?:da )?tela\s*:?\s*(\d{2}(?:[.,]\d)?)", pv) or _primeiro(r"(\d{2}(?:[.,]\d)?)\s*(?:\"|''|pol|polegadas)", pv) \
        or _primeiro(r"\bmon(?:itor)?\b[^|]{0,30}?(\d{2}(?:[.,]\d)?)(?:\"| |$)", pv)
    if fx:
        c.check_num("tamanho da tela", fx, pol, "\"")
    if re.search(r"full ?hd|1920\s*x\s*1080|fhd", item):
        c.check_bool("resolução Full HD", True, True if re.search(r"full ?hd|1920\s*[x*]\s*1080|fhd", pv) else
                     (False if re.search(r"\bhd\b|1366|1600\s*x\s*900", pv) else None), "Full HD", "não é Full HD")
    c.check_bool("painel IPS", "ips" in item, True if "ips" in pv else (False if re.search(r"\bva\b|\btn\b", pv) else None))
    c.check_bool("entrada HDMI", "hdmi" in item, True if "hdmi" in pv else None)
    if re.search(r"displayport|\bdp\b", item):
        c.check_bool("entrada DisplayPort", True, True if re.search(r"displayport|\bdp\b", pv) else None)
    elif re.search(r"conexao d\s*$|conexao d\b(?!-?sub|isplay)", item):
        c.duvida("2ª conexão ('CONEXAO D…')", "descrição cortada no PNCP — D-SUB (VGA) ou DisplayPort? ver TR")
    # "altura" sozinho casa com 'Altura (bruto) [m]' (dimensão da caixa) — exigir o ajuste em si
    aj_alt = r"ajuste (?:de )?altura|regulagem de altura|altura ajust|height adjust|\bhas\b|pivot"
    if "altura" in item:
        c.check_bool("ajuste de altura", True, True if re.search(aj_alt, pv) else None)
    if "rotacao" in item:
        c.check_bool("ajuste de rotação/pivot", True, True if re.search(r"pivot|rotac|giro", pv) else None)
    return c


def cmp_ssd(item, prod, specs):
    c = Comparacao()
    pv = norm(" | ".join(f"{k}: {v}" for k, v in specs.items())) + " | " + prod
    cap_i = _primeiro(r"capacidade(?: memoria)?\s*:\s*(\d+(?:[.,]\d+)?)", item)
    if re.search(r"capacidade[^,]{0,12}tb", item) and cap_i:
        cap_i *= 1000
    cap_p = None
    m = re.search(r"capacidade[^:]*:\s*(\d+(?:[.,]\d+)?)\s*(tb|gb)", pv) or re.search(r"(\d+(?:[.,]\d+)?)\s*(tb|gb)\b", pv)
    if m:
        cap_p = num(m.group(1)) * (1000 if m.group(2) == "tb" else 1)
    if cap_i:
        # capacidade: aceita de -5% (240 x 256 é a mesma faixa comercial? não — exige ≥) até 2,1x
        c.check_num("capacidade (GB)", (cap_i * 0.94, cap_i * 2.1), cap_p, " GB")
    eh_ram = "memoria ram" in item
    if eh_ram:
        ddr_i = re.search(r"ddr(\d)", item)
        ddr_p = re.search(r"ddr(\d)", pv)
        if ddr_i:
            c.check_bool(f"padrão DDR{ddr_i.group(1)}", True, (ddr_p.group(1) == ddr_i.group(1)) if ddr_p else None,
                         f"DDR{ddr_p.group(1) if ddr_p else ''}", f"produto DDR{ddr_p.group(1) if ddr_p else '?'}")
        mhz_i = _primeiro(r"(\d{4})\s*mhz", item)
        if mhz_i:
            c.check_num("frequência (MHz)", (mhz_i, None), _primeiro(r"(\d{4})\s*mhz", pv), " MHz")
        if "microcomputador" in item or "udimm" in item or "desktop" in item:
            c.check_bool("formato desktop (não SODIMM)", True, False if re.search(r"so-?dimm|notebook", pv) else (True if re.search(r"u?dimm|desktop", pv) else None))
        return c
    if "pen drive" in item or "memoria portatil" in item:
        return c
    # SSD
    if re.search(r"nvme|pcie|m\.?2|22 x 80|2280", item):
        c.check_bool("interface NVMe/M.2", True, True if re.search(r"nvme|pcie", pv) else (False if "sata" in pv else None), "NVMe", "produto é SATA")
    elif re.search(r"sata|2,5", item):
        c.check_bool("SATA 2,5\"", True, True if re.search(r"sata", pv) and not re.search(r"m\.?2|nvme", pv) else
                     (False if re.search(r"nvme|m\.?2 ?2280", pv) else None), "SATA 2,5\"", "produto é M.2/NVMe")
    return c


def cmp_teclado_mouse(item, prod, specs):
    c = Comparacao()
    pv = norm(" | ".join(f"{k}: {v}" for k, v in specs.items())) + " | " + prod
    quer_kit = bool(re.search(r"teclado e mouse|teclado\s*\+\s*mouse|kit", item))
    quer_mouse = not quer_kit and item.lstrip().startswith("mouse")
    p_kit = bool(re.search(r"kit|tec\s*\+\s*mou|teclado e mouse|combo", pv[:120]))
    p_mouse = pv.lstrip().startswith("mouse") or bool(re.match(r"\s*mouse", prod))
    if quer_kit:
        c.check_bool("é kit teclado + mouse", True, p_kit, "kit", "produto não é kit")
    elif quer_mouse:
        c.check_bool("é mouse", True, p_mouse and not p_kit, "mouse", "produto não é mouse avulso")
    else:
        c.check_bool("é teclado", True, (not p_mouse) and not p_kit, "teclado", "produto não é teclado avulso")
    if re.search(r"conectividade: com fio|\bcom fio\b", item):
        c.check_bool("com fio (USB)", True, False if re.search(r"sem fio|s/fio|wireless|bluetooth|2\.4 ?ghz", pv) else True,
                     "com fio", "produto é sem fio")
    elif re.search(r"sem fio|wireless", item):
        c.check_bool("sem fio", True, True if re.search(r"sem fio|s/fio|wireless|2\.4 ?ghz|bluetooth", pv) else False, "sem fio", "produto é com fio")
    if "usb" in item:
        c.check_bool("conector USB", True, True if "usb" in pv else None)
    if "abnt" in item:
        c.check_bool("padrão ABNT2", True, True if "abnt" in pv else None)
    if "vertical" in item:
        c.check_bool("mouse vertical", True, True if "vertical" in pv else False, "vertical", "não é vertical")
    if "sensor: laser" in item:
        c.check_bool("sensor laser", True, True if "laser" in pv else (False if re.search(r"optic|led", pv) else None), "laser", "sensor óptico/LED")
    return c


def cmp_projetor(item, prod, specs):
    c = Comparacao()
    pv = norm(" | ".join(f"{k}: {v}" for k, v in specs.items())) + " | " + prod
    lum_i = _primeiro(r"luminosidade minima\s*:\s*(\d+(?:[.,]\d+)?)", item) or _primeiro(r"(\d[\d.]*)\s*(?:ansi )?lumens", item)
    lum_p = _primeiro(r"(?:ansi lumens|brilho|lumens)\s*:\s*(\d[\d.]*)", pv) or _primeiro(r"(\d[\d.]{2,})\s*(?:ansi )?(?:lumens|lm)", pv)
    if lum_i:
        c.check_num("luminosidade (lúmens)", (lum_i, None), lum_p, " lm")
        if lum_p and "ansi" not in pv:
            c.duvida("lúmens ANSI", "ficha não diz se o brilho é ANSI (TR costuma exigir ANSI)")
    m = re.search(r"resolucao\s*:\s*(\d[\d.]*)\s*x\s*(\d[\d.]*)", item)
    if m:
        need = num(m.group(1)) * num(m.group(2))
        mp = re.search(r"(\d{3,4})\s*[x*]\s*(\d{3,4})", pv)
        have = num(mp.group(1)) * num(mp.group(2)) if mp else None
        c.check_num("resolução nativa (pixels)", (need, None), have)
    ctr_i = _primeiro(r"contraste minimo\s*:\s*(\d[\d.]*)", item)
    if ctr_i:
        c.check_num("contraste", (ctr_i, None), _primeiro(r"contraste\s*:?\s*(\d[\d.]*)\s*:\s*1", pv))
    for porta in ("hdmi", "vga", "rj45", "wi-fi"):
        rx = {"vga": r"vga|d-sub", "wi-fi": r"wi-?fi|wireless", "rj45": r"rj45|lan|ethernet"}.get(porta, porta)
        if re.search({"vga": r"vga|d-sub15", "wi-fi": r"wi-?fi", "rj45": r"rj45"}.get(porta, porta), item):
            c.check_bool(f"entrada {porta.upper()}", True, True if re.search(rx, pv) else None)
    tec = re.search(r"tipo tecnologia\s*:\s*(lcd|dlp)", item)
    if tec:
        c.check_bool(f"tecnologia {tec.group(1).upper()}", True,
                     True if tec.group(1) in pv else (False if re.search(r"\b(lcd|dlp)\b", pv) else None),
                     tec.group(1).upper(), "tecnologia diferente")
    if "interativo" in item:
        c.check_bool("projetor interativo", True, True if "interativ" in pv else None)
    return c


def nucleos_cpu(pv: str):
    """Núcleos a partir da ficha: '6P+4E' (Intel híbrido) = 10, '6P+8E+2LPE' = 16, '2NU' = 2,
    '8 nucleos'/'8 cores'. Nunca deduz pelo nome do modelo (i5/i7 não diz quantos núcleos)."""
    m = re.search(r"(\d+)p\s*\+\s*(\d+)e(?:\s*\+\s*(\d+)lpe)?", pv)
    if m:
        return float(int(m.group(1)) + int(m.group(2)) + int(m.group(3) or 0))
    m = re.search(r"(\d+)\s*nu\b|(\d+)\s*(?:nucleos|cores)\b", pv)
    if m:
        return float(m.group(1) or m.group(2))
    return None


def cmp_computador(item, prod, specs, notebook=False):
    c = Comparacao()
    pv = norm(" | ".join(f"{k}: {v}" for k, v in specs.items())) + " | " + prod
    ram_i = faixa(item, r"memoria ram")
    ram_p = _primeiro(r"(?:memoria(?: ram)?|ram)\s*:?\s*(\d+)\s*gb", pv) or _primeiro(r"(\d+)\s*gb(?: de)? (?:ram|memoria|ddr)", pv) \
        or _primeiro(r"\b(?:i[3579]|ryzen \d)[^,|]{0,15},\s*(\d+)\s*,", pv)
    c.check_num("memória RAM (GB)", ram_i, ram_p, " GB", teto_flexivel=True)
    ssd_i = faixa(item, r"armazenamento ssd")
    if ssd_i:
        ssd_p = None
        m = re.search(r"ssd\s*:?\s*(?:de\s*)?(\d+(?:[.,]\d+)?)\s*(tb|gb)", pv) or re.search(r"(\d+(?:[.,]\d+)?)\s*(tb|gb)\s*(?:ssd|nvme|sata)", pv) \
            or re.search(r"\b(?:i[3579]|ryzen \d)[^,|]{0,15},\s*\d+\s*,\s*(\d+)()", pv)
        if m:
            ssd_p = num(m.group(1)) * (1000 if m.group(2) == "tb" else 1)
        c.check_num("SSD (GB)", ssd_i, ssd_p, " GB", teto_flexivel=True)
    nuc_i = faixa(item, r"nucleos por processador")
    if nuc_i:
        nuc_p = nucleos_cpu(pv)
        if nuc_p is None:
            c.duvida("núcleos do processador", f"item pede {fmt_fx(nuc_i)}; ficha só traz o modelo da CPU — conferir no site do fabricante")
        else:
            c.check_num("núcleos do processador", nuc_i, nuc_p, teto_flexivel=True)
    if notebook:
        tela_i = faixa(item, r"tela")
        c.check_num("tela (pol)", tela_i, _primeiro(r"(\d{2}(?:[.,]\d)?)\s*(?:\"|''|pol)", pv)
                    or _primeiro(r"(1[0-8](?:[.,]\d)?)\s+(?:wuxga|fhd|full ?hd|hd|wxga|2\.?\dk|qhd|ips|led|oled|tn)", pv), "\"")
    if "sistema operacional: proprietario" in item:
        c.check_bool("Windows (SO proprietário)", True, True if "windows" in pv else (False if re.search(r"linux|lnx|sem sistema|free ?dos|chromebook|chrome ?os", pv) else None),
                     "Windows", "produto vem com Linux/sem Windows")
    if re.search(r"monitor: (\d+) a (\d+)", item):
        c.duvida("monitor junto", "item pede computador COM monitor — cotar monitor à parte se o kit não incluir")
    if "com teclado e mouse" in item:
        c.check_bool("teclado e mouse inclusos", True, True if re.search(r"teclado|mouse", pv) else None)
    gar = _primeiro(r"garantia on site\s*:\s*(?:superior a\s*)?(\d+)", item)
    if gar:
        c.duvida("garantia on-site", f"item pede {gar:g} meses on-site — confirmar com o vendedor")
    return c


def cmp_tablet(item, prod, specs):
    c = Comparacao()
    pv = norm(" | ".join(f"{k}: {v}" for k, v in specs.items())) + " | " + prod
    c.check_num("tela (pol)", faixa(item, r"tela"), _primeiro(r"(\d{1,2}(?:[.,]\d)?)\s*(?:\"|''|pol)", pv) or _primeiro(r"\btbl\b[^|]*?(\d{1,2})\s", pv), "\"")
    c.check_num("RAM (GB)", faixa(item, r"memoria ram"), _primeiro(r"(?:memoria ram|ram)\s*:?\s*(\d+)\s*gb", pv), " GB")
    c.check_num("armazenamento (GB)", faixa(item, r"armazenamento interno"), _primeiro(r"(?:armazenamento|memoria interna)[^:]*:\s*(\d+)\s*gb", pv) or _primeiro(r"(\d+)\s*gb", pv), " GB")
    if "5g" in item:
        c.check_bool("5G", True, True if "5g" in pv else (False if "4g" in pv else None), "5G", "produto é 4G")
    elif "4g" in item:
        c.check_bool("4G", True, True if re.search(r"4g|lte", pv) else None)
    if "chip m2" in item:
        c.falha("processador Apple M2", "item é iPad (chip M2) — nenhum fornecedor de periférico atende")
    return c


def cmp_generico(item, prod, specs):
    c = Comparacao()
    pv = norm(" | ".join(f"{k}: {v}" for k, v in specs.items())) + " | " + prod
    if "usb" in item:
        c.check_bool("conexão USB", True, True if "usb" in pv else None)
    if "microfone" in item:
        c.check_bool("microfone", True, True if re.search(r"microfone|mic\b", pv) else None)
    if re.search(r"1080|full ?hd", item):
        c.check_bool("resolução 1080p", True, True if re.search(r"1080|full ?hd|fhd", pv) else (False if "720" in pv else None))
    w = _primeiro(r"potencia\s*:\s*(\d+)\s*w", item)
    if w:
        c.check_num("potência (W RMS)", (w, None), _primeiro(r"(\d+)\s*w(?:atts)?\s*rms", pv) or _primeiro(r"potencia[^:]*:\s*(\d+)\s*w", pv), " W")
    return c


def cmp_impressora(item, prod, specs):
    c = Comparacao()
    pv = norm(" | ".join(f"{k}: {v}" for k, v in specs.items())) + " | " + prod
    if "multifuncional" in item:
        c.check_bool("multifuncional", True, True if "multifuncional" in pv else False, "multifuncional", "impressora simples")
    if "laser" in item:
        c.check_bool("laser", True, True if "laser" in pv else (False if re.search(r"tanque|jato", pv) else None), "laser", "não é laser")
    col = _primeiro(r"velocidade impressao colorida\s*:\s*(\d+)", item)
    if col:
        c.check_bool("impressão colorida", True, True if re.search(r"color", pv) else (False if re.search(r"mono", pv) else None), "colorida", "monocromática")
    ppm = _primeiro(r"velocidade impressao preto e branco\s*:\s*(\d+)", item)
    if ppm:
        c.check_num("velocidade (ppm)", (ppm, None), _primeiro(r"(\d+)\s*ppm", pv), " ppm")
    if "ethernet" in item or "rede" in item:
        c.check_bool("rede ethernet", True, True if re.search(r"ethernet|rede|rj45|lan", pv) else None)
    if "wireless" in item or "wi-fi" in item:
        c.check_bool("wi-fi", True, True if re.search(r"wi-?fi|wireless", pv) else None)
    return c


def comparar(categoria: str, item_desc: str, produto: dict) -> Comparacao:
    item = norm(item_desc)
    prod = norm(produto.get("texto") or produto.get("nome"))
    specs = produto.get("specs") or {}
    if categoria == "Nobreak":
        return cmp_nobreak(item, prod, specs)
    if categoria == "Estabilizador":
        return cmp_nobreak(item, prod, specs, estabilizador=True)
    if categoria == "Monitor":
        return cmp_monitor(item, prod, specs)
    if categoria == "Armazenamento":
        return cmp_ssd(item, prod, specs)
    if categoria == "Teclado/Mouse":
        return cmp_teclado_mouse(item, prod, specs)
    if categoria == "Projetor":
        return cmp_projetor(item, prod, specs)
    if categoria == "Computador":
        return cmp_computador(item, prod, specs)
    if categoria == "Notebook":
        return cmp_computador(item, prod, specs, notebook=True)
    if categoria == "Tablet":
        return cmp_tablet(item, prod, specs)
    if categoria == "Impressora":
        return cmp_impressora(item, prod, specs)
    return cmp_generico(item, prod, specs)
