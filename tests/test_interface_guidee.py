"""Fenêtre guidée : questions décrites, vérification pendant la saisie, connexion, mots de passe, PDF."""
import time

import pytest

from sophos_auto import assistant
from sophos_auto.diagnostic import meme_reseau, port_ouvert
from sophos_auto.fenetre import deviner_question


def test_question_devinee_depuis_le_texte():
    assert deviner_question("Continuer quand même ? (o/N) ", False) == {
        "genre": "oui_non", "question": "Continuer quand même ?", "defaut": False}
    assert deviner_question("Appuyez sur Entrée quand c'est fait... ", False)["genre"] == "continuer"
    assert deviner_question("Mot de passe de « admin » : ", True)["genre"] == "secret"
    assert deviner_question("\x1b[1m? Nom\x1b[0m : ", False)["question"] == "Nom"


def test_questions_annoncees_a_la_fenetre(monkeypatch):
    recues = []
    monkeypatch.setattr(assistant, "INTERFACE", recues.append)
    monkeypatch.setattr("builtins.input", lambda invite="": "")
    assert assistant.oui_non("Wi-Fi ?", True, "aide") is True
    assert assistant.choix("Situation ?", [("a", "Bureau"), ("b", "PME")], 2) == "b"
    assert assistant.texte("IP", "192.168.1.254", valider=assistant._v_ip) == "192.168.1.254"
    genres = [q["genre"] for q in recues]
    assert genres == ["oui_non", "choix", "texte"]
    assert recues[1]["options"] == ["Bureau", "PME"] and recues[1]["defaut"] == 2
    assert recues[2]["valider"]("300.1.1.1") and recues[2]["valider"]("10.0.0.1") is None


def test_outils_de_connexion():
    assert meme_reseau("172.16.16.20", "172.16.16.16")
    assert not meme_reseau("192.168.1.20", "172.16.16.16")
    assert not meme_reseau("", "172.16.16.16")
    assert port_ouvert("adresse invalide", 4444, 0.2) is False


def test_pdf_sans_navigateur(monkeypatch, tmp_path):
    from sophos_auto import pdf
    page = tmp_path / "page.html"
    page.write_text("<p>bonjour</p>", encoding="utf-8")
    monkeypatch.setattr(pdf, "navigateur", lambda: None)
    assert pdf.en_pdf(page) is None                    # pas de navigateur : la page HTML suffit


def _fenetre(tmp_path, monkeypatch):
    tk = pytest.importorskip("tkinter")
    monkeypatch.chdir(tmp_path)
    try:
        from sophos_auto.fenetre import Application
        return Application()
    except tk.TclError:
        pytest.skip("pas d'affichage graphique")


def _fermer(app):
    app.partage["fin"] = True
    time.sleep(0.2)
    app.racine.destroy()
    import gc
    gc.collect()


def test_fenetre_verifie_la_reponse_et_affiche_les_fichiers(tmp_path, monkeypatch):
    app = _fenetre(tmp_path, monkeypatch)
    try:
        def action():
            print("ip :", assistant.texte("Adresse IP du pare-feu", "172.16.16.16", valider=assistant._v_ip))
            f = tmp_path / "dossier.html"
            f.write_text("x", encoding="utf-8")
            assistant.annoncer_fichiers([("Dossier technique", str(f))])
            assistant._annoncer(genre="mots_de_passe", client="Dupont", liste=[("Mot de passe admin", "Ab1-xyz")],
                                coffre=True)

        def pomper(condition, delai=10):
            fin = time.time() + delai
            while time.time() < fin:
                app.racine.update()
                if condition():
                    return True
                time.sleep(0.02)
            return False
        app.lancer(action, "Essai")
        assert pomper(lambda: str(app.saisie.cget("state")) == "normal")
        assert app.saisie.get() == "172.16.16.16"            # réponse proposée déjà remplie
        app.saisie.delete(0, "end")
        app.saisie.insert(0, "999.1.1.1")
        app._valider_saisie()                                 # refusée tout de suite, rien n'est envoyé
        assert str(app.saisie.cget("state")) == "normal" and "✗" in app.c_note.cget("text")
        app.saisie.delete(0, "end")
        app.saisie.insert(0, "10.0.0.1")
        app._valider_saisie()
        assert pomper(lambda: not app.en_cours)
        assert "ip : 10.0.0.1" in app.texte.get("1.0", "end")
        assert app.resultats.winfo_ismapped()               # bouton pour ouvrir le fichier créé
        assert len(app.fenetres) == 1                        # fenêtre des mots de passe
        app.afficher_connexion({"ip": app.partage["ip"], "ip_pc": "172.16.16.20", "joignable": True,
                                "meme_reseau": True})
        assert app.cx_etat.cget("text") == "Pare-feu joignable" and app.cx_pc.cget("text") == "172.16.16.20"
    finally:
        _fermer(app)
