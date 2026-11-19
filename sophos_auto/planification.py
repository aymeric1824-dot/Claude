"""Rapport mensuel automatique : une tâche planifiée Windows qui prépare le tableau de bord le 1er du mois.

La tâche lance l'outil en mode « rapport mensuel » (sans fenêtre) : tableau de bord de tous les clients et liste
des rappels, enregistrés dans le dossier rapports. Aucun pare-feu n'est contacté et aucun mot de passe n'est
nécessaire. La tâche est créée pour l'utilisateur Windows connecté (pas besoin d'être administrateur).
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

NOM_TACHE = "SophosXGS - rapport mensuel"


def commande(dossier: Path | None = None) -> str:
    """Ligne de commande lancée par la tâche (programme .exe ou Python)."""
    dossier = (dossier or Path.cwd()).resolve()
    if getattr(sys, "frozen", False):
        programme = f'"{Path(sys.executable).resolve()}" --rapport-mensuel'
    else:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        exe = pythonw if pythonw.exists() else Path(sys.executable)
        lanceur = Path(__file__).resolve().parent.parent / "lanceur.py"
        programme = f'"{exe}" "{lanceur}" --rapport-mensuel'
    return f'cmd /c cd /d "{dossier}" && {programme}'


def _schtasks(*arguments: str) -> tuple[bool, str]:
    if os.name != "nt":
        return False, "Les tâches planifiées n'existent que sous Windows."
    try:
        r = subprocess.run(["schtasks", *arguments], capture_output=True, text=True, timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.returncode == 0, (r.stdout or r.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def creer(heure: str = "08:00") -> tuple[bool, str]:
    return _schtasks("/Create", "/F", "/SC", "MONTHLY", "/D", "1", "/ST", heure, "/TN", NOM_TACHE, "/TR", commande())


def supprimer() -> tuple[bool, str]:
    return _schtasks("/Delete", "/F", "/TN", NOM_TACHE)


def existe() -> bool:
    return _schtasks("/Query", "/TN", NOM_TACHE)[0]


def rapport_mensuel() -> Path:
    """Ce que fait la tâche : tableau de bord et rappels du mois."""
    from .rappels import calculer
    from .tableau import page
    f = page(Path("rapports") / f"rapport_mensuel_{dt.date.today():%Y-%m}.html")
    rappels = calculer()
    texte = [f"Rapport du {dt.date.today():%d/%m/%Y}", f"{len(rappels)} rappel(s)", ""]
    texte += [f"{'IMPORTANT' if r.urgence == 1 else 'à prévoir'} — {r.client} : {r.texte}" for r in rappels]
    f.with_suffix(".txt").write_text("\n".join(texte) + "\n", encoding="utf-8")
    return f
