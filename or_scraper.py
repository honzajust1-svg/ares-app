# -*- coding: utf-8 -*-
"""
Osoby z Obchodniho rejstriku - pres ARES VR endpoint.
GET /ekonomicke-subjekty-vr/{ico}
"""

from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Optional
import requests

ARES_VR_URL = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty-vr/{ico}"

_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}

def _log(msg: str) -> None:
    try:
        from pathlib import Path
        log = Path(__file__).parent / "ares_debug.log"
        with open(log, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


REQUEST_DELAY = 0.15   # pauza mezi pozadavky (s)
MAX_RETRIES   = 3      # pocet pokusu pri chybe
RETRY_DELAY   = 2.0    # pauza pred retry (s)
SUBJECT_TIMEOUT = 60   # max sekund na jeden subjekt (retry + cekani)

# Debug: prvni odpoved se ulozi sem
DEBUG_PATH = Path(__file__).parent / "vr_debug.json"


def _adresa(adresa: dict | None) -> str:
    """Vraci textovou adresu."""
    if not adresa:
        return ""
    if adresa.get("textovaAdresa"):
        return adresa["textovaAdresa"]
    parts = []
    if adresa.get("nazevUlice"):
        ulice = adresa["nazevUlice"]
        cp = adresa.get("cisloDomovni")
        co = adresa.get("cisloOrientacni")
        if cp and co:
            ulice += f" {cp}/{co}"
        elif cp:
            ulice += f" {cp}"
        parts.append(ulice)
    if adresa.get("nazevObce"):
        obec = adresa["nazevObce"]
        psc = adresa.get("psc")
        if psc:
            obec = f"{psc} {obec}"
        parts.append(obec)
    return ", ".join(parts)


def _full_name(fo: dict) -> str:
    if not fo:
        return ""
    parts = []
    if fo.get("titulPredJmenem"):
        parts.append(fo["titulPredJmenem"])
    if fo.get("jmeno"):
        parts.append(fo["jmeno"])
    if fo.get("prijmeni"):
        parts.append(fo["prijmeni"])
    if fo.get("titulZaJmenem"):
        parts.append(fo["titulZaJmenem"])
    return " ".join(parts).strip()


def _parse_clen(clen: dict, organ_nazev: str) -> Optional[dict]:
    """Parsuje jednoho clena organu - vraci role, jmeno, datum_narozeni, adresa."""
    role = (clen.get("nazevAngazma") or
            clen.get("typAngazma") or
            organ_nazev or
            "clen")

    # Preskoc zaniklé clenstvi
    clenstvi = clen.get("clenstvi", {}) or {}
    if clenstvi.get("zanikClenstvi"):
        return None

    # Fyzicka osoba
    fo = clen.get("fyzickaOsoba", {}) or {}
    if fo:
        jmeno = _full_name(fo)
        if jmeno:
            # Adresa: zkus vsechna mozna pole kde ARES muze vratit bydliste
            adresa_obj = (
                fo.get("bydliste") or      # FyzickaOsobaVr.bydliste
                fo.get("adresa") or        # OsobaVr.adresa (zdedit)
                clen.get("adresa") or      # AngazmaOsobaVr - primo na clenu
                None
            )
            return {
                "role": role,
                "jmeno": jmeno,
                "datum_narozeni": fo.get("datumNarozeni", "") or "",
                "adresa": _adresa(adresa_obj),
            }

    # Pravnicka osoba
    po = clen.get("pravnickaOsoba", {}) or {}
    if po:
        nazev = po.get("obchodniJmeno", "")
        if nazev:
            adresa_obj = po.get("adresa") or clen.get("adresa")
            return {
                "role": role,
                "jmeno": nazev,
                "datum_narozeni": "",
                "adresa": _adresa(adresa_obj),
            }

    return None


def _extract_persons(data: dict) -> list[dict]:
    persons = []
    for zaznam in data.get("zaznamy", []):
        # Statutarni organy
        for organ in zaznam.get("statutarniOrgany", []):
            organ_nazev = organ.get("nazevOrganu", "") or organ.get("typOrganu", "")
            for clen in organ.get("clenoveOrganu", []):
                if clen.get("datumVymazu"):
                    continue
                p = _parse_clen(clen, organ_nazev)
                if p:
                    persons.append(p)
        # Ostatni organy
        for organ in zaznam.get("ostatniOrgany", []):
            organ_nazev = organ.get("nazevOrganu", "") or organ.get("typOrganu", "")
            for clen in organ.get("clenoveOrganu", []):
                if clen.get("datumVymazu"):
                    continue
                p = _parse_clen(clen, organ_nazev)
                if p:
                    persons.append(p)
        # Podnikatel
        for pod in zaznam.get("podnikatel", []):
            if pod.get("datumVymazu"):
                continue
            osoba_wrap = pod.get("osobaPodnikatel", {}) or {}
            fo = osoba_wrap.get("fyzickaOsoba", {}) or {}
            jmeno = _full_name(fo)
            if jmeno:
                adresa_obj = fo.get("bydliste") or fo.get("adresa")
                persons.append({
                    "role": "podnikatel",
                    "jmeno": jmeno,
                    "datum_narozeni": fo.get("datumNarozeni", "") or "",
                    "adresa": _adresa(adresa_obj),
                })
    return persons


def get_or_persons(ico: str, session: requests.Session) -> list[dict]:
    """
    Vraci seznam osob z OR pro dane ICO pres ARES VR endpoint.
    Retry logika: az MAX_RETRIES pokusu, celkovy limit SUBJECT_TIMEOUT sekund.
    Pri neuspech (timeout / chyba / prilis mnoho pokusu) vraci prazdny seznam
    a pokracuje dal - nezaseknе export.
    """
    ico_padded = str(ico).strip().zfill(8)
    url = ARES_VR_URL.format(ico=ico_padded)

    deadline = time.monotonic() + SUBJECT_TIMEOUT

    for attempt in range(1, MAX_RETRIES + 1):
        # Zkontroluj celkovy cas jeste pred spankem
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _log(f"ICO {ico_padded}: celkovy timeout ({SUBJECT_TIMEOUT}s) vypršel, preskakuji")
            return []

        # Zdvorilostni pauza (kratsi pokud zbyvá malo casu)
        sleep_time = REQUEST_DELAY if attempt == 1 else RETRY_DELAY
        time.sleep(min(sleep_time, max(remaining - 1, 0.1)))

        # Dynamicky timeout = zbyvajici cas, max 20s
        req_timeout = min(20, max(int(deadline - time.monotonic()), 3))

        try:
            resp = session.get(url, headers=_HEADERS, timeout=req_timeout)

            if resp.status_code == 404:
                return []  # Subjekt neni v OR - nema smysl retryovat

            if resp.status_code == 429:
                # Too Many Requests - pocka dele a zkusi znovu
                wait = min(5.0 * attempt, deadline - time.monotonic() - 1)
                if wait > 0:
                    _log(f"ICO {ico_padded}: 429 Too Many Requests, cekam {wait:.1f}s (pokus {attempt})")
                    time.sleep(wait)
                continue

            if not resp.ok:
                _log(f"ICO {ico_padded}: HTTP {resp.status_code} (pokus {attempt}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES:
                    continue
                return []

            data = resp.json()

            # Debug: uloz prvni uspesnou odpoved
            if not DEBUG_PATH.exists():
                DEBUG_PATH.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
                )

            return _extract_persons(data)

        except requests.Timeout:
            _log(f"ICO {ico_padded}: timeout po {req_timeout}s (pokus {attempt}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES and time.monotonic() < deadline:
                continue
            return []

        except Exception as e:
            _log(f"ICO {ico_padded}: chyba {type(e).__name__} (pokus {attempt}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES and time.monotonic() < deadline:
                continue
            return []

    return []


def create_session() -> requests.Session:
    return requests.Session()
