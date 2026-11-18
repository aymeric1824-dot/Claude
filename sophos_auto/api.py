"""Client minimal pour l'API XML des Sophos Firewall (XGS / SFOS).

L'API répond sur https://<ip>:<port>/webconsole/APIController.
Chaque requête est un document XML <Request> qui contient l'identifiant
de connexion puis une opération (Get, Set, Remove).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

import requests
import urllib3
import xmltodict


class ErreurAPI(Exception):
    """Le pare-feu a refusé la requête."""


class ErreurConnexion(ErreurAPI):
    """Impossible de se connecter (identifiants, API désactivée, IP non autorisée...)."""


@dataclass
class Resultat:
    ok: bool
    code: str
    message: str
    deja_existant: bool = False


_SECRETS_XML = re.compile(r"<(Password|PresharedKey|Key|EncryptionPassword|secureMasterKey|PasswordHash)>(.*?)</\1>",
                          re.DOTALL)


def masquer(xml: str) -> str:
    """Remplace le contenu des balises de mots de passe par ********."""
    return _SECRETS_XML.sub(lambda m: f"<{m.group(1)}>********</{m.group(1)}>", xml)


def to_xml(objet: dict) -> str:
    """Transforme un dictionnaire en XML (les caractères spéciaux sont échappés)."""
    xml = xmltodict.unparse(objet, full_document=False, pretty=True)
    return xml


class SophosAPI:
    def __init__(self, hote: str, utilisateur: str, mot_de_passe: str,
                 port: int = 4444, verifier_certificat: bool = False, timeout: int = 30):
        self.url = f"https://{hote}:{port}/webconsole/APIController"
        self.utilisateur = utilisateur
        self.mot_de_passe = mot_de_passe
        self.verifier_certificat = verifier_certificat
        self.timeout = timeout
        self.tentatives = 3          # nouvelles tentatives en cas de coupure réseau passagère
        self.journal = None          # fonction(texte) : journal technique (mots de passe masqués)
        if not verifier_certificat:
            # Les XGS sortent d'usine avec un certificat auto-signé.
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # ------------------------------------------------------------------ bas niveau
    def _requete(self, corps: str) -> dict:
        login = to_xml({"Login": {"Username": self.utilisateur, "Password": self.mot_de_passe}})
        payload = f"<Request>{login}{corps}</Request>"
        if self.journal:
            self.journal(">>> " + masquer(corps))
        for essai in range(1, max(1, self.tentatives) + 1):
            try:
                rep = requests.post(
                    self.url,
                    data={"reqxml": payload},
                    headers={"Accept": "application/xml"},
                    verify=self.verifier_certificat,
                    timeout=self.timeout,
                )
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                if essai < self.tentatives:
                    time.sleep(2 * essai)
                    continue
                raise ErreurConnexion(
                    f"Pare-feu injoignable sur {self.url} ({exc.__class__.__name__}). "
                    "Vérifiez le câble, l'adresse IP et que le port 4444 est accessible."
                ) from exc
            except requests.exceptions.RequestException as exc:
                raise ErreurConnexion(f"Erreur de communication avec {self.url} ({exc.__class__.__name__}).") from exc
        if self.journal:
            self.journal("<<< " + masquer(rep.text[:4000]))

        try:
            reponse = xmltodict.parse(rep.content.decode("utf-8", errors="replace"))["Response"]
        except Exception as exc:  # réponse non XML
            raise ErreurAPI(f"Réponse inattendue du pare-feu : {rep.text[:300]}") from exc

        statut = reponse.get("Status") if isinstance(reponse, dict) else None
        if isinstance(statut, dict):
            code = statut.get("@code", "")
            texte = statut.get("#text", "")
            if code == "532":
                raise ErreurConnexion("L'API n'est pas activée sur le pare-feu (Sauvegarde et firmware > API).")
            if code == "534":
                raise ErreurConnexion("L'adresse IP de ce PC n'est pas autorisée à utiliser l'API "
                                      "(Sauvegarde et firmware > API > Adresses IP autorisées).")
            if not code.startswith("2"):
                raise ErreurAPI(f"{code} : {texte}")

        login_rep = reponse.get("Login") if isinstance(reponse, dict) else None
        if isinstance(login_rep, dict) and "Failure" in str(login_rep.get("status", "")):
            raise ErreurConnexion("Identifiant ou mot de passe administrateur incorrect.")
        return reponse

    # ------------------------------------------------------------------ opérations
    def tester_connexion(self) -> None:
        self._requete("")

    def lire(self, balise: str, nom: str | None = None) -> dict | list | None:
        """Lit un type d'objet (ex. 'IPHost'). Renvoie None s'il n'y en a pas."""
        if nom:
            filtre = to_xml({"Filter": {"key": {"@name": "Name", "@criteria": "=", "#text": nom}}})
            corps = f"<Get><{balise}>{filtre}</{balise}></Get>"
        else:
            corps = f"<Get><{balise}></{balise}></Get>"
        reponse = self._requete(corps)
        contenu = reponse.get(balise)
        if isinstance(contenu, dict) and "Status" in contenu and len(contenu) <= 2:
            return None  # "Number of records Zero."
        return contenu

    def noms(self, balise: str, champ: str = "Name") -> set[str]:
        """Noms des objets existants d'un type (ensemble vide si aucun ou type inconnu)."""
        try:
            contenu = self.lire(balise)
        except ErreurConnexion:
            raise
        except ErreurAPI:
            return set()
        if contenu is None:
            return set()
        elements = contenu if isinstance(contenu, list) else [contenu]
        return {str(e.get(champ)) for e in elements if isinstance(e, dict) and e.get(champ)}

    def ecrire(self, balise: str, contenu: dict, operation: str = "add") -> Resultat:
        """Envoie un objet avec Set operation="add" ou "update"."""
        corps = f'<Set operation="{operation}">{to_xml({balise: contenu})}</Set>'
        reponse = self._requete(corps)
        return analyser_statut(reponse, balise)

    def supprimer(self, balise: str, cle: dict) -> Resultat:
        """Supprime un objet. cle = champs qui l'identifient, ex. {"Name": "SRV-01"}."""
        reponse = self._requete(f"<Remove>{to_xml({balise: cle})}</Remove>")
        return analyser_statut(reponse, balise)

    def ecrire_ou_mettre_a_jour(self, balise: str, contenu: dict) -> tuple[Resultat, str]:
        """Crée l'objet ; s'il existe déjà, le met à jour. Renvoie (résultat, 'créé'|'mis à jour')."""
        res = self.ecrire(balise, contenu, "add")
        if res.ok:
            return res, "créé"
        if res.deja_existant:
            res2 = self.ecrire(balise, contenu, "update")
            return res2, "mis à jour"
        return res, "erreur"


_DEJA = re.compile(r"already exists|same name", re.IGNORECASE)


def analyser_statut(reponse: dict, balise: str) -> Resultat:
    bloc = reponse.get(balise)
    if not (isinstance(bloc, (dict, list))):
        # certaines réponses portent un autre nom de balise : on prend le premier bloc avec un statut
        bloc = next((v for k, v in reponse.items() if k not in ("Login", "@APIVersion", "@IPS_CAT_VER")
                     and isinstance(v, (dict, list))), None)
    if isinstance(bloc, list):
        bloc = bloc[0]
    if not isinstance(bloc, dict) or "Status" not in bloc:
        return Resultat(False, "?", f"Réponse sans statut pour {balise} : {reponse}")
    statut = bloc["Status"]
    if isinstance(statut, dict):
        code, texte = statut.get("@code", "?"), statut.get("#text", "")
    else:
        code, texte = "?", str(statut)
    ok = code.startswith("2")
    return Resultat(ok, code, texte, deja_existant=(not ok and (code == "502" or bool(_DEJA.search(texte)))))
