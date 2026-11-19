"""État de santé de l'outil, vérifié au démarrage : tout ce qui pourrait le faire échouer en intervention.

Chaque point est vert ou rouge, avec la correction à faire. Rien n'est modifié.
"""
from __future__ import annotations

import importlib
import os
import shutil
import tempfile
from pathlib import Path

COMPOSANTS = [("openpyxl", "fichiers Excel"), ("requests", "connexion au pare-feu"), ("xmltodict", "connexion au pare-feu"),
              ("pykeepass", "coffre KeePass")]


def verifier(internet: bool = True) -> list[tuple[bool, str, str]]:
    """[(bon ?, point vérifié, quoi faire si ce n'est pas bon)]"""
    res: list[tuple[bool, str, str]] = []
    # Dossier de travail : peut-on y écrire ?
    try:
        with tempfile.NamedTemporaryFile(dir=".", prefix=".essai_", delete=True):
            pass
        res.append((True, f"Dossier de travail accessible ({Path.cwd()})", ""))
    except OSError:
        res.append((False, "Impossible d'écrire dans le dossier de travail",
                    "Rangez le programme dans un dossier à vous (ex. Documents\\SophosXGS), pas dans Téléchargements "
                    "ni sur une clé protégée en écriture."))
    # Dossier partagé de l'équipe
    try:
        from .poste import charger
        partage = charger().get("dossier_partage") or ""
    except Exception:
        partage = ""
    if partage:
        if Path(partage).is_dir():
            res.append((True, "Dossier partagé de l'équipe accessible", ""))
        else:
            res.append((False, f"Dossier partagé inaccessible : {partage}",
                        "Vérifiez la connexion au réseau de l'entreprise ou à OneDrive. En attendant, l'outil travaille "
                        "en local sur ce PC."))
    # Composants
    manquants = []
    for module, usage in COMPOSANTS:
        try:
            importlib.import_module(module)
        except ImportError:
            manquants.append(f"{module} ({usage})")
    res.append((not manquants, "Composants du programme" + (f" manquants : {', '.join(manquants)}" if manquants else " présents"),
                "Relancez SophosXGS.bat (il installe les composants), ou utilisez SophosXGS.exe." if manquants else ""))
    # PDF
    from .pdf import navigateur
    res.append((bool(navigateur()), "Création des PDF (Microsoft Edge ou Google Chrome)" if navigateur()
                else "Pas de navigateur pour créer les PDF", "" if navigateur() else
                "Installez Microsoft Edge ou Google Chrome. Sans eux, les rapports restent en page web (imprimables)."))
    # Place sur le disque
    try:
        libre = shutil.disk_usage(".").free // (1024 * 1024)
        res.append((libre > 300, f"Place libre sur le disque : {libre} Mo",
                    "" if libre > 300 else "Faites de la place : il faut au moins 300 Mo pour les rapports et sauvegardes."))
    except OSError:
        pass
    # Version
    if internet:
        from . import __version__
        from .mise_a_jour import verifier as nouvelle_version
        info = nouvelle_version(delai=3)
        if info:
            res.append((False, f"Version {__version__} : la version {info['version']} est disponible",
                        "Action « Mise à jour » (ou redémarrez SophosXGS.exe : il se met à jour tout seul)."))
        else:
            res.append((True, f"Version {__version__} à jour (ou vérification impossible sans Internet)", ""))
    if os.name != "nt":
        res.append((False, "Ce PC n'est pas sous Windows", "Certaines fonctions (réglage du PC, tâches planifiées) "
                                                         "n'existent que sous Windows."))
    return res
