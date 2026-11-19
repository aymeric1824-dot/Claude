"""Avant / après un envoi, en clair : ce qui a été ajouté, modifié ou supprimé sur le pare-feu.

On compare l'état lu avant l'envoi (photo « avant ») et l'état relu juste après, type d'objet par type d'objet.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .simulateur import cle

NOMS = {
    "IPHost": "Équipement / réseau", "FQDNHost": "Nom de domaine", "IPHostGroup": "Groupe d'équipements",
    "Services": "Service", "FirewallRule": "Règle de pare-feu", "NATRule": "Redirection / NAT", "Zone": "Zone",
    "VLAN": "VLAN", "Interface": "Interface", "DHCPServer": "Serveur DHCP", "User": "Compte",
    "VPNIPSecConnection": "VPN entre sites", "SSLVPNPolicy": "VPN télétravail", "WirelessNetworks": "Wi-Fi",
    "UnicastRoute": "Route", "AuthenticationServer": "Serveur Active Directory", "CountryGroup": "Groupe de pays",
    "QoSPolicy": "Priorité de débit", "REDDevice": "Boîtier RED",
}


@dataclass
class Ecarts:
    ajoutes: list[str] = field(default_factory=list)
    modifies: list[str] = field(default_factory=list)
    supprimes: list[str] = field(default_factory=list)

    def resume(self) -> str:
        return f"{len(self.ajoutes)} ajouté(s), {len(self.modifies)} modifié(s), {len(self.supprimes)} supprimé(s)"


def _elements(balise: str, contenu) -> dict[str, str]:
    if not isinstance(contenu, (dict, list)):
        return {}
    liste = contenu if isinstance(contenu, list) else [contenu]
    res = {}
    for i, e in enumerate(liste):
        if not isinstance(e, dict):
            continue
        e = {k: v for k, v in e.items() if k != "@transactionid"}
        nom = str(cle(balise, e) or ("(réglage)" if len(liste) == 1 else f"#{i + 1}"))
        res[nom] = json.dumps(e, sort_keys=True, ensure_ascii=False, default=str)
    return res


def comparer(avant: dict, apres: dict) -> Ecarts:
    ec = Ecarts()
    for balise in sorted(set(avant) | set(apres)):
        a, b = _elements(balise, avant.get(balise)), _elements(balise, apres.get(balise))
        libelle = NOMS.get(balise, balise)
        ec.ajoutes += [f"{libelle} « {n} »" for n in sorted(set(b) - set(a))]
        ec.supprimes += [f"{libelle} « {n} »" for n in sorted(set(a) - set(b))]
        ec.modifies += [f"{libelle} « {n} »" for n in sorted(set(a) & set(b)) if a[n] != b[n]]
    return ec


def afficher(ec: Ecarts, ecrire=print, limite: int = 40) -> None:
    vert, jaune, rouge, fin = "\033[32m", "\033[33m", "\033[31m", "\033[0m"
    ecrire(f"\nAvant / après : {ec.resume()}")
    for couleur, signe, liste in ((vert, "+", ec.ajoutes), (jaune, "~", ec.modifies), (rouge, "−", ec.supprimes)):
        for x in liste[:limite]:
            ecrire(f"  {couleur}{signe} {x}{fin}")
        if len(liste) > limite:
            ecrire(f"  … et {len(liste) - limite} autre(s)")


def html(ec: Ecarts) -> str:
    import html as h
    blocs = []
    for titre, liste in (("Ajouté", ec.ajoutes), ("Modifié", ec.modifies), ("Supprimé", ec.supprimes)):
        if liste:
            blocs.append(f"<h3>{titre} ({len(liste)})</h3><ul>{''.join(f'<li>{h.escape(x)}</li>' for x in liste)}</ul>")
    return f"<h2>Avant / après</h2><p>{h.escape(ec.resume())}</p>{''.join(blocs)}"
