"""Clients prêts à envoyer : préparés (même sans réseau, chez soi), en attente d'être envoyés sur leur pare-feu.

L'assistant ajoute le client quand on répond « plus tard » à l'envoi ; un envoi réussi le retire.
L'accueil affiche un bouton par client en attente.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

FICHIER = Path("clients") / "a_envoyer.json"


def lister() -> list[dict]:
    try:
        d = json.loads(FICHIER.read_text(encoding="utf-8"))
        return [x for x in d if isinstance(x, dict) and Path(x.get("fichier", "")).exists()]
    except (OSError, ValueError):
        return []


def _ecrire(liste: list[dict]) -> None:
    FICHIER.parent.mkdir(parents=True, exist_ok=True)
    FICHIER.write_text(json.dumps(liste, ensure_ascii=False, indent=1), encoding="utf-8")


def _meme(a: str, b: str) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return a == b


def ajouter(client: str, fichier: str) -> None:
    liste = [x for x in lister() if not _meme(x["fichier"], fichier)]
    liste.append({"client": client, "fichier": str(Path(fichier)), "date": dt.datetime.now().isoformat(timespec="minutes")})
    _ecrire(liste)


def retirer(fichier: str) -> None:
    avant = lister()
    apres = [x for x in avant if not _meme(x["fichier"], fichier)]
    if len(apres) != len(avant):
        _ecrire(apres)
