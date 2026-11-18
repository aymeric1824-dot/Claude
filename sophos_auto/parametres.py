"""Vos paramètres (enregistrés dans parametres.json, à côté du programme).

Rien de secret n'est enregistré ici : uniquement le nom de votre société (affiché dans
les rapports remis aux clients), l'adresse e-mail du support et les valeurs proposées
par défaut (IP du pare-feu, compte administrateur, fuseau horaire).
"""
from __future__ import annotations

import json
from pathlib import Path

FICHIER = Path("parametres.json")
DEFAUTS = {
    "societe": "",                 # ex. « InfoServices 69 » : apparaît dans les rapports
    "email_support": "",           # proposé comme destinataire des alertes
    "ip_defaut": "172.16.16.16",
    "utilisateur_defaut": "admin",
    "fuseau_defaut": "Europe/Paris",
    "prefixe_admin": "admin-presta",   # identifiant proposé pour le compte administrateur nominatif
    "depot_mises_a_jour": "aymeric1824-dot/Claude",   # dépôt GitHub des nouvelles versions (vide = jamais)
    "mise_a_jour_auto": True,      # installer seul les nouvelles versions au démarrage (sinon : simple message)
}


def charger() -> dict:
    p = dict(DEFAUTS)
    try:
        p.update({k: v for k, v in json.loads(FICHIER.read_text(encoding="utf-8")).items() if k in DEFAUTS})
    except (OSError, ValueError):
        pass
    return p


def enregistrer(valeurs: dict) -> None:
    p = charger()
    p.update({k: v for k, v in valeurs.items() if k in DEFAUTS})
    FICHIER.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
