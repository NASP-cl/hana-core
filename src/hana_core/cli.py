"""Los cuatro verbos. Este es el estandar de despliegue.

    python -m hana_<servicio> validar               revisa config y estilo. No escribe
    python -m hana_<servicio> registrar             publica el manifiesto. Idempotente
    python -m hana_<servicio> correr [--prueba]     ejecuta el pipeline
    python -m hana_<servicio> estado                ultima corrida y capas publicadas

El programador de tareas solo llama a estos verbos; no sabe nada de cada servicio.
Por eso agregar un servicio es dejar la carpeta, validar, registrar y agendar correr.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Sequence

from hana_core.logs import configurar_logs
from hana_core.servicio import ErrorDeContrato, ServicioBase

logger = logging.getLogger(__name__)


def construir_parser(nombre: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=f"python -m hana_{nombre}",
        description=f"Servicio {nombre} de HANA.",
    )
    p.add_argument(
        "verbo",
        choices=["validar", "registrar", "correr", "estado"],
        help="validar: revisa y no escribe | registrar: publica el manifiesto | "
        "correr: ejecuta el pipeline | estado: ultima corrida",
    )
    p.add_argument("--prueba", action="store_true", help="con `correr`: muestra que haria, sin escribir")
    p.add_argument("--json", action="store_true", help="salida en JSON, para el programador de tareas")
    p.add_argument("--verboso", action="store_true", help="log de nivel DEBUG")
    return p


def main(servicio: ServicioBase, argv: Sequence[str] | None = None) -> int:
    args = construir_parser(servicio.nombre).parse_args(argv)
    configurar_logs(
        servicio.nombre,
        carpeta=servicio.rutas.outputs_logs,
        nivel=logging.DEBUG if args.verboso else logging.INFO,
    )

    def salida(obj: object, texto: str) -> None:
        print(json.dumps(obj, ensure_ascii=False, indent=2, default=str) if args.json else texto)

    try:
        if args.verbo == "validar":
            problemas = servicio.validar()
            if problemas:
                salida(
                    {"servicio": servicio.nombre, "ok": False, "problemas": problemas},
                    "\n".join(f"  - {p}" for p in problemas),
                )
                if not args.json:
                    print(f"\n{servicio.nombre}: {len(problemas)} problema(s).", file=sys.stderr)
                return 1
            ms = servicio.manifiestos()
            salida(
                {"servicio": servicio.nombre, "ok": True, "capas": [m.capa for m in ms]},
                f"{servicio.nombre}: contrato {servicio.contrato} correcto. "
                f"{len(ms)} capa(s): {', '.join(m.capa for m in ms)}",
            )
            return 0

        if args.verbo == "registrar":
            problemas = servicio.validar()
            if problemas:
                # Nunca se publica algo que no valida: un estilo malo rompe el mapa de todos.
                print("No se registra: primero corrige lo que indica `validar`.", file=sys.stderr)
                for p in problemas:
                    print(f"  - {p}", file=sys.stderr)
                return 1
            n = servicio.registrar()
            salida({"servicio": servicio.nombre, "registradas": n}, f"{n} capa(s) registrada(s).")
            return 0

        if args.verbo == "correr":
            res = servicio.correr(prueba=args.prueba)
            salida(
                {"servicio": servicio.nombre, "filas": res.filas, "mensaje": res.mensaje,
                 "archivos": res.archivos, "prueba": args.prueba},
                (f"(prueba) {res.mensaje}" if args.prueba else res.mensaje)
                + (f"\n{res.filas} fila(s)." if res.filas else ""),
            )
            return 0

        est = servicio.estado()
        if args.json:
            salida(est, "")
        else:
            u = est["ultima_corrida"]
            print(f"{est['servicio']}  contrato {est['contrato']}")
            print(f"  capas publicadas: {', '.join(est['capas']) or 'ninguna'}")
            print(
                "  ultima corrida:   "
                + (f"{u['estado']} el {u['fin']} ({u['filas']} filas)" if u else "nunca")
            )
        return 0

    except ErrorDeContrato as e:
        print(f"Contrato: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrumpido.", file=sys.stderr)
        return 130
    except Exception as e:
        logger.error(f"{args.verbo} fallo: {e}")
        logger.debug("detalle", exc_info=True)
        return 1
