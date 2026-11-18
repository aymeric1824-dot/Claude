"""Confort : historique, rappels, réglages du poste, dossier partagé."""
import datetime as dt
import os

from sophos_auto import historique, poste
from sophos_auto.rappels import calculer


def test_reglages_du_poste(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert poste.charger()["theme"] == "clair"
    poste.enregistrer({"technicien": "Aymeric", "theme": "sombre", "inconnu": 1})
    assert poste.charger()["technicien"] == "Aymeric" and "inconnu" not in poste.charger()


def test_dossier_partage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    partage = tmp_path / "partage"
    poste.enregistrer({"dossier_partage": str(partage)})
    assert poste.appliquer_dossier_partage() == partage and os.getcwd() == str(partage)
    # le fichier du poste reste à côté du programme, pas dans le dossier partagé
    assert poste.fichier() == tmp_path / "parametres_poste.json"
    assert poste.charger()["dossier_partage"] == str(partage)


def test_dossier_partage_inaccessible(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bloque = tmp_path / "fichier"
    bloque.write_text("pas un dossier")
    poste.enregistrer({"dossier_partage": str(bloque / "sous")})
    messages = []
    assert poste.appliquer_dossier_partage(messages.append) == tmp_path
    assert "inaccessible" in messages[0]


def test_historique(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    poste.enregistrer({"technicien": "Léa"})
    historique.enregistrer("Dupont Industrie", "application", "10 réussie(s), 0 échec(s)", echecs=0)
    historique.enregistrer("Dupont Industrie", "audit", "note 92/100", note=92)
    historique.enregistrer("Boulangerie Martin", "creation", "")
    entrees = historique.lire("Dupont Industrie")
    assert [e["action"] for e in entrees] == ["application", "audit"] and entrees[0]["technicien"] == "Léa"
    assert historique.clients() == ["Boulangerie Martin", "Dupont Industrie"]
    assert "Léa — Contrôle de sécurité : note 92/100" in historique.resume(entrees[1])


def test_rappels(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    historique.enregistrer("A", "application", "", echecs=0)                     # jamais contrôlé
    historique.enregistrer("B", "audit", "", note=35)                             # note faible
    historique.enregistrer("C", "conformite", "", ecarts=2)                       # écarts non corrigés
    historique.enregistrer("D", "sauvegarde_central", "", firmware="SFOS 21.0", firmware_ancien=True)
    historique.enregistrer("E", "application", "", echecs=3)
    dans_4_mois = dt.datetime.now() + dt.timedelta(days=120)
    textes = {r.client: r.texte for r in calculer(dans_4_mois)}
    assert "aucun contrôle" in textes["A"]
    assert "jours" in textes["B"] or "note de sécurité faible" in textes["B"]
    assert any("faible" in r.texte for r in calculer() if r.client == "B")
    assert "écart" in textes["C"]
    assert any("firmware" in r.texte for r in calculer() if r.client == "D")
    assert any("échec" in r.texte for r in calculer() if r.client == "E")
    assert calculer()[0].urgence == 1     # les plus importants en premier


def test_application_et_audit_enregistres(tmp_path, monkeypatch):
    from sophos_auto import api as api_mod
    from sophos_auto.creer_modele import creer
    from sophos_auto.deployer import deployer
    from tests.faux_xgs import FauxXGS
    from tests.test_deploiement import _sans_secrets
    monkeypatch.chdir(tmp_path)
    f = FauxXGS()
    monkeypatch.setattr(api_mod.requests, "post", f.post)
    monkeypatch.setenv("SOPHOS_MOT_DE_PASSE", "secret")
    chemin = creer(str(tmp_path / "c.xlsx"))
    _sans_secrets(chemin)
    assert deployer(chemin) == 0
    actions = [e["action"] for e in historique.lire("Exemple SARL")]
    assert actions == ["audit", "application"]
    app = historique.lire("Exemple SARL")[-1]
    assert app["echecs"] == 0 and app["rapport"].endswith(".html") and app["etat_avant"].endswith("_avant.json")
