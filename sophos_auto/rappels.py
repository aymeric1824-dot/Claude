"""Rappels : ce qu'il faudrait refaire chez vos clients, d'après l'historique des interventions.

Seuls des faits connus de l'outil sont utilisés : dates des contrôles de sécurité et des
sauvegardes Sophos Central, note de sécurité, écarts de conformité, firmware vu dans Central.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from . import historique

DELAI_AUDIT = 90          # jours sans contrôle de sécurité
DELAI_SAUVEGARDE = 30     # jours sans sauvegarde Sophos Central (pour les clients déjà sauvegardés par Central)
NOTE_FAIBLE = 50


@dataclass
class Rappel:
    client: str
    urgence: int        # 1 = important, 2 = à prévoir
    texte: str


def _age(entree: dict, maintenant: dt.datetime) -> int:
    try:
        return (maintenant - dt.datetime.fromisoformat(entree["date"])).days
    except (KeyError, ValueError):
        return 0


def calculer(maintenant: dt.datetime | None = None) -> list[Rappel]:
    maintenant = maintenant or dt.datetime.now()
    rappels: list[Rappel] = []
    par_client: dict[str, list[dict]] = {}
    for e in historique.lire():
        par_client.setdefault(e.get("client", ""), []).append(e)
    for client, entrees in par_client.items():
        derniere = {}
        for e in entrees:
            derniere[e.get("action")] = e
        audit = derniere.get("audit")
        if audit is None and "application" in derniere:
            rappels.append(Rappel(client, 2, "aucun contrôle de sécurité depuis la configuration"))
        elif audit is not None:
            if _age(audit, maintenant) > DELAI_AUDIT:
                rappels.append(Rappel(client, 2, f"dernier contrôle de sécurité il y a {_age(audit, maintenant)} jours"))
            note = audit.get("note")
            if isinstance(note, int) and note < NOTE_FAIBLE:
                rappels.append(Rappel(client, 1, f"note de sécurité faible ({note}/100) : corrigez les points critiques"))
        sauvegarde = derniere.get("sauvegarde_central")
        if sauvegarde is not None and _age(sauvegarde, maintenant) > DELAI_SAUVEGARDE:
            rappels.append(Rappel(client, 2, f"dernière sauvegarde Central il y a {_age(sauvegarde, maintenant)} jours"))
        if sauvegarde is not None and sauvegarde.get("firmware_ancien"):
            rappels.append(Rappel(client, 1, f"firmware {sauvegarde.get('firmware')} : mise à jour conseillée"))
        conf = derniere.get("conformite")
        if conf is not None and conf.get("ecarts"):
            plus_recent = max(derniere.get("application", {}).get("date", ""), conf.get("date", ""))
            if plus_recent == conf.get("date"):
                rappels.append(Rappel(client, 1, f"{conf['ecarts']} écart(s) de conformité non corrigé(s)"))
        app = derniere.get("application")
        if app is not None and app.get("echecs"):
            if app.get("date", "") >= max((e.get("date", "") for e in entrees if e.get("action") == "application"), default=""):
                rappels.append(Rappel(client, 1, f"la dernière application a eu {app['echecs']} échec(s)"))
    return sorted(rappels, key=lambda r: (r.urgence, r.client.lower()))
