"""Menu principal : python -m sophos_auto  (mode texte ; la fenêtre s'ouvre avec SophosXGS.bat)."""
from __future__ import annotations

import datetime as dt
import getpass
import os
import re
import sys
from pathlib import Path

from .assistant import (FICHE_COLLECTE, Retour, B, C, F, G, GR, J, R, choix, conseil, info, oui_non, texte, titre,
                        _v_ip)

from . import __version__ as VERSION


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


def action_appliquer(fichier: str | None = None):
    from .deployer import deployer, repeter
    f = fichier or _choisir_fichier_client()
    if deployer(f, simulation=True) != 0:
        return
    if oui_non("Faire d'abord une répétition sur le pare-feu d'entraînement (sans aucun risque) ?", False,
               "La configuration est envoyée en entier sur un faux pare-feu, dans l'outil : vous voyez ce qui serait "
               "refusé. Rien ne part vers le vrai pare-feu."):
        repeter(f)
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
    from .assistant import annoncer_fichiers, page_et_pdf
    annoncer_fichiers([(f"Rapport de sécurité ({lib})", x) for lib, x in page_et_pdf(chemin)])


def _choisir_fichier_client(question="Quel client ?"):
    fichiers = sorted(Path("clients").glob("*.xlsx")) if Path("clients").exists() else []
    f = choix(question, [(str(x), x.stem) for x in fichiers] + [("autre", "Un autre fichier (je donne le chemin)")], 1) \
        if fichiers else "autre"
    if f == "autre":
        from .assistant import choisir_fichier
        f = choisir_fichier("Fichier Excel du client", [("Fichier Excel", "*.xlsx")])
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
    from .assistant import annoncer_fichiers, page_et_pdf
    page = generer(f)
    print(f"{G}✔ Dossier créé : {page}{F}  (à ouvrir dans un navigateur)")
    annoncer_fichiers([(f"Dossier technique ({lib})", x) for lib, x in page_et_pdf(page)])


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
    from . import historique
    historique.enregistrer(nom, "duplication", f"à partir de {Path(source).stem}", fichier=cible)
    conseil("Relisez les onglets Interfaces, VLAN, DHCP, Hôtes, VPN et Redirections : les adresses IP sont celles "
            "de l'ancien client. Les mots de passe ont été remis à *demander*.")


def action_intervention():
    from .intervention import guider
    guider()


def action_reprise():
    from . import import_config
    from .assistant import choisir_fichier
    titre("REPRENDRE L'EXISTANT (ancien pare-feu ou inventaire)")
    info("Ajoute au fichier d'un client ce qui existe déjà : équipements, redirections de ports, adresses réservées. "
         "Vous relisez ensuite le fichier Excel avant de l'envoyer.")
    source = choix("D'où vient l'existant ?", [
        ("fortinet", "Sauvegarde d'un pare-feu Fortinet / FortiGate (fichier .conf)"),
        ("inventaire", "Un inventaire : fichier CSV ou Excel avec au moins un nom et une adresse IP (export GLPI...)")], 1,
        "FortiGate : Système > Configuration > Sauvegarde, fichier non chiffré. Inventaire : une ligne de titres "
        "(Nom, IP, et si possible MAC), puis une ligne par appareil.")
    if source == "fortinet":
        f = choisir_fichier("Fichier de sauvegarde du FortiGate", [("Sauvegarde FortiGate", "*.conf"), ("Texte", "*.txt")])
        try:
            reprise = import_config.lire_fortinet(Path(f).read_text(encoding="utf-8", errors="replace"))
        except OSError as exc:
            print(f"{R}✘ {exc}{F}")
            return
    else:
        f = choisir_fichier("Fichier d'inventaire", [("Inventaire", "*.csv *.xlsx"), ("CSV", "*.csv"), ("Excel", "*.xlsx")])
        try:
            reprise = import_config.lire_inventaire(f)
        except (ValueError, OSError) as exc:
            print(f"{R}✘ {exc}{F}")
            return
    print(f"{G}Trouvé : {reprise.resume()}{F}")
    for x in reprise.remarques:
        print(f"{J}  ! {x}{F}")
    if not (reprise.hotes or reprise.redirections or reprise.reservations):
        return
    client = _choisir_fichier_client("Dans quel fichier client les ajouter ?")
    for x in import_config.ajouter_au_classeur(client, reprise):
        print(f"  {G}+{F} {x}")
    if reprise.lan:
        print(f"{J}  Réseau local de l'ancien pare-feu : {reprise.lan}. Pour garder les mêmes adresses, mettez-la dans "
              f"l'onglet Interfaces (Port1).{F}")
    from .garde_fous import afficher, verifier
    constats = verifier(client)
    if constats:
        print(f"\n{B}Contrôle du fichier :{F}")
        afficher(constats)


def action_verification():
    from .verification import verifier_services
    titre("VÉRIFIER QUE TOUT FONCTIONNE CHEZ LE CLIENT")
    info("Votre PC doit être branché sur le réseau du client, derrière le pare-feu (comme un PC du client).")
    f = _choisir_fichier_client()
    from .modele import lire_classeur
    verifier_services(f, lire_classeur(f).general.get("Nom du client") or Path(f).stem)


def action_analyse_reseau():
    from . import reseau
    titre("ANALYSE DU RÉSEAU DU CLIENT (rien n'est modifié)")
    info("Branchez votre PC sur le réseau du client, comme un PC normal (sur la box ou un switch). L'outil regarde "
         "l'équipement actuel vers Internet et les appareils présents. Environ 15 secondes.")
    an = reseau.analyser(lambda t: print(f"   {t}"))
    for ligne in an.resume():
        print(f"  {ligne}")
    if an.pare_feux:
        print(f"{G}Pare-feu Sophos trouvé : {', '.join(an.pare_feux)}{F}")


def action_questionnaire():
    from . import questionnaire
    from .assistant import annoncer_fichiers, choisir_fichier
    from .parametres import charger
    titre("QUESTIONNAIRE À ENVOYER AU CLIENT")
    info("Le client répond à une douzaine de questions simples avant votre venue, dans son navigateur. Ses "
         "réponses sont ensuite proposées d'avance dans l'assistant.")
    c = choix("Que voulez-vous faire ?", [
        ("creer", "Créer le questionnaire à envoyer au client (une page web à joindre à un e-mail)"),
        ("importer", "Importer les réponses renvoyées par le client (fichier reponses_….json)")], 1)
    if c == "creer":
        f = questionnaire.generer(societe=charger().get("societe", ""))
        print(f"{G}✔ Questionnaire créé : {f}{F}")
        print("Envoyez ce fichier au client par e-mail. Il l'ouvre, répond, puis clique sur « Enregistrer mes réponses »"
              " et vous renvoie le petit fichier obtenu.")
        annoncer_fichiers([("Questionnaire (à envoyer au client)", str(f))])
    else:
        f = choisir_fichier("Fichier de réponses du client", [("Réponses du questionnaire", "*.json")])
        try:
            nom, cible = questionnaire.importer(f)
        except (ValueError, OSError) as exc:
            print(f"{R}✘ {exc}{F}")
            return
        print(f"{G}✔ Réponses de « {nom} » enregistrées. Elles seront proposées au lancement de l'assistant.{F}")


def action_profil():
    from . import questionnaire
    titre("PROFIL DE VOTRE SOCIÉTÉ (réponses proposées d'avance)")
    profil = questionnaire.lire_profil()
    if not profil:
        info("Aucun profil pour l'instant. À la fin de l'assistant, répondez « Oui » à « Garder vos choix comme "
             "réponses proposées » : vos choix habituels seront proposés aux clients suivants.")
        return
    for q, v in profil.items():
        print(f"  {C}•{F} {q} → {B}{'Oui' if v is True else 'Non' if v is False else v}{F}")
    if oui_non("Effacer ce profil ?", False):
        questionnaire.effacer_profil()
        print(f"{G}✔ Profil effacé.{F}")


def action_statistiques():
    from .statistiques import difficultes
    titre("QUESTIONS OÙ L'ON HÉSITE LE PLUS")
    info("Compté sur ce poste (ou le dossier partagé) : questions posées, aides demandées, réponses refusées, retours "
         "en arrière. Les réponses elles-mêmes ne sont jamais enregistrées.")
    lignes = difficultes()
    if not lignes:
        print(f"{G}Pas encore assez d'utilisations.{F}")
        return
    for q, c, score in lignes:
        print(f"  {J}{score:4.1f}{F}  {q}  {GR}(posée {c.get('posee', 0)}, aide {c.get('aide', 0)}, "
              f"refusée {c.get('erreur', 0)}, retour {c.get('retour', 0)}){F}")


def action_tableau():
    from .assistant import annoncer_fichiers, page_et_pdf
    from .tableau import lignes, page
    titre("TABLEAU DE BORD DE VOS CLIENTS")
    tous = lignes()
    if not tous:
        print(f"{J}Aucun client dans l'historique pour l'instant.{F}")
        return
    symbole = {"rouge": f"{R}● IMPORTANT{F}", "orange": f"{J}● à prévoir{F}", "vert": f"{G}● OK{F}"}
    for l in tous:
        note = f" — sécurité {l.note}/100" if l.note is not None else ""
        print(f"  {symbole[l.etat]}  {B}{l.client}{F} — {l.date} {l.derniere}{note}")
        for r in l.rappels:
            print(f"        {GR}→ {r}{F}")
    f = page()
    annoncer_fichiers([(f"Tableau de bord ({lib})", x) for lib, x in page_et_pdf(f)])


def action_compte_rendu():
    from . import historique
    from .assistant import annoncer_fichiers, page_et_pdf, signature
    from .compte_rendu import generer, lire_traits
    titre("COMPTE RENDU D'INTERVENTION À FAIRE SIGNER")
    noms = historique.clients()
    if not noms:
        print(f"{J}Aucune intervention enregistrée pour l'instant.{F}")
        return
    client = choix("Pour quel client ?", [(n, n) for n in reversed(noms)], 1) if len(noms) > 1 else noms[0]
    remarques = texte("Remarques à ajouter (facultatif)", "", vide_ok=True)
    signataire = texte("Nom de la personne qui signe (le client)", "", vide_ok=True)
    traits = lire_traits(signature("Signature du client")) if signataire else []
    f = generer(client, signataire, traits, remarques)
    print(f"{G}✔ Compte rendu créé : {f}{F}")
    annoncer_fichiers([(f"Compte rendu ({lib})", x) for lib, x in page_et_pdf(f)])


def action_rapport_mensuel():
    from . import planification
    titre("RAPPORT MENSUEL AUTOMATIQUE")
    info("Le 1er de chaque mois à 8 h, Windows prépare tout seul le tableau de bord de vos clients et la liste des "
         "rappels, dans le dossier rapports. Le PC doit être allumé ; aucun pare-feu n'est contacté.")
    actif = planification.existe()
    print(f"  État : {G + 'activé' if actif else J + 'désactivé'}{F}")
    c = choix("Que voulez-vous faire ?", [("faire", "Préparer le rapport maintenant"),
                                          ("activer" if not actif else "desactiver",
                                           "Activer le rapport automatique" if not actif else "Désactiver le rapport automatique"),
                                          ("rien", "Rien")], 1)
    if c == "faire":
        f = planification.rapport_mensuel()
        print(f"{G}✔ Rapport : {f}{F}")
        from .assistant import annoncer_fichiers
        annoncer_fichiers([("Rapport mensuel", str(f))])
    elif c in ("activer", "desactiver"):
        ok, message = planification.creer() if c == "activer" else planification.supprimer()
        print(f"{G + '✔ Fait.' if ok else R + '✘ ' + message}{F}")


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
        "modele_nom_pare_feu": texte("Nom proposé pour le pare-feu ({client} = nom du client)", p["modele_nom_pare_feu"]),
        "modele_wifi": texte("Nom proposé pour le Wi-Fi salariés ({CLIENT} = nom du client en majuscules)",
                             p["modele_wifi"]),
        "modele_wifi_invites": texte("Nom proposé pour le Wi-Fi invités", p["modele_wifi_invites"]),
        "mise_a_jour_auto": oui_non("Installer automatiquement les nouvelles versions au démarrage ?",
                                    bool(p["mise_a_jour_auto"]),
                                    "Oui : à chaque démarrage, le programme vérifie sur GitHub et s'installe tout seul "
                                    "(fichier vérifié, ancienne version gardée en secours). Non : il vous prévient seulement."),
    })
    print(f"{G}✔ Paramètres de l'équipe enregistrés (parametres.json).{F}")

    from . import poste
    titre("RÉGLAGES DE CE POSTE")
    q = poste.charger()
    info("Le dossier partagé permet à plusieurs techniciens de travailler sur les mêmes clients : mettez-y par "
         "exemple un dossier réseau (\\\\serveur\\it\\SophosXGS) ou un dossier OneDrive / SharePoint synchronisé. "
         "Les fichiers clients, rapports, sauvegardes, l'historique et les paramètres de l'équipe y seront rangés.")
    partage = texte("Dossier partagé entre techniciens (Entrée = aucun, - pour l'enlever)", q["dossier_partage"],
                    vide_ok=True)
    partage = "" if partage == "-" else partage
    poste.enregistrer({
        "technicien": texte("Votre nom (affiché dans l'historique des interventions)", q["technicien"], vide_ok=True),
        "dossier_partage": partage,
        "theme": choix("Thème de la fenêtre", [("clair", "Clair"), ("sombre", "Sombre")],
                       1 if q["theme"] == "clair" else 2),
        "taille_texte": int(texte("Taille du texte (8 à 20)", str(q["taille_texte"]),
                                  valider=lambda t: None if t.isdigit() and 8 <= int(t) <= 20 else "Entre 8 et 20.")),
    })
    print(f"{G}✔ Réglages du poste enregistrés.{F} Le dossier partagé et le thème s'appliquent au prochain démarrage.")


def action_historique():
    from . import historique
    titre("HISTORIQUE DES INTERVENTIONS")
    noms = historique.clients()
    if not noms:
        print(f"{J}Aucune intervention enregistrée pour l'instant.{F}")
        return
    c = choix("Quel client ?", [(n, n) for n in noms] + [("tous", "Les 30 dernières interventions, tous clients")], 1)
    entrees = historique.lire(None if c == "tous" else c)
    for e in entrees[-30:] if c == "tous" else entrees:
        ligne = historique.resume(e)
        if c == "tous":
            ligne = f"{e.get('client')} — {ligne}"
        couleur = R if (e.get("echecs") or e.get("ecarts")) else G
        print(f"  {couleur}•{F} {ligne}")
        if e.get("rapport"):
            print(f"      {C}{e['rapport']}{F}")


def action_rappels():
    from .rappels import calculer
    titre("RAPPELS")
    rappels = calculer()
    if not rappels:
        print(f"{G}✔ Rien à signaler pour vos clients.{F}")
        return
    for r in rappels:
        print(f"  {R + '!' if r.urgence == 1 else J + '•'}{F} {B}{r.client}{F} : {r.texte}")


def action_dossiers():
    titre("DOSSIERS DE TRAVAIL")
    for nom, lib in (("clients", "Fichiers des clients"), ("rapports", "Rapports"), ("sauvegardes", "Sauvegardes Central")):
        Path(nom).mkdir(exist_ok=True)
        print(f"  {lib} : {Path(nom).resolve()}")
    c = choix("Ouvrir un dossier ?", [("clients", "Clients"), ("rapports", "Rapports"),
                                      ("sauvegardes", "Sauvegardes"), ("non", "Non")], 4)
    if c != "non":
        ouvrir(Path(c).resolve())


def ouvrir(chemin: Path) -> None:
    """Ouvre un dossier ou un fichier avec le programme habituel de Windows."""
    try:
        if os.name == "nt":
            os.startfile(str(chemin))   # noqa: S606 - ouverture volontaire par l'utilisateur
        else:
            import subprocess
            subprocess.Popen(["xdg-open", str(chemin)])
    except (OSError, AttributeError) as exc:
        print(f"{J}Impossible d'ouvrir automatiquement : {exc}. Chemin : {chemin}{F}")


def action_glossaire():
    from .glossaire import chercher
    titre("GLOSSAIRE")
    while True:
        mot = texte("Mot à expliquer (Entrée pour revenir au menu, * pour tout afficher)", "", vide_ok=True)
        if not mot:
            return
        res = chercher("" if mot == "*" else mot)
        if not res:
            print(f"{J}   Aucun terme trouvé.{F}")
        for terme, definition in res:
            print(f"{C}{B}{terme}{F} : {definition}")


def action_mise_a_jour():
    from .mise_a_jour import installer, verifier
    print("Recherche d'une nouvelle version...")
    info_maj = verifier(delai=10)
    if not info_maj:
        print(f"{G}✔ Vous avez la dernière version ({VERSION}).{F}")
        return
    print(f"{J}Nouvelle version {info_maj['version']} disponible (vous avez la {VERSION}).{F}")
    if info_maj.get("notes"):
        print(info_maj["notes"][:1500])
    if oui_non("Installer la mise à jour maintenant ?", True):
        resultat = installer(info_maj)
        if resultat == "RELANCE":
            print(f"{G}Mise à jour téléchargée : le programme va redémarrer.{F}")
            os._exit(0)
        print(resultat)


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


def _historique_sauvegarde(pf, fichier) -> None:
    from . import historique
    from .central import firmware_compatible
    historique.enregistrer(pf.nom, "sauvegarde_central", f"firmware {pf.firmware}", fichier=fichier,
                           firmware=pf.firmware, firmware_ancien=firmware_compatible(pf.firmware) is False)


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
                    if isinstance(r, Path):
                        _historique_sauvegarde(pf, r)
            elif a == "export":
                if not pfs:
                    continue
                pf = _choisir_pare_feux(pfs, "Quel pare-feu sauvegarder ?")[0]
                if not _verifier_firmware([pf], "à sauvegarder"):
                    continue
                f = c.exporter(pf.id, _fichier_sauvegarde(pf), rappel=_rappel)
                _historique_sauvegarde(pf, f)
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
    from . import historique
    for p in cibles:
        historique.enregistrer(p.nom, "import_central", f"depuis {fichier.name}", fichier=fichier)
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
    ("rappels", "Rappels : ce qu'il faudrait refaire chez vos clients", action_rappels),
    ("historique", "Historique des interventions d'un client", action_historique),
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
    ("dossiers", "Ouvrir les dossiers (clients, rapports, sauvegardes)", action_dossiers),
    ("parametres", "Mes paramètres (nom de ma société, valeurs par défaut)", action_parametres),
    ("glossaire", "Glossaire : les termes techniques expliqués", action_glossaire),
    ("analyse", "Analyser le réseau du client (box, serveurs, imprimantes...)", action_analyse_reseau),
    ("intervention", "Intervention guidée pas à pas (boîtier neuf : brancher, allumer, activer l'API)",
     action_intervention),
    ("reprise", "Reprendre l'existant : ancien pare-feu Fortinet ou inventaire", action_reprise),
    ("verification", "Vérifier que tout fonctionne chez le client (après l'installation)", action_verification),
    ("questionnaire", "Questionnaire à envoyer au client avant l'intervention", action_questionnaire),
    ("tableau", "Tableau de bord de tous les clients", action_tableau),
    ("compte_rendu", "Compte rendu d'intervention à faire signer", action_compte_rendu),
    ("profil", "Profil de votre société (réponses proposées d'avance)", action_profil),
    ("statistiques", "Questions où l'on hésite le plus", action_statistiques),
    ("rapport_mensuel", "Rapport mensuel automatique", action_rapport_mensuel),
    ("maj", "Mise à jour du programme", action_mise_a_jour),
    ("quitter", "Quitter", None),
]


def main() -> int:
    if os.name == "nt" and sys.stdout is not None and sys.stdout.isatty():
        os.system("")
    from .poste import appliquer_dossier_partage
    appliquer_dossier_partage(lambda t: print(f"{J}{t}{F}"))
    try:
        from .rappels import calculer
        urgents = [r for r in calculer() if r.urgence == 1]
        if urgents:
            print(f"{J}{len(urgents)} rappel(s) important(s) : menu « Rappels ».{F}")
    except Exception:
        pass
    try:
        from .mise_a_jour import mise_a_jour_automatique
        if mise_a_jour_automatique(lambda t: print(f"{J}{t}{F}"), delai=3):
            return 0          # la nouvelle version va démarrer à la place de celle-ci
    except Exception:  # une vérification ratée ne doit jamais gêner l'utilisation
        pass
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
