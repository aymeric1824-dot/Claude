"""« Demander de l'aide » : un dossier .zip avec tout ce qu'il faut à un expert pour comprendre le problème.

Contenu : la description du problème, l'état de la connexion au pare-feu, la configuration réseau du PC,
la version de l'outil, le fichier Excel du client, ses derniers rapports et son historique.
Les mots de passe ne sont jamais ajoutés (ils sont retirés du fichier Excel s'il en contient).
Le dossier est rangé dans « assistance » (dans le dossier partagé de l'équipe s'il y en a un).
"""
from __future__ import annotations

import datetime as dt
import io
import json
import zipfile
from pathlib import Path

DOSSIER = Path("assistance")


def _excel_sans_secrets(fichier: Path) -> bytes:
    from openpyxl import load_workbook

    from .schema import GENERAL, SECRETS
    wb = load_workbook(fichier)
    colonnes = {}
    for onglet, colonne in SECRETS:
        colonnes.setdefault(onglet, set()).add(colonne)
    for onglet, cols in colonnes.items():
        if onglet in wb.sheetnames:
            ws = wb[onglet]
            entetes = [str(c.value or "") for c in ws[1]]
            for i, nom in enumerate(entetes):
                if nom in cols:
                    for ligne in ws.iter_rows(min_row=2, min_col=i + 1, max_col=i + 1):
                        if ligne[0].value:
                            ligne[0].value = "(retiré)"
    secrets_generaux = {p for p, _, _, _, s in GENERAL if s}
    if "Général" in wb.sheetnames:
        for ligne in wb["Général"].iter_rows(min_row=2):
            if ligne[0].value in secrets_generaux and len(ligne) > 1 and ligne[1].value:
                ligne[1].value = "(retiré)"
    tampon = io.BytesIO()
    wb.save(tampon)
    return tampon.getvalue()


def creer(message: str = "", client: str = "", journal: str = "", connexion: dict | None = None) -> Path:
    from . import __version__, historique
    DOSSIER.mkdir(parents=True, exist_ok=True)
    nom = "".join(c if c.isalnum() or c in "-_" else "_" for c in (client or "general"))[:40]
    f = DOSSIER / f"aide_{nom}_{dt.datetime.now():%Y-%m-%d_%H%M}.zip"
    with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as z:
        resume = [f"Demande d'aide — {dt.datetime.now():%d/%m/%Y %H:%M}", f"Version de l'outil : {__version__}",
                  f"Client : {client or '(non précisé)'}", "", "Problème décrit :", message or "(non précisé)", ""]
        if connexion:
            resume += ["Connexion au pare-feu :"] + [f"  {k} : {v}" for k, v in connexion.items()]
        try:
            from .reseau import cartes_pc
            resume += ["", "Cartes réseau du PC :"] + [f"  {c.nom} : {c.ip}/{c.prefixe} passerelle {c.passerelle} "
                                                       f"DHCP={'oui' if c.dhcp else 'non'}" for c in cartes_pc()]
        except Exception:
            pass
        z.writestr("LISEZ-MOI.txt", "\n".join(resume) + "\n")
        if journal:
            z.writestr("deroulement.txt", journal)
        if client:
            slug = historique._slug(client)
            for x in sorted(Path("clients").glob("*.xlsx")) if Path("clients").exists() else []:
                if historique._slug(x.stem) == slug or slug in historique._slug(x.stem):
                    try:
                        z.writestr(f"client/{x.name}", _excel_sans_secrets(x))
                    except Exception:
                        pass
            entrees = historique.lire(client)
            if entrees:
                z.writestr("client/historique.json", json.dumps(entrees, ensure_ascii=False, indent=1))
            rapports = sorted(Path("rapports").glob(f"*{nom}*"), key=lambda p: p.stat().st_mtime)[-6:] \
                if Path("rapports").exists() else []
            for r in rapports:
                if r.suffix in (".html", ".txt") and r.stat().st_size < 5_000_000:
                    z.write(r, f"rapports/{r.name}")
    return f
