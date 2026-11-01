#!/usr/bin/env python3
"""Control independiente de archivos: ventanas, etiquetas y unión de vigencias."""
import sys,os
sys.modules['numexpr']=None; os.environ['OPENBLAS_NUM_THREADS']='1'
from pathlib import Path
import json,hashlib,ast
import numpy as np
import pandas as pd
OUT=Path(__file__).resolve().parent; BASE=OUT.parent

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 # Literal provenance of the four pure functions; no training program import.
 copied=(OUT/'funciones_congeladas.py').read_text()
 extracted={node.name:ast.get_source_segment(copied,node) for node in ast.parse(copied).body if isinstance(node,ast.FunctionDef)}
 for path,names in [(BASE/'linea_base_inicio_v0/ejecutar.py',['features']),(BASE/'evaluacion_avisos_v1/evaluar.py',['engine','classification','event_links'])]:
  original=path.read_text()
  for node in ast.parse(original).body:
   if isinstance(node,ast.FunctionDef) and node.name in names: assert extracted[node.name]==ast.get_source_segment(original,node)
 from funciones_congeladas import engine,classification
 # Post-hoc labels can change radically without changing any operative state.
 av=np.ones(20,bool); above=np.arange(20)%3==0; state=np.zeros(20,int)
 one=engine(av,above,state,3)
 snapshot={k:v.copy() for k,v in one.items() if isinstance(v,np.ndarray)}
 labels_a=classification(one['active'],np.maximum(one['expires'],np.arange(20)),np.zeros(20,bool),np.zeros(20,bool),np.zeros(20,bool))
 labels_b=classification(one['active'],np.maximum(one['expires'],np.arange(20)),np.ones(20,bool),np.ones(20,bool),np.ones(20,bool))
 assert not np.array_equal(labels_a,labels_b)
 assert all(np.array_equal(one[k],v) for k,v in snapshot.items())
 two=engine(av,above,state,3)
 assert all(np.array_equal(two[k],v) for k,v in snapshot.items())
 manifest=pd.read_csv(OUT/'tablas/manifiesto_preservacion.csv')
 assert all(sha(Path(r.archivo))==r.sha256_antes==r.sha256_despues for r in manifest.itertuples())
 obs=pd.read_csv(BASE/'diagnostico_2013_2023/tablas/estados_horarios.csv',usecols=['fecha_sin_zona','estado'],parse_dates=['fecha_sin_zona']).set_index('fecha_sin_zona').estado.map({'no_cumple':0,'cumple':1,'no_evaluable':-1})
 assert obs.index.min()==pd.Timestamp('2013-01-01') and obs.index.max()==pd.Timestamp('2023-12-31 23:00')
 cat=pd.read_csv(BASE/'catalogo_provisional_v0/catalogo_referencia.csv',usecols=['id_tramo','primera_marca','ultima_marca'],parse_dates=['primera_marca','ultima_marca'])
 avail=pd.read_csv(OUT/'disponibilidad.csv.gz',parse_dates=['emision','ancla'])
 target=pd.read_csv(OUT/'objetivos_posteriores.csv.gz',parse_dates=['emision','objetivo_hasta'])
 pred=pd.read_csv(OUT/'predicciones.csv.gz',parse_dates=['emision','ancla','predictor_desde'])
 assert not pred.duplicated(['bloque','retraso_h','horizonte_h','modelo','emision']).any()
 assert pred.groupby(['bloque','retraso_h','horizonte_h','emision']).modelo.nunique().eq(3).all()
 assert np.isfinite(pred.probabilidad).all() and pred.probabilidad.between(0,1).all()
 checks=[]
 for (b,d),g in avail.groupby(['bloque','retraso_h']):
  grid=pd.date_range(f'{b[:4]}-01-01',f'{b[-4:]}-12-31 23:00',freq='h'); state=obs.loc[grid].to_numpy(); n=len(grid); positions=np.arange(n)
  assert np.array_equal(g.emision.to_numpy(),grid.to_numpy()); assert np.array_equal(g.ancla.to_numpy(),(grid-pd.Timedelta(hours=d)).to_numpy())
  expected=np.zeros(n,bool); known=np.full(n,-1,int)
  for t in range(n):
   a=t-d
   if a>=0: known[t]=state[a]
   if a>=6: expected[t]=(state[a]==0 and (state[a-6:a+1]!=-1).all())
  assert np.array_equal(expected,g.puede_emitir) and np.array_equal(known,g.estado_conocido)
  cs=cat[cat.primera_marca.between(grid[0],grid[-1])]; onset=set(grid.get_indexer(cs.primera_marca))
  for h in [1,3]:
   z=target[(target.bloque==b)&(target.retraso_h==d)&(target.horizonte_h==h)]
   assert np.array_equal(z.emision.to_numpy(),grid[expected].to_numpy())
   labels=[]
   for t in np.flatnonzero(expected):
    if t+h>=n: label='fuera_de_alcance'
    elif (state[t+1:t+h+1]==-1).any(): label='desconocido'
    elif any(j in onset for j in range(t+1,t+h+1)): label='positivo'
    else: label='negativo'
    labels.append(label)
   assert labels==z.estado_objetivo.tolist()
   assert z[z.estado_objetivo.isin(['desconocido','fuera_de_alcance'])].objetivo.isna().all()
   for m in ['logistica','frecuencia','regla']:
    pp=pred[(pred.bloque==b)&(pred.retraso_h==d)&(pred.horizonte_h==h)&(pred.modelo==m)]
    assert np.array_equal(pp.emision.to_numpy(),z.emision.to_numpy()) and pp.estado_objetivo.tolist()==labels
   checks.append({'bloque':b,'retraso_h':d,'horizonte_h':h,'marcas':n,'emisiones':int(expected.sum()),'disponibilidad_y_objetivos':True})
 # Streaming chunks are exactly one whole run per original block.
 runs=0; alerts=0; issued=0; run_totals=[]
 for chunk in pd.read_csv(OUT/'historial_horario.csv.gz',chunksize=17520,parse_dates=['emision']):
  # Chunk edges may split 2020–2021 runs; buffer below handles them.
  if runs==0 and 'buffer' not in locals(): buffer=chunk
  else: buffer=pd.concat([buffer,chunk],ignore_index=True)
  while len(buffer):
   row=buffer.iloc[0]; b=row.bloque; grid=pd.date_range(f'{b[:4]}-01-01',f'{b[-4:]}-12-31 23:00',freq='h'); n=len(grid)
   if len(buffer)<n: break
   g=buffer.iloc[:n]; buffer=buffer.iloc[n:].reset_index(drop=True)
   assert g.groupby(['bloque','retraso_h','horizonte_h','modelo','politica']).ngroups==1
   d=int(row.retraso_h); h=int(row.horizonte_h); m=row.modelo; policy=row.politica
   a=avail[(avail.bloque==b)&(avail.retraso_h==d)]; expected_av=a.puede_emitir.to_numpy(); known=a.estado_conocido.to_numpy()
   if m=='siempre': above=np.ones(n,bool)
   else:
    p=pred[(pred.bloque==b)&(pred.retraso_h==d)&(pred.horizonte_h==h)&(pred.modelo==m)].set_index('emision').reindex(grid)
    above=(p.regla==1).to_numpy() if policy=='regla_nativa' else (p.probabilidad>=float(policy[3:])).to_numpy()
   warnings=expected_av&above&(known==0); active=np.zeros(n,bool); ends=np.full(n,-1,int); episode=np.full(n,-1,int); actions=np.full(n,'',object); last=-1; ei=-1
   for t in range(n):
    if warnings[t]:
     if t>last: ei+=1; actions[t]='activacion' if ei==0 else 'reactivacion'
     else: actions[t]='renovacion'
     last=t+h
    active[t]=last>t; ends[t]=last
    if active[t]: episode[t]=ei
   assert np.array_equal(g.emision.to_numpy(),grid.to_numpy())
   assert np.array_equal(warnings,g.aviso_emitido) and np.array_equal(active,g.alerta_activa) and np.array_equal(episode,g.episodio)
   assert actions.tolist()==g.accion.fillna('').tolist()
   expected_end=[str(grid[0]+pd.Timedelta(hours=int(t))) if t>=0 else '' for t in ends]
   assert expected_end==g.vencimiento_vigente.fillna('').tolist()
   tlabels=target[(target.bloque==b)&(target.retraso_h==d)&(target.horizonte_h==h)].set_index('emision').estado_objetivo
   assert g.loc[g.puede_emitir,'estado_objetivo'].tolist()==tlabels.tolist()
   opportunities=set()
   for r in cat[cat.primera_marca.between(grid[0],grid[-1])].itertuples():
    j=grid.get_indexer([r.primera_marca])[0]
    if any(expected_av[t] and tlabels.get(grid[t])=='positivo' for t in range(max(0,j-h),j)): opportunities.add(j)
   state=obs.loc[grid].to_numpy(); onset=set(grid.get_indexer(cat.loc[cat.primera_marca.between(grid[0],grid[-1]),'primera_marca']))
   expectedlab=np.zeros(n,int)
   for t in np.flatnonzero(active):
    end=ends[t]
    if end>=n or (state[t+1:min(end+1,n)]==-1).any() or any(j in onset-opportunities for j in range(t+1,min(end+1,n))): lab=3
    elif any(j in opportunities for j in range(t+1,end+1)): lab=2
    else: lab=1
    expectedlab[t]=lab
   assert np.array_equal(expectedlab,g.carga_vigente_clase)
   weight=np.ones(n,int); weight[-1]=0; hours=int(weight[active].sum()); counts={i:int(weight[expectedlab==i].sum()) for i in [1,2,3]}; assert hours==sum(counts.values())
   run_totals.append({'bloque':b,'retraso_h':d,'horizonte_h':h,'modelo':m,'politica':policy,'horas_alerta':hours,'emisiones_con_aviso':int(warnings.sum())})
   runs+=1; alerts+=hours; issued+=int(warnings.sum())
   if runs%46==0: print('Verificados',runs,'flujos',flush=True)
 assert not len(buffer) and runs==3*3*2*23
 metric=pd.read_csv(OUT/'tablas/metricas.csv'); selected=metric[(metric.bloque!='AGREGADO')&(metric.epoca=='ALL')]
 cmp=pd.DataFrame(run_totals).merge(selected,on=['bloque','retraso_h','horizonte_h','modelo','politica'],suffixes=('_control','_tabla'))
 assert len(cmp)==runs
 for k in ['horas_alerta','emisiones_con_aviso']: assert cmp[k+'_control'].eq(cmp[k+'_tabla']).all()
 pairs=pd.read_csv(OUT/'tablas/correspondencias.csv',parse_dates=['inicio','emision'])
 lead=(pairs.inicio-pairs.emision)/pd.Timedelta(hours=1); assert lead.gt(0).all() and lead.le(pairs.horizonte_h).all()
 assert not pairs[pairs.primaria].duplicated(['bloque','retraso_h','horizonte_h','modelo','politica','id_inicio']).any()
 assert all(sha(Path(r.archivo))==r.sha256_antes for r in manifest.itertuples())
 pd.DataFrame(checks).to_csv(OUT/'tablas/control_independiente_disponibilidad.csv',index=False)
 (OUT/'verificacion.json').write_text(json.dumps({'conforme':True,'flujos_verificados':runs,'horas_alerta_reconciliadas':alerts,'avisos_reconciliados':issued,'fuentes_preservadas':len(manifest),'etiquetas_desconocidas_no_negativas':True,'anticipaciones_estrictamente_positivas':True},indent=2))
 print('Verificación independiente conforme',flush=True)
if __name__=='__main__': main()
