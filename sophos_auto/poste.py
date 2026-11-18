"""Réglages propres à ce poste (fichier parametres_poste.json, à côté du programme).

Contrairement à parametres.json (réglages de l'équipe, qui peuvent être partagés), ce fichier
reste sur le PC : nom du technicien, thème de la fenêtre, taille du texte, et l'emplacement
du dossier partagé entre techniciens.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DEFAUTS = {
    "technicien": "",          # apparaît dans l'historique des interventions
    "theme": "clair",          # clair | sombre
    "taille_texte": 10,
    "dossier_partage": "",     # ex. \\\\serveur\\it\\SophosXGS ou un dossier OneDrive synchronisé
}


def dossier_programme() -> Path:
    """Dossier du programme (là où est SophosXGS.exe), ou dossier courant avec Python."""
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path.cwd()


_FICHIER: Path | None = None


def fichier() -> Path:
    global _FICHIER
    if _FICHIER is None:      # retenu au premier appel : le dossier courant peut ensuite devenir le dossier partagé
        _FICHIER = dossier_programme() / "parametres_poste.json"
    return _FICHIER


def charger() -> dict:
    p = dict(DEFAUTS)
    try:
        p.update({k: v for k, v in json.loads(fichier().read_text(encoding="utf-8")).items() if k in DEFAUTS})
    except (OSError, ValueError):
        pass
    return p


def enregistrer(valeurs: dict) -> None:
    p = charger()
    p.update({k: v for k, v in valeurs.items() if k in DEFAUTS})
    fichier().write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")


def appliquer_dossier_partage(afficher=print) -> Path:
    """Travaille dans le dossier partagé s'il est configuré et joignable ; sinon reste en local.
    Renvoie le dossier de travail retenu."""
    fichier()      # fige l'emplacement du fichier du poste avant tout changement de dossier
    partage = str(charger().get("dossier_partage") or "").strip()
    if partage:
        p = Path(partage).expanduser()
        try:
            p.mkdir(parents=True, exist_ok=True)
            essai = p / ".test_ecriture"
            essai.write_text("ok", encoding="utf-8")
            essai.unlink()
            os.chdir(p)
            return p
        except OSError as exc:
            afficher(f"Dossier partagé inaccessible ({partage} : {exc.strerror or exc}). Travail en local pour cette fois.")
    return Path.cwd()
