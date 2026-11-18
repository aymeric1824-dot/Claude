"""Glossaire : les termes techniques expliqués simplement.

Dans l'assistant, tapez ?? suivi d'un mot (ex. « ?? dhcp ») à n'importe quelle question.
"""
from __future__ import annotations

import unicodedata

TERMES: dict[str, str] = {
    "WAN": "Le côté Internet du pare-feu : le port branché sur la box ou le routeur de l'opérateur.",
    "LAN": "Le réseau local de l'entreprise : les PC, imprimantes et serveurs.",
    "DMZ": "Une zone à part pour les serveurs accessibles depuis Internet, isolée du réseau des PC.",
    "Zone": "Un groupe d'interfaces (LAN, WAN, DMZ...). Les règles du pare-feu se décident de zone à zone.",
    "Adresse IP": "Le « numéro de téléphone » d'un appareil sur le réseau, par exemple 192.168.1.10.",
    "Masque": "Indique la taille du réseau. /24 (255.255.255.0) = 254 appareils possibles.",
    "Passerelle": "L'appareil par lequel on sort du réseau. Pour les PC, c'est le pare-feu ; pour le pare-feu, la box.",
    "DHCP": "Le service qui donne automatiquement une adresse IP à chaque appareil qui se branche.",
    "Réservation DHCP": "Une adresse IP toujours donnée au même appareil, reconnu par son adresse MAC.",
    "Adresse MAC": "L'identifiant unique de la carte réseau d'un appareil (ex. 00:11:22:33:44:55), écrit sur l'étiquette.",
    "DNS": "Le service qui traduit les noms (google.fr) en adresses IP.",
    "NTP": "Le service qui met les appareils à l'heure exacte.",
    "VLAN": "Un réseau séparé qui passe sur les mêmes câbles et switchs, pour isoler des équipements (caméras, téléphones...).",
    "Trunk": "Un port de switch qui transporte plusieurs VLAN à la fois (en général celui relié au pare-feu).",
    "NAT": "La traduction d'adresses : les PC sortent sur Internet avec l'adresse publique du pare-feu.",
    "Redirection de port": "Faire arriver une connexion venant d'Internet sur un équipement interne (aussi appelé DNAT).",
    "IP publique": "L'adresse de l'entreprise sur Internet, donnée par l'opérateur. Fixe ou changeante.",
    "IP fixe": "Une adresse qui ne change jamais. Nécessaire pour les VPN et les accès depuis Internet.",
    "PPPoE": "Un mode de connexion Internet avec identifiant et mot de passe fournis par l'opérateur.",
    "VPN": "Un tunnel chiffré sur Internet entre deux sites, ou entre un PC en télétravail et l'entreprise.",
    "VPN site à site": "Un VPN permanent entre deux pare-feux, qui relie deux réseaux (siège et agence).",
    "IPsec": "Le type de VPN utilisé entre deux pare-feux.",
    "SSL VPN": "Le type de VPN utilisé par les télétravailleurs, avec le logiciel Sophos Connect.",
    "Clé partagée": "Le mot de passe commun aux deux pare-feux d'un VPN site à site.",
    "Double authentification": "En plus du mot de passe, un code à 6 chiffres affiché sur le téléphone (OTP, MFA, 2FA).",
    "OTP": "Mot de passe à usage unique : le code à 6 chiffres qui change toutes les 30 secondes.",
    "Filtrage web": "Le blocage des sites dangereux ou interdits (piratage, adultes, jeux d'argent...).",
    "IPS": "La prévention d'intrusion : le pare-feu reconnaît et bloque les attaques connues.",
    "Contrôle d'applications": "Le blocage d'applications précises (P2P, proxy de contournement...) quel que soit le port.",
    "Inspection HTTPS": "Le pare-feu déchiffre le trafic des sites sécurisés pour l'analyser. Il faut installer son certificat sur les PC.",
    "Certificat": "Une carte d'identité électronique qui prouve l'identité d'un site ou d'un pare-feu.",
    "Active Directory": "Le serveur Windows qui gère les comptes des utilisateurs (connexion « DOMAINE\\nom »).",
    "SNMP": "Le protocole qui permet à un outil de supervision de surveiller le pare-feu.",
    "Haute disponibilité": "Deux pare-feux identiques : si l'un tombe en panne, l'autre prend le relais (HA).",
    "SD-WAN": "Le choix intelligent du lien Internet selon l'usage : la téléphonie sur la fibre, le reste sur la 4G...",
    "QoS": "La qualité de service : réserver de la bande passante pour ce qui est prioritaire (voix, visio).",
    "Bande passante": "Le débit disponible sur un lien, en kilo-octets ou mégabits par seconde.",
    "RED": "Petit boîtier Sophos installé dans une agence, qui la relie automatiquement au pare-feu du siège.",
    "Sophos Central": "La console en ligne de Sophos (aussi appelée Sophos Fusion) pour gérer les pare-feux à distance.",
    "Zero Touch": "Préconfiguration du boîtier dans Sophos Central : il se configure seul au premier branchement.",
    "Firmware": "Le logiciel interne du pare-feu (SFOS). À mettre à jour régulièrement.",
    "API": "La porte d'entrée qui permet à ce programme de configurer le pare-feu automatiquement.",
    "Règle de pare-feu": "Ce qui est autorisé ou bloqué : de quelle zone vers quelle zone, pour quels services.",
    "Service": "Un protocole et un numéro de port, par exemple HTTPS = TCP 443.",
    "Port": "Selon le contexte : une prise physique du pare-feu (Port1, Port2) ou un numéro de service (443, 3389).",
    "RDP": "Le bureau à distance Windows (port 3389). À ne jamais ouvrir directement sur Internet.",
    "Groupe de pays": "Une liste de pays utilisée dans les règles pour autoriser ou bloquer un trafic selon son origine.",
    "Coffre-fort": "Un logiciel qui range les mots de passe de façon chiffrée (ex. KeePass, Bitwarden).",
}


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn").strip()


def chercher(mot: str) -> list[tuple[str, str]]:
    """Termes dont le nom contient le mot cherché (sans tenir compte des accents ni des majuscules)."""
    m = _norm(mot)
    if not m:
        return sorted(TERMES.items())
    exacts = [(k, v) for k, v in TERMES.items() if _norm(k) == m]
    return exacts or [(k, v) for k, v in TERMES.items() if m in _norm(k) or m in _norm(v)][:8]
