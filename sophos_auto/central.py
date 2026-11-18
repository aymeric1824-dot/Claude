"""Client de l'API Sophos Central (Sophos Fusion) pour les pare-feux.

Fonctions :
  - lister les pare-feux du compte (nom, n° de série, modèle, firmware, connecté ou non) ;
  - exporter la configuration d'un pare-feu (sauvegarde à distance, fichier .tar) ;
  - importer un fichier de configuration sur 1 à 25 pare-feux (ex. votre « modèle maison »).

L'export / import par Central demande SFOS 22.0 MR2 ou plus récent, un pare-feu géré par
Central et un abonnement payant (ou un contrat de support) actif.

Identifiants API : dans Sophos Central, Paramètres globaux > Identifiants API (API Credentials),
rôle « Service Principal Firewall » conseillé. On les donne au lancement ou via les variables
d'environnement SOPHOS_CENTRAL_ID et SOPHOS_CENTRAL_SECRET (jamais enregistrés par l'outil).
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from pathlib import Path

import requests

URL_JETON = "https://id.sophos.com/api/v2/oauth2/token"
URL_GLOBALE = "https://api.central.sophos.com"


class ErreurCentral(Exception):
    pass


@dataclass
class Client:
    """Un client (tenant) Sophos Central."""
    id: str
    nom: str
    hote_api: str


@dataclass
class PareFeu:
    id: str
    nom: str
    serie: str
    modele: str
    firmware: str
    connecte: bool
    ip_publiques: list[str]

    @classmethod
    def depuis(cls, d: dict) -> "PareFeu":
        statut = d.get("status") or {}
        return cls(id=d.get("id", ""), nom=d.get("name") or d.get("hostname") or "?",
                   serie=d.get("serialNumber", ""), modele=d.get("model", ""),
                   firmware=d.get("firmwareVersion", ""), connecte=bool(statut.get("connected")),
                   ip_publiques=list(d.get("externalIpv4Addresses") or []))


def firmware_compatible(version: str) -> bool | None:
    """Export / import Central : SFOS 22.0 MR2 minimum. None si la version est illisible."""
    m = re.search(r"(\d+)\.(\d+)(?:\.\d+)?(?:[ .-]*MR[- ]?(\d+))?", version or "", re.IGNORECASE)
    if not m:
        return None
    majeur, mineur, mr = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    return (majeur, mineur, mr) >= (22, 0, 2)


def _message_http(rep: requests.Response) -> str:
    try:
        d = rep.json()
        detail = d.get("message") or d.get("error") or d.get("errorCode") or str(d)
    except ValueError:
        detail = rep.text[:200]
    conseils = {401: "identifiants API refusés ou expirés",
                403: "droits insuffisants (rôle « Service Principal Firewall » conseillé) ou fonction non disponible "
                     "(firmware SFOS 22.0 MR2 minimum, abonnement actif)",
                404: "élément introuvable (le pare-feu est-il bien géré par Central ?)",
                429: "trop de requêtes, réessayez dans une minute"}
    return f"{rep.status_code} — {conseils.get(rep.status_code, 'erreur')} : {detail}"


class SophosCentral:
    def __init__(self, client_id: str, client_secret: str, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.client_id, self.client_secret = client_id, client_secret
        self.jeton = ""
        self.type_compte = ""          # tenant | partner | organization
        self.id_compte = ""
        self.hote_region = ""
        self.client: Client | None = None

    # ------------------------------------------------------------------ connexion
    def connecter(self) -> None:
        try:
            rep = self.session.request("POST", URL_JETON, data={
                "grant_type": "client_credentials", "client_id": self.client_id,
                "client_secret": self.client_secret, "scope": "token"}, timeout=30)
        except requests.exceptions.RequestException as exc:
            raise ErreurCentral(f"Sophos Central injoignable ({exc.__class__.__name__}) : vérifiez l'accès Internet.") from exc
        if rep.status_code != 200:
            raise ErreurCentral("Connexion à Sophos Central refusée : " + _message_http(rep))
        self.jeton = rep.json()["access_token"]
        moi = self._appel("GET", f"{URL_GLOBALE}/whoami/v1", entete_compte=False)
        self.type_compte, self.id_compte = moi.get("idType", ""), moi.get("id", "")
        self.hote_region = (moi.get("apiHosts") or {}).get("dataRegion", "")
        if self.type_compte == "tenant":
            self.client = Client(self.id_compte, "Mon compte", self.hote_region)

    def _entetes(self, entete_compte=True, client: Client | None = None) -> dict:
        h = {"Authorization": f"Bearer {self.jeton}", "Accept": "application/json"}
        if not entete_compte:
            return h
        c = client or self.client
        if c:
            h["X-Tenant-ID"] = c.id
        elif self.type_compte == "partner":
            h["X-Partner-ID"] = self.id_compte
        elif self.type_compte == "organization":
            h["X-Organization-ID"] = self.id_compte
        return h

    def _appel(self, methode: str, url: str, *, entete_compte=True, json=None, params=None) -> dict:
        for essai in range(4):
            try:
                rep = self.session.request(methode, url, headers=self._entetes(entete_compte), json=json,
                                           params=params, timeout=60)
            except requests.exceptions.RequestException as exc:
                if essai < 3:
                    time.sleep(2 ** essai)
                    continue
                raise ErreurCentral(f"Sophos Central injoignable ({exc.__class__.__name__}).") from exc
            if rep.status_code in (429, 502, 503, 504) and essai < 3:   # trop de requêtes / indisponible : on patiente
                attente = rep.headers.get("Retry-After") if hasattr(rep, "headers") and rep.headers else None
                time.sleep(int(attente) if attente and str(attente).isdigit() else 2 ** (essai + 1))
                continue
            break
        if rep.status_code >= 300:
            raise ErreurCentral(_message_http(rep))
        return rep.json() if rep.content else {}

    def _pages(self, url: str, entete_compte=True) -> list[dict]:
        elements, page = [], 1
        while True:
            d = self._appel("GET", url, entete_compte=entete_compte, params={"page": page, "pageSize": 100, "pageTotal": "true"})
            elements += d.get("items", [])
            total = (d.get("pages") or {}).get("total", 1)
            if page >= total:
                return elements
            page += 1

    # ------------------------------------------------------------------ clients (comptes partenaire)
    def clients(self) -> list[Client]:
        if self.type_compte == "tenant":
            return [self.client]
        chemin = "partner/v1/tenants" if self.type_compte == "partner" else "organization/v1/tenants"
        return sorted((Client(t["id"], t.get("showAs") or t.get("name", t["id"]), t.get("apiHost", ""))
                       for t in self._pages(f"{URL_GLOBALE}/{chemin}")), key=lambda c: c.nom.lower())

    def choisir_client(self, client: Client) -> None:
        self.client = client

    def _hote(self) -> str:
        if not self.client:
            raise ErreurCentral("Choisissez d'abord un client.")
        return self.client.hote_api or self.hote_region

    # ------------------------------------------------------------------ pare-feux
    def pare_feux(self) -> list[PareFeu]:
        return [PareFeu.depuis(d) for d in self._pages(f"{self._hote()}/firewall/v1/firewalls")]

    def _attendre(self, transaction: str, delai_max=900, rappel=None) -> dict:
        debut = time.monotonic()
        while True:
            d = self._appel("GET", f"{self._hote()}/firewall/v1/firewall-config/firewalls/transactions/{transaction}")
            if d.get("status") == "finished":
                if d.get("result") != "success":
                    raise ErreurCentral(f"Opération terminée en échec : {d.get('response') or d}")
                return d
            if time.monotonic() - debut > delai_max:
                raise ErreurCentral("Délai dépassé : l'opération continue peut-être dans Central, vérifiez plus tard.")
            if rappel:
                rappel(d.get("status", "en cours"))
            time.sleep(5)

    def sauvegarder_tous(self, dossier: Path, rappel=None) -> list[tuple[PareFeu, Path | str]]:
        """Exporte la configuration de tous les pare-feux connectés et compatibles."""
        resultats = []
        for pf in self.pare_feux():
            if not pf.connecte:
                resultats.append((pf, "non connecté à Central"))
                continue
            if firmware_compatible(pf.firmware) is False:
                resultats.append((pf, f"firmware {pf.firmware} trop ancien (SFOS 22.0 MR2 minimum)"))
                continue
            nom = re.sub(r"[^A-Za-z0-9_-]", "_", pf.nom)
            try:
                f = self.exporter(pf.id, dossier / f"{nom}_{pf.serie}_{time.strftime('%Y-%m-%d_%H%M%S')}.tar", rappel=rappel)
                resultats.append((pf, f))
            except ErreurCentral as exc:
                resultats.append((pf, str(exc)))
        return resultats

    def exporter(self, pare_feu_id: str, destination: Path, entites: list[str] | None = None, rappel=None) -> Path:
        corps = {"fullExport": True} if not entites else {"fullExport": False, "includeDependency": True,
                                                            "exportEntities": entites}
        tx = self._appel("POST", f"{self._hote()}/firewall/v1/firewall-config/firewalls/{pare_feu_id}/export", json=corps)
        fin = self._attendre(tx["transactionId"], rappel=rappel)
        url = (fin.get("response") or {}).get("url")
        if not url:
            raise ErreurCentral("Export terminé mais aucun lien de téléchargement fourni.")
        rep = self.session.request("GET", url, timeout=300)   # lien pré-signé : sans jeton
        if rep.status_code != 200:
            raise ErreurCentral(f"Téléchargement impossible : {rep.status_code}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(rep.content)
        return destination

    def importer(self, fichier: Path, pare_feu_ids: list[str], cle_maitre: str = "", rappel=None) -> dict:
        if not 1 <= len(pare_feu_ids) <= 25:
            raise ErreurCentral("L'import se fait sur 1 à 25 pare-feux à la fois.")
        donnees = fichier.read_bytes()
        session = self._appel("POST", f"{self._hote()}/firewall/v1/firewall-config/firewalls/import")
        rep = self.session.request(session.get("method", "PUT"), session["url"], data=donnees, timeout=300)
        if rep.status_code >= 300:
            raise ErreurCentral(f"Envoi du fichier refusé : {rep.status_code}")
        corps = {"firewallIds": pare_feu_ids, "checksumMd5": hashlib.md5(donnees).hexdigest(),
                 "fileSizeBytes": len(donnees), "performPartialImport": False}
        if cle_maitre:
            corps["secureMasterKey"] = cle_maitre
        tx = session["transactionId"]
        self._appel("POST", f"{self._hote()}/firewall/v1/firewall-config/firewalls/import/{tx}/upload-complete", json=corps)
        fin = self._attendre(tx, rappel=rappel)
        return fin.get("response") or {}
