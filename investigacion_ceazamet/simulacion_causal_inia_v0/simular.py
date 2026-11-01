#!/usr/bin/env python3
"""Reconstrucción sin rutinas de ajuste ni acceso a fuentes no autorizadas."""
import os,sys
os.environ['OPENBLAS_NUM_THREADS']='1'; sys.modules['numexpr']=None
import json,hashlib,platform,gzip
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import expit
from funciones_congeladas import features,engine,classification,event_links,MAIN
OUT=Path(__file__).resolve().parent; BASE=OUT.parent; V0=BASE/'linea_base_inicio_v0'; V1=BASE/'evaluacion_avisos_v1'
START=pd.Timestamp('2013-01-01'); END=pd.Timestamp('2023-12-31 23:00'); IDX=pd.date_range(START,END,freq='h')
BLOCKS=['2018-2019','2020-2021','2022-2023']; TH=[.001,.003,.01,.03,.1,.3,.5]; TOL=1e-9

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(df,name): df.to_csv(OUT/'tablas'/f'{name}.csv',index=False,float_format='%.12g')
def epoch(idx): return np.select([idx.month.isin([12,1,2]),idx.month.isin([3,4,5]),idx.month.isin([6,7,8])],['DJF','MAM','JJA'],default='SON')
def ratio(a,b): return a/b if b else np.nan

def sources():
 files=[BASE/'historico_inia/derivados'/f'observaciones_{y}.csv' for y in range(2013,2024)]
 files += [BASE/'catalogo_provisional_v0/catalogo_referencia.csv',BASE/'diagnostico_2013_2023/tablas/estados_horarios.csv']
 for folder in [V0,V1]: files += sorted(p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
 return files

def ingest():
 frames=[]
 for y in range(2013,2024):
  df=pd.read_csv(BASE/'historico_inia/derivados'/f'observaciones_{y}.csv',usecols=['fecha_sin_zona','variable','prom','porcentaje_datos','prom_utilizable_revision','dentro_periodo'])
  dates=pd.to_datetime(df.fecha_sin_zona); assert dates.dt.year.eq(y).all() and df.dentro_periodo.eq(1).all()
  df=df[df.variable.isin(MAIN)].copy(); df['fecha']=pd.to_datetime(df.fecha_sin_zona)
  valid=np.isfinite(df.prom)&df.porcentaje_datos.gt(0)&df.prom_utilizable_revision.eq(1)
  valid &= ~(df.variable.eq('humedad')&~df.prom.between(0,100))
  valid &= ~(df.variable.eq('viento_2m')&df.prom.lt(0))
  valid &= ~(df.variable.eq('direccion_2m')&~df.prom.between(0,360))
  df['valor']=df.prom.where(valid); frames.append(df[['fecha','variable','valor']])
 raw=pd.concat(frames); assert not raw.duplicated(['fecha','variable']).any()
 x=raw.pivot(index='fecha',columns='variable',values='valor').reindex(IDX)[MAIN]
 state=states(x)
 cat=pd.read_csv(BASE/'catalogo_provisional_v0/catalogo_referencia.csv',usecols=['id_tramo','primera_marca','ultima_marca'],parse_dates=['primera_marca','ultima_marca'])
 assert cat.primera_marca.between(START,END).all() and cat.ultima_marca.between(START,END).all()
 hit=np.zeros(len(x),bool)
 for r in cat.itertuples(): hit[(IDX>=r.primera_marca)&(IDX<=r.ultima_marca)]=True
 assert np.array_equal(hit,state==1) and hit.sum()==867 and len(cat)==156
 assert (state.loc[cat.primera_marca-pd.Timedelta(hours=1)]==0).all()
 obs=pd.read_csv(BASE/'diagnostico_2013_2023/tablas/estados_horarios.csv',usecols=['fecha_sin_zona','estado'],parse_dates=['fecha_sin_zona']).set_index('fecha_sin_zona')
 assert obs.index.equals(IDX) and np.array_equal(obs.estado.map({'cumple':1,'no_cumple':0,'no_evaluable':-1}),state)
 return x,cat

def states(x):
 valid=x.notna().all(axis=1)
 hit=x.temperatura.gt(11)&x.humedad.lt(30)&x.viento_2m.gt(2)&x.direccion_2m.between(0,180)
 return pd.Series(np.where(~valid,-1,np.where(hit,1,0)),index=x.index)

def stream(x,delay):
 """Only trailing operations. Does not receive labels or catalog."""
 f=features(x); s=states(x)
 complete=x.notna().all(axis=1).rolling(7,min_periods=7).sum().eq(7)
 a=complete & s.eq(0)
 rule=x.direccion_2m.between(0,180)&x.temperatura.gt(10)&x.humedad.lt(40)&x.viento_2m.gt(1)&f.temperatura_delta1.gt(0)&f.humedad_delta1.lt(0)&f.viento_2m_delta1.gt(0)
 return f.shift(delay),a.shift(delay,fill_value=False).to_numpy(),s.shift(delay,fill_value=-1).to_numpy(),rule.shift(delay,fill_value=False).to_numpy(),complete.shift(delay,fill_value=False).to_numpy()

def predict(f,rule,b,h,delay):
 params=pd.read_csv(V0/'ajustes'/f'logistica_{b}_{h}h.csv'); meta=json.loads((V0/'ajustes'/f'logistica_{b}_{h}h.json').read_text())
 assert list(params.variable)==list(f.columns) and len(params)==35
 p=expit(meta['intercepto']+((f.to_numpy()-params.media_train.to_numpy())/params.sd_train.to_numpy())@params.coef_estandarizado.to_numpy())
 refs=pd.read_csv(V0/'tablas'/f'referencia_{b}_{h}h.csv').set_index(['mes','hora']).p
 anchors=f.index-pd.Timedelta(hours=delay)
 freq=np.array([refs.loc[(t.month,t.hour)] for t in anchors])
 rp=meta['regla_probabilidades']; return {'logistica':p,'frecuencia':freq,'regla':np.where(rule,rp['1'],rp['0'])}

def targets(state,events,h):
 n=len(state); pos=np.arange(n); unknown=np.zeros(n,bool); yes=np.zeros(n,bool)
 onset=(state==1)&np.r_[True,state[:-1]!=1]; uncertain=onset&~np.r_[False,state[:-1]==0]
 for k in range(1,h+1):
  unknown[:-k] |= (state[k:]==-1)|uncertain[k:]; yes[:-k] |= events[k:]
 return np.where(pos+h>=n,'fuera_de_alcance',np.where(unknown,'desconocido',np.where(yes,'positivo','negativo')))

def ap(y,p):
 if not len(y) or not y.sum(): return np.nan
 order=np.argsort(-p,kind='stable'); yy=y[order]; pp=p[order]; ends=np.r_[np.flatnonzero(pp[:-1]!=pp[1:]),len(pp)-1]
 tp=np.cumsum(yy)[ends]; rec=tp/y.sum(); return np.sum(np.diff(np.r_[0,rec])*(tp/(ends+1)))

def controls(x):
 checks=[]
 def check(name,ok): assert ok,name; checks.append({'control':name,'conforme':True})
 # Include real outage boundaries and onset, plus fixed arbitrary cutoff.
 s=states(x); cuts=[300, len(x)//2]
 cuts+=list(np.flatnonzero((s.to_numpy()==-1)&np.r_[False,s.to_numpy()[:-1]!=-1])[:2])
 cuts+=list(np.flatnonzero((s.to_numpy()==0)&np.r_[False,s.to_numpy()[:-1]==-1])[:2])
 cuts+=list(np.flatnonzero((s.to_numpy()==1)&np.r_[False,s.to_numpy()[:-1]==0])[:2])
 for d in [0,1,2]:
  full=stream(x,d)
  for cut in cuts:
   for kind in ['alterar','eliminar']:
    changed=x.copy(); changed.iloc[cut+1:]=999 if kind=='alterar' else np.nan
    other=stream(changed,d)
    check(f'{kind}_futuro_prefijo_predictores_d{d}_c{cut}',np.allclose(full[0].iloc[:cut+1],other[0].iloc[:cut+1],equal_nan=True) and all(np.array_equal(full[j][:cut+1],other[j][:cut+1]) for j in range(1,5)))
    ps=predict(full[0],full[3],'2018-2019',3,d); po=predict(other[0],other[3],'2018-2019',3,d)
    check(f'{kind}_futuro_probabilidades_d{d}_c{cut}',all(np.allclose(ps[m][:cut+1],po[m][:cut+1],equal_nan=True) for m in ps))
    for h in [1,3]:
     r=engine(full[1],ps['logistica']>=.01,full[2],h); q=engine(other[1],po['logistica']>=.01,other[2],h)
     check(f'{kind}_futuro_alertas_d{d}_h{h}_c{cut}',all(np.array_equal(r[k][:cut+1],q[k][:cut+1]) for k in ['warning','expires','active','episode','action','closed']))
  # Truncating observations removes future rows completely.
  cut=cuts[0]; prefix=stream(x.iloc[:cut+1],d)
  check(f'truncar_observaciones_d{d}',all(np.array_equal(full[j][:cut+1],prefix[j]) for j in range(1,5)) and np.allclose(full[0].iloc[:cut+1],prefix[0],equal_nan=True))
 test=pd.DataFrame({'temperatura':9.,'humedad':50.,'viento_2m':1.,'direccion_2m':200.},index=pd.date_range('2018-01-01',periods=30,freq='h')); test.iloc[9:12]=np.nan
 for d in [0,1,2]:
  f,av,s,r,c=stream(test,d)
  check(f'arranque_6_mas_d_{d}',not av[:6+d].any() and av[6+d])
  check(f'recuperacion_siete_marcas_d{d}',not av[9+d:18+d].any() and av[18+d])
  e=engine(av,np.ones(30,bool),s,3)
  check(f'hueco_vigencia_sin_renovar_d{d}',e['active'][9+d] and e['active'][10+d] and not e['active'][11+d] and not e['warning'][9+d:18+d].any())
 e=engine(np.ones(8,bool),np.array([1,0,0,1,0,0,0,1],bool),np.zeros(8,int),3)
 check('adyacencia_y_vencimiento',len(e['episodes'])==2 and e['episodes'][0]['end']==6 and e['action'][3]=='renovacion' and e['expires'][7]==10)
 _,p=event_links(np.array([3,4,5]),3,[('evento',3)])
 check('aviso_en_o_despues_inicio_no_anticipa',not p)
 save(pd.DataFrame(checks),'controles_causales'); return checks

def main():
 files=sources(); before={str(p):sha(p) for p in files}
 registration={'fecha_local':'2026-10-08','protocolo_sha256':sha(OUT/'protocolo.md'),'tolerancia_absoluta':TOL,'retrasos':[0,1,2],'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'fuentes':list(before),'sin_ajuste':True}
 (OUT/'registro_previo.json').write_text(json.dumps(registration,indent=2))
 x,cat=ingest(); checks=controls(x.loc['2018-01-01':'2019-12-31 23:00'])
 old=pd.read_csv(V0/'predicciones_validacion.csv',parse_dates=['emision'])
 metrics=[]; episodes=[]; events_out=[]; links_out=[]; forecast_metrics=[]; calibration=[]; recon=[]; forecasts=[]; availability=[]; targets_out=[]
 handles={k:gzip.open(OUT/f'{k}.csv.gz','wt') for k in ['historial_horario','emisiones_renovaciones','transiciones']}; first={k:True for k in handles}
 def append(name,df): df.to_csv(handles[name],index=False,header=first[name],float_format='%.12g'); first[name]=False
 for b in BLOCKS:
  xb=x.loc[f'{b[:4]}-01-01':f'{b[-4:]}-12-31 23:00']; grid=xb.index; n=len(grid); pos=np.arange(n); s=states(xb).to_numpy(); seasons=epoch(grid); weight=np.ones(n,int); weight[-1]=0
  cs=cat[cat.primera_marca.between(grid[0],grid[-1])]; event=np.zeros(n,bool); evlist=[]
  for row in cs.itertuples():
   j=grid.get_indexer([row.primera_marca])[0]; event[j]=True; evlist.append((row.id_tramo,j))
  for d in [0,1,2]:
   f,av,known,rule,complete=stream(xb,d)
   availability.append(pd.DataFrame({'bloque':b,'retraso_h':d,'emision':grid,'ancla':grid-pd.Timedelta(hours=d),'estado_conocido':known,'ventana_completa':complete,'puede_emitir':av,'motivo':np.select([pos<6+d,known==-1,known==1,~complete],['arranque_bloque','observacion_desconocida','tramo_activo_conocido','ventana_incompleta'],default='disponible')}))
   for h in [1,3]:
    # Probabilities computed before any call to target evaluator.
    probs=predict(f,rule,b,h,d)
    frozen_runs={}
    for m in ['frecuencia','logistica','regla','siempre']:
     policies=['toda_emision'] if m=='siempre' else [f'p>={v:g}' for v in TH]+(['regla_nativa'] if m=='regla' else [])
     for policy in policies:
      above=np.ones(n,bool) if m=='siempre' else (rule if policy=='regla_nativa' else probs[m]>=float(policy[3:]))
      frozen_runs[m,policy]=engine(av,above,known,h)
    # All evaluation begins here, after frozen operative runs.
    target=targets(s,event,h); evaluable=np.isin(target,['positivo','negativo']); y=(target=='positivo'); opportunities=[]
    for eid,j in evlist:
     if (av&evaluable&(pos<j)&(pos+h>=j)).any(): opportunities.append(eid)
    evmask=np.zeros(n,bool); uneval=np.zeros(n,bool)
    for eid,j in evlist: (evmask if eid in opportunities else uneval)[j]=True
    targets_out.append(pd.DataFrame({'bloque':b,'retraso_h':d,'horizonte_h':h,'emision':grid[av],'objetivo_hasta':grid[av]+pd.Timedelta(hours=h),'estado_objetivo':target[av],'objetivo':np.where(evaluable[av],y[av].astype(float),np.nan)}))
    for m in probs:
     p=probs[m]; assert np.isfinite(p[av]).all() and ((p[av]>=0)&(p[av]<=1)).all()
     pf=pd.DataFrame({'bloque':b,'retraso_h':d,'horizonte_h':h,'modelo':m,'emision':grid[av],'ancla':grid[av]-pd.Timedelta(hours=d),'predictor_desde':grid[av]-pd.Timedelta(hours=d+6),'probabilidad':p[av],'regla':rule[av].astype(int),'estado_objetivo':target[av],'objetivo':np.where(evaluable[av],y[av].astype(float),np.nan)})
     forecasts.append(pf)
     if d==0:
      original=old[(old.bloque==b)&(old.horizonte_h==h)&(old.modelo==m)]
      ids=grid.get_indexer(original.emision); assert av[ids].all(); error=float(np.max(np.abs(p[ids]-original.probabilidad.to_numpy())))
      assert error<=TOL and np.array_equal(rule[ids],original.regla) and np.array_equal(y[ids].astype(int),original.objetivo)
      # Compare all IDs as well as binary targets.
      expected=['|'.join(eid for eid,j in evlist if t<j<=t+h) for t in ids]
      assert expected==original.id_inicio_objetivo.fillna('').tolist()
      recon.append({'bloque':b,'horizonte_h':h,'modelo':m,'filas_v0':len(original),'error_absoluto_max':error,'tolerancia':TOL,'emisiones_reconstruidas':int(av.sum()),'adicionales':int(av.sum())-len(original)})
     for ep in ['ALL','DJF','MAM','JJA','SON']:
      sel=np.ones(n,bool) if ep=='ALL' else seasons==ep; z=av&evaluable&sel
      forecast_metrics.append({'bloque':b,'retraso_h':d,'horizonte_h':h,'modelo':m,'epoca':ep,'n':int(z.sum()),'positivos':int(y[z].sum()),'AP':ap(y[z],p[z]),'Brier':np.mean((p[z]-y[z])**2) if z.any() else np.nan})
     edges=[0,.001,.003,.01,.03,.1,.3,.5,1.0000001]
     for lo,hi in zip(edges[:-1],edges[1:]):
      z=av&evaluable&(p>=lo)&(p<hi); calibration.append({'bloque':b,'retraso_h':d,'horizonte_h':h,'modelo':m,'inferior':lo,'superior':min(hi,1),'n':int(z.sum()),'p_media':p[z].mean() if z.any() else np.nan,'frecuencia':y[z].mean() if z.any() else np.nan})
    for (m,policy),run in frozen_runs.items():
     keys={'bloque':b,'retraso_h':d,'horizonte_h':h,'modelo':m,'politica':policy}; warning=run['warning']; active=run['active']; inds=np.flatnonzero(warning)
     lab=classification(active,np.maximum(run['expires'],pos),s==-1,evmask,uneval)
     end=run['expires']; clipped=np.minimum(np.maximum(end,pos),n-1); cum=np.cumsum(s==-1); loss=active&((cum[clipped]-cum[pos])>0); outside=active&(end>=n)
     hist=pd.DataFrame({'emision':grid,'duracion_celda_h':weight,'puede_emitir':av,'estado_conocido':known,'aviso_emitido':warning,'alerta_activa':active,'accion':run['action'],'episodio':run['episode'],'episodio_cerrado':run['closed'],'vencimiento_vigente':np.where(end>=0,(grid[0]+pd.to_timedelta(np.maximum(end,0),unit='h')).astype(str),''),'estado_objetivo':target,'carga_vigente_clase':lab,'carga_perdida_futura':loss,'carga_fuera_bloque':outside,'observacion_real_desconocida':s==-1,'tramo_real_activo':s==1})
     for k,v in keys.items(): hist[k]=v
     append('historial_horario',hist); issued=hist.iloc[inds].copy(); issued['vence']=grid[inds]+pd.Timedelta(hours=h); issued['probabilidad']=np.nan if m=='siempre' else probs[m][inds]; append('emisiones_renovaciones',issued)
     append('transiciones',hist[(hist.accion!='')|(hist.episodio_cerrado>=0)])
     validissues=np.flatnonzero(warning&evaluable); links,primary=event_links(validissues,h,[(eid,j) for eid,j in evlist if eid in opportunities]); pmap={eid:(j,t,last,count) for eid,j,t,last,count in primary}
     for eid,j,t,isprimary in links: links_out.append({**keys,'id_inicio':eid,'inicio':grid[j],'emision':grid[t],'anticipacion_h':j-t,'primaria':isprimary,'episodio':run['issue_episode'][t]})
     local_events=[]
     for eid,j in evlist:
      detected=eid in pmap; t=pmap[eid][1] if detected else -1; ei=run['issue_episode'][t] if detected else -1; start=run['episodes'][ei]['start'] if detected else -1
      er={**keys,'id_inicio':eid,'inicio':grid[j],'epoca':seasons[j],'estado':'anticipado' if detected else ('omitido' if eid in opportunities else 'sin_oportunidad'),'anticipacion_h':j-t if detected else np.nan,'edad_alerta_h':j-start if detected else np.nan,'primera_emision_valida':grid[t] if detected else pd.NaT,'episodio':ei}
      local_events.append(er); events_out.append(er)
     le=pd.DataFrame(local_events); local_eps=[]
     for e in run['episodes']:
      start,end=e['start'],e['end']; dur=min(end,n-1)-start; times=np.arange(start,min(end,n-1)); count=int(((le.episodio==e['episode'])&(le.estado=='anticipado')).sum())
      row={**keys,'episodio':e['episode'],'inicio_alerta':grid[start],'vencimiento_final':grid[0]+pd.Timedelta(hours=end),'duracion_h':dur,'censurado_borde':end>n-1,'n_emisiones':e['n_issues'],'n_inicios':count,'epoca':seasons[start],'horas_indeterminadas':int(weight[times][lab[times]==3].sum())}; episodes.append(row); local_eps.append(row)
     assert sum(e['duracion_h'] for e in local_eps)==weight[active].sum()
     for ep in ['ALL','DJF','MAM','JJA','SON']:
      sel=np.ones(n,bool) if ep=='ALL' else seasons==ep; eligible=av&evaluable&sel; issuedsel=warning&sel
      ee=le if ep=='ALL' else le[le.epoca==ep]; rr=[e for e in local_eps if ep=='ALL' or e['epoca']==ep]; ds=[e['duracion_h'] for e in rr]
      nissued=int(issuedsel.sum()); evalissued=int((issuedsel&evaluable).sum()); tp=int((issuedsel&evaluable&y).sum()); positive=int((eligible&y).sum()); detected=int((ee.estado=='anticipado').sum()); opportunity=int((ee.estado!='sin_oportunidad').sum()); hours=int(weight[sel].sum()); alert=int(weight[sel&active].sum())
      row={**keys,'epoca':ep,'n_emisiones':int((av&sel).sum()),'emisiones_evaluables':int(eligible.sum()),'pronosticos_desconocidos':int((av&sel&(target=='desconocido')).sum()),'pronosticos_fuera_alcance':int((av&sel&(target=='fuera_de_alcance')).sum()),'positivos_horarios':positive,'emisiones_con_aviso':nissued,'avisos_evaluables':evalissued,'avisos_desconocidos':int((issuedsel&(target=='desconocido')).sum()),'avisos_fuera_alcance':int((issuedsel&(target=='fuera_de_alcance')).sum()),'emisiones_acertadas':tp,'avisos_en_tramo_real_activo':int((issuedsel&(s==1)).sum()),'inicios_catalogo':len(ee),'inicios_evaluables':opportunity,'inicios_anticipados':detected,'inicios_omitidos':opportunity-detected,'inicios_sin_oportunidad':len(ee)-opportunity,'anticipacion_suma_h':ee.anticipacion_h.sum(),'edad_alerta_suma_h':ee.edad_alerta_h.sum(),'activaciones_dentro_h':int(((ee.estado=='anticipado')&(ee.edad_alerta_h<=h)).sum()),'episodios':len(rr),'episodios_con_inicio':sum(e['n_inicios']>0 for e in rr),'episodios_censurados':sum(e['censurado_borde'] for e in rr),'horas_reloj':hours,'horas_disponibles':int(weight[av&sel].sum()),'horas_evaluables_pronostico':int(weight[eligible].sum()),'horas_observacion_conocida':int(weight[sel&(s!=-1)].sum()),'horas_alerta':alert,'horas_alerta_evaluables':int(weight[eligible&active].sum()),'horas_alerta_disponibles':int(weight[av&sel&active].sum()),'horas_alerta_conocidas':int(weight[sel&active&(s!=-1)].sum()),'horas_alerta_desconocidas':int(weight[sel&active&(s==-1)].sum()),'horas_alerta_indeterminada_vigente':int(weight[sel&(lab==3)].sum()),'horas_alerta_perdida_futura':int(weight[sel&loss].sum()),'horas_alerta_fuera_bloque':int(weight[sel&outside].sum()),'horas_alerta_sin_inicio_vigente':int(weight[sel&(lab==1)].sum()),'horas_alerta_con_inicio_vigente':int(weight[sel&(lab==2)].sum())}
      assert row['horas_alerta']==sum(row[k] for k in ['horas_alerta_indeterminada_vigente','horas_alerta_sin_inicio_vigente','horas_alerta_con_inicio_vigente'])
      metrics.append(row)
  print('Bloque terminado:',b,flush=True)
 for v in handles.values(): v.close()
 pred=pd.concat(forecasts,ignore_index=True); pred.to_csv(OUT/'predicciones.csv.gz',index=False,float_format='%.15g'); pd.concat(availability).to_csv(OUT/'disponibilidad.csv.gz',index=False); pd.concat(targets_out).to_csv(OUT/'objetivos_posteriores.csv.gz',index=False)
 save(pd.DataFrame(recon),'reconciliacion_v0'); save(pd.DataFrame(episodes),'episodios'); save(pd.DataFrame(events_out),'inicios'); save(pd.DataFrame(links_out),'correspondencias'); save(pd.DataFrame(calibration),'calibracion'); save(pd.DataFrame(forecast_metrics),'metricas_pronostico_bloques')
 mf=pd.DataFrame(metrics); additive=[c for c in mf if c not in ['bloque','retraso_h','horizonte_h','modelo','politica','epoca']]
 agg=mf.groupby(['retraso_h','horizonte_h','modelo','politica','epoca'],as_index=False)[additive].sum(); agg['bloque']='AGREGADO'; combined=pd.concat([mf,agg],ignore_index=True); eps=pd.DataFrame(episodes)
 for numerator,denominator,name,factor in [('emisiones_acertadas','avisos_evaluables','precision_emisiones',1),('emisiones_acertadas','emisiones_con_aviso','precision_limite_inferior',1),('emisiones_acertadas','positivos_horarios','recall_emisiones',1),('inicios_anticipados','inicios_evaluables','recall_inicios',1),('anticipacion_suma_h','inicios_anticipados','anticipacion_media_h',1),('edad_alerta_suma_h','inicios_anticipados','edad_alerta_media_h',1),('horas_alerta','horas_reloj','ocupacion_reloj_pct',100),('horas_alerta_evaluables','horas_evaluables_pronostico','ocupacion_evaluable_pct',100),('horas_alerta_disponibles','horas_disponibles','ocupacion_disponible_pct',100),('horas_alerta_conocidas','horas_observacion_conocida','ocupacion_conocida_pct',100)]:
  combined[name]=factor*combined[numerator]/combined[denominator].replace(0,np.nan)
 for i,r in combined.iterrows():
  z=eps[(eps.retraso_h==r.retraso_h)&(eps.horizonte_h==r.horizonte_h)&(eps.modelo==r.modelo)&(eps.politica==r.politica)]
  if r.bloque!='AGREGADO': z=z[z.bloque==r.bloque]
  if r.epoca!='ALL': z=z[z.epoca==r.epoca]
  for name,value in [('media',z.duracion_h.mean()),('mediana',z.duracion_h.median()),('p95',z.duracion_h.quantile(.95)),('max',z.duracion_h.max())]: combined.loc[i,f'duracion_{name}_h']=value
 save(combined,'metricas'); save(combined[combined.bloque=='AGREGADO'],'metricas_agregadas')
 original=pd.read_csv(V1/'tablas/metricas_agregadas.csv'); comparison=combined[(combined.bloque=='AGREGADO')&(combined.retraso_h==0)].merge(original,on=['horizonte_h','modelo','politica','epoca'],suffixes=('_causal','_v1'))
 for c in ['n_emisiones','emisiones_con_aviso','inicios_anticipados','precision_emisiones','ocupacion_reloj_pct','horas_alerta','horas_alerta_desconocidas','horas_alerta_indeterminada_vigente','episodios','duracion_max_h']: comparison['delta_'+c]=comparison[c+'_causal']-comparison[c+'_v1']
 save(comparison,'comparacion_v1')
 paired=[]; overall=[]
 for (d,h,m),z in pred.groupby(['retraso_h','horizonte_h','modelo']):
  z=z[z.estado_objetivo.isin(['positivo','negativo'])]; overall.append({'retraso_h':d,'horizonte_h':h,'modelo':m,'n':len(z),'positivos':int(z.objetivo.sum()),'AP':ap(z.objetivo.to_numpy(),z.probabilidad.to_numpy()),'Brier':((z.probabilidad-z.objetivo)**2).mean()})
 for (h,m),z in pred.groupby(['horizonte_h','modelo']):
  good=z[z.estado_objetivo.isin(['positivo','negativo'])]; wide=good.pivot(index=['bloque','emision','objetivo'],columns='retraso_h',values='probabilidad').dropna()
  y=wide.index.get_level_values('objetivo').to_numpy()
  for d in [0,1,2]: paired.append({'horizonte_h':h,'modelo':m,'retraso_h':d,'n_comun':len(wide),'positivos':int(y.sum()),'AP':ap(y,wide[d].to_numpy()),'Brier':np.mean((wide[d].to_numpy()-y)**2)})
 save(pd.DataFrame(paired),'comparacion_retrasos_pareada'); save(pd.DataFrame(overall),'metricas_pronostico_agregadas')
 rows=[{'archivo':p,'sha256_antes':v,'sha256_despues':sha(Path(p))} for p,v in before.items()]; assert all(r['sha256_antes']==r['sha256_despues'] for r in rows); save(pd.DataFrame(rows),'manifiesto_preservacion')
 (OUT/'comprobaciones.json').write_text(json.dumps({'controles_causales':len(checks),'reconciliacion_filas':int(pd.DataFrame(recon).filas_v0.sum()),'error_max':max(r['error_absoluto_max'] for r in recon),'tolerancia':TOL,'fuentes_preservadas':len(rows),'criterio_catalogo_conforme':True,'emisiones_totales_tres_modelos':len(pred)},indent=2))
 print('Simulación y controles completos',flush=True)
if __name__=='__main__': main()
