# ARES + Obchodní rejstřík – Webová aplikace

## Nasazení na Streamlit Cloud (zdarma)

### 1. Nahraj kód na GitHub

Vytvoř nový **privátní** nebo veřejný repozitář na github.com a nahraj všechny soubory z této složky:

```
app.py
requirements.txt
ares_client.py
or_scraper.py
exporter.py
legal_forms.py
obce_db.py
.streamlit/config.toml
```

Nejjednodušeji přes GitHub web – „Add file → Upload files".

### 2. Nasaď na Streamlit Cloud

1. Jdi na **share.streamlit.io** a přihlas se přes GitHub
2. Klikni **„New app"**
3. Vyber svůj repozitář, větev `main`, soubor `app.py`
4. Klikni **„Deploy"**

Za ~2 minuty je aplikace živá na adrese jako:
`https://tvoje-jmeno-ares-app.streamlit.app`

### 3. Lokální spuštění (volitelné)

```bash
pip install streamlit requests openpyxl lxml beautifulsoup4
streamlit run app.py
```

## Soubory

| Soubor | Popis |
|--------|-------|
| `app.py` | Streamlit GUI |
| `ares_client.py` | ARES REST API klient |
| `or_scraper.py` | OR osoby přes ARES VR API |
| `exporter.py` | Export do Excelu |
| `legal_forms.py` | Číselník právních forem |
| `obce_db.py` | Offline databáze 6 280 obcí ČR |
| `.streamlit/config.toml` | Tmavý vzhled |
