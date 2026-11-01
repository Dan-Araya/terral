#!/usr/bin/env python3
"""Adquisición CEAZAMet secuencial. Nunca ejecuta entrenamiento ni escribe en INIA."""
import argparse
import calendar
import csv
import datetime as dt
import fcntl
import hashlib
import io
import json
import math
import re
import shutil
import subprocess
import time
import unicodedata
import uuid
from collections import Counter, defaultdict
from pathlib import Path
import xlrd

ROOT = Path(__file__).resolve().parent
LOW, HIGH = dt.date(2013, 1, 1), dt.date(2023, 12, 31)
VARS = ['temperatura', 'humedad', 'presion', 'viento', 'direccion']
FIELDS = ['min', 'prom', 'max', 'porcentaje_datos']

class Stop(Exception): pass
class Invalid(Exception): pass

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def save(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(p)
def norm(s):
    # La normalización sirve solo para identificar encabezados; no altera originales.
    s = re.sub(r'(?:Ã.|Â.)+', lambda m: repair(m.group()), str(s))
    return ''.join(c for c in unicodedata.normalize('NFD', s).lower() if not unicodedata.combining(c))
def repair(s):
    try: return s.encode('latin1').decode('utf8')
    except UnicodeError: return s

def numeric(v): return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
def scope(a, b):
    a, b = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
    if not LOW <= a <= b <= HIGH or (b-a).days > 6: raise ValueError('Solicitud fuera de 2013–2023 o superior a siete días')
    return a, b

def configuration(path):
    evidence=ROOT/'evidencia_metadatos'/'manifest.json'
    if evidence.exists():
        for source in read(evidence):
            if sha(ROOT/source['path'])!=source['sha256']: raise Invalid('Metadatos oficiales alterados: '+source['path'])
    c = read(path)
    if c['start'] != str(LOW) or c['end'] != str(HIGH): raise ValueError('Reserva temporal inmutable')
    if any(not math.isfinite(c[k]) or c[k]<limit for k,limit in [('pause_post_get_seconds',10),('pause_blocks_seconds',15)]): raise ValueError('Pausas insuficientes')
    ids = [s['e_cod'] for s in c['stations']]
    if len(ids) != len(set(ids)) or '6' in ids: raise ValueError('Estaciones duplicadas o INIA')
    for s in c['stations']:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', s['slug']): raise ValueError('Ruta insegura')
        if not re.fullmatch(r'[A-Za-z0-9_-]+',s['e_cod']): raise ValueError('Código inseguro')
        if not s['identity_verified']: raise ValueError('Identidad pendiente de verificar')
        sensors = s['sensors']
        if len({x['code'] for x in sensors}) != len(sensors): raise ValueError('Sensores repetidos')
        for x in sensors:
            if not re.fullmatch(r'[A-Za-z0-9_-]+',x['code']): raise ValueError('Código sensor inseguro')
            if x['variable'] not in VARS or not x['label'] or x['height_m'] is None: raise ValueError('Sensor incompleto')
        if not set(s['basic_sensors']) <= {x['code'] for x in sensors}: raise ValueError('Conjunto básico no pertenece a estación')
    if not c['basic_predictors'] or not set(c['basic_predictors'])<=set(VARS): raise ValueError('Predictores básicos inválidos')
    return c

def plan(station):
    if station['development_status'] == 'sin_cobertura_en_desarrollo': return []
    start = max(LOW, dt.date.fromisoformat(station['metadata_start']))
    end = min(HIGH, dt.date.fromisoformat(station['metadata_end']))
    if start > end: return []
    # El primer día es la prueba; forma parte del plan y nunca se repite.
    result = [{'start': str(start), 'end': str(start), 'trial': True}]
    start += dt.timedelta(days=1)
    while start <= end:
        last = min(start + dt.timedelta(days=6), end)
        result.append({'start': str(start), 'end': str(last), 'trial': False})
        start = last + dt.timedelta(days=1)
    for j in result:
        j['id'] = j['start'] + '_' + j['end']
        j['sensors'] = [x['code'] for x in station['sensors']]
        scope(j['start'], j['end'])
    return result

def params(station, job):
    scope(job['start'], job['end'])
    return [('e_cod', station['e_cod'])] + [('s_cod[]', x) for x in job['sensors']] + [
        ('intervalo','hora'), ('formato_archivo','xls'), ('fecha_inicio',job['start']),
        ('fecha_fin',job['end']), ('accion','generar_informe'), ('B1','Enviar')]

def request(url, directory, phase, config, payload=None, content_type=None):
    # Mismo transporte curl/multipart probado en historico_inia; sin redirecciones ni reintentos.
    if not re.fullmatch(r'https://www\.ceazamet\.cl/(index\.php\?.*|temp/[A-Za-z0-9_-]+\.xls)',url): raise Stop('Destino no autorizado')
    body, headers = directory / f'{phase}.body', directory / f'{phase}.headers'
    if body.exists() or (directory/f'{phase}.http.json').exists(): raise Stop('Intento previo: conservar evidencia y revisar manualmente')
    command = ['curl','--silent','--show-error','--max-time','60','--dump-header',str(headers),'--output',str(body),'--write-out','%{http_code}']
    if payload is not None:
        (directory/'parametros.multipart').write_bytes(payload)
        command += ['--header','Content-Type: '+content_type,'--data-binary','@'+str(directory/'parametros.multipart')]
    began = now()
    result = subprocess.run(command+[url],capture_output=True,text=True)
    h = headers.read_text(errors='replace') if headers.exists() else ''
    h = '\n'.join(x for x in h.splitlines() if not x.lower().startswith('set-cookie:'))
    headers.write_text(h)
    info = {'url':url,'started_utc':began,'finished_utc':now(),'finished_epoch':time.time(),
            'curl_exit':result.returncode,'http_status':result.stdout,'stderr':result.stderr,
            'body_sha256':sha(body) if body.exists() else None}
    save(directory/f'{phase}.http.json',info)
    save(ROOT/'ultima_solicitud.json',info)
    if result.returncode or result.stdout != '200' or 'retry-after:' in h.lower(): raise Stop(f'HTTP detenido: {info}')
    if re.search(rb'captcha|access denied|too many requests|rate limit|forbidden',body.read_bytes(),re.I): raise Stop('Control o límite del servidor')
    return body.read_bytes(), info

def verify(station, job, directory):
    scope(job['start'],job['end'])
    p = directory/'original.xls'; m = read(directory/'manifest.json')
    if m['station'] != station['e_cod'] or m['fields'] != [list(x) for x in params(station,job)] or sha(p) != m['sha256']: raise Invalid('Identidad, parámetros o hash incompatibles')
    if sha(directory/'post.body') != m['generation_sha256']: raise Invalid('Generación alterada')
    if not p.read_bytes().startswith(bytes.fromhex('d0cf11e0a1b11ae1')): raise Invalid('Archivo no XLS/OLE')
    try: book = xlrd.open_workbook(p,logfile=io.StringIO())
    except Exception as e: raise Invalid('XLS ilegible') from e
    expected = f"[{job['start']},{job['end']}]"
    records, schemas, external, issues, seen = [], [], [], [], set()
    specs = {s['code']:s for s in station['sensors']}
    for sheet in book.sheets():
        if sheet.nrows < 4 or sheet.ncols < 2: raise Invalid('Hoja sin identidad/esquema')
        if norm(sheet.cell_value(0,1)).strip('* ') not in [norm(x).strip('* ') for x in station['xls_names']]: raise Invalid('Estación XLS inesperada')
        if sheet.cell_value(1,1) != expected: raise Invalid('Rango XLS distinto de solicitud')
        columns = {}
        for col in range(1,sheet.ncols):
            raw = str(sheet.cell_value(3,col))
            match = re.fullmatch(r'\[(Min|Prom|Max|%Datos)\]\s*(.*?)\[(-?[\d.]+)m\]',raw)
            if not match: raise Invalid('Cambio de esquema: '+raw)
            field, descriptor, height = match.groups()
            candidates = [s for s in specs.values() if norm(s['label']) in norm(descriptor) and float(height)==float(s['height_m'])]
            if len(candidates)!=1: raise Invalid('Sensor/altura ambiguos: '+raw)
            s=candidates[0]; sid=s['code']; seen.add(sid)
            field={'Min':'min','Prom':'prom','Max':'max','%Datos':'porcentaje_datos'}[field]
            unit=descriptor.split(' ',1)[0]
            if field!='porcentaje_datos' and s.get('unit') and norm(unit)!=norm(s['unit']): raise Invalid('Cambio de unidad: '+raw)
            if field in columns.setdefault(sid,{}): raise Invalid('Campo duplicado')
            columns[sid][field]=col
            schemas.append({'sensor':sid,'sheet':sheet.name,'field':field,'header':raw,'column':col+1,'unit':unit,'height_m':height})
        if not columns or any(set(x)!=set(FIELDS) for x in columns.values()): raise Invalid('Esquema sin sensores o incompleto')
        for i in range(4,sheet.nrows):
            label=str(sheet.cell_value(i,0))
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',label):
                if label and label not in ['Más información:','Fecha Generación:']: issues.append({'sheet':sheet.name,'row':i+1,'issue':'fila_no_interpretada'})
                continue
            stamp=dt.datetime.fromisoformat(label)
            if not LOW <= stamp.date() <= HIGH or not job['start'] <= str(stamp.date()) <= job['end']:
                external.append({'sheet':sheet.name,'row':i+1,'timestamp':label}); continue
            for sid, cols in columns.items():
                s=specs[sid]; values={f:sheet.cell_value(i,cols[f]) for f in FIELDS}
                flags=[]
                for f,v in values.items():
                    if v!='' and not numeric(v): flags.append(f+':no_numerico')
                    if v=='': flags.append(f+':faltante')
                pct=values['porcentaje_datos']; avg=values['prom']
                present=numeric(avg) and numeric(pct) and pct>0
                if numeric(pct) and not 0<=pct<=100: flags.append('porcentaje_fuera_rango')
                limits={'temperatura':(-50,60),'humedad':(0,100),'viento':(0,75),'direccion':(0,360),'presion':(300,1100)}
                a,b=limits[s['variable']]
                if any(numeric(values[f]) and not a<=values[f]<=b for f in ['min','prom','max']): flags.append('rango_revision')
                if s['variable']!='direccion' and all(numeric(values[f]) for f in ['min','prom','max']) and not values['min']<=avg<=values['max']: flags.append('orden_min_prom_max')
                if stamp.minute or stamp.second: flags.append('fuera_rejilla')
                records.append({'fecha_sin_zona':label,'sensor':sid,'variable':s['variable'],'altura_m':s['height_m'],
                    'unidad':s.get('unit') or next(x['unit'] for x in schemas if x['sensor']==sid and x['field']=='prom'),
                    **values,'presente':int(present),'utilizable_revision':int(present and not flags),
                    'problemas':'|'.join(flags),'archivo_original':str(p.relative_to(ROOT)),'sha256_original':m['sha256'],
                    'hoja':sheet.name,'fila_excel':i+1,'bloque':job['id']})
    detail={'status':'verificado_con_observaciones' if any(x['presente'] for x in records) else 'verificado_sin_observaciones',
        'sha256':m['sha256'],'generation_sha256':m['generation_sha256'],'sensors_absent':sorted(set(job['sensors'])-seen),
        'schema':schemas,'excluded_external_rows':external,'issues':issues,'rows':len(records),'verified_utc':now()}
    save(directory/'verificacion.json',detail)
    return detail, records

def saved_http(directory,phase):
    info=read(directory/f'{phase}.http.json')
    body=directory/f'{phase}.body'
    headers=(directory/f'{phase}.headers').read_text(errors='replace')
    if info['curl_exit'] or info['http_status']!='200' or sha(body)!=info['body_sha256'] or 'retry-after:' in headers.lower(): raise Stop('HTTP previo fallido, limitado o alterado')
    data=body.read_bytes()
    if re.search(rb'captcha|access denied|too many requests|rate limit|forbidden',data,re.I): raise Stop('Control previo del servidor')
    return data,info

def acquire(station,job,directory,config):
    directory.mkdir(parents=True,exist_ok=True)
    if (directory/'manifest.json').exists(): return verify(station,job,directory)
    fields=params(station,job)
    form=f"https://www.ceazamet.cl/index.php?pag=mod_estacion&pag2=mod_estacion_descargas&e_cod={station['e_cod']}&p_cod=ceazamet"
    acquisition={'station':station['e_cod'],'sensors':job['sensors'],'fields':fields,'form_url':form,
        'started_utc':now(),'station_metadata_sha256':hashlib.sha256(json.dumps(station,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'pause_post_get_seconds':config['pause_post_get_seconds'],'pause_blocks_seconds':config['pause_blocks_seconds']}
    # Recuperar solo respuestas HTTP exitosas conservadas. Nunca reintentar automáticamente.
    if (directory/'adquisicion.json').exists():
        acquisition=read(directory/'adquisicion.json')
        if acquisition['fields'] != [list(x) for x in fields]: raise Stop('Configuración cambió durante adquisición')
    else: save(directory/'adquisicion.json',acquisition)
    if (directory/'post.http.json').exists():
        response,posted=saved_http(directory,'post')
    else:
        if (ROOT/'ultima_solicitud.json').exists(): time.sleep(max(0,config['pause_blocks_seconds']-(time.time()-read(ROOT/'ultima_solicitud.json')['finished_epoch'])))
        boundary='----Vicuna'+uuid.uuid4().hex
        body=''.join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k,v in fields)+f'--{boundary}--\r\n'
        response,posted=request(form,directory,'post',config,body.encode(),'multipart/form-data; boundary='+boundary)
    links=re.findall(r'https://www\.ceazamet\.cl/temp/[A-Za-z0-9_-]+\.xls',response.decode('utf8','replace'))
    if len(set(links))!=1: raise Stop('Generación sin enlace XLS inequívoco; no se interpreta como ausencia')
    if (directory/'get.http.json').exists():
        data,got=saved_http(directory,'get')
    else:
        time.sleep(max(0,config['pause_post_get_seconds']-(time.time()-posted['finished_epoch'])))
        data,got=request(links[0],directory,'get',config)
    if not (directory/'original.xls').exists(): (directory/'original.xls').write_bytes(data)
    if sha(directory/'original.xls')!=hashlib.sha256(data).hexdigest(): raise Invalid('Original distinto de respuesta')
    acquisition.update(download_url=links[0],downloaded_utc=got['finished_utc'],sha256=sha(directory/'original.xls'),
                       generation_sha256=sha(directory/'post.body'),bytes=len(data))
    save(directory/'manifest.json',acquisition)
    return verify(station,job,directory)

def write_csv(path,rows,fields):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp')
    with tmp.open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    tmp.replace(path)

ROW_FIELDS=['fecha_sin_zona','sensor','variable','altura_m','unidad',*FIELDS,'presente','utilizable_revision','problemas','archivo_original','sha256_original','hoja','fila_excel','bloque']

def stopped_job(config,allowed_statuses=('solicitud_fallida',)):
    marker=ROOT/'DETENIDO.json'
    if not marker.exists(): raise Stop('No hay una descarga detenida')
    stopped=read(marker)
    station=next((s for s in config['stations'] if s['slug']==stopped['station']),None)
    if station is None: raise Stop('Estación detenida no configurada')
    job=next((j for j in plan(station) if j['id']==stopped['job']),None)
    if job is None or stopped['status'] not in allowed_statuses: raise Stop('Bloque o tipo de fallo no aptos para preparación de reintento')
    directory=ROOT/station['slug']/'originales'/job['id']
    return marker,stopped,station,job,directory

def archive_failed_attempt(marker,stopped,station,job,directory,reason,review=None):
    state_path=ROOT/station['slug']/'estado.json'
    state=read(state_path)
    archive=ROOT/station['slug']/'intentos_fallidos'/job['id']/uuid.uuid4().hex
    archive.mkdir(parents=True)
    save(archive/'auditoria.json',{'utc':now(),'reason':reason,'review':review,
        'stopped':stopped,'previous_state':state.get(job['id']),
        'files_sha256':{p.name:sha(p) for p in directory.iterdir() if p.is_file()}})
    shutil.move(str(directory),str(archive/'bloque'))
    state[job['id']]={'status':'pendiente','manual_retry_prepared_utc':now(),'failed_attempt_archive':str(archive.relative_to(ROOT))}
    save(state_path,state)
    # El marcador se retira al final y se conserva intacto en auditoría.
    shutil.move(str(marker),str(archive/'DETENIDO.json'))
    print(f"Intento fallido conservado en {archive}. Bloque pendiente; no se realizaron solicitudes HTTP.",flush=True)
    return archive

def prepare_connection_retry(config):
    """Acción manual local: POST sin respuesta por DNS/conexión/reset (curl 6/7/56)."""
    marker,stopped,station,job,directory=stopped_job(config)
    info=read(directory/'post.http.json')
    if info['curl_exit'] not in (6,7,56) or info['http_status']!='000' or info.get('body_sha256') is not None:
        raise Stop('Solo se admite curl 6/7/56 sin respuesta HTTP ni cuerpo; revisar otros fallos manualmente')
    if any((directory/name).exists() for name in ['get.http.json','get.body','original.xls','manifest.json']):
        raise Stop('Hay evidencia de descarga: no se permite repetir el bloque con esta acción')
    if (directory/'post.headers').read_text().strip() or ((directory/'post.body').exists() and (directory/'post.body').stat().st_size):
        raise Stop('Se recibió una respuesta; no se permite levantar posibles controles del servidor')
    acquisition=read(directory/'adquisicion.json')
    if acquisition['station']!=station['e_cod'] or acquisition['fields']!=[list(x) for x in params(station,job)] or info['url']!=acquisition['form_url']:
        raise Stop('Identidad o parámetros de la solicitud fallida incompatibles')
    return archive_failed_attempt(marker,stopped,station,job,directory,
        f"preparación manual de un nuevo intento tras curl {info['curl_exit']}, sin solicitudes HTTP")

def prepare_transfer_retry(config):
    """Solo GET curl 56/HTTP 200 con truncamiento acreditado por Content-Length."""
    marker,stopped,station,job,directory=stopped_job(config)
    if any((directory/name).exists() for name in ['original.xls','manifest.json']):
        raise Stop('Existe original o manifiesto; no se permite repetir una adquisición con esta acción')
    acquisition=read(directory/'adquisicion.json')
    form=f"https://www.ceazamet.cl/index.php?pag=mod_estacion&pag2=mod_estacion_descargas&e_cod={station['e_cod']}&p_cod=ceazamet"
    if acquisition['station']!=station['e_cod'] or acquisition['fields']!=[list(x) for x in params(station,job)] or acquisition['form_url']!=form:
        raise Stop('Identidad o parámetros de generación incompatibles')
    response,posted=saved_http(directory,'post')
    links=set(re.findall(r'https://www\.ceazamet\.cl/temp/[A-Za-z0-9_-]+\.xls',response.decode('utf8','replace')))
    info=read(directory/'get.http.json')
    body=directory/'get.body'; headers=(directory/'get.headers').read_text(errors='replace')
    if posted['url']!=form or len(links)!=1 or info['url'] not in links:
        raise Stop('El GET no corresponde al enlace generado para este bloque')
    if info['curl_exit']!=56 or info['http_status']!='200' or sha(body)!=info['body_sha256']:
        raise Stop('Solo se admite curl 56/HTTP 200 con cuerpo íntegro respecto a su evidencia local')
    if re.search(r'^retry-after:|^cf-mitigated:\s*challenge',headers,re.I|re.M) or re.search(rb'captcha|access denied|too many requests|rate limit|forbidden',body.read_bytes(),re.I):
        raise Stop('Control o límite del servidor: no se permite preparar reintento')
    lengths=re.findall(r'^content-length:\s*(\d+)\s*$',headers,re.I|re.M)
    encoding=re.findall(r'^content-encoding:\s*(.*?)\s*$',headers,re.I|re.M)
    if len(lengths)!=1 or (encoding and encoding!=['identity']) or not 0<body.stat().st_size<int(lengths[0]):
        raise Stop('No se acredita truncamiento por tamaño; se requiere otra revisión manual')
    if not body.read_bytes().startswith(bytes.fromhex('d0cf11e0a1b11ae1')):
        raise Stop('El cuerpo parcial no es un XLS/OLE; requiere revisión manual')
    review={'announced_bytes':int(lengths[0]),'received_bytes':body.stat().st_size,
        'missing_bytes':int(lengths[0])-body.stat().st_size,'partial_sha256':sha(body),'accepted_as_observations':False}
    try:
        book=xlrd.open_workbook(body,logfile=io.StringIO())
        review['xls_readable']=True
        book.release_resources()
    except Exception as exc:
        review.update(xls_readable=False,xls_error=type(exc).__name__+': '+str(exc))
    return archive_failed_attempt(marker,stopped,station,job,directory,
        'preparación manual tras GET truncado curl 56/HTTP 200; próxima adquisición desde nueva generación, sin solicitudes HTTP',review)

def prepare_wrong_response_retry(config):
    """Archiva una respuesta XLS de otra estación/período; solo lee sus metadatos."""
    marker,stopped,station,job,directory=stopped_job(config,('archivo_invalido',))
    if stopped.get('cause') not in ['Estación XLS inesperada','Rango XLS distinto de solicitud']:
        raise Stop('Esta acción solo admite una discrepancia explícita de estación o período')
    manifest=read(directory/'manifest.json')
    form=f"https://www.ceazamet.cl/index.php?pag=mod_estacion&pag2=mod_estacion_descargas&e_cod={station['e_cod']}&p_cod=ceazamet"
    if manifest['station']!=station['e_cod'] or manifest['fields']!=[list(x) for x in params(station,job)] or manifest['form_url']!=form:
        raise Stop('La solicitud no coincide con la planificación autorizada')
    for phase in ['post','get']:
        headers=(directory/f'{phase}.headers').read_text(errors='replace')
        if re.search(r'^cf-mitigated:\s*challenge',headers,re.I|re.M):
            raise Stop('Desafío del servidor: no se permite preparar reintento')
    response,posted=saved_http(directory,'post')
    data,got=saved_http(directory,'get')
    links=set(re.findall(r'https://www\.ceazamet\.cl/temp/[A-Za-z0-9_-]+\.xls',response.decode('utf8','replace')))
    if posted['url']!=form or len(links)!=1 or got['url'] not in links or manifest['download_url']!=got['url']:
        raise Stop('Procedencia HTTP incompatible con el manifiesto')
    original=directory/'original.xls'
    if sha(original)!=manifest['sha256'] or sha(original)!=got['body_sha256'] or sha(directory/'post.body')!=manifest['generation_sha256']:
        raise Stop('Original o generación alterados')
    if not data.startswith(bytes.fromhex('d0cf11e0a1b11ae1')):
        raise Stop('Respuesta no XLS/OLE; requiere otra revisión')
    book=xlrd.open_workbook(original,logfile=io.StringIO())
    expected_range=f"[{job['start']},{job['end']}]"
    metadata=[]; mismatch=False
    for sheet in book.sheets():
        if sheet.nrows<2 or sheet.ncols<2: raise Stop('Identidad o período no interpretables')
        declared_station=str(sheet.cell_value(0,1)); declared_range=str(sheet.cell_value(1,1))
        if not re.fullmatch(r'\[\d{4}-\d{2}-\d{2},\d{4}-\d{2}-\d{2}\]',declared_range):
            raise Stop('Período declarado no interpretable')
        station_mismatch=norm(declared_station).strip('* ') not in [norm(x).strip('* ') for x in station['xls_names']]
        range_mismatch=declared_range!=expected_range
        mismatch |= station_mismatch or range_mismatch
        metadata.append({'sheet':sheet.name,'declared_station':declared_station,'declared_range':declared_range,
            'station_mismatch':station_mismatch,'range_mismatch':range_mismatch})
    book.release_resources()
    if not mismatch: raise Stop('No hay discrepancia de identidad/período; no se prepara reintento')
    return archive_failed_attempt(marker,stopped,station,job,directory,
        'respuesta de otra estación/período archivada; nueva generación manual del bloque autorizado, sin solicitudes HTTP',
        {'requested_station':station['e_cod'],'requested_range':expected_range,'xls_metadata':metadata,
         'observation_rows_examined':False,'accepted_as_observations':False,
         'incidental_exposure':'solo identidad y rango de un XLS no solicitado; valores de observaciones no leídos'})

def recover_local_interruption(config):
    """Recupera marcadores heredados con causa vacía, solo con adquisición local íntegra."""
    marker,stopped,station,job,directory=stopped_job(config)
    if stopped.get('cause')!='': raise Stop('Esta recuperación solo admite el marcador heredado de causa vacía')
    # Ninguna red: ambos comprobantes HTTP deben acreditar éxito y conservar sus hashes.
    response,posted=saved_http(directory,'post')
    data,got=saved_http(directory,'get')
    manifest=read(directory/'manifest.json')
    links=set(re.findall(r'https://www\.ceazamet\.cl/temp/[A-Za-z0-9_-]+\.xls',response.decode('utf8','replace')))
    if posted['url']!=manifest['form_url'] or len(links)!=1 or got['url'] not in links or manifest['download_url']!=got['url'] or sha(directory/'original.xls')!=got['body_sha256']:
        raise Stop('La adquisición local no coincide con sus comprobantes HTTP')
    previous_verification=(directory/'verificacion.json').read_bytes() if (directory/'verificacion.json').exists() else None
    detail,_=verify(station,job,directory)
    state_path=ROOT/station['slug']/'estado.json'; state=read(state_path)
    archive=ROOT/station['slug']/'interrupciones_locales'/job['id']/uuid.uuid4().hex
    archive.mkdir(parents=True)
    save(archive/'auditoria.json',{'utc':now(),'reason':'marcador heredado de causa vacía; recuperación por verificación local completa, sin red',
        'stopped':stopped,'previous_state':state.get(job['id']),'verification':detail,
        'original_sha256':sha(directory/'original.xls'),'original_moved':False})
    if previous_verification is not None: (archive/'verificacion_previa.json').write_bytes(previous_verification)
    state[job['id']]=detail; save(state_path,state)
    shutil.move(str(marker),str(archive/'DETENIDO.json'))
    print(f"Bloque {station['slug']} {job['id']} recuperado localmente. Marcador conservado en {archive}. Sin solicitudes HTTP.",flush=True)
    return archive

def run(config,mode,selected=None,max_blocks=None):
    if mode=='verificar':
        for station in config['stations']:
            if selected and selected!=station['slug']: continue
            target=ROOT/station['slug']/'derivados'
            integrity=target/'integridad.json'
            if integrity.exists():
                for name,digest in read(integrity).get('tables_sha256',{}).items():
                    if sha(target/name)!=digest: raise Invalid('Tabla derivada alterada: '+str(target/name))
    if mode=='descargar' and (ROOT/'DETENIDO.json').exists(): raise Stop('Existe DETENIDO.json; revisar causa antes de cualquier red')
    processed=0
    for s in config['stations']:
        if selected and selected!=s['slug']: continue
        folder=ROOT/s['slug']; folder.mkdir(exist_ok=True)
        jobs=plan(s); save(folder/'plan.json',jobs); save(folder/'metadatos.json',s)
        state=read(folder/'estado.json') if (folder/'estado.json').exists() else {}
        for j in jobs:
            directory=folder/'originales'/j['id']
            if mode=='plan': state.setdefault(j['id'],{'status':'pendiente'}); continue
            try:
                if (directory/'manifest.json').exists(): detail,_=verify(s,j,directory)
                elif mode=='descargar':
                    if max_blocks is not None and processed>=max_blocks: break
                    detail,_=acquire(s,j,directory,config); processed+=1
                else:
                    state.setdefault(j['id'],{'status':'pendiente'}); continue
                state[j['id']]=detail
                with (folder/'avance.jsonl').open('a') as f: f.write(json.dumps({'utc':now(),'job':j['id'],'status':detail['status']})+'\n')
                print(s['slug'],j['id'],detail['status'],flush=True)
                save(folder/'estado.json',state)
                if j['trial']: save(folder/'prueba.json',{'job':j,'verification':detail})
            except KeyboardInterrupt:
                # Ctrl+C es una pausa del usuario, no un fallo HTTP. Los originales
                # y el estado anterior permanecen; una solicitud parcial se detectará
                # por sus evidencias antes de cualquier nueva solicitud al reanudar.
                state.setdefault(j['id'],{'status':'pendiente'})
                save(folder/'estado.json',state)
                with (folder/'avance.jsonl').open('a') as f:
                    f.write(json.dumps({'utc':now(),'job':j['id'],'status':'interrupcion_usuario'})+'\n')
                print('Interrumpido por el usuario. Evidencia conservada; reanudar con el mismo comando.',flush=True)
                return
            except Exception as exc:
                status='archivo_invalido' if isinstance(exc,Invalid) else 'solicitud_fallida'
                state[j['id']]={'status':status,'cause':str(exc),'utc':now()}; save(folder/'estado.json',state)
                if mode=='descargar': save(ROOT/'DETENIDO.json',{'station':s['slug'],'job':j['id'],**state[j['id']]})
                raise
        for j in jobs: state.setdefault(j['id'],{'status':'pendiente'})
        save(folder/'estado.json',state)
        save(folder/'estado_estacion.json',{'development_status':s['development_status'],'utc':now(),'verified':sum(state[j['id']]['status'].startswith('verificado_') for j in jobs),'pending':sum(state[j['id']]['status']=='pendiente' for j in jobs),'total_blocks':len(jobs)})
        if mode=='descargar' and any(not state[j['id']]['status'].startswith('verificado_') for j in jobs): break


def hourly_grid():
    t=dt.datetime.combine(LOW,dt.time()); end=dt.datetime.combine(HIGH+dt.timedelta(days=1),dt.time())
    while t<end: yield t.strftime('%Y-%m-%d %H:%M:%S'); t+=dt.timedelta(hours=1)

def report(config):
    grid=list(hourly_grid()); grid_set=set(grid); groups=defaultdict(set)
    for t in grid: groups[('ano',t[:4])].add(t); groups[('mes',t[:7])].add(t)
    inia={v:set() for v in VARS}; inia_sources=[]; inia_counts=Counter()
    # SOLO estos 11 archivos; no abrir SQLite ni tablas/informes globales de INIA.
    for year in range(2013,2024):
        p=ROOT.parent/'historico_inia'/'derivados'/f'observaciones_{year}.csv'
        if not p.exists(): raise Invalid('Falta fuente INIA '+str(p))
        inia_sources.append({'path':str(p),'sha256':sha(p)})
        with p.open(newline='',encoding='utf8') as f:
            for r in csv.DictReader(f):
                t=r['fecha_sin_zona']; stamp=dt.datetime.fromisoformat(t)
                if stamp.year!=year or not LOW<=stamp.date()<=HIGH or r['dentro_periodo']!='1': raise Invalid('Fuente INIA fuera de alcance')
                v={'viento_2m':'viento','direccion_2m':'direccion'}.get(r['variable'],r['variable'])
                if v not in VARS: continue
                inia_counts[(v,t)]+=1
                try: avg=float(r['prom']); pct=float(r['porcentaje_datos'])
                except ValueError: continue
                physical = (v=='humedad' and not 0<=avg<=100) or (v=='viento' and avg<0) or (v=='direccion' and not 0<=avg<=360)
                if math.isfinite(avg) and 0<pct<=100 and r['prom_utilizable_revision']=='1' and not physical: inia[v].add(t)
    for (v,t),count in inia_counts.items():
        if count>1: inia[v].discard(t)
    basic=config['basic_predictors']; inia_basic=set.intersection(*(inia[v] for v in basic))
    summary=[]
    for s in config['stations']:
        folder=ROOT/s['slug']; folder.mkdir(exist_ok=True); rows=[]; block_details=[]; states=[]
        saved_state=read(folder/'estado.json') if (folder/'estado.json').exists() else {}
        for j in plan(s):
            d=folder/'originales'/j['id']
            if not (d/'manifest.json').exists(): states.append({'job':j['id'],'status':saved_state.get(j['id'],{}).get('status','pendiente')}); continue
            try: detail,data=verify(s,j,d)
            except Exception as exc:
                states.append({'job':j['id'],'status':'archivo_invalido','cause':str(exc)}); continue
            rows+=data; block_details.append({'job':j['id'],**detail}); states.append({'job':j['id'],'status':detail['status']})
        rows.sort(key=lambda r:(r['fecha_sin_zona'],r['sensor'],r['archivo_original'],r['hoja'],r['fila_excel']))
        day_status={}
        details_by_job={x['job']:x for x in block_details}
        for j,st in zip(plan(s),states):
            a,b=scope(j['start'],j['end'])
            for offset in range((b-a).days+1): day_status[str(a+dt.timedelta(days=offset))]=(st['status'],details_by_job.get(j['id'],{}))
        target=folder/'derivados'; write_csv(target/'horarias.csv',rows,ROW_FIELDS)
        by=defaultdict(list)
        for r in rows: by[(r['sensor'],r['fecha_sin_zona'])].append(r)
        zero_hours={(r['sensor'],r['fecha_sin_zona']) for r in rows if numeric(r['prom']) and r['prom']==0 and r['presente'] and r['fecha_sin_zona'] in grid_set}
        zeros=Counter((sid,t[:7]) for sid,t in zero_hours)
        sets={x['code']:set() for x in s['sensors']}; present={x['code']:set() for x in s['sensors']}
        dup=[]; suspect=[]
        for (sid,t),rs in by.items():
            if any(r['presente'] for r in rs): present[sid].add(t)
            if len(rs)>1: dup.extend(rs)
            elif rs[0]['utilizable_revision']: sets[sid].add(t)
            suspect.extend(r for r in rs if r['problemas'])
        write_csv(target/'duplicados.csv',dup,ROW_FIELDS); write_csv(target/'sospechosos.csv',suspect,ROW_FIELDS)
        coverage=[]; gaps=[]; supports=[]; comparisons=[]; shared_coverage=[]
        available_by_var={v:set() for v in VARS}
        for sensor in s['sensors']:
            sid=sensor['code']; good=sets[sid]; available_by_var[sensor['variable']] |= good
            for (scale,period),hours in sorted(groups.items()): coverage.append({'sensor':sid,'variable':sensor['variable'],'escala':scale,'periodo':period,'esperadas':len(hours),'presentes':len(hours&present[sid]),'utilizables':len(hours&good),'ausentes':len(hours-present[sid]),'presentes_no_utilizables':len((hours&present[sid])-good),'cobertura_pct':100*len(hours&good)/len(hours),'ceros_presentes':sum(n for (zero_sid,month),n in zeros.items() if zero_sid==sid and (month==period if scale=='mes' else month[:4]==period))})
            first=None; last=None; count=0; current_kind=None
            for t in grid+[None]:
                kind=None
                if t is not None and t not in good:
                    status,detail=day_status.get(t[:10],('sin_cobertura_metadatos',{}))
                    if not status.startswith('verificado_'): kind=status
                    elif sid in detail['sensors_absent']: kind='sensor_ausente_encabezado'
                    elif (sid,t) not in by: kind='sin_fila_horaria'
                    elif len(by[(sid,t)])>1: kind='duplicado'
                    elif not any(r['presente'] for r in by[(sid,t)]): kind='sin_observacion_sensor'
                    else: kind='observacion_sospechosa'
                if kind!=current_kind and first is not None:
                    gaps.append({'sensor':sid,'inicio':first,'fin':last,'horas':count,'tipo':current_kind}); first=None; count=0
                current_kind=kind
                if kind is not None:
                    if first is None: first=t
                    last=t; count+=1
            shared=inia[sensor['variable']]&good
            for (scale,period),hours in sorted(groups.items()): shared_coverage.append({'sensor':sid,'variable':sensor['variable'],'escala':scale,'periodo':period,'esperadas':len(hours),'compartidas':len(shared&hours)})
            comparisons.append({'sensor':sid,'variable':sensor['variable'],'inia':len(inia[sensor['variable']]),'complementaria':len(good),'compartidas_por_marca':len(shared),'alineacion_fisica_confirmada':False})
            for t in sorted(shared): supports.append({'fecha_sin_zona':t,'experimento':'variable_inia_mas_sensor','sensor':sid,'predictores':sensor['variable']})
            for t in sorted(inia_basic&good): supports.append({'fecha_sin_zona':t,'experimento':'basico_inia_mas_sensor','sensor':sid,'predictores':','.join(basic)})
        # Conjunto complementario explícito: elegir por configuración, nunca por correlación.
        chosen=s['basic_sensors']; shared_basic=set(inia_basic)
        for sid in chosen: shared_basic &= sets[sid]
        if not chosen: shared_basic=set()
        for t in sorted(shared_basic): supports.append({'fecha_sin_zona':t,'experimento':'basico_inia_mas_estacion','sensor':','.join(chosen),'predictores':','.join(basic)})
        write_csv(target/'cobertura_compartida.csv',shared_coverage,['sensor','variable','escala','periodo','esperadas','compartidas'])
        write_csv(target/'cobertura.csv',coverage,['sensor','variable','escala','periodo','esperadas','presentes','utilizables','ausentes','presentes_no_utilizables','cobertura_pct','ceros_presentes'])
        write_csv(target/'huecos.csv',gaps,['sensor','inicio','fin','horas','tipo'])
        write_csv(target/'soporte_comparaciones.csv',supports,['fecha_sin_zona','experimento','sensor','predictores'])
        save(target/'compatibilidad.json',{'inia_sources':inia_sources,'basic_predictors':basic,'basic_sensors':chosen,'shared_basic_hours':len(shared_basic),'by_sensor':comparisons,'by_variable':{v:len(inia[v]&available_by_var[v]) for v in VARS},'timezone':None,'physical_alignment_confirmed':False,'pressure_reference':s['pressure_reference']})
        schemas=[x['schema'] for x in block_details]
        save(target/'integridad.json',{'tables_sha256':{x.name:sha(x) for x in target.glob('*.csv')},'blocks':block_details,'states':states,'schema_changes':[i for i in range(1,len(schemas)) if schemas[i]!=schemas[i-1]],'external_rows_excluded':sum(len(x['excluded_external_rows']) for x in block_details),'analytic_temporal_limits':[str(LOW),str(HIGH)],'acquisition_complete':all(x['status'].startswith('verificado_') for x in states)})
        summary.append({'station':s['name'],'development_status':('sin_cobertura_en_desarrollo' if s['development_status']=='sin_cobertura_en_desarrollo' else 'adquisicion_completa_requiere_aclaraciones' if all(x['status'].startswith('verificado_') for x in states) else 'adquisicion_parcial' if block_details else 'pendiente_adquisicion'),'blocks_verified':len(block_details),'blocks_pending':sum(x['status']=='pendiente' for x in states),'shared_basic_hours':len(shared_basic),'ready_for_physical_comparison':False})
    save(ROOT/'resumen.json',summary)
    (ROOT/'informe_resultados.md').write_text('# Resultados de adquisición\n\nCoincidencias de marcas sin zona; alineación física no confirmada. No se calculan gradientes ni se entrena.\n\n'+ '\n'.join(f"- {x['station']}: {x['blocks_verified']} bloques verificados; {x['blocks_pending']} pendientes; {x['shared_basic_hours']} horas compartidas del conjunto básico. {x['development_status']}." for x in summary),encoding='utf8')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['plan','descargar','verificar','informar','preparar-reintento-conexion','preparar-reintento-transferencia','preparar-reintento-respuesta','recuperar-interrupcion-local'])
    p.add_argument('--config',type=Path,default=ROOT/'configuracion.json')
    p.add_argument('--estacion'); p.add_argument('--max-bloques',type=int)
    args=p.parse_args(); config=configuration(args.config)
    if args.estacion and args.estacion not in [s['slug'] for s in config['stations']]: p.error('Estación no configurada')
    if args.max_bloques is not None and args.max_bloques<1: p.error('Máximo debe ser positivo')
    if (args.action.startswith('preparar-reintento-') or args.action=='recuperar-interrupcion-local') and (args.estacion or args.max_bloques is not None):
        p.error('La preparación se aplica únicamente al bloque de DETENIDO.json, sin filtros')
    with (ROOT/'.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.action=='preparar-reintento-conexion': prepare_connection_retry(config)
        elif args.action=='preparar-reintento-transferencia': prepare_transfer_retry(config)
        elif args.action=='preparar-reintento-respuesta': prepare_wrong_response_retry(config)
        elif args.action=='recuperar-interrupcion-local': recover_local_interruption(config)
        elif args.action=='informar': report(config)
        else: run(config,args.action,args.estacion,args.max_bloques)

if __name__=='__main__': main()
