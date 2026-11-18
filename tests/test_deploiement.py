"""Tests sans vrai pare-feu : un faux XGS en mémoire remplace requests.post."""
import xmltodict
import pytest

from sophos_auto import api as api_mod
from sophos_auto.creer_modele import creer
from sophos_auto.deployer import main
from sophos_auto.modele import lire_classeur


class FauxXGS:
    def __init__(self, mdp="secret"):
        self.mdp, self.objets, self.requetes = mdp, {}, []

    def post(self, url, data, headers, verify, timeout):
        req = xmltodict.parse(data["reqxml"])["Request"]
        self.requetes.append(req)
        if req["Login"]["Password"] != self.mdp:
            return _rep("<Login><status>Authentication Failure</status></Login>")
        corps = "<Login><status>Authentication Successful</status></Login>"
        if "Set" in req:
            op = req["Set"]["@operation"]
            for balise, contenu in req["Set"].items():
                if balise.startswith("@"):
                    continue
                cle = (balise, (contenu or {}).get("Name", ""))
                if op == "add" and cle in self.objets:
                    corps += f'<{balise}><Status code="502">Operation failed. Entity having same name already exists.</Status></{balise}>'
                else:
                    self.objets[cle] = contenu
                    corps += f'<{balise}><Status code="200">Configuration applied successfully.</Status></{balise}>'
        return _rep(corps)


class _R:
    def __init__(self, txt):
        self.content, self.text = txt.encode(), txt


def _rep(corps):
    return _R(f'<?xml version="1.0" encoding="UTF-8"?><Response APIVersion="2100.1">{corps}</Response>')


@pytest.fixture
def modele(tmp_path):
    return creer(str(tmp_path / "client.xlsx"))


@pytest.fixture
def faux(monkeypatch):
    f = FauxXGS()
    monkeypatch.setattr(api_mod.requests, "post", f.post)
    monkeypatch.setenv("SOPHOS_MOT_DE_PASSE", "secret")
    return f


def test_modele_valide(modele):
    cfg = lire_classeur(modele)
    assert cfg.erreurs == []
    noms = [o.nom for o in cfg.objets]
    assert "INVITES" not in noms and "Port1.10" in noms and "LAN vers Internet" in noms
    svc = next(o for o in cfg.objets if o.nom == "RDP-TCP-UDP")
    assert [d["Protocol"] for d in svc.contenu["ServiceDetails"]["ServiceDetail"]] == ["TCP", "UDP"]
    res = next(o for o in cfg.objets if o.nom == "RES-SERVEURS")
    assert res.contenu["Subnet"] == "255.255.255.0"
    assert any("HTTPS" in w for w in cfg.avertissements)  # service d'origine, simple avertissement


def test_erreurs_detectees(tmp_path):
    from openpyxl import load_workbook
    chemin = creer(str(tmp_path / "c.xlsx"))
    wb = load_workbook(chemin)
    wb["Hôtes"]["D2"] = "172.16.16.5"     # pas une adresse de réseau
    wb["Hôtes"]["D4"] = "192.168.10.300"  # IP invalide
    wb["Services"]["D2"] = "99999"
    wb.save(chemin)
    erreurs = lire_classeur(chemin).erreurs
    assert len(erreurs) == 3, erreurs


def test_deploiement_puis_relance(modele, faux, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main([modele]) == 0
    assert ("FirewallRule", "LAN vers Internet") in faux.objets
    assert ("VLAN", "Port1.10") in faux.objets
    n = len(faux.objets)
    assert main([modele]) == 0           # relance : mises à jour, pas de doublons
    assert len(faux.objets) == n
    assert list((tmp_path / "rapports").iterdir())


def test_mauvais_mot_de_passe(modele, faux, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SOPHOS_MOT_DE_PASSE", "faux")
    assert main([modele]) == 1
    assert faux.objets == {}


def test_simulation_n_envoie_rien(modele, faux, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main([modele, "--simulation"]) == 0
    assert faux.requetes == []
    assert len(list((tmp_path / "simulation").rglob("*.xml"))) > 10
