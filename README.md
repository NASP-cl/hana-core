# hana-core

Un armazón en Python para **servicios de datos geoespaciales que publican capas de mapa**.

Cada servicio es un programa pequeño con un solo trabajo: obtiene datos de una fuente,
los procesa y los deja disponibles. Además publica un **manifiesto** por cada capa que
produce: qué es, cómo se dibuja, con qué colores y dónde están sus datos. Un visualizador
web lee esos manifiestos y dibuja cada capa según su **tipo**, sin conocer los servicios
de antemano. Por eso se puede agregar un servicio, o cambiar cómo se ve una capa, sin
tocar la web.

hana-core es lo que todos esos servicios comparten: el contrato de capas, las cuatro
órdenes de línea de comandos, el registro de capas y ejecuciones, las rutas y una
revisión automática de la estructura. Un servicio solo aporta su configuración, sus
manifiestos y su pipeline.

---

## Contenido

- [La idea](#la-idea)
- [Instalar](#instalar)
- [Qué hay dentro](#qué-hay-dentro)
- [Cómo funciona una orden](#cómo-funciona-una-orden)
- [Escribir un servicio](#escribir-un-servicio)
- [El contrato de capas](#el-contrato-de-capas)
- [Rutas y variables de entorno](#rutas-y-variables-de-entorno)
- [La revisión de arquitectura](#la-revisión-de-arquitectura)
- [Versiones](#versiones)
- [Desarrollar](#desarrollar)

---

## La idea

```
fuente ──► servicio ── correr ────► datos (tabla en Postgres, o COG / PMTiles en un bucket)
                   └── registrar ─► manifiesto en la tabla `capas`
                                          │
                       visualizador web ──┘  lee los manifiestos, elige cómo dibujar
                                             según el tipo y va a buscar los datos
```

La web conoce cinco **tipos** de capa, no capas concretas:

| Tipo | Cómo se dibuja |
| --- | --- |
| `raster_tiles` | Manto de color sobre el mapa, con leyenda |
| `vector` | Polígonos o líneas con relleno |
| `puntos` | Marcadores agrupados |
| `serie` | Gráfico de tiempo |
| `panel` | Interfaz propia dentro de la web |

Un tipo que la web no conoce lo ignora sin romperse. Diez capas de tipo `raster_tiles`
no son diez desarrollos: son un dibujo y diez archivos de configuración.

---

## Instalar

En el `pyproject.toml` del servicio, **siempre con una etiqueta, nunca con una rama**:

```toml
[project]
dependencies = ["hana-core @ git+https://github.com/NASP-cl/hana-core@v0.1.0"]
```

Requiere Python 3.11 o más. Única dependencia: `pydantic`. Lo pesado (geopandas,
rioxarray…) va en cada servicio.

---

## Qué hay dentro

| Módulo | Qué hace |
| --- | --- |
| `hana_core.contrato` | El contrato de capas en Pydantic: `Manifiesto`, `Fuente`, `Meta`, los estilos, `ArchivoEstilo` (el `estilo.json`) y la versión `CONTRATO`. Es la referencia del protocolo |
| `hana_core.servicio` | `ServicioBase`, la clase de la que hereda todo servicio, y `Resultado`, lo que devuelve una ejecución |
| `hana_core.cli` | Las cuatro órdenes. El `__main__.py` de cada servicio solo llama a `main()` |
| `hana_core.registro` | Dónde se publican los manifiestos y se anotan las ejecuciones: `RegistroSupabase` (PostgREST) o `RegistroLocal` (archivos JSON) |
| `hana_core.corridas` | Envuelve cada ejecución y deja su fila en `corridas`, haya salido bien o mal |
| `hana_core.rutas` | `PathManager`: dónde está la configuración del servicio y dónde van sus datos |
| `hana_core.logs` | La configuración de logs: consola y un archivo por servicio |
| `hana_core.secretos` | Lee claves de variables de entorno. Nunca las escribe en un log |
| `hana_core.arquitectura` | Revisa que un servicio tenga la estructura y siga las reglas |

---

## Cómo funciona una orden

Todo servicio se llama igual: `python -m hana_<servicio> <orden>`.

```
python -m hana_ejemplo correr
  │
  ├─ ServicioEjemplo()             busca la carpeta con servicio.toml, arma su PathManager
  ├─ configurar_logs()             consola + outputs/logs/ejemplo.log
  └─ según la orden:
       validar    → revisa servicio.toml, config, estilo, manifiestos y secretos declarados
       registrar  → validar; si pasa, publica los manifiestos     → tabla capas
       correr     → ejecuta el pipeline y anota la ejecución      → tabla corridas
       estado     → capas publicadas y última ejecución
```

| Orden | Escribe | Código de salida |
| --- | --- | --- |
| `validar` | Nada | `0` bien, `1` con problemas |
| `registrar` | Tabla `capas`. Idempotente por `servicio.capa` | `1` si `validar` falla: nunca se publica algo que no valida |
| `correr [--prueba]` | Lo que escriba el pipeline, y una fila en `corridas` | `1` si el pipeline falla; la fila se anota igual, con estado `error` |
| `estado` | Nada | `0` |

Opciones: `--json` (salida para otro programa) y `--verboso` (log en DEBUG). El código
`2` indica que falta un archivo obligatorio o que no cumple el contrato.

**Registro local o Supabase.** Si están definidas `HANA_SUPABASE_URL` y
`HANA_SUPABASE_SECRET_KEY`, el registro escribe en Supabase; si no, en
`datos/registro/` del servicio. Las cuatro órdenes funcionan igual en los dos casos.

---

## Escribir un servicio

Un servicio tiene esta forma (la revisa `hana_core.arquitectura`):

```
hana-ejemplo/
  servicio.toml          nombre, versión, contrato, capas que publica, agenda, secretos
  pyproject.toml         depende de hana-core con versión fija
  config/config.json     parámetros del proceso
  config/estilo.json     colores, leyenda y pestaña de cada capa
  src/hana_ejemplo/
    __main__.py          entrega el servicio a hana_core.cli.main
    interface/           la clase del servicio (y el modelo de config.json)
    core/                lógica pura: no conoce hana-core ni el resto del servicio
    process/             el pipeline: solo funciones paso_N_nombre() y correr()
    utils/               ayudas propias
  tests/
```

```toml
# servicio.toml
[servicio]
nombre   = "ejemplo"
version  = "0.1.0"
contrato = 1
paquete  = "hana_ejemplo"

[publica]
capas = ["indice"]

[agenda]
cron = "17 3 * * *"

[secretos]
requiere = ["HANA_SUPABASE_SECRET_KEY"]
```

```python
# src/hana_ejemplo/interface/servicio.py
from hana_core.contrato import Fuente, Manifiesto, Meta
from hana_core.servicio import Resultado, ServicioBase
from hana_ejemplo.process import pipeline


class ServicioEjemplo(ServicioBase):
    nombre = "ejemplo"        # igual al de servicio.toml
    contrato = 1

    def manifiestos(self) -> list[Manifiesto]:
        e = self.estilos.por_capa("indice")
        return [
            Manifiesto(
                capa="indice", servicio=self.nombre, tipo="raster_tiles",
                nombre="Índice", titulo="Índice de ejemplo", descripcion="Qué muestra la capa.",
                meta=Meta(autor="Fuente", version="0.1.0", actualizado="diario", unidad="índice",
                          resolucion="10 m", rango="2020 - 2026", frecuencia="Diaria"),
                fuente=Fuente(clase="pmtiles", url="https://ejemplo.org/indice/{fecha}.pmtiles"),
                estilo=e.estilo, leyenda=e.leyenda, ui=e.ui,
            )
        ]

    def ejecutar(self, prueba: bool = False) -> Resultado:
        r = pipeline.correr(self.rutas, prueba=prueba)
        return Resultado(filas=r["filas"], mensaje="listo")
```

```python
# src/hana_ejemplo/__main__.py
import sys

from hana_core.cli import main
from hana_ejemplo.interface.servicio import ServicioEjemplo

if __name__ == "__main__":
    sys.exit(main(ServicioEjemplo()))
```

Lo demás lo pone `ServicioBase`:

| Atributo o método | Qué entrega |
| --- | --- |
| `self.rutas` | El `PathManager` del servicio |
| `self.descriptor` | `servicio.toml` leído |
| `self.config` | `config/config.json` leído |
| `self.estilos` | `config/estilo.json` validado contra el contrato; `por_capa(nombre)` da una entrada |
| `self.registro()` | El registro: Supabase o local |
| `validar()`, `registrar()`, `correr()`, `estado()` | Las órdenes; no se redefinen |

`validar()` revisa además que las capas que arma `manifiestos()` sean exactamente las que
declara `[publica] capas`, y avisa si faltan los secretos declarados.

---

## El contrato de capas

Un `Manifiesto` es la fila que el servicio publica en `capas`:

| Campo | Para qué |
| --- | --- |
| `contrato` | Versión del protocolo (hoy `1`). Si no coincide con `CONTRATO`, falla |
| `capa`, `servicio` | Identidad. Minúsculas, números y `_`. `capa_id` = `servicio.capa` |
| `tipo` | Uno de los cinco tipos: qué dibujo usa la web |
| `nombre`, `titulo`, `descripcion` | Lo que lee la persona que mira el mapa |
| `meta` | Autor, versión, actualizado, unidad, resolución, rango, frecuencia: la ficha de la capa |
| `fuente` | Dónde están los datos: `pmtiles` o `cog` con `url`, `tabla` con `tabla` y `columnas`, o `ninguna` |
| `estilo` | `continua` (`dominio` y `paleta` del mismo largo, dominio creciente, colores hex) o `clases` (`{v, color}`) |
| `leyenda` | Título, unidad, decimales |
| `ui` | `grupo` (la pestaña), `orden`, `visible`, `zoom_min` |
| `roles` | Qué roles de usuario la ven (ver `ROLES` en `contrato.py`) |
| `params` | Parámetros propios que la web necesita, para ajustarlos sin desplegar la web |

Todos los modelos usan `extra="forbid"`: un campo mal escrito falla en `validar`, no en
producción.

El `estilo.json` de un servicio tiene la parte del manifiesto que se edita a mano:

```json
{
  "contrato": 1,
  "capas": [
    {
      "capa": "indice",
      "estilo": { "escala": "continua", "dominio": [0, 0.5, 1],
                  "paleta": ["#C9952F", "#92CA90", "#004651"], "opacidad": 0.85 },
      "leyenda": { "titulo": "Índice", "unidad": "índice", "decimales": 2 },
      "ui": { "grupo": "General", "orden": 10, "visible": true }
    }
  ]
}
```

---

## Rutas y variables de entorno

La **raíz del servicio** es la carpeta que tiene su `servicio.toml`. `ServicioBase` la
busca subiendo desde el archivo de la clase del servicio y, si no la encuentra, desde la
carpeta actual.

| Propiedad de `PathManager` | Ruta |
| --- | --- |
| `config_json`, `estilo_json`, `servicio_toml` | `<raiz>/config/…`, `<raiz>/servicio.toml` |
| `datos_raw`, `datos_interim`, `datos_processed` | `<base>/datos/{raw,interim,processed}/<servicio>/` |
| `paso(n, nombre)` | `<base>/datos/interim/<servicio>/NN_nombre/`: la salida de un paso del pipeline |
| `registro_local` | `<base>/datos/registro/` |
| `outputs_logs`, `outputs_tables`, `outputs_maps` | `<base>/outputs/…` |

`<base>` es la raíz del servicio, salvo que `HANA_DATOS` diga otra cosa.

| Variable | Para qué |
| --- | --- |
| `HANA_SUPABASE_URL`, `HANA_SUPABASE_SECRET_KEY` | Escribir en Supabase. Sin ellas, registro local |
| `HANA_DATOS` | Llevar `datos/` y `outputs/` a otro disco sin mover el servicio |
| `HANA_RAIZ` | Forzar la carpeta del servicio. Casi nunca hace falta |

Los pasos del pipeline se comunican por disco: cada uno escribe su resultado y el
siguiente lo lee de ahí. Si falla el paso 4, se corrige y se reanuda desde el 4.

---

## La revisión de arquitectura

```bash
python -m hana_core.arquitectura                 # el servicio de la carpeta actual
python -m hana_core.arquitectura ruta/a/servicio # uno o varios
```

Lee el código sin ejecutarlo y comprueba:

- los archivos obligatorios del servicio y `tests/test_*.py`;
- `servicio.toml`: paquete, contrato, capas, cron de 5 campos, secretos con prefijo `HANA_`;
- que `estilo.json` y `servicio.toml` declaren las mismas capas;
- `pyproject.toml`: nombre `hana-<servicio>` y dependencia de `hana-core`;
- que `__main__.py` entregue el servicio a `hana_core.cli.main`;
- `core/` no importa `hana_core` ni el resto del servicio, no usa `PathManager` ni `*args`/`**kwargs`;
- `process/` no importa la clase del servicio y solo tiene `paso_N_nombre()` y `correr()`;
- un servicio no importa a otro;
- logs con f-string, sin `basicConfig` ni handlers, sin imports relativos fuera de `__init__.py`.

Devuelve `0` sin problemas y `1` con la lista. Pensada para integración continua,
pre-commit y hooks de editor.

---

## Versiones

Cada servicio fija la versión que usa, así que un cambio aquí no le llega a nadie hasta
que ese servicio sube su etiqueta. Los cambios de cada versión están en
[`CAMBIOS.md`](CAMBIOS.md).

| Tipo de cambio | Versión |
| --- | --- |
| Arreglo sin cambio de comportamiento | `v0.1.0` → `v0.1.1` |
| Algo nuevo que no rompe (un campo opcional, una regla nueva de arquitectura) | `v0.1.0` → `v0.2.0` |
| Algo que rompe (el contrato, una firma de `ServicioBase`, una ruta) | Número mayor; si cambia el protocolo de capas, también `CONTRATO` |

Para publicar: subir `version` en `pyproject.toml`, anotar en `CAMBIOS.md` y crear la
etiqueta `vX.Y.Z` sobre `main`.

---

## Desarrollar

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e . -r requirements-dev.txt
pre-commit install --hook-type pre-commit --hook-type pre-push

ruff check .
python -m pytest
```

Para probar un cambio contra un servicio sin publicar: dentro del servicio,
`pip install -e ../hana-core`.

Las reglas de trabajo están en [`CLAUDE.md`](CLAUDE.md).
