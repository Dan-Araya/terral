"""Controles adicionales independientes y distribución de anticipación; no entrena."""
import os,sys
os.environ['OPENBLAS_NUM_THREADS']='1'; sys.modules['numexpr']=None; sys.dont_write_bytecode=True
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
BASE=Path(__file__).resolve().parent; ROOT=BASE.parent.parent; MONTH=365.25*24/12

def audit(out):
 out=Path(out); checks={}; sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
 def ck(name,v):
  assert bool(v),name
  checks[name]=True
 def near(a,b):return np.allclose(a,b,rtol=1e-8,atol=1e-10,equal_nan=True)
 config=json.loads((BASE/'configuracion.json').read_text()); spec=config['etapas']['laguna_sin_presion']; station=spec['slug']
 raw=pd.read_csv(ROOT/f'estaciones_complementarias/{station}/derivados/horarias.csv',dtype={'sensor':str},low_memory=False)
 meta=json.loads((ROOT/f'estaciones_complementarias/{station}/metadatos.json').read_text()); conf=json.loads((ROOT/'estaciones_complementarias/configuracion.json').read_text()); cfg=next(s for s in conf['stations'] if s['slug']==station)
 expected={'LAGELTA':('temperatura',1.5,'°C',-50,60),'LAGELHR':('humedad',1.5,'%',0,100),'LAGELVV10':('viento',10.,'m/s',0,75),'LAGELDV10':('direccion',10.,'°',0,360)}
 for sid,(v,h,unit,lo,hi) in expected.items():
  q=raw[raw.sensor.eq(sid)]; t=pd.to_datetime(q.fecha_sin_zona); ck('fechas_'+sid,t.between('2013-01-01','2023-12-31 23:00').all() and not t.duplicated().any()); ck('identidad_'+sid,q.variable.eq(v).all() and q.altura_m.eq(h).all() and q.unidad.eq(unit).all())
  for label,src in [('metadatos',meta),('configuracion',cfg)]:
   r=next(s for s in src['sensors'] if s['code']==sid); ck(label+'_'+sid,(r['variable'],r['height_m'],r['unit'])==(v,h,unit))
  z=q[['min','prom','max','porcentaje_datos']].to_numpy(); good=np.isfinite(z).all(axis=1)&(z[:,3]>0)&(z[:,3]<=100)&(z[:,:3]>=lo).all(axis=1)&(z[:,:3]<=hi).all(axis=1)
  if v!='direccion':good &= (z[:,0]<=z[:,1])&(z[:,1]<=z[:,2])
  ck('calidad_'+sid,np.array_equal(good,q.utilizable_revision.eq(1)))
 inia_expected={'temperatura':('39',2.,'°C'),'humedad':('40',2.,'%'),'viento_2m':('36',2.,'m/s'),'direccion_2m':('37',2.,'°'),'presion':('VCNPA',2.,'hPa')}
 for year in range(2013,2024):
  metadata=pd.read_csv(ROOT/f'historico_inia/derivados/observaciones_{year}.csv',usecols=['variable','sensor','altura_encabezado_m','unidad'],dtype={'sensor':str})
  for variable,(sid,height,unit) in inia_expected.items():
   z=metadata[metadata.variable.eq(variable)]
   ck(f'INIA_identidad_{year}_{variable}',len(z)>0 and z.sensor.eq(sid).all() and z.altura_encabezado_m.eq(height).all() and z.unidad.eq(unit).all())
 pred=pd.read_csv(out/'predicciones_validacion.csv',parse_dates=['emision']).fillna({'id_inicio_objetivo':''}); m=pd.read_csv(out/'tablas/metricas_avisos.csv'); a=pd.read_csv(out/'tablas/correspondencia_avisos.csv'); events=pd.read_csv(out/'tablas/evaluacion_inicios.csv'); cal=pd.read_csv(out/'tablas/calibracion.csv')
 distributions=[]
 for r in m.itertuples():
  d=pred[(pred.horizonte_h==r.horizonte_h)&pred.modelo.eq(r.modelo)]; alerts=a[(a.horizonte_h==r.horizonte_h)&a.modelo.eq(r.modelo)&a.politica.eq(r.politica)]; ev=events[(events.horizonte_h==r.horizonte_h)&events.modelo.eq(r.modelo)&events.politica.eq(r.politica)]
  if r.bloque!='AGREGADO': d=d[d.bloque.eq(r.bloque)]; alerts=alerts[alerts.bloque.eq(r.bloque)]; ev=ev[ev.bloque.eq(r.bloque)]
  eligible=ev.estado.ne('sin_oportunidad').sum(); detected=ev.estado.eq('anticipado').sum(); false=alerts.estado.eq('falsa_alarma').sum(); red=alerts.estado.eq('redundante').sum()
  ck(f'conteos_{r.horizonte_h}_{r.bloque}_{r.modelo}_{r.politica}',near([r.inicios_evaluables,r.inicios_anticipados,r.falsas_alarmas,r.redundantes,r.grupos_avisos],[eligible,detected,false,red,len(alerts)]))
  ck(f'lead_{r.horizonte_h}_{r.bloque}_{r.modelo}_{r.politica}',near([r.anticipacion_media_h,r.anticipacion_mediana_h],[alerts.anticipacion_h.mean(),alerts.anticipacion_h.median()]))
  active=0
  for bl,db in d.groupby('bloque'):
   pol=m[(m.horizonte_h==r.horizonte_h)&m.modelo.eq(r.modelo)&m.politica.eq(r.politica)&m.bloque.eq(bl)].iloc[0]; active+=db.probabilidad.ge(pol.umbral).sum()
  ck(f'exposicion_{r.horizonte_h}_{r.bloque}_{r.modelo}_{r.politica}',near([r.n_emisiones,r.horas_bajo_aviso,r.proporcion_tiempo_aviso,r.falsas_alarmas_por_mes],[len(d),active,active/len(d),false/(len(d)/MONTH)]))
  for k in config['horizontes']:
   if k<=r.horizonte_h: ck(f'todos_eventos_{r.horizonte_h}_{r.bloque}_{r.modelo}_{r.politica}_{k}',near(getattr(r,f'fraccion_eventos_ge_{k}h'),ev.anticipacion_h.ge(k).sum()/eligible))
  lead=alerts.anticipacion_h.dropna(); distributions.append(dict(horizonte_h=r.horizonte_h,bloque=r.bloque,modelo=r.modelo,politica=r.politica,n_detectados=len(lead),inicios_elegibles=eligible,**{name:lead.quantile(q) if len(lead) else np.nan for name,q in [('min',0),('p10',.1),('p25',.25),('mediana',.5),('p75',.75),('p90',.9),('max',1)]}))
 # Independently reconstruct every calibration bin and its contents.
 for r in cal.itertuples():
  d=pred[(pred.horizonte_h==r.horizonte_h)&pred.modelo.eq(r.modelo)]
  if r.bloque!='AGREGADO':d=d[d.bloque.eq(r.bloque)]
  z=d[(d.probabilidad>=r.limite_inf)&((d.probabilidad<r.limite_sup) if r.limite_sup<1 else d.probabilidad.le(1))]
  ck(f'bin_{r.horizonte_h}_{r.bloque}_{r.modelo}_{r.limite_inf}',near([r.n,r.positivos,r.p_media,r.frecuencia],[len(z),z.objetivo.sum(),z.probabilidad.mean(),z.objetivo.mean()]))
 ci=pd.read_csv(out/'tablas/intervalos_completos.csv').fillna({'politica':''}); reps=pd.read_csv(out/'tablas/bootstrap_replicas.csv').fillna({'politica':''})
 for (h,policy,metric),z in reps.groupby(['horizonte_h','politica','metrica']):
  wide=z.pivot(index='replica',columns='contraste',values='valor')
  for new,old in [('B','A'),('C','A'),('D','B')]:ck(f'bootstrap_pareado_{h}_{policy}_{metric}_{new}-{old}',near(wide[new]-wide[old],wide[new+'-'+old]))
 pm=pd.read_csv(out/'tablas/metricas_probabilidades.csv')
 for r in ci.itertuples():
  table=pm if r.politica=='' else m
  z=table[table.horizonte_h.eq(r.horizonte_h)&table.bloque.eq('AGREGADO')]
  if r.politica!='':z=z[z.politica.eq(r.politica)]
  z=z.set_index('modelo')
  if '-' in r.contraste:
   new,old=r.contraste.split('-'); expected=z.loc[new,r.metrica]-z.loc[old,r.metrica]
  else: expected=z.loc[r.contraste,r.metrica]
  ck(f'bootstrap_estimacion_{r.horizonte_h}_{r.politica}_{r.metrica}_{r.contraste}',near(r.estimacion,expected))
 pd.DataFrame(distributions).to_csv(out/'tablas/distribucion_anticipacion.csv',index=False,float_format='%.17g')
 (out/'auditoria_adicional.json').write_text(json.dumps({'resultado':'conforme','codigo_sha256':sha(__file__),'comprobaciones':checks},indent=2,ensure_ascii=False)+'\n')
 print('Auditoría adicional conforme',len(checks),flush=True)
if __name__=='__main__':audit(Path(sys.argv[1]) if len(sys.argv)>1 else BASE/'resultados/pisco')
