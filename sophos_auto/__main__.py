"""Menu principal : python -m sophos_auto  (ou double-clic sur demarrer.bat)."""
from __future__ import annotations

import datetime as dt
import getpass
import os
import re
import sys
from pathlib import Path

from .assistant import (FICHE_COLLECTE, Retour, B, C, F, G, J, R, choix, conseil, info, oui_non, texte, titre,
                        _v_ip)

VERSION = "4.0"


def _pause():
    try:
        input("\nAppuyez sur Entrée pour revenir au menu...")
    except EOFError:
        pass


def _connexion_xgs(defaut_ip=None):
    from .api import SophosAPI
    from .parametres import charger as params
    p = params()
    ip = texte("Adresse IP du pare-feu", defaut_ip or p["ip_defaut"], valider=_v_ip)
    user = texte("Utilisateur admin", p["utilisateur_defaut"])
    mdp = os.environ.get("SOPHOS_MOT_DE_PASSE") or getpass.getpass(f"Mot de passe de « {user} » : ")
    return SophosAPI(ip, user, mdp), ip


# ----------------------------------------------------------------------------- actions
def action_assistant():
    from . import assistant
    assistant.main()


def action_appliquer():
    from .deployer import deployer
    f = _choisir_fichier_client()
    if deployer(f, simulation=True) != 0:
        return
    if not oui_non("Envoyer cette configuration au pare-feu ?", False):
        return
    prudent = oui_non("Pare-feu déjà en service : ne rien modifier de ce qui existe (création seulement) ?", False,
                      "Oui = seuls les objets absents sont créés ; les objets et réglages existants ne sont pas touchés. "
                      "Pratique pour ajouter des éléments chez un client sans risque.")
    seulement = None
    if oui_non("Appliquer tout le fichier ?", True, "Non = choisir les onglets à appliquer (ex. seulement les Règles)."):
        pass
    else:
        seulement = [x.strip() for x in texte("Onglets à appliquer, séparés par des virgules", "Règles").split(",")]
    deployer(f, sans_modifier=prudent, seulement=seulement)


def action_audit():
    from .api import ErreurAPI
    from .audit import afficher, executer
    titre("CONTRÔLE DE SÉCURITÉ (lecture seule, rien n'est modifié)")
    api, ip = _connexion_xgs()
    client = texte("Nom du client (pour le rapport)", "", vide_ok=True)
    try:
        constats, chemin = executer(api, ip, client)
    except ErreurAPI as exc:
        print(f"{R}✘ {exc}{F}")
        return
    afficher(constats)
    print(f"\n{G}Rapport à remettre au client : {chemin}{F}")


def _choisir_fichier_client(question="Quel client ?"):
    fichiers = sorted(Path("clients").glob("*.xlsx")) if Path("clients").exists() else []
    f = choix(question, [(str(x), x.stem) for x in fichiers] + [("autre", "Un autre fichier (je donne le chemin)")], 1) \
        if fichiers else "autre"
    if f == "autre":
        f = texte("Chemin du fichier Excel", valider=lambda t: None if Path(t).exists() else "Fichier introuvable.")
    return f


def action_conformite():
    from .api import ErreurAPI
    from .conformite import afficher, verifier
    from .modele import lire_classeur
    titre("CONFORMITÉ : LE PARE-FEU CORRESPOND-IL À SON FICHIER ? (lecture seule)")
    f = _choisir_fichier_client()
    api, _ = _connexion_xgs(lire_classeur(f).general.get("Adresse IP du pare-feu") or "172.16.16.16")
    try:
        ecarts, n = verifier(api, f)
    except (ErreurAPI, ValueError) as exc:
        print(f"{R}✘ {exc}{F}")
        return
    afficher(ecarts, n)
    from .conformite import enregistrer_rapport
    client = lire_classeur(f).general.get("Nom du client") or Path(f).stem
    print(f"{G}Rapport : {enregistrer_rapport(ecarts, n, client, api.url.split('//')[1].split('/')[0])}{F}")


def action_restaurer():
    from .api import ErreurAPI
    from .restaurer import restaurer
    titre("REVENIR EN ARRIÈRE")
    info("Avant chaque application, l'état du pare-feu est enregistré. Choisissez l'application à annuler : les "
         "objets créés depuis seront supprimés et les réglages modifiés remis comme avant.")
    photos = sorted(Path("rapports").glob("*_avant.json"), reverse=True) if Path("rapports").exists() else []
    if not photos:
        print(f"{J}Aucun état enregistré dans le dossier rapports.{F}")
        return
    f = choix("Quelle application annuler ?", [(str(x), x.stem.replace("_avant", "")) for x in photos[:20]], 1)
    api, _ = _connexion_xgs()
    try:
        restaurer(f, api, confirmer=lambda q: oui_non(q, False))
    except ErreurAPI as exc:
        print(f"{R}✘ {exc}{F}")


def action_documentation():
    from .documentation import generer
    f = _choisir_fichier_client("Dossier technique de quel client ?")
    print(f"{G}✔ Dossier créé : {generer(f)}{F}  (à ouvrir dans un navigateur, imprimable en PDF)")


def action_diagnostic():
    from .diagnostic import diagnostiquer
    from .parametres import charger as params
    titre("DIAGNOSTIC DE CONNEXION")
    info("Vérifie étape par étape ce qui empêche de se connecter au pare-feu : câble, adresse, API, droits.")
    p = params()
    ip = texte("Adresse IP du pare-feu", p["ip_defaut"], valider=_v_ip)
    port = int(texte("Port d'administration", "4444", valider=lambda t: None if t.isdigit() else "Nombre attendu."))
    etapes = diagnostiquer(ip, port, texte("Utilisateur admin", p["utilisateur_defaut"]))
    if all(e[0] for e in etapes):
        print(f"\n{G}Tout est prêt : vous pouvez appliquer une configuration.{F}")
    else:
        print(f"\n{J}Corrigez le point en rouge, puis relancez le diagnostic.{F}")


def action_dupliquer():
    """Nouveau client à partir d'un client existant (mêmes objets et règles, infos client effacées)."""
    from openpyxl import load_workbook
    from .assistant import _slug
    from .schema import DEMANDER, GENERAL
    titre("NOUVEAU CLIENT À PARTIR D'UN CLIENT EXISTANT")
    source = _choisir_fichier_client("Quel client recopier ?")
    nom = texte("Nom du nouveau client")
    cible = Path("clients") / f"{_slug(nom)}.xlsx"
    if cible.exists() and not oui_non(f"{cible} existe déjà. Le remplacer ?", False):
        return
    wb = load_workbook(source)
    effacer = {"Adresse publique du pare-feu", "AD : adresse IP", "AD : domaine", "AD : nom NetBIOS",
               "AD : compte de service", "Central : e-mail du compte", "Lieu", "Domaine pour les clients VPN",
               "DNS pour les clients VPN", "E-mail de sauvegarde"}
    secrets = {prm for prm, _, _, _, sec in GENERAL if sec}
    for row in wb["Général"].iter_rows(min_row=2):
        cle = row[0].value
        if cle == "Nom du client":
            row[1].value = nom
        elif cle == "Nom d'hôte du pare-feu":
            row[1].value = f"fw-{_slug(nom)}"
        elif cle in effacer:
            row[1].value = ""
        elif cle in secrets:
            row[1].value = DEMANDER
    from .schema import SECRETS
    for onglet, colonne in SECRETS:
        if onglet in wb.sheetnames:
            ws = wb[onglet]
            entetes = [c.value for c in ws[1]]
            if colonne in entetes:
                i = entetes.index(colonne) + 1
                for r in range(2, ws.max_row + 1):
                    if ws.cell(r, i).value:
                        ws.cell(r, i).value = DEMANDER
    cible.parent.mkdir(exist_ok=True)
    wb.save(cible)
    print(f"{G}✔ Créé : {cible}{F}")
    conseil("Relisez les onglets Interfaces, VLAN, DHCP, Hôtes, VPN et Redirections : les adresses IP sont celles "
            "de l'ancien client. Les mots de passe ont été remis à *demander*.")


def action_parametres():
    from .parametres import charger, enregistrer
    titre("VOS PARAMÈTRES")
    info("Ces valeurs sont proposées par défaut et le nom de votre société apparaît dans les rapports remis aux "
         "clients. Aucun mot de passe n'est enregistré.")
    p = charger()
    enregistrer({
        "societe": texte("Nom de votre société", p["societe"], vide_ok=True),
        "email_support": texte("E-mail de votre support (alertes des pare-feux)", p["email_support"], vide_ok=True),
        "ip_defaut": texte("IP du pare-feu proposée par défaut", p["ip_defaut"], valider=_v_ip),
        "utilisateur_defaut": texte("Compte admin proposé par défaut", p["utilisateur_defaut"]),
        "fuseau_defaut": texte("Fuseau horaire par défaut", p["fuseau_defaut"]),
        "prefixe_admin": texte("Identifiant du compte administrateur nominatif proposé", p["prefixe_admin"]),
    })
    print(f"{G}✔ Paramètres enregistrés (parametres.json).{F}")


def action_lire():
    from .api import ErreurAPI, to_xml
    types = [("FirewallRule", "Règles de pare-feu"), ("NATRule", "Règles NAT"), ("IPHost", "Hôtes"),
             ("Services", "Services"), ("Zone", "Zones"), ("Interface", "Interfaces"), ("VLAN", "VLAN"),
             ("DHCPServer", "Serveurs DHCP"), ("User", "Comptes"), ("VPNIPSecConnection", "VPN IPsec"),
             ("WebFilterPolicy", "Stratégies de filtrage web"), ("IPSPolicy", "Stratégies IPS"),
             ("VPNProfile", "Profils IPsec"), ("autre", "Autre (je donne le nom technique)")]
    t = choix("Quels objets afficher ?", types, 1)
    if t == "autre":
        t = texte("Nom technique (ex. GatewayConfiguration)")
    api, _ = _connexion_xgs()
    try:
        print(to_xml({t: api.lire(t) or {}}))
    except ErreurAPI as exc:
        print(f"{R}✘ {exc}{F}")


def action_collecte():
    print(FICHE_COLLECTE)
    Path("fiche_collecte.txt").write_text(FICHE_COLLECTE.strip() + "\n", encoding="utf-8")
    print(f"{G}Enregistrée dans fiche_collecte.txt (à imprimer ou envoyer au client).{F}")


def action_modele():
    from .creer_modele import creer
    print(f"{G}Modèle créé : {creer('modele_client.xlsx')}{F}")


# ----------------------------------------------------------------------------- Sophos Central
def _central():
    from .central import ErreurCentral, SophosCentral
    titre("SOPHOS CENTRAL")
    info("Il faut des identifiants API Sophos Central : dans Central, Paramètres globaux > Identifiants API "
         "(API Credentials) > Ajouter, rôle « Service Principal Firewall » conseillé. Ils ne sont jamais enregistrés "
         "par l'outil (vous pouvez aussi les mettre dans les variables SOPHOS_CENTRAL_ID et SOPHOS_CENTRAL_SECRET).")
    cid = os.environ.get("SOPHOS_CENTRAL_ID") or texte("Client ID")
    secret = os.environ.get("SOPHOS_CENTRAL_SECRET") or getpass.getpass("Client secret (saisie masquée) : ")
    c = SophosCentral(cid, secret)
    try:
        c.connecter()
        if c.type_compte != "tenant":
            clients = c.clients()
            if not clients:
                raise ErreurCentral("Aucun client trouvé sur ce compte.")
            filtre = texte("Nom du client (ou une partie, Entrée = tous)", "", vide_ok=True).lower()
            liste = [x for x in clients if filtre in x.nom.lower()] or clients
            choisi = choix("Quel client ?", [(str(i), x.nom) for i, x in enumerate(liste[:40])], 1)
            c.choisir_client(liste[int(choisi)])
        print(f"{G}✔ Connecté à Sophos Central ({c.client.nom}){F}")
    except ErreurCentral as exc:
        print(f"{R}✘ {exc}{F}")
        return None
    return c


def _afficher_pare_feux(pfs):
    if not pfs:
        print(f"{J}Aucun pare-feu sur ce compte.{F}")
        return
    print(f"\n   {'N°':<4}{'Nom':<28}{'Modèle':<10}{'Firmware':<26}{'Connecté':<10}IP publique")
    for i, p in enumerate(pfs, 1):
        etat = f"{G}oui{F}" if p.connecte else f"{R}non{F}"
        print(f"   {i:<4}{p.nom[:27]:<28}{p.modele[:9]:<10}{p.firmware[:25]:<26}{etat:<19}{', '.join(p.ip_publiques)}")


def _inventaire(c, pfs) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from .central import firmware_compatible
    wb = Workbook()
    ws = wb.active
    ws.title = "Pare-feux"
    ws.append(["Nom", "N° de série", "Modèle", "Firmware", "Export/import Central possible", "Connecté", "IP publique"])
    for cell in ws[1]:
        cell.font, cell.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F4E78")
    for p in pfs:
        compat = firmware_compatible(p.firmware)
        ws.append([p.nom, p.serie, p.modele, p.firmware, {True: "Oui", False: "Non (SFOS 22.0 MR2 minimum)",
                   None: "?"}[compat], "Oui" if p.connecte else "Non", ", ".join(p.ip_publiques)])
    for col, largeur in zip("ABCDEFG", (28, 18, 12, 26, 30, 10, 30)):
        ws.column_dimensions[col].width = largeur
    ws.auto_filter.ref = ws.dimensions
    Path("rapports").mkdir(exist_ok=True)
    nom = re.sub(r"[^A-Za-z0-9_-]", "_", c.client.nom if c.client else "central")
    f = Path("rapports") / f"inventaire_{nom}_{dt.datetime.now():%Y-%m-%d}.xlsx"
    wb.save(f)
    return f


def _verifier_firmware(pfs, role: str) -> bool:
    from .central import firmware_compatible
    anciens = [p for p in pfs if firmware_compatible(p.firmware) is False]
    for p in anciens:
        print(f"{R}   ✘ {p.nom} ({role}) : firmware {p.firmware} — l'export/import Central demande SFOS 22.0 MR2 "
              f"ou plus récent. Mettez-le à jour depuis Central d'abord.{F}")
    return not anciens


def _choisir_pare_feux(pfs, question, plusieurs=False):
    _afficher_pare_feux(pfs)
    while True:
        rep = texte(question + (" (numéros séparés par des virgules)" if plusieurs else ""))
        try:
            n = [int(x) for x in re.split(r"[,; ]+", rep) if x]
            if n and all(1 <= x <= len(pfs) for x in n) and (plusieurs or len(n) == 1):
                return [pfs[x - 1] for x in n]
        except ValueError:
            pass
        print(f"{J}   Numéro(s) entre 1 et {len(pfs)}.{F}")


def firmware_compatible_ordre(source, cibles) -> bool | None:
    """Faux si une cible a un firmware plus ancien que le modèle (comparaison des numéros)."""
    def v(f):
        m = re.search(r"(\d+)\.(\d+)\.?(\d*)(?:[ .-]*MR[- ]?(\d+))?", f or "", re.IGNORECASE)
        return tuple(int(x or 0) for x in m.groups()) if m else None
    vs = v(source.firmware)
    if vs is None:
        return None
    return all(v(c.firmware) is None or v(c.firmware) >= vs for c in cibles)


def _rappel(etat):
    print(f"{C}   … {etat}{F}")


def _fichier_sauvegarde(pf) -> Path:
    nom = re.sub(r"[^A-Za-z0-9_-]", "_", pf.nom)
    return Path("sauvegardes") / f"{nom}_{pf.serie}_{dt.datetime.now():%Y-%m-%d_%H%M%S}.tar"


def action_central():
    from .central import ErreurCentral
    c = _central()
    if not c:
        return
    while True:
        a = choix("Que voulez-vous faire dans Sophos Central ?", [
            ("liste", "Voir mes pare-feux (modèle, firmware, connecté, IP publique)"),
            ("inventaire", "Inventaire des pare-feux dans un fichier Excel"),
            ("tous", "Sauvegarder tous les pare-feux d'un coup"),
            ("export", "Sauvegarder la configuration d'un pare-feu (fichier .tar sur ce PC)"),
            ("copie", "Copier la configuration d'un pare-feu « modèle » vers d'autres pare-feux"),
            ("import", "Envoyer un fichier de configuration (.tar) vers des pare-feux"),
            ("fin", "Revenir au menu principal")], 1,
            "L'export et l'import passent par Central : pas besoin d'être sur place. Il faut SFOS 22.0 MR2 ou plus "
            "récent, des pare-feux gérés par Central et un abonnement (ou contrat de support) actif.")
        if a == "fin":
            return
        try:
            pfs = c.pare_feux()
            if a == "liste":
                _afficher_pare_feux(pfs)
            elif a == "inventaire":
                print(f"{G}✔ Inventaire : {_inventaire(c, pfs)}{F}")
            elif a == "tous":
                for pf, r in c.sauvegarder_tous(Path("sauvegardes"), rappel=_rappel):
                    print(f"   {G + '✔' if isinstance(r, Path) else J + '!'}{F} {pf.nom} : {r}")
            elif a == "export":
                if not pfs:
                    continue
                pf = _choisir_pare_feux(pfs, "Quel pare-feu sauvegarder ?")[0]
                if not _verifier_firmware([pf], "à sauvegarder"):
                    continue
                f = c.exporter(pf.id, _fichier_sauvegarde(pf), rappel=_rappel)
                print(f"{G}✔ Configuration enregistrée : {f}{F}")
                conseil("Ce fichier contient toute la configuration du client : rangez-le dans un endroit protégé.")
            elif a in ("copie", "import"):
                _importer(c, pfs, depuis_modele=(a == "copie"))
        except ErreurCentral as exc:
            print(f"{R}✘ {exc}{F}")


def _importer(c, pfs, depuis_modele: bool):
    if not pfs:
        return
    if depuis_modele:
        info("Principe : vous configurez une fois un pare-feu « modèle » avec vos réglages habituels (objets, "
             "services, règles, protections...). Ses réglages sont ensuite copiés sur les pare-feux choisis. "
             "Les spécificités de chaque client se font ensuite avec l'assistant.")
        source = _choisir_pare_feux(pfs, "Quel est le pare-feu modèle ?")[0]
        quoi = choix("Que copier ?", [
            ("tout", "Toute la configuration"),
            ("partiel", "Seulement les objets et règles (hôtes, services, règles, NAT, stratégies)")], 2,
            "« Tout » copie aussi les interfaces et adresses IP : à réserver à un boîtier identique qui remplace "
            "l'autre. Pour un nouveau client, copiez seulement les objets et règles.")
    cibles = [p for p in _choisir_pare_feux(pfs, "Vers quel(s) pare-feu(x) ? (25 maximum)", plusieurs=True)]
    if depuis_modele:
        cibles = [p for p in cibles if p.id != source.id]
    if not _verifier_firmware(([source] if depuis_modele else []) + cibles, "concerné"):
        return
    if depuis_modele and firmware_compatible_ordre(source, cibles) is False:
        print(f"{R}   ✘ Les cibles doivent avoir un firmware égal ou plus récent que le modèle ({source.firmware}).{F}")
        return
    hors_ligne = [p.nom for p in cibles if not p.connecte]
    if hors_ligne:
        print(f"{J}   Non connectés à Central (l'import échouera) : {', '.join(hors_ligne)}{F}")
    print(f"\n{B}Avant d'importer :{F}")
    print("   - les pare-feux cibles doivent avoir un firmware égal ou plus récent que le fichier ;")
    print("   - ce qui existe dans le fichier remplace la configuration actuelle (rien n'est supprimé) ;")
    print("   - sans la « clé maître de stockage sécurisé » (SSMK), les mots de passe et données sensibles "
          "ne sont pas importés.")
    if not oui_non(f"Importer vers {len(cibles)} pare-feu(x) : {', '.join(p.nom for p in cibles)} ?", False):
        return
    if oui_non("Sauvegarder d'abord la configuration actuelle de chaque cible (conseillé) ?", True):
        for p in cibles:
            print(f"   Sauvegarde de {p.nom}...")
            print(f"{G}   ✔ {c.exporter(p.id, _fichier_sauvegarde(p), rappel=_rappel)}{F}")
    if depuis_modele:
        entites = None if quoi == "tout" else ["IPHost", "IPHostGroup", "FQDNHost", "FQDNHostGroup", "Services",
                                                "ServiceGroup", "FirewallRule", "FirewallRuleGroup", "NATRule",
                                                "WebFilterPolicy", "ApplicationFilterPolicy", "IPSPolicy"]
        fichier = c.exporter(source.id, _fichier_sauvegarde(source), entites, rappel=_rappel)
        print(f"{G}   ✔ Configuration du modèle exportée : {fichier}{F}")
    else:
        fichier = Path(texte("Chemin du fichier .tar", valider=lambda t: None if Path(t).exists() else "Fichier introuvable."))
    ssmk = getpass.getpass("Clé maître SSMK (Entrée si vous ne l'avez pas) : ")
    resultat = c.importer(fichier, [p.id for p in cibles], ssmk, rappel=_rappel)
    elements = resultat.get("items") if isinstance(resultat, dict) else None
    for e in elements or []:
        nom = next((p.nom for p in cibles if p.id == e.get("firewallId") or p.id == e.get("id")), e.get("firewallId", "?"))
        ok = str(e.get("result", e.get("status", ""))).lower() in ("success", "finished")
        print(f"   {G + '✔' if ok else R + '✘'}{F} {nom} : {e.get('result') or e.get('status')} {e.get('message', '')}")
    print(f"{G}Import terminé.{F} Vérifiez chaque pare-feu dans l'interface : un statut « succès » confirme le "
          f"traitement par Central, pas que tout fonctionne.")


# ----------------------------------------------------------------------------- menu
MENU = [
    ("assistant", "Nouveau client, ou reprendre une configuration en cours (assistant)", action_assistant),
    ("dupliquer", "Nouveau client à partir d'un client existant", action_dupliquer),
    ("diagnostic", "Diagnostic : pourquoi je n'arrive pas à me connecter au pare-feu ?", action_diagnostic),
    ("appliquer", "Appliquer un fichier client sur un pare-feu", action_appliquer),
    ("audit", "Contrôle de sécurité d'un pare-feu (rapport pour le client)", action_audit),
    ("conformite", "Vérifier qu'un pare-feu correspond toujours à son fichier client", action_conformite),
    ("restaurer", "Revenir en arrière : annuler une application", action_restaurer),
    ("central", "Sophos Central : liste, sauvegarde, copie d'un pare-feu modèle", action_central),
    ("documentation", "Dossier technique d'un client (page à remettre au client)", action_documentation),
    ("collecte", "Liste des informations à demander au client avant l'intervention", action_collecte),
    ("lire", "Voir les objets d'un pare-feu (règles, hôtes, VPN...)", action_lire),
    ("modele", "Créer un fichier Excel vierge (modèle)", action_modele),
    ("parametres", "Mes paramètres (nom de ma société, valeurs par défaut)", action_parametres),
    ("quitter", "Quitter", None),
]


def main() -> int:
    if os.name == "nt":
        os.system("")
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(errors="replace")   # jamais de plantage sur un caractère non affichable
        except (AttributeError, ValueError):
            pass
    while True:
        titre(f"SOPHOS XGS — OUTIL DE CONFIGURATION (v{VERSION})")
        try:
            c = choix("Que voulez-vous faire ? (q pour quitter)", [(k, lib) for k, lib, _ in MENU], 1)
            if c == "quitter":
                return 0
            next(f for k, _, f in MENU if k == c)()
        except Retour:
            continue
        except KeyboardInterrupt:
            print(f"\n{J}Action annulée.{F}")
            continue
        _pause()


if __name__ == "__main__":
    sys.exit(main())
