#!/usr/bin/env python3
"""Verifica artefactos guardados; no entrena, descarga ni modifica fuentes."""
import sys,os,json,hashlib
os.environ['OPENBLAS_NUM_THREADS']='1'; os.environ['MPLCONFIGDIR']='/tmp/huanta-v1-mpl'; sys.modules['numexpr']=None; sys.dont_write_bytecode=True
from pathlib import Path
import importlib.util
import numpy as np
import pandas as pd
BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('exp',BASE/'ejecutar.py'); e=importlib.util.module_from_spec(spec); spec.loader.exec_module(e)
OUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else BASE
checks={}
def check(k,v):
 assert v,k
 checks[k]=True
manifest=pd.read_csv(OUT/'tablas/manifiesto_fuentes.csv')
for r in manifest.itertuples(): check('hash_'+r.archivo,e.b.digest(e.b.ROOT/r.archivo)==r.sha256_antes==r.sha256_despues)
reg=json.loads((OUT/'registro_preentrenamiento.json').read_text())
code_name='ejecutar.py'
if e.b.digest(OUT/code_name)!=reg['codigo_sha256']:
 corr=json.loads((OUT/'correccion_codigo.json').read_text())
 check('cadena_correccion_codigo',corr['codigo_registrado_sha256']==reg['codigo_sha256'] and corr['codigo_corregido_sha256']==e.b.digest(OUT/code_name))
 code_name='ejecutar_registrado_v1.py'
for name,key in [('protocolo.md','protocolo_sha256'),('predictores.json','predictores_sha256'),(code_name,'codigo_sha256'),('manifiesto_previo.json','manifiesto_previo_sha256')]: check('previo_'+name,e.b.digest(OUT/name)==reg[key])
e.b.save=lambda *args: None
x,state,cat,_=e.b.ingest(); p,pe=e.load_extra([]); features=e.allfeatures(x,p,pe)
cols=json.loads((OUT/'predictores.json').read_text())
pred=pd.read_csv(OUT/'predicciones_validacion.csv',parse_dates=['emision','predictor_desde','predictor_hasta','objetivo_hasta']).fillna({'id_inicio_objetivo':''})
additional=pd.read_csv(OUT/'tablas/elegibilidad_adicional.csv',parse_dates=['emision'])
starts=cat[cat.inicio_conocido]
for (h,block),d in pred.groupby(['horizonte_h','bloque']):
 check(f'soporte_comun_{h}_{block}',d.groupby('emision').modelo.nunique().eq(4).all() and d.groupby('emision').objetivo.nunique().eq(1).all())
 check(f'fuente_hasta_t_{h}_{block}',d.predictor_hasta.eq(d.emision).all() and d.predictor_desde.eq(d.emision-pd.Timedelta(hours=6)).all())
 check(f'limites_{h}_{block}',d.predictor_desde.ge(pd.Timestamp(block[:4]+'-01-01')).all() and d.objetivo_hasta.le(pd.Timestamp(block[-4:]+'-12-31 23:00')).all())
 check(f'estado_emision_{h}_{block}',state.reindex(d.emision).eq(0).all())
 check(f'no_duplicados_{h}_{block}',not d.duplicated(['modelo','emision']).any())
 for k in range(1,h+1): check(f'objetivo_conocido_{h}_{block}_{k}',state.reindex(d.emision+pd.Timedelta(hours=k)).ne(-1).all())
 one=d[d.modelo.eq('A')]
 ids=['|'.join(starts.loc[(starts.inicio>t)&(starts.inicio<=t+pd.Timedelta(hours=h)),'id_tramo']) for t in one.emision]
 check(f'etiquetas_exactas_{h}_{block}',np.array_equal(one.id_inicio_objetivo,ids) and np.array_equal(one.objetivo,np.array(ids)!=''))
 for role in ['entrenamiento','validacion']:
  z=additional[(additional.horizonte_h==h)&(additional.bloque==block)&additional.rol.eq(role)&additional.motivo_primario.eq('incluida')]
  times=pd.DatetimeIndex(z.emision)
  check(f'calidad_completa_{h}_{block}_{role}',pd.concat([x,p.rename('P'),pe.add_prefix('LLH_')],axis=1).notna().all(axis=1).rolling(7,min_periods=7).sum().eq(7).reindex(times).all())
  if role=='entrenamiento': train_times=times
  else: check(f'soporte_guardado_{h}_{block}',np.array_equal(times,one.emision))
 for arm in 'ABCD':
  coef=pd.read_csv(OUT/f'ajustes/{arm}/ajustes/logistica_{block}_{h}h.csv'); info=json.loads((OUT/f'ajustes/{arm}/ajustes/logistica_{block}_{h}h.json').read_text())
  check(f'columnas_{arm}_{h}_{block}',list(coef.variable)==cols[arm])
  xx=features.loc[train_times,cols[arm]].to_numpy(); sd=xx.std(axis=0); sd[sd==0]=1
  check(f'escala_entrenamiento_{arm}_{h}_{block}',np.allclose(xx.mean(axis=0),coef.media_train) and np.allclose(sd,coef.sd_train) and len(train_times)==info['n_train'])
  check(f'train_antes_validacion_{arm}_{h}_{block}',train_times.max()+pd.Timedelta(hours=h)<pd.Timestamp(block[:4]+'-01-01'))
  v=d[d.modelo.eq(arm)]; calc=e.b.expit(info['intercepto']+((features.loc[v.emision,cols[arm]].to_numpy()-coef.media_train.to_numpy())/coef.sd_train.to_numpy())@coef.coef_estandarizado.to_numpy())
  check(f'probabilidades_recalculadas_{arm}_{h}_{block}',np.allclose(v.probabilidad,calc,rtol=1e-9,atol=1e-11))
check('probabilidades_finitas',np.isfinite(pred.probabilidad).all() and pred.probabilidad.between(0,1).all())
a=pd.read_csv(OUT/'tablas/correspondencia_avisos.csv',parse_dates=['primera_emision','ultima_emision','primera_emision_anticipadora','inicio']).fillna({'id_inicio':''})
for (h,block,arm,policy),g in a.groupby(['horizonte_h','bloque','modelo','politica']):
 d=pred[(pred.horizonte_h==h)&(pred.bloque==block)&(pred.modelo==arm)].set_index('emision')
 check(f'aciertos_unicos_{h}_{block}_{arm}_{policy}',not g.loc[g.estado.eq('acierto'),'id_inicio'].duplicated().any())
 for r in g.itertuples():
  times=pd.date_range(r.primera_emision,r.ultima_emision,freq='h')
  check('grupo_'+r.id_aviso,len(times)==r.n_emisiones and times.isin(d.index).all() and d.loc[times].probabilidad.ge(float(policy[3:])-1e-11).all())
  if r.estado=='acierto': check('anticipo_'+r.id_aviso,0<r.anticipacion_h<=h and r.inicio-r.primera_emision_anticipadora==pd.Timedelta(hours=r.anticipacion_h))
  if r.estado=='falsa_alarma': check('falsa_'+r.id_aviso,not d.loc[times].objetivo.any())
hm=pd.read_csv(OUT/'tablas/metricas_horarias.csv'); cal=pd.read_csv(OUT/'tablas/calibracion.csv')
for r in hm.itertuples():
 z=cal[(cal.horizonte_h==r.horizonte_h)&(cal.bloque==r.bloque)&(cal.modelo==r.modelo)&(cal.epoca==r.epoca)]
 check(f'denominadores_{r.horizonte_h}_{r.bloque}_{r.modelo}_{r.epoca}',z.n.sum()==r.n_emisiones and z.positivos.sum()==r.positivos)
# Independent reconstruction: no eligibility/support function or saved flags used as input.
full=pd.concat([x,p.rename('P'),pe.add_prefix('LLH_')],axis=1)
window=pd.Series(True,index=e.IDX)
for lag in range(7): window &= full.notna().all(axis=1).shift(lag,fill_value=False)
base_window=pd.Series(True,index=e.IDX)
for lag in range(7): base_window &= x.notna().all(axis=1).shift(lag,fill_value=False)
unknown_starts=cat[~cat.inicio_conocido].inicio
for h in [1,3]:
 target_bad=pd.Series(False,index=e.IDX)
 for k in range(1,h+1):
  target_bad |= state.shift(-k).eq(-1) | pd.Series(e.IDX.isin(unknown_starts),index=e.IDX).shift(-k,fill_value=False)
 for block,ty,vs,ve in e.b.BLOCKS:
  for role,lo,hi in [('entrenamiento',e.b.START,pd.Timestamp(f'{ty}-12-31 23:00')),('validacion',pd.Timestamp(f'{vs}-01-01'),pd.Timestamp(f'{ve}-12-31 23:00'))]:
   t=e.IDX
   basic=state.eq(0)&~target_bad&base_window&(t-pd.Timedelta(hours=6)>=lo)&(t+pd.Timedelta(hours=h)<=hi)
   for r in cat.itertuples():
    if r.inicio<lo<=r.fin or r.inicio<=hi<r.fin:
     basic &= ~((t-pd.Timedelta(hours=6)<=r.fin)&(t+pd.Timedelta(hours=h)>=r.inicio))
   expected=t[basic&window]
   rows=additional[(additional.horizonte_h==h)&(additional.bloque==block)&additional.rol.eq(role)]
   check(f'base_reconstruida_{h}_{block}_{role}',np.array_equal(t[basic],rows.emision))
   check(f'exclusiones_reconstruidas_{h}_{block}_{role}',np.array_equal(expected,rows.loc[rows.motivo_primario.eq('incluida'),'emision']))
   iniaok=pd.Series(True,index=t); llhok=iniaok.copy()
   for lag in range(7):
    iniaok &= p.notna().shift(lag,fill_value=False)
    llhok &= pe.notna().all(axis=1).shift(lag,fill_value=False)
   for column,expectedflag in [('presion_INIA_ventana_incompleta',~iniaok),('Huanta_ventana_incompleta',~llhok)]:
    check(f'motivo_{column}_{h}_{block}_{role}',np.array_equal(rows[column],expectedflag.loc[rows.emision]))
   for v in pe:
    valid=pd.Series(True,index=t)
    for lag in range(7): valid &= pe[v].notna().shift(lag,fill_value=False)
    check(f'sensor_ventana_{v}_{h}_{block}_{role}',np.array_equal(rows[v+'_Huanta_ventana_incompleta'],(~valid).loc[rows.emision]))
   if role=='entrenamiento':
    yy=np.array([((starts.inicio>tt)&(starts.inicio<=tt+pd.Timedelta(hours=h))).any() for tt in expected],int)
    for arm in 'ABCD':
     info=json.loads((OUT/f'ajustes/{arm}/ajustes/logistica_{block}_{h}h.json').read_text())
     check(f'etiquetas_train_{h}_{block}_{arm}',info['positivos_train']==int(yy.sum()) and np.isclose(info['prior'],yy.mean()) and info['C']==1)
# AP implementation independent of b.pr, with tie grouping and optional bootstrap weights.
def metrics(y,pr,w=None):
 if w is None: w=np.ones(len(y))
 z=pd.DataFrame({'p':np.asarray(pr),'w':np.asarray(w),'pos':np.asarray(y)*np.asarray(w)})
 z=z.groupby('p',sort=True)[['w','pos']].sum().iloc[::-1]
 z=z[z.w.gt(0)]; positives=z.pos.sum()
 ap=float((z.pos*z.pos.cumsum()/z.w.cumsum()).sum()/positives) if positives else np.nan
 return {'AP':ap,'Brier':float(np.average((np.asarray(pr)-np.asarray(y))**2,weights=w))}
for r in hm.itertuples():
 d=pred[(pred.horizonte_h==r.horizonte_h)&(pred.bloque==r.bloque)&(pred.modelo==r.modelo)]
 if r.epoca!='ALL': d=d[d.epoca.eq(r.epoca)]
 for metric,value in metrics(d.objetivo,d.probabilidad).items(): check(f'metrica_{metric}_{r.horizonte_h}_{r.bloque}_{r.modelo}_{r.epoca}',np.isclose(value,getattr(r,metric),rtol=2e-8,atol=1e-12,equal_nan=True))
for tab,aggregated in [(cal,False),(pd.read_csv(OUT/'tablas/calibracion_agregada.csv'),True)]:
 for i,r in enumerate(tab.itertuples()):
  d=pred[(pred.horizonte_h==r.horizonte_h)&(pred.modelo==r.modelo)]
  if not aggregated:
   d=d[d.bloque.eq(r.bloque)]
   if r.epoca!='ALL': d=d[d.epoca.eq(r.epoca)]
  d=d[d.probabilidad.ge(r.limite_inf)&(d.probabilidad.lt(r.limite_sup) if r.limite_sup<1 else d.probabilidad.le(1))]
  check(f'calibracion_recalculada_{aggregated}_{i}',len(d)==r.n and d.objetivo.sum()==r.positivos and np.isclose(d.probabilidad.mean(),r.p_media,rtol=2e-8,atol=1e-12,equal_nan=True) and np.isclose(d.objetivo.mean(),r.frecuencia_observada,rtol=2e-8,atol=1e-12,equal_nan=True))
samples=pd.read_csv(OUT/'tablas/bootstrap_muestras.csv')
rng=np.random.default_rng(20132023)
for rep in range(300):
 for block,_,_,_ in e.b.BLOCKS:
  months=pd.period_range(block[:4]+'-01',block[-4:]+'-12',freq='M').astype(str)
  counts=np.zeros(24,int)
  for start in rng.integers(0,22,8): counts[start:start+3]+=1
  rows=samples[(samples.replica==rep)&samples.bloque.eq(block)]
  check(f'muestreo_{rep}_{block}',np.array_equal(rows.mes,months) and np.array_equal(rows.multiplicidad,counts))
ci=pd.read_csv(OUT/'tablas/intervalos_pareados.csv').fillna({'politica':''})
for h in [1,3]:
 wide=pred[pred.horizonte_h.eq(h)].pivot(index=['bloque','emision','objetivo'],columns='modelo',values='probabilidad').reset_index()
 keys=pd.MultiIndex.from_arrays([wide.bloque,wide.emision.dt.strftime('%Y-%m')])
 reps={arm:{metric:[] for metric in ['AP','Brier']} for arm in 'ABCD'}
 for rep,z in samples.groupby('replica'):
  w=z.set_index(['bloque','mes']).multiplicidad.reindex(keys).to_numpy()
  for arm in 'ABCD':
   for metric,val in metrics(wide.objetivo,wide[arm],w).items(): reps[arm][metric].append(val)
 for metric in ['AP','Brier']:
  for contrast in list('ABCD')+['B-A','C-A','D-B']:
   if '-' in contrast:
    new,old=contrast.split('-'); vals=np.array(reps[new][metric])-reps[old][metric]
    point=metrics(wide.objetivo,wide[new])[metric]-metrics(wide.objetivo,wide[old])[metric]
   else: vals=reps[contrast][metric]; point=metrics(wide.objetivo,wide[contrast])[metric]
   r=ci[(ci.horizonte_h==h)&ci.contraste.eq(contrast)&ci.metrica.eq(metric)].iloc[0]
   check(f'IC_independiente_{h}_{metric}_{contrast}',np.allclose([point,*np.quantile(vals,[.025,.975])],[r.estimacion,r.p025,r.p975],rtol=3e-8,atol=1e-11))
# Preserved original experiment and baseline artifacts; excludes no source after the fact.
protected=json.loads((BASE/'conservacion_previa.json').read_text())
for row in protected: check('conservacion_'+row['archivo'],e.b.digest(e.b.ROOT/row['archivo'])==row['sha256'])
(OUT/'verificacion_independiente.json').write_text(json.dumps({'resultado':'conforme','n_comprobaciones':len(checks),'controles_resumen':[k for k in checks if not k.startswith(('grupo_','anticipo_','falsa_'))]},indent=2,ensure_ascii=False)+'\n')
print(f'Conforme: {len(checks)} comprobaciones independientes')
