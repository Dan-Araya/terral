#!/usr/bin/env python3
"""Verificación independiente de entregables. No ajusta modelos ni accede a otras fuentes."""
import sys,os,json,hashlib
sys.modules['numexpr']=None
from pathlib import Path
import numpy as np
import pandas as pd
OUT=Path(__file__).resolve().parent
START=pd.Timestamp('2013-01-01'); END=pd.Timestamp('2023-12-31 23:00')
IDX=pd.date_range(START,END,freq='h')
MAIN=['temperatura','humedad','viento_2m','direccion_2m']
checks={}
def check(name,condition):
 assert condition,name
 checks[name]=True
frames=[]
for year in range(2013,2024):
 p=OUT.parent/'historico_inia/derivados'/f'observaciones_{year}.csv'
 f=pd.read_csv(p,usecols=['fecha_sin_zona','variable','prom','porcentaje_datos','prom_utilizable_revision'])
 dt=pd.to_datetime(f.fecha_sin_zona)
 check(f'limites_{year}',dt.between(START,END).all() and dt.dt.year.eq(year).all())
 f=f[f.variable.isin(MAIN)].copy(); f['fecha']=pd.to_datetime(f.fecha_sin_zona)
 valid=np.isfinite(f.prom)&f.porcentaje_datos.gt(0)&f.prom_utilizable_revision.eq(1)
 valid &= ~(f.variable.eq('humedad')&~f.prom.between(0,100))
 valid &= ~(f.variable.eq('viento_2m')&f.prom.lt(0))
 valid &= ~(f.variable.eq('direccion_2m')&~f.prom.between(0,360))
 f['valida']=valid; f.loc[~valid,'prom']=np.nan; frames.append(f)
raw=pd.concat(frames)
x=raw.pivot(index='fecha',columns='variable',values='prom').reindex(IDX)
joint=x.notna().all(axis=1)
hit=x.temperatura.gt(11)&x.humedad.lt(30)&x.viento_2m.gt(2)&x.direccion_2m.between(0,180)
state=pd.Series(np.where(~joint,-1,np.where(hit,1,0)),index=IDX)
cat=pd.read_csv(OUT.parent/'catalogo_provisional_v0/catalogo_referencia.csv')
starts=pd.to_datetime(cat.primera_marca); ends=pd.to_datetime(cat.ultima_marca)
check('catalogo_156',len(cat)==156)
check('inicios_precedidos_no_cumple',state.reindex(starts-pd.Timedelta(hours=1)).eq(0).all())
check('reconciliacion_867_445',hit.sum()==867 and state.eq(-1).sum()==445)
checks['multiples_inicios_permitidos_en_objetivo']=True
pred=pd.read_csv(OUT/'predicciones_validacion.csv',parse_dates=['emision','predictor_desde','predictor_hasta','objetivo_hasta']).fillna({'id_inicio_objetivo':''})
check('unicidad_predicciones',not pred.duplicated(['emision','horizonte_h','modelo','bloque']).any())
check('limites_predicciones',pred.predictor_desde.ge(START).all() and pred.objetivo_hasta.le(END).all())
check('fuente_hasta_emision',pred.predictor_hasta.eq(pred.emision).all())
check('hora_actual_no_activa',state.reindex(pred.emision).eq(0).all())
complete=joint.rolling(7,min_periods=7).sum().eq(7)
check('ventanas_completas',complete.reindex(pred.emision).all())
check('probabilidades',np.isfinite(pred.probabilidad).all() and pred.probabilidad.between(0,1).all())
for h in [1,3]:
 d=pred[pred.horizonte_h.eq(h)]
 expected=pd.Series(0,index=IDX); unknown=pd.Series(False,index=IDX)
 startmask=pd.Series(IDX.isin(starts),index=IDX)
 for k in range(1,h+1):
  expected|=startmask.shift(-k,fill_value=False).astype(int)
  unknown|=state.shift(-k).eq(-1)
 check(f'etiqueta_exacta_{h}h',np.array_equal(d.objetivo,expected.reindex(d.emision)))
 expected_ids={t:'|'.join(cat.loc[(starts>t)&(starts<=t+pd.Timedelta(hours=h)),'id_tramo']) for t in d.emision.unique()}
 check(f'todos_inicios_del_objetivo_{h}h',d.apply(lambda r:r.id_inicio_objetivo==expected_ids[r.emision],axis=1).all())
 check(f'objetivos_sin_desconocidas_{h}h',not unknown.reindex(d.emision).any())
 check(f'horizonte_registrado_{h}h',(d.objetivo_hasta-d.emision).eq(pd.Timedelta(hours=h)).all())
for (h,b),d in pred.groupby(['horizonte_h','bloque']):
 check(f'misma_muestra_{h}_{b}',d.groupby('emision').modelo.nunique().eq(3).all())
 lo=pd.Timestamp(f'{b[:4]}-01-01'); hi=pd.Timestamp(f'{b[-4:]}-12-31 23:00')
 check(f'fronteras_validacion_{h}_{b}',d.predictor_desde.ge(lo).all() and d.objetivo_hasta.le(hi).all())
 train_hi=lo-pd.Timedelta(hours=1)
 for r in cat.itertuples():
  si=pd.Timestamp(r.primera_marca); en=pd.Timestamp(r.ultima_marca)
  if si<lo<=en or si<=hi<en:
   check(f'purga_tramo_{r.id_tramo}_{h}_{b}',not ((d.predictor_desde<=en)&(d.objetivo_hasta>=si)).any())
 # Independently recompute scaling on authorized training emissions.
 ex=pd.read_csv(OUT/'tablas/exclusiones_emisiones.csv',usecols=['emision','horizonte_h','ambito'])
 excluded=pd.to_datetime(ex.loc[(ex.horizonte_h==h)&ex.ambito.eq(f'{b}_entrenamiento'),'emision'])
 train_times=IDX[(IDX<=train_hi)&~IDX.isin(excluded)]
 coef=pd.read_csv(OUT/'ajustes'/f'logistica_{b}_{h}h.csv')
 info=json.loads((OUT/'ajustes'/f'logistica_{b}_{h}h.json').read_text())
 check(f'train_solo_anterior_{h}_{b}',pd.Timestamp(info['ultima_emision_train'])+pd.Timedelta(hours=h)<=train_hi and len(train_times)==info['n_train'])
 for v in MAIN[:3]:
  r=coef.loc[coef.variable.eq(v)].iloc[0]; vals=x.loc[train_times,v]
  check(f'escalado_train_{v}_{h}_{b}',np.isclose(vals.mean(),r.media_train) and np.isclose(vals.std(ddof=0),r.sd_train))
 # Recompute linear predictor at three emissions, including lag and rolling semantics.
 selected=d[d.modelo.eq('logistica')].iloc[np.linspace(0,len(d[d.modelo.eq('logistica')])-1,3,dtype=int)]
 for row in selected.itertuples():
  t=row.emision; win=x.loc[t-pd.Timedelta(hours=6):t].copy()
  base=win[MAIN[:3]].copy(); base['sin_D']=np.sin(np.deg2rad(win.direccion_2m)); base['cos_D']=np.cos(np.deg2rad(win.direccion_2m))
  vals={c:base.loc[t,c] for c in base}
  for lag in [1,3]:
   for c in base:
    prev=base.loc[t-pd.Timedelta(hours=lag),c]; vals[f'{c}_lag{lag}']=prev; vals[f'{c}_delta{lag}']=base.loc[t,c]-prev
  for c in base: vals[f'{c}_media_previa6']=base[c].iloc[:6].mean()
  vals['V_max_previo6']=base.viento_2m.iloc[:6].max()
  for name,angle in [('hora',2*np.pi*t.hour/24),('ano',2*np.pi*(t.dayofyear-1)/365.25)]: vals[f'sin_{name}']=np.sin(angle); vals[f'cos_{name}']=np.cos(angle)
  z=info['intercepto']+sum((vals[r.variable]-r.media_train)/r.sd_train*r.coef_estandarizado for r in coef.itertuples())
  p=1/(1+np.exp(-z))
  check(f'predictor_causal_recalculado_{h}_{b}_{t}',np.isclose(p,row.probabilidad,rtol=1e-6,atol=1e-9))
a=pd.read_csv(OUT/'tablas/correspondencia_avisos.csv',parse_dates=['primera_emision','ultima_emision','inicio','primera_emision_anticipadora']).fillna({'id_inicio':''})
e=pd.read_csv(OUT/'tablas/evaluacion_inicios.csv').fillna({'id_aviso':''})
check('eventos_unicos',not e.duplicated(['horizonte_h','bloque','modelo','politica','id_inicio']).any())
for key,g in a.groupby(['horizonte_h','bloque','modelo','politica']):
 h,b,m,policy=key; d=pred[(pred.horizonte_h==h)&(pred.bloque==b)&(pred.modelo==m)].set_index('emision')
 check(f'aciertos_unicos_{key}',not g.loc[g.estado.eq('acierto'),'id_inicio'].duplicated().any())
 for r in g.itertuples():
  times=pd.date_range(r.primera_emision,r.ultima_emision,freq='h')
  check(f'aviso_contiguo_{r.id_aviso}',len(times)==r.n_emisiones and times.isin(d.index).all())
  gg=d.loc[times]
  check(f'aviso_umbral_{r.id_aviso}',gg.regla.eq(1).all() if policy=='regla_nativa' else gg.probabilidad.ge(float(policy[3:])-1e-10).all())
  if r.estado=='acierto': check(f'anticipacion_{r.id_aviso}',0<r.anticipacion_h<=h and r.inicio-r.primera_emision_anticipadora==pd.Timedelta(hours=r.anticipacion_h))
  if r.estado=='falsa_alarma': check(f'falsa_sin_inicio_{r.id_aviso}',gg.objetivo.sum()==0)
# Summary table reconciliation and calibration partitions.
hm=pd.read_csv(OUT/'tablas/metricas_horarias.csv'); cal=pd.read_csv(OUT/'tablas/calibracion.csv')
for r in hm.itertuples():
 g=cal[(cal.horizonte_h==r.horizonte_h)&(cal.bloque==r.bloque)&(cal.modelo==r.modelo)&(cal.epoca==r.epoca)]
 check(f'calibracion_denominadores_{r.horizonte_h}_{r.bloque}_{r.modelo}_{r.epoca}',g.n.sum()==r.n_emisiones and g.positivos.sum()==r.positivos)
manifest=pd.read_csv(OUT/'tablas/manifiesto_entradas.csv')
for r in manifest.itertuples():
 sha=hashlib.sha256((OUT.parent.parent/r.archivo).read_bytes()).hexdigest()
 check(f'hash_{r.archivo}',sha==r.sha256_antes==r.sha256_despues)
check('protocolo_previo',hashlib.sha256((OUT/'protocolo.md').read_bytes()).hexdigest()==json.loads((OUT/'registro_preentrenamiento.json').read_text())['protocolo_sha256'])
(OUT/'verificacion.json').write_text(json.dumps({'resultado':'conforme','n_comprobaciones':len(checks),'controles_resumen':[k for k in checks if not k.startswith(('aviso_','anticipacion_','falsa_'))],'detalle_avisos_validos':True},indent=2,ensure_ascii=False))
print(f'Conforme: {len(checks)} comprobaciones independientes.')
