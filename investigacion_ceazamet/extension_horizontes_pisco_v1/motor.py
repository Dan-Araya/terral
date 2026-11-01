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
BASE=Path(__file__).resolve().parent; ROOT=BASE.parent
CONFIG=json.loads((BASE/'configuracion.json').read_text()); H=CONFIG['horizontes']; MONTH=365.25*24/12
ETAPA='pisco'
OUT=BASE/'resultados'/ETAPA
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
 paths.extend(BASE/n for n in ['estudio.py','heredado.py','sensores.py','verificar.py','protocolo.md','configuracion.json','revision_previa.md','README.md','test_reglas.py'])
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
 cols={'A':list(b.features(x)),'B':[c for c in f if not c.startswith('PE_')],'C':[c for c in f if not c.startswith('INIA_')],'D':list(f)}
 assert [len(cols[a]) for a in 'ABCD']==([35,41,72,78] if CONFIG['etapas'][ETAPA]['presion_complementaria'] else [35,41,66,72])
 cols['K']=['sin_hora','cos_hora','sin_ano','cos_ano']
 return x,state,cat,f,cols

def labels(state,cat):
 known=pd.Series('',index=b.IDX); uncertain=pd.Series(False,index=b.IDX)
 for r in cat.itertuples():
  if r.inicio_conocido: known.loc[r.inicio]=r.id_tramo
  else: uncertain.loc[r.inicio]=True
 yy={}; ids={}; future=pd.Series(False,index=b.IDX)
 first=pd.Series('',index=b.IDX); lead=pd.Series(np.nan,index=b.IDX)
 accum=pd.Series('',index=b.IDX)
 for k in range(1,73):
  future |= state.shift(-k).eq(-1)|uncertain.shift(-k,fill_value=False)|state.shift(-k).isna()
  q=known.shift(-k,fill_value=''); take=first.eq('')&q.ne(''); first.loc[take]=q.loc[take]; lead.loc[take]=k
  accum=accum.where(q.eq(''),accum+np.where(accum.eq(''),'','|')+q)
  if k in H:
   if FAMILY=='acumuladas': ids[k]=accum.copy()
   else:
    lower={36:24,48:36,72:48}[k]
    ids[k]=first.where(lead.gt(lower)&lead.le(k),'')
   yy[k]=ids[k].ne('').astype(int)
 save(pd.DataFrame({'emision':b.IDX,'primer_inicio_hasta72':first,'distancia_h':lead,'futuro72_desconocido':future}),OUT/'tablas/primer_inicio.csv')
 return yy,ids,future

def dataset(f,state,cat,yy,ids,future,lo,hi,h,common=True):
 ix=f.index; lo=pd.Timestamp(lo); hi=pd.Timestamp(hi)
 hist=f.notna().all(axis=1) if common else f[list(b.features_cache)].notna().all(axis=1)
 # f finite alone is insufficient for direction cancellation or gaps; raw completeness is applied in prepare.
 hist &= COMPLETE if common else BASIC
 maxh=72 if common else h
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
 # Seven actual marks for every required source, including Pisco/INIA pressure.
 scalar=['temperatura','humedad','viento_2m','sin_D','cos_D','INIA_presion','PE_temperatura','PE_humedad','PE_viento','PE_presion','PE_sin_D','PE_cos_D']
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
    getids=lambda z:{v for a in z.id_inicio_objetivo for v in a.split('|') if v}
    rows.append(dict(bloque=block,rol=role,horizonte_h=h,n=len(d),positivos=int(d.y.sum()),prevalencia=d.y.mean(),inicios=len(getids(d))))
    prior=pd.read_csv(ROOT/'estudio_horizontes_inicio_v1/resultados/pisco/soportes'/f'{block}_{role}_24.csv',parse_dates=['emision']).fillna({'ids':''})
    lost=prior[~prior.emision.isin(d.index)]
    before={v for a in prior.ids for v in a.split('|') if v}
    retained={v for a in prior[prior.emision.isin(d.index)].ids for v in a.split('|') if v}
    losses.append(dict(bloque=block,rol=role,horizonte_h=h,anterior_horas=len(prior),comun72_horas=len(d),horas_perdidas=len(lost),inicios24_antes=len(before),inicios24_retenidos=len(retained),inicios24_perdidos=len(before-retained),inicios24_afectados=len({v for a in lost.ids for v in a.split('|') if v})))
    save(pd.DataFrame({'emision':d.index,'objetivo':d.y,'ids':d.id_inicio_objetivo}),OUT/'soportes'/f'{block}_{role}_{h}.csv')
  for role in ['train','val']:
   for h in H: assert datasets[block,role,h].index.equals(datasets[block,role,H[0]].index)
 save(pd.DataFrame(rows),OUT/'tablas/particiones.csv'); save(pd.DataFrame(losses),OUT/'tablas/perdidas_soporte.csv'); js(OUT/'predictores.json',cols)
 save(pd.DataFrame({'emision':b.IDX,'estado':state,'historia_basica':BASIC,'historia_completa':COMPLETE,'futuro72_desconocido':future}),OUT/'tablas/mascaras.csv')
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
 for k in [24,36,48,72]:
  if k<=h:
   m[f'detectados_ge_{k}h']=int(e.anticipacion_h.ge(k).sum()); m[f'fraccion_eventos_ge_{k}h']=m[f'detectados_ge_{k}h']/ne if ne else np.nan
 maxlead=dict.fromkeys(eligible,0.)
 for row in d[d.objetivo.eq(1)].itertuples():
  for cid in row.id_inicio_objetivo.split('|'):
   if cid: maxlead[cid]=max(maxlead[cid],(starts[cid]-row.emision)/pd.Timedelta(hours=1))
 for k in [24,36,48,72]:
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
   for arm in 'ABCDK':
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
 js(OUT/'estado_etapa.json',{'estado':'ajustes_completos','etapa':ETAPA,'unidades':len(H)*15,'otras_etapas':'pendientes_sin_entrenar','firma':signature})
 report(cat)

def report(cat=None):
 setup()
 if cat is None:
  _,_,cat,*_=prepare()
 preds=[]; policies=[]
 for bl,_,_,_ in b.BLOCKS:
  for h in H:
   for arm in 'ABCDK':
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
  prob.append(dict(horizonte_h=h,bloque=bl,modelo=arm,n_emisiones=len(d),positivos=int(d.objetivo.sum()),prevalencia=d.objetivo.mean(),inicios=len({v for ids in d.id_inicio_objetivo for v in ids.split('|') if v}),AP=b.pr(d.objetivo,d.probabilidad)[0],Brier=np.mean((d.probabilidad-d.objetivo)**2),Brier_constante_train=np.mean((d.p_constante_train-d.objetivo)**2),Brier_frecuencia=np.mean((d.p_frecuencia-d.objetivo)**2)))
  edges=[0,.001,.003,.01,.03,.1,.3,.5,1.0000001]; bins=np.clip(np.searchsorted(edges,d.probabilidad,side='right')-1,0,7)
  for k in range(8):
   z=d.iloc[np.flatnonzero(bins==k)]; calibration.append(dict(horizonte_h=h,bloque=bl,modelo=arm,limite_inf=edges[k],limite_sup=min(edges[k+1],1),n=len(z),positivos=int(z.objetivo.sum()),p_media=z.probabilidad.mean(),frecuencia=z.objetivo.mean()))
 for (h,bl,arm),d in pred.groupby(['horizonte_h','bloque','modelo']): hourly(d,h,bl,arm)
 for (h,arm),d in pred.groupby(['horizonte_h','modelo']): hourly(d,h,'AGREGADO',arm)
 a=pd.concat(aa,ignore_index=True); e=pd.concat(ee,ignore_index=True); m=pd.DataFrame(mm)
 for (h,arm,policy),z in m.groupby(['horizonte_h','modelo','politica']):
  if len(z)!=3: continue
  az=a[(a.horizonte_h==h)&a.modelo.eq(arm)&a.politica.eq(policy)]; ez=e[(e.horizonte_h==h)&e.modelo.eq(arm)&e.politica.eq(policy)]
  sums=['n_emisiones','meses_equivalentes','inicios_evaluables','inicios_anticipados','inicios_omitidos','inicios_sin_oportunidad','grupos_avisos','falsas_alarmas','redundantes','aciertos_avisos','horas_bajo_aviso','emisiones_activas_fuera_objetivo','horas_evaluables']+[f'detectados_ge_{k}h' for k in [24,36,48,72] if k<=h]+[f'oportunidad_ge_{k}h' for k in [24,36,48,72] if k<=h]
  v={c:z[c].sum() for c in sums}; v.update(recall_inicios=v['inicios_anticipados']/v['inicios_evaluables'],falsas_alarmas_por_mes=v['falsas_alarmas']/v['meses_equivalentes'],proporcion_tiempo_aviso=v['horas_bajo_aviso']/v['n_emisiones'],anticipacion_media_h=az.anticipacion_h.mean(),anticipacion_mediana_h=az.anticipacion_h.median())
  v.update({f'fraccion_eventos_ge_{k}h':v[f'detectados_ge_{k}h']/v['inicios_evaluables'] for k in [24,36,48,72] if k<=h})
  mm.append(dict(horizonte_h=h,bloque='AGREGADO',modelo=arm,politica=policy,**v))
 m=pd.DataFrame(mm); pm=pd.DataFrame(prob)
 for d,n in [(a,'correspondencia_avisos'),(e,'evaluacion_inicios'),(m,'metricas_avisos'),(pm,'metricas_probabilidades'),(pd.DataFrame(calibration),'calibracion')]: save(d,OUT/f'tablas/{n}.csv')
 delta=[]
 for table,metrics in [(pm,['AP','Brier']),(m,['recall_inicios','falsas_alarmas_por_mes','proporcion_tiempo_aviso','anticipacion_media_h']+[f'fraccion_eventos_ge_{k}h' for k in [24,36,48,72]])]:
  for key,z in table.groupby(['horizonte_h','bloque']+(['politica'] if 'politica' in table else [])):
   z=z.set_index('modelo')
   for new,old in [('B','A'),('C','A'),('D','B'),('A','K'),('B','K'),('C','K'),('D','K')]:
    if new not in z.index or old not in z.index: continue
    for metric in metrics:
     if metric in z: delta.append(dict(horizonte_h=key[0],bloque=key[1],politica=key[2] if len(key)>2 else '',contraste=new+'-'+old,metrica=metric,delta=z.loc[new,metric]-z.loc[old,metric]))
 save(pd.DataFrame(delta),OUT/'tablas/diferencias_pareadas.csv')
 bootstrap(pred,a,e,m); render(pm,m,pd.DataFrame(calibration))
 js(OUT/'estado_etapa.json',{'estado':'resultados_completos_pendiente_verificacion_independiente','etapa':ETAPA,'otras_etapas':'pendientes_sin_entrenar'})

