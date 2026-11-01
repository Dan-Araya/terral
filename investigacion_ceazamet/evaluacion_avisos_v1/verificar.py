#!/usr/bin/env python3
"""Controles independientes de avisos sin ajustar ni modificar v0."""
import sys,json,hashlib
sys.modules['numexpr']=None
from pathlib import Path
import numpy as np
import pandas as pd
OUT=Path(__file__).resolve().parent; ROOT=OUT.parent.parent; V0=OUT.parent/'linea_base_inicio_v0'
KEY=['horizonte_h','bloque','modelo','politica']
controls=[]
def check(name,ok):
 assert ok,name
 controls.append(name)
def groups_stream(path):
 tail=pd.DataFrame()
 for chunk in pd.read_csv(path,chunksize=100000,parse_dates=['instante','vencimiento_vigente'],dtype={'accion':'string','id_episodio':'string','episodio_cerrado':'string'}):
  d=pd.concat([tail,chunk],ignore_index=True)
  keys=pd.MultiIndex.from_frame(d[KEY]); last=keys[-1]; mask=keys==last
  ready=d.loc[~mask]; tail=d.loc[mask].copy()
  for key,g in ready.groupby(KEY,sort=False): yield key,g.reset_index(drop=True)
 if len(tail):
  for key,g in tail.groupby(KEY,sort=False): yield key,g.reset_index(drop=True)

pred=pd.read_csv(V0/'predicciones_validacion.csv',parse_dates=['emision']).fillna({'id_inicio_objetivo':''})
metrics=pd.read_csv(OUT/'tablas/metricas.csv'); episodes=pd.read_csv(OUT/'tablas/episodios.csv',parse_dates=['inicio_alerta','cierre_por_vencimiento','ultimo_aviso']); events=pd.read_csv(OUT/'tablas/inicios.csv',parse_dates=['inicio','primera_emision_valida','ultima_emision_valida','activacion_episodio']); pairs=pd.read_csv(OUT/'tablas/correspondencia_emisiones_inicios.csv',parse_dates=['emision','inicio','vence']); agg=pd.read_csv(OUT/'tablas/metricas_agregadas.csv')
obs=pd.read_csv(OUT.parent/'diagnostico_2013_2023/tablas/estados_horarios.csv',usecols=['fecha_sin_zona','estado'],parse_dates=['fecha_sin_zona']).set_index('fecha_sin_zona')
check('fuente_observacional_solo_2013_2023',obs.index.min()==pd.Timestamp('2013-01-01') and obs.index.max()==pd.Timestamp('2023-12-31 23:00'))
cat=pd.read_csv(OUT.parent/'catalogo_provisional_v0/catalogo_referencia.csv',usecols=['id_tramo','primera_marca'],parse_dates=['primera_marca'])
check('catalogo_autorizado',cat.primera_marca.between('2013-01-01','2023-12-31 23:00').all())
for key,g in groups_stream(OUT/'historial_horario.csv.gz'):
 h,b,model,policy=key; prefix=f'{b}_{h}h_{model}_{policy}'; n=len(g); times=pd.DatetimeIndex(g.instante)
 check(f'grilla_{prefix}',times.equals(pd.date_range(f'{b[:4]}-01-01',f'{b[-4:]}-12-31 23:00',freq='h')))
 source=pred[(pred.horizonte_h==h)&pred.bloque.eq(b)&pred.modelo.eq('frecuencia' if model=='siempre' else model)].set_index('emision')
 available=times.isin(source.index); check(f'disponibilidad_{prefix}',np.array_equal(available,g.pronostico_disponible))
 pp=source.probabilidad.reindex(times).to_numpy(); yy=source.objetivo.reindex(times).to_numpy()
 check(f'etiquetas_inalteradas_{prefix}',np.allclose(yy,g.objetivo_original,equal_nan=True,rtol=0,atol=0))
 if model!='siempre': check(f'probabilidades_inalteradas_{prefix}',np.allclose(pp,g.probabilidad_original,equal_nan=True,rtol=0,atol=0))
 warning=available if model=='siempre' else (source.regla.reindex(times).eq(1).to_numpy() if policy=='regla_nativa' else pp>=float(policy[3:]))
 warning = warning & obs.loc[times,'estado'].eq('no_cumple').to_numpy()
 check(f'emisiones_umbral_causal_{prefix}',np.array_equal(warning,g.aviso_emitido))
 inds=np.flatnonzero(warning); positions=np.arange(n)
 # Independent interval union, not the engine's cumulative-deadline algorithm.
 delta=np.zeros(n+1,int)
 np.add.at(delta,inds,1); np.add.at(delta,inds+h,-1)
 active=np.cumsum(delta[:-1])>0
 check(f'union_vigencias_{prefix}',np.array_equal(active,g.alerta_activa))
 expected_exp=np.full(n,-1,int)
 for t in inds: expected_exp[t:t+h]=t+h
 expected_dt=np.full(n,np.datetime64('NaT'),dtype='datetime64[ns]'); at=np.flatnonzero(active); expected_dt[at]=times[expected_exp[at]].to_numpy(dtype='datetime64[ns]')
 check(f'vencimientos_sin_extension_retroactiva_{prefix}',np.array_equal(expected_dt,g.vencimiento_vigente.to_numpy(dtype='datetime64[ns]'),equal_nan=True))
 # Independently merge intervals in chronological order with exact expiry adjacency.
 merged=[]; issue_episode={}
 for t in inds:
  if merged and t<=merged[-1][1]: merged[-1][1]=int(t+h); merged[-1][2]+=1
  else: merged.append([int(t),int(t+h),1])
  issue_episode[t]=len(merged)-1
 eps=episodes[(episodes.horizonte_h==h)&episodes.bloque.eq(b)&episodes.modelo.eq(model)&episodes.politica.eq(policy)]
 check(f'episodios_union_{prefix}',len(eps)==len(merged))
 ids=np.full(n,'',object); closed=np.full(n,'',object); actions=np.full(n,'',object)
 for i,(start,end,nissues) in enumerate(merged):
  eid=f'{prefix}_E{i:05}'; row=eps[eps.id_episodio.eq(eid)].iloc[0]
  check(f'episodio_duracion_{eid}',row.inicio_alerta==times[start] and row.cierre_por_vencimiento==times[end] and row.duracion_h==end-start and row.n_emisiones_renovaciones==nissues)
  ids[start:end]=eid; closed[end]=eid
  actions[start]='activacion' if i==0 else 'reactivacion'
 for t in inds:
  if not actions[t]: actions[t]='renovacion'
 check(f'historial_renovaciones_cierres_{prefix}',np.array_equal(actions,g.accion.fillna('')) and np.array_equal(ids,g.id_episodio.fillna('')) and np.array_equal(closed,g.episodio_cerrado.fillna('')))
 weight=np.ones(n,int); weight[-1]=0
 check(f'horas_reconciliadas_{prefix}',np.array_equal(weight,g.duracion_celda_h) and sum(e[1]-e[0] for e in merged)==np.dot(weight,active))
 es=events[(events.horizonte_h==h)&events.bloque.eq(b)&events.modelo.eq(model)&events.politica.eq(policy)]
 cs=cat[cat.primera_marca.dt.year.between(int(b[:4]),int(b[-4:]))]
 check(f'inicios_una_fila_{prefix}',len(es)==len(cs) and not es.id_inicio.duplicated().any())
 eligible_ids={cid for value in source.id_inicio_objetivo for cid in value.split('|') if cid}
 onset_mask=np.zeros(n,bool); unevaluable=np.zeros(n,bool)
 for r in cs.itertuples():
  onset=times.get_indexer([r.primera_marca])[0]; valid=inds[(inds<onset)&(inds+h>=onset)]
  row=es[es.id_inicio.eq(r.id_tramo)].iloc[0]
  (onset_mask if r.id_tramo in eligible_ids else unevaluable)[onset]=True
  expected_status='sin_oportunidad' if r.id_tramo not in eligible_ids else ('anticipado' if len(valid) else 'omitido')
  check(f'deteccion_valida_{prefix}_{r.id_tramo}',row.estado==expected_status)
  ppairs=pairs[(pairs.horizonte_h==h)&pairs.bloque.eq(b)&pairs.modelo.eq(model)&pairs.politica.eq(policy)&pairs.id_inicio.eq(r.id_tramo)]
  check(f'todas_emisiones_validas_{prefix}_{r.id_tramo}',np.array_equal(ppairs.emision.to_numpy(),times[valid].to_numpy()))
  if len(valid):
   epi=issue_episode[valid[0]]; start=merged[epi][0]
   check(f'anticipacion_y_edad_{prefix}_{r.id_tramo}',row.primera_emision_valida==times[valid[0]] and row.anticipacion_h==onset-valid[0] and 0<row.anticipacion_h<=h and row.edad_alerta_al_inicio_h==onset-start and row.activacion_dentro_h==(onset-start<=h) and row.ya_activa_antes_h==(onset-start>h) and ppairs.emision_primaria.sum()==1)
 # Independent per-hour future classification from cumulative counts and deadlines.
 unknown_at=obs.loc[times,'estado'].eq('no_evaluable').to_numpy()
 def classify(ends):
  out=np.zeros(n,int)
  for t in at:
   end=int(ends[t]); win=slice(t+1,min(end+1,n))
   indeterminate=end>=n or unknown_at[win].any() or unevaluable[win].any()
   out[t]=3 if indeterminate else (2 if onset_mask[win].any() else 1)
  return out
 lab=classify(expected_exp); rolling=classify(positions+h)
 check(f'carga_por_vigencia_{prefix}',np.array_equal(lab,g.carga_vigente_clase) and np.array_equal(rolling,g.carga_h_desde_instante_clase))
 ms=metrics[(metrics.horizonte_h==h)&metrics.bloque.eq(b)&metrics.modelo.eq(model)&metrics.politica.eq(policy)]
 for r in ms.itertuples():
  select=np.ones(n,bool) if r.epoca=='ALL' else g.epoca.eq(r.epoca).to_numpy(); elig=select&available
  check(f'metricas_emisiones_{prefix}_{r.epoca}',r.n_emisiones==elig.sum() and r.emisiones_con_aviso==np.sum(warning&elig) and r.emisiones_acertadas==np.sum(warning&elig&(yy==1)))
  check(f'metricas_carga_{prefix}_{r.epoca}',r.horas_alerta==np.dot(weight,select&active) and r.horas_alerta_evaluables==np.dot(weight,elig&active) and r.horas_alerta_sin_inicio_vigente==np.dot(weight,select&(lab==1)) and r.horas_alerta_con_inicio_vigente==np.dot(weight,select&(lab==2)) and r.horas_alerta_indeterminada_vigente==np.dot(weight,select&(lab==3)))
 print(f'Conforme {prefix}',flush=True)
check('fuentes_v0_preservadas',all(hashlib.sha256((ROOT/r.archivo).read_bytes()).hexdigest()==r.sha256_antes==r.sha256_despues for r in pd.read_csv(OUT/'tablas/manifiesto_preservacion.csv').itertuples()))
for p in (OUT/'horarias_preservadas').glob('*.csv'): check(f'metrica_horaria_copia_exacta_{p.name}',p.read_bytes()==(V0/'tablas'/p.name).read_bytes())
check('protocolo_previo_inalterado',hashlib.sha256((OUT/'protocolo.md').read_bytes()).hexdigest()==json.loads((OUT/'registro_previo.json').read_text())['protocolo_sha256'])
for (h,m,p,s),gg in metrics.groupby(['horizonte_h','modelo','politica','epoca']):
 row=agg[(agg.horizonte_h==h)&agg.modelo.eq(m)&agg.politica.eq(p)&agg.epoca.eq(s)].iloc[0]
 for c in ['n_emisiones','emisiones_con_aviso','emisiones_acertadas','inicios_anticipados','inicios_omitidos','horas_alerta','horas_alerta_evaluables','horas_alerta_sin_inicio_vigente','horas_evaluables_pronostico','episodios']:
  check(f'agregado_{h}_{m}_{p}_{s}_{c}',row[c]==gg[c].sum())
# Always and the low-threshold rule must match on load and detection for every block.
a=metrics[metrics.modelo.eq('siempre')].set_index(['horizonte_h','bloque','epoca']); b=metrics[metrics.modelo.eq('regla')&metrics.politica.eq('p>=0.001')].set_index(['horizonte_h','bloque','epoca'])
for c in ['emisiones_con_aviso','inicios_anticipados','horas_alerta','ocupacion_evaluable_pct','episodios','duracion_max_h']:
 check(f'referencia_siempre_identica_regla_umbral_bajo_{c}',np.allclose(a[c],b[c],equal_nan=True))
check('referencia_siempre_ocupacion_100',a.ocupacion_evaluable_pct.eq(100).all())
# Explicit observational gap test: prior notices persist only until their deadlines.
from evaluar import engine, classification
availability=np.ones(12,bool); availability[2:7]=False
state=np.zeros(12,int); state[2:7]=-1
run=engine(availability,np.ones(12,bool),state,3)
check('hueco_observacional_no_cancela_antes_de_vencer',run['active'][2] and run['active'][3] and not run['active'][4] and not run['warning'][2:7].any())
classes=classification(run['active'],np.maximum(run['expires'],np.arange(12)),state==-1,np.zeros(12,bool),np.zeros(12,bool))
check('futuro_desconocido_no_se_clasifica_sin_inicio',classes[2]==3 and classes[3]==3)
check('aviso_nuevo_durante_desconocida_rechazado',not engine(np.ones(12,bool),np.ones(12,bool),state,3)['warning'][2:7].any())
(OUT/'verificacion.json').write_text(json.dumps({'resultado':'conforme','n_comprobaciones':len(controls),'historial_reconstruido_independientemente':True,'causalidad_condicional_flujo_archivado':True,'v0_integro':True,'resumen':controls[-10:]},indent=2,ensure_ascii=False))
print(f'Conforme: {len(controls)} comprobaciones independientes; v0 íntegro.',flush=True)
