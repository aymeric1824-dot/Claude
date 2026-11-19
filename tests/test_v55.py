"""Version 5.5 : réseau détecté, mode express, questionnaire, profil, garde-fous, schéma, suivi des clients."""
import json
import time
import zipfile

import pytest

from sophos_auto import assistant
from sophos_auto.classeur import ecrire_classeur


def _client_dangereux(tmp_path):
    f = tmp_path / "clients" / "dupont.xlsx"
    f.parent.mkdir(parents=True, exist_ok=True)
    ecrire_classeur(str(f), {"Nom du client": "Dupont", "Nom d'hôte du pare-feu": "fw-dupont"}, {
        "Interfaces": [{"Port": "Port2", "Zone": "WAN", "Mode": "DHCP", "Description": "Internet"},
                       {"Port": "Port1", "Zone": "LAN", "Mode": "Statique", "Adresse IP": "192.168.10.254",
                        "Masque": "255.255.255.0", "Description": "Réseau local"}],
        "Hôtes": [{"Nom": "NAS-01", "Type": "IP", "Adresse": "192.168.10.20", "Description": "NAS"}],
        "Redirections": [{"Nom": "Bureau à distance", "Port WAN": "Port2", "Service externe": "RDP",
                          "Serveur interne": "NAS-01", "Port interne": "3389"}],
        "Comptes": [{"Identifiant": "admin-presta", "Mot de passe": "azerty", "Profil admin": "Administrator"}],
        "Wi-Fi": [{"Nom": "WIFI", "SSID": "Dupont", "Clé Wi-Fi": "court", "Zone": "LAN"}],
    })
    return f


# ----------------------------------------------------------------------------- réseau
def test_type_d_appareil_et_propositions():
    from sophos_auto import reseau
    assert reseau.type_appareil({389, 88, 445})[0] == "AD"
    assert reseau.type_appareil({9100, 80})[0] == "IMP"
    assert reseau.type_appareil({4444, 443})[0] == "FW"
    an = reseau.Analyse(carte=reseau.CartePC("Ethernet", 3, "192.168.1.20", 24, passerelle="192.168.1.1",
                                             serveur_dhcp="192.168.1.10", domaine="dupont.local"),
                        passerelle="192.168.1.1", equipement="Pare-feu Fortinet", genre_equipement="routeur",
                        appareils=[reseau.Appareil("192.168.1.10", [389, 88], "AD", "AD"),
                                   reseau.Appareil("192.168.1.30", [9100], "IMP", "Imprimante")])
    faits = assistant._propositions_reseau(an)
    assert faits
    p = assistant.PREREMPLI
    assert p["Quelle situation ressemble le plus à celle du client ?"][0] == "remplacement"
    assert p["IP que doit prendre le pare-feu sur le LAN, avec le masque"][0] == "192.168.1.1/24"
    assert p["IP du contrôleur de domaine"][0] == "192.168.1.10" and p["Nom du domaine"][0] == "dupont.local"
    assert p["Qui doit distribuer les adresses sur le réseau local ?"][0] == "srv"


def test_remettre_pc_sans_reglage(tmp_path):
    from sophos_auto import reseau
    assert reseau.reglage_pc_en_attente(tmp_path) is False
    assert reseau.remettre_pc(tmp_path) is False     # rien n'a été changé : rien à remettre


# ----------------------------------------------------------------------------- assistant
def test_reponse_proposee_et_son_origine(monkeypatch):
    recues = []
    monkeypatch.setattr(assistant, "INTERFACE", recues.append)
    monkeypatch.setattr("builtins.input", lambda invite="": "")
    assistant.PREREMPLI["Wi-Fi ?"] = (False, "questionnaire rempli par Dupont")
    assistant.PREREMPLI["Mode ?"] = ("b", "profil de votre société")
    assert assistant.oui_non("Wi-Fi ?", True) is False
    assert assistant.choix("Mode ?", [("a", "A"), ("b", "B")], 1) == "b"
    assert recues[0]["origine"] == "questionnaire rempli par Dupont" and recues[1]["defaut"] == 2
    assert assistant.REPONSES == {"Wi-Fi ?": False, "Mode ?": "b"}


def test_mode_express(monkeypatch):
    posees = []
    monkeypatch.setattr("builtins.input", lambda invite="": posees.append(invite) or "")
    assistant.EXPRESS = True
    assert assistant.oui_non("Activer la prévention d'intrusion (IPS) ?", True) is True     # réglage conseillé
    assert assistant.texte("Port du XGS relié à la box", "Port2") == "Port2"
    assert not posees                                                                      # rien n'est demandé
    monkeypatch.setattr("builtins.input", lambda invite="": posees.append(invite) or "Boulangerie")
    assert assistant.texte("Nom du client") == "Boulangerie"                              # indispensable
    assert len(posees) == 1


def test_statistiques(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from sophos_auto import statistiques
    for ev in ("posee", "posee", "aide", "erreur"):
        statistiques.noter("Masque ?", ev)
    statistiques.noter("Facile ?", "posee")
    d = statistiques.difficultes()
    assert d[0][0] == "Masque ?" and d[0][1]["erreur"] == 1 and len(d) == 1


# ----------------------------------------------------------------------------- questionnaire et profil
def test_questionnaire_aller_retour(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from sophos_auto import questionnaire
    page = questionnaire.generer(societe="Ma Société")
    contenu = page.read_text(encoding="utf-8")
    assert "Enregistrer mes réponses" in contenu and "Ma Société" in contenu
    renvoi = tmp_path / "reponses_Dupont.json"
    renvoi.write_text(json.dumps({"version": 1, "client": "Dupont", "notes": "Fibre Orange",
                                  "reponses": {"Nom du client": "Dupont", "Créer un Wi-Fi invités (isolé, Internet "
                                               "uniquement) ?": True, "Question inconnue": "x"}}), encoding="utf-8")
    nom, cible = questionnaire.importer(renvoi)
    assert nom == "Dupont" and cible.exists() and questionnaire.disponibles()[0][0] == "Dupont"
    reps, notes = questionnaire.reponses(cible)
    assert reps == {"Nom du client": "Dupont", "Créer un Wi-Fi invités (isolé, Internet uniquement) ?": True}
    assert notes == "Fibre Orange"
    with pytest.raises(ValueError):
        (tmp_path / "x.json").write_text("{}", encoding="utf-8")
        questionnaire.importer(tmp_path / "x.json")


def test_profil_ne_garde_que_les_choix_habituels(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from sophos_auto import questionnaire
    questionnaire.enregistrer_profil({
        "Nom du client": "Dupont", "IP du contrôleur de domaine": "192.168.1.10", "Adresse MAC": "00:11:22:33:44:55",
        "Activer le filtrage web (bloquer les sites dangereux, adultes, piratage...) ?": True,
        "Quel fuseau horaire ?": "Europe/Paris", "Mot de passe principal du coffre": "secret"})
    assert questionnaire.lire_profil() == {
        "Activer le filtrage web (bloquer les sites dangereux, adultes, piratage...) ?": True,
        "Quel fuseau horaire ?": "Europe/Paris"}


# ----------------------------------------------------------------------------- envoi sûr
def test_garde_fous(tmp_path):
    from sophos_auto.garde_fous import DANGER, verifier
    constats = verifier(_client_dangereux(tmp_path))
    textes = " ".join(c.texte for c in constats)
    assert "bureau à distance (RDP) est ouvert à tout Internet" in textes
    assert "admin-presta" in textes and "clé trop courte" in textes
    assert sum(c.niveau == DANGER for c in constats) == 2


def test_schema_du_reseau(tmp_path):
    from sophos_auto.schema_reseau import branchements, donnees, generer
    f = _client_dangereux(tmp_path)
    d = donnees(f)
    assert any("Port2" in b and "box" in b for b in branchements(d))
    page = generer(f).read_text(encoding="utf-8")
    assert "<svg" in page and "NAS-01 — 192.168.10.20" in page and "fw-dupont" in page


def test_erreurs_expliquees():
    from sophos_auto.erreurs import expliquer
    assert "existe déjà" in expliquer("502", "Entity having same name already exists")[0]
    assert "licence" in expliquer("", "Feature not licensed")[0]
    assert "API n'est pas activée" in expliquer("532", "")[0]
    assert "Demander de l'aide" in expliquer("999", "???")[1]


# ----------------------------------------------------------------------------- suivi
def test_tableau_de_bord_et_rapport_mensuel(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from sophos_auto import historique, planification, tableau
    historique.enregistrer("Dupont", "application", "3 réussie(s), 1 échec(s)", echecs=1)
    historique.enregistrer("Martin", "audit", "ok", note=92)
    lignes = tableau.lignes()
    assert [l.client for l in lignes] == ["Dupont", "Martin"] and lignes[0].etat == "rouge"
    assert lignes[1].note == 92
    assert "Dupont" in tableau.page().read_text(encoding="utf-8")
    f = planification.rapport_mensuel()
    assert f.exists() and "Dupont" in f.with_suffix(".txt").read_text(encoding="utf-8")
    assert "--rapport-mensuel" in planification.commande(tmp_path)


def test_dossier_d_assistance_sans_mot_de_passe(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _client_dangereux(tmp_path)
    from sophos_auto import historique
    from sophos_auto.assistance import creer
    historique.enregistrer("dupont", "creation", "ok")
    z = creer("Le VPN ne marche pas", "dupont", "déroulement…", {"ip": "172.16.16.16"})
    with zipfile.ZipFile(z) as archive:
        noms = archive.namelist()
        assert "LISEZ-MOI.txt" in noms and "client/dupont.xlsx" in noms
        assert "Le VPN ne marche pas" in archive.read("LISEZ-MOI.txt").decode("utf-8")
        (tmp_path / "x.xlsx").write_bytes(archive.read("client/dupont.xlsx"))
    from openpyxl import load_workbook
    valeurs = [str(c.value) for ws in load_workbook(tmp_path / "x.xlsx") for r in ws.iter_rows() for c in r]
    assert "azerty" not in valeurs and "(retiré)" in valeurs


def test_compte_rendu_signe(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from sophos_auto import historique
    from sophos_auto.compte_rendu import generer, lire_traits
    historique.enregistrer("Dupont", "application", "12 réussie(s), 0 échec(s)")
    f = generer("Dupont", "M. Dupont", lire_traits("[[[10, 10], [60, 40], [90, 20]]]"), "RAS")
    page = f.read_text(encoding="utf-8")
    assert "<polyline" in page and "M. Dupont" in page and "Configuration appliquée" in page
    assert historique.lire("Dupont")[-1]["action"] == "compte_rendu"
    assert lire_traits("pas du json") == []


# ----------------------------------------------------------------------------- fenêtre
def test_fenetre_signature_et_fichier(tmp_path, monkeypatch):
    tk = pytest.importorskip("tkinter")
    monkeypatch.chdir(tmp_path)
    try:
        from sophos_auto.fenetre import Application
        app = Application()
    except tk.TclError:
        pytest.skip("pas d'affichage graphique")
    resultat = {}
    try:
        def action():
            resultat["signature"] = assistant.signature()
            resultat["fichier"] = assistant.choisir_fichier("Fichier de réponses", [("JSON", "*.json")])

        def pomper(condition, delai=10):
            fin = time.time() + delai
            while time.time() < fin:
                app.racine.update()
                if condition():
                    return True
                time.sleep(0.02)
            return False
        app.lancer(action, "Essai")
        assert pomper(lambda: app.question and app.question.get("genre") == "signature")
        app.envoyer(json.dumps([[[1, 2], [3, 4]]]), "(signature)")
        assert pomper(lambda: app.question and app.question.get("genre") == "fichier")
        assert any(b.cget("text").endswith("Parcourir…") for b in app.dynamiques)
        f = tmp_path / "r.json"
        f.write_text("{}", encoding="utf-8")
        app.saisie.insert(0, str(f))
        app._valider_saisie()
        assert pomper(lambda: not app.en_cours)
        assert json.loads(resultat["signature"]) == [[[1, 2], [3, 4]]] and resultat["fichier"] == str(f)
        assert app._mots_techniques("Le DHCP et le VLAN du LAN")[0][0] in ("DHCP", "VLAN", "LAN")
    finally:
        app.partage["fin"] = True
        time.sleep(0.2)
        app.racine.destroy()
        import gc
        gc.collect()
