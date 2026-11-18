"""Fonctions v5 : pays, double authentification, inspection HTTPS, HA, SD-WAN, priorités, RED, audit, métiers,
glossaire, coffre KeePass, mise à jour."""
import builtins
import getpass

import pytest
from openpyxl import load_workbook

from sophos_auto import api as api_mod
from sophos_auto.api import SophosAPI
from sophos_auto.audit import auditer
from sophos_auto.classeur import ecrire_classeur
from sophos_auto.creer_modele import EXEMPLES, GENERAL_EXEMPLE
from sophos_auto.deployer import deployer
from sophos_auto.modele import lire_classeur
from tests.faux_xgs import FauxXGS


def _fichier(tmp_path, general=None, lignes=None):
    g = dict(GENERAL_EXEMPLE, **(general or {}))
    l = {k: list(v) for k, v in EXEMPLES.items()}
    for k, v in (lignes or {}).items():
        l[k] = v
    for onglet in l:
        for ligne in l[onglet]:
            for k, v in list(ligne.items()):
                if v == "*demander*":
                    ligne[k] = "MotDePasse-Test-1"
    return ecrire_classeur(str(tmp_path / "c.xlsx"), g, l)


@pytest.fixture
def faux(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    f = FauxXGS()
    for n in ("Maximum compatibility",):
        f._mettre("DecryptionProfile", {"Name": n})
    monkeypatch.setattr(api_mod.requests, "post", f.post)
    monkeypatch.setenv("SOPHOS_MOT_DE_PASSE", "secret")
    return f


def test_toutes_les_fonctions_avancees(tmp_path, faux):
    chemin = _fichier(tmp_path, {
        "Pays autorisés depuis Internet": "France;Belgium", "Pays bloqués": "North Korea",
        "Double authentification VPN": "Oui", "Inspection HTTPS activée": "Oui",
        "Rôle haute disponibilité": "Principal", "Port de liaison HA": "Port8", "Phrase secrète HA": "Phrase-HA-123456",
    }, {
        "Redirections": [{"Nom": "WEB", "Port WAN": "Port2", "Service externe": "HTTPS", "Serveur interne": "172.16.16.20",
                          "Zone du serveur": "LAN"}],
        "SD-WAN": [{"Nom": "VOIX", "Réseaux source": "RES-LAN", "Passerelle principale": "Port2_GW",
                    "Passerelle de secours": "Port3_GW"}],
        "Priorités": [{"Nom": "PRIORITE-VOIX", "Priorité": "Temps réel", "Garanti (Ko/s)": 256, "Maximum (Ko/s)": 1024}],
        "RED": [{"Nom": "AGENCE-LYON", "Modèle": "RED15", "ID du RED": "A1234567890", "Adresse du pare-feu": "203.0.113.1",
                 "Zone": "LAN", "Adresse IP": "192.168.30.254", "Masque": "/24"}],
        "Règles": EXEMPLES["Règles"] + [{"Nom": "Voix", "Action": "Accepter", "Zones source": "LAN",
                                         "Zones destination": "WAN", "Priorité (QoS)": "PRIORITE-VOIX"}],
    })
    cfg = lire_classeur(chemin)
    assert cfg.erreurs == [], cfg.erreurs
    assert deployer(chemin) == 0
    o = faux.obtenir
    assert o("CountryGroup", "PAYS-AUTORISES")["CountryList"]["Country"] == ["France", "Belgium"]
    nat_regle = o("FirewallRule", "WEB - accès")["NetworkPolicy"]
    assert nat_regle["SourceNetworks"]["Network"] == "PAYS-AUTORISES"
    blocage = o("FirewallRule", "Blocage des pays interdits")
    assert blocage["Position"] == "Top" and blocage["NetworkPolicy"]["Action"] == "Drop"
    assert o("OTPSettings", "")["otpSSLVPN"] == "1" and o("OTPSettings", "")["otpWebAdmin"] == "0"
    assert o("SSLTLSInspectionRule", "INSPECTION-HTTPS")["DecryptAction"] == "Decrypt"
    assert o("HAConfigure", "")["HA_Quick"]["Passphrase"] == "Phrase-HA-123456"
    assert o("SDWANPolicyRoute", "VOIX")["Gateway"] == "Port2_GW"
    assert o("QoSPolicy", "PRIORITE-VOIX")["GuaranteedBandwidth"] == "256"
    assert o("FirewallRule", "Voix")["NetworkPolicy"]["TrafficShapingPolicy"] == "PRIORITE-VOIX"
    assert o("REDDevice", "")["NetworkSetting"]["IPAddress"] == "192.168.30.254"


def test_controles_des_nouveaux_onglets(tmp_path):
    chemin = _fichier(tmp_path, {"Rôle haute disponibilité": "Principal"}, {
        "Priorités": [{"Nom": "P", "Priorité": "Temps réel", "Garanti (Ko/s)": 500, "Maximum (Ko/s)": 100}],
        "SD-WAN": [{"Nom": "S"}],
        "RED": [{"Nom": "R", "Modèle": "RED15", "Adresse IP": "192.168.10.1", "Masque": "/24",
                 "ID du RED": "X", "Adresse du pare-feu": "a.fr"}],   # chevauche le VLAN 10
    })
    erreurs = " ".join(lire_classeur(chemin).erreurs)
    for attendu in ("débit maximum", "passerelle principale", "port de liaison", "se chevauchent"):
        assert attendu in erreurs, erreurs


def test_profil_de_destination_inconnu_signale(tmp_path, faux, monkeypatch):
    chemin = _fichier(tmp_path, {"Inspection HTTPS activée": "Oui", "Profil de déchiffrement": "Profil-Inexistant"})
    monkeypatch.setattr(builtins, "input", lambda *_: "n")
    assert deployer(chemin) == 1          # arrêt avant toute modification


def test_audit_vpn_faible_et_sans_double_authentification(faux):
    faux._mettre("VPNIPSecConnection", {"Configuration": {"Name": "V1", "Policy": "Ancien"}})
    faux._mettre("VPNProfile", {"Name": "Ancien", "Phase1": {"EncryptionAlgorithm1": "3DES",
                                                            "SupportedDHGroups": {"DHGroup": "2(DH1024)"}},
                                "Phase2": {"AuthenticationAlgorithm1": "MD5"}})
    faux._mettre("SSLVPNPolicy", {"TunnelPolicy": {"Name": "T"}})
    titres = {c.titre for c in auditer(SophosAPI("172.16.16.16", "admin", "secret"))}
    assert "Chiffrement VPN dépassé : profil « Ancien »" in titres
    assert "VPN télétravail sans double authentification" in titres


def test_glossaire():
    from sophos_auto.glossaire import chercher
    assert chercher("dhcp")[0][0] == "DHCP"
    assert chercher("réservation")[0][0] == "Réservation DHCP"
    assert chercher("haute dispo")[0][0] == "Haute disponibilité"
    assert len(chercher("")) > 40


def test_glossaire_dans_une_question(monkeypatch, capsys):
    from sophos_auto.assistant import texte
    reponses = iter(["?? vlan", "valeur"])
    monkeypatch.setattr(builtins, "input", lambda *_: next(reponses))
    assert texte("Question") == "valeur"
    assert "réseau séparé" in capsys.readouterr().out


def test_metier_propose_ses_vlan(tmp_path, monkeypatch):
    """Commerce : les VLAN CAISSES, INVITES et CAMERAS sont proposés d'office."""
    from sophos_auto import assistant
    from tests.repondeur import Repondeur
    monkeypatch.chdir(tmp_path)
    r = Repondeur([(r"Nom du client", "Boutique"), (r"Votre choix", "1"), (r"Votre choix", "4"),  # commerce
                   (r"Votre choix", "1"), (r"Votre choix", "1"), (r"découpé en VLAN", "o"),
                   (r"Votre choix", "q"), (r"alertes du pare-feu", "n"), (r"Votre choix", "1"),
                   (r"Votre choix", "2"), (r"coffre-fort KeePass", "n"), (r"Appliquer la configuration", "n")])
    monkeypatch.setattr(builtins, "input", r)
    monkeypatch.setattr(getpass, "getpass", r)
    assert assistant.main() == 0
    cfg = lire_classeur(str(tmp_path / "clients" / "boutique.xlsx"))
    assert cfg.erreurs == []
    zones = {o.nom for o in cfg.operations if o.balise == "Zone"}
    assert {"CAISSES", "INVITES", "CAMERAS"} <= zones
    fiche = (tmp_path / "clients" / "boutique_fiche.txt").read_text(encoding="utf-8")
    assert "PCI-DSS" in fiche


def test_coffre_keepass(tmp_path):
    from pykeepass import PyKeePass
    from sophos_auto.coffre import creer_coffre
    f = creer_coffre(str(tmp_path / "x.kdbx"), "Principal-123", "Client", {"Mot de passe du compte jean": "abc"})
    e = PyKeePass(f, password="Principal-123").entries[0]
    assert (e.title, e.username, e.password) == ("Mot de passe du compte jean", "jean", "abc")


def test_mise_a_jour(monkeypatch, tmp_path):
    from sophos_auto import mise_a_jour

    class R:
        status_code = 200

        def __init__(self, tag):
            self.tag = tag

        def json(self):
            return {"tag_name": self.tag, "assets": [{"name": "SophosXGS.exe", "browser_download_url": "https://x/e"}],
                    "body": "notes", "html_url": "https://x/r"}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mise_a_jour.requests, "get", lambda *a, **k: R("v99.0"))
    info = mise_a_jour.verifier()
    assert info["version"] == "99.0" and info["url"] == "https://x/e"
    monkeypatch.setattr(mise_a_jour.requests, "get", lambda *a, **k: R("v0.1"))
    assert mise_a_jour.verifier() is None
    assert "disponible" in mise_a_jour.installer({"version": "9", "page": "p"})   # hors programme Windows

    def coupure(*a, **k):
        raise mise_a_jour.requests.exceptions.ConnectionError()
    monkeypatch.setattr(mise_a_jour.requests, "get", coupure)
    assert mise_a_jour.verifier() is None
