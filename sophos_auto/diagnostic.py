"""Diagnostic de connexion au pare-feu : trouve pourquoi le script ne peut pas se connecter.

    python -m sophos_auto.diagnostic --ip 172.16.16.16
"""
from __future__ import annotations

import argparse
import getpass
import ipaddress
import os
import socket
import sys

import requests
import urllib3

from .api import ErreurAPI, ErreurConnexion, SophosAPI

VERT, ROUGE, JAUNE, FIN = "\033[32m", "\033[31m", "\033[33m", "\033[0m"


def ip_locale_vers(ip: str) -> str:
    """Adresse de ce PC utilisée pour joindre l'IP donnée (sans rien envoyer)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((ip, 9))
        locale = s.getsockname()[0]
        s.close()
        return locale
    except OSError:
        return ""


def port_ouvert(ip: str, port: int = 4444, delai: float = 2.0) -> bool:
    """Le pare-feu répond-il sur ce port ? (simple ouverture de connexion, aucun identifiant envoyé)"""
    try:
        with socket.create_connection((ip, port), timeout=delai):
            return True
    except (OSError, ValueError):
        return False


def meme_reseau(ip_pc: str, ip_pare_feu: str) -> bool:
    try:
        return ipaddress.IPv4Address(ip_pc) in ipaddress.IPv4Network(f"{ip_pare_feu}/24", strict=False)
    except ValueError:
        return False


def diagnostiquer(ip: str, port: int = 4444, utilisateur: str = "admin", mot_de_passe: str | None = None,
                  demander=getpass.getpass, afficher: bool = True) -> list[tuple[bool, str, str]]:
    """Renvoie la liste des étapes (réussie ?, étape, conseil). afficher=False : rien n'est écrit à l'écran."""
    etapes: list[tuple[bool, str, str]] = []

    def ajouter(ok, etape, conseil=""):
        etapes.append((ok, etape, conseil))
        if afficher:
            print(f"{VERT + '  ✔' if ok else ROUGE + '  ✘'}{FIN} {etape}" + (f"\n      → {conseil}" if conseil and not ok else ""))
        return ok

    try:
        ipaddress.IPv4Address(ip)
    except ValueError:
        ajouter(False, f"Adresse « {ip} »", "Ce n'est pas une adresse IP valide (ex. 172.16.16.16).")
        return etapes
    locale = ip_locale_vers(ip)
    if locale:
        meme = meme_reseau(locale, ip)
        ajouter(True, f"Votre PC a l'adresse {locale}" + ("" if meme else " (pas dans le même réseau que le pare-feu)"))
    try:
        with socket.create_connection((ip, port), timeout=5):
            pass
        ajouter(True, f"Le pare-feu répond sur le port {port}")
    except OSError:
        ajouter(False, f"Le pare-feu ne répond pas sur {ip}:{port}",
                "Vérifiez le câble (PC branché sur le bon port, en général Port1), l'adresse IP du pare-feu, et que "
                "votre PC est dans le même réseau (ipconfig). Sur un XGS neuf : IP 172.16.16.16, port 4444. "
                "Depuis une zone non LAN, l'administration HTTPS doit être autorisée dans la zone.")
        return etapes
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)   # certificat auto-signé d'usine
    try:
        requests.get(f"https://{ip}:{port}/", verify=False, timeout=10)
        ajouter(True, "L'interface web du pare-feu répond (HTTPS)")
    except requests.exceptions.RequestException as exc:
        ajouter(False, "L'interface web ne répond pas en HTTPS", f"Erreur : {exc.__class__.__name__}.")
        return etapes
    mdp = mot_de_passe or os.environ.get("SOPHOS_MOT_DE_PASSE") or demander(f"Mot de passe de « {utilisateur} » : ")
    api = SophosAPI(ip, utilisateur, mdp, port=port)
    api.tentatives = 1
    try:
        api.tester_connexion()
        ajouter(True, "API activée, adresse de votre PC autorisée, identifiants corrects")
    except ErreurConnexion as exc:
        texte = str(exc)
        if "pas activée" in texte:
            conseil = "Dans l'interface web : Sauvegarde et firmware > API > cocher « Configuration de l'API » > Appliquer."
        elif "pas autorisée" in texte:
            conseil = (f"Dans Sauvegarde et firmware > API, ajoutez l'adresse de votre PC ({locale or 'voir ipconfig'}) "
                       "dans « Adresses IP autorisées ».")
        elif "mot de passe" in texte:
            conseil = "Vérifiez l'identifiant et le mot de passe (ceux de l'interface web du pare-feu)."
        else:
            conseil = texte
        ajouter(False, "Connexion à l'API refusée", conseil)
        return etapes
    try:
        api.lire("Zone")
        ajouter(True, "Lecture de la configuration autorisée")
    except ErreurAPI as exc:
        ajouter(False, "Lecture de la configuration impossible",
                f"{exc}. Le compte a-t-il le profil Administrator ?")
    return etapes


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Diagnostic de connexion au pare-feu.")
    p.add_argument("--ip", default="172.16.16.16")
    p.add_argument("--port", type=int, default=4444)
    p.add_argument("--utilisateur", default="admin")
    a = p.parse_args(argv)
    etapes = diagnostiquer(a.ip, a.port, a.utilisateur)
    ok = all(e[0] for e in etapes)
    print(f"\n{VERT + 'Tout est prêt : vous pouvez appliquer une configuration.' if ok else JAUNE + 'Corrigez le point en rouge puis relancez le diagnostic.'}{FIN}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
