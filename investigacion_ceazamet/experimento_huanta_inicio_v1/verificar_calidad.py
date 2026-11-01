#!/usr/bin/env python3
"""Auditoría de calidad independiente de la ingestión del experimento."""
import os,sys,json,hashlib
os.environ['OPENBLAS_NUM_THREADS']='1'; sys.modules['numexpr']=None; sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np
import pandas as pd
BASE=Path(__file__).resolve().parent; ROOT=BASE.parent
OUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else BASE
checks={}
def check(k,v):
 assert v,k
 checks[k]=True
expected={'LLHTA':('temperatura',2.,'°C',-50,60),'LLHHR':('humedad',2.,'%',0,100),'LLHVV2M':('viento',2.,'m/s',0,75),'LLHDV2M':('direccion',2.,'°',0,360),'LLHPA':('presion',2.,'hPa',300,1100)}
config=json.loads((ROOT/'estaciones_complementarias/configuracion.json').read_text())
station=next(s for s in config['stations'] if s['slug']=='llanos_de_huanta')
meta=json.loads((ROOT/'estaciones_complementarias/llanos_de_huanta/metadatos.json').read_text())
raw=pd.read_csv(ROOT/'estaciones_complementarias/llanos_de_huanta/derivados/horarias.csv',dtype={'sensor':str,'problemas':str})
dates=pd.to_datetime(raw.fecha_sin_zona)
check('limites_huanta',dates.between('2013-01-01','2023-12-31 23:00').all() and dates.eq(dates.dt.floor('h')).all())
counts=pd.read_csv(OUT/'tablas/sensores_huanta.csv').set_index('sensor')
raw=raw[raw.sensor.isin(expected)].copy()
check('sin_duplicados',not raw.duplicated(['fecha_sin_zona','sensor']).any())
for sid,(v,h,unit,lo,hi) in expected.items():
 for source,items in [('configuracion',station['sensors']),('metadatos',meta['sensors'])]:
  r=next(r for r in items if r['code']==sid)
  check(source+'_'+sid,r['variable']==v and r['height_m']==h and r['unit']==unit)
 z=raw[raw.sensor.eq(sid)]
 check('identidad_'+sid,len(z)==96408 and z.altura_m.eq(h).all() and z.variable.eq(v).all() and z.unidad.eq(unit).all())
 vals=z[['min','prom','max','porcentaje_datos']].to_numpy(float)
 valid=np.isfinite(vals).all(axis=1)&(vals[:,3]>0)&(vals[:,3]<=100)&(vals[:,:3]>=lo).all(axis=1)&(vals[:,:3]<=hi).all(axis=1)
 if v!='direccion': valid &= (vals[:,0]<=vals[:,1])&(vals[:,1]<=vals[:,2])
 check('mascara_'+sid,np.array_equal(valid,z.utilizable_revision.to_numpy()==1))
 check('conteos_'+sid,valid.sum()==counts.loc[sid,'utilizables'] and np.sum(valid&(vals[:,1]==0))==counts.loc[sid,'ceros_validos'])
 # All eligible seven-hour windows must contain only this masked sensor.
 ts=pd.to_datetime(z.fecha_sin_zona); available=pd.Series(valid,index=ts)
 examples=pd.read_csv(OUT/'tablas/ejemplos_comunes.csv',usecols=['emision']).drop_duplicates() if 'examples' not in globals() else examples
 em=pd.DatetimeIndex(pd.to_datetime(examples.emision))
 check('aplicacion_mascara_'+sid,all(available.reindex(em-pd.Timedelta(hours=k),fill_value=False).all() for k in range(7)))
# Independently inspect INIA mask fields and valid zeros without using experiment functions.
for year in range(2013,2024):
 q=pd.read_csv(ROOT/f'historico_inia/derivados/observaciones_{year}.csv',usecols=['fecha_sin_zona','variable','prom','porcentaje_datos','prom_utilizable_revision','dentro_periodo'])
 dt=pd.to_datetime(q.fecha_sin_zona)
 check('limites_INIA_'+str(year),dt.dt.year.eq(year).all() and q.dentro_periodo.eq(1).all())
 check('porcentaje_max_INIA_'+str(year),not (q.prom_utilizable_revision.eq(1)&q.porcentaje_datos.gt(100)).any())
 for var in ['temperatura','humedad','viento_2m','direccion_2m','presion']:
  z=q[q.variable.eq(var)]; valid=np.isfinite(z.prom)&z.porcentaje_datos.gt(0)&z.porcentaje_datos.le(100)&z.prom_utilizable_revision.eq(1)
  if var=='humedad': valid &= z.prom.between(0,100)
  if var=='viento_2m': valid &= z.prom.ge(0)
  if var=='direccion_2m': valid &= z.prom.between(0,360)
  available=pd.Series(valid.to_numpy(),index=pd.to_datetime(z.fecha_sin_zona))
  for k in range(7):
   t=em-pd.Timedelta(hours=k); t=t[t.year==year]
   check(f'aplicacion_INIA_{year}_{var}_{k}',available.reindex(t,fill_value=False).all())
(OUT/'verificacion_calidad.json').write_text(json.dumps({'resultado':'conforme','codigo_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'comprobaciones':checks,'limites':'Lectura y cálculo de máscaras independientes del ejecutor, sobre las mismas fuentes derivadas auditadas. No contrasta XLS originales ni certifica exactitud instrumental.'},indent=2,ensure_ascii=False)+'\n')
print('Calidad, sensores, alturas y aplicación de máscaras conformes.')
