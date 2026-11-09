#!/usr/bin/env python3
"""Página — Radar de Fornecedor: onde estão os fornecedores catalogados e com quem falar primeiro.

Snapshot estático da base "📫 Fornecedores e portais" do Notion (113 fornecedores,
lida em 09/nov/2026) — mapa por UF + fila de prioridade de contato a partir de
Fortaleza. Mesma página do artifact "Radar de Fornecedores B2G"; o HTML vive em
assets/radar_fornecedor.html e não consulta banco nem Notion em tempo real.
"""

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

HTML = (Path(__file__).parent.parent / "assets" / "radar_fornecedor.html").read_text(encoding="utf-8")

components.html(HTML, height=2900, scrolling=True)
