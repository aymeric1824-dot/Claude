import pytest


@pytest.fixture(autouse=True)
def _poste_isole():
    """Chaque test retrouve l'emplacement du fichier du poste dans son propre dossier."""
    from sophos_auto import poste
    poste._FICHIER = None
    yield
    poste._FICHIER = None
