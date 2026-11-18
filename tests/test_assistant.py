"""Déroulé complet de l'assistant (scénario PME), puis application sur le faux pare-feu."""
import builtins
import getpass

from sophos_auto import api as api_mod
from sophos_auto import assistant
from sophos_auto.modele import lire_classeur
from tests.faux_xgs import FauxXGS
from tests.repondeur import Repondeur

SCENARIO_PME = [
    (r"Nom du client", "Dupont Industrie"),
    (r"Votre choix", "2"),                                  # situation : PME
    (r"géré dans Sophos Central", "n"),
    (r"Votre choix", "2"),                                  # WAN : IP fixe
    (r"IP du pare-feu côté Internet", "203.0.113.10/29"),
    (r"DEUXIÈME accès", "o"),
    (r"Votre choix", "1"),                                  # 2e lien en DHCP
    (r"Votre choix", "1"),                                  # en secours
    (r"IP que doit prendre le pare-feu sur le LAN", "192.168.1.254/24"),
    (r"IP du contrôleur de domaine", "192.168.1.10"),
    (r"Nom du domaine", "dupont.local"),
    (r"Relier le pare-feu à l'Active Directory", "o"),
    (r"Compte de service", "svc-fw"),
    (r"service AD \(saisie", "Svc-Passw0rd!"),
    (r"Confirmez", "Svc-Passw0rd!"),
    (r"Votre choix", "3"),                                  # équipement : NVR
    (r"Adresse IP de NVR", "192.168.1.20"),
    (r"Votre choix", "7"),                                  # fin des équipements
    (r"Votre choix", "1"),                                  # DHCP : le pare-feu
    (r"même adresse", "o"),
    (r"Nom de l'appareil", "COPIEUR"),
    (r"Adresse MAC", "00:11:22:33:44:55"),
    (r"Adresse IP réservée", "192.168.1.50"),
    (r"découpé en VLAN", "o"),
    (r"Votre choix", "1"),                                  # VLAN téléphonie
    (r"Votre choix", "7"),                                  # fin des VLAN
    (r"Votre choix", "1"),                                  # Internet : tout autoriser
    (r"bornes Wi-Fi Sophos", "o"),
    (r"accessible depuis Internet", "o"),
    (r"Adresse IP \(ou nom\) de l'équipement", "192.168.1.20"),
    (r"Votre choix", "3"),                                  # service personnalisé
    (r"Port vu depuis Internet", "8443"),
    (r"Votre choix", "1"),                                  # TCP
    (r"Port sur l'équipement", "443"),
    (r"Votre choix", "1"),                                  # zone LAN
    (r"relier ce site", "o"),
    (r"Nom du site distant", "Lyon"),
    (r"IP publique ou nom DNS du pare-feu de Lyon", "198.51.100.7"),
    (r"Réseau\(x\) de Lyon", "192.168.50.0/24"),
    (r"Votre choix", "1"),                                  # ce pare-feu initie
    (r"Identifiant de la personne", "jdupont"),
    (r"Nom et prénom", "Jean Dupont"),
    (r"E-mail \(facultatif\)", "j.dupont@dupont.fr"),
    (r"Identifiant de la personne", "mmartin"),
    (r"Votre choix", "1"),                                  # Microsoft 365
    (r"Adresse expéditeur", "firewall@dupont.fr"),
    (r"reçoit les alertes", "support@presta.fr"),
    (r"Mot de passe SMTP \(saisie", "Smtp-Passw0rd"),
    (r"Confirmez", "Smtp-Passw0rd"),
    (r"Votre choix", "1"),                                  # sauvegarde par e-mail
    (r"Votre choix", "1"),                                  # hebdomadaire
    (r"supervisé en SNMP", "o"),
    (r"IP du serveur de supervision", "192.168.1.30"),
    (r"Appliquer la configuration sur le pare-feu maintenant", "o"),
]


def test_assistant_pme_complet(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    faux = FauxXGS()
    monkeypatch.setattr(api_mod.requests, "post", faux.post)
    monkeypatch.setenv("SOPHOS_MOT_DE_PASSE", "secret")
    journal = []
    r = Repondeur(SCENARIO_PME, journal)
    monkeypatch.setattr(builtins, "input", r)
    monkeypatch.setattr(getpass, "getpass", r)

    assert assistant.main() == 0
    assert r.regles == [], f"questions attendues non posées : {r.regles}"

    # Le fichier Excel produit est valide et ne contient aucun mot de passe
    xlsx = tmp_path / "clients" / "dupont-industrie.xlsx"
    cfg = lire_classeur(str(xlsx))
    assert cfg.erreurs == []
    from openpyxl import load_workbook
    textes = " ".join(str(c.value) for ws in load_workbook(xlsx).worksheets for row in ws.iter_rows() for c in row)
    assert "Svc-Passw0rd!" not in textes and "Smtp-Passw0rd" not in textes
    assert (tmp_path / "clients" / "dupont-industrie_fiche.txt").exists()

    # Tout a été appliqué sur le faux pare-feu, y compris après le changement d'IP du LAN
    o = faux.obtenir
    assert faux.ip == "192.168.1.254"
    assert o("Interface", "Port1")["IPAddress"] == "192.168.1.254"
    assert o("Interface", "Port2")["GatewayIP"] == "203.0.113.9"
    assert o("DHCPServer", "DHCP-LAN")["StaticLease"]["Lease"]["MACAddress"] == "00:11:22:33:44:55"
    assert o("DHCPServer", "DHCP-LAN")["PrimaryDNSServer"] == "192.168.1.10"
    assert o("VLAN", "Port1.10")["Zone"] == "TELEPHONIE"
    assert o("NATRule", "PUBLI-NVR-02-1")["TranslatedService"] == "TCP-443"
    assert o("VPNIPSecConnection", "VPN-LYON")["Configuration"]["PresharedKey"]
    assert o("SSLVPNPolicy", "VPN-TELETRAVAIL")["TunnelPolicy"]["PolicyMembers"]["Member"] == ["jdupont", "mmartin"]
    assert o("User", "jdupont")["Password"]
    assert o("User", "admin-presta")["UserType"] == "Administrator"
    assert o("AuthenticationServer", "AD-dupont.local")["ActiveDirectory"]["Password"] == "Svc-Passw0rd!"
    assert o("Notification", "")["Password"] == "Smtp-Passw0rd"
    assert o("GatewayConfiguration", "")["Gateway"][1]["Type"] == "Backup"
    assert o("Zone", "WAN")["ApplianceAccess"]["VPNServices"]["SSLVPN"] == "Enable"
    assert o("WirelessNetworks", "WIFI-INVITES")["ClientIsolation"] == "Enabled"
    assert o("FirewallRule", "Wi-Fi invités vers Internet")
    assert o("SNMPCommunity", "supervision-dupont-industrie")
    # aucun mot de passe redemandé pendant l'application
    debut = next(i for i, (q, _) in enumerate(journal) if "Envoyer au pare-feu" in q)
    assert not any(("Confirmez" in q or "Mot de passe" in q) for q, _ in journal[debut:])


def test_assistant_petit_bureau_valeurs_par_defaut(tmp_path, monkeypatch):
    """Petit bureau : on garde presque toutes les propositions ; le fichier produit doit être valide."""
    monkeypatch.chdir(tmp_path)
    r = Repondeur([
        (r"Nom du client", "Boulangerie Martin"),
        (r"alertes du pare-feu par e-mail", "n"),
        (r"Votre choix", "1"),   # situation
        (r"Votre choix", "1"),   # WAN DHCP
        (r"Votre choix", "1"),   # DHCP par le pare-feu
        (r"Votre choix", "1"),   # Internet : tout
        (r"Votre choix", "2"),   # sauvegarde : locale (pas d'e-mail configuré)
        (r"Appliquer la configuration", "n"),
    ])
    monkeypatch.setattr(builtins, "input", r)
    monkeypatch.setattr(getpass, "getpass", r)
    assert assistant.main() == 0
    cfg = lire_classeur(str(tmp_path / "clients" / "boulangerie-martin.xlsx"))
    assert cfg.erreurs == []
    noms = {o.nom for o in cfg.operations}
    assert {"DHCP-LAN", "LAN vers Internet", "Sauvegarde automatique", "admin-presta"} <= noms
    # Géré par Sophos Central en Zero Touch (réponses par défaut) : le boîtier a déjà sa nouvelle IP
    assert cfg.general["Adresse IP du pare-feu"] == "192.168.10.254"
    assert not any(o.balise == "Interface" and o.cle == "Port1" for o in cfg.operations)
    fiche = (tmp_path / "clients" / "boulangerie-martin_fiche.txt").read_text(encoding="utf-8")
    assert "Zero Touch" in fiche and "IP 192.168.10.254" in fiche and "Port2, mode DHCP" in fiche
    assert not (tmp_path / "clients" / "brouillons" / "boulangerie-martin.json").exists()


def test_assistant_mots_de_passe_dans_excel(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    regles = [x for x in SCENARIO_PME if not x[0].startswith("Appliquer")]
    regles += [(r"Enregistrer aussi les mots de passe", "o"), (r"Appliquer la configuration", "n")]
    r = Repondeur(regles)
    monkeypatch.setattr(builtins, "input", r)
    monkeypatch.setattr(getpass, "getpass", r)
    assert assistant.main() == 0
    from sophos_auto.deployer import secrets_de
    cfg = lire_classeur(str(tmp_path / "clients" / "dupont-industrie.xlsx"))
    assert cfg.erreurs == []
    assert secrets_de(cfg) == []   # plus rien à demander : tout est dans le fichier


def test_assistant_retour_et_reprise(tmp_path, monkeypatch):
    """« < » recommence l'étape ; une interruption laisse un brouillon que l'on peut reprendre."""
    monkeypatch.chdir(tmp_path)
    r = Repondeur([
        (r"Nom du client", "Garage Test"),
        (r"Votre choix", "1"),
        (r"géré dans Sophos Central", "n"),
        (r"Port du XGS relié à la box", "<"),        # recommencer l'étape Internet
        (r"Port du XGS relié à la box", "Port3"),
        (r"Votre choix", "1"),
        (r"Port du XGS relié au switch", "STOP"),    # interruption simulée
    ])

    def repondre(invite=""):
        rep = r(invite)
        if rep == "STOP":
            raise KeyboardInterrupt
        return rep
    monkeypatch.setattr(builtins, "input", repondre)
    monkeypatch.setattr(getpass, "getpass", repondre)
    assert assistant.main() == 1
    brouillon = tmp_path / "clients" / "brouillons" / "garage-test.json"
    assert brouillon.exists()
    import json
    d = json.loads(brouillon.read_text(encoding="utf-8"))
    assert d["etape"] == 2
    assert [l["Port"] for l in d["projet"]["lignes"]["Interfaces"]] == ["Port3"]   # pas de doublon après « < »

    # Reprise : on choisit le brouillon, on termine avec les réponses par défaut
    r2 = Repondeur([(r"Votre choix", "2"), (r"alertes du pare-feu par e-mail", "n"),
                    (r"Votre choix", "1"), (r"Votre choix", "1"), (r"Votre choix", "2"),
                    (r"Appliquer la configuration", "n")])
    monkeypatch.setattr(builtins, "input", r2)
    monkeypatch.setattr(getpass, "getpass", r2)
    assert assistant.main() == 0
    cfg = lire_classeur(str(tmp_path / "clients" / "garage-test.xlsx"))
    assert cfg.erreurs == []
    assert any(o.balise == "Interface" and o.cle == "Port3" for o in cfg.operations)
    assert not brouillon.exists()
