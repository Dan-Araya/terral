#!/usr/bin/env python3
"""Línea base cerrada Vicuña–INIA 2013–2023. Sin red ni selección de modelos."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
os.environ.setdefault('MPLCONFIGDIR','/tmp/terral-matplotlib')
import sys
sys.modules['numexpr']=None
from pathlib import Path
import hashlib,json,platform
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit
import scipy
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
OUT=Path(__file__).resolve().parent
ROOT=OUT.parent.parent
START=pd.Timestamp('2013-01-01'); END=pd.Timestamp('2023-12-31 23:00')
IDX=pd.date_range(START,END,freq='h')
MAIN=['temperatura','humedad','viento_2m','direccion_2m']
BLOCKS=[('2018-2019',2017,2018,2019),('2020-2021',2019,2020,2021),('2022-2023',2021,2022,2023)]
THRESHOLDS=[.001,.003,.01,.03,.1,.3,.5]
for d in ['tablas','graficos','ajustes']: (OUT/d).mkdir(exist_ok=True)
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(df,name): df.to_csv(OUT/'tablas'/f'{name}.csv',index=False,float_format='%.10g')
def season(d):
 return np.select([d.month.isin([12,1,2]),d.month.isin([3,4,5]),d.month.isin([6,7,8])],['DJF','MAM','JJA'],default='SON')
def features(x):
 b=x[MAIN[:3]].copy()
 b['sin_D']=np.sin(np.deg2rad(x.direccion_2m)); b['cos_D']=np.cos(np.deg2rad(x.direccion_2m))
 f=b.copy()
 for lag in [1,3]:
  for c in b:
   f[f'{c}_lag{lag}']=b[c].shift(lag)
   f[f'{c}_delta{lag}']=b[c]-b[c].shift(lag)
 for c in b: f[f'{c}_media_previa6']=b[c].shift(1).rolling(6,min_periods=6).mean()
 f['V_max_previo6']=b.viento_2m.shift(1).rolling(6,min_periods=6).max()
 for name,angle in [('hora',2*np.pi*x.index.hour/24),('ano',2*np.pi*(x.index.dayofyear-1)/365.25)]:
  f[f'sin_{name}']=np.sin(angle); f[f'cos_{name}']=np.cos(angle)
 return f

def pr(y,p):
 y=np.asarray(y,int); p=np.asarray(p,float)
 order=np.argsort(-p,kind='stable'); yy=y[order]; pp=p[order]
 ends=np.r_[np.flatnonzero(pp[:-1]!=pp[1:]),len(pp)-1]
 tp=np.cumsum(yy)[ends]; n=ends+1
 precision=tp/n; recall=tp/y.sum() if y.sum() else np.full(len(tp),np.nan)
 ap=np.sum(np.diff(np.r_[0,recall])*precision) if y.sum() else np.nan
 return ap,pd.DataFrame({'umbral':pp[ends],'precision':precision,'recall':recall,'n_avisos_horarios':n,'verdaderos_horarios':tp})

def ingest():
 frames=[]; manifest=[]
 columns=['fecha_sin_zona','variable','prom','porcentaje_datos','prom_utilizable_revision','dentro_periodo']
 for year in range(2013,2024):
  path=OUT.parent/'historico_inia/derivados'/f'observaciones_{year}.csv'
  f=pd.read_csv(path,usecols=columns)
  dates=pd.to_datetime(f.fecha_sin_zona,errors='raise')
  assert dates.between(START,END).all() and dates.dt.year.eq(year).all()
  assert dates.eq(dates.dt.floor('h')).all() and f.dentro_periodo.eq(1).all()
  manifest.append({'archivo':str(path.relative_to(ROOT)),'sha256_antes':digest(path),'filas':len(f),'primera':dates.min(),'ultima':dates.max()})
  f=f[f.variable.isin(MAIN)].copy(); f['fecha']=pd.to_datetime(f.fecha_sin_zona)
  frames.append(f)
 raw=pd.concat(frames,ignore_index=True)
 assert not raw.duplicated(['fecha','variable']).any()
 valid=np.isfinite(raw.prom)&raw.porcentaje_datos.gt(0)&raw.prom_utilizable_revision.eq(1)
 valid &= ~(raw.variable.eq('humedad')&~raw.prom.between(0,100))
 valid &= ~(raw.variable.eq('viento_2m')&raw.prom.lt(0))
 valid &= ~(raw.variable.eq('direccion_2m')&~raw.prom.between(0,360))
 raw['valida']=valid
 v=raw.pivot(index='fecha',columns='variable',values='valida').reindex(IDX).fillna(False).astype(bool)
 x=raw.pivot(index='fecha',columns='variable',values='prom').reindex(IDX).where(v)
 joint=v.all(axis=1)
 hit=x.temperatura.gt(11)&x.humedad.lt(30)&x.viento_2m.gt(2)&x.direccion_2m.between(0,180)
 state=pd.Series(np.where(~joint,-1,np.where(hit,1,0)),index=IDX)
 path=OUT.parent/'catalogo_provisional_v0/catalogo_referencia.csv'
 cat=pd.read_csv(path); cat['inicio']=pd.to_datetime(cat.primera_marca); cat['fin']=pd.to_datetime(cat.ultima_marca)
 assert cat.inicio.between(START,END).all() and cat.fin.between(START,END).all()
 manifest.append({'archivo':str(path.relative_to(ROOT)),'sha256_antes':digest(path),'filas':len(cat),'primera':cat.inicio.min(),'ultima':cat.fin.max()})
 reconstructed=np.zeros(len(IDX),bool)
 for r in cat.itertuples():
  ii=IDX.get_indexer(pd.date_range(r.inicio,r.fin,freq='h')); assert (ii>=0).all()
  assert not reconstructed[ii].any(); reconstructed[ii]=True
  assert len(ii)==r.horas_candidatas
 assert np.array_equal(reconstructed,state.eq(1)) and len(cat)==156 and state.eq(1).sum()==867
 cat['inicio_conocido']=[d>START and state.loc[d-pd.Timedelta(hours=1)]==0 for d in cat.inicio]
 return x,state,cat,manifest

def eligibility(x,state,cat):
 f=features(x); complete=x.notna().all(axis=1).rolling(7,min_periods=7).sum().eq(7)
 assert f.shape[1]==35
 known=pd.Series(False,index=IDX); unknown_start=known.copy(); ids=pd.Series('',index=IDX)
 for r in cat.itertuples():
  (known if r.inicio_conocido else unknown_start).loc[r.inicio]=True
  if r.inicio_conocido: ids.loc[r.inicio]=r.id_tramo
 exclusions=[]; totals=[]; datasets={}
 for h in [1,3]:
  future_unknown=pd.Series(False,index=IDX); future_uncertain=future_unknown.copy(); y=pd.Series(0,index=IDX); target_ids=pd.Series('',index=IDX)
  for k in range(1,h+1):
   future_unknown |= state.shift(-k).eq(-1)
   future_uncertain |= unknown_start.shift(-k,fill_value=False)
   y |= known.shift(-k,fill_value=False).astype(int)
   z=ids.shift(-k,fill_value=''); target_ids=target_ids.where(z.eq(''),target_ids+np.where(target_ids.eq(''),'','|')+z)
  flags=pd.DataFrame({'estado_t_desconocido':state.eq(-1),'tramo_activo':state.eq(1),'objetivo_fuera_periodo':IDX+pd.Timedelta(hours=h)>END,'objetivo_desconocido':future_unknown,'inicio_no_conocido':future_uncertain,'ventana_previa_incompleta':~complete},index=IDX)
  def record(flags,scope):
   excluded=flags.any(axis=1)
   primary=pd.Series('incluida',index=flags.index)
   for c in reversed(list(flags.columns)): primary.loc[flags[c]]=c
   for c in flags:
    totals.append({'horizonte_h':h,'ambito':scope,'motivo':c,'n_con_motivo':int(flags[c].sum()),'n_primario':int(primary.eq(c).sum()),'horas_ambito':len(flags),'incluidas':int((~excluded).sum())})
   z=flags[excluded].copy(); z.insert(0,'motivo_primario',primary[excluded]); z.insert(0,'ambito',scope); z.insert(0,'horizonte_h',h); z.index.name='emision'; exclusions.append(z.reset_index())
   return ~excluded
  record(flags,'global_2013_2023')
  for block,ty,vs,ve in BLOCKS:
   for role,lo,hi in [('entrenamiento',START,pd.Timestamp(f'{ty}-12-31 23:00')),('validacion',pd.Timestamp(f'{vs}-01-01'),pd.Timestamp(f'{ve}-12-31 23:00'))]:
    mask=(IDX>=lo)&(IDX<=hi); ff=flags.loc[mask].copy(); times=ff.index
    ff['soporte_cruza_frontera']=(times-pd.Timedelta(hours=6)<lo)|(times+pd.Timedelta(hours=h)>hi)
    crossing=np.zeros(len(times),bool)
    for r in cat.itertuples():
     # Only catalog segments split by either edge of this partition.
     if (r.inicio<lo<=r.fin) or (r.inicio<=hi<r.fin):
      crossing |= (times-pd.Timedelta(hours=6)<=r.fin)&(times+pd.Timedelta(hours=h)>=r.inicio)
    ff['tramo_cruza_frontera']=crossing
    ok=record(ff,f'{block}_{role}'); times=times[ok]
    d=f.loc[times].copy(); d['y']=y.loc[times]; d['id_inicio_objetivo']=target_ids.loc[times]; d['regla']=((x.direccion_2m.between(0,180))&x.temperatura.gt(10)&x.humedad.lt(40)&x.viento_2m.gt(1)&f.temperatura_delta1.gt(0)&f.humedad_delta1.lt(0)&f.viento_2m_delta1.gt(0)).loc[times].astype(int)
    assert d.notna().all().all()
    assert (times-pd.Timedelta(hours=6)>=lo).all() and (times+pd.Timedelta(hours=h)<=hi).all()
    datasets[h,block,role]=d
 save(pd.concat(exclusions,ignore_index=True),'exclusiones_emisiones'); save(pd.DataFrame(totals),'exclusiones_resumen')
 return f,datasets

def fit_predict(train,val,cols,h,block):
 y=train.y.to_numpy(); prior=float(y.mean()); refs=[]
 hh=train.groupby(train.index.hour).y.agg(['size','sum'])
 hp=(hh['sum']+200*prior)/(hh['size']+200)
 mh=train.groupby([train.index.month,train.index.hour]).y.agg(['size','sum'])
 lookup={}
 for m in range(1,13):
  for hour in range(24):
   n,s=(mh.loc[(m,hour),['size','sum']] if (m,hour) in mh.index else [0,0])
   p=float((s+200*hp[hour])/(n+200)) if n>=100 else float(hp[hour])
   lookup[m,hour]=p; refs.append({'mes':m,'hora':hour,'n':n,'positivos':s,'p_global':prior,'n_hora':hh.loc[hour,'size'],'p_hora':hp[hour],'p':p,'fallback_n_menor100':n<100})
 save(pd.DataFrame(refs).assign(horizonte_h=h,bloque=block),f'referencia_{block}_{h}h')
 rr=train.groupby('regla').y.agg(['size','sum']); rp={}
 for r in [0,1]:
  n,s=rr.loc[r,['size','sum']] if r in rr.index else [0,0]
  rp[r]=float((s+20*prior)/(n+20))
 X=train[cols].to_numpy(); mean=X.mean(axis=0); sd=X.std(axis=0); sd[sd==0]=1; X=(X-mean)/sd
 X=np.column_stack([np.ones(len(X)),X])
 def objective(beta):
  z=X@beta; p=expit(z); penalty=beta.copy(); penalty[0]=0
  return float(np.logaddexp(0,z).sum()-y@z+.5*penalty@penalty),X.T@(p-y)+penalty
 initial=np.zeros(X.shape[1]); initial[0]=np.log(prior/(1-prior))
 result=minimize(objective,initial,jac=True,method='L-BFGS-B',options={'maxiter':1000,'gtol':1e-6,'ftol':1e-12})
 assert result.success, result.message
 V=np.column_stack([np.ones(len(val)),(val[cols].to_numpy()-mean)/sd])
 pd.DataFrame({'variable':cols,'media_train':mean,'sd_train':sd,'coef_estandarizado':result.x[1:]}).to_csv(OUT/'ajustes'/f'logistica_{block}_{h}h.csv',index=False)
 (OUT/'ajustes'/f'logistica_{block}_{h}h.json').write_text(json.dumps({'intercepto':float(result.x[0]),'C':1,'prior':prior,'regla_probabilidades':rp,'n_train':len(train),'positivos_train':int(y.sum()),'ultima_emision_train':str(train.index.max()),'primera_emision_val':str(val.index.min()),'convergencia':str(result.message),'iteraciones':result.nit,'gradiente_max':float(np.abs(result.jac).max())},indent=2))
 return {'frecuencia':np.array([lookup[m,hour] for m,hour in zip(val.index.month,val.index.hour)]),'regla':val.regla.map(rp).to_numpy(),'logistica':expit(V@result.x)},prior

def hourly(pred):
 rows=[]; curves=[]; calibration=[]
 edges=np.array([0,.001,.003,.01,.03,.1,.3,.5,1.0000001])
 for (h,block,model),d in pred.groupby(['horizonte_h','bloque','modelo']):
  for epoch in ['ALL','DJF','MAM','JJA','SON']:
   g=d if epoch=='ALL' else d[d.epoca.eq(epoch)]
   if not len(g): continue
   ap,curve=pr(g.objetivo,g.probabilidad)
   brier=float(((g.probabilidad-g.objetivo)**2).mean()); base=float(((g.p_frecuencia-g.objetivo)**2).mean())
   rows.append({'horizonte_h':h,'bloque':block,'modelo':model,'epoca':epoch,'n_emisiones':len(g),'positivos':int(g.objetivo.sum()),'prevalencia':g.objetivo.mean(),'AP':ap,'Brier':brier,'Brier_constante_train':((g.p_constante_train-g.objetivo)**2).mean(),'Brier_skill_vs_frecuencia':1-brier/base,'meses_equivalentes':len(g)/(365.25*24/12)})
   if epoch=='ALL': curves.append(curve.assign(horizonte_h=h,bloque=block,modelo=model))
   bins=np.clip(np.searchsorted(edges,g.probabilidad,side='right')-1,0,len(edges)-2)
   for i in range(len(edges)-1):
    z=g.iloc[np.flatnonzero(bins==i)]
    calibration.append({'horizonte_h':h,'bloque':block,'modelo':model,'epoca':epoch,'limite_inf':edges[i],'limite_sup':min(edges[i+1],1),'n':len(z),'positivos':int(z.objetivo.sum()),'p_media':z.probabilidad.mean(),'frecuencia_observada':z.objetivo.mean()})
 save(pd.DataFrame(rows),'metricas_horarias'); save(pd.concat(curves),'curvas_precision_recall'); save(pd.DataFrame(calibration),'calibracion')
 return pd.DataFrame(rows)

def notices(pred,cat):
 alerts=[]; events=[]; metrics=[]
 for (h,block,model),d in pred.groupby(['horizonte_h','bloque','modelo'],sort=True):
  d=d.sort_values('emision'); eligible_ids={cid for value in d.id_inicio_objetivo[d.objetivo.eq(1)] for cid in value.split('|')}
  cs=cat[cat.inicio.dt.year.between(int(block[:4]),int(block[-4:]))]
  for policy in [f'p>={p:g}' for p in THRESHOLDS]+(['regla_nativa'] if model=='regla' else []):
   if policy=='regla_nativa': on=d[d.regla.eq(1)]
   else: on=d[d.probabilidad.ge(float(policy[3:]))]
   groups=(on.emision.diff().ne(pd.Timedelta(hours=1))).cumsum()
   used={}; local=[]
   for gid,g in on.groupby(groups):
    cand=list(dict.fromkeys(cid for value in g.loc[g.objetivo.eq(1),'id_inicio_objetivo'] for cid in value.split('|')))
    cand.sort(key=lambda cid: cat.loc[cat.id_tramo.eq(cid),'inicio'].iloc[0])
    match=next((cid for cid in cand if cid not in used),'')
    status='acierto' if match else ('redundante' if cand else 'falsa_alarma')
    aid=f'{block}_{h}_{model}_{policy}_{int(gid):05}'
    lead=np.nan; validtime=pd.NaT; onset=pd.NaT
    if match:
     onset=cat.loc[cat.id_tramo.eq(match),'inicio'].iloc[0]
     validtime=g.loc[g.id_inicio_objetivo.map(lambda value: match in value.split('|')),'emision'].iloc[0]
     lead=(onset-validtime)/pd.Timedelta(hours=1); assert 0<lead<=h
     used[match]=(aid,lead)
    local.append({'horizonte_h':h,'bloque':block,'modelo':model,'politica':policy,'id_aviso':aid,'primera_emision':g.emision.iloc[0],'ultima_emision':g.emision.iloc[-1],'n_emisiones':len(g),'estado':status,'id_inicio':match,'inicios_en_objetivos':'|'.join(cand),'inicio':onset,'primera_emision_anticipadora':validtime,'anticipacion_h':lead,'epoca_aviso':g.epoca.iloc[0],'mes_aviso':g.emision.iloc[0].strftime('%Y-%m')})
   a=pd.DataFrame(local,columns=['horizonte_h','bloque','modelo','politica','id_aviso','primera_emision','ultima_emision','n_emisiones','estado','id_inicio','inicios_en_objetivos','inicio','primera_emision_anticipadora','anticipacion_h','epoca_aviso','mes_aviso'])
   assert not a.loc[a.estado.eq('acierto'),'id_inicio'].duplicated().any()
   alerts.extend(local)
   er=[]
   for r in cs.itertuples():
    status='sin_oportunidad' if r.id_tramo not in eligible_ids else ('anticipado' if r.id_tramo in used else 'omitido')
    er.append({'horizonte_h':h,'bloque':block,'modelo':model,'politica':policy,'id_inicio':r.id_tramo,'inicio':r.inicio,'epoca_inicio':season(pd.DatetimeIndex([r.inicio]))[0],'mes_inicio':r.inicio.strftime('%Y-%m'),'estado':status,'id_aviso':used.get(r.id_tramo,('',np.nan))[0],'anticipacion_h':used.get(r.id_tramo,('',np.nan))[1]})
   e=pd.DataFrame(er); events.extend(er)
   for epoch in ['ALL','DJF','MAM','JJA','SON']:
    z=d if epoch=='ALL' else d[d.epoca.eq(epoch)]
    aa=a if epoch=='ALL' else a[a.epoca_aviso.eq(epoch)]
    ee=e if epoch=='ALL' else e[e.epoca_inicio.eq(epoch)]
    n=len(aa); tp=int(aa.estado.eq('acierto').sum()); fp=int(aa.estado.eq('falsa_alarma').sum()); redundant=int(aa.estado.eq('redundante').sum())
    evaluable=int(ee.estado.ne('sin_oportunidad').sum()); detected=int(ee.estado.eq('anticipado').sum())
    months=len(z)/(365.25*24/12)
    metrics.append({'horizonte_h':h,'bloque':block,'modelo':model,'politica':policy,'epoca':epoch,'n_emisiones':len(z),'meses_equivalentes':months,'meses_calendario_con_emisiones':z.emision.dt.strftime('%Y-%m').nunique(),'inicios_catalogo':len(ee),'inicios_evaluables':evaluable,'inicios_sin_oportunidad':len(ee)-evaluable,'inicios_anticipados':detected,'inicios_omitidos':evaluable-detected,'recall_inicios':detected/evaluable if evaluable else np.nan,'grupos_avisos':n,'aciertos_avisos':tp,'falsas_alarmas':fp,'redundantes':redundant,'precision_avisos':tp/n if n else np.nan,'falsas_alarmas_por_mes':fp/months if months else np.nan,'anticipacion_media_h':aa.anticipacion_h.mean(),'anticipacion_mediana_h':aa.anticipacion_h.median()})
 save(pd.DataFrame(alerts),'correspondencia_avisos'); save(pd.DataFrame(events),'evaluacion_inicios'); save(pd.DataFrame(metrics),'metricas_avisos')
 return pd.DataFrame(alerts),pd.DataFrame(events),pd.DataFrame(metrics)

# Paired temporal bootstrap: sample contiguous 3-month blocks within each biennium.
def uncertainty(pred,alerts,events):
 rng=np.random.default_rng(20132023); samples=[]
 months={b:pd.period_range(f'{b[:4]}-01',f'{b[-4:]}-12',freq='M').astype(str).tolist() for b,_,_,_ in BLOCKS}
 for _ in range(300):
  counts={}
  for b in months:
   cnt={m:0 for m in months[b]}
   for s in rng.integers(0,22,8):
    for m in months[b][s:s+3]: cnt[m]+=1
   counts.update({(b,m):v for m,v in cnt.items()})
  samples.append(counts)
 rows=[]
 for h in [1,3]:
  wide=pred[pred.horizonte_h.eq(h)].pivot(index=['bloque','emision','objetivo'],columns='modelo',values='probabilidad').reset_index()
  keys=list(zip(wide.bloque,wide.emision.dt.strftime('%Y-%m'))); y=wide.objetivo.to_numpy()
  vals={m:[] for m in ['frecuencia','regla','logistica']}; differences={m:[] for m in ['regla','logistica']}
  for cnt in samples:
   weights=np.array([cnt[k] for k in keys]); inds=np.repeat(np.arange(len(wide)),weights)
   yy=y[inds]; br={}; aps={}
   for model in vals:
    pp=wide[model].to_numpy()[inds]; ap,_=pr(yy,pp); brier=np.mean((pp-yy)**2)
    vals[model].append((ap,brier)); br[model]=brier; aps[model]=ap
   for model in differences: differences[model].append((aps[model]-aps['frecuencia'],br[model]-br['frecuencia']))
  for model,arr in vals.items():
   for j,metric in enumerate(['AP','Brier']):
    a=np.array(arr)[:,j]; rows.append({'horizonte_h':h,'modelo':model,'politica':'','metrica':metric,'estimacion':pr(y,wide[model])[0] if j==0 else np.mean((wide[model]-y)**2),'p025':np.nanquantile(a,.025),'p975':np.nanquantile(a,.975),'replicas_validas':int(np.isfinite(a).sum())})
  for model,arr in differences.items():
   for j,metric in enumerate(['delta_AP_vs_frecuencia','delta_Brier_vs_frecuencia']):
    a=np.array(arr)[:,j]
    estimate=pr(y,wide[model])[0]-pr(y,wide.frecuencia)[0] if j==0 else np.mean((wide[model]-y)**2)-np.mean((wide.frecuencia-y)**2)
    rows.append({'horizonte_h':h,'modelo':model,'politica':'','metrica':metric,'estimacion':estimate,'p025':np.nanquantile(a,.025),'p975':np.nanquantile(a,.975),'replicas_validas':int(np.isfinite(a).sum())})
 # Event uncertainty from additive, already matched monthly records.
 for (h,model,policy),e in events.groupby(['horizonte_h','modelo','politica']):
  a=alerts[(alerts.horizonte_h==h)&(alerts.modelo==model)&(alerts.politica==policy)]
  d=pred[(pred.horizonte_h==h)&(pred.modelo==model)]
  ek=list(zip(e.bloque,e.mes_inicio)); ak=list(zip(a.bloque,a.mes_aviso)); dk=list(zip(d.bloque,d.emision.dt.strftime('%Y-%m')))
  exposure=pd.Series(dk).value_counts().to_dict()
  detected=e.estado.eq('anticipado').to_numpy(); evaluable=e.estado.ne('sin_oportunidad').to_numpy()
  success=a.estado.eq('acierto').to_numpy(); false=a.estado.eq('falsa_alarma').to_numpy()
  arrays=[]
  for cnt in samples:
   ew=np.array([cnt[k] for k in ek]); aw=np.array([cnt[k] for k in ak]); hours=sum(cnt[k]*v for k,v in exposure.items())
   arrays.append((np.dot(ew,detected)/np.dot(ew,evaluable) if np.dot(ew,evaluable) else np.nan,np.dot(aw,success)/aw.sum() if aw.sum() else np.nan,np.dot(aw,false)/(hours/(365.25*24/12))))
  estimates=[detected.sum()/evaluable.sum(),success.sum()/len(a) if len(a) else np.nan,false.sum()/(len(d)/(365.25*24/12))]
  for j,metric in enumerate(['recall_inicios','precision_avisos','falsas_alarmas_por_mes']):
   v=np.array(arrays)[:,j]; rows.append({'horizonte_h':h,'modelo':model,'politica':policy,'metrica':metric,'estimacion':estimates[j],'p025':np.nanquantile(v,.025) if np.isfinite(v).any() else np.nan,'p975':np.nanquantile(v,.975) if np.isfinite(v).any() else np.nan,'replicas_validas':int(np.isfinite(v).sum())})
 save(pd.DataFrame(rows),'incertidumbre'); return pd.DataFrame(rows)

def plots(pred,am):
 colors={'frecuencia':'#999999','regla':'#d58c13','logistica':'#1769aa'}
 for h in [1,3]:
  fig,axs=plt.subplots(1,3,figsize=(14,4),layout='constrained')
  for ax,(b,_,_,_) in zip(axs,BLOCKS):
   for m,c in colors.items():
    d=pred[(pred.horizonte_h==h)&(pred.bloque==b)&(pred.modelo==m)]; ap,curve=pr(d.objetivo,d.probabilidad)
    ax.step(np.r_[0,curve.recall],np.r_[1,curve.precision],where='pre',color=c,label=f'{m}: AP={ap:.3f}')
   ax.axhline(d.objetivo.mean(),ls='--',color='black',label=f'prevalencia {d.objetivo.mean():.4f}')
   ax.set(xlabel='Recall horario',ylabel='Precisión horaria',title=f'{b}, {h} h',ylim=(0,1),xlim=(0,1)); ax.legend(fontsize=8)
  fig.savefig(OUT/'graficos'/f'precision_recall_{h}h.png',dpi=150); plt.close(fig)
  fig,axs=plt.subplots(1,3,figsize=(14,4),layout='constrained')
  for ax,(b,_,_,_) in zip(axs,BLOCKS):
   for m,c in colors.items():
    z=am[(am.horizonte_h==h)&(am.bloque==b)&(am.modelo==m)&(am.epoca=='ALL')&am.politica.ne('regla_nativa')]
    ax.plot(z.falsas_alarmas_por_mes,z.recall_inicios,'o-',color=c,label=m)
    for r in z.itertuples(): ax.annotate(r.politica[3:],(r.falsas_alarmas_por_mes,r.recall_inicios),fontsize=6)
   ax.set(xlabel='Falsas alarmas / mes equivalente',ylabel='Fracción de inicios anticipados',title=f'{b}, {h} h',ylim=(-.02,1.02)); ax.legend(fontsize=8)
  fig.savefig(OUT/'graficos'/f'compromiso_avisos_{h}h.png',dpi=150); plt.close(fig)
  cal=pd.read_csv(OUT/'tablas/calibracion.csv'); cal=cal[(cal.horizonte_h==h)&(cal.epoca=='ALL')]
  fig,axs=plt.subplots(1,3,figsize=(14,4),layout='constrained')
  for ax,(b,_,_,_) in zip(axs,BLOCKS):
   for m,c in colors.items():
    z=cal[(cal.bloque==b)&(cal.modelo==m)&cal.n.gt(0)]
    ax.plot(z.p_media,z.frecuencia_observada,'o-',color=c,label=m)
    for r in z.itertuples(): ax.annotate(str(r.n),(r.p_media,r.frecuencia_observada),fontsize=6)
   ax.plot([0,1],[0,1],'--',color='black',lw=1); ax.set(xlabel='Probabilidad media prevista',ylabel='Fracción observada',title=f'{b}, {h} h; números = n',xlim=(0,1),ylim=(0,1)); ax.legend(fontsize=8)
  fig.savefig(OUT/'graficos'/f'calibracion_{h}h.png',dpi=150); plt.close(fig)

def main():
 protocol_hash=digest(OUT/'protocolo.md')
 # Timestamp evidence is written before the first fit.
 (OUT/'registro_preentrenamiento.json').write_text(json.dumps({'protocolo_sha256':protocol_hash,'registrado_utc':pd.Timestamp.now(tz='UTC').isoformat(),'estado':'protocolo guardado antes de entrenar','script_sha256':digest(Path(__file__))},indent=2))
 x,state,cat,manifest=ingest(); f,ds=eligibility(x,state,cat)
 cols=list(f.columns); predictions=[]; partitions=[]
 for h in [1,3]:
  for b,ty,vs,ve in BLOCKS:
   train=ds[h,b,'entrenamiento']; val=ds[h,b,'validacion']
   for role,d in [('entrenamiento',train),('validacion',val)]: partitions.append({'horizonte_h':h,'bloque':b,'rol':role,'n':len(d),'positivos':int(d.y.sum()),'primera_emision':d.index.min(),'ultima_emision':d.index.max(),'primer_dato_predictor':d.index.min()-pd.Timedelta(hours=6),'ultimo_dato_predictor':d.index.max(),'ultimo_objetivo':d.index.max()+pd.Timedelta(hours=h),'inicios_con_oportunidad':len({cid for value in d.id_inicio_objetivo[d.y.eq(1)] for cid in value.split('|')})})
   print(f'Ajuste {b} {h}h: train={len(train)} val={len(val)} positivos={val.y.sum()}',flush=True)
   probs,prior=fit_predict(train,val,cols,h,b)
   for m,p in probs.items():
    assert np.isfinite(p).all() and ((p>=0)&(p<=1)).all()
    predictions.append(pd.DataFrame({'emision':val.index,'horizonte_h':h,'objetivo':val.y.to_numpy(),'modelo':m,'bloque':b,'probabilidad':p,'id_inicio_objetivo':val.id_inicio_objetivo.to_numpy(),'regla':val.regla.to_numpy(),'p_constante_train':prior,'p_frecuencia':probs['frecuencia'],'epoca':season(val.index),'predictor_desde':val.index-pd.Timedelta(hours=6),'predictor_hasta':val.index,'objetivo_hasta':val.index+pd.Timedelta(hours=h)}))
 pred=pd.concat(predictions,ignore_index=True)
 pred.to_csv(OUT/'predicciones_validacion.csv',index=False,float_format='%.10g')
 save(pd.DataFrame(partitions),'particiones'); hm=hourly(pred); a,e,am=notices(pred,cat)
 print('Bootstrap temporal pareado (300 réplicas)',flush=True)
 uncertainty(pred,a,e); plots(pred,am)
 # Counterfactual future modification must not change features at or before cutoff.
 cutoff=pd.Timestamp('2019-08-13 01:00'); modified=x.copy(); modified.loc[modified.index>cutoff,MAIN]=123.456
 fm=features(modified); pd.testing.assert_frame_equal(f.loc[:cutoff],fm.loc[:cutoff])
 for row in manifest:
  row['sha256_despues']=digest(ROOT/row['archivo']); assert row['sha256_antes']==row['sha256_despues']
 save(pd.DataFrame(manifest),'manifiesto_entradas')
 assert digest(OUT/'protocolo.md')==protocol_hash
 controls={'periodo':['2013-01-01 00:00:00','2023-12-31 23:00:00'],'lista_cerrada_11_anuales_y_catalogo':True,'sin_red':True,'otras_estaciones':False,'presion_5m_predictores':False,'protocolo_inmutable':True,'protocolo_sha256':protocol_hash,'script_sha256':digest(Path(__file__)),'n_horas':len(IDX),'cumple':int(state.eq(1).sum()),'no_cumple':int(state.eq(0).sum()),'desconocido':int(state.eq(-1).sum()),'tramos_v0':len(cat),'inicios_conocidos':int(cat.inicio_conocido.sum()),'predictores':cols,'ventanas_completas_sin_imputacion':True,'escalado_solo_entrenamiento':True,'soportes_dentro_particiones':True,'predictores_invariantes_a_futuro_modificado':True,'cutoff_prueba':str(cutoff),'fuentes_hash_inalterado':True,'probabilidades_finitas':True,'aciertos_unicos_por_inicio':True,'predicciones':len(pred),'versiones':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'scipy':scipy.__version__,'matplotlib':matplotlib.__version__}}
 (OUT/'comprobaciones.json').write_text(json.dumps(controls,indent=2,ensure_ascii=False))
 (OUT/'requirements.txt').write_text('\n'.join(f'{k}=={v}' for k,v in controls['versiones'].items() if k!='python')+'\n')
 print('Completado; fuentes intactas, controles conformes.',flush=True)
if __name__=='__main__': main()
