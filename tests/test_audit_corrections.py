"""Non-régression des fautes trouvées pendant l'audit."""
import builtins
from pathlib import Path

import pytest

from sophos_auto import api as api_mod
from sophos_auto.api import SophosAPI
from sophos_auto.audit import ATTENTION, INFO, auditer
from sophos_auto.deployer import deployer
from sophos_auto.modele import lire_classeur
from sophos_auto.restaurer import restaurer
from tests.faux_xgs import FauxXGS
from tests.test_v5 import _fichier


@pytest.fixture
def faux(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    f = FauxXGS()
    f._mettre("DecryptionProfile", {"Name": "Maximum compatibility"})
    monkeypatch.setattr(api_mod.requests, "post", f.post)
    monkeypatch.setattr(api_mod.time, "sleep", lambda s: None)
    monkeypatch.setenv("SOPHOS_MOT_DE_PASSE", "secret")
    return f


def test_operation_finale_apres_changement_ip_sans_dhcp(tmp_path, faux, monkeypatch):
    """Faute 1 : la double authentification admin (tout à la fin) doit partir vers la nouvelle IP."""
    chemin = _fichier(tmp_path, {"Double authentification administrateurs": "Oui"}, {
        "Interfaces": [{"Port": "Port1", "Zone": "LAN", "Mode": "Statique", "Adresse IP": "192.168.5.254", "Masque": "/24"}],
        "DHCP": [], "Réservations DHCP": [], "Hôtes": [{"Nom": "RES-LAN", "Type": "Réseau", "Adresse": "192.168.5.0",
                                                        "Masque / IP de fin": "/24"}],
    })
    monkeypatch.setattr(builtins, "input", lambda *_: "")
    assert deployer(chemin) == 0
    assert faux.ip == "192.168.5.254"
    assert faux.obtenir("OTPSettings", "")["otpWebAdmin"] == "1"


def test_une_erreur_du_general_ne_bloque_pas_les_autres_sections(tmp_path):
    """Faute 2 : alertes e-mail incomplètes, mais la sauvegarde et le SNMP sont quand même préparés."""
    chemin = _fichier(tmp_path, {"Serveur SMTP": "smtp.x.fr", "Fréquence de sauvegarde": "Hebdomadaire",
                                 "Destination de la sauvegarde": "Locale", "SNMP activé": "Oui",
                                 "Communauté SNMP": "supervision", "IP du serveur de supervision": "192.168.10.30",
                                 "Mot de passe de chiffrement de la sauvegarde": "Chiffre-123456"})
    cfg = lire_classeur(chemin)
    assert any("alertes e-mail" in e for e in cfg.erreurs)
    noms = {o.nom for o in cfg.operations}
    assert "Sauvegarde automatique" in noms and "SNMP" in noms


def test_fuseau_vide_ne_modifie_pas_l_heure(tmp_path):
    """Faute 3."""
    assert not any(o.balise == "Time" for o in lire_classeur(_fichier(tmp_path, {"Fuseau horaire": ""})).operations)
    assert any(o.balise == "Time" for o in lire_classeur(_fichier(tmp_path, {})).operations)


def test_conseil_affiche_en_cas_d_echec(tmp_path, faux, monkeypatch):
    """Faute 4 : le conseil d'une opération non facultative apparaît dans le rapport."""
    original = faux.post

    def refuser(url, data, **kw):
        if "<CountryGroup>" in data["reqxml"]:
            return __import__("tests.faux_xgs", fromlist=["_rep"])._rep(
                '<CountryGroup><Status code="500">Invalid country.</Status></CountryGroup>')
        return original(url, data, **kw)
    monkeypatch.setattr(api_mod.requests, "post", refuser)
    deployer(_fichier(tmp_path, {"Pays bloqués": "Narnia"}))
    rapport = next(Path("rapports").glob("*.txt")).read_text(encoding="utf-8")
    assert "à faire à la main : vérifiez l'orthographe des pays" in rapport


def test_retour_en_arriere_des_fonctions_v5(tmp_path, faux):
    """Fautes 6, 7, 8 : RED supprimé, règle d'inspection supprimée avant les objets, OTP remis."""
    chemin = _fichier(tmp_path, {"Double authentification VPN": "Oui", "Inspection HTTPS activée": "Oui",
                                 "Réseaux à inspecter": "192.168.77.0/24"}, {
        "RED": [{"Nom": "AGENCE", "Modèle": "RED15", "ID du RED": "A1", "Adresse du pare-feu": "a.fr", "Zone": "LAN",
                 "Adresse IP": "192.168.30.254", "Masque": "/24"}]})
    faux.objets["OTPSettings"] = {"": {"otp": "0", "otpSSLVPN": "0"}}
    assert deployer(chemin) == 0
    assert faux.obtenir("REDDevice", "") and faux.obtenir("OTPSettings", "")["otpSSLVPN"] == "1"
    photo = next(Path("rapports").glob("*_avant.json"))
    assert restaurer(str(photo), SophosAPI("172.16.16.16", "admin", "secret"), confirmer=lambda q: True) == 0
    assert not faux.objets.get("REDDevice")
    assert faux.obtenir("SSLTLSInspectionRule", "INSPECTION-HTTPS") is None
    assert faux.obtenir("IPHost", "RES_192.168.77.0_24") is None
    assert faux.obtenir("OTPSettings", "")["otpSSLVPN"] == "0"


def test_audit_coherent_avec_les_regles_de_l_assistant(faux):
    """Faute 9 : une règle avec filtrage web mais sans antivirus n'est qu'un conseil."""
    faux._mettre("FirewallRule", {"Name": "Wi-Fi invités vers Internet", "Status": "Enable", "NetworkPolicy": {
        "Action": "Accept", "SourceZones": {"Zone": "WiFi"}, "DestinationZones": {"Zone": "WAN"},
        "WebFilter": "Default Workplace Policy"}})
    faux._mettre("FirewallRule", {"Name": "Sans rien", "Status": "Enable", "NetworkPolicy": {
        "Action": "Accept", "SourceZones": {"Zone": "LAN"}, "DestinationZones": {"Zone": "WAN"}}})
    niveaux = {c.titre: c.niveau for c in auditer(SophosAPI("172.16.16.16", "admin", "secret"))}
    assert niveaux["Accès Internet sans protection complète : « Wi-Fi invités vers Internet »"] == INFO
    assert niveaux["Accès Internet sans protection complète : « Sans rien »"] == ATTENTION


def test_plage_dhcp_jamais_sur_le_pare_feu_et_grands_reseaux():
    """Fautes 17 et 18."""
    import ipaddress
    import time
    from sophos_auto.assistant import _plage_dhcp
    for iface in ("192.168.1.150/24", "192.168.1.254/24", "10.0.0.1/8", "172.16.0.10/26", "192.168.5.20/28"):
        i = ipaddress.IPv4Interface(iface)
        debut, fin = (ipaddress.IPv4Address(x) for x in _plage_dhcp(i))
        assert debut <= fin and debut in i.network and fin in i.network
        assert not debut <= i.ip <= fin, iface
    t = time.time()
    _plage_dhcp(ipaddress.IPv4Interface("10.0.0.1/8"))
    assert time.time() - t < 0.1


def test_lire_ne_confond_pas_un_objet_avec_une_reponse_vide(faux):
    """Faute 19 : un objet qui a un champ Status n'est pas une réponse « aucun enregistrement »."""
    faux.objets["OTPSettings"] = {"": {"otp": "1", "Status": "x"}}
    assert SophosAPI("172.16.16.16", "admin", "secret").lire("OTPSettings") == {"otp": "1", "Status": "x"}
    assert SophosAPI("172.16.16.16", "admin", "secret").lire("NATRule") is None


def test_script_de_mise_a_jour_sans_timeout():
    """Faute 16 : le script de remplacement n'utilise pas « timeout » et réessaie tant que l'ancien est ouvert."""
    from pathlib import PureWindowsPath
    from sophos_auto.mise_a_jour import script_remplacement
    neuf, exe = PureWindowsPath("C:/A B/SophosXGS.nouveau.exe"), PureWindowsPath("C:/A B/SophosXGS.exe")
    script = script_remplacement(neuf, exe)
    assert "timeout" not in script and "goto attente" in script and "ping -n 2" in script
    assert f'move /y "{neuf}" "{exe}"' in script and "C:\\A B\\SophosXGS.exe" in script
    assert script.index("move") < script.index("start")


def test_dossier_technique_contient_les_sections_v5(tmp_path):
    """Faute 21."""
    from sophos_auto.documentation import generer
    page = generer(_fichier(tmp_path, {"Double authentification VPN": "Oui", "Pays bloqués": "North Korea",
                                       "Rôle haute disponibilité": "Principal", "Port de liaison HA": "Port8"})
                   ).read_text(encoding="utf-8")
    for attendu in ("Double authentification", "Filtrage par pays", "North Korea", "Haute disponibilité", "Port8"):
        assert attendu in page, attendu
    assert "Connexion au pare-feu" not in page


def test_menu_et_guide_coherents():
    """Faute 22/23 : les fonctions citées dans le guide existent dans le menu, le nombre de termes est exact."""
    from sophos_auto.__main__ import MENU
    from sophos_auto.glossaire import TERMES
    guide = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
    assert f"{len(TERMES)} termes" in guide
    numeros = [l.split("|")[1].strip() for l in guide.splitlines() if l.startswith("| ") and l.split("|")[1].strip().isdigit()]
    assert len(numeros) == len([m for m in MENU if m[2] is not None])
