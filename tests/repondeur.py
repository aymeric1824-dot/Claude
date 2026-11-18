"""Répond automatiquement aux questions de l'assistant (pour les tests)."""
import re


class Repondeur:
    """regles : liste de (motif regex, réponse). Chaque règle sert une seule fois, dans l'ordre ;
    une question sans règle reçoit "" (valeur proposée)."""

    def __init__(self, regles, journal=None):
        self.regles = list(regles)
        self.journal = journal if journal is not None else []

    def __call__(self, invite=""):
        texte = re.sub(r"\033\[[0-9;]*m", "", invite)
        for i, (motif, rep) in enumerate(self.regles):
            if re.search(motif, texte):
                del self.regles[i]
                self.journal.append((texte, rep))
                return rep
        self.journal.append((texte, ""))
        if len(self.journal) > 600:
            raise RuntimeError("boucle infinie dans l'assistant")
        return ""
