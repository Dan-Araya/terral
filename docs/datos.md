# Datos, licencia y reproducibilidad

Las observaciones pertenecen a sus fuentes. El proyecto las obtiene de [CEAZAMet](https://www.ceazamet.cl/), red del Centro de Estudios Avanzados en Zonas Áridas. La licencia MIT del repositorio no cambia las condiciones de uso de CEAZA ni las del artículo científico citado.

## Incluido en GitHub

- Código original de adquisición, normalización, investigación y aplicación.
- Configuraciones y protocolos seleccionados de investigación.
- Seis modelos congelados en JSON, con su manifiesto SHA-256.
- Métricas agregadas de evaluación y documentación.
- Generador de entradas sintéticas y pruebas públicas.

## Conservado fuera de GitHub

Originales XLS, cuerpos y cabeceras HTTP, tablas de observaciones y predicciones individuales, bases SQLite, capturas operativas, respaldos, estados de descarga, evidencias privadas, credenciales, archivos de entorno, PDF de terceros y el archivo completo de investigación.

Publicar el código no ejecuta adquisiciones ni abre el período reservado. La demo inventa sus entradas y usa un reloj simulado de 2023. No consulta observaciones de ningún año.

## Qué se puede reproducir

**Desde un clon limpio:** el panel, el motor congelado, la construcción de predictores sobre entradas sintéticas, el registro de versiones y los escenarios operativos cubiertos por las pruebas públicas. La integridad del modelo se verifica al cargarlo y el script de publicación verifica las rutas y hashes congelados.

**Con el archivo de investigación adicional:** las evaluaciones y auditorías históricas completas. Los scripts conservan las rutas relativas del trabajo original y algunos manifiestos esperan también los resultados previos. Sus comandos no constituyen una reproducción completa con los archivos de este repositorio solamente. No se han sustituido datos reales por datos sintéticos dentro de esos experimentos.

Las pruebas y CI públicas no reemplazan las auditorías históricas. El número de comprobaciones informado en cierres anteriores corresponde a sus respectivos archivos y versiones, no a una suite descargable completa desde este repositorio.

## Antes de añadir archivos

El repositorio utiliza una lista explícita de publicación en `publicacion.json` y reglas de exclusión generadas a partir de ella. Un archivo nuevo no se incorpora automáticamente. Revisa su contenido, añádelo a `publicacion.json`, ejecuta `python3 scripts/verificar_publicacion.py --generar-ignore`, y luego prepara el commit. No uses `git add -f` para saltar esta revisión.
