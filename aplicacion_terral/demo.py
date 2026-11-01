"""Demo pública sin red ni observaciones reales; reloj y entradas sintéticos."""
import argparse
import datetime as dt
import json
import tempfile
from http import HTTPStatus
from wsgiref.simple_server import make_server

from .comun import SENSORES
from .g2 import almacen as a
from .g4.wsgi import HEADERS, STATIC, WEB
from .ha3 import operacion as ha3

CORTE = '2023-06-15T16:15:00+00:00'
AVISO = ('Demostración local · Datos sintéticos · Reloj simulado de 2023. '
         'No representa las condiciones actuales del valle.')


def registros_sinteticos():
    """Valores inventados, no muestreados ni derivados de observaciones CEAZAMet."""
    result = []
    for hour in range(10, 17):
        for station, sensor, variable, unit, height, *_ in SENSORES:
            value = {'temperatura': 15.0, 'humedad': 48.0, 'viento_2m': 1.2,
                     'viento': 1.5, 'direccion_2m': 270.0, 'direccion': 270.0,
                     'presion': 950.0}[variable]
            if variable == 'temperatura':
                value += (hour-10)*0.2 + (2 if station == '8' else 0)
            if variable == 'presion' and station == '8':
                value = 875.0
            result.append(dict(estacion=station, sensor=sensor, variable=variable,
                unidad=unit, altura_m=height, marca_original=f'2023-06-15 {hour}:00:00',
                min=value, prom=value, max=value, porcentaje_datos=100,
                adquisicion_utc='2023-06-15T16:14:00+00:00',
                procedencia={'tipo': 'sintetica', 'generador': 'demo.py'}))
    return result


def preparar(root):
    """Crea un ledger nuevo y evalúa el motor congelado; nunca descarga ni entrena."""
    with a.conexion(root) as db:
        ha3.migrar(db)
        db.execute('INSERT INTO ciclos VALUES(?,?)', ('demo', CORTE))
        rows = registros_sinteticos()
        for station in ('6', '8'):
            a.recibir(db, 'demo', station, '2023-06-15', 'adquirido',
                      {'datos_sinteticos': True}, [r for r in rows if r['estacion'] == station])
        ha3.cerrar(db, 'demo', current=CORTE)


def crear_aplicacion(root):
    def application(env, start_response):
        status, mime = 200, 'application/json'
        path = env.get('PATH_INFO', '/')
        if env.get('REQUEST_METHOD') != 'GET':
            status, body = 405, {'error': 'Método no permitido'}
        elif env.get('QUERY_STRING', ''):
            status, body = 400, {'error': 'La demo no acepta parámetros'}
        elif path in STATIC:
            name, mime = STATIC[path]
            body = (WEB/name).read_bytes()
            if mime == 'text/html':
                marker = b'<main class="prose">' if b'<main class="prose">' in body else b'<main>'
                body = body.replace(marker, marker+('<p role="note">'+AVISO+'</p>').encode(), 1)
        elif path == '/api/actual':
            with a.conexion(root, lectura=True) as db:
                body = dict(ha3.panel(db, CORTE), consulta_utc=CORTE,
                            datos_sinteticos=True, aviso_demo=AVISO,
                            programacion='Demo local: reloj simulado, sin adquisiciones')
        elif path == '/api/emisiones':
            with a.conexion(root, lectura=True) as db:
                body = dict(ha3.historial(db), datos_sinteticos=True)
        else:
            status, body = 404, {'error': 'Recurso no incluido en la demo pública'}
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
        start_response(f'{status} {HTTPStatus(status).phrase}', HEADERS + [
            ('Content-Type', mime+'; charset=utf-8'), ('Content-Length', str(len(body)))])
        return [body]
    return application


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='terral-demo-') as root:
        preparar(root)
        with make_server('127.0.0.1', args.port, crear_aplicacion(root)) as server:
            print(f'{AVISO}\nhttp://127.0.0.1:{server.server_port}', flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass


if __name__ == '__main__':
    main()
