#!/usr/bin/env python3
"""Verificación de agregados finales y manifiesto de entrega."""
import sys
sys.modules['numexpr']=None
import hashlib,json
from pathlib import Path
import pandas as pd
p=Path(__file__).resolve().parent
m=pd.read_csv(p/'tablas/metricas.csv'); a=m[m.bloque=='AGREGADO']; b=m[m.bloque!='AGREGADO']; keys=['retraso_h','horizonte_h','modelo','politica','epoca']
for col in ['emisiones_con_aviso','avisos_sin_resultado','inicios_anticipados','horas_alerta','horas_alerta_indeterminada_vigente','episodios','episodios_ge24h','episodios_ge168h']:
 merged=a[keys+[col]].merge(b.groupby(keys,as_index=False)[col].sum(),on=keys,suffixes=('_agregado','_suma')); assert merged[col+'_agregado'].eq(merged[col+'_suma']).all()
assert m.avisos_sin_resultado.eq(m.avisos_desconocidos+m.avisos_fuera_alcance).all()
assert m.pronosticos_sin_resultado.eq(m.pronosticos_desconocidos+m.pronosticos_fuera_alcance).all()
assert m.horas_alerta.eq(m.horas_alerta_con_inicio_vigente+m.horas_alerta_sin_inicio_vigente+m.horas_alerta_indeterminada_vigente).all()
manifest=pd.read_csv(p/'tablas/manifiesto_preservacion.csv'); assert all(hashlib.sha256(Path(r.archivo).read_bytes()).hexdigest()==r.sha256_antes for r in manifest.itertuples())
(p/'control_cierre.json').write_text(json.dumps({'conforme':True,'sumas_entre_bloques':True,'resultados_no_evaluables_separados':True,'clases_de_carga_reconciliadas':True,'fuentes_preservadas':len(manifest),'filas_metricas':len(m)},indent=2))
rows=[{'archivo':str(f.relative_to(p)),'sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'bytes':f.stat().st_size} for f in sorted(p.rglob('*')) if f.is_file() and '__pycache__' not in f.parts and f.suffix!='.log' and f.name!='manifiesto_resultados.csv']
pd.DataFrame(rows).to_csv(p/'manifiesto_resultados.csv',index=False)
print('Cierre conforme:',len(rows),'artefactos;',len(m),'filas de métricas')
