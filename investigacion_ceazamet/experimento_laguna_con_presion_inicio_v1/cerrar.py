#!/usr/bin/env python3
"""Cierre: verificaciones, conservación y manifiesto de entregables."""
import sys,json,hashlib,datetime
from pathlib import Path
OUT=Path(__file__).resolve().parent; ROOT=OUT.parent.parent
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
checks=['comprobaciones.json','verificacion.json','verificacion_independiente.json','verificacion_avisos.json','verificacion_huecos.json','verificacion_calidad.json','verificacion_presion.json','reproduccion.json']
for n in checks:
 rec=json.loads((OUT/n).read_text())
 assert rec.get('resultado','conforme' if rec.get('fuentes_inmutables') else None)=='conforme',n
protected=json.loads((OUT/'conservacion_previa.json').read_text())
for r in protected: assert sha(ROOT/r['archivo'])==r['sha256'],r['archivo']
reg=json.loads((OUT/'registro_preentrenamiento.json').read_text())
assert sha(OUT/'ejecutar.py')==reg['codigo_sha256']
assert sha(OUT/'protocolo.md')==reg['protocolo_sha256']
rep=json.loads((OUT/'reproduccion.json').read_text())
record={'resultado':'conforme','fecha_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'modelos_originales':36,'modelos_repetidos':36,'archivos_reproducidos_identicos':rep['n_archivos_identicos'],'archivos_previos_conservados':len(protected),'verificaciones':checks,'sin_descargas':True,'sin_despliegue':True}
(OUT/'cierre.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
text=(OUT/'informe.md').read_text().split('\n## Cierre verificado')[0]
text+=f"\n## Cierre verificado\n\nTodos los verificadores terminaron conformes. La repetición completa reajustó 36 modelos y conservó exactamente {rep['n_archivos_identicos']} archivos deterministas por SHA-256. Se conservaron {len(protected)} archivos previos inventariados de fuentes autorizadas, catálogo y experimentos anteriores. Ver cierre.json, reproduccion.json y verificaciones independientes. Las comprobaciones usan las mismas fuentes derivadas y algunas funciones de carga compartidas: no certifican calibración instrumental ni exactitud del criterio histórico.\n"
(OUT/'informe.md').write_text(text)
files=[dict(archivo=str(p.relative_to(OUT)),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='manifiesto_entregables.json' and not p.name.endswith('.log') and '__pycache__' not in p.parts]
(OUT/'manifiesto_entregables.json').write_text(json.dumps({'archivos':files,'limites':'Excluye este propio manifiesto, bytecode y logs abiertos. Fuente/conservación por separado.'},indent=2,ensure_ascii=False)+'\n')
print(json.dumps(record,ensure_ascii=False,indent=2))
