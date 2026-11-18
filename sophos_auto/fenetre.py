"""Fenêtre Windows de l'outil (boutons à gauche, échanges à droite).

Toutes les fonctions du menu restent les mêmes : la fenêtre affiche les questions et
vous répondez dans la zone du bas, ou avec les boutons Oui / Non / Valeur proposée.
"""
from __future__ import annotations

import builtins
import getpass
import queue
import re
import sys
import threading

ANSI = re.compile(r"\x1b\[([0-9;]*)m")
COULEURS = {"31": "rouge", "32": "vert", "33": "jaune", "36": "cyan", "90": "gris", "1": "gras"}


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
    try:
        from .mise_a_jour import verifier
        nouvelle = verifier()
        if nouvelle:
            sorties.put(("texte", f"\x1b[33mNouvelle version {nouvelle['version']} disponible : bouton "
                                  f"« Mise à jour du programme ».\x1b[0m\n"))
    except Exception:
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
        self.texte = scrolledtext.ScrolledText(droite, wrap="word", font=("Consolas", 10), bg="#fbfbfb",
                                               state="disabled")
        self.texte.pack(fill="both", expand=True)
        for nom, opts in {"rouge": {"foreground": "#c0392b"}, "vert": {"foreground": "#1e8449"},
                          "jaune": {"foreground": "#b9770e"}, "cyan": {"foreground": "#1f618d"},
                          "gris": {"foreground": "#7f8c8d"}, "gras": {"font": ("Consolas", 10, "bold")}}.items():
            self.texte.tag_configure(nom, **opts)

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
        self.etat = tk.Label(droite, text="Choisissez une action à gauche.", anchor="w", fg="#555")
        self.etat.pack(fill="x")

        self.ecrire(f"Bienvenue. Choisissez une action dans la colonne de gauche.\n"
                    f"Astuce : tapez ?? suivi d'un mot (ex. ?? vlan) pour le glossaire.\n\n")
        self.racine.protocol("WM_DELETE_WINDOW", self.quitter)
        self.racine.after(50, self.relever)
        # Les tâches de fond ne gardent jamais de référence à la fenêtre (Tk ne doit être libéré que par le fil principal)
        threading.Thread(target=_verifier_mise_a_jour, args=(self.sorties,), daemon=True).start()

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

    def quitter(self):
        from tkinter import messagebox
        if self.en_cours and not messagebox.askyesno("Quitter", "Une action est en cours. Quitter quand même ?"):
            return
        self.reponses.put(None)
        self.racine.destroy()

    def demarrer(self):
        self.racine.mainloop()


def main() -> int:
    Application().demarrer()
    return 0


if __name__ == "__main__":
    sys.exit(main())
