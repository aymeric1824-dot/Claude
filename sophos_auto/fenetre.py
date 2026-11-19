"""Fenêtre Windows de l'outil, au style de XPhare (fond sombre, accents rouges, actions à gauche).

Toutes les fonctions du menu restent les mêmes. Chaque question s'affiche dans une carte en bas :
la question, son explication, et les bons boutons (Oui / Non, liste de choix, zone de saisie).
"""
from __future__ import annotations

import builtins
import getpass
import os
import queue
import re
import sys
import threading
import time

ANSI = re.compile(r"\x1b\[([0-9;]*)m")
COULEURS = {"31": "rouge", "32": "vert", "33": "jaune", "36": "cyan", "90": "gris", "1": "gras"}

ROUGE = "#E10600"   # couleur d'accent de XPhare

# Thèmes : « sombre » reprend la fenêtre de XPhare, « clair » ses rapports HTML.
THEMES = {
    "sombre": {
        "fond": "#0E0E10", "panneau": "#0B0B0D", "carte": "#131316", "bord": "#24242A", "bord_fort": "#34343C",
        "texte": "#F4F4F6", "texte2": "#9A9AA3", "discret": "#5C5C66", "journal": "#0A0A0C", "saisie": "#131316",
        "saisie_focus": "#1A1214", "survol": "#1A1214", "actif": "#2A1213", "fantome": "#16161A",
        "fantome_texte": "#A8A8B0", "ligne_fin": "#1A1A1F", "accent": ROUGE, "accent_vif": "#FF3B30",
        "rouge": "#FF6A60", "vert": "#3FB950", "jaune": "#E3A008", "cyan": "#6CB6FF", "gris": "#7A7A84",
    },
    "clair": {
        "fond": "#ECECEF", "panneau": "#FFFFFF", "carte": "#FFFFFF", "bord": "#D8D8DE", "bord_fort": "#C4C4CC",
        "texte": "#1D1D22", "texte2": "#5C5C66", "discret": "#8A8A94", "journal": "#FFFFFF", "saisie": "#FFFFFF",
        "saisie_focus": "#FFF6F5", "survol": "#FDECEA", "actif": "#FBDAD7", "fantome": "#FFFFFF",
        "fantome_texte": "#3A3A42", "ligne_fin": "#ECECEF", "accent": ROUGE, "accent_vif": "#C40500",
        "rouge": "#B3140B", "vert": "#1F7A37", "jaune": "#8A6100", "cyan": "#1F6FEB", "gris": "#7A7A84",
    },
}

# Colonne de gauche : actions regroupées, avec un libellé court (le libellé complet s'affiche au survol)
GROUPES = [
    ("PRÉPARER", ("intervention", "assistant", "questionnaire", "analyse", "reprise", "dupliquer", "collecte",
                  "modele")),
    ("INTERVENIR", ("diagnostic", "appliquer", "verification", "conformite", "restaurer", "lire", "central")),
    ("SUIVRE", ("tableau", "rappels", "historique", "audit", "documentation", "compte_rendu")),
    ("OUTIL", ("dossiers", "parametres", "profil", "statistiques", "rapport_mensuel", "glossaire", "maj")),
]
COURTS = {
    "assistant": "Nouveau client / reprendre", "dupliquer": "Copier un client existant",
    "collecte": "Infos à demander au client", "modele": "Fichier Excel vierge",
    "diagnostic": "Diagnostic de connexion", "appliquer": "Envoyer un fichier client",
    "conformite": "Vérifier la conformité", "restaurer": "Revenir en arrière",
    "lire": "Voir les objets du pare-feu", "central": "Sophos Central",
    "rappels": "Rappels", "historique": "Historique d'un client", "audit": "Contrôle de sécurité",
    "documentation": "Dossier technique", "dossiers": "Ouvrir les dossiers", "parametres": "Mes paramètres",
    "glossaire": "Glossaire", "maj": "Mise à jour",
    "analyse": "Analyser le réseau du client", "questionnaire": "Questionnaire client",
    "tableau": "Tableau de bord des clients", "compte_rendu": "Compte rendu à signer",
    "profil": "Profil de ma société", "statistiques": "Questions difficiles", "rapport_mensuel": "Rapport mensuel",
    "intervention": "Intervention guidée (boîtier neuf)", "reprise": "Reprendre l'existant",
    "verification": "Vérifier que tout fonctionne",
}
# Mode simple : seulement l'essentiel dans la colonne de gauche
ACTIONS_SIMPLES = ("intervention", "assistant", "appliquer", "verification", "diagnostic", "compte_rendu")
# Mode simple : les mêmes questions, sans jargon (la version technique reste affichée en petit)
SIMPLES = {
    "Port du XGS relié à la box / au routeur": "Sur quel port du pare-feu la box Internet est-elle branchée ?",
    "Comment ce lien Internet est-il fourni ?": "Comment le client est-il relié à Internet ?",
    "Le client a-t-il une adresse IP publique FIXE ?":
        "L'abonnement Internet du client a-t-il une adresse fixe ? (c'est écrit sur le contrat)",
    "Y a-t-il un DEUXIÈME accès Internet (4G, 2e fibre, ADSL) ?":
        "Le client a-t-il une deuxième connexion Internet (4G, deuxième ligne) ?",
    "Port du XGS relié au switch du réseau local": "Sur quel port du pare-feu le réseau des PC est-il branché ?",
    "Le client a-t-il déjà un réseau en place dont il faut garder les adresses ?":
        "Faut-il garder les réglages actuels des PC et des imprimantes du client ?",
    "IP que doit prendre le pare-feu sur le LAN, avec le masque": "Quelle adresse donner au pare-feu dans le réseau du client ?",
    "IP du pare-feu sur le LAN, avec le masque": "Quelle adresse donner au pare-feu dans le réseau du client ?",
    "Qui doit distribuer les adresses sur le réseau local ?": "Quel appareil donne automatiquement leur adresse aux PC ?",
    "Le client a-t-il un Active Directory (domaine Windows) ?":
        "Les salariés ouvrent-ils leur session Windows avec un compte de l'entreprise ?",
    "Relier le pare-feu à l'Active Directory ?": "Utiliser les comptes Windows de l'entreprise dans le pare-feu ?",
    "Le réseau doit-il être découpé en VLAN ?":
        "Faut-il séparer certains appareils (caméras, téléphones, invités) du réseau des PC ?",
    "Le client a-t-il des bornes Wi-Fi Sophos (APX / AP6) gérées par le pare-feu ?":
        "Le client a-t-il des bornes Wi-Fi de la marque Sophos ?",
    "Créer un Wi-Fi invités (isolé, Internet uniquement) ?":
        "Créer un Wi-Fi pour les visiteurs, séparé du réseau de l'entreprise ?",
    "Activer la prévention d'intrusion (IPS) ?": "Bloquer automatiquement les attaques connues ?",
    "Bloquer les applications indésirables (proxy de contournement, P2P...) ?":
        "Bloquer les logiciels de téléchargement illégal et de contournement ?",
    "Analyser les téléchargements (antivirus) ?": "Vérifier les fichiers téléchargés avec un antivirus ?",
    "Faut-il rendre un équipement interne accessible depuis Internet ?":
        "Faut-il pouvoir joindre un appareil des locaux depuis l'extérieur (caméras, serveur) ?",
    "Faut-il relier ce site à un ou plusieurs autres sites ?":
        "Faut-il relier ces locaux à d'autres locaux du client (agences) ?",
    "Des personnes doivent-elles se connecter à distance ?":
        "Des salariés travaillent-ils de chez eux et doivent-ils accéder aux fichiers de l'entreprise ?",
    "Exiger la double authentification (code sur téléphone) pour le VPN ?":
        "Demander en plus un code sur le téléphone pour se connecter depuis l'extérieur ?",
    "Analyser aussi le trafic chiffré (inspection HTTPS) ?":
        "Analyser aussi les sites sécurisés (https) ? (protection renforcée, à installer sur les PC)",
    "Choisir les serveurs DNS du pare-feu (sinon ceux de l'opérateur) ?":
        "Choisir vous-même les serveurs qui traduisent les noms de sites ? (sinon ceux de l'opérateur)",
    "Le pare-feu doit-il être supervisé en SNMP (PRTG, Zabbix, Centreon...) ?":
        "Le client a-t-il un logiciel de surveillance du réseau (PRTG, Zabbix...) ?",
    "Programmer une sauvegarde automatique de la configuration ?": "Sauvegarder automatiquement les réglages du pare-feu ?",
}

# Écran d'accueil : les 3 étapes pour configurer un pare-feu, dans l'ordre
ETAPES_ACCUEIL = [
    ("Préparer le pare-feu", "À faire une seule fois sur un boîtier neuf, environ 5 minutes.",
     ["Branchez votre PC sur le port « Port1 » du pare-feu, puis allumez le pare-feu.",
      "Ouvrez la page du pare-feu (bouton à droite) et suivez l'assistant Sophos : mot de passe, licence. "
      "Un avertissement de sécurité s'affiche : c'est normal, cliquez sur « Avancé » puis « Continuer ».",
      "Menu « Sauvegarde et firmware » > « API » : cochez « Configuration de l'API », ajoutez l'adresse IP "
      "de votre PC dans « Adresses IP autorisées », puis « Appliquer »."],
     [("Me guider pas à pas", "intervention", True), ("Ouvrir la page du pare-feu", "web", False),
      ("Je n'arrive pas à me connecter", "diagnostic", False)]),
    ("Décrire le client", "Des questions simples, chacune expliquée, avec une réponse déjà proposée.",
     ["Internet, réseau, Wi-Fi, VPN, sécurité : l'assistant vous guide étape par étape.",
      "En cas de doute, gardez la réponse proposée : elle convient à la plupart des clients.",
      "Tout est enregistré après chaque étape : vous pouvez fermer et reprendre plus tard."],
     [("Commencer", "assistant", True), ("Questionnaire pour le client", "questionnaire", False)]),
    ("Envoyer la configuration au pare-feu", "Proposé automatiquement à la fin de l'assistant.",
     ["D'abord une simulation : elle montre ce qui va changer, sans rien envoyer.",
      "Vous confirmez ensuite l'envoi. Un rapport et une sauvegarde sont créés à chaque fois."],
     [("Envoyer un fichier client", "appliquer", False)]),
]


def decouper_ansi(texte: str) -> list[tuple[str, tuple[str, ...]]]:
    """Découpe un texte coloré (codes ANSI) en morceaux (texte, styles)."""
    morceaux, styles, pos = [], [], 0
    for m in ANSI.finditer(texte):
        if m.start() > pos:
            morceaux.append((texte[pos:m.start()], tuple(styles)))
        codes = [c for c in m.group(1).split(";") if c]
        if not codes or "0" in codes:
            styles = []
        styles += [COULEURS[c] for c in codes if c in COULEURS and COULEURS[c] not in styles]
        pos = m.end()
    if pos < len(texte):
        morceaux.append((texte[pos:], tuple(styles)))
    return morceaux


def deviner_question(invite: str, masque: bool) -> dict:
    """Question posée sans description (input simple) : on devine son type d'après le texte."""
    q = ANSI.sub("", invite).strip()
    oui_non = re.search(r"[(\[]\s*(o/N|O/n)\s*[)\]]", q)
    q = re.sub(r"\s*[(\[]\s*(o/N|O/n)\s*[)\]]", "", q).strip().rstrip(":").strip().lstrip("?").strip()
    if masque:
        return {"genre": "secret", "question": q or "Mot de passe"}
    if oui_non:
        return {"genre": "oui_non", "question": q, "defaut": oui_non.group(1) == "O/n"}
    if "appuyez sur entrée" in q.lower():
        return {"genre": "continuer", "question": q}
    return {"genre": "texte", "question": q or "Votre réponse", "defaut": "", "vide_ok": True}


def _melanger(c1: str, c2: str, t: float) -> str:
    """Couleur intermédiaire entre c1 et c2 (t de 0 à 1), pour les dégradés."""
    t = max(0.0, min(1.0, t))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def _colorref(couleur: str) -> int:
    r, v, b = (int(couleur[i:i + 2], 16) for i in (1, 3, 5))
    return (b << 16) | (v << 8) | r


def _barre_de_titre(racine, theme: dict, sombre: bool) -> None:
    """Windows 10/11 : barre de titre sombre et aux couleurs de la fenêtre (sans effet ailleurs)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        racine.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(racine.winfo_id())
        dwm = ctypes.windll.dwmapi
        for attribut, valeur in ((20, 1 if sombre else 0), (35, _colorref(theme["fond"])),
                                 (34, _colorref("#4A1210" if sombre else theme["bord"])),
                                 (36, _colorref(theme["texte"]))):
            v = ctypes.c_int(valeur)
            dwm.DwmSetWindowAttribute(hwnd, attribut, ctypes.byref(v), ctypes.sizeof(v))
    except Exception:  # ancienne version de Windows : on garde la barre normale
        pass


class _Sortie:
    """Remplace sys.stdout : le texte est envoyé à la fenêtre."""

    def __init__(self, file_attente: queue.Queue):
        self.q = file_attente

    def write(self, t):
        if t:
            self.q.put(("texte", t))
        return len(t)

    def flush(self):
        pass

    def isatty(self):
        return False


def _question(sorties: queue.Queue, reponses: queue.Queue, invite: str = "", masque: bool = False) -> str:
    sorties.put(("texte", invite))
    sorties.put(("question", (masque, invite)))
    rep = reponses.get()
    if rep is None:
        raise KeyboardInterrupt
    return rep


def _travail(action, sorties: queue.Queue, reponses: queue.Queue) -> None:
    """Exécute une action du menu dans un fil séparé ; ses questions passent par la fenêtre."""
    from . import assistant
    ancien_input, ancien_getpass, ancien_stdout = builtins.input, getpass.getpass, sys.stdout
    builtins.input = lambda invite="": _question(sorties, reponses, invite)
    getpass.getpass = lambda invite="Mot de passe : ", stream=None: _question(sorties, reponses, invite, masque=True)
    sys.stdout = _Sortie(sorties)
    assistant.INTERFACE = lambda q: sorties.put(("carte", q))
    try:
        action()
    except KeyboardInterrupt:
        print("\nAction annulée.")
    except assistant.Retour:
        print("\nRetour au menu.")
    except SystemExit:
        pass
    except Exception as exc:  # une erreur ne doit jamais fermer la fenêtre
        print(f"\n\x1b[31mErreur inattendue : {exc}\x1b[0m")
    finally:
        builtins.input, getpass.getpass, sys.stdout = ancien_input, ancien_getpass, ancien_stdout
        assistant.INTERFACE = None
        sorties.put(("fin", None))


def _verifier_mise_a_jour(sorties: queue.Queue) -> None:
    """Au démarrage : cherche une nouvelle version sur GitHub et l'installe toute seule si c'est activé."""
    try:
        from .mise_a_jour import mise_a_jour_automatique
        if mise_a_jour_automatique(lambda t: sorties.put(("texte", f"\x1b[33m{t}\x1b[0m\n"))):
            sorties.put(("redemarrer", None))
    except Exception:  # une vérification ratée ne doit jamais gêner l'utilisation
        pass


def _surveiller_connexion(partage: dict, sorties: queue.Queue) -> None:
    """Toutes les 4 secondes (accueil affiché) : adresse du PC et pare-feu joignable ou non.

    Aucun identifiant n'est envoyé : une connexion refusée répétée pourrait bloquer le PC sur le pare-feu.
    """
    from .diagnostic import ip_locale_vers, meme_reseau, port_ouvert
    while not partage.get("fin"):
        if partage.get("actif"):
            ip = str(partage.get("ip", "")).strip()
            ip_pc = ip_locale_vers(ip) if ip else ""
            sorties.put(("connexion", {"ip": ip, "ip_pc": ip_pc, "joignable": bool(ip) and port_ouvert(ip),
                                       "meme_reseau": meme_reseau(ip_pc, ip) if ip_pc else False}))
        for _ in range(40):
            if partage.get("fin") or partage.pop("maintenant", False):
                break
            time.sleep(0.1)


def _chercher_pare_feu(sorties: queue.Queue) -> None:
    from .reseau import trouver_pare_feu
    try:
        trouves = trouver_pare_feu()
    except Exception:
        trouves = []
    sorties.put(("pare_feu_trouve", trouves))


def _verifier_sante(sorties: queue.Queue) -> None:
    try:
        from .sante import verifier
        sorties.put(("sante", verifier()))
    except Exception:
        pass


def _tester_api(ip: str, utilisateur: str, mot_de_passe: str, sorties: queue.Queue) -> None:
    from .diagnostic import diagnostiquer
    try:
        etapes = diagnostiquer(ip, utilisateur=utilisateur, mot_de_passe=mot_de_passe, afficher=False)
    except Exception as exc:
        etapes = [(False, "Test impossible", str(exc))]
    sorties.put(("test_api", etapes))


# ---------------------------------------------------------------------- éléments graphiques
class _Bouton:
    """Bouton plat au style XPhare : « fantôme » (contour, teinte rouge au survol) ou « principal » (rouge)."""

    def __init__(self, app, parent, texte: str, commande, principal: bool = False, icone: str = "",
                 petit: bool = False, aide: str = "", gauche: bool = False, grand: bool = False):
        tk = app.tk
        self.app, self.commande, self.principal, self.aide = app, commande, principal, aide
        self.etat = "normal"
        self.survol = False
        self.cadre = tk.Frame(parent, highlightthickness=1, bd=0)
        libelle = f"{icone}  {texte}" if icone and texte else (icone or texte)
        taille = 9 if petit else (12 if grand else (11 if principal else 10))
        police = ("Arial", taille, "bold") if grand else ("Consolas", taille, "bold" if principal else "normal")
        self.label = tk.Label(self.cadre, text=libelle, font=police, anchor="w" if gauche else "center",
                              justify="left", padx=10 if petit else (20 if principal or grand else 14),
                              pady=3 if petit else (9 if grand else (8 if principal else 6)), cursor="hand2")
        self.label.pack(fill="both", expand=True)
        for w in (self.cadre, self.label):
            w.bind("<Enter>", self._entrer)
            w.bind("<Leave>", self._sortir)
            w.bind("<Button-1>", self._clic)
        app.elements.append(self)
        self.peindre()

    def pack(self, **kw):
        self.cadre.pack(**kw)
        return self

    def grid(self, **kw):
        self.cadre.grid(**kw)
        return self

    def pack_forget(self):
        self.cadre.pack_forget()

    def detruire(self):
        if self in self.app.elements:
            self.app.elements.remove(self)
        self.cadre.destroy()

    def configure(self, **kw):
        if "state" in kw:
            self.etat = str(kw.pop("state"))
            self.peindre()
        if "text" in kw:
            self.label.configure(text=kw.pop("text"))

    def cget(self, option):
        return self.etat if option == "state" else self.label.cget(option)

    def _entrer(self, _e=None):
        self.survol = True
        self.peindre()
        if self.aide:
            self.app.indice(self.aide)

    def _sortir(self, _e=None):
        self.survol = False
        self.peindre()
        if self.aide:
            self.app.indice(None)

    def _clic(self, _e=None):
        if self.etat != "disabled" and self.commande:
            self.commande()

    def peindre(self):
        t = THEMES[self.app.theme]
        actif = self.etat != "disabled"
        if self.principal:
            fond = t["accent_vif"] if (self.survol and actif) else t["accent"]
            texte, bord = "#FFFFFF", t["accent_vif"]
            if not actif:
                fond, texte, bord = _melanger(t["accent"], t["fond"], 0.6), _melanger("#FFFFFF", t["fond"], 0.4), fond
        else:
            survol = self.survol and actif
            fond = _melanger(t["fantome"], t["accent"], 0.16) if survol else t["fantome"]
            texte = (t["texte"] if survol else t["fantome_texte"]) if actif else t["discret"]
            bord = t["accent"] if survol else (t["bord_fort"] if actif else t["bord"])
        self.cadre.configure(bg=fond, highlightbackground=bord, highlightcolor=bord)
        self.label.configure(bg=fond, fg=texte, cursor="hand2" if actif else "arrow")


class _Action:
    """Ligne d'action de la colonne de gauche : numéro rouge, libellé, barre d'accent au survol et pendant l'action."""

    def __init__(self, app, parent, numero: int, court: str, complet: str, commande):
        tk = app.tk
        self.app, self.commande, self.complet = app, commande, complet
        self.etat, self.survol, self.actif = "normal", False, False
        self.cadre = tk.Frame(parent, cursor="hand2")
        self.barre = tk.Frame(self.cadre, width=3)
        self.barre.pack(side="left", fill="y")
        self.num = tk.Label(self.cadre, text=f"{numero:02d}", font=("Consolas", 10, "bold"), padx=8, pady=5)
        self.num.pack(side="left")
        self.nom = tk.Label(self.cadre, text=court, font=("Arial", 10, "bold"), anchor="w")
        self.nom.pack(side="left", fill="x", expand=True)
        for w in (self.cadre, self.num, self.nom):
            w.bind("<Enter>", self._entrer)
            w.bind("<Leave>", self._sortir)
            w.bind("<Button-1>", self._clic)
            w.bind("<MouseWheel>", app._molette_gauche)

    def configure(self, **kw):
        if "state" in kw:
            self.etat = str(kw["state"])
            self.peindre()

    def _entrer(self, _e=None):
        self.survol = True
        self.peindre()
        self.app.indice(self.complet)

    def _sortir(self, _e=None):
        self.survol = False
        self.peindre()
        self.app.indice(None)

    def _clic(self, _e=None):
        if self.etat != "disabled":
            self.commande()

    def peindre(self):
        t = THEMES[self.app.theme]
        dispo = self.etat != "disabled"
        fond = t["actif"] if self.actif else (t["survol"] if self.survol and dispo else t["panneau"])
        for w in (self.cadre, self.num, self.nom):
            w.configure(bg=fond, cursor="hand2" if dispo else "arrow")
        self.barre.configure(bg=t["accent"] if (self.actif or (self.survol and dispo)) else fond)
        self.num.configure(fg=t["accent"] if dispo or self.actif else t["discret"])
        self.nom.configure(fg=(t["texte"] if dispo or self.actif else t["discret"]))


class Application:
    def __init__(self):
        import tkinter as tk
        from tkinter import font as tkfont
        from tkinter import ttk

        from . import __version__
        from .__main__ import MENU

        self.tk = tk
        self.racine = tk.Tk()
        self.racine.title("SophosXGS")
        hauteur = max(700, min(900, self.racine.winfo_screenheight() - 90))
        self.racine.geometry(f"1240x{hauteur}")
        self.racine.minsize(1000, 640)
        self.sorties: queue.Queue = queue.Queue()
        self.reponses: queue.Queue = queue.Queue()
        self.en_cours = False
        self.masque = False
        self.redemarrage_en_attente = False
        self.elements: list = []          # boutons à repeindre quand le thème change
        self.peints: list = []            # (widget, {option: clé du thème})
        self.textes_longs: list = []      # libellés dont la largeur suit celle de la fenêtre (widget, marge)
        self.carte_attente: dict | None = None   # description de la prochaine question
        self.question: dict | None = None        # question affichée
        self.section = ""                 # titre de la partie en cours (ex. « ACCÈS INTERNET »)
        self.dans_assistant = False
        self.dynamiques: list = []        # boutons de la question affichée
        self.fenetres: list = []          # fenêtres annexes ouvertes (mots de passe, test de l'API)
        from .parametres import charger as charger_parametres
        params = charger_parametres()
        self.utilisateur_defaut = params.get("utilisateur_defaut") or "admin"
        # Partagé avec la surveillance de la connexion (fil de fond) : jamais de référence à la fenêtre
        self.partage = {"ip": params.get("ip_defaut") or "172.16.16.16", "actif": True, "fin": False}
        from .poste import charger as charger_poste
        reglages = charger_poste()
        self.theme = reglages["theme"] if reglages["theme"] in THEMES else "sombre"
        self.taille = max(8, min(20, int(reglages["taille_texte"] or 10)))
        self.simple = bool(reglages.get("mode_simple"))
        familles = set(tkfont.families(self.racine))
        self.icones = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in familles), None)

        def ic(code: str) -> str:      # glyphe d'icône, ou rien si la police d'icônes est absente
            return chr(code) if self.icones else ""
        self.ic = ic

        self.style = ttk.Style(self.racine)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        try:   # barres de défilement fines, sans flèches (comme XPhare)
            self.style.layout("X.Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
                ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
        except tk.TclError:
            pass

        def peint(widget, **options):
            self.peints.append((widget, options))
            return widget
        self.peint = peint

        racine = peint(tk.Frame(self.racine, padx=28), bg="fond")
        racine.pack(fill="both", expand=True)

        # ------------------------------------------------------------ en-tête
        tete = peint(tk.Frame(racine, height=58), bg="fond")
        tete.pack(fill="x")
        tete.pack_propagate(False)
        marque = peint(tk.Frame(tete), bg="fond")
        marque.pack(side="left", fill="y")
        peint(tk.Label(marque, text="SophosXGS", font=("Consolas", 16, "bold")), bg="fond", fg="texte").pack(
            side="left")
        peint(tk.Label(marque, text="■", font=("Arial", 11)), bg="fond", fg="accent").pack(side="left", padx=(8, 0))
        peint(tk.Frame(marque, width=1, height=16), bg="bord_fort").pack(side="left", padx=18)
        peint(tk.Label(marque, text="CONFIGURATION DES PARE-FEU", font=("Consolas", 10)), bg="fond",
              fg="texte2").pack(side="left")
        peint(tk.Label(marque, text=f"v{__version__}", font=("Consolas", 9)), bg="fond", fg="discret").pack(
            side="left", padx=(12, 0))

        droite_tete = peint(tk.Frame(tete), bg="fond")
        droite_tete.pack(side="right", fill="y")
        self.date = peint(tk.Label(droite_tete, font=("Consolas", 10)), bg="fond", fg="texte2")
        self.date.pack(side="right", padx=(10, 0))
        if self.icones:
            peint(tk.Label(droite_tete, text=ic(0xE787), font=(self.icones, 10)), bg="fond", fg="discret").pack(
                side="right")
        _Bouton(self, droite_tete, "Thème", self.changer_theme, icone=ic(0xE793), petit=True,
                aide="Passer du thème sombre au thème clair").pack(side="right", padx=(0, 14))
        self.bouton_simple = _Bouton(self, droite_tete, "", self.changer_mode_simple, icone=ic(0xE8D3), petit=True,
                                     aide="Mode simple : seulement l'essentiel, et des questions sans mots techniques")
        self.bouton_simple.pack(side="right", padx=(0, 6))
        _Bouton(self, droite_tete, "Visite guidée", self.visite_guidee, icone=ic(0xE7BE), petit=True,
                aide="Revoir la présentation de l'outil en 1 minute").pack(side="right", padx=(0, 6))
        _Bouton(self, droite_tete, "A+", lambda: self.changer_taille(1), petit=True,
                aide="Agrandir le texte (Ctrl +)").pack(side="right", padx=(0, 6))
        _Bouton(self, droite_tete, "A−", lambda: self.changer_taille(-1), petit=True,
                aide="Réduire le texte (Ctrl −)").pack(side="right", padx=(0, 6))
        self.bouton_rappels = _Bouton(self, droite_tete, "", lambda: self.lancer_cle("rappels"), icone=ic(0xE7BA),
                                      petit=True, aide="Voir ce qu'il faudrait refaire chez vos clients")
        self.ligne_tete = tk.Canvas(racine, height=1, highlightthickness=0, bd=0)
        self.ligne_tete.pack(fill="x")
        self.ligne_tete.bind("<Configure>", lambda e: self._degrade())

        # ------------------------------------------------------------ pied (avant le contenu : toujours visible)
        pied = peint(tk.Frame(racine, pady=12), bg="fond")
        pied.pack(side="bottom", fill="x")
        gauche_pied = peint(tk.Frame(pied), bg="fond")
        gauche_pied.pack(side="left", fill="x", expand=True)
        self.etat = peint(tk.Label(gauche_pied, text="Choisissez une action à gauche.", anchor="w",
                                   font=("Consolas", 10)), bg="fond", fg="texte")
        self.etat.pack(fill="x")
        self.indication = peint(tk.Label(gauche_pied, text="", anchor="w", font=("Consolas", 9)), bg="fond",
                                fg="discret")
        self.indication.pack(fill="x", pady=(3, 0))
        _Bouton(self, pied, "Quitter", self.quitter, icone=ic(0xE8BB), aide="Fermer le programme").pack(
            side="right")
        _Bouton(self, pied, "Effacer l'écran", self.effacer, icone=ic(0xE74D),
                aide="Vider la zone des échanges").pack(side="right", padx=(0, 10))
        _Bouton(self, pied, "Rapports", lambda: self.ouvrir("rapports"), icone=ic(0xE8B7),
                aide="Ouvrir le dossier des rapports").pack(side="right", padx=(0, 10))
        _Bouton(self, pied, "Clients", lambda: self.ouvrir("clients"), icone=ic(0xE8B7),
                aide="Ouvrir le dossier des fichiers clients").pack(side="right", padx=(0, 10))
        self.bouton_aide = _Bouton(self, pied, "Demander de l'aide", self._dialogue_aide, icone=ic(0xE897),
                                   aide="Prépare un dossier avec tout ce qu'il faut à un expert pour vous aider")
        self.bouton_aide.pack(side="right", padx=(0, 10))
        self.bouton_accueil = _Bouton(self, pied, "Accueil", self.montrer_accueil, icone=ic(0xE80F),
                                      aide="Revenir à l'écran d'accueil (les 3 étapes)")
        self.bouton_accueil.pack(side="right", padx=(0, 10))

        # ------------------------------------------------------------ contenu
        contenu = peint(tk.Frame(racine, pady=16), bg="fond")
        contenu.pack(fill="both", expand=True)

        # Colonne de gauche : panneau des actions (défilant)
        gauche = peint(tk.Frame(contenu, width=292, highlightthickness=1), bg="panneau", highlightbackground="bord",
                       highlightcolor="bord")
        gauche.pack(side="left", fill="y")
        gauche.pack_propagate(False)
        entete_g = peint(tk.Frame(gauche, padx=14, pady=10), bg="panneau")
        entete_g.pack(fill="x")
        if self.icones:
            peint(tk.Label(entete_g, text=ic(0xE8FD), font=(self.icones, 10)), bg="panneau", fg="accent").pack(
                side="left", padx=(0, 8))
        peint(tk.Label(entete_g, text="TOUTES LES ACTIONS", font=("Consolas", 9, "bold")), bg="panneau",
              fg="accent").pack(side="left")

        recherche = peint(tk.Frame(gauche, padx=12), bg="panneau")
        recherche.pack(fill="x", pady=(0, 6))
        self.recherche = peint(tk.Entry(recherche, font=("Consolas", 10), relief="flat", bd=6, highlightthickness=1),
                               bg="saisie", fg="texte", insertbackground="accent_vif", highlightbackground="bord_fort",
                               highlightcolor="accent", selectbackground="accent")
        self.recherche.pack(fill="x")
        self.recherche.insert(0, "Rechercher…")
        self.recherche.bind("<FocusIn>", lambda e: self.recherche.get() == "Rechercher…" and self.recherche.delete(0, "end"))
        self.recherche.bind("<KeyRelease>", lambda e: self.filtrer_actions() if e.keysym != "Return" else None)
        self.recherche.bind("<Return>", lambda e: self._lancer_premiere())
        self.liste = peint(tk.Canvas(gauche, highlightthickness=0, bd=0), bg="panneau")
        defil_g = ttk.Scrollbar(gauche, orient="vertical", command=self.liste.yview, style="X.Vertical.TScrollbar")
        self.liste.configure(yscrollcommand=defil_g.set)
        defil_g.pack(side="right", fill="y", pady=(0, 8))
        self.liste.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=(0, 8))
        interieur = peint(tk.Frame(self.liste), bg="panneau")
        fen = self.liste.create_window(0, 0, window=interieur, anchor="nw")
        interieur.bind("<Configure>", lambda e: self.liste.configure(scrollregion=self.liste.bbox("all")))
        self.liste.bind("<Configure>", lambda e: self.liste.itemconfigure(fen, width=e.width))
        for w in (self.liste, interieur):
            w.bind("<MouseWheel>", self._molette_gauche)

        self.boutons = []
        self.groupes_lignes: list = []      # (titre du groupe, [lignes d'action]) pour filtrer
        self.actions = {cle: (i + 1, libelle, action) for i, (cle, libelle, action) in enumerate(MENU) if action}
        groupes = [(titre, [c for c in cles if c in self.actions]) for titre, cles in GROUPES]
        reste = [c for c in self.actions if not any(c in cles for _t, cles in GROUPES)]
        if reste:
            groupes.append(("AUTRES", reste))
        for titre, cles in groupes:
            if not cles:
                continue
            g = peint(tk.Frame(interieur, pady=4), bg="panneau")
            g.pack(fill="x", pady=(6, 2))
            peint(tk.Label(g, text=titre, font=("Consolas", 8, "bold")), bg="panneau", fg="discret").pack(
                side="left", padx=(8, 8))
            peint(tk.Frame(g, height=1), bg="bord").pack(side="left", fill="x", expand=True, padx=(0, 8))
            g.bind("<MouseWheel>", self._molette_gauche)
            self.groupes_lignes.append((g, []))
            for cle in cles:
                numero, libelle, action = self.actions[cle]
                ligne = _Action(self, interieur, numero, COURTS.get(cle, libelle), libelle,
                                lambda a=action, l=libelle, c=cle: self.lancer(a, l, c))
                ligne.cadre.pack(fill="x", pady=1)
                ligne.cle = cle
                self.boutons.append(ligne)
                self.groupes_lignes[-1][1].append(ligne)

        # Colonne de droite : titre, puis accueil ou échanges, puis carte de la question
        droite = peint(tk.Frame(contenu), bg="fond")
        droite.pack(side="left", fill="both", expand=True, padx=(26, 0))
        self.droite = droite
        droite.bind("<Configure>", lambda e: self._ajuster_largeurs(e.width))
        self.fil = peint(tk.Label(droite, text="ACCUEIL", font=("Consolas", 10, "bold"), anchor="w"), bg="fond",
                         fg="accent")
        self.fil.pack(fill="x")
        self.titre = peint(tk.Label(droite, text="Configurer un pare-feu Sophos", font=("Arial", 22, "bold"),
                                    anchor="w"), bg="fond", fg="texte")
        self.titre.pack(fill="x", pady=(4, 0))
        self.sous_titre = peint(tk.Label(droite, text="Suivez les 3 étapes ci-dessous, dans l'ordre. "
                                         "Aucune connaissance technique n'est nécessaire.",
                                         font=("Arial", 11), anchor="w", justify="left"), bg="fond", fg="texte2")
        self.sous_titre.pack(fill="x", pady=(4, 0))
        self.textes_longs.append((self.sous_titre, 0))
        self.progression = tk.Canvas(droite, height=6, highlightthickness=0, bd=0)
        self.progression.bind("<Configure>", lambda e: self._dessiner_progression())
        self.etape_en_cours: tuple[int, int] | None = None
        self.espace_titre = peint(tk.Frame(droite, height=12), bg="fond")
        self.espace_titre.pack(fill="x")

        self._construire_carte(droite)
        self._construire_journal(droite, ttk)
        self._construire_accueil(droite)
        self.vue = ""
        self.montrer_accueil()

        self.appliquer_theme()
        self.racine.bind("<Control-plus>", lambda e: self.changer_taille(1))
        self.racine.bind("<Control-equal>", lambda e: self.changer_taille(1))
        self.racine.bind("<Control-minus>", lambda e: self.changer_taille(-1))
        self.racine.bind("<Return>", self._entree_globale)

        self.ecrire("\x1b[90mIci s'affiche tout ce que fait le programme. "
                    "Astuce : tapez ?? suivi d'un mot (ex. ?? vlan) dans une réponse pour avoir sa définition.\x1b[0m\n\n")
        self.afficher_rappels()
        self._horloge()
        self.racine.protocol("WM_DELETE_WINDOW", self.quitter)
        self.racine.after(50, self.relever)
        # Les tâches de fond ne gardent jamais de référence à la fenêtre (Tk ne doit être libéré que par le fil principal)
        threading.Thread(target=_verifier_mise_a_jour, args=(self.sorties,), daemon=True).start()
        threading.Thread(target=_surveiller_connexion, args=(self.partage, self.sorties), daemon=True).start()
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            threading.Thread(target=_verifier_sante, args=(self.sorties,), daemon=True).start()
        self.filtrer_actions()
        if not reglages.get("visite_faite") and not os.environ.get("PYTEST_CURRENT_TEST"):
            self.racine.after(900, self.visite_guidee)

    # ------------------------------------------------------------------ construction
    def _construire_carte(self, droite):
        """Carte de la question, en bas : question, explication, puis les boutons ou la zone de saisie."""
        tk, peint, ic = self.tk, self.peint, self.ic
        carte = peint(tk.Frame(droite, highlightthickness=1, padx=20, pady=16), bg="carte",
                      highlightbackground="accent", highlightcolor="accent")
        self.carte = carte
        tete = peint(tk.Frame(carte), bg="carte")
        tete.pack(fill="x")
        self.c_type = peint(tk.Label(tete, text="QUESTION", font=("Consolas", 9, "bold"), anchor="w"), bg="carte",
                            fg="accent")
        self.c_type.pack(side="left")
        self.c_question = peint(tk.Label(carte, font=("Arial", 14, "bold"), anchor="w", justify="left"),
                                bg="carte", fg="texte")
        self.c_question.pack(fill="x", pady=(6, 0))
        self.textes_longs.append((self.c_question, 44))
        self.c_aide = peint(tk.Label(carte, font=("Arial", 10), anchor="w", justify="left"), bg="carte", fg="texte2")
        self.textes_longs.append((self.c_aide, 44))
        self.c_zone = peint(tk.Frame(carte), bg="carte")
        self.c_zone.pack(fill="x", pady=(12, 0))

        # Zone de saisie (gardée d'une question à l'autre)
        self.ligne_saisie = peint(tk.Frame(self.c_zone), bg="carte")
        self.saisie = peint(tk.Entry(self.ligne_saisie, font=("Consolas", self.taille + 2), state="disabled",
                                     relief="flat", bd=9, highlightthickness=1),
                            bg="saisie", fg="texte", insertbackground="accent_vif", disabledbackground="carte",
                            highlightbackground="bord_fort", highlightcolor="accent", selectbackground="accent",
                            disabledforeground="discret")
        self.saisie.pack(side="left", fill="x", expand=True)
        self.saisie.bind("<Return>", lambda e: self._valider_saisie())
        self.saisie.bind("<KeyRelease>", lambda e: self._verifier_saisie() if e.keysym != "Return" else None)
        self.saisie.bind("<FocusIn>", lambda e: self._focus_saisie(True))
        self.saisie.bind("<FocusOut>", lambda e: self._focus_saisie(False))
        self.valider = _Bouton(self, self.ligne_saisie, "VALIDER", self._valider_saisie, principal=True,
                               icone=ic(0xE768), aide="Envoyer la réponse (touche Entrée)")
        self.valider.pack(side="left", padx=(10, 0))
        self.c_note = peint(tk.Label(self.c_zone, font=("Arial", 9), anchor="w", justify="left"), bg="carte",
                            fg="discret")
        self.textes_longs.append((self.c_note, 44))
        self.c_boutons = peint(tk.Frame(self.c_zone), bg="carte")

        # Retour en arrière (assistant seulement)
        self.c_pied = peint(tk.Frame(carte), bg="carte")
        self.retours = [
            _Bouton(self, self.c_pied, "Recommencer cette étape", lambda: self.envoyer("<", "↺ Recommencer l'étape"),
                    icone=ic(0xE72C), petit=True, aide="Reposer depuis le début les questions de cette étape"),
            _Bouton(self, self.c_pied, "Étape précédente", lambda: self.envoyer("<<", "⟵ Étape précédente"),
                    icone=ic(0xE72B), petit=True, aide="Revenir à l'étape d'avant pour corriger une réponse"),
        ]
        for b in self.retours:
            b.pack(side="left", padx=(0, 8))
        self.boutons_reponse = [self.valider]

    def _construire_journal(self, droite, ttk):
        tk, peint = self.tk, self.peint
        self.journal = peint(tk.Frame(droite), bg="fond")
        entete_j = peint(tk.Frame(self.journal), bg="fond")
        entete_j.pack(fill="x", pady=(0, 6))
        if self.icones:
            peint(tk.Label(entete_j, text=self.ic(0xE9D9), font=(self.icones, 9)), bg="fond", fg="discret").pack(
                side="left", padx=(0, 7))
        peint(tk.Label(entete_j, text="DÉROULEMENT", font=("Consolas", 9)), bg="fond", fg="discret").pack(
            side="left")
        self.resultats = peint(tk.Frame(self.journal, highlightthickness=1, padx=14, pady=10), bg="carte",
                               highlightbackground="vert", highlightcolor="vert")
        peint(tk.Label(self.resultats, text="FICHIERS CRÉÉS : CLIQUEZ POUR LES OUVRIR", font=("Consolas", 9, "bold"),
                       anchor="w"), bg="carte", fg="vert").pack(fill="x", pady=(0, 8))
        self.resultats_boutons = peint(tk.Frame(self.resultats), bg="carte")
        self.resultats_boutons.pack(fill="x")
        cadre = peint(tk.Frame(self.journal, highlightthickness=1), bg="journal", highlightbackground="bord",
                      highlightcolor="bord")
        cadre.pack(fill="both", expand=True)
        self.cadre_journal = cadre
        defil = ttk.Scrollbar(cadre, orient="vertical", style="X.Vertical.TScrollbar")
        self.texte = tk.Text(cadre, wrap="word", font=("Consolas", self.taille), state="disabled",
                             relief="flat", bd=0, highlightthickness=0, padx=14, pady=10, spacing1=1, spacing3=1,
                             yscrollcommand=defil.set)
        defil.configure(command=self.texte.yview)
        defil.pack(side="right", fill="y", padx=(0, 2), pady=2)
        self.texte.pack(side="left", fill="both", expand=True)

    def _construire_accueil(self, droite):
        """Écran d'accueil : les 3 étapes pour configurer un pare-feu, chacune avec ses boutons."""
        tk, peint = self.tk, self.peint
        from tkinter import ttk
        # Accueil défilant : il reste utilisable sur un petit écran
        self.accueil = peint(tk.Frame(droite), bg="fond")
        toile = peint(tk.Canvas(self.accueil, highlightthickness=0, bd=0), bg="fond")
        defil = ttk.Scrollbar(self.accueil, orient="vertical", command=toile.yview, style="X.Vertical.TScrollbar")
        toile.configure(yscrollcommand=defil.set)
        defil.pack(side="right", fill="y")
        toile.pack(side="left", fill="both", expand=True)
        contenu = peint(tk.Frame(toile), bg="fond")
        fen = toile.create_window(0, 0, window=contenu, anchor="nw")
        contenu.bind("<Configure>", lambda e: toile.configure(scrollregion=toile.bbox("all")))
        toile.bind("<Configure>", lambda e: toile.itemconfigure(fen, width=e.width - 10))

        def molette(e):
            if contenu.winfo_height() > toile.winfo_height():
                toile.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")
        toile.bind("<Enter>", lambda e: self.racine.bind_all("<MouseWheel>", molette))
        toile.bind("<Leave>", lambda e: self.racine.unbind_all("<MouseWheel>"))
        self.accueil_contenu = contenu
        self._construire_connexion(contenu)
        for n, (titre, resume, points, boutons) in enumerate(ETAPES_ACCUEIL, 1):
            carte = peint(tk.Frame(contenu, highlightthickness=1, padx=18, pady=10), bg="carte",
                          highlightbackground="bord", highlightcolor="bord")
            carte.pack(fill="x", pady=(0, 10))
            peint(tk.Label(carte, text=f"{n:02d}", font=("Consolas", 20, "bold"), anchor="n"), bg="carte",
                  fg="accent").pack(side="left", anchor="n", padx=(0, 16))
            zone = peint(tk.Frame(carte), bg="carte")       # boutons à droite : l'accueil tient en hauteur
            zone.pack(side="right", anchor="n", padx=(16, 0), pady=(2, 0))
            for libelle, cible, principal in boutons:
                _Bouton(self, zone, libelle, lambda c=cible: self._accueil_clic(c), principal=principal,
                        icone=self.ic(0xE768 if principal else (0xE774 if cible == "web" else 0xE9CE)),
                        petit=not principal, gauche=not principal).pack(fill="x", pady=(0, 6))
            corps = peint(tk.Frame(carte), bg="carte")
            corps.pack(side="left", fill="both", expand=True)
            peint(tk.Label(corps, text=titre, font=("Arial", 13, "bold"), anchor="w"), bg="carte",
                  fg="texte").pack(fill="x")
            peint(tk.Label(corps, text=resume, font=("Arial", 10), anchor="w"), bg="carte", fg="texte2").pack(
                fill="x", pady=(2, 6))
            for p in points:
                ligne = peint(tk.Frame(corps), bg="carte")
                ligne.pack(fill="x", pady=1)
                peint(tk.Label(ligne, text="■", font=("Arial", 7)), bg="carte", fg="accent").pack(
                    side="left", anchor="n", padx=(2, 8), pady=(4, 0))
                lab = peint(tk.Label(ligne, text=p, font=("Arial", 10), anchor="w", justify="left"), bg="carte",
                            fg="texte")
                lab.pack(side="left", fill="x", expand=True)
                self.textes_longs.append((lab, 430))
            if n == 1:
                self.dessin_ports = peint(tk.Canvas(corps, height=74, highlightthickness=0, bd=0), bg="carte")
                self.dessin_ports.pack(fill="x", pady=(8, 0))
                self.dessin_ports.bind("<Configure>", lambda e: self._dessiner_ports())
                self.carte_01 = carte
            if n == 2:
                self.carte_02 = carte
            if n == 3:
                self.zone_attente = peint(tk.Frame(corps), bg="carte")

    def _accueil_clic(self, cible: str):
        if cible == "web":
            import webbrowser
            adresse = f"https://{self.partage['ip']}:4444"
            webbrowser.open(adresse)
            self.etat.configure(text=f"Page du pare-feu ouverte dans le navigateur ({adresse}).")
        else:
            self.lancer_cle(cible)

    # ------------------------------------------------------------------ connexion au pare-feu (accueil)
    def _construire_connexion(self, parent):
        """Bandeau « Connexion au pare-feu » : adresse du PC, adresse du pare-feu, voyant et test de l'API."""
        tk, peint, ic = self.tk, self.peint, self.ic
        cadre = peint(tk.Frame(parent, highlightthickness=1, padx=18, pady=12), bg="carte",
                      highlightbackground="bord", highlightcolor="bord")
        cadre.pack(fill="x", pady=(0, 10))
        tete = peint(tk.Frame(cadre), bg="carte")
        tete.pack(fill="x")
        if self.icones:
            peint(tk.Label(tete, text=ic(0xE839), font=(self.icones, 10)), bg="carte", fg="accent").pack(
                side="left", padx=(0, 8))
        peint(tk.Label(tete, text="CONNEXION AU PARE-FEU", font=("Consolas", 9, "bold")), bg="carte",
              fg="accent").pack(side="left")
        peint(tk.Label(tete, text="vérifiée toutes les 4 secondes", font=("Consolas", 8)), bg="carte",
              fg="discret").pack(side="left", padx=(12, 0))
        _Bouton(self, tete, "Tester l'accès API", self._dialogue_api, icone=ic(0xE72E), petit=True,
                aide="Vérifie avec le mot de passe que l'API est activée et que votre PC est autorisé").pack(
            side="right")
        self.cx_reglage = _Bouton(self, tete, "", self._regler_pc, icone=ic(0xE713), petit=True,
                                  aide="Règle la carte réseau de votre PC pour joindre un pare-feu neuf, ou la remet "
                                       "comme avant")
        self.cx_reglage.pack(side="right", padx=(0, 8))
        self._libelle_reglage()
        self.cx_chercher = _Bouton(self, tete, "Trouver le pare-feu", self._chercher, icone=ic(0xE721), petit=True,
                                   aide="Cherche tout seul le pare-feu Sophos sur le réseau de votre PC")
        self.cx_chercher.pack(side="right", padx=(0, 8))

        ligne = peint(tk.Frame(cadre), bg="carte")
        ligne.pack(fill="x", pady=(10, 0))
        # Adresse de ce PC
        pc = peint(tk.Frame(ligne), bg="carte")
        pc.pack(side="left", padx=(0, 34))
        peint(tk.Label(pc, text="Adresse de votre PC", font=("Arial", 9), anchor="w"), bg="carte",
              fg="texte2").pack(fill="x")
        rang = peint(tk.Frame(pc), bg="carte")
        rang.pack(fill="x", pady=(3, 0))
        self.cx_pc = peint(tk.Label(rang, text="…", font=("Consolas", 13, "bold"), anchor="w", width=15), bg="carte",
                           fg="texte")
        self.cx_pc.pack(side="left")
        _Bouton(self, rang, "Copier", self._copier_ip_pc, icone=ic(0xE8C8), petit=True,
                aide="Copier l'adresse de votre PC (à coller dans « Adresses IP autorisées » du pare-feu)").pack(
            side="left", padx=(6, 0))
        # Adresse du pare-feu (modifiable)
        fw = peint(tk.Frame(ligne), bg="carte")
        fw.pack(side="left", padx=(0, 34))
        peint(tk.Label(fw, text="Adresse du pare-feu (modifiable)", font=("Arial", 9), anchor="w"), bg="carte",
              fg="texte2").pack(fill="x")
        self.cx_ip = peint(tk.Entry(fw, font=("Consolas", 12), width=16, relief="flat", bd=5, highlightthickness=1),
                           bg="saisie", fg="texte", insertbackground="accent_vif", highlightbackground="bord_fort",
                           highlightcolor="accent", selectbackground="accent")
        self.cx_ip.insert(0, self.partage["ip"])
        self.cx_ip.pack(fill="x", pady=(3, 0))
        self.cx_ip.bind("<KeyRelease>", lambda e: self._changer_ip_cible())
        # Voyant
        etat = peint(tk.Frame(ligne), bg="carte")
        etat.pack(side="left", fill="y")
        peint(tk.Label(etat, text="État", font=("Arial", 9), anchor="w"), bg="carte", fg="texte2").pack(fill="x")
        rang = peint(tk.Frame(etat), bg="carte")
        rang.pack(fill="x", pady=(5, 0))
        self.cx_voyant = peint(tk.Canvas(rang, width=14, height=14, highlightthickness=0, bd=0), bg="carte")
        self.cx_voyant.pack(side="left")
        self.cx_couleur = "gris"
        self.cx_etat = peint(tk.Label(rang, text="Vérification…", font=("Arial", 11, "bold"), anchor="w"),
                             bg="carte", fg="texte")
        self.cx_etat.pack(side="left", padx=(8, 0))

        self.cx_conseil = peint(tk.Label(cadre, text="", font=("Arial", 10), anchor="w", justify="left"),
                                bg="carte", fg="texte2")
        self.cx_conseil.pack(fill="x", pady=(10, 0))
        self.textes_longs.append((self.cx_conseil, 60))
        self.cx_api = peint(tk.Frame(cadre), bg="carte")
        self.derniere_connexion: dict = {}
        self._peindre_voyant()

    def _peindre_voyant(self):
        t = THEMES[self.theme]
        c = self.cx_voyant
        c.delete("all")
        couleur = t[self.cx_couleur]
        c.create_oval(2, 2, 12, 12, fill=couleur, outline=_melanger(couleur, t["carte"], 0.3))

    def _changer_ip_cible(self):
        self.partage["ip"] = self.cx_ip.get().strip()
        self.partage["maintenant"] = True
        self.cx_couleur = "gris"
        self.cx_etat.configure(text="Vérification…")
        self._peindre_voyant()

    def _copier_ip_pc(self):
        ip = self.derniere_connexion.get("ip_pc")
        if not ip:
            self.etat.configure(text="Adresse du PC inconnue : branchez d'abord le câble réseau.")
            return
        self.racine.clipboard_clear()
        self.racine.clipboard_append(ip)
        self.etat.configure(text=f"Adresse {ip} copiée : collez-la (Ctrl+V) dans « Adresses IP autorisées ».")

    def afficher_connexion(self, info: dict):
        if info.get("ip") != self.partage.get("ip"):
            return                       # réponse pour une ancienne adresse
        self.derniere_connexion = info
        ip, ip_pc = info.get("ip", ""), info.get("ip_pc", "")
        self.cx_pc.configure(text=ip_pc or "aucune")
        if info.get("joignable"):
            self.cx_couleur, etat = "vert", "Pare-feu joignable"
            conseil = (f"Le pare-feu répond. Si ce n'est pas déjà fait : activez l'API et autorisez l'adresse {ip_pc} "
                       "(étape 01 ci-dessous), puis cliquez sur « Tester l'accès API ».")
        else:
            self.cx_couleur, etat = "rouge", "Pare-feu injoignable"
            if not ip_pc:
                conseil = ("Votre PC n'est relié à aucun réseau. Branchez un câble entre votre PC et le port « Port1 » "
                           "du pare-feu.")
            elif not info.get("meme_reseau"):
                conseil = (f"Votre PC ({ip_pc}) n'est pas dans le même réseau que le pare-feu ({ip}). Branchez le "
                           "câble sur le port « Port1 » : votre PC recevra une adresse en 172.16.16.x. Si le pare-feu "
                           "a déjà une autre adresse, tapez-la dans « Adresse du pare-feu ».")
            else:
                conseil = ("Votre PC est dans le bon réseau mais le pare-feu ne répond pas. Vérifiez qu'il est allumé "
                           "(il lui faut 3 à 5 minutes pour démarrer) et que son adresse est la bonne.")
        self.cx_etat.configure(text=etat)
        self.cx_conseil.configure(text=conseil)
        self._peindre_voyant()

    def _nouvelle_fenetre(self, titre: str, largeur: int = 560):
        """Petite fenêtre annexe aux couleurs de l'outil. Renvoie (fenêtre, cadre intérieur)."""
        tk, t = self.tk, THEMES[self.theme]
        top = tk.Toplevel(self.racine, bg=t["fond"])
        top.title(titre)
        top.transient(self.racine)
        top.resizable(False, False)
        cadre = tk.Frame(top, bg=t["fond"], padx=26, pady=20, width=largeur)
        cadre.pack(fill="both", expand=True)
        _barre_de_titre(top, t, self.theme == "sombre")
        self.fenetres.append(top)
        return top, cadre

    def _centrer(self, top):
        top.update_idletasks()
        x = self.racine.winfo_rootx() + (self.racine.winfo_width() - top.winfo_width()) // 2
        y = self.racine.winfo_rooty() + (self.racine.winfo_height() - top.winfo_height()) // 3
        top.geometry(f"+{max(0, x)}+{max(0, y)}")
        top.lift()

    def _dialogue_api(self):
        """Demande l'identifiant et le mot de passe, puis vérifie l'accès à l'API (une seule tentative)."""
        tk, t = self.tk, THEMES[self.theme]
        ip = self.partage.get("ip", "")
        top, c = self._nouvelle_fenetre("Tester l'accès à l'API")
        tk.Label(c, text="TESTER L'ACCÈS À L'API", font=("Consolas", 9, "bold"), bg=t["fond"], fg=t["accent"],
                 anchor="w").pack(fill="x")
        tk.Label(c, text=f"Pare-feu {ip}", font=("Arial", 15, "bold"), bg=t["fond"], fg=t["texte"],
                 anchor="w").pack(fill="x", pady=(6, 0))
        tk.Label(c, text="Saisissez le compte administrateur du pare-feu (celui de sa page web). Il n'est utilisé que "
                         "pour ce test et n'est enregistré nulle part.", font=("Arial", 10), bg=t["fond"],
                 fg=t["texte2"], wraplength=480, justify="left", anchor="w").pack(fill="x", pady=(6, 12))
        champs = {}
        for libelle, cle, masque, defaut in (("Identifiant", "u", False, self.utilisateur_defaut),
                                             ("Mot de passe", "m", True, "")):
            tk.Label(c, text=libelle, font=("Arial", 9), bg=t["fond"], fg=t["texte2"], anchor="w").pack(fill="x")
            e = tk.Entry(c, font=("Consolas", 12), relief="flat", bd=7, highlightthickness=1, show="•" if masque else "",
                         bg=t["saisie"], fg=t["texte"], insertbackground=t["accent_vif"],
                         highlightbackground=t["bord_fort"], highlightcolor=t["accent"])
            e.insert(0, defaut)
            e.pack(fill="x", pady=(3, 10))
            champs[cle] = e
        boutons = tk.Frame(c, bg=t["fond"])
        boutons.pack(fill="x", pady=(6, 0))

        def tester(_e=None):
            u, m = champs["u"].get().strip(), champs["m"].get()
            if not u or not m:
                return
            fermer()
            self._afficher_test_api([(None, "Test en cours, patientez quelques secondes…", "")])
            threading.Thread(target=_tester_api, args=(ip, u, m, self.sorties), daemon=True).start()

        def fermer():
            top.destroy()
        _Bouton(self, boutons, "TESTER", tester, principal=True, icone=self.ic(0xE768)).pack(side="right")
        _Bouton(self, boutons, "Annuler", fermer).pack(side="right", padx=(0, 10))
        champs["m"].bind("<Return>", tester)
        top.bind("<Escape>", lambda e: fermer())
        self._centrer(top)
        champs["m"].focus_set()
        top.grab_set()

    def _afficher_test_api(self, etapes):
        """Résultat du test de l'API sous le bandeau : une ligne par vérification, avec quoi faire si c'est rouge."""
        tk, t = self.tk, THEMES[self.theme]
        for w in self.cx_api.winfo_children():
            w.destroy()
        self.cx_api.pack(fill="x", pady=(10, 0))
        tk.Frame(self.cx_api, height=1, bg=t["bord"]).pack(fill="x", pady=(0, 8))
        for ok, etape, conseil in etapes:
            symbole, couleur = ("•", t["texte2"]) if ok is None else (("✓", t["vert"]) if ok else ("✗", t["rouge"]))
            tk.Label(self.cx_api, text=f"{symbole}  {etape}", font=("Arial", 10, "bold"), bg=t["carte"], fg=couleur,
                     anchor="w", justify="left").pack(fill="x", pady=1)
            if conseil and ok is False:
                lab = tk.Label(self.cx_api, text=f"     Que faire : {conseil}", font=("Arial", 10), bg=t["carte"],
                               fg=t["texte"], anchor="w", justify="left",
                               wraplength=max(300, self.droite.winfo_width() - 80))
                lab.pack(fill="x", pady=(0, 4))
        if etapes and all(ok for ok, *_ in etapes):
            tk.Label(self.cx_api, text="Tout est prêt : vous pouvez envoyer une configuration au pare-feu.",
                     font=("Arial", 10, "bold"), bg=t["carte"], fg=t["vert"], anchor="w").pack(fill="x", pady=(6, 0))

    # ------------------------------------------------------------------ recherche du pare-feu, réglage du PC
    def _chercher(self):
        self.cx_chercher.configure(state="disabled")
        self.cx_etat.configure(text="Recherche…")
        self.cx_conseil.configure(text="Recherche du pare-feu sur le réseau de votre PC (environ 10 secondes)…")
        threading.Thread(target=_chercher_pare_feu, args=(self.sorties,), daemon=True).start()

    def _pare_feu_trouve(self, trouves: list):
        self.cx_chercher.configure(state="normal")
        if not trouves:
            self.cx_conseil.configure(text="Aucun pare-feu Sophos trouvé. Vérifiez qu'il est allumé (3 à 5 minutes de "
                                           "démarrage) et que le câble va de votre PC au port « Port1 ». Si votre PC "
                                           "n'a pas d'adresse en 172.16.16.x, cliquez sur « Régler mon PC ».")
            self._changer_ip_cible()
            return
        self.cx_ip.delete(0, "end")
        self.cx_ip.insert(0, trouves[0])
        self._changer_ip_cible()
        autres = f" (autres : {', '.join(trouves[1:])})" if len(trouves) > 1 else ""
        self.etat.configure(text=f"Pare-feu trouvé à l'adresse {trouves[0]}{autres}.")

    def _libelle_reglage(self):
        from .reseau import reglage_pc_en_attente
        self.cx_reglage.configure(text=f"{self.ic(0xE713)}  " + ("Remettre mon PC comme avant" if reglage_pc_en_attente()
                                                                else "Régler mon PC").strip())

    def _regler_pc(self):
        from tkinter import messagebox

        from . import reseau
        if reseau.reglage_pc_en_attente():
            if messagebox.askyesno("Remettre mon PC comme avant", "Remettre la carte réseau de votre PC comme elle était "
                                   "avant ?\nWindows va demander l'autorisation.", parent=self.racine):
                ok = reseau.remettre_pc()
                self.etat.configure(text="Carte réseau remise comme avant." if ok else "Réglage non fait.")
        elif messagebox.askyesno("Régler mon PC", "Votre PC va prendre l'adresse 172.16.16.20 sur sa carte réseau filaire, "
                                 "pour joindre un pare-feu neuf (172.16.16.16).\n\nWindows va demander l'autorisation. "
                                 "Le réglage actuel est noté : le bouton « Remettre mon PC comme avant » le rétablira.",
                                 parent=self.racine):
            ok, message = reseau.regler_pc_filaire()
            self.etat.configure(text=message)
        self._libelle_reglage()
        self.partage["maintenant"] = True

    def _dessiner_ports(self, toile=None):
        """Étape 01 : la face arrière du pare-feu, avec les deux câbles à brancher."""
        c, t = toile or self.dessin_ports, THEMES[self.theme]
        c.delete("all")
        x0, y0, pas = 4, 6, 46
        c.create_rectangle(x0, y0, x0 + 8 * pas + 10, y0 + 40, fill=t["panneau"], outline=t["bord_fort"])
        for k in range(1, 9):
            x = x0 + 8 + (k - 1) * pas
            couleur = t["vert"] if k == 1 else (t["accent"] if k == 2 else t["bord_fort"])
            c.create_rectangle(x, y0 + 8, x + pas - 10, y0 + 32, fill=couleur, outline="")
            c.create_text(x + (pas - 10) / 2, y0 + 20, text=str(k), fill="#FFFFFF", font=("Consolas", 9, "bold"))
        c.create_text(x0 + 8 + (pas - 10) / 2, y0 + 54, text="votre PC", fill=t["vert"], font=("Arial", 9, "bold"))
        c.create_text(x0 + 8 + pas + (pas - 10) / 2, y0 + 54, text="box", fill=t["accent"], font=("Arial", 9, "bold"))
        c.create_text(x0 + 8 * pas + 26, y0 + 20, anchor="w", fill=t["texte2"], font=("Arial", 9),
                      text="Port1 : câble vers votre PC (puis vers le switch du client)\n"
                           "Port2 : câble vers la box Internet")

    # ------------------------------------------------------------------ mode simple, recherche
    def changer_mode_simple(self):
        self.simple = not self.simple
        try:
            from .poste import enregistrer
            enregistrer({"mode_simple": self.simple})
        except OSError:
            pass
        self.filtrer_actions()

    def filtrer_actions(self):
        """Colonne de gauche : mode simple et recherche (sur le libellé court et le libellé complet)."""
        import unicodedata

        def simplifier(t):
            return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
        texte = self.recherche.get().strip()
        texte = "" if texte == "Rechercher…" else simplifier(texte)
        for g, lignes in self.groupes_lignes:
            g.pack_forget()
            for l in lignes:
                l.cadre.pack_forget()
        for g, lignes in self.groupes_lignes:
            visibles = [l for l in lignes if (not self.simple or texte or l.cle in ACTIONS_SIMPLES)
                        and (not texte or texte in simplifier(l.complet + " " + l.nom.cget("text")))]
            if visibles:
                g.pack(fill="x", pady=(6, 2))
                for l in visibles:
                    l.cadre.pack(fill="x", pady=1)
        self.bouton_simple.configure(text=f"{self.ic(0xE8D3)}  " + ("Mode simple : oui" if self.simple
                                                                   else "Mode simple : non").strip())
        if texte:
            from .glossaire import chercher
            res = chercher(texte)
            self.indice(f"{res[0][0]} : {res[0][1]}" if res else None)

    def _lancer_premiere(self):
        for _g, lignes in self.groupes_lignes:
            for l in lignes:
                if l.cadre.winfo_ismapped():
                    l._clic()
                    return

    def _afficher_attente(self):
        """Étape 03 de l'accueil : un bouton par client préparé mais pas encore envoyé."""
        if not hasattr(self, "zone_attente"):
            return
        from . import attente
        tk, t = self.tk, THEMES[self.theme]
        for w in self.zone_attente.winfo_children():
            w.destroy()
        liste = attente.lister()
        if not liste:
            self.zone_attente.pack_forget()
            return
        self.zone_attente.pack(fill="x", pady=(8, 0))
        tk.Label(self.zone_attente, text=f"PRÊT(S) À ENVOYER : {len(liste)}", font=("Consolas", 9, "bold"),
                 bg=t["carte"], fg=t["jaune"], anchor="w").pack(fill="x", pady=(0, 4))
        ligne = tk.Frame(self.zone_attente, bg=t["carte"])
        ligne.pack(fill="x")
        from .__main__ import action_appliquer
        for x in liste[:6]:
            _Bouton(self, ligne, x["client"], lambda f=x["fichier"], c=x["client"]: self.lancer(
                lambda: action_appliquer(f), f"Envoyer la configuration de {c}", "appliquer"),
                icone=self.ic(0xE724), petit=True, aide=f"Préparé le {x['date'][:10]} — {x['fichier']}").pack(
                side="left", padx=(0, 8))

    def _afficher_sante(self, points: list):
        """En bas de l'accueil : l'état de l'outil (vert si tout va bien, sinon ce qu'il faut corriger)."""
        tk, t = self.tk, THEMES[self.theme]
        if not hasattr(self, "accueil_contenu"):
            return
        if not hasattr(self, "carte_sante"):
            self.carte_sante = self.peint(tk.Frame(self.accueil_contenu, highlightthickness=1, padx=18, pady=10),
                                          bg="carte", highlightbackground="bord", highlightcolor="bord")
            self.carte_sante.pack(fill="x", pady=(0, 10))
        for w in self.carte_sante.winfo_children():
            w.destroy()
        mauvais = [p for p in points if not p[0]]
        tk.Label(self.carte_sante, text="ÉTAT DE L'OUTIL : " + ("TOUT VA BIEN" if not mauvais
                                                              else f"{len(mauvais)} POINT(S) À CORRIGER"),
                 font=("Consolas", 9, "bold"), bg=t["carte"], fg=t["vert"] if not mauvais else t["jaune"],
                 anchor="w").pack(fill="x")
        for ok, quoi, faire in (mauvais or points):
            tk.Label(self.carte_sante, text=f"{'✓' if ok else '✗'}  {quoi}" + (f" — {faire}" if faire else ""),
                     font=("Arial", 9), bg=t["carte"], fg=t["texte2"] if ok else t["rouge"], anchor="w", justify="left",
                     wraplength=max(300, self.droite.winfo_width() - 80)).pack(fill="x", pady=1)

    # ------------------------------------------------------------------ question : informations, fichier, signature
    def _infos_question(self, q: dict):
        """Sous l'explication : d'où vient la réponse proposée, et les mots techniques expliqués."""
        tk, t = self.tk, THEMES[self.theme]
        if not hasattr(self, "c_infos"):
            self.c_infos = self.peint(tk.Frame(self.carte), bg="carte")
        origine = q.get("origine")
        if q.get("technique"):
            self.c_infos.pack(fill="x", pady=(8, 0), before=self.c_zone)
            tk.Label(self.c_infos, text=f"Question technique : {q['technique']}", font=("Arial", 9), bg=t["carte"],
                     fg=t["discret"], anchor="w", justify="left").pack(fill="x")
        mots = self._mots_techniques(" ".join([str(q.get("question") or ""), str(q.get("aide") or "")]
                                              + [str(o) for o in (q.get("options") or [])]))
        if not origine and not mots:
            return
        self.c_infos.pack(fill="x", pady=(8, 0), before=self.c_zone)
        self.c_infos.pack(fill="x", pady=(8, 0), before=self.c_zone)
        if origine:
            tk.Label(self.c_infos, text=f"✓  Réponse proposée d'après : {origine}", font=("Arial", 10, "bold"),
                     bg=t["carte"], fg=t["vert"], anchor="w").pack(fill="x")
        if mots:
            ligne = tk.Frame(self.c_infos, bg=t["carte"])
            ligne.pack(fill="x", pady=(4, 0))
            tk.Label(ligne, text="Mots expliqués :", font=("Arial", 9), bg=t["carte"], fg=t["discret"]).pack(side="left")
            definition = tk.Label(self.c_infos, text="", font=("Arial", 10), bg=t["carte"], fg=t["cyan"], anchor="w",
                                  justify="left", wraplength=max(300, self.droite.winfo_width() - 80))
            for mot, sens in mots:
                b = _Bouton(self, ligne, mot, lambda m=mot, s=sens: (definition.configure(text=f"{m} : {s}"),
                                                                    definition.pack(fill="x", pady=(4, 0))),
                            petit=True)
                b.pack(side="left", padx=(6, 0))
                self.dynamiques.append(b)

    @staticmethod
    def _mots_techniques(texte: str) -> list[tuple[str, str]]:
        from .glossaire import TERMES
        trouves = []
        for mot, sens in TERMES.items():
            if re.search(rf"(?<![\w-]){re.escape(mot)}(?![\w-])", texte, re.IGNORECASE):
                trouves.append((mot, sens))
        trouves.sort(key=lambda x: -len(x[0]))
        garde = []
        for mot, sens in trouves:            # « VPN site à site » plutôt que « VPN » et « site »
            if not any(mot.lower() in g.lower() for g, _ in garde):
                garde.append((mot, sens))
        return garde[:5]

    def _parcourir(self, types):
        from tkinter import filedialog
        types = [tuple(t) for t in (types or [])] + [("Tous les fichiers", "*.*")]
        chemin = filedialog.askopenfilename(parent=self.racine, title="Choisir le fichier", filetypes=types)
        if chemin:
            self.saisie.delete(0, "end")
            self.saisie.insert(0, os.path.normpath(chemin))
            self._verifier_saisie()

    def _zone_signature(self):
        """Cadre où le client signe avec la souris ou le doigt."""
        import json as _json
        tk, t = self.tk, THEMES[self.theme]
        self.c_boutons.pack(fill="x")
        toile = tk.Canvas(self.c_boutons, width=520, height=170, bg="#FFFFFF", highlightthickness=2,
                          highlightbackground=t["accent"], cursor="pencil")
        toile.pack(anchor="w")
        traits: list = []

        def debut(e):
            traits.append([[e.x, e.y]])

        def suite(e):
            if traits:
                x0, y0 = traits[-1][-1]
                traits[-1].append([e.x, e.y])
                toile.create_line(x0, y0, e.x, e.y, fill="#1d1d22", width=2.4, capstyle="round", smooth=True)

        def effacer():
            traits.clear()
            toile.delete("all")
        toile.bind("<ButtonPress-1>", debut)
        toile.bind("<B1-Motion>", suite)
        boutons = tk.Frame(self.c_boutons, bg=t["carte"])
        boutons.pack(fill="x", pady=(8, 0))
        for b in (_Bouton(self, boutons, "VALIDER LA SIGNATURE",
                          lambda: self.envoyer(_json.dumps(traits), "(signature)") if traits else None,
                          principal=True, icone=self.ic(0xE73E)),
                  _Bouton(self, boutons, "Effacer", effacer, icone=self.ic(0xE74D)),
                  _Bouton(self, boutons, "Sans signature", lambda: self.envoyer("", "(sans signature)"))):
            b.pack(side="left", padx=(0, 8))
            self.dynamiques.append(b)

    # ------------------------------------------------------------------ demander de l'aide
    def _dialogue_aide(self):
        tk, t = self.tk, THEMES[self.theme]
        top, c = self._nouvelle_fenetre("Demander de l'aide")
        tk.Label(c, text="DEMANDER DE L'AIDE", font=("Consolas", 9, "bold"), bg=t["fond"], fg=t["accent"],
                 anchor="w").pack(fill="x")
        tk.Label(c, text="Décrivez le problème en quelques mots", font=("Arial", 15, "bold"), bg=t["fond"],
                 fg=t["texte"], anchor="w").pack(fill="x", pady=(6, 0))
        tk.Label(c, text="L'outil prépare un dossier (.zip) avec tout ce qu'il faut à un expert : ce que vous avez vu à "
                         "l'écran, l'état de la connexion, la configuration du PC, le fichier du client et ses rapports. "
                         "Aucun mot de passe n'y est mis.", font=("Arial", 10), bg=t["fond"], fg=t["texte2"],
                 wraplength=500, justify="left", anchor="w").pack(fill="x", pady=(6, 10))
        message = tk.Text(c, height=5, width=60, font=("Arial", 11), relief="flat", bd=8, wrap="word", bg=t["saisie"],
                          fg=t["texte"], insertbackground=t["accent_vif"], highlightthickness=1,
                          highlightbackground=t["bord_fort"], highlightcolor=t["accent"])
        message.pack(fill="x")
        tk.Label(c, text="Client concerné (facultatif)", font=("Arial", 9), bg=t["fond"], fg=t["texte2"],
                 anchor="w").pack(fill="x", pady=(10, 0))
        client = tk.Entry(c, font=("Consolas", 11), relief="flat", bd=6, bg=t["saisie"], fg=t["texte"],
                          insertbackground=t["accent_vif"], highlightthickness=1, highlightbackground=t["bord_fort"],
                          highlightcolor=t["accent"])
        client.pack(fill="x", pady=(3, 0))
        bas = tk.Frame(c, bg=t["fond"])
        bas.pack(fill="x", pady=(14, 0))

        def creer():
            from .assistance import creer as creer_dossier
            try:
                f = creer_dossier(message.get("1.0", "end").strip(), client.get().strip(),
                                  self.texte.get("1.0", "end"), self.derniere_connexion)
            except Exception as exc:
                self.etat.configure(text=f"Dossier d'aide non créé : {exc}")
                top.destroy()
                return
            top.destroy()
            self.racine.clipboard_clear()
            self.racine.clipboard_append(str(f.resolve()))
            self.etat.configure(text=f"Dossier d'aide prêt : {f.name}. Envoyez-le par e-mail (son chemin est copié).")
            self._ouvrir_fichier(str(f.resolve().parent))
        _Bouton(self, bas, "PRÉPARER LE DOSSIER", creer, principal=True, icone=self.ic(0xE73E)).pack(side="right")
        _Bouton(self, bas, "Annuler", top.destroy).pack(side="right", padx=(0, 10))
        self._centrer(top)
        message.focus_set()

    # ------------------------------------------------------------------ visite guidée
    def visite_guidee(self):
        """Présentation en quelques bulles : où regarder, où cliquer."""
        if self.en_cours:
            return
        self.montrer_accueil()
        etapes = [
            (lambda: self.cx_ip.master.master.master, "La connexion au pare-feu",
             "Ici, l'outil vérifie en permanence que votre PC voit le pare-feu. Vert : tout va bien. Rouge : la phrase "
             "en dessous dit quoi faire. « Trouver le pare-feu » cherche son adresse tout seul."),
            (lambda: getattr(self, "carte_01", None), "Étape 1 : préparer le pare-feu",
             "À faire une seule fois sur un boîtier neuf : deux câbles à brancher, puis quelques clics sur sa page."),
            (lambda: getattr(self, "carte_02", None), "Étape 2 : décrire le client",
             "Cliquez sur « Commencer ». Chaque question est expliquée et une réponse est déjà proposée : en cas de "
             "doute, gardez-la. Le mode express ne pose que l'indispensable."),
            (lambda: self.liste, "Toutes les actions",
             "Les autres actions sont ici : envoyer un fichier client, contrôle de sécurité, tableau de bord de vos "
             "clients, compte rendu à faire signer…"),
            (lambda: self.bouton_aide.cadre, "Bloqué ?",
             "« Demander de l'aide » prépare un dossier pour un expert, avec tout ce qu'il faut pour comprendre le "
             "problème. Bonne configuration !"),
        ]
        self._visite = {"etapes": etapes, "rang": 0, "bulle": None}
        self.racine.after(150, self._etape_visite)

    def _etape_visite(self):
        tk, t = self.tk, THEMES[self.theme]
        v = getattr(self, "_visite", None)
        if not v:
            return
        if v["bulle"] is not None:
            v["bulle"].destroy()
        if v["rang"] >= len(v["etapes"]):
            self._fin_visite()
            return
        cible, titre_bulle, texte_bulle = v["etapes"][v["rang"]]
        widget = cible()
        bulle = tk.Frame(self.racine, bg=t["carte"], highlightthickness=2, highlightbackground=t["accent"],
                         highlightcolor=t["accent"], padx=16, pady=12)
        v["bulle"] = bulle
        tk.Label(bulle, text=f"{v['rang'] + 1} / {len(v['etapes'])} · {titre_bulle.upper()}", font=("Consolas", 9, "bold"),
                 bg=t["carte"], fg=t["accent"], anchor="w").pack(fill="x")
        tk.Label(bulle, text=texte_bulle, font=("Arial", 11), bg=t["carte"], fg=t["texte"], wraplength=360,
                 justify="left", anchor="w").pack(fill="x", pady=(6, 10))
        bas = tk.Frame(bulle, bg=t["carte"])
        bas.pack(fill="x")
        dernier = v["rang"] == len(v["etapes"]) - 1

        def suivant():
            v["rang"] += 1
            self._etape_visite()
        _Bouton(self, bas, "Terminer" if dernier else "Suivant", suivant, principal=True, petit=True).pack(side="right")
        if not dernier:
            _Bouton(self, bas, "Passer la visite", self._fin_visite, petit=True).pack(side="right", padx=(0, 8))
        self.racine.update_idletasks()
        x, y = 360, 160
        if widget is not None:
            try:
                wx = widget.winfo_rootx() - self.racine.winfo_rootx()
                wy = widget.winfo_rooty() - self.racine.winfo_rooty()
                x = min(max(10, wx + 30), self.racine.winfo_width() - bulle.winfo_reqwidth() - 10)
                y = wy + widget.winfo_height() + 8
                if y + bulle.winfo_reqheight() > self.racine.winfo_height() - 10:
                    y = max(10, wy - bulle.winfo_reqheight() - 8)
            except Exception:
                pass
        bulle.place(x=x, y=y)
        bulle.lift()

    def _fin_visite(self):
        v = getattr(self, "_visite", None)
        if v and v["bulle"] is not None:
            v["bulle"].destroy()
        self._visite = None
        try:
            from .poste import enregistrer
            enregistrer({"visite_faite": True})
        except OSError:
            pass

    # ------------------------------------------------------------------ fin d'intervention
    def fenetre_mots_de_passe(self, client: str, liste: list, coffre: bool = False):
        """Mots de passe générés : affichés dans une fenêtre, chacun avec un bouton Copier."""
        from tkinter import messagebox
        tk, t = self.tk, THEMES[self.theme]
        top, c = self._nouvelle_fenetre("Mots de passe générés", 700)
        tk.Label(c, text=f"MOTS DE PASSE — {client}".upper(), font=("Consolas", 9, "bold"), bg=t["fond"],
                 fg=t["accent"], anchor="w").pack(fill="x")
        tk.Label(c, text="Notez ces mots de passe maintenant", font=("Arial", 15, "bold"), bg=t["fond"],
                 fg=t["texte"], anchor="w").pack(fill="x", pady=(6, 0))
        avis = ("Ils sont aussi dans le coffre KeePass du client." if coffre else
                "Ils ne sont enregistrés nulle part : une fois cette fenêtre fermée, ils ne seront plus affichés.")
        tk.Label(c, text="Copiez-les dans votre coffre-fort de mots de passe (bouton Copier, puis Ctrl+V). " + avis,
                 font=("Arial", 10), bg=t["fond"], fg=t["jaune"], wraplength=640, justify="left",
                 anchor="w").pack(fill="x", pady=(6, 14))
        grille = tk.Frame(c, bg=t["carte"], highlightthickness=1, highlightbackground=t["bord"], padx=14, pady=10)
        grille.pack(fill="x")
        grille.columnconfigure(1, weight=1)

        def copier(valeur, libelle):
            self.racine.clipboard_clear()
            self.racine.clipboard_append(valeur)
            info.configure(text=f"Copié : {libelle}")
        for i, (libelle, valeur) in enumerate(liste):
            tk.Label(grille, text=libelle, font=("Arial", 10), bg=t["carte"], fg=t["texte2"], anchor="w",
                     wraplength=280, justify="left").grid(row=i, column=0, sticky="w", pady=4, padx=(0, 14))
            champ = tk.Entry(grille, font=("Consolas", 12, "bold"), relief="flat", bd=4, readonlybackground=t["saisie"],
                             fg=t["texte"], highlightthickness=0)
            champ.insert(0, valeur)
            champ.configure(state="readonly")
            champ.grid(row=i, column=1, sticky="ew", pady=4)
            _Bouton(self, grille, "Copier", lambda v=valeur, l=libelle: copier(v, l), icone=self.ic(0xE8C8),
                    petit=True).grid(row=i, column=2, padx=(10, 0))
        info = tk.Label(c, text="", font=("Consolas", 9), bg=t["fond"], fg=t["vert"], anchor="w")
        info.pack(fill="x", pady=(8, 0))
        bas = tk.Frame(c, bg=t["fond"])
        bas.pack(fill="x", pady=(8, 0))

        def tout_copier():
            copier("\n".join(f"{l} : {v}" for l, v in liste), "tous les mots de passe")

        def fermer():
            if coffre or messagebox.askyesno("Mots de passe", "Avez-vous bien noté tous les mots de passe ?\n"
                                             "Ils ne pourront plus être affichés.", parent=top):
                top.destroy()
        _Bouton(self, bas, "J'AI NOTÉ LES MOTS DE PASSE", fermer, principal=True, icone=self.ic(0xE73E)).pack(
            side="right")
        _Bouton(self, bas, "Tout copier", tout_copier, icone=self.ic(0xE8C8)).pack(side="right", padx=(0, 10))
        top.protocol("WM_DELETE_WINDOW", fermer)
        self._centrer(top)

    def ajouter_fichiers(self, fichiers: list):
        """Fichiers créés : un bouton pour ouvrir chacun, au-dessus du déroulement."""
        tk = self.tk
        if not fichiers:
            return
        if not self.resultats.winfo_ismapped():
            for w in self.resultats_boutons.winfo_children():
                w.destroy()
            self.resultats.pack(fill="x", pady=(0, 8), before=self.cadre_journal)
        for libelle, chemin in fichiers:
            if chemin.startswith("action:"):
                _Bouton(self, self.resultats_boutons, libelle, lambda c=chemin[7:]: self.lancer_cle(c),
                        icone=self.ic(0xE7A7), petit=True).pack(side="left", padx=(0, 8), pady=(0, 4))
                continue
            icone = 0xEA90 if chemin.lower().endswith(".pdf") else 0xE8A5
            _Bouton(self, self.resultats_boutons, libelle, lambda c=chemin: self._ouvrir_fichier(c),
                    icone=self.ic(icone), petit=True, aide=chemin).pack(side="left", padx=(0, 8), pady=(0, 4))
        vrais = [c for _l, c in fichiers if not c.startswith("action:")]
        dossier = os.path.dirname(vrais[0]) if vrais else ""
        if dossier and not any(getattr(w, "_dossier", False) for w in self.resultats_boutons.winfo_children()):
            b = _Bouton(self, self.resultats_boutons, "Ouvrir le dossier", lambda: self._ouvrir_fichier(dossier),
                        icone=self.ic(0xE8B7), petit=True, aide=dossier)
            b.cadre._dossier = True
            b.pack(side="left", padx=(0, 8), pady=(0, 4))
        tk.Misc.update_idletasks(self.racine)

    def _ouvrir_fichier(self, chemin: str):
        try:
            if os.name == "nt":
                os.startfile(chemin)  # noqa: S606 - fichier créé par l'outil
            else:
                import webbrowser
                webbrowser.open(f"file://{chemin}")
        except OSError as exc:
            self.etat.configure(text=f"Impossible d'ouvrir {chemin} : {exc}")

    # ------------------------------------------------------------------ vues
    def montrer_accueil(self):
        if self.en_cours or self.vue == "accueil":
            return
        self.journal.pack_forget()
        self.accueil.pack(fill="both", expand=True)
        self.vue = "accueil"
        self.partage["actif"] = True
        self.partage["maintenant"] = True
        self._afficher_attente()
        self.fil.configure(text="ACCUEIL")
        self.titre.configure(text="Configurer un pare-feu Sophos")
        self.sous_titre.configure(text="Suivez les 3 étapes ci-dessous, dans l'ordre. "
                                       "Aucune connaissance technique n'est nécessaire.")
        self.bouton_accueil.pack_forget()

    def montrer_journal(self):
        if self.vue == "journal":
            return
        self.accueil.pack_forget()
        self.journal.pack(fill="both", expand=True)
        self.vue = "journal"
        self.partage["actif"] = False
        self.racine.unbind_all("<MouseWheel>")
        self.bouton_accueil.pack(side="right", padx=(0, 10))

    # ------------------------------------------------------------------ confort
    def appliquer_theme(self):
        t = THEMES[self.theme]
        self.racine.configure(bg=t["fond"])
        for widget, options in self.peints:
            try:
                widget.configure(**{opt: t[cle] for opt, cle in options.items()})
            except self.tk.TclError:      # widget détruit
                pass
        self.texte.configure(bg=t["journal"], fg=t["texte"], insertbackground=t["accent_vif"],
                             selectbackground=t["accent"], selectforeground="#FFFFFF", font=("Consolas", self.taille))
        for nom in ("rouge", "vert", "jaune", "cyan", "gris"):
            self.texte.tag_configure(nom, foreground=t[nom])
        self.texte.tag_configure("gras", font=("Consolas", self.taille, "bold"))
        self.texte.tag_configure("titre", foreground=t["accent"], font=("Consolas", self.taille, "bold"),
                                 spacing1=8, spacing3=4)
        self.texte.tag_configure("reponse", foreground=t["accent_vif"], font=("Consolas", self.taille, "bold"))
        self.saisie.configure(font=("Consolas", self.taille + 2))
        self.progression.configure(bg=t["fond"])
        self.style.configure("X.Vertical.TScrollbar", background=t["bord_fort"], troughcolor=t["journal"],
                             bordercolor=t["journal"], lightcolor=t["bord_fort"], darkcolor=t["bord_fort"],
                             arrowcolor=t["discret"], gripcount=0, arrowsize=8, width=8, relief="flat")
        self.style.map("X.Vertical.TScrollbar", background=[("pressed", t["accent"]), ("active", t["discret"])])
        self.elements = [e for e in self.elements if e.cadre.winfo_exists()]
        for e in self.elements:
            e.peindre()
        self._peindre_voyant()
        for b in self.boutons:
            b.peindre()
        if hasattr(self, "dessin_ports"):
            self._dessiner_ports()
        self._degrade()
        self._dessiner_progression()
        _barre_de_titre(self.racine, t, self.theme == "sombre")

    def _ajuster_largeurs(self, largeur: int):
        for widget, marge in self.textes_longs:
            widget.configure(wraplength=max(200, largeur - marge))

    def _degrade(self):
        """Fine ligne sous l'en-tête : rouge à gauche, qui s'estompe vers la droite (comme XPhare)."""
        t = THEMES[self.theme]
        c = self.ligne_tete
        c.delete("all")
        largeur = max(1, c.winfo_width())
        c.configure(bg=t["fond"])
        pas = 6
        for x in range(0, largeur, pas):
            r = x / largeur
            couleur = (_melanger(t["accent"], t["bord_fort"], r / 0.18) if r < 0.18
                       else _melanger(t["bord_fort"], t["ligne_fin"], (r - 0.18) / 0.82))
            c.create_line(x, 0, x + pas, 0, fill=couleur, width=2)

    def _dessiner_progression(self):
        t = THEMES[self.theme]
        c = self.progression
        c.delete("all")
        if not self.etape_en_cours:
            return
        i, total = self.etape_en_cours
        largeur = max(1, c.winfo_width())
        c.create_rectangle(0, 1, largeur, 5, fill=t["bord"], outline="")
        fin = int(largeur * min(1.0, (i + 1) / (total + 1)))
        c.create_rectangle(0, 1, fin, 5, fill=t["accent"], outline="")

    def _focus_saisie(self, focus: bool):
        t = THEMES[self.theme]
        if str(self.saisie.cget("state")) == "normal":
            self.saisie.configure(bg=t["saisie_focus"] if focus else t["saisie"])

    def _molette_gauche(self, e):
        self.liste.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")

    def _horloge(self):
        self.date.configure(text=time.strftime("%d/%m/%Y  %H:%M"))
        self.racine.after(20000, self._horloge)

    def indice(self, texte):
        """Ligne d'aide du pied : libellé complet de l'élément survolé."""
        self.indication.configure(text=texte or "")

    def _enregistrer_reglages(self):
        try:
            from .poste import enregistrer
            enregistrer({"theme": self.theme, "taille_texte": self.taille})
        except OSError:
            pass

    def changer_taille(self, delta: int):
        self.taille = max(8, min(20, self.taille + delta))
        self.appliquer_theme()
        self._enregistrer_reglages()

    def changer_theme(self):
        self.theme = "sombre" if self.theme == "clair" else "clair"
        self.appliquer_theme()
        self._enregistrer_reglages()

    def ouvrir(self, dossier: str):
        from pathlib import Path

        from .__main__ import ouvrir
        Path(dossier).mkdir(exist_ok=True)
        ouvrir(Path(dossier).resolve())

    def effacer(self):
        self.texte.configure(state="normal")
        self.texte.delete("1.0", "end")
        self.texte.configure(state="disabled")

    def afficher_rappels(self):
        try:
            from .rappels import calculer
            rappels = calculer()
        except Exception:
            return
        if not rappels:
            return
        urgents = sum(1 for r in rappels if r.urgence == 1)
        self.bouton_rappels.configure(text=f"{self.ic(0xE7BA)}  {len(rappels)} rappel(s)".strip())
        self.bouton_rappels.pack(side="right", padx=(0, 14))
        if urgents:
            self.bouton_rappels.label.configure(fg=THEMES[self.theme]["jaune"])
        self.ecrire("RAPPELS\n", ("titre",))
        for r in rappels[:8]:
            couleur = "31" if r.urgence == 1 else "33"
            self.ecrire(f"  \x1b[{couleur}m■\x1b[0m {r.client} : {r.texte}\n")
        if len(rappels) > 8:
            self.ecrire(f"  … et {len(rappels) - 8} autre(s) : action « Rappels ».\n")
        self.ecrire("\n")

    # ------------------------------------------------------------------ affichage
    def ecrire(self, t: str, styles_en_plus: tuple = ()):
        self.texte.configure(state="normal")
        for morceau, styles in decouper_ansi(t):
            self.texte.insert("end", morceau, styles + styles_en_plus)
        self.texte.configure(state="disabled")
        self.texte.see("end")

    def relever(self):
        try:
            while True:
                genre, val = self.sorties.get_nowait()
                if genre == "texte":
                    self.ecrire(val)
                elif genre == "carte":
                    self.recevoir_carte(val)
                elif genre == "question":
                    masque, invite = val if isinstance(val, tuple) else (val, "")
                    self.attendre_reponse(masque=masque, invite=invite)
                elif genre == "fin":
                    self.fin_action()
                elif genre == "redemarrer":
                    self.redemarrer_apres_maj()
                elif genre == "connexion":
                    self.afficher_connexion(val)
                elif genre == "test_api":
                    self._afficher_test_api(val)
                elif genre == "pare_feu_trouve":
                    self._pare_feu_trouve(val)
                elif genre == "sante":
                    self._afficher_sante(val)
                elif genre == "etat":
                    self.etat.configure(text=val)
        except queue.Empty:
            pass
        self.racine.after(50, self.relever)

    def recevoir_carte(self, q: dict):
        genre = q.get("genre")
        if genre == "titre":
            t = re.sub(r"^\d+\.\s*", "", str(q.get("texte", ""))).strip()
            self.section = t
        elif genre == "etape":
            self.dans_assistant = True
            i, total = int(q.get("index", 0)), int(q.get("total", 1))
            self.etape_en_cours = (i, total)
            self.fil.configure(text=(f"ASSISTANT · ÉTAPE {min(i + 1, total)} SUR {total}" if i < total
                                     else "ASSISTANT · DERNIÈRE ÉTAPE")
                               + (" · MODE EXPRESS" if getattr(self, "mode_express", False) else ""))
            self.titre.configure(text=str(q.get("nom", "")))
            self.sous_titre.configure(text="Répondez aux questions en bas. En cas de doute, gardez la réponse "
                                           "proposée.")
            self.progression.pack(fill="x", pady=(8, 0), before=self.espace_titre)
            self._dessiner_progression()
        elif genre == "etape_fin":
            self.etape_en_cours = (1, 0)
            self.fil.configure(text="ASSISTANT · TERMINÉ")
            self._dessiner_progression()
        elif genre == "mots_de_passe":
            self.fenetre_mots_de_passe(str(q.get("client", "")), list(q.get("liste") or []), bool(q.get("coffre")))
        elif genre == "fichiers":
            self.ajouter_fichiers(list(q.get("fichiers") or []))
        elif genre == "mode":
            self.mode_express = bool(q.get("express"))
        else:
            self.carte_attente = q

    # ------------------------------------------------------------------ questions
    def _vider_question(self):
        for b in self.dynamiques:
            b.detruire()
        self.dynamiques = []
        for w in self.c_boutons.winfo_children():
            w.destroy()
        for w in (self.ligne_saisie, self.c_note, self.c_boutons, self.c_aide, self.c_pied):
            w.pack_forget()
        if hasattr(self, "c_infos"):
            for w in self.c_infos.winfo_children():
                w.destroy()
            self.c_infos.pack_forget()

    def attendre_reponse(self, masque: bool, invite: str = ""):
        q = self.carte_attente or deviner_question(invite, masque)
        if masque:
            q = dict(q, genre="secret")
        self.carte_attente = None
        self.question = q
        self.masque = masque
        self.montrer_journal()
        self._vider_question()
        tk, ic = self.tk, self.ic
        genre = q.get("genre", "texte")
        self.c_type.configure(text=self.section.upper() if self.section else "QUESTION")
        self.c_question.configure(text=q.get("question") or "Votre réponse")
        if self.simple and q.get("question") in SIMPLES:
            q = dict(q, technique=q["question"])
            self.question = q
            self.c_question.configure(text=SIMPLES[q["question"]])
        aide = (q.get("aide") or "").strip()
        if aide:
            self.c_aide.configure(text=aide)
            self.c_aide.pack(fill="x", pady=(6, 0), before=self.c_zone)
        self._infos_question(q)

        self.saisie.configure(state="normal", show="•" if masque else "")
        self._bordure_saisie(None)
        self.note_base = ""
        self.saisie.delete(0, "end")
        for b in self.boutons_reponse:
            b.configure(state="normal")

        if genre == "oui_non":
            defaut = bool(q.get("defaut"))
            self.c_boutons.pack(fill="x")
            for valeur, libelle, glyphe in ((True, "Oui", 0xE73E), (False, "Non", 0xE711)):
                texte = f"{libelle}   (réponse proposée)" if valeur == defaut else libelle
                b = _Bouton(self, self.c_boutons, texte, lambda v=valeur, l=libelle: self.envoyer("o" if v else "n", l),
                            principal=valeur == defaut, icone=ic(glyphe), grand=True)
                b.pack(side="left", padx=(0, 10))
                self.dynamiques.append(b)
            self._note("Touche Entrée = réponse proposée.")
        elif genre == "choix":
            options = list(q.get("options") or [])
            defaut = int(q.get("defaut") or 1)
            self.c_boutons.pack(fill="x")
            colonnes = 2 if len(options) > 5 else 1
            for c in range(colonnes):
                self.c_boutons.columnconfigure(c, weight=1, uniform="choix")
            for n, libelle in enumerate(options, 1):
                texte = f"{n}.  {libelle}" + ("     ← proposé" if n == defaut else "")
                b = _Bouton(self, self.c_boutons, texte, lambda n=n, l=libelle: self.envoyer(str(n), l),
                            principal=n == defaut, gauche=True)
                b.label.configure(font=("Arial", 10, "bold" if n == defaut else "normal"), pady=7)
                ligne, col = divmod(n - 1, colonnes)
                b.grid(row=ligne, column=col, sticky="ew", padx=(0, 8), pady=(0, 6))
                self.dynamiques.append(b)
            self._note("Cliquez sur votre choix. Touche Entrée = choix proposé.")
        elif genre == "continuer":
            self.c_boutons.pack(fill="x")
            b = _Bouton(self, self.c_boutons, "Continuer", lambda: self.envoyer("", "Continuer"), principal=True,
                        icone=ic(0xE768))
            b.pack(side="left")
            self.dynamiques.append(b)
        elif genre == "consigne":
            self.c_type.configure(text="À FAIRE MAINTENANT")
            if q.get("illustration") == "ports":
                toile = self.tk.Canvas(self.c_boutons, height=74, highlightthickness=0, bd=0, bg=THEMES[self.theme]["carte"])
                self.c_boutons.pack(fill="x")
                toile.pack(fill="x", pady=(0, 10))
                self.racine.after(30, lambda: self._dessiner_ports(toile))
            self.c_boutons.pack(fill="x")
            ligne = self.tk.Frame(self.c_boutons, bg=THEMES[self.theme]["carte"])
            ligne.pack(fill="x")
            for b in (_Bouton(self, ligne, (q.get("bouton") or "C'est fait").upper(), lambda: self.envoyer("", "C'est fait"),
                              principal=True, icone=ic(0xE73E), grand=True),
                      _Bouton(self, ligne, "J'ai un problème", lambda: self.envoyer("?", "J'ai un problème"),
                              icone=ic(0xE897), grand=True)):
                b.pack(side="left", padx=(0, 10))
                self.dynamiques.append(b)
        elif genre == "signature":
            self._zone_signature()
        else:   # texte, fichier ou mot de passe
            self.ligne_saisie.pack(fill="x")
            if genre == "fichier":
                self.c_boutons.pack(fill="x", pady=(8, 0))
                b = _Bouton(self, self.c_boutons, "Parcourir…", lambda: self._parcourir(q.get("types")),
                            icone=ic(0xE8B7), aide="Choisir le fichier dans l'explorateur Windows")
                b.pack(side="left")
                self.dynamiques.append(b)
            defaut = str(q.get("defaut") or "")
            if genre == "secret":
                self._note("La saisie est masquée. Rien n'est enregistré sur le disque.")
            elif defaut:
                self.saisie.insert(0, defaut)
                self.saisie.select_range(0, "end")
                self._note(f"Réponse proposée : {defaut}. Cliquez sur Valider pour la garder, ou tapez une "
                           "autre valeur.")
            elif q.get("vide_ok"):
                self._note("Vous pouvez laisser vide et cliquer sur Valider.")
            self.saisie.focus_set()
            self._focus_saisie(True)
        if self.dans_assistant:
            self.c_pied.pack(fill="x", pady=(12, 0))
        self.carte.pack(side="bottom", fill="x", pady=(12, 0), before=self.journal)
        self.racine.after(120, lambda: self.texte.see("end"))   # la zone a rétréci : on garde la fin visible
        if genre != "texte" and genre != "secret":
            self.racine.focus_set()
        self.etat.configure(text="À vous de répondre à la question en bas.")

    def _note(self, texte: str, couleur: str | None = None, base: bool = True):
        if base:
            self.note_base = texte
        if not texte:
            self.c_note.pack_forget()
            return
        self.c_note.configure(text=texte, fg=THEMES[self.theme][couleur or "discret"])
        self.c_note.pack(fill="x", pady=(6, 0))

    def _bordure_saisie(self, couleur: str | None):
        t = THEMES[self.theme]
        self.saisie.configure(highlightbackground=t[couleur] if couleur else t["bord_fort"],
                              highlightcolor=t[couleur] if couleur else t["accent"])

    def _verifier_saisie(self) -> str | None:
        """Vérifie la réponse pendant la frappe (format d'une adresse IP, d'un e-mail…). Renvoie l'erreur."""
        q = self.question or {}
        regle = q.get("valider")
        texte = self.saisie.get().strip()
        if not callable(regle) or self.masque or not texte or texte.startswith(("?", "<")):
            self._bordure_saisie(None)
            self._note(getattr(self, "note_base", ""), base=False)
            return None
        try:
            erreur = regle(texte)
        except Exception:  # une règle qui plante ne doit jamais empêcher de répondre
            erreur = None
        if erreur:
            self._bordure_saisie("rouge")
            self._note(f"✗  {erreur}", "rouge", base=False)
        else:
            self._bordure_saisie("vert")
            self._note("✓  Réponse correcte : cliquez sur Valider.", "vert", base=False)
        return erreur

    def _valider_saisie(self):
        if self._verifier_saisie():
            self.saisie.focus_set()
            self.racine.bell()
            return
        self.envoyer(self.saisie.get())

    def _entree_globale(self, e):
        """Touche Entrée hors de la zone de saisie : réponse proposée (Oui / Non, choix, Continuer)."""
        if e.widget is self.saisie or not self.question:
            return
        if self.question.get("genre") in ("oui_non", "choix", "continuer"):
            self.envoyer("")

    def envoyer(self, valeur: str, affichage: str | None = None):
        if str(self.saisie.cget("state")) == "disabled":
            return
        q = self.question or {}
        if affichage is None:
            if self.masque:
                affichage = "•" * min(len(valeur), 12)
            elif valeur == "" and q.get("genre") == "oui_non":
                affichage = "Oui" if q.get("defaut") else "Non"
            elif valeur == "" and q.get("genre") == "choix" and q.get("options"):
                affichage = q["options"][int(q.get("defaut") or 1) - 1]
            elif valeur == "" and q.get("defaut"):
                affichage = str(q["defaut"])
            else:
                affichage = valeur
        self.ecrire(f"→ {affichage}\n", ("reponse",))
        self.saisie.delete(0, "end")
        self.saisie.configure(state="disabled")
        for b in self.boutons_reponse:
            b.configure(state="disabled")
        self.question = None
        self._vider_question()
        self.carte.pack_forget()
        self.etat.configure(text="Le programme travaille, patientez…")
        self.reponses.put(valeur)

    # ------------------------------------------------------------------ actions
    def lancer_cle(self, cle: str):
        if cle in self.actions:
            _n, libelle, action = self.actions[cle]
            self.lancer(action, libelle, cle)

    def lancer(self, action, libelle, cle: str = ""):
        if self.en_cours:
            return
        self.en_cours = True
        self.dans_assistant = False
        self.section = ""
        self.etape_en_cours = None
        self.progression.pack_forget()
        self.resultats.pack_forget()
        for b in self.boutons:
            b.actif = bool(cle) and getattr(b, "cle", "") == cle
            b.configure(state="disabled")
        self.bouton_accueil.configure(state="disabled")
        court = COURTS.get(cle, libelle)
        self.montrer_journal()
        self.fil.configure(text="ACTION EN COURS")
        self.titre.configure(text=court)
        self.sous_titre.configure(text=libelle)
        self.etat.configure(text=f"En cours : {court}")
        self.ecrire(f"\n{libelle.upper()}\n", ("titre",))

        threading.Thread(target=_travail, args=(action, self.sorties, self.reponses), daemon=True).start()

    def fin_action(self):
        self.en_cours = False
        self.question = None
        self._vider_question()
        self.carte.pack_forget()
        self.saisie.configure(state="disabled")
        for b in self.boutons:
            b.actif = False
            b.configure(state="normal")
        self.bouton_accueil.configure(state="normal")
        self.fil.configure(text="TERMINÉ")
        self.sous_titre.configure(text="Le déroulement est ci-dessous. Choisissez une autre action à gauche, "
                                       "ou revenez à l'accueil.")
        self.etat.configure(text="Terminé. Choisissez une autre action à gauche.")
        if self.redemarrage_en_attente:
            self.redemarrer_apres_maj()

    def redemarrer_apres_maj(self):
        """La nouvelle version est prête : on ferme (le script d'installation la relance), sans couper une action."""
        if self.en_cours:
            self.redemarrage_en_attente = True
            self.etat.configure(text="Mise à jour prête : le programme redémarrera à la fin de l'action en cours.")
            return
        self.ecrire("\x1b[32mRedémarrage sur la nouvelle version...\x1b[0m\n")
        self.racine.after(1500, self._fermer_pour_maj)

    def _fermer_pour_maj(self):
        self.reponses.put(None)
        self.racine.destroy()
        os._exit(0)

    def quitter(self):
        from tkinter import messagebox
        if self.en_cours and not messagebox.askyesno("Quitter", "Une action est en cours. Quitter quand même ?"):
            return
        self.partage["fin"] = True
        self.reponses.put(None)
        self.racine.destroy()

    def demarrer(self):
        self.racine.mainloop()


def main() -> int:
    from .poste import appliquer_dossier_partage
    appliquer_dossier_partage(lambda t: None)
    Application().demarrer()
    return 0


if __name__ == "__main__":
    sys.exit(main())
