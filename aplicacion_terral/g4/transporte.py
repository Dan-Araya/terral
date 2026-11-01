"""Transporte G1/G2 extraído sin cambios; procedencia en transporte_origen.json."""

import datetime as dt
import re
import json
import hashlib
import subprocess
import time
from pathlib import Path
ROOT=Path(__file__).parent

class Stop(Exception): pass

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def save(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(p)

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
