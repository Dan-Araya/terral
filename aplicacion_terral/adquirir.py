"""Una comprobación prospectiva manual. Reutiliza request oficial sin tocar ROOT histórico."""
import datetime as dt
import fcntl
import importlib.util
import re
import time
import uuid
from .comun import BASE,ROOT,SENSORES,guardar,sha,leer
TRANSPORTE=ROOT/'investigacion_ceazamet/estaciones_complementarias/gestionar.py'


def campos(station,day):
    if day!=rango(dt.datetime.now(dt.timezone.utc)): raise ValueError('Solo día prospectivo actual')
    if station not in ('6','8'): raise ValueError('Solo INIA/Pisco')
    return [('e_cod',station)]+[('s_cod[]',s[1]) for s in SENSORES if s[0]==station]+[
        ('intervalo','hora'),('formato_archivo','xls'),('fecha_inicio',day),('fecha_fin',day),('accion','generar_informe'),('B1','Enviar')]

def rango(ahora):
    # El formulario solo admite fechas, no límites horarios ni zona.
    # Pedir únicamente el día UTC actual minimiza extensión: 24 etiquetas nominales,
    # subconjunto nominal de las últimas 48 h. No afirma una conversión física.
    if ahora.utcoffset()!=dt.timedelta(0): raise ValueError('Ancla UTC requerida')
    if ahora.year<2026: raise ValueError('No abrir reserva 2024–2025')
    return ahora.date().isoformat()

def pausa(last,minimum):
    time.sleep(max(0,minimum-(time.time()-last)))

def adquirir(nombre="adquisicion_controlada"):
    if not re.fullmatch(r"adquisicion_[a-z0-9_]+",nombre): raise ValueError("Nombre de evidencia inválido")
    evidence=BASE/"evidencia"/nombre
    evidence.mkdir(parents=True,exist_ok=True)
    with (BASE/'evidencia/adquisicion.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        # Una sola ejecución de G1, también ante fallo. Revisión manual para nueva versión.
        if (evidence/'plan.json').exists(): raise SystemExit('Intento G1 ya conservado: no reintentar')
        now=dt.datetime.now(dt.timezone.utc); day=rango(now)
        guardar(evidence/'plan.json',dict(ancla_utc=now.isoformat(),fecha_inicio=day,fecha_fin=day,
            limite_horas_nominal=24,maximo_autorizado_h=48,estaciones=['6','8'],
            limitacion='Formulario por fechas sin zona: día actual según ancla UTC; no equivalencia física confirmada. No se solicitan días anteriores.',
            transporte_sha256=sha(TRANSPORTE),pausa_generacion_descarga_s=10,pausa_bloques_s=15,reintentos=0))
        spec=importlib.util.spec_from_file_location('terral_transporte_oficial',TRANSPORTE)
        transport=importlib.util.module_from_spec(spec); spec.loader.exec_module(transport)
        # ROOT solo de este objeto nuevo: request escribe ultima_solicitud aquí.
        transport.ROOT=evidence
        past=[leer(p).get('finished_epoch',0) for p in (BASE/'evidencia').glob('adquisicion_*/[68]/*.http.json')]
        previous=max(past) if past else None
        for station in ('6','8'):
            if previous is not None: pausa(previous,15)
            directory=evidence/station; directory.mkdir()
            fields=campos(station,day)
            url=f'https://www.ceazamet.cl/index.php?pag=mod_estacion&pag2=mod_estacion_descargas&e_cod={station}&p_cod=ceazamet'
            guardar(directory/'solicitud.json',dict(estacion=station,campos=fields,adquisicion_inicio_utc=transport.now()))
            boundary='----TerralG1'+uuid.uuid4().hex
            payload=(''.join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k,v in fields)+f'--{boundary}--\r\n').encode()
            try:
                body,posted=transport.request(url,directory,'post',{},payload,'multipart/form-data; boundary='+boundary)
                links=set(re.findall(r'https://www\.ceazamet\.cl/temp/[A-Za-z0-9_-]+\.xls',body.decode('utf8','replace')))
                if len(links)!=1: raise transport.Stop('Generación sin enlace XLS inequívoco')
                pausa(posted['finished_epoch'],10)
                data,got=transport.request(next(iter(links)),directory,'get',{})
                (directory/'original.xls').write_bytes(data)
                guardar(directory/'resultado.json',dict(estado='adquirido_pendiente_contrato',sha256=sha(directory/'original.xls'),adquisicion_utc=got['finished_utc']))
            except transport.Stop as e:
                guardar(directory/'resultado.json',dict(estado='fallo_adquisicion',detalle=str(e),adquisicion_utc=transport.now(),observaciones_ausentes=None))
                # Un bloqueo/límite detiene toda la comprobación; no probar otra estación.
                limited=False
                for phase in ('post','get'):
                    if (directory/f'{phase}.http.json').exists():
                        info=leer(directory/f'{phase}.http.json')
                        headers=(directory/f'{phase}.headers').read_text().lower()
                        limited |= info['http_status'] in ('403','429') or 'retry-after:' in headers
                if limited or 'límite' in str(e) or 'Control' in str(e): break
            previous=time.time()
        files={str(p.relative_to(evidence)):sha(p) for p in evidence.rglob('*') if p.is_file() and p.name!='manifiesto.json'}
        guardar(evidence/'manifiesto.json',files)
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('--evidencia',default='adquisicion_controlada')
    adquirir(parser.parse_args().evidencia)
