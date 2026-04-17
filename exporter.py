"""
Exporter do Excelu.

Každý řádek = jeden subjekt z ARES.
Sloupce:
  - Všechna data z ARES (zploštěná)
  - OR_Osoba_1_Role, OR_Osoba_1_Jmeno, OR_Osoba_2_Role, OR_Osoba_2_Jmeno, …
    (počet sloupců odpovídá maximu osob u jednoho subjektu)
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from ares_client import flatten_subject
from or_scraper import get_or_persons, create_session
from legal_forms import code_to_name

# ---------------------------------------------------------------------------
# Konstanty vzhledu
# ---------------------------------------------------------------------------

COLOR_HEADER_ARES = "1F538D"   # tmavě modrá – ARES sloupce
COLOR_HEADER_OR   = "2E7D32"   # tmavě zelená – OR sloupce
COLOR_HEADER_FONT = "FFFFFF"
COLOR_ALT_ROW     = "F5F7FA"   # světle šedá – liché řádky


# ---------------------------------------------------------------------------
# Mapování ARES klíčů → pěkné české názvy sloupců
# ---------------------------------------------------------------------------

ARES_COLUMN_LABELS: dict[str, str] = {
    "ico":                          "IČO",
    "obchodniJmeno":                "Obchodní firma / jméno",
    "pravniForma":                  "Právní forma (kód)",
    "pravniForma_nazev":            "Právní forma (název)",
    "financniUrad":                 "Finanční úřad",
    "datumVzniku":                  "Datum vzniku",
    "datumZapisu":                  "Datum zápisu",
    "datumZaniku":                  "Datum zániku",
    "kategorieCrd":                 "Kategorie CRD",
    "sidlo_textovaAdresa":          "Adresa (textová)",
    "sidlo_psc":                    "PSČ",
    "sidlo_nazevObce":              "Obec",
    "sidlo_nazevUlice":             "Ulice",
    "sidlo_cisloDomovni":           "Číslo popisné",
    "sidlo_cisloOrientacni":        "Číslo orientační",
    "sidlo_nazevKraje":             "Kraj",
    "sidlo_nazevOkresu":            "Okres",
    "sidlo_nazevStatu":             "Stát",
    "sidlo_nazevSpravnihoObvodu":   "Správní obvod",
    "sidlo_nazevMestskeCasti":      "Část obce",
    "sidlo_kodStatu":               "Kód státu",
    "datovaSkladka_idds":           "Datová schránka",
}

# Pořadí preferovaných ARES sloupců (ostatní se přidají za ně abecedně)
PREFERRED_ARES_ORDER = [
    "ico", "obchodniJmeno", "pravniForma", "pravniForma_nazev",
    "sidlo_textovaAdresa", "sidlo_psc", "sidlo_nazevObce",
    "sidlo_nazevUlice", "sidlo_cisloDomovni", "sidlo_cisloOrientacni",
    "sidlo_nazevOkresu", "sidlo_nazevKraje", "sidlo_nazevStatu",
    "datumVzniku", "datumZapisu", "datumZaniku",
    "financniUrad", "datovaSkladka_idds",
]


# ---------------------------------------------------------------------------
# Pomocné funkce
# ---------------------------------------------------------------------------

def _col_label(key: str) -> str:
    return ARES_COLUMN_LABELS.get(key, key)


def _enrich_legal_form(flat: dict[str, Any]) -> dict[str, Any]:
    """Doplní pěkný název právní formy."""
    code = flat.get("pravniForma", "")
    if code and "pravniForma_nazev" not in flat:
        flat["pravniForma_nazev"] = code_to_name(str(code))
    return flat


def _build_column_order(all_flat_records: list[dict[str, Any]]) -> list[str]:
    """Sestaví konečné pořadí ARES sloupců."""
    all_keys: set[str] = set()
    for r in all_flat_records:
        all_keys.update(r.keys())

    ordered: list[str] = []
    for key in PREFERRED_ARES_ORDER:
        if key in all_keys:
            ordered.append(key)
            all_keys.discard(key)

    # Zbytek abecedně
    ordered.extend(sorted(all_keys))
    return ordered


def _style_header_cell(cell, bg_color: str) -> None:
    cell.font      = Font(bold=True, color=COLOR_HEADER_FONT, size=10)
    cell.fill      = PatternFill("solid", fgColor=bg_color)
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin = Side(style="thin", color="CCCCCC")
    cell.border    = Border(left=thin, right=thin, top=thin, bottom=thin)


def _style_data_cell(cell, alt_row: bool) -> None:
    cell.alignment = Alignment(vertical="top", wrap_text=False)
    if alt_row:
        cell.fill = PatternFill("solid", fgColor=COLOR_ALT_ROW)


def _auto_width(ws) -> None:
    for col_cells in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col_cells[0].column)
        for cell in col_cells:
            try:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max(max_len + 2, 10), 45)


# ---------------------------------------------------------------------------
# Hlavní export
# ---------------------------------------------------------------------------

def export_to_excel(
    ares_results: list[dict[str, Any]],
    output_path,   # str (cesta) nebo file-like objekt (BytesIO pro web)
    or_delay: float = 2.0,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    cancel_flag: Optional[threading.Event] = None,
) -> None:
    """
    Exportuje výsledky ARES + OR osoby do Excelu.

    Args:
        ares_results:      Seznam subjektů z ares_client.fetch_all().
        output_path:       Cílová cesta .xlsx.
        progress_callback: Funkce(current, total, zpráva).
        cancel_flag:       threading.Event – přeruší export.

    Raises:
        InterruptedError: Pokud uživatel zruší export.
    """
    total = len(ares_results)

    # --- Fáze 1: Zploštit ARES data a sestavit seznam sloupců ---
    if progress_callback:
        progress_callback(0, total, "Příprava dat z ARES…")

    flat_records: list[dict[str, Any]] = []
    for subj in ares_results:
        flat = _enrich_legal_form(flatten_subject(subj))
        flat_records.append(flat)

    ares_columns = _build_column_order(flat_records)

    # --- Fáze 2: Stáhnout OR osoby pro každý subjekt ---
    # Nastav prodlevu dle uzivatelskeho nastaveni
    import or_scraper as _or_mod
    _or_mod.REQUEST_DELAY = float(or_delay)

    or_session = create_session()
    or_persons_list: list[list[dict[str, str]]] = []
    max_persons = 0

    for i, subj in enumerate(ares_results):
        if cancel_flag and cancel_flag.is_set():
            raise InterruptedError("Export zrušen uživatelem.")

        ico = subj.get("ico", "")
        if progress_callback:
            progress_callback(
                i, total,
                f"OR: Zpracovávám {i + 1:,} / {total:,}  •  IČO {ico}"
            )

        persons = get_or_persons(ico, or_session) if ico else []
        or_persons_list.append(persons)

        if len(persons) > max_persons:
            max_persons = len(persons)

    # --- Fáze 3: Sestavení Excelu ---
    if progress_callback:
        progress_callback(total, total, "Zapisuji Excel…")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ARES + OR"
    ws.freeze_panes = "A2"  # zmrazí záhlaví

    # Záhlaví – ARES sloupce
    col_idx = 1
    for key in ares_columns:
        cell = ws.cell(row=1, column=col_idx, value=_col_label(key))
        _style_header_cell(cell, COLOR_HEADER_ARES)
        col_idx += 1

    # Záhlaví – OR sloupce (Role, Jméno, Datum nar., Adresa pro každou osobu)
    or_start_col = col_idx
    for n in range(1, max_persons + 1):
        for label in [f"OR – Role {n}", f"OR – Jméno {n}", f"OR – Datum nar. {n}", f"OR – Adresa {n}"]:
            cell = ws.cell(row=1, column=col_idx, value=label)
            _style_header_cell(cell, COLOR_HEADER_OR)
            col_idx += 1

    # Výška záhlaví
    ws.row_dimensions[1].height = 28

    # Data řádky
    for row_i, (flat, persons) in enumerate(zip(flat_records, or_persons_list), start=2):
        alt = (row_i % 2 == 0)

        # ARES data
        for ci, key in enumerate(ares_columns, start=1):
            val = flat.get(key, "")
            cell = ws.cell(row=row_i, column=ci, value=val)
            _style_data_cell(cell, alt)

        # OR osoby (4 sloupce na osobu: role, jmeno, datum_narozeni, adresa)
        for pi, person in enumerate(persons):
            base_col = or_start_col + pi * 4
            vals = [
                person.get("role", ""),
                person.get("jmeno", ""),
                person.get("datum_narozeni", ""),
                person.get("adresa", ""),
            ]
            for offset, val in enumerate(vals):
                c = ws.cell(row=row_i, column=base_col + offset, value=val)
                _style_data_cell(c, alt)

        ws.row_dimensions[row_i].height = 16

    # Automatická šířka sloupců
    _auto_width(ws)

    # Uložení
    wb.save(output_path)

    if progress_callback:
        label = output_path if isinstance(output_path, str) else "buffer"
        progress_callback(total, total, f"Export dokončen → {label}")
