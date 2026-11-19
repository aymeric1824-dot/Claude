"""Après l'installation : vérifier que tout fonctionne chez le client.

Tests automatiques depuis le PC (branché derrière le pare-feu) : Internet, puis chaque équipement déclaré dans le
fichier client (serveurs, NAS, imprimantes...). Puis une courte liste à cocher pour ce qui ne se teste qu'à la main
(Wi-Fi invités sur un téléphone, connexion d'un télétravailleur). Le résultat est noté dans l'historique.
"""
from __future__ import annotations

import ipaddress
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from openpyxl import load_workbook

from .garde_fous import _lignes

PORTS_COURANTS = [445, 80, 443, 9100, 631, 554, 3389, 22, 5000, 5060, 139, 8080]


def repond(ip: str, delai: float = 1.5) -> bool:
    """L'équipement répond-il ? (ping, puis un port courant si le ping est bloqué)."""
    try:
        commande = ["ping", "-n" if os.name == "nt" else "-c", "1", "-w" if os.name == "nt" else "-W",
                    "1000" if os.name == "nt" else "1", ip]
        r = subprocess.run(commande, capture_output=True, text=True, timeout=5,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode == 0 and ("TTL=" in r.stdout.upper() or os.name != "nt"):
            return True
    except (OSError, subprocess.SubprocessError):
        pass
    from .reseau import port_ouvert
    return any(port_ouvert(ip, p, delai / 3) for p in PORTS_COURANTS)


def equipements(fichier: str | Path) -> list[tuple[str, str, str]]:
    wb = load_workbook(fichier, data_only=True)
    res = []
    for h in _lignes(wb, "Hôtes"):
        if h.get("Type", "").upper() != "IP":
            continue
        try:
            ipaddress.IPv4Address(h.get("Adresse", ""))
        except ValueError:
            continue
        res.append((h.get("Nom", ""), h.get("Adresse", ""), h.get("Description", "")))
    return res


def controles_manuels(fichier: str | Path) -> list[tuple[str, str]]:
    """(question, explication) pour ce qui ne se teste qu'à la main, selon le contenu du fichier."""
    wb = load_workbook(fichier, data_only=True)
    q = []
    wifi = _lignes(wb, "Wi-Fi")
    if any(w.get("Isolation des clients", "").lower().startswith("o") for w in wifi):
        q.append(("Le Wi-Fi invités fonctionne-t-il sur un téléphone ?",
                  "Connectez un téléphone au Wi-Fi invités et ouvrez un site web."))
    if any(not w.get("Isolation des clients", "").lower().startswith("o") for w in wifi):
        q.append(("Le Wi-Fi salariés fonctionne-t-il ?", "Connectez un PC portable ou un téléphone au Wi-Fi salariés."))
    if any(c.get("VPN télétravail", "").lower().startswith("o") for c in _lignes(wb, "Comptes")):
        q.append(("Un télétravailleur arrive-t-il à se connecter au VPN ?",
                  "Depuis un téléphone en partage de connexion (4G), testez Sophos Connect avec un des comptes."))
    if _lignes(wb, "Redirections"):
        q.append(("Les accès depuis Internet fonctionnent-ils ?",
                  "Depuis un téléphone en 4G (pas sur le Wi-Fi), essayez d'accéder au service publié."))
    if any("imprim" in (h.get("Description", "") + h.get("Nom", "")).lower() or h.get("Nom", "").startswith("IMP")
           for h in _lignes(wb, "Hôtes")):
        q.append(("Les imprimantes impriment-elles ?", "Lancez une page de test depuis un PC du client."))
    q.append(("Les utilisateurs accèdent-ils à leurs fichiers et logiciels habituels ?",
              "Demandez à une ou deux personnes de vérifier leur travail habituel."))
    return q


def verifier_services(fichier: str | Path, client: str = "") -> tuple[int, int]:
    """Tests automatiques puis liste à cocher. Renvoie (nombre de points OK, nombre de problèmes)."""
    from . import historique
    from .assistant import oui_non
    from .deployer import tester_internet
    vert, rouge, jaune, fin = "\033[32m", "\033[31m", "\033[33m", "\033[0m"
    ok = ko = 0
    problemes = []
    if tester_internet():
        ok += 1
    else:
        ko += 1
        problemes.append("Internet ne répond pas depuis le PC")
    liste = equipements(fichier)
    if liste:
        print(f"Les {len(liste)} équipement(s) du client répondent-ils ?")
        for nom, ip, bon in tester_equipements(fichier):
            print(f"  {vert + '✔' if bon else rouge + '✘'}{fin} {nom} ({ip})")
            ok, ko = (ok + 1, ko) if bon else (ok, ko + 1)
            if not bon:
                problemes.append(f"{nom} ({ip}) ne répond pas")
        if ko:
            print(f"{jaune}  Un équipement qui ne répond pas est peut-être éteint, ou bloque le ping : vérifiez-le sur "
                  f"place.{fin}")
    for question, explication in controles_manuels(fichier):
        if oui_non(question, True, explication):
            ok += 1
        else:
            ko += 1
            problemes.append(question.rstrip(" ?"))
    print(f"\n{vert if not ko else jaune}Vérification : {ok} point(s) OK, {ko} problème(s).{fin}")
    for p in problemes:
        print(f"  - {p}")
    historique.enregistrer(client or Path(fichier).stem, "verification", f"{ok} OK, {ko} problème(s)", echecs=ko,
                           problemes=problemes)
    return ok, ko


def tester_equipements(fichier: str | Path) -> list[tuple[str, str, bool]]:
    liste = equipements(fichier)
    with ThreadPoolExecutor(max_workers=16) as pool:
        resultats = list(pool.map(lambda e: repond(e[1]), liste))
    return [(n, ip, ok) for (n, ip, _d), ok in zip(liste, resultats)]
