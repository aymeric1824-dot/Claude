"""Contrôle de sécurité et client Sophos Central (sans réseau)."""
import json
from pathlib import Path

import pytest

from sophos_auto import api as api_mod
from sophos_auto import central as central_mod
from sophos_auto.api import SophosAPI
from sophos_auto.audit import ATTENTION, CRITIQUE, auditer, rapport_html
from sophos_auto.central import ErreurCentral, SophosCentral
from tests.faux_xgs import FauxXGS


# ----------------------------------------------------------------------------- audit
@pytest.fixture
def faux(monkeypatch):
    f = FauxXGS()
    monkeypatch.setattr(api_mod.requests, "post", f.post)
    return f


def _api():
    return SophosAPI("172.16.16.16", "admin", "secret")


def test_audit_detecte_les_risques(faux):
    faux._mettre("Zone", {"Name": "WAN", "Type": "WAN", "ApplianceAccess": {"AdminServices": {"HTTPS": "Enable"}}})
    faux._mettre("Services", {"Name": "RDP-PERSO", "ServiceDetails": {"ServiceDetail": {"DestinationPort": "3389"}}})
    faux._mettre("NATRule", {"Name": "Bureau distance", "TranslatedDestination": "SRV-01",
                             "OriginalServices": {"Service": "RDP-PERSO"}})
    faux._mettre("FirewallRule", {"Name": "Tout", "Status": "Enable", "NetworkPolicy": {"Action": "Accept"}})
    faux._mettre("FirewallRule", {"Name": "Sortie", "Status": "Enable", "NetworkPolicy": {
        "Action": "Accept", "SourceZones": {"Zone": "LAN"}, "DestinationZones": {"Zone": "WAN"}}})
    faux._mettre("SNMPCommunity", {"Name": "public"})
    constats = auditer(_api())
    titres = {c.titre: c.niveau for c in constats}
    assert titres["Administration du pare-feu ouverte sur Internet"] == CRITIQUE
    assert titres["Service sensible publié sur Internet : « Bureau distance »"] == CRITIQUE
    assert titres["Règle « tout autoriser » : « Tout »"] == CRITIQUE
    assert titres["Accès Internet sans protection complète : « Sortie »"] == ATTENTION
    assert titres["Communauté SNMP par défaut « public »"] == CRITIQUE
    assert titres["Aucune sauvegarde automatique"] == ATTENTION
    assert constats[0].niveau == CRITIQUE   # trié du plus grave au moins grave
    page = rapport_html(constats, "172.16.16.16", "Client <test>")
    assert "Client &lt;test&gt;" in page and "Critique" in page


def test_audit_configuration_propre(faux):
    faux._mettre("FirewallRule", {"Name": "Sortie", "Status": "Enable", "NetworkPolicy": {
        "Action": "Accept", "SourceZones": {"Zone": "LAN"}, "DestinationZones": {"Zone": "WAN"},
        "WebFilter": "Default Workplace Policy", "IntrusionPrevention": "lantowan_general", "ScanVirus": "Enable"}})
    faux.objets["BackupRestore"] = {"": {"ScheduleBackup": {"BackupFrequency": "Weekly", "BackupMode": "Mail"}}}
    faux.objets["Notification"] = {"": {"MailServer": "smtp.office365.com", "Recepient": "a@b.fr"}}
    faux._mettre("User", {"Username": "tech1", "UserType": "Administrator"})
    constats = auditer(_api())
    assert not [c for c in constats if c.niveau in (CRITIQUE, ATTENTION)], constats


# ----------------------------------------------------------------------------- Sophos Central
class Rep:
    def __init__(self, code=200, data=None, contenu=b""):
        self.status_code, self._data = code, data
        self.content = contenu or (json.dumps(data).encode() if data is not None else b"")
        self.text = self.content.decode(errors="replace")

    def json(self):
        return self._data


class FauxCentral:
    """Simule id.sophos.com, whoami, la liste des pare-feux et l'export / import."""

    def __init__(self, type_compte="tenant"):
        self.type_compte, self.appels, self.envoye = type_compte, [], None
        self.etat_tx = {}

    def request(self, methode, url, headers=None, json=None, params=None, data=None, timeout=None):
        self.appels.append((methode, url, headers or {}, json))
        if url.endswith("/oauth2/token"):
            return Rep(200, {"access_token": "JETON"}) if data["client_secret"] == "bon" else Rep(401, {"message": "invalid"})
        assert headers is None or "Authorization" not in headers or headers["Authorization"] == "Bearer JETON"
        if url.endswith("/whoami/v1"):
            return Rep(200, {"id": "T1" if self.type_compte == "tenant" else "P1", "idType": self.type_compte,
                             "apiHosts": {"dataRegion": "https://api-eu01.central.sophos.com"}})
        if url.endswith("/partner/v1/tenants"):
            assert headers["X-Partner-ID"] == "P1"
            return Rep(200, {"items": [{"id": "T9", "name": "Dupont", "apiHost": "https://api-eu02.central.sophos.com"}],
                             "pages": {"total": 1}})
        if url.endswith("/firewall/v1/firewalls"):
            assert "X-Tenant-ID" in headers
            return Rep(200, {"items": [
                {"id": "FW1", "name": "fw-modele", "serialNumber": "X1", "model": "XGS2100", "firmwareVersion": "SFOS 22.0.0 MR-2",
                 "status": {"connected": True}, "externalIpv4Addresses": ["203.0.113.1"]},
                {"id": "FW2", "hostname": "fw-dupont", "serialNumber": "X2", "status": {"connected": False}}],
                "pages": {"total": 1}})
        if url.endswith("/export"):
            self.etat_tx["TX1"] = {"status": "finished", "result": "success", "response": {"url": "https://s3/fichier.tar"}}
            return Rep(200, {"transactionId": "TX1"})
        if url == "https://s3/fichier.tar":
            return Rep(200, contenu=b"CONTENU-TAR")
        if url.endswith("/firewall-config/firewalls/import"):
            return Rep(200, {"transactionId": "TX2", "url": "https://s3/envoi", "method": "PUT"})
        if url == "https://s3/envoi":
            self.envoye = data
            return Rep(200, {})
        if url.endswith("/upload-complete"):
            self.complet = json
            self.etat_tx["TX2"] = {"status": "finished", "result": "success",
                                   "response": {"items": [{"firewallId": "FW2", "result": "success"}]}}
            return Rep(200, {"id": "TX2", "status": "started"})
        if "/transactions/" in url:
            return Rep(200, self.etat_tx[url.rsplit("/", 1)[1]])
        return Rep(404, {"message": url})


def test_central_tenant_liste_export_import(tmp_path):
    s = FauxCentral()
    c = SophosCentral("id", "bon", session=s)
    c.connecter()
    pfs = c.pare_feux()
    assert [p.nom for p in pfs] == ["fw-modele", "fw-dupont"]
    assert pfs[0].connecte and not pfs[1].connecte and pfs[0].ip_publiques == ["203.0.113.1"]
    f = c.exporter("FW1", tmp_path / "s" / "fw.tar", ["FirewallRule"])
    assert f.read_bytes() == b"CONTENU-TAR"
    export = next(a for a in s.appels if a[1].endswith("/export"))
    assert export[3] == {"fullExport": False, "includeDependency": True, "exportEntities": ["FirewallRule"]}
    res = c.importer(f, ["FW2"], cle_maitre="SSMK")
    assert s.envoye == b"CONTENU-TAR"
    assert s.complet["firewallIds"] == ["FW2"] and s.complet["fileSizeBytes"] == 11
    assert s.complet["secureMasterKey"] == "SSMK" and len(s.complet["checksumMd5"]) == 32
    assert res["items"][0]["result"] == "success"


def test_central_partenaire_et_erreurs():
    c = SophosCentral("id", "bon", session=FauxCentral("partner"))
    c.connecter()
    clients = c.clients()
    assert clients[0].nom == "Dupont"
    c.choisir_client(clients[0])
    assert c.pare_feux()
    with pytest.raises(ErreurCentral, match="refusée"):
        SophosCentral("id", "mauvais", session=FauxCentral()).connecter()
    with pytest.raises(ErreurCentral, match="1 à 25"):
        c.importer(Path(__file__), [])
