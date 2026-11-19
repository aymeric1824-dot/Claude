"""Conversion d'une page HTML (dossier technique, rapport) en PDF, sans rien installer.

On utilise le navigateur déjà présent sur le PC (Microsoft Edge, ou Google Chrome) en mode « sans fenêtre ».
Si aucun navigateur n'est trouvé, on renvoie None : la page HTML reste disponible et imprimable.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

NAVIGATEURS = [
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
    r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
]


def navigateur() -> str | None:
    for chemin in NAVIGATEURS:
        p = os.path.expandvars(chemin)
        if "%" not in p and Path(p).is_file():
            return p
    for nom in ("msedge", "chrome", "chromium", "google-chrome", "chromium-browser"):
        trouve = shutil.which(nom)
        if trouve:
            return trouve
    return None


def en_pdf(page_html: str | Path, destination: str | Path | None = None, delai: int = 90) -> Path | None:
    """Crée le PDF à côté de la page HTML (même nom, extension .pdf). Renvoie son chemin, ou None."""
    source = Path(page_html).resolve()
    cible = Path(destination).resolve() if destination else source.with_suffix(".pdf")
    exe = navigateur()
    if not exe or not source.is_file():
        return None
    cible.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="sophosxgs_pdf_") as profil:   # profil à part : Edge peut être ouvert
        commande = [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-pdf-header-footer",
                    f"--user-data-dir={profil}", f"--print-to-pdf={cible}", source.as_uri()]
        try:
            subprocess.run(commande, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=delai,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            return None
    return cible if cible.is_file() and cible.stat().st_size > 0 else None
