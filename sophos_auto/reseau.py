"""Ce que l'outil peut découvrir tout seul sur le réseau, pour poser moins de questions.

- la configuration du PC (adresse, passerelle, DNS, serveur DHCP, domaine Windows) ;
- la box ou le routeur actuel (Orange, Free, SFR, Bouygues, ancien pare-feu...) ;
- les appareils du réseau (serveurs, imprimantes, NAS, caméras, téléphonie) ;
- le pare-feu Sophos lui-même (port 4444), sans avoir à taper son adresse ;
- le réglage de la carte réseau du PC pour joindre un pare-feu neuf, puis le retour à l'état d'origine.

Rien n'est envoyé hors du réseau local, et aucun identifiant n'est utilisé.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

PARE_FEU_NEUF = "172.16.16.16"          # adresse d'usine d'un XGS (Port1)
PC_POUR_PARE_FEU_NEUF = "172.16.16.20"  # adresse proposée au PC pour le joindre

# Ports ouverts → type d'appareil (du plus précis au plus général)
PORTS_SONDES = [4444, 389, 88, 9100, 631, 554, 5000, 5001, 5060, 3389, 445, 22, 80, 443]
TYPES = [
    ({4444}, "FW", "Pare-feu Sophos"),
    ({389, 88}, "AD", "Contrôleur de domaine (Active Directory)"),
    ({9100}, "IMP", "Imprimante / copieur"),
    ({631}, "IMP", "Imprimante / copieur"),
    ({554}, "NVR", "Caméra ou enregistreur vidéo (NVR)"),
    ({5000}, "NAS", "NAS (Synology ou équivalent)"),
    ({5001}, "NAS", "NAS (Synology ou équivalent)"),
    ({5060}, "IPBX", "Téléphonie (IPBX)"),
    ({445, 3389}, "SRV", "Serveur ou PC Windows"),
    ({445}, "PARTAGE", "Partage de fichiers (PC, serveur ou NAS)"),
    ({22}, "EQ", "Équipement Linux ou réseau"),
    ({80}, "WEB", "Équipement avec une page d'administration"),
    ({443}, "WEB", "Équipement avec une page d'administration"),
]
# Mots trouvés sur la page d'accueil de la passerelle → qui est-ce ?
EQUIPEMENTS = [
    ("livebox", "Livebox (Orange)", "box"), ("freebox", "Freebox (Free)", "box"), ("sfr", "Box SFR", "box"),
    ("bbox", "Bbox (Bouygues Telecom)", "box"), ("sophos", "Pare-feu Sophos", "routeur"),
    ("fortigate", "Pare-feu Fortinet", "routeur"), ("fortinet", "Pare-feu Fortinet", "routeur"),
    ("stormshield", "Pare-feu Stormshield", "routeur"), ("pfsense", "Pare-feu pfSense", "routeur"),
    ("opnsense", "Pare-feu OPNsense", "routeur"), ("watchguard", "Pare-feu WatchGuard", "routeur"),
    ("draytek", "Routeur DrayTek", "routeur"), ("zyxel", "Routeur Zyxel", "routeur"),
    ("unifi", "Routeur Ubiquiti UniFi", "routeur"), ("mikrotik", "Routeur MikroTik", "routeur"),
    ("routeros", "Routeur MikroTik", "routeur"), ("netgear", "Routeur Netgear", "routeur"),
    ("tp-link", "Routeur TP-Link", "routeur"), ("cisco", "Routeur Cisco", "routeur"),
]


# Marques reconnues sur la page d'administration d'un appareil : (mot cherché, marque, type d'appareil)
MARQUES = [
    ("brother", "Brother", "IMP"), ("hewlett", "HP", "IMP"), ("hp laserjet", "HP", "IMP"), ("officejet", "HP", "IMP"),
    ("canon", "Canon", "IMP"), ("epson", "Epson", "IMP"), ("ricoh", "Ricoh", "IMP"), ("kyocera", "Kyocera", "IMP"),
    ("xerox", "Xerox", "IMP"), ("konica", "Konica Minolta", "IMP"), ("lexmark", "Lexmark", "IMP"),
    ("sharp", "Sharp", "IMP"), ("toshiba", "Toshiba", "IMP"), ("hikvision", "Hikvision", "NVR"),
    ("dahua", "Dahua", "NVR"), ("axis", "Axis", "NVR"), ("synology", "Synology", "NAS"), ("qnap", "QNAP", "NAS"),
    ("3cx", "3CX", "IPBX"), ("yealink", "Yealink", "IPBX"), ("snom", "Snom", "IPBX"), ("ubiquiti", "Ubiquiti", "EQ"),
    ("unifi", "Ubiquiti", "EQ"), ("aruba", "Aruba", "EQ"), ("cisco", "Cisco", "EQ"), ("netgear", "Netgear", "EQ"),
]


def marque_appareil(page: str) -> tuple[str, str]:
    for mot, marque, code in MARQUES:
        if mot in page:
            return marque, code
    return "", ""


@dataclass
class CartePC:
    nom: str
    index: int
    ip: str
    prefixe: int
    passerelle: str = ""
    dns: list[str] = field(default_factory=list)
    dhcp: bool = True
    serveur_dhcp: str = ""
    domaine: str = ""
    sans_fil: bool = False

    @property
    def reseau(self) -> ipaddress.IPv4Network:
        return ipaddress.IPv4Interface(f"{self.ip}/{self.prefixe}").network


@dataclass
class Appareil:
    ip: str
    ports: list[int]
    code: str
    libelle: str
    nom: str = ""
    marque: str = ""


@dataclass
class Analyse:
    carte: CartePC | None = None
    passerelle: str = ""
    equipement: str = ""          # ex. « Livebox (Orange) »
    genre_equipement: str = ""    # box | routeur | ""
    appareils: list[Appareil] = field(default_factory=list)
    pare_feux: list[str] = field(default_factory=list)

    def resume(self) -> list[str]:
        lignes = []
        if self.carte:
            c = self.carte
            lignes.append(f"Votre PC : {c.ip}/{c.prefixe} sur « {c.nom} »" + (" (Wi-Fi)" if c.sans_fil else ""))
            if c.passerelle:
                lignes.append(f"Passerelle actuelle : {c.passerelle}" + (f" — {self.equipement}" if self.equipement else ""))
            if c.serveur_dhcp:
                lignes.append(f"Adresses distribuées par : {c.serveur_dhcp}")
            if c.domaine:
                lignes.append(f"Domaine Windows : {c.domaine}")
        for a in self.appareils:
            lignes.append(f"  {a.ip:<15} {a.libelle}" + (f" ({a.nom})" if a.nom else ""))
        return lignes


# ----------------------------------------------------------------------------- PC
_SCRIPT_PC = r"""
$up = @{}; Get-NetAdapter -Physical -ErrorAction SilentlyContinue | Where-Object Status -eq 'Up' | ForEach-Object { $up[[int]$_.InterfaceIndex] = $_ }
Get-CimInstance Win32_NetworkAdapterConfiguration -Filter 'IPEnabled=True' | ForEach-Object {
  $a = $up[[int]$_.InterfaceIndex]
  [pscustomobject]@{ Nom = $(if ($a) { $a.Name } else { $_.Description }); Index = [int]$_.InterfaceIndex; Actif = [bool]$a
    Description = $_.Description; IP = @($_.IPAddress); Masque = @($_.IPSubnet); Passerelle = @($_.DefaultIPGateway)
    DNS = @($_.DNSServerSearchOrder); DHCP = [bool]$_.DHCPEnabled; ServeurDHCP = $_.DHCPServer; Domaine = $_.DNSDomain }
} | ConvertTo-Json -Depth 3
"""


def _powershell(script: str, delai: int = 20) -> str:
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True,
                           text=True, timeout=delai, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def cartes_pc() -> list[CartePC]:
    """Cartes réseau actives du PC (Windows), la carte filaire en premier."""
    if os.name != "nt":
        return []
    try:
        donnees = json.loads(_powershell(_SCRIPT_PC) or "[]")
    except ValueError:
        return []
    if isinstance(donnees, dict):
        donnees = [donnees]
    cartes = []
    for d in donnees:
        ips = [x for x in (d.get("IP") or []) if x and ":" not in x and not x.startswith("169.254.")]
        if not ips:
            continue
        masques = [m for m in (d.get("Masque") or []) if m and "." in m]
        try:
            prefixe = ipaddress.IPv4Network(f"0.0.0.0/{masques[0]}").prefixlen if masques else 24
        except ValueError:
            prefixe = 24
        passerelles = [g for g in (d.get("Passerelle") or []) if g and ":" not in g]
        texte = f"{d.get('Nom', '')} {d.get('Description', '')}".lower()
        cartes.append(CartePC(
            nom=str(d.get("Nom") or ""), index=int(d.get("Index") or 0), ip=ips[0], prefixe=prefixe,
            passerelle=passerelles[0] if passerelles else "",
            dns=[x for x in (d.get("DNS") or []) if x and ":" not in x], dhcp=bool(d.get("DHCP")),
            serveur_dhcp=str(d.get("ServeurDHCP") or "") if d.get("DHCP") else "", domaine=str(d.get("Domaine") or ""),
            sans_fil=bool(re.search(r"wi-?fi|wireless|wlan|sans fil", texte)) and not re.search(r"ethernet", texte)))
    # la carte filaire branchée en premier, puis celle qui a une passerelle
    cartes.sort(key=lambda c: (c.sans_fil, not c.passerelle))
    return cartes


def carte_principale() -> CartePC | None:
    cartes = cartes_pc()
    return cartes[0] if cartes else None


# ----------------------------------------------------------------------------- sondes
def port_ouvert(ip: str, port: int, delai: float = 0.4) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=delai):
            return True
    except (OSError, ValueError):
        return False


def type_appareil(ports: set[int]) -> tuple[str, str]:
    for besoin, code, libelle in TYPES:
        if besoin <= ports:
            return code, libelle
    return "EQ", "Appareil"


def page_accueil(ip: str, delai: float = 2.0) -> str:
    """Texte de la page d'accueil d'un équipement (http puis https), en minuscules ; vide si rien."""
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    for url in (f"http://{ip}/", f"https://{ip}/", f"https://{ip}:4444/"):
        try:
            r = requests.get(url, timeout=delai, verify=False, allow_redirects=True)
            return (r.text[:20000] + " " + " ".join(f"{k} {v}" for k, v in r.headers.items())).lower()
        except Exception:  # équipement muet, certificat étrange... : on essaie l'adresse suivante
            continue
    return ""


def identifier_equipement(ip: str) -> tuple[str, str]:
    """(nom lisible, « box » ou « routeur ») d'après la page d'accueil de la passerelle."""
    page = page_accueil(ip)
    for mot, nom, genre in EQUIPEMENTS:
        if mot in page:
            return nom, genre
    return "", ""


def balayer(reseau: ipaddress.IPv4Network, ports: list[int] | None = None, limite: int = 254,
            progression=None) -> list[Appareil]:
    """Cherche les appareils du réseau (connexion simple sur quelques ports connus, en parallèle)."""
    ports = ports or PORTS_SONDES
    hotes = [str(h) for h in list(reseau.hosts())[:limite]]
    if not hotes:
        return []

    def sonder(ip):
        ouverts = [p for p in ports if port_ouvert(ip, p)]
        return ip, ouverts
    trouves = []
    with ThreadPoolExecutor(max_workers=96) as pool:
        for n, (ip, ouverts) in enumerate(pool.map(sonder, hotes), 1):
            if progression and n % 32 == 0:
                progression(n, len(hotes))
            if ouverts:
                code, libelle = type_appareil(set(ouverts))
                trouves.append(Appareil(ip, ouverts, code, libelle))

    def nommer(a: Appareil):
        try:
            a.nom = socket.gethostbyaddr(a.ip)[0].split(".")[0]
        except OSError:
            pass
    with ThreadPoolExecutor(max_workers=32) as pool:
        list(pool.map(nommer, trouves))
    return trouves


def reconnaitre_marques(appareils: list[Appareil]) -> None:
    """Marque de chaque appareil qui a une page d'administration (imprimante Brother, caméra Hikvision...)."""
    a_voir = [a for a in appareils if {80, 443} & set(a.ports) and a.code not in ("FW", "AD")]

    def voir(a: Appareil):
        marque, code = marque_appareil(page_accueil(a.ip, 1.5))
        if marque:
            a.marque = marque
            if code != "EQ" and a.code in ("WEB", "EQ", "PARTAGE", "SRV"):
                a.code = code
                a.libelle = dict((c, l) for _p, c, l in TYPES).get(code, a.libelle)
            a.libelle = f"{a.libelle} — {marque}"
    with ThreadPoolExecutor(max_workers=24) as pool:
        list(pool.map(voir, a_voir))


def trouver_pare_feu(progression=None) -> list[str]:
    """Adresses des pare-feux Sophos joignables (adresse d'usine d'abord, puis réseaux du PC)."""
    trouves = []
    if port_ouvert(PARE_FEU_NEUF, 4444, 1.0):
        trouves.append(PARE_FEU_NEUF)
    for carte in cartes_pc():
        reseau = carte.reseau
        if reseau.prefixlen < 22:           # trop grand : on se limite au /24 du PC
            reseau = ipaddress.IPv4Interface(f"{carte.ip}/24").network
        for a in balayer(reseau, [4444], progression=progression):
            if a.ip not in trouves and a.ip != carte.ip:
                trouves.append(a.ip)
    return trouves


def analyser(afficher=print, balayage: bool = True) -> Analyse:
    """Analyse complète du réseau où le PC est branché."""
    an = Analyse(carte=carte_principale())
    if not an.carte:
        afficher("Aucune carte réseau active : branchez le PC sur le réseau du client.")
        return an
    c = an.carte
    afficher(f"Votre PC : {c.ip}/{c.prefixe}, passerelle {c.passerelle or 'aucune'}")
    if c.passerelle:
        an.passerelle = c.passerelle
        an.equipement, an.genre_equipement = identifier_equipement(c.passerelle)
        if an.equipement:
            afficher(f"Équipement actuel vers Internet : {an.equipement}")
    if balayage:
        reseau = c.reseau if c.reseau.prefixlen >= 22 else ipaddress.IPv4Interface(f"{c.ip}/24").network
        afficher(f"Recherche des appareils sur {reseau} (environ 15 secondes)...")
        an.appareils = [a for a in balayer(reseau) if a.ip != c.ip]
        reconnaitre_marques(an.appareils)
        an.pare_feux = [a.ip for a in an.appareils if a.code == "FW"]
        afficher(f"{len(an.appareils)} appareil(s) trouvé(s).")
    return an


# ----------------------------------------------------------------------------- réglage du PC
SAUVEGARDE_PC = "reseau_pc_avant.json"


def _executer_admin(commandes: list[str]) -> bool:
    """Lance les commandes netsh avec les droits administrateur (Windows demande la permission)."""
    if os.name != "nt":
        return False
    import ctypes
    script = " & ".join(commandes)
    r = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", f'/c {script}', None, 0)
    return r > 32


def regler_pc_pour(carte: CartePC, ip_pc: str = PC_POUR_PARE_FEU_NEUF, masque: str = "255.255.255.0",
                   dossier: Path | None = None) -> bool:
    """Donne au PC une adresse fixe dans le réseau du pare-feu, après avoir noté le réglage actuel."""
    f = (dossier or Path(".")) / SAUVEGARDE_PC
    if not f.exists():          # on garde le réglage d'ORIGINE, même après plusieurs essais
        f.write_text(json.dumps(carte.__dict__, ensure_ascii=False, indent=1), encoding="utf-8")
    return _executer_admin([f'netsh interface ipv4 set address name="{carte.nom}" static {ip_pc} {masque}'])


def remettre_pc(dossier: Path | None = None) -> bool:
    """Remet la carte réseau du PC comme elle était avant (automatique, ou l'ancienne adresse fixe)."""
    f = (dossier or Path(".")) / SAUVEGARDE_PC
    if not f.exists():
        return False
    avant = json.loads(f.read_text(encoding="utf-8"))
    nom = avant["nom"]
    if avant.get("dhcp", True):
        cmds = [f'netsh interface ipv4 set address name="{nom}" source=dhcp',
                f'netsh interface ipv4 set dnsservers name="{nom}" source=dhcp']
    else:
        masque = str(ipaddress.IPv4Network(f"0.0.0.0/{avant['prefixe']}").netmask)
        gw = f" {avant['passerelle']}" if avant.get("passerelle") else ""
        cmds = [f'netsh interface ipv4 set address name="{nom}" static {avant["ip"]} {masque}{gw}']
        if avant.get("dns"):
            cmds.append(f'netsh interface ipv4 set dnsservers name="{nom}" static {avant["dns"][0]} primary')
    ok = _executer_admin(cmds)
    if ok:
        f.unlink()
    return ok


def carte_filaire() -> tuple[str, CartePC | None]:
    """Nom de la carte réseau filaire du PC (celle à brancher sur le pare-feu), et sa configuration si elle en a une."""
    noms = []
    if os.name == "nt":
        sortie = _powershell("Get-NetAdapter -Physical -ErrorAction SilentlyContinue | Sort-Object "
                             "@{e={$_.Status -ne 'Up'}} | ForEach-Object { $_.Name + '|' + $_.InterfaceDescription }")
        for ligne in sortie.splitlines():
            nom, _, desc = ligne.partition("|")
            if nom.strip() and not re.search(r"wi-?fi|wireless|wlan|bluetooth|sans fil", f"{nom} {desc}", re.I):
                noms.append(nom.strip())
    if not noms:
        return "", None
    carte = next((c for c in cartes_pc() if c.nom == noms[0]), None)
    return noms[0], carte


def regler_pc_filaire(dossier: Path | None = None) -> tuple[bool, str]:
    """Règle la carte filaire du PC pour joindre un pare-feu neuf (172.16.16.x). Renvoie (lancé ?, message)."""
    nom, carte = carte_filaire()
    if not nom:
        return False, "Aucune carte réseau filaire trouvée sur ce PC : il faut un port Ethernet (ou un adaptateur USB)."
    carte = carte or CartePC(nom=nom, index=0, ip="", prefixe=24, dhcp=True)
    if regler_pc_pour(carte, dossier=dossier):
        return True, f"Carte « {nom} » réglée en {PC_POUR_PARE_FEU_NEUF} (Windows a demandé l'autorisation)."
    return False, "Réglage refusé ou impossible (l'autorisation administrateur est nécessaire)."


def reglage_pc_en_attente(dossier: Path | None = None) -> bool:
    return ((dossier or Path(".")) / SAUVEGARDE_PC).exists()
