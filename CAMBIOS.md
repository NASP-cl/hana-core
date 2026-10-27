# Cambios

## v0.1.0 · 2026-10-27

Primera versión publicada.

- Contrato de capas 1: manifiesto, fuente, estilos continuo y por clases, archivo de estilo.
- `ServicioBase` y los cuatro verbos: `validar`, `registrar`, `correr`, `estado`.
- Registro en Supabase, o en archivos locales cuando no hay credenciales, y bitácora de corridas.
- `PathManager`: la raíz de un servicio es la carpeta que tiene su `servicio.toml`. `HANA_DATOS` lleva `datos/` y `outputs/` a otro disco.
- `hana_core.arquitectura`: la revisión automática de las reglas de un servicio (`python -m hana_core.arquitectura`).
