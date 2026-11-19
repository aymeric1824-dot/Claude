"""Questionnaire à envoyer au client avant l'intervention, et profil de réponses de votre société.

1. « Créer le questionnaire » produit une page web autonome (aucun Internet nécessaire) que vous envoyez
   au client. Il la remplit dans son navigateur et clique sur « Enregistrer mes réponses » : un petit fichier
   .json est téléchargé, qu'il vous renvoie par e-mail.
2. « Importer les réponses » range ce fichier dans clients/questionnaires. Au lancement de l'assistant,
   ses réponses sont proposées d'avance.

Le profil de votre société garde vos choix habituels (filtrage, alertes, sauvegardes...) pour les proposer
aux clients suivants. Les informations propres à un client (noms, adresses, mots de passe) n'y vont jamais.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

from .metiers import METIERS

DOSSIER = Path("clients") / "questionnaires"
PROFIL = Path("profil_reponses.json")

# (question exacte de l'assistant, type, choix possibles, libellé pour le client, explication pour le client)
QUESTIONS = [
    ("Nom du client", "texte", None, "Nom de votre entreprise", ""),
    ("Quel est le secteur d'activité du client ?", "choix", [(k, v["libelle"]) for k, v in METIERS.items()],
     "Votre secteur d'activité", ""),
    ("Le client a-t-il une adresse IP publique FIXE ?", "oui_non", None,
     "Votre abonnement Internet a-t-il une adresse IP fixe ?", "Indiqué sur le contrat ou la facture de votre opérateur. "
     "Si vous ne savez pas, laissez « Je ne sais pas »."),
    ("Y a-t-il un DEUXIÈME accès Internet (4G, 2e fibre, ADSL) ?", "oui_non", None,
     "Avez-vous un deuxième accès Internet (4G, deuxième ligne) ?", ""),
    ("Le client a-t-il un Active Directory (domaine Windows) ?", "oui_non", None,
     "Vos salariés se connectent-ils aux PC avec un compte de l'entreprise (« DOMAINE\\nom ») ?",
     "C'est le cas si vous avez un serveur Windows qui gère les comptes."),
    ("Y a-t-il d'autres serveurs ou équipements importants (NAS, logiciel métier, NVR caméras, IPBX...) ?",
     "oui_non", None, "Avez-vous un serveur, un NAS, des caméras ou un standard téléphonique ?", ""),
    ("Le client a-t-il des bornes Wi-Fi Sophos (APX / AP6) gérées par le pare-feu ?", "oui_non", None,
     "Avez-vous des bornes Wi-Fi de la marque Sophos ?", "Le nom Sophos est écrit sur la borne."),
    ("Créer un Wi-Fi invités (isolé, Internet uniquement) ?", "oui_non", None,
     "Souhaitez-vous un Wi-Fi pour vos visiteurs, séparé de votre réseau ?", ""),
    ("Faut-il rendre un équipement interne accessible depuis Internet ?", "oui_non", None,
     "Faut-il accéder depuis l'extérieur à un appareil de vos locaux (caméras, serveur...) ?", ""),
    ("Faut-il relier ce site à un ou plusieurs autres sites ?", "oui_non", None,
     "Avez-vous d'autres locaux (agences) à relier à celui-ci ?", ""),
    ("Des personnes doivent-elles se connecter à distance ?", "oui_non", None,
     "Des salariés travaillent-ils à distance (télétravail) et doivent accéder aux fichiers de l'entreprise ?", ""),
    ("Recevoir les alertes du pare-feu par e-mail ?", "oui_non", None,
     "Souhaitez-vous recevoir les alertes de sécurité par e-mail ?", ""),
]

# Le profil de la société ne garde jamais ces questions (propres à chaque client)
PROPRES_AU_CLIENT = re.compile(
    r"nom|adresse|\bip\b|ip |mac|identifiant|mot de passe|clé|domaine|netbios|situation|secteur|plage|"
    r"première|dernière|e-mail du compte|central|afficher d'abord|appliquer|envoyer|enregistrer|coffre|"
    r"profil|réseaux|relier ce site|autres sites|passerelle|ssid|compte|personne|équipement|fichier|chemin|numéro de série|vlan id",
    re.IGNORECASE)


def generer(destination: str | Path | None = None, societe: str = "") -> Path:
    """Crée la page du questionnaire (un seul fichier HTML, sans Internet)."""
    DOSSIER.mkdir(parents=True, exist_ok=True)
    f = Path(destination) if destination else DOSSIER / "questionnaire_client.html"
    blocs = []
    for i, (question, genre, options, libelle, aide) in enumerate(QUESTIONS):
        champ = f"q{i}"
        if genre == "texte":
            entree = f'<input name="{champ}" required>'
        elif genre == "choix":
            entree = f'<select name="{champ}"><option value="">Je ne sais pas</option>' + "".join(
                f'<option value="{html.escape(k)}">{html.escape(v)}</option>' for k, v in options) + "</select>"
        else:
            entree = "".join(f'<label class="r"><input type="radio" name="{champ}" value="{v}"{" checked" if v == "" else ""}> '
                             f"{t}</label>" for v, t in (("oui", "Oui"), ("non", "Non"), ("", "Je ne sais pas")))
        blocs.append(f'<div class="q"><b>{html.escape(libelle)}</b>'
                     f'{f"<small>{html.escape(aide)}</small>" if aide else ""}{entree}</div>')
    correspondance = json.dumps([[q, g] for q, g, *_ in QUESTIONS], ensure_ascii=False)
    de = f" de la part de {html.escape(societe)}" if societe else ""
    page = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Questionnaire avant l'installation de votre pare-feu</title><style>
body{{font-family:'Segoe UI',Arial,sans-serif;background:#ececef;color:#1d1d22;margin:0}}main{{max-width:760px;margin:0 auto;padding:28px 18px 60px}}
header{{border-bottom:3px solid #E10600;padding-bottom:12px}}h1{{font-size:24px;margin:6px 0}}p{{line-height:1.5}}
.q{{background:#fff;border:1px solid #d8d8de;border-radius:8px;padding:14px 16px;margin:12px 0}}.q b{{display:block;margin-bottom:6px}}
.q small{{display:block;color:#5c5c66;margin-bottom:8px}}input,select,textarea{{font:inherit;padding:8px;border:1px solid #c4c4cc;border-radius:6px;width:100%;box-sizing:border-box}}
.r{{display:inline-block;margin-right:18px}}.r input{{width:auto}}button{{background:#E10600;color:#fff;border:0;padding:12px 22px;font-weight:bold;border-radius:6px;font-size:15px;cursor:pointer}}
.ok{{display:none;background:#e3f5e8;color:#1f7a37;padding:12px 16px;border-radius:6px;margin-top:14px}}</style></head><body><main>
<header><h1>Questionnaire avant l'installation de votre pare-feu</h1><p>Envoyé{de}. Répondez simplement : « Je ne sais pas » est une bonne réponse.
Ne mettez jamais de mot de passe dans ce questionnaire.</p></header>
<form id="f">{"".join(blocs)}<div class="q"><b>Autre chose à nous signaler ?</b><textarea name="notes" rows="4"></textarea></div>
<button type="submit">Enregistrer mes réponses</button><div class="ok" id="ok">Merci ! Un fichier « reponses_….json » vient d'être enregistré
(dossier Téléchargements). Envoyez-le par e-mail à votre technicien.</div></form></main>
<script>const Q={correspondance};
document.getElementById('f').addEventListener('submit',function(e){{e.preventDefault();const d=new FormData(this),r={{}};
Q.forEach(function(x,i){{const v=d.get('q'+i);if(v===null||v==='')return;r[x[0]]=x[1]==='oui_non'?(v==='oui'):v;}});
const nom=(d.get('q0')||'client').toString().trim(),contenu=JSON.stringify({{version:1,client:nom,reponses:r,notes:d.get('notes')||''}},null,1);
const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([contenu],{{type:'application/json'}}));
a.download='reponses_'+nom.replace(/[^A-Za-z0-9_-]+/g,'_')+'.json';document.body.appendChild(a);a.click();a.remove();
document.getElementById('ok').style.display='block';}});</script></body></html>"""
    f.write_text(page, encoding="utf-8")
    return f


def importer(fichier: str | Path) -> tuple[str, Path]:
    """Range le fichier de réponses du client dans clients/questionnaires. Renvoie (client, chemin)."""
    d = json.loads(Path(fichier).read_text(encoding="utf-8"))
    if not isinstance(d, dict) or not isinstance(d.get("reponses"), dict):
        raise ValueError("Ce fichier n'est pas un fichier de réponses du questionnaire.")
    client = str(d.get("client") or Path(fichier).stem).strip() or "client"
    DOSSIER.mkdir(parents=True, exist_ok=True)
    cible = DOSSIER / ("".join(c if c.isalnum() or c in "-_" else "_" for c in client)[:60] + ".json")
    cible.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return client, cible


def disponibles() -> list[tuple[str, Path]]:
    if not DOSSIER.exists():
        return []
    res = []
    for f in sorted(DOSSIER.glob("*.json")):
        try:
            res.append((str(json.loads(f.read_text(encoding="utf-8")).get("client") or f.stem), f))
        except (OSError, ValueError):
            continue
    return res


def reponses(fichier: Path) -> tuple[dict, str]:
    d = json.loads(Path(fichier).read_text(encoding="utf-8"))
    connues = {q for q, *_ in QUESTIONS}
    return {q: v for q, v in d.get("reponses", {}).items() if q in connues}, str(d.get("notes") or "")


# ----------------------------------------------------------------------------- profil de la société
def lire_profil() -> dict:
    try:
        d = json.loads(PROFIL.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def enregistrer_profil(reponses_donnees: dict) -> int:
    """Garde les choix habituels (pas les informations du client). Renvoie le nombre de réponses gardées."""
    profil = lire_profil()
    for q, v in reponses_donnees.items():
        if isinstance(v, (bool, str)) and not PROPRES_AU_CLIENT.search(q):
            profil[q] = v
    PROFIL.write_text(json.dumps(profil, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(profil)


def effacer_profil() -> None:
    PROFIL.unlink(missing_ok=True)
