"""Pruebas de las rutas: la raiz de un servicio es la carpeta con su servicio.toml."""
from __future__ import annotations

from pathlib import Path

import pytest

from hana_core.rutas import PathManager, raiz_proyecto


@pytest.fixture
def servicio(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.delenv("HANA_RAIZ", raising=False)
    monkeypatch.delenv("HANA_DATOS", raising=False)
    raiz = tmp_path / "hana-prueba"
    (raiz / "src" / "hana_prueba" / "interface").mkdir(parents=True)
    (raiz / "servicio.toml").write_text('[servicio]\nnombre = "prueba"\n', encoding="utf-8")
    return raiz


def test_encuentra_la_raiz_subiendo_desde_el_codigo(servicio: Path):
    assert raiz_proyecto(servicio / "src" / "hana_prueba" / "interface") == servicio


def test_encuentra_la_raiz_desde_la_carpeta_actual(servicio: Path, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(servicio)
    assert raiz_proyecto(tmp_path / "otro_lado") == servicio


def test_hana_raiz_manda(servicio: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HANA_RAIZ", str(tmp_path))
    assert raiz_proyecto(servicio) == tmp_path.resolve()


def test_sin_servicio_toml_falla_claro(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("HANA_RAIZ", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError, match="servicio.toml"):
        raiz_proyecto(tmp_path)


def test_config_y_datos_viven_en_la_carpeta_del_servicio(servicio: Path):
    r = PathManager("prueba", servicio)
    assert r.config_json == servicio / "config" / "config.json"
    assert r.servicio_toml == servicio / "servicio.toml"
    assert r.datos_raw == servicio / "datos" / "raw" / "prueba"
    assert r.paso(2, "calculo") == servicio / "datos" / "interim" / "prueba" / "02_calculo"
    assert r.registro_local == servicio / "datos" / "registro"
    assert r.outputs_logs == servicio / "outputs" / "logs"


def test_hana_datos_muda_solo_los_datos(servicio: Path, tmp_path: Path, monkeypatch):
    disco = tmp_path / "disco_grande"
    monkeypatch.setenv("HANA_DATOS", str(disco))
    r = PathManager("prueba", servicio)
    assert r.config_json == servicio / "config" / "config.json"
    assert r.datos_raw == disco.resolve() / "datos" / "raw" / "prueba"
