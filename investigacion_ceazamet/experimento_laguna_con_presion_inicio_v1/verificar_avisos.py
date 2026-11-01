#!/usr/bin/env python3
"""Auditoría independiente de avisos, métricas e intervalos desde artefactos; sin ajustar."""
import os,sys,json,hashlib
os.environ['OPENBLAS_NUM_THREADS']='1'; sys.modules['numexpr']=None
from pathlib import Path
import numpy as np
import pandas as pd
OUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parent
T=OUT/'tablas'; checks={}
def check(k,v):
 assert v,k
 checks[k]=True
p=pd.read_csv(OUT/'predicciones_validacion.csv',parse_dates=['emision']).fillna({'id_inicio_objetivo':''})
a=pd.read_csv(T/'correspondencia_avisos.csv',parse_dates=['primera_emision','ultima_emision']).fillna({'id_inicio':''})
e=pd.read_csv(T/'evaluacion_inicios.csv')
m=pd.read_csv(T/'metricas_avisos.csv'); agg=pd.read_csv(T/'avisos_agregados.csv'); ci=pd.read_csv(T/'intervalos_pareados.csv').fillna({'politica':''})
sm=pd.read_csv(T/'bootstrap_muestras.csv'); monthkeys=list(sm[sm.replica.eq(0)][['bloque','mes']].itertuples(index=False,name=None)); pos={k:i for i,k in enumerate(monthkeys)}
W=np.stack([z.set_index(['bloque','mes']).multiplicidad.reindex(pd.MultiIndex.from_tuples(monthkeys)).to_numpy() for _,z in sm.groupby('replica')])
metrics=['grupos_avisos','falsas_alarmas','redundantes','inicios_anticipados','inicios_omitidos','inicios_evaluables','recall_inicios','precision_avisos','falsas_alarmas_por_mes','anticipacion_media_h']
def quantities(v):
 groups,false,red,det,miss,eligible,success,leads,nleads,hours=v
 return [groups,false,red,det,miss,eligible,det/eligible if eligible else np.nan,success/groups if groups else np.nan,false/(hours/(365.25*24/12)) if hours else np.nan,leads/nleads if nleads else np.nan]
def near(x,y): return np.allclose(x,y,rtol=3e-8,atol=1e-9,equal_nan=True)
# Recreate every threshold's consecutive groups from predictions, including groups omitted accidentally.
for (h,bl,arm),d in p.groupby(['horizonte_h','bloque','modelo']):
 d=d.sort_values('emision')
 for threshold in [.001,.003,.01,.03,.1,.3,.5]:
  policy=f'p>={threshold:g}'; on=d[d.probabilidad.ge(threshold)]
  groupid=on.emision.diff().ne(pd.Timedelta(hours=1)).cumsum()
  g=a[(a.horizonte_h==h)&a.bloque.eq(bl)&a.modelo.eq(arm)&a.politica.eq(policy)]
  check(f'grupos_completos_{h}_{bl}_{arm}_{policy}',len(g)==groupid.nunique())
  used=set()
  for (gid,rows),r in zip(on.groupby(groupid),g.itertuples()):
   candidates=list(dict.fromkeys(cid for ids in rows.id_inicio_objetivo for cid in ids.split('|') if cid))
   # Catalog IDs are chronological; explicitly recover chronology from target emission opportunity.
   candidates.sort(key=lambda cid:e.loc[e.id_inicio.eq(cid),'inicio'].iloc[0])
   match=next((cid for cid in candidates if cid not in used),'')
   state='acierto' if match else ('redundante' if candidates else 'falsa_alarma')
   check('reconstruccion_'+r.id_aviso,r.primera_emision==rows.emision.iloc[0] and r.ultima_emision==rows.emision.iloc[-1] and r.n_emisiones==len(rows) and r.estado==state and r.id_inicio==match)
   if match: used.add(match)
  ev=e[(e.horizonte_h==h)&e.bloque.eq(bl)&e.modelo.eq(arm)&e.politica.eq(policy)]
  available={cid for ids in d.id_inicio_objetivo for cid in ids.split('|') if cid}
  check(f'inicios_{h}_{bl}_{arm}_{policy}',all(r.estado==('sin_oportunidad' if r.id_inicio not in available else 'anticipado' if r.id_inicio in used else 'omitido') for r in ev.itertuples()))
# Recompute every per-partition/season metric from matched rows and exposure.
for r in m.itertuples():
 aa=a[(a.horizonte_h==r.horizonte_h)&a.bloque.eq(r.bloque)&a.modelo.eq(r.modelo)&a.politica.eq(r.politica)]
 ee=e[(e.horizonte_h==r.horizonte_h)&e.bloque.eq(r.bloque)&e.modelo.eq(r.modelo)&e.politica.eq(r.politica)]
 dd=p[(p.horizonte_h==r.horizonte_h)&p.bloque.eq(r.bloque)&p.modelo.eq(r.modelo)]
 if r.epoca!='ALL': aa=aa[aa.epoca_aviso.eq(r.epoca)]; ee=ee[ee.epoca_inicio.eq(r.epoca)]; dd=dd[dd.epoca.eq(r.epoca)]
 vals=quantities([len(aa),aa.estado.eq('falsa_alarma').sum(),aa.estado.eq('redundante').sum(),ee.estado.eq('anticipado').sum(),ee.estado.eq('omitido').sum(),ee.estado.ne('sin_oportunidad').sum(),aa.estado.eq('acierto').sum(),aa.anticipacion_h.sum(),aa.anticipacion_h.notna().sum(),len(dd)])
 check(f'metricas_{r.Index}',near(vals,[getattr(r,c) for c in metrics]) and near([aa.anticipacion_h.median()],[r.anticipacion_mediana_h]))
for h in [1,3]:
 for policy in [f'p>={v:g}' for v in [.001,.003,.01,.03,.1,.3,.5]]:
  values={}; reps={}
  for arm in 'ABCDEF':
   aa=a[(a.horizonte_h==h)&a.modelo.eq(arm)&a.politica.eq(policy)]
   ee=e[(e.horizonte_h==h)&e.modelo.eq(arm)&e.politica.eq(policy)]
   dd=p[(p.horizonte_h==h)&p.modelo.eq(arm)]
   mat=np.zeros((72,10))
   for r in aa.itertuples():
    j=pos[r.bloque,r.mes_aviso]; mat[j,0]+=1; mat[j,1]+=r.estado=='falsa_alarma'; mat[j,2]+=r.estado=='redundante'; mat[j,6]+=r.estado=='acierto'
    if r.estado=='acierto': mat[j,7]+=r.anticipacion_h; mat[j,8]+=1
   for r in ee.itertuples():
    j=pos[r.bloque,r.mes_inicio]; mat[j,3]+=r.estado=='anticipado'; mat[j,4]+=r.estado=='omitido'; mat[j,5]+=r.estado!='sin_oportunidad'
   for k,n in dd.groupby([dd.bloque,dd.emision.dt.strftime('%Y-%m')]).size().items(): mat[pos[k],9]=n
   values[arm]=np.asarray(quantities(mat.sum(axis=0))); reps[arm]=np.asarray([quantities(row) for row in W@mat])
   row=agg[(agg.horizonte_h==h)&agg.modelo.eq(arm)&agg.politica.eq(policy)].iloc[0]
   check(f'agregado_{h}_{arm}_{policy}',near(values[arm],row[metrics].astype(float)))
  for contrast in list('ABCDEF')+['E-C','F-D','C-A','D-B','E-A','F-B']:
   if '-' in contrast:
    new,old=contrast.split('-'); v=values[new]-values[old]; boot=reps[new]-reps[old]
   else: v=values[contrast]; boot=reps[contrast]
   for j,metric in enumerate(metrics):
    row=ci[(ci.horizonte_h==h)&ci.contraste.eq(contrast)&ci.politica.eq(policy)&ci.metrica.eq(metric)].iloc[0]
    finite=boot[np.isfinite(boot[:,j]),j]
    q=np.quantile(finite,[.025,.975]) if len(finite) else [np.nan,np.nan]
    check(f'intervalo_{h}_{policy}_{contrast}_{metric}',near([v[j],*q],[row.estimacion,row.p025,row.p975]) and len(finite)==row.replicas_validas)
record={'resultado':'conforme','codigo_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'controles':list(checks),'limites':'Reconstruye agrupación y correspondencias desde predicciones; etiquetas y medidas proceden del experimento. El bootstrap sigue siendo condicional a ajustes y catálogo.'}
(OUT/'verificacion_avisos.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print('Avisos, métricas e intervalos conformes.')
