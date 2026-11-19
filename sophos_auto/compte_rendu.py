"""Compte rendu d'intervention à faire signer par le client, sur l'écran du PC (souris ou doigt).

Le compte rendu reprend ce qui a été fait (historique du jour, fiche de configuration) et ce qu'il reste à faire.
La signature est dessinée dans la fenêtre ; elle est enregistrée sous forme de tracé dans la page, puis le tout
est converti en PDF et rangé dans le dossier du client.
"""
from __future__ import annotations

import datetime as dt
import html
import json
from pathlib import Path

from . import historique
from .parametres import charger as charger_parametres


def _fiche(client: str) -> tuple[list[str], list[str]]:
    """(ce qui est configuré, à faire à la main) d'après la fiche de l'assistant, si elle existe."""
    slug = historique._slug(client)
    for f in sorted(Path("clients").glob("*_fiche.txt")) if Path("clients").exists() else []:
        if historique._slug(f.stem.removesuffix("_fiche")) != slug:
            continue
        fait, a_faire, partie = [], [], None
        for ligne in f.read_text(encoding="utf-8").splitlines():
            if ligne.startswith("Ce qui est configuré"):
                partie = fait
            elif ligne.startswith("À faire à la main"):
                partie = a_faire
            elif ligne and not ligne.startswith(" "):
                partie = None
            elif partie is not None and ligne.strip():
                partie.append(ligne.strip().lstrip("-").strip())
        return fait, a_faire
    return [], []


def tracer(traits: list, largeur: int = 520, hauteur: int = 170) -> str:
    """Signature (liste de traits, chacun une liste de points [x, y]) en image SVG."""
    lignes = []
    for t in traits or []:
        pts = " ".join(f"{float(x):.1f},{float(y):.1f}" for x, y in t if 0 <= float(x) <= largeur * 2)
        if pts:
            lignes.append(f'<polyline points="{pts}" fill="none" stroke="#1d1d22" stroke-width="2.4" '
                          f'stroke-linecap="round" stroke-linejoin="round"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largeur} {hauteur}" width="{largeur}" '
            f'height="{hauteur}">{"".join(lignes)}</svg>')


def generer(client: str, signataire: str = "", traits: list | None = None, remarques: str = "") -> Path:
    from .poste import charger as charger_poste
    e = html.escape
    societe = charger_parametres().get("societe", "")
    technicien = charger_poste().get("technicien", "")
    aujourd_hui = dt.date.today().isoformat()
    entrees = historique.lire(client)
    du_jour = [x for x in entrees if x.get("date", "").startswith(aujourd_hui)] or entrees[-5:]
    fait, a_faire = _fiche(client)
    interventions = "".join(f"<li>{e(historique.resume(x))}</li>" for x in du_jour) or "<li>—</li>"
    page = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Compte rendu — {e(client)}</title>
<style>body{{font-family:'Segoe UI',Arial,sans-serif;color:#1d1d22;margin:0;background:#fff}}main{{max-width:800px;margin:0 auto;padding:28px 24px}}
header{{border-bottom:3px solid #E10600;padding-bottom:10px;margin-bottom:14px}}h1{{font-size:24px;margin:4px 0}}h2{{font-size:13px;letter-spacing:.08em;
text-transform:uppercase;color:#E10600;margin:22px 0 6px}}li{{margin:3px 0}}.sig{{border:1px solid #c4c4cc;border-radius:6px;padding:8px;display:inline-block}}
.s{{color:#5c5c66}}</style></head><body><main><header><h1>Compte rendu d'intervention</h1>
<div class="s">{e(client)} — {dt.date.today():%d/%m/%Y}{(" — " + e(societe)) if societe else ""}{(" — technicien : " + e(technicien)) if technicien else ""}</div></header>
<h2>Interventions</h2><ul>{interventions}</ul>
{f"<h2>Ce qui est en place</h2><ul>{''.join(f'<li>{e(x)}</li>' for x in fait)}</ul>" if fait else ""}
{f"<h2>Reste à faire</h2><ul>{''.join(f'<li>{e(x)}</li>' for x in a_faire)}</ul>" if a_faire else ""}
{f"<h2>Remarques</h2><p>{e(remarques)}</p>" if remarques else ""}
<h2>Signature du client</h2><p>{e(signataire) or "—"}, le {dt.date.today():%d/%m/%Y}</p>
<div class="sig">{tracer(traits) if traits else '<span class="s">Non signé</span>'}</div>
</main></body></html>"""
    dossier = Path("clients") / "comptes_rendus"
    dossier.mkdir(parents=True, exist_ok=True)
    f = dossier / f"{historique._slug(client)}_{dt.datetime.now():%Y-%m-%d_%H%M}.html"
    f.write_text(page, encoding="utf-8")
    historique.enregistrer(client, "compte_rendu", "signé" if traits else "non signé", rapport=f, signataire=signataire)
    return f


def lire_traits(texte: str) -> list:
    try:
        traits = json.loads(texte or "[]")
        return traits if isinstance(traits, list) else []
    except ValueError:
        return []
