#!/usr/bin/env python3
"""Comprobaciones sintéticas y de coherencia sin abrir datos externos."""
import sys
sys.modules['numexpr']=None
import ast,json,csv,math,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
O=Path(__file__).resolve().parent
p=json.loads((O/'protocolo.json').read_text()); c=p['sensibilidad_prefijada'][0]
# Extraer solo funciones puras del análisis; no ejecutar su ingesta al importar.
tree=ast.parse((O/'diagnostico.py').read_text())
fn=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ['runs','state','segments']],type_ignores=[])
ns={'np':np,'pd':pd}; exec(compile(fn,'funciones_diagnostico','exec'),ns)
idx=pd.date_range('2013-01-01',periods=9,freq='h'); ns['IDX']=idx
x=pd.DataFrame({'temperatura':[12,11,12,12,12,12,12,12,12],'humedad':[29,29,30,29,29,29,29,29,29],'viento_2m':[3,3,3,2,3,3,3,3,3],'direccion_2m':[0,90,90,90,180,360,181,90,90]},index=idx)
ns['x']=x; ns['joint']=pd.Series([True]*8+[False],index=idx)
st=ns['state'](c)
assert st.tolist()==[1,0,0,0,1,0,0,1,-1]
# Un desconocido rompe cualquier agrupación; una negativa puede ser puente solo en alternativa.
ns['joint']=pd.Series(True,index=idx)
st=pd.Series([1,1,-1,1,0,1,1,0,0],index=idx)
sg,keep=ns['segments'](st,c); assert sg.horas_candidatas.tolist()==[2,1,2]
sg,keep=ns['segments'](st,{**c,'persistencia':2}); assert sg.horas_candidatas.tolist()==[2,2] and keep.sum()==4
sg,keep=ns['segments'](st,{**c,'puente_negativo':1}); assert sg.horas_candidatas.tolist()==[2,3] and sg.amplitud_h.tolist()==[2,4] and keep.sum()==5
h=pd.read_csv(O/'tablas/estados_horarios.csv'); dt=pd.to_datetime(h.fecha_sin_zona)
assert dt.between('2013-01-01','2023-12-31 23:00').all()
assert len(h)==96408 and not dt.duplicated().any()
assert dt.diff().dropna().eq(pd.Timedelta(hours=1)).all()
assert set(h.estado)=={'cumple','no_cumple','no_evaluable'}
assert (h.estado.eq('no_evaluable')==~h.validez_conjunta).all()
sg=pd.read_csv(O/'tablas/tramos_anual.csv'); assert sg.horas_candidatas.sum()==h.estado.eq('cumple').sum()
assert (pd.to_datetime(sg.fin)-pd.to_datetime(sg.inicio)).dt.total_seconds().div(3600).add(1).eq(sg.horas_candidatas).all()
for r in sg.itertuples():
 within=dt.between(r.inicio,r.fin)
 assert h.loc[within,'estado'].eq('cumple').all()
cov=pd.read_csv(O/'tablas/cobertura.csv')
assert cov.horas_esperadas.eq(cov.ausentes+cov.presentes_no_validas+cov.validas).all()
co=pd.read_csv(O/'tablas/conteos_candidatos.csv'); assert co.horas_ambito.eq(co.cumple+co.no_cumple+co.no_evaluable).all()
s=pd.read_csv(O/'tablas/sensibilidad_resumen.csv'); ref=s.set_index('configuracion').loc['original']
assert ref.horas_retenidas==h.estado.eq('cumple').sum() and ref.tramos==len(sg)
bridge=s.set_index('configuracion').loc['puente_1_negativa']; assert bridge.horas_retenidas==ref.horas_retenidas and bridge.tramos<=ref.tramos
manifest=pd.read_csv(O/'tablas/manifiesto_fuentes.csv')
for row in manifest.itertuples():
 path=O.parent.parent/row.archivo
 assert hashlib.sha256(path.read_bytes()).hexdigest()==row.sha256_csv, 'Fuente modificada'
# Reconciliación independiente: csv de biblioteca estándar, sin pivot ni vectorización.
control={}; main={'temperatura','humedad','viento_2m','direccion_2m'}
for year in range(2013,2024):
 with (O.parent/'historico_inia/derivados'/f'observaciones_{year}.csv').open() as f:
  for row in csv.DictReader(f):
   assert '2013-01-01 00:00:00'<=row['fecha_sin_zona']<='2023-12-31 23:00:00'
   if row['variable'] not in main: continue
   value=float(row['prom']) if row['prom'] else math.nan
   good=math.isfinite(value) and float(row['porcentaje_datos'])>0 and row['prom_utilizable_revision']=='1'
   v=row['variable']
   if v=='humedad': good &= 0<=value<=100
   if v=='viento_2m': good &= value>=0
   if v=='direccion_2m': good &= 0<=value<=360
   control.setdefault(row['fecha_sin_zona'],{})[v]=(value,good)
check={'cumple':0,'no_cumple':0,'no_evaluable':0}
for dt,row in control.items():
 if len(row)!=4 or not all(g for v,g in row.values()): result='no_evaluable'
 else:
  yes=(0<=row['direccion_2m'][0]<=180 and row['viento_2m'][0]>2 and row['temperatura'][0]>11 and row['humedad'][0]<30)
  result='cumple' if yes else 'no_cumple'
 check[result]+=1
assert check==h.estado.value_counts().to_dict()
print('OK: límites, tres estados, cortes exactos, persistencia, huecos desconocidos, puente conocido, denominadores y coherencia de tablas.')
print('OK: hashes fuente sin cambios y conteos independientes desde los once CSV con csv/math:',check)
