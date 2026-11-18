"""Description du fichier Excel client et conversion de ses lignes en objets Sophos.

Chaque onglet du classeur correspond à un type d'objet. La première ligne
contient les en-têtes, les lignes suivantes les données. La colonne « Actif »
permet de désactiver une ligne pour un client sans la supprimer (Oui/Non).
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field

from openpyxl import load_workbook

# ----------------------------------------------------------------------------- spécification
# Pour chaque onglet : liste de (en-tête, aide, valeurs autorisées ou None)
OUI_NON = ["Oui", "Non"]

ONGLETS: dict[str, list[tuple[str, str, list[str] | None]]] = {
    "Zones": [
        ("Actif", "Oui pour appliquer la ligne, Non pour l'ignorer", OUI_NON),
        ("Nom", "Nom de la zone (ex. SERVEURS). Les zones LAN/WAN/DMZ existent déjà.", None),
        ("Type", "LAN ou DMZ", ["LAN", "DMZ"]),
        ("Description", "Texte libre", None),
        ("Ping", "Autoriser le ping vers le pare-feu depuis cette zone", OUI_NON),
        ("Admin HTTPS", "Autoriser l'interface d'admin web depuis cette zone", OUI_NON),
        ("SSH", "Autoriser SSH vers le pare-feu depuis cette zone", OUI_NON),
        ("DNS", "Le pare-feu sert de DNS pour cette zone", OUI_NON),
    ],
    "VLAN": [
        ("Actif", "Oui / Non", OUI_NON),
        ("Interface physique", "Port sur lequel créer le VLAN (ex. Port1)", None),
        ("ID VLAN", "Numéro de VLAN (1-4094)", None),
        ("Zone", "Zone du VLAN (LAN, DMZ ou une zone créée dans l'onglet Zones)", None),
        ("Adresse IP", "IP du pare-feu dans ce VLAN (ex. 192.168.10.254)", None),
        ("Masque", "Masque (ex. 255.255.255.0 ou /24)", None),
    ],
    "Hôtes": [
        ("Actif", "Oui / Non", OUI_NON),
        ("Nom", "Nom de l'objet (ex. SRV-AD-01)", None),
        ("Type", "IP = une machine, Réseau = un sous-réseau, Plage = plage d'IP, FQDN = nom DNS",
         ["IP", "Réseau", "Plage", "FQDN"]),
        ("Adresse", "IP, adresse réseau, IP de début, ou nom DNS selon le type", None),
        ("Masque / IP de fin", "Masque pour un Réseau, IP de fin pour une Plage, vide sinon", None),
        ("Description", "Texte libre", None),
    ],
    "Groupes": [
        ("Actif", "Oui / Non", OUI_NON),
        ("Nom", "Nom du groupe d'hôtes", None),
        ("Membres", "Noms des hôtes (type IP/Réseau/Plage) séparés par ;", None),
        ("Description", "Texte libre", None),
    ],
    "Services": [
        ("Actif", "Oui / Non", OUI_NON),
        ("Nom", "Nom du service (ex. APP-METIER)", None),
        ("Protocole", "TCP, UDP ou TCP+UDP", ["TCP", "UDP", "TCP+UDP"]),
        ("Ports", "Port(s) de destination : 443, ou 8000:8010, plusieurs séparés par ;", None),
        ("Description", "Texte libre (non envoyé, pour mémoire)", None),
    ],
    "Règles": [
        ("Actif", "Oui / Non", OUI_NON),
        ("Nom", "Nom de la règle. Les règles sont créées dans l'ordre du tableau.", None),
        ("Action", "Accepter, Bloquer (drop silencieux) ou Rejeter", ["Accepter", "Bloquer", "Rejeter"]),
        ("Zones source", "Ex. LAN ; plusieurs séparées par ; ; vide = toutes", None),
        ("Réseaux source", "Noms d'hôtes/groupes ; vide = tous", None),
        ("Zones destination", "Ex. WAN ; vide = toutes", None),
        ("Réseaux destination", "Noms d'hôtes/groupes ; vide = tous", None),
        ("Services", "Noms de services (ex. HTTPS;DNS) ; vide = tous", None),
        ("Journaliser", "Enregistrer le trafic dans les journaux", OUI_NON),
        ("Description", "Texte libre", None),
    ],
}

GENERAL: list[tuple[str, str, str]] = [
    # (paramètre, valeur par défaut, aide)
    ("Nom du client", "", "Sert au nom du rapport"),
    ("Nom d'hôte du pare-feu", "", "Ex. fw-client-siege (vide = ne pas modifier)"),
    ("Adresse IP du pare-feu", "172.16.16.16", "IP utilisée pour joindre le boîtier (par défaut 172.16.16.16 sur Port1)"),
    ("Port d'administration", "4444", "4444 par défaut"),
    ("Utilisateur admin", "admin", "Le mot de passe est demandé au lancement, il n'est jamais stocké"),
]

ORDRE_DEPLOIEMENT = ["Général", "Zones", "VLAN", "Hôtes", "Groupes", "Services", "Règles"]


# ----------------------------------------------------------------------------- objets
@dataclass
class Objet:
    onglet: str
    ligne: int
    nom: str
    balise: str            # balise XML Sophos (IPHost, FirewallRule...)
    contenu: dict          # contenu XML sous forme de dictionnaire (ordre conservé)


@dataclass
class Configuration:
    general: dict[str, str] = field(default_factory=dict)
    objets: list[Objet] = field(default_factory=list)
    erreurs: list[str] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)


class ErreurLigne(ValueError):
    pass


# ----------------------------------------------------------------------------- utilitaires
def _txt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _oui(v, defaut: bool = False) -> bool:
    t = _txt(v).lower()
    if not t:
        return defaut
    if t in ("oui", "o", "yes", "y", "1", "vrai", "true", "x", "enable"):
        return True
    if t in ("non", "n", "no", "0", "faux", "false", "disable"):
        return False
    raise ErreurLigne(f"valeur « {v} » non comprise (attendu Oui ou Non)")


def _ed(b: bool) -> str:
    return "Enable" if b else "Disable"


def _liste(v) -> list[str]:
    t = _txt(v).replace(",", ";").replace("\n", ";")
    return [x.strip() for x in t.split(";") if x.strip()]


def _ip(v, quoi="adresse IP") -> str:
    t = _txt(v)
    try:
        return str(ipaddress.IPv4Address(t))
    except ValueError:
        raise ErreurLigne(f"{quoi} invalide : « {t} »") from None


def _masque(v) -> str:
    t = _txt(v).lstrip("/")
    try:
        if t.isdigit():
            return str(ipaddress.IPv4Network(f"0.0.0.0/{t}").netmask)
        ipaddress.IPv4Network(f"0.0.0.0/{t}")  # vérifie que le masque est valide
        return t
    except ValueError:
        raise ErreurLigne(f"masque invalide : « {t} »") from None


def _choix(v, valeurs: dict[str, str], quoi: str) -> str:
    t = _txt(v).lower()
    for cle, val in valeurs.items():
        if t == cle.lower():
            return val
    raise ErreurLigne(f"{quoi} « {v} » inconnu (valeurs possibles : {', '.join(valeurs)})")


def _ports(v) -> list[str]:
    ports = []
    for p in _liste(v):
        p = p.replace("-", ":")
        morceaux = p.split(":")
        if not all(m.isdigit() and 1 <= int(m) <= 65535 for m in morceaux) or len(morceaux) > 2:
            raise ErreurLigne(f"port invalide : « {p} »")
        ports.append(p)
    if not ports:
        raise ErreurLigne("aucun port indiqué")
    return ports


# ----------------------------------------------------------------------------- constructeurs XML
def construire_zone(c: dict) -> tuple[str, dict]:
    nom = _txt(c["Nom"])
    contenu = {
        "Name": nom,
        "Type": _choix(c["Type"] or "LAN", {"LAN": "LAN", "DMZ": "DMZ"}, "type de zone"),
        "Description": _txt(c["Description"]),
        "ApplianceAccess": {
            "AdminServices": {"HTTPS": _ed(_oui(c["Admin HTTPS"])), "SSH": _ed(_oui(c["SSH"]))},
            "NetworkServices": {"DNS": _ed(_oui(c["DNS"])), "Ping": _ed(_oui(c["Ping"]))},
        },
    }
    return nom, contenu


def construire_vlan(c: dict) -> tuple[str, dict]:
    interface = _txt(c["Interface physique"])
    if not interface:
        raise ErreurLigne("interface physique manquante")
    vid = _txt(c["ID VLAN"])
    if not vid.isdigit() or not 1 <= int(vid) <= 4094:
        raise ErreurLigne(f"ID VLAN invalide : « {vid} »")
    nom = f"{interface}.{vid}"
    contenu = {
        "Zone": _txt(c["Zone"]) or "LAN",
        "Interface": interface,
        "Hardware": nom,
        "Name": nom,
        "VLANID": vid,
        "IPv4Configuration": "Enable",
        "IPv6Configuration": "Disable",
        "IPv4Assignment": "Static",
        "IPAddress": _ip(c["Adresse IP"]),
        "Netmask": _masque(c["Masque"]),
    }
    return nom, contenu


def construire_hote(c: dict) -> tuple[str, str, dict]:
    nom = _txt(c["Nom"])
    type_ = _choix(c["Type"], {"IP": "IP", "Réseau": "Network", "Reseau": "Network", "Network": "Network",
                               "Plage": "IPRange", "IPRange": "IPRange", "FQDN": "FQDN"}, "type d'hôte")
    adresse = c["Adresse"]
    extra = c["Masque / IP de fin"]
    desc = _txt(c["Description"])
    if type_ == "FQDN":
        fqdn = _txt(adresse)
        if not fqdn or " " in fqdn:
            raise ErreurLigne(f"FQDN invalide : « {fqdn} »")
        return nom, "FQDNHost", {"Name": nom, "Description": desc, "FQDN": fqdn}
    contenu = {"Name": nom, "IPFamily": "IPv4", "HostType": type_}
    if type_ == "IP":
        contenu["IPAddress"] = _ip(adresse)
    elif type_ == "Network":
        ip, masque = _ip(adresse, "adresse réseau"), _masque(extra)
        reseau = ipaddress.IPv4Network(f"{ip}/{masque}", strict=False)
        if str(reseau.network_address) != ip:
            raise ErreurLigne(f"{ip}/{masque} n'est pas une adresse de réseau (vouliez-vous {reseau.network_address} ?)")
        contenu["IPAddress"], contenu["Subnet"] = ip, masque
    else:
        debut, fin = _ip(adresse, "IP de début"), _ip(extra, "IP de fin")
        if ipaddress.IPv4Address(debut) > ipaddress.IPv4Address(fin):
            raise ErreurLigne("l'IP de début est après l'IP de fin")
        contenu["StartIPAddress"], contenu["EndIPAddress"] = debut, fin
    if desc:
        contenu["Description"] = desc
    return nom, "IPHost", contenu


def construire_groupe(c: dict) -> tuple[str, dict]:
    nom = _txt(c["Nom"])
    membres = _liste(c["Membres"])
    if not membres:
        raise ErreurLigne("le groupe n'a aucun membre")
    return nom, {"Name": nom, "IPFamily": "IPv4", "Description": _txt(c["Description"]),
                 "HostList": {"Host": membres}}


def construire_service(c: dict) -> tuple[str, dict]:
    nom = _txt(c["Nom"])
    proto = _choix(c["Protocole"], {"TCP": "TCP", "UDP": "UDP", "TCP+UDP": "TCP+UDP",
                                    "TCP/UDP": "TCP+UDP"}, "protocole")
    protos = ["TCP", "UDP"] if proto == "TCP+UDP" else [proto]
    details = [{"SourcePort": "1:65535", "DestinationPort": p, "Protocol": pr}
               for pr in protos for p in _ports(c["Ports"])]
    return nom, {"Name": nom, "Type": "TCPorUDP", "ServiceDetails": {"ServiceDetail": details}}


def construire_regle(c: dict) -> tuple[str, dict]:
    nom = _txt(c["Nom"])
    action = _choix(c["Action"], {"Accepter": "Accept", "Accept": "Accept", "Autoriser": "Accept",
                                  "Bloquer": "Drop", "Drop": "Drop",
                                  "Rejeter": "Reject", "Reject": "Reject"}, "action")
    politique: dict = {
        "Action": action,
        "LogTraffic": _ed(_oui(c["Journaliser"], defaut=True)),
        "SkipLocalDestined": "Disable",
    }
    if z := _liste(c["Zones source"]):
        politique["SourceZones"] = {"Zone": z}
    if z := _liste(c["Zones destination"]):
        politique["DestinationZones"] = {"Zone": z}
    politique["Schedule"] = "All The Time"
    if r := _liste(c["Réseaux source"]):
        politique["SourceNetworks"] = {"Network": r}
    if r := _liste(c["Réseaux destination"]):
        politique["DestinationNetworks"] = {"Network": r}
    if s := _liste(c["Services"]):
        politique["Services"] = {"Service": s}
    contenu = {
        "Name": nom,
        "Description": _txt(c["Description"]),
        "IPFamily": "IPv4",
        "Status": "Enable",
        "Position": "Bottom",
        "PolicyType": "Network",
        "NetworkPolicy": politique,
    }
    return nom, contenu


# ----------------------------------------------------------------------------- lecture du classeur
def lire_classeur(chemin: str) -> Configuration:
    cfg = Configuration()
    wb = load_workbook(chemin, data_only=True)

    # Onglet Général (paramètre en colonne A, valeur en colonne B)
    if "Général" in wb.sheetnames:
        for row in wb["Général"].iter_rows(min_row=2, values_only=True):
            if row and _txt(row[0]):
                cfg.general[_txt(row[0])] = _txt(row[1] if len(row) > 1 else "")
    for param, defaut, _ in GENERAL:
        cfg.general.setdefault(param, defaut)
        if not cfg.general[param]:
            cfg.general[param] = defaut

    hostname = cfg.general.get("Nom d'hôte du pare-feu", "")
    if hostname:
        cfg.objets.append(Objet("Général", 3, hostname, "AdminSettings",
                                {"HostnameSettings": {"HostName": hostname, "HostNameDesc": cfg.general.get("Nom du client", "")}}))

    noms_vus: dict[str, set[str]] = {}
    for onglet, colonnes in ONGLETS.items():
        if onglet not in wb.sheetnames:
            continue
        ws = wb[onglet]
        entetes = [_txt(c.value) for c in ws[1]]
        manquantes = [col for col, _, _ in colonnes if col not in entetes]
        if manquantes:
            cfg.erreurs.append(f"[{onglet}] colonnes manquantes : {', '.join(manquantes)}")
            continue
        for num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            ligne = {entetes[i]: row[i] for i in range(min(len(entetes), len(row))) if entetes[i]}
            for col, _, _ in colonnes:
                ligne.setdefault(col, None)
            if not any(_txt(v) for v in ligne.values()):
                continue
            ref = f"[{onglet} ligne {num}]"
            try:
                if not _oui(ligne["Actif"], defaut=True):
                    continue
                if onglet != "VLAN" and not _txt(ligne.get("Nom")):
                    raise ErreurLigne("nom manquant")
                if onglet == "Zones":
                    nom, contenu = construire_zone(ligne); balise = "Zone"
                elif onglet == "VLAN":
                    nom, contenu = construire_vlan(ligne); balise = "VLAN"
                elif onglet == "Hôtes":
                    nom, balise, contenu = construire_hote(ligne)
                elif onglet == "Groupes":
                    nom, contenu = construire_groupe(ligne); balise = "IPHostGroup"
                elif onglet == "Services":
                    nom, contenu = construire_service(ligne); balise = "Services"
                else:
                    nom, contenu = construire_regle(ligne); balise = "FirewallRule"
            except ErreurLigne as exc:
                cfg.erreurs.append(f"{ref} {exc}")
                continue
            vus = noms_vus.setdefault(balise, set())
            if nom in vus:
                cfg.erreurs.append(f"{ref} le nom « {nom} » est utilisé deux fois")
                continue
            vus.add(nom)
            cfg.objets.append(Objet(onglet, num, nom, balise, contenu))

    _verifier_references(cfg)
    return cfg


def _verifier_references(cfg: Configuration) -> None:
    """Signale les noms utilisés dans les règles/groupes qui ne sont pas définis dans le fichier.

    Ce ne sont que des avertissements : l'objet peut exister d'origine sur le
    pare-feu (ex. services HTTPS, DNS, zones LAN/WAN).
    """
    definis = {o.nom for o in cfg.objets}
    zones_origine = {"LAN", "WAN", "DMZ", "VPN", "WiFi"}
    for o in cfg.objets:
        if o.balise == "IPHostGroup":
            refs = [("hôte", m) for m in o.contenu["HostList"]["Host"]]
        elif o.balise == "FirewallRule":
            p = o.contenu["NetworkPolicy"]
            refs = [("zone", z) for k in ("SourceZones", "DestinationZones") for z in p.get(k, {}).get("Zone", [])]
            refs += [("réseau", n) for k in ("SourceNetworks", "DestinationNetworks") for n in p.get(k, {}).get("Network", [])]
            refs += [("service", s) for s in p.get("Services", {}).get("Service", [])]
        else:
            continue
        for quoi, nom in refs:
            if nom not in definis and not (quoi == "zone" and nom in zones_origine):
                cfg.avertissements.append(
                    f"[{o.onglet} ligne {o.ligne}] {quoi} « {nom} » absent du fichier : il doit déjà exister sur le pare-feu")
