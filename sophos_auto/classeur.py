"""Écriture du fichier Excel client (modèle vierge, exemple ou résultat de l'assistant)."""
from __future__ import annotations

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from .schema import GENERAL, ONGLETS

BLEU = PatternFill("solid", fgColor="1F4E78")
SECTION = PatternFill("solid", fgColor="D9E1F2")
JAUNE = PatternFill("solid", fgColor="FFF2CC")

AIDE = [
    "MODE D'EMPLOI",
    "",
    "Le plus simple : lancez l'assistant (assistant.bat ou « python -m sophos_auto.assistant »).",
    "Il pose les questions et remplit ce fichier pour vous.",
    "",
    "Pour remplir à la main :",
    "1. Faites une copie de ce fichier par client (ex. clients/dupont.xlsx).",
    "2. Remplissez l'onglet Général puis les onglets utiles. Un onglet vide est simplement ignoré.",
    "   Les lignes jaunes sont des exemples : modifiez-les, supprimez-les ou mettez « Non » dans la colonne Actif.",
    "3. Survolez un en-tête de colonne pour voir l'aide (petit triangle rouge).",
    "4. Les listes se séparent par un point-virgule : HTTP;HTTPS;DNS",
    "5. Partout où l'on attend un objet réseau, vous pouvez écrire directement une adresse :",
    "   192.168.1.10, 192.168.1.0/24 ou 192.168.1.10-192.168.1.20 (l'objet est créé automatiquement).",
    "   Pareil pour les services : « TCP 8443 », « UDP 1194 ».",
    "6. Mots de passe : laissez *demander* pour qu'ils soient demandés au lancement (rien n'est stocké).",
    "",
    "Vérifier sans rien envoyer :  python -m sophos_auto.deployer clients/dupont.xlsx --simulation",
    "Appliquer :                   python -m sophos_auto.deployer clients/dupont.xlsx",
    "",
    "Relancer est sans danger : un objet qui existe déjà est mis à jour au lieu d'être recréé.",
]


def ecrire_classeur(chemin: str, general: dict[str, str] | None = None,
                    lignes: dict[str, list[dict]] | None = None, surligner: bool = False) -> str:
    general, lignes = general or {}, lignes or {}
    wb = Workbook()
    aide = wb.active
    aide.title = "Aide"
    for i, ligne in enumerate(AIDE, start=1):
        aide.cell(i, 1, ligne).font = Font(bold=(i == 1), size=14 if i == 1 else 11)
    aide.column_dimensions["A"].width = 120

    g = wb.create_sheet("Général")
    for col, titre in enumerate(["Paramètre", "Valeur", "Aide"], start=1):
        c = g.cell(1, col, titre)
        c.font, c.fill = Font(bold=True, color="FFFFFF"), BLEU
    for i, (param, defaut, aide_txt, valeurs, _secret) in enumerate(GENERAL, start=2):
        if param.startswith("▸"):
            for col in (1, 2, 3):
                g.cell(i, col).fill = SECTION
            g.cell(i, 1, param).font = Font(bold=True)
            continue
        g.cell(i, 1, param).font = Font(bold=True)
        g.cell(i, 2, general.get(param, defaut))
        g.cell(i, 3, aide_txt).font = Font(italic=True, color="666666")
        if valeurs:
            dv = DataValidation(type="list", formula1='"' + ",".join(valeurs) + '"', allow_blank=True)
            g.add_data_validation(dv)
            dv.add(f"B{i}")
    g.column_dimensions["A"].width, g.column_dimensions["B"].width, g.column_dimensions["C"].width = 42, 32, 90

    for nom, colonnes in ONGLETS.items():
        ws = wb.create_sheet(nom)
        ws.freeze_panes = "A2"
        for col, (titre, aide_txt, valeurs) in enumerate(colonnes, start=1):
            c = ws.cell(1, col, titre)
            c.font, c.fill = Font(bold=True, color="FFFFFF"), BLEU
            c.alignment = Alignment(wrap_text=True, vertical="center")
            if aide_txt:
                c.comment = Comment(aide_txt, "Aide")
            lettre = c.column_letter
            ws.column_dimensions[lettre].width = 9 if titre == "Actif" else max(16, min(len(titre) + 4, 30))
            if valeurs:
                dv = DataValidation(type="list", formula1='"' + ",".join(valeurs) + '"', allow_blank=True)
                dv.error, dv.errorTitle = f"Valeurs possibles : {', '.join(valeurs)}", "Valeur non valide"
                ws.add_data_validation(dv)
                dv.add(f"{lettre}2:{lettre}500")
        for r, ligne in enumerate(lignes.get(nom, []), start=2):
            for col, (titre, _, _) in enumerate(colonnes, start=1):
                val = ligne.get(titre, "Oui" if titre == "Actif" else "")
                cell = ws.cell(r, col, val)
                if surligner:
                    cell.fill = JAUNE
    wb.save(chemin)
    return chemin
