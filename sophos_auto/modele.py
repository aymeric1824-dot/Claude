"""Lecture du fichier Excel client et conversion en opérations pour l'API Sophos.

Chaque ligne du classeur devient une ou plusieurs « opérations » : créer un
objet, mettre à jour un réglage, ou modifier un objet existant (lecture puis
écriture, par exemple pour une interface physique).
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field

from openpyxl import load_workbook

from .schema import DEMANDER, GENERAL, ONGLETS, SERVICES_ORIGINE, ZONES_ORIGINE

# Étapes d'application (dans l'ordre)
ETAPES = {
    "système": 10, "zones": 20, "interfaces": 30, "vlan": 35, "routes": 40, "wifi": 45,
    "hôtes": 50, "groupes": 55, "services": 60, "dhcp": 65, "comptes": 70, "vpn": 75,
    "règles": 80, "nat": 85, "central": 90, "fin": 99, "après": 100,
}


# ----------------------------------------------------------------------------- structures
@dataclass
class Secret:
    """Mot de passe à demander au lancement (jamais écrit dans les rapports)."""
    libelle: str
    valeur: str | None = None


@dataclass
class Operation:
    onglet: str
    ligne: int
    nom: str
    balise: str
    contenu: dict
    etape: int
    mode: str = "creer"          # creer (ajout, sinon mise à jour) | maj (mise à jour directe) | patch (lecture + modification)
    refs: list[tuple[str, str]] = field(default_factory=list)  # (type, nom) utilisés par l'opération
    cle: str | None = None       # patch : nom de l'objet à lire
    champ_cle: str = "Name"      # patch : champ qui porte ce nom
    sous_liste: str | None = None  # patch : l'objet est dans une liste (ex. GatewayConfiguration/Gateway)
    retirer: list[str] = field(default_factory=list)   # patch : champs à supprimer
    defauts: dict = field(default_factory=dict)       # patch : champs ajoutés seulement s'ils manquent
    existe_ok: bool = False      # « existe déjà » = réussite (ex. routes, sans nom)
    facultatif: bool = False     # un échec n'est qu'un avertissement (à finir à la main)
    conseil_echec: str = ""      # que faire à la main si l'opération échoue

    @property
    def libelle(self) -> str:
        return f"[{self.onglet}] {self.nom}"


@dataclass
class Configuration:
    general: dict[str, str] = field(default_factory=dict)
    operations: list[Operation] = field(default_factory=list)
    erreurs: list[str] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)
    definis: dict[str, set[str]] = field(default_factory=dict)   # noms créés par le fichier, par type
    ip_interfaces: dict[str, tuple[str, str]] = field(default_factory=dict)  # interface -> (ip, masque)
    _auto: dict[str, str] = field(default_factory=dict)

    def ajouter(self, op: Operation, type_ref: str | None = None) -> Operation:
        self.operations.append(op)
        if type_ref:
            self.definis.setdefault(type_ref, set()).add(op.nom)
        return op

    def defini(self, type_ref: str, nom: str) -> bool:
        return nom in self.definis.get(type_ref, set())

    # ---- objets créés automatiquement quand on écrit une adresse au lieu d'un nom
    def reseau(self, texte: str, onglet: str, ligne: int) -> str:
        """« 192.168.1.0/24 », « 10.0.0.5 » ou « 10.0.0.10-10.0.0.20 » -> nom d'objet créé automatiquement.
        Un nom d'objet est renvoyé tel quel."""
        t = texte.strip()
        if t in self._auto:
            return self._auto[t]
        contenu = None
        try:
            if "-" in t and re.fullmatch(r"[\d.]+\s*-\s*[\d.]+", t):
                a, b = (str(ipaddress.IPv4Address(x.strip())) for x in t.split("-"))
                nom, contenu = f"PLAGE_{a}-{b}", {"Name": f"PLAGE_{a}-{b}", "IPFamily": "IPv4", "HostType": "IPRange",
                                                   "StartIPAddress": a, "EndIPAddress": b}
            elif "/" in t:
                n = ipaddress.IPv4Network(t, strict=False)
                if n.prefixlen == 32:
                    t2 = str(n.network_address)
                    nom, contenu = f"IP_{t2}", {"Name": f"IP_{t2}", "IPFamily": "IPv4", "HostType": "IP", "IPAddress": t2}
                else:
                    nom = f"RES_{n.network_address}_{n.prefixlen}"
                    contenu = {"Name": nom, "IPFamily": "IPv4", "HostType": "Network",
                               "IPAddress": str(n.network_address), "Subnet": str(n.netmask)}
            else:
                ip = str(ipaddress.IPv4Address(t))
                nom, contenu = f"IP_{ip}", {"Name": f"IP_{ip}", "IPFamily": "IPv4", "HostType": "IP", "IPAddress": ip}
        except ValueError:
            if re.fullmatch(r"[\d./\- ]+", t):
                raise ErreurLigne(f"adresse invalide : « {t} »") from None
            return t  # c'est un nom d'objet
        cles = ("HostType", "IPAddress", "Subnet", "StartIPAddress", "EndIPAddress")
        existant = next((o.nom for o in self.operations if o.balise == "IPHost" and o.onglet != "Auto"
                         and all(o.contenu.get(k) == contenu.get(k) for k in cles)), None)
        if existant:   # un objet de même adresse est déjà déclaré : on le réutilise
            self._auto[t] = existant
            return existant
        self._auto[t] = nom
        if not self.defini("reseau", nom):
            self.ajouter(Operation("Auto", ligne, nom, "IPHost", contenu, ETAPES["hôtes"]), "reseau")
        return nom

    def service(self, texte: str, ligne: int) -> str:
        """« TCP 8443 », « udp 1194 », « 8443 » ou « TCP 9000-9010 » -> service créé automatiquement."""
        t = texte.strip()
        m = re.fullmatch(r"(?i)(tcp|udp|tcp\+udp)?\s*[: ]?\s*(\d{1,5}(?:\s*[-:]\s*\d{1,5})?)", t)
        if not m:
            return t  # nom de service
        proto = (m.group(1) or "TCP").upper()
        ports = re.sub(r"\s", "", m.group(2)).replace("-", ":")
        nom = f"{proto.replace('+', '-')}-{ports.replace(':', '-')}"
        if t in self._auto:
            return self._auto[t]
        self._auto[t] = nom
        if not self.defini("service", nom):
            contenu = _contenu_service(nom, proto, [ports])
            self.ajouter(Operation("Auto", ligne, nom, "Services", contenu, ETAPES["services"]), "service")
        return nom


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
        raise ErreurLigne(f"{quoi} invalide : « {t} »" if t else f"{quoi} manquante") from None


def _masque(v) -> str:
    t = _txt(v).lstrip("/")
    if not t:
        raise ErreurLigne("masque manquant")
    try:
        if t.isdigit():
            return str(ipaddress.IPv4Network(f"0.0.0.0/{t}").netmask)
        ipaddress.IPv4Network(f"0.0.0.0/{t}")
        return t
    except ValueError:
        raise ErreurLigne(f"masque invalide : « {t} »") from None


def _ip_masque(ip_v, masque_v) -> tuple[str, str]:
    """Accepte « 192.168.1.254 » + « /24 », ou « 192.168.1.254/24 » dans la colonne IP."""
    t = _txt(ip_v)
    if "/" in t and not _txt(masque_v):
        t, m = t.split("/", 1)
        return _ip(t), _masque(m)
    return _ip(t), _masque(masque_v)


def _choix(v, valeurs: dict[str, str], quoi: str, defaut: str | None = None) -> str:
    t = _txt(v).lower()
    if not t and defaut is not None:
        return defaut
    for cle, val in valeurs.items():
        if t == cle.lower():
            return val
    raise ErreurLigne(f"{quoi} « {v} » inconnu (valeurs possibles : {', '.join(valeurs)})")


def _ports(v) -> list[str]:
    ports = []
    for p in _liste(v):
        p = p.replace("-", ":").replace(" ", "")
        morceaux = p.split(":")
        if len(morceaux) > 2 or not all(m.isdigit() and 1 <= int(m) <= 65535 for m in morceaux):
            raise ErreurLigne(f"port invalide : « {p} »")
        ports.append(p)
    if not ports:
        raise ErreurLigne("aucun port indiqué")
    return ports


PORTS_SENSIBLES = {3389: "le bureau à distance (RDP)", 445: "le partage de fichiers Windows (SMB)", 139: "NetBIOS",
                   23: "Telnet", 21: "FTP", 22: "SSH", 1433: "SQL Server", 3306: "MySQL", 5900: "VNC",
                   135: "RPC Windows", 5985: "WinRM", 5986: "WinRM"}


def _port_risque(texte: str) -> str:
    """Renvoie la description du port sensible contenu dans « TCP 3389 », « 3389 », « RDP »..., sinon ""."""
    t = texte.strip().upper()
    if not t:
        return ""
    for mot, port in (("RDP", 3389), ("SMB", 445), ("TELNET", 23), ("VNC", 5900)):
        if mot in t:
            return PORTS_SENSIBLES[port]
    for a, b in re.findall(r"(\d{1,5})(?:\s*[-:]\s*(\d{1,5}))?", t):
        debut, fin = int(a), int(b or a)
        for port, lib in PORTS_SENSIBLES.items():
            if debut <= port <= fin:
                return lib
    return ""


def _secret(v, libelle: str):
    t = _txt(v)
    if not t or t == DEMANDER:
        return Secret(libelle)
    return t


def _contenu_service(nom: str, proto: str, ports: list[str]) -> dict:
    protos = ["TCP", "UDP"] if proto == "TCP+UDP" else [proto]
    details = [{"SourcePort": "1:65535", "DestinationPort": p, "Protocol": pr} for pr in protos for p in ports]
    return {"Name": nom, "Type": "TCPorUDP", "ServiceDetails": {"ServiceDetail": details}}


# ----------------------------------------------------------------------------- règles et NAT (partagés)
def regle(cfg: Configuration, onglet: str, ligne: int, nom: str, *, action="Accept",
          zones_src=(), reseaux_src=(), zones_dst=(), reseaux_dst=(), services=(),
          journal=True, web="", appli="", ips="", antivirus=False, description="", qos="",
          position="Bottom") -> Operation:
    zs, zd = list(zones_src), list(zones_dst)
    rs = [cfg.reseau(r, onglet, ligne) for r in reseaux_src]
    rd = [cfg.reseau(r, onglet, ligne) for r in reseaux_dst]
    sv = [cfg.service(s, ligne) for s in services]
    p: dict = {"Action": action, "LogTraffic": _ed(journal), "SkipLocalDestined": "Disable"}
    if zs:
        p["SourceZones"] = {"Zone": zs}
    if zd:
        p["DestinationZones"] = {"Zone": zd}
    p["Schedule"] = "All The Time"
    if rs:
        p["SourceNetworks"] = {"Network": rs}
    if rd:
        p["DestinationNetworks"] = {"Network": rd}
    if sv:
        p["Services"] = {"Service": sv}
    if web:
        p["WebFilter"] = web
    if antivirus:
        p["ScanVirus"] = "Enable"
    if appli:
        p["ApplicationControl"] = appli
    if ips:
        p["IntrusionPrevention"] = ips
    if qos:
        p["TrafficShapingPolicy"] = qos
    contenu = {"Name": nom, "Description": description, "IPFamily": "IPv4", "Status": "Enable",
               "Position": position, "PolicyType": "Network", "NetworkPolicy": p}
    refs = [("zone", z) for z in zs + zd] + [("reseau", r) for r in rs + rd] + [("service", s) for s in sv]
    refs += [(t, n) for t, n in (("webfilter", web), ("appfilter", appli), ("ips", ips), ("qos", qos)) if n]
    return cfg.ajouter(Operation(onglet, ligne, nom, "FirewallRule", contenu, ETAPES["règles"], refs=refs), "regle")


# ----------------------------------------------------------------------------- onglets
def _interfaces(cfg, c, onglet, ligne):
    port = _txt(c["Port"])
    if not port:
        raise ErreurLigne("port manquant")
    zone = _txt(c["Zone"]) or "LAN"
    mode = _choix(c["Mode"], {"Statique": "Static", "Static": "Static", "DHCP": "DHCP", "PPPoE": "PPPoE"}, "mode", "Static")
    patch = {"NetworkZone": zone, "IPv4Configuration": "Enable", "IPv4Assignment": mode}
    retirer, defauts = ["Status", "InterfaceStatus"], {}
    if mode == "Static":
        ip, masque = _ip_masque(c["Adresse IP"], c["Masque"])
        patch.update(IPAddress=ip, Netmask=masque)
        cfg.ip_interfaces[port] = (ip, masque)
        if _txt(c["Passerelle"]):
            patch["GatewayIP"] = _ip(c["Passerelle"], "passerelle")
            defauts["GatewayName"] = f"{port}_GW"
        elif zone.upper() == "WAN":
            raise ErreurLigne("un port WAN en IP fixe a besoin d'une passerelle (IP de la box / du routeur)")
        else:
            retirer += ["GatewayIP", "GatewayName"]
    else:
        retirer += ["IPAddress", "Netmask", "GatewayIP"]
        if mode == "PPPoE":
            if not _txt(c["Utilisateur PPPoE"]):
                raise ErreurLigne("identifiant PPPoE manquant")
            patch["Username"] = _txt(c["Utilisateur PPPoE"])
            patch["Password"] = _secret(c["Mot de passe PPPoE"], f"Mot de passe PPPoE ({port})")
    cfg.ajouter(Operation(onglet, ligne, port, "Interface", patch, ETAPES["interfaces"], mode="patch",
                          cle=port, champ_cle="Hardware", retirer=retirer, defauts=defauts,
                          refs=[("zone", zone)]), "interface")


def _zones(cfg, c, onglet, ligne):
    nom = _txt(c["Nom"])
    contenu = {
        "Name": nom,
        "Type": _choix(c["Type"], {"LAN": "LAN", "DMZ": "DMZ"}, "type de zone", "LAN"),
        "Description": _txt(c["Description"]),
        "ApplianceAccess": {
            "AdminServices": {"HTTPS": _ed(_oui(c["Admin HTTPS"])), "SSH": _ed(_oui(c["SSH"]))},
            "NetworkServices": {"DNS": _ed(_oui(c["DNS"])), "Ping": _ed(_oui(c["Ping"]))},
        },
    }
    cfg.ajouter(Operation(onglet, ligne, nom, "Zone", contenu, ETAPES["zones"]), "zone")


def _vlan(cfg, c, onglet, ligne):
    interface = _txt(c["Interface physique"])
    if not interface:
        raise ErreurLigne("interface physique manquante")
    vid = _txt(c["ID VLAN"])
    if not vid.isdigit() or not 1 <= int(vid) <= 4094:
        raise ErreurLigne(f"ID VLAN invalide : « {vid} »")
    nom = f"{interface}.{vid}"
    ip, masque = _ip_masque(c["Adresse IP"], c["Masque"])
    zone = _txt(c["Zone"]) or "LAN"
    contenu = {"Name": nom, "Hardware": nom, "Interface": interface, "Zone": zone, "VLANID": vid,
               "IPv4Configuration": "Enable", "IPv4Assignment": "Static", "IPAddress": ip, "Netmask": masque}
    cfg.ip_interfaces[nom] = (ip, masque)
    cfg.ajouter(Operation(onglet, ligne, nom, "VLAN", contenu, ETAPES["vlan"],
                          refs=[("zone", zone), ("interface", interface)]), "interface")


def _routes(cfg, c, onglet, ligne):
    t = _txt(c["Réseau de destination"])
    try:
        reseau = ipaddress.IPv4Network(t, strict=False)
    except ValueError:
        raise ErreurLigne(f"réseau de destination invalide : « {t} » (ex. 10.20.0.0/16)") from None
    gw, interface = _ip(c["Passerelle"], "passerelle"), _txt(c["Interface"])
    if not interface:
        raise ErreurLigne("interface manquante")
    contenu = {"IPFamily": "IPv4", "DestinationIP": str(reseau.network_address), "Netmask": str(reseau.netmask),
               "Gateway": gw, "Interface": interface, "Distance": "0", "AdministrativeDistance": "1",
               "Description": _txt(c["Description"])}
    cfg.ajouter(Operation(onglet, ligne, f"{reseau} via {gw}", "UnicastRoute", contenu, ETAPES["routes"],
                          existe_ok=True, refs=[("interface", interface)]))


def _wifi(cfg, c, onglet, ligne):
    nom, ssid = _txt(c["Nom"]), _txt(c["SSID"])
    if not ssid:
        raise ErreurLigne("SSID manquant")
    cle = _secret(c["Clé Wi-Fi"], f"Clé Wi-Fi ({ssid})")
    if isinstance(cle, str) and len(cle) < 8:
        raise ErreurLigne("la clé Wi-Fi doit faire au moins 8 caractères")
    n = len(cfg.definis.get("wifi", set())) + 1
    materiel = f"wlnet{n}"
    separe = _choix(c["Mode"], {"Zone séparée": True, "Zone separee": True, "Pont vers le LAN": False}, "mode", True)
    contenu = {"Name": nom, "Hardware": materiel, "SSID": ssid, "SecurityMode": "WPA2Personal", "Key": cle,
               "ClientTraffic": "SeparateZone" if separe else "BridgetoAPLAN"}
    refs = []
    if separe:
        zone = _txt(c["Zone"]) or "WiFi"
        ip, masque = _ip_masque(c["Adresse IP"], c["Masque"])
        contenu.update(Zone=zone, IPAddress=ip, Netmask=masque)
        cfg.ip_interfaces[materiel] = (ip, masque)
        cfg.ip_interfaces[nom] = (ip, masque)
        refs.append(("zone", zone))
    contenu.update(FrequencyBand="2.4and5GHz", ClientIsolation="Enabled" if _oui(c["Isolation des clients"]) else "Disabled",
                   HideSSID="Enabled" if _oui(c["SSID masqué"]) else "Disabled", MACFiltering="None")
    cfg.ajouter(Operation(onglet, ligne, nom, "WirelessNetworks", contenu, ETAPES["wifi"], refs=refs), "wifi")
    cfg.definis.setdefault("interface", set()).update({materiel, nom})


def _hotes(cfg, c, onglet, ligne):
    nom = _txt(c["Nom"])
    type_ = _choix(c["Type"], {"IP": "IP", "Réseau": "Network", "Reseau": "Network", "Network": "Network",
                               "Plage": "IPRange", "IPRange": "IPRange", "FQDN": "FQDN"}, "type d'hôte")
    adresse, extra, desc = c["Adresse"], c["Masque / IP de fin"], _txt(c["Description"])
    if type_ == "FQDN":
        fqdn = _txt(adresse)
        if not fqdn or " " in fqdn:
            raise ErreurLigne(f"FQDN invalide : « {fqdn} »")
        cfg.ajouter(Operation(onglet, ligne, nom, "FQDNHost", {"Name": nom, "Description": desc, "FQDN": fqdn},
                              ETAPES["hôtes"]), "reseau")
        return
    contenu = {"Name": nom, "IPFamily": "IPv4", "HostType": type_}
    if type_ == "IP":
        contenu["IPAddress"] = _ip(adresse)
    elif type_ == "Network":
        ip, masque = _ip_masque(adresse, extra)
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
    cfg.ajouter(Operation(onglet, ligne, nom, "IPHost", contenu, ETAPES["hôtes"]), "reseau")


def _groupes(cfg, c, onglet, ligne):
    nom = _txt(c["Nom"])
    membres = [cfg.reseau(m, onglet, ligne) for m in _liste(c["Membres"])]
    if not membres:
        raise ErreurLigne("le groupe n'a aucun membre")
    contenu = {"Name": nom, "IPFamily": "IPv4", "Description": _txt(c["Description"]), "HostList": {"Host": membres}}
    cfg.ajouter(Operation(onglet, ligne, nom, "IPHostGroup", contenu, ETAPES["groupes"],
                          refs=[("reseau", m) for m in membres]), "reseau")


def _services(cfg, c, onglet, ligne):
    nom = _txt(c["Nom"])
    proto = _choix(c["Protocole"], {"TCP": "TCP", "UDP": "UDP", "TCP+UDP": "TCP+UDP", "TCP/UDP": "TCP+UDP"}, "protocole")
    cfg.ajouter(Operation(onglet, ligne, nom, "Services", _contenu_service(nom, proto, _ports(c["Ports"])),
                          ETAPES["services"]), "service")


def _dhcp(cfg, c, onglet, ligne):
    nom, interface = _txt(c["Nom"]), _txt(c["Interface"])
    if not interface:
        raise ErreurLigne("interface manquante")
    debut, fin = _ip(c["Début de plage"], "début de plage"), _ip(c["Fin de plage"], "fin de plage")
    if ipaddress.IPv4Address(debut) > ipaddress.IPv4Address(fin):
        raise ErreurLigne("le début de plage est après la fin")
    ip_if = cfg.ip_interfaces.get(interface)
    masque = _masque(c["Masque"]) if _txt(c["Masque"]) else (ip_if[1] if ip_if else _masque(""))
    passerelle = _ip(c["Passerelle"], "passerelle") if _txt(c["Passerelle"]) else (ip_if[0] if ip_if else None)
    if not passerelle:
        raise ErreurLigne("passerelle manquante (en général l'IP du pare-feu sur ce réseau)")
    contenu: dict = {"Name": nom, "Interface": interface}
    if ip_if and passerelle == ip_if[0]:
        contenu["UseInterfaceIPasGateway"] = "UseInterfaceIPAsGateway"
    contenu["IPLease"] = {"IP": f"{debut}-{fin}"}
    contenu["SubnetMask"] = masque
    if _txt(c["Domaine"]):
        contenu["DomainName"] = _txt(c["Domaine"])
    bail = _txt(c["Durée du bail (minutes)"]) or "1440"
    if not bail.isdigit() or not 1 <= int(bail) <= 43200:
        raise ErreurLigne("durée du bail invalide (1 à 43200 minutes)")
    contenu.update(Gateway=passerelle, DefaultLeaseTime=bail, MaxLeaseTime=str(max(int(bail), 2880)),
                   ConflictDetection="Enable")
    if _txt(c["DNS 1"]):
        contenu["PrimaryDNSServer"] = _ip(c["DNS 1"], "DNS 1")
        if _txt(c["DNS 2"]):
            contenu["SecondaryDNSServer"] = _ip(c["DNS 2"], "DNS 2")
    else:
        contenu["UseApplianceDNSSettings"] = "Enable"
    cfg.ajouter(Operation(onglet, ligne, nom, "DHCPServer", contenu, ETAPES["dhcp"],
                          refs=[("interface", interface)]), "dhcp")


def _reservations(cfg, c, onglet, ligne):
    serveur = _txt(c["Serveur DHCP"])
    op = next((o for o in cfg.operations if o.balise == "DHCPServer" and o.nom == serveur), None)
    if not op:
        raise ErreurLigne(f"serveur DHCP « {serveur} » absent de l'onglet DHCP")
    mac = _txt(c["Adresse MAC"]).replace("-", ":").lower()
    if not re.fullmatch(r"([0-9a-f]{2}:){5}[0-9a-f]{2}", mac):
        raise ErreurLigne(f"adresse MAC invalide : « {mac} » (ex. 00:11:22:33:44:55)")
    bail = {"HostName": _txt(c["Nom de l'appareil"]) or mac.replace(":", ""), "MACAddress": mac,
            "IPAddress": _ip(c["Adresse IP"])}
    # StaticLease se place juste après IPLease
    nouveau = {}
    for k, v in op.contenu.items():
        if k == "StaticLease":
            continue
        nouveau[k] = v
        if k == "IPLease":
            baux = op.contenu.get("StaticLease", {}).get("Lease", [])
            nouveau["StaticLease"] = {"Lease": baux + [bail]}
    op.contenu.clear()
    op.contenu.update(nouveau)


def _comptes(cfg, c, onglet, ligne):
    ident = _txt(c["Identifiant"])
    if not ident:
        raise ErreurLigne("identifiant manquant")
    admin = _choix(c["Type"], {"Administrateur": True, "Admin": True, "Utilisateur": False, "User": False}, "type", False)
    contenu: dict = {"Username": ident, "Name": _txt(c["Nom complet"]) or ident,
                     "Password": _secret(c["Mot de passe"], f"Mot de passe du compte {ident}"),
                     "UserType": "Administrator" if admin else "User"}
    if admin:
        contenu["Profile"] = _txt(c["Profil admin"]) or "Administrator"
    if _txt(c["E-mail"]):
        contenu["EmailList"] = {"EmailID": _txt(c["E-mail"])}
    contenu.update(Group="Open Group", Description="Créé par sophos_auto", LoginRestriction="AnyNode",
                   ScheduleForApplianceAccess="All The Time", LoginRestrictionForAppliance="AnyNode")
    cfg.ajouter(Operation(onglet, ligne, ident, "User", contenu, ETAPES["comptes"]), "utilisateur")
    if _oui(c["VPN télétravail"]):
        cfg.definis.setdefault("vpn_nomade", set()).add(ident)


def _vpn_sites(cfg, c, onglet, ligne):
    nom, port = _txt(c["Nom"]), _txt(c["Port WAN"]) or "Port2"
    distant = _txt(c["Adresse du site distant"])
    if not distant:
        raise ErreurLigne("adresse du site distant manquante")
    locaux = [cfg.reseau(r, onglet, ligne) for r in _liste(c["Réseaux locaux"])]
    distants = [cfg.reseau(r, onglet, ligne) for r in _liste(c["Réseaux distants"])]
    if not locaux or not distants:
        raise ErreurLigne("indiquez au moins un réseau local et un réseau distant")
    profil = _txt(c["Profil IPsec"]) or "IKEv2"
    role = _choix(c["Rôle"], {"Initier": "Initiate", "Répondre": "RespondOnly", "Repondre": "RespondOnly"}, "rôle", "Initiate")
    conf = {"Name": nom, "Description": "Créé par sophos_auto", "ConnectionType": "SiteToSite", "Policy": profil,
            "ActionOnVPNRestart": role, "AuthenticationType": "PresharedKey",
            "PresharedKey": _secret(c["Clé partagée"], f"Clé partagée du VPN {nom}"),
            "SubnetFamily": "IPv4", "EndpointFamily": "IPv4", "LocalWANPort": port, "RemoteHost": distant,
            "LocalSubnet": locaux, "RemoteNetwork": {"Network": distants}, "UserAuthenticationMode": "Disable",
            "ActivateOnSave": "y"}
    cfg.ajouter(Operation(onglet, ligne, nom, "VPNIPSecConnection", {"Configuration": conf}, ETAPES["vpn"],
                          refs=[("vpnprofile", profil), ("interface", port)] + [("reseau", r) for r in locaux + distants]))
    cfg.ajouter(Operation(onglet, ligne, f"Activation de {nom}", "VPNIPSecConnection", {"Active": {"Name": nom}},
                          ETAPES["vpn"] + 1, mode="maj", facultatif=True,
                          conseil_echec=f"activez la connexion {nom} dans VPN > IPsec (bouton Actif)"))
    regle(cfg, onglet, ligne, f"{nom} - sortant", zones_src=["LAN"], reseaux_src=locaux, zones_dst=["VPN"],
          reseaux_dst=distants, description=f"Trafic vers le site distant ({nom})")
    regle(cfg, onglet, ligne, f"{nom} - entrant", zones_src=["VPN"], reseaux_src=distants, zones_dst=["LAN"],
          reseaux_dst=locaux, description=f"Trafic depuis le site distant ({nom})")


def _redirections(cfg, c, onglet, ligne):
    nom, port_wan = _txt(c["Nom"]), _txt(c["Port WAN"]) or "Port2"
    externe = _txt(c["Service externe"])
    if not externe:
        raise ErreurLigne("service externe manquant (ex. HTTPS ou « TCP 8443 »)")
    serveur_txt = _txt(c["Serveur interne"])
    if not serveur_txt:
        raise ErreurLigne("serveur interne manquant")
    serveur = cfg.reseau(serveur_txt, onglet, ligne)
    svc_ext = cfg.service(externe, ligne)
    risque = _port_risque(externe) or _port_risque(_txt(c["Port interne"]))
    if risque and not _liste(c["Sources autorisées"]):
        cfg.avertissements.append(f"[{onglet} ligne {ligne}] SÉCURITÉ : {risque} ouvert à tout Internet. "
                                  "Préférez le VPN, ou limitez les sources autorisées.")
    svc_int = "Original"
    if _txt(c["Port interne"]):
        proto = "UDP" if externe.lower().startswith("udp") else "TCP"
        svc_int = cfg.service(f"{proto} {_txt(c['Port interne'])}", ligne)
    ip_wan = f"#{port_wan}"   # objet système : IP de l'interface WAN
    zone = _txt(c["Zone du serveur"]) or "LAN"
    sources = _liste(c["Sources autorisées"])
    if not sources and cfg.general.get("Pays autorisés depuis Internet"):
        sources = [groupe_pays(cfg, "PAYS-AUTORISES", cfg.general["Pays autorisés depuis Internet"],
                               "Pays autorisés à joindre les services publiés")]
    nat: dict = {"Name": nom, "Description": f"Redirection vers {serveur_txt}", "IPFamily": "IPv4", "Status": "Enable",
                 "Position": "Top"}
    if sources:
        nat["OriginalSourceNetworks"] = {"Network": [cfg.reseau(s, onglet, ligne) for s in sources]}
    nat.update(TranslatedSource="Original", OriginalDestinationNetworks={"Network": [ip_wan]},
               TranslatedDestination=serveur, OriginalServices={"Service": [svc_ext]}, TranslatedService=svc_int,
               InboundInterfaces={"Interface": [port_wan]})
    refs = [("reseau", serveur), ("service", svc_ext), ("interface", port_wan)]
    if svc_int != "Original":
        refs.append(("service", svc_int))
    cfg.ajouter(Operation(onglet, ligne, nom, "NATRule", nat, ETAPES["nat"], refs=refs))
    # Règle de pare-feu associée : zone de destination = zone du serveur, destination = IP publique (avant NAT)
    regle(cfg, onglet, ligne, f"{nom} - accès", zones_src=["WAN"], reseaux_src=sources, zones_dst=[zone],
          reseaux_dst=[ip_wan], services=[externe], ips="", description=f"Accès Internet vers {serveur_txt}")


def _regles(cfg, c, onglet, ligne):
    action = _choix(c["Action"], {"Accepter": "Accept", "Accept": "Accept", "Autoriser": "Accept",
                                  "Bloquer": "Drop", "Drop": "Drop", "Rejeter": "Reject", "Reject": "Reject"},
                    "action", "Accept")
    regle(cfg, onglet, ligne, _txt(c["Nom"]), action=action,
          zones_src=_liste(c["Zones source"]), reseaux_src=_liste(c["Réseaux source"]),
          zones_dst=_liste(c["Zones destination"]), reseaux_dst=_liste(c["Réseaux destination"]),
          services=_liste(c["Services"]), journal=_oui(c["Journaliser"], True),
          web=_txt(c["Filtrage web"]), appli=_txt(c["Contrôle d'applications"]), ips=_txt(c["IPS"]),
          antivirus=_oui(c["Antivirus"]), description=_txt(c["Description"]), qos=_txt(c.get("Priorité (QoS)")))


def groupe_pays(cfg: Configuration, nom: str, liste: str, description: str) -> str:
    """Crée (une seule fois) un groupe de pays utilisable comme réseau dans les règles."""
    if not cfg.defini("reseau", nom):
        pays = _liste(liste)
        if not pays:
            raise ErreurLigne(f"{nom} : aucun pays indiqué")
        cfg.ajouter(Operation("Général", 0, nom, "CountryGroup", {"Name": nom, "Description": description,
                                                                   "CountryList": {"Country": pays}},
                              ETAPES["hôtes"], conseil_echec="vérifiez l'orthographe des pays (noms anglais, comme dans "
                              "Hôtes et services > Groupes de pays)"), "reseau")
    return nom


def _sdwan(cfg, c, onglet, ligne):
    nom, gw = _txt(c["Nom"]), _txt(c["Passerelle principale"])
    if not gw:
        raise ErreurLigne("passerelle principale manquante (ex. Port2_GW)")
    contenu: dict = {"Name": nom, "Description": "Créé par sophos_auto", "IPFamily": "0"}
    sources = [cfg.reseau(r, onglet, ligne) for r in _liste(c["Réseaux source"])]
    services = [cfg.service(x, ligne) for x in _liste(c["Services"])]
    if sources:
        contenu["SourceNetworks"] = {"Network": sources}
    if services:
        contenu["Services"] = {"Service": services}
    contenu.update(LinkSelection="SelectGateways", Gateway=gw)
    secours = _txt(c["Passerelle de secours"])
    if secours:
        contenu["BackupGateway"] = secours
    refs = [("passerelle", gw)] + ([("passerelle", secours)] if secours else [])
    refs += [("reseau", r) for r in sources] + [("service", x) for x in services]
    cfg.ajouter(Operation(onglet, ligne, nom, "SDWANPolicyRoute", contenu, ETAPES["routes"] + 1, refs=refs))


PRIORITES = {"Temps réel": "RealTime", "Temps reel": "RealTime", "Critique": "BusinessCritical",
             "Normale": "Normal3", "Faible": "BestEffort"}


def _priorites(cfg, c, onglet, ligne):
    nom = _txt(c["Nom"])
    prio = _choix(c["Priorité"], PRIORITES, "priorité", "RealTime")
    contenu = {"Name": nom, "PolicyBasedOn": "Firewall", "PolicyType": "Committed", "ImplementationOn": "Total",
               "Priority": prio, "BandwidthUsageType": "Shared"}
    g, m = _txt(c["Garanti (Ko/s)"]), _txt(c["Maximum (Ko/s)"])
    if not (g.isdigit() and m.isdigit()):
        raise ErreurLigne("indiquez les débits garanti et maximum en Ko/s (nombres entiers)")
    if not 2 <= int(g) < int(m) <= 2560000:
        raise ErreurLigne("le débit maximum doit être supérieur au débit garanti (2 à 2 560 000 Ko/s)")
    contenu.update(GuaranteedBandwidth=g, BurstableBandwidth=m, Description=_txt(c["Description"]))
    cfg.ajouter(Operation(onglet, ligne, nom, "QoSPolicy", contenu, ETAPES["services"]), "qos")


def _red(cfg, c, onglet, ligne):
    nom, ident = _txt(c["Nom"]), _txt(c["ID du RED"])
    if not ident:
        raise ErreurLigne("ID du RED manquant (inscrit sous le boîtier)")
    adresse = _txt(c["Adresse du pare-feu"])
    if not adresse:
        raise ErreurLigne("adresse du pare-feu manquante (IP publique ou nom DNS)")
    ip, masque = _ip_masque(c["Adresse IP"], c["Masque"])
    zone = _txt(c["Zone"]) or "LAN"
    contenu = {"Status": "Enable", "BranchName": nom, "Device": _txt(c["Modèle"]) or "RED15", "REDDeviceID": ident,
               "UTMHostName": adresse, "Description": f"Agence {nom}", "DeploymentMode": "AutoDeployment",
               "UplinkSettings": {"Uplink": {"Connection": "DHCP"}}, "Authorized": "1",
               "NetworkSetting": {"OperationMode": "Standard", "IPAddress": ip, "NetMask": masque, "Zone": zone,
                                  "TunnelCompression": "Disable"},
               "REDMTU": "1500"}
    cfg.ip_interfaces[f"RED {nom}"] = (ip, masque)
    cfg.ajouter(Operation(onglet, ligne, nom, "REDDevice", contenu, ETAPES["vlan"] + 1, refs=[("zone", zone)],
                          conseil_echec="ajoutez le RED dans Réseau > Interfaces > Ajouter > RED"))


CONSTRUCTEURS = {
    "Interfaces": _interfaces, "Zones": _zones, "VLAN": _vlan, "Routes": _routes, "Wi-Fi": _wifi,
    "Hôtes": _hotes, "Groupes": _groupes, "Services": _services, "DHCP": _dhcp,
    "Réservations DHCP": _reservations, "Comptes": _comptes, "VPN sites": _vpn_sites,
    "Redirections": _redirections, "Règles": _regles, "SD-WAN": _sdwan, "Priorités": _priorites, "RED": _red,
}
SANS_NOM = {"Interfaces", "VLAN", "Routes", "Réservations DHCP", "Comptes"}


# ----------------------------------------------------------------------------- onglet Général
def _general(cfg: Configuration) -> None:
    """Chaque section de l'onglet Général est traitée séparément : une erreur dans l'une n'empêche pas les autres."""
    for section in (_g_systeme, _g_alertes, _g_sauvegarde, _g_snmp, _g_ad, _g_secours, _g_vpn, _g_pays, _g_otp,
                    _g_inspection, _g_ha, _g_central):
        try:
            section(cfg)
        except ErreurLigne as exc:
            cfg.erreurs.append(f"[Général] {exc}")


def _op_general(cfg: Configuration):
    def op(nom, balise, contenu, **kw):
        kw.setdefault("etape", ETAPES["système"])
        return cfg.ajouter(Operation("Général", 0, nom, balise, contenu, kw.pop("etape"), **kw))
    return op


def _g_systeme(cfg):
    g, op = cfg.general, _op_general(cfg)

    if g["Nom d'hôte du pare-feu"]:
        op("Nom d'hôte", "AdminSettings", {"HostnameSettings": {"HostName": g["Nom d'hôte du pare-feu"],
                                                                "HostNameDesc": g["Nom du client"]}}, mode="maj")
    if g["Fuseau horaire"]:
        ntp = _liste(g["Serveurs NTP"])
        contenu = {"TimeZone": g["Fuseau horaire"], "PredefinedNTPServer": "Disable" if ntp else "Enable"}
        if ntp:
            contenu["CustomNTPServer"] = {"NTPServer": ntp}
        op("Heure et NTP", "Time", contenu, mode="maj")
    dns = [_ip(g[k], k) for k in ("DNS 1", "DNS 2", "DNS 3") if g[k]]
    if dns:
        op("Serveurs DNS", "DNS", {"IPv4Settings": {"ObtainDNSFrom": "Static",
                                                    "DNSIPList": {f"DNS{i}": d for i, d in enumerate(dns, 1)}}}, mode="maj")


def _g_alertes(cfg):
    g, op = cfg.general, _op_general(cfg)
    if g["Serveur SMTP"]:
        if not (g["Adresse expéditeur"] and g["Destinataire des alertes"]):
            raise ErreurLigne("alertes e-mail : indiquez l'adresse expéditeur et le destinataire")
        secu = {"Aucune": "None", "STARTTLS": "STARTTLS", "SSL/TLS": "SSLTLS"}.get(g["Sécurité SMTP"], "STARTTLS")
        contenu = {"MailServer": g["Serveur SMTP"], "Port": g["Port SMTP"] or "587",
                   "AuthenticationRequired": "Enable" if g["Utilisateur SMTP"] else "Disable"}
        if g["Utilisateur SMTP"]:
            contenu["Username"] = g["Utilisateur SMTP"]
            contenu["Password"] = _secret(g["Mot de passe SMTP"], "Mot de passe SMTP")
        contenu.update(SenderAddress=g["Adresse expéditeur"], Recepient=g["Destinataire des alertes"],
                       ConnectionSecurity=secu, IPSecTunnelStatusChangeNotification="Enable")
        op("Alertes e-mail", "Notification", contenu, mode="maj")


def _g_sauvegarde(cfg):
    g, op = cfg.general, _op_general(cfg)
    freq = {"Quotidienne": "Daily", "Hebdomadaire": "Weekly", "Mensuelle": "Monthly"}.get(g["Fréquence de sauvegarde"])
    if freq:
        mode = {"E-mail": "Mail", "FTP": "FTP", "Locale": "Local"}.get(g["Destination de la sauvegarde"], "Mail")
        s = {"BackupMode": mode, "BackupPrefix": re.sub(r"\W", "", g["Nom du client"])[:20] or "backup"}
        if mode == "Mail":
            if not g["E-mail de sauvegarde"]:
                raise ErreurLigne("sauvegarde par e-mail : indiquez l'adresse qui la reçoit")
            s["EmailAddress"] = g["E-mail de sauvegarde"]
        elif mode == "FTP":
            s.update(FTPServer=g["Serveur FTP"], Username=g["Utilisateur FTP"],
                     Password=_secret(g["Mot de passe FTP"], "Mot de passe FTP"), FtpPath=g["Dossier FTP"] or "/")
        s.update(BackupFrequency=freq, Day="Sunday", Hour="01", Minute="30", Date="1",
                 EncryptionPassword=_secret(g["Mot de passe de chiffrement de la sauvegarde"],
                                            "Mot de passe de chiffrement des sauvegardes"))
        op("Sauvegarde automatique", "BackupRestore", {"ScheduleBackup": s}, mode="maj")


def _g_snmp(cfg):
    g, op = cfg.general, _op_general(cfg)
    if _oui(g["SNMP activé"]):
        if not (g["Communauté SNMP"] and g["IP du serveur de supervision"]):
            raise ErreurLigne("SNMP : indiquez la communauté et l'IP du serveur de supervision")
        op("SNMP", "SNMPAgentConfiguration", {"Configuration": "Enable", "Name": g["Nom d'hôte du pare-feu"] or "sophos",
                                              "Description": g["Nom du client"], "Location": g["Lieu"],
                                              "ContactPerson": g["Contact"], "ManagerPort": "162"}, mode="maj")
        op(f"Communauté {g['Communauté SNMP']}", "SNMPCommunity",
           {"Name": g["Communauté SNMP"], "Description": "Supervision", "IPAddress": _ip(g["IP du serveur de supervision"]),
            "Supportv1ProtocolVersion": "Disable", "Supportv2cProtocolVersion": "Enable",
            "TrapSupportv1": "Disable", "TrapSupportv2c": "Enable"})
        op("SNMP autorisé depuis le LAN", "Zone", {"ApplianceAccess": {"OtherServices": {"SNMP": "Enable"}}},
           mode="patch", cle="LAN", etape=ETAPES["zones"])


def _g_ad(cfg):
    g, op = cfg.general, _op_general(cfg)
    if g["AD : adresse IP"]:
        if not (g["AD : domaine"] and g["AD : compte de service"]):
            raise ErreurLigne("Active Directory : indiquez le domaine et le compte de service")
        domaine = g["AD : domaine"]
        op(f"Active Directory {domaine}", "AuthenticationServer", {"ActiveDirectory": {
            "ServerName": f"AD-{domaine}", "ServerAddress": _ip(g["AD : adresse IP"], "IP de l'AD"),
            "Port": g["AD : port"] or "389", "NetBIOSDomain": g["AD : nom NetBIOS"] or domaine.split(".")[0].upper(),
            "ADSUsername": g["AD : compte de service"], "Password": _secret(g["AD : mot de passe"], "Mot de passe du compte de service AD"),
            "ConnectionSecurity": "Simple", "ValidCertReq": "Disable", "DisplayNameAttribute": "", "EmailAddressAttribute": "mail",
            "DomainName": domaine, "SearchQueries": {"Query": ",".join(f"dc={p}" for p in domaine.split("."))}}},
           etape=ETAPES["comptes"])


def _g_secours(cfg):
    g, op = cfg.general, _op_general(cfg)
    if g["Port WAN de secours"]:
        port = g["Port WAN de secours"]
        op(f"Lien de secours {port}", "GatewayConfiguration",
           {"Type": "Backup", "ActivateGatewayOnFailureOf": "Any", "ActionOnActivation": "InheritWeight",
            "ActionOnFailback": "ServeAllConnections"},
           mode="patch", cle=g["Passerelle de secours"] or f"{port}_GW", sous_liste="Gateway",
           etape=ETAPES["routes"], refs=[("passerelle", g["Passerelle de secours"] or f"{port}_GW")])


def _g_vpn(cfg):
    if _oui(cfg.general["VPN télétravail activé"]):
        _vpn_nomade(cfg)


def _g_pays(cfg):
    g = cfg.general
    if g.get("Pays bloqués"):
        groupe = groupe_pays(cfg, "PAYS-BLOQUES", g["Pays bloqués"], "Pays dont tout le trafic est refusé")
        regle(cfg, "Général", 0, "Blocage des pays interdits", action="Drop", zones_src=["WAN"], reseaux_src=[groupe],
              position="Top", description="Refuse tout trafic venant des pays bloqués")


def _g_otp(cfg):
    g, op = cfg.general, _op_general(cfg)
    if _oui(g.get("Double authentification VPN")) or _oui(g.get("Double authentification administrateurs")):
        vpn, admin = _oui(g.get("Double authentification VPN")), _oui(g.get("Double authentification administrateurs"))
        op("Double authentification", "OTPSettings",
           {"otp": "1", "allUsers": "1", "tokenAutoCreation": "1", "otpUserPortal": "1" if vpn else "0",
            "otpVPNPortal": "1" if vpn else "0", "otpSSLVPN": "1" if vpn else "0",
            "otpWebAdmin": "1" if admin else "0", "otpIPsec": "0"},
           mode="maj", etape=ETAPES["après"] + 1 if admin else ETAPES["comptes"] + 1, facultatif=admin,
           conseil_echec="activez les codes à usage unique dans Authentification > Mot de passe à usage unique")


def _g_inspection(cfg):
    g, op = cfg.general, _op_general(cfg)
    if _oui(g.get("Inspection HTTPS activée")):
        reseaux = [cfg.reseau(r, "Général", 0) for r in _liste(g.get("Réseaux à inspecter"))]
        profil = g.get("Profil de déchiffrement") or "Maximum compatibility"
        op("Moteur d'inspection HTTPS", "SSLTLSInspectionSettings",
           {"SSLTLSEngine": "Enabled", "SSLTLSInspection": "Enabled"}, mode="patch", etape=ETAPES["règles"])
        contenu = {"Name": "INSPECTION-HTTPS", "Description": "Déchiffrement HTTPS des postes (sophos_auto)",
                   "IsDefault": "no", "Enable": "Yes", "Position": "Bottom", "LogConnections": "Enable",
                   "DecryptAction": "Decrypt", "DecryptionProfile": profil, "SourceZones": {"Zone": ["LAN"]}}
        if reseaux:
            contenu["SourceNetworks"] = {"Network": reseaux}
        contenu["DestinationZones"] = {"Zone": ["WAN"]}
        op("INSPECTION-HTTPS", "SSLTLSInspectionRule", contenu, etape=ETAPES["règles"] + 1,
           refs=[("decryptprofile", profil)] + [("reseau", r) for r in reseaux])


def _g_ha(cfg):
    g, op = cfg.general, _op_general(cfg)
    role = g.get("Rôle haute disponibilité") or "Aucun"
    if role in ("Principal", "Secondaire"):
        if not g.get("Port de liaison HA"):
            raise ErreurLigne("haute disponibilité : indiquez le port de liaison entre les deux pare-feux")
        op(f"Haute disponibilité ({role.lower()})", "HAConfigure", {"HA_Quick": {
            "Device": "Active_Passive" if role == "Principal" else "Auxilliary",
            "NodeName": g.get("Nom d'hôte du pare-feu") or ("fw-principal" if role == "Principal" else "fw-secondaire"),
            "DedicatedLink": g["Port de liaison HA"],
            "Passphrase": _secret(g.get("Phrase secrète HA"), "Phrase secrète de la haute disponibilité")}},
           mode="maj", etape=ETAPES["central"] + 1, facultatif=True,
           conseil_echec="configurez la HA dans Système > Haute disponibilité (mode rapide), même phrase secrète des deux côtés")


def _g_central(cfg):
    g, op = cfg.general, _op_general(cfg)
    if _oui(g["Inscrire dans Sophos Central"]):
        if not g["Central : e-mail du compte"]:
            raise ErreurLigne("Sophos Central : indiquez l'e-mail du compte Central")
        conseil = "inscrivez le boîtier dans Système > Sophos Central (connexion avec votre compte Central)"
        op("Inscription dans Sophos Central", "HBCloudRegistration",
           {"Username": g["Central : e-mail du compte"],
            "Password": _secret(g["Central : mot de passe"], "Mot de passe du compte Sophos Central")},
           mode="maj", etape=ETAPES["central"], facultatif=True, conseil_echec=conseil)
        op("Gestion par Sophos Central", "EnableCloudCentralManagement",
           {"FWBackup": "BackupEnable" if _oui(g["Central : sauvegardes"], True) else "BackupDisable"},
           mode="maj", etape=ETAPES["central"], facultatif=True,
           conseil_echec="dans Système > Sophos Central, activez « Gestion par Sophos Central » puis acceptez dans Central")


def _vpn_nomade(cfg: Configuration) -> None:
    g, G = cfg.general, "Général"
    membres = sorted(cfg.definis.get("vpn_nomade", set()))
    if not membres:
        raise ErreurLigne("VPN télétravail : cochez au moins un compte « VPN télétravail » dans l'onglet Comptes")
    reseaux = [cfg.reseau(r, G, 0) for r in _liste(g["Réseaux accessibles en VPN"])]
    if not reseaux:
        raise ErreurLigne("VPN télétravail : indiquez les réseaux accessibles (ex. 192.168.1.0/24)")
    debut, fin = _ip(g["Début plage VPN"], "début plage VPN"), _ip(g["Fin plage VPN"], "fin plage VPN")
    reglages = {"Protocol": g["Protocole VPN"] or "UDP", "Port": g["Port VPN"] or "8443",
                "IPLeaseRange": {"StartIP": debut, "EndIP": fin}, "SubnetMask": _masque(g["Masque plage VPN"] or "/24")}
    if g["Adresse publique du pare-feu"]:
        reglages["OverrideHostName"] = g["Adresse publique du pare-feu"]
    if g["DNS pour les clients VPN"]:
        reglages["PrimaryDNSIPv4"] = _ip(g["DNS pour les clients VPN"], "DNS VPN")
    if g["Domaine pour les clients VPN"]:
        reglages["DomainName"] = g["Domaine pour les clients VPN"]
    cfg.ajouter(Operation(G, 0, "Réglages SSL VPN", "SSLTunnelAccessSettings", reglages, ETAPES["vpn"], mode="patch"))
    cfg.ajouter(Operation(G, 0, "VPN-TELETRAVAIL", "SSLVPNPolicy", {"TunnelPolicy": {
        "Name": "VPN-TELETRAVAIL", "Description": "Accès télétravail (sophos_auto)",
        "PolicyMembers": {"Member": membres}, "UseAsDefaultGateway": "off",
        "PermittedNetworkResourcesIPv4": {"Resource": reseaux}, "DisconnectIdleClients": "on"}},
        ETAPES["vpn"], refs=[("reseau", r) for r in reseaux]))
    cfg.ajouter(Operation(G, 0, "SSL VPN autorisé depuis Internet", "Zone",
                          {"ApplianceAccess": {"VPNServices": {"SSLVPN": "Enable"}}}, ETAPES["zones"], mode="patch", cle="WAN"))
    regle(cfg, G, 0, "VPN télétravail vers réseaux internes", zones_src=["VPN"], reseaux_src=[f"{debut}-{fin}"],
          zones_dst=["LAN"], reseaux_dst=reseaux, description="Postes en télétravail")


# Paramètres dont la valeur vide veut dire « ne pas modifier » (et non « valeur par défaut »)
VIDE_NE_PAS_MODIFIER = {"Fuseau horaire"}


# ----------------------------------------------------------------------------- lecture du classeur
def lire_classeur(chemin: str) -> Configuration:
    cfg = Configuration()
    wb = load_workbook(chemin, data_only=True)

    if "Général" in wb.sheetnames:
        for row in wb["Général"].iter_rows(min_row=2, values_only=True):
            if row and _txt(row[0]) and not _txt(row[0]).startswith("▸"):
                cfg.general[_txt(row[0])] = _txt(row[1] if len(row) > 1 else "")
    presents = set(cfg.general)
    for param, defaut, *_ in GENERAL:
        if param.startswith("▸"):
            continue
        if param in VIDE_NE_PAS_MODIFIER and param in presents:
            continue      # laissé vide exprès : le réglage du pare-feu n'est pas touché
        if not cfg.general.get(param):
            cfg.general[param] = defaut

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
            if not any(_txt(v) for k, v in ligne.items() if k != "Actif"):
                continue
            ref = f"[{onglet} ligne {num}]"
            try:
                if not _oui(ligne["Actif"], defaut=True):
                    continue
                if onglet not in SANS_NOM:
                    nom = _txt(ligne.get("Nom"))
                    if not nom:
                        raise ErreurLigne("nom manquant")
                    vus = noms_vus.setdefault(onglet, set())
                    if nom in vus:
                        raise ErreurLigne(f"le nom « {nom} » est utilisé deux fois")
                    vus.add(nom)
                avant = len(cfg.operations)
                CONSTRUCTEURS[onglet](cfg, ligne, onglet, num)
                for o in cfg.operations[avant:]:
                    if o.onglet == onglet:
                        o.ligne = num
            except ErreurLigne as exc:
                cfg.erreurs.append(f"{ref} {exc}")
    _general(cfg)

    _doublons(cfg)
    _coherence(cfg)
    _verifier_references(cfg)
    cfg.operations.sort(key=lambda o: o.etape)
    return cfg


def _reseau_objet(cfg: Configuration, nom: str) -> ipaddress.IPv4Network | None:
    o = next((x for x in cfg.operations if x.balise == "IPHost" and x.nom == nom), None)
    if not o:
        return None
    c = o.contenu
    try:
        if c.get("HostType") == "Network":
            return ipaddress.IPv4Network(f"{c['IPAddress']}/{c['Subnet']}", strict=False)
        if c.get("HostType") == "IP":
            return ipaddress.IPv4Network(f"{c['IPAddress']}/32")
    except (KeyError, ValueError):
        pass
    return None


def _coherence(cfg: Configuration) -> None:
    """Contrôles qui demandent de voir tout le fichier : chevauchements de réseaux, DHCP, doublons."""
    ou = lambda o: f"[{o.onglet} ligne {o.ligne}]" if o.ligne else f"[{o.onglet}]"  # noqa: E731
    # 1. réseaux des interfaces (LAN, VLAN, Wi-Fi...) qui se chevauchent
    locaux: list[tuple[str, ipaddress.IPv4Network]] = []
    vus = set()
    for nom, (ip, masque) in cfg.ip_interfaces.items():
        n = ipaddress.IPv4Interface(f"{ip}/{masque}").network
        if (ip, masque) in vus:
            continue
        vus.add((ip, masque))
        for autre, n2 in locaux:
            if n.overlaps(n2):
                cfg.erreurs.append(f"Les réseaux de {autre} ({n2}) et de {nom} ({n}) se chevauchent : "
                                   "chaque interface doit avoir son propre réseau.")
        locaux.append((nom, n))
    # 2. réseaux distants des VPN et plage du VPN télétravail qui chevauchent un réseau local
    for o in cfg.operations:
        if o.balise == "VPNIPSecConnection" and "Configuration" in o.contenu:
            for r in o.contenu["Configuration"]["RemoteNetwork"]["Network"]:
                n = _reseau_objet(cfg, r)
                for nom, loc in locaux:
                    if n and n.overlaps(loc):
                        cfg.erreurs.append(f"{ou(o)} le réseau distant {n} chevauche le réseau local de {nom} ({loc}) : "
                                           "le VPN ne peut pas fonctionner. Changez le plan d'adressage d'un des sites.")
        if o.balise == "SSLTunnelAccessSettings":
            debut = o.contenu["IPLeaseRange"]["StartIP"]
            for nom, loc in locaux:
                if ipaddress.IPv4Address(debut) in loc:
                    cfg.erreurs.append(f"[Général] la plage du VPN télétravail ({debut}...) est dans le réseau de {nom} "
                                       f"({loc}) : choisissez une plage inutilisée (ex. 10.81.234.5).")
    # 3. DHCP : plage dans le réseau de l'interface, sans l'IP du pare-feu ; réservations cohérentes
    for o in cfg.operations:
        if o.balise != "DHCPServer":
            continue
        ip_if = cfg.ip_interfaces.get(o.contenu["Interface"])
        debut, fin = (ipaddress.IPv4Address(x) for x in o.contenu["IPLease"]["IP"].split("-"))
        if ip_if:
            reseau = ipaddress.IPv4Interface(f"{ip_if[0]}/{ip_if[1]}").network
            if debut not in reseau or fin not in reseau:
                cfg.erreurs.append(f"{ou(o)} la plage {debut}-{fin} sort du réseau {reseau} de l'interface "
                                   f"{o.contenu['Interface']}.")
            if debut <= ipaddress.IPv4Address(ip_if[0]) <= fin:
                cfg.erreurs.append(f"{ou(o)} la plage {debut}-{fin} contient l'adresse du pare-feu ({ip_if[0]}).")
        baux = o.contenu.get("StaticLease", {}).get("Lease", [])
        macs, ips = set(), set()
        for b in baux:
            if b["MACAddress"] in macs:
                cfg.erreurs.append(f"{ou(o)} l'adresse MAC {b['MACAddress']} est réservée deux fois.")
            if b["IPAddress"] in ips:
                cfg.erreurs.append(f"{ou(o)} l'adresse {b['IPAddress']} est réservée deux fois.")
            macs.add(b["MACAddress"])
            ips.add(b["IPAddress"])
            if ip_if and ipaddress.IPv4Address(b["IPAddress"]) not in ipaddress.IPv4Interface(
                    f"{ip_if[0]}/{ip_if[1]}").network:
                cfg.erreurs.append(f"{ou(o)} la réservation {b['IPAddress']} ({b['HostName']}) n'est pas dans le "
                                   "réseau de l'interface.")
    # 4. deux objets différents pour la même adresse IP
    par_ip: dict[str, str] = {}
    for o in cfg.operations:
        if o.balise == "IPHost" and o.contenu.get("HostType") == "IP":
            ip = o.contenu["IPAddress"]
            if ip in par_ip and par_ip[ip] != o.nom:
                cfg.avertissements.append(f"{ou(o)} « {o.nom} » et « {par_ip[ip]} » ont la même adresse {ip}.")
            par_ip.setdefault(ip, o.nom)


def _doublons(cfg: Configuration) -> None:
    vus: dict[tuple[str, str], Operation] = {}
    for o in cfg.operations:
        if o.mode != "creer":
            continue
        k = (o.balise, o.nom)
        if k in vus and o.onglet != "Auto":
            cfg.erreurs.append(f"[{o.onglet} ligne {o.ligne}] « {o.nom} » est déjà défini ({vus[k].onglet} ligne {vus[k].ligne})")
        vus.setdefault(k, o)


def _verifier_references(cfg: Configuration) -> None:
    """Avertit quand une opération utilise un nom qui n'est pas créé par le fichier.
    Ce n'est pas une erreur : l'objet peut exister d'origine sur le pare-feu."""
    for o in cfg.operations:
        for type_, nom in o.refs:
            if nom.startswith("#") or cfg.defini(type_, nom):
                continue
            if (type_ == "zone" and nom in ZONES_ORIGINE) or (type_ == "service" and nom in SERVICES_ORIGINE):
                continue
            if type_ in ("webfilter", "appfilter", "ips", "vpnprofile", "passerelle", "decryptprofile"):
                continue  # stratégies d'origine : vérifiées sur le pare-feu au lancement
            if type_ == "interface" and re.fullmatch(r"Port\d+(\.\d+)?", nom):
                continue
            quoi = {"decryptprofile": "profil de déchiffrement", "qos": "priorité",
                    "zone": "zone", "reseau": "réseau", "service": "service", "webfilter": "stratégie web",
                    "appfilter": "stratégie d'applications", "ips": "stratégie IPS", "vpnprofile": "profil IPsec",
                    "interface": "interface", "passerelle": "passerelle"}[type_]
            ou = f"[{o.onglet} ligne {o.ligne}]" if o.ligne else f"[{o.onglet}]"
            cfg.avertissements.append(f"{ou} {quoi} « {nom} » absent du fichier : il doit exister sur le pare-feu")
