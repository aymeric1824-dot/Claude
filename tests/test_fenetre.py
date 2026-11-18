"""Fenêtre Windows : découpage des couleurs (partout) et essai réel de la fenêtre (si tkinter est disponible)."""
import time

import pytest

from sophos_auto.fenetre import decouper_ansi


def test_decoupage_des_couleurs():
    assert decouper_ansi("a\x1b[31mb\x1b[1mc\x1b[0md") == [("a", ()), ("b", ("rouge",)), ("c", ("rouge", "gras")),
                                                          ("d", ())]


def test_fenetre_lance_une_action_et_repond(tmp_path, monkeypatch):
    tk = pytest.importorskip("tkinter")
    monkeypatch.chdir(tmp_path)
    try:
        from sophos_auto.fenetre import Application
        app = Application()
    except tk.TclError:
        pytest.skip("pas d'affichage graphique")
    from sophos_auto.__main__ import action_glossaire
    app.lancer(action_glossaire, "Glossaire")

    def pomper(condition, delai=10):
        fin = time.time() + delai
        while time.time() < fin:
            app.racine.update()
            if condition():
                return True
            time.sleep(0.02)
        return False
    assert pomper(lambda: str(app.saisie.cget("state")) == "normal")     # la question est posée
    app.envoyer("dhcp")
    assert pomper(lambda: "adresse IP à chaque appareil" in app.texte.get("1.0", "end"))
    assert pomper(lambda: str(app.saisie.cget("state")) == "normal")
    app.envoyer("")                                                       # retour au menu
    assert pomper(lambda: not app.en_cours)
    time.sleep(0.2)                     # laisse finir le fil de l'action
    app.racine.destroy()
    del app
    import gc
    gc.collect()                        # libère Tk dans le fil principal
