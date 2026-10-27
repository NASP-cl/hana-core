# hana-core · reglas del repositorio

El paquete común de todos los servicios de HANA. Este repositorio es **público**: aquí
no va nada sobre qué hace la plataforma, para quién, ni dónde corre. Ejemplos, pruebas y
documentación usan casos genéricos.

## Lo que no se negocia

- **Español** en código, comentarios, docstrings, logs, commits y documentación. El
  inglés solo aparece dentro de nombres de campos y de librerías.
- **Nada aquí se cambia sin aviso explícito.** Todos los servicios dependen de este
  paquete. Antes de tocar algo, se dice qué cambia y qué servicios se ven afectados.
- **Secretos solo en variables de entorno.** Nunca en un archivo, un log ni un mensaje de error.
- **Nada del negocio en un repositorio público:** ni el dominio de la plataforma, ni sus
  usuarios, ni nombres de servicios reales, ni detalles de la infraestructura. Tampoco en
  los mensajes de commit.
- `contrato.py` es la implementación de referencia del protocolo de capas. Si la
  documentación y este archivo no coinciden, manda el archivo.

## Versiones

Los servicios fijan una versión (`@v0.1.0`). Cada cambio que se publica:

1. sube `version` en `pyproject.toml`;
2. se anota en `CAMBIOS.md`;
3. se publica con la etiqueta `vX.Y.Z`.

Un cambio que rompe (contrato, firmas de `ServicioBase`, rutas) sube el número mayor
y, si cambia el protocolo de capas, también `CONTRATO`.

## La revisión de arquitectura

`hana_core/arquitectura.py` comprueba las reglas que todo servicio debe cumplir. Una
regla nueva lleva su prueba en `tests/test_arquitectura.py`, que arma un servicio mínimo
correcto y lo rompe a propósito. La plantilla de servicios del equipo tiene que seguir
pasando la revisión: al cambiar una regla, se revisa también la plantilla.

## Python

- `logger = logging.getLogger(__name__)` por módulo; la configuración solo en `logs.py`.
- f-strings en logs y en pantalla, nunca formato con `%`.
- Imports absolutos; relativos solo en `__init__.py`.
- Tipos anotados en firmas públicas; docstrings en español.
- Dependencias mínimas: hoy solo `pydantic`. Lo pesado va en cada servicio.

## Antes de dar algo por terminado

```
ruff check .
python -m pytest
```
