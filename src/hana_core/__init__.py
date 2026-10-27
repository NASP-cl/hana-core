"""Contrato de capas, registro y verbos comunes de HANA."""

from hana_core.contrato import CONTRATO, Manifiesto  # noqa: F401
from hana_core.servicio import Resultado, ServicioBase  # noqa: F401

__all__ = ["CONTRATO", "Manifiesto", "Resultado", "ServicioBase"]
