"""Historique des interventions : qui a fait quoi, quand, sur quel client.

Une ligne JSON par intervention dans clients/historique/<client>.jsonl : ajouter une ligne ne
modifie jamais les précédentes, ce qui convient aussi à un dossier partagé entre techniciens.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

DOSSIER = Path("clients") / "historique"
LIBELLES = {
    "creation": "Configuration préparée (assistant)", "application": "Configuration appliquée",
    "simulation": "Simulation", "audit": "Contrôle de sécurité", "conformite": "Vérification de conformité",
    "restauration": "Retour en arrière", "sauvegarde_central": "Sauvegarde Sophos Central",
    "import_central": "Import Sophos Central", "duplication": "Client créé par duplication",
}


def _slug(nom: str) -> str:
    t = (nom or "sans-nom").lower()
    for a, b in (("éèêë", "e"), ("àâä", "a"), ("îï", "i"), ("ôö", "o"), ("ùûü", "u"), ("ç", "c")):
        for ch in a:
            t = t.replace(ch, b)
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:40] or "sans-nom"


def enregistrer(client: str, action: str, resultat: str = "", **details) -> None:
    """Ajoute une intervention. Ne fait jamais échouer l'action principale."""
    try:
        from .poste import charger
        DOSSIER.mkdir(parents=True, exist_ok=True)
        ligne = {"date": dt.datetime.now().isoformat(timespec="seconds"), "client": client, "action": action,
                 "resultat": resultat, "technicien": charger().get("technicien", ""),
                 **{k: (str(v) if isinstance(v, Path) else v) for k, v in details.items()}}
        with open(DOSSIER / f"{_slug(client)}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    except Exception:  # l'historique est un confort : jamais bloquant
        pass


def lire(client: str | None = None) -> list[dict]:
    """Interventions d'un client (ou de tous), de la plus ancienne à la plus récente."""
    fichiers = [DOSSIER / f"{_slug(client)}.jsonl"] if client else sorted(DOSSIER.glob("*.jsonl"))
    entrees = []
    for f in fichiers:
        try:
            for l in f.read_text(encoding="utf-8").splitlines():
                try:
                    entrees.append(json.loads(l))
                except ValueError:
                    continue
        except OSError:
            continue
    return sorted(entrees, key=lambda e: e.get("date", ""))


def clients() -> list[str]:
    """Noms des clients qui ont un historique (nom le plus récent enregistré)."""
    noms = {}
    for e in lire():
        noms[_slug(e.get("client", ""))] = e.get("client", "")
    return sorted(noms.values(), key=str.lower)


def resume(entree: dict) -> str:
    date = entree.get("date", "")[:16].replace("T", " ")
    qui = f" — {entree['technicien']}" if entree.get("technicien") else ""
    res = f" : {entree['resultat']}" if entree.get("resultat") else ""
    return f"{date}{qui} — {LIBELLES.get(entree.get('action'), entree.get('action'))}{res}"
