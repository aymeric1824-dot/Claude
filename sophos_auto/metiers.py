"""Modèles par métier : réglages conseillés et points de vigilance propres à chaque secteur.

Ces modèles ne changent que les choix proposés par défaut dans l'assistant et ajoutent des
conseils dans la fiche du client : toutes les questions restent posées.
"""
from __future__ import annotations

METIERS: dict[str, dict] = {
    "general": {
        "libelle": "Autre / généraliste",
        "vlans": [],
        "conseils": [],
    },
    "medical": {
        "libelle": "Santé (cabinet médical, dentaire, paramédical, laboratoire)",
        "vlans": ["SERVEURS", "INVITES"],
        "teletravail": False, "wifi_invites": True, "filtrage": True, "inspection": False, "pays": True,
        "conseils": [
            "Santé : données de santé = données sensibles (RGPD). Hébergez les dossiers patients chez un hébergeur "
            "certifié HDS et conservez les journaux du pare-feu au moins 1 an (Sophos Central ou serveur syslog).",
            "Santé : séparez le Wi-Fi de la salle d'attente du réseau du cabinet (Wi-Fi invités isolé).",
            "Santé : n'exposez jamais le logiciel médical ou le bureau à distance sur Internet ; utilisez le VPN.",
        ],
    },
    "comptable": {
        "libelle": "Expertise comptable, notaire, avocat, assurance",
        "vlans": ["SERVEURS"],
        "teletravail": True, "wifi_invites": True, "filtrage": True, "inspection": False, "pays": True, "otp": True,
        "conseils": [
            "Cabinet : activez la double authentification sur le VPN (pics de télétravail pendant les périodes fiscales).",
            "Cabinet : sauvegardez les dossiers clients hors site (sauvegarde externalisée chiffrée).",
            "Cabinet : bloquez les sites de partage de fichiers non autorisés (contrôle d'applications).",
        ],
    },
    "commerce": {
        "libelle": "Commerce, restaurant, hôtel (caisses, terminaux de paiement)",
        "vlans": ["CAISSES", "INVITES", "CAMERAS"],
        "teletravail": False, "wifi_invites": True, "filtrage": True, "inspection": False, "pays": True,
        "conseils": [
            "Commerce : placez caisses et terminaux de paiement dans un VLAN dédié, sans accès au Wi-Fi clients "
            "(exigence PCI-DSS des banques).",
            "Commerce : le Wi-Fi clients doit être totalement isolé et limité en débit.",
            "Commerce : les caméras ne doivent pas être joignables depuis Internet sans VPN.",
        ],
    },
    "ecole": {
        "libelle": "École, centre de formation, association accueillant des mineurs",
        "vlans": ["ELEVES", "SERVEURS"],
        "teletravail": False, "wifi_invites": True, "filtrage": True, "inspection": True, "pays": False,
        "conseils": [
            "Établissement scolaire : filtrage web strict obligatoire pour les mineurs ; choisissez une stratégie web "
            "adaptée (ex. « Default Education Policy » si elle existe) et conservez les journaux.",
            "Établissement scolaire : séparez le réseau des élèves de celui de l'administration.",
            "Inspection HTTPS : installez le certificat du pare-feu sur les postes, sinon les élèves verront des alertes.",
        ],
    },
    "industrie": {
        "libelle": "Industrie, atelier, BTP (machines, automates)",
        "vlans": ["AUTOMATES", "SERVEURS", "CAMERAS"],
        "teletravail": True, "wifi_invites": True, "filtrage": True, "inspection": False, "pays": True,
        "conseils": [
            "Industrie : isolez les automates et machines (VLAN AUTOMATES) : aucun accès Internet, aucun accès depuis "
            "les bureaux sauf postes de supervision.",
            "Industrie : la télémaintenance des machines passe par le VPN, avec un compte par prestataire et une plage "
            "horaire limitée ; jamais de redirection de port vers un automate.",
        ],
    },
}

# VLAN propres aux métiers, en plus de ceux de l'assistant :
# (nom, libellé, accès Internet, accessible depuis le LAN)
VLAN_METIERS = {
    "CAISSES": ("Caisses et terminaux de paiement", True, False),
    "ELEVES": ("Postes et Wi-Fi des élèves", True, False),
    "AUTOMATES": ("Automates, machines, supervision industrielle", False, False),
}
