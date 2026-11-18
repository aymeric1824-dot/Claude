"""Coffre-fort KeePass (.kdbx) chiffré contenant les mots de passe d'un client."""
from __future__ import annotations

from pathlib import Path


def creer_coffre(chemin: str, mot_de_passe_principal: str, client: str, secrets: dict[str, str]) -> str:
    """Crée (ou remplace) un fichier KeePass avec un groupe par client et une entrée par mot de passe."""
    from pykeepass import create_database
    f = Path(chemin)
    if f.exists():
        f.unlink()
    kp = create_database(str(f), password=mot_de_passe_principal)
    groupe = kp.add_group(kp.root_group, client or "Client")
    for libelle, valeur in sorted(secrets.items()):
        utilisateur = ""
        if libelle.startswith("Mot de passe du compte "):
            utilisateur = libelle.removeprefix("Mot de passe du compte ")
        kp.add_entry(groupe, libelle, utilisateur, valeur, notes=f"Pare-feu Sophos — {client}")
    kp.save()
    return str(f)
