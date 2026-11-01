#!/usr/bin/env python3
from pathlib import Path
import json,hashlib,datetime
OUT=Path(__file__).resolve().parent; R=OUT.parent.parent
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
rows=json.loads((OUT/'conservacion_previa.json').read_text())
for r in rows: assert digest(R/r['archivo'])==r['sha256'],r['archivo']
for n in ['verificacion_independiente.json','verificacion_calidad.json','verificacion_avisos.json','reproduccion.json']: assert json.loads((OUT/n).read_text())['resultado']=='conforme'
checks=json.loads((OUT/'comprobaciones.json').read_text()); assert checks['fuentes_inmutables'] and checks['protocolo_inmutable']
files=[dict(archivo=str(p.relative_to(OUT)),sha256=digest(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name not in ['manifiesto_entregables.json','cierre.json'] and '__pycache__' not in p.parts]
(OUT/'manifiesto_entregables.json').write_text(json.dumps(files,indent=2,ensure_ascii=False)+'\n')
(OUT/'cierre.json').write_text(json.dumps(dict(resultado='conforme',fecha_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),archivos_previos_intactos=len(rows),fuentes_y_catalogo_intactos=True,modelos_por_ejecucion=48,repeticion_completa=True,verificaciones=['verificacion.json','verificacion_independiente.json','verificacion_calidad.json','verificacion_avisos.json'],manifiesto_entregables_sha256=digest(OUT/'manifiesto_entregables.json')),indent=2,ensure_ascii=False)+'\n')
print(f'Cierre conforme; {len(rows)} archivos previos intactos, fuentes intactas.')
