# -*- coding: utf-8 -*-
"""ARES v3 REST API klient.

Overeno: kodObce funguje jako STRING (ne integer)!
ARES web posilá: sidlo: { "kodObce": "547034" } (string)
My jsme posilali: sidlo: { "kodObce": 547034 } (integer) -> 0 vysledku
"""

from __future__ import annotations
import json
import threading
from pathlib import Path
from typing import Any, Callable, Optional
import requests

SEARCH_URL = (
    "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest"
    "/ekonomicke-subjekty/vyhledat"
)
PAGE_SIZE = 1000

_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}

LOG_PATH = Path(__file__).parent / "ares_debug.log"
_TOO_MANY = "VYSTUP_PRILIS_MNOHO_VYSLEDKU"


def _log(msg: str) -> None:
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


def _build_payload(
    pravni_forma: Optional[str],
    kod_obce: Optional[str],
    textova_adresa: Optional[str],
    start: int,
    pocet: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"start": start, "pocet": pocet}
    if pravni_forma and str(pravni_forma).strip():
        payload["pravniForma"] = [str(pravni_forma).strip().zfill(3)]
    # Sidlo: pouzij jen vyplnena pole, kombinuji se (AND)
    sidlo: dict[str, Any] = {}
    if kod_obce and str(kod_obce).strip():
        sidlo["kodObce"] = str(kod_obce).strip()
    if textova_adresa and textova_adresa.strip():
        sidlo["textovaAdresa"] = textova_adresa.strip()
    if sidlo:
        payload["sidlo"] = sidlo
    return payload


def _post(session: requests.Session, payload: dict) -> dict:
    _log("\n=== REQUEST ===")
    _log("PAYLOAD: " + json.dumps(payload, ensure_ascii=False))
    try:
        resp = session.post(SEARCH_URL, json=payload, headers=_HEADERS, timeout=45)
    except Exception as e:
        _log("CONNECTION ERROR: " + str(e))
        raise

    _log("HTTP STATUS: " + str(resp.status_code))
    _log("RESPONSE (first 500): " + resp.text[:500])

    if resp.status_code == 400:
        try:
            err = resp.json()
            if err.get("subKod") == _TOO_MANY:
                raise ValueError(
                    "Dotaz vraci prilis mnoho vysledku.\n\n"
                    "ARES povoluje maximalne 1 000 vysledku.\n"
                    "Zpresni hledani - pridej obec ze seznamu nebo cast adresy."
                )
        except ValueError:
            raise
        except Exception:
            pass
        raise requests.HTTPError("HTTP 400 - " + resp.text[:200], response=resp)

    if not resp.ok:
        try:
            popis = resp.json().get("popis", resp.text[:200])
        except Exception:
            popis = resp.text[:200]
        raise requests.HTTPError("HTTP " + str(resp.status_code) + " - " + popis, response=resp)

    return resp.json()


def fetch_all(
    pravni_forma: Optional[str] = None,
    kod_obce: Optional[str] = None,
    textova_adresa: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    cancel_flag: Optional[threading.Event] = None,
) -> list[dict[str, Any]]:
    try:
        LOG_PATH.unlink(missing_ok=True)
    except Exception:
        pass

    _log("fetch_all: pravni_forma=" + repr(pravni_forma) + " kod_obce=" + repr(kod_obce) + " textova_adresa=" + repr(textova_adresa))

    session = requests.Session()
    results: list[dict[str, Any]] = []
    start = 0
    total: Optional[int] = None

    while True:
        if cancel_flag and cancel_flag.is_set():
            raise InterruptedError("Stazeni zruseno.")

        payload = _build_payload(pravni_forma, kod_obce, textova_adresa, start, PAGE_SIZE)
        data = _post(session, payload)

        if total is None:
            total = data.get("pocetCelkem", 0)
            _log("TOTAL: " + str(total))
            if progress_callback:
                progress_callback(0, max(total, 1),
                    "ARES: Nalezeno " + f"{total:,}" + " subjektu. Stahuji...")

        page_items: list[dict] = data.get("ekonomickeSubjekty", [])
        results.extend(page_items)

        if progress_callback and total:
            progress_callback(len(results), total,
                "ARES: Nacteno " + f"{len(results):,}" + " / " + f"{total:,}")

        if not page_items or len(results) >= (total or 0):
            break

        start += PAGE_SIZE

    _log("DONE - " + str(len(results)) + " vysledku")
    return results


def flatten_subject(subj: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in subj.items():
        if isinstance(value, dict):
            for sk, sv in value.items():
                if isinstance(sv, dict):
                    for ssk, ssv in sv.items():
                        flat[f"{key}_{sk}_{ssk}"] = ssv
                elif isinstance(sv, list):
                    flat[f"{key}_{sk}"] = "; ".join(str(v) for v in sv)
                else:
                    flat[f"{key}_{sk}"] = sv
        elif isinstance(value, list):
            flat[key] = "; ".join(str(v) for v in value)
        else:
            flat[key] = value
    return flat
