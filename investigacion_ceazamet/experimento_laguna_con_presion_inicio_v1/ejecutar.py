#!/usr/bin/env python3
"""Comparación cerrada de seis brazos; solo fuentes locales 2013–2023."""
import os,sys
os.environ['OPENBLAS_NUM_THREADS']='1'; os.environ['OMP_NUM_THREADS']='1'
os.environ.setdefault('MPLCONFIGDIR','/tmp/laguna-v1-mpl')
sys.dont_write_bytecode=True
sys.modules['numexpr']=None
from pathlib import Path
import importlib.util,json,platform
import numpy as np
import pandas as pd
OUT=Path(__file__).resolve().parent; ROOT=OUT.parent
spec=importlib.util.spec_from_file_location('base',ROOT/'linea_base_inicio_v0/ejecutar.py')
b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b); b.OUT=OUT
IDX=b.IDX
EXPECTED={'LAGELTA':('temperatura',1.5),'LAGELHR':('humedad',1.5),'LAGELVV10':('viento',10.),'LAGELDV10':('direccion',10.),'LAGELPA':('presion',2.)}
CONFIG=json.loads((OUT/'configuracion_experimento.json').read_text())
assert CONFIG['estacion']=='la_laguna_elqui' and CONFIG['sensores']=={k:{'variable':v,'altura_m':h} for k,(v,h) in EXPECTED.items()}
CONTRASTS=[('E','C'),('F','D'),('C','A'),('D','B'),('E','A'),('F','B')]
def js(name,obj): (OUT/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False,default=str,allow_nan=False)+'\n')
def save(d,name): b.save(d,name)
def extension(x,prefix,wind=None):
 f=x.copy()
 for lag in [1,3]:
  for c in x:
   f[f'{c}_lag{lag}']=x[c].shift(lag); f[f'{c}_delta{lag}']=x[c]-x[c].shift(lag)
 for c in x: f[f'{c}_media_previa6']=x[c].shift(1).rolling(6,min_periods=6).mean()
 if wind: f['V_max_previo6']=x[wind].shift(1).rolling(6,min_periods=6).max()
 return f.add_prefix(prefix)
def allfeatures(x,p,pe):
 z=pe[['temperatura','humedad','viento']].copy()
 z['sin_D']=np.sin(np.deg2rad(pe.direccion)); z['cos_D']=np.cos(np.deg2rad(pe.direccion))
 return pd.concat([b.features(x),extension(p.to_frame('presion'),'INIA_'),extension(z,'LAG_',wind='viento'),extension(pe[['presion']],'LAG_')],axis=1)
def load_extra(manifest):
 confpath=ROOT/'estaciones_complementarias/configuracion.json'
 config=json.loads(confpath.read_text()); assert config['start']=='2013-01-01' and config['end']=='2023-12-31'
 station=next(s for s in config['stations'] if s['slug']==CONFIG['estacion'])
 metadata_path=ROOT/'estaciones_complementarias/la_laguna_elqui/metadatos.json'
 metadata=json.loads(metadata_path.read_text())
 assert metadata['slug']==station['slug']
 metadata_sensors={s['code']:s for s in metadata['sensors']}
 for sid,(v,height) in EXPECTED.items(): assert metadata_sensors[sid]['variable']==v and metadata_sensors[sid]['height_m']==height
 specs={s['code']:s for s in station['sensors']}
 for sid,(v,height) in EXPECTED.items(): assert specs[sid]['variable']==v and specs[sid]['height_m']==height
 prs=[]; meta=[]
 for year in range(2013,2024):
  q=pd.read_csv(ROOT/f'historico_inia/derivados/observaciones_{year}.csv',usecols=['fecha_sin_zona','variable','sensor','altura_encabezado_m','unidad','prom','porcentaje_datos','prom_utilizable_revision'])
  dt=pd.to_datetime(q.fecha_sin_zona); assert dt.between(b.START,b.END).all() and dt.dt.year.eq(year).all()
  basic=q[q.variable.isin(b.MAIN)]
  assert not (basic.prom_utilizable_revision.eq(1)&basic.porcentaje_datos.gt(100)).any()
  meta.append(q[q.variable.isin(b.MAIN+['presion'])][['variable','sensor','altura_encabezado_m','unidad']].drop_duplicates().assign(ano=year))
  q=q[q.variable.eq('presion')].copy(); assert not q.fecha_sin_zona.duplicated().any()
  good=np.isfinite(q.prom)&q.porcentaje_datos.gt(0)&q.porcentaje_datos.le(100)&q.prom_utilizable_revision.eq(1)
  prs.append(pd.Series(q.prom.where(good).to_numpy(),index=pd.to_datetime(q.fecha_sin_zona)))
 p=pd.concat(prs).reindex(IDX); save(pd.concat(meta),'metadatos_inia')
 path=ROOT/'estaciones_complementarias/la_laguna_elqui/derivados/horarias.csv'
 integrity=ROOT/'estaciones_complementarias/la_laguna_elqui/derivados/integridad.json'
 assert b.digest(path)==json.loads(integrity.read_text())['tables_sha256']['horarias.csv']
 chunks=pd.read_csv(path,dtype={'sensor':str},chunksize=50000,usecols=['fecha_sin_zona','sensor','variable','altura_m','unidad','min','prom','max','porcentaje_datos','presente','utilizable_revision','problemas'])
 q=pd.concat([chunk.loc[chunk.sensor.isin(EXPECTED)] for chunk in chunks],ignore_index=True)
 dt=pd.to_datetime(q.fecha_sin_zona); assert dt.between(b.START,b.END).all() and dt.eq(dt.dt.floor('h')).all()
 q=q[q.sensor.isin(EXPECTED)].copy(); q['fecha']=pd.to_datetime(q.fecha_sin_zona)
 assert not q.duplicated(['fecha','sensor']).any()
 limits={'temperatura':(-50,60),'humedad':(0,100),'viento':(0,75),'direccion':(0,360),'presion':(300,1100)}
 masks=[]
 for sid,(v,height) in EXPECTED.items():
  z=q[q.sensor.eq(sid)]; assert z.variable.eq(v).all() and z.altura_m.eq(height).all() and z.unidad.eq(specs[sid]['unit']).all()
  good=np.isfinite(z[['min','prom','max','porcentaje_datos']]).all(axis=1)&z.porcentaje_datos.gt(0)&z.porcentaje_datos.le(100)
  for c in ['min','prom','max']: good &= z[c].between(*limits[v])
  if v!='direccion': good &= z['min'].le(z.prom)&z.prom.le(z['max'])
  assert np.array_equal(good,z.utilizable_revision.eq(1))
  masks.append({'sensor':sid,'variable':v,'altura_m':height,'unidad':specs[sid]['unit'],'filas':len(z),'utilizables':int(good.sum()),'ceros_validos':int((good&z.prom.eq(0)).sum())})
 pressure=q[q.sensor.eq('LAGELPA')]
 suspect=pressure[['min','prom','max']].notna().all(axis=1)&(~pressure[['min','prom','max']].ge(300).all(axis=1)|~pressure[['min','prom','max']].le(1100).all(axis=1))
 assert int(suspect.sum())==4004 and not pressure.loc[suspect,'utilizable_revision'].eq(1).any()
 assert pressure.loc[suspect].groupby(pressure.loc[suspect,'fecha'].dt.year).size().to_dict()=={2015:1334,2016:2664,2017:6}
 save(pressure.loc[suspect].copy(),'presion_sospechosa_excluida')
 q.loc[~q.utilizable_revision.eq(1),'prom']=np.nan
 pe=q.pivot(index='fecha',columns='variable',values='prom').reindex(IDX)
 gaps=[]; coverage=[]
 for v in pe:
  absent=pe[v].isna(); groups=absent.ne(absent.shift()).cumsum()
  for _,g in absent[absent].groupby(groups[absent]): gaps.append({'variable':v,'inicio':g.index.min(),'fin':g.index.max(),'horas':len(g)})
  for yr,z in pe[v].groupby(pe.index.year): coverage.append({'variable':v,'ano':yr,'horas_calendario':len(z),'utilizables':int(z.notna().sum()),'no_utilizables':int(z.isna().sum()),'ceros_validos':int(z.eq(0).sum())})
 save(pd.DataFrame(gaps),'huecos_por_sensor'); save(pd.DataFrame(coverage),'cobertura_anual_laguna')
 save(pd.DataFrame(masks),'sensores_laguna')
 for path in [confpath,path,integrity,metadata_path]:
  manifest.append({'archivo':str(path.relative_to(b.ROOT)),'sha256_antes':b.digest(path)})
 return p,pe

def support(ds,f,p,pe):
 pe=pe[[v for v,h in EXPECTED.values()]]
 masks={'A':pd.Series(True,index=IDX),'B':p.notna().rolling(7,min_periods=7).sum().eq(7),'C':pe.drop(columns='presion').notna().all(axis=1).rolling(7,min_periods=7).sum().eq(7)}
 masks['D']=masks['B']&masks['C']
 masks['E']=pe.notna().all(axis=1).rolling(7,min_periods=7).sum().eq(7)
 masks['F']=masks['B']&masks['E']
 missing={v:~pe[v].notna().rolling(7,min_periods=7).sum().eq(7) for v in pe}
 rows=[]; reasons=[]; partitions=[]; impact=[]; membership=[]
 def ids(d): return {cid for value in d.loc[d.y.eq(1),'id_inicio_objetivo'] for cid in value.split('|') if cid}
 for (h,block,role),d in list(ds.items()):
  common=masks['F'].reindex(d.index)
  for arm in 'ABCDEF':
   ok=masks[arm].reindex(d.index)
   rows.append({'horizonte_h':h,'bloque':block,'rol':role,'brazo_potencial':arm,'base_elegible_A':len(d),'potencial_brazo':int(ok.sum()),'comun_6_brazos':int(common.sum()),'perdidas_vs_A':int((~common).sum()),'perdidas_vs_potencial':int((ok&~common).sum()),'positivos_A':int(d.y.sum()),'positivos_comunes':int(d.loc[common,'y'].sum()),'inicios_base':len(ids(d)),'inicios_comunes':len(ids(d.loc[common])),'inicios_sin_oportunidad_por_exclusion':len(ids(d)-ids(d.loc[common]))})
  ex=pd.DataFrame({'emision':d.index,'presion_INIA_ventana_incompleta':~masks['B'].reindex(d.index).to_numpy(),'Laguna_ventana_incompleta':~masks['E'].reindex(d.index).to_numpy()})
  for v,flag in missing.items(): ex[v+'_Laguna_ventana_incompleta']=flag.reindex(d.index).to_numpy()
  ex['motivo_primario']=np.where(ex.presion_INIA_ventana_incompleta,'presion_INIA_ventana_incompleta',np.where(ex.Laguna_ventana_incompleta,'Laguna_ventana_incompleta','incluida'))
  ex['objetivo']=d.y.to_numpy(); ex['id_inicio_objetivo']=d.id_inicio_objetivo.to_numpy()
  reasons.append(ex.assign(horizonte_h=h,bloque=block,rol=role))
  # Nonexclusive losses, and marginal losses after imposing every other sensor.
  for cause,bad in missing.items():
   bad=bad.reindex(d.index)
   rest=masks['B'].copy(); others=[v for v in pe if v!=cause]
   for v in others: rest &= ~missing[v]
   lost=rest.reindex(d.index)&bad
   recover=common|lost
   impact.append({'horizonte_h':h,'bloque':block,'rol':role,'causa':cause,'ventanas_afectadas':int(bad.sum()),'positivos_afectados':int(d.loc[bad,'y'].sum()),'inicios_afectados':len(ids(d.loc[bad])),'perdidas_marginales_horas':int(lost.sum()),'perdidas_marginales_positivos':int(d.loc[lost,'y'].sum()),'inicios_perdidos_sin_otras_oportunidades':len(ids(d)-ids(d.loc[~bad])),'inicios_recuperables_marginalmente':len(ids(d.loc[recover])-ids(d.loc[common]))})
  times=d.index[common]
  z=f.loc[times].copy(); z[['y','id_inicio_objetivo','regla']]=d.loc[times,['y','id_inicio_objetivo','regla']]
  assert z.notna().all().all(); ds[h,block,role]=z
  membership.append(z[['y','id_inicio_objetivo']].rename_axis('emision').reset_index().assign(horizonte_h=h,bloque=block,rol=role,brazos='A|B|C|D|E|F'))
  partitions.append({'horizonte_h':h,'bloque':block,'rol':role,'n':len(z),'positivos':int(z.y.sum()),'primera_emision':times.min(),'ultima_emision':times.max(),'inicios_con_oportunidad':len(ids(z))})
 save(pd.DataFrame(impact),'efecto_huecos_laguna'); save(pd.DataFrame(rows),'soporte_potencial_y_perdidas'); save(pd.concat(reasons),'elegibilidad_adicional'); save(pd.DataFrame(partitions),'particiones'); save(pd.concat(membership),'ejemplos_comunes')
 return ds

def bootstrap(pred,alerts,events):
 rng=np.random.default_rng(20132023); monthmap={bl:pd.period_range(f'{bl[:4]}-01',f'{bl[-4:]}-12',freq='M').astype(str).tolist() for bl,_,_,_ in b.BLOCKS}
 keys=[(bl,m) for bl in monthmap for m in monthmap[bl]]; samples=[]
 for rep in range(300):
  cnt=dict.fromkeys(keys,0)
  for bl,months in monthmap.items():
   for s in rng.integers(0,22,8):
    for m in months[s:s+3]: cnt[bl,m]+=1
  samples.append(cnt)
 save(pd.DataFrame([{'replica':i,'bloque':k[0],'mes':k[1],'multiplicidad':v} for i,cnt in enumerate(samples) for k,v in cnt.items()]),'bootstrap_muestras')
 boot=[]; points=[]
 def storemetric(h,policy,metric,est,reps):
  for arm in 'ABCDEF':
   a=np.asarray(reps[arm],float); finite=a[np.isfinite(a)]
   boot.append({'horizonte_h':h,'politica':policy,'metrica':metric,'contraste':arm,'estimacion':est[arm],'p025':np.quantile(finite,.025) if len(finite) else np.nan,'p975':np.quantile(finite,.975) if len(finite) else np.nan,'replicas_validas':len(finite)})
  for new,old in CONTRASTS:
   a=np.asarray(reps[new])-np.asarray(reps[old]); a=a[np.isfinite(a)]
   boot.append({'horizonte_h':h,'politica':policy,'metrica':metric,'contraste':new+'-'+old,'estimacion':est[new]-est[old],'p025':np.quantile(a,.025) if len(a) else np.nan,'p975':np.quantile(a,.975) if len(a) else np.nan,'replicas_validas':len(a)})
 for h in [1,3]:
  wide=pred[pred.horizonte_h.eq(h)].pivot(index=['bloque','emision','objetivo'],columns='modelo',values='probabilidad').reset_index()
  kk=list(zip(wide.bloque,wide.emision.dt.strftime('%Y-%m'))); y=wide.objetivo.to_numpy()
  est={metric:{arm:(b.pr(y,wide[arm])[0] if metric=='AP' else np.mean((wide[arm]-y)**2)) for arm in 'ABCDEF'} for metric in ['AP','Brier']}
  reps={metric:{arm:[] for arm in 'ABCDEF'} for metric in est}
  for cnt in samples:
   inds=np.repeat(np.arange(len(wide)),[cnt[k] for k in kk]); yy=y[inds]
   for arm in 'ABCDEF':
    pp=wide[arm].to_numpy()[inds]
    reps['AP'][arm].append(b.pr(yy,pp)[0]); reps['Brier'][arm].append(np.mean((pp-yy)**2))
  for metric in est: storemetric(h,'',metric,est[metric],reps[metric])
  print(f'Bootstrap horario {h}h completado',flush=True)
 # Monthly additive statistics preserve the original matching and month attribution.
 am=pd.read_csv(OUT/'tablas/metricas_avisos.csv'); am=am[am.epoca.eq('ALL')]
 notice_metrics=['grupos_avisos','falsas_alarmas','redundantes','inicios_anticipados','inicios_omitidos','inicios_evaluables','recall_inicios','precision_avisos','falsas_alarmas_por_mes','anticipacion_media_h']
 def quantities(s):
  groups,false,red,det,miss,evaluable,success,lead_sum,lead_n,hours=s
  return dict(zip(notice_metrics,[groups,false,red,det,miss,evaluable,det/evaluable if evaluable else np.nan,success/groups if groups else np.nan,false/(hours/(365.25*24/12)) if hours else np.nan,lead_sum/lead_n if lead_n else np.nan]))
 for h in [1,3]:
  for policy in [f'p>={v:g}' for v in b.THRESHOLDS]:
   est={metric:{} for metric in notice_metrics}; reps={metric:{} for metric in notice_metrics}
   for arm in 'ABCDEF':
    a=alerts[(alerts.horizonte_h==h)&(alerts.modelo==arm)&(alerts.politica==policy)]
    e=events[(events.horizonte_h==h)&(events.modelo==arm)&(events.politica==policy)]
    d=pred[(pred.horizonte_h==h)&(pred.modelo==arm)]
    mat=np.zeros((len(keys),10)); keypos={k:i for i,k in enumerate(keys)}
    for row in a.itertuples():
     j=keypos[row.bloque,row.mes_aviso]; mat[j,0]+=1; mat[j,1]+=row.estado=='falsa_alarma'; mat[j,2]+=row.estado=='redundante'; mat[j,6]+=row.estado=='acierto'
     if row.estado=='acierto': mat[j,7]+=row.anticipacion_h; mat[j,8]+=1
    for row in e.itertuples():
     j=keypos[row.bloque,row.mes_inicio]; mat[j,3]+=row.estado=='anticipado'; mat[j,4]+=row.estado=='omitido'; mat[j,5]+=row.estado!='sin_oportunidad'
    counts=d.groupby([d.bloque,d.emision.dt.strftime('%Y-%m')]).size()
    for k,n in counts.items(): mat[keypos[k],9]=n
    point=quantities(mat.sum(axis=0)); arr=[quantities(np.array([cnt[k] for k in keys])@mat) for cnt in samples]
    points.append(dict(horizonte_h=h,politica=policy,modelo=arm,**point))
    for metric in notice_metrics: est[metric][arm]=point[metric]; reps[metric][arm]=[r[metric] for r in arr]
   for metric in notice_metrics: storemetric(h,policy,metric,est[metric],reps[metric])
 save(pd.DataFrame(boot),'intervalos_pareados'); save(pd.DataFrame(points),'avisos_agregados')
 # Exact per-partition contrasts; avoid comparing different supports.
 hm=pd.read_csv(OUT/'tablas/metricas_horarias.csv'); paired=[]
 for table,metrics in [(hm,['AP','Brier']),(am,notice_metrics+['anticipacion_mediana_h'])]:
  groups=['horizonte_h','bloque']+(['politica'] if 'politica' in table else [])
  for key,z in table[table.epoca.eq('ALL')].groupby(groups):
   z=z.set_index('modelo')
   for new,old in CONTRASTS:
    for metric in metrics: paired.append(dict(zip(groups,key),contraste=new+'-'+old,metrica=metric,delta=z.loc[new,metric]-z.loc[old,metric]))
 save(pd.DataFrame(paired),'diferencias_por_particion')


def verify(x,p,pe,f,ds,pred,cat):
 checks={}
 def check(name,v):
  assert v,name
  checks[name]=True
 for cutoff in [pd.Timestamp('2013-01-03 12:00'),pd.Timestamp('2019-08-13 01:00'),pd.Timestamp('2023-12-30 12:00')]:
  xx=x.copy(); pp=p.copy(); zz=pe.copy(); xx.loc[xx.index>cutoff]=123.456; pp.loc[pp.index>cutoff]=876.543; zz.loc[zz.index>cutoff]=234.567
  pd.testing.assert_frame_equal(f.loc[:cutoff],allfeatures(xx,pp,zz).loc[:cutoff]); checks[f'invariancia_futuro_{cutoff}']=True
 for (h,block,role),d in ds.items():
  ty,vs,ve=next((ty,vs,ve) for bb,ty,vs,ve in b.BLOCKS if bb==block)
  lo=b.START if role=='entrenamiento' else pd.Timestamp(f'{vs}-01-01'); hi=pd.Timestamp(f'{ty if role=="entrenamiento" else ve}-12-31 23:00')
  check(f'fronteras_{h}_{block}_{role}',((d.index-pd.Timedelta(hours=6)>=lo)&(d.index+pd.Timedelta(hours=h)<=hi)).all())
  for r in cat.itertuples():
   if r.inicio<lo<=r.fin or r.inicio<=hi<r.fin: check(f'purga_{h}_{block}_{role}_{r.id_tramo}',not ((d.index-pd.Timedelta(hours=6)<=r.fin)&(d.index+pd.Timedelta(hours=h)>=r.inicio)).any())
  for t,row in d.iloc[np.linspace(0,len(d)-1,3,dtype=int)].iterrows():
   # Independent local seven-hour construction, without rolling/shift implementations.
   win=x.loc[t-pd.Timedelta(hours=6):t]; wpe=pe.loc[win.index]
   scalars={c:win[c] for c in b.MAIN[:3]}; scalars['sin_D']=np.sin(np.deg2rad(win.direccion_2m)); scalars['cos_D']=np.cos(np.deg2rad(win.direccion_2m))
   scalars['INIA_presion']=p.loc[win.index]
   for c in ['temperatura','humedad','viento','presion']: scalars['LAG_'+c]=wpe[c]
   scalars['LAG_sin_D']=np.sin(np.deg2rad(wpe.direccion)); scalars['LAG_cos_D']=np.cos(np.deg2rad(wpe.direccion))
   vals={}
   for c,s in scalars.items():
    vals[c]=s.iloc[-1]
    for lag in [1,3]: vals[f'{c}_lag{lag}']=s.iloc[-1-lag]; vals[f'{c}_delta{lag}']=s.iloc[-1]-s.iloc[-1-lag]
    vals[f'{c}_media_previa6']=s.iloc[:6].mean()
   vals['V_max_previo6']=win.viento_2m.iloc[:6].max(); vals['LAG_V_max_previo6']=wpe.viento.iloc[:6].max()
   for name,angle in [('hora',2*np.pi*t.hour/24),('ano',2*np.pi*(t.dayofyear-1)/365.25)]: vals['sin_'+name]=np.sin(angle); vals['cos_'+name]=np.cos(angle)
   check(f'features_locales_{h}_{block}_{role}_{t}',np.allclose([vals[c] for c in f],row[list(f)].astype(float),rtol=1e-9,atol=1e-8))
 check('probabilidades_finitas',np.isfinite(pred.probabilidad).all() and pred.probabilidad.between(0,1).all())
 check('unicidad_predicciones',not pred.duplicated(['emision','horizonte_h','bloque','modelo']).any())
 for (h,block),d in pred.groupby(['horizonte_h','bloque']):
  check(f'soporte_exacto_{h}_{block}',d.groupby('emision').modelo.nunique().eq(6).all() and d.groupby('emision').objetivo.nunique().eq(1).all())
  check(f'denominador_{h}_{block}',len(d)==6*len(ds[h,block,'validacion']))
 for file in ['metricas_horarias','metricas_avisos']:
  z=pd.read_csv(OUT/f'tablas/{file}.csv')
  check(f'denominadores_{file}',z.groupby(['horizonte_h','bloque','epoca']+(['politica'] if 'politica' in z else [])).n_emisiones.nunique().eq(1).all())
  if file=='metricas_avisos':
   check('conteos_eventos',z.inicios_evaluables.eq(z.inicios_anticipados+z.inicios_omitidos).all())
   check('conteos_grupos',z.grupos_avisos.eq(z.aciertos_avisos+z.falsas_alarmas+z.redundantes).all())
 cal=pd.read_csv(OUT/'tablas/calibracion.csv'); hm=pd.read_csv(OUT/'tablas/metricas_horarias.csv')
 cs=cal.groupby(['horizonte_h','bloque','modelo','epoca'])[['n','positivos']].sum().sort_index(); hs=hm.set_index(['horizonte_h','bloque','modelo','epoca']).sort_index()
 check('calibracion_denominadores',np.array_equal(cs.n,hs.n_emisiones) and np.array_equal(cs.positivos,hs.positivos))
 js('verificacion.json',{'resultado':'conforme','n_comprobaciones':len(checks),'comprobaciones':checks})

def diagnostics(x,p,pe,ds):
 full=pd.concat([x,p.rename('presion_INIA'),pe.add_prefix('LAG_')],axis=1)
 oldfull=full.drop(columns='LAG_presion')
 pressure=pe.presion.notna()
 win=lambda valid: valid.rolling(7,min_periods=7).sum().eq(7)
 oldwin=win(oldfull.notna().all(axis=1)); newwin=win(full.notna().all(axis=1)); pwin=win(pressure)
 masks=full.notna().add_suffix('_valida').astype(int)
 masks['LAGELPA_ventana7_valida']=pwin.astype(int); masks['entrada_sin_presion_valida']=oldwin.astype(int); masks['entrada_con_presion_valida']=newwin.astype(int)
 save(masks.rename_axis('emision').reset_index(),'mascaras_horarias')
 def ids(d): return {cid for val in d.loc[d.y.eq(1),'id_inicio_objetivo'] for cid in val.split('|') if cid}
 def intervals(v,lo,hi):
  v=v.loc[lo:hi]; changes=np.diff(np.r_[False,v.to_numpy(),False].astype(int)); left=np.flatnonzero(changes==1); right=np.flatnonzero(changes==-1)-1
  return [{'inicio':v.index[a],'fin':v.index[z],'horas':int(z-a+1)} for a,z in zip(left,right)]
 ranges=[]; summaries=[]
 scopes=[('global','desarrollo',b.START,b.END)]
 for block,ty,vs,ve in b.BLOCKS:
  scopes += [(block,'entrenamiento',b.START,pd.Timestamp(f'{ty}-12-31 23:00')),(block,'validacion',pd.Timestamp(f'{vs}-01-01'),pd.Timestamp(f'{ve}-12-31 23:00'))]
 for block,role,lo,hi in scopes:
  for year in range(lo.year,hi.year+1):
   yl=max(lo,pd.Timestamp(f'{year}-01-01')); yh=min(hi,pd.Timestamp(f'{year}-12-31 23:00'))
   for status,valid in [('utilizable',pressure),('hueco',~pressure)]:
    for row in intervals(valid,yl,yh): ranges.append(dict(bloque=block,rol=role,ano=year,estado=status,**row))
   for h in [1,3]:
    common=dict(horizonte_h=h,bloque=block,rol=role,ano=year,horas_calendario=len(pressure.loc[yl:yh]),presion_horas_utilizables=int(pressure.loc[yl:yh].sum()),presion_horas_excluidas=int((~pressure.loc[yl:yh]).sum()),ventanas_presion_incompletas=int((~pwin.loc[yl:yh]).sum()),entradas_sin_presion=int(oldwin.loc[yl:yh].sum()),entradas_con_presion=int(newwin.loc[yl:yh].sum()),entradas_perdidas_por_presion=int((oldwin&~newwin).loc[yl:yh].sum()))
    if block!='global':
     d=ds[h,block,role]; d=d.loc[(d.index>=yl)&(d.index<=yh)]
     a=d.loc[oldwin.reindex(d.index)]; z=d.loc[newwin.reindex(d.index)]; lost=a.loc[~a.index.isin(z.index)]
     common.update(elegibles_sin_presion=len(a),elegibles_con_presion=len(z),ventanas_elegibles_perdidas=len(lost),positivos_sin_presion=int(a.y.sum()),positivos_con_presion=int(z.y.sum()),positivos_perdidos=int(lost.y.sum()),inicios_sin_presion=len(ids(a)),inicios_con_presion=len(ids(z)),inicios_afectados=len(ids(lost)),inicios_completamente_perdidos=len(ids(a)-ids(z)))
    summaries.append(common)
 save(pd.DataFrame(ranges),'intervalos_presion_por_ano_particion'); save(pd.DataFrame(summaries),'presion_soporte_por_ano_particion')
 # Full partition counts: onset opportunity can span adjacent calendar years.
 compare=[]
 previous=pd.read_csv(ROOT/'experimento_laguna_sin_presion_inicio_v1/tablas/ejemplos_comunes.csv',parse_dates=['emision']).fillna({'id_inicio_objetivo':''})
 for (h,block,role),d in ds.items():
  a=d.loc[oldwin.reindex(d.index)]; z=d.loc[newwin.reindex(d.index)]; lost=a.loc[~a.index.isin(z.index)]
  prev=previous[(previous.horizonte_h==h)&previous.bloque.eq(block)&previous.rol.eq(role)]
  assert np.array_equal(a.index,prev.emision) and np.array_equal(a.y,prev.y) and np.array_equal(a.id_inicio_objetivo,prev.id_inicio_objetivo)
  compare.append(dict(horizonte_h=h,bloque=block,rol=role,elegibles_sin_presion=len(a),elegibles_con_presion=len(z),ventanas_perdidas=len(lost),positivos_sin_presion=int(a.y.sum()),positivos_con_presion=int(z.y.sum()),positivos_perdidos=int(lost.y.sum()),inicios_sin_presion=len(ids(a)),inicios_con_presion=len(ids(z)),inicios_afectados=len(ids(lost)),inicios_completamente_perdidos=len(ids(a)-ids(z)),soporte_anterior_reconstruido=True))
 save(pd.DataFrame(compare),'comparacion_soporte_anterior')

def main():
 if (OUT/'registro_preentrenamiento.json').exists(): raise SystemExit('Esta ejecución ya está registrada; usar --reproducir DIRECTORIO_NUEVO')
 # Explicit allowed documents and code: no raw downloads or reserved-period observations.
 docs=[ROOT/'linea_base_inicio_v0'/n for n in ['protocolo.md','ejecutar.py','verificar.py','correcciones_implementacion.md']]
 docs += [ROOT/'experimento_pisco_inicio_v1'/n for n in ['protocolo.md','ejecutar.py','ejecutar_registrado_v1.py','correcciones_implementacion.md']]
 docs += [ROOT/'experimento_laguna_sin_presion_inicio_v1'/n for n in ['protocolo.md','ejecutar.py','informe.md','verificar.py','auditar_metodo.py','tablas/ejemplos_comunes.csv']]
 docs += [ROOT/'estaciones_complementarias/auditoria_2013_2023'/n for n in ['hallazgos.md','informe.md','auditar.py']]
 docs += [Path(__file__).parent/n for n in ['configuracion_experimento.json','verificar.py','verificar_avisos.py','verificar_huecos.py','verificar_calidad.py','verificar_presion.py','informar.py','comparar_reproduccion.py','revision_previa.md','conservacion_previa.json','cerrar.py']]
 manifest=[{'archivo':str(q.relative_to(b.ROOT)),'sha256_antes':b.digest(q)} for q in docs]
 b.OUT=ROOT/'linea_base_inicio_v0'  # ingest solo lee; sus rutas se basan en OUT.parent
 x,state,cat,entries=b.ingest(); manifest+=entries
 b.OUT=OUT
 p,pe=load_extra(manifest); f=allfeatures(x,p,pe)
 base=list(b.features(x)); own=[c for c in f if c.startswith('INIA_')]; lag=[c for c in f if c.startswith('LAG_') and not c.startswith('LAG_presion')]; pressure=[c for c in f if c.startswith('LAG_presion')]
 cols={'A':base,'B':base+own,'C':base+lag,'D':base+own+lag,'E':base+lag+pressure,'F':base+own+lag+pressure}
 assert [len(cols[a]) for a in 'ABCDEF']==[35,41,66,72,72,78]; assert len(f.columns)==len(set(f.columns))
 js('predictores.json',cols)
 _,ds=b.eligibility(x,state,cat); diagnostics(x,p,pe,ds); ds=support(ds,f,p,pe)
 protocol_hash=b.digest(OUT/'protocolo.md'); js('manifiesto_previo.json',manifest)
 js('registro_preentrenamiento.json',{'registrado_utc':pd.Timestamp.now(tz='UTC').isoformat(),'protocolo_sha256':protocol_hash,'predictores_sha256':b.digest(OUT/'predictores.json'),'codigo_sha256':b.digest(Path(__file__)),'manifiesto_previo_sha256':b.digest(OUT/'manifiesto_previo.json'),'tablas_previas_sha256':{q.name:b.digest(q) for q in sorted((OUT/'tablas').glob('*.csv'))},'semilla_bootstrap':20132023,'replicas_bootstrap':300,'estado':'antes del primer ajuste'})
 predictions=[]
 for h in [1,3]:
  for block,_,_,_ in b.BLOCKS:
   train=ds[h,block,'entrenamiento']; val=ds[h,block,'validacion']
   for arm in 'ABCDEF':
    b.OUT=OUT/'ajustes'/arm
    for d in ['tablas','ajustes']: (b.OUT/d).mkdir(parents=True,exist_ok=True)
    print(f'Ajuste {arm} {block} {h}h train={len(train)} val={len(val)} positivos={val.y.sum()}',flush=True)
    probs,prior=b.fit_predict(train,val,cols[arm],h,block)
    predictions.append(pd.DataFrame({'emision':val.index,'horizonte_h':h,'objetivo':val.y.to_numpy(),'modelo':arm,'bloque':block,'probabilidad':probs['logistica'],'id_inicio_objetivo':val.id_inicio_objetivo.to_numpy(),'regla':val.regla.to_numpy(),'p_constante_train':prior,'p_frecuencia':probs['frecuencia'],'epoca':b.season(val.index),'predictor_desde':val.index-pd.Timedelta(hours=6),'predictor_hasta':val.index,'objetivo_hasta':val.index+pd.Timedelta(hours=h)}))
 b.OUT=OUT
 pred=pd.concat(predictions,ignore_index=True); pred.to_csv(OUT/'predicciones_validacion.csv',index=False,float_format='%.12g')
 b.hourly(pred)
 aggregated_cal=[]
 edges=np.array([0,.001,.003,.01,.03,.1,.3,.5,1.0000001])
 for (h,arm),g in pred.groupby(['horizonte_h','modelo']):
  bins=np.clip(np.searchsorted(edges,g.probabilidad,side='right')-1,0,len(edges)-2)
  for i in range(len(edges)-1):
   z=g.iloc[np.flatnonzero(bins==i)]
   aggregated_cal.append({'horizonte_h':h,'modelo':arm,'limite_inf':edges[i],'limite_sup':min(edges[i+1],1),'n':len(z),'positivos':int(z.objetivo.sum()),'p_media':z.probabilidad.mean(),'frecuencia_observada':z.objetivo.mean()})
 save(pd.DataFrame(aggregated_cal),'calibracion_agregada')
 a,e,am=b.notices(pred,cat); bootstrap(pred,a,e)
 verify(x,p,pe,f,ds,pred,cat)
 for row in manifest:
  row['sha256_despues']=b.digest(b.ROOT/row['archivo']); assert row['sha256_antes']==row['sha256_despues']
 save(pd.DataFrame(manifest),'manifiesto_fuentes'); assert b.digest(OUT/'protocolo.md')==protocol_hash
 js('comprobaciones.json',{'fuentes_inmutables':True,'protocolo_inmutable':True,'periodo':['2013-01-01','2023-12-31 23:00'],'sin_red':True,'catalogo_tramos':len(cat),'catalogo_horas':int(state.eq(1).sum()),'inicios_conocidos':int(cat.inicio_conocido.sum()),'predicciones':len(pred),'versiones':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'scipy':b.scipy.__version__,'matplotlib':b.matplotlib.__version__}})
 (OUT/'requirements.txt').write_text('\n'.join(f'{k}=={v}' for k,v in json.loads((OUT/'comprobaciones.json').read_text())['versiones'].items() if k!='python')+'\n')
 print('Finalizado; fuentes intactas y controles conformes.',flush=True)
if __name__=='__main__':
 if len(sys.argv)>1:
  assert len(sys.argv)==3 and sys.argv[1]=='--reproducir'
  import shutil
  dest=Path(sys.argv[2]).resolve(); assert not dest.exists(); dest.mkdir(parents=True)
  for n in ['protocolo.md','ejecutar.py','informar.py','verificar.py','configuracion_experimento.json','comparar_reproduccion.py','revision_previa.md','verificar_avisos.py','verificar_huecos.py','verificar_calidad.py','verificar_presion.py','conservacion_previa.json','cerrar.py']:
   if (OUT/n).exists(): shutil.copy2(OUT/n,dest/n)
  OUT=dest; b.OUT=OUT
  for d in ['tablas','ajustes','graficos']: (OUT/d).mkdir()
 main()
