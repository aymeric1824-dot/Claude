"""Tests des améliorations v4 : contrôles, modes d'application, rapports, audit, Central, assistant."""
import builtins
import getpass
import json
from pathlib import Path

import pytest
from openpyxl import load_workbook

from sophos_auto import api as api_mod
from sophos_auto.api import SophosAPI, masquer
from sophos_auto.audit import auditer, note
from sophos_auto.central import SophosCentral, firmware_compatible
from sophos_auto.creer_modele import creer
from sophos_auto.deployer import deployer, resume_operations
from sophos_auto.documentation import generer
from sophos_auto.modele import lire_classeur
from tests.faux_xgs import FauxXGS
from tests.test_audit_central import FauxCentral
from tests.test_deploiement import _sans_secrets


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    f = FauxXGS()
    monkeypatch.setattr(api_mod.requests, "post", f.post)
    monkeypatch.setenv("SOPHOS_MOT_DE_PASSE", "secret")
    chemin = creer(str(tmp_path / "client.xlsx"))
    _sans_secrets(chemin)
    return f, chemin


def _ecrire(chemin, onglet, ligne, valeurs):
    wb = load_workbook(chemin)
    for col, v in enumerate(valeurs, start=1):
        wb[onglet].cell(ligne, col, v)
    wb.save(chemin)


# ----------------------------------------------------------------------------- contrôles du fichier
def test_chevauchement_de_reseaux(env):
    _, chemin = env
    _ecrire(chemin, "VLAN", 3, ["Oui", "Port1", 20, "LAN", "192.168.10.1", "/25"])   # chevauche le VLAN 10
    erreurs = lire_classeur(chemin).erreurs
    assert any("se chevauchent" in e for e in erreurs), erreurs


def test_vpn_distant_identique_au_lan(env):
    _, chemin = env
    _ecrire(chemin, "VPN sites", 2, ["Oui", "VPN-X", "Port2", "198.51.100.7", "192.168.10.0/24", "192.168.10.0/24",
                                     "Cle-123456789", "IKEv2", "Initier"])
    assert any("chevauche le réseau local" in e for e in lire_classeur(chemin).erreurs)


def test_dhcp_hors_reseau_et_ip_du_pare_feu(env):
    _, chemin = env
    _ecrire(chemin, "DHCP", 3, ["Oui", "DHCP-VLAN10", "Port1.10", "192.168.10.200", "192.168.10.254", "/24", "", "", "",
                                "", 1440])
    _ecrire(chemin, "DHCP", 4, ["Oui", "DHCP-VLAN10B", "Port1.10", "192.168.99.1", "192.168.99.9", "/24", "", "", "",
                                "", 1440])
    erreurs = lire_classeur(chemin).erreurs
    assert any("contient l'adresse du pare-feu" in e for e in erreurs)
    assert any("sort du réseau" in e for e in erreurs)


def test_reservation_en_double(env):
    _, chemin = env
    _ecrire(chemin, "Réservations DHCP", 3, ["Oui", "DHCP-LAN", "AUTRE", "00:11:22:33:44:55", "172.16.16.51"])
    assert any("réservée deux fois" in e for e in lire_classeur(chemin).erreurs)


def test_objet_reutilise_et_redirection_dangereuse(env):
    _, chemin = env
    _ecrire(chemin, "Redirections", 2, ["Oui", "RDP", "Port2", "TCP 3389", "192.168.10.10", "", "LAN", ""])
    cfg = lire_classeur(chemin)
    nat = next(o for o in cfg.operations if o.balise == "NATRule")
    assert nat.contenu["TranslatedDestination"] == "SRV-AD-01"         # objet existant réutilisé
    assert not any(o.nom == "IP_192.168.10.10" for o in cfg.operations)
    assert any("SÉCURITÉ" in a and "bureau à distance" in a for a in cfg.avertissements)


# ----------------------------------------------------------------------------- application
def test_mode_prudent_ne_modifie_rien(env):
    faux, chemin = env
    faux._mettre("IPHost", {"Name": "SRV-AD-01", "IPFamily": "IPv4", "HostType": "IP", "IPAddress": "10.9.9.9"})
    assert deployer(chemin, sans_modifier=True) == 0
    assert faux.obtenir("IPHost", "SRV-AD-01")["IPAddress"] == "10.9.9.9"   # existant conservé
    assert faux.obtenir("IPHost", "RES-LAN")                                # nouveau créé
    assert "HostnameSettings" not in (faux.obtenir("AdminSettings", "") or {})  # réglage non touché


def test_seulement_certains_onglets(env):
    faux, chemin = env
    assert deployer(chemin, seulement=["Hôtes"]) == 0
    assert faux.obtenir("IPHost", "RES-LAN") and faux.obtenir("FirewallRule", "LAN vers Internet") is None


def test_journal_debug_et_rapport_html(env):
    faux, chemin = env
    wb = load_workbook(chemin)
    wb["Comptes"]["F2"] = "MotDePasse-Tres-Secret-1"
    wb.save(chemin)
    assert deployer(chemin, debug=True) == 0
    journal = next(Path("rapports").glob("*_debug.log")).read_text(encoding="utf-8")
    assert "<Password>********</Password>" in journal and "Tres-Secret" not in journal
    page = next(Path("rapports").glob("Exemple*.html")).read_text(encoding="utf-8")
    assert "Rapport de configuration" in page and "Tres-Secret" not in page
    assert masquer("<Key>abc</Key><PresharedKey>x</PresharedKey>") == "<Key>********</Key><PresharedKey>********</PresharedKey>"


def test_resume_operations(env):
    _, chemin = env
    lignes = resume_operations(lire_classeur(chemin).operations)
    assert any("règle(s) de pare-feu" in l for l in lignes) and any(l.startswith("réglages") for l in lignes)


def test_nouvelles_tentatives_reseau(monkeypatch):
    import requests
    appels = []
    f = FauxXGS()

    def instable(url, data, **kw):
        appels.append(1)
        if len(appels) < 3:
            raise requests.exceptions.ConnectionError("coupure")
        return f.post(url, data, **kw)
    monkeypatch.setattr(api_mod.requests, "post", instable)
    monkeypatch.setattr(api_mod.time, "sleep", lambda s: None)
    SophosAPI("172.16.16.16", "admin", "secret").tester_connexion()
    assert len(appels) == 3


# ----------------------------------------------------------------------------- documents
def test_dossier_technique_sans_mot_de_passe(env):
    _, chemin = env
    wb = load_workbook(chemin)
    wb["Comptes"]["F2"] = "Secret-Visible-1"
    wb.save(chemin)
    page = generer(chemin).read_text(encoding="utf-8")
    assert "Dossier technique" in page and "LAN vers Internet" in page and "SRV-AD-01" in page
    assert "Secret-Visible" not in page and "coffre-fort" in page


def test_diagnostic_port_ferme():
    from sophos_auto.diagnostic import diagnostiquer
    etapes = diagnostiquer("127.0.0.1", 1, mot_de_passe="x")
    assert not etapes[-1][0] and "ne répond pas" in etapes[-1][1]
    assert not diagnostiquer("pas-une-ip")[0][0]


# ----------------------------------------------------------------------------- audit
def test_audit_note_et_doublons(env, monkeypatch):
    faux, _ = env
    regle = {"Status": "Enable", "NetworkPolicy": {"Action": "Accept", "SourceZones": {"Zone": "LAN"},
                                                   "DestinationZones": {"Zone": "DMZ"}}}
    faux._mettre("FirewallRule", {"Name": "A", **regle})
    faux._mettre("FirewallRule", {"Name": "B", **regle})
    constats = auditer(SophosAPI("172.16.16.16", "admin", "secret"))
    assert any("Règles en double" in c.titre for c in constats)
    assert 0 <= note(constats) < 100
    from sophos_auto.audit import executer
    _, chemin = executer(SophosAPI("172.16.16.16", "admin", "secret"), "172.16.16.16", "Test")
    donnees = json.loads(chemin.with_suffix(".json").read_text(encoding="utf-8"))
    assert donnees["note"] == note(constats) and "Note" in chemin.read_text(encoding="utf-8")


# ----------------------------------------------------------------------------- Central
def test_firmware_et_sauvegarde_de_tous(tmp_path):
    assert firmware_compatible("SFOS 22.0.0 MR-2") and not firmware_compatible("SFOS 21.5.0 MR-1")
    c = SophosCentral("id", "bon", session=FauxCentral())
    c.connecter()
    res = {pf.nom: r for pf, r in c.sauvegarder_tous(tmp_path)}
    assert isinstance(res["fw-modele"], Path) and res["fw-dupont"] == "non connecté à Central"


# ----------------------------------------------------------------------------- assistant
def test_fiches_vpn_et_teletravail(tmp_path, monkeypatch):
    from sophos_auto import assistant
    from tests.repondeur import Repondeur
    from tests.test_assistant import SCENARIO_PME
    monkeypatch.chdir(tmp_path)
    regles = [x for x in SCENARIO_PME if not x[0].startswith("Appliquer")] + [(r"Appliquer la configuration", "n")]
    r = Repondeur(regles)
    monkeypatch.setattr(builtins, "input", r)
    monkeypatch.setattr(getpass, "getpass", r)
    assert assistant.main() == 0
    autre = (tmp_path / "clients" / "dupont-industrie_vpn_lyon.txt").read_text(encoding="utf-8")
    assert "192.168.50.0/24   (les réseaux de Lyon)" in autre and "Répondre" in autre
    fiche = (tmp_path / "clients" / "dupont-industrie_teletravail" / "jdupont.txt").read_text(encoding="utf-8")
    assert "jdupont" in fiche and "Sophos Connect" in fiche
    assert (tmp_path / "clients" / "dupont-industrie_dossier.html").exists()
    cfg = lire_classeur(str(tmp_path / "clients" / "dupont-industrie.xlsx"))
    assert cfg.general["Début plage VPN"] == "10.81.234.5" and cfg.erreurs == []


def test_parametres_societe_dans_les_rapports(env):
    from sophos_auto.parametres import charger, enregistrer
    _, chemin = env
    enregistrer({"societe": "InfoServices Test", "inconnu": "ignoré"})
    assert charger()["societe"] == "InfoServices Test" and "inconnu" not in charger()
    assert deployer(chemin) == 0
    assert "InfoServices Test" in next(Path("rapports").glob("Exemple*.html")).read_text(encoding="utf-8")
    assert "InfoServices Test" in generer(chemin).read_text(encoding="utf-8")
