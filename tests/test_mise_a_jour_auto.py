"""Mise à jour automatique : vérification d'intégrité, choix du bon programme, déclenchement au démarrage."""
import hashlib
import sys
from pathlib import PureWindowsPath

import pytest

from sophos_auto import mise_a_jour as maj


class Flux:
    def __init__(self, contenu):
        self.contenu = contenu

    def raise_for_status(self):
        pass

    def iter_content(self, n):
        return [self.contenu]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _info(contenu=b"NOUVEAU", **autres):
    d = {"version": "99.0", "url": "https://x/e", "sha256": hashlib.sha256(contenu).hexdigest(), "taille": len(contenu)}
    d.update(autres)
    return d


def test_telechargement_verifie(tmp_path, monkeypatch):
    monkeypatch.setattr(maj.requests, "get", lambda *a, **k: Flux(b"NOUVEAU"))
    f = maj.telecharger(_info(), tmp_path / "n.exe")
    assert f.read_bytes() == b"NOUVEAU"


@pytest.mark.parametrize("info, message", [
    (_info(sha256="0" * 64), "empreinte"),
    (_info(taille=999), "incomplet"),
    (_info(url=None), "ne contient pas"),
])
def test_telechargement_refuse_et_nettoye(tmp_path, monkeypatch, info, message):
    monkeypatch.setattr(maj.requests, "get", lambda *a, **k: Flux(b"NOUVEAU"))
    with pytest.raises(maj.ErreurMiseAJour, match=message):
        maj.telecharger(info, tmp_path / "n.exe")
    assert not (tmp_path / "n.exe").exists()      # rien de douteux ne reste sur le disque


def test_le_programme_console_reste_le_programme_console(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Outils\SophosXGS-console.exe")
    assert maj.programme_actuel() == "SophosXGS-console.exe"

    class R:
        status_code = 200

        def json(self):
            return {"tag_name": "v99.0", "assets": [
                {"name": "SophosXGS.exe", "browser_download_url": "https://x/fenetre", "size": 1, "digest": "sha256:aa"},
                {"name": "SophosXGS-console.exe", "browser_download_url": "https://x/console", "size": 2,
                 "digest": "sha256:BB"}]}
    monkeypatch.setattr(maj.requests, "get", lambda *a, **k: R())
    info = maj.verifier()
    assert (info["url"], info["sha256"], info["taille"]) == ("https://x/console", "bb", 2)


def test_script_garde_l_ancienne_version():
    exe = PureWindowsPath(r"C:\A B\SophosXGS.exe")
    script = maj.script_remplacement(exe.with_name("SophosXGS.nouveau.exe"), exe)
    assert r'copy /y "C:\A B\SophosXGS.exe" "C:\A B\SophosXGS.ancien.exe"' in script
    assert script.index("copy") < script.index("move") < script.index("start")


def test_demarrage_installe_tout_seul(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    messages = []
    monkeypatch.setattr(maj, "verifier", lambda delai=4: _info())
    monkeypatch.setattr(maj, "installable", lambda: True)
    monkeypatch.setattr(maj, "installer", lambda info: "RELANCE")
    assert maj.mise_a_jour_automatique(messages.append) is True
    assert "redémarre" in messages[-1]


def test_demarrage_sans_installation_automatique(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from sophos_auto.parametres import enregistrer
    appels = []
    monkeypatch.setattr(maj, "verifier", lambda delai=4: _info())
    monkeypatch.setattr(maj, "installable", lambda: True)
    monkeypatch.setattr(maj, "installer", lambda info: appels.append(info) or "RELANCE")
    enregistrer({"mise_a_jour_auto": False})
    messages = []
    assert maj.mise_a_jour_automatique(messages.append) is False
    assert not appels and "disponible" in messages[0]


def test_demarrage_avec_python_ou_hors_connexion(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(maj, "verifier", lambda delai=4: None)     # rien de neuf, ou pas d'Internet
    assert maj.mise_a_jour_automatique(print) is False
    monkeypatch.setattr(maj, "verifier", lambda delai=4: _info())
    monkeypatch.setattr(maj, "installable", lambda: False)          # lancé avec Python
    messages = []
    assert maj.mise_a_jour_automatique(messages.append) is False and "disponible" in messages[0]


def test_echec_d_installation_n_empeche_pas_de_travailler(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(maj, "verifier", lambda delai=4: _info())
    monkeypatch.setattr(maj, "installable", lambda: True)
    monkeypatch.setattr(maj, "installer", lambda info: "Mise à jour non installée : empreinte.")
    messages = []
    assert maj.mise_a_jour_automatique(messages.append) is False
    assert "non installée" in messages[-1]
