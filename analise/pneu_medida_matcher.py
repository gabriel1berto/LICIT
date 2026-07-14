"""
Matching de medida de pneu — determinístico, sem LLM.

PASSO A (extrair_medida): captura ampla, zero falso-negativo. Aceita qualquer
separador/ordem razoável ("225/70R13", "225/70/13", "225 70 13", "22570R13").
Se a construção ("R") estiver ausente no texto, assume "R" e marca
inferido_construcao=True.

PASSO B (comparar_medidas): compara SEMPRE tupla-a-tupla (nunca string-a-string).
  - match_exato:   tupla idêntica, construção não-inferida, índice carga/velocidade presente
  - match_parcial: tupla idêntica, mas construção inferida OU índice carga/velocidade ausente
  - sem_match:     largura, perfil ou aro divergem — nunca confundir com falta de estoque
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MedidaTupla:
    largura: int
    perfil: int
    construcao: str  # normalizado, ex: "R"
    aro: float
    inferido_construcao: bool = False
    indice_carga_velocidade: Optional[str] = None

    def chave(self) -> tuple[int, int, str, float]:
        """Tupla comparável (largura, perfil, construcao, aro) — nunca compare strings."""
        return (self.largura, self.perfil, self.construcao, self.aro)


# Índice de carga/velocidade: 2-3 dígitos seguidos de 1-2 letras (ex: "104S", "91V", "104/102S")
_RE_INDICE = re.compile(r"\b(\d{2,3}(?:/\d{2,3})?\s*[A-Z]{1,2})\b")

# Padrão com separador explícito: largura[sep]perfil[sep][R][sep]aro
_RE_COM_SEPARADOR = re.compile(
    r"(?P<largura>\d{3})\s*[\/\s\-]\s*(?P<perfil>\d{2})\s*[\/\s\-]?\s*"
    r"(?P<construcao>[A-Z])?\s*[\/\s\-]?\s*(?P<aro>\d{1,2}(?:[.,]5)?)"
)

# Padrão sem separador (dígitos colados): 3 dígitos + 2 dígitos + letra opcional + 1-2 dígitos
_RE_SEM_SEPARADOR = re.compile(
    r"(?P<largura>\d{3})(?P<perfil>\d{2})(?P<construcao>[A-Z])?(?P<aro>\d{1,2})\b"
)

_CONSTRUCOES_VALIDAS = {"R", "D", "B"}  # radial, diagonal, bias


def _normaliza_aro(txt: str) -> float:
    return float(txt.replace(",", "."))


def extrair_medida(texto_bruto: str) -> Optional[MedidaTupla]:
    """PASSO A — extração permissiva. Retorna None só se nada reconhecível for encontrado."""
    if not texto_bruto:
        return None

    texto = texto_bruto.upper().strip()

    indice_match = _RE_INDICE.search(texto)
    indice = indice_match.group(1).replace(" ", "") if indice_match else None

    for padrao in (_RE_COM_SEPARADOR, _RE_SEM_SEPARADOR):
        m = padrao.search(texto)
        if not m:
            continue
        largura = int(m.group("largura"))
        perfil = int(m.group("perfil"))
        aro = _normaliza_aro(m.group("aro"))
        construcao_bruta = m.group("construcao")

        # sanity check nos ranges reais de pneu — evita casar número aleatório de 3+2+2 dígitos
        if not (125 <= largura <= 335):
            continue
        if not (25 <= perfil <= 95):
            continue
        if not (10 <= aro <= 24.5):
            continue

        if construcao_bruta and construcao_bruta in _CONSTRUCOES_VALIDAS:
            return MedidaTupla(
                largura=largura,
                perfil=perfil,
                construcao=construcao_bruta,
                aro=aro,
                inferido_construcao=False,
                indice_carga_velocidade=indice,
            )
        else:
            # construção ausente ou não reconhecida -> assume "R", marca como inferido
            return MedidaTupla(
                largura=largura,
                perfil=perfil,
                construcao="R",
                aro=aro,
                inferido_construcao=True,
                indice_carga_velocidade=indice,
            )

    return _extrair_com_fuzzy(texto, indice)


def _extrair_com_fuzzy(texto: str, indice: Optional[str]) -> Optional[MedidaTupla]:
    """Fallback pra erro de digitação: remove tudo que não é dígito/letra relevante
    e tenta casar o padrão sem separador contra o resultado."""
    limpo = re.sub(r"[^0-9A-Z]", "", texto)
    m = _RE_SEM_SEPARADOR.search(limpo)
    if not m:
        return None
    largura = int(m.group("largura"))
    perfil = int(m.group("perfil"))
    aro = _normaliza_aro(m.group("aro"))
    construcao_bruta = m.group("construcao")

    if not (125 <= largura <= 335) or not (25 <= perfil <= 95) or not (10 <= aro <= 24.5):
        return None

    construcao_valida = construcao_bruta in _CONSTRUCOES_VALIDAS if construcao_bruta else False
    return MedidaTupla(
        largura=largura,
        perfil=perfil,
        construcao=construcao_bruta if construcao_valida else "R",
        aro=aro,
        inferido_construcao=not construcao_valida,
        indice_carga_velocidade=indice,
    )


def comparar_medidas(candidata: MedidaTupla, referencia: MedidaTupla) -> str:
    """PASSO B — comparação tupla-a-tupla. Retorna 'match_exato' | 'match_parcial' | 'sem_match'."""
    if candidata.chave() != referencia.chave():
        return "sem_match"

    if candidata.inferido_construcao or candidata.indice_carga_velocidade is None:
        return "match_parcial"

    return "match_exato"


def avaliar(texto_bruto: str, referencia: MedidaTupla) -> tuple[str, Optional[MedidaTupla]]:
    """Combina extração + comparação. Retorna (confianca, tupla_extraida_ou_None)."""
    extraida = extrair_medida(texto_bruto)
    if extraida is None:
        return "sem_match", None
    return comparar_medidas(extraida, referencia), extraida
