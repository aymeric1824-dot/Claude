"""Revenir en arrière : remet le pare-feu dans l'état enregistré avant une application.

    python -m sophos_auto.restaurer rapports/dupont_2026-11-18_1245_avant.json --ip 192.168.1.254

Avant chaque application, le script enregistre l'état des objets qu'il va toucher
(fichier *_avant.json). La restauration :
  - supprime les objets créés depuis (règles, hôtes, VPN, comptes...) ;
  - remet les objets modifiés et les réglages (DNS, heure, alertes...) dans leur état d'avant.
Elle montre d'abord ce qu'elle va faire et demande confirmation.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .api import ErreurAPI, ErreurConnexion, SophosAPI

VERT, ROUGE, JAUNE, GRIS, FIN = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m"

UNIQUES = {"AdminSettings", "Time", "DNS", "Notification", "BackupRestore", "SNMPAgentConfiguration",
           "SSLTunnelAccessSettings", "GatewayConfiguration", "OTPSettings", "SSLTLSInspectionSettings"}
# Réglages qui ne se « remettent » pas automatiquement (action unique ou risquée) : signalés seulement
NON_RESTAURABLES = {"HAConfigure", "HBCloudRegistration", "EnableCloudCentralManagement"}
# Ordre de suppression : ce qui utilise d'autres objets d'abord
ORDRE_SUPPRESSION = ["NATRule", "FirewallRule", "SSLTLSInspectionRule", "SDWANPolicyRoute", "SSLVPNPolicy",
                     "VPNIPSecConnection", "DHCPServer", "User", "AuthenticationServer", "WirelessNetworks",
                     "REDDevice", "QoSPolicy", "IPHostGroup", "CountryGroup", "FQDNHost", "IPHost", "Services",
                     "UnicastRoute", "SNMPCommunity", "VLAN", "Zone"]
# Ne jamais supprimer ces objets d'origine, même s'ils semblent nouveaux
INTOUCHABLES = {("Zone", n) for n in ("LAN", "WAN", "DMZ", "VPN", "WiFi", "LOCAL")} | {("User", "admin")}


@dataclass
class Action:
    type: str        # supprimer | remettre
    balise: str
    nom: str
    contenu: dict


def _liste(x) -> list:
    if x is None or isinstance(x, str):
        return []
    return x if isinstance(x, list) else [x]


def cle(balise: str, e: dict) -> str:
    if not isinstance(e, dict):
        return ""
    if balise == "Interface":
        return str(e.get("Hardware") or e.get("Name") or "")
    if balise == "UnicastRoute":
        return f"{e.get('DestinationIP')}/{e.get('Netmask')} via {e.get('Gateway')}"
    if balise == "User":
        return str(e.get("Username") or "")
    if balise == "REDDevice":
        return str(e.get("BranchName") or "")
    for sous in ("TunnelPolicy", "Configuration", "ActiveDirectory"):
        if isinstance(e.get(sous), dict):
            return cle(balise, e[sous])
    return str(e.get("Name") or e.get("ServerName") or "")


def cle_suppression(balise: str, e: dict) -> dict:
    if balise == "UnicastRoute":
        return {k: e.get(k) for k in ("DestinationIP", "Netmask", "Gateway", "Interface") if e.get(k)}
    if balise == "AuthenticationServer":
        return {"ActiveDirectory": {"ServerName": cle(balise, e)}}
    if balise == "REDDevice":
        return {"BranchName": cle(balise, e)}
    return {"Name": cle(balise, e)}


def _propre(e: dict) -> dict:
    """Retire les champs en lecture seule avant de renvoyer un objet au pare-feu."""
    e = dict(e)
    for k in ("@transactionid", "Status", "InterfaceStatus") if "Hardware" in e else ("@transactionid",):
        e.pop(k, None)
    return e


def plan(api: SophosAPI, avant: dict) -> list[Action]:
    actions: list[Action] = []
    remises: list[Action] = []
    for balise, contenu_avant in avant.items():
        if isinstance(contenu_avant, str) or balise in NON_RESTAURABLES:   # illisible, ou à défaire à la main
            continue
        maintenant = api.lire(balise)
        if balise in UNIQUES:
            a = contenu_avant if isinstance(contenu_avant, dict) else (_liste(contenu_avant) or [None])[0]
            m = maintenant if isinstance(maintenant, dict) else (_liste(maintenant) or [None])[0]
            if a and _propre(a) != _propre(m or {}):
                remises.append(Action("remettre", balise, "réglage", _propre(a)))
            continue
        par_cle_avant = {cle(balise, e): e for e in _liste(contenu_avant)}
        for e in _liste(maintenant):
            k = cle(balise, e)
            if not k:
                continue
            if k not in par_cle_avant:
                if (balise, k) not in INTOUCHABLES:
                    actions.append(Action("supprimer", balise, k, cle_suppression(balise, e)))
            elif _propre(par_cle_avant[k]) != _propre(e):
                remises.append(Action("remettre", balise, k, _propre(par_cle_avant[k])))
    rang = {b: i for i, b in enumerate(ORDRE_SUPPRESSION)}
    actions.sort(key=lambda a: rang.get(a.balise, len(rang)))
    # les interfaces en dernier (un changement d'IP peut couper la connexion)
    remises.sort(key=lambda a: a.balise == "Interface")
    return actions + remises


def appliquer_plan(api: SophosAPI, actions: list[Action]) -> tuple[int, list[str]]:
    ok, erreurs = 0, []
    for a in actions:
        try:
            if a.type == "supprimer":
                res = api.supprimer(a.balise, a.contenu)
            else:
                res = api.ecrire(a.balise, a.contenu, "update")
        except ErreurConnexion as exc:
            if a.balise == "Interface":
                ok += 1
                print(f"{JAUNE}  ✔ {a.balise} {a.nom} remis (connexion coupée : l'IP a changé){FIN}")
                continue
            erreurs.append(f"{a.type} {a.balise} {a.nom} : {exc}")
            break
        except ErreurAPI as exc:
            erreurs.append(f"{a.type} {a.balise} {a.nom} : {exc}")
            continue
        if res.ok:
            ok += 1
            print(f"{VERT}  ✔{FIN} {'Supprimé' if a.type == 'supprimer' else 'Remis'} : {a.balise} {a.nom}")
        else:
            erreurs.append(f"{a.type} {a.balise} {a.nom} : {res.code} {res.message}")
            print(f"{ROUGE}  ✘ {a.balise} {a.nom} : {res.code} {res.message}{FIN}")
    return ok, erreurs


def restaurer(fichier: str, api: SophosAPI, confirmer=None, simulation: bool = False) -> int:
    avant = json.loads(Path(fichier).read_text(encoding="utf-8"))
    print("Comparaison avec l'état actuel du pare-feu...")
    actions = plan(api, avant)
    if not actions:
        print(f"{VERT}Le pare-feu est déjà dans l'état enregistré : rien à faire.{FIN}")
        return 0
    for a in actions:
        print(f"  {ROUGE + 'supprimer' if a.type == 'supprimer' else JAUNE + 'remettre '}{FIN} {a.balise:<22} {a.nom}")
    if simulation:
        print(f"\n{GRIS}Simulation : rien n'a été modifié.{FIN}")
        return 0
    question = f"Appliquer ces {len(actions)} action(s) ?"
    rep = confirmer(question) if confirmer else input(f"{question} (o/N) ").strip().lower() in ("o", "oui")
    if not rep:
        return 1
    ok, erreurs = appliquer_plan(api, actions)
    from . import historique
    client = Path(fichier).stem.replace("_avant", "").rsplit("_", 2)[0]
    historique.enregistrer(client, "restauration", f"{ok} action(s), {len(erreurs)} échec(s)", echecs=len(erreurs),
                           etat=fichier)
    print(f"\n{VERT if not erreurs else ROUGE}Restauration : {ok} action(s) réussie(s), {len(erreurs)} échec(s).{FIN}")
    for e in erreurs:
        print(f"{ROUGE}  ✘ {e}{FIN}")
    if erreurs:
        print(f"{JAUNE}Terminez ces points à la main dans l'interface du pare-feu.{FIN}")
    return 0 if not erreurs else 2


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Remet le pare-feu dans l'état enregistré avant une application.")
    p.add_argument("fichier", help="Fichier *_avant.json (dossier rapports)")
    p.add_argument("--ip", default="172.16.16.16")
    p.add_argument("--port", type=int, default=4444)
    p.add_argument("--utilisateur", default="admin")
    p.add_argument("--simulation", action="store_true", help="Afficher seulement ce qui serait fait")
    a = p.parse_args(argv)
    mdp = os.environ.get("SOPHOS_MOT_DE_PASSE") or getpass.getpass(f"Mot de passe de « {a.utilisateur} » : ")
    try:
        return restaurer(a.fichier, SophosAPI(a.ip, a.utilisateur, mdp, port=a.port), simulation=a.simulation)
    except ErreurAPI as exc:
        print(f"{ROUGE}✘ {exc}{FIN}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
