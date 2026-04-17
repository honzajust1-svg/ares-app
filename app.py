# -*- coding: utf-8 -*-
"""
ARES + Obchodní rejstřík – Webová aplikace (Streamlit)
Každý uživatel pracuje se svými daty v session state.
"""

import io
import threading
import time

import streamlit as st

from ares_client import fetch_all
from exporter import export_to_excel
from legal_forms import DROPDOWN_OPTIONS, DEFAULT_FORM, parse_dropdown_code
from obce_db import OBCE, hledej

# ---------------------------------------------------------------------------
# Konfigurace stránky
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="ARES + OR Vyhledávač",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Session state – každý uživatel má svá data
# ---------------------------------------------------------------------------

def init_state():
    defaults = {
        "results": [],
        "searching": False,
        "search_done": False,
        "error": None,
        "export_bytes": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

# ---------------------------------------------------------------------------
# Hlavička
# ---------------------------------------------------------------------------

st.markdown(
    "<h1 style='color:#4fc3f7; margin-bottom:0'>🔎 ARES + Obchodní rejstřík</h1>"
    "<p style='color:#888; margin-top:4px'>Vyhledávání ekonomických subjektů a osob z OR</p>",
    unsafe_allow_html=True,
)
st.divider()

# ---------------------------------------------------------------------------
# Panel filtrů
# ---------------------------------------------------------------------------

col1, col2 = st.columns([2, 1])

with col1:
    # Právní forma
    forma_options = [""] + DROPDOWN_OPTIONS
    default_idx = next(
        (i for i, o in enumerate(forma_options) if o.startswith("145")), 0
    )
    forma_raw = st.selectbox(
        "Právní forma",
        options=forma_options,
        index=default_idx,
        help="Vyberte ze seznamu nebo ponechte prázdné",
    )
    forma_kod = parse_dropdown_code(forma_raw) if forma_raw else None

    # Obec – autocomplete přes text_input + filtrování
    obec_query = st.text_input(
        "Obec",
        placeholder="Začněte psát název obce…",
        help="Vyberte obec ze seznamu níže",
    )

    # Filtruj obce dle textu
    kod_obce = None
    if obec_query.strip():
        matches = hledej(obec_query.strip())[:30]
        if matches:
            nazvy = ["-- nevybráno --"] + [f"{n}  [{k}]" for n, k in matches]
            vybrana = st.selectbox("Nalezené obce:", nazvy, key="obec_select")
            if vybrana and vybrana != "-- nevybráno --":
                kod_obce = vybrana.split("[")[-1].rstrip("]").strip()
                st.caption(f"✓ Vybrán RÚIAN kód: `{kod_obce}`")
        else:
            st.caption("❌ Žádná obec nenalezena")

    # Textová adresa
    textova_adr = st.text_input(
        "Textová adresa (nebo její část)",
        placeholder="např. Dubí, nebo Tovární, nebo 415 01",
        help="Město, ulice, PSČ nebo libovolná část adresy. Prázdné = nepoužije se.",
    ) or None

with col2:
    st.markdown("##### Nastavení exportu")
    or_delay = st.number_input(
        "Prodleva OR (sekundy)",
        min_value=0.0,
        max_value=30.0,
        value=2.0,
        step=0.5,
        help="Pauza mezi dotazy na Obchodní rejstřík. Vyšší = bezpečnější, pomalejší.",
    )
    st.caption(f"Odhad: {or_delay}s × počet výsledků")

    st.markdown("---")
    st.markdown("##### Nápověda")
    st.markdown("""
- **Obec**: napište název a vyberte ze seznamu
- **Textová adresa**: volný text – město, PSČ, ulice
- **Prodleva OR**: 2s = bezpečné, 0.5s = rychlejší ale riskantnější
- Prázdné pole = filtr se **nepoužije**
    """)

# ---------------------------------------------------------------------------
# Tlačítka Vyhledat / Exportovat
# ---------------------------------------------------------------------------

st.divider()
bcol1, bcol2, bcol3 = st.columns([1, 1, 3])

with bcol1:
    hledat = st.button(
        "🔍 Vyhledat v ARES",
        type="primary",
        use_container_width=True,
        disabled=st.session_state.searching,
    )

with bcol2:
    exportovat = st.button(
        "💾 Exportovat do Excelu",
        use_container_width=True,
        disabled=not st.session_state.results or st.session_state.searching,
    )

# ---------------------------------------------------------------------------
# Vyhledávání
# ---------------------------------------------------------------------------

if hledat:
    if not any([forma_kod, kod_obce, textova_adr]):
        st.error("⚠️ Vyplňte alespoň jedno pole: Právní forma, Obec nebo Textová adresa.")
    else:
        st.session_state.searching = True
        st.session_state.search_done = False
        st.session_state.results = []
        st.session_state.error = None
        st.session_state.export_bytes = None

        progress_bar = st.progress(0, text="Připojuji se na ARES…")

        try:
            # Jednoduché synchronní volání – Streamlit nemá vlákna
            results = fetch_all(
                pravni_forma=forma_kod,
                kod_obce=kod_obce,
                textova_adresa=textova_adr,
                progress_callback=lambda cur, tot, msg: progress_bar.progress(
                    min(cur / max(tot, 1), 1.0), text=msg
                ),
            )
            st.session_state.results = results
            st.session_state.search_done = True
            progress_bar.progress(1.0, text=f"Hotovo – {len(results):,} subjektů")
        except ValueError as e:
            st.session_state.error = str(e)
            progress_bar.empty()
        except Exception as e:
            st.session_state.error = f"Chyba: {e}"
            progress_bar.empty()
        finally:
            st.session_state.searching = False

# ---------------------------------------------------------------------------
# Zobrazení výsledků
# ---------------------------------------------------------------------------

if st.session_state.error:
    st.error(st.session_state.error)

if st.session_state.results:
    results = st.session_state.results
    st.success(f"✅ Nalezeno **{len(results):,}** subjektů")

    # Tabulka preview
    import pandas as pd

    rows = []
    for s in results:
        sidlo = s.get("sidlo", {}) or {}
        rows.append({
            "IČO": s.get("ico", ""),
            "Název": s.get("obchodniJmeno", ""),
            "PF": s.get("pravniForma", ""),
            "PSČ": str(sidlo.get("psc", "") or ""),
            "Obec": sidlo.get("nazevObce", ""),
            "Adresa": sidlo.get("textovaAdresa", ""),
        })

    df = pd.DataFrame(rows)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=400,
        column_config={
            "IČO": st.column_config.TextColumn(width="small"),
            "PF": st.column_config.TextColumn("Práv. forma", width="small"),
            "PSČ": st.column_config.TextColumn(width="small"),
            "Název": st.column_config.TextColumn(width="large"),
            "Adresa": st.column_config.TextColumn(width="large"),
        },
    )

# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

if exportovat and st.session_state.results:
    n = len(st.session_state.results)
    est = n * (or_delay + 0.5) / 60

    with st.spinner(
        f"Exportuji {n:,} subjektů + OR osoby (odhad ~{est:.0f} min, prodleva {or_delay}s)…"
    ):
        buf = io.BytesIO()

        # Progress placeholder
        exp_progress = st.progress(0, text="Připravuji export…")

        try:
            export_to_excel(
                st.session_state.results,
                buf,
                or_delay=or_delay,
                progress_callback=lambda cur, tot, msg: exp_progress.progress(
                    min(cur / max(tot, 1), 1.0), text=msg
                ),
            )
            buf.seek(0)
            st.session_state.export_bytes = buf.getvalue()
            exp_progress.progress(1.0, text="Export dokončen!")
        except Exception as e:
            st.error(f"Chyba při exportu: {e}")
            exp_progress.empty()

if st.session_state.export_bytes:
    st.download_button(
        label="⬇️ Stáhnout Excel",
        data=st.session_state.export_bytes,
        file_name="ares_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=False,
    )
