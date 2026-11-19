"""Schéma du réseau du client et des branchements, dessiné à partir de son fichier Excel.

Une page web (avec une image SVG, sans Internet) qui montre d'un coup d'œil :
- quel câble brancher sur quel port du pare-feu (Internet, réseau local, DMZ...) ;
- les réseaux (LAN, VLAN, Wi-Fi) et les équipements déclarés dans chacun.
À regarder avant d'envoyer la configuration, et à garder dans le dossier du client.
"""
from __future__ import annotations

import html
import ipaddress
import re
from pathlib import Path

from openpyxl import load_workbook

from .garde_fous import _lignes

COULEURS = {"WAN": "#E10600", "LAN": "#1f7a37", "DMZ": "#c98a00", "WIFI": "#1f6feb", "VPN": "#8250df"}
GRIS = "#7a7a84"


def _couleur(zone: str) -> str:
    z = (zone or "").upper()
    for k, c in COULEURS.items():
        if k in z:
            return c
    return GRIS


def _reseau(ip: str, masque: str):
    try:
        return ipaddress.IPv4Interface(f"{ip}/{masque or '24'}")
    except ValueError:
        return None


def _num_port(port: str) -> int:
    m = re.search(r"(\d+)", port or "")
    return int(m.group(1)) if m else 0


def donnees(fichier: str | Path) -> dict:
    wb = load_workbook(fichier, data_only=True)
    general = {}
    if "Général" in wb.sheetnames:
        for row in wb["Général"].iter_rows(min_row=2, values_only=True):
            if row and row[0]:
                general[str(row[0])] = "" if len(row) < 2 or row[1] is None else str(row[1])
    reseaux, ports = [], {}
    for r in _lignes(wb, "Interfaces"):
        port, zone = r.get("Port", ""), r.get("Zone", "")
        ports[port] = (zone, r.get("Description", ""), r.get("Mode", ""))
        if "WAN" not in zone.upper():
            iface = _reseau(r.get("Adresse IP", ""), r.get("Masque", ""))
            if iface:
                reseaux.append({"titre": f"{zone} — {port}", "zone": zone, "iface": iface, "hotes": [],
                                "detail": r.get("Description", "")})
    if not any("LAN" in z.upper() for z, *_ in ports.values()):     # pare-feu neuf : Port1 = LAN d'usine
        ip = general.get("Adresse IP du pare-feu") or "172.16.16.16"
        ports.setdefault("Port1", ("LAN", "Réseau local", "Statique"))
        iface = _reseau(ip, "24")
        if iface:
            reseaux.insert(0, {"titre": "LAN — Port1", "zone": "LAN", "iface": iface, "hotes": [], "detail": "Réseau local"})
    for r in _lignes(wb, "VLAN"):
        iface = _reseau(r.get("Adresse IP", ""), r.get("Masque", ""))
        if iface:
            reseaux.append({"titre": f"VLAN {r.get('ID VLAN')} — {r.get('Zone')}", "zone": r.get("Zone", ""),
                            "iface": iface, "hotes": [], "detail": r.get("Description", "") +
                            f" (sur {r.get('Interface physique')})"})
    for r in _lignes(wb, "Wi-Fi"):
        iface = _reseau(r.get("Adresse IP", ""), r.get("Masque", ""))
        reseaux.append({"titre": f"Wi-Fi « {r.get('SSID') or r.get('Nom')} »", "zone": "WIFI " + r.get("Zone", ""),
                        "iface": iface, "hotes": [], "detail": "Isolé" if r.get("Isolation des clients", "").lower()
                        .startswith("o") else ""})
    for r in _lignes(wb, "Hôtes"):
        if r.get("Type", "").upper() != "IP":
            continue
        try:
            ip = ipaddress.IPv4Address(r.get("Adresse", ""))
        except ValueError:
            continue
        for n in reseaux:
            if n["iface"] and ip in n["iface"].network:
                n["hotes"].append(f"{r.get('Nom')} — {ip}")
                break
    return {"client": general.get("Nom du client", Path(fichier).stem), "nom": general.get("Nom d'hôte du pare-feu", ""),
            "ports": ports, "reseaux": reseaux}


def svg(d: dict) -> str:
    largeur = 960
    e = html.escape
    parts = []
    # Internet et liens WAN
    wans = [(p, v) for p, v in d["ports"].items() if "WAN" in v[0].upper()] or [("Port2", ("WAN", "Internet", "DHCP"))]
    parts.append(f'<rect x="{largeur / 2 - 110}" y="10" width="220" height="46" rx="23" fill="#fff" stroke="{COULEURS["WAN"]}" '
                 f'stroke-width="2"/><text x="{largeur / 2}" y="39" text-anchor="middle" class="t">Internet</text>')
    for i, (p, (zone, desc, mode)) in enumerate(wans):
        x = largeur / 2 + (i - (len(wans) - 1) / 2) * 260
        parts.append(f'<line x1="{largeur / 2}" y1="56" x2="{x}" y2="86" stroke="{COULEURS["WAN"]}" stroke-width="2"/>'
                     f'<rect x="{x - 115}" y="86" width="230" height="40" rx="6" fill="#fff5f4" stroke="{COULEURS["WAN"]}"/>'
                     f'<text x="{x}" y="104" text-anchor="middle" class="s">Box / routeur de l\'opérateur</text>'
                     f'<text x="{x}" y="119" text-anchor="middle" class="p">{e(p)} · {e(mode or "")}</text>'
                     f'<line x1="{x}" y1="126" x2="{x}" y2="160" stroke="{COULEURS["WAN"]}" stroke-width="3"/>')
    # Pare-feu et ses ports (branchements)
    parts.append(f'<rect x="40" y="160" width="{largeur - 80}" height="92" rx="10" fill="#1d1d22"/>'
                 f'<text x="62" y="186" class="b">Pare-feu Sophos{(" — " + e(d["nom"])) if d["nom"] else ""}</text>')
    n = max([8] + [_num_port(p) for p in d["ports"]])
    pas = min(70, (largeur - 160) / n)
    for k in range(1, n + 1):
        nom = f"Port{k}"
        zone = d["ports"].get(nom, ("", "", ""))[0]
        x = 62 + (k - 1) * pas
        couleur = _couleur(zone) if zone else "#3a3a42"
        parts.append(f'<rect x="{x}" y="200" width="{pas - 10}" height="26" rx="3" fill="{couleur}"/>'
                     f'<text x="{x + (pas - 10) / 2}" y="217" text-anchor="middle" class="w">{k}</text>'
                     f'<text x="{x + (pas - 10) / 2}" y="242" text-anchor="middle" class="pw">{e(zone[:8]) or "libre"}</text>')
    # Réseaux internes : 4 colonnes au plus, sur autant de lignes que nécessaire
    reseaux = d["reseaux"] or []
    colonnes = max(1, min(4, len(reseaux)))
    larg_col = (largeur - 80 - (colonnes - 1) * 16) / colonnes

    def hauteur_carte(r):
        return 78 + 17 * min(12, len(r["hotes"])) + (17 if len(r["hotes"]) > 12 else 0)
    y = 300
    for debut_ligne in range(0, len(reseaux), colonnes):
        rang = reseaux[debut_ligne:debut_ligne + colonnes]
        haut = max(hauteur_carte(r) for r in rang)
        for col, r in enumerate(rang):
            x = 40 + col * (larg_col + 16)
            couleur = _couleur(r["zone"])
            hotes = r["hotes"][:12]
            depart = 252 if debut_ligne == 0 else y - 16
            parts.append(f'<line x1="{x + larg_col / 2}" y1="{depart}" x2="{x + larg_col / 2}" y2="{y}" stroke="{couleur}" '
                         f'stroke-width="2" stroke-dasharray="{"5,4" if "WIFI" in r["zone"].upper() else "0"}"/>'
                         f'<rect x="{x}" y="{y}" width="{larg_col}" height="{haut}" rx="8" fill="#fff" stroke="{couleur}" stroke-width="2"/>'
                         f'<rect x="{x}" y="{y}" width="{larg_col}" height="6" rx="3" fill="{couleur}"/>'
                         f'<text x="{x + 12}" y="{y + 28}" class="b2">{e(r["titre"])}</text>'
                         f'<text x="{x + 12}" y="{y + 46}" class="p">{e(str(r["iface"].network) if r["iface"] else "")}'
                         f'{(" · passerelle " + e(str(r["iface"].ip))) if r["iface"] else ""}</text>'
                         f'<text x="{x + 12}" y="{y + 62}" class="s">{e(r["detail"][:48])}</text>')
            for j, hote in enumerate(hotes):
                parts.append(f'<text x="{x + 18}" y="{y + 82 + 17 * j}" class="p">• {e(hote)}</text>')
            if len(r["hotes"]) > 12:
                parts.append(f'<text x="{x + 18}" y="{y + 82 + 17 * 12}" class="s">… et {len(r["hotes"]) - 12} autre(s)</text>')
        y += haut + 24
    hauteur = y + 10
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largeur} {hauteur}" width="100%">'
            '<style>.t{font:bold 18px Segoe UI,Arial}.b{font:bold 15px Segoe UI,Arial;fill:#fff}'
            '.b2{font:bold 14px Segoe UI,Arial;fill:#1d1d22}.s{font:12px Segoe UI,Arial;fill:#5c5c66}'
            '.p{font:12px Consolas,monospace;fill:#1d1d22}.w{font:bold 12px Consolas,monospace;fill:#fff}'
            '.pw{font:10px Consolas,monospace;fill:#c8c8ce}</style>' + "".join(parts) + "</svg>")


def branchements(d: dict) -> list[str]:
    res = []
    for p, (zone, desc, mode) in sorted(d["ports"].items(), key=lambda x: _num_port(x[0])):
        if "WAN" in zone.upper():
            res.append(f"{p} : câble vers la box / le routeur de l'opérateur ({desc or 'Internet'})")
        elif "LAN" in zone.upper():
            res.append(f"{p} : câble vers le switch du réseau local (les PC)")
        else:
            res.append(f"{p} : {zone} — {desc}")
    return res


def generer(fichier: str | Path, destination: str | Path | None = None) -> Path:
    d = donnees(fichier)
    f = Path(destination) if destination else Path(fichier).with_name(Path(fichier).stem + "_schema.html")
    e = html.escape
    page = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Schéma du réseau — {e(d['client'])}</title><style>body{{font-family:'Segoe UI',Arial,sans-serif;background:#ececef;color:#1d1d22;margin:0}}
main{{max-width:1000px;margin:0 auto;padding:24px 16px}}header{{border-bottom:3px solid #E10600;margin-bottom:16px}}h1{{font-size:24px;margin:4px 0 10px}}
.c{{background:#fff;border:1px solid #d8d8de;border-radius:8px;padding:14px 18px;margin:14px 0}}li{{margin:4px 0}}</style></head><body><main>
<header><h1>Schéma du réseau — {e(d['client'])}</h1></header>
<div class="c"><b>Branchements</b><ul>{''.join(f'<li>{e(x)}</li>' for x in branchements(d))}</ul></div>
<div class="c">{svg(d)}</div></main></body></html>"""
    f.write_text(page, encoding="utf-8")
    return f
