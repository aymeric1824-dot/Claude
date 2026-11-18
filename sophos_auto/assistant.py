"""Assistant pas à pas : pose des questions sur le client et prépare toute la configuration.

    python -m sophos_auto.assistant

À chaque question :
  - Entrée seule = garder la valeur proposée entre [crochets]
  - ? = afficher une explication
"""
from __future__ import annotations

import copy
import getpass
import ipaddress
import json
import re
import secrets as rnd
import string
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

from .classeur import ecrire_classeur
from .parametres import charger as charger_parametres
from .schema import DEMANDER

PARAMS = charger_parametres()

B, G, J, C, R, GR, F = "\033[1m", "\033[32m", "\033[33m", "\033[36m", "\033[31m", "\033[90m", "\033[0m"
LARGEUR = 88


class Retour(Exception):
    """L'utilisateur a tapé < (refaire l'étape) ou << (étape précédente)."""

    def __init__(self, precedente: bool):
        super().__init__()
        self.precedente = precedente


def _retour(rep: str) -> None:
    if rep in ("<", "<<"):
        raise Retour(rep == "<<")


# ============================================================================ questions
def _wrap(t: str, indent="   ") -> str:
    return "\n".join(textwrap.fill(p, LARGEUR, initial_indent=indent, subsequent_indent=indent) if p.strip() else ""
                     for p in t.strip("\n").split("\n"))


def titre(t: str) -> None:
    print(f"\n{C}{B}{'═' * LARGEUR}\n  {t}\n{'═' * LARGEUR}{F}")


def info(t: str) -> None:
    print(f"{GR}{_wrap(t)}{F}")


def conseil(t: str) -> None:
    print(f"{J}{_wrap('💡 ' + t)}{F}")


def _lire(invite: str) -> str:
    try:
        return input(invite).strip()
    except EOFError:
        print()
        sys.exit(1)


def texte(question: str, defaut: str = "", aide: str = "", valider=None, vide_ok=False) -> str:
    while True:
        d = f" [{defaut}]" if defaut else ""
        rep = _lire(f"{B}? {question}{F}{d} : ")
        _retour(rep)
        if rep == "?":
            print(f"{C}{_wrap(aide or 'Pas d’explication supplémentaire pour cette question.')}{F}")
            continue
        if not rep:
            rep = defaut
        if not rep and not vide_ok:
            print(f"{J}   Une réponse est nécessaire (tapez ? pour de l'aide).{F}")
            continue
        if rep and valider:
            erreur = valider(rep)
            if erreur:
                print(f"{R}   {erreur}{F}")
                continue
        return rep


def oui_non(question: str, defaut: bool = True, aide: str = "") -> bool:
    while True:
        rep = _lire(f"{B}? {question}{F} [{'O/n' if defaut else 'o/N'}] : ").lower()
        _retour(rep)
        if rep == "?":
            print(f"{C}{_wrap(aide or 'Pas d’explication supplémentaire.')}{F}")
            continue
        if not rep:
            return defaut
        if rep in ("o", "oui", "y", "yes"):
            return True
        if rep in ("n", "non", "no"):
            return False
        print(f"{J}   Répondez o (oui) ou n (non).{F}")


def choix(question: str, options: list[tuple[str, str]], defaut: int = 1, aide: str = "") -> str:
    """options = [(clé, libellé)] ; renvoie la clé."""
    print(f"{B}? {question}{F}")
    for i, (_, lib) in enumerate(options, 1):
        print(f"   {C}{i}{F}. {lib}")
    while True:
        rep = _lire(f"   Votre choix [{defaut}] : ")
        _retour(rep)
        if rep == "?":
            print(f"{C}{_wrap(aide or 'Pas d’explication supplémentaire.')}{F}")
            continue
        if not rep:
            return options[defaut - 1][0]
        if rep.lower() == "q" and options[-1][0] in ("quitter", "fin"):
            return options[-1][0]
        if rep.isdigit() and 1 <= int(rep) <= len(options):
            return options[int(rep) - 1][0]
        print(f"{J}   Tapez un numéro entre 1 et {len(options)}.{F}")


def _v_ip(t):
    try:
        ipaddress.IPv4Address(t)
    except ValueError:
        return "Adresse IP invalide (ex. 192.168.1.254)."


def _v_iface(t):
    try:
        i = ipaddress.IPv4Interface(t)
    except ValueError:
        return "Format attendu : IP/masque, ex. 192.168.10.254/24"
    if i.network.prefixlen > 30 or i.ip in (i.network.network_address, i.network.broadcast_address):
        return "Cette IP n'est pas utilisable sur ce réseau."


def _v_reseaux(t):
    for x in re.split(r"[;,]", t):
        try:
            ipaddress.IPv4Network(x.strip(), strict=False)
        except ValueError:
            return f"« {x.strip()} » n'est pas un réseau (ex. 192.168.2.0/24)."


def _v_port(t):
    if not re.fullmatch(r"(?i)port\d{1,2}", t):
        return "Nom de port attendu : Port1, Port2, Port3..."


def _v_mac(t):
    if not re.fullmatch(r"([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}", t):
        return "Adresse MAC attendue, ex. 00:11:22:33:44:55"


def _v_email(t):
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", t):
        return "Adresse e-mail invalide."


def _v_nom(t):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.-]{0,49}", t):
        return "Utilisez lettres, chiffres, espaces, - _ . (50 caractères maximum)."


PRIVES = [ipaddress.IPv4Network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10")]


def _est_publique(ip: ipaddress.IPv4Address) -> bool:
    return not any(ip in n for n in PRIVES)


def port_reseau(t):
    return t[0].upper() + t[1:].lower() if t else t


def generer_mdp(n=20) -> str:
    alphabet = string.ascii_letters + string.digits + "-_.!+"
    while True:
        m = "".join(rnd.choice(alphabet) for _ in range(n))
        if (any(c.islower() for c in m) and any(c.isupper() for c in m) and any(c.isdigit() for c in m)
                and any(c in "-_.!+" for c in m)):
            return m


def mot_de_passe(libelle: str, aide: str = "", generer_ok=True) -> tuple[str, bool]:
    """Renvoie (valeur, générée ?)."""
    if generer_ok and oui_non(f"Générer automatiquement « {libelle} » (conseillé) ?", True, aide):
        v = generer_mdp()
        print(f"   {G}→ {libelle} : {B}{v}{F}   {J}(notez-le dans votre coffre-fort de mots de passe){F}")
        return v, True
    while True:
        v = getpass.getpass(f"{B}? {libelle}{F} (saisie masquée) : ")
        if len(v) < 8:
            print(f"{J}   8 caractères minimum.{F}")
            continue
        if getpass.getpass("   Confirmez : ") == v:
            return v, False
        print(f"{J}   Les deux saisies sont différentes.{F}")


# ============================================================================ données collectées
@dataclass
class Projet:
    general: dict[str, str] = field(default_factory=dict)
    lignes: dict[str, list[dict]] = field(default_factory=dict)
    secrets: dict[str, str] = field(default_factory=dict)       # libellé -> valeur (en mémoire seulement)
    generes: list[tuple[str, str]] = field(default_factory=list)  # mots de passe générés à noter
    a_faire: list[str] = field(default_factory=list)            # étapes manuelles
    resume: list[str] = field(default_factory=list)             # ce qui est configuré (fiche client)
    infos_client: list[str] = field(default_factory=list)       # infos à transmettre au client
    lan_iface: ipaddress.IPv4Interface | None = None
    lan_port: str = "Port1"
    wan_port: str = "Port2"
    adresse_publique: str = ""
    ad_ip: str = ""
    domaine: str = ""
    reseaux_internes: list[str] = field(default_factory=list)
    zones_internes: list[str] = field(default_factory=list)
    serveurs: list[tuple[str, str, str]] = field(default_factory=list)  # (nom, ip, type)
    vpn_sites: list[dict] = field(default_factory=list)       # pour les fiches « autre site »
    teletravailleurs: list[dict] = field(default_factory=list)  # pour les fiches utilisateurs
    situation: str = "autre"
    central: bool = False          # le client est géré dans Sophos Central
    zero_touch: bool = False       # le boîtier est préconfiguré par Central (Zero Touch)
    prochain_octet: int = 20

    def ligne(self, onglet: str, **valeurs) -> dict:
        d = {"Actif": "Oui", **{k: v for k, v in valeurs.items()}}
        self.lignes.setdefault(onglet, []).append(d)
        return d

    def secret(self, libelle: str, valeur: str, genere: bool) -> str:
        self.secrets[libelle] = valeur
        if genere:
            self.generes.append((libelle, valeur))
        return DEMANDER


def _suivant_reseau(p: Projet) -> ipaddress.IPv4Interface:
    """Propose le prochain réseau libre en /24 pour un VLAN."""
    base = p.lan_iface.network if p.lan_iface else ipaddress.IPv4Network("192.168.10.0/24")
    a, b, _, _ = str(base.network_address).split(".")
    if a == "192":
        b = "168"
    pris = [ipaddress.IPv4Network(r) for r in p.reseaux_internes]
    while True:
        o = p.prochain_octet
        p.prochain_octet = o + 10 if o + 10 < 255 else 11
        iface = ipaddress.IPv4Interface(f"{a}.{b}.{o}.254/24")
        if not any(iface.network.overlaps(n) for n in pris):
            return iface


def _plage_dhcp(iface: ipaddress.IPv4Interface) -> tuple[str, str]:
    hosts = list(iface.network.hosts())
    if len(hosts) >= 200:
        return str(hosts[99]), str(hosts[198])
    tiers = max(1, len(hosts) // 3)
    return str(hosts[tiers]), str(hosts[-3])


def _slug(t: str) -> str:
    t = t.lower()
    for a, b in (("éèêë", "e"), ("àâä", "a"), ("îï", "i"), ("ôö", "o"), ("ùûü", "u"), ("ç", "c")):
        for ch in a:
            t = t.replace(ch, b)
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:30] or "client"


# ============================================================================ étapes
FICHE_COLLECTE = """
Informations à demander au client (ou à relever sur place) AVANT de commencer :

 Internet
  - Opérateur, type de connexion (box, fibre pro...), IP publique fixe ou non
  - Si IP fixe : adresse IP, masque, passerelle donnés par l'opérateur
  - Si fibre pro « PPPoE » : identifiant et mot de passe de connexion
  - Y a-t-il un deuxième accès Internet (4G, 2e fibre) ?
 Réseau local
  - Adresses actuelles des PC (ex. 192.168.1.x) et IP de l'ancien routeur / pare-feu
  - Qui distribue les adresses (box, serveur Windows, ancien pare-feu) ?
  - Y a-t-il des VLAN sur les switchs (téléphonie, caméras...) ?
 Serveurs et équipements
  - Liste des serveurs (AD, fichiers, logiciel métier, NAS) avec leurs IP
  - Équipements à joindre depuis Internet (caméras, serveur web, messagerie...)
  - Imprimantes, téléphonie IP, bornes Wi-Fi (marque ?)
 Accès à distance
  - Personnes en télétravail (nom, identifiant, e-mail)
  - Autres sites à relier (agences) : IP publique et réseaux de chaque site
 Administration
  - Adresse e-mail qui doit recevoir les alertes et les sauvegardes
  - Serveur d'envoi d'e-mails (SMTP) : ex. Microsoft 365, Gmail, serveur du client
  - Outil de supervision éventuel (PRTG, Zabbix, Centreon...)
"""

SITUATIONS = [
    ("petit", "Petit bureau ou commerce : Internet + quelques PC, pas de serveur"),
    ("pme", "PME avec serveur(s) : Active Directory, fichiers, logiciel métier, télétravail"),
    ("multi", "Entreprise multi-sites : un siège et une ou plusieurs agences à relier"),
    ("remplacement", "Remplacement d'un ancien pare-feu ou routeur (garder les adresses existantes)"),
    ("autre", "Je ne sais pas / autre : je réponds à toutes les questions"),
]


def etape_intro(p: Projet) -> str:
    titre("ASSISTANT DE CONFIGURATION SOPHOS XGS")
    info("Cet assistant vous pose des questions sur le client, puis prépare toute la configuration du pare-feu. "
         "À la fin, il crée un fichier Excel (modifiable), une fiche récapitulative, et peut appliquer la "
         "configuration sur le boîtier.")
    info("Règles : appuyez sur Entrée pour garder la valeur proposée entre [crochets]. Tapez ? à n'importe quelle "
         "question pour avoir une explication. Tapez < pour recommencer l'étape en cours, << pour revenir à "
         "l'étape précédente. Vos réponses sont enregistrées après chaque étape : en cas d'interruption, vous "
         "pourrez reprendre. Ctrl+C pour quitter.")
    if oui_non("Afficher d'abord la liste des informations à demander au client ?", False,
               "Utile si vous n'êtes pas encore chez le client : la liste est aussi enregistrée dans un fichier."):
        print(FICHE_COLLECTE)
        Path("fiche_collecte.txt").write_text(FICHE_COLLECTE.strip() + "\n", encoding="utf-8")
        print(f"{G}   (enregistrée dans fiche_collecte.txt){F}")
        _lire("   Appuyez sur Entrée pour continuer...")

    titre("1. LE CLIENT")
    nom = texte("Nom du client", aide="Sert à nommer les fichiers, les sauvegardes et le pare-feu.", valider=_v_nom)
    p.general["Nom du client"] = nom
    p.general["Nom d'hôte du pare-feu"] = texte(
        "Nom du pare-feu", f"fw-{_slug(nom)}",
        "Nom technique du boîtier (sans espace). Il apparaît dans les alertes et Sophos Central.",
        lambda t: None if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,62}", t) else "Lettres, chiffres, - et . uniquement.")
    situation = choix("Quelle situation ressemble le plus à celle du client ?", SITUATIONS, 1,
                      "Votre réponse sert seulement à proposer les bons choix par défaut. Toutes les questions "
                      "utiles seront posées dans tous les cas.")
    if situation == "remplacement":
        conseil("Avant de débrancher l'ancien équipement, relevez son adresse IP côté LAN, ses redirections de "
                "ports, ses VPN et s'il distribue les adresses (DHCP). En reprenant la même IP côté LAN, les PC "
                "n'auront rien à changer.")
    p.central = oui_non("Ce pare-feu sera-t-il géré dans Sophos Central ?", True,
                        "Sophos Central (aussi appelé Sophos Fusion) est la console en ligne de Sophos. Elle permet "
                        "de préconfigurer le boîtier avant de le brancher (Zero Touch), de le gérer à distance, de "
                        "planifier les mises à jour et de garder ses sauvegardes.")
    if p.central:
        p.zero_touch = oui_non("Préconfigurer le boîtier avec le Zero Touch de Sophos Central ?", True,
                               "Vous saisissez le n° de série du boîtier dans Central avec les réglages de base "
                               "(Internet, réseau local, DHCP, fuseau). Au premier démarrage, branché sur Internet, le "
                               "boîtier télécharge ces réglages tout seul : plus d'assistant de démarrage en local. "
                               "L'assistant vous donnera la liste exacte des valeurs à saisir dans Central.")
        if not p.zero_touch and oui_non("Inscrire automatiquement le boîtier dans Sophos Central à la fin ?", True,
                                        "Le script fait l'inscription (Système > Sophos Central) avec le compte Central "
                                        "du client, et active l'envoi des sauvegardes dans Central. Si le compte a la "
                                        "double authentification, l'inscription peut être refusée : l'outil vous dira "
                                        "alors de la faire à la main."):
            p.general["Inscrire dans Sophos Central"] = "Oui"
            p.general["Central : e-mail du compte"] = texte("E-mail du compte Sophos Central", valider=_v_email)
            v, gen = mot_de_passe("Mot de passe du compte Sophos Central", generer_ok=False)
            p.general["Central : mot de passe"] = p.secret("Mot de passe du compte Sophos Central", v, gen)
            p.resume.append("Inscription automatique dans Sophos Central (sauvegardes envoyées dans Central)")
    return situation


def etape_internet(p: Projet, situation: str) -> None:
    titre("2. ACCÈS INTERNET (WAN)")
    info("Le WAN est le côté Internet du pare-feu : le port branché sur la box ou le routeur de l'opérateur.")
    p.wan_port = port_reseau(texte("Port du XGS relié à la box / au routeur", "Port2",
                                   "Sur un XGS neuf, Port1 = réseau local (LAN) et Port2 = Internet (WAN). "
                                   "Le nom est écrit sur la face avant du boîtier.", _v_port))
    mode = choix("Comment ce lien Internet est-il fourni ?", [
        ("DHCP", "Par une box (Orange, SFR, Bouygues, Free...) qui donne une adresse automatiquement — le plus courant"),
        ("Statique", "Avec une adresse IP fixe fournie par l'opérateur (ou fixée sur la box)"),
        ("PPPoE", "Fibre/ADSL pro branchée en direct, avec un identifiant et un mot de passe (PPPoE)"),
    ], 1, "DHCP : la box donne une adresse au pare-feu, rien à saisir. Statique : l'opérateur vous a donné une "
          "IP, un masque et une passerelle. PPPoE : l'opérateur a fourni un identifiant de connexion (souvent "
          "avec un modem ou un ONT fibre sans box).")
    ligne = {"Port": p.wan_port, "Zone": "WAN", "Mode": mode, "Description": "Accès Internet principal"}
    if mode == "Statique":
        iface = ipaddress.IPv4Interface(texte("IP du pare-feu côté Internet, avec le masque", "",
                                              "Ex. 203.0.113.10/29 ou 192.168.1.2/24 si la box est devant.", _v_iface))
        gw = texte("Passerelle (IP de la box ou du routeur opérateur)", str(next(iface.network.hosts())),
                   "C'est l'adresse vers laquelle le pare-feu envoie tout le trafic Internet.", _v_ip)
        ligne.update({"Adresse IP": str(iface.ip), "Masque": str(iface.netmask), "Passerelle": gw})
        if _est_publique(iface.ip):
            p.adresse_publique = str(iface.ip)
    elif mode == "PPPoE":
        ligne["Utilisateur PPPoE"] = texte("Identifiant PPPoE fourni par l'opérateur")
        v, gen = mot_de_passe(f"Mot de passe PPPoE ({p.wan_port})", generer_ok=False)
        ligne["Mot de passe PPPoE"] = p.secret(f"Mot de passe PPPoE ({p.wan_port})", v, gen)
    p.ligne("Interfaces", **ligne)
    p.resume.append(f"Internet : {p.wan_port} en {mode}")
    if mode == "DHCP":
        p.a_faire.append("Sur la box : placer l'adresse du pare-feu en DMZ (ou la box en mode « bridge ») pour que "
                         "les redirections et les VPN fonctionnent.")

    if not p.adresse_publique and oui_non(
            "Le client a-t-il une adresse IP publique FIXE ?", situation in ("pme", "multi"),
            "Nécessaire pour les VPN et les accès depuis Internet. Avec une box, l'IP publique est celle de la box "
            "(visible sur https://ifconfig.me depuis un PC du client). Sans IP fixe, utilisez un nom DNS dynamique."):
        p.adresse_publique = texte("Adresse IP publique ou nom DNS", aide="Ex. 203.0.113.10 ou vpn.client.fr")
    elif not p.adresse_publique:
        p.adresse_publique = texte("Nom DNS dynamique (si le client en a un, sinon Entrée)", "", vide_ok=True,
                                   aide="Ex. client.dyndns.org. Facultatif : utile pour le VPN télétravail.")

    if oui_non("Y a-t-il un DEUXIÈME accès Internet (4G, 2e fibre, ADSL) ?", False,
               "Le pare-feu peut basculer automatiquement sur le 2e lien en cas de panne, ou utiliser les deux en même temps."):
        port2 = port_reseau(texte("Port du XGS relié au 2e accès", "Port3", valider=_v_port))
        mode2 = choix("Ce 2e lien est fourni :", [("DHCP", "Par une box ou un routeur 4G (adresse automatique)"),
                                                  ("Statique", "Avec une IP fixe"), ("PPPoE", "En PPPoE")], 1)
        l2 = {"Port": port2, "Zone": "WAN", "Mode": mode2, "Description": "Accès Internet secondaire"}
        if mode2 == "Statique":
            iface = ipaddress.IPv4Interface(texte("IP du pare-feu sur ce lien, avec le masque", valider=_v_iface))
            l2.update({"Adresse IP": str(iface.ip), "Masque": str(iface.netmask),
                       "Passerelle": texte("Passerelle", str(next(iface.network.hosts())), valider=_v_ip)})
        elif mode2 == "PPPoE":
            l2["Utilisateur PPPoE"] = texte("Identifiant PPPoE")
            v, gen = mot_de_passe(f"Mot de passe PPPoE ({port2})", generer_ok=False)
            l2["Mot de passe PPPoE"] = p.secret(f"Mot de passe PPPoE ({port2})", v, gen)
        p.ligne("Interfaces", **l2)
        if choix("Comment utiliser ce 2e lien ?", [
                ("secours", "En secours : utilisé seulement si le lien principal tombe (conseillé pour une 4G)"),
                ("les2", "Les deux en même temps (répartition de charge)")], 1) == "secours":
            p.general["Port WAN de secours"] = port2
            p.resume.append(f"Internet de secours : {port2} ({mode2})")
            p.a_faire.append("Vérifier dans Routage > Passerelles que la passerelle du lien de secours est bien en mode "
                             "« Backup » (le script le règle si son nom est trouvé).")
        else:
            p.resume.append(f"2e accès Internet : {port2} ({mode2}), répartition de charge")


def etape_lan(p: Projet, situation: str) -> None:
    titre("3. RÉSEAU LOCAL (LAN)")
    info("Le LAN est le réseau des PC du client. Le pare-feu y a une adresse IP qui sert de « passerelle » : "
         "c'est par elle que les PC sortent sur Internet.")
    p.lan_port = port_reseau(texte("Port du XGS relié au switch du réseau local", "Port1", valider=_v_port))
    if situation == "remplacement" or oui_non("Le client a-t-il déjà un réseau en place dont il faut garder les adresses ?",
                                             situation != "petit",
                                             "Si les PC ont déjà des adresses (ex. 192.168.1.x) et des équipements en IP "
                                             "fixe (imprimantes, serveurs), on garde le même réseau pour ne rien casser."):
        iface = ipaddress.IPv4Interface(texte(
            "IP que doit prendre le pare-feu sur le LAN, avec le masque", "192.168.1.254/24",
            "Reprenez l'adresse de l'ancien routeur / de la passerelle actuelle des PC (commande ipconfig sur un PC : "
            "ligne « Passerelle par défaut »). Ex. 192.168.1.1/24.", _v_iface))
    else:
        conseil("Évitez 192.168.0.x et 192.168.1.x : ce sont les adresses des box à la maison, ce qui bloque le VPN "
                "télétravail. Choisissez par exemple 192.168.10.0/24.")
        iface = ipaddress.IPv4Interface(texte("IP du pare-feu sur le LAN, avec le masque", "192.168.10.254/24",
                                              "Le masque /24 permet 254 appareils, suffisant dans la plupart des cas.",
                                              _v_iface))
    p.lan_iface = iface
    p.reseaux_internes.append(str(iface.network))
    p.zones_internes.append("LAN")
    p.ligne("Hôtes", Nom="RES-LAN", Type="Réseau", Adresse=str(iface.network.network_address),
            **{"Masque / IP de fin": str(iface.netmask), "Description": "Réseau local principal"})
    p.resume.append(f"LAN : {p.lan_port}, pare-feu en {iface}")
    if p.zero_touch:
        p.general["Adresse IP du pare-feu"] = str(iface.ip)   # Central lui a déjà donné cette adresse
    elif str(iface.ip) != "172.16.16.16" or p.lan_port != "Port1":
        p.ligne("Interfaces", Port=p.lan_port, Zone="LAN", Mode="Statique", **{"Adresse IP": str(iface.ip),
                "Masque": str(iface.netmask), "Description": "Réseau local"})
        pc = str(list(iface.network.hosts())[-5])
        p.general["_ip_pc_apres"] = pc
        p.a_faire.insert(0, f"AVANT de lancer : dans Sauvegarde et firmware > API, autorisez l'IP actuelle de votre PC "
                            f"ET l'adresse {pc} (le script vous demandera de passer votre PC sur cette adresse quand "
                            f"l'IP du pare-feu changera).")


def etape_dhcp(p: Projet, situation: str) -> None:
    titre("4. DISTRIBUTION DES ADRESSES (DHCP)")
    info("Le DHCP donne automatiquement une adresse IP à chaque PC, téléphone ou imprimante qui se branche. "
         "Un seul équipement doit le faire sur un réseau, sinon c'est le désordre.")
    qui = choix("Qui doit distribuer les adresses sur le réseau local ?", [
        ("fw", "Le pare-feu (conseillé s'il n'y a pas de serveur Windows)"),
        ("srv", "Un serveur Windows du client (rôle DHCP), ou un autre équipement : le pare-feu ne fait rien"),
    ], 2 if situation == "pme" else 1,
        "Avec un Active Directory, le DHCP est souvent sur le serveur Windows : laissez-le. En cas de doute, "
        "regardez sur un PC (ipconfig /all, ligne « Serveur DHCP »).")
    if qui != "fw":
        p.resume.append("DHCP : assuré par un autre équipement")
        if situation in ("remplacement",):
            p.a_faire.append("Si l'ancien routeur distribuait les adresses, vérifiez que le DHCP est bien repris par un équipement.")
        return
    _dhcp_pour(p, "DHCP-LAN", p.lan_port, p.lan_iface, principal=True)
    if oui_non("Certains appareils doivent-ils toujours recevoir la même adresse (imprimantes, caméras...) ?", False,
               "C'est une « réservation » : on associe l'adresse MAC de l'appareil (inscrite sur son étiquette ou dans "
               "son menu réseau) à une IP. Vous pouvez aussi mettre une IP fixe directement dans l'appareil."):
        while True:
            nom = texte("Nom de l'appareil (Entrée pour terminer)", "", vide_ok=True)
            if not nom:
                break
            mac = texte("Adresse MAC", valider=_v_mac)
            ip = texte("Adresse IP réservée", valider=_v_ip)
            p.ligne("Réservations DHCP", **{"Serveur DHCP": "DHCP-LAN", "Nom de l'appareil": nom, "Adresse MAC": mac,
                                            "Adresse IP": ip})


def _dhcp_pour(p: Projet, nom: str, interface: str, iface: ipaddress.IPv4Interface, principal=False) -> None:
    debut, fin = _plage_dhcp(iface)
    if principal:
        info(f"Proposition : distribuer de {debut} à {fin}. Les adresses en dehors de cette plage restent libres "
             f"pour les équipements en IP fixe (serveurs, imprimantes...).")
        debut = texte("Première adresse distribuée", debut, valider=_v_ip)
        fin = texte("Dernière adresse distribuée", fin, valider=_v_ip)
    dns1 = p.ad_ip if p.ad_ip else ""
    ligne = {"Nom": nom, "Interface": interface, "Début de plage": debut, "Fin de plage": fin,
             "Masque": str(iface.netmask), "Passerelle": str(iface.ip), "DNS 1": dns1,
             "Domaine": p.domaine, "Durée du bail (minutes)": 1440}
    p.ligne("DHCP", **ligne)
    p.resume.append(f"DHCP {nom} : {debut} → {fin}" + (f", DNS {dns1}" if dns1 else ", DNS = pare-feu"))


def etape_serveurs(p: Projet, situation: str) -> None:
    titre("5. SERVEURS ET ÉQUIPEMENTS IMPORTANTS")
    info("Déclarer les serveurs permet de les utiliser dans les règles, les VPN et les accès depuis Internet.")
    if oui_non("Le client a-t-il un Active Directory (domaine Windows) ?", situation in ("pme", "multi"),
                        "Un Active Directory, c'est un serveur Windows qui gère les comptes (connexion « DOMAINE\\nom »). "
                        "Sur un PC : Paramètres > Système > Informations, ligne « Domaine »."):
        p.ad_ip = texte("IP du contrôleur de domaine", valider=_v_ip)
        p.domaine = texte("Nom du domaine", "", "Ex. dupont.local ou ad.dupont.fr",
                          lambda t: None if "." in t else "Un nom de domaine contient un point, ex. dupont.local")
        p.serveurs.append(("SRV-AD", p.ad_ip, "Contrôleur de domaine"))
        p.ligne("Hôtes", Nom="SRV-AD", Type="IP", Adresse=p.ad_ip, Description=f"Contrôleur de domaine {p.domaine}")
        if oui_non("Relier le pare-feu à l'Active Directory ?", False,
                   "Permet ensuite d'écrire des règles par utilisateur/groupe Windows et d'utiliser les comptes Windows "
                   "pour le VPN. Il faut un compte de service dans l'AD (un simple utilisateur du domaine suffit)."):
            p.general.update({"AD : adresse IP": p.ad_ip, "AD : domaine": p.domaine,
                              "AD : nom NetBIOS": texte("Nom NetBIOS du domaine", p.domaine.split(".")[0].upper(),
                                                        "Nom court du domaine, ex. DUPONT (affiché avant le \\ à la connexion)."),
                              "AD : compte de service": texte("Compte de service (ex. svc-firewall)")})
            v, gen = mot_de_passe("Mot de passe du compte de service AD", generer_ok=False)
            p.general["AD : mot de passe"] = p.secret("Mot de passe du compte de service AD", v, gen)
            p.resume.append(f"Pare-feu relié à l'Active Directory {p.domaine}")
            p.a_faire.append("Active Directory : dans Authentification > Serveurs, cliquez sur « Tester la connexion », "
                             "puis importez les groupes si vous voulez des règles par groupe.")
    if oui_non("Y a-t-il d'autres serveurs ou équipements importants (NAS, logiciel métier, NVR caméras, IPBX...) ?",
               situation in ("pme", "multi"), "Seulement ceux qui ont une IP fixe et qui serviront dans une règle, "
                                                 "un VPN ou un accès depuis Internet."):
        types = [("SRV", "Serveur (fichiers, applicatif, logiciel métier)"), ("NAS", "NAS"),
                 ("NVR", "Enregistreur de caméras (NVR)"), ("IPBX", "Téléphonie (IPBX)"),
                 ("IMP", "Imprimante / copieur"), ("EQ", "Autre équipement")]
        while True:
            t = choix("Type d'équipement", types + [("fin", "J'ai terminé")], len(types) + 1)
            if t == "fin":
                break
            nom = texte("Nom de l'équipement", f"{t}-{len(p.serveurs) + 1:02d}", valider=_v_nom).replace(" ", "-").upper()
            ip = texte(f"Adresse IP de {nom}", valider=_v_ip)
            lib = dict(types)[t]
            p.serveurs.append((nom, ip, lib))
            p.ligne("Hôtes", Nom=nom, Type="IP", Adresse=ip, Description=lib)
    if p.serveurs:
        p.resume.append("Équipements déclarés : " + ", ".join(f"{n} ({i})" for n, i, _ in p.serveurs))


def etape_vlan(p: Projet, situation: str, dhcp_fw: bool) -> None:
    titre("6. DÉCOUPAGE DU RÉSEAU (VLAN)")
    info("Un VLAN est un réseau séparé qui passe sur les mêmes câbles et switchs. On l'utilise pour isoler des "
         "équipements : caméras, téléphonie, Wi-Fi invités, serveurs... Le pare-feu contrôle ce qui passe entre eux.")
    if not oui_non("Le réseau doit-il être découpé en VLAN ?", False,
                   "Si les switchs du client ne sont pas « manageables » (configurables), répondez non. Si vous ne "
                   "savez pas, répondez non : on peut l'ajouter plus tard."):
        return
    p.a_faire.append(f"Sur le switch : configurer le port relié au {p.lan_port} du pare-feu en « trunk » (VLAN tagués) "
                     "et chaque port d'équipement dans son VLAN.")
    modeles = [
        ("TELEPHONIE", "Téléphonie IP", True, True),
        ("CAMERAS", "Caméras / vidéosurveillance", False, False),
        ("SERVEURS", "Serveurs", True, True),
        ("INVITES", "Invités (filaire ou bornes Wi-Fi non Sophos)", True, False),
        ("IOT", "Objets connectés / équipements techniques", False, False),
        ("AUTRE", "Autre (je donne le nom)", True, False),
    ]
    vid = 10
    while True:
        c = choix("Quel VLAN ajouter ?", [(m[0], m[1]) for m in modeles] + [("fin", "J'ai terminé")], len(modeles) + 1)
        if c == "fin":
            break
        m = next(x for x in modeles if x[0] == c)
        nom = c if c != "AUTRE" else texte("Nom du VLAN (ex. ATELIER)", valider=_v_nom).upper().replace(" ", "-")
        vid = int(texte("Numéro de VLAN (le même que sur le switch)", str(vid),
                        "Entre 1 et 4094. Demandez-le à la personne qui gère les switchs.",
                        lambda t: None if t.isdigit() and 1 <= int(t) <= 4094 else "Nombre entre 1 et 4094."))
        iface = ipaddress.IPv4Interface(texte(f"IP du pare-feu dans le VLAN {nom}, avec masque", str(_suivant_reseau(p)),
                                              "Chaque VLAN est un réseau différent.", _v_iface))
        interface = f"{p.lan_port}.{vid}"
        p.ligne("Zones", Nom=nom, Type="LAN", Description=m[1], Ping="Oui", **{"Admin HTTPS": "Non"}, SSH="Non", DNS="Oui")
        p.ligne("VLAN", **{"Interface physique": p.lan_port, "ID VLAN": vid, "Zone": nom, "Adresse IP": str(iface.ip),
                           "Masque": str(iface.netmask), "Description": m[1]})
        p.ligne("Hôtes", Nom=f"RES-{nom}", Type="Réseau", Adresse=str(iface.network.network_address),
                **{"Masque / IP de fin": str(iface.netmask), "Description": f"VLAN {vid} {m[1]}"})
        if dhcp_fw and oui_non(f"Le pare-feu distribue-t-il les adresses dans le VLAN {nom} ?", c != "SERVEURS"):
            _dhcp_pour(p, f"DHCP-{nom}", interface, iface)
        if oui_non(f"Le VLAN {nom} peut-il aller sur Internet ?", m[2]):
            p.ligne("Règles", Nom=f"{nom} vers Internet", Action="Accepter", **{"Zones source": nom,
                    "Réseaux source": f"RES-{nom}", "Zones destination": "WAN"}, Journaliser="Oui",
                    **{"Filtrage web": "_WEB_", "IPS": "_IPS_"})
        if oui_non(f"Les PC du réseau principal doivent-ils pouvoir joindre le VLAN {nom} ?", m[3]):
            p.ligne("Règles", Nom=f"LAN vers {nom}", Action="Accepter", **{"Zones source": "LAN", "Réseaux source": "RES-LAN",
                    "Zones destination": nom, "Réseaux destination": f"RES-{nom}"}, Journaliser="Oui")
        if oui_non(f"Les équipements du VLAN {nom} doivent-ils pouvoir joindre le réseau principal ?", False,
                   "Pour la sécurité, on répond non sauf besoin précis (ex. serveurs qui doivent joindre les PC)."):
            p.ligne("Règles", Nom=f"{nom} vers LAN", Action="Accepter", **{"Zones source": nom, "Réseaux source": f"RES-{nom}",
                    "Zones destination": "LAN", "Réseaux destination": "RES-LAN"}, Journaliser="Oui")
        p.reseaux_internes.append(str(iface.network))
        p.zones_internes.append(nom)
        p.resume.append(f"VLAN {vid} {nom} : {iface}")
        vid += 10


def etape_wifi(p: Projet) -> None:
    titre("7. WI-FI")
    if not oui_non("Le client a-t-il des bornes Wi-Fi Sophos (APX / AP6) gérées par le pare-feu ?", False,
                   "Seules les bornes Sophos se configurent depuis le pare-feu. Pour d'autres marques (Ubiquiti, "
                   "Aruba...), le Wi-Fi invités se fait avec un VLAN « INVITES » à l'étape précédente."):
        return
    p.a_faire.append("Bornes Wi-Fi : dans Protéger > Sans fil > Points d'accès, acceptez les bornes détectées et "
                     "affectez-leur les réseaux Wi-Fi créés.")
    if oui_non("Créer un Wi-Fi pour les salariés (même réseau que les PC) ?", True):
        ssid = texte("Nom du Wi-Fi salariés (SSID)", f"{_slug(p.general['Nom du client']).upper()}")
        v, gen = mot_de_passe(f"Clé Wi-Fi ({ssid})", "Mot de passe du Wi-Fi, 8 caractères minimum.")
        p.ligne("Wi-Fi", Nom="WIFI-SALARIES", SSID=ssid, **{"Clé Wi-Fi": p.secret(f"Clé Wi-Fi ({ssid})", v, gen)},
                Mode="Pont vers le LAN", **{"Isolation des clients": "Non", "SSID masqué": "Non"})
        p.resume.append(f"Wi-Fi salariés « {ssid} » (même réseau que le LAN)")
    if oui_non("Créer un Wi-Fi invités (isolé, Internet uniquement) ?", True):
        ssid = texte("Nom du Wi-Fi invités (SSID)", f"{_slug(p.general['Nom du client']).upper()}-INVITES")
        v, gen = mot_de_passe(f"Clé Wi-Fi ({ssid})")
        iface = ipaddress.IPv4Interface(texte("IP du pare-feu sur le Wi-Fi invités", "10.99.0.254/24",
                                              "Réseau totalement séparé du réseau de l'entreprise.", _v_iface))
        p.ligne("Wi-Fi", Nom="WIFI-INVITES", SSID=ssid, **{"Clé Wi-Fi": p.secret(f"Clé Wi-Fi ({ssid})", v, gen)},
                Mode="Zone séparée", Zone="WiFi", **{"Adresse IP": str(iface.ip), "Masque": str(iface.netmask),
                                                    "Isolation des clients": "Oui", "SSID masqué": "Non"})
        debut, fin = _plage_dhcp(iface)
        p.ligne("DHCP", Nom="DHCP-WIFI-INVITES", Interface="wlnet2" if p.lignes.get("Wi-Fi") and len(p.lignes["Wi-Fi"]) > 1 else "wlnet1",
                **{"Début de plage": debut, "Fin de plage": fin, "Masque": str(iface.netmask), "Passerelle": str(iface.ip),
                   "Durée du bail (minutes)": 240})
        p.ligne("Règles", Nom="Wi-Fi invités vers Internet", Action="Accepter", **{"Zones source": "WiFi",
                "Zones destination": "WAN", "Services": "HTTP;HTTPS;DNS"}, Journaliser="Oui",
                **{"Filtrage web": "_WEB_"})
        p.resume.append(f"Wi-Fi invités « {ssid} » : réseau {iface.network} isolé, Internet uniquement (web)")
        p.infos_client.append(f"Wi-Fi invités : {ssid} (clé à communiquer aux visiteurs)")


def etape_securite(p: Projet) -> None:
    titre("8. SORTIE SUR INTERNET ET PROTECTIONS")
    info("On crée la règle principale qui autorise les PC à aller sur Internet, avec les protections Sophos.")
    acces = choix("Que peuvent faire les PC du réseau local sur Internet ?", [
        ("tout", "Tout (conseillé pour commencer : tout est autorisé mais analysé)"),
        ("web", "Uniquement le web et les e-mails (HTTP, HTTPS, DNS, IMAP/SMTP sécurisés)"),
    ], 1, "« Uniquement le web » est plus sûr, mais peut bloquer des logiciels (VPN de fournisseurs, logiciels "
          "métier, mises à jour spécifiques). On peut toujours ajouter des règles ensuite.")
    web = ips = appli = ""
    if oui_non("Activer le filtrage web (bloquer les sites dangereux, adultes, piratage...) ?", True,
               "Utilise la stratégie d'origine « Default Workplace Policy ». Vous pourrez l'ajuster dans Protéger > Web."):
        web = "Default Workplace Policy"
    if oui_non("Activer la prévention d'intrusion (IPS) ?", True,
               "Bloque les attaques connues dans le trafic. Nécessite la licence Network Protection (incluse dans les "
               "packs Standard/Xstream)."):
        ips = "lantowan_general"
    if oui_non("Bloquer les applications indésirables (proxy de contournement, P2P...) ?", True,
               "Utilise la stratégie d'origine « Block generally unwanted apps »."):
        appli = "Block generally unwanted apps"
    av = oui_non("Analyser les téléchargements (antivirus) ?", True, "Nécessite la licence Web Protection.")
    reseaux = ";".join(["RES-LAN"])
    p.ligne("Règles", Nom="LAN vers Internet", Action="Accepter",
            **{"Zones source": "LAN", "Réseaux source": reseaux, "Zones destination": "WAN",
               "Services": "" if acces == "tout" else "HTTP;HTTPS;DNS;TCP 993;TCP 465;TCP 587",
               "Journaliser": "Oui", "Filtrage web": web, "Contrôle d'applications": appli, "IPS": ips,
               "Antivirus": "Oui" if av else "Non", "Description": "Accès Internet des postes"})
    # remplace les marqueurs des règles créées plus tôt (VLAN, Wi-Fi)
    for r in p.lignes.get("Règles", []):
        if r.get("Filtrage web") == "_WEB_":
            r["Filtrage web"] = web
        if r.get("IPS") == "_IPS_":
            r["IPS"] = ips
    prot = [n for n, v in (("filtrage web", web), ("IPS", ips), ("contrôle d'applications", appli), ("antivirus", av)) if v]
    p.resume.append("Accès Internet des PC : " + ("tout" if acces == "tout" else "web et e-mail uniquement")
                    + (f", protections : {', '.join(prot)}" if prot else ""))
    if prot:
        p.a_faire.append("Les protections (filtrage web, IPS, antivirus...) ne fonctionnent qu'avec les licences "
                         "actives : vérifiez dans Administration > Licences.")


def etape_redirections(p: Projet) -> None:
    titre("9. ACCÈS DEPUIS INTERNET (REDIRECTIONS DE PORTS)")
    info("Une redirection rend un équipement interne joignable depuis Internet (caméras, serveur web, messagerie...). "
         "Chaque redirection est une porte ouverte : n'en créez que si c'est indispensable.")
    if not oui_non("Faut-il rendre un équipement interne accessible depuis Internet ?", False,
                   "Pour un accès à distance aux PC ou aux serveurs (bureau à distance, fichiers), le VPN télétravail "
                   "est BEAUCOUP plus sûr qu'une redirection."):
        return
    services = [("HTTPS", "Site / interface web sécurisée (HTTPS, 443)"),
                ("SMTP", "Réception de la messagerie (SMTP, 25)"),
                ("PERSO", "Autre : je donne le protocole et le port"),
                ("RDP", "Bureau à distance (RDP, 3389) — DÉCONSEILLÉ")]
    n = 1
    while True:
        cible = texte("Adresse IP (ou nom) de l'équipement à rendre accessible (Entrée pour terminer)", "", vide_ok=True,
                      aide="Les équipements déclarés : " + ", ".join(f"{a} = {b}" for a, b, _ in p.serveurs))
        if not cible:
            break
        connu = next((s for s in p.serveurs if cible in (s[0], s[1])), None)
        nom_srv = connu[0] if connu else cible
        s = choix("Quel service ?", services, 1)
        port_int = ""
        if s == "RDP":
            print(f"{R}{_wrap('Le bureau à distance exposé sur Internet est la première cause de rançongiciels. Préférez le VPN télétravail.')}{F}")
            if not oui_non("Créer quand même cette redirection ?", False):
                continue
            externe = texte("Port externe (utiliser un autre port que 3389 limite les attaques automatiques)", "TCP 33890")
            port_int = "3389"
        elif s == "PERSO":
            proto = choix("Protocole", [("TCP", "TCP (le plus courant)"), ("UDP", "UDP")], 1)
            pe = texte("Port vu depuis Internet", valider=lambda t: None if t.isdigit() and 0 < int(t) < 65536 else "Port invalide.")
            pi = texte("Port sur l'équipement (si différent)", pe,
                       valider=lambda t: None if t.isdigit() and 0 < int(t) < 65536 else "Port invalide.")
            externe = f"{proto} {pe}"
            port_int = pi if pi != pe else ""
        else:
            externe = s
        sources = ""
        if oui_non("Limiter l'accès à certaines adresses IP (ex. le prestataire) ?", s == "RDP",
                   "Fortement conseillé quand on sait qui se connecte : les autres adresses seront bloquées."):
            sources = texte("Adresses ou réseaux autorisés (séparés par ;)", valider=_v_reseaux)
        zone = "LAN"
        if len(p.zones_internes) > 1:
            zone = choix("Dans quelle zone est l'équipement ?", [(z, z) for z in p.zones_internes], 1)
        nom = f"PUBLI-{nom_srv}-{n}".upper().replace(" ", "-")
        p.ligne("Redirections", Nom=nom, **{"Port WAN": p.wan_port, "Service externe": externe, "Serveur interne": cible,
                "Port interne": port_int, "Zone du serveur": zone, "Sources autorisées": sources})
        p.resume.append(f"Redirection : Internet {externe} → {nom_srv}" + (f":{port_int}" if port_int else "")
                        + (f" (depuis {sources} uniquement)" if sources else ""))
        n += 1


def etape_vpn_sites(p: Projet, situation: str) -> None:
    titre("10. VPN ENTRE SITES")
    info("Un VPN site à site relie deux réseaux (siège et agence) par un tunnel chiffré sur Internet : les PC "
         "d'un site joignent les serveurs de l'autre comme s'ils étaient sur place.")
    if not oui_non("Faut-il relier ce site à un ou plusieurs autres sites ?", situation == "multi"):
        return
    if not p.adresse_publique:
        conseil("Ce pare-feu n'a pas d'IP publique fixe déclarée : il devra « initier » le tunnel vers l'autre site.")
    while True:
        nom = texte("Nom du site distant (Entrée pour terminer)", "", vide_ok=True, valider=_v_nom)
        if not nom:
            break
        nom_vpn = f"VPN-{nom.upper().replace(' ', '-')}"
        distant = texte(f"IP publique ou nom DNS du pare-feu de {nom}")
        reseaux = texte(f"Réseau(x) de {nom} (ex. 192.168.20.0/24 ; séparés par ;)", valider=_v_reseaux)
        locaux = texte("Réseau(x) d'ici à partager", ";".join(p.reseaux_internes), valider=_v_reseaux)
        v, gen = mot_de_passe(f"Clé partagée du VPN {nom_vpn}",
                              "La même clé doit être saisie sur le pare-feu d'en face. Générez-la et transmettez-la "
                              "par un moyen sûr (pas par e-mail en clair).")
        role = choix("Quel pare-feu lance la connexion ?", [
            ("Initier", "Celui-ci (conseillé si l'autre site a une IP fixe)"),
            ("Répondre", "L'autre : celui-ci attend la connexion")], 1)
        profil = texte("Profil de chiffrement IPsec", "IKEv2",
                       "Doit être identique des deux côtés. Sur deux Sophos, gardez le même profil. Le script vérifie "
                       "que ce profil existe et affiche les profils disponibles sinon.")
        p.ligne("VPN sites", Nom=nom_vpn, **{"Port WAN": p.wan_port, "Adresse du site distant": distant,
                "Réseaux locaux": locaux, "Réseaux distants": reseaux,
                "Clé partagée": p.secret(f"Clé partagée du VPN {nom_vpn}", v, gen), "Profil IPsec": profil, "Rôle": role})
        p.resume.append(f"VPN site à site {nom_vpn} : {locaux} ⇄ {reseaux} ({distant})")
        p.vpn_sites.append({"nom": nom_vpn, "site": nom, "distant": distant, "locaux": locaux, "reseaux": reseaux,
                            "profil": profil, "role": role})
        p.a_faire.append(f"VPN {nom_vpn} : configurer l'autre pare-feu en miroir (réseaux locaux/distants inversés, "
                         f"même clé, même profil, adresse distante = {p.adresse_publique or 'IP publique de ce site'}), "
                         f"puis activer la connexion dans VPN > IPsec.")


def etape_teletravail(p: Projet, situation: str) -> None:
    titre("11. VPN TÉLÉTRAVAIL")
    info("Le VPN télétravail permet à un salarié, depuis chez lui, d'accéder aux serveurs et fichiers de l'entreprise "
         "de façon sécurisée. Chaque personne a un identifiant et installe le logiciel Sophos Connect.")
    if not oui_non("Des personnes doivent-elles se connecter à distance ?", situation in ("pme", "multi")):
        return
    adresse = texte("Adresse publique du pare-feu (IP ou nom DNS)", p.adresse_publique,
                    "C'est l'adresse que les postes en télétravail contacteront.")
    p.adresse_publique = adresse
    reseaux = texte("Réseaux accessibles en VPN (séparés par ;)", ";".join(p.reseaux_internes), valider=_v_reseaux)
    pris = [ipaddress.IPv4Network(r, strict=False) for r in p.reseaux_internes]
    for v in p.lignes.get("VPN sites", []):
        pris += [ipaddress.IPv4Network(x.strip(), strict=False) for x in re.split(r"[;,]", v["Réseaux distants"]) if x.strip()]
    for troisieme in range(234, 254):
        pool = ipaddress.IPv4Network(f"10.81.{troisieme}.0/24")
        if not any(pool.overlaps(n) for n in pris):
            break
    p.general.update({"Début plage VPN": str(pool.network_address + 5), "Fin plage VPN": str(pool.network_address + 55),
                      "Masque plage VPN": "255.255.255.0"})
    p.general.update({"VPN télétravail activé": "Oui", "Adresse publique du pare-feu": adresse,
                      "Réseaux accessibles en VPN": reseaux, "DNS pour les clients VPN": p.ad_ip,
                      "Domaine pour les clients VPN": p.domaine})
    info("Créons maintenant les comptes des personnes autorisées.")
    generer_tous = oui_non("Générer automatiquement les mots de passe des comptes ?", True,
                           "Les mots de passe sont affichés à la fin : à transmettre à chaque personne.")
    while True:
        ident = texte("Identifiant de la personne (ex. jdupont ; Entrée pour terminer)", "", vide_ok=True,
                      valider=lambda t: None if re.fullmatch(r"[a-zA-Z0-9._-]{2,40}", t) else "Lettres, chiffres, . _ - uniquement.")
        if not ident:
            if not any(c.get("VPN télétravail") == "Oui" for c in p.lignes.get("Comptes", [])):
                print(f"{J}   Il faut au moins un compte pour le VPN.{F}")
                continue
            break
        nom = texte("Nom et prénom", ident)
        mail = texte("E-mail (facultatif)", "", vide_ok=True, valider=_v_email)
        if generer_tous:
            v, gen = generer_mdp(14), True
        else:
            v, gen = mot_de_passe(f"Mot de passe du compte {ident}", generer_ok=False)
        p.ligne("Comptes", Identifiant=ident, **{"Nom complet": nom}, Type="Utilisateur", **{"E-mail": mail,
                "Mot de passe": p.secret(f"Mot de passe du compte {ident}", v, gen), "VPN télétravail": "Oui"})
        p.teletravailleurs.append({"identifiant": ident, "nom": nom, "email": mail})
    nb = sum(1 for c in p.lignes.get("Comptes", []) if c.get("VPN télétravail") == "Oui")
    p.resume.append(f"VPN télétravail (SSL VPN) : {nb} compte(s), accès à {reseaux}")
    p.infos_client.append("Télétravail : chaque personne installe Sophos Connect, se connecte au portail utilisateur "
                          "du pare-feu avec son identifiant pour récupérer sa configuration VPN, puis l'importe.")
    p.a_faire.append("VPN télétravail : testez une connexion depuis l'extérieur (partage de connexion d'un téléphone) "
                     "avec un des comptes créés.")


def etape_administration(p: Projet) -> None:
    titre("12. ADMINISTRATION, ALERTES ET SAUVEGARDES")
    fuseau = PARAMS.get("fuseau_defaut") or "Europe/Paris"
    if not oui_non(f"Le client est-il dans le fuseau horaire {FUSEAUX.get(fuseau, fuseau)} ?", True):
        fuseau = choix("Quel fuseau horaire ?", [(k, v) for k, v in FUSEAUX.items()] + [("autre", "Autre")], 1)
        if fuseau == "autre":
            fuseau = texte("Nom du fuseau (format Région/Ville)", "Europe/Paris",
                           "Ex. Europe/Madrid, America/Cayenne, Pacific/Noumea, Africa/Casablanca.",
                           lambda t: None if re.fullmatch(r"[A-Za-z_]+/[A-Za-z_/-]+", t) else "Format attendu : Région/Ville")
    p.general["Fuseau horaire"] = fuseau
    wan_statique = any(l.get("Mode") == "Statique" and l.get("Zone") == "WAN" for l in p.lignes.get("Interfaces", []))
    if wan_statique or oui_non("Choisir les serveurs DNS du pare-feu (sinon ceux de l'opérateur) ?", False,
                               "Les DNS traduisent les noms (google.fr) en adresses. Ceux de l'opérateur conviennent "
                               "en général. Avec une IP fixe, il faut les indiquer."):
        p.general["DNS 1"] = texte("DNS 1", "1.1.1.1", "1.1.1.1 (Cloudflare), 9.9.9.9 (Quad9), 8.8.8.8 (Google)...", _v_ip)
        p.general["DNS 2"] = texte("DNS 2", "9.9.9.9", valider=_v_ip)

    if oui_non("Créer un compte administrateur nominatif pour votre société (au lieu d'utiliser « admin ») ?", True,
               "Bonne pratique : chaque technicien a son compte, on sait qui a fait quoi, et le compte « admin » "
               "reste en secours."):
        ident = texte("Identifiant administrateur", PARAMS.get("prefixe_admin") or "admin-presta",
                      valider=lambda t: None if re.fullmatch(r"[a-zA-Z0-9._-]{2,40}", t) else "Lettres, chiffres, . _ -")
        v, gen = mot_de_passe(f"Mot de passe du compte {ident}")
        p.ligne("Comptes", Identifiant=ident, **{"Nom complet": "Administrateur prestataire"}, Type="Administrateur",
                **{"Mot de passe": p.secret(f"Mot de passe du compte {ident}", v, gen), "VPN télétravail": "Non",
                   "Profil admin": "Administrator"})
        p.resume.append(f"Compte administrateur : {ident}")

    smtp = False
    if oui_non("Recevoir les alertes du pare-feu par e-mail ?", True,
               "Le pare-feu prévient en cas de problème (lien Internet coupé, VPN tombé, attaque...)."):
        fournisseur = choix("Quel service d'envoi d'e-mails ?", [
            ("m365", "Microsoft 365 / Outlook (smtp.office365.com)"), ("gmail", "Gmail / Google Workspace (smtp.gmail.com)"),
            ("autre", "Autre serveur SMTP")], 1,
            "Le pare-feu a besoin d'un compte e-mail pour envoyer. Avec Microsoft 365 ou Gmail, utilisez un compte "
            "dédié ; un « mot de passe d'application » peut être nécessaire.")
        serveur, port = {"m365": ("smtp.office365.com", "587"), "gmail": ("smtp.gmail.com", "587")}.get(fournisseur, ("", "587"))
        if fournisseur == "autre":
            serveur = texte("Adresse du serveur SMTP")
            port = texte("Port SMTP", "587", "587 (STARTTLS) le plus souvent, 465 (SSL/TLS), 25 (sans chiffrement).")
        exp = texte("Adresse expéditeur (compte utilisé pour envoyer)", valider=_v_email)
        dest = texte("Adresse qui reçoit les alertes", PARAMS.get("email_support", ""), valider=_v_email)
        p.general.update({"Serveur SMTP": serveur, "Port SMTP": port,
                          "Sécurité SMTP": {"465": "SSL/TLS", "25": "Aucune"}.get(port, "STARTTLS"),
                          "Adresse expéditeur": exp, "Destinataire des alertes": dest})
        if oui_non("Ce serveur demande-t-il un identifiant et un mot de passe ?", fournisseur != "autre"):
            p.general["Utilisateur SMTP"] = texte("Identifiant SMTP", exp)
            v, gen = mot_de_passe("Mot de passe SMTP", generer_ok=False)
            p.general["Mot de passe SMTP"] = p.secret("Mot de passe SMTP", v, gen)
        p.resume.append(f"Alertes e-mail vers {dest}")
        smtp = True

    if oui_non("Programmer une sauvegarde automatique de la configuration ?", True,
               "Indispensable : en cas de panne, on restaure la configuration sur un boîtier neuf en quelques minutes."):
        dest_opts = ([("E-mail", "Par e-mail (le plus simple)")] if smtp else []) + [
            ("FTP", "Sur un serveur FTP"), ("Locale", "Sur le boîtier seulement (déconseillé : perdue si le boîtier meurt)")]
        dest = choix("Où envoyer la sauvegarde ?", dest_opts, 1)
        freq = choix("À quelle fréquence ?", [("Hebdomadaire", "Chaque semaine (dimanche 1h30)"),
                                             ("Quotidienne", "Chaque jour (1h30)"), ("Mensuelle", "Chaque mois")], 1)
        p.general.update({"Fréquence de sauvegarde": freq, "Destination de la sauvegarde": dest})
        if dest == "E-mail":
            p.general["E-mail de sauvegarde"] = texte("Adresse qui reçoit les sauvegardes",
                                                      p.general.get("Destinataire des alertes", ""), valider=_v_email)
        elif dest == "FTP":
            p.general["Serveur FTP"] = texte("Serveur FTP (IP ou nom)")
            p.general["Utilisateur FTP"] = texte("Utilisateur FTP")
            v, gen = mot_de_passe("Mot de passe FTP", generer_ok=False)
            p.general["Mot de passe FTP"] = p.secret("Mot de passe FTP", v, gen)
            p.general["Dossier FTP"] = texte("Dossier FTP", "/")
        v, gen = mot_de_passe("Mot de passe de chiffrement des sauvegardes",
                              "Les sauvegardes sont chiffrées : sans ce mot de passe, impossible de les restaurer.")
        p.general["Mot de passe de chiffrement de la sauvegarde"] = p.secret("Mot de passe de chiffrement des sauvegardes", v, gen)
        p.resume.append(f"Sauvegarde {freq.lower()} ({dest})")

    if oui_non("Le pare-feu doit-il être supervisé en SNMP (PRTG, Zabbix, Centreon...) ?", False):
        p.general.update({"SNMP activé": "Oui",
                          "Communauté SNMP": texte("Communauté SNMP", f"supervision-{_slug(p.general['Nom du client'])}",
                                                   "Sorte de mot de passe partagé avec l'outil de supervision. Évitez « public »."),
                          "IP du serveur de supervision": texte("IP du serveur de supervision", valider=_v_ip),
                          "Lieu": texte("Emplacement du boîtier", "Baie informatique", vide_ok=True),
                          "Contact": texte("Contact", p.general.get("Destinataire des alertes", ""), vide_ok=True)})
        p.resume.append("Supervision SNMP v2c")


def fiche_zero_touch(p: Projet) -> list[str]:
    """Valeurs à saisir dans Sophos Central pour le Zero Touch."""
    g = p.general
    wan = next((l for l in p.lignes.get("Interfaces", []) if l.get("Port") == p.wan_port), {})
    dhcp = next((l for l in p.lignes.get("DHCP", []) if l.get("Nom") == "DHCP-LAN"), None)
    nom_fw = g.get("Nom d'hôte du pare-feu", "")
    l = ["Dans Sophos Central : Pare-feux > Ajouter un pare-feu > Zero Touch, puis saisissez :",
         "  - Numéro de série du boîtier (étiquette sous le XGS)",
         f"  - Nom du pare-feu : {nom_fw}",
         f"  - Fuseau horaire : {g.get('Fuseau horaire') or 'Europe/Paris'}",
         f"  - Port Internet (WAN) : {p.wan_port}, mode {wan.get('Mode', 'DHCP')}"]
    if wan.get("Mode") == "Statique":
        l.append(f"      IP {wan.get('Adresse IP')} / {wan.get('Masque')}, passerelle {wan.get('Passerelle')}")
    elif wan.get("Mode") == "PPPoE":
        l.append(f"      identifiant PPPoE {wan.get('Utilisateur PPPoE')} (mot de passe : voir votre coffre-fort)")
    if p.lan_iface:
        l.append(f"  - Réseau local (LAN) : {p.lan_port}, IP {p.lan_iface.ip}, masque {p.lan_iface.netmask}")
    if dhcp:
        l.append(f"  - DHCP sur le LAN : de {dhcp['Début de plage']} à {dhcp['Fin de plage']}")
    if g.get("DNS 1"):
        l.append(f"  - DNS : {g['DNS 1']}" + (f", {g['DNS 2']}" if g.get("DNS 2") else ""))
    l += ["  - Mot de passe admin : choisissez-le dans Central et rangez-le dans votre coffre-fort",
          "Branchez ensuite le Port WAN sur Internet et allumez : le boîtier récupère sa configuration seul.",
          f"Puis, depuis le réseau local, activez l'API (https://{p.lan_iface.ip if p.lan_iface else 'IP'}:4444 > "
          "Sauvegarde et firmware > API) et lancez le script pour le reste de la configuration."]
    return l


FUSEAUX = {
    "Europe/Paris": "France métropolitaine", "Europe/Brussels": "Belgique", "Europe/Zurich": "Suisse",
    "Europe/Luxembourg": "Luxembourg", "America/Montreal": "Québec", "Indian/Reunion": "La Réunion",
    "America/Martinique": "Martinique", "America/Guadeloupe": "Guadeloupe", "America/Cayenne": "Guyane",
    "Indian/Mayotte": "Mayotte", "Pacific/Noumea": "Nouvelle-Calédonie", "Pacific/Tahiti": "Polynésie",
    "Africa/Casablanca": "Maroc",
}


A_FAIRE_COMMUN = [
    "Mettre à jour le firmware (Sauvegarde et firmware > Firmware) AVANT la mise en production.",
    "Vérifier les licences et l'enregistrement du boîtier (Administration > Licences).",
    "Facultatif : rattacher le boîtier à Sophos Central pour la gestion à distance (Système > Sophos Central).",
    "Tester depuis un PC : navigation Internet, accès aux serveurs, impression.",
    "Une fois tout validé : faire une sauvegarde manuelle et la ranger dans le dossier du client.",
    "Ranger tous les mots de passe dans votre coffre-fort (jamais dans un fichier Excel non protégé).",
]


def etape_fin(p: Projet) -> None:
    titre("13. RÉCAPITULATIF")
    for r in p.resume:
        print(f"  {G}✔{F} {r}")
    client = p.general["Nom du client"]
    dossier = Path("clients")
    dossier.mkdir(exist_ok=True)
    base = dossier / _slug(client)
    xlsx = f"{base}.xlsx"

    stocker = oui_non("Enregistrer aussi les mots de passe dans le fichier Excel ?", False,
                      "Déconseillé : le fichier Excel n'est pas chiffré. Si vous répondez non, ils vous seront demandés "
                      "(ou réutilisés automatiquement si vous appliquez maintenant).")
    if stocker:
        _ecrire_secrets(p)
    ip_pc = p.general.pop("_ip_pc_apres", None)
    ecrire_classeur(xlsx, p.general, p.lignes)

    a_faire = p.a_faire + A_FAIRE_COMMUN
    if p.central:
        a_faire = [a.replace("Facultatif : rattacher le boîtier à Sophos Central pour la gestion à distance (Système > Sophos Central).",
                             "Vérifier que le boîtier apparaît dans Sophos Central (Gestion des pare-feux) et accepter "
                             "la gestion ; activer les sauvegardes Central et planifier les mises à jour firmware depuis Central.")
                   for a in a_faire]
    fiche = [f"FICHE DE CONFIGURATION — {client}", "=" * 60, "", "Ce qui est configuré :"]
    fiche += [f"  - {r}" for r in p.resume]
    if p.zero_touch:
        fiche += ["", "Préconfiguration Sophos Central (Zero Touch) :"] + [f"  {x}" for x in fiche_zero_touch(p)]
    fiche += ["", "À faire à la main :"] + [f"  {i}. {a}" for i, a in enumerate(a_faire, 1)]
    if p.infos_client:
        fiche += ["", "À transmettre au client :"] + [f"  - {i}" for i in p.infos_client]
    if p.generes:
        fiche += ["", "Mots de passe générés : affichés une seule fois à l'écran, NON enregistrés dans ce fichier."]
    Path(f"{base}_fiche.txt").write_text("\n".join(fiche) + "\n", encoding="utf-8")
    fiches = ecrire_fiches_annexes(p, base)

    print(f"\n{G}Fichiers créés :{F}\n  - {xlsx}  (configuration, modifiable dans Excel)\n  - {base}_fiche.txt  (récapitulatif et étapes manuelles)")
    for f in fiches:
        print(f"  - {f}")
    try:
        from .documentation import generer
        print(f"  - {generer(xlsx)}  (dossier technique à remettre au client)")
    except Exception as exc:  # le dossier est un bonus : ne jamais bloquer la fin de l'assistant
        print(f"{J}  (dossier technique non généré : {exc}){F}")
    if p.generes:
        print(f"\n{J}{B}Mots de passe générés — NOTEZ-LES MAINTENANT (ils ne sont enregistrés nulle part) :{F}")
        for lib, v in p.generes:
            print(f"  {lib:<55} {B}{v}{F}")
    if p.zero_touch:
        print(f"\n{B}Préconfiguration Sophos Central (Zero Touch) :{F}")
        for x in fiche_zero_touch(p):
            print(f"  {x}")
    print(f"\n{B}À faire à la main :{F}")
    for i, a in enumerate(a_faire, 1):
        print(_wrap(f"{i}. {a}", "  "))

    print()
    if not oui_non("Appliquer la configuration sur le pare-feu maintenant ?", False,
                   "Le PC doit être branché sur le pare-feu, l'assistant de démarrage Sophos terminé et l'API activée "
                   "(Sauvegarde et firmware > API, avec l'IP de votre PC autorisée)."):
        print(f"\nPlus tard : {B}python -m sophos_auto.deployer {xlsx}{F}  (ou glissez le fichier sur lancer.bat)")
        return
    from .deployer import deployer
    print()
    if deployer(xlsx, simulation=True) != 0:
        return
    if oui_non("La simulation est correcte. Envoyer au pare-feu ?", True):
        deployer(xlsx, secrets=dict(p.secrets), ip_pc_apres=ip_pc)


def ecrire_fiches_annexes(p: Projet, base: Path) -> list[str]:
    """Fiche « autre site » pour chaque VPN, et fiche d'installation pour chaque télétravailleur."""
    crees = []
    client = p.general.get("Nom du client", "")
    for v in p.vpn_sites:
        f = Path(f"{base}_vpn_{_slug(v['site'])}.txt")
        f.write_text("\n".join([
            f"VPN {v['nom']} — réglages à saisir sur le pare-feu du site « {v['site']} »",
            "=" * 70, "",
            f"Ce document décrit la configuration à faire EN FACE pour le tunnel vers {client}.", "",
            "  Type de connexion      : IPsec site à site",
            f"  Adresse du site distant: {p.adresse_publique or '(IP publique de ' + client + ')'}",
            f"  Réseaux locaux         : {v['reseaux']}   (les réseaux de {v['site']})",
            f"  Réseaux distants       : {v['locaux']}   (les réseaux de {client})",
            f"  Profil de chiffrement  : {v['profil']} (identique des deux côtés)",
            "  Authentification       : clé partagée — transmise séparément, par un moyen sûr",
            f"  Rôle                   : {'Répondre (attendre la connexion)' if v['role'] == 'Initier' else 'Initier la connexion'}",
            "",
            "Pensez aussi aux règles de pare-feu dans les deux sens (VPN <-> LAN) entre ces réseaux.",
            "Les deux sites ne doivent pas utiliser le même plan d'adressage.",
        ]) + "\n", encoding="utf-8")
        crees.append(f"{f}  (à transmettre à qui gère l'autre site)")
    if p.teletravailleurs:
        dossier = Path(f"{base}_teletravail")
        dossier.mkdir(exist_ok=True)
        adresse = p.general.get("Adresse publique du pare-feu") or "(adresse communiquée par votre service informatique)"
        for u in p.teletravailleurs:
            (dossier / f"{u['identifiant']}.txt").write_text("\n".join([
                f"Accès à distance (VPN) — {u['nom']}", "=" * 60, "",
                f"Votre identifiant : {u['identifiant']}",
                "Votre mot de passe vous est communiqué séparément (jamais par e-mail avec ce document).", "",
                "Installation (une seule fois) :",
                "  1. Installez le logiciel « Sophos Connect » fourni par votre service informatique.",
                "  2. Récupérez votre fichier de configuration VPN depuis le portail utilisateur du pare-feu",
                "     (adresse fournie par votre service informatique), avec votre identifiant.",
                "  3. Ouvrez Sophos Connect > Importer une connexion > choisissez ce fichier.", "",
                "Utilisation :",
                "  - Cliquez sur « Se connecter », saisissez votre identifiant et votre mot de passe.",
                "  - Une fois connecté, vous accédez aux serveurs et fichiers de l'entreprise.",
                "  - Déconnectez-vous quand vous avez fini.", "",
                f"Adresse du pare-feu : {adresse}",
                "En cas de problème, contactez votre service informatique.",
            ]) + "\n", encoding="utf-8")
        crees.append(f"{dossier}/  ({len(p.teletravailleurs)} fiche(s) à remettre aux télétravailleurs)")
    return crees


def _ecrire_secrets(p: Projet) -> None:
    for onglet, lignes in p.lignes.items():
        for l in lignes:
            for k, v in list(l.items()):
                if v == DEMANDER:
                    lib = next((lb for lb in p.secrets if _correspond(onglet, l, k, lb)), None)
                    if lib:
                        l[k] = p.secrets[lib]
    for k, v in list(p.general.items()):
        if v == DEMANDER:
            lib = {"Mot de passe SMTP": "Mot de passe SMTP", "Mot de passe FTP": "Mot de passe FTP",
                   "Mot de passe de chiffrement de la sauvegarde": "Mot de passe de chiffrement des sauvegardes",
                   "AD : mot de passe": "Mot de passe du compte de service AD",
                   "Central : mot de passe": "Mot de passe du compte Sophos Central"}.get(k)
            if lib in p.secrets:
                p.general[k] = p.secrets[lib]


def _correspond(onglet, ligne, colonne, libelle) -> bool:
    if onglet == "Interfaces":
        return libelle == f"Mot de passe PPPoE ({ligne.get('Port')})"
    if onglet == "Wi-Fi":
        return libelle == f"Clé Wi-Fi ({ligne.get('SSID')})"
    if onglet == "Comptes":
        return libelle == f"Mot de passe du compte {ligne.get('Identifiant')}"
    if onglet == "VPN sites":
        return libelle == f"Clé partagée du VPN {ligne.get('Nom')}"
    return False


ETAPES = [
    ("Le client", lambda p: setattr(p, "situation", etape_intro(p))),
    ("Accès Internet", lambda p: etape_internet(p, p.situation)),
    ("Réseau local", lambda p: etape_lan(p, p.situation)),
    ("Serveurs", lambda p: etape_serveurs(p, p.situation)),
    ("DHCP", lambda p: etape_dhcp(p, p.situation)),
    ("VLAN", lambda p: etape_vlan(p, p.situation, bool(p.lignes.get("DHCP")))),
    ("Wi-Fi", etape_wifi),
    ("Protections", etape_securite),
    ("Accès depuis Internet", etape_redirections),
    ("VPN entre sites", lambda p: etape_vpn_sites(p, p.situation)),
    ("Télétravail", lambda p: etape_teletravail(p, p.situation)),
    ("Administration", etape_administration),
]
DOSSIER_BROUILLONS = Path("clients") / "brouillons"


def _vers_json(p: Projet) -> dict:
    d = {k: getattr(p, k) for k in p.__dataclass_fields__ if k not in ("secrets", "generes")}
    d["lan_iface"] = str(p.lan_iface) if p.lan_iface else None
    return d


def _depuis_json(d: dict) -> Projet:
    p = Projet()
    for k, v in d.items():
        if k in p.__dataclass_fields__:
            setattr(p, k, v)
    p.lan_iface = ipaddress.IPv4Interface(d["lan_iface"]) if d.get("lan_iface") else None
    p.serveurs = [tuple(x) for x in p.serveurs]
    return p


def enregistrer_brouillon(p: Projet, etape: int) -> None:
    """Sauvegarde les réponses (jamais les mots de passe) pour pouvoir reprendre plus tard."""
    if not p.general.get("Nom du client"):
        return
    DOSSIER_BROUILLONS.mkdir(parents=True, exist_ok=True)
    f = DOSSIER_BROUILLONS / f"{_slug(p.general['Nom du client'])}.json"
    f.write_text(json.dumps({"etape": etape, "projet": _vers_json(p)}, ensure_ascii=False, indent=1), encoding="utf-8")


def _choisir_brouillon() -> tuple[Projet, int] | None:
    brouillons = sorted(DOSSIER_BROUILLONS.glob("*.json")) if DOSSIER_BROUILLONS.exists() else []
    if not brouillons:
        return None
    lus = []
    for f in brouillons:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            lus.append((f, d))
        except (ValueError, OSError):
            continue
    if not lus:
        return None
    options = [("nouveau", "Nouveau client")] + [
        (str(i), f"Reprendre « {d['projet']['general'].get('Nom du client')} » (à l'étape « {ETAPES[min(d['etape'], len(ETAPES) - 1)][0]} »)")
        for i, (_, d) in enumerate(lus)]
    c = choix("Des configurations sont en cours. Que voulez-vous faire ?", options, 1)
    if c == "nouveau":
        return None
    _, d = lus[int(c)]
    p = _depuis_json(d["projet"])
    conseil("Les mots de passe saisis avant l'interruption ne sont jamais enregistrés : ils vous seront demandés "
            "au moment d'appliquer la configuration.")
    return p, d["etape"]


def main() -> int:
    PARAMS.update(charger_parametres())
    try:
        repris = _choisir_brouillon()
    except Retour:
        repris = None
    except KeyboardInterrupt:
        return 1
    p, i = repris if repris else (Projet(), 0)
    instantanes: dict[int, Projet] = {}
    try:
        while i < len(ETAPES):
            instantanes[i] = copy.deepcopy(p)
            try:
                ETAPES[i][1](p)
            except Retour as r:
                if r.precedente and i > 0:
                    i -= 1
                p = copy.deepcopy(instantanes.get(i, p))
                print(f"{J}   ↺ Retour à l'étape « {ETAPES[i][0]} »{F}")
                continue
            i += 1
            enregistrer_brouillon(p, i)
        while True:
            try:
                etape_fin(p)
                break
            except Retour:
                print(f"{J}   Pour modifier une réponse, relancez l'assistant et reprenez la configuration en cours, "
                      f"ou corrigez directement le fichier Excel.{F}")
    except KeyboardInterrupt:
        etat = "Vos réponses sont enregistrées : relancez l'assistant pour reprendre." if p.general.get("Nom du client") \
            else "Rien n'a été enregistré."
        print(f"\n{J}Assistant interrompu. {etat}{F}")
        return 1
    f = DOSSIER_BROUILLONS / f"{_slug(p.general.get('Nom du client', ''))}.json"
    if f.exists():
        f.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
