"""Structure du fichier Excel client : onglets, colonnes, aides et valeurs autorisées."""
from __future__ import annotations

OUI_NON = ["Oui", "Non"]
DEMANDER = "*demander*"   # valeur d'un mot de passe à demander au lancement

# ----------------------------------------------------------------------------- onglet Général
# (paramètre, valeur par défaut, aide, valeurs autorisées, secret)
# Une ligne dont le paramètre commence par « ▸ » est un titre de section.
GENERAL: list[tuple[str, str, str, list[str] | None, bool]] = [
    ("▸ Identification", "", "", None, False),
    ("Nom du client", "", "Sert aux noms des rapports et des sauvegardes", None, False),
    ("Nom d'hôte du pare-feu", "", "Ex. fw-dupont (vide = ne pas modifier)", None, False),

    ("▸ Connexion au pare-feu (pour le script)", "", "", None, False),
    ("Adresse IP du pare-feu", "172.16.16.16", "IP utilisée pour joindre le boîtier (d'usine : 172.16.16.16 sur Port1)", None, False),
    ("Port d'administration", "4444", "4444 par défaut", None, False),
    ("Utilisateur admin", "admin", "Son mot de passe est demandé au lancement, il n'est jamais enregistré", None, False),

    ("▸ Heure et DNS", "", "", None, False),
    ("Fuseau horaire", "Europe/Paris", "Ex. Europe/Paris, Europe/Brussels, America/Montreal (vide = ne pas modifier)", None, False),
    ("Serveurs NTP", "", "Serveurs de temps séparés par ; (vide = serveurs Sophos)", None, False),
    ("DNS 1", "", "Serveur DNS utilisé par le pare-feu (vide = ne pas modifier)", None, False),
    ("DNS 2", "", "", None, False),
    ("DNS 3", "", "", None, False),

    ("▸ Alertes par e-mail", "", "", None, False),
    ("Serveur SMTP", "", "Ex. smtp.office365.com (vide = ne pas configurer les alertes)", None, False),
    ("Port SMTP", "587", "25, 465 ou 587", None, False),
    ("Sécurité SMTP", "STARTTLS", "Aucune, STARTTLS ou SSL/TLS", ["Aucune", "STARTTLS", "SSL/TLS"], False),
    ("Utilisateur SMTP", "", "Vide = serveur sans authentification", None, False),
    ("Mot de passe SMTP", DEMANDER, "Laissez *demander* pour le saisir au lancement", None, True),
    ("Adresse expéditeur", "", "Ex. firewall@client.fr", None, False),
    ("Destinataire des alertes", "", "Ex. support@votre-societe.fr", None, False),

    ("▸ Sauvegarde automatique", "", "", None, False),
    ("Fréquence de sauvegarde", "Jamais", "Jamais, Quotidienne, Hebdomadaire ou Mensuelle",
     ["Jamais", "Quotidienne", "Hebdomadaire", "Mensuelle"], False),
    ("Destination de la sauvegarde", "E-mail", "E-mail, FTP ou Locale (sur le boîtier)", ["E-mail", "FTP", "Locale"], False),
    ("E-mail de sauvegarde", "", "Adresse qui reçoit les sauvegardes (destination E-mail)", None, False),
    ("Serveur FTP", "", "Destination FTP uniquement", None, False),
    ("Utilisateur FTP", "", "", None, False),
    ("Mot de passe FTP", DEMANDER, "", None, True),
    ("Dossier FTP", "/", "", None, False),
    ("Mot de passe de chiffrement de la sauvegarde", DEMANDER, "Indispensable pour restaurer : notez-le dans votre coffre-fort", None, True),

    ("▸ Supervision SNMP", "", "", None, False),
    ("SNMP activé", "Non", "Oui pour être supervisé (PRTG, Centreon, Zabbix...)", OUI_NON, False),
    ("Communauté SNMP", "", "Ex. supervision-dupont (évitez « public »)", None, False),
    ("IP du serveur de supervision", "", "", None, False),
    ("Lieu", "", "Ex. Baie informatique, siège Lyon", None, False),
    ("Contact", "", "Ex. support@votre-societe.fr", None, False),

    ("▸ VPN télétravail (SSL VPN)", "", "", None, False),
    ("VPN télétravail activé", "Non", "Les utilisateurs autorisés se cochent dans l'onglet Comptes", OUI_NON, False),
    ("Adresse publique du pare-feu", "", "IP publique ou nom DNS que les télétravailleurs utilisent pour se connecter", None, False),
    ("Protocole VPN", "UDP", "UDP (recommandé) ou TCP", ["UDP", "TCP"], False),
    ("Port VPN", "8443", "8443 par défaut", None, False),
    ("Début plage VPN", "10.81.234.5", "Adresses données aux postes en VPN (réseau inutilisé ailleurs)", None, False),
    ("Fin plage VPN", "10.81.234.55", "", None, False),
    ("Masque plage VPN", "255.255.255.0", "", None, False),
    ("DNS pour les clients VPN", "", "En général l'IP du serveur AD (vide = pare-feu)", None, False),
    ("Domaine pour les clients VPN", "", "Ex. dupont.local", None, False),
    ("Réseaux accessibles en VPN", "", "Objets ou réseaux (ex. 192.168.1.0/24) séparés par ;", None, False),

    ("▸ Active Directory", "", "", None, False),
    ("AD : adresse IP", "", "IP du contrôleur de domaine (vide = pas d'AD)", None, False),
    ("AD : domaine", "", "Ex. dupont.local", None, False),
    ("AD : nom NetBIOS", "", "Ex. DUPONT", None, False),
    ("AD : compte de service", "", "Compte qui lit l'annuaire, ex. svc-firewall", None, False),
    ("AD : mot de passe", DEMANDER, "", None, True),
    ("AD : port", "389", "389 (ou 636 en LDAPS)", None, False),

    ("▸ Sophos Central", "", "", None, False),
    ("Inscrire dans Sophos Central", "Non", "Oui = le script inscrit le boîtier dans Central (inutile en Zero Touch)", OUI_NON, False),
    ("Central : e-mail du compte", "", "Compte administrateur Sophos Central du client", None, False),
    ("Central : mot de passe", DEMANDER, "Si la double authentification bloque, inscrivez le boîtier à la main", None, True),
    ("Central : sauvegardes", "Oui", "Envoyer les sauvegardes de configuration dans Central", OUI_NON, False),

    ("▸ Deuxième accès Internet", "", "", None, False),
    ("Port WAN de secours", "", "Port du lien de secours (vide = pas de secours ; deux liens WAN sans secours = répartition de charge)", None, False),
    ("Passerelle de secours", "", "Nom de la passerelle du lien de secours (Routage > Passerelles). Vide = automatique", None, False),
]

PARAMS_SECRETS = {p for p, _, _, _, s in GENERAL if s}

# ----------------------------------------------------------------------------- onglets tableaux
# (en-tête, aide, valeurs autorisées) ; les colonnes listées dans SECRETS sont des mots de passe
ONGLETS: dict[str, list[tuple[str, str, list[str] | None]]] = {
    "Interfaces": [
        ("Actif", "Oui pour appliquer la ligne, Non pour l'ignorer", OUI_NON),
        ("Port", "Port physique : Port1, Port2... (étiquette sur la face avant)", None),
        ("Zone", "WAN pour Internet, LAN pour le réseau local, DMZ...", None),
        ("Mode", "Statique (IP fixe), DHCP (IP donnée par la box) ou PPPoE (identifiant opérateur)",
         ["Statique", "DHCP", "PPPoE"]),
        ("Adresse IP", "IP du pare-feu sur ce port (mode Statique)", None),
        ("Masque", "Ex. 255.255.255.0 ou /24", None),
        ("Passerelle", "WAN en Statique : IP de la box / du routeur opérateur", None),
        ("Utilisateur PPPoE", "Identifiant fourni par l'opérateur", None),
        ("Mot de passe PPPoE", "Laissez *demander* pour le saisir au lancement", None),
        ("Description", "Texte libre", None),
    ],
    "Zones": [
        ("Actif", "Oui / Non", OUI_NON),
        ("Nom", "Nom de la zone (ex. SERVEURS). Les zones LAN/WAN/DMZ/VPN/WiFi existent déjà.", None),
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
        ("ID VLAN", "Numéro de VLAN (1-4094), le même que sur le switch", None),
        ("Zone", "Zone du VLAN (LAN, DMZ ou une zone de l'onglet Zones)", None),
        ("Adresse IP", "IP du pare-feu dans ce VLAN (ex. 192.168.10.254)", None),
        ("Masque", "Ex. 255.255.255.0 ou /24", None),
        ("Description", "Texte libre (pour mémoire)", None),
    ],
    "Routes": [
        ("Actif", "Oui / Non", OUI_NON),
        ("Réseau de destination", "Ex. 10.20.0.0/16", None),
        ("Passerelle", "IP du routeur qui mène à ce réseau", None),
        ("Interface", "Port par lequel on joint la passerelle (ex. Port1)", None),
        ("Description", "Texte libre", None),
    ],
    "Wi-Fi": [
        ("Actif", "Oui / Non", OUI_NON),
        ("Nom", "Nom du réseau dans le pare-feu (ex. WIFI-INVITES)", None),
        ("SSID", "Nom visible sur les téléphones", None),
        ("Clé Wi-Fi", "8 caractères minimum ; *demander* pour la saisir au lancement", None),
        ("Mode", "Zone séparée (réseau à part, ex. invités) ou Pont vers le LAN (même réseau que les PC)",
         ["Zone séparée", "Pont vers le LAN"]),
        ("Zone", "Zone séparée uniquement : WiFi par défaut", None),
        ("Adresse IP", "Zone séparée uniquement : IP du pare-feu sur ce Wi-Fi", None),
        ("Masque", "Zone séparée uniquement", None),
        ("Isolation des clients", "Les appareils ne se voient pas entre eux (conseillé pour les invités)", OUI_NON),
        ("SSID masqué", "Réseau invisible dans la liste", OUI_NON),
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
        ("Description", "Texte libre (pour mémoire)", None),
    ],
    "DHCP": [
        ("Actif", "Oui / Non", OUI_NON),
        ("Nom", "Ex. DHCP-LAN", None),
        ("Interface", "Port ou VLAN qui distribue les adresses (ex. Port1 ou Port1.10)", None),
        ("Début de plage", "Première IP distribuée", None),
        ("Fin de plage", "Dernière IP distribuée", None),
        ("Masque", "Ex. 255.255.255.0 ou /24", None),
        ("Passerelle", "En général l'IP du pare-feu sur ce réseau", None),
        ("DNS 1", "Vide = le pare-feu sert de DNS. Avec un AD : IP du serveur AD", None),
        ("DNS 2", "", None),
        ("Domaine", "Ex. dupont.local", None),
        ("Durée du bail (minutes)", "1440 = 1 jour", None),
    ],
    "Réservations DHCP": [
        ("Actif", "Oui / Non", OUI_NON),
        ("Serveur DHCP", "Nom du serveur DHCP (onglet DHCP)", None),
        ("Nom de l'appareil", "Ex. IMPRIMANTE-ACCUEIL", None),
        ("Adresse MAC", "Ex. 00:11:22:33:44:55", None),
        ("Adresse IP", "IP toujours donnée à cet appareil", None),
    ],
    "Comptes": [
        ("Actif", "Oui / Non", OUI_NON),
        ("Identifiant", "Nom de connexion (ex. jdupont)", None),
        ("Nom complet", "Ex. Jean Dupont", None),
        ("Type", "Administrateur (gère le pare-feu) ou Utilisateur (VPN...)", ["Administrateur", "Utilisateur"]),
        ("E-mail", "Facultatif", None),
        ("Mot de passe", "*demander* pour le saisir au lancement", None),
        ("VPN télétravail", "Autoriser ce compte à se connecter en VPN", OUI_NON),
        ("Profil admin", "Administrateurs : Administrator (tous droits), Audit Admin (lecture)...", None),
    ],
    "VPN sites": [
        ("Actif", "Oui / Non", OUI_NON),
        ("Nom", "Ex. VPN-AGENCE-LYON", None),
        ("Port WAN", "Port Internet local utilisé (ex. Port2)", None),
        ("Adresse du site distant", "IP publique ou nom DNS du pare-feu d'en face", None),
        ("Réseaux locaux", "Réseaux d'ici à partager (ex. 192.168.1.0/24) séparés par ;", None),
        ("Réseaux distants", "Réseaux de l'autre site (ex. 192.168.2.0/24) séparés par ;", None),
        ("Clé partagée", "Même clé des deux côtés ; *demander* pour la saisir au lancement", None),
        ("Profil IPsec", "Profil de chiffrement identique des deux côtés (ex. IKEv2)", None),
        ("Rôle", "Initier (ce pare-feu appelle) ou Répondre (il attend l'appel)", ["Initier", "Répondre"]),
    ],
    "Redirections": [
        ("Actif", "Oui / Non", OUI_NON),
        ("Nom", "Ex. ACCES-NVR-CAMERAS", None),
        ("Port WAN", "Port Internet qui reçoit les connexions (ex. Port2)", None),
        ("Service externe", "Service ou port vu d'Internet : HTTPS, « TCP 8443 », « UDP 1194 »", None),
        ("Serveur interne", "IP (ou nom d'objet) du serveur interne", None),
        ("Port interne", "Port sur le serveur, si différent (ex. 443) ; vide = identique", None),
        ("Zone du serveur", "LAN, DMZ...", None),
        ("Sources autorisées", "IP/réseaux autorisés à se connecter ; vide = tout Internet", None),
    ],
    "Règles": [
        ("Actif", "Oui / Non", OUI_NON),
        ("Nom", "Nom de la règle. Les règles sont créées dans l'ordre du tableau.", None),
        ("Action", "Accepter, Bloquer (drop silencieux) ou Rejeter", ["Accepter", "Bloquer", "Rejeter"]),
        ("Zones source", "Ex. LAN ; plusieurs séparées par ; ; vide = toutes", None),
        ("Réseaux source", "Objets ou adresses (192.168.1.0/24) ; vide = tous", None),
        ("Zones destination", "Ex. WAN ; vide = toutes", None),
        ("Réseaux destination", "Objets ou adresses ; vide = tous", None),
        ("Services", "Ex. HTTP;HTTPS;DNS ou « TCP 8080 » ; vide = tous", None),
        ("Journaliser", "Enregistrer le trafic dans les journaux", OUI_NON),
        ("Filtrage web", "Nom de la stratégie web (ex. Default Workplace Policy) ; vide = aucune", None),
        ("Contrôle d'applications", "Nom de la stratégie (ex. Block generally unwanted apps) ; vide = aucune", None),
        ("IPS", "Nom de la stratégie IPS (ex. lantowan_general) ; vide = aucune", None),
        ("Antivirus", "Analyser les téléchargements (HTTP/HTTPS/FTP)", OUI_NON),
        ("Description", "Texte libre", None),
    ],
}

SECRETS = {
    ("Interfaces", "Mot de passe PPPoE"),
    ("Wi-Fi", "Clé Wi-Fi"),
    ("Comptes", "Mot de passe"),
    ("VPN sites", "Clé partagée"),
}

# Objets présents d'origine sur un XGS (non exhaustif) : pas d'avertissement s'ils sont référencés.
ZONES_ORIGINE = {"LAN", "WAN", "DMZ", "VPN", "WiFi", "LOCAL"}
SERVICES_ORIGINE = {"HTTP", "HTTPS", "DNS", "NTP", "SMTP", "SMTPS", "POP3", "POP3S", "IMAP", "IMAPS", "FTP", "SSH"}
