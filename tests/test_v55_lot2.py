"""Version 5.5, deuxième lot : reprise de l'existant, cohérence, répétition, avant/après, attente, santé."""
import json

import pytest
import requests

from sophos_auto import assistant
from sophos_auto.classeur import ecrire_classeur

FORTIGATE = '''
config system interface
    edit "wan1"
        set ip 203.0.113.10 255.255.255.248
    next
    edit "internal"
        set ip 192.168.1.99 255.255.255.0
    next
end
config firewall address
    edit "NAS-COMPTA"
        set subnet 192.168.1.20 255.255.255.255
        set comment "NAS de la compta"
    next
    edit "LAN-RESEAU"
        set subnet 192.168.1.0 255.255.255.0
    next
end
config firewall vip
    edit "Cameras"
        set extintf "wan1"
        set portforward enable
        set mappedip "192.168.1.30"
        set extport 8000
        set mappedport 80
    next
    edit "Serveur-complet"
        set mappedip "192.168.1.40"
    next
end
config system dhcp server
    edit 1
        config reserved-address
            edit 1
                set ip 192.168.1.50
                set mac 00:11:22:aa:bb:cc
                set description "Imprimante accueil"
            next
        end
    next
end
'''


def _client(tmp_path, **lignes):
    f = tmp_path / "clients" / "dupont.xlsx"
    f.parent.mkdir(parents=True, exist_ok=True)
    ecrire_classeur(str(f), {"Nom du client": "Dupont"}, lignes)
    return f


def test_reprise_fortinet(tmp_path):
    from sophos_auto.import_config import ajouter_au_classeur, lire_fortinet
    r = lire_fortinet(FORTIGATE)
    assert ("NAS-COMPTA", "192.168.1.20", "NAS de la compta") in r.hotes
    assert ("CAMERAS", "TCP 8000", "192.168.1.30", "80") in r.redirections
    assert ("IMPRIMANTE-ACCUEIL", "00:11:22:AA:BB:CC", "192.168.1.50") in r.reservations
    assert r.lan == "192.168.1.99/24" and any("Serveur-complet" in x for x in r.remarques)
    f = _client(tmp_path)
    fait = ajouter_au_classeur(f, r)
    assert any("NAS-COMPTA" in x for x in fait) and any("CAMERAS" in x for x in fait)
    assert ajouter_au_classeur(f, r) == [x for x in fait if x.startswith("Redirection")]   # pas de doublon d'équipement


def test_reprise_inventaire_csv(tmp_path):
    from sophos_auto.import_config import lire_inventaire
    inv = tmp_path / "glpi.csv"
    inv.write_text("Nom;Adresse IP;Adresse MAC;Type\nCopieur Accueil;192.168.1.60;00-11-22-33-44-55;Imprimante\n"
                   "Poste 1;pas une ip;;PC\n", encoding="utf-8")
    r = lire_inventaire(inv)
    assert r.hotes == [("COPIEUR-ACCUEIL", "192.168.1.60", "Imprimante")]
    assert r.reservations == [("COPIEUR-ACCUEIL", "00:11:22:33:44:55", "192.168.1.60")]
    (tmp_path / "x.csv").write_text("Nom;Rien\nA;B\n", encoding="utf-8")
    with pytest.raises(ValueError):
        lire_inventaire(tmp_path / "x.csv")


def test_coherence_du_fichier(tmp_path):
    from sophos_auto.garde_fous import DANGER, verifier
    f = _client(tmp_path, **{
        "Hôtes": [{"Nom": "IMP", "Type": "IP", "Adresse": "192.168.10.50"},
                  {"Nom": "IMP", "Type": "IP", "Adresse": "192.168.10.60"}],
        "DHCP": [{"Nom": "DHCP-LAN", "Interface": "Port1", "Début de plage": "192.168.10.20",
                  "Fin de plage": "192.168.10.200"}],
        "VLAN": [{"Interface physique": "Port1", "ID VLAN": "20", "Zone": "LAN", "Adresse IP": "192.168.20.254",
                  "Masque": "255.255.255.0"},
                 {"Interface physique": "Port1", "ID VLAN": "20", "Zone": "LAN", "Adresse IP": "192.168.20.253",
                  "Masque": "255.255.255.0"}]})
    textes = {c.texte: c.niveau for c in verifier(f)}
    assert any("« IMP » est utilisé 2 fois" in t for t in textes)
    assert any("adresse fixe dans la plage" in t for t in textes)
    assert any("VLAN 20 est déclaré 2 fois" in t and n == DANGER for t, n in textes.items())
    assert any("utilisent le même réseau" in t for t in textes)


def test_noms_et_plan_d_adressage():
    from sophos_auto import reseau
    assert assistant.nommer("fw-{client}", "Boulangerie Dupont") == "fw-boulangerie-dupont"
    assert assistant.nommer("{CLIENT}-INVITES", "Dupont") == "DUPONT-INVITES"

    class P:
        reseaux_internes = ["192.168.10.0/24"]
    assert assistant.reseau_libre(P()) == "192.168.20.254/24"
    assistant.ANALYSE = reseau.Analyse(carte=reseau.CartePC("Ethernet", 1, "192.168.20.5", 24))
    assert assistant.reseau_libre(P()) == "192.168.30.254/24"
    assert reseau.marque_appareil("<title>brother hl-l2350dw</title>") == ("Brother", "IMP")


def test_avant_apres():
    from sophos_auto.comparaison import comparer
    avant = {"IPHost": [{"Name": "NAS", "IPAddress": "1.1.1.1"}, {"Name": "VIEUX"}], "Zone": {"Name": "LAN"}}
    apres = {"IPHost": [{"Name": "NAS", "IPAddress": "1.1.1.2"}, {"Name": "NEUF"}], "Zone": {"Name": "LAN"}}
    ec = comparer(avant, apres)
    assert ec.ajoutes == ["Équipement / réseau « NEUF »"] and ec.supprimes == ["Équipement / réseau « VIEUX »"]
    assert ec.modifies == ["Équipement / réseau « NAS »"]


def test_repetition_sans_risque(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from sophos_auto import historique
    from sophos_auto.deployer import repeter
    f = _client(tmp_path, **{"Hôtes": [{"Nom": "NAS-01", "Type": "IP", "Adresse": "192.168.10.20"}]})
    vrai_post = requests.post
    code = repeter(str(f))
    assert code in (0, 2) and requests.post is vrai_post             # le vrai réseau n'a jamais été touché
    assert historique.lire() == []                                    # une répétition n'est pas une intervention
    assert list((tmp_path / "simulation").rglob("*_repetition.html"))
    assert not (tmp_path / "rapports").exists() or not list((tmp_path / "rapports").glob("*_avant.json"))


def test_clients_prets_a_envoyer(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from sophos_auto import attente
    f = _client(tmp_path)
    attente.ajouter("Dupont", str(f))
    attente.ajouter("Dupont", str(f))
    assert [x["client"] for x in attente.lister()] == ["Dupont"]
    attente.retirer(str(f.resolve()))
    assert attente.lister() == []


def test_controles_manuels_selon_le_fichier(tmp_path):
    from sophos_auto.verification import controles_manuels
    f = _client(tmp_path, **{"Wi-Fi": [{"Nom": "W", "SSID": "INV", "Isolation des clients": "Oui"}],
                             "Comptes": [{"Identifiant": "jdupont", "VPN télétravail": "Oui"}]})
    questions = [q for q, _ in controles_manuels(f)]
    assert any("Wi-Fi invités" in q for q in questions) and any("télétravailleur" in q for q in questions)


def test_sante_de_l_outil(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from sophos_auto.sante import verifier
    points = verifier(internet=False)
    assert points[0][0] is True and any("Composants" in p[1] for p in points)


def test_consigne_en_mode_texte(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda invite="": "?")
    assert assistant.consigne("Branchez", "Le câble") == "?"


def test_fenetre_mode_simple_et_recherche(tmp_path, monkeypatch):
    tk = pytest.importorskip("tkinter")
    monkeypatch.chdir(tmp_path)
    try:
        from sophos_auto.fenetre import ACTIONS_SIMPLES, Application
        app = Application()
    except tk.TclError:
        pytest.skip("pas d'affichage graphique")
    try:
        app.racine.update()
        app.changer_mode_simple()
        app.racine.update()
        visibles = {l.cle for _g, ls in app.groupes_lignes for l in ls if l.cadre.winfo_ismapped()}
        assert visibles and visibles <= set(ACTIONS_SIMPLES)
        app.changer_mode_simple()
        app.recherche.delete(0, "end")
        app.recherche.insert(0, "fortinet")
        app.filtrer_actions()
        app.racine.update()
        visibles = {l.cle for _g, ls in app.groupes_lignes for l in ls if l.cadre.winfo_ismapped()}
        assert visibles == {"reprise"}
        from sophos_auto.poste import charger
        assert charger()["mode_simple"] is False
    finally:
        app.partage["fin"] = True
        app.racine.destroy()
        import gc
        gc.collect()


def test_nouvelles_actions_du_menu_se_lancent(tmp_path, monkeypatch):
    """Chaque nouvelle action du menu s'exécute sans erreur (mode texte, réponses proposées)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("builtins.input", lambda invite="": "")
    from sophos_auto import __main__ as m
    from sophos_auto import historique
    historique.enregistrer("Dupont", "audit", "ok", note=40)
    for action in (m.action_tableau, m.action_statistiques, m.action_profil):
        action()
    monkeypatch.setattr("builtins.input", lambda invite="": "1")      # questionnaire : « Créer »
    m.action_questionnaire()
    assert (tmp_path / "clients" / "questionnaires" / "questionnaire_client.html").exists()
