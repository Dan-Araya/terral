"""SQLite privado: versiones de observaciones, recepciones y evaluaciones append-only."""
import datetime as dt
import hashlib
import fcntl
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from ..comun import BASE, SENSORES, leer
from ..inferencia import calidad, emitir, evaluar_frescura

DATOS = BASE / 'datos_G2'
OBS_FIELDS = ('estacion', 'sensor', 'variable', 'unidad', 'altura_m', 'marca_original', 'min', 'prom', 'max', 'porcentaje_datos', 'adquisicion_utc', 'version', 'contenido_sha256')
TABLAS = {
    'ciclos': 'id TEXT PRIMARY KEY, inicio_utc TEXT NOT NULL',
    'cierres': 'ciclo TEXT PRIMARY KEY REFERENCES ciclos(id), fin_utc TEXT NOT NULL, estado TEXT NOT NULL, detalle TEXT NOT NULL',
    'adquisiciones': 'id INTEGER PRIMARY KEY, ciclo TEXT NOT NULL REFERENCES ciclos(id), estacion TEXT NOT NULL, dia TEXT NOT NULL, estado TEXT NOT NULL, detalle TEXT NOT NULL',
    'observaciones': 'id INTEGER PRIMARY KEY, estacion TEXT NOT NULL, sensor TEXT NOT NULL, marca TEXT NOT NULL, version INTEGER NOT NULL, hash TEXT NOT NULL, contenido TEXT NOT NULL, anterior INTEGER REFERENCES observaciones(id), UNIQUE(estacion,sensor,marca,version)',
    'recepciones': 'id INTEGER PRIMARY KEY, observacion INTEGER NOT NULL REFERENCES observaciones(id), adquisicion INTEGER NOT NULL REFERENCES adquisiciones(id), utc TEXT NOT NULL, procedencia TEXT NOT NULL, UNIQUE(observacion,adquisicion)',
    'evaluaciones': 'id INTEGER PRIMARY KEY, ciclo TEXT NOT NULL UNIQUE REFERENCES ciclos(id), utc TEXT NOT NULL, salida TEXT NOT NULL, entradas TEXT NOT NULL',
}


def ahora():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def json_text(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def conectar(root=DATOS, lectura=False):
    path = Path(root) / 'terral.sqlite3'
    if lectura:
        db = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        db = sqlite3.connect(path)
        path.chmod(0o600)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    if not lectura:
        for name, schema in TABLAS.items():
            db.execute(f'CREATE TABLE IF NOT EXISTS {name} ({schema})')
            for op in ('UPDATE', 'DELETE'):
                db.execute(f"CREATE TRIGGER IF NOT EXISTS {name}_no_{op} BEFORE {op} ON {name} BEGIN SELECT RAISE(ABORT, 'registro inmutable'); END")
        db.commit()
    return db


@contextmanager
def conexion(root=DATOS, lectura=False):
    db = conectar(root, lectura)
    try:
        with db:
            yield db
    finally:
        db.close()


def recibir(db, ciclo, station, day, estado, detalle, records=()):
    aid = db.execute('INSERT INTO adquisiciones(ciclo,estacion,dia,estado,detalle) VALUES(?,?,?,?,?)',
                     (ciclo, station, day, estado, json_text(detalle))).lastrowid
    for r in records:
        # Calidad y evidencia se conservan aunque la fila esté vacía o sea inválida.
        calidad(r)  # Rechaza identidad incompatible, no convierte valores inválidos.
        content = {k: v for k, v in r.items() if k not in ('adquisicion_utc', 'procedencia')}
        digest = hashlib.sha256(json_text(content).encode()).hexdigest()
        prev = db.execute('SELECT * FROM observaciones WHERE estacion=? AND sensor=? AND marca=? ORDER BY version DESC LIMIT 1',
                          (station, r['sensor'], r['marca_original'])).fetchone()
        if prev is None or prev['hash'] != digest:
            oid = db.execute('INSERT INTO observaciones(estacion,sensor,marca,version,hash,contenido,anterior) VALUES(?,?,?,?,?,?,?)',
                (station, r['sensor'], r['marca_original'], prev['version']+1 if prev else 1, digest, json_text(content), prev['id'] if prev else None)).lastrowid
        else:
            oid = prev['id']
        db.execute('INSERT INTO recepciones(observacion,adquisicion,utc,procedencia) VALUES(?,?,?,?)',
                   (oid, aid, r['adquisicion_utc'], json_text(r['procedencia'])))
    return aid


def registros(db):
    rows = db.execute('''SELECT o.*, r.utc, r.procedencia FROM observaciones o
        JOIN recepciones r ON r.id=(SELECT MAX(r2.id) FROM recepciones r2 WHERE r2.observacion=o.id)
        WHERE o.version=(SELECT MAX(o2.version) FROM observaciones o2 WHERE o2.estacion=o.estacion AND o2.sensor=o.sensor AND o2.marca=o.marca)
        ORDER BY o.marca,o.estacion,o.sensor''').fetchall()
    return [dict(json.loads(r['contenido']), adquisicion_utc=r['utc'], procedencia=json.loads(r['procedencia']),
                 version=r['version'], observacion_id=r['id'], contenido_sha256=r['hash']) for r in rows]


def evaluar(db, current=None, fallo=None):
    current = current or ahora()
    records = registros(db)
    meaningful = [r for r in records if any(r[k] != '' for k in ('min', 'prom', 'max'))]
    mark = max((r['marca_original'] for r in meaningful), default='')
    # Selección por etiqueta nominal; nunca se interpreta como UTC ni hora civil.
    if mark:
        t = dt.datetime.fromisoformat(mark)
        selected = [r for r in records if t-dt.timedelta(hours=6) <= dt.datetime.fromisoformat(r['marca_original']) <= t]
    else:
        selected = []
    # La caché más antigua de las entradas requeridas gobierna, no la última recepción global.
    acquisition = min((r['adquisicion_utc'] for r in selected), default=None)
    out = emitir(selected, mark, modo='actual', adquisicion_utc=acquisition, ahora_utc=current, fallo_adquisicion=fallo)
    out['decision_habilitacion'] = 'G2-1'
    out['frescura']['politica'] = leer(BASE/'g2/politica_actual_v1.json')
    return out, selected


def cerrar(db, ciclo, fallo=None, current=None):
    current = current or ahora()
    out, selected = evaluar(db, current, fallo)
    db.execute('INSERT INTO evaluaciones(ciclo,utc,salida,entradas) VALUES(?,?,?,?)',
               (ciclo, current, json_text(out), json_text(selected)))
    db.execute('INSERT INTO cierres VALUES(?,?,?,?)', (ciclo, current, 'fallo_adquisicion' if fallo else 'completo', json_text({'fallo': fallo})))
    return out


def publica(r, current):
    # Lista positiva: no se filtran rutas, originales, cuerpos HTTP ni mensajes del origen.
    p = {k: r[k] for k in OBS_FIELDS}
    p.update(calidad='valida' if calidad(r) is not None else 'invalida',
             edad_observacion_h=None, observacion_utc=None,
             cache=evaluar_frescura(r['adquisicion_utc'], current, 2))
    return p


def salida_publica(out):
    keys = ('modo', 'modelo', 'modelo_sha256', 'hora_observacion_original', 'adquisicion_utc',
            'calidad', 'completitud', 'criterio', 'elegible', 'estado', 'estimaciones', 'advertencia')
    return {k: out[k] for k in keys}


def consultar(recurso, modo='actual', root=DATOS, current=None, limite=100, antes=None, ejemplo='ordinario'):
    if modo not in ('actual', 'historico') or recurso not in ('estado', 'observaciones', 'estimacion', 'emisiones', 'ejemplos'):
        raise ValueError('Consulta no autorizada')
    if not 1 <= limite <= 500 or (antes is not None and (not isinstance(antes, int) or antes < 1)):
        raise ValueError('Paginación inválida')
    if ejemplo not in ('ordinario', 'inicio_6h'):
        raise ValueError('Ejemplo no autorizado')
    current = current or ahora()
    envelope = dict(version_contrato='G2-1', modo=modo, consulta_utc=current,
        decision_habilitacion='G2-1', advertencia='Estimaciones experimentales del criterio histórico; no probabilidades meteorológicas certificadas.')
    if modo == 'historico':
        # Catálogo cerrado, materializado desde validación 2022–2023.
        examples = leer(BASE/'g2/ejemplos_historicos.json')
        entry = examples[ejemplo]
        inp = entry['entrada']
        out = emitir(**inp)
        envelope['ejemplo'] = ejemplo
        payload = {'salida': salida_publica(out), 'validacion': entry['validacion']}
        if recurso == 'observaciones':
            payload = [{k: r[k] for k in OBS_FIELDS if k in r} for r in inp['registros']]
        elif recurso == 'emisiones': payload = [salida_publica(out)]
        elif recurso in ('estado', 'estimacion'): payload = salida_publica(out)
        elif recurso == 'ejemplos':
            payload = [dict(id=k, marca=v['entrada']['emision'], validacion=v['validacion'],
                            salida=salida_publica(v['salida'])) for k, v in examples.items()]
        envelope['datos'] = payload
        return envelope
    if recurso == 'ejemplos': raise ValueError('Ejemplos solo en histórico')
    if not (Path(root)/'terral.sqlite3').exists():
        envelope['datos'] = {'estado': 'sin_adquisiciones'}
        return envelope
    with conexion(root, lectura=True) as db:
        db.execute('BEGIN')  # Vista coherente aunque el escritor cierre durante la consulta.
        last = db.execute('SELECT c.*, x.estado cierre FROM ciclos c LEFT JOIN cierres x ON x.ciclo=c.id ORDER BY c.rowid DESC LIMIT 1').fetchone()
        running = False
        if last and last['cierre'] is None:
            with (BASE/'evidencia/adquisicion.lock').open('r') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    running = True
        failure = last and last['cierre'] != 'completo' and not running
        out, selected = evaluar(db, current, 'último ciclo fallido o interrumpido' if failure else None)
        records = registros(db)
        if recurso == 'estado':
            envelope['datos'] = dict(estado=out['estado'], motivos=out['motivos'],
                observaciones_disponibles=any(calidad(r) is not None for r in records),
                estimacion_disponible=False, inferencia_actual_habilitada=False,
                compatibilidad_temporal='pendiente', calidad=out['calidad'], completitud=out['completitud'],
                criterio=out['criterio'], frescura=out['frescura'],
                adquisicion_en_curso=running, ultimo_ciclo=dict(last) if last else None)
        elif recurso == 'observaciones':
            groups = []
            for station, sensor, *_ in SENSORES:
                group = [r for r in records if r['estacion'] == station and r['sensor'] == sensor]
                received = [r for r in group if any(r[k] != '' for k in ('min', 'prom', 'max'))]
                latest = max(received, key=lambda r: r['marca_original'], default=None)
                valid = max((r for r in received if calidad(r) is not None), key=lambda r: r['marca_original'], default=None)
                groups.append(dict(estacion=station, sensor=sensor,
                    ultima=publica(latest, current) if latest else None,
                    ultima_valida=publica(valid, current) if valid else None,
                    filas_vacias=sum(all(r[k] == '' for k in ('min', 'prom', 'max')) for r in group)))
            envelope['datos'] = groups
        elif recurso == 'estimacion':
            envelope['datos'] = dict(actual=None, ultima_valida_historica=None, estado=out['estado'])
        else:
            # Evaluaciones bloqueadas se ofrecen como estados; no se inventan emisiones.
            rows = db.execute('SELECT id,utc,salida FROM evaluaciones WHERE id<? ORDER BY id DESC LIMIT ?', (antes or 2**63-1, limite)).fetchall()
            envelope['datos'] = dict(emisiones=[], evaluaciones=[dict(id=r['id'], evaluacion_utc=r['utc'], **salida_publica(json.loads(r['salida']))) for r in rows])
            envelope['siguiente_antes'] = rows[-1]['id'] if len(rows) == limite else None
    return envelope
