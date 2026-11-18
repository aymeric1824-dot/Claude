"""Dossier technique du client (page HTML) à partir de son fichier Excel.

    python -m sophos_auto.documentation clients/dupont.xlsx

La page est faite pour être remise au client ou rangée dans son dossier :
réseaux, VLAN, DHCP, règles, VPN, comptes... Aucun mot de passe n'y figure.
"""
from __future__ import annotations

import datetime as dt
import html
import sys
from pathlib import Path

from openpyxl import load_workbook

from .modele import lire_classeur
from .parametres import charger
from .schema import GENERAL, ONGLETS, SECRETS

TITRES = {
    "Interfaces": "Interfaces (Internet et réseau local)", "Zones": "Zones", "VLAN": "VLAN", "Routes": "Routes",
    "Wi-Fi": "Wi-Fi", "Hôtes": "Équipements et réseaux déclarés", "Groupes": "Groupes", "Services": "Services",
    "DHCP": "Distribution des adresses (DHCP)", "Réservations DHCP": "Adresses réservées",
    "Comptes": "Comptes", "VPN sites": "VPN entre sites", "Redirections": "Accès depuis Internet",
    "Règles": "Règles de pare-feu",
}
SECTIONS_GENERAL = {"▸ Heure et DNS", "▸ Alertes par e-mail", "▸ Sauvegarde automatique", "▸ Supervision SNMP",
                    "▸ VPN télétravail (SSL VPN)", "▸ Active Directory", "▸ Sophos Central", "▸ Deuxième accès Internet"}


def _v(x) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    return str(x)


def generer(fichier: str, destination: str | None = None) -> Path:
    wb = load_workbook(fichier, data_only=True)
    cfg = lire_classeur(fichier)
    g = cfg.general
    client = g.get("Nom du client") or Path(fichier).stem
    parties = []

    # Paramètres généraux par section (mots de passe masqués, valeurs vides ignorées)
    secrets_generaux = {p for p, _, _, _, s in GENERAL if s}
    section, lignes = None, []
    for param, *_ in GENERAL:
        if param.startswith("▸"):
            if section and lignes and section in SECTIONS_GENERAL:
                parties.append(f"<h3>{html.escape(section[2:])}</h3><table>{''.join(lignes)}</table>")
            section, lignes = param, []
            continue
        val = g.get(param, "")
        if not val or val in ("Non", "Jamais"):
            continue
        if param in secrets_generaux:
            val = "(dans le coffre-fort)"
        lignes.append(f"<tr><th>{html.escape(param)}</th><td>{html.escape(val)}</td></tr>")
    if section and lignes and section in SECTIONS_GENERAL:
        parties.append(f"<h3>{html.escape(section[2:])}</h3><table>{''.join(lignes)}</table>")

    # Onglets tableaux
    for onglet, colonnes in ONGLETS.items():
        if onglet not in wb.sheetnames:
            continue
        ws = wb[onglet]
        entetes = [_v(c.value) for c in ws[1]]
        visibles = [c for c, _, _ in colonnes if c != "Actif" and c in entetes]
        rangs = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            d = {entetes[i]: row[i] for i in range(min(len(entetes), len(row)))}
            if not any(_v(v) for k, v in d.items() if k != "Actif") or _v(d.get("Actif")).lower() == "non":
                continue
            cellules = []
            for c in visibles:
                val = _v(d.get(c))
                if (onglet, c) in SECRETS and val:
                    val = "(dans le coffre-fort)"
                cellules.append(val)
            rangs.append(cellules)
        if rangs:
            # on n'affiche que les colonnes utilisées
            utilisees = [i for i in range(len(visibles)) if any(r[i] for r in rangs)]
            tete = "".join(f"<th>{html.escape(visibles[i])}</th>" for i in utilisees)
            corps = "".join("<tr>" + "".join(f"<td>{html.escape(r[i])}</td>" for i in utilisees) + "</tr>" for r in rangs)
            parties.append(f"<h2>{html.escape(TITRES.get(onglet, onglet))}</h2><table class='l'><tr>{tete}</tr>{corps}</table>")

    p = charger()
    societe = p.get("societe", "")
    page = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dossier pare-feu</title><style>
body{{font-family:Segoe UI,Arial,sans-serif;max-width:1000px;margin:24px auto;padding:0 16px;color:#222;background:#fff}}
h1{{margin-bottom:4px}} h2{{border-bottom:2px solid #1f4e78;padding-bottom:4px;margin-top:32px;color:#1f4e78}}
table{{border-collapse:collapse;margin:8px 0;width:100%}} th,td{{text-align:left;padding:5px 8px;border-bottom:1px solid #e5e5e5;vertical-align:top}}
table.l th{{background:#f0f4f8}} table:not(.l) th{{width:40%;color:#555;font-weight:normal}} .s{{color:#666}}
@media print{{h2{{page-break-after:avoid}}}}
</style></head><body><h1>Dossier technique du pare-feu</h1>
<p class="s">{html.escape(client)} — pare-feu {html.escape(g.get("Nom d'hôte du pare-feu", ""))} — {dt.date.today():%d/%m/%Y}
{(" — " + html.escape(societe)) if societe else ""}</p>
<h2>Paramètres généraux</h2>{''.join(x for x in parties if x.startswith("<h3>"))}
{''.join(x for x in parties if not x.startswith("<h3>"))}
<p class="s">Les mots de passe ne figurent jamais dans ce document.</p></body></html>"""
    sortie = Path(destination) if destination else Path(fichier).with_name(Path(fichier).stem + "_dossier.html")
    sortie.write_text(page, encoding="utf-8")
    return sortie


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage : python -m sophos_auto.documentation clients/<client>.xlsx")
        sys.exit(1)
    print("Dossier créé :", generer(sys.argv[1]))
