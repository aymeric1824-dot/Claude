"""Reprendre ce qui existe déjà chez le client, au lieu de tout ressaisir.

- Ancien pare-feu Fortinet (FortiGate) : fichier de sauvegarde .conf (Système > Configuration > Sauvegarde).
  On reprend les objets adresses (serveurs, NAS...), les redirections de ports (VIP), les adresses réservées
  du DHCP et l'adresse du réseau local.
- Inventaire : fichier CSV ou Excel (export GLPI, liste du client...) avec au moins un nom et une adresse IP ;
  l'adresse MAC, si elle est là, sert à réserver l'adresse.

Tout est ajouté au fichier Excel d'un client existant : relisez-le, puis lancez la simulation.
"""
from __future__ import annotations

import csv
import ipaddress
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import load_workbook


@dataclass
class Reprise:
    hotes: list[tuple[str, str, str]] = field(default_factory=list)                 # (nom, ip, description)
    redirections: list[tuple[str, str, str, str]] = field(default_factory=list)     # (nom, "TCP 3389", ip, port)
    reservations: list[tuple[str, str, str]] = field(default_factory=list)          # (nom, mac, ip)
    lan: str = ""                                                                    # ex. 192.168.1.99/24
    remarques: list[str] = field(default_factory=list)

    def resume(self) -> str:
        return (f"{len(self.hotes)} équipement(s), {len(self.redirections)} redirection(s), "
                f"{len(self.reservations)} adresse(s) réservée(s)" + (f", réseau local {self.lan}" if self.lan else ""))


def nom_propre(texte: str, prefixe: str = "EQ") -> str:
    t = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9_.-]+", "-", t).strip("-").upper()[:40]
    return t or prefixe


# ----------------------------------------------------------------------------- Fortinet
def _arbre_fortinet(texte: str) -> dict:
    """config / edit / set / next / end → dictionnaires imbriqués {section: {entrée: {clé: [valeurs]}}}."""
    racine: dict = {}
    pile = [racine]
    for brute in texte.splitlines():
        ligne = brute.strip()
        if not ligne or ligne.startswith("#"):
            continue
        mots = [m.strip('"') for m in re.findall(r'"[^"]*"|\S+', ligne)]
        commande = mots[0]
        if commande == "config":
            noeud = pile[-1].setdefault(" ".join(mots[1:]), {})
            pile.append(noeud)
        elif commande == "edit":
            noeud = pile[-1].setdefault(" ".join(mots[1:]), {})
            pile.append(noeud)
        elif commande in ("next", "end"):
            if len(pile) > 1:
                pile.pop()
        elif commande == "set" and len(mots) >= 2:
            pile[-1][mots[1]] = mots[2:]
    return racine


def lire_fortinet(texte: str) -> Reprise:
    a = _arbre_fortinet(texte)
    r = Reprise()
    for nom, obj in a.get("firewall address", {}).items():
        sub = obj.get("subnet") or []
        if len(sub) >= 2:
            try:
                iface = ipaddress.IPv4Interface(f"{sub[0]}/{sub[1]}")
            except ValueError:
                continue
            if iface.network.prefixlen == 32 and not iface.ip.is_unspecified:
                r.hotes.append((nom_propre(nom), str(iface.ip), " ".join(obj.get("comment", [])) or "Repris du FortiGate"))
    for nom, obj in a.get("firewall vip", {}).items():
        ip = (obj.get("mappedip") or [""])[0].split("-")[0]
        if not ip:
            continue
        proto = (obj.get("protocol") or ["tcp"])[0].upper()
        ext = (obj.get("extport") or [""])[0]
        interne = (obj.get("mappedport") or [ext])[0]
        if (obj.get("portforward") or ["disable"])[0] != "enable" or not ext:
            r.remarques.append(f"VIP « {nom} » : NAT complet vers {ip} (pas de port) — à reprendre à la main.")
            continue
        r.redirections.append((nom_propre(nom, "REDIR"), f"{'UDP' if proto == 'UDP' else 'TCP'} {ext}", ip, interne))
        if not any(h[1] == ip for h in r.hotes):
            r.hotes.append((nom_propre(f"SRV-{ip.replace('.', '-')}"), ip, f"Cible de la redirection {nom}"))
    for _id, serveur in a.get("system dhcp server", {}).items():
        for _n, res in serveur.get("reserved-address", {}).items():
            ip, mac = (res.get("ip") or [""])[0], (res.get("mac") or [""])[0]
            if ip and mac:
                r.reservations.append((nom_propre(" ".join(res.get("description", [])) or f"APPAREIL-{ip.split('.')[-1]}"),
                                       mac.upper().replace("-", ":"), ip))
    for nom, iface in a.get("system interface", {}).items():
        ip = iface.get("ip") or []
        if len(ip) >= 2 and re.search(r"internal|lan|port1$", nom, re.I) and not r.lan:
            try:
                r.lan = str(ipaddress.IPv4Interface(f"{ip[0]}/{ip[1]}"))
            except ValueError:
                pass
    return r


# ----------------------------------------------------------------------------- inventaire
COLONNES = {
    "nom": ("nom", "name", "hostname", "nom de l'appareil", "appareil", "equipement", "machine", "poste"),
    "ip": ("ip", "adresse ip", "ip address", "adresse", "address", "ipv4"),
    "mac": ("mac", "adresse mac", "mac address", "macaddress"),
    "type": ("type", "categorie", "category", "role"),
}


def _simplifier(t: str) -> str:
    return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().strip().lower()


def _lignes_inventaire(fichier: Path) -> list[list[str]]:
    if fichier.suffix.lower() in (".xlsx", ".xlsm"):
        ws = load_workbook(fichier, data_only=True).active
        return [["" if v is None else str(v) for v in row] for row in ws.iter_rows(values_only=True)]
    brut = fichier.read_bytes().decode("utf-8-sig", errors="replace")
    separateur = ";" if brut.count(";") > brut.count(",") else ","
    return list(csv.reader(brut.splitlines(), delimiter=separateur))


def lire_inventaire(fichier: str | Path) -> Reprise:
    lignes = [l for l in _lignes_inventaire(Path(fichier)) if any(str(x).strip() for x in l)]
    r = Reprise()
    if not lignes:
        return r
    entetes = [_simplifier(x) for x in lignes[0]]
    pos = {cle: next((i for i, e in enumerate(entetes) if e in noms), None) for cle, noms in COLONNES.items()}
    if pos["ip"] is None:
        raise ValueError("Colonne « IP » introuvable : la première ligne doit contenir les titres (Nom, IP, MAC...).")
    for l in lignes[1:]:
        def val(cle):
            i = pos[cle]
            return str(l[i]).strip() if i is not None and i < len(l) else ""
        try:
            ip = str(ipaddress.IPv4Address(val("ip")))
        except ValueError:
            continue
        nom = nom_propre(val("nom") or f"APPAREIL-{ip.split('.')[-1]}")
        mac = val("mac").upper().replace("-", ":")
        r.hotes.append((nom, ip, val("type") or "Repris de l'inventaire"))
        if re.fullmatch(r"([0-9A-F]{2}:){5}[0-9A-F]{2}", mac):
            r.reservations.append((nom, mac, ip))
    return r


# ----------------------------------------------------------------------------- ajout au fichier client
def _ajouter_ligne(ws, valeurs: dict) -> None:
    entetes = [str(c.value or "") for c in ws[1]]
    ws.append([valeurs.get(e, "") for e in entetes])


def ajouter_au_classeur(fichier: str | Path, r: Reprise) -> list[str]:
    """Ajoute la reprise au fichier client (sans doublon). Renvoie ce qui a été ajouté."""
    wb = load_workbook(fichier)
    fait = []
    if "Hôtes" in wb.sheetnames:
        ws = wb["Hôtes"]
        noms = {str(row[1]).upper() for row in ws.iter_rows(min_row=2, values_only=True) if row and row[1]}
        ips = {str(row[3]) for row in ws.iter_rows(min_row=2, values_only=True) if row and len(row) > 3 and row[3]}
        for nom, ip, desc in r.hotes:
            if ip in ips:
                continue
            base, n = nom, 2
            while nom.upper() in noms:
                nom, n = f"{base}-{n}", n + 1
            _ajouter_ligne(ws, {"Actif": "Oui", "Nom": nom, "Type": "IP", "Adresse": ip, "Description": desc})
            noms.add(nom.upper())
            ips.add(ip)
            fait.append(f"Équipement {nom} ({ip})")
    noms_ip = {}
    if "Hôtes" in wb.sheetnames:
        for row in wb["Hôtes"].iter_rows(min_row=2, values_only=True):
            if row and len(row) > 3 and row[3]:
                noms_ip[str(row[3])] = str(row[1])
    if "Redirections" in wb.sheetnames:
        for nom, externe, ip, interne in r.redirections:
            _ajouter_ligne(wb["Redirections"], {"Actif": "Oui", "Nom": nom, "Port WAN": "Port2", "Service externe": externe,
                                                "Serveur interne": noms_ip.get(ip, ip), "Port interne": interne,
                                                "Zone du serveur": "LAN"})
            fait.append(f"Redirection {nom} : {externe} → {ip}:{interne}")
    if "Réservations DHCP" in wb.sheetnames:
        ws = wb["Réservations DHCP"]
        macs = {str(row[3]).upper() for row in ws.iter_rows(min_row=2, values_only=True) if row and len(row) > 3 and row[3]}
        for nom, mac, ip in r.reservations:
            if mac in macs:
                continue
            _ajouter_ligne(ws, {"Actif": "Oui", "Serveur DHCP": "DHCP-LAN", "Nom de l'appareil": nom, "Adresse MAC": mac,
                                "Adresse IP": ip})
            macs.add(mac)
            fait.append(f"Adresse réservée {ip} pour {nom}")
    wb.save(fichier)
    return fait
