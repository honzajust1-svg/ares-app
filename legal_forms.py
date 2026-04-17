"""Číselník právních forem ARES – seřazeno dle kódu."""

COMMON_FORMS: list[tuple[str, str]] = sorted([
    ("101", "Veřejná obchodní společnost"),
    ("105", "Evropské hospodářské zájmové sdružení"),
    ("111", "Komanditní společnost"),
    ("112", "Společnost s ručením omezeným (s.r.o.)"),
    ("114", "Zjednodušená akciová společnost (z.a.s.)"),
    ("117", "Evropská společnost"),
    ("121", "Akciová společnost (a.s.)"),
    ("131", "Svěřenský fond"),
    ("141", "Obecně prospěšná společnost"),
    ("145", "Společenství vlastníků jednotek (SVJ)"),
    ("161", "Ústav"),
    ("201", "Fyzická osoba – živnostník (ŽL)"),
    ("205", "Fyzická osoba – jiný zákon"),
    ("211", "Družstvo"),
    ("221", "Sociální družstvo"),
    ("231", "Bytové družstvo"),
    ("241", "Výrobní družstvo"),
    ("242", "Spotřební družstvo"),
    ("251", "Zemědělské družstvo"),
    ("261", "Družstevní záložna"),
    ("271", "Pojišťovací družstvo"),
    ("301", "Státní podnik"),
    ("311", "Národní podnik"),
    ("321", "Příspěvková organizace"),
    ("325", "Organizační složka státu"),
    ("331", "Obec"),
    ("332", "Kraj"),
    ("333", "Hlavní město Praha"),
    ("334", "Statutární město"),
    ("335", "Městský obvod"),
    ("336", "Městská část hl. m. Prahy"),
    ("341", "Vojenská správa"),
    ("342", "Svazek obcí"),
    ("343", "Region soudržnosti"),
    ("381", "Veřejná výzkumná instituce"),
    ("391", "Zdravotní pojišťovna"),
    ("401", "Banka (a.s.)"),
    ("411", "Spořitelní a úvěrové družstvo"),
    ("421", "Nadace"),
    ("422", "Nadační fond"),
    ("431", "Politická strana"),
    ("432", "Politické hnutí"),
    ("441", "Církev a náboženská společnost"),
    ("442", "Evidovaná právnická osoba"),
    ("521", "Odborová organizace"),
    ("525", "Organizace zaměstnavatelů"),
    ("601", "Komora podnikatelů"),
    ("641", "Profesní komora zřízená zákonem"),
    ("651", "Hospodářská komora"),
    ("701", "Spolek"),
    ("711", "Pobočný spolek"),
    ("721", "Mezinárodní organizace"),
    ("745", "Honební společenstvo"),
    ("751", "Zahraniční fyzická osoba"),
    ("761", "Organizační složka zahraniční osoby"),
    ("771", "Zahraniční právnická osoba"),
    ("801", "Česká národní banka"),
    ("805", "Státní fond"),
    ("906", "Veřejná prospěšná společnost"),
    ("910", "Právnická osoba zřízená zákonem"),
], key=lambda x: int(x[0]))

ALL_FORMS: dict[str, str] = {code: name for code, name in COMMON_FORMS}
DROPDOWN_OPTIONS: list[str] = [f"{code} – {name}" for code, name in COMMON_FORMS]
DEFAULT_FORM: str = next((opt for opt in DROPDOWN_OPTIONS if opt.startswith("145")), "")


def parse_dropdown_code(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    for sep in (" – ", " - ", " "):
        if sep in value:
            code = value.split(sep)[0].strip()
            if code.isdigit():
                return code
    return value if value.isdigit() else None


def code_to_name(code: str) -> str:
    return ALL_FORMS.get(str(code), str(code))
