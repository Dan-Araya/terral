"""WSGI de producción: rutas cerradas y snapshot SQLite por respuesta compuesta."""
import json
import logging
import os
import sqlite3
import tempfile
import subprocess
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs
from ..g2 import almacen as a
from ..g3.servidor import actual, historico, STATIC, CASES
from ..comun import BASE, leer

DATA = Path(os.environ.get('TERRAL_DATA', '/var/lib/terral'))
WEB = Path(__file__).parent / 'web'
HEADERS = [('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'),
 ('Referrer-Policy','no-referrer'), ('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"),
 ('Permissions-Policy','camera=(), microphone=(), geolocation=()')]


def current(root=DATA):
    # Backup online = un único snapshot confirmado para todos los recursos G3.
    # No retiene una transacción de lectura mientras se compone JSON ni mezcla commits.
    with tempfile.TemporaryDirectory(prefix='terral-read-') as temp:
        if (Path(root)/'terral.sqlite3').exists():
            with a.conexion(root, lectura=True) as source:
                target = sqlite3.connect(str(Path(temp)/'terral.sqlite3'))
                try:
                    source.backup(target)
                finally:
                    target.close()
        result = None
        if (Path(temp)/'terral.sqlite3').exists():
            from ..ha3.operacion import existe, panel
            with a.conexion(Path(temp), lectura=True) as db:
                if existe(db):
                    now=a.ahora()
                    result=dict(consulta_utc=now,**panel(db,now))
        if result is None:
            result = actual(root=Path(temp))
    try:
        active = subprocess.run(['systemctl','is-active','terral-g2.timer'],capture_output=True,text=True,timeout=2).stdout.strip()
        result['programacion'] = 'Actualización horaria activa' if active=='active' else 'Actualización horaria inactiva'
        result['actualizacion'] = f'Timer terral-g2.timer: {active}. Consulta del sistema al leer el panel. El último ciclo y su recepción se muestran por separado; un timer activo no garantiza éxito del origen.'
    except (OSError, subprocess.TimeoutExpired):
        result['programacion'] = 'Estado del programador desconocido'
        result['actualizacion'] = 'No se pudo comprobar el programador del sistema.'
    return result


def application(env, start_response):
    status, mime = 200, 'application/json'
    try:
        if env['REQUEST_METHOD'] != 'GET':
            status, body = 405, {'error':'Método no permitido'}
        else:
            path = env.get('PATH_INFO', '')
            raw = env.get('QUERY_STRING','')
            if len(raw)>256: raise ValueError()
            query = parse_qs(raw, keep_blank_values=True, strict_parsing=True, max_num_fields=4)
            if path in STATIC and not query:
                name, mime = STATIC[path]
                body = (WEB/name).read_bytes()
            elif path == '/api/actual' and not query:
                body = current()
            elif path == '/api/emisiones':
                if set(query)-{'antes'} or any(len(v)!=1 for v in query.values()): raise ValueError()
                before=int(query['antes'][0]) if query else None
                if before is not None and not 0 < before < 2**63: raise ValueError()
                from ..ha3.operacion import historial
                if (DATA/'terral.sqlite3').exists():
                    with a.conexion(DATA,lectura=True) as db: body=historial(db,before)
                else: body={'emisiones':[],'siguiente_antes':None}
            elif path in ('/api/historico','/api/verificacion'):
                allowed = {'caso'} if path == '/api/historico' else {'caso','horizonte'}
                if set(query)!=allowed or any(len(v)!=1 for v in query.values()): raise ValueError()
                case = query['caso'][0]
                if case not in CASES: raise ValueError()
                if path == '/api/historico': body = historico(case)
                else:
                    h = query['horizonte'][0]
                    if h not in ('1','3','6','8','12','24'): raise ValueError()
                    validation = leer(BASE/'g2/ejemplos_historicos.json')[case]['validacion'][h]
                    body = dict(modo='verificacion_retrospectiva',caso=case,horizonte=int(h),**validation)
            else: status,body = 404, {'error':'Recurso no disponible'}
    except ValueError:
        status,body = 400, {'error':'Parámetros no permitidos'}
    except Exception:
        logging.getLogger('terral').exception('Fallo de lectura local')
        # Gunicorn registra incidencias de proceso; nunca publicar traceback/rutas.
        status,body = 503, {'error':'Lectura local no disponible. Revise el almacén con el administrador.'}
    if not isinstance(body, bytes): body=json.dumps(body,ensure_ascii=False,allow_nan=False).encode()
    start_response(f'{status} {HTTPStatus(status).phrase}', HEADERS + [('Content-Type',mime+'; charset=utf-8'),('Content-Length',str(len(body)))])
    return [body]
