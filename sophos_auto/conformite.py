"""Vérifier qu'un pare-feu correspond toujours à son fichier client (lecture seule).

    python -m sophos_auto.conformite clients/dupont.xlsx --ip 192.168.1.254

Utile après une intervention de quelqu'un d'autre, ou plusieurs mois plus tard :
indique ce qui manque sur le pare-feu et ce qui a été modifié depuis.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .api import ErreurAPI, SophosAPI
from .deployer import _remplacer
from .modele import Operation, Secret, lire_classeur
from .restaurer import cle

VERT, ROUGE, JAUNE, FIN = "\033[32m", "\033[31m", "\033[33m", "\033[0m"
# Champs dont la valeur affichée par le pare-feu peut différer de ce qu'on envoie (sans être une erreur)
IGNORES = {"Password", "Key", "PresharedKey", "EncryptionPassword", "Position", "Description", "@transactionid",
           "Status", "InterfaceStatus"}


@dataclass
class Ecart:
    op: Operation
    type: str            # absent | différent
    details: list[str]


def _norm(v) -> str:
    return str(v).strip().lower()


def _comparer(attendu, actuel, chemin="") -> list[str]:
    """Liste les champs attendus dont la valeur diffère sur le pare-feu (champs en plus ignorés)."""
    diffs = []
    if isinstance(attendu, Secret):
        return diffs
    if isinstance(attendu, dict):
        if not isinstance(actuel, dict):
            return [f"{chemin or 'objet'} : attendu {attendu}, trouvé {actuel}"]
        for k, v in attendu.items():
            if k in IGNORES:
                continue
            diffs += _comparer(v, actuel.get(k), f"{chemin}/{k}" if chemin else k)
        return diffs
    if isinstance(attendu, list):
        actuel_l = actuel if isinstance(actuel, list) else ([] if actuel is None else [actuel])
        if all(not isinstance(x, (dict, list)) for x in attendu):
            if sorted(map(_norm, attendu)) != sorted(map(_norm, actuel_l)):
                return [f"{chemin} : attendu {', '.join(map(str, attendu))} ; trouvé {', '.join(map(str, actuel_l)) or 'rien'}"]
            return []
        for i, x in enumerate(attendu):
            diffs += _comparer(x, actuel_l[i] if i < len(actuel_l) else None, f"{chemin}[{i + 1}]")
        return diffs
    if actuel is None:
        return [f"{chemin} : attendu « {attendu} », absent"]
    if _norm(attendu) != _norm(actuel) and not (isinstance(actuel, (dict, list))):
        return [f"{chemin} : attendu « {attendu} », trouvé « {actuel} »"]
    return []


def verifier(api: SophosAPI, fichier: str) -> tuple[list[Ecart], int]:
    cfg = lire_classeur(fichier)
    if cfg.erreurs:
        raise ValueError("Le fichier contient des erreurs : " + " ; ".join(cfg.erreurs[:3]))
    cache: dict[str, dict] = {}
    ecarts, verifies = [], 0
    for o in cfg.operations:
        if o.mode == "maj" or o.existe_ok:
            continue
        if o.balise not in cache:
            try:
                lu = api.lire(o.balise)
            except ErreurAPI:
                lu = None
            elements = lu if isinstance(lu, list) else ([lu] if lu else [])
            cache[o.balise] = {cle(o.balise, e): e for e in elements if isinstance(e, dict)}
        attendu = _remplacer(o.contenu, masquer=True)
        if o.sous_liste:
            racine = next(iter(cache[o.balise].values()), {}) or {}
            elements = racine.get(o.sous_liste)
            elements = elements if isinstance(elements, list) else [elements]
            actuel = next((e for e in elements if isinstance(e, dict) and e.get(o.champ_cle) == o.cle), None)
        else:
            nom = o.cle if o.mode == "patch" and o.cle else cle(o.balise, attendu)
            actuel = cache[o.balise].get(nom) if nom else (next(iter(cache[o.balise].values()), None))
        verifies += 1
        if actuel is None:
            ecarts.append(Ecart(o, "absent", []))
            continue
        d = _comparer(attendu, actuel)
        if d:
            ecarts.append(Ecart(o, "différent", d))
    return ecarts, verifies


def afficher(ecarts: list[Ecart], verifies: int) -> None:
    if not ecarts:
        print(f"{VERT}✔ Conforme : les {verifies} éléments du fichier sont présents et identiques sur le pare-feu.{FIN}")
        return
    for e in ecarts:
        if e.type == "absent":
            print(f"{ROUGE}  ✘ Absent du pare-feu : {e.op.libelle}{FIN}")
        else:
            print(f"{JAUNE}  ≠ Modifié : {e.op.libelle}{FIN}")
            for d in e.details[:6]:
                print(f"      {d}")
    print(f"\n{len(ecarts)} écart(s) sur {verifies} éléments vérifiés. Pour remettre le pare-feu en conformité, "
          f"ré-appliquez le fichier (les objets existants sont mis à jour).")


def rapport_html(ecarts: list[Ecart], verifies: int, client: str, cible: str) -> str:
    import datetime as dt
    import html as h
    lignes = "".join(
        f"<tr><td style='color:{'#c0392b' if e.type == 'absent' else '#d68910'};font-weight:bold'>{e.type}</td>"
        f"<td>{h.escape(e.op.libelle)}</td><td>{'<br>'.join(h.escape(d) for d in e.details[:8])}</td></tr>"
        for e in ecarts)
    etat = (f"<p style='color:#1e8449'><b>Conforme</b> : les {verifies} éléments du fichier sont présents et identiques.</p>"
            if not ecarts else f"<p><b>{len(ecarts)}</b> écart(s) sur {verifies} éléments vérifiés.</p>")
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Conformité du pare-feu</title><style>body{{font-family:Segoe UI,Arial,sans-serif;max-width:960px;margin:24px auto;padding:0 16px;background:#fff;color:#222}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #eee;padding:6px;text-align:left;vertical-align:top}}</style></head>
<body><h1>Conformité du pare-feu</h1><p style="color:#666">{h.escape(client)} — {h.escape(cible)} — {dt.datetime.now():%d/%m/%Y %H:%M}</p>
{etat}{"<table><tr><th>Écart</th><th>Élément</th><th>Détail</th></tr>" + lignes + "</table>" if ecarts else ""}</body></html>"""


def enregistrer_rapport(ecarts, verifies, client, cible) -> "Path":
    import datetime as dt
    import re
    from pathlib import Path
    Path("rapports").mkdir(exist_ok=True)
    f = Path("rapports") / f"conformite_{re.sub(r'[^A-Za-z0-9_-]', '_', client)}_{dt.datetime.now():%Y-%m-%d_%H%M}.html"
    f.write_text(rapport_html(ecarts, verifies, client, cible), encoding="utf-8")
    from . import historique
    historique.enregistrer(client, "conformite", "conforme" if not ecarts else f"{len(ecarts)} écart(s)",
                           ecarts=len(ecarts), verifies=verifies, pare_feu=cible, rapport=f)
    return f


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Compare un pare-feu à son fichier client (lecture seule).")
    p.add_argument("fichier")
    p.add_argument("--ip")
    p.add_argument("--port", type=int, default=4444)
    p.add_argument("--utilisateur", default="admin")
    a = p.parse_args(argv)
    ip = a.ip or lire_classeur(a.fichier).general["Adresse IP du pare-feu"]
    mdp = os.environ.get("SOPHOS_MOT_DE_PASSE") or getpass.getpass(f"Mot de passe de « {a.utilisateur} » : ")
    try:
        ecarts, n = verifier(SophosAPI(ip, a.utilisateur, mdp, port=a.port), a.fichier)
    except (ErreurAPI, ValueError) as exc:
        print(f"{ROUGE}✘ {exc}{FIN}")
        return 1
    afficher(ecarts, n)
    client = lire_classeur(a.fichier).general.get("Nom du client") or a.fichier
    print(f"Rapport : {enregistrer_rapport(ecarts, n, client, ip)}")
    return 0 if not ecarts else 2


if __name__ == "__main__":
    sys.exit(main())
