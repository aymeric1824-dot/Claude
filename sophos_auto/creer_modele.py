"""Génère le fichier Excel modèle à remplir pour chaque client.

    python -m sophos_auto.creer_modele            -> modele_client.xlsx
    python -m sophos_auto.creer_modele mon.xlsx
"""
from __future__ import annotations

import sys

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from .modele import GENERAL, ONGLETS

# Exemples : une configuration « standard » de PME, à adapter.
EXEMPLES = {
    "Zones": [
        ["Oui", "SERVEURS", "LAN", "Serveurs internes", "Oui", "Non", "Non", "Oui"],
        ["Non", "INVITES", "DMZ", "Wi-Fi invités (exemple désactivé)", "Oui", "Non", "Non", "Oui"],
    ],
    "VLAN": [
        ["Oui", "Port1", 10, "SERVEURS", "192.168.10.254", "255.255.255.0"],
        ["Non", "Port1", 20, "INVITES", "192.168.20.254", "/24"],
    ],
    "Hôtes": [
        ["Oui", "RES-LAN", "Réseau", "172.16.16.0", "255.255.255.0", "Réseau utilisateurs"],
        ["Oui", "RES-SERVEURS", "Réseau", "192.168.10.0", "/24", "VLAN serveurs"],
        ["Oui", "SRV-AD-01", "IP", "192.168.10.10", "", "Contrôleur de domaine"],
        ["Oui", "SRV-FICHIERS", "IP", "192.168.10.20", "", ""],
        ["Oui", "PLAGE-IMPRIMANTES", "Plage", "172.16.16.200", "172.16.16.220", ""],
        ["Oui", "MAJ-EDITEUR", "FQDN", "update.editeur-metier.fr", "", "Mises à jour du logiciel métier"],
    ],
    "Groupes": [
        ["Oui", "GRP-SERVEURS-AD", "SRV-AD-01", "Serveurs Active Directory"],
    ],
    "Services": [
        ["Oui", "APP-METIER", "TCP", "8443;9000:9010", "Logiciel métier du client"],
        ["Oui", "RDP-TCP-UDP", "TCP+UDP", "3389", ""],
    ],
    "Règles": [
        ["Oui", "LAN vers Internet", "Accepter", "LAN", "RES-LAN", "WAN", "", "HTTP;HTTPS;DNS", "Oui", "Navigation"],
        ["Oui", "LAN vers Serveurs", "Accepter", "LAN", "RES-LAN", "SERVEURS", "RES-SERVEURS", "", "Oui", ""],
        ["Oui", "Serveurs vers Internet", "Accepter", "SERVEURS", "RES-SERVEURS", "WAN", "", "HTTP;HTTPS;DNS;NTP", "Oui", ""],
        ["Non", "Invités vers Internet", "Accepter", "INVITES", "", "WAN", "", "HTTP;HTTPS", "Non", "Exemple désactivé"],
    ],
}

ENTETE = PatternFill("solid", fgColor="1F4E78")
EXEMPLE = PatternFill("solid", fgColor="FFF2CC")

AIDE = [
    "MODE D'EMPLOI",
    "",
    "1. Faites une copie de ce fichier par client (ex. client_dupont.xlsx).",
    "2. Remplissez l'onglet Général, puis les autres onglets. Les lignes jaunes sont des exemples : modifiez-les,",
    "   supprimez-les ou mettez « Non » dans la colonne Actif.",
    "3. Survolez un en-tête de colonne pour voir l'aide (petit triangle rouge).",
    "4. Les listes (plusieurs zones, services...) se séparent par un point-virgule : HTTP;HTTPS;DNS",
    "5. Vérifiez d'abord sans toucher au pare-feu :   python -m sophos_auto.deployer client_dupont.xlsx --simulation",
    "6. Puis appliquez :                                 python -m sophos_auto.deployer client_dupont.xlsx",
    "",
    "Ordre d'application : nom d'hôte, zones, VLAN, hôtes, groupes, services, règles.",
    "Relancer le script est sans danger : un objet qui existe déjà est mis à jour au lieu d'être recréé.",
    "",
    "Noms qui existent d'origine sur un XGS (inutile de les créer) :",
    "  Zones : LAN, WAN, DMZ, VPN, WiFi",
    "  Services : par exemple HTTP, HTTPS, DNS, NTP (liste complète dans Hôtes et services > Services)",
]


def creer(chemin: str = "modele_client.xlsx") -> str:
    wb = Workbook()
    aide = wb.active
    aide.title = "Aide"
    for i, ligne in enumerate(AIDE, start=1):
        aide.cell(i, 1, ligne).font = Font(bold=(i == 1), size=14 if i == 1 else 11)
    aide.column_dimensions["A"].width = 120

    g = wb.create_sheet("Général")
    for col, titre in enumerate(["Paramètre", "Valeur", "Aide"], start=1):
        c = g.cell(1, col, titre)
        c.font, c.fill = Font(bold=True, color="FFFFFF"), ENTETE
    for i, (param, defaut, aide_txt) in enumerate(GENERAL, start=2):
        g.cell(i, 1, param).font = Font(bold=True)
        g.cell(i, 2, defaut)
        g.cell(i, 3, aide_txt).font = Font(italic=True, color="666666")
    g.column_dimensions["A"].width, g.column_dimensions["B"].width, g.column_dimensions["C"].width = 28, 30, 80

    for nom, colonnes in ONGLETS.items():
        ws = wb.create_sheet(nom)
        ws.freeze_panes = "A2"
        for col, (titre, aide_txt, valeurs) in enumerate(colonnes, start=1):
            c = ws.cell(1, col, titre)
            c.font, c.fill = Font(bold=True, color="FFFFFF"), ENTETE
            c.alignment = Alignment(wrap_text=True, vertical="center")
            c.comment = Comment(aide_txt, "Aide")
            lettre = c.column_letter
            ws.column_dimensions[lettre].width = 10 if titre == "Actif" else max(16, len(titre) + 4)
            if valeurs:
                dv = DataValidation(type="list", formula1='"' + ",".join(valeurs) + '"', allow_blank=True)
                dv.error, dv.errorTitle = f"Valeurs possibles : {', '.join(valeurs)}", "Valeur non valide"
                ws.add_data_validation(dv)
                dv.add(f"{lettre}2:{lettre}500")
        for r, ligne in enumerate(EXEMPLES.get(nom, []), start=2):
            for col, val in enumerate(ligne, start=1):
                ws.cell(r, col, val).fill = EXEMPLE
    wb.save(chemin)
    return chemin


if __name__ == "__main__":
    print("Modèle créé :", creer(sys.argv[1] if len(sys.argv) > 1 else "modele_client.xlsx"))
