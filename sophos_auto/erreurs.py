"""Erreurs du pare-feu expliquées simplement.

Le pare-feu répond en anglais, avec un code. On traduit les cas connus en une phrase claire et une action.
Si le cas n'est pas connu, on le dit, et on propose de demander de l'aide (dossier d'assistance).
"""
from __future__ import annotations

import re

CAS = [
    (r"already exists|same name", "Un élément portant ce nom existe déjà sur le pare-feu.",
     "Rien à faire : l'outil le met à jour. Si l'erreur reste, renommez l'élément dans le fichier Excel."),
    (r"in use|is used|referenced|reference", "Cet élément est utilisé ailleurs sur le pare-feu (règle, groupe, VPN...).",
     "Retirez-le d'abord de là où il est utilisé, ou gardez-le tel quel."),
    (r"does not exist|not found|no such|introuvable", "Le fichier utilise un élément qui n'existe pas sur le pare-feu.",
     "Vérifiez l'orthographe du nom dans le fichier Excel (colonne indiquée), ou créez l'élément manquant."),
    (r"licen[cs]e|subscription|not licensed", "Cette fonction demande une licence que ce pare-feu n'a pas.",
     "Vérifiez les licences dans Sophos Central (Licences), ou désactivez cette ligne dans le fichier."),
    (r"authentication|login|credential|password", "Identifiant ou mot de passe refusé.",
     "Vérifiez le compte administrateur du pare-feu (celui de sa page web)."),
    (r"time ?out|timed out|unreachable|injoignable|connection", "Le pare-feu ne répond plus.",
     "Vérifiez le câble et l'adresse du pare-feu (voyant de l'accueil), puis relancez : ce qui est déjà fait ne "
     "sera pas refait en double."),
    (r"invalid|not valid|wrong|incorrect|format", "Une valeur du fichier n'est pas acceptée par ce pare-feu.",
     "Vérifiez la ligne correspondante dans le fichier Excel (adresse, masque, nom...). Certaines options n'existent "
     "pas sur toutes les versions du pare-feu."),
    (r"could not be performed|operation failed|failed", "Le pare-feu a refusé cette opération.",
     "Souvent une option absente de cette version du pare-feu. Mettez le firmware à jour, ou faites ce réglage à la "
     "main dans la page web du pare-feu."),
]
CODES = {
    "502": CAS[0][1:], "404": CAS[2][1:], "532": ("L'API n'est pas activée sur le pare-feu.",
                                              "Sauvegarde et firmware > API > cocher « Configuration de l'API »."),
    "534": ("L'adresse de ce PC n'est pas autorisée à utiliser l'API.",
            "Sauvegarde et firmware > API > Adresses IP autorisées : ajoutez l'adresse de votre PC (voyant de l'accueil)."),
}


def expliquer(code: str = "", message: str = "") -> tuple[str, str]:
    """(ce qui se passe, quoi faire)."""
    code = str(code or "").strip()
    for motif, quoi, faire in CAS:
        if re.search(motif, message or "", re.IGNORECASE):
            return quoi, faire
    if code in CODES:
        return CODES[code]
    return ("Erreur inconnue de l'outil.",
            "Cliquez sur « Demander de l'aide » en bas de la fenêtre : un dossier avec tout le nécessaire est préparé.")


def phrase(code: str = "", message: str = "") -> str:
    quoi, faire = expliquer(code, message)
    return f"{quoi} {faire}"
