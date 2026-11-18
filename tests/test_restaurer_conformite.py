"""Revenir en arrière, conformité, opérations facultatives (inscription Central, activation IPsec)."""
import copy
from pathlib import Path

from openpyxl import load_workbook

from sophos_auto import api as api_mod
from sophos_auto.api import SophosAPI
from sophos_auto.conformite import verifier
from sophos_auto.creer_modele import creer
from sophos_auto.deployer import main as deployer_main
from sophos_auto.modele import lire_classeur
from sophos_auto.restaurer import restaurer
from tests.faux_xgs import FauxXGS
from tests.test_deploiement import _sans_secrets


def _preparer(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    f = FauxXGS()
    monkeypatch.setattr(api_mod.requests, "post", f.post)
    monkeypatch.setenv("SOPHOS_MOT_DE_PASSE", "secret")
    chemin = creer(str(tmp_path / "client.xlsx"))
    _sans_secrets(chemin)
    return f, chemin


def test_revenir_en_arriere(tmp_path, monkeypatch):
    faux, chemin = _preparer(tmp_path, monkeypatch)
    initial = copy.deepcopy(faux.objets)
    assert deployer_main([chemin]) == 0
    assert faux.obtenir("FirewallRule", "LAN vers Internet")
    photo = next(Path("rapports").glob("*_avant.json"))
    api = SophosAPI("172.16.16.16", "admin", "secret")
    assert restaurer(str(photo), api, confirmer=lambda q: True) == 0
    # objets créés supprimés, réglages et interfaces remis comme avant
    assert faux.obtenir("FirewallRule", "LAN vers Internet") is None
    assert faux.obtenir("VLAN", "Port1.10") is None
    assert faux.obtenir("IPHost", "RES-LAN") is None
    lecture_seule = ("Status", "InterfaceStatus")
    remis = {k: v for k, v in faux.obtenir("Interface", "Port2").items() if k not in lecture_seule}
    assert remis == {k: v for k, v in initial["Interface"]["Port2"].items() if k not in lecture_seule}
    assert faux.obtenir("Zone", "LAN")      # objets d'origine conservés
    # une 2e restauration n'a plus rien à faire
    assert restaurer(str(photo), api, confirmer=lambda q: False) == 0


def test_conformite(tmp_path, monkeypatch):
    faux, chemin = _preparer(tmp_path, monkeypatch)
    api = SophosAPI("172.16.16.16", "admin", "secret")
    ecarts, n = verifier(api, chemin)
    assert n > 10 and sum(e.type == "absent" for e in ecarts) >= 10   # rien n'est encore appliqué
    assert deployer_main([chemin]) == 0
    ecarts, _ = verifier(api, chemin)
    assert ecarts == [], [(e.op.libelle, e.details) for e in ecarts]
    # quelqu'un modifie une règle et supprime un hôte
    faux.objets["FirewallRule"]["LAN vers Internet"]["NetworkPolicy"]["Action"] = "Drop"
    del faux.objets["IPHost"]["SRV-AD-01"]
    ecarts = {e.op.nom: e for e in verifier(api, chemin)[0]}
    assert ecarts["SRV-AD-01"].type == "absent"
    assert ecarts["LAN vers Internet"].type == "différent"
    assert any("Action" in d for d in ecarts["LAN vers Internet"].details)


def test_inscription_central_et_activation_ipsec(tmp_path, monkeypatch):
    faux, chemin = _preparer(tmp_path, monkeypatch)
    wb = load_workbook(chemin)
    g = wb["Général"]
    for row in g.iter_rows(min_row=2):
        if row[0].value == "Inscrire dans Sophos Central":
            row[1].value = "Oui"
        if row[0].value == "Central : e-mail du compte":
            row[1].value = "it@client.fr"
    ws = wb["VPN sites"]
    for col, v in enumerate(["Oui", "VPN-LYON", "Port2", "198.51.100.7", "172.16.16.0/24", "192.168.50.0/24",
                             "Cle-Partagee-Test-123", "IKEv2", "Initier"], start=1):
        ws.cell(2, col, v)
    wb.save(chemin)
    cfg = lire_classeur(chemin)
    assert cfg.erreurs == []
    central = [o for o in cfg.operations if o.balise in ("HBCloudRegistration", "EnableCloudCentralManagement")]
    assert len(central) == 2 and all(o.facultatif for o in central)
    vpn = next(o for o in cfg.operations if o.nom == "VPN-LYON")
    assert vpn.contenu["Configuration"]["ActivateOnSave"] == "y"
    assert any(o.nom == "Activation de VPN-LYON" and o.facultatif for o in cfg.operations)
    # un refus de Central (ex. double authentification) n'est pas compté comme un échec
    original = faux.post

    def refuser_central(url, data, **kw):
        if "HBCloudRegistration" in data["reqxml"]:
            return __import__("tests.faux_xgs", fromlist=["_rep"])._rep(
                '<HBCloudRegistration><Status code="541">MFA required.</Status></HBCloudRegistration>')
        return original(url, data, **kw)
    monkeypatch.setattr(api_mod.requests, "post", refuser_central)
    assert deployer_main([chemin]) == 0
    rapport = next(Path("rapports").glob("*.txt")).read_text(encoding="utf-8")
    assert "À FAIRE [Général] Inscription dans Sophos Central" in rapport
    assert faux.obtenir("EnableCloudCentralManagement", "")["FWBackup"] == "BackupEnable"
