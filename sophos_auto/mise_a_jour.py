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
    script.write_text(
        "@echo off\r\n"
        "timeout /t 2 /nobreak > nul\r\n"
        f'move /y "{neuf}" "{exe}" > nul\r\n'
        f'start "" "{exe}"\r\n', encoding="ascii", errors="replace")
    subprocess.Popen(["cmd", "/c", str(script)], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    return "RELANCE"
