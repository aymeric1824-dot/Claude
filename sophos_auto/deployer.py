"""Applique un fichier Excel client sur un Sophos XGS via l'API XML.

Exemples :
    python -m sophos_auto.deployer client.xlsx --simulation   # vérifie, n'envoie rien
    python -m sophos_auto.deployer client.xlsx                # applique
    python -m sophos_auto.deployer --lire IPHost --ip 172.16.16.16   # affiche des objets existants
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import getpass
import json
import os
import sys
from pathlib import Path

from .api import ErreurAPI, ErreurConnexion, Resultat, SophosAPI, to_xml
from .modele import ETAPES, Configuration, Operation, Secret, lire_classeur

VERT, ROUGE, JAUNE, GRIS, GRAS, FIN = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[1m", "\033[0m"
if os.name == "nt":
    os.system("")  # active les couleurs dans la console Windows

# Où chercher les noms existants sur le pare-feu, par type de référence
SOURCES_NOMS = {
    "zone": [("Zone", "Name")],
    "reseau": [("IPHost", "Name"), ("IPHostGroup", "Name"), ("FQDNHost", "Name"), ("FQDNHostGroup", "Name")],
    "service": [("Services", "Name"), ("ServiceGroup", "Name")],
    "webfilter": [("WebFilterPolicy", "Name")],
    "appfilter": [("ApplicationFilterPolicy", "Name")],
    "ips": [("IPSPolicy", "Name")],
    "vpnprofile": [("VPNProfile", "Name")],
    "interface": [("Interface", "Hardware"), ("Interface", "Name"), ("VLAN", "Name")],
}


# ----------------------------------------------------------------------------- mots de passe
def secrets_de(cfg: Configuration) -> list[Secret]:
    trouves: list[Secret] = []

    def parcourir(x):
        if isinstance(x, Secret):
            trouves.append(x)
        elif isinstance(x, dict):
            for v in x.values():
                parcourir(v)
        elif isinstance(x, list):
            for v in x:
                parcourir(v)
    for o in cfg.operations:
        parcourir(o.contenu)
    return trouves


def demander_secrets(cfg: Configuration, fournis: dict[str, str] | None = None) -> None:
    fournis = fournis or {}
    for s in secrets_de(cfg):
        if s.valeur is not None:
            continue
        if s.libelle in fournis:
            s.valeur = fournis[s.libelle]
            continue
        while True:
            v = getpass.getpass(f"{s.libelle} : ")
            if not v:
                print(f"{JAUNE}  Valeur vide, recommencez.{FIN}")
                continue
            if getpass.getpass("  Confirmez : ") == v:
                break
            print(f"{JAUNE}  Les deux saisies sont différentes, recommencez.{FIN}")
        s.valeur = v
        fournis[s.libelle] = v


def _remplacer(x, masquer: bool):
    if isinstance(x, Secret):
        return "********" if masquer else (x.valeur or "")
    if isinstance(x, dict):
        return {k: _remplacer(v, masquer) for k, v in x.items()}
    if isinstance(x, list):
        return [_remplacer(v, masquer) for v in x]
    return x


# ----------------------------------------------------------------------------- application d'une opération
def _fusion(base: dict, patch: dict) -> dict:
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _fusion(base[k], v)
        else:
            base[k] = v
    return base


def _trouver(elements, champ: str, cle: str):
    elements = elements if isinstance(elements, list) else [elements]
    for e in elements:
        if isinstance(e, dict) and cle in (e.get(champ), e.get("Name")):
            return e
    return None


def appliquer(api: SophosAPI, op: Operation, sans_modifier: bool = False) -> tuple[Resultat, str]:
    contenu = _remplacer(op.contenu, masquer=False)
    if sans_modifier:
        if op.mode != "creer":
            return Resultat(True, "", ""), "ignoré (mode prudent : réglage existant non modifié)"
        res = api.ecrire(op.balise, contenu, "add")
        if not res.ok and res.deja_existant:
            return Resultat(True, res.code, res.message), "existe déjà : non modifié (mode prudent)"
        return res, "créé"
    if op.mode == "maj":
        return api.ecrire(op.balise, contenu, "update"), "mis à jour"
    if op.mode == "creer":
        res, action = api.ecrire_ou_mettre_a_jour(op.balise, contenu)
        if not res.ok and res.deja_existant and op.existe_ok:
            return Resultat(True, res.code, res.message), "déjà présent"
        return res, action
    # patch : lecture de l'objet existant, modification, renvoi complet
    actuel = api.lire(op.balise)
    if actuel is None:
        return Resultat(False, "404", f"{op.balise} introuvable sur le pare-feu"), "erreur"
    if op.sous_liste:  # ex. GatewayConfiguration > Gateway[Name=...]
        racine = copy.deepcopy(actuel if isinstance(actuel, dict) else actuel[0])
        cible = _trouver(racine.get(op.sous_liste), op.champ_cle, op.cle)
        if cible is None:
            return Resultat(False, "404", f"« {op.cle} » introuvable dans {op.balise}"), "erreur"
        envoi = racine
    elif op.cle:
        cible = copy.deepcopy(_trouver(actuel, op.champ_cle, op.cle))
        if cible is None:
            return Resultat(False, "404", f"{op.balise} « {op.cle} » introuvable sur le pare-feu"), "erreur"
        envoi = cible
    else:
        cible = copy.deepcopy(actuel if isinstance(actuel, dict) else actuel[0])
        envoi = cible
    for k, v in op.defauts.items():
        if not cible.get(k):
            cible[k] = v
    _fusion(cible, contenu)
    for k in op.retirer:
        cible.pop(k, None)
    envoi.pop("@transactionid", None)
    return api.ecrire(op.balise, envoi, "update"), "modifié"


# ----------------------------------------------------------------------------- contrôle avant application
def verifier_sur_pare_feu(api: SophosAPI, cfg: Configuration) -> list[str]:
    """Liste les noms utilisés qui n'existent ni dans le fichier, ni sur le pare-feu."""
    besoins = {(t, n) for o in cfg.operations for t, n in o.refs
               if not n.startswith("#") and not cfg.defini(t, n) and t in SOURCES_NOMS}
    if not besoins:
        return []
    existants: dict[str, set[str]] = {}
    for t in {t for t, _ in besoins}:
        noms: set[str] = set()
        for balise, champ in SOURCES_NOMS[t]:
            noms |= api.noms(balise, champ)
        existants[t] = noms
    problemes = []
    for t, n in sorted(besoins):
        if n not in existants[t]:
            dispo = sorted(existants[t])
            astuce = f" Disponibles : {', '.join(dispo[:12])}{'…' if len(dispo) > 12 else ''}" if dispo and t in (
                "webfilter", "appfilter", "ips", "vpnprofile", "zone") else ""
            problemes.append(f"« {n} » ({t}) n'existe pas sur le pare-feu.{astuce}")
    return problemes


def _ip_de_connexion(api: SophosAPI, cfg: Configuration, ip: str) -> Operation | None:
    """L'interface qui porte l'IP de connexion et dont l'IP change est appliquée en dernier ;
    les serveurs DHCP de cette interface sont créés après, une fois reconnecté sur la nouvelle IP."""
    trouve = None
    interfaces = None
    for o in cfg.operations:
        if o.balise != "Interface" or "IPAddress" not in o.contenu:
            continue
        if interfaces is None:
            interfaces = api.lire("Interface") or []
        actuel = _trouver(interfaces, "Hardware", o.cle)
        if actuel and actuel.get("IPAddress") == ip and o.contenu["IPAddress"] != ip:
            o.etape = ETAPES["fin"]
            o.nom += f" (nouvelle IP {o.contenu['IPAddress']})"
            trouve = o
            for d in cfg.operations:
                if d.balise == "DHCPServer" and d.contenu.get("Interface") == o.cle:
                    d.etape = ETAPES["après"]
    cfg.operations.sort(key=lambda x: x.etape)
    return trouve


def _reconnexion(api: SophosAPI, op: Operation, ip_pc: str | None, confirmer) -> SophosAPI | None:
    nouvelle = op.contenu["IPAddress"]
    masque = op.contenu.get("Netmask", "255.255.255.0")
    print(f"\n{JAUNE}{GRAS}Le pare-feu a maintenant l'adresse {nouvelle}.{FIN}")
    print(f"Pour continuer, passez votre PC sur ce réseau : IP fixe {ip_pc or 'libre de ce réseau'}, "
          f"masque {masque}, passerelle {nouvelle}.")
    print("(Windows : Paramètres > Réseau > Ethernet > Attribution d'IP > Modifier > Manuel)")
    neuf = SophosAPI(nouvelle, api.utilisateur, api.mot_de_passe, port=int(api.url.split(":")[2].split("/")[0]),
                     verifier_certificat=api.verifier_certificat)
    while True:
        if confirmer:
            if not confirmer("PC reconfiguré ?"):
                return None
        else:
            input("Appuyez sur Entrée quand c'est fait (Ctrl+C pour arrêter)... ")
        try:
            neuf.tester_connexion()
            print(f"{VERT}✔ Reconnecté sur {nouvelle}{FIN}")
            return neuf
        except ErreurAPI as exc:
            print(f"{ROUGE}✘ {exc}{FIN}")
            if confirmer:
                return None


NOMS_BALISES = {
    "IPHost": "objet(s) réseau", "FQDNHost": "objet(s) FQDN", "IPHostGroup": "groupe(s) d'hôtes",
    "Services": "service(s)", "FirewallRule": "règle(s) de pare-feu", "NATRule": "redirection(s) NAT",
    "Zone": "zone(s)", "VLAN": "VLAN", "Interface": "interface(s)", "DHCPServer": "serveur(s) DHCP",
    "User": "compte(s)", "VPNIPSecConnection": "opération(s) VPN IPsec", "SSLVPNPolicy": "stratégie(s) VPN SSL",
    "WirelessNetworks": "réseau(x) Wi-Fi", "UnicastRoute": "route(s)", "AuthenticationServer": "serveur(s) AD",
}


def resume_operations(operations: list[Operation]) -> list[str]:
    """Résumé lisible : « 12 objet(s) réseau », « 5 règle(s) de pare-feu », réglages..."""
    from collections import Counter
    n = Counter(o.balise for o in operations if o.balise in NOMS_BALISES)
    lignes = [f"{v} {NOMS_BALISES[k]}" for k, v in sorted(n.items(), key=lambda x: -x[1])]
    autres = sorted({o.nom for o in operations if o.balise not in NOMS_BALISES})
    if autres:
        lignes.append("réglages : " + ", ".join(autres))
    return lignes


def rapport_html(client: str, cible: str, date: str, journal: list[str], avertissements: list[str],
                 societe: str = "") -> str:
    import html as h
    couleurs = {"OK": "#1e8449", "ERREUR": "#c0392b", "ARRÊT": "#c0392b", "À FAIRE": "#d68910",
                "À VÉRIFIER": "#d68910", "SÉCURITÉ": "#c0392b", "NON FAIT": "#c0392b"}
    lignes = []
    for j in journal:
        etat = next((k for k in couleurs if j.startswith(k)), "")
        lignes.append(f'<tr><td style="color:{couleurs.get(etat, "#333")};font-weight:bold">{h.escape(etat)}</td>'
                      f'<td>{h.escape(j[len(etat):].strip())}</td></tr>')
    ok = sum(j.startswith("OK") for j in journal)
    ko = sum(j.startswith(("ERREUR", "ARRÊT", "NON FAIT")) for j in journal)
    aw = "".join(f"<li>{h.escape(a)}</li>" for a in avertissements)
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rapport de configuration</title><style>body{{font-family:Segoe UI,Arial,sans-serif;max-width:960px;margin:24px auto;padding:0 16px;color:#222;background:#fff}}
table{{border-collapse:collapse;width:100%}}td{{border-bottom:1px solid #eee;padding:6px;vertical-align:top}}.s{{color:#666}}</style></head>
<body><h1>Rapport de configuration du pare-feu</h1><p class="s">{h.escape(client)} — {h.escape(cible)} — {h.escape(date)}
{(" — réalisé par " + h.escape(societe)) if societe else ""}</p><p><b>{ok}</b> opération(s) réussie(s), <b>{ko}</b> échec(s).</p>
<table>{"".join(lignes)}</table>{f"<h2>Avertissements</h2><ul>{aw}</ul>" if aw else ""}</body></html>"""


# ----------------------------------------------------------------------------- sécurité avant / après
def photo_avant(api: SophosAPI, cfg: Configuration, chemin: Path) -> int:
    """Enregistre l'état actuel des types d'objets qui vont être modifiés (pour comparer ou revenir en arrière)."""
    etat = {}
    for balise in sorted({o.balise for o in cfg.operations}):
        try:
            etat[balise] = api.lire(balise)
        except ErreurConnexion:
            raise
        except ErreurAPI as exc:
            etat[balise] = f"lecture impossible : {exc}"
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(etat, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return len(etat)


def _cle_op(op: Operation) -> str:
    c = op.contenu
    for sous in ("TunnelPolicy", "Configuration", "ActiveDirectory"):
        if isinstance(c.get(sous), dict):
            c = c[sous]
    return str(c.get("Name") or c.get("Username") or c.get("ServerName") or "")


def verifier_presence(api: SophosAPI, operations: list[Operation]) -> list[Operation]:
    """Relit le pare-feu et renvoie les objets créés qu'on ne retrouve pas."""
    cache: dict[str, str] = {}
    absents = []
    for o in operations:
        cle = _cle_op(o)
        if o.mode != "creer" or o.existe_ok or not cle:
            continue
        if o.balise not in cache:
            try:
                cache[o.balise] = json.dumps(api.lire(o.balise), ensure_ascii=False, default=str)
            except ErreurAPI:
                cache[o.balise] = ""
        if json.dumps(cle, ensure_ascii=False) not in cache[o.balise]:
            absents.append(o)
    return absents


# ----------------------------------------------------------------------------- programme principal
def deployer(fichier: str, *, simulation=False, ip=None, port=None, utilisateur=None, mot_de_passe=None,
             verifier_certificat=False, continuer=False, secrets: dict[str, str] | None = None,
             confirmer=None, ip_pc_apres: str | None = None, seulement: list[str] | None = None,
             sans_modifier: bool = False, debug: bool = False) -> int:
    print(f"Lecture de {fichier}...")
    cfg = lire_classeur(fichier)
    if seulement:
        voulus = {x.strip().lower() for x in seulement}
        inconnus = voulus - {o.onglet.lower() for o in cfg.operations}
        if inconnus:
            print(f"{JAUNE}  Onglet(s) sans opération : {', '.join(sorted(inconnus))}{FIN}")
        cfg.operations = [o for o in cfg.operations if o.onglet.lower() in voulus or o.onglet == "Auto"]
    g = cfg.general
    client = g.get("Nom du client") or Path(fichier).stem
    print(f"Client : {GRAS}{client}{FIN} — {len(cfg.operations)} opération(s)\n")
    for w in cfg.avertissements:
        print(f"{JAUNE}  ! {w}{FIN}")
    for e in cfg.erreurs:
        print(f"{ROUGE}  ✘ {e}{FIN}")
    if cfg.erreurs and not continuer:
        print(f"\n{ROUGE}{len(cfg.erreurs)} erreur(s) dans le fichier : corrigez-les puis relancez "
              f"(ou ajoutez --continuer pour ignorer ces lignes).{FIN}")
        return 1

    if simulation:
        dossier = Path("simulation") / _fichier(client)
        dossier.mkdir(parents=True, exist_ok=True)
        for f in dossier.glob("*.xml"):
            f.unlink()
        for i, o in enumerate(cfg.operations, start=1):
            mode = {"creer": 'Set operation="add" (ou "update" s\'il existe)', "maj": 'Set operation="update"',
                    "patch": f'lecture de {o.balise} {o.cle or ""} puis Set operation="update" avec ces champs modifiés'}[o.mode]
            xml = f"<!-- {mode} -->\n{to_xml({o.balise: _remplacer(o.contenu, masquer=True)})}\n"
            (dossier / f"{i:03d}_{o.balise}_{_fichier(o.nom)}.xml").write_text(xml, encoding="utf-8")
            print(f"  {GRIS}{i:3d}.{FIN} {o.libelle}")
        n = len(secrets_de(cfg))
        if n:
            print(f"\n{n} mot(s) de passe seront demandés au lancement.")
        print(f"\n{VERT}Simulation terminée : rien n'a été envoyé. Requêtes XML dans {dossier}/{FIN}")
        return 0

    ip = ip or g["Adresse IP du pare-feu"]
    port = port or int(g["Port d'administration"] or 4444)
    utilisateur = utilisateur or g["Utilisateur admin"]
    mdp = mot_de_passe or os.environ.get("SOPHOS_MOT_DE_PASSE") or getpass.getpass(f"Mot de passe de « {utilisateur} » sur le pare-feu : ")
    api = SophosAPI(ip, utilisateur, mdp, port=port, verifier_certificat=verifier_certificat)
    print(f"Connexion à {ip}:{port}...")
    try:
        api.tester_connexion()
        print(f"{VERT}✔ Connecté{FIN}\n")
        print("Vérification des noms utilisés...")
        problemes = verifier_sur_pare_feu(api, cfg)
        changement_ip = _ip_de_connexion(api, cfg, ip)
    except ErreurAPI as exc:
        print(f"{ROUGE}✘ {exc}{FIN}")
        return 1
    if problemes:
        for p in problemes:
            print(f"{ROUGE}  ✘ {p}{FIN}")
        print(f"{JAUNE}Les opérations qui utilisent ces noms vont échouer.{FIN}")
        rep = confirmer("Continuer quand même ?") if confirmer else input("Continuer quand même ? (o/N) ").strip().lower() in ("o", "oui")
        if not rep:
            return 1
    else:
        print(f"{VERT}✔ Tous les noms sont connus{FIN}\n")

    horodatage = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    photo = Path("rapports") / f"{_fichier(client)}_{horodatage}_avant.json"
    try:
        n = photo_avant(api, cfg, photo)
        print(f"{VERT}✔ État actuel enregistré ({n} types d'objets) : {photo}{FIN}")
    except ErreurAPI as exc:
        print(f"{ROUGE}✘ Impossible de lire l'état actuel : {exc}{FIN}")
        return 1

    if debug:
        trace = Path("rapports") / f"{_fichier(client)}_{horodatage}_debug.log"
        fichier_trace = trace.open("a", encoding="utf-8")
        api.journal = lambda t: (fichier_trace.write(f"{dt.datetime.now():%H:%M:%S} {t}\n"), fichier_trace.flush())
        print(f"{GRIS}Journal technique (mots de passe masqués) : {trace}{FIN}")

    print(f"\n{GRAS}Ce qui va être fait :{FIN}")
    for ligne in resume_operations(cfg.operations):
        print(f"  - {ligne}")
    if sans_modifier:
        print(f"{JAUNE}  Mode prudent : les objets et réglages existants ne seront pas modifiés.{FIN}")
    print()

    demander_secrets(cfg, secrets)

    journal, nb_ok, nb_ko = [], 0, 0
    total = len(cfg.operations)
    reussies: list[Operation] = []
    reconnecte = False
    for o in cfg.operations:
        if o.etape == ETAPES["après"] and not reconnecte:
            reconnecte = True
            api2 = _reconnexion(api, changement_ip, ip_pc_apres, confirmer) if changement_ip else None
            if api2 is None:
                reste = [x for x in cfg.operations if x.etape == ETAPES["après"]]
                journal += [f"NON FAIT {x.libelle} (pas de reconnexion)" for x in reste]
                nb_ko += len(reste)
                print(f"{JAUNE}Relancez le script avec --ip {changement_ip.contenu['IPAddress'] if changement_ip else ''} "
                      f"pour terminer (le reste est déjà fait).{FIN}")
                break
            api = api2
        rang = f"{GRIS}[{cfg.operations.index(o) + 1}/{total}]{FIN}"
        if o.etape == ETAPES["fin"]:
            api.tentatives = 1     # la connexion va être coupée : inutile d'insister
        try:
            res, action = appliquer(api, o, sans_modifier=sans_modifier)
        except ErreurConnexion as exc:
            if o.etape == ETAPES["fin"]:   # changement de l'IP de connexion : coupure normale
                res, action = Resultat(True, "", ""), "appliqué (connexion coupée, c'est normal)"
            else:
                print(f"{ROUGE}✘ Connexion perdue : {exc}{FIN}")
                journal.append(f"ARRÊT  {o.libelle} : {exc}")
                nb_ko += 1
                break
        except ErreurAPI as exc:
            res, action = Resultat(False, "?", str(exc)), "erreur"
        if res.ok:
            nb_ok += 1
            reussies.append(o)
            print(f"{rang} {VERT}✔{FIN} {o.libelle} {GRIS}({action}){FIN}")
            journal.append(f"OK     {o.libelle} ({action})")
        elif o.facultatif:
            print(f"{rang} {JAUNE}! {o.libelle} — non fait automatiquement ({res.code} : {res.message}). "
                  f"À faire à la main : {o.conseil_echec}{FIN}")
            journal.append(f"À FAIRE {o.libelle} — {o.conseil_echec} ({res.code} : {res.message})")
        else:
            nb_ko += 1
            print(f"{rang} {ROUGE}✘ {o.libelle} — {res.code} : {res.message}{FIN}")
            journal.append(f"ERREUR {o.libelle} — {res.code} : {res.message}")

    print("\nVérification : relecture du pare-feu...")
    try:
        absents = verifier_presence(api, reussies)
    except ErreurAPI as exc:
        absents = []
        print(f"{JAUNE}  Relecture impossible : {exc}{FIN}")
    for o in absents:
        print(f"{JAUNE}  ! {o.libelle} : accepté par le pare-feu mais introuvable à la relecture{FIN}")
        journal.append(f"À VÉRIFIER {o.libelle} : introuvable à la relecture")
    if not absents:
        print(f"{VERT}  ✔ Tous les objets créés sont bien présents{FIN}")

    try:
        from .audit import CRITIQUE, executer
        constats, chemin_audit = executer(api, f"{api.url.split('//')[1].split('/')[0]}", client)
        critiques = [c for c in constats if c.niveau == CRITIQUE]
        print(f"\nContrôle de sécurité : {ROUGE if critiques else VERT}{len(critiques)} point(s) critique(s){FIN}"
              f" — rapport : {chemin_audit}")
        for c in critiques:
            print(f"{ROUGE}  ✘ {c.titre}{FIN}")
            journal.append(f"SÉCURITÉ (critique) {c.titre}")
    except ErreurAPI as exc:
        print(f"{JAUNE}  Contrôle de sécurité impossible : {exc}{FIN}")

    Path("rapports").mkdir(exist_ok=True)
    rapport = Path("rapports") / f"{_fichier(client)}_{horodatage}.txt"
    rapport.write_text(
        f"Client : {client}\nPare-feu : {ip}:{port}\nDate : {horodatage}\n"
        f"Réussis : {nb_ok}  Échecs : {nb_ko}\n\n" + "\n".join(journal) + "\n"
        + ("\nAvertissements :\n" + "\n".join(cfg.avertissements) + "\n" if cfg.avertissements else ""),
        encoding="utf-8")
    rapport_web = rapport.with_suffix(".html")
    from .parametres import charger as charger_parametres
    rapport_web.write_text(rapport_html(client, f"{ip}:{port}", horodatage, journal, cfg.avertissements,
                                        charger_parametres().get("societe", "")), encoding="utf-8")
    couleur = VERT if nb_ko == 0 else ROUGE
    print(f"\n{couleur}Terminé : {nb_ok} réussi(s), {nb_ko} échec(s).{FIN} Rapport : {rapport_web}")
    if changement_ip:
        print(f"{JAUNE}L'IP du pare-feu est maintenant {changement_ip.contenu['IPAddress']} : "
              f"remettez votre PC en DHCP (automatique) s'il le faut.{FIN}")
    return 0 if nb_ko == 0 else 2


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Paramétrage automatique d'un Sophos XGS à partir d'un fichier Excel.")
    p.add_argument("fichier", nargs="?", help="Fichier Excel du client")
    p.add_argument("--simulation", action="store_true", help="Vérifie le fichier et montre ce qui serait envoyé, sans rien envoyer")
    p.add_argument("--ip", help="IP du pare-feu (remplace celle du fichier)")
    p.add_argument("--port", type=int, help="Port d'administration (remplace celui du fichier)")
    p.add_argument("--utilisateur", help="Utilisateur admin (remplace celui du fichier)")
    p.add_argument("--verifier-certificat", action="store_true", help="Refuser les certificats auto-signés")
    p.add_argument("--lire", metavar="TYPE", help="Affiche les objets existants d'un type (ex. IPHost, FirewallRule, Zone, VLAN, Interface)")
    p.add_argument("--continuer", action="store_true", help="Ne pas s'arrêter s'il y a des erreurs dans le fichier")
    p.add_argument("--seulement", help="N'appliquer que ces onglets, séparés par des virgules (ex. Règles,Hôtes)")
    p.add_argument("--prudent", action="store_true", help="Ne rien modifier de ce qui existe déjà (création seulement)")
    p.add_argument("--debug", action="store_true", help="Enregistrer un journal technique (mots de passe masqués)")
    a = p.parse_args(argv)

    if a.lire:
        u = a.utilisateur or "admin"
        mdp = os.environ.get("SOPHOS_MOT_DE_PASSE") or getpass.getpass(f"Mot de passe de « {u} » : ")
        api = SophosAPI(a.ip or "172.16.16.16", u, mdp, port=a.port or 4444, verifier_certificat=a.verifier_certificat)
        try:
            print(to_xml({a.lire: api.lire(a.lire) or {}}))
        except ErreurAPI as exc:
            print(f"{ROUGE}{exc}{FIN}")
            return 1
        return 0
    if not a.fichier:
        p.error("indiquez le fichier Excel du client")
    if not Path(a.fichier).exists():
        print(f"{ROUGE}Fichier introuvable : {a.fichier}{FIN}")
        return 1
    return deployer(a.fichier, simulation=a.simulation, ip=a.ip, port=a.port, utilisateur=a.utilisateur,
                    seulement=a.seulement.split(",") if a.seulement else None, sans_modifier=a.prudent, debug=a.debug,
                    verifier_certificat=a.verifier_certificat, continuer=a.continuer)


def _fichier(nom: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in nom)[:60]


if __name__ == "__main__":
    sys.exit(main())
