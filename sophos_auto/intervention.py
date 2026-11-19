"""Intervention guidée pas à pas, pour un boîtier neuf : une consigne à la fois, vérifiée avant de passer à la suite.

1. Brancher le PC sur le port 1.   2. Allumer : l'outil attend que le pare-feu réponde.
3. Assistant de démarrage Sophos (la page s'ouvre toute seule).   4. Activer l'API : l'outil teste avec le mot de passe.
5. Brancher la box sur le port 2.   6. Décrire le client (assistant), puis envoyer.
"""
from __future__ import annotations

import getpass
import time
import webbrowser

from .assistant import B, F, G, J, R, consigne, info, oui_non, titre
from .diagnostic import ip_locale_vers, meme_reseau, port_ouvert

NEUF = "172.16.16.16"


def _attendre_pare_feu(ip: str, minutes: int = 6) -> bool:
    """Attend que le pare-feu réponde sur le port 4444 (il met 3 à 5 minutes à démarrer)."""
    debut = time.time()
    dernier = -1
    while time.time() - debut < minutes * 60:
        if port_ouvert(ip, 4444, 2):
            return True
        ecoule = int(time.time() - debut)
        if ecoule // 30 != dernier:
            dernier = ecoule // 30
            pc = ip_locale_vers(ip)
            etat = "" if pc and meme_reseau(pc, ip) else f" — votre PC n'a pas encore d'adresse en 172.16.16.x ({pc or 'aucune'})"
            print(f"   Le pare-feu démarre… {ecoule} s{etat}")
        time.sleep(3)
    return False


def _etape(titre_c: str, texte_c: str, verifier=None, aide_echec: str = "", illustration: str = "") -> bool:
    """Affiche la consigne jusqu'à ce que la vérification passe (ou que l'utilisateur abandonne)."""
    while True:
        rep = consigne(titre_c, texte_c, illustration)
        if rep == "?":
            print(f"{J}   {aide_echec or 'Relisez la consigne ; si vous êtes bloqué, « Demander de l aide » en bas.'}{F}")
            continue
        if verifier is None or verifier():
            print(f"{G}   ✔ Étape validée{F}")
            return True
        print(f"{R}   ✘ Ce n'est pas encore bon.{F} {aide_echec}")
        if not oui_non("Réessayer cette étape ?", True):
            return False


def guider() -> None:
    titre("INTERVENTION GUIDÉE — BOÎTIER NEUF")
    info("Suivez les consignes une par une. Après chaque « C'est fait », l'outil vérifie avant de passer à la suite.")

    _etape("Branchez votre PC sur le port 1 du pare-feu",
           "Prenez un câble réseau. Branchez un bout sur la prise réseau de votre PC, l'autre sur le port marqué « 1 » "
           "à l'arrière du pare-feu (le port vert sur le dessin). Ne branchez pas encore la box.", illustration="ports")

    def demarre():
        print("   Attente du pare-feu (jusqu'à 6 minutes)…")
        if _attendre_pare_feu(NEUF):
            return True
        pc = ip_locale_vers(NEUF)
        if not pc or not meme_reseau(pc, NEUF):
            print(f"{J}   Votre PC n'est pas dans le réseau du pare-feu (adresse {pc or 'aucune'}).{F}")
            if oui_non("Régler votre PC automatiquement (adresse 172.16.16.20) ?", True,
                       "Windows va demander l'autorisation. Le réglage actuel est noté pour être remis ensuite "
                       "(bouton « Remettre mon PC comme avant » sur l'accueil)."):
                from .reseau import regler_pc_filaire
                ok, message = regler_pc_filaire()
                print(f"   {message}")
                time.sleep(5)
                return _attendre_pare_feu(NEUF, 1)
        return False
    if not _etape("Allumez le pare-feu",
                  "Branchez l'alimentation et appuyez sur le bouton marche s'il y en a un. Les voyants s'allument. "
                  "Le pare-feu met 3 à 5 minutes à démarrer : cliquez sur « C'est fait » tout de suite, l'outil attend.",
                  demarre, "Vérifiez le câble (port 1), que le pare-feu est allumé, et attendez qu'il ait fini de démarrer."):
        return

    webbrowser.open(f"https://{NEUF}:4444")
    _etape("Faites l'assistant de démarrage Sophos",
           "La page du pare-feu vient de s'ouvrir dans le navigateur. Un avertissement de sécurité s'affiche : c'est "
           "normal, cliquez sur « Paramètres avancés » puis « Continuer ». Suivez l'assistant Sophos : choisissez un mot "
           "de passe administrateur (notez-le !), acceptez la licence, enregistrez le boîtier avec le compte Sophos du "
           "client. À la fin, la page de connexion du pare-feu s'affiche.",
           aide_echec="Si la page ne s'ouvre pas, tapez l'adresse https://172.16.16.16:4444 dans le navigateur.")

    pc = ip_locale_vers(NEUF) or "votre PC"

    def api_ok():
        from .api import ErreurAPI, SophosAPI
        from .erreurs import phrase
        mdp = getpass.getpass("Mot de passe administrateur choisi dans l'assistant Sophos : ")
        api = SophosAPI(NEUF, "admin", mdp)
        api.tentatives = 1
        try:
            api.tester_connexion()
            return True
        except ErreurAPI as exc:
            print(f"{R}   {exc}{F}\n   → {phrase('', str(exc))}")
            return False
    if not _etape("Activez l'API",
                  f"Connectez-vous à la page du pare-feu (compte « admin »). Menu de gauche : « Sauvegarde et firmware », "
                  f"onglet « API ». Cochez « Configuration de l'API ». Dans « Adresses IP autorisées », ajoutez {pc} "
                  f"(l'adresse de votre PC). Cliquez sur « Appliquer ».", api_ok,
                  "Vérifiez que la case est cochée, que l'adresse de votre PC est bien dans la liste, et le mot de passe."):
        return

    _etape("Branchez la box sur le port 2",
           "Prenez un deuxième câble réseau : un bout sur la box Internet du client (une prise LAN de la box), l'autre sur "
           "le port marqué « 2 » du pare-feu (le port rouge sur le dessin).", illustration="ports")

    print(f"\n{G}{B}Le pare-feu est prêt.{F} Il reste à décrire le client, puis à envoyer la configuration.")
    if oui_non("Décrire le client maintenant (assistant) ?", True):
        from . import assistant
        assistant.main()
