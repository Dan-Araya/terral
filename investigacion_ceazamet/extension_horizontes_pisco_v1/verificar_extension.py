"""Auditoría separada: índices por búsqueda ordenada y correspondencia sin motor.notice."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import extension as e
m=e.m

def read(p): return pd.read_csv(p,float_precision='round_trip').fillna({'id_inicio_objetivo':'','ids':''})

def matching(d,starts,threshold):
 active=d[d.probabilidad.ge(threshold)].copy();active['t']=pd.to_datetime(active.emision)
 groups=active.t.diff().ne(pd.Timedelta(hours=1)).cumsum();used={};rows=[]
 for gid,g in active.groupby(groups):
  candidates=set(v for ids in g.id_inicio_objetivo for v in ids.split('|') if v);ordered=sorted(candidates,key=starts.get);cid=next((v for v in ordered if v not in used),'')
  lead=np.nan
  if cid:
   t=g.loc[g.id_inicio_objetivo.map(lambda q:cid in q.split('|')),'t'].iloc[0];lead=(starts[cid]-t)/pd.Timedelta(hours=1);used[cid]=lead
  rows.append((cid,'acierto' if cid else ('redundante' if candidates else 'falsa_alarma'),lead))
 eligible=set(v for ids in d.id_inicio_objetivo for v in ids.split('|') if v)
 return dict(detectados=len(used),falsas=sum(r[1]=='falsa_alarma' for r in rows),eventos=len(eligible),horas_aviso=len(active),redundantes=sum(r[1]=='redundante' for r in rows)),rows

def verify(dest):
 checks=0;common=None
 for family in ['acumuladas','tramos']:
  e.configure(dest,family);m.setup();reg=json.loads((m.OUT/'registro_preentrenamiento.json').read_text());assert reg['fuentes']==e.sources()
  x,state,cat,f,cols=m.load();starts=cat.set_index('id_tramo').inicio.to_dict();known=cat[cat.inicio_conocido].sort_values('inicio');kt=known.inicio.to_numpy();kid=known.id_tramo.to_numpy();ix=f.index
  scalar=['temperatura','humedad','viento_2m','sin_D','cos_D','INIA_presion','PE_temperatura','PE_humedad','PE_viento','PE_presion','PE_sin_D','PE_cos_D']
  complete=f[scalar].notna().all(axis=1).rolling(7,min_periods=7).min().eq(1)&f.notna().all(axis=1)
  future=state.eq(-1).iloc[::-1].rolling(72,min_periods=72).sum().iloc[::-1].shift(-1).eq(0)
  uncertain=pd.Series(False,index=ix)
  for r in cat[~cat.inicio_conocido].itertuples(): uncertain.loc[r.inicio]=True
  uc=uncertain.iloc[::-1].rolling(72,min_periods=72).sum().iloc[::-1].shift(-1).eq(0)
  def dataset(lo,hi,h):
   lo=pd.Timestamp(lo);hi=pd.Timestamp(hi);ok=state.eq(0)&complete&future&uc&(ix-pd.Timedelta(hours=6)>=lo)&(ix+pd.Timedelta(hours=72)<=hi)
   for r in cat.itertuples():
    if r.inicio<lo<=r.fin or r.inicio<=hi<r.fin:ok &= ~((ix-pd.Timedelta(hours=6)<=r.fin)&(ix+pd.Timedelta(hours=72)>=r.inicio))
   t=ix[ok];j=np.searchsorted(kt,t.to_numpy(),side='right');ids=[]
   for tt,jj in zip(t,j):
    if family=='acumuladas':
     end=np.searchsorted(kt,np.datetime64(tt+pd.Timedelta(hours=h)),side='right');ids.append('|'.join(kid[jj:end]))
    else:
     delta=(pd.Timestamp(kt[jj])-tt)/pd.Timedelta(hours=1) if jj<len(kt) else np.inf
     ids.append(str(kid[jj]) if {36:24,48:36,72:48}[h]<delta<=h else '')
   d=f.loc[t].copy();d['id_inicio_objetivo']=ids;d['y']=np.array(ids)!='';d['regla']=0;return d
  for bl,ty,vs,ve in m.b.BLOCKS:
   for h in m.H:
    tr=dataset('2013-01-01',f'{ty}-12-31 23:00',h);va=dataset(f'{vs}-01-01',f'{ve}-12-31 23:00',h)
    if common is None:common={}
    for role,dd in [('train',tr),('val',va)]:
     key=(bl,role)
     if key in common:assert dd.index.equals(common[key])
     else:common[key]=dd.index
     support=read(m.OUT/'soportes'/f'{bl}_{role}_{h}.csv');assert pd.DatetimeIndex(pd.to_datetime(support.emision)).equals(dd.index);assert np.array_equal(support.objetivo,dd.y);assert support.ids.tolist()==dd.id_inicio_objetivo.tolist();checks+=3
    internals={vy:(dataset('2013-01-01',f'{vy-1}-12-31 23:00',h),dataset(f'{vy}-01-01',f'{vy}-12-31 23:00',h)) for vy in [ty-1,ty]}
    for arm in 'ABCDK':
     path=m.OUT/'unidades'/bl/f'{h}h'/arm;assert m.unit_valid(path,reg['firma'])
     pred=read(path/'predicciones.csv');oof=read(path/'oof.csv');assert not oof.emision.duplicated().any()
     for tag,tt,vv,pp,fitpath in [(bl,tr,va,pred,path/'externo')]+[(str(vy),tt,vv,oof[oof.fold.eq(vy)],path/'interno'/str(vy)) for vy,(tt,vv) in internals.items()]:
      assert pd.DatetimeIndex(pd.to_datetime(pp.emision)).equals(vv.index);assert np.array_equal(pp.objetivo,vv.y);assert pp.id_inicio_objetivo.tolist()==vv.id_inicio_objetivo.tolist()
      co=read(fitpath/'ajustes'/f'logistica_{tag}_{h}h.csv');meta=json.loads((fitpath/'ajustes'/f'logistica_{tag}_{h}h.json').read_text());X=tt[cols[arm]].to_numpy();sd=X.std(axis=0);sd[sd==0]=1
      assert co.variable.tolist()==cols[arm];assert np.allclose(co.media_train,X.mean(axis=0),atol=1e-10,rtol=1e-10);assert np.allclose(co.sd_train,sd,atol=1e-10,rtol=1e-10)
      pro=m.b.expit(meta['intercepto']+((vv[cols[arm]].to_numpy()-co.media_train.to_numpy())/co.sd_train.to_numpy())@co.coef_estandarizado.to_numpy());assert np.allclose(pro,pp.probabilidad,atol=1e-10,rtol=1e-9);assert np.allclose(pp.p_constante_train,tt.y.mean());checks+=8
     inner=[]
     for t in m.CONFIG['umbrales']:
      mm=[matching(q,starts,t)[0] for _,q in oof.groupby('fold')];z={k:sum(q[k] for q in mm) for k in mm[0]};z.update(umbral=t,meses=len(oof)/m.MONTH,tasa=z['falsas']/(len(oof)/m.MONTH));inner.append(z)
     im=pd.DataFrame(inner);stored=read(path/'evaluacion_interna.csv')
     for c in ['eventos','detectados','falsas','horas_aviso','tasa']:assert np.allclose(im[c],stored[c])
     policies=json.loads((path/'politicas_congeladas.json').read_text())
     for policy in policies:
      feasible=im[(im.tasa<=policy['presupuesto'])&(im.meses>=12)&(im.eventos>=10)].sort_values(['detectados','tasa','horas_aviso','umbral'],ascending=[False,True,True,False])
      assert (policy['umbral'] is None) if feasible.empty else policy['umbral']==float(feasible.umbral.iloc[0]);checks+=1
     metrics=read(m.OUT/'tablas/metricas_avisos.csv');alerts=read(m.OUT/'tablas/correspondencia_avisos.csv')
     z=metrics[metrics.bloque.eq(bl)&metrics.horizonte_h.eq(h)&metrics.modelo.eq(arm)]
     for row in z.itertuples():
      mt,ar=matching(pred,starts,row.umbral);assert mt['detectados']==row.inicios_anticipados and mt['falsas']==row.falsas_alarmas and mt['eventos']==row.inicios_evaluables and mt['horas_aviso']==row.horas_bajo_aviso and mt['redundantes']==row.redundantes
      az=alerts[alerts.bloque.eq(bl)&alerts.horizonte_h.eq(h)&alerts.modelo.eq(arm)&alerts.politica.eq(row.politica)].fillna({'id_inicio':''})
      assert len(ar)==len(az)
      for expected,actual in zip(ar,az.itertuples()):
       assert expected[0]==actual.id_inicio and expected[1]==actual.estado
       assert (np.isnan(expected[2]) and np.isnan(actual.anticipacion_h)) or abs(expected[2]-actual.anticipacion_h)<1e-10
      checks+=3
    print('Verificado',family,bl,h,flush=True)
  pm=read(m.OUT/'tablas/metricas_probabilidades.csv')
  for row in pm.itertuples():
   ds=[read(m.OUT/'unidades'/bl/f'{row.horizonte_h}h'/row.modelo/'predicciones.csv') for bl,_,_,_ in m.b.BLOCKS if row.bloque=='AGREGADO' or bl==row.bloque];d=pd.concat(ds)
   assert abs(m.b.pr(d.objetivo,d.probabilidad)[0]-row.AP)<1e-12;assert abs(np.mean((d.probabilidad-d.objetivo)**2)-row.Brier)<1e-12;checks+=2
  assert reg['fuentes']==e.sources();m.js(m.OUT/'verificacion_independiente.json',dict(resultado='conforme',comprobaciones=checks,metodo='búsquedas ordenadas para primer inicio/objetivos; máscara futura invertida; correspondencia separada; escalas y predicciones externas/internas; rejilla OOF y selección; fuentes SHA256',limites='Lectores de sensores auditados compartidos; no certifica instrumentos'))
