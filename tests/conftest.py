import pytest


@pytest.fixture(autouse=True)
def _poste_isole():
    """Chaque test retrouve l'emplacement du fichier du poste dans son propre dossier."""
    from sophos_auto import poste
    poste._FICHIER = None
    yield
    poste._FICHIER = None


@pytest.fixture(autouse=True)
def _assistant_sans_preparation():
    """Les scénarios d'assistant écrits avant la version 5.5 ne passent pas par « Avant de commencer »
    (mode express, questionnaire, analyse du réseau) : ces étapes ont leurs propres tests."""
    from sophos_auto import assistant, deployer
    deployer.PROPOSER_VERIFICATION = False
    assistant.PREPARATION, assistant.EXPRESS, assistant.ANALYSE = False, False, None
    assistant.PREREMPLI.clear()
    assistant.REPONSES.clear()
    yield
    assistant.PREPARATION, assistant.EXPRESS, assistant.ANALYSE = True, False, None
    assistant.PREREMPLI.clear()
