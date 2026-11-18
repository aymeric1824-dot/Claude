"""Tests du fichier Excel et du déploiement, sans vrai pare-feu."""
import pytest
from openpyxl import load_workbook

from sophos_auto import api as api_mod
from sophos_auto.creer_modele import creer
from sophos_auto.deployer import main
from sophos_auto.modele import lire_classeur
from tests.faux_xgs import FauxXGS


@pytest.fixture
def modele(tmp_path):
    return creer(str(tmp_path / "client.xlsx"))


@pytest.fixture
def faux(monkeypatch, tmp_path):
    f = FauxXGS()
    monkeypatch.setattr(api_mod.requests, "post", f.post)
    monkeypatch.setenv("SOPHOS_MOT_DE_PASSE", "secret")
    monkeypatch.chdir(tmp_path)
    return f


def _sans_secrets(chemin):
    wb = load_workbook(chemin)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.value == "*demander*":
                    c.value = "MotDePasse-Test-1"
    wb.save(chemin)


def test_modele_valide(modele):
    cfg = lire_classeur(modele)
    assert cfg.erreurs == []
    noms = {o.nom for o in cfg.operations}
    assert {"Port1.10", "LAN vers Internet", "DHCP-LAN", "RES_192.168.10.0_24"} <= noms
    dhcp = next(o for o in cfg.operations if o.nom == "DHCP-LAN")
    assert dhcp.contenu["StaticLease"]["Lease"][0]["MACAddress"] == "00:11:22:33:44:55"
    assert not cfg.avertissements  # HTTP/HTTPS/DNS et stratégies d'origine : pas d'avertissement


def test_erreurs_detectees(tmp_path):
    chemin = creer(str(tmp_path / "c.xlsx"))
    wb = load_workbook(chemin)
    wb["Hôtes"]["D2"] = "172.16.16.5"     # pas une adresse de réseau
    wb["Hôtes"]["D3"] = "192.168.10.300"  # IP invalide
    wb["Services"]["D2"] = "99999"
    wb["Réservations DHCP"]["D2"] = "pas-une-mac"
    wb.save(chemin)
    erreurs = lire_classeur(chemin).erreurs
    assert len(erreurs) == 4, erreurs


def test_deploiement_puis_relance(modele, faux):
    _sans_secrets(modele)
    assert main([modele]) == 0
    assert faux.obtenir("FirewallRule", "LAN vers Internet")["NetworkPolicy"]["WebFilter"] == "Default Workplace Policy"
    assert faux.obtenir("VLAN", "Port1.10")
    assert faux.obtenir("Interface", "Port2")["IPv4Assignment"] == "DHCP"
    assert faux.obtenir("AdminSettings", "")["HostnameSettings"]["HostName"] == "fw-exemple"
    import pathlib
    assert list(pathlib.Path("rapports").glob("*_avant.json"))      # état avant modification
    assert list(pathlib.Path("rapports").glob("securite_*.html"))   # contrôle de sécurité après
    n = sum(len(v) for v in faux.objets.values())
    assert main([modele]) == 0           # relance : mises à jour, pas de doublons
    assert sum(len(v) for v in faux.objets.values()) == n


def test_nom_inconnu_sur_le_pare_feu(modele, faux, monkeypatch):
    _sans_secrets(modele)
    wb = load_workbook(modele)
    wb["Règles"]["J2"] = "Strategie-Inexistante"
    wb.save(modele)
    monkeypatch.setattr("builtins.input", lambda *_: "n")
    assert main([modele]) == 1
    assert faux.obtenir("FirewallRule", "LAN vers Internet") is None


def test_mauvais_mot_de_passe(modele, faux, monkeypatch):
    monkeypatch.setenv("SOPHOS_MOT_DE_PASSE", "faux")
    assert main([modele]) == 1


def test_simulation_n_envoie_rien(modele, faux):
    assert main([modele, "--simulation"]) == 0
    assert faux.requetes == []
    fichiers = list(__import__("pathlib").Path("simulation").rglob("*.xml"))
    assert len(fichiers) > 10
    assert all("MotDePasse" not in f.read_text(encoding="utf-8") for f in fichiers)
