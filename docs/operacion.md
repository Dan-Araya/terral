# Servicio con datos reales

El comando de demo del README funciona sin adquisición. Esta página describe el servicio real y sus dependencias; no instala ni activa tareas automáticamente.

## Dependencias

Linux, Python 3.11 o posterior, SQLite, `curl` y las dependencias fijadas en `aplicacion_terral/g4/requirements.txt`:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r aplicacion_terral/g4/requirements.txt
```

La ruta de datos se establece mediante `TERRAL_DATA`, fuera del checkout y con acceso restringido al usuario del servicio. Ejemplo de servidor de aplicación, para una instalación que ya tiene su almacén:

```bash
export TERRAL_DATA=/var/lib/terral
gunicorn --bind 127.0.0.1:8080 --workers 2 aplicacion_terral.g4.wsgi:application
```

En producción, un proxy Caddy termina HTTPS. Gunicorn escucha en loopback. Un temporizador systemd independiente invoca `python -m aplicacion_terral.g4.ciclo` una vez por hora, al minuto 15 UTC. Ese comando **sí realiza solicitudes a CEAZAMet**; no es necesario para probar el repositorio.

El ciclo consulta únicamente INIA Vicuña y Pisco Elqui. Utiliza el día nominal solicitado y, si necesita completar antecedentes alrededor de medianoche, el anterior, con el límite prospectivo implementado. Mantiene al menos diez segundos entre generación y descarga y quince entre bloques. No crea reintentos automáticos ante un bloqueo del origen.

El panel usa `/api/actual`; `/api/emisiones` permite consultar el registro publicado. Ambos son de lectura. Las rutas históricas heredadas necesitan el catálogo privado de casos, que no se incluye en la distribución pública y no forma parte de la demo.

## Persistencia y sincronización

Los originales y sus hashes se guardan en el directorio de adquisición. SQLite conserva las observaciones, sus revisiones, recepciones, cierres y emisiones. HA-3 publica un conjunto coherente al final de un ciclo completo, en la misma transacción. La lectura utiliza una copia consistente y no mezcla ciclos.

Si una estación publica antes, se busca la última ventana válida de siete horas común a ambas. Una adquisición pendiente o fallida no borra el conjunto publicado anterior. La lectura vuelve a comprobar sus límites de caché; si caduca, deja de presentarlo como vigente. La política exacta se versiona en `aplicacion_terral/ha3/politica.json`.

Cada instalación debe configurar su propio usuario, permisos, temporizador, proxy HTTPS y copias de respaldo, y probar la restauración. No se publican las credenciales, respaldos o configuraciones privadas del servidor de Terral. Los scripts de investigación no deben ejecutarse como tareas del servidor web.
