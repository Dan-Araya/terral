"""Corrección aditiva de intervalos para políticas disponibles en parte de los brazos."""
import os,sys
os.environ['OPENBLAS_NUM_THREADS']='1';sys.modules['numexpr']=None;sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np
import pandas as pd
BASE=Path(__file__).resolve().parent; MONTH=365.25*24/12

def complete(out):
 out=Path(out); t=out/'tablas'; m=pd.read_csv(t/'metricas_avisos.csv'); alerts=pd.read_csv(t/'correspondencia_avisos.csv'); events=pd.read_csv(t/'evaluacion_inicios.csv'); pred=pd.read_csv(out/'predicciones_validacion.csv',parse_dates=['emision']); sm=pd.read_csv(t/'bootstrap_muestras.csv'); original=pd.read_csv(t/'intervalos_pareados.csv').fillna({'politica':''})
 keys=list(sm[sm.replica.eq(0)][['bloque','mes']].itertuples(index=False,name=None)); pos={k:i for i,k in enumerate(keys)}; W=np.stack([z.multiplicidad.to_numpy() for _,z in sm.groupby('replica')]); rows=[]
 for (h,policy),z in m[m.bloque.eq('AGREGADO')].groupby(['horizonte_h','politica']):
  if len(z)==4: continue
  names=['grupos_avisos','falsas_alarmas','redundantes','inicios_anticipados','inicios_omitidos','inicios_evaluables','recall_inicios','falsas_alarmas_por_mes','horas_bajo_aviso','proporcion_tiempo_aviso','anticipacion_media_h']+[f'fraccion_eventos_ge_{k}h' for k in [1,3,6,8,12,24] if k<=h]
  values={}; points={}
  for arm in z.modelo:
   a=alerts[alerts.horizonte_h.eq(h)&alerts.modelo.eq(arm)&alerts.politica.eq(policy)]; ev=events[events.horizonte_h.eq(h)&events.modelo.eq(arm)&events.politica.eq(policy)]; d=pred[pred.horizonte_h.eq(h)&pred.modelo.eq(arm)]; mat=np.zeros((len(keys),10+len([k for k in [1,3,6,8,12,24] if k<=h])))
   for r in a.itertuples():
    j=pos[r.bloque,r.mes];mat[j,0]+=1;mat[j,1]+=r.estado=='falsa_alarma';mat[j,2]+=r.estado=='redundante'
    if r.estado=='acierto':mat[j,8]+=r.anticipacion_h;mat[j,9]+=1
   for r in ev.itertuples():
    j=pos[r.bloque,r.mes];mat[j,3]+=r.estado=='anticipado';mat[j,4]+=r.estado=='omitido';mat[j,5]+=r.estado!='sin_oportunidad'
    for c,k in enumerate(k for k in [1,3,6,8,12,24] if k<=h):mat[j,10+c]+=r.anticipacion_h>=k
   for bl,g in d.groupby('bloque'):
    threshold=m[m.horizonte_h.eq(h)&m.modelo.eq(arm)&m.politica.eq(policy)&m.bloque.eq(bl)].umbral.iloc[0]
    for month,n in g.groupby(g.emision.dt.strftime('%Y-%m')).size().items():mat[pos[bl,month],6]=n
    on=g[g.probabilidad>=threshold]
    for month,n in on.groupby(on.emision.dt.strftime('%Y-%m')).size().items():mat[pos[bl,month],7]=n
   v=W@mat; div=lambda a,b:np.divide(a,b,out=np.full_like(a,np.nan),where=b!=0)
   arrays=[v[:,0],v[:,1],v[:,2],v[:,3],v[:,4],v[:,5],div(v[:,3],v[:,5]),div(v[:,1],v[:,6]/MONTH),v[:,7],div(v[:,7],v[:,6]),div(v[:,8],v[:,9])]+[div(v[:,10+c],v[:,5]) for c,k in enumerate(k for k in [1,3,6,8,12,24] if k<=h)]
   values[arm]=dict(zip(names,arrays));points[arm]=z[z.modelo.eq(arm)].iloc[0]
  for contrast in list(values)+[a+'-'+b for a,b in [('B','A'),('C','A'),('D','B')] if a in values and b in values]:
   for name in names:
    if '-' in contrast:
     new,old=contrast.split('-');v=values[new][name]-values[old][name];point=points[new][name]-points[old][name]
    else:v=values[contrast][name];point=points[contrast][name]
    finite=v[np.isfinite(v)];rows.append(dict(horizonte_h=h,politica=policy,metrica=name,contraste=contrast,estimacion=point,p025=np.quantile(finite,.025) if len(finite) else np.nan,p975=np.quantile(finite,.975) if len(finite) else np.nan,replicas_validas=len(finite)))
 extra=pd.DataFrame(rows);extra.to_csv(t/'intervalos_politicas_disponibles.csv',index=False,float_format='%.17g'); full=pd.concat([original,extra],ignore_index=True);assert not full.duplicated(['horizonte_h','politica','metrica','contraste']).any();full.to_csv(t/'intervalos_completos.csv',index=False,float_format='%.17g')
 print('Intervalos adicionales para políticas disponibles:',len(extra),flush=True)
if __name__=='__main__':complete(Path(sys.argv[1]) if len(sys.argv)>1 else BASE/'resultados/pisco')
