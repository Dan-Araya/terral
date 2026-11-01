"""Auditoría independiente de artefactos, etiquetas, soporte, OOF y correspondencias."""
import os,sys
os.environ['OPENBLAS_NUM_THREADS']='1'; sys.modules['numexpr']=None; sys.dont_write_bytecode=True
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.special import expit
import estudio as e

def read_csv(*args,**kwargs):
 kwargs.setdefault('float_precision','round_trip')
 return pd.read_csv(*args,**kwargs)

def oof_counts(d,cat,threshold):
 d=d.sort_values('emision'); times=d.emision.to_numpy(); active=np.flatnonzero(d.probabilidad.to_numpy()>=threshold); target=d.id_inicio_objetivo.to_numpy(); onset=cat.set_index('id_tramo').inicio.to_dict(); used=set(); fp=0
 breaks=np.flatnonzero(np.diff(times[active])!=np.timedelta64(1,'h'))+1 if len(active)>1 else []
 for group in np.split(active,breaks):
  if not len(group):continue
  candidates={v for value in target[group] for v in value.split('|') if v}
  match=next((cid for cid in sorted(candidates,key=onset.get) if cid not in used),'')
  if match:used.add(match)
  elif not candidates:fp+=1
 eligible={v for value in target for v in value.split('|') if v}
 return dict(inicios_evaluables=len(eligible),inicios_anticipados=len(used),falsas_alarmas=fp,horas_bajo_aviso=len(active))

def verify(out):
 e.OUT=Path(out); e.ETAPA=next(k for k,v in e.CONFIG['etapas'].items() if v.get('slug')==e.s.STATION); e.setup(); checks={}
 def ck(name,v):
  assert bool(v),name
  checks[name]=True
 def near(a,b): return np.allclose(a,b,rtol=1e-8,atol=1e-10,equal_nan=True)
 reg=json.loads((e.OUT/'registro_preentrenamiento.json').read_text()); ck('fuentes_y_codigo_intactos',reg['fuentes']==e.sources())
 x,state,cat,f,cols,yy,ids,future,ds=e.prepare()
 ck('catalogo_reconciliado',len(cat)==156 and state.eq(1).sum()==867)
 # Independent scalar quality on INIA, not its ingestion mask.
 raw=pd.concat([read_csv(e.ROOT/f'historico_inia/derivados/observaciones_{y}.csv',usecols=['fecha_sin_zona','variable','prom','porcentaje_datos','prom_utilizable_revision']) for y in range(2013,2024)],ignore_index=True)
 for variable in e.b.MAIN+['presion']:
  q=raw[raw.variable.eq(variable)].copy(); t=pd.to_datetime(q.fecha_sin_zona)
  ck('limites_'+variable,t.between(e.b.START,e.b.END).all() and not t.duplicated().any())
  good=np.isfinite(q.prom)&q.porcentaje_datos.gt(0)&q.porcentaje_datos.le(100)&q.prom_utilizable_revision.eq(1)
  if variable=='humedad': good &= q.prom.between(0,100)
  if variable=='viento_2m': good &= q.prom.ge(0)
  if variable=='direccion_2m': good &= q.prom.between(0,360)
  expected=pd.Series(q.prom.where(good).to_numpy(),index=t).reindex(e.b.IDX)
  actual=f.INIA_presion if variable=='presion' else x[variable]
  ck('calidad_independiente_'+variable,near(expected,actual))
 # Independent future targets by onset timestamp search, not shift/rolling.
 starts=cat[cat.inicio_conocido]; known=starts.inicio.to_numpy(); idarr=starts.id_tramo.to_numpy()
 for h in e.H:
  for bl,ty,vs,ve in e.b.BLOCKS:
   for role in ['train','val']:
    d=ds[bl,role,h]; times=d.index; lo=pd.Timestamp('2013-01-01' if role=='train' else f'{vs}-01-01'); hi=pd.Timestamp(f'{ty if role=="train" else ve}-12-31 23:00')
    ck(f'fronteras24_{bl}_{role}_{h}',((times-pd.Timedelta(hours=6)>=lo)&(times+pd.Timedelta(hours=24)<=hi)).all())
    ck(f'estado_{bl}_{role}_{h}',state.reindex(times).eq(0).all())
    for k in range(1,25): ck(f'futuro_conocido_{bl}_{role}_{h}_{k}',state.reindex(times+pd.Timedelta(hours=k)).ge(0).all())
    left=np.searchsorted(known,times.to_numpy(),side='right'); right=np.searchsorted(known,(times+pd.Timedelta(hours=h)).to_numpy(),side='right')
    target=['|'.join(idarr[a:b]) for a,b in zip(left,right)]
    ck(f'etiquetas_ids_{bl}_{role}_{h}',np.array_equal(target,d.id_inicio_objetivo) and np.array_equal(right>left,d.y))
    # Compute all eligible times independently from scalar windows, future and purges.
    scalar=['temperatura','humedad','viento_2m','sin_D','cos_D','INIA_presion','PE_temperatura','PE_humedad','PE_viento','PE_presion','PE_sin_D','PE_cos_D']
    scalar=[c for c in scalar if c in f]
    alltimes=e.b.IDX; ok=(alltimes-pd.Timedelta(hours=6)>=lo)&(alltimes+pd.Timedelta(hours=24)<=hi)&state.eq(0).to_numpy()
    present=f[scalar].notna().all(axis=1)
    for k in range(7): ok &= present.reindex(alltimes-pd.Timedelta(hours=k),fill_value=False).to_numpy()
    for k in range(1,25): ok &= state.reindex(alltimes+pd.Timedelta(hours=k),fill_value=-1).ge(0).to_numpy() & ~e.UNCERTAIN.reindex(alltimes+pd.Timedelta(hours=k),fill_value=True).to_numpy()
    for r in cat.itertuples():
     if r.inicio<lo<=r.fin or r.inicio<=hi<r.fin: ok &= ~((alltimes-pd.Timedelta(hours=6)<=r.fin)&(alltimes+pd.Timedelta(hours=24)>=r.inicio))
    ck(f'soporte_exacto_{bl}_{role}_{h}',times.equals(alltimes[ok]))
 # Causal invariance, all feature values preceding cutoff.
 for cutoff in ['2016-03-14 12:00','2019-12-31 23:00','2023-06-30 12:00']:
  # Reconstruct features from independent seven-row windows at multiple cutoffs.
  t=pd.Timestamp(cutoff); idx=pd.date_range(t-pd.Timedelta(hours=6),t,freq='h'); w=f.reindex(idx)
  for current in ['temperatura','humedad','viento_2m','INIA_presion','PE_temperatura','PE_humedad','PE_viento','PE_presion','PE_sin_D','PE_cos_D','sin_D','cos_D']:
   for lag in [1,3]:
    ck(f'feature_{cutoff}_{current}_{lag}',near(w[current].iloc[-1-lag],f.loc[t,current+f'_lag{lag}']) and near(w[current].iloc[-1]-w[current].iloc[-1-lag],f.loc[t,current+f'_delta{lag}']))
   ck(f'media_{cutoff}_{current}',near(w[current].iloc[:6].mean() if w[current].iloc[:6].notna().all() else np.nan,f.loc[t,current+'_media_previa6']))
 def modelcheck(train,val,columns,h,tag,path,pred):
  co=read_csv(path/'ajustes'/f'logistica_{tag}_{h}h.csv'); meta=json.loads((path/'ajustes'/f'logistica_{tag}_{h}h.json').read_text()); X=train[columns].to_numpy(); sd=X.std(axis=0); sd[sd==0]=1
  ck(f'escala_{path}',list(co.variable)==columns and near(co.media_train,X.mean(axis=0)) and near(co.sd_train,sd))
  ck(f'prior_train_{path}',near(pred.p_constante_train,train.y.mean()) and meta['n_train']==len(train) and meta['positivos_train']==int(train.y.sum()))
  p=expit(meta['intercepto']+((val[columns].to_numpy()-co.media_train.to_numpy())/co.sd_train.to_numpy())@co.coef_estandarizado.to_numpy())
  ck(f'prediccion_{path}',near(p,pred.probabilidad) and np.array_equal(pred.objetivo,val.y) and list(pred.emision)==list(val.index))
 policies=[]
 for bl,ty,vs,ve in e.b.BLOCKS:
  for h in e.H:
   for arm in 'ABCD':
    path=e.OUT/'unidades'/bl/f'{h}h'/arm; ck(f'hashes_unidad_{bl}_{h}_{arm}',e.unit_valid(path,reg['firma']))
    p=read_csv(path/'predicciones.csv',parse_dates=['emision']); modelcheck(ds[bl,'train',h],ds[bl,'val',h],cols[arm],h,bl,path/'externo',p)
    oof=read_csv(path/'oof.csv',parse_dates=['emision']).fillna({'id_inicio_objetivo':''}); internal=[]
    ck(f'OOF_sin_duplicados_{bl}_{h}_{arm}',not oof.emision.duplicated().any())
    for vy,g in oof.groupby('fold'):
     tr=e.dataset(f,state,cat,yy,ids,future,'2013-01-01',f'{vy-1}-12-31 23:00',h); va=e.dataset(f,state,cat,yy,ids,future,f'{vy}-01-01',f'{vy}-12-31 23:00',h)
     ck(f'OOF_purga_{bl}_{h}_{arm}_{vy}',tr.index.max()+pd.Timedelta(hours=24)<va.index.min()-pd.Timedelta(hours=6) and vy<=ty)
     modelcheck(tr,va,cols[arm],h,str(vy),path/'interno'/str(vy),g)
    im=read_csv(path/'evaluacion_interna.csv'); pol=json.loads((path/'politicas_congeladas.json').read_text())
    for threshold in e.CONFIG['umbrales']:
     ms=[oof_counts(g,cat,threshold) for vy,g in oof.groupby('fold')]
     r=im[im.umbral.eq(threshold)].iloc[0]; ck(f'OOF_metricas_{bl}_{h}_{arm}_{threshold}',near([r.n_oof,r.meses,r.eventos,r.detectados,r.falsas,r.tasa,r.horas_aviso],[len(oof),len(oof)/e.MONTH,sum(m['inicios_evaluables'] for m in ms),sum(m['inicios_anticipados'] for m in ms),sum(m['falsas_alarmas'] for m in ms),sum(m['falsas_alarmas'] for m in ms)/(len(oof)/e.MONTH),sum(m['horas_bajo_aviso'] for m in ms)]))
    for policy in pol:
     feasible=[r for r in im.itertuples() if r.tasa<=policy['presupuesto'] and r.meses>=12 and r.eventos>=10]
     chosen=sorted(feasible,key=lambda r:(-r.detectados,r.tasa,r.horas_aviso,-r.umbral))[0] if feasible else None
     ck(f'politica_OOF_{bl}_{h}_{arm}_{policy["presupuesto"]}',policy['umbral']==(None if chosen is None else chosen.umbral))
     policies.append(dict(bloque=bl,horizonte_h=h,modelo=arm,**policy))
 pred=read_csv(e.OUT/'predicciones_validacion.csv',parse_dates=['emision']).fillna({'id_inicio_objetivo':''}); a=read_csv(e.OUT/'tablas/correspondencia_avisos.csv',parse_dates=['primera_emision','ultima_emision']).fillna({'id_inicio':'','candidatos':''}); events=read_csv(e.OUT/'tablas/evaluacion_inicios.csv')
 onset_lookup=cat.set_index('id_tramo').inicio.to_dict()
 m=read_csv(e.OUT/'tablas/metricas_avisos.csv'); pm=read_csv(e.OUT/'tablas/metricas_probabilidades.csv'); cal=read_csv(e.OUT/'tablas/calibracion.csv')
 for (h,bl,arm),d in pred.groupby(['horizonte_h','bloque','modelo']):
  ck(f'comun_{h}_{bl}_{arm}',len(d)==len(ds[bl,'val',h]))
  for r in m[(m.horizonte_h==h)&m.bloque.eq(bl)&m.modelo.eq(arm)].itertuples():
   on=d[d.probabilidad>=r.umbral].sort_values('emision'); groups=[]
   for rr in on.itertuples():
    if not groups or rr.emision-groups[-1][-1].emision!=pd.Timedelta(hours=1): groups.append([])
    groups[-1].append(rr)
   stored=a[(a.horizonte_h==h)&a.bloque.eq(bl)&a.modelo.eq(arm)&a.politica.eq(r.politica)]
   ck(f'grupos_{h}_{bl}_{arm}_{r.politica}',len(stored)==len(groups)); used=set(); lead=[]; fp=red=0
   for group,saved in zip(groups,stored.itertuples()):
    candidates={v for rr in group for v in rr.id_inicio_objetivo.split('|') if v}; ordered=sorted(candidates,key=onset_lookup.get); match=next((cid for cid in ordered if cid not in used),'')
    status='acierto' if match else ('redundante' if candidates else 'falsa_alarma'); ck(f'correspondencia_{h}_{bl}_{arm}_{r.politica}_{saved.id_aviso}',saved.estado==status and saved.id_inicio==match and saved.n_emisiones==len(group) and saved.primera_emision==group[0].emision and saved.ultima_emision==group[-1].emision)
    fp+=status=='falsa_alarma'; red+=status=='redundante'
    if match:
     used.add(match); onset=onset_lookup[match]; first=next(rr.emision for rr in group if match in rr.id_inicio_objetivo.split('|')); lead.append((onset-first)/pd.Timedelta(hours=1)); ck(f'anticipacion_{h}_{bl}_{arm}_{r.politica}_{match}',near(lead[-1],saved.anticipacion_h))
   ne=len({v for ids_ in d.id_inicio_objetivo for v in ids_.split('|') if v})
   ck(f'metricas_avisos_{h}_{bl}_{arm}_{r.politica}',near([r.inicios_evaluables,r.inicios_anticipados,r.inicios_omitidos,r.falsas_alarmas,r.redundantes,r.falsas_alarmas_por_mes,r.horas_bajo_aviso,r.proporcion_tiempo_aviso],[ne,len(used),ne-len(used),fp,red,fp/(len(d)/e.MONTH),len(on),len(on)/len(d)]))
   for k in e.H:
    if k<=h: ck(f'denominador_anticipacion_{h}_{bl}_{arm}_{r.politica}_{k}',near(getattr(r,f'fraccion_eventos_ge_{k}h'),sum(v>=k for v in lead)/ne))
 for r in pm.itertuples():
  d=pred[(pred.horizonte_h==r.horizonte_h)&pred.modelo.eq(r.modelo)]
  if r.bloque!='AGREGADO': d=d[d.bloque.eq(r.bloque)]
  # Independent AP: tie-grouped cumulative precision/recall.
  grouped=d.groupby('probabilidad').objetivo.agg(['sum','size']).sort_index(ascending=False); tp=grouped['sum'].cumsum(); nn=grouped['size'].cumsum(); ap=((tp/nn)*grouped['sum']/d.objetivo.sum()).sum()
  ck(f'prob_metricas_{r.horizonte_h}_{r.bloque}_{r.modelo}',near([r.n_emisiones,r.positivos,r.AP,r.Brier,r.Brier_constante_train],[len(d),d.objetivo.sum(),ap,np.mean((d.probabilidad-d.objetivo)**2),np.mean((d.p_constante_train-d.objetivo)**2)]))
  c=cal[(cal.horizonte_h==r.horizonte_h)&cal.bloque.eq(r.bloque)&cal.modelo.eq(r.modelo)]; ck(f'calibracion_{r.horizonte_h}_{r.bloque}_{r.modelo}',c.n.sum()==len(d) and c.positivos.sum()==d.objetivo.sum())
 boot=read_csv(e.OUT/'tablas/bootstrap_replicas.csv').fillna({'politica':''}); ci=read_csv(e.OUT/'tablas/intervalos_pareados.csv').fillna({'politica':''})
 for key,z in boot.groupby(['horizonte_h','politica','metrica','contraste']):
  r=ci[(ci.horizonte_h==key[0])&ci.politica.eq(key[1])&ci.metrica.eq(key[2])&ci.contraste.eq(key[3])].iloc[0]; v=z.valor.dropna()
  ck('intervalo_'+str(key),r.replicas_validas==len(v) and (near([r.p025,r.p975],np.quantile(v,[.025,.975])) if len(v) else pd.isna(r.p025)))
 samples=read_csv(e.OUT/'tablas/bootstrap_muestras.csv'); rng=np.random.default_rng(20132023)
 for rep in range(300):
  z=samples[samples.replica.eq(rep)]
  for bl,_,_,_ in e.b.BLOCKS:
   expected=np.zeros(24,int)
   for start in rng.integers(0,22,8): expected[start:start+3]+=1
   ck(f'bootstrap_original_{rep}_{bl}',np.array_equal(expected,z[z.bloque.eq(bl)].multiplicidad))
 ck('conservacion_final',e.sources()==reg['fuentes'])
 e.js(e.OUT/'verificacion_independiente.json',{'resultado':'conforme','comprobaciones':checks,'limite':'Mismas fuentes y lectores heredados; OOF métricas usa función compartida, correspondencia externa se reconstruye independientemente.'})
 e.js(e.OUT/'estado_etapa.json',{'estado':'verificado','etapa':'pisco','unidades':72,'otras_etapas':'pendientes_sin_entrenar'})
 e.js(e.OUT/'manifiesto_entregables.json',{str(p.relative_to(e.OUT)):e.digest(p) for p in sorted(e.OUT.rglob('*')) if p.is_file() and p.name not in ['manifiesto_entregables.json','reproduccion.json']})
 print('Verificación independiente conforme:',len(checks),flush=True)
if __name__=='__main__': verify(Path(sys.argv[1]) if len(sys.argv)>1 else e.OUT)
