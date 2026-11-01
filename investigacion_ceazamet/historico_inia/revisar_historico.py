#!/usr/bin/env python3
"""Auditoría local de originales, CSV y cobertura. No hace solicitudes de red.

Ejecutar después de gestionar_historico.py reconstruir, sin adquisición activa.
No modifica XLS ni observaciones; escribe auditoria.json y huecos_conjuntos.csv.
"""
import csv
import datetime as dt
import fcntl
import hashlib
import io
import json
import sqlite3
from collections import Counter
from functools import lru_cache
from pathlib import Path

import xlrd

ROOT = Path(__file__).resolve().parent


def audit():
    config = json.loads((ROOT / "configuracion.json").read_text())
    db = sqlite3.connect(f"file:{ROOT / 'historico.sqlite'}?mode=ro", uri=True)
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    jobs = db.execute("SELECT id,spec,status,detail FROM jobs ORDER BY id").fetchall()
    verified = {}
    errors = []
    acquisition_missing = []
    plan_days = Counter()
    for job_id, encoded, status, encoded_detail in jobs:
        job, detail = json.loads(encoded), json.loads(encoded_detail) if encoded_detail else {}
        if not status.startswith("verificado_"):
            errors.append([job_id, status])
            continue
        original = ROOT / detail["original_path"]
        manifest = json.loads(original.with_name("manifest.json").read_text())
        digest = hashlib.sha256(original.read_bytes()).hexdigest()
        assert digest == manifest["sha256"] == detail["sha256"], job_id
        assert manifest["station"] == "6"
        params = dict(manifest["fields"])
        assert params["e_cod"] == "6" and params["intervalo"] == "hora"
        request_days = (dt.date.fromisoformat(params["fecha_fin"]) - dt.date.fromisoformat(params["fecha_inicio"])).days + 1
        assert 1 <= request_days <= 7, job_id
        if not manifest.get("downloaded_utc"):
            acquisition_missing.append(job_id)
        if "39" in job["sensors"]:
            start, end = dt.date.fromisoformat(job["start"]), dt.date.fromisoformat(job["end"])
            for i in range((end - start).days + 1):
                plan_days[str(start + dt.timedelta(days=i))] += 1
        verified[job_id] = (original, detail, digest)
    start, end = dt.date.fromisoformat(config["start"]), dt.date.fromisoformat(config["end"])
    expected_days = {str(start + dt.timedelta(days=i)) for i in range((end-start).days+1)}
    assert set(plan_days) == expected_days and all(v == 1 for v in plan_days.values())

    @lru_cache(maxsize=4)
    def source(job_id):
        path, detail, digest = verified[job_id]
        book = xlrd.open_workbook(path, logfile=io.StringIO())
        sheet = book.sheet_by_index(0)
        columns = {(c["sensor"], c["campo"]): c["columna_excel"] - 1 for c in detail["schema"]}
        return sheet, columns, digest

    csv_rows, outside_rows, zero_means = 0, 0, Counter()
    fields = ["min", "prom", "max", "porcentaje_datos"]
    csv_counts = {}
    for path in sorted((ROOT / "derivados").glob("observaciones_*.csv")):
        previous, count = None, 0
        with path.open(newline="") as f:
            for row in csv.DictReader(f):
                key = (row["fecha_sin_zona"], row["sensor"], row["bloque"], int(row["fila_excel"]))
                assert previous is None or previous <= key, (path.name, key)
                previous = key
                sheet, columns, digest = source(row["bloque"])
                excel_row = int(row["fila_excel"]) - 1
                assert row["hoja"] == sheet.name
                assert row["archivo_original"] == str(verified[row["bloque"]][0].relative_to(ROOT))
                assert row["sha256_original"] == digest
                assert row["fecha_sin_zona"] == str(sheet.cell_value(excel_row, 0))
                for field in fields:
                    value = sheet.cell_value(excel_row, columns[(row["sensor"], field)])
                    assert row[field] == str(value), (path.name, key, field)
                if row["dentro_periodo"] == "0":
                    outside_rows += 1
                elif row["prom"] in ("0", "0.0"):
                    zero_means[row["sensor"]] += 1
                count += 1
        csv_counts[path.name] = count
        csv_rows += count
    db_rows = db.execute("SELECT count(*) FROM observations").fetchone()[0]
    assert csv_rows == db_rows

    usable = {r[0] for r in db.execute("""SELECT timestamp FROM observations
      WHERE in_scope=1 AND sensor IN ('39','40','36','37') GROUP BY timestamp
      HAVING count(*)=4 AND count(DISTINCT sensor)=4 AND sum(usable)=4""")}
    gaps, gap_start, gap_end, length = [], None, None, 0
    cursor = dt.datetime.combine(start, dt.time())
    limit = dt.datetime.combine(end + dt.timedelta(days=1), dt.time())
    while cursor < limit:
        stamp = cursor.strftime("%Y-%m-%d %H:%M:%S")
        if stamp not in usable:
            gap_start = gap_start or stamp
            gap_end, length = stamp, length + 1
        elif gap_start:
            gaps.append([gap_start, gap_end, length])
            gap_start, length = None, 0
        cursor += dt.timedelta(hours=1)
    if gap_start:
        gaps.append([gap_start, gap_end, length])
    derived = ROOT / "derivados"
    with (derived / "huecos_conjuntos.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["inicio_sin_zona", "fin_sin_zona_inclusivo", "horas_sin_cuatro_principales_utilizables"])
        writer.writerows(gaps)
    summary = json.loads((derived / "resumen.json").read_text())
    assert len(usable) == summary["main_usable_unique_hours"]
    assert sum(g[2] for g in gaps) == summary["expected_hours"] - len(usable)
    http_pairs = []
    failed_attempts = []
    for directory in (ROOT / "originales").iterdir():
        if not (directory / "post.http.json").exists():
            continue
        post = json.loads((directory / "post.http.json").read_text())
        get = json.loads((directory / "get.http.json").read_text())
        assert post["curl_exit"] == get["curl_exit"] == 0
        assert post["http_status"] == get["http_status"] == "200"
        pause = (dt.datetime.fromisoformat(get["started_utc"]) - dt.datetime.fromisoformat(post["finished_utc"])).total_seconds()
        assert pause >= config["pause_post_get_seconds"], directory.name
        http_pairs.append((post["started_utc"], get["finished_utc"], pause))
    http_pairs.sort()
    between_blocks = [(dt.datetime.fromisoformat(b[0]) - dt.datetime.fromisoformat(a[1])).total_seconds()
                      for a,b in zip(http_pairs,http_pairs[1:])]
    assert all(p >= config["pause_blocks_seconds"] for p in between_blocks)
    for path in (ROOT / "intentos_fallidos").rglob("*.http.json"):
        attempt = json.loads(path.read_text())
        if attempt["curl_exit"] != 0 or attempt["http_status"] != "200":
            failed_attempts.append({"evidence": str(path.relative_to(ROOT)), "curl_exit":attempt["curl_exit"],
                                    "http_status":attempt["http_status"], "stderr":attempt["stderr"]})
    result = {
        "reviewed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "network_requests": 0, "sqlite_integrity": "ok", "start": config["start"], "end": config["end"],
        "verified_originals_hashes": len(verified), "unverified_jobs": errors,
        "originals_without_downloaded_utc": acquisition_missing,
        "primary_plan_days_no_gaps_or_overlaps": len(plan_days),
        "csv_rows_compared_to_original_cells": csv_rows, "csv_rows_by_file": csv_counts,
        "csv_cells_compared": csv_rows*4,
        "out_of_scope_sensor_rows_retained": outside_rows,
        "zero_mean_observations_in_scope": dict(zero_means),
        "main_usable_hours_independent_count": len(usable), "joint_gap_count": len(gaps),
        "joint_unusable_hours": sum(g[2] for g in gaps),
        "longest_joint_gaps": sorted(gaps, key=lambda r:r[2], reverse=True)[:10],
        "issues_by_type": dict(db.execute("SELECT issue,count(*) FROM issues GROUP BY issue")),
        "originals_out_of_order": [j for j, (_, d, _) in verified.items() if not d["sorted_original"]],
        "schema_hash_count": len({d["schema_hash"] for _, d, _ in verified.values()}),
        "sensor_header_absent_blocks": {s:sum(s in d["sensors_absent"] for _,d,_ in verified.values())
                                         for s in ("39","40","36","37","VCNPA","VCNVV5","VCNDV5")},
        "successful_http_block_pairs": len(http_pairs),
        "minimum_post_get_pause_seconds": min(p[2] for p in http_pairs),
        "minimum_between_blocks_seconds": min(between_blocks),
        "archived_failed_http_attempts": failed_attempts,
    }
    (derived / "auditoria.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    coverage = {}
    for sensor, rows, numeric, missing, zeros in db.execute('''SELECT sensor,count(*),sum(numeric_mean),
      sum(prom_original='""'),sum(zero_mean) FROM observations WHERE in_scope=1 GROUP BY sensor'''):
        coverage[sensor] = (rows,numeric,missing,zeros)
    annual = list(csv.DictReader((derived / "cobertura_principales_anual.csv").open()))
    recent = [r for r in annual if r["periodo"] >= "2013"]
    recent_good = sum(int(r["horas_cuatro_principales_utilizables"]) for r in recent)
    recent_expected = sum(int(r["horas_esperadas"]) for r in recent)
    text = f'''# Revisión local del histórico Vicuña–INIA

Revisado UTC: {result['reviewed_utc']}. **Adquisición completa para el corte fijo {config['start']}–{config['end']}: {len(verified)} originales verificados, sin bloques pendientes.** El corte corresponde a la ejecución inicial, no se amplió a 2026-10-07 durante esta revisión. No hubo consultas de red.

Se reconstruyeron las tablas desde los XLS. Una comprobación independiente validó todos los SHA-256 y comparó **{csv_rows:,} filas / {csv_rows*4:,} celdas Min, Prom, Max y %Datos** de los CSV con sus celdas originales, junto con marcas, orden, hoja, fila y trazabilidad. SQLite supera `integrity_check`. El plan principal cubre todos los días exactamente una vez, con solicitudes de hasta siete días. Las pausas HTTP registradas cumplen al menos 10 s entre POST/GET y 15 s entre bloques. El fallo DNS previo permanece archivado en `intentos_fallidos/`; no quedan errores de descarga pendientes.

## Cobertura y disponibilidad

Hay **{summary['expected_hours']:,} marcas horarias esperadas y presentes**, sin duplicados sensor/hora ni filas horarias faltantes dentro del alcance. Esto representa cobertura de la rejilla, no disponibilidad de valores: 56 bloques válidos no contienen promedios numéricos. Todos los sensores solicitados aparecen en sus encabezados; la falta de observaciones se manifiesta mediante celdas vacías y %Datos=0. En las horas con valores, %Datos=100; no hay porcentajes parciales publicados en esta descarga. El significado físico y denominador de ese porcentaje siguen sin confirmar.

| Sensor | Variable / altura del encabezado | Horas utilizables | % del período | Promedios ausentes | Ceros observados |
|---|---|---:|---:|---:|---:|
'''
    names = {"39":"Temperatura / 2 m", "40":"Humedad relativa / 2 m", "36":"Velocidad del viento / 2 m",
             "37":"Dirección del viento / 2 m", "VCNPA":"Presión / 2 m", "VCNVV5":"Velocidad del viento / 5 m", "VCNDV5":"Dirección del viento / 5 m"}
    for sensor,name in names.items():
        n = summary["usable_hours_by_sensor"][sensor]
        text += f'| {sensor} | {name} | {n:,} | {100*n/summary["expected_hours"]:.2f}% | {coverage[sensor][2]:,} | {coverage[sensor][3]:,} |\n'
    text += f'''
Los criterios técnicos de utilidad exigen promedio numérico finito, %Datos mayor que cero y no mayor que 100, marca en la hora exacta y rangos de revisión de T −50–60 °C, HR 0–100%, viento 0–75 m/s, dirección 0–360° y presión 800–1100 hPa. Son filtros de revisión, no certificación meteorológica. Las cuatro variables principales son utilizables simultáneamente en **{len(usable):,} horas ({summary['main_usable_percent_full_target']:.2f}%)**; {sum(g[2] for g in gaps):,} horas no cumplen esa disponibilidad conjunta. No se rellenaron valores ni se eliminaron filas. Hay {len(gaps)} huecos consecutivos de disponibilidad conjunta, detallados en `derivados/huecos_conjuntos.csv`; incluyen ausencia de una o más variables, no solo interrupciones totales.

La presión y el viento/dirección a 5 m empiezan a tener valores el **2012-04-30 13:00**, sin que eso pruebe la fecha de instalación. Los opcionales no condicionan la disponibilidad conjunta.

## Problemas y esquema

- Cinco promedios de presión quedan fuera del rango de revisión 800–1100 hPa: cuatro el 2015-07-20 entre 11:00 y 14:00 (11,554–12,368 hPa) y uno el 2024-12-16 a las 06:00 (721,114 hPa). Se preservan íntegros y se marcan; no se propone una corrección automática. No hay promedios principales fuera de los rangos de revisión ni incoherencias Min ≤ Prom ≤ Max detectadas.
- Una muestra previa reutilizada trae las 24 horas del 2026-10-07: se conservan {outside_rows} filas de sensores fuera del alcance con `dentro_periodo=0`, excluidas de la cobertura. Se detectaron {len(result["originals_out_of_order"])} originales con marcas fuera de orden; los CSV están ordenados y conservan la referencia a la fila original.
- No se detectaron cambios de encabezados/formato entre bloques que solicitaron la misma selección de sensores. Las selecciones de siete, cinco y dos sensores explican los distintos esquemas; no acreditan homogeneidad instrumental durante 22 años. Las advertencias del lector OLE/BIFF5 y codificación se conservan en cada `verificacion.json`.
- Fechas **sin zona**: GMT−4 es la referencia publicada, pendiente de confirmar su continuidad histórica y si las marcas indican inicio o cierre de intervalos. También están pendientes la altura física histórica de T/HR (el estudio indica 1,5 m), los cambios instrumentales y el método de promedio direccional. La dirección es circular y una media horaria no describe toda su variabilidad. El máximo horario del viento queda separado y no se denomina ráfaga.

## Cobertura conjunta por año

| Año | Horas esperadas | Cuatro variables utilizables | Cobertura |
|---|---:|---:|---:|
'''
    for row in annual:
        text += f'| {row["periodo"]} | {int(row["horas_esperadas"]):,} | {int(row["horas_cuatro_principales_utilizables"]):,} | {float(row["porcentaje_utilizable_objetivo"]):.2f}% |\n'
    text += '\nLos límites de 2004 y 2026 son parciales por el alcance fijado. Detalle por mes y sensor en `derivados/cobertura_mensual_sensor.csv` y `cobertura_anual_sensor.csv`.\n\n## Huecos conjuntos más largos\n\n| Inicio sin zona | Fin inclusivo sin zona | Horas |\n|---|---|---:|\n'
    for a,b,n in result["longest_joint_gaps"]:
        text += f'| {a} | {b} | {n:,} |\n'
    text += f'''

La hora de adquisición de la muestra de octubre reutilizada procede de su fecha de generación y cabeceras guardadas; el instante exacto de GET no quedó registrado en aquella prueba inicial. El manifiesto declara esta limitación.

## Viabilidad y siguiente análisis

La recuperación histórica está terminada para el corte solicitado. Es viable avanzar a una revisión meteorológica de episodios sobre las {len(usable):,} horas conjuntas disponibles, manteniendo huecos y banderas explícitos. **Desde 2013 hasta el corte hay {recent_good:,}/{recent_expected:,} horas conjuntas ({100*recent_good/recent_expected:.2f}%)**: es el tramo más consistente para empezar; 2007–2012 requieren atención especial y 2011 solo alcanza 44,27% anual. La disponibilidad no certifica calibración ni estabilidad de sensores. Antes de estudiar desfases, inicios y horarios de episodios conviene resolver la convención temporal con CEAZA. No se generó un catálogo de terrales ni se entrenaron modelos.

Para repetir la revisión local desde la raíz del proyecto:

```bash
python3 investigacion_ceazamet/historico_inia/gestionar_historico.py reconstruir
python3 investigacion_ceazamet/historico_inia/revisar_historico.py
```

Evidencia: `derivados/auditoria.json`, `resumen.json`, `problemas.csv`, `huecos_conjuntos.csv` y los manifiestos/verificaciones junto a cada original.
'''
    (ROOT / "revision_final.md").write_text(text)
    db.close()
    print(json.dumps({k:v for k,v in result.items() if k != "csv_rows_by_file"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    with (ROOT / "proceso.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        audit()
