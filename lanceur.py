"""Point d'entrée de SophosXGS.exe : la fenêtre, ou le mode texte avec --console."""
import sys


def principal() -> int:
    from sophos_auto.poste import appliquer_dossier_partage
    appliquer_dossier_partage(lambda t: None)
    if "--rapport-mensuel" in sys.argv:        # tâche planifiée : rapport sans fenêtre
        from sophos_auto.planification import rapport_mensuel
        rapport_mensuel()
        return 0
    if "--console" not in sys.argv:
        try:
            from sophos_auto.fenetre import main as fenetre
            return fenetre()
        except Exception:   # pas d'affichage graphique disponible : mode texte
            if sys.stdout is None:
                raise
    from sophos_auto.__main__ import main
    return main()


if __name__ == "__main__":
    sys.exit(principal())
