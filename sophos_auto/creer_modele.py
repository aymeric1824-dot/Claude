"""Génère le fichier Excel modèle (avec des lignes d'exemple en jaune).

    python -m sophos_auto.creer_modele            -> modele_client.xlsx
    python -m sophos_auto.creer_modele mon.xlsx
"""
from __future__ import annotations

import sys

from .classeur import ecrire_classeur


GENERAL_EXEMPLE = {
    "Nom du client": "Exemple SARL",
    "Nom d'hôte du pare-feu": "fw-exemple",
    "DNS 1": "1.1.1.1",
    "DNS 2": "9.9.9.9",
}

EXEMPLES = {
    "Interfaces": [
        {"Port": "Port2", "Zone": "WAN", "Mode": "DHCP", "Description": "Box opérateur"},
    ],
    "Zones": [
        {"Nom": "SERVEURS", "Type": "LAN", "Description": "Serveurs internes", "Ping": "Oui", "Admin HTTPS": "Non",
         "SSH": "Non", "DNS": "Oui"},
    ],
    "VLAN": [
        {"Interface physique": "Port1", "ID VLAN": 10, "Zone": "SERVEURS", "Adresse IP": "192.168.10.254",
         "Masque": "/24", "Description": "VLAN serveurs"},
    ],
    "Hôtes": [
        {"Nom": "RES-LAN", "Type": "Réseau", "Adresse": "172.16.16.0", "Masque / IP de fin": "/24"},
        {"Nom": "SRV-AD-01", "Type": "IP", "Adresse": "192.168.10.10", "Description": "Contrôleur de domaine"},
        {"Nom": "MAJ-EDITEUR", "Type": "FQDN", "Adresse": "update.editeur-metier.fr"},
    ],
    "Services": [
        {"Nom": "APP-METIER", "Protocole": "TCP", "Ports": "8443;9000:9010", "Description": "Logiciel métier"},
    ],
    "DHCP": [
        {"Nom": "DHCP-LAN", "Interface": "Port1", "Début de plage": "172.16.16.100", "Fin de plage": "172.16.16.199",
         "Masque": "/24", "Passerelle": "172.16.16.16", "Durée du bail (minutes)": 1440},
    ],
    "Réservations DHCP": [
        {"Serveur DHCP": "DHCP-LAN", "Nom de l'appareil": "IMPRIMANTE", "Adresse MAC": "00:11:22:33:44:55",
         "Adresse IP": "172.16.16.50"},
    ],
    "Comptes": [
        {"Identifiant": "jdupont", "Nom complet": "Jean Dupont", "Type": "Utilisateur", "Mot de passe": "*demander*",
         "VPN télétravail": "Non"},
    ],
    "Redirections": [
        {"Actif": "Non", "Nom": "ACCES-NVR", "Port WAN": "Port2", "Service externe": "TCP 8443",
         "Serveur interne": "172.16.16.20", "Port interne": "443", "Zone du serveur": "LAN"},
    ],
    "Règles": [
        {"Nom": "LAN vers Internet", "Action": "Accepter", "Zones source": "LAN", "Réseaux source": "RES-LAN",
         "Zones destination": "WAN", "Services": "HTTP;HTTPS;DNS", "Journaliser": "Oui",
         "Filtrage web": "Default Workplace Policy", "IPS": "lantowan_general", "Antivirus": "Oui"},
        {"Nom": "LAN vers Serveurs", "Action": "Accepter", "Zones source": "LAN", "Réseaux source": "RES-LAN",
         "Zones destination": "SERVEURS", "Réseaux destination": "192.168.10.0/24", "Journaliser": "Oui"},
    ],
}


def creer(chemin: str = "modele_client.xlsx") -> str:
    return ecrire_classeur(chemin, GENERAL_EXEMPLE, EXEMPLES, surligner=True)


if __name__ == "__main__":
    print("Modèle créé :", creer(sys.argv[1] if len(sys.argv) > 1 else "modele_client.xlsx"))
