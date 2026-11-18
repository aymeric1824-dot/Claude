"""Mise à jour automatique du programme à partir des versions publiées sur GitHub.

Au démarrage, le programme interroge la page « Releases » du dépôt GitHub. Si une version plus
récente existe (et que la mise à jour automatique est activée dans « Mes paramètres ») :
  1. le nouveau programme est téléchargé à côté de l'actuel ;
  2. son empreinte SHA-256 est comparée à celle publiée par GitHub (s'il en publie une) ;
  3. un petit script attend la fermeture du programme, garde l'ancienne version en secours
     (SophosXGS.ancien.exe), met la nouvelle à sa place et la relance.
Rien n'est installé si le téléchargement est incomplet ou si l'empreinte ne correspond pas.
"""
from __future__ import annotations

import hashlib
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
PROGRAMMES = ("SophosXGS.exe", "SophosXGS-console.exe")


class ErreurMiseAJour(Exception):
    pass


def _tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v or "")) or (0,)


def programme_actuel() -> str:
    """Nom du fichier à remplacer : la fenêtre ou le mode texte (jamais l'un par l'autre)."""
    nom = re.split(r"[\\/]", sys.executable)[-1] if getattr(sys, "frozen", False) else ""
    return nom if nom in PROGRAMMES else "SophosXGS.exe"


def installable() -> bool:
    """La mise à jour ne s'installe toute seule que pour le programme Windows (pas avec Python)."""
    return bool(getattr(sys, "frozen", False)) and os.name == "nt"


def verifier(delai: float = 4) -> dict | None:
    """Renvoie {version, url, sha256, taille, notes, page} si une version plus récente existe, sinon None
    (aussi hors connexion : une vérification ratée ne doit jamais gêner l'utilisation)."""
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
    nom = programme_actuel()
    fichier = next((a for a in d.get("assets", []) if a.get("name") == nom), {})
    empreinte = str(fichier.get("digest") or "")
    return {"version": version, "url": fichier.get("browser_download_url"),
            "sha256": empreinte.split(":", 1)[1].lower() if empreinte.startswith("sha256:") else "",
            "taille": int(fichier.get("size") or 0), "notes": d.get("body") or "", "page": d.get("html_url", "")}


def script_remplacement(neuf: Path, exe: Path) -> str:
    """Script Windows qui remplace l'ancien programme par le nouveau, puis le relance.

    Pas de « timeout » : il échoue sans console. On attend avec ping, et on réessaie tant que
    l'ancien programme est encore ouvert (au plus 30 essais d'environ 1 seconde). L'ancienne
    version est gardée en secours ; si la mise en place échoue, elle est remise."""
    ancien = exe.with_name(exe.stem + ".ancien" + exe.suffix)
    return ("@echo off\r\n"
            "set /a n=0\r\n"
            ":attente\r\n"
            "ping -n 2 127.0.0.1 > nul\r\n"
            f'copy /y "{exe}" "{ancien}" > nul 2>&1\r\n'
            f'move /y "{neuf}" "{exe}" > nul 2>&1\r\n'
            "if errorlevel 1 (\r\n"
            "  set /a n+=1\r\n"
            "  if %n% lss 30 goto attente\r\n"
            f'  if exist "{ancien}" copy /y "{ancien}" "{exe}" > nul 2>&1\r\n'
            ")\r\n"
            f'start "" "{exe}"\r\n')


def telecharger(info: dict, destination: Path) -> Path:
    """Télécharge le nouveau programme et vérifie sa taille et son empreinte. Supprime le fichier si c'est faux."""
    if not info.get("url"):
        raise ErreurMiseAJour("la nouvelle version ne contient pas de programme Windows")
    h = hashlib.sha256()
    try:
        with requests.get(info["url"], stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(destination, "wb") as f:
                for bloc in r.iter_content(1 << 16):
                    f.write(bloc)
                    h.update(bloc)
    except requests.exceptions.RequestException as exc:
        destination.unlink(missing_ok=True)
        raise ErreurMiseAJour(f"téléchargement interrompu ({exc.__class__.__name__})") from exc
    taille = destination.stat().st_size
    if taille == 0 or (info.get("taille") and taille != info["taille"]):
        destination.unlink(missing_ok=True)
        raise ErreurMiseAJour("fichier téléchargé incomplet")
    if info.get("sha256") and h.hexdigest() != info["sha256"]:
        destination.unlink(missing_ok=True)
        raise ErreurMiseAJour("l'empreinte du fichier téléchargé ne correspond pas à celle publiée : installation refusée")
    return destination


def installer(info: dict) -> str:
    """Télécharge la nouvelle version et lance son installation. Renvoie « RELANCE » : le programme doit
    alors se fermer (le script le remplace et le relance). Sinon, renvoie un message à afficher."""
    if not installable():
        return (f"Version {info['version']} disponible : {info.get('page') or 'voir GitHub'}. "
                "Avec Python, mettez à jour le dossier (git pull ou nouveau téléchargement).")
    exe = Path(sys.executable)
    neuf = exe.with_name(exe.stem + ".nouveau" + exe.suffix)
    try:
        telecharger(info, neuf)
    except ErreurMiseAJour as exc:
        return f"Mise à jour non installée : {exc}."
    except OSError as exc:      # ex. programme rangé dans un dossier protégé (Program Files)
        return (f"Mise à jour non installée : impossible d'écrire à côté du programme ({exc.strerror}). "
                "Rangez SophosXGS.exe dans un dossier à vous, par exemple Documents\\SophosXGS.")
    script = Path(tempfile.gettempdir()) / "maj_sophosxgs.bat"
    script.write_text(script_remplacement(neuf, exe), encoding="oem" if os.name == "nt" else "utf-8",
                      errors="replace")
    subprocess.Popen(["cmd", "/c", str(script)], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    return "RELANCE"


def mise_a_jour_automatique(afficher=print, delai: float = 4) -> bool:
    """À appeler au démarrage. Renvoie True si une mise à jour est en cours d'installation :
    l'appelant doit alors fermer le programme pour qu'elle se termine."""
    params = charger()
    info = verifier(delai=delai)
    if not info:
        return False
    if not params.get("mise_a_jour_auto", True) or not installable():
        afficher(f"Nouvelle version {info['version']} disponible : menu « Mise à jour du programme ».")
        return False
    afficher(f"Nouvelle version {info['version']} trouvée : téléchargement et vérification...")
    resultat = installer(info)
    if resultat == "RELANCE":
        afficher(f"Version {info['version']} prête : le programme redémarre.")
        return True
    afficher(resultat)
    return False
