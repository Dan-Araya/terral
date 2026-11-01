#!/usr/bin/env python3
"""Vicuña–INIA exclusivamente: descargar, estado o reconstruir. Python3/curl/xlrd.

Sin reintentos de red. Toda respuesta y XLS se conservan antes de interpretar.
Fechas originales sin zona. No calcula etiquetas de terral.
"""
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
import sqlite3
import subprocess
import sys
import time
import unicodedata
import uuid
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo

import xlrd

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
sys.path.insert(0, str(PROJECT))
from descargar_vicuna import FORM, SENSORS

SPECS = {
    "39": ("temperatura", "Temperatura del Aire", "°C", 2, -50, 60),
    "40": ("humedad", "Humedad Relativa", "%", 2, 0, 100),
    "36": ("viento_2m", "Velocidad de Viento", "m/s", 2, 0, 75),
    "37": ("direccion_2m", "Dirección de viento", "°", 2, 0, 360),
    "VCNPA": ("presion", "Presión Atmosférica", "hPa", 2, 800, 1100),
    "VCNVV5": ("viento_5m", "Velocidad de Viento", "m/s", 5, 0, 75),
    "VCNDV5": ("direccion_5m", "Dirección de viento", "°", 5, 0, 360),
}
MAIN = ["39", "40", "36", "37"]
ALL = list(SPECS)
FIELDS = ["min", "prom", "max", "porcentaje_datos"]
FORMAT = "%Y-%m-%d %H:%M:%S"
START = dt.date(2004, 1, 31)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def atomic_json(path, data):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def event(kind, **kwargs):
    with (ROOT / "avance.jsonl").open("a") as f:
        f.write(json.dumps({"utc": now(), "tipo": kind, **kwargs}, ensure_ascii=False) + "\n")


def connect():
    db = sqlite3.connect(ROOT / "historico.sqlite")
    db.executescript("""
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, spec TEXT, status TEXT DEFAULT 'pendiente', detail TEXT);
    CREATE TABLE IF NOT EXISTS observations(job TEXT, timestamp TEXT, sensor TEXT, min_original TEXT,
      prom_original TEXT, max_original TEXT, pct_original TEXT, promedio REAL, cobertura REAL,
      usable INTEGER, numeric_mean INTEGER, zero_mean INTEGER, in_scope INTEGER, sheet TEXT,
      row_excel INTEGER, height_original TEXT, units_original TEXT, flags TEXT,
      PRIMARY KEY(job,sheet,row_excel,sensor));
    CREATE INDEX IF NOT EXISTS obs_time ON observations(timestamp,sensor);
    CREATE TABLE IF NOT EXISTS dates(job TEXT, timestamp TEXT, row_excel INTEGER, in_scope INTEGER);
    CREATE TABLE IF NOT EXISTS issues(job TEXT, row_excel INTEGER, timestamp TEXT, sensor TEXT, issue TEXT, detail TEXT);
    """)
    return db


def chunks(start, end):
    while start <= end:
        last = min(start + dt.timedelta(days=6), end)
        yield start, last
        start = last + dt.timedelta(days=1)


def prepare(db):
    config_path = ROOT / "configuracion.json"
    if not config_path.exists():
        execution = dt.datetime.now(ZoneInfo("America/Santiago"))
        end = execution.date() - dt.timedelta(days=1)
        config = {"station": "6", "start": str(START), "end": str(end), "created_utc": now(),
                  "execution_timezone": "America/Santiago", "timestamps_timezone": None,
                  "published_reference": "GMT-4, historia/inicio/cierre pendientes",
                  "pause_post_get_seconds": 10, "pause_blocks_seconds": 15}
        atomic_json(config_path, config)
    config = json.loads(config_path.read_text())
    assert config["station"] == "6" and config["start"] == str(START)
    if db.execute("SELECT count(*) FROM jobs").fetchone()[0]:
        return config
    end = dt.date.fromisoformat(config["end"])
    jobs = []
    # Se reutilizan las cinco consultas verificadas del piloto. Las dos alturas
    # opcionales se solicitan por separado, sin redescargar sus sensores principales.
    imported = []
    for source in sorted((PROJECT / "piloto_2025_07").glob("*_original.xls")):
        manifest = json.loads(source.with_suffix(".manifest.json").read_text())
        if sha(source) != manifest["sha256"]:
            raise ValueError(f"Original del piloto alterado: {source}")
        fields = manifest["fields"]
        first, last = (dt.date.fromisoformat(dict(fields)[k]) for k in ("fecha_inicio", "fecha_fin"))
        if START <= first <= last <= end:
            imported.append((first, last, source, manifest))
    # La muestra anterior cubre 1–6 octubre por completo, aunque su petición
    # original incluía el día 7. Se conserva toda y se marca fuera de alcance
    # cada observación posterior al corte, sin descartarla de las tablas originales.
    sample = PROJECT / "muestra/vicuna_2026-10-01_2026-10-07_original.xls"
    if sample.exists() and end >= dt.date(2026, 10, 6):
        valid = json.loads(sample.with_suffix(".validacion.json").read_text())
        if sha(sample) != valid["sha256"]:
            raise ValueError("Muestra original alterada")
        fields = [("e_cod", "6")] + [("s_cod[]", s) for s in ALL]
        fields += [("intervalo", "hora"), ("formato_archivo", "xls"), ("fecha_inicio", "2026-10-01"), ("fecha_fin", "2026-10-07"), ("accion", "generar_informe"), ("B1", "Enviar")]
        manifest = {"station": "6", "sha256": sha(sample), "fields": fields, "form_url": FORM,
                    "downloaded_utc": "2026-10-08T00:24:35+00:00", "acquisition_time_source": "fecha de generación del XLS y cabeceras guardadas en evidencia; instante exacto de GET no registrado",
                    "download_url": "https://www.ceazamet.cl/temp/1791419075down.xls", "bytes": sample.stat().st_size}
        imported.append((dt.date(2026, 10, 1), min(end, dt.date(2026, 10, 6)), sample, manifest))
    cursor = START
    for first, last, source, manifest in sorted(imported):
        for a, b in chunks(cursor, first - dt.timedelta(days=1)):
            jobs.append({"start": str(a), "end": str(b), "sensors": ALL, "role": "completo"})
        jobs.append({"start": str(first), "end": str(last), "sensors": [v for k, v in manifest["fields"] if k == "s_cod[]"],
                     "role": "reutilizado", "import_source": str(source), "import_manifest": manifest})
        missing_optional = [s for s in ALL if s not in jobs[-1]["sensors"]]
        if missing_optional:
            jobs.append({"start": str(first), "end": str(last), "sensors": missing_optional, "role": "opcionales"})
        cursor = last + dt.timedelta(days=1)
    for a, b in chunks(cursor, end):
        jobs.append({"start": str(a), "end": str(b), "sensors": ALL, "role": "completo"})
    for job in jobs:
        job["id"] = f'{job["start"]}_{job["end"]}_{job["role"]}'
        db.execute("INSERT INTO jobs(id,spec) VALUES(?,?)", (job["id"], json.dumps(job, ensure_ascii=False)))
    db.commit()
    atomic_json(ROOT / "plan.json", [{k: v for k, v in j.items() if k != "import_manifest"} for j in jobs])
    return config


def normalized(text):
    # Solo para reconocer encabezados; nunca se modifica el original guardado.
    def repair(match):
        try:
            return match.group().encode("latin1").decode("utf-8")
        except (UnicodeError, ValueError):
            return match.group()
    text = re.sub(r"(?:Ã.|Â.)+", repair, text)
    return "".join(c for c in unicodedata.normalize("NFD", text).lower() if not unicodedata.combining(c))


def number(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def verify_file(db, job, directory, config):
    path = directory / "original.xls"
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest["station"] != "6" or sha(path) != manifest["sha256"]:
        raise ValueError("Identidad o hash de original incorrectos")
    params = dict(manifest["fields"])
    if params["e_cod"] != "6" or params["intervalo"] != "hora":
        raise ValueError("Parámetros fuera del alcance")
    if [v for k, v in manifest["fields"] if k == "s_cod[]"] != job["sensors"]:
        raise ValueError("Sensores del manifiesto y planificación incompatibles")
    warnings = io.StringIO()
    book = xlrd.open_workbook(path, logfile=warnings)
    sheet = book.sheet_by_index(0)
    if normalized(str(sheet.cell_value(0, 1))) != "vicuna":
        raise ValueError("Respuesta XLS de otra estación o sin identidad de Vicuña")
    expected_range = f'[{params["fecha_inicio"]},{params["fecha_fin"]}]'
    if sheet.cell_value(1,1) != expected_range:
        raise ValueError("Período declarado en el XLS distinto del solicitado: respuesta inválida, no período sin datos")
    headers = sheet.row_values(3)
    columns, schema = {}, []
    for col in range(1, sheet.ncols):
        raw = str(headers[col])
        match = re.fullmatch(r"\[(Min|Prom|Max|%Datos)\]\s*(.*?)\[([\d.]+)m\]", raw)
        if not match:
            raise ValueError(f"Encabezado no reconocido: {raw!r}")
        field, descriptor, height = match.groups()
        matches = [sid for sid, spec in SPECS.items() if normalized(spec[1]) in normalized(descriptor) and float(height) == spec[3]]
        if len(matches) != 1:
            raise ValueError(f"Sensor/altura ambiguos: {raw!r}")
        sid = matches[0]
        if sid not in job["sensors"]:
            raise ValueError("XLS contiene sensor no solicitado")
        field = {"Min": "min", "Prom": "prom", "Max": "max", "%Datos": "porcentaje_datos"}[field]
        unit = "%" if field == "porcentaje_datos" else SPECS[sid][2]
        if field != "porcentaje_datos" and not descriptor.startswith(unit + " "):
            raise ValueError(f"Cambio de unidad no interpretable: {raw}")
        if field in columns.setdefault(sid, {}):
            raise ValueError("Campo de sensor duplicado en encabezados")
        columns[sid][field] = col
        schema.append({"sensor": sid, "campo": field, "columna_excel": col + 1, "encabezado_original": raw,
                       "unidad_original": unit, "altura_encabezado_m": height})
    if not columns or any(set(fields) != set(FIELDS) for fields in columns.values()):
        raise ValueError("Esquema incompleto o sin sensores reconocidos")
    observations, dates, issues = [], [], []
    low = str(job["start"]) + " 00:00:00"
    high = str(dt.date.fromisoformat(job["end"]) + dt.timedelta(days=1)) + " 00:00:00"
    global_low, global_high = config["start"] + " 00:00:00", str(dt.date.fromisoformat(config["end"]) + dt.timedelta(days=1)) + " 00:00:00"
    stamps = []
    for i in range(4, sheet.nrows):
        row = sheet.row_values(i)
        label = str(row[0])
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", label):
            if any(x != "" for x in row) and label not in ("Más información:", "Fecha Generación:"):
                issues.append((job["id"], i + 1, label, "", "fila_no_interpretada", json.dumps(row, ensure_ascii=False)))
            continue
        stamp = dt.datetime.strptime(label, FORMAT)
        in_scope = int(low <= label < high and global_low <= label < global_high)
        stamps.append(label)
        dates.append((job["id"], label, i + 1, in_scope))
        if not in_scope:
            issues.append((job["id"], i + 1, label, "", "fuera_periodo_efectivo", label))
        if stamp.minute or stamp.second:
            issues.append((job["id"], i + 1, label, "", "fuera_rejilla_horaria", label))
        for sid, fields in columns.items():
            values = [row[fields[f]] for f in FIELDS]
            cell_types = [sheet.cell_type(i, fields[f]) for f in FIELDS]
            minimum, average, maximum, pct = values
            flags = []
            for field, value, cell_type in zip(FIELDS, values, cell_types):
                if value != "" and not number(value):
                    flags.append(field + ":no_numerico_o_no_finito")
                if value != "" and cell_type != xlrd.XL_CELL_NUMBER:
                    flags.append(field + f":tipo_original_{cell_type}_valor_{value}")
            if number(pct) and not 0 <= pct <= 100:
                flags.append("cobertura_fuera_0_100")
            if all(number(x) for x in values[:3]) and not minimum <= average <= maximum:
                flags.append("min_prom_max_inconsistente")
            _, _, unit, height, lower, upper = SPECS[sid]
            if number(average) and not lower <= average <= upper:
                flags.append("promedio_fuera_rango_revision")
            numeric_average = number(average) and cell_types[1] == xlrd.XL_CELL_NUMBER
            numeric_coverage = number(pct) and cell_types[3] == xlrd.XL_CELL_NUMBER
            usable = int(numeric_average and numeric_coverage and 0 < pct <= 100 and lower <= average <= upper and stamp.minute == 0 and stamp.second == 0)
            for flag in flags:
                issues.append((job["id"], i + 1, label, sid, flag, json.dumps(values, ensure_ascii=False)))
            observations.append((job["id"], label, sid, *[json.dumps(v, ensure_ascii=False) for v in values],
                                 average if numeric_average else None, pct if numeric_coverage else None,
                                 usable, int(numeric_average), int(numeric_average and average == 0),
                                 in_scope, sheet.name, i + 1, str(height), unit, json.dumps(flags)))
    for label, count in Counter(stamps).items():
        if count > 1:
            issues.append((job["id"], 0, label, "", "marca_duplicada_en_xls", str(count)))
    status = "verificado_con_datos" if any(o[7] is not None for o in observations if o[12]) else "verificado_sin_datos"
    detail = {"id": job["id"], "status": status, "sha256": manifest["sha256"], "biff_version": book.biff_version,
              "schema": schema, "schema_hash": hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest(),
              "sensors_present": list(columns), "sensors_absent": [s for s in job["sensors"] if s not in columns],
              "dated_rows": len(dates), "rows_in_scope": sum(d[3] for d in dates), "issues": len(issues),
              "warnings_xlrd": warnings.getvalue(), "verified_utc": now(),
              "original_path": str(path.relative_to(ROOT)), "sorted_original": stamps == sorted(stamps)}
    with db:
        for table in ("observations", "dates", "issues"):
            db.execute(f"DELETE FROM {table} WHERE job=?", (job["id"],))
        db.executemany("INSERT INTO observations VALUES(" + ",".join("?" * 18) + ")", observations)
        db.executemany("INSERT INTO dates VALUES(?,?,?,?)", dates)
        db.executemany("INSERT INTO issues VALUES(?,?,?,?,?,?)", issues)
        db.execute("UPDATE jobs SET status=?,detail=? WHERE id=?", (status, json.dumps(detail, ensure_ascii=False), job["id"]))
    atomic_json(directory / "verificacion.json", detail)
    return detail


class DownloadStop(Exception):
    pass


def request(url, directory, phase, config, data=None, content_type=None):
    if not re.fullmatch(r"https://www\.ceazamet\.cl/(index\.php\?.*|temp/[A-Za-z0-9_-]+\.xls)", url):
        raise DownloadStop("Destino fuera de endpoints oficiales autorizados")
    body, headers_path = directory / f"{phase}.body", directory / f"{phase}.headers"
    command = ["curl", "--silent", "--show-error", "--max-time", "60", "--dump-header", str(headers_path),
               "--output", str(body), "--write-out", "%{http_code}"]
    if data is not None:
        payload = directory / "parametros.multipart"
        payload.write_bytes(data)
        command += ["--header", "Content-Type: " + content_type, "--data-binary", "@" + str(payload)]
    began = now()
    result = subprocess.run(command + [url], capture_output=True, text=True)
    headers = headers_path.read_text() if headers_path.exists() else ""
    headers = "\n".join(line for line in headers.splitlines() if not line.lower().startswith("set-cookie:"))
    headers_path.write_text(headers)
    detail = {"phase": phase, "url": url, "started_utc": began, "finished_utc": now(),
              "curl_exit": result.returncode, "http_status": result.stdout, "stderr": result.stderr,
              "body_sha256": sha(body) if body.exists() else None}
    atomic_json(directory / f"{phase}.http.json", detail)
    # Persistir fin de última solicitud para respetar pausa también al reanudar.
    atomic_json(ROOT / "ultima_solicitud.json", {"finished_epoch": time.time(), **detail})
    if result.returncode or result.stdout != "200":
        raise DownloadStop(f'{phase}: curl={result.returncode}, HTTP={result.stdout}; {result.stderr.strip()}')
    if "retry-after:" in headers.lower():
        raise DownloadStop("Servidor anuncia Retry-After; descarga detenida")
    return body.read_bytes()


def download_one(db, job, config):
    directory = ROOT / "originales" / job["id"]
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "original.xls").exists() and (directory / "manifest.json").exists():
        # Una interrupción después del GET solo necesita verificación local.
        return verify_file(db, job, directory, config)
    if job.get("import_source"):
        shutil.copyfile(job["import_source"], directory / "original.xls")
        manifest = dict(job["import_manifest"])
        manifest.update({"import_source": job["import_source"], "imported_utc": now(), "effective_start": job["start"], "effective_end": job["end"]})
        atomic_json(directory / "manifest.json", manifest)
        return verify_file(db, job, directory, config)
    if (directory / "get.http.json").exists():
        acquired = json.loads((directory / "get.http.json").read_text())
        body = directory / "get.body"
        if acquired["curl_exit"] == 0 and acquired["http_status"] == "200" and body.exists() and sha(body) == acquired["body_sha256"] and body.read_bytes().startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
            # Recuperación de un GET exitoso cuyo procesamiento local se interrumpió.
            shutil.copyfile(body, directory / "original.xls")
            manifest = json.loads((directory / "adquisicion.json").read_text())
            manifest.update({"download_url": acquired["url"], "downloaded_utc": acquired["finished_utc"],
                             "sha256": sha(body), "bytes": body.stat().st_size, "status": "adquirido", "recovered_locally_utc": now()})
            atomic_json(directory / "manifest.json", manifest)
            return verify_file(db, job, directory, config)
        raise DownloadStop("GET previo fallido o incompleto: no se reintenta automáticamente")
    if (directory / "post.http.json").exists():
        posted = json.loads((directory / "post.http.json").read_text())
        if posted["curl_exit"] or posted["http_status"] != "200":
            raise DownloadStop("POST previo fallido: no se reintenta automáticamente")
        # Se puede proseguir únicamente un GET que nunca se intentó.
        response = (directory / "post.body").read_bytes()
        links = re.findall(r"https://www\.ceazamet\.cl/temp/[A-Za-z0-9_-]+\.xls", response.decode("utf-8", "replace"))
        if not links:
            raise DownloadStop("POST previo sin enlace válido: no se repite")
        last_time = dt.datetime.fromisoformat(posted["finished_utc"]).timestamp()
        time.sleep(max(0, config["pause_post_get_seconds"] - (time.time() - last_time)))
        data = request(links[0],directory,"get",config)
        if not data.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
            raise DownloadStop("GET de continuación no contiene XLS/OLE")
        shutil.copyfile(directory / "get.body", directory / "original.xls")
        manifest = json.loads((directory / "adquisicion.json").read_text())
        manifest.update({"download_url": links[0], "downloaded_utc": now(), "sha256": sha(directory / "original.xls"),
                         "bytes": len(data), "status": "adquirido", "resumed_get_only": True})
        atomic_json(directory / "manifest.json",manifest)
        return verify_file(db,job,directory,config)
    last_path = ROOT / "ultima_solicitud.json"
    if last_path.exists():
        remaining = config["pause_blocks_seconds"] - (time.time() - json.loads(last_path.read_text())["finished_epoch"])
        if remaining > 0:
            time.sleep(remaining)
    fields = [("e_cod", "6")] + [("s_cod[]", s) for s in job["sensors"]]
    fields += [("intervalo", "hora"), ("formato_archivo", "xls"), ("fecha_inicio", job["start"]), ("fecha_fin", job["end"]), ("accion", "generar_informe"), ("B1", "Enviar")]
    manifest = {"station": "6", "form_url": FORM, "fields": fields, "started_utc": now(), "status": "iniciado",
                "pause_post_get_seconds": 10, "pause_blocks_seconds": 15}
    atomic_json(directory / "adquisicion.json", manifest)
    boundary = "----Vicuna" + uuid.uuid4().hex
    multipart = "".join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k, v in fields) + f"--{boundary}--\r\n"
    response = request(FORM, directory, "post", config, multipart.encode(), "multipart/form-data; boundary=" + boundary)
    links = re.findall(r"https://www\.ceazamet\.cl/temp/[A-Za-z0-9_-]+\.xls", response.decode("utf-8", "replace"))
    if not links:
        raise DownloadStop("Respuesta inválida: formulario sin enlace XLS. No se trata como período sin datos")
    time.sleep(config["pause_post_get_seconds"])
    data = request(links[0], directory, "get", config)
    if not data.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
        raise DownloadStop("Respuesta inválida: el GET no contiene un XLS/OLE")
    # original.xls es copia exacta de get.body, que permanece como evidencia.
    (directory / "original.xls").write_bytes(data)
    manifest.update({"download_url": links[0], "downloaded_utc": now(), "sha256": sha(directory / "original.xls"),
                     "bytes": len(data), "status": "adquirido"})
    atomic_json(directory / "manifest.json", manifest)
    return verify_file(db, job, directory, config)


def progress(db, config):
    states = dict(db.execute("SELECT status,count(*) FROM jobs GROUP BY status"))
    result = {"updated_utc": now(), "start": config["start"], "end": config["end"], "jobs": states,
              "observations": db.execute("SELECT count(*) FROM observations").fetchone()[0],
              "download_stop": json.loads((ROOT / "DETENIDO.json").read_text()) if (ROOT / "DETENIDO.json").exists() else None}
    atomic_json(ROOT / "estado.json", result)
    return result


def download_all(db, config):
    if (ROOT / "DETENIDO.json").exists():
        raise DownloadStop("Existe DETENIDO.json. No se reintenta ni se eluden controles; revisar la causa")
    # Revalidar los hashes en disco antes de omitir tareas.
    for job_id, detail in db.execute("SELECT id,detail FROM jobs WHERE status LIKE 'verificado_%'").fetchall():
        d = json.loads(detail)
        if sha(ROOT / d["original_path"]) != d["sha256"]:
            raise DownloadStop(f"Hash alterado del bloque {job_id}")
    jobs = db.execute("SELECT spec FROM jobs WHERE status='pendiente' ORDER BY json_extract(spec,'$.start'), CASE json_extract(spec,'$.role') WHEN 'reutilizado' THEN 0 WHEN 'completo' THEN 1 ELSE 2 END").fetchall()
    # Importar fuentes locales primero, sin tráfico ni cambios en el orden de las solicitudes.
    jobs.sort(key=lambda row: not bool(json.loads(row[0]).get("import_source")))
    for (encoded,) in jobs:
        job = json.loads(encoded)
        try:
            detail = download_one(db, job, config)
            event("verificado", job=job["id"], status=detail["status"], sensors_absent=detail["sensors_absent"])
            state = progress(db, config)
            verified = sum(v for k, v in state["jobs"].items() if k.startswith("verificado_"))
            print(f'{verified}/{sum(state["jobs"].values())}: {job["id"]} {detail["status"]}', flush=True)
            if verified % 20 == 0:
                rebuild_reports(db, config, export=False)
        except Exception as exc:
            stopped = {"utc": now(), "job": job["id"], "cause": str(exc), "type": type(exc).__name__, "automatic_retry": False}
            atomic_json(ROOT / "DETENIDO.json", stopped)
            with db:
                db.execute("UPDATE jobs SET status='error_descarga',detail=? WHERE id=?", (json.dumps(stopped, ensure_ascii=False), job["id"]))
            event("detenido", **stopped)
            progress(db, config)
            print("DETENIDO: " + str(exc), flush=True)
            break
    rebuild_reports(db, config, export=True)


def csv_query(path, headers, cursor):
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(cursor)
    temporary.replace(path)


def rebuild_reports(db, config, export=True):
    derived = ROOT / "derivados"
    derived.mkdir(exist_ok=True)
    low = dt.datetime.combine(dt.date.fromisoformat(config["start"]), dt.time())
    high = dt.datetime.combine(dt.date.fromisoformat(config["end"]) + dt.timedelta(days=1), dt.time())
    expected = int((high - low).total_seconds() / 3600)
    # Agrupar a nivel sensor/hora antes de contar cobertura: duplicados explícitos.
    entries = db.execute("""SELECT timestamp,sensor,count(*),max(numeric_mean),max(usable),max(zero_mean),
      sum(CASE WHEN prom_original='""' THEN 1 ELSE 0 END), min(cobertura),max(cobertura)
      FROM observations WHERE in_scope=1 GROUP BY timestamp,sensor ORDER BY timestamp,sensor""").fetchall()
    indexed = {(r[0], r[1]): r for r in entries}
    valid_primary = 0
    valid_months = Counter()
    stats = {}
    missing_rows, duplicate_rows = [], []
    stamp = low
    recovered_dates = {r[0] for r in db.execute("SELECT DISTINCT timestamp FROM dates WHERE in_scope=1")}
    main_acquired = set()
    requested_acquired = {s: set() for s in ALL}
    absent_header = {s: set() for s in ALL}
    jobs = db.execute("SELECT id,spec,status,detail FROM jobs ORDER BY id").fetchall()
    present_schema = {}
    schema_rows = []
    for job_id, encoded, status, detail in jobs:
        job = json.loads(encoded)
        if not status.startswith("verificado_"):
            continue
        detail = json.loads(detail)
        present_schema[job_id] = detail["sensors_present"]
        first, last = dt.datetime.fromisoformat(job["start"]), dt.datetime.fromisoformat(job["end"]) + dt.timedelta(days=1)
        labels = [(first + dt.timedelta(hours=i)).strftime(FORMAT) for i in range(int((last-first).total_seconds()/3600))]
        for sensor in job["sensors"]:
            requested_acquired[sensor].update(labels)
            if sensor not in detail["sensors_present"]:
                absent_header[sensor].update(labels)
        if any(s in MAIN for s in job["sensors"]):
            first, last = dt.datetime.fromisoformat(job["start"]), dt.datetime.fromisoformat(job["end"]) + dt.timedelta(days=1)
            main_acquired.update((first + dt.timedelta(hours=i)).strftime(FORMAT) for i in range(int((last-first).total_seconds()/3600)))
        for col in detail["schema"]:
            schema_rows.append([job_id, detail["schema_hash"], detail["biff_version"], col["sensor"], col["campo"], col["columna_excel"], col["encabezado_original"], col["unidad_original"], col["altura_encabezado_m"], detail["original_path"]])
    while stamp < high:
        label = stamp.strftime(FORMAT)
        ym = stamp.strftime("%Y-%m")
        unique_good = all((r := indexed.get((label, s))) is not None and r[2] == 1 and r[4] for s in MAIN)
        if unique_good:
            valid_primary += 1
            valid_months[ym] += 1
        for s in ALL:
            metric = stats.setdefault((ym, s), Counter())
            metric["expected"] += 1
            metric["requested_acquired"] += int(label in requested_acquired[s])
            metric["absent_header"] += int(label in absent_header[s])
            r = indexed.get((label, s))
            if r:
                metric["timestamps"] += 1
                metric["numeric"] += int(r[3])
                metric["usable"] += int(r[4] and r[2] == 1)
                metric["zeros"] += int(r[5])
                metric["absent_values"] += int(r[6] > 0)
                metric["duplicates"] += max(r[2] - 1, 0)
                metric["partial_coverage"] += int(r[7] is not None and 0 < r[7] < 100)
                metric["zero_coverage"] += int(r[8] == 0)
            elif label in requested_acquired[s]:
                metric["missing_acquired"] += 1
            else:
                metric["pending"] += 1
        if export and label not in recovered_dates:
            missing_rows.append([label, "sin_fila_en_bloque_recuperado" if label in main_acquired else "pendiente_descarga"])
        stamp += dt.timedelta(hours=1)
    monthly = []
    annual = {}
    metric_keys = ["expected", "timestamps", "numeric", "usable", "zeros", "absent_values", "duplicates", "partial_coverage", "zero_coverage", "missing_acquired", "pending", "requested_acquired", "absent_header"]
    for (ym, sensor), m in sorted(stats.items()):
        monthly.append([ym, sensor, SPECS[sensor][0], *[m[k] for k in metric_keys], round(100*m["usable"]/m["expected"], 5), valid_months[ym]])
        annual.setdefault((ym[:4], sensor), Counter()).update(m)
    annual_rows = [[year, sensor, SPECS[sensor][0], *[m[k] for k in metric_keys], round(100*m["usable"]/m["expected"], 5)] for (year, sensor), m in sorted(annual.items())]
    stat_headers = ["periodo", "sensor", "variable", "horas_esperadas", "marcas_presentes", "promedios_numericos", "horas_utilizables_sin_duplicados", "ceros_prom_observados", "horas_con_prom_ausente", "registros_duplicados_extra", "horas_cobertura_parcial", "horas_cobertura_cero", "sin_observacion_en_periodo_recuperado", "horas_pendientes_descarga", "horas_solicitud_verificada", "horas_sensor_ausente_encabezado", "porcentaje_utilizable_esperado"]
    csv_query(derived / "cobertura_mensual_sensor.csv", stat_headers + ["horas_cuatro_principales_utilizables"], monthly)
    csv_query(derived / "cobertura_anual_sensor.csv", stat_headers, annual_rows)
    acquired_months = Counter(label[:7] for label in main_acquired)
    core_months, core_years = [], {}
    for (ym, sensor), m in sorted(stats.items()):
        if sensor != MAIN[0]:
            continue
        expected_month, acquired_month, usable_month = m["expected"], acquired_months[ym], valid_months[ym]
        core_months.append([ym,expected_month,acquired_month,expected_month-acquired_month,usable_month,acquired_month-usable_month,
                            round(100*usable_month/expected_month,5), round(100*usable_month/acquired_month,5) if acquired_month else ""])
        core_years.setdefault(ym[:4],Counter()).update(expected=expected_month,acquired=acquired_month,usable=usable_month)
    core_headers = ["periodo","horas_esperadas","horas_consulta_verificada","horas_pendientes_descarga","horas_cuatro_principales_utilizables","horas_recuperadas_no_utilizables_conjuntamente","porcentaje_utilizable_objetivo","porcentaje_utilizable_adquirido"]
    csv_query(derived / "cobertura_principales_mensual.csv",core_headers,core_months)
    csv_query(derived / "cobertura_principales_anual.csv",core_headers,
              [[year,m["expected"],m["acquired"],m["expected"]-m["acquired"],m["usable"],m["acquired"]-m["usable"],round(100*m["usable"]/m["expected"],5),round(100*m["usable"]/m["acquired"],5) if m["acquired"] else ""] for year,m in sorted(core_years.items())])
    csv_query(derived / "esquemas.csv", ["bloque", "esquema_hash", "biff_version", "sensor", "campo", "columna_excel", "encabezado_original", "unidad", "altura_encabezado_m", "archivo_original"], schema_rows)
    csv_query(derived / "bloques.csv", ["bloque", "inicio", "fin", "sensores_solicitados", "estado", "detalle"],
              [[j, json.loads(s)["start"], json.loads(s)["end"], ",".join(json.loads(s)["sensors"]), status, detail] for j, s, status, detail in jobs])
    totals = {s: sum(m["usable"] for (ym, sid), m in stats.items() if sid == s) for s in ALL}
    sensor_ranges = {}
    for r in entries:
        if r[2] == 1 and r[4]:
            sensor_ranges.setdefault(r[1], {"first":r[0],"last":r[0]})["last"] = r[0]
    summary = {"updated_utc": now(), "start": config["start"], "end": config["end"], "expected_hours": expected,
               "unique_recovered_dates": len(recovered_dates), "verified_requested_primary_hours": len(main_acquired),
               "pending_primary_hours": expected-len(main_acquired), "main_usable_unique_hours": valid_primary,
               "main_usable_percent_full_target": round(100*valid_primary/expected, 5),
               "main_usable_percent_acquired": round(100*valid_primary/len(main_acquired), 5) if main_acquired else 0,
               "usable_hours_by_sensor": totals, "duplicates_sensor_hours": sum(r[2]>1 for r in entries),
               "usable_date_ranges_by_sensor": sensor_ranges,
               "issues": db.execute("SELECT count(*) FROM issues").fetchone()[0], **progress(db, config)}
    atomic_json(derived / "resumen.json", summary)
    if export:
        csv_query(derived / "errores_descarga.csv", ["bloque","inicio","fin","estado","detalle"],
                  [[job_id,json.loads(spec)["start"],json.loads(spec)["end"],status,detail] for job_id,spec,status,detail in jobs if status.startswith("error_")])
        field_metrics = {}
        for stamp, sensor, *cells_and_flags in db.execute("SELECT timestamp,sensor,min_original,prom_original,max_original,pct_original,flags FROM observations WHERE in_scope=1"):
            cells, flags = cells_and_flags[:4], json.loads(cells_and_flags[4])
            for field, encoded in zip(FIELDS, cells):
                val = json.loads(encoded)
                is_numeric = number(val) and not any(flag.startswith(field + ":tipo_original_") for flag in flags)
                m = field_metrics.setdefault((stamp[:7],sensor,field),Counter())
                m["rows"] += 1
                m["numeric"] += int(is_numeric)
                m["missing"] += int(val == "")
                m["zeros"] += int(is_numeric and val == 0)
                m["other"] += int(val != "" and not is_numeric)
        csv_query(derived / "campos_mensual_sensor.csv", ["mes","sensor","campo","registros_incluidos_duplicados","numericos","ausentes","ceros_observados","otros_no_numericos"],
                  [[*key,*[m[k] for k in ("rows","numeric","missing","zeros","other")]] for key,m in sorted(field_metrics.items())])
        changes, previous = [], {}
        for job_id, encoded, status, detail in sorted(jobs,key=lambda x:json.loads(x[1])["start"]):
            if not status.startswith("verificado_"):
                continue
            spec, info = json.loads(encoded), json.loads(detail)
            requested = tuple(spec["sensors"])
            signature = (info["schema_hash"], info["biff_version"])
            if requested in previous and signature != previous[requested][1]:
                changes.append([previous[requested][0],job_id,",".join(requested),"cambio_encabezados_o_formato_misma_seleccion",previous[requested][1][0],signature[0]])
            previous[requested] = (job_id,signature)
        csv_query(derived / "cambios_esquema.csv", ["bloque_anterior","bloque_actual","seleccion_sensores","tipo","hash_anterior","hash_actual"],changes)
        csv_query(derived / "horas_sin_fila.csv", ["fecha_sin_zona", "estado"], missing_rows)
        csv_query(derived / "duplicados_sensor_hora.csv", ["fecha_sin_zona", "sensor", "registros"],
                  [[r[0],r[1],r[2]] for r in entries if r[2]>1])
        csv_query(derived / "problemas.csv", ["bloque", "fila_excel", "marca_original", "sensor", "problema", "detalle"], db.execute("SELECT * FROM issues ORDER BY timestamp,job,row_excel"))
        # CSV largos por año: todos los registros, también duplicados y los de
        # fuera del alcance (marcados), conservan las cuatro celdas originales.
        obs_headers = ["fecha_sin_zona", "sensor", "variable", "unidad", "altura_encabezado_m", "min", "prom", "max", "porcentaje_datos", "prom_utilizable_revision", "dentro_periodo", "bloque", "archivo_original", "sha256_original", "hoja", "fila_excel", "problemas"]
        for year in range(low.year, high.year+1):
            cursor = db.execute("SELECT timestamp,sensor,min_original,prom_original,max_original,pct_original,usable,in_scope,job,sheet,row_excel,height_original,units_original,flags FROM observations WHERE substr(timestamp,1,4)=? ORDER BY timestamp,sensor,job,row_excel", (str(year),))
            def converted():
                digests = {job_id: json.loads(detail)["sha256"] for job_id, _, status, detail in jobs if status.startswith("verificado_")}
                for r in cursor:
                    original_path = f"originales/{r[8]}/original.xls"
                    digest = digests.get(r[8], "SIN_VERIFICACION")
                    yield [r[0], r[1], SPECS[r[1]][0], r[12], r[11], *[json.loads(v) for v in r[2:6]], r[6], r[7], r[8], original_path, digest, r[9], r[10], r[13]]
            csv_query(derived / f"observaciones_{year}.csv", obs_headers, converted())
    report(summary, monthly, jobs)
    return summary


def report(summary, monthly, jobs):
    recovered = [(json.loads(spec), status) for _, spec, status, _ in jobs if status.startswith("verificado_") and any(s in MAIN for s in json.loads(spec)["sensors"])]
    intervals = []
    for job, status in sorted(recovered, key=lambda x:x[0]["start"]):
        a, b = dt.date.fromisoformat(job["start"]), dt.date.fromisoformat(job["end"])
        if intervals and a == intervals[-1][1]+dt.timedelta(days=1):
            intervals[-1] = (intervals[-1][0], b)
        else:
            intervals.append((a,b))
    text = f'''# Histórico de Vicuña–INIA (`e_cod=6`)

Estado generado UTC: {summary['updated_utc']}. Alcance fijo: **{summary['start']}–{summary['end']}**, todos los meses, resolución horaria. {summary['expected_hours']:,} horas esperadas por marcas originales sin zona.

## Recuperación y pendientes

Estados de bloques: `{json.dumps(summary['jobs'], ensure_ascii=False)}`.

Períodos principales recuperados/verificados: {', '.join(f'{a}–{b}' for a,b in intervals) or 'ninguno'}.

Horas del período solicitado cubiertas por consultas verificadas de variables principales: **{summary['verified_requested_primary_hours']:,}**. Horas pendientes de adquisición: **{summary['pending_primary_hours']:,}**. Marcas únicas realmente presentes: **{summary['unique_recovered_dates']:,}** (un archivo válido sin observaciones es un período sin datos, no un error HTTP).

Cuatro variables principales simultáneamente utilizables y sin duplicados por sensor/hora: **{summary['main_usable_unique_hours']:,} horas**, {summary['main_usable_percent_full_target']}% de todo el objetivo y {summary['main_usable_percent_acquired']}% de las horas solicitadas en períodos ya recuperados. Los sensores opcionales no condicionan esta cifra.

| Sensor | Variable | Altura del encabezado actual | Horas utilizables únicas | Primera / última marca utilizable recuperada |
|---|---|---:|---:|---|
'''
    for sensor in ALL:
        spec = SPECS[sensor]
        available = summary["usable_date_ranges_by_sensor"].get(sensor)
        bounds = available["first"] + " / " + available["last"] if available else "sin observaciones"
        text += f'| {sensor} | {spec[0]} ({spec[2]}) | {spec[3]} m | {summary["usable_hours_by_sensor"][sensor]:,} | {bounds} |\n'
    text += f'''
Duplicados sensor/hora: **{summary['duplicates_sensor_hours']}**. Incidencias registradas: **{summary['issues']}**. La primera y última marca disponible no implican continuidad entre ambas. Una fila ausente y una celda ausente se informan por separado; los ceros numéricos se conservan como observaciones. Véanse `derivados/cobertura_anual_sensor.csv`, `cobertura_mensual_sensor.csv`, `cobertura_principales_anual.csv`, `cobertura_principales_mensual.csv`, `campos_mensual_sensor.csv`, `bloques.csv`, `errores_descarga.csv`, `esquemas.csv`, `cambios_esquema.csv`, `problemas.csv` y `horas_sin_fila.csv`. Los porcentajes por sensor usan todas las horas esperadas como denominador, incluidas las pendientes; las tablas de cobertura conjunta distinguen objetivo y horas adquiridas.

## Conservación y criterios

Cada XLS permanece intacto en `originales/<bloque>/original.xls`, con `manifest.json` (parámetros, adquisición, origen, hash), `verificacion.json`, evidencia HTTP y registro en `avance.jsonl`. Las fuentes locales verificadas se importaron sin nuevas solicitudes. Los cinco bloques de julio 2025 se complementan únicamente con viento/dirección a 5 m; las observaciones de la muestra de octubre posteriores al corte se conservan pero llevan `dentro_periodo=0` y no contribuyen a la cobertura.

Los CSV `derivados/observaciones_AAAA.csv` son tablas largas ordenadas por marca, sensor y fuente, con Min/Prom/Max/`%Datos`, unidades y alturas separadas, bloque, ruta, hash, hoja y fila Excel. Conservan todos los registros interpretados, incluidos duplicados y fuera de alcance, identificados explícitamente. Los originales y `problemas.csv` conservan evidencia de las filas no interpretadas. La base SQLite es derivada y se puede reconstruir desde los originales.

Utilizable significa promedio numérico finito, porcentaje publicado mayor que cero y no mayor que 100, dentro de rangos amplios de revisión (T −50–60 °C, HR 0–100%, viento 0–75 m/s, dirección 0–360°, presión 800–1100 hPa), con marca en la hora exacta. La cobertura conjunta exige una sola observación utilizable de cada principal por hora. Es una revisión técnica, no validación meteorológica ni homogeneidad histórica. Las demás celdas se conservan incluso si se marcan incoherencias Min/Prom/Max.

Un XLS válido puede contener sensores con celdas vacías; eso es falta de observaciones. `sensors_absent` en cada verificación indica sensores solicitados que no aparecen en el esquema, que es distinto. Los períodos válidos sin promedios numéricos se marcan `verificado_sin_datos`. Respuestas HTTP erróneas, sin enlace o sin XLS válido se marcan como error y detienen nuevas consultas; nunca se cuentan como períodos sin datos. Cambios no interpretables de unidad/altura/esquema también detienen la descarga para evitar mezclar variables.

Las fechas quedan **sin zona**. GMT−4 es la referencia publicada; continuidad histórica e inicio/cierre del intervalo siguen pendientes. Las alturas del encabezado no certifican las alturas físicas de instalación en cada año (el estudio describe T/HR a 1,5 m). El máximo horario de viento se conserva como máximo de definición pendiente, **sin denominarlo ráfaga**. El método circular/vectorial de promedio de dirección no está confirmado.

## Ejecución, reanudación y reconstrucción

Requisitos: Python3, curl y xlrd 2.0.2. Desde la raíz del proyecto:

```bash
python3 investigacion_ceazamet/historico_inia/gestionar_historico.py descargar
python3 investigacion_ceazamet/historico_inia/gestionar_historico.py estado
python3 investigacion_ceazamet/historico_inia/gestionar_historico.py reconstruir
```

`descargar` omite bloques verificados tras comprobar hashes. El corte inicial permanece fijado en `configuracion.json`; reanudar no lo amplía. Hay exclusión mutua para impedir procesos simultáneos. Las solicitudes son secuenciales: 10 s entre POST/GET y al menos 15 s entre bloques, incluso al reanudar. No hay incremento automático de frecuencia ni reintentos HTTP. Si existe `DETENIDO.json`, el proceso no continúa: hay que revisar la causa y resolver el bloqueo externo o la evidencia de la interrupción antes de autorizar una nueva ejecución; no retirar el marcador para eludir un control de acceso. `reconstruir` es local, verifica hashes y reconstruye observaciones e informes; no vuelve a descargar.

Para la detención DNS registrada (`curl=6`, `HTTP=000`), ejecutar manualmente `python3 investigacion_ceazamet/historico_inia/gestionar_historico.py preparar-reanudacion-dns` y después `descargar`. La preparación no consulta la red: archiva íntegro el intento fallido y el marcador en `intentos_fallidos/`, y deja ese bloque pendiente. Solo admite ese fallo de resolución sin XLS adquirido; rechaza denegaciones HTTP y otros errores. No hay ningún proceso de descarga activo ni reintentos programados. El corte de esta ejecución sigue siendo 2026-10-06, sin ampliación automática.

No se consultan otras estaciones ni se entrenan modelos o construyen etiquetas de terral. La cantidad utilizable informa disponibilidad para el siguiente análisis; siguen pendientes las confirmaciones instrumentales y temporales ya descritas.
'''
    if summary["download_stop"]:
        text += "\n## Causa de detención\n\n```json\n" + json.dumps(summary["download_stop"], ensure_ascii=False, indent=2) + "\n```\n"
    (ROOT / "informe.md").write_text(text, encoding="utf-8")


def preparar_reanudacion_dns(db, config):
    """Acción manual local: conserva el intento fallido, sin solicitudes HTTP."""
    marker = ROOT / "DETENIDO.json"
    if not marker.exists():
        raise DownloadStop("No existe una detención que preparar")
    stopped = json.loads(marker.read_text())
    job_id = stopped["job"]
    record = db.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
    directory = ROOT / "originales" / job_id
    failed = []
    for path in directory.glob("*.http.json"):
        response = json.loads(path.read_text())
        if response.get("curl_exit") != 0 or response.get("http_status") != "200":
            failed.append(response)
    if (not record or record[0] != "error_descarga" or not failed
            or any(r.get("curl_exit") != 6 or r.get("http_status") != "000" for r in failed)
            or (directory / "original.xls").exists()
            or (directory / "manifest.json").exists()):
        raise DownloadStop("Solo se permite preparar manualmente un fallo DNS curl=6/HTTP=000 sin XLS adquirido; otros errores requieren revisión")
    archive = ROOT / "intentos_fallidos" / job_id / uuid.uuid4().hex
    archive.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(directory), str(archive))
    shutil.copy2(marker, archive / "DETENIDO.json")
    with db:
        db.execute("UPDATE jobs SET status='pendiente',detail=NULL WHERE id=?", (job_id,))
    marker.unlink()
    event("reanudacion_dns_manual_preparada", job=job_id, evidence=str(archive.relative_to(ROOT)))
    progress(db, config)
    print("Preparado sin consultas HTTP. Evidencia conservada en " + str(archive))
    print("Ejecutar ahora la acción descargar cuando la conexión esté disponible.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accion", choices=["descargar", "estado", "reconstruir", "preparar-reanudacion-dns"])
    args = parser.parse_args()
    ROOT.mkdir(exist_ok=True)
    if args.accion == "estado" and (ROOT / "estado.json").exists():
        print((ROOT / "estado.json").read_text())
        return
    with (ROOT / "proceso.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Ya hay un proceso de adquisición/reconstrucción en ejecución. Leer estado.json para seguimiento")
        db = connect()
        config = prepare(db)
        if args.accion == "descargar":
            download_all(db, config)
        elif args.accion == "preparar-reanudacion-dns":
            preparar_reanudacion_dns(db, config)
        elif args.accion == "estado":
            print(json.dumps(progress(db, config), indent=2, ensure_ascii=False))
        else:
            for _, encoded, status in db.execute("SELECT id,spec,status FROM jobs WHERE status LIKE 'verificado_%'").fetchall():
                job = json.loads(encoded)
                verify_file(db, job, ROOT / "originales" / job["id"], config)
            print(json.dumps(rebuild_reports(db, config), indent=2, ensure_ascii=False))
        db.close()


if __name__ == "__main__":
    main()
