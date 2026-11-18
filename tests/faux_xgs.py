"""Faux pare-feu XGS en mémoire, qui remplace requests.post pendant les tests."""
from __future__ import annotations

import copy

import requests
import xmltodict

SINGLETONS = {"AdminSettings", "Time", "DNS", "Notification", "BackupRestore", "SNMPAgentConfiguration",
              "SSLTunnelAccessSettings", "GatewayConfiguration"}


def cle(balise, contenu):
    if not isinstance(contenu, dict):
        return ""
    if balise == "User":
        return contenu.get("Username", "")
    for k in ("Name", "Username", "ServerName"):
        if k in contenu:
            return contenu[k]
    for sous in ("TunnelPolicy", "Configuration", "ActiveDirectory"):
        if isinstance(contenu.get(sous), dict):
            return cle(balise, contenu[sous])
    if balise == "UnicastRoute":
        return contenu.get("DestinationIP", "")
    if balise == "Interface":
        return contenu.get("Hardware", "")
    return ""


class FauxXGS:
    def __init__(self, mdp="secret", ip="172.16.16.16"):
        self.mdp, self.ip = mdp, ip
        self.requetes: list[dict] = []
        self.objets: dict[str, dict[str, dict]] = {}
        for z in ("LAN", "WAN", "DMZ", "VPN", "WiFi"):
            self._mettre("Zone", {"Name": z, "Type": z, "ApplianceAccess": {"AdminServices": {"HTTPS": "Enable"}}})
        for n, ip_ in (("Port1", "172.16.16.16"), ("Port2", None), ("Port3", None)):
            d = {"Name": n, "Hardware": n, "NetworkZone": "LAN" if n == "Port1" else "WAN", "IPv4Assignment": "Static",
                 "Status": "Connected", "InterfaceStatus": "ON"}
            if ip_:
                d.update(IPAddress=ip_, Netmask="255.255.255.0")
            self._mettre("Interface", d)
        for s in ("HTTP", "HTTPS", "DNS", "NTP"):
            self._mettre("Services", {"Name": s})
        self._mettre("WebFilterPolicy", {"Name": "Default Workplace Policy"})
        self._mettre("IPSPolicy", {"Name": "lantowan_general"})
        self._mettre("ApplicationFilterPolicy", {"Name": "Block generally unwanted apps"})
        self._mettre("VPNProfile", {"Name": "IKEv2"})
        self.objets["SSLTunnelAccessSettings"] = {"": {"Protocol": "TCP", "Port": "8443", "SSLServerCertificate": "ApplianceCertificate"}}
        self.objets["GatewayConfiguration"] = {"": {"GatewayFailoverTimeout": "60", "Gateway": [
            {"Name": "Port2_GW", "Type": "Active"}, {"Name": "Port3_GW", "Type": "Active"}]}}

    def _mettre(self, balise, contenu):
        self.objets.setdefault(balise, {})[cle(balise, contenu)] = contenu

    def obtenir(self, balise, nom=""):
        return self.objets.get(balise, {}).get(nom)

    # ------------------------------------------------------------------ requests.post
    def post(self, url, data, headers, verify, timeout):
        hote = url.split("//")[1].split(":")[0]
        if hote != self.ip:
            raise requests.exceptions.ConnectionError("hôte injoignable")
        req = xmltodict.parse(data["reqxml"])["Request"]
        self.requetes.append(req)
        if req["Login"]["Password"] != self.mdp:
            return _rep("<Login><status>Authentication Failure</status></Login>")
        corps = "<Login><status>Authentication Successful</status></Login>"
        if "Get" in req:
            for balise in req["Get"]:
                elements = list(self.objets.get(balise, {}).values())
                if not elements:
                    corps += f"<{balise}><Status>No. of records Zero.</Status></{balise}>"
                else:
                    corps += "".join(xmltodict.unparse({balise: e}, full_document=False) for e in elements)
        if "Set" in req:
            op = req["Set"]["@operation"]
            for balise, contenu in req["Set"].items():
                if balise.startswith("@"):
                    continue
                k = cle(balise, contenu)
                if balise in SINGLETONS:
                    actuel = self.objets.setdefault(balise, {}).setdefault("", {})
                    actuel.update(copy.deepcopy(contenu))
                    corps += _ok(balise)
                elif op == "add" and k in self.objets.get(balise, {}):
                    corps += (f'<{balise}><Status code="502">Operation failed. Entity having same name already exists.'
                              f'</Status></{balise}>')
                else:
                    self._mettre(balise, copy.deepcopy(contenu))
                    corps += _ok(balise)
                    if balise == "Interface" and contenu.get("Hardware") == "Port1" and contenu.get("IPAddress") \
                            and contenu["IPAddress"] != self.ip:
                        self.ip = contenu["IPAddress"]   # la connexion tombe : l'IP a changé
        return _rep(corps)


def _ok(balise):
    return f'<{balise}><Status code="200">Configuration applied successfully.</Status></{balise}>'


class _R:
    def __init__(self, txt):
        self.content, self.text = txt.encode(), txt


def _rep(corps):
    return _R(f'<?xml version="1.0" encoding="UTF-8"?><Response APIVersion="2100.1">{corps}</Response>')
