#!/usr/bin/env python3
"""Comprueba repetición completa; no vuelve a ajustar aquí."""
from pathlib import Path
import hashlib,json,sys,datetime
BASE=Path(__file__).resolve().parent; other=Path(sys.argv[1]).resolve()
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
files=[]
for folder in ['tablas','ajustes','graficos']:
 for p in sorted((BASE/folder).rglob('*')):
  if p.is_file(): files.append(p.relative_to(BASE))
files += [Path(n) for n in ['protocolo.md','configuracion_experimento.json','predictores.json','predicciones_validacion.csv','manifiesto_previo.json','verificacion.json','comprobaciones.json','requirements.txt','verificacion_independiente.json','verificacion_avisos.json','verificacion_calidad.json','informe.md']]
detail=[]
for rel in files:
 a=digest(BASE/rel); b=digest(other/rel); assert a==b,str(rel)
 detail.append(dict(archivo=str(rel),sha256_original=a,sha256_repeticion=b,identico=True))
for target in [BASE,other]:
 reg=json.loads((target/'registro_preentrenamiento.json').read_text())
 for filename,key in [('ejecutar.py','codigo_sha256'),('protocolo.md','protocolo_sha256'),('predictores.json','predictores_sha256'),('manifiesto_previo.json','manifiesto_previo_sha256')]: assert digest(target/filename)==reg[key]
 fits=list((target/'ajustes').glob('*/ajustes/logistica_*.json')); assert len(fits)==48
 assert len(json.loads((target/'verificacion_independiente.json').read_text())['controles_resumen'])>1000
record=dict(resultado='conforme',fecha_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),directorio_repeticion=str(other),modelos_reajustados_por_ejecucion=48,n_archivos_identicos=len(detail),detalle=detail,limites='Igualdad exacta en el mismo entorno; registros de reloj no comparados byte a byte. Verificaciones independientes ejecutadas en ambas carpetas.')
(BASE/'reproduccion.json').write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n')
print(f'Repetición completa conforme: {len(detail)} archivos idénticos y 48 ajustes nuevos.')
