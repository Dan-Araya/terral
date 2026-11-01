#!/usr/bin/env python3
"""Auditoría de avisos congelados: no importa ni ejecuta código de ajuste v0."""
import os,sys,json,hashlib,gzip,platform
sys.modules['numexpr']=None
os.environ.setdefault('MPLCONFIGDIR','/tmp/terral-matplotlib')
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
OUT=Path(__file__).resolve().parent; V0=OUT.parent/'linea_base_inicio_v0'; ROOT=OUT.parent.parent
FIRST=pd.Timestamp('2013-01-01'); LAST=pd.Timestamp('2023-12-31 23:00')
THRESHOLDS=[.001,.003,.01,.03,.1,.3,.5]
BLOCKS=['2018-2019','2020-2021','2022-2023']
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(d,name): d.to_csv(OUT/'tablas'/f'{name}.csv',index=False,float_format='%.10g')
def epoch(times): return np.select([times.month.isin([12,1,2]),times.month.isin([3,4,5]),times.month.isin([6,7,8])],['DJF','MAM','JJA'],default='SON')

def engine(available,above,state,h):
 """Input at each step: record presence, threshold decision and CURRENT state only.
 Target labels and future onsets are deliberately absent from the interface.
 """
 available=np.asarray(available,bool); above=np.asarray(above,bool); state=np.asarray(state,int)
 n=len(state); warning=available & above & (state==0)
 expires=np.maximum.accumulate(np.where(warning,np.arange(n)+h,-1))
 active=expires>np.arange(n)
 issue_episode=np.full(n,-1,int); action=np.full(n,'',object); episodes=[]
 last_end=-1; episode=-1
 for t in np.flatnonzero(warning):
  if t>last_end:
   episode+=1; episodes.append({'episode':episode,'start':int(t),'end':int(t+h),'first_expiry':int(t+h),'n_issues':1,'reactivation':episode>0})
   action[t]='reactivacion' if episode>0 else 'activacion'
  else:
   episodes[-1]['end']=int(t+h); episodes[-1]['n_issues']+=1; action[t]='renovacion'
  issue_episode[t]=episode; last_end=int(t+h)
 hist_episode=np.maximum.accumulate(issue_episode); hist_episode[~active]=-1
 closed=np.full(n,-1,int)
 for e in episodes:
  if e['end']<n: closed[e['end']]=e['episode']
 return {'warning':warning,'expires':expires,'active':active,'episode':hist_episode,'issue_episode':issue_episode,'action':action,'closed':closed,'episodes':episodes}

def classification(active,end,unknown,event,unevaluable):
 """Post-hoc attribution only. Evaluate future (t,end[t]]; never changes engine."""
 n=len(active); t=np.arange(n); clipped=np.minimum(end,n-1)
 def count(mask):
  c=np.cumsum(np.asarray(mask,int)); return c[clipped]-c[t]
 outside=end>=n
 unc=outside| (count(unknown)>0) | (count(unevaluable)>0)
 yes=count(event)>0
 # 0 off, 1 no onset, 2 evaluable onset, 3 indeterminate.
 return np.where(active,np.where(unc,3,np.where(yes,2,1)),0)

def event_links(issue_positions,h,events):
 """All valid pairs; every onset has at most one primary (earliest valid) issue."""
 links=[]; primary=[]
 for eid, onset in events:
  valid=issue_positions[(issue_positions<onset)&(issue_positions+h>=onset)]
  if len(valid):
   primary.append((eid,int(onset),int(valid[0]),int(valid[-1]),len(valid)))
   links.extend((eid,int(onset),int(t),i==0) for i,t in enumerate(valid))
 return links,primary

def synthetic_tests():
 results=[]
 def test(name,ok):
  assert ok,name; results.append({'caso':name,'resultado':'conforme'})
 n=24*28; s=np.zeros(n,int); av=np.ones(n,bool)
 e=engine(av,np.ones(n,bool),s,3)
 test('aviso_continuo_28_dias_un_episodio',len(e['episodes'])==1 and e['episodes'][0]['end']==n+2 and e['active'].all())
 # One late event does not make the preceding weeks selective.
 lab=classification(e['active'],e['expires'],np.zeros(n,bool),np.arange(n)==n-3,np.zeros(n,bool))
 test('semanas_carga_sin_inicio',np.sum(lab==1)>n-10)
 flags=np.zeros(12,bool); flags[2]=True; e=engine(np.ones(12,bool),flags,np.zeros(12,int),3)
 links,primary=event_links(np.flatnonzero(e['warning']),3,[('correcto',5),('posterior',6)])
 test('aislado_acierto_en_vencimiento_y_falso_posterior',len(primary)==1 and primary[0][0]=='correcto' and primary[0][2]==2)
 test('aislado_duracion_exacta',np.sum(e['active'])==3 and e['episodes'][0]['end']==5)
 _,false=event_links(np.flatnonzero(e['warning']),3,[('fuera',7)])
 test('aislado_falso',not false)
 flags=np.zeros(12,bool); flags[[1,3,6,10]]=True; e=engine(np.ones(12,bool),flags,np.zeros(12,int),3)
 test('renovaciones_solapadas_adyacentes_y_reactivacion',[(x['start'],x['end']) for x in e['episodes']]==[(1,9),(10,13)] and e['action'][6]=='renovacion' and e['action'][10]=='reactivacion')
 av=np.ones(12,bool); av[2:7]=False; flags=np.ones(12,bool); e=engine(av,flags,np.zeros(12,int),3)
 test('hueco_no_cancela_ni_renueva',e['active'][2] and e['active'][3] and not e['active'][4] and not e['warning'][2:7].any())
 test('hueco_registrado_sin_negativo',not av[4] and e['action'][7]=='reactivacion')
 flags=np.zeros(12,bool); flags[2]=True; e=engine(np.ones(12,bool),flags,np.zeros(12,int),3)
 links,primary=event_links(np.flatnonzero(e['warning']),3,[('a',3),('b',5)])
 test('varios_inicios_proximos_sin_duplicacion',len(primary)==2 and len({r[0] for r in primary})==2 and len(e['episodes'])==1)
 s=np.zeros(12,int); s[2]=1; e=engine(np.ones(12,bool),flags,s,3)
 test('tramo_activo_impide_nuevo_aviso',not e['warning'][2])
 rng=np.random.default_rng(77); n=100; av=rng.random(n)>.2; flags=rng.random(n)>.6; s=np.zeros(n,int)
 full=engine(av,flags,s,3); cut=51; modav=av.copy(); modflags=flags.copy(); mods=s.copy(); modav[cut:]=False; modflags[cut:]=True; mods[cut:]=1
 changed=engine(modav,modflags,mods,3)
 test('prefijo_invariante_al_cambiar_todo_futuro',all(np.array_equal(full[k][:cut],changed[k][:cut]) for k in ['warning','expires','active','episode','action','closed']))
 # A prefix ending before a scheduled future close cannot materialize that close yet.
 prefix=engine(av[:cut],flags[:cut],s[:cut],3)
 test('procesamiento_prefijo_equivale_a_flujo_completo',all(np.array_equal(full[k][:cut],prefix[k]) for k in ['warning','expires','active','episode','action','closed']))
 save(pd.DataFrame(results),'casos_sinteticos'); return results

def audit_v0(pred):
 previous=pd.read_csv(V0/'tablas/correspondencia_avisos.csv',parse_dates=['primera_emision','ultima_emision','inicio','primera_emision_anticipadora']).fillna({'id_inicio':''})
 records=[]; conclusions=[]
 for (h,b,m),d in pred.groupby(['horizonte_h','bloque','modelo']):
  for policy in [f'p>={v:g}' for v in THRESHOLDS]+(['regla_nativa'] if m=='regla' else []):
   on=d[d.regla.eq(1)] if policy=='regla_nativa' else d[d.probabilidad.ge(float(policy[3:]))]
   gr=(on.emision.diff().ne(pd.Timedelta(hours=1))).cumsum()
   old=previous[(previous.horizonte_h==h)&previous.bloque.eq(b)&previous.modelo.eq(m)&previous.politica.eq(policy)]
   rebuilt=pd.DataFrame([{'first':g.emision.iloc[0],'last':g.emision.iloc[-1],'n':len(g)} for _,g in on.groupby(gr)])
   assert len(old)==len(rebuilt)
   if len(old):
    assert np.array_equal(old.primera_emision.to_numpy(),rebuilt['first'].to_numpy())
    assert np.array_equal(old.ultima_emision.to_numpy(),rebuilt['last'].to_numpy())
    assert np.array_equal(old.n_emisiones.to_numpy(),rebuilt.n.to_numpy())
 for r in previous.itertuples():
  age=(r.inicio-r.primera_emision)/pd.Timedelta(hours=1) if pd.notna(r.inicio) else np.nan
  records.append({**r._asdict(),'duracion_cadena_h':(r.ultima_emision-r.primera_emision)/pd.Timedelta(hours=1)+1,'inicio_menos_activacion_h':age,'activacion_antes_del_horizonte':age>r.horizonte_h if np.isfinite(age) else False})
 audit=pd.DataFrame(records).drop(columns='Index')
 save(audit,'auditoria_grupos_v0')
 for h in [1,3]:
  d=pred[(pred.modelo=='regla')&(pred.horizonte_h==h)]; old=audit[(audit.modelo=='regla')&(audit.horizonte_h==h)&audit.politica.eq('p>=0.001')]
  conclusions.append({'hallazgo':f'regla_p>=0.001_{h}h','emisiones':len(d),'emisiones_con_aviso':int(d.probabilidad.ge(.001).sum()),'grupos_v0':len(old),'aciertos_v0':int(old.estado.eq('acierto').sum()),'precision_grupos_v0':old.estado.eq('acierto').mean(),'grupos_acertados_activados_antes_h':int((old.estado.eq('acierto')&old.activacion_antes_del_horizonte).sum()),'max_duracion_cadena_h':old.duracion_cadena_h.max()})
 d=audit[(audit.modelo=='logistica')&(audit.horizonte_h==3)&audit.politica.eq('p>=0.1')&audit.estado.eq('acierto')]
 conclusions.append({'hallazgo':'logistica_p>=0.1_3h','aciertos_v0':len(d),'grupos_acertados_activados_antes_h':int(d.activacion_antes_del_horizonte.sum()),'max_inicio_menos_activacion_h':d.inicio_menos_activacion_h.max()})
 assert conclusions[0]['precision_grupos_v0']==79/86 and conclusions[1]['emisiones']==conclusions[1]['emisiones_con_aviso']
 assert len(d)==57 and d.activacion_antes_del_horizonte.sum()==19
 save(pd.DataFrame(conclusions),'hallazgos_v0'); return audit

def ingest():
 pred=pd.read_csv(V0/'predicciones_validacion.csv',parse_dates=['emision','objetivo_hasta']).fillna({'id_inicio_objetivo':''})
 assert pred.emision.between('2018-01-01',LAST).all() and pred.objetivo_hasta.le(LAST).all()
 assert set(pred.bloque)==set(BLOCKS) and set(pred.modelo)=={'frecuencia','regla','logistica'} and set(pred.horizonte_h)=={1,3}
 assert not pred.duplicated(['emision','horizonte_h','modelo','bloque']).any()
 assert pred.probabilidad.between(0,1).all()
 p=OUT.parent/'diagnostico_2013_2023/tablas/estados_horarios.csv'
 obs=pd.read_csv(p,usecols=['fecha_sin_zona','estado','validez_conjunta'],parse_dates=['fecha_sin_zona'])
 assert obs.fecha_sin_zona.between(FIRST,LAST).all() and not obs.fecha_sin_zona.duplicated().any()
 cat=pd.read_csv(OUT.parent/'catalogo_provisional_v0/catalogo_referencia.csv',usecols=['id_tramo','primera_marca','ultima_marca'],parse_dates=['primera_marca','ultima_marca'])
 assert cat.primera_marca.between(FIRST,LAST).all() and cat.ultima_marca.between(FIRST,LAST).all()
 obs=obs.set_index('fecha_sin_zona'); assert obs.index.equals(pd.date_range(FIRST,LAST,freq='h'))
 assert obs.loc[cat.primera_marca-pd.Timedelta(hours=1),'estado'].eq('no_cumple').all()
 for (h,b),d in pred.groupby(['horizonte_h','bloque']):
  assert d.groupby('emision').modelo.nunique().eq(3).all()
  base=d[d.modelo=='frecuencia']; times=base.emision
  assert obs.loc[times,'estado'].eq('no_cumple').all()
  events=cat[cat.primera_marca.dt.year.between(int(b[:4]),int(b[-4:]))]
  # Exact objective and IDs from fixed catalog, not recomputed meteorological labels.
  expected={t:[] for t in times}
  for r in events.itertuples():
   for lag in range(1,h+1):
    t=r.primera_marca-pd.Timedelta(hours=lag)
    if t in expected: expected[t].append(r.id_tramo)
  for r in base.itertuples():
   assert r.objetivo==bool(expected[r.emision])
   assert set(r.id_inicio_objetivo.split('|'))- {''}==set(expected[r.emision])
  for k in range(1,h+1): assert obs.loc[times+pd.Timedelta(hours=k),'estado'].ne('no_evaluable').all()
 return pred,obs,cat

def simulate(pred,obs,cat):
 allmetrics=[]; allepisodes=[]; allevents=[]; allpairs=[]; exposures=[]; causal_checks=[]
 handles={k:gzip.open(OUT/f'{k}.csv.gz','wt',encoding='utf-8',newline='') for k in ['historial_horario','emisiones_renovaciones','transiciones']}
 first={k:True for k in handles}
 def append(name,d):
  d.to_csv(handles[name],index=False,header=first[name],float_format='%.10g'); first[name]=False
 try:
  for h in [1,3]:
   for block in BLOCKS:
    grid=pd.date_range(f'{block[:4]}-01-01',f'{block[-4:]}-12-31 23:00',freq='h'); n=len(grid); pos=np.arange(n); epoca=epoch(grid)
    state=obs.loc[grid,'estado'].map({'no_cumple':0,'cumple':1,'no_evaluable':-1}).to_numpy()
    weight=np.ones(n,int); weight[-1]=0
    base=pred[(pred.horizonte_h==h)&pred.bloque.eq(block)&pred.modelo.eq('frecuencia')].sort_values('emision')
    ii=grid.get_indexer(base.emision); available=np.zeros(n,bool); available[ii]=True; labels=np.full(n,np.nan); labels[ii]=base.objetivo.to_numpy()
    cs=cat[cat.primera_marca.dt.year.between(int(block[:4]),int(block[-4:]))].copy()
    opportunities={cid for text in base.id_inicio_objetivo for cid in text.split('|') if cid}
    events=[(r.id_tramo,int(grid.get_indexer([r.primera_marca])[0])) for r in cs.itertuples() if r.id_tramo in opportunities]
    evmask=np.zeros(n,bool); uneval=np.zeros(n,bool)
    for r in cs.itertuples(): (evmask if r.id_tramo in opportunities else uneval)[grid.get_indexer([r.primera_marca])[0]]=True
    status=np.select([state==-1,state==1,available],['observacion_desconocida','tramo_activo','pronostico_archivado'],default='sin_pronostico_archivado')
    for season in ['ALL','DJF','MAM','JJA','SON']:
     sel=np.ones(n,bool) if season=='ALL' else epoca==season
     exposures.append({'horizonte_h':h,'bloque':block,'epoca':season,'marcas_reloj':int(sel.sum()),'horas_reloj':int(weight[sel].sum()),'emisiones_evaluables':int((available&sel).sum()),'horas_evaluables_pronostico':int(weight[available&sel].sum()),'horas_observacion_conocida':int(weight[(state!=-1)&sel].sum()),'marcas_desconocidas':int(((state==-1)&sel).sum()),'horas_desconocidas':int(weight[(state==-1)&sel].sum()),'horas_tramo_activo':int(weight[(state==1)&sel].sum()),'horas_sin_pronostico_archivado':int(weight[(~available)&sel].sum()),'horas_conocidas_no_activas_sin_pronostico':int(weight[(~available)&(state==0)&sel].sum())})
    for model in ['frecuencia','regla','logistica','siempre']:
     d=base if model=='siempre' else pred[(pred.horizonte_h==h)&pred.bloque.eq(block)&pred.modelo.eq(model)].sort_values('emision')
     assert np.array_equal(d.emision.to_numpy(),base.emision.to_numpy())
     probs=np.full(n,np.nan); probs[ii]=d.probabilidad.to_numpy(); rule=np.zeros(n,int); rule[ii]=d.regla.to_numpy()
     policies=['toda_emision'] if model=='siempre' else [f'p>={t:g}' for t in THRESHOLDS]+(['regla_nativa'] if model=='regla' else [])
     for policy in policies:
      above=available if model=='siempre' else (rule==1 if policy=='regla_nativa' else probs>=float(policy[3:]))
      run=engine(available,above,state,h); warning=run['warning']; active=run['active']; inds=np.flatnonzero(warning)
      keys={'horizonte_h':h,'bloque':block,'modelo':model,'politica':policy}
      prefix=f'{block}_{h}h_{model}_{policy}'
      # Full-stream prefix check at an arbitrary fixed point, including a future perturbation.
      cutoff=n//2; altered=above.copy(); altered[cutoff:]=~altered[cutoff:]
      other=engine(available,altered,state,h)
      assert all(np.array_equal(run[k][:cutoff],other[k][:cutoff]) for k in ['warning','expires','active','episode','action','closed'])
      assert not warning[state==1].any(); assert not warning[~available].any()
      causal_checks.append({**keys,'prefijo_invariante':True,'sin_aviso_en_tramo_activo':True,'sin_aviso_sin_pronostico':True})
      lab=classification(active,np.maximum(run['expires'],pos),state==-1,evmask,uneval)
      rolling=classification(active,pos+h,state==-1,evmask,uneval)
      # Any issued interval ends inside its block in this frozen archive.
      assert not len(inds) or (inds+h<n).all()
      hist=pd.DataFrame({'instante':grid,'epoca':epoca,'duracion_celda_h':weight,'estado_observacion':obs.loc[grid,'estado'].to_numpy(),'estado_flujo_archivado':status,'pronostico_disponible':available,'probabilidad_original':probs if model!='siempre' else np.full(n,np.nan),'objetivo_original':labels,'aviso_emitido':warning,'accion':run['action'],'alerta_activa':active,'id_episodio':np.where(run['episode']>=0,[f'{prefix}_E{x:05}' if x>=0 else '' for x in run['episode']],''),'vencimiento_vigente':pd.to_datetime([grid[x] if x>=0 and x<n and active[t] else pd.NaT for t,x in enumerate(run['expires'])]),'episodio_cerrado':np.where(run['closed']>=0,[f'{prefix}_E{x:05}' if x>=0 else '' for x in run['closed']],''),'carga_vigente_clase':lab,'carga_h_desde_instante_clase':rolling})
      for k,v in keys.items(): hist[k]=v
      append('historial_horario',hist)
      emitted=hist.iloc[inds].copy(); emitted['id_emision']=[f'{prefix}_A{x:05}' for x in inds]; emitted['vence']=grid[inds+h]; emitted['desde_objetivo_exclusivo']=grid[inds]; emitted['hasta_objetivo_inclusivo']=grid[inds+h]
      append('emisiones_renovaciones',emitted)
      transitions=hist[(hist.accion!='')|(hist.episodio_cerrado!='')].copy(); append('transiciones',transitions)
      links,primary=event_links(inds,h,events); pmap={eid:(onset,t,last,count) for eid,onset,t,last,count in primary}
      assert len(pmap)==len(primary)
      correspondence={e['episode']:[] for e in run['episodes']}
      erows=[]
      for r in cs.itertuples():
       onset=grid.get_indexer([r.primera_marca])[0]
       detected=r.id_tramo in pmap; estatus='sin_oportunidad' if r.id_tramo not in opportunities else ('anticipado' if detected else 'omitido')
       t,last,count=pmap[r.id_tramo][1:] if detected else (-1,-1,0)
       ei=run['issue_episode'][t] if detected else -1; start=run['episodes'][ei]['start'] if detected else -1
       if detected: correspondence[ei].append(r.id_tramo)
       age=onset-start if detected else np.nan
       erows.append({**keys,'id_inicio':r.id_tramo,'inicio':r.primera_marca,'epoca':epoca[onset],'estado':estatus,'id_episodio':f'{prefix}_E{ei:05}' if detected else '', 'primera_emision_valida':grid[t] if detected else pd.NaT,'ultima_emision_valida':grid[last] if detected else pd.NaT,'n_emisiones_validas':count,'anticipacion_h':onset-t if detected else np.nan,'activacion_episodio':grid[start] if detected else pd.NaT,'edad_alerta_al_inicio_h':age,'activacion_dentro_h':detected and age<=h,'ya_activa_antes_h':detected and age>h})
      allevents.extend(erows); ef=pd.DataFrame(erows)
      for eid,onset,t,isprimary in links:
       ei=run['issue_episode'][t]
       allpairs.append({**keys,'id_inicio':eid,'inicio':grid[onset],'emision':grid[t],'vence':grid[t+h],'anticipacion_h':onset-t,'emision_primaria':isprimary,'id_episodio':f'{prefix}_E{ei:05}'})
      ep_rows=[]
      for e in run['episodes']:
       start,end=e['start'],e['end']; times=np.arange(start,min(end,n-1)); duration=min(end,n-1)-start
       assert duration==weight[times].sum()
       ep_rows.append({**keys,'id_episodio':f'{prefix}_E{e["episode"]:05}','inicio_alerta':grid[start],'cierre_por_vencimiento':grid[end] if end<n else pd.NaT,'ultimo_aviso':grid[end-h],'duracion_h':duration,'n_emisiones_renovaciones':e['n_issues'],'reactivacion':e['reactivation'],'epoca_inicio_alerta':epoca[start],'n_inicios_correspondientes':len(correspondence[e['episode']]),'ids_inicios':'|'.join(correspondence[e['episode']]),'horas_evaluables_bajo_alerta':int(weight[times][available[times]].sum()),'horas_con_inicio_vigente':int(weight[times][lab[times]==2].sum()),'horas_sin_inicio_vigente':int(weight[times][lab[times]==1].sum()),'horas_indeterminadas':int(weight[times][lab[times]==3].sum()),'prolongado_mayor_h':duration>h,'duracion_ge24h':duration>=24,'duracion_ge168h':duration>=168})
      allepisodes.extend(ep_rows); eps=pd.DataFrame(ep_rows)
      assert int(weight[active].sum())==sum(r['duracion_h'] for r in ep_rows)
      assert weight[active].sum()==sum(weight[lab==c].sum() for c in [1,2,3])
      for season in ['ALL','DJF','MAM','JJA','SON']:
       select=np.ones(n,bool) if season=='ALL' else epoca==season; eligible=select&available
       ee=ef if season=='ALL' else ef[ef.epoca.eq(season)]
       rr=eps if season=='ALL' or not len(eps) else eps[eps.epoca_inicio_alerta.eq(season)]
       total=int(weight[select].sum()); ev=int(weight[eligible].sum()); known=int(weight[select&(state!=-1)].sum()); alarm=int(weight[select&active].sum()); aev=int(weight[eligible&active].sum()); aknown=int(weight[select&active&(state!=-1)].sum())
       nissued=int((warning&eligible).sum()); tp=int(((labels==1)&warning&eligible).sum()); npositive=int(((labels==1)&eligible).sum())
       nevaluable=int(ee.estado.ne('sin_oportunidad').sum()); ndetected=int(ee.estado.eq('anticipado').sum()); durations=rr.duracion_h.to_numpy() if len(rr) else np.array([])
       matched=int(rr.n_inicios_correspondientes.gt(0).sum()) if len(rr) else 0
       row={**keys,'epoca':season,'n_emisiones':int(eligible.sum()),'positivos_horarios':npositive,'emisiones_con_aviso':nissued,'emisiones_acertadas':tp,'emisiones_falsas':nissued-tp,'precision_emisiones':tp/nissued if nissued else np.nan,'recall_emisiones':tp/npositive if npositive else np.nan,'inicios_catalogo':len(ee),'inicios_evaluables':nevaluable,'inicios_sin_oportunidad':len(ee)-nevaluable,'inicios_anticipados':ndetected,'inicios_omitidos':nevaluable-ndetected,'recall_inicios':ndetected/nevaluable if nevaluable else np.nan,'anticipacion_media_h':ee.anticipacion_h.mean(),'activaciones_dentro_h':int(ee.activacion_dentro_h.sum()),'alerta_ya_activa_antes_h':int(ee.ya_activa_antes_h.sum()),'edad_alerta_media_h':ee.edad_alerta_al_inicio_h.mean(),'horas_reloj':total,'horas_evaluables_pronostico':ev,'horas_observacion_conocida':known,'horas_desconocidas':int(weight[select&(state==-1)].sum()),'horas_tramo_activo':int(weight[select&(state==1)].sum()),'horas_alerta':alarm,'horas_alerta_evaluables':aev,'horas_alerta_conocidas':aknown,'horas_alerta_desconocidas':int(weight[select&active&(state==-1)].sum()),'horas_alerta_sin_pronostico':int(weight[select&active&~available].sum()),'ocupacion_evaluable_pct':100*aev/ev if ev else np.nan,'ocupacion_conocida_pct':100*aknown/known if known else np.nan,'ocupacion_reloj_pct':100*alarm/total,'episodios':len(rr),'episodios_con_inicio':matched,'episodios_sin_inicio':len(rr)-matched,'precision_episodios_descriptiva':matched/len(rr) if len(rr) else np.nan,'duracion_media_h':durations.mean() if len(rr) else np.nan,'duracion_mediana_h':np.median(durations) if len(rr) else np.nan,'duracion_p95_h':np.quantile(durations,.95) if len(rr) else np.nan,'duracion_max_h':durations.max() if len(rr) else np.nan,'episodios_mayores_h':int((durations>h).sum()),'episodios_ge24h':int((durations>=24).sum()),'episodios_ge168h':int((durations>=168).sum())}
       for c,name in [(1,'sin_inicio'),(2,'con_inicio'),(3,'indeterminada')]:
        row[f'horas_alerta_{name}_vigente']=int(weight[select&(lab==c)].sum()); row[f'horas_alerta_evaluable_{name}_vigente']=int(weight[eligible&(lab==c)].sum()); row[f'horas_alerta_{name}_h_desde_t']=int(weight[select&(rolling==c)].sum())
       allmetrics.append(row)
     print(f'{block} {h}h {model}: políticas archivadas evaluadas',flush=True)
 finally:
  for handle in handles.values(): handle.close()
 save(pd.DataFrame(allmetrics),'metricas'); save(pd.DataFrame(allepisodes),'episodios'); save(pd.DataFrame(allevents),'inicios'); save(pd.DataFrame(allpairs),'correspondencia_emisiones_inicios'); save(pd.DataFrame(exposures),'exposicion'); save(pd.DataFrame(causal_checks),'controles_causales')
 return pd.DataFrame(allmetrics),pd.DataFrame(allepisodes),pd.DataFrame(allevents)

def main():
 for folder in ['tablas','graficos','horarias_preservadas']: (OUT/folder).mkdir(exist_ok=True)
 protected=sorted(p for p in V0.rglob('*') if p.is_file())
 inputs=protected+[OUT.parent/'diagnostico_2013_2023/tablas/estados_horarios.csv',OUT.parent/'catalogo_provisional_v0/catalogo_referencia.csv']
 before={str(p.relative_to(ROOT)):sha(p) for p in inputs}
 protocol=sha(OUT/'protocolo.md')
 (OUT/'registro_previo.json').write_text(json.dumps({'protocolo_sha256':protocol,'script_sha256':sha(Path(__file__)),'registrado_utc':pd.Timestamp.now(tz='UTC').isoformat(),'operacion':'auditoria y protocolo previos al recálculo; ningún ajuste de modelos'},indent=2))
 tests=synthetic_tests(); pred,obs,cat=ingest(); audit=audit_v0(pred)
 # Preserve full source metric CSVs byte for byte; do not recompute AP/Brier/calibration.
 for name in ['metricas_horarias','metricas_horarias_agregadas','curvas_precision_recall','calibracion','calibracion_agregada']:
  source=V0/'tablas'/f'{name}.csv'; target=OUT/'horarias_preservadas'/source.name; target.write_bytes(source.read_bytes()); assert sha(source)==sha(target)
 # Document retrospective exclusion reasons after simulation; never pass them into engine.
 ex=pd.read_csv(V0/'tablas/exclusiones_emisiones.csv',parse_dates=['emision'])
 ex=ex[ex.ambito.str.endswith('_validacion')].copy(); assert ex.emision.between('2018-01-01',LAST).all()
 save(ex,'ausencias_retrospectivas_v0')
 metrics,episodes,events=simulate(pred,obs,cat)
 # Aggregate exactly, preserving episode durations and counts across temporal blocks.
 from presentar import aggregate,plots,report
 agg=aggregate(metrics,episodes,events); save(agg,'metricas_agregadas'); plots(metrics,agg,episodes,audit); report(metrics,agg,episodes,events,audit)
 assert sha(OUT/'protocolo.md')==protocol
 manifest=[]
 for rel,original in before.items():
  now=sha(ROOT/rel); assert now==original
  manifest.append({'archivo':rel,'sha256_antes':original,'sha256_despues':now,'conservado':True})
 save(pd.DataFrame(manifest),'manifiesto_preservacion')
 check={'resultado':'conforme','modelos_reentrenados':False,'probabilidades_etiquetas_alteradas':False,'v0_integro':True,'protocolo_sha256':protocol,'script_sha256':sha(Path(__file__)),'predicciones_fuente_sha256':sha(V0/'predicciones_validacion.csv'),'limites_observacionales':['2013-01-01','2023-12-31 23:00:00'],'validacion':['2018-01-01','2023-12-31 23:00:00'],'casos_sinteticos':tests,'causalidad_motor_condicional_flujo_archivado':True,'historia_independiente_de_objetivos_futuros':True,'episodios_reconcilian_horas':True,'inicios_primarios_unicos':True,'sin_recalibracion_sin_despliegue':True,'filas_predicciones_fuente':len(pred),'n_politicas_bloques_h':len(metrics[metrics.epoca.eq('ALL')]),'versiones':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'matplotlib':matplotlib.__version__}}
 (OUT/'comprobaciones.json').write_text(json.dumps(check,ensure_ascii=False,indent=2))
 (OUT/'requirements.txt').write_text('\n'.join(f'{k}=={v}' for k,v in check['versiones'].items() if k!='python')+'\n')
 print('Completado; v0 íntegro y políticas causales auditadas.',flush=True)
if __name__=='__main__': main()
