"""Mise à jour automatique du programme à partir des versions publiées sur GitHub."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

from . import __version__
from .parametres import charger

API = "https://api.github.com/repos/{depot}/releases/latest"


def _tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v or "")) or (0,)


def verifier(delai: float = 4) -> dict | None:
    """Renvoie {version, url, notes} si une version plus récente existe, sinon None (aussi hors connexion)."""
    depot = charger().get("depot_mises_a_jour")
    if not depot:
        return None
    try:
        rep = requests.get(API.format(depot=depot), timeout=delai, headers={"Accept": "application/vnd.github+json"})
        if rep.status_code != 200:
            return None
        d = rep.json()
    except (requests.exceptions.RequestException, ValueError):
        return None
    version = str(d.get("tag_name", "")).lstrip("vV")
    if _tuple(version) <= _tuple(__version__):
        return None
    nom_exe = "SophosXGS.exe"
    url = next((a.get("browser_download_url") for a in d.get("assets", []) if a.get("name") == nom_exe), None)
    return {"version": version, "url": url, "notes": d.get("body") or "", "page": d.get("html_url", "")}


def script_remplacement(neuf: Path, exe: Path) -> str:
    """Script Windows qui remplace l'ancien programme par le nouveau, puis le relance.

    Pas de « timeout » : il échoue sans console. On attend avec ping, et on réessaie tant que
    l'ancien programme est encore ouvert (au plus 30 essais d'environ 1 seconde)."""
    return ("@echo off\r\n"
            "set /a n=0\r\n"
            ":attente\r\n"
            "ping -n 2 127.0.0.1 > nul\r\n"
            f'move /y "{neuf}" "{exe}" > nul 2>&1\r\n'
            "if errorlevel 1 (\r\n"
            "  set /a n+=1\r\n"
            "  if %n% lss 30 goto attente\r\n"
            ")\r\n"
            f'start "" "{exe}"\r\n')


def installer(info: dict) -> str:
    """Télécharge la nouvelle version et la met en place au prochain démarrage (programme Windows uniquement)."""
    if not getattr(sys, "frozen", False) or os.name != "nt":
        return (f"Version {info['version']} disponible : {info.get('page') or 'voir GitHub'}. "
                "Avec Python, mettez à jour le dossier (git pull ou nouveau téléchargement).")
    if not info.get("url"):
        return "Nouvelle version trouvée, mais sans programme Windows joint : téléchargez-la depuis GitHub."
    exe = Path(sys.executable)
    neuf = exe.with_suffix(".nouveau.exe")
    with requests.get(info["url"], stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(neuf, "wb") as f:
            for bloc in r.iter_content(1 << 16):
                f.write(bloc)
    script = Path(tempfile.gettempdir()) / "maj_sophosxgs.bat"
    script.write_text(script_remplacement(neuf, exe), encoding="oem" if os.name == "nt" else "utf-8",
                      errors="replace")
    subprocess.Popen(["cmd", "/c", str(script)], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    return "RELANCE"
