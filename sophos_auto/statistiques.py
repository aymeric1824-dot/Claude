"""Statistiques des questions : où les utilisateurs hésitent ou se trompent le plus.

Tout reste dans le fichier statistiques_questions.json (dans le dossier de travail, donc le dossier partagé
de l'équipe s'il y en a un). Rien n'est envoyé ailleurs. Seuls le texte des questions et des compteurs sont
enregistrés : jamais les réponses.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

FICHIER = Path("statistiques_questions.json")
EVENEMENTS = ("posee", "aide", "erreur", "retour")
_verrou = threading.Lock()


def lire() -> dict[str, dict[str, int]]:
    try:
        return json.loads(FICHIER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def noter(question: str, evenement: str) -> None:
    if evenement not in EVENEMENTS or not question:
        return
    with _verrou:
        d = lire()
        q = d.setdefault(question, {e: 0 for e in EVENEMENTS})
        q[evenement] = q.get(evenement, 0) + 1
        try:
            FICHIER.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass


def difficultes(n: int = 15) -> list[tuple[str, dict[str, int], float]]:
    """Questions les plus difficiles : (question, compteurs, score). Score = (aides + erreurs + retours) / posées."""
    lignes = []
    for q, c in lire().items():
        posees = max(1, c.get("posee", 0))
        score = (c.get("aide", 0) + 2 * c.get("erreur", 0) + c.get("retour", 0)) / posees
        if score > 0:
            lignes.append((q, c, score))
    lignes.sort(key=lambda x: (-x[2], -x[1].get("posee", 0)))
    return lignes[:n]
