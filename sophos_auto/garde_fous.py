"""Garde-fous : réglages dangereux repérés dans le fichier client AVANT l'envoi au pare-feu.

Chaque constat explique le risque avec des mots simples et ce qu'il faut faire à la place.
« danger » = à corriger (l'envoi demande une confirmation) ; « attention » = à vérifier.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

DANGER, ATTENTION = "danger", "attention"

# Services qu'on ne doit jamais ouvrir à tout Internet : (motif, nom lisible, conseil)
SERVICES_RISQUES = [
    (r"\brdp\b|3389|bureau à distance", "le bureau à distance (RDP)",
     "C'est la première porte d'entrée des rançongiciels. Utilisez le VPN télétravail, ou limitez l'accès aux "
     "adresses IP du prestataire (colonne « Sources autorisées »)."),
    (r"\bsmb\b|\b445\b|partage", "le partage de fichiers Windows (SMB)", "Ne l'ouvrez jamais sur Internet : utilisez le VPN."),
    (r"\btelnet\b|\b23\b", "Telnet", "Protocole sans chiffrement : utilisez SSH ou le VPN."),
    (r"\bvnc\b|590[0-9]", "la prise en main VNC", "Utilisez le VPN, ou limitez aux adresses du prestataire."),
    (r"\bsql\b|1433|3306|5432", "une base de données", "Une base de données ne doit être joignable que par le VPN."),
    (r"\bftp\b|\b21\b", "le FTP", "Le FTP envoie les mots de passe en clair : préférez SFTP ou un partage via le VPN."),
]


@dataclass
class Constat:
    niveau: str
    texte: str
    conseil: str = ""


def _lignes(wb, onglet: str) -> list[dict]:
    if onglet not in wb.sheetnames:
        return []
    ws = wb[onglet]
    entetes = [str(c.value or "").strip() for c in ws[1]]
    res = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        d = {entetes[i]: ("" if v is None else str(v).strip()) for i, v in enumerate(row) if i < len(entetes)}
        if any(d.values()) and d.get("Actif", "Oui").lower() not in ("non", "no", "0", "false"):
            res.append(d)
    return res


def _mot_de_passe_faible(m: str) -> bool:
    return len(m) < 10 or not (re.search(r"[a-z]", m) and re.search(r"[A-Z]", m) and re.search(r"\d", m))


def verifier(fichier: str | Path) -> list[Constat]:
    wb = load_workbook(fichier, data_only=True)
    constats: list[Constat] = []
    for r in _lignes(wb, "Redirections"):
        texte = " ".join(r.get(k, "") for k in ("Nom", "Service externe", "Port WAN", "Port interne")).lower()
        ouvert = not r.get("Sources autorisées") or r.get("Sources autorisées", "").lower() in ("any", "tous", "toutes")
        for motif, nom, conseil in SERVICES_RISQUES:
            if re.search(motif, texte):
                if ouvert:
                    constats.append(Constat(DANGER, f"Redirection « {r.get('Nom')} » : {nom} est ouvert à tout Internet.",
                                            conseil))
                else:
                    constats.append(Constat(ATTENTION, f"Redirection « {r.get('Nom')} » : {nom} est accessible depuis "
                                                       f"Internet (limité à {r.get('Sources autorisées')}).", conseil))
                break
    for r in _lignes(wb, "Règles"):
        src, dst = r.get("Zones source", "").upper(), r.get("Zones destination", "").upper()
        accepte = r.get("Action", "").lower().startswith(("accep", "autor", "allow"))
        if accepte and "WAN" in src and re.search(r"LAN|DMZ", dst) and not r.get("Réseaux source") \
                and not r.get("Services"):
            constats.append(Constat(DANGER, f"Règle « {r.get('Nom')} » : tout Internet peut joindre tout le réseau {dst}.",
                                    "Précisez les services et les adresses autorisés, ou supprimez cette règle."))
    for r in _lignes(wb, "Comptes"):
        m = r.get("Mot de passe", "")
        if m and not m.startswith("(") and _mot_de_passe_faible(m):
            qui = "administrateur" if r.get("Profil admin") else "utilisateur"
            constats.append(Constat(DANGER if r.get("Profil admin") else ATTENTION,
                                    f"Compte {qui} « {r.get('Identifiant')} » : mot de passe trop faible.",
                                    "10 caractères minimum, avec majuscules, minuscules et chiffres. Laissez l'outil "
                                    "le générer."))
    for r in _lignes(wb, "Wi-Fi"):
        cle = r.get("Clé Wi-Fi", "")
        if cle and not cle.startswith("(") and len(cle) < 12:
            constats.append(Constat(ATTENTION, f"Wi-Fi « {r.get('SSID') or r.get('Nom')} » : clé trop courte "
                                               f"({len(cle)} caractères).", "12 caractères minimum conseillés."))
    constats += coherence(wb)
    if "Général" in wb.sheetnames:
        for row in wb["Général"].iter_rows(min_row=2, values_only=True):
            nom, val = str(row[0] or ""), str(row[1] if len(row) > 1 and row[1] is not None else "")
            if re.search(r"administration", nom, re.I) and re.search(r"wan|internet", nom, re.I) \
                    and val.lower() in ("oui", "yes"):
                constats.append(Constat(DANGER, "L'administration du pare-feu est ouverte depuis Internet.",
                                        "Administrez-le depuis Sophos Central ou par le VPN."))
    return constats


def _ip(t: str):
    import ipaddress
    try:
        return ipaddress.IPv4Address(str(t).strip())
    except ValueError:
        return None


def coherence(wb) -> list[Constat]:
    """Erreurs de saisie : doublons, adresse fixe dans la plage DHCP, VLAN en double, réseaux qui se chevauchent."""
    import ipaddress
    from collections import Counter
    constats: list[Constat] = []
    hotes = [h for h in _lignes(wb, "Hôtes") if h.get("Type", "").upper() == "IP"]
    for nom, n in Counter(h.get("Nom", "").upper() for h in _lignes(wb, "Hôtes") if h.get("Nom")).items():
        if n > 1:
            constats.append(Constat(DANGER, f"Le nom « {nom} » est utilisé {n} fois dans l'onglet Hôtes.",
                                    "Chaque équipement doit avoir un nom unique (ajoutez -2, -3...)."))
    for ip, n in Counter(h.get("Adresse", "") for h in hotes if _ip(h.get("Adresse", ""))).items():
        if n > 1:
            noms = ", ".join(h.get("Nom", "") for h in hotes if h.get("Adresse") == ip)
            constats.append(Constat(ATTENTION, f"L'adresse {ip} est donnée à plusieurs équipements ({noms}).",
                                    "Deux appareils ne peuvent pas avoir la même adresse : corrigez l'un d'eux."))
    plages = []
    for d in _lignes(wb, "DHCP"):
        debut, fin = _ip(d.get("Début de plage", "")), _ip(d.get("Fin de plage", ""))
        if debut and fin:
            if int(debut) > int(fin):
                constats.append(Constat(DANGER, f"DHCP « {d.get('Nom')} » : la plage commence après sa fin.",
                                        "Inversez « Début de plage » et « Fin de plage »."))
            plages.append((d.get("Nom", ""), debut, fin))
    reservees = {r.get("Adresse IP", "") for r in _lignes(wb, "Réservations DHCP")}
    for h in hotes:
        ip = _ip(h.get("Adresse", ""))
        for nom, debut, fin in plages:
            if ip and int(debut) <= int(ip) <= int(fin) and str(ip) not in reservees:
                constats.append(Constat(ATTENTION, f"« {h.get('Nom')} » ({ip}) a une adresse fixe dans la plage distribuée "
                                                   f"par « {nom} » ({debut} → {fin}).",
                                        "Le DHCP pourrait donner cette adresse à un autre appareil : choisissez une adresse "
                                        "hors plage, ou réservez-la (onglet Réservations DHCP)."))
    for col in ("Adresse MAC", "Adresse IP"):
        for v, n in Counter(r.get(col, "").upper() for r in _lignes(wb, "Réservations DHCP") if r.get(col)).items():
            if n > 1:
                constats.append(Constat(DANGER, f"Réservations DHCP : « {v} » apparaît {n} fois ({col}).",
                                        "Une adresse MAC et une adresse IP ne peuvent être réservées qu'une fois."))
    for (iface, vid), n in Counter((v.get("Interface physique", ""), v.get("ID VLAN", ""))
                                   for v in _lignes(wb, "VLAN") if v.get("ID VLAN")).items():
        if n > 1:
            constats.append(Constat(DANGER, f"Le VLAN {vid} est déclaré {n} fois sur {iface}.",
                                    "Chaque numéro de VLAN doit être unique sur une interface."))
    reseaux = []
    for onglet, quoi in (("Interfaces", "Port"), ("VLAN", "ID VLAN")):
        for r in _lignes(wb, onglet):
            if "WAN" in r.get("Zone", "").upper():
                continue
            try:
                reseaux.append((f"{onglet} {r.get(quoi)}",
                                ipaddress.IPv4Interface(f"{r.get('Adresse IP')}/{r.get('Masque') or 24}").network))
            except ValueError:
                continue
    for i, (a, na) in enumerate(reseaux):
        for b, nb in reseaux[i + 1:]:
            if na.overlaps(nb):
                constats.append(Constat(DANGER, f"{a} et {b} utilisent le même réseau ({na}).",
                                        "Chaque réseau (LAN, VLAN) doit avoir sa propre plage d'adresses."))
    return constats


def afficher(constats: list[Constat], ecrire=print) -> None:
    rouge, jaune, fin = "\033[31m", "\033[33m", "\033[0m"
    for c in constats:
        couleur = rouge if c.niveau == DANGER else jaune
        ecrire(f"{couleur}  {'✘ DANGER' if c.niveau == DANGER else '! À vérifier'} : {c.texte}{fin}")
        if c.conseil:
            ecrire(f"      → {c.conseil}")
