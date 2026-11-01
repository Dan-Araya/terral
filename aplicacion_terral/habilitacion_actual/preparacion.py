"""Operaciones independientes de la convención física aún no acreditada.

No convierte marcas originales, calcula probabilidades ni habilita producción.
"""
import datetime as dt
import hashlib
import json
from ..comun import SPECS, HORIZONTES
from ..inferencia import calidad, ventana


def canon(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def marca(value):
    t = dt.datetime.fromisoformat(value)
    if t.tzinfo is not None or t.minute or t.second or t.microsecond:
        raise ValueError('Se exige marca nominal horaria sin zona')
    return t


def utc(value):
    t = dt.datetime.fromisoformat(value)
    if t.utcoffset() != dt.timedelta(0):
        raise ValueError('UTC explícito requerido; no convertir etiquetas originales')
    return t


def ultima_ventana_comun(registros):
    """Registros de la última revisión de cada sensor/marca, nunca versiones mezcladas.

    La selección es nominal: no acredita completitud física, frescura ni elegibilidad.
    Un duplicado se rechaza, incluso si una de sus versiones sería válida.
    """
    index = {}
    for r in registros:
        key = (marca(r['marca_original']), str(r['estacion']), str(r['sensor']))
        if key in index:
            raise ValueError('Revisiones/duplicados sin resolver')
        calidad(r)  # Metadatos estrictos, misma máscara congelada.
        index[key] = r
    valid = {key for key, r in index.items() if calidad(r) is not None}
    candidates = sorted({key[0] for key in valid}, reverse=True)
    for t in candidates:
        keys = [(t-dt.timedelta(hours=k), s, sensor)
                for k in range(6, -1, -1) for s, sensor in SPECS]
        if not all(key in valid for key in keys):
            continue
        records = [index[key] for key in keys]
        ventana(records, t.isoformat())
        return {'referencia_original': t.isoformat(),
                'desde_original': (t-dt.timedelta(hours=6)).isoformat(),
                'referencia_utc': None, 'intervalo_fisico': None,
                'completitud_nominal': True, 'elegible_para_emitir': False,
                'motivo': 'contrato_temporal_no_acreditado', 'registros': records}
    return None


def identidad_candidata(registros, modelo_sha256, horizonte, politica):
    """Clave propuesta por contenido/revisión; una recepción igual no crea emisión.

    La procedencia de cada recepción se conserva separada en el almacén G2.
    Cambiar un valor, revisión, política o modelo cambia la identidad.
    Un XLS contenedor nuevo con las mismas entradas no crea otra identidad.
    No es un registro de emisión: falta cerrar el contrato temporal e integrarlo.
    """
    if horizonte not in HORIZONTES:
        raise ValueError('Horizonte no permitido')
    candidate = ultima_ventana_comun(registros)
    if candidate is None:
        raise ValueError('Sin ventana completa')
    fields = ('estacion', 'sensor', 'variable', 'unidad', 'altura_m', 'marca_original',
              'min', 'prom', 'max', 'porcentaje_datos', 'version', 'contenido_sha256')
    inputs = []
    for r in candidate['registros']:
        entry = {k: r[k] for k in fields if k in r}
        inputs.append(entry)
    payload = dict(modelo_sha256=modelo_sha256, horizonte=horizonte, politica=politica,
                   referencia_original=candidate['referencia_original'], entradas=inputs)
    return hashlib.sha256(canon(payload).encode()).hexdigest()


def clasificar_objetivo(referencia_utc, emision_utc, horizonte):
    """Solo acepta referencia UTC ya acreditada por un futuro adaptador.

    Nunca obtiene UTC desde una marca XLS. No desplaza ni recorta probabilidades.
    Política propuesta: omitir del pronóstico actual todo objetivo ya empezado.
    """
    if horizonte not in HORIZONTES:
        raise ValueError('Horizonte no permitido')
    t, e = utc(referencia_utc), utc(emision_utc)
    end = t + dt.timedelta(hours=horizonte)
    state = ('referencia_futura_invalida' if e < t else
             'vencido' if e >= end else 'parcialmente_transcurrido' if e > t else 'integro')
    return dict(inicio_utc=t.isoformat(), fin_utc=end.isoformat(), emision_utc=e.isoformat(),
                estado=state, mostrar_como_pronostico_actual=state == 'integro')
