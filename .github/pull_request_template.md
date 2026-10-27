## Qué cambia

<!-- Una o dos frases: qué hace este cambio y por qué. -->

## A quién afecta

<!-- Qué servicios usan lo que cambia. "Nadie" si es interno. -->

## Revisión

- [ ] Se avisó antes del cambio: todos los servicios dependen de este paquete.
- [ ] ¿Rompe algo para los servicios? Si sí: sube el número mayor y está explicado en `CAMBIOS.md`.
- [ ] `version` en `pyproject.toml` y `CAMBIOS.md` actualizados, si se va a publicar.
- [ ] Si cambia una regla de `arquitectura.py`: tiene su prueba y la plantilla de servicios la sigue cumpliendo.
- [ ] Este repositorio es público: nada sobre el negocio, los usuarios o la infraestructura, tampoco en los commits.
- [ ] Código, comentarios, logs y documentación en español.
