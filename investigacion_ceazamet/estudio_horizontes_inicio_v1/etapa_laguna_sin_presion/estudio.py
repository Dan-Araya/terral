#!/usr/bin/env python3
"""Estudio secuencial local. No red. Ver README.md y protocolo.md."""
import os,sys
os.environ['OPENBLAS_NUM_THREADS']='1'; os.environ['OMP_NUM_THREADS']='1'
os.environ['MPLBACKEND']='Agg'; os.environ['MPLCONFIGDIR']='/tmp/horizontes-mpl'; sys.modules['numexpr']=None; sys.dont_write_bytecode=True
from pathlib import Path
import json,hashlib,argparse,platform,shutil
import numpy as np
import pandas as pd
import heredado as b
import sensores as s
BASE=Path(__file__).resolve().parent; ROOT=BASE.parent.parent
CONFIG=json.loads((BASE/'configuracion.json').read_text()); H=CONFIG['horizontes']; MONTH=365.25*24/12
ETAPA='laguna_sin_presion'
OUT=BASE.parent/'resultados'/ETAPA
s.STATION='la_laguna_elqui'
s.EXPECTED={'LAGELTA':('temperatura',1.5),'LAGELHR':('humedad',1.5),'LAGELVV10':('viento',10.),'LAGELDV10':('direccion',10.)}
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def js(p,obj):
 p=Path(p); p.parent.mkdir(parents=True,exist_ok=True); tmp=p.with_suffix(p.suffix+'.tmp'); tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False,default=str,allow_nan=False)+'\n'); tmp.replace(p)
def save(d,p):
 p=Path(p); p.parent.mkdir(parents=True,exist_ok=True); d.to_csv(p,index=False,float_format='%.17g')
def sources():
 paths=[ROOT/f'historico_inia/derivados/observaciones_{y}.csv' for y in range(2013,2024)]
 paths += [ROOT/'catalogo_provisional_v0/catalogo_referencia.csv',ROOT/'estaciones_complementarias/configuracion.json',ROOT/f'estaciones_complementarias/{s.STATION}/derivados/horarias.csv',ROOT/f'estaciones_complementarias/{s.STATION}/derivados/integridad.json',ROOT/f'estaciones_complementarias/{s.STATION}/metadatos.json']
 for name in ['experimento_pisco_inicio_v1','experimento_huanta_inicio_v1','experimento_laguna_sin_presion_inicio_v1','experimento_laguna_con_presion_inicio_v1']:
  paths.extend(p for p in (ROOT/name).rglob('*') if p.is_file() and p.suffix not in ['.pyc','.png'])
 paths.extend(p for p in (ROOT/'estaciones_complementarias/auditoria_2013_2023').glob('*') if p.is_file() and p.suffix in ['.md','.json','.py'])
 paths.extend(p for p in BASE.iterdir() if p.is_file() and p.suffix in ['.py','.json','.md'])
 paths.extend(p for p in BASE.rglob('*') if p.is_file() and p.suffix in ['.py','.md','.json'] and '__pycache__' not in str(p))
 return {str(p):digest(p) for p in sorted(set(paths))}
def setup():
 OUT.mkdir(parents=True,exist_ok=True); (OUT/'tablas').mkdir(exist_ok=True); b.OUT=OUT; s.b.OUT=OUT

def load():
 b.OUT=ROOT/'linea_base_inicio_v0'; x,state,cat,_=b.ingest(); b.OUT=OUT
 p,pe=s.load_extra([])
 meta=json.loads((ROOT/f'estaciones_complementarias/{s.STATION}/metadatos.json').read_text())
 for sid,(v,h) in s.EXPECTED.items():
  q=next(z for z in meta['sensors'] if z['code']==sid); assert (q['variable'],q['height_m'])==(v,h)
 f=s.allfeatures(x,p,pe)
 cols={'A':list(b.features(x)),'B':[c for c in f if not c.startswith('LAG_')],'C':[c for c in f if not c.startswith('INIA_')],'D':list(f)}
 assert [len(cols[a]) for a in 'ABCD']==([35,41,72,78] if CONFIG['etapas'][ETAPA]['presion_complementaria'] else [35,41,66,72])
 return x,state,cat,f,cols

def labels(state,cat):
 known=pd.Series('',index=b.IDX); uncertain=pd.Series(False,index=b.IDX)
 for r in cat.itertuples():
  if r.inicio_conocido: known.loc[r.inicio]=r.id_tramo
  else: uncertain.loc[r.inicio]=True
 yy={}; ids={}; future=pd.Series(False,index=b.IDX)
 for h in range(1,25):
  future |= state.shift(-h).eq(-1)|uncertain.shift(-h,fill_value=False)
  if h in H:
   z=[known.shift(-k,fill_value='') for k in range(1,h+1)]
   ids[h]=pd.Series(['|'.join(v for v in row if v) for row in zip(*z)],index=b.IDX)
   yy[h]=ids[h].ne('').astype(int)
 return yy,ids,future

def dataset(f,state,cat,yy,ids,future,lo,hi,h,common=True):
 ix=f.index; lo=pd.Timestamp(lo); hi=pd.Timestamp(hi)
 hist=f.notna().all(axis=1) if common else f[list(b.features_cache)].notna().all(axis=1)
 # f finite alone is insufficient for direction cancellation or gaps; raw completeness is applied in prepare.
 hist &= COMPLETE if common else BASIC
 maxh=24 if common else h
 unk=future if common else pd.concat([state.shift(-k).eq(-1)|UNCERTAIN.shift(-k,fill_value=False) for k in range(1,h+1)],axis=1).any(axis=1)
 ok=state.eq(0)&hist&~unk&(ix-pd.Timedelta(hours=6)>=lo)&(ix+pd.Timedelta(hours=maxh)<=hi)
 for r in cat.itertuples():
  if r.inicio<lo<=r.fin or r.inicio<=hi<r.fin:
   ok &= ~((ix-pd.Timedelta(hours=6)<=r.fin)&(ix+pd.Timedelta(hours=maxh)>=r.inicio))
 d=f.loc[ok].copy(); d['y']=yy[h].loc[ok]; d['id_inicio_objetivo']=ids[h].loc[ok]; d['regla']=0
 return d

def prepare():
 global COMPLETE,BASIC,UNCERTAIN
 setup(); x,state,cat,f,cols=load(); b.features_cache=cols['A']
 # Seven actual marks for every required source, including La Laguna sin presión/INIA pressure.
 scalar=['temperatura','humedad','viento_2m','sin_D','cos_D','INIA_presion','LAG_temperatura','LAG_humedad','LAG_viento','LAG_sin_D','LAG_cos_D']
 scalar=[c for c in scalar if c in f]
 COMPLETE=f[scalar].notna().all(axis=1).rolling(7,min_periods=7).sum().eq(7)
 BASIC=x.notna().all(axis=1).rolling(7,min_periods=7).sum().eq(7)
 UNCERTAIN=pd.Series(False,index=b.IDX)
 for r in cat[~cat.inicio_conocido].itertuples(): UNCERTAIN.loc[r.inicio]=True
 yy,ids,future=labels(state,cat); datasets={}; rows=[]; losses=[]
 for block,ty,vs,ve in b.BLOCKS:
  for role,lo,hi in [('train','2013-01-01',f'{ty}-12-31 23:00'),('val',f'{vs}-01-01',f'{ve}-12-31 23:00')]:
   for h in H:
    d=dataset(f,state,cat,yy,ids,future,lo,hi,h); datasets[block,role,h]=d
    old=dataset(f,state,cat,yy,ids,future,lo,hi,h,False)
    # Original La Laguna sin presión support (all inputs, future only h), reconstructed without old metrics.
    oldp=old.loc[COMPLETE.reindex(old.index)]
    getids=lambda z:{v for a in z.id_inicio_objetivo for v in a.split('|') if v}
    rows.append(dict(bloque=block,rol=role,horizonte_h=h,n=len(d),positivos=int(d.y.sum()),prevalencia=d.y.mean(),inicios=len(getids(d))))
    losses.append(dict(bloque=block,rol=role,horizonte_h=h,base_horas=len(old),laguna_sin_presion_original_horas=len(oldp),comun24_horas=len(d),perdida_base=len(old)-len(d),perdida_vs_laguna_sin_presion=len(oldp)-len(d),positivos_base=int(old.y.sum()),positivos_original=int(oldp.y.sum()),positivos_comun=int(d.y.sum()),inicios_base=len(getids(old)),inicios_original=len(getids(oldp)),inicios_comun=len(getids(d)),inicios_perdidos_vs_laguna_sin_presion=len(getids(oldp)-getids(d)),inicios_afectados_vs_laguna_sin_presion=len(getids(oldp.loc[~oldp.index.isin(d.index)]))))
    save(pd.DataFrame({'emision':d.index,'objetivo':d.y,'ids':d.id_inicio_objetivo}),OUT/'soportes'/f'{block}_{role}_{h}.csv')
  for role in ['train','val']:
   for h in H: assert datasets[block,role,h].index.equals(datasets[block,role,24].index)
 save(pd.DataFrame(rows),OUT/'tablas/particiones.csv'); save(pd.DataFrame(losses),OUT/'tablas/perdidas_soporte.csv'); js(OUT/'predictores.json',cols)
 save(pd.DataFrame({'emision':b.IDX,'estado':state,'historia_basica':BASIC,'historia_completa':COMPLETE,'futuro24_desconocido':future}),OUT/'tablas/mascaras.csv')
 return x,state,cat,f,cols,yy,ids,future,datasets

def notice(d,cat,h,threshold,block,arm,policy):
 """Misma agrupación/uno a uno original, independiente del umbral elegido."""
 d=d.sort_values('emision'); eligible={v for ids in d.id_inicio_objetivo for v in ids.split('|') if v}; on=d[d.probabilidad.ge(threshold)]
 used={}; alerts=[]
 starts=cat.set_index('id_tramo').inicio.to_dict()
 for gid,g in on.groupby(on.emision.diff().ne(pd.Timedelta(hours=1)).cumsum()):
  cand=sorted({v for ids in g.id_inicio_objetivo for v in ids.split('|') if v},key=starts.get)
  match=next((v for v in cand if v not in used),''); lead=np.nan; anticip=pd.NaT
  if match:
   anticip=g.loc[g.id_inicio_objetivo.map(lambda z:match in z.split('|')),'emision'].iloc[0]; lead=(starts[match]-anticip)/pd.Timedelta(hours=1); used[match]=(int(gid),lead)
  alerts.append(dict(id_aviso=int(gid),primera_emision=g.emision.iloc[0],ultima_emision=g.emision.iloc[-1],n_emisiones=len(g),estado='acierto' if match else ('redundante' if cand else 'falsa_alarma'),id_inicio=match,candidatos='|'.join(cand),primera_emision_anticipadora=anticip,anticipacion_h=lead,mes=g.emision.iloc[0].strftime('%Y-%m')))
 events=[]
 for r in cat[cat.inicio.dt.year.between(int(block[:4]),int(block[-4:]))].itertuples():
  events.append(dict(id_inicio=r.id_tramo,inicio=r.inicio,mes=r.inicio.strftime('%Y-%m'),estado='sin_oportunidad' if r.id_tramo not in eligible else ('anticipado' if r.id_tramo in used else 'omitido'),id_aviso=used.get(r.id_tramo,('',np.nan))[0],anticipacion_h=used.get(r.id_tramo,('',np.nan))[1]))
 a=pd.DataFrame(alerts,columns=['id_aviso','primera_emision','ultima_emision','n_emisiones','estado','id_inicio','candidatos','primera_emision_anticipadora','anticipacion_h','mes']); e=pd.DataFrame(events)
 ne=len(eligible); det=len(used); fp=int(a.estado.eq('falsa_alarma').sum()); months=len(d)/MONTH
 m=dict(n_emisiones=len(d),meses_equivalentes=months,inicios_evaluables=ne,inicios_anticipados=det,inicios_omitidos=ne-det,inicios_sin_oportunidad=int(e.estado.eq('sin_oportunidad').sum()),recall_inicios=det/ne if ne else np.nan,grupos_avisos=len(a),falsas_alarmas=fp,redundantes=int(a.estado.eq('redundante').sum()),aciertos_avisos=det,falsas_alarmas_por_mes=fp/months if months else np.nan,horas_bajo_aviso=len(on),proporcion_tiempo_aviso=len(on)/len(d),anticipacion_media_h=a.anticipacion_h.mean(),anticipacion_mediana_h=a.anticipacion_h.median())
 for k in H:
  if k<=h:
   m[f'detectados_ge_{k}h']=int(e.anticipacion_h.ge(k).sum()); m[f'fraccion_eventos_ge_{k}h']=m[f'detectados_ge_{k}h']/ne if ne else np.nan
 maxlead=dict.fromkeys(eligible,0.)
 for row in d[d.objetivo.eq(1)].itertuples():
  for cid in row.id_inicio_objetivo.split('|'):
   if cid: maxlead[cid]=max(maxlead[cid],(starts[cid]-row.emision)/pd.Timedelta(hours=1))
 for k in H:
  if k<=h: m[f'oportunidad_ge_{k}h']=sum(v>=k for v in maxlead.values())
 for z in [a,e]:
  z['bloque']=block; z['modelo']=arm; z['horizonte_h']=h; z['politica']=policy
 return a,e,m

def fit(train,val,cols,h,tag,dest):
 b.OUT=dest
 for n in ['tablas','ajustes']: (dest/n).mkdir(parents=True,exist_ok=True)
 probs,prior=b.fit_predict(train,val,cols,h,tag); b.OUT=OUT
 return pd.DataFrame({'emision':val.index,'objetivo':val.y.to_numpy(),'id_inicio_objetivo':val.id_inicio_objetivo.to_numpy(),'probabilidad':probs['logistica'],'p_constante_train':prior,'p_frecuencia':probs['frecuencia'],'predictor_desde':val.index-pd.Timedelta(hours=6),'predictor_hasta':val.index,'objetivo_hasta':val.index+pd.Timedelta(hours=h)})

def unit_valid(p,signature):
 try:
  m=json.loads((p/'estado.json').read_text())
  return m['estado']=='verificado' and m['firma']==signature and all((p/n).is_file() and digest(p/n)==sha for n,sha in m['archivos'].items())
 except (OSError,KeyError,ValueError): return False

def run():
 setup(); initial=sources(); signature=hashlib.sha256(json.dumps(initial,sort_keys=True).encode()).hexdigest()
 reg=OUT/'registro_preentrenamiento.json'
 if reg.exists(): assert json.loads(reg.read_text())['firma']==signature,'Código/fuentes cambiados: crear directorio nuevo o documentar corrección'
 else: js(reg,{'fecha_utc':pd.Timestamp.now(tz='UTC').isoformat(),'firma':signature,'fuentes':initial,'versiones':{'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'scipy':b.scipy.__version__},'estado':'antes del primer ajuste'})
 x,state,cat,f,cols,yy,ids,future,ds=prepare()
 for block,ty,vs,ve in b.BLOCKS:
  for h in H:
   for arm in 'ABCD':
    path=OUT/'unidades'/block/f'{h}h'/arm
    if unit_valid(path,signature): print('Omitida verificada',block,h,arm,flush=True); continue
    if path.exists(): shutil.rmtree(path)
    path.mkdir(parents=True); js(path/'estado.json',{'estado':'ejecutando','firma':signature})
    print('Ajustando',block,h,arm,flush=True)
    oo=[]; foldmeta=[]; inner_metrics=[]
    for vy in [ty-1,ty]:
     tr=dataset(f,state,cat,yy,ids,future,'2013-01-01',f'{vy-1}-12-31 23:00',h)
     va=dataset(f,state,cat,yy,ids,future,f'{vy}-01-01',f'{vy}-12-31 23:00',h)
     q=fit(tr,va,cols[arm],h,str(vy),path/'interno'/str(vy)); q['fold']=vy; oo.append(q)
     foldmeta.append(dict(fold=vy,train_hasta=f'{vy-1}-12-31 23:00',validacion_desde=f'{vy}-01-01',n_train=len(tr),n_oof=len(va)))
    oof=pd.concat(oo,ignore_index=True); save(oof,path/'oof.csv'); js(path/'folds.json',foldmeta)
    for threshold in CONFIG['umbrales']:
     aa=[]; ee=[]; mm=[]
     for vy,d in oof.groupby('fold'):
      a,e,m=notice(d,cat,h,threshold,str(vy),arm,f'p>={threshold:g}'); aa.append(a); ee.append(e); mm.append(m)
     ne=sum(m['inicios_evaluables'] for m in mm); det=sum(m['inicios_anticipados'] for m in mm); fp=sum(m['falsas_alarmas'] for m in mm)
     inner_metrics.append(dict(umbral=threshold,n_oof=len(oof),meses=len(oof)/MONTH,eventos=ne,detectados=det,falsas=fp,tasa=fp/(len(oof)/MONTH),horas_aviso=sum(m['horas_bajo_aviso'] for m in mm)))
    im=pd.DataFrame(inner_metrics); save(im,path/'evaluacion_interna.csv'); policies=[]
    for budget in CONFIG['presupuestos']:
     feasible=im[(im.tasa<=budget)&(im.meses>=12)&(im.eventos>=10)]
     chosen=None if feasible.empty else feasible.sort_values(['detectados','tasa','horas_aviso','umbral'],ascending=[False,True,True,False]).iloc[0]
     policies.append(dict(presupuesto=budget,estado='sin_soporte_o_no_factible' if chosen is None else 'congelada',umbral=None if chosen is None else float(chosen.umbral),tasa_interna=None if chosen is None else float(chosen.tasa),eventos_internos=int(im.eventos.iloc[0])))
    js(path/'politicas_congeladas.json',policies)
    pred=fit(ds[block,'train',h],ds[block,'val',h],cols[arm],h,block,path/'externo'); pred['bloque']=block; pred['modelo']=arm; pred['horizonte_h']=h
    assert len(pred)==len(ds[block,'val',h]) and np.isfinite(pred.probabilidad).all() and pred.probabilidad.between(0,1).all()
    assert not oof.emision.duplicated().any()
    for fold in foldmeta:
     assert pd.Timestamp(fold['train_hasta'])<pd.Timestamp(fold['validacion_desde'])<=pd.Timestamp(f'{ty}-12-31 23:00')
    assert len(pred)==len(ds[block,'val',h]) and pred.emision.min()>=pd.Timestamp(f'{vs}-01-01')
    co=pd.read_csv(path/'externo/ajustes'/f'logistica_{block}_{h}h.csv')
    meta=json.loads((path/'externo/ajustes'/f'logistica_{block}_{h}h.json').read_text())
    means=ds[block,'train',h][cols[arm]].to_numpy().mean(axis=0)
    assert np.allclose(co.media_train,means,rtol=1e-10,atol=1e-10)
    reconstructed=b.expit(meta['intercepto']+((ds[block,'val',h][cols[arm]].to_numpy()-co.media_train.to_numpy())/co.sd_train.to_numpy())@co.coef_estandarizado.to_numpy())
    assert np.allclose(reconstructed,pred.probabilidad,rtol=1e-9,atol=1e-10)
    save(pred,path/'predicciones.csv')
    files={str(p.relative_to(path)):digest(p) for p in sorted(path.rglob('*')) if p.is_file() and p.name!='estado.json'}
    js(path/'estado.json',{'estado':'verificado','firma':signature,'archivos':files,'verificacion_local':['convergencia','fronteras_fold','OOF_temporal','probabilidades_finitas','soporte_comun'],'bloque':block,'horizonte_h':h,'variante':arm})
 assert sources()==initial,'Fuentes o archivos previos alterados'
 js(OUT/'estado_etapa.json',{'estado':'ajustes_completos','etapa':ETAPA,'unidades':72,'otras_etapas':'pendientes_sin_entrenar','firma':signature})
 report(cat)

def bootstrap(pred,alerts,events,metrics):
 rng=np.random.default_rng(CONFIG['semilla']); keys=[(bl,str(m)) for bl,_,_,_ in b.BLOCKS for m in pd.period_range(bl[:4]+'-01',bl[-4:]+'-12',freq='M')]; pos={k:i for i,k in enumerate(keys)}
 W=np.zeros((300,72),int)
 for i in range(300):
  for j in range(3):
   for start in rng.integers(0,22,8): W[i,j*24+start:j*24+start+3]+=1
 save(pd.DataFrame([dict(replica=i,bloque=k[0],mes=k[1],multiplicidad=int(W[i,j])) for i in range(300) for j,k in enumerate(keys)]),OUT/'tablas/bootstrap_muestras.csv')
 rows=[]; repout=[]
 def store(h,policy,metric,values,points):
  for arm in list('ABCD')+['B-A','C-A','D-B']:
   if '-' in arm:
    a,c=arm.split('-'); v=values[a]-values[c]; point=points[a]-points[c]
   else: v=values[arm]; point=points[arm]
   good=v[np.isfinite(v)]; rows.append(dict(horizonte_h=h,politica=policy,metrica=metric,contraste=arm,estimacion=point,p025=np.quantile(good,.025) if len(good) else np.nan,p975=np.quantile(good,.975) if len(good) else np.nan,replicas_validas=len(good)))
   repout.extend(dict(horizonte_h=h,politica=policy,metrica=metric,contraste=arm,replica=i,valor=v[i]) for i in range(300))
 for h in H:
  vals={'AP':{},'Brier':{}}; pts={'AP':{},'Brier':{}}
  for arm in 'ABCD':
   d=pred[(pred.horizonte_h==h)&(pred.modelo==arm)]; y=d.objetivo.to_numpy(); p=d.probabilidad.to_numpy(); k=np.array([pos[bl,t.strftime('%Y-%m')] for bl,t in zip(d.bloque,d.emision)])
   order=np.argsort(-p,kind='stable'); ends=np.r_[np.flatnonzero(p[order][:-1]!=p[order][1:]),len(p)-1]
   aps=[]; br=[]
   for w in W:
    weights=w[k]; wy=weights[order]*y[order]; tp=np.cumsum(wy)[ends]; nn=np.cumsum(weights[order])[ends]; recall=tp/wy.sum() if wy.sum() else tp*np.nan
    precision=np.divide(tp,nn,out=np.zeros_like(tp,dtype=float),where=nn>0)
    aps.append(np.sum(np.diff(np.r_[0,recall])*precision)); br.append(np.dot(weights,(p-y)**2)/weights.sum())
   vals['AP'][arm]=np.array(aps); vals['Brier'][arm]=np.array(br); pts['AP'][arm]=b.pr(y,p)[0]; pts['Brier'][arm]=np.mean((p-y)**2)
  for metric in vals: store(h,'',metric,vals[metric],pts[metric])
  for policy in metrics.politica.unique():
   z=metrics[(metrics.horizonte_h==h)&(metrics.politica==policy)&(metrics.bloque=='AGREGADO')]
   if len(z)!=4: continue
   names=['grupos_avisos','falsas_alarmas','redundantes','inicios_anticipados','inicios_omitidos','inicios_evaluables','recall_inicios','falsas_alarmas_por_mes','horas_bajo_aviso','proporcion_tiempo_aviso','anticipacion_media_h']+[f'fraccion_eventos_ge_{k}h' for k in H if k<=h]
   values={n:{} for n in names}; points={n:{} for n in names}
   for arm in 'ABCD':
    a=alerts[(alerts.horizonte_h==h)&(alerts.modelo==arm)&(alerts.politica==policy)]; e=events[(events.horizonte_h==h)&(events.modelo==arm)&(events.politica==policy)]; d=pred[(pred.horizonte_h==h)&(pred.modelo==arm)]
    mat=np.zeros((72,10+len([k for k in H if k<=h])))
    for r in a.itertuples():
     j=pos[r.bloque,r.mes]; mat[j,0]+=1; mat[j,1]+=r.estado=='falsa_alarma'; mat[j,2]+=r.estado=='redundante'; mat[j,7]+=0
     if r.estado=='acierto': mat[j,8]+=r.anticipacion_h; mat[j,9]+=1
    for r in e.itertuples():
     j=pos[r.bloque,r.mes]; mat[j,3]+=r.estado=='anticipado'; mat[j,4]+=r.estado=='omitido'; mat[j,5]+=r.estado!='sin_oportunidad'
     for c,k in enumerate(k for k in H if k<=h): mat[j,10+c]+=r.anticipacion_h>=k
    for (bl,month),n in d.groupby([d.bloque,d.emision.dt.strftime('%Y-%m')]).size().items(): mat[pos[bl,month],6]=n
    for bl,dblock in d.groupby('bloque'):
     threshold=metrics[(metrics.horizonte_h==h)&metrics.modelo.eq(arm)&metrics.politica.eq(policy)&metrics.bloque.eq(bl)].umbral.iloc[0]
     on=dblock[dblock.probabilidad.ge(threshold)]
     for month,n in on.groupby(on.emision.dt.strftime('%Y-%m')).size().items(): mat[pos[bl,month],7]=n
    v=W@mat; div=lambda a,c:np.divide(a,c,out=np.full_like(a,np.nan,dtype=float),where=c!=0)
    arrays=[v[:,0],v[:,1],v[:,2],v[:,3],v[:,4],v[:,5],div(v[:,3],v[:,5]),div(v[:,1],v[:,6]/MONTH),v[:,7],div(v[:,7],v[:,6]),div(v[:,8],v[:,9])]+[div(v[:,10+c],v[:,5]) for c,k in enumerate(k for k in H if k<=h)]
    point=z[z.modelo.eq(arm)].iloc[0]
    for n,array in zip(names,arrays): values[n][arm]=array; points[n][arm]=point[n]
   for n in names: store(h,policy,n,values[n],points[n])
  print('Bootstrap',h,flush=True)
 save(pd.DataFrame(rows),OUT/'tablas/intervalos_pareados.csv'); save(pd.DataFrame(repout),OUT/'tablas/bootstrap_replicas.csv')

def report(cat=None):
 setup()
 if cat is None:
  _,_,cat,*_=prepare()
 preds=[]; policies=[]
 for bl,_,_,_ in b.BLOCKS:
  for h in H:
   for arm in 'ABCD':
    p=OUT/'unidades'/bl/f'{h}h'/arm
    pred=pd.read_csv(p/'predicciones.csv',parse_dates=['emision','predictor_desde','predictor_hasta','objetivo_hasta']).fillna({'id_inicio_objetivo':''}); preds.append(pred)
    for pol in json.loads((p/'politicas_congeladas.json').read_text()): policies.append(dict(bloque=bl,horizonte_h=h,modelo=arm,**pol))
 pred=pd.concat(preds,ignore_index=True); save(pred,OUT/'predicciones_validacion.csv'); save(pd.DataFrame(policies),OUT/'tablas/politicas.csv')
 prob=[]; calibration=[]; aa=[]; ee=[]; mm=[]
 for (h,bl,arm),d in pred.groupby(['horizonte_h','bloque','modelo']):
  choices=[(f'p>={t:g}',t,None) for t in CONFIG['umbrales']]
  choices += [(f'presupuesto_{z["presupuesto"]}',z['umbral'],z['presupuesto']) for z in policies if z['bloque']==bl and z['horizonte_h']==h and z['modelo']==arm and z['umbral'] is not None]
  for policy,threshold,budget in choices:
   a,e,m=notice(d,cat,h,threshold,bl,arm,policy); aa.append(a); ee.append(e); mm.append(dict(horizonte_h=h,bloque=bl,modelo=arm,politica=policy,umbral=threshold,presupuesto=budget,**m))
 def hourly(d,h,bl,arm):
  prob.append(dict(horizonte_h=h,bloque=bl,modelo=arm,n_emisiones=len(d),positivos=int(d.objetivo.sum()),prevalencia=d.objetivo.mean(),inicios=len({v for ids in d.id_inicio_objetivo for v in ids.split('|') if v}),AP=b.pr(d.objetivo,d.probabilidad)[0],Brier=np.mean((d.probabilidad-d.objetivo)**2),Brier_constante_train=np.mean((d.p_constante_train-d.objetivo)**2)))
  edges=[0,.001,.003,.01,.03,.1,.3,.5,1.0000001]; bins=np.clip(np.searchsorted(edges,d.probabilidad,side='right')-1,0,7)
  for k in range(8):
   z=d.iloc[np.flatnonzero(bins==k)]; calibration.append(dict(horizonte_h=h,bloque=bl,modelo=arm,limite_inf=edges[k],limite_sup=min(edges[k+1],1),n=len(z),positivos=int(z.objetivo.sum()),p_media=z.probabilidad.mean(),frecuencia=z.objetivo.mean()))
 for (h,bl,arm),d in pred.groupby(['horizonte_h','bloque','modelo']): hourly(d,h,bl,arm)
 for (h,arm),d in pred.groupby(['horizonte_h','modelo']): hourly(d,h,'AGREGADO',arm)
 a=pd.concat(aa,ignore_index=True); e=pd.concat(ee,ignore_index=True); m=pd.DataFrame(mm)
 for (h,arm,policy),z in m.groupby(['horizonte_h','modelo','politica']):
  if len(z)!=3: continue
  az=a[(a.horizonte_h==h)&a.modelo.eq(arm)&a.politica.eq(policy)]; ez=e[(e.horizonte_h==h)&e.modelo.eq(arm)&e.politica.eq(policy)]
  sums=['n_emisiones','meses_equivalentes','inicios_evaluables','inicios_anticipados','inicios_omitidos','inicios_sin_oportunidad','grupos_avisos','falsas_alarmas','redundantes','aciertos_avisos','horas_bajo_aviso']+[f'detectados_ge_{k}h' for k in H if k<=h]+[f'oportunidad_ge_{k}h' for k in H if k<=h]
  v={c:z[c].sum() for c in sums}; v.update(recall_inicios=v['inicios_anticipados']/v['inicios_evaluables'],falsas_alarmas_por_mes=v['falsas_alarmas']/v['meses_equivalentes'],proporcion_tiempo_aviso=v['horas_bajo_aviso']/v['n_emisiones'],anticipacion_media_h=az.anticipacion_h.mean(),anticipacion_mediana_h=az.anticipacion_h.median())
  v.update({f'fraccion_eventos_ge_{k}h':v[f'detectados_ge_{k}h']/v['inicios_evaluables'] for k in H if k<=h})
  mm.append(dict(horizonte_h=h,bloque='AGREGADO',modelo=arm,politica=policy,**v))
 m=pd.DataFrame(mm); pm=pd.DataFrame(prob)
 for d,n in [(a,'correspondencia_avisos'),(e,'evaluacion_inicios'),(m,'metricas_avisos'),(pm,'metricas_probabilidades'),(pd.DataFrame(calibration),'calibracion')]: save(d,OUT/f'tablas/{n}.csv')
 delta=[]
 for table,metrics in [(pm,['AP','Brier']),(m,['recall_inicios','falsas_alarmas_por_mes','proporcion_tiempo_aviso','anticipacion_media_h']+[f'fraccion_eventos_ge_{k}h' for k in H])]:
  for key,z in table.groupby(['horizonte_h','bloque']+(['politica'] if 'politica' in table else [])):
   z=z.set_index('modelo')
   for new,old in [('B','A'),('C','A'),('D','B')]:
    if new not in z.index or old not in z.index: continue
    for metric in metrics:
     if metric in z: delta.append(dict(horizonte_h=key[0],bloque=key[1],politica=key[2] if len(key)>2 else '',contraste=new+'-'+old,metrica=metric,delta=z.loc[new,metric]-z.loc[old,metric]))
 save(pd.DataFrame(delta),OUT/'tablas/diferencias_pareadas.csv')
 bootstrap(pred,a,e,m); render(pm,m,pd.DataFrame(calibration))
 js(OUT/'estado_etapa.json',{'estado':'resultados_completos_pendiente_verificacion_independiente','etapa':ETAPA,'otras_etapas':'pendientes_sin_entrenar'})

def render(pm,m,cal):
 import matplotlib.pyplot as plt
 g=OUT/'graficos'; g.mkdir(exist_ok=True)
 for h in H:
  fig,axs=plt.subplots(1,3,figsize=(16,4))
  for arm in 'ABCD':
   z=m[(m.horizonte_h==h)&m.modelo.eq(arm)&m.bloque.eq('AGREGADO')&m.politica.str.startswith('p>=')].sort_values('falsas_alarmas_por_mes')
   axs[0].plot(z.falsas_alarmas_por_mes,z.recall_inicios,'o-',label=arm); axs[1].plot(z.proporcion_tiempo_aviso,z.anticipacion_media_h,'o-',label=arm)
   c=cal[(cal.horizonte_h==h)&cal.modelo.eq(arm)&cal.bloque.eq('AGREGADO')&cal.n.gt(0)]; axs[2].plot(c.p_media,c.frecuencia,'o-',label=arm)
  axs[0].set(xlabel='Falsos / mes evaluable',ylabel='Fracción de eventos detectados'); axs[1].set(xlabel='Proporción del tiempo bajo aviso',ylabel='Anticipación efectiva media (h)'); axs[2].plot([0,1],[0,1],'k--'); axs[2].set(xlabel='Probabilidad media',ylabel='Frecuencia observada')
  for ax in axs: ax.legend(); ax.grid(alpha=.2)
  fig.suptitle(f'INIA/La Laguna sin presión · ventana {h} h · exploratorio 2013–2023'); fig.tight_layout(); fig.savefig(g/f'horizonte_{h}h.png',dpi=140); plt.close(fig)
 ci=pd.read_csv(OUT/'tablas/intervalos_pareados.csv').fillna({'politica':''}); delta=pd.read_csv(OUT/'tablas/diferencias_pareadas.csv').fillna({'politica':''})
 lines=['# Etapa La Laguna sin presión: INIA y La Laguna–Elqui','', 'Estudio exploratorio 2013–2023, referido al criterio histórico. No demuestra mecanismo físico ni capacidad operacional. Ventana futura y anticipación efectiva son conceptos distintos. AP no es porcentaje de aciertos; al variar horizonte cambia la prevalencia. No se selecciona un horizonte ganador ni una política operacional.','', '## Probabilidades y aporte de La Laguna sin presión','']
 lines.append(pm[pm.bloque.eq('AGREGADO')].to_markdown(index=False,floatfmt='.5g'))
 for h in H:
  lines += ['',f'### Ventana {h} horas','']
  for contrast in ['B-A','C-A','D-B']:
   c=ci[(ci.horizonte_h==h)&ci.contraste.eq(contrast)&ci.politica.eq('')].set_index('metrica'); d=delta[(delta.horizonte_h==h)&delta.contraste.eq(contrast)&delta.politica.eq('')&delta.bloque.ne('AGREGADO')]
   ap=c.loc['AP']; br=c.loc['Brier']; good=(d[d.metrica.eq('AP')].delta>0).all() and (d[d.metrica.eq('Brier')].delta<0).all() and ap.p025>0 and br.p975<0
   bad=(d[d.metrica.eq('AP')].delta<0).all() and (d[d.metrica.eq('Brier')].delta>0).all() and ap.p975<0 and br.p025>0
   status='mejora consistente' if good else ('empeoramiento consistente' if bad else ('ausencia de evidencia de mejora' if ap.p025<=0<=ap.p975 and br.p025<=0<=br.p975 else 'incierto'))
   lines.append(f'{contrast}: ΔAP={ap.estimacion:.5g} [IC95% {ap.p025:.5g}, {ap.p975:.5g}], ΔBrier={br.estimacion:.5g} [{br.p025:.5g}, {br.p975:.5g}]; {status}.')
  z=m[(m.horizonte_h==h)&m.bloque.eq('AGREGADO')&m.politica.str.startswith('presupuesto')]
  lines += ['', 'Políticas congeladas mediante OOF interno. Los presupuestos son escenarios exploratorios; la tasa observada puede excederlos.', '',z[['modelo','politica','inicios_evaluables','inicios_anticipados','inicios_omitidos','recall_inicios','falsas_alarmas_por_mes','horas_bajo_aviso','proporcion_tiempo_aviso','anticipacion_media_h','anticipacion_mediana_h']].to_markdown(index=False,floatfmt='.4g'),'', 'Anticipación sobre todos los eventos elegibles, incluidos omitidos:', '', z[['modelo','politica']+[f'fraccion_eventos_ge_{k}h' for k in H if k<=h]].to_markdown(index=False,floatfmt='.4g'),'',f'![Ventana {h} horas](graficos/horizonte_{h}h.png)']
 lines += ['', '## Soporte y escasez de eventos','', pd.read_csv(OUT/'tablas/perdidas_soporte.csv').to_markdown(index=False), '', 'El soporte máximo24 excluye ventanas con cualquier estado futuro desconocido y exige las mismas entradas para todas las variantes. Los entrenamientos expansivos se solapan: sus eventos no se suman como evidencia independiente. El agregado usa solo las validaciones externas disjuntas. En tablas/evaluacion_inicios.csv se conservan omitidos y sin oportunidad; correspondencia_avisos.csv entrega la distribución completa de anticipación. Las fracciones ≥k usan todos los eventos elegibles del horizonte, sin restringirse a detectados. Un episodio solo puede detectar un inicio.', '', '## Resultados completos y límites', '', 'tablas/metricas_probabilidades.csv y calibracion.csv incluyen particiones y agregado; metricas_avisos.csv conserva toda la rejilla y políticas; politicas.csv documenta umbrales, presupuestos y falta de soporte. Intervalos pareados y realizaciones bootstrap están en tablas. Las diferencias por partición son puntuales, los IC agregados siguen el método original. 300 réplicas de bloques móviles de tres meses, ocho por bienio, semilla 20132023, compartidas. Condicionales a modelos y catálogo, con extremos no uniformes; no incluyen incertidumbre de etiquetas, instrumentos ni entrenamiento. Múltiples comparaciones exploratorias: los IC por contraste no garantizan cobertura conjunta 95%.', '', 'Calibración descriptiva con bins fijos; colas con escasos casos no acreditan calibración fiable. Persisten dudas de latencia, zona histórica, posición del promedio y altura T/HR INIA; no se infiere alineación física por desempeño. La presión solo es variable local. Las validaciones de desarrollo fueron reutilizadas: no son una prueba independiente final.', '', '## Integridad y continuación', '', 'Consultar registro_preentrenamiento.json, unidades/*/*/*/estado.json, verificacion_independiente.json y reproduccion.json. La conclusión de reproducibilidad solo es válida si dichos archivos indican conformidad. Código y comandos en ../../etapa_laguna_sin_presion/README.md. La Laguna sin presión ejecutada; comparación directa entre estaciones pendiente.']
 (OUT/'informe.md').write_text('\n\n'.join(lines)+'\n')

def main():
 global OUT,ETAPA
 ap=argparse.ArgumentParser(); ap.add_argument('comando',choices=['preparar','ejecutar','reanudar','informar','verificar','reproducir']); ap.add_argument('--etapa',choices=list(CONFIG['etapas']),default='laguna_sin_presion'); ap.add_argument('--salida',type=Path); ap.add_argument('--activar-etapa-pendiente',action='store_true',help='Solo usar en un encargo posterior que autorice esa etapa'); args=ap.parse_args()
 if args.etapa!='laguna_sin_presion': raise SystemExit('Esta copia solo autoriza La Laguna sin presión')
 if args.etapa!='pisco' and not args.activar_etapa_pendiente: raise SystemExit(f'Etapa {args.etapa} preparada en configuracion.json, pendiente y no autorizada en este encargo. No se ha entrenado.')
 ETAPA=args.etapa
 if ETAPA=='sintesis': raise SystemExit('Síntesis pendiente de completar las tres estaciones')
 spec=CONFIG['etapas'][ETAPA]; s.STATION=spec['slug']
 variables=['temperatura','humedad','viento','direccion']+(['presion'] if spec['presion_complementaria'] else [])
 s.EXPECTED={sid:(v,height) for sid,v,height in zip(spec['sensores'],variables,spec['alturas_m'])}
 OUT=args.salida.resolve() if args.salida else BASE.parent/'resultados'/ETAPA
 if args.comando=='preparar': prepare(); js(OUT/'preparacion.json',{'estado':'datos_preparados','etapa':ETAPA,'horizontes':H})
 elif args.comando in ['ejecutar','reanudar']: run()
 elif args.comando=='informar': report()
 elif args.comando=='verificar':
  import verificar_rapido as verificar; verificar.verify(OUT)
 elif args.comando=='reproducir':
  import subprocess
  dest=OUT.parent/(ETAPA+'_reproduccion'); assert not dest.exists(),'La reproducción debe usar directorio nuevo'
  subprocess.run([sys.executable,str(BASE/'estudio.py'),'ejecutar','--etapa',ETAPA,'--activar-etapa-pendiente','--salida',str(dest)],check=True)
  import verificar_rapido as verificar; verificar.verify(dest); verificar.verify(OUT)
  paths=[p.relative_to(OUT) for p in OUT.rglob('*') if p.is_file() and p.name not in ['registro_preentrenamiento.json','verificacion_independiente.json','reproduccion.json','preparacion.json','manifiesto_entregables.json']]
  differences=[str(p) for p in paths if not (dest/p).exists() or digest(OUT/p)!=digest(dest/p)]
  js(OUT/'reproduccion.json',{'resultado':'conforme' if not differences else 'discrepancias','archivos_comparados':len(paths),'diferencias':differences,'directorio':str(dest),'ajustes_por_ejecucion':216,'excepciones':['registro con fecha UTC; verificación con rutas de ejecución; manifiesto de entregables; preparación opcional']}); assert not differences,differences
if __name__=='__main__': main()
