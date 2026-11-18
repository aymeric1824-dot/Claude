"""Menu principal : python -m sophos_auto  (ou double-clic sur demarrer.bat)."""
from __future__ import annotations

import datetime as dt
import getpass
import os
import re
import sys
from pathlib import Path

from .assistant import (FICHE_COLLECTE, Retour, B, C, F, G, J, R, choix, conseil, info, oui_non, texte, titre,
                        _v_ip)

VERSION = "3.1"


def _pause():
    try:
        input("\nAppuyez sur Entrée pour revenir au menu...")
    except EOFError:
        pass


def _connexion_xgs(defaut_ip="172.16.16.16"):
    from .api import SophosAPI
    ip = texte("Adresse IP du pare-feu", defaut_ip, valider=_v_ip)
    user = texte("Utilisateur admin", "admin")
    mdp = os.environ.get("SOPHOS_MOT_DE_PASSE") or getpass.getpass(f"Mot de passe de « {user} » : ")
    return SophosAPI(ip, user, mdp), ip


# ----------------------------------------------------------------------------- actions
def action_assistant():
    from . import assistant
    assistant.main()


def action_appliquer():
    from .deployer import deployer
    f = _choisir_fichier_client()
    if deployer(f, simulation=True) != 0:
        return
    if oui_non("Envoyer cette configuration au pare-feu ?", False):
        deployer(f)


def action_audit():
    from .api import ErreurAPI
    from .audit import afficher, executer
    titre("CONTRÔLE DE SÉCURITÉ (lecture seule, rien n'est modifié)")
    api, ip = _connexion_xgs()
    client = texte("Nom du client (pour le rapport)", "", vide_ok=True)
    try:
        constats, chemin = executer(api, ip, client)
    except ErreurAPI as exc:
        print(f"{R}✘ {exc}{F}")
        return
    afficher(constats)
    print(f"\n{G}Rapport à remettre au client : {chemin}{F}")


def _choisir_fichier_client(question="Quel client ?"):
    fichiers = sorted(Path("clients").glob("*.xlsx")) if Path("clients").exists() else []
    f = choix(question, [(str(x), x.stem) for x in fichiers] + [("autre", "Un autre fichier (je donne le chemin)")], 1) \
        if fichiers else "autre"
    if f == "autre":
        f = texte("Chemin du fichier Excel", valider=lambda t: None if Path(t).exists() else "Fichier introuvable.")
    return f


def action_conformite():
    from .api import ErreurAPI
    from .conformite import afficher, verifier
    from .modele import lire_classeur
    titre("CONFORMITÉ : LE PARE-FEU CORRESPOND-IL À SON FICHIER ? (lecture seule)")
    f = _choisir_fichier_client()
    api, _ = _connexion_xgs(lire_classeur(f).general.get("Adresse IP du pare-feu") or "172.16.16.16")
    try:
        afficher(*verifier(api, f))
    except (ErreurAPI, ValueError) as exc:
        print(f"{R}✘ {exc}{F}")


def action_restaurer():
    from .api import ErreurAPI
    from .restaurer import restaurer
    titre("REVENIR EN ARRIÈRE")
    info("Avant chaque application, l'état du pare-feu est enregistré. Choisissez l'application à annuler : les "
         "objets créés depuis seront supprimés et les réglages modifiés remis comme avant.")
    photos = sorted(Path("rapports").glob("*_avant.json"), reverse=True) if Path("rapports").exists() else []
    if not photos:
        print(f"{J}Aucun état enregistré dans le dossier rapports.{F}")
        return
    f = choix("Quelle application annuler ?", [(str(x), x.stem.replace("_avant", "")) for x in photos[:20]], 1)
    api, _ = _connexion_xgs()
    try:
        restaurer(f, api, confirmer=lambda q: oui_non(q, False))
    except ErreurAPI as exc:
        print(f"{R}✘ {exc}{F}")


def action_lire():
    from .api import ErreurAPI, to_xml
    types = [("FirewallRule", "Règles de pare-feu"), ("NATRule", "Règles NAT"), ("IPHost", "Hôtes"),
             ("Services", "Services"), ("Zone", "Zones"), ("Interface", "Interfaces"), ("VLAN", "VLAN"),
             ("DHCPServer", "Serveurs DHCP"), ("User", "Comptes"), ("VPNIPSecConnection", "VPN IPsec"),
             ("WebFilterPolicy", "Stratégies de filtrage web"), ("IPSPolicy", "Stratégies IPS"),
             ("VPNProfile", "Profils IPsec"), ("autre", "Autre (je donne le nom technique)")]
    t = choix("Quels objets afficher ?", types, 1)
    if t == "autre":
        t = texte("Nom technique (ex. GatewayConfiguration)")
    api, _ = _connexion_xgs()
    try:
        print(to_xml({t: api.lire(t) or {}}))
    except ErreurAPI as exc:
        print(f"{R}✘ {exc}{F}")


def action_collecte():
    print(FICHE_COLLECTE)
    Path("fiche_collecte.txt").write_text(FICHE_COLLECTE.strip() + "\n", encoding="utf-8")
    print(f"{G}Enregistrée dans fiche_collecte.txt (à imprimer ou envoyer au client).{F}")


def action_modele():
    from .creer_modele import creer
    print(f"{G}Modèle créé : {creer('modele_client.xlsx')}{F}")


# ----------------------------------------------------------------------------- Sophos Central
def _central():
    from .central import ErreurCentral, SophosCentral
    titre("SOPHOS CENTRAL")
    info("Il faut des identifiants API Sophos Central : dans Central, Paramètres globaux > Identifiants API "
         "(API Credentials) > Ajouter, rôle « Service Principal Firewall » conseillé. Ils ne sont jamais enregistrés "
         "par l'outil (vous pouvez aussi les mettre dans les variables SOPHOS_CENTRAL_ID et SOPHOS_CENTRAL_SECRET).")
    cid = os.environ.get("SOPHOS_CENTRAL_ID") or texte("Client ID")
    secret = os.environ.get("SOPHOS_CENTRAL_SECRET") or getpass.getpass("Client secret (saisie masquée) : ")
    c = SophosCentral(cid, secret)
    try:
        c.connecter()
        if c.type_compte != "tenant":
            clients = c.clients()
            if not clients:
                raise ErreurCentral("Aucun client trouvé sur ce compte.")
            filtre = texte("Nom du client (ou une partie, Entrée = tous)", "", vide_ok=True).lower()
            liste = [x for x in clients if filtre in x.nom.lower()] or clients
            choisi = choix("Quel client ?", [(str(i), x.nom) for i, x in enumerate(liste[:40])], 1)
            c.choisir_client(liste[int(choisi)])
        print(f"{G}✔ Connecté à Sophos Central ({c.client.nom}){F}")
    except ErreurCentral as exc:
        print(f"{R}✘ {exc}{F}")
        return None
    return c


def _afficher_pare_feux(pfs):
    if not pfs:
        print(f"{J}Aucun pare-feu sur ce compte.{F}")
        return
    print(f"\n   {'N°':<4}{'Nom':<28}{'Modèle':<10}{'Firmware':<26}{'Connecté':<10}IP publique")
    for i, p in enumerate(pfs, 1):
        etat = f"{G}oui{F}" if p.connecte else f"{R}non{F}"
        print(f"   {i:<4}{p.nom[:27]:<28}{p.modele[:9]:<10}{p.firmware[:25]:<26}{etat:<19}{', '.join(p.ip_publiques)}")


def _choisir_pare_feux(pfs, question, plusieurs=False):
    _afficher_pare_feux(pfs)
    while True:
        rep = texte(question + (" (numéros séparés par des virgules)" if plusieurs else ""))
        try:
            n = [int(x) for x in re.split(r"[,; ]+", rep) if x]
            if n and all(1 <= x <= len(pfs) for x in n) and (plusieurs or len(n) == 1):
                return [pfs[x - 1] for x in n]
        except ValueError:
            pass
        print(f"{J}   Numéro(s) entre 1 et {len(pfs)}.{F}")


def _rappel(etat):
    print(f"{C}   … {etat}{F}")


def _fichier_sauvegarde(pf) -> Path:
    nom = re.sub(r"[^A-Za-z0-9_-]", "_", pf.nom)
    return Path("sauvegardes") / f"{nom}_{pf.serie}_{dt.datetime.now():%Y-%m-%d_%H%M%S}.tar"


def action_central():
    from .central import ErreurCentral
    c = _central()
    if not c:
        return
    while True:
        a = choix("Que voulez-vous faire dans Sophos Central ?", [
            ("liste", "Voir mes pare-feux (modèle, firmware, connecté, IP publique)"),
            ("export", "Sauvegarder la configuration d'un pare-feu (fichier .tar sur ce PC)"),
            ("copie", "Copier la configuration d'un pare-feu « modèle » vers d'autres pare-feux"),
            ("import", "Envoyer un fichier de configuration (.tar) vers des pare-feux"),
            ("fin", "Revenir au menu principal")], 1,
            "L'export et l'import passent par Central : pas besoin d'être sur place. Il faut SFOS 22.0 MR2 ou plus "
            "récent, des pare-feux gérés par Central et un abonnement (ou contrat de support) actif.")
        if a == "fin":
            return
        try:
            pfs = c.pare_feux()
            if a == "liste":
                _afficher_pare_feux(pfs)
            elif a == "export":
                if not pfs:
                    continue
                pf = _choisir_pare_feux(pfs, "Quel pare-feu sauvegarder ?")[0]
                f = c.exporter(pf.id, _fichier_sauvegarde(pf), rappel=_rappel)
                print(f"{G}✔ Configuration enregistrée : {f}{F}")
                conseil("Ce fichier contient toute la configuration du client : rangez-le dans un endroit protégé.")
            elif a in ("copie", "import"):
                _importer(c, pfs, depuis_modele=(a == "copie"))
        except ErreurCentral as exc:
            print(f"{R}✘ {exc}{F}")


def _importer(c, pfs, depuis_modele: bool):
    if not pfs:
        return
    if depuis_modele:
        info("Principe : vous configurez une fois un pare-feu « modèle » avec vos réglages habituels (objets, "
             "services, règles, protections...). Ses réglages sont ensuite copiés sur les pare-feux choisis. "
             "Les spécificités de chaque client se font ensuite avec l'assistant.")
        source = _choisir_pare_feux(pfs, "Quel est le pare-feu modèle ?")[0]
        quoi = choix("Que copier ?", [
            ("tout", "Toute la configuration"),
            ("partiel", "Seulement les objets et règles (hôtes, services, règles, NAT, stratégies)")], 2,
            "« Tout » copie aussi les interfaces et adresses IP : à réserver à un boîtier identique qui remplace "
            "l'autre. Pour un nouveau client, copiez seulement les objets et règles.")
    cibles = [p for p in _choisir_pare_feux(pfs, "Vers quel(s) pare-feu(x) ? (25 maximum)", plusieurs=True)]
    if depuis_modele:
        cibles = [p for p in cibles if p.id != source.id]
    hors_ligne = [p.nom for p in cibles if not p.connecte]
    if hors_ligne:
        print(f"{J}   Non connectés à Central (l'import échouera) : {', '.join(hors_ligne)}{F}")
    print(f"\n{B}Avant d'importer :{F}")
    print("   - les pare-feux cibles doivent avoir un firmware égal ou plus récent que le fichier ;")
    print("   - ce qui existe dans le fichier remplace la configuration actuelle (rien n'est supprimé) ;")
    print("   - sans la « clé maître de stockage sécurisé » (SSMK), les mots de passe et données sensibles "
          "ne sont pas importés.")
    if not oui_non(f"Importer vers {len(cibles)} pare-feu(x) : {', '.join(p.nom for p in cibles)} ?", False):
        return
    if oui_non("Sauvegarder d'abord la configuration actuelle de chaque cible (conseillé) ?", True):
        for p in cibles:
            print(f"   Sauvegarde de {p.nom}...")
            print(f"{G}   ✔ {c.exporter(p.id, _fichier_sauvegarde(p), rappel=_rappel)}{F}")
    if depuis_modele:
        entites = None if quoi == "tout" else ["IPHost", "IPHostGroup", "FQDNHost", "FQDNHostGroup", "Services",
                                                "ServiceGroup", "FirewallRule", "FirewallRuleGroup", "NATRule",
                                                "WebFilterPolicy", "ApplicationFilterPolicy", "IPSPolicy"]
        fichier = c.exporter(source.id, _fichier_sauvegarde(source), entites, rappel=_rappel)
        print(f"{G}   ✔ Configuration du modèle exportée : {fichier}{F}")
    else:
        fichier = Path(texte("Chemin du fichier .tar", valider=lambda t: None if Path(t).exists() else "Fichier introuvable."))
    ssmk = getpass.getpass("Clé maître SSMK (Entrée si vous ne l'avez pas) : ")
    resultat = c.importer(fichier, [p.id for p in cibles], ssmk, rappel=_rappel)
    elements = resultat.get("items") if isinstance(resultat, dict) else None
    for e in elements or []:
        nom = next((p.nom for p in cibles if p.id == e.get("firewallId") or p.id == e.get("id")), e.get("firewallId", "?"))
        ok = str(e.get("result", e.get("status", ""))).lower() in ("success", "finished")
        print(f"   {G + '✔' if ok else R + '✘'}{F} {nom} : {e.get('result') or e.get('status')} {e.get('message', '')}")
    print(f"{G}Import terminé.{F} Vérifiez chaque pare-feu dans l'interface : un statut « succès » confirme le "
          f"traitement par Central, pas que tout fonctionne.")


# ----------------------------------------------------------------------------- menu
MENU = [
    ("assistant", "Nouveau client, ou reprendre une configuration en cours (assistant)", action_assistant),
    ("appliquer", "Appliquer un fichier client sur un pare-feu", action_appliquer),
    ("audit", "Contrôle de sécurité d'un pare-feu (rapport pour le client)", action_audit),
    ("conformite", "Vérifier qu'un pare-feu correspond toujours à son fichier client", action_conformite),
    ("restaurer", "Revenir en arrière : annuler une application", action_restaurer),
    ("central", "Sophos Central : liste, sauvegarde, copie d'un pare-feu modèle", action_central),
    ("collecte", "Liste des informations à demander au client avant l'intervention", action_collecte),
    ("lire", "Voir les objets d'un pare-feu (règles, hôtes, VPN...)", action_lire),
    ("modele", "Créer un fichier Excel vierge (modèle)", action_modele),
    ("quitter", "Quitter", None),
]


def main() -> int:
    if os.name == "nt":
        os.system("")
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(errors="replace")   # jamais de plantage sur un caractère non affichable
        except (AttributeError, ValueError):
            pass
    while True:
        titre(f"SOPHOS XGS — OUTIL DE CONFIGURATION (v{VERSION})")
        try:
            c = choix("Que voulez-vous faire ? (q pour quitter)", [(k, lib) for k, lib, _ in MENU], 1)
            if c == "quitter":
                return 0
            next(f for k, _, f in MENU if k == c)()
        except Retour:
            continue
        except KeyboardInterrupt:
            print(f"\n{J}Action annulée.{F}")
            continue
        _pause()


if __name__ == "__main__":
    sys.exit(main())
