#!/usr/bin/env python3
import os,sys
os.environ['OPENBLAS_NUM_THREADS']='1'; os.environ['OMP_NUM_THREADS']='1'; sys.dont_write_bytecode=True
from pathlib import Path
import json,argparse,hashlib,subprocess
import motor as m
import numpy as np
import pandas as pd
BASE=Path(__file__).resolve().parent
ORIGINAL=BASE.parent/'estudio_horizontes_inicio_v1'
ORIG_NOTICE=m.notice

def sources():
 paths=[BASE.parent/f'historico_inia/derivados/observaciones_{y}.csv' for y in range(2013,2024)]
 paths += [BASE.parent/'catalogo_provisional_v0/catalogo_referencia.csv',BASE.parent/'estaciones_complementarias/configuracion.json']
 paths += [BASE.parent/'estaciones_complementarias/pisco_elqui'/n for n in ['derivados/horarias.csv','derivados/integridad.json','metadatos.json']]
 paths += [p for p in ORIGINAL.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
 paths += [p for p in BASE.iterdir() if p.is_file() and p.suffix in ['.py','.json','.md']]
 return {str(p):m.digest(p) for p in sorted(set(paths))}

def notice(d,cat,h,threshold,block,arm,policy):
 a,e,z=ORIG_NOTICE(d,cat,h,threshold,block,arm,policy)
 on=d.probabilidad.ge(threshold)
 z['emisiones_activas_fuera_objetivo']=int((on&d.objetivo.eq(0)).sum())
 z['horas_evaluables']=len(d); z['duracion_operacional_aviso']='no_definida'
 for q in [0,.25,.5,.75,1]: z[f'anticipacion_q{q:g}']=a.anticipacion_h.quantile(q)
 return a,e,z

def bootstrap(pred,alerts,events,metrics):
 rng=np.random.default_rng(20132023)
 keys=[(bl,str(t)) for bl,_,_,_ in m.b.BLOCKS for t in pd.period_range(bl[:4]+'-01',bl[-4:]+'-12',freq='M')]; pos={k:i for i,k in enumerate(keys)}
 W=np.zeros((300,72),int)
 for r in range(300):
  for j in range(3):
   for start in rng.integers(0,22,8): W[r,24*j+start:24*j+start+3]+=1
 m.save(pd.DataFrame([dict(replica=r,bloque=k[0],mes=k[1],multiplicidad=int(W[r,j])) for r in range(300) for j,k in enumerate(keys)]),m.OUT/'tablas/bootstrap_muestras.csv')
 rows=[]; replicas=[]
 def emit(h,policy,metric,arrays,points):
  contrasts={a:(a,None) for a in arrays}
  contrasts.update({a+'-'+b:(a,b) for a,b in [('B','A'),('C','A'),('D','B')]+[(a,'K') for a in 'ABCD'] if a in arrays and b in arrays})
  for name,(a,b) in contrasts.items():
   v=arrays[a] if b is None else arrays[a]-arrays[b]; point=points[a] if b is None else points[a]-points[b]; good=v[np.isfinite(v)]
   rows.append(dict(horizonte_h=h,politica=policy,metrica=metric,contraste=name,estimacion=point,p025=np.quantile(good,.025) if len(good) else np.nan,p975=np.quantile(good,.975) if len(good) else np.nan,replicas_validas=len(good)))
   replicas.extend(dict(horizonte_h=h,politica=policy,metrica=metric,contraste=name,replica=r,valor=v[r]) for r in range(300))
 div=lambda a,b:np.divide(a,b,out=np.full_like(a,np.nan,dtype=float),where=b!=0)
 for h in m.H:
  vals={k:{} for k in ['AP','Brier']}; pts={k:{} for k in vals}
  for arm in 'ABCDK':
   d=pred[pred.horizonte_h.eq(h)&pred.modelo.eq(arm)]; y=d.objetivo.to_numpy(); p=d.probabilidad.to_numpy(); idx=np.array([pos[bl,t.strftime('%Y-%m')] for bl,t in zip(d.bloque,d.emision)])
   order=np.argsort(-p,kind='stable'); ends=np.r_[np.flatnonzero(p[order][:-1]!=p[order][1:]),len(p)-1]; aps=[]; br=[]
   for w in W:
    weights=w[idx]; tp=np.cumsum(weights[order]*y[order])[ends]; nn=np.cumsum(weights[order])[ends]; rec=div(tp,np.full_like(tp,np.dot(weights,y))); precision=div(tp,nn); precision=np.nan_to_num(precision)
    aps.append(np.sum(np.diff(np.r_[0,rec])*precision)); br.append(np.dot(weights,(p-y)**2)/weights.sum())
   vals['AP'][arm]=np.array(aps); vals['Brier'][arm]=np.array(br); pts['AP'][arm]=m.b.pr(y,p)[0]; pts['Brier'][arm]=np.mean((p-y)**2)
  for metric in vals: emit(h,'',metric,vals[metric],pts[metric])
  for policy in metrics.politica.unique():
   names=['inicios_anticipados','inicios_omitidos','inicios_evaluables','falsas_alarmas','redundantes','grupos_avisos','horas_bajo_aviso','recall_inicios','falsas_alarmas_por_mes','proporcion_tiempo_aviso','anticipacion_media_h']+[f'fraccion_eventos_ge_{k}h' for k in [24,36,48,72] if k<=h]
   vv={n:{} for n in names}; pp={n:{} for n in names}
   for arm in 'ABCDK':
    z=metrics[metrics.horizonte_h.eq(h)&metrics.modelo.eq(arm)&metrics.politica.eq(policy)&metrics.bloque.ne('AGREGADO')]
    if len(z)!=3: continue
    d=pred[pred.horizonte_h.eq(h)&pred.modelo.eq(arm)]; a=alerts[alerts.horizonte_h.eq(h)&alerts.modelo.eq(arm)&alerts.politica.eq(policy)]; e=events[events.horizonte_h.eq(h)&events.modelo.eq(arm)&events.politica.eq(policy)]
    mat=np.zeros((72,11+len([k for k in [24,36,48,72] if k<=h])))
    for r in a.itertuples():
     j=pos[r.bloque,r.mes]; mat[j,3]+=r.estado=='falsa_alarma'; mat[j,4]+=r.estado=='redundante'; mat[j,5]+=1
     if r.estado=='acierto': mat[j,9]+=r.anticipacion_h; mat[j,10]+=1
    for r in e.itertuples():
     j=pos[r.bloque,r.mes]; mat[j,0]+=r.estado=='anticipado'; mat[j,1]+=r.estado=='omitido'; mat[j,2]+=r.estado!='sin_oportunidad'
     for c,k in enumerate(k for k in [24,36,48,72] if k<=h): mat[j,11+c]+=r.anticipacion_h>=k
    thresholds=z.set_index('bloque').umbral.to_dict()
    for (bl,month),g in d.groupby([d.bloque,d.emision.dt.strftime('%Y-%m')]):
     j=pos[bl,month]; mat[j,6]=g.probabilidad.ge(thresholds[bl]).sum(); mat[j,7]=len(g)
    v=W@mat
    arrays=[v[:,i] for i in range(7)]+[div(v[:,0],v[:,2]),div(v[:,3],v[:,7]/m.MONTH),div(v[:,6],v[:,7]),div(v[:,9],v[:,10])]+[div(v[:,11+c],v[:,2]) for c,k in enumerate(k for k in [24,36,48,72] if k<=h)]
    point=metrics[metrics.horizonte_h.eq(h)&metrics.modelo.eq(arm)&metrics.politica.eq(policy)&metrics.bloque.eq('AGREGADO')].iloc[0]
    for n,vv0 in zip(names,arrays): vv[n][arm]=vv0; pp[n][arm]=point[n]
   for n in names: emit(h,policy,n,vv[n],pp[n])
  print('Bootstrap',m.FAMILY,h,flush=True)
 m.save(pd.DataFrame(rows),m.OUT/'tablas/intervalos_pareados.csv'); m.save(pd.DataFrame(replicas),m.OUT/'tablas/bootstrap_replicas.csv')

def render(pm,metrics,cal):
 import matplotlib.pyplot as plt
 g=m.OUT/'graficos';g.mkdir(exist_ok=True)
 for h in m.H:
  fig,axs=plt.subplots(1,3,figsize=(15,4))
  for arm in 'ABCDK':
   c=cal[cal.horizonte_h.eq(h)&cal.modelo.eq(arm)&cal.bloque.eq('AGREGADO')&cal.n.gt(0)];axs[0].plot(c.p_media,c.frecuencia,'o-',label=arm)
   z=metrics[metrics.horizonte_h.eq(h)&metrics.modelo.eq(arm)&metrics.bloque.eq('AGREGADO')&metrics.politica.str.startswith('presupuesto')];axs[1].plot(z.falsas_alarmas_por_mes,z.recall_inicios,'o-',label=arm);axs[2].plot(z.proporcion_tiempo_aviso,z.anticipacion_media_h,'o-',label=arm)
  axs[0].set(xlabel='Probabilidad',ylabel='Frecuencia');axs[1].set(xlabel='Falsas / mes evaluable',ylabel='Eventos detectados / elegibles');axs[2].set(xlabel='Fracción de emisiones activas',ylabel='Anticipación media h')
  for ax in axs: ax.legend();ax.grid(alpha=.2)
  fig.suptitle(f'{m.FAMILY}, extremo {h} h');fig.tight_layout();fig.savefig(g/f'{h}h.png',dpi=140);plt.close(fig)
 ci=pd.read_csv(m.OUT/'tablas/intervalos_pareados.csv').fillna({'politica':''});dt=pd.read_csv(m.OUT/'tablas/diferencias_pareadas.csv').fillna({'politica':''})
 lines=[f'# Pisco: {m.FAMILY}', 'Exploratorio, criterio histórico 2013–2023. No acredita operación ni mecanismo físico. IC marginales, múltiples comparaciones; no se declara límite físico a partir de incertidumbre. AP no compara objetivos de diferente prevalencia.', '## Probabilidades',pm[pm.bloque.eq('AGREGADO')].to_markdown(index=False)]
 for h in m.H:
  lines += [f'## Objetivo {h} h (extremo superior)', 'K: calendario; A/B/C/D conservan calendario original.']
  for contrast in ['B-A','C-A','D-B','A-K','B-K','C-K','D-K']:
   z=ci[ci.horizonte_h.eq(h)&ci.contraste.eq(contrast)&ci.politica.eq('')].set_index('metrica');d=dt[dt.horizonte_h.eq(h)&dt.contraste.eq(contrast)&dt.bloque.ne('AGREGADO')&dt.politica.eq('')];ap=z.loc['AP'];br=z.loc['Brier']
   good=(d[d.metrica.eq('AP')].delta>0).all() and (d[d.metrica.eq('Brier')].delta<0).all() and ap.p025>0 and br.p975<0
   bad=(d[d.metrica.eq('AP')].delta<0).all() and (d[d.metrica.eq('Brier')].delta>0).all() and ap.p975<0 and br.p025>0
   status='mejora consistente' if good else ('empeoramiento consistente' if bad else ('ausencia de evidencia de mejora' if ap.p025<=0<=ap.p975 and br.p025<=0<=br.p975 else 'incierto'))
   lines.append(f'{contrast}: ΔAP {ap.estimacion:.6f} [{ap.p025:.6f}, {ap.p975:.6f}]; ΔBrier {br.estimacion:.6f} [{br.p025:.6f}, {br.p975:.6f}]: {status}.')
  z=metrics[metrics.horizonte_h.eq(h)&metrics.bloque.eq('AGREGADO')&metrics.politica.str.startswith('presupuesto')]
  cols=['modelo','politica','inicios_evaluables','inicios_anticipados','inicios_omitidos','falsas_alarmas','redundantes','horas_bajo_aviso','n_emisiones','anticipacion_media_h','anticipacion_mediana_h']+[f'fraccion_eventos_ge_{k}h' for k in [24,36,48,72] if k<=h]
  lines += ['Políticas disponibles en los tres bienios (resto: tablas/politicas.csv; no equivalen a cero). Presupuesto interno no garantiza tasa externa.',z[cols].to_markdown(index=False),f'![Resultados](graficos/{h}h.png)']
 lines+=['## Límites y trazabilidad','Ventanas solapadas y dependencia temporal: IC de 300 remuestreos por bloques de tres meses, condicionales a ajustes y etiquetas, extremos no uniformes, sin cobertura conjunta. Las validaciones fueron reutilizadas en desarrollo. Horas activas son marcas con emisión, no duración operacional. Todas las políticas, particiones, calibración y registros de anticipación están en tablas. Predicciones trazables y OOF en unidades. Soporte común72 y pérdidas frente al estudio anterior en tablas/perdidas_soporte.csv. Latencia, zona y discrepancia de altura INIA siguen sin resolver. No se entrenan otras estaciones.']
 (m.OUT/'informe.md').write_text('\n\n'.join(lines)+'\n')

def configure(dest,family):
 m.FAMILY=family;m.H=[24,36,48,72] if family=='acumuladas' else [36,48,72];m.OUT=dest/family;m.s.ROOT=BASE.parent;m.s.b.ROOT=BASE.parent.parent
 m.sources=sources;m.notice=notice;m.bootstrap=bootstrap;m.render=render

def main():
 p=argparse.ArgumentParser();p.add_argument('comando',choices=['ejecutar','verificar','reproducir','informar']);p.add_argument('--salida',type=Path,default=BASE/'resultados/principal');a=p.parse_args();dest=a.salida.resolve()
 if a.comando in ['ejecutar','informar']:
  for family in ['acumuladas','tramos']:
   configure(dest,family)
   if a.comando=='ejecutar':m.run()
   else:m.report()
 elif a.comando=='verificar':
  from verificar_extension import verify
  verify(dest)
 else:
  rep=dest.parent/'reproduccion';assert not rep.exists(),'Reproducción requiere directorio nuevo'
  subprocess.run([sys.executable,str(BASE/'extension.py'),'ejecutar','--salida',str(rep)],check=True)
  from verificar_extension import verify
  verify(dest);verify(rep)
  excluded={'registro_preentrenamiento.json','verificacion_independiente.json'}
  paths=[p.relative_to(dest) for p in dest.rglob('*') if p.is_file() and p.name not in excluded]
  diff=[str(p) for p in paths if not (rep/p).exists() or m.digest(dest/p)!=m.digest(rep/p)]
  m.js(dest/'reproduccion.json',dict(resultado='conforme' if not diff else 'discrepancias',archivos_comparados=len(paths),diferencias=diff,ajustes_por_ejecucion=315));assert not diff,diff
if __name__=='__main__':main()
