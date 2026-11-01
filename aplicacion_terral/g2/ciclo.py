"""Un ciclo secuencial; usa exactamente request/curl oficial de G1, sin reintentos."""
import datetime as dt
import fcntl
import importlib.util
import re
import time
import uuid
import xlrd
from contextlib import contextmanager
from pathlib import Path
from ..adquirir import TRANSPORTE, pausa
from ..comun import BASE, SENSORES, guardar, leer, sha
from ..inferencia import calidad
from .almacen import DATOS, ahora, conexion, recibir, registros, cerrar
from .normalizar import bloque

INICIO = dt.date(2026, 10, 30)


@contextmanager
def exclusion():
    # Compartido con G1: ambos comandos respetan la misma exclusión.
    with (BASE/'evidencia/adquisicion.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def campos(station, day, anchor):
    today = anchor.date()
    if anchor.utcoffset() != dt.timedelta(0) or station not in ('6', '8'):
        raise ValueError('Ancla UTC y estación autorizada requeridas')
    if not max(INICIO, today-dt.timedelta(days=1)) <= dt.date.fromisoformat(day) <= today:
        raise ValueError('Fuera del ámbito prospectivo de dos fechas completas')
    return [('e_cod', station)] + [('s_cod[]', s[1]) for s in SENSORES if s[0] == station] + [
        ('intervalo', 'hora'), ('formato_archivo', 'xls'), ('fecha_inicio', day),
        ('fecha_fin', day), ('accion', 'generar_informe'), ('B1', 'Enviar')]


def transporte(evidence):
    spec = importlib.util.spec_from_file_location('terral_g2_transporte', TRANSPORTE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT = evidence
    return module


def limitado(folder, message):
    for phase in ('post', 'get'):
        if (folder/f'{phase}.http.json').exists():
            h = leer(folder/f'{phase}.http.json')
            headers = (folder/f'{phase}.headers').read_text().lower()
            if h['http_status'] in ('401', '403', '429') or 'retry-after:' in headers:
                return True
    return bool(re.search('control|límite|captcha|access denied|rate limit|forbidden', message, re.I))


def adquirir_bloque(station, day, anchor, folder, evidence, previous):
    folder.mkdir(parents=True)
    if previous is not None:
        pausa(previous, 15)
    transport = transporte(evidence)
    fields = campos(station, day, anchor)
    guardar(folder/'solicitud.json', dict(estacion=station, campos=fields, adquisicion_inicio_utc=ahora()))
    boundary = '----TerralG2'+uuid.uuid4().hex
    payload = (''.join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k, v in fields)+f'--{boundary}--\r\n').encode()
    url = f'https://www.ceazamet.cl/index.php?pag=mod_estacion&pag2=mod_estacion_descargas&e_cod={station}&p_cod=ceazamet'
    try:
        body, posted = transport.request(url, folder, 'post', {}, payload, 'multipart/form-data; boundary='+boundary)
        links = set(re.findall(r'https://www\.ceazamet\.cl/temp/[A-Za-z0-9_-]+\.xls', body.decode('utf8', 'replace')))
        if len(links) != 1:
            raise transport.Stop('Generación sin enlace XLS inequívoco')
        pausa(posted['finished_epoch'], 10)
        data, got = transport.request(next(iter(links)), folder, 'get', {})
        (folder/'original.xls').write_bytes(data)
        guardar(folder/'resultado.json', dict(estado='adquirido', sha256=sha(folder/'original.xls'), adquisicion_utc=got['finished_utc']))
        records = bloque(folder, station, day)
        guardar(folder/'normalizado.json', records)
        return records, None, False
    except (transport.Stop, ValueError, OSError, xlrd.XLRDError) as e:
        message = str(e)
        guardar(folder/'fallo.json', dict(estado='fallo_adquisicion', detalle=message, utc=ahora(), observaciones_ausentes=None))
        return [], message, limitado(folder, message)
    finally:
        guardar(folder/'manifiesto.json', {str(p.relative_to(folder)): sha(p) for p in sorted(folder.rglob('*')) if p.is_file() and p.name != 'manifiesto.json'})


def necesita_previo(records, station, today):
    group = [r for r in records if r['estacion'] == station]
    meaningful = [r for r in group if r['marca_original'][:10] == today and any(r[k] != '' for k in ('min', 'prom', 'max'))]
    if not meaningful:
        return True
    mark = max(r['marca_original'] for r in meaningful)
    t = dt.datetime.fromisoformat(mark)
    if t.hour >= 6:
        return False  # No ampliar una consulta por huecos dentro del día.
    needed = {((t-dt.timedelta(hours=k)).isoformat(sep=' '), s[1]) for k in range(7) for s in SENSORES if s[0] == station}
    available = {(r['marca_original'], r['sensor']) for r in group if calidad(r) is not None}
    return not needed <= available


def ultimo_http(root):
    paths = list((BASE/'evidencia').glob('adquisicion_*/[68]/*.http.json'))
    paths += list((root/'adquisiciones').glob('*/*/*/*.http.json'))
    return max((leer(p)['finished_epoch'] for p in paths), default=None)


def ejecutar(root=DATOS, *, adquirir=adquirir_bloque, anchor=None):
    root = Path(root)
    anchor = anchor or dt.datetime.now(dt.timezone.utc)
    # Validación antes de cualquier mutación/red.
    campos('6', anchor.date().isoformat(), anchor)
    with exclusion():
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if (root/'DETENIDO.json').exists():
            return dict(estado='detenido_requiere_revision_manual', inferencias_actuales_emitidas=0)
        with conexion(root) as db:
            last = db.execute('SELECT inicio_utc FROM ciclos ORDER BY rowid DESC LIMIT 1').fetchone()
            if last and turno_horario(anchor) <= turno_horario(dt.datetime.fromisoformat(last['inicio_utc'])):
                return dict(estado='cache_sin_nueva_adquisicion', inferencias_actuales_emitidas=0)
            cid = anchor.strftime('%Y%m%dT%H%M%S')+'_'+uuid.uuid4().hex
            evidence = root/'adquisiciones'/cid
            evidence.mkdir(parents=True)
            plan = dict(ciclo=cid, ancla_utc=anchor.isoformat(), inicio_autorizado=str(INICIO), estaciones=['6', '8'],
                estrategia='día UTC nominal actual; día anterior solo si faltan antecedentes que cruzan medianoche o día vacío; nunca antes de inicio autorizado',
                max_dias_por_estacion=2, reintentos=0, transporte_sha256=sha(TRANSPORTE),
                pausa_generacion_descarga_s=10, pausa_bloques_s=15,
                decision='G2-1', conversion_marcas_a_utc=None)
            guardar(evidence/'plan.json', plan)
            db.execute('INSERT INTO ciclos VALUES(?,?)', (cid, anchor.isoformat()))
            db.commit()  # Un proceso interrumpido queda identificado, no se oculta.
            previous, failures, stop = ultimo_http(root), [], False
            try:
                for station in ('6', '8'):
                    today = anchor.date().isoformat()
                    days = [today]
                    for day in days:
                        folder = evidence/station/day
                        records, failure, stop = adquirir(station, day, anchor, folder, evidence, previous)
                        detail = dict(fallo=failure, manifiesto_sha256=sha(folder/'manifiesto.json'))
                        recibir(db, cid, station, day, 'fallo_adquisicion' if failure else 'adquirido', detail, records)
                        db.commit()
                        previous = time.time()
                        if failure:
                            failures.append(f'{station}/{day}: {failure}')
                            # Ningún fallo desencadena otra descarga para recuperar ese bloque.
                            break
                        previous_day = anchor.date()-dt.timedelta(days=1)
                        if day == today and previous_day >= INICIO and necesita_previo(registros(db), station, today):
                            days.append(previous_day.isoformat())
                    if stop:
                        guardar(root/'DETENIDO.json', dict(ciclo=cid, utc=ahora(), motivo='Límite/control del origen; no reanudar automáticamente'))
                        break
                if stop:
                    failures.append('Ejecución detenida por control del origen; estaciones restantes no consultadas')
                out = cerrar(db, cid, '; '.join(failures) or None)
                db.commit()
                guardar(evidence/'evaluacion.json', out)
            finally:
                # Incluso una interrupción conserva el intento y todos los archivos ya recibidos.
                guardar(evidence/'manifiesto.json', {str(p.relative_to(evidence)): sha(p) for p in sorted(evidence.rglob('*')) if p.is_file() and p != evidence/'manifiesto.json'})
            return dict(ciclo=cid, estado=out['estado'], inferencias_actuales_emitidas=0, fallos=len(failures))


def turno_horario(anchor):
    # Turnos del timer a :15 UTC, sin perder la hora siguiente por jitter.
    # El intento se registra antes de HTTP y el lock abarca todo el ciclo:
    # ni duplicados en el mismo turno ni reintentos tras fallos/interrupción.
    return (anchor-dt.timedelta(minutes=15)).replace(minute=0,second=0,microsecond=0)


def reanudar(motivo, root=DATOS):
    if not motivo.strip(): raise ValueError('Motivo de revisión manual requerido')
    root = Path(root)
    with exclusion():
        marker = root/'DETENIDO.json'
        if not marker.exists(): raise ValueError('No hay bloqueo de origen')
        guardar(root/'revisiones'/f'{uuid.uuid4().hex}.json', dict(utc=ahora(), motivo=motivo, bloqueo=leer(marker)))
        marker.unlink()
