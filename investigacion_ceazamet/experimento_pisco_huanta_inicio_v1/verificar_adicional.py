#!/usr/bin/env python3
"""Controles adicionales sin compartir ingestión: sensores INIA y etiquetas de cada fila."""
import os,sys,json,hashlib
os.environ['OPENBLAS_NUM_THREADS']='1'; sys.modules['numexpr']=None; sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np
import pandas as pd
BASE=Path(__file__).resolve().parent; ROOT=BASE.parent; OUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else BASE
checks={}
def check(name,valid):
 assert valid,name
 checks[name]=True
expected={'viento_2m':('36',2.,'m/s'),'direccion_2m':('37',2.,'°'),'temperatura':('39',2.,'°C'),'humedad':('40',2.,'%'),'presion':('VCNPA',2.,'hPa')}
for year in range(2013,2024):
 q=pd.read_csv(ROOT/f'historico_inia/derivados/observaciones_{year}.csv',usecols=['variable','sensor','altura_encabezado_m','unidad','fecha_sin_zona'],dtype={'sensor':str})
 check(f'fechas_INIA_{year}',pd.to_datetime(q.fecha_sin_zona).dt.year.eq(year).all())
 for var,(sensor,height,unit) in expected.items():
  z=q[q.variable.eq(var)]
  check(f'sensor_INIA_{year}_{var}',len(z)>0 and z.sensor.eq(sensor).all() and z.altura_encabezado_m.eq(height).all() and z.unidad.eq(unit).all() and not z.fecha_sin_zona.duplicated().any())
cat=pd.read_csv(ROOT/'catalogo_provisional_v0/catalogo_referencia.csv')
cat['inicio']=pd.to_datetime(cat.primera_marca); cat['fin']=pd.to_datetime(cat.ultima_marca)
# Historical start known iff previous hour was observed and no active historical segment;
# reconstruct states from raw INIA usable masks instead of using the experiment's state.
frames=[]
for year in range(2013,2024):
 q=pd.read_csv(ROOT/f'historico_inia/derivados/observaciones_{year}.csv',usecols=['fecha_sin_zona','variable','prom','porcentaje_datos','prom_utilizable_revision'])
 q=q[q.variable.isin(['temperatura','humedad','viento_2m','direccion_2m'])].copy(); valid=np.isfinite(q.prom)&q.porcentaje_datos.gt(0)&q.porcentaje_datos.le(100)&q.prom_utilizable_revision.eq(1)
 valid &= ~q.variable.eq('humedad')|q.prom.between(0,100); valid &= ~q.variable.eq('viento_2m')|q.prom.ge(0); valid &= ~q.variable.eq('direccion_2m')|q.prom.between(0,360)
 q['valid']=valid; frames.append(q.pivot(index='fecha_sin_zona',columns='variable',values='valid'))
valid=pd.concat(frames).all(axis=1); valid.index=pd.to_datetime(valid.index)
active=pd.Series(False,index=valid.index)
for r in cat.itertuples(): active.loc[r.inicio:r.fin]=True
known=[]
for r in cat.itertuples():
 previous=r.inicio-pd.Timedelta(hours=1)
 if previous in valid.index and valid.loc[previous] and not active.loc[previous]: known.append((r.inicio,r.id_tramo))
starts=pd.DataFrame(known,columns=['inicio','id']).sort_values('inicio'); dates=starts.inicio.to_numpy(dtype='datetime64[ns]'); ids=starts.id.to_numpy()
rows=pd.read_csv(OUT/'tablas/ejemplos_comunes.csv',parse_dates=['emision']).fillna({'id_inicio_objetivo':''})
for (h,block,role),g in rows.groupby(['horizonte_h','bloque','rol']):
 left=np.searchsorted(dates,g.emision.to_numpy(dtype='datetime64[ns]'),side='right'); right=np.searchsorted(dates,(g.emision+pd.Timedelta(hours=h)).to_numpy(dtype='datetime64[ns]'),side='right')
 labels=np.array(['|'.join(ids[l:r]) for l,r in zip(left,right)])
 check(f'etiquetas_fila_{h}_{block}_{role}',np.array_equal(labels,g.id_inicio_objetivo) and np.array_equal(left<right,g.y.astype(bool)))
 check(f'comun_ocho_{h}_{block}_{role}',g.brazos.eq('A|B|C|D|E|F|G|H').all() and not g.emision.duplicated().any())
 # Original individual support membership: read only eligibility timestamps and primary reasons.
 for station in ['pisco','huanta']:
  old=pd.read_csv(ROOT/f'experimento_{station}_inicio_v1/tablas/elegibilidad_adicional.csv',parse_dates=['emision'])
  old=old[(old.horizonte_h==h)&old.bloque.eq(block)&old.rol.eq(role)&old.motivo_primario.eq('incluida')]
  check(f'subconjunto_individual_{station}_{h}_{block}_{role}',g.emision.isin(old.emision).all())
(OUT/'verificacion_adicional.json').write_text(json.dumps({'resultado':'conforme','codigo_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'n_comprobaciones':len(checks),'comprobaciones':checks,'limites':'Sensores anunciados en derivados; no prueba continuidad histórica de instalación. Etiquetas corresponden al catálogo histórico.'},indent=2,ensure_ascii=False)+'\n')
print(f'Controles adicionales conformes: {len(checks)}')
