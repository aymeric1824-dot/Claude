"""Contrôle de sécurité d'un Sophos XGS (lecture seule : rien n'est modifié).

    python -m sophos_auto.audit --ip 192.168.1.254

Produit un rapport HTML lisible (à remettre au client) dans le dossier rapports/.
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import html
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from .api import ErreurAPI, ErreurConnexion, SophosAPI

CRITIQUE, ATTENTION, INFO = "Critique", "À corriger", "Conseil"
ORDRE = {CRITIQUE: 0, ATTENTION: 1, INFO: 2}

# Ports dangereux à exposer sur Internet
PORTS_RISQUES = {3389: "Bureau à distance (RDP)", 445: "Partage de fichiers Windows (SMB)", 139: "NetBIOS",
                 23: "Telnet", 21: "FTP", 1433: "SQL Server", 3306: "MySQL", 5900: "VNC", 22: "SSH",
                 135: "RPC Windows", 5985: "WinRM", 5986: "WinRM"}
NOMS_RISQUES = {"RDP": 3389, "SMB": 445, "TELNET": 23, "VNC": 5900, "MSSQL": 1433, "MYSQL": 3306}


@dataclass
class Constat:
    niveau: str
    titre: str
    detail: str
    conseil: str


def _l(x) -> list:
    """Normalise une valeur XML en liste (absente -> [], valeur seule -> [valeur])."""
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _valeurs(bloc, cle) -> list[str]:
    """Ex. _valeurs(policy.get('SourceZones'), 'Zone')."""
    if not isinstance(bloc, dict):
        return []
    return [str(v) for v in _l(bloc.get(cle)) if v not in (None, "")]


def _ports_service(service: dict) -> list[tuple[int, int]]:
    plages = []
    for d in _l((service.get("ServiceDetails") or {}).get("ServiceDetail")):
        if not isinstance(d, dict):
            continue
        p = str(d.get("DestinationPort", ""))
        m = re.fullmatch(r"(\d+)(?::(\d+))?", p)
        if m:
            plages.append((int(m.group(1)), int(m.group(2) or m.group(1))))
    return plages


def _risques(noms_services: list[str], services: dict[str, dict]) -> list[str]:
    trouves = []
    for nom in noms_services:
        for mot, port in NOMS_RISQUES.items():
            if mot in nom.upper():
                trouves.append(f"{nom} ({PORTS_RISQUES[port]})")
                break
        else:
            for a, b in _ports_service(services.get(nom, {})):
                for port, lib in PORTS_RISQUES.items():
                    if a <= port <= b:
                        trouves.append(f"{nom} (port {port} : {lib})")
    return trouves


def auditer(api: SophosAPI) -> list[Constat]:
    def lire(balise) -> list[dict]:
        try:
            return [e for e in _l(api.lire(balise)) if isinstance(e, dict)]
        except ErreurConnexion:
            raise
        except ErreurAPI:
            return []

    c: list[Constat] = []
    services = {s.get("Name"): s for s in lire("Services")}

    # ---- administration exposée sur Internet
    for z in lire("Zone"):
        if z.get("Name") != "WAN":
            continue
        acces = z.get("ApplianceAccess") or {}
        admin = acces.get("AdminServices") or {}
        ouverts = [s for s in ("HTTPS", "SSH") if admin.get(s) == "Enable"]
        if ouverts:
            c.append(Constat(CRITIQUE, "Administration du pare-feu ouverte sur Internet",
                             f"Depuis la zone WAN : {', '.join(ouverts)}.",
                             "Désactivez-la dans Administration > Accès aux services de l'appareil, et administrez "
                             "par VPN ou via Sophos Central."))
        autres = acces.get("OtherServices") or {}
        if autres.get("UserPortal") == "Enable":
            c.append(Constat(ATTENTION, "Portail utilisateur accessible depuis Internet",
                             "Le portail utilisateur est ouvert dans la zone WAN.",
                             "Fermez-le si les utilisateurs n'en ont pas besoin depuis l'extérieur."))
        if (acces.get("NetworkServices") or {}).get("DNS") == "Enable":
            c.append(Constat(ATTENTION, "Serveur DNS du pare-feu ouvert sur Internet",
                             "Le service DNS est autorisé depuis la zone WAN.",
                             "Désactivez le DNS sur la zone WAN (risque d'attaques par amplification)."))

    # ---- redirections (NAT) vers des services dangereux
    for n in lire("NATRule"):
        if n.get("Status") == "Disable" or n.get("TranslatedDestination") in (None, "", "Original"):
            continue
        svc = _valeurs(n.get("OriginalServices"), "Service")
        risques = _risques(svc, services)
        sources = _valeurs(n.get("OriginalSourceNetworks"), "Network")
        if risques:
            c.append(Constat(CRITIQUE if not sources else ATTENTION,
                             f"Service sensible publié sur Internet : « {n.get('Name')} »",
                             f"Redirection de {', '.join(risques)} vers {n.get('TranslatedDestination')}"
                             + (f", limitée à {', '.join(sources)}." if sources else ", depuis n'importe quelle adresse."),
                             "Supprimez cette redirection et utilisez le VPN télétravail. À défaut, limitez-la aux "
                             "adresses IP connues."))
        elif not svc:
            c.append(Constat(CRITIQUE, f"Redirection de TOUS les ports : « {n.get('Name')} »",
                             f"Tout le trafic entrant est envoyé vers {n.get('TranslatedDestination')}.",
                             "Ne redirigez que les ports strictement nécessaires."))

    # ---- règles de pare-feu
    desactivees = 0
    for r in lire("FirewallRule"):
        nom = r.get("Name", "?")
        if r.get("Status") == "Disable":
            desactivees += 1
            continue
        p = r.get("NetworkPolicy") or r.get("UserPolicy") or {}
        if p.get("Action") != "Accept":
            continue
        zs, zd = _valeurs(p.get("SourceZones"), "Zone"), _valeurs(p.get("DestinationZones"), "Zone")
        rs, rd = _valeurs(p.get("SourceNetworks"), "Network"), _valeurs(p.get("DestinationNetworks"), "Network")
        svc = _valeurs(p.get("Services"), "Service")
        if not zs and not zd and not rs and not rd and not svc:
            c.append(Constat(CRITIQUE, f"Règle « tout autoriser » : « {nom} »",
                             "Cette règle accepte tout le trafic, de n'importe où vers n'importe où.",
                             "Remplacez-la par des règles précises (zones, réseaux et services)."))
            continue
        depuis_internet = "WAN" in zs or not zs
        if depuis_internet and "WAN" in zs and not rs and not svc:
            c.append(Constat(CRITIQUE, f"Règle trop ouverte depuis Internet : « {nom} »",
                             f"Tout Internet peut joindre {', '.join(zd or ['toutes les zones'])} sur tous les ports.",
                             "Limitez les services et, si possible, les adresses sources."))
        elif "WAN" in zs and _risques(svc, services) and not rs:
            c.append(Constat(CRITIQUE, f"Service sensible ouvert depuis Internet : « {nom} »",
                             ", ".join(_risques(svc, services)) + ", depuis n'importe quelle adresse.",
                             "Passez par le VPN ou limitez aux adresses connues."))
        if "WAN" in zd and "WAN" not in zs:  # sortie vers Internet
            manque = [lib for cle, lib in (("WebFilter", "filtrage web"), ("IntrusionPrevention", "IPS"))
                      if p.get(cle) in (None, "", "None")]
            if p.get("ScanVirus") != "Enable":
                manque.append("antivirus")
            if manque:
                c.append(Constat(ATTENTION, f"Accès Internet sans protection complète : « {nom} »",
                                 f"Protections absentes : {', '.join(manque)}.",
                                 "Activez-les dans la règle (licences Web et Network Protection nécessaires)."))
        if "WAN" in zs and p.get("LogTraffic") == "Disable":
            c.append(Constat(INFO, f"Trafic entrant non journalisé : « {nom} »",
                             "Les connexions venant d'Internet ne sont pas enregistrées.",
                             "Activez la journalisation pour pouvoir enquêter en cas d'incident."))
    if desactivees:
        c.append(Constat(INFO, f"{desactivees} règle(s) désactivée(s)",
                         "Des règles désactivées encombrent la configuration.",
                         "Supprimez celles qui ne servent plus."))

    # ---- sauvegardes, alertes, supervision, comptes
    sauvegarde = next(iter(lire("BackupRestore")), {})
    freq = ((sauvegarde.get("ScheduleBackup") or {}).get("BackupFrequency") or "Never")
    if freq == "Never":
        c.append(Constat(ATTENTION, "Aucune sauvegarde automatique",
                         "La configuration n'est pas sauvegardée régulièrement.",
                         "Programmez une sauvegarde hebdomadaire (par e-mail ou FTP), ou utilisez les sauvegardes "
                         "Sophos Central."))
    elif (sauvegarde.get("ScheduleBackup") or {}).get("BackupMode") == "Local":
        c.append(Constat(INFO, "Sauvegardes stockées uniquement sur le boîtier",
                         "Si le boîtier tombe en panne, les sauvegardes sont perdues avec lui.",
                         "Envoyez-les par e-mail, sur un FTP ou utilisez Sophos Central."))
    notif = next(iter(lire("Notification")), {})
    if not notif.get("MailServer") or not notif.get("Recepient"):
        c.append(Constat(ATTENTION, "Alertes e-mail non configurées",
                         "Personne n'est prévenu en cas de panne de lien, de VPN coupé ou d'attaque.",
                         "Configurez un serveur d'envoi et un destinataire (Administration > Paramètres de notification)."))
    for s in lire("SNMPCommunity"):
        if str(s.get("Name", "")).lower() in ("public", "private"):
            c.append(Constat(CRITIQUE, f"Communauté SNMP par défaut « {s.get('Name')} »",
                             "Ce nom est connu de tous et permet de lire la configuration réseau.",
                             "Utilisez un nom de communauté propre au client (ou SNMPv3)."))
    admins = [u.get("Username") for u in lire("User") if u.get("UserType") == "Administrator"]
    if admins == ["admin"] or not admins:
        c.append(Constat(INFO, "Seul le compte « admin » administre le pare-feu",
                         "Impossible de savoir qui a fait quelle modification.",
                         "Créez un compte administrateur nominatif par technicien."))

    if not any(x.niveau == CRITIQUE for x in c):
        c.append(Constat(INFO, "Aucun problème critique détecté", "Les contrôles critiques sont passés.", "—"))
    return sorted(c, key=lambda x: ORDRE[x.niveau])


# ----------------------------------------------------------------------------- rapport
COULEURS = {CRITIQUE: "#c0392b", ATTENTION: "#d68910", INFO: "#2e86c1"}


def rapport_html(constats: list[Constat], cible: str, client: str = "") -> str:
    date = dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    nb = {n: sum(1 for c in constats if c.niveau == n) for n in ORDRE}
    lignes = "".join(
        f'<div class="c" style="border-left-color:{COULEURS[x.niveau]}"><span class="n" style="background:'
        f'{COULEURS[x.niveau]}">{x.niveau}</span><h3>{html.escape(x.titre)}</h3><p>{html.escape(x.detail)}</p>'
        f'<p class="k"><b>Que faire :</b> {html.escape(x.conseil)}</p></div>' for x in constats)
    resume = " ".join(f'<span class="b" style="background:{COULEURS[n]}">{nb[n]} {n.lower()}</span>' for n in ORDRE)
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Contrôle de sécurité</title><style>
body{{font-family:Segoe UI,Arial,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;color:#222;background:#fff}}
h1{{margin-bottom:4px}} .s{{color:#666}} .b{{color:#fff;padding:4px 10px;border-radius:12px;margin-right:6px;font-size:14px}}
.c{{border-left:6px solid;padding:8px 16px;margin:14px 0;background:#f7f7f7;border-radius:4px}}
.c h3{{margin:6px 0}} .n{{color:#fff;font-size:12px;padding:2px 8px;border-radius:8px}} .k{{color:#333}}
</style></head><body><h1>Contrôle de sécurité du pare-feu</h1>
<p class="s">{html.escape(client + ' — ' if client else '')}{html.escape(cible)} — {date}</p><p>{resume}</p>{lignes}
<p class="s">Contrôle automatique en lecture seule : il ne remplace pas un audit complet.</p></body></html>"""


def executer(api: SophosAPI, cible: str, client: str = "") -> tuple[list[Constat], Path]:
    constats = auditer(api)
    Path("rapports").mkdir(exist_ok=True)
    nom = re.sub(r"[^A-Za-z0-9_-]", "_", client or cible)
    chemin = Path("rapports") / f"securite_{nom}_{dt.datetime.now():%Y-%m-%d_%H%M}.html"
    chemin.write_text(rapport_html(constats, cible, client), encoding="utf-8")
    return constats, chemin


def afficher(constats: list[Constat]) -> None:
    coul = {CRITIQUE: "\033[31m", ATTENTION: "\033[33m", INFO: "\033[36m"}
    for x in constats:
        print(f"{coul[x.niveau]}  [{x.niveau}] {x.titre}\033[0m\n      {x.detail}\n      → {x.conseil}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Contrôle de sécurité d'un Sophos XGS (lecture seule).")
    p.add_argument("--ip", default="172.16.16.16")
    p.add_argument("--port", type=int, default=4444)
    p.add_argument("--utilisateur", default="admin")
    p.add_argument("--client", default="", help="Nom du client (pour le rapport)")
    a = p.parse_args(argv)
    mdp = os.environ.get("SOPHOS_MOT_DE_PASSE") or getpass.getpass(f"Mot de passe de « {a.utilisateur} » : ")
    try:
        constats, chemin = executer(SophosAPI(a.ip, a.utilisateur, mdp, port=a.port), a.ip, a.client)
    except ErreurAPI as exc:
        print(f"\033[31m✘ {exc}\033[0m")
        return 1
    afficher(constats)
    print(f"\nRapport : {chemin}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
