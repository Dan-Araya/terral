"""Adaptación del lector estricto G1 a un bloque independiente, sin efectos G1."""
import datetime as dt
import io
import re
import xlrd
from ..comun import SENSORES, leer, sha
from ..normalizar_actual import LABELS, FIELDS, reparar


def exigir(condition, message):
    if not condition:
        raise ValueError(message)


def bloque(folder, station, day):
    p = folder / 'original.xls'
    result = leer(folder / 'resultado.json')
    exigir(sha(p) == result['sha256'], 'Original alterado')
    request = leer(folder / 'solicitud.json')
    expected = [s for s in SENSORES if s[0] == station]
    exigir(request['estacion'] == station, 'Estación de solicitud incompatible')
    exigir([v for k, v in request['campos'] if k == 's_cod[]'] == [s[1] for s in expected], 'Sensores incompatibles')
    fields = dict(request['campos'])
    exigir(fields['fecha_inicio'] == fields['fecha_fin'] == day and fields['intervalo'] == 'hora', 'Rango incompatible')
    http = leer(folder / 'get.http.json')
    exigir(http['http_status'] == '200' and http['curl_exit'] == 0 and sha(folder/'get.body') == http['body_sha256'] == sha(p), 'HTTP/original incompatible')
    book = xlrd.open_workbook(p, logfile=io.StringIO())
    exigir(len(book.sheets()) == 1, 'Esquema no previsto')
    sheet = book.sheet_by_index(0)
    exigir(sheet.cell_value(0, 1) == {'6': 'Vicuña', '8': 'Pisco Elqui'}[station], 'Identidad XLS incompatible')
    exigir(sheet.cell_value(1, 1) == f'[{day},{day}]', 'Rango XLS incompatible')
    columns = {}
    for col in range(1, sheet.ncols):
        raw = sheet.cell_value(3, col)
        label = re.sub(r'(?:Ã.|Â.)+', lambda m: reparar(m.group()), raw)
        match = re.fullmatch(r'\[(Min|Prom|Max|%Datos)\]\s*(.*?)\[([\d.]+)m\]', label)
        exigir(match is not None, 'Encabezado inesperado')
        field, desc, height = match.groups()
        matches = [s for s in expected if float(height) == s[4] and desc == ('' if field == '%Datos' else s[3]+' ') + LABELS[s[2]]]
        exigir(len(matches) == 1, 'Identidad/altura/unidad ambigua')
        key = (matches[0][1], FIELDS[field])
        exigir(key not in columns, 'Campo duplicado')
        columns[key] = col
    exigir(set(columns) == {(s[1], f) for s in expected for f in FIELDS.values()}, 'Campos incompletos')
    records, seen = [], set()
    for row in range(4, sheet.nrows):
        label = sheet.cell_value(row, 0)
        if not isinstance(label, str) or not re.fullmatch(r'\d{4}-\d\d-\d\d \d\d:00:00', label):
            continue
        stamp = dt.datetime.fromisoformat(label)
        exigir(stamp.date().isoformat() == day and label not in seen, 'Marca duplicada/fuera de rango')
        seen.add(label)
        for s in expected:
            values = {f: sheet.cell_value(row, columns[s[1], f]) for f in FIELDS.values()}
            for field, value in values.items():
                exigir(value == '' or sheet.cell_type(row, columns[s[1], field]) == xlrd.XL_CELL_NUMBER, 'Tipo XLS incompatible')
            records.append(dict(estacion=station, sensor=s[1], variable=s[2], unidad=s[3], altura_m=s[4],
                marca_original=label, **values, adquisicion_utc=http['finished_utc'],
                procedencia=dict(sha256_original=sha(p), hoja=sheet.name, fila_excel=row+1)))
    exigir(len(seen) == 24, 'Se esperaban 24 etiquetas horarias')
    return records
