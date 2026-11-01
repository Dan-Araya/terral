"""HTTP local de solo lectura, con rutas y parámetros cerrados."""
import argparse
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from ..comun import BASE, leer
from ..g2 import almacen as a
from ..inferencia import calidad

WEB = Path(__file__).parent / 'web'
STATIC = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css'), '/metodologia': ('metodologia.html', 'text/html')}
CASES = ('ordinario', 'inicio_6h')


def actual(root=a.DATOS, current=None):
    current = current or a.ahora()
    state = a.consultar('estado', root=root, current=current)
    obs = a.consultar('observaciones', root=root, current=current)
    history = a.consultar('emisiones', root=root, current=current, limite=10)
    series = []
    if (Path(root) / 'terral.sqlite3').exists():
        with a.conexion(root, lectura=True) as db:
            records = a.registros(db)
        # Solo el último día nominal; corte por etiquetas, sin inventar zona.
        last_mark = max((r['marca_original'] for r in records if any(r[k] != '' for k in ('min', 'prom', 'max'))), default='')
        day = last_mark[:10]
        series = [a.publica(r, current) for r in records if r['marca_original'].startswith(day) and r['marca_original'] <= last_mark]
    return dict(version='G3-1', modo='actual', consulta_utc=current, estado=state['datos'],
                observaciones=obs['datos'], series=series, historial=history['datos'],
                estimacion=None, programacion='no_activada_en_entrega_G2_G3')


def historico(case):
    # Salida guardada, no reconstrucción ni inferencia durante una visita.
    entry = leer(BASE / 'g2/ejemplos_historicos.json')[case]
    out = a.salida_publica(entry['salida'])
    out['estimaciones'] = {h: v['probabilidad_guardada'] for h, v in entry['validacion'].items()}
    rows = [{k: r[k] for k in a.OBS_FIELDS if k in r} for r in entry['entrada']['registros']]
    for r in rows:
        r['calidad'] = 'valida' if calidad(r) is not None else 'invalida'
    return dict(version='G3-1', modo='historico', caso=case, salida=out, series=rows,
                entrenamiento='2013–2021; última emisión de entrenamiento: 2021-12-30 23:00:00',
                bloque_validacion='2022–2023', seleccion='Primer negativo y primer positivo del objetivo guardado a seis horas; ventanas aisladas, no evaluación de desempeño.')


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body, mime='application/json'):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime + '; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            url = urlsplit(self.path)
            query = parse_qs(url.query, keep_blank_values=True, strict_parsing=True)
            if url.path in STATIC and not query:
                name, mime = STATIC[url.path]
                return self.reply(200, (WEB / name).read_bytes(), mime)
            if url.path == '/api/actual' and not query:
                return self.reply(200, actual(root=self.server.data_root))
            if url.path in ('/api/historico', '/api/verificacion'):
                allowed = {'caso'} if url.path == '/api/historico' else {'caso', 'horizonte'}
                if set(query) != allowed or any(len(v) != 1 for v in query.values()):
                    raise ValueError()
                case = query['caso'][0]
                if case not in CASES:
                    raise ValueError()
                if url.path == '/api/historico':
                    return self.reply(200, historico(case))
                h = query['horizonte'][0]
                if h not in ('1', '3', '6', '8', '12', '24'):
                    raise ValueError()
                validation = leer(BASE / 'g2/ejemplos_historicos.json')[case]['validacion'][h]
                return self.reply(200, dict(modo='verificacion_retrospectiva', caso=case, horizonte=int(h), **validation))
            return self.reply(404, {'error': 'Recurso no disponible'})
        except ValueError:
            return self.reply(400, {'error': 'Parámetros no permitidos'})
        except (OSError, KeyError, sqlite3.Error):
            # Nunca revelar rutas, contenido privado ni excepciones del origen.
            return self.reply(503, {'error': 'Lectura local no disponible. Revise el almacén con el administrador.'})

    def log_message(self, format, *args):
        pass


def crear_servidor(port=8080, root=a.DATOS):
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.data_root = root  # Configuración de proceso; jamás parámetro del visitante.
    return server


def main():
    parser = argparse.ArgumentParser(description='Terral G3: panel local de lectura')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    server = crear_servidor(args.port)
    print(f'Terral local: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
