"""Tableau de bord de tous les clients : qui va bien, qui a besoin d'une intervention.

Construit à partir de l'historique des interventions et des rappels (aucune connexion aux pare-feux).
Un voyant par client : vert = rien à faire, orange = à prévoir, rouge = important.
"""
from __future__ import annotations

import datetime as dt
import html
from dataclasses import dataclass, field
from pathlib import Path

from . import historique
from .rappels import calculer


@dataclass
class LigneClient:
    client: str
    etat: str                      # vert | orange | rouge
    derniere: str = ""             # dernière intervention (texte)
    date: str = ""
    note: int | None = None        # dernière note de sécurité
    firmware: str = ""
    rappels: list[str] = field(default_factory=list)


def lignes(maintenant: dt.datetime | None = None) -> list[LigneClient]:
    rappels = calculer(maintenant)
    par_client: dict[str, list[dict]] = {}
    for e in historique.lire():
        par_client.setdefault(e.get("client", ""), []).append(e)
    res = []
    for client, entrees in par_client.items():
        if not client:
            continue
        derniere = entrees[-1]
        audits = [e for e in entrees if e.get("action") == "audit"]
        sauvegardes = [e for e in entrees if e.get("action") == "sauvegarde_central" and e.get("firmware")]
        siens = [r for r in rappels if r.client == client]
        etat = "rouge" if any(r.urgence == 1 for r in siens) else ("orange" if siens else "vert")
        res.append(LigneClient(
            client=client, etat=etat, derniere=historique.LIBELLES.get(derniere.get("action"), derniere.get("action", "")),
            date=derniere.get("date", "")[:10], note=audits[-1].get("note") if audits else None,
            firmware=str(sauvegardes[-1].get("firmware", "")) if sauvegardes else "",
            rappels=[r.texte for r in siens]))
    ordre = {"rouge": 0, "orange": 1, "vert": 2}
    return sorted(res, key=lambda l: (ordre[l.etat], l.client.lower()))


def page(destination: str | Path | None = None) -> Path:
    f = Path(destination) if destination else Path("rapports") / "tableau_de_bord.html"
    f.parent.mkdir(parents=True, exist_ok=True)
    e = html.escape
    couleurs = {"rouge": "#d1242f", "orange": "#c98a00", "vert": "#1f7a37"}
    rangs = "".join(
        f'<tr><td><span class="v" style="background:{couleurs[l.etat]}"></span>{e(l.client)}</td><td>{e(l.date)}</td>'
        f'<td>{e(l.derniere)}</td><td>{"" if l.note is None else f"{l.note}/100"}</td><td>{e(l.firmware)}</td>'
        f'<td>{"<br>".join(e(r) for r in l.rappels) or "—"}</td></tr>' for l in lignes())
    f.write_text(f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Tableau de bord des clients</title>
<style>body{{font-family:'Segoe UI',Arial,sans-serif;background:#ececef;color:#1d1d22;margin:0}}main{{max-width:1100px;margin:0 auto;padding:24px 16px}}
h1{{border-bottom:3px solid #E10600;padding-bottom:10px}}table{{border-collapse:collapse;width:100%;background:#fff}}th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid #e2e2e6;vertical-align:top}}
th{{font-size:12px;text-transform:uppercase;color:#5c5c66}}.v{{display:inline-block;width:10px;height:10px;border-radius:5px;margin-right:8px}}</style></head>
<body><main><h1>Tableau de bord des clients</h1><p>Mis à jour le {dt.datetime.now():%d/%m/%Y à %H:%M}.</p>
<table><tr><th>Client</th><th>Dernière intervention</th><th></th><th>Note sécurité</th><th>Firmware</th><th>À faire</th></tr>{rangs}</table>
</main></body></html>""", encoding="utf-8")
    return f
