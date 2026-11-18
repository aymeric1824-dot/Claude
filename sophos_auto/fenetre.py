"""Fenêtre Windows de l'outil (boutons à gauche, échanges à droite).

Toutes les fonctions du menu restent les mêmes : la fenêtre affiche les questions et
vous répondez dans la zone du bas, ou avec les boutons Oui / Non / Valeur proposée.
"""
from __future__ import annotations

import builtins
import getpass
import os
import queue
import re
import sys
import threading

ANSI = re.compile(r"\x1b\[([0-9;]*)m")
COULEURS = {"31": "rouge", "32": "vert", "33": "jaune", "36": "cyan", "90": "gris", "1": "gras"}

# Thèmes de la fenêtre : fond et texte de la zone d'échange, couleurs des messages
THEMES = {
    "clair": {"fond": "#fbfbfb", "texte": "#222222", "saisie": "#ffffff", "cadre": "#f0f0f0", "etat": "#555555",
              "rouge": "#c0392b", "vert": "#1e8449", "jaune": "#b9770e", "cyan": "#1f618d", "gris": "#7f8c8d"},
    "sombre": {"fond": "#1e1f22", "texte": "#e3e3e3", "saisie": "#2b2d31", "cadre": "#26272b", "etat": "#b0b0b0",
               "rouge": "#ff6b6b", "vert": "#5fd068", "jaune": "#f0c040", "cyan": "#5dade2", "gris": "#9a9a9a"},
}


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
    sorties.put(("question", masque))
    rep = reponses.get()
    if rep is None:
        raise KeyboardInterrupt
    return rep


def _travail(action, sorties: queue.Queue, reponses: queue.Queue) -> None:
    """Exécute une action du menu dans un fil séparé ; ses questions passent par la fenêtre."""
    ancien_input, ancien_getpass, ancien_stdout = builtins.input, getpass.getpass, sys.stdout
    builtins.input = lambda invite="": _question(sorties, reponses, invite)
    getpass.getpass = lambda invite="Mot de passe : ", stream=None: _question(sorties, reponses, invite, masque=True)
    sys.stdout = _Sortie(sorties)
    try:
        action()
    except KeyboardInterrupt:
        print("\nAction annulée.")
    except SystemExit:
        pass
    except Exception as exc:  # une erreur ne doit jamais fermer la fenêtre
        print(f"\n\x1b[31mErreur inattendue : {exc}\x1b[0m")
    finally:
        builtins.input, getpass.getpass, sys.stdout = ancien_input, ancien_getpass, ancien_stdout
        sorties.put(("fin", None))


def _verifier_mise_a_jour(sorties: queue.Queue) -> None:
    """Au démarrage : cherche une nouvelle version sur GitHub et l'installe toute seule si c'est activé."""
    try:
        from .mise_a_jour import mise_a_jour_automatique
        if mise_a_jour_automatique(lambda t: sorties.put(("texte", f"\x1b[33m{t}\x1b[0m\n"))):
            sorties.put(("redemarrer", None))
    except Exception:  # une vérification ratée ne doit jamais gêner l'utilisation
        pass


class Application:
    def __init__(self):
        import tkinter as tk
        from tkinter import scrolledtext

        from . import __version__
        from .__main__ import MENU

        self.tk = tk
        self.racine = tk.Tk()
        self.racine.title(f"Sophos XGS — outil de configuration (v{__version__})")
        self.racine.geometry("1180x760")
        self.racine.minsize(900, 560)
        self.sorties: queue.Queue = queue.Queue()
        self.reponses: queue.Queue = queue.Queue()
        self.en_cours = False
        self.masque = False
        self.redemarrage_en_attente = False
        from .poste import charger as charger_poste
        reglages = charger_poste()
        self.theme = reglages["theme"] if reglages["theme"] in THEMES else "clair"
        self.taille = max(8, min(20, int(reglages["taille_texte"] or 10)))

        gauche = tk.Frame(self.racine, bg="#1f4e78", padx=8, pady=8)
        gauche.pack(side="left", fill="y")
        tk.Label(gauche, text="SOPHOS XGS", fg="white", bg="#1f4e78", font=("Segoe UI", 14, "bold")).pack(pady=(0, 8))
        self.boutons = []
        for _cle, libelle, action in MENU:
            if action is None:
                continue
            b = tk.Button(gauche, text=libelle, wraplength=240, justify="left", anchor="w", relief="flat",
                          bg="#2e6da4", fg="white", activebackground="#3c83c4", font=("Segoe UI", 9),
                          command=lambda a=action, l=libelle: self.lancer(a, l))
            b.pack(fill="x", pady=2, ipady=3)
            self.boutons.append(b)
        tk.Button(gauche, text="Quitter", command=self.quitter, bg="#7f8c8d", fg="white", relief="flat").pack(
            side="bottom", fill="x", pady=4)

        droite = tk.Frame(self.racine, padx=8, pady=8)
        droite.pack(side="left", fill="both", expand=True)
        self.droite = droite
        outils = tk.Frame(droite)
        outils.pack(fill="x", pady=(0, 6))
        self.outils = outils
        for libelle, commande in (("A−", lambda: self.changer_taille(-1)), ("A+", lambda: self.changer_taille(1)),
                                  ("☾ / ☀ Thème", self.changer_theme), ("📁 Clients", lambda: self.ouvrir("clients")),
                                  ("📁 Rapports", lambda: self.ouvrir("rapports")),
                                  ("🗑 Effacer l'écran", self.effacer)):
            tk.Button(outils, text=libelle, command=commande, relief="groove").pack(side="left", padx=2)
        self.texte = scrolledtext.ScrolledText(droite, wrap="word", font=("Consolas", self.taille), state="disabled")
        self.texte.pack(fill="both", expand=True)

        bas = tk.Frame(droite, pady=6)
        bas.pack(fill="x")
        self.saisie = tk.Entry(bas, font=("Segoe UI", 11), state="disabled")
        self.saisie.pack(side="left", fill="x", expand=True, ipady=4)
        self.saisie.bind("<Return>", lambda e: self.envoyer(self.saisie.get()))
        self.boutons_reponse = []
        for libelle, valeur in (("Valider", None), ("Oui", "o"), ("Non", "n"), ("Valeur proposée", ""),
                                ("Aide ?", "?"), ("↺ Refaire l'étape", "<")):
            b = tk.Button(bas, text=libelle, state="disabled",
                          command=lambda v=valeur: self.envoyer(self.saisie.get() if v is None else v))
            b.pack(side="left", padx=2)
            self.boutons_reponse.append(b)
        self.etat = tk.Label(droite, text="Choisissez une action à gauche.", anchor="w")
        self.etat.pack(fill="x")
        self.bas = bas
        self.appliquer_theme()
        self.racine.bind("<Control-plus>", lambda e: self.changer_taille(1))
        self.racine.bind("<Control-equal>", lambda e: self.changer_taille(1))
        self.racine.bind("<Control-minus>", lambda e: self.changer_taille(-1))

        self.ecrire("Bienvenue. Choisissez une action dans la colonne de gauche.\n"
                    "Astuces : ?? suivi d'un mot (ex. ?? vlan) pour le glossaire ; Ctrl + / Ctrl − pour la taille du texte.\n\n")
        self.afficher_rappels()
        self.racine.protocol("WM_DELETE_WINDOW", self.quitter)
        self.racine.after(50, self.relever)
        # Les tâches de fond ne gardent jamais de référence à la fenêtre (Tk ne doit être libéré que par le fil principal)
        threading.Thread(target=_verifier_mise_a_jour, args=(self.sorties,), daemon=True).start()

    # ------------------------------------------------------------------ confort
    def appliquer_theme(self):
        t = THEMES[self.theme]
        self.texte.configure(bg=t["fond"], fg=t["texte"], insertbackground=t["texte"],
                             font=("Consolas", self.taille))
        for nom in ("rouge", "vert", "jaune", "cyan", "gris"):
            self.texte.tag_configure(nom, foreground=t[nom])
        self.texte.tag_configure("gras", font=("Consolas", self.taille, "bold"))
        for cadre in (self.droite, self.outils, self.bas):
            cadre.configure(bg=t["cadre"])
        self.etat.configure(bg=t["cadre"], fg=t["etat"])
        self.saisie.configure(bg=t["saisie"], fg=t["texte"], insertbackground=t["texte"],
                              disabledbackground=t["cadre"], font=("Segoe UI", self.taille + 1))

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
        self.ecrire(f"\x1b[1mRappels ({len(rappels)}) :\x1b[0m\n")
        for r in rappels[:8]:
            couleur = "31" if r.urgence == 1 else "33"
            self.ecrire(f"  \x1b[{couleur}m•\x1b[0m {r.client} : {r.texte}\n")
        if len(rappels) > 8:
            self.ecrire(f"  … et {len(rappels) - 8} autre(s) : bouton « Rappels ».\n")
        self.ecrire("\n")

    # ------------------------------------------------------------------ affichage
    def ecrire(self, t: str):
        self.texte.configure(state="normal")
        for morceau, styles in decouper_ansi(t):
            self.texte.insert("end", morceau, styles)
        self.texte.configure(state="disabled")
        self.texte.see("end")

    def relever(self):
        try:
            while True:
                genre, val = self.sorties.get_nowait()
                if genre == "texte":
                    self.ecrire(val)
                elif genre == "question":
                    self.attendre_reponse(masque=val)
                elif genre == "fin":
                    self.fin_action()
                elif genre == "redemarrer":
                    self.redemarrer_apres_maj()
                elif genre == "etat":
                    self.etat.configure(text=val)
        except queue.Empty:
            pass
        self.racine.after(50, self.relever)

    def attendre_reponse(self, masque: bool):
        self.masque = masque
        self.saisie.configure(state="normal", show="•" if masque else "")
        self.saisie.delete(0, "end")
        self.saisie.focus_set()
        for b in self.boutons_reponse:
            b.configure(state="normal")

    def envoyer(self, valeur: str):
        if str(self.saisie.cget("state")) == "disabled":
            return
        self.ecrire(("•" * min(len(valeur), 12) if self.masque else valeur) + "\n")
        self.saisie.delete(0, "end")
        self.saisie.configure(state="disabled")
        for b in self.boutons_reponse:
            b.configure(state="disabled")
        self.reponses.put(valeur)

    # ------------------------------------------------------------------ actions
    def lancer(self, action, libelle):
        if self.en_cours:
            return
        self.en_cours = True
        for b in self.boutons:
            b.configure(state="disabled")
        self.etat.configure(text=f"En cours : {libelle}")
        self.ecrire(f"\n——— {libelle} ———\n")

        threading.Thread(target=_travail, args=(action, self.sorties, self.reponses), daemon=True).start()

    def fin_action(self):
        self.en_cours = False
        for b in self.boutons:
            b.configure(state="normal")
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
