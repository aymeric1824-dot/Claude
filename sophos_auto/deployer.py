"""Applique un fichier Excel client sur un Sophos XGS via l'API XML.

Exemples :
    python -m sophos_auto.deployer client.xlsx --simulation   # vérifie, n'envoie rien
    python -m sophos_auto.deployer client.xlsx                # applique
    python -m sophos_auto.deployer --lire IPHost --ip 172.16.16.16   # affiche des objets existants
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import os
import sys
from pathlib import Path

from .api import ErreurAPI, ErreurConnexion, SophosAPI, to_xml
from .modele import ORDRE_DEPLOIEMENT, lire_classeur

VERT, ROUGE, JAUNE, GRIS, FIN = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m"
if os.name == "nt":
    os.system("")  # active les couleurs dans la console Windows


def _mot_de_passe(utilisateur: str) -> str:
    mdp = os.environ.get("SOPHOS_MOT_DE_PASSE")
    return mdp if mdp else getpass.getpass(f"Mot de passe de « {utilisateur} » : ")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Paramétrage automatique d'un Sophos XGS à partir d'un fichier Excel.")
    p.add_argument("fichier", nargs="?", help="Fichier Excel du client")
    p.add_argument("--simulation", action="store_true", help="Vérifie le fichier et montre ce qui serait envoyé, sans rien envoyer")
    p.add_argument("--ip", help="IP du pare-feu (remplace celle du fichier)")
    p.add_argument("--port", type=int, help="Port d'administration (remplace celui du fichier)")
    p.add_argument("--utilisateur", help="Utilisateur admin (remplace celui du fichier)")
    p.add_argument("--verifier-certificat", action="store_true", help="Refuser les certificats auto-signés")
    p.add_argument("--lire", metavar="TYPE", help="Affiche les objets existants d'un type (ex. IPHost, FirewallRule, Zone, VLAN, Interface)")
    p.add_argument("--continuer", action="store_true", help="Ne pas s'arrêter s'il y a des erreurs dans le fichier")
    a = p.parse_args(argv)

    if a.lire:
        api = SophosAPI(a.ip or "172.16.16.16", a.utilisateur or "admin", _mot_de_passe(a.utilisateur or "admin"),
                        port=a.port or 4444, verifier_certificat=a.verifier_certificat)
        try:
            print(to_xml({a.lire: api.lire(a.lire) or {}}))
        except ErreurAPI as exc:
            print(f"{ROUGE}{exc}{FIN}")
            return 1
        return 0

    if not a.fichier:
        p.error("indiquez le fichier Excel du client")
    if not Path(a.fichier).exists():
        print(f"{ROUGE}Fichier introuvable : {a.fichier}{FIN}")
        return 1

    # ------------------------------------------------------------ 1. lecture et contrôle
    print(f"Lecture de {a.fichier}...")
    cfg = lire_classeur(a.fichier)
    g = cfg.general
    client = g.get("Nom du client") or Path(a.fichier).stem
    print(f"Client : {client} — {len(cfg.objets)} élément(s) à appliquer\n")
    for w in cfg.avertissements:
        print(f"{JAUNE}  ! {w}{FIN}")
    for e in cfg.erreurs:
        print(f"{ROUGE}  ✘ {e}{FIN}")
    if cfg.erreurs and not a.continuer:
        print(f"\n{ROUGE}{len(cfg.erreurs)} erreur(s) dans le fichier : corrigez-les puis relancez "
              f"(ou ajoutez --continuer pour ignorer ces lignes).{FIN}")
        return 1

    cfg.objets.sort(key=lambda o: ORDRE_DEPLOIEMENT.index(o.onglet))

    # ------------------------------------------------------------ 2. simulation
    if a.simulation:
        dossier = Path("simulation") / client
        dossier.mkdir(parents=True, exist_ok=True)
        for i, o in enumerate(cfg.objets, start=1):
            xml = f'<Set operation="add">\n{to_xml({o.balise: o.contenu})}\n</Set>\n'
            (dossier / f"{i:03d}_{o.balise}_{_fichier(o.nom)}.xml").write_text(xml, encoding="utf-8")
            print(f"  {GRIS}{i:3d}.{FIN} [{o.onglet}] {o.nom}")
        print(f"\n{VERT}Simulation terminée : rien n'a été envoyé. Requêtes XML dans {dossier}/{FIN}")
        return 0

    # ------------------------------------------------------------ 3. application
    ip = a.ip or g["Adresse IP du pare-feu"]
    port = a.port or int(g["Port d'administration"] or 4444)
    utilisateur = a.utilisateur or g["Utilisateur admin"]
    api = SophosAPI(ip, utilisateur, _mot_de_passe(utilisateur), port=port, verifier_certificat=a.verifier_certificat)
    print(f"Connexion à {ip}:{port}...")
    try:
        api.tester_connexion()
    except ErreurAPI as exc:
        print(f"{ROUGE}✘ {exc}{FIN}")
        return 1
    print(f"{VERT}✔ Connecté{FIN}\n")

    journal, nb_ok, nb_ko = [], 0, 0
    for o in cfg.objets:
        libelle = f"[{o.onglet}] {o.nom}"
        try:
            if o.balise == "AdminSettings":  # réglage unique : toujours une mise à jour
                res, action = api.ecrire(o.balise, o.contenu, "update"), "mis à jour"
            else:
                res, action = api.ecrire_ou_mettre_a_jour(o.balise, o.contenu)
        except ErreurConnexion as exc:
            print(f"{ROUGE}✘ Connexion perdue : {exc}{FIN}")
            journal.append(f"ARRÊT  {libelle} : {exc}")
            nb_ko += 1
            break
        except ErreurAPI as exc:
            res, action = None, str(exc)
        if res and res.ok:
            nb_ok += 1
            print(f"{VERT}  ✔{FIN} {libelle} {GRIS}({action}){FIN}")
            journal.append(f"OK     {libelle} ({action})")
        else:
            nb_ko += 1
            detail = f"{res.code} : {res.message}" if res else action
            print(f"{ROUGE}  ✘ {libelle} — {detail}{FIN}")
            journal.append(f"ERREUR {libelle} — {detail}")

    # ------------------------------------------------------------ 4. rapport
    Path("rapports").mkdir(exist_ok=True)
    horodatage = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    rapport = Path("rapports") / f"{_fichier(client)}_{horodatage}.txt"
    rapport.write_text(
        f"Client : {client}\nPare-feu : {ip}:{port}\nDate : {horodatage}\n"
        f"Réussis : {nb_ok}  Échecs : {nb_ko}\n\n" + "\n".join(journal) + "\n"
        + ("\nAvertissements :\n" + "\n".join(cfg.avertissements) + "\n" if cfg.avertissements else ""),
        encoding="utf-8")
    couleur = VERT if nb_ko == 0 else ROUGE
    print(f"\n{couleur}Terminé : {nb_ok} réussi(s), {nb_ko} échec(s).{FIN} Rapport : {rapport}")
    return 0 if nb_ko == 0 else 2


def _fichier(nom: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in nom)[:60]


if __name__ == "__main__":
    sys.exit(main())
