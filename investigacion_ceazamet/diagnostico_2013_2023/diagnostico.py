#!/usr/bin/env python3
"""Diagnóstico limitado estrictamente a 2013–2023. Ejecutar desde cualquier cwd."""
import sys
sys.modules['numexpr'] = None  # Evitar extensión opcional incompatible del host.
import os, json, hashlib, platform
from pathlib import Path
import numpy as np
import pandas as pd
os.environ.setdefault('MPLCONFIGDIR','/tmp/terral-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
OUT=Path(__file__).resolve().parent
ROOT=OUT.parent.parent
SRC=OUT.parent/'historico_inia/derivados'
P=json.loads((OUT/'protocolo.json').read_text())
START,END=map(pd.Timestamp,P['periodo'])
IDX=pd.date_range(START,END,freq='h')
VARS=['temperatura','humedad','viento_2m','direccion_2m','presion']
MAIN=VARS[:4]
Q=[0,.01,.05,.25,.5,.75,.95,.99,1]
(OUT/'tablas').mkdir(exist_ok=True); (OUT/'graficos').mkdir(exist_ok=True)
def save(df,name):
 df.to_csv(OUT/'tablas'/f'{name}.csv',index=False,float_format='%.6f')
def quant(a):
 a=pd.Series(a).dropna()
 return {'n':len(a),**{f'q{int(q*100):02}':a.quantile(q) if len(a) else np.nan for q in Q}}
def runs(mask):
 a=np.flatnonzero(np.asarray(mask));
 return np.split(a,np.flatnonzero(np.diff(a)>1)+1) if len(a) else []
frames=[]; manifest=[]
for year in range(2013,2024):
 path=SRC/f'observaciones_{year}.csv'
 f=pd.read_csv(path)
 dates=pd.to_datetime(f.fecha_sin_zona,errors='raise')
 assert dates.between(START,END).all(), f'Fecha prohibida en {path}'
 assert (dates.dt.year==year).all()
 assert dates.eq(dates.dt.floor('h')).all()
 assert f.dentro_periodo.eq(1).all()
 f['fecha']=dates; f['csv_fuente']=path.relative_to(ROOT).as_posix(); f['fila_csv']=np.arange(len(f))+2
 manifest.append({'archivo':path.relative_to(ROOT).as_posix(),'sha256_csv':hashlib.sha256(path.read_bytes()).hexdigest(),'filas':len(f),'fecha_min':dates.min(),'fecha_max':dates.max()})
 frames.append(f[f.variable.isin(VARS)].copy())
raw=pd.concat(frames,ignore_index=True)
assert not raw.duplicated(['fecha','variable']).any(), 'Duplicados: resolver manualmente'
for c in ['min','prom','max','porcentaje_datos']: raw[c]=pd.to_numeric(raw[c],errors='raise')
raw['presente']=np.isfinite(raw['prom']) & raw.porcentaje_datos.gt(0)
raw['valido']=raw.presente & raw.prom_utilizable_revision.eq(1)
physical=((raw.variable.eq('humedad') & ~raw['prom'].between(0,100)) | (raw.variable.eq('viento_2m') & raw['prom'].lt(0)) | (raw.variable.eq('direccion_2m') & ~raw['prom'].between(0,360))) & raw.presente
raw.loc[physical,'valido']=False
raw['bandera_rango']=raw.presente & ((raw.variable.eq('temperatura') & ~raw['prom'].between(-30,50)) | (raw.variable.eq('viento_2m') & raw['prom'].gt(60)) | (raw.variable.eq('presion') & ~raw['prom'].between(500,1100)) | physical)
raw['bandera_orden']=raw.presente & ~raw.variable.eq('direccion_2m') & ((raw['min']>raw['prom']) | (raw['prom']>raw['max']) | (raw['min']>raw['max']))
save(pd.DataFrame(manifest),'manifiesto_fuentes')
save(raw[['fecha','variable','csv_fuente','fila_csv','archivo_original','sha256_original','hoja','fila_excel','sensor','unidad','altura_encabezado_m','min','prom','max','porcentaje_datos','prom_utilizable_revision','problemas','presente','valido','bandera_rango','bandera_orden']],'trazabilidad_observaciones')
save(raw[raw.bandera_rango|raw.bandera_orden|(~raw.valido & raw.presente)],'valores_sospechosos')
wide=raw.pivot(index='fecha',columns='variable',values='prom').reindex(IDX)
valid=raw.pivot(index='fecha',columns='variable',values='valido').reindex(IDX,fill_value=False).fillna(False).astype(bool)
present=raw.pivot(index='fecha',columns='variable',values='presente').reindex(IDX,fill_value=False).fillna(False).astype(bool)
x=wide.where(valid); joint=valid[MAIN].all(axis=1)
coverage=[]
for freq in ['Y','M']:
 for key, inds in pd.Series(np.arange(len(IDX)),index=IDX).groupby(IDX.year if freq=='Y' else IDX.strftime('%Y-%m')):
  ii=inds.values
  for v in VARS+['conjunta_4']:
   vv=valid[v].iloc[ii] if v!='conjunta_4' else joint.iloc[ii]
   pp=present[v].iloc[ii] if v!='conjunta_4' else present[MAIN].all(axis=1).iloc[ii]
   coverage.append({'escala':freq,'periodo':key,'variable':v,'horas_esperadas':len(ii),'presentes':int(pp.sum()),'validas':int(vv.sum()),'ausentes':int((~pp).sum()),'presentes_no_validas':int((pp & ~vv).sum()),'ceros_validos':int((vv & wide[v].iloc[ii].eq(0)).sum()) if v!='conjunta_4' else np.nan,'cobertura_pct':100*vv.mean()})
cov=pd.DataFrame(coverage); save(cov,'cobertura')
gaps=[]; constant=[]
for v in VARS+['conjunta_4']:
 for kind,mask in [('no_valido',~(valid[v] if v!='conjunta_4' else joint)),('ausente',~(present[v] if v!='conjunta_4' else present[MAIN].all(axis=1)))]:
  for a in runs(mask): gaps.append({'variable':v,'tipo':kind,'inicio':IDX[a[0]],'fin':IDX[a[-1]],'horas':len(a),'limite_periodo':a[0]==0 or a[-1]==len(IDX)-1})
 if v!='conjunta_4':
  s=x[v]; groups=(s.ne(s.shift())|s.isna()).cumsum()
  for _,g in s.dropna().groupby(groups):
   if len(g)>=12: constant.append({'variable':v,'inicio':g.index[0],'fin':g.index[-1],'horas':len(g),'valor':g.iloc[0]})
save(pd.DataFrame(gaps),'huecos'); save(pd.DataFrame(constant),'repeticiones_exactas')
save(pd.DataFrame([{'variable':v,'tipo':k,**quant(g.horas)} for (v,k),g in pd.DataFrame(gaps).groupby(['variable','tipo'])]),'distribucion_huecos')
# Descripciones por mes calendario, hora registrada y sus cruces; anual-mensual para discontinuidades.
dist=[]; dirs=[]; changes=[]
def describe(s,v,scale,key):
 base={'variable':v,'escala':scale,'grupo':key}
 if v!='direccion_2m': return {**base,**quant(s)}
 a=s.dropna().to_numpy(); rad=np.deg2rad(a)
 sn=np.sin(rad).mean() if len(a) else np.nan; cs=np.cos(rad).mean() if len(a) else np.nan
 r=np.hypot(sn,cs); mu=np.rad2deg(np.arctan2(sn,cs))%360 if r>1e-12 else np.nan
 dev=(a-mu+180)%360-180
 dirs.append({**base,'n':len(a),'media_circular_grados':mu,'R':r,**{f'desvio_{k}':val for k,val in quant(dev).items() if k!='n'}})
 return None
keys={'total':['total']*len(IDX),'ano':IDX.year,'mes':IDX.month,'hora':IDX.hour,'mes_hora':[f'{m:02}-{h:02}' for m,h in zip(IDX.month,IDX.hour)],'ano_mes':IDX.strftime('%Y-%m')}
for v in VARS:
 for scale,key in keys.items():
  for k,s in x[v].groupby(key):
   d=describe(s,v,scale,k)
   if d: dist.append(d)
save(pd.DataFrame(dist),'distribuciones'); save(pd.DataFrame(dirs),'direccion_circular')
sector=pd.DataFrame({'mes':IDX.month,'hora':IDX.hour,'valida':valid.direccion_2m.astype(int),'calma_con_direccion':(valid.direccion_2m & valid.viento_2m & wide.viento_2m.eq(0)).astype(int)})
for lo in range(0,360,45): sector[f'sector_{lo}_{lo+45}']=(valid.direccion_2m & (wide.direccion_2m%360).ge(lo) & (wide.direccion_2m%360).lt(lo+45)).astype(int)
save(sector.groupby(['mes','hora']).sum().reset_index(),'sectores_direccion')
jumps=[]
for v,limit in [('temperatura',8),('humedad',40),('viento_2m',5)]:
 for lag in [1,3]:
  delta=x[v]-x[v].shift(lag)
  assert (IDX[lag:]-IDX[:-lag]==pd.Timedelta(hours=lag)).all()
  intermediate=pd.Series(True,index=IDX)
  for j in range(1,lag): intermediate &= valid[v].shift(j,fill_value=False)
  for scale,key in {'total':['total']*len(IDX),**{k:keys[k] for k in ['mes','hora','mes_hora']}}.items():
   for k,g in delta.groupby(key): changes.append({'variable':v,'lag_h':lag,'escala':scale,'grupo':k,**quant(g),'pares_con_intermedias_invalidas':int((g.notna() & ~intermediate.loc[g.index]).sum())})
  if lag==1:
   for dt,z in delta[delta.abs().ge(limit)].items(): jumps.append({'fecha':dt,'variable':v,'anterior':x.loc[dt-pd.Timedelta(hours=1),v],'actual':x.loc[dt,v],'cambio':z})
save(pd.DataFrame(changes),'cambios_exactos'); save(pd.DataFrame(jumps),'saltos_revision')
# Diferencias entre medianas de meses contiguos: descripción, no atribución instrumental.
med=x.resample('MS').median(); shift=med.diff(); disc=[]
for dt,row in shift.iterrows():
 for v in VARS:
  if v!='direccion_2m': disc.append({'mes':dt,'variable':v,'mediana':med.loc[dt,v],'cambio_mediana_mes_previo':row[v],'n':x.loc[dt:dt+pd.offsets.MonthEnd(0)+pd.Timedelta(hours=23),v].count()})
save(pd.DataFrame(disc),'continuidad_mensual')
quality=[]
for year,g in raw.groupby(raw.fecha.dt.year):
 for v,r in g.groupby('variable'):
  p=r[r.presente]; good=r[r.valido]
  quality.append({'ano':year,'variable':v,'n_presentes':len(p),'n_validas':len(good),'banderas_rango':int(r.bandera_rango.sum()),'banderas_orden':int(r.bandera_orden.sum()),'porcentaje_parcial_entre_0_100':int(r.porcentaje_datos.between(0,100,inclusive='neither').sum()),'ceros_validos':int(good['prom'].eq(0).sum()),'fraccion_prom_enteros':float(good['prom'].eq(good['prom'].round()).mean()),'sensores':','.join(map(str,sorted(r.sensor.astype(str).unique()))),'alturas_encabezado_m':','.join(map(str,sorted(r.altura_encabezado_m.unique())))})
save(pd.DataFrame(quality),'calidad_anual')
def state(config):
 ok=(x.direccion_2m.between(config['dlo'],config['dhi']) & x.viento_2m.gt(config['v']) & x.temperatura.gt(config['t']) & x.humedad.lt(config['rh']))
 return pd.Series(np.where(~joint,-1,np.where(ok,1,0)),index=IDX)
def segments(st,c):
 strict=[a for a in runs(st.eq(1)) if len(a)>=c['persistencia']]
 retained=np.zeros(len(IDX),dtype=bool)
 for a in strict: retained[a]=True
 grouped=[]
 for a in strict:
  if grouped and c['puente_negativo'] and a[0]-grouped[-1][-1]==2 and st.iloc[a[0]-1]==0:
   grouped[-1]=np.r_[grouped[-1],a]
  else: grouped.append(a.copy())
 rows=[]
 for n,a in enumerate(grouped,1):
  rows.append({'tramo':n,'inicio':IDX[a[0]],'fin':IDX[a[-1]],'horas_candidatas':len(a),'amplitud_h':a[-1]-a[0]+1,'horas_puente':a[-1]-a[0]+1-len(a),'viento_medio_ms':x.viento_2m.iloc[a].mean(),'max_promedio_horario_ms':x.viento_2m.iloc[a].max(),'censura_izq':a[0]==0 or st.iloc[a[0]-1]==-1,'censura_der':a[-1]==len(IDX)-1 or st.iloc[a[-1]+1]==-1})
 return pd.DataFrame(rows),retained
orig=state(P['sensibilidad_prefijada'][0]); seg,ret=segments(orig,P['sensibilidad_prefijada'][0])
assert (orig.eq(1)&~joint).sum()==0
hourly=wide.copy(); hourly['validez_conjunta']=joint; hourly['estado']=orig.map({1:'cumple',0:'no_cumple',-1:'no_evaluable'})
hourly.index.name='fecha_sin_zona'; save(hourly.reset_index(),'estados_horarios')
counts=[]
def count_time(st,label,mask):
 for scale,key in {'ano':IDX.year,'ano_mes':keys['ano_mes'],'mes':keys['mes'],'hora':keys['hora'],'mes_hora':keys['mes_hora']}.items():
  z=pd.DataFrame({'grupo':key,'st':st.values,'incluida':np.asarray(mask)})
  for k,g in z[z.incluida].groupby('grupo'):
   n=len(g); yes=int(g.st.eq(1).sum()); ev=int(g.st.ne(-1).sum())
   counts.append({'aplicacion':label,'escala':scale,'grupo':k,'horas_ambito':n,'cumple':yes,'no_cumple':int(g.st.eq(0).sum()),'no_evaluable':n-ev,'fraccion_sobre_evaluables':yes/ev if ev else np.nan})
count_time(orig,'anual',np.ones(len(IDX),bool)); winter=(IDX.month>=4)&(IDX.month<=8)
count_time(orig,'abril_agosto_sin_filtro_hora',winter)
save(seg,'tramos_anual')
winterst=orig.copy(); winterst.loc[~winter]=0
ws,_=segments(winterst,P['sensibilidad_prefijada'][0]); save(ws,'tramos_abril_agosto')
# Agrupación TD/TE; días negativos y desconocidos permanecen diferenciados.
days=[]
for dt,g in orig.groupby(IDX.normalize()):
 cand=g[g.eq(1)]; n=len(cand)
 first=cand.index[0] if n else pd.NaT
 prior=g[g.index<first] if n else g.iloc[:0]
 prev=dt-pd.Timedelta(hours=1)
 uncertain=bool(prior.eq(-1).any() or (n and first.hour==0 and (prev not in orig.index or orig.loc[prev]==-1)))
 continuation=bool(n and first.hour==0 and prev in orig.index and orig.loc[prev]==1)
 dayruns=runs(g.eq(1))
 days.append({'dia':dt,'horas_candidatas':n,'tramos_dentro_dia':len(dayruns),'max_horas_consecutivas_dia':max(map(len,dayruns),default=0),'no_evaluables':int(g.eq(-1).sum()),'estado_dia':'candidato' if n else ('desconocido' if g.eq(-1).any() else 'sin_candidatos'),'primera_hora':first.hour if n else np.nan,'inicio_incierto':uncertain,'continuacion_dia_previo':continuation,'abril_agosto':4<=dt.month<=8,'agricola_proxy_00_07':bool(n and 4<=dt.month<=8 and first.hour<8),'agricola_proxy_01_07':bool(n and 4<=dt.month<=8 and 1<=first.hour<8)})
days=pd.DataFrame(days); save(days,'dias_historicos')
events=[]
for label,mask in [('anual',days.horas_candidatas.gt(0)),('abril_agosto',days.horas_candidatas.gt(0)&days.abril_agosto),('agricola_proxy_00_07',days.agricola_proxy_00_07),('agricola_proxy_01_07',days.agricola_proxy_01_07)]:
 for n,a in enumerate(runs(mask),1):
  g=days.iloc[a]; events.append({'aplicacion':label,'evento':n,'inicio_dia':g.dia.iloc[0],'fin_dia':g.dia.iloc[-1],'dias':len(g),'horas_candidatas':g.horas_candidatas.sum(),'dias_con_desconocidas':g.no_evaluables.gt(0).sum(),'inicios_inciertos':g.inicio_incierto.sum(),'adyacente_dia_desconocido':bool((a[0]>0 and days.estado_dia.iloc[a[0]-1]=='desconocido') or (a[-1]<len(days)-1 and days.estado_dia.iloc[a[-1]+1]=='desconocido'))})
 for limit in [0,1] if label.startswith('agricola_proxy') else []:
  if limit==0:
   selected=set(days.loc[mask,'dia']); hm=np.array([dt.normalize() in selected for dt in IDX]); count_time(orig,label,hm)
save(pd.DataFrame(events),'eventos_por_dias'); save(pd.DataFrame(counts).drop_duplicates(),'conteos_candidatos')
group_dist=[]
for label,mask in [('anual',days.horas_candidatas.gt(0)),('abril_agosto',days.horas_candidatas.gt(0)&days.abril_agosto),('agricola_proxy_00_07',days.agricola_proxy_00_07),('agricola_proxy_01_07',days.agricola_proxy_01_07)]:
 group_dist.append({'aplicacion':label,'unidad':'dia','variable':'horas_candidatas',**quant(days.loc[mask,'horas_candidatas'])})
 ev=pd.DataFrame(events); group_dist.append({'aplicacion':label,'unidad':'evento_por_dias','variable':'dias',**quant(ev.loc[ev.aplicacion.eq(label),'dias'])})
 selected=set(days.loc[mask,'dia']); hm=np.array([dt.normalize() in selected for dt in IDX])
 scoped=orig.copy(); scoped.loc[~hm]=0
 ss,_=segments(scoped,P['sensibilidad_prefijada'][0])
 save(ss,f'tramos_dias_{label}')
 for v in ['horas_candidatas','viento_medio_ms','max_promedio_horario_ms']:
  group_dist.append({'aplicacion':label,'unidad':'tramo_en_dias_seleccionados','variable':v,**quant(ss[v])})
save(pd.DataFrame(group_dist),'distribuciones_dias_eventos')
summary=[]; temporal=[]; allseg=[]; sd=[]
for c in P['sensibilidad_prefijada']:
 st=state(c); sg,keep=segments(st,c)
 total=int(st.eq(1).sum()); held=int(keep.sum())
 summary.append({'configuracion':c['id'],'horas_criterio':total,'horas_retenidas':held,'tramos':len(sg),'duracion_mediana_h':sg.horas_candidatas.median(),'duracion_p95_h':sg.horas_candidatas.quantile(.95),'duracion_max_h':sg.horas_candidatas.max(),'amplitud_media_h':sg.amplitud_h.mean(),'delta_horas_vs_original':held-int(ret.sum()),'delta_tramos_vs_original':len(sg)-len(seg)})
 allseg.append(sg.assign(configuracion=c['id']))
 for column in ['horas_candidatas','amplitud_h','viento_medio_ms','max_promedio_horario_ms']:
  sd.append({'configuracion':c['id'],'variable':column,**quant(sg[column])})
 for scale,key in {'ano':IDX.year,'ano_mes':keys['ano_mes'],'mes':IDX.month,'hora':IDX.hour}.items():
  df=pd.DataFrame({'grupo':key,'criterio':st.eq(1).astype(int).values,'retenidas':keep.astype(int),'evaluables':joint.astype(int).values})
  for k,g in df.groupby('grupo'): temporal.append({'configuracion':c['id'],'escala':scale,'grupo':k,'horas_criterio':g.criterio.sum(),'horas_retenidas':g.retenidas.sum(),'evaluables':g.evaluables.sum()})
sens=pd.DataFrame(summary); save(sens,'sensibilidad_resumen'); save(pd.DataFrame(temporal),'sensibilidad_temporal'); save(pd.concat(allseg),'sensibilidad_tramos'); save(pd.DataFrame(sd),'distribuciones_tramos')
# Gráficos limitados al período permitido.
plt.rcParams.update({'font.size':9})
fig,ax=plt.subplots(figsize=(11,3.5)); cm=cov[cov.escala.eq('M')].pivot(index='variable',columns='periodo',values='cobertura_pct').reindex(VARS+['conjunta_4'])
im=ax.imshow(cm,aspect='auto',vmin=95,vmax=100,cmap='viridis'); ax.set_yticks(range(6),cm.index); ax.set_xticks(range(0,132,12),[str(y) for y in range(2013,2024)]); ax.set_title('Cobertura válida mensual (%); saturación visual por debajo de 95%'); fig.colorbar(im,ax=ax); fig.tight_layout(); fig.savefig(OUT/'graficos/cobertura.png',dpi=160); plt.close(fig)
fig,axes=plt.subplots(3,1,figsize=(10,7),sharex=True)
for ax,v in zip(axes,MAIN[:3]):
 for m in [1,4,7,10]:
  g=x[v][IDX.month==m].groupby(IDX[IDX.month==m].hour).median(); ax.plot(g.index,g.values,label=f'Mes {m}')
 ax.set_ylabel({'temperatura':'Temperatura (°C)','humedad':'HR (%)','viento_2m':'Viento a 2 m (m/s)'}[v]); ax.legend(ncol=4)
axes[-1].set_xlabel('Hora registrada (zona no confirmada)'); fig.tight_layout(); fig.savefig(OUT/'graficos/ciclo_horario.png',dpi=160); plt.close(fig)
fig,axes=plt.subplots(1,3,figsize=(12,3.5))
for ax,key,title in zip(axes,[IDX.year,IDX.month,IDX.hour],['Año','Mes','Hora registrada']):
 a=orig.eq(1).groupby(key).sum(); ax.bar(a.index,a.values); ax.set_xlabel(title); ax.set_ylabel('Horas candidatas')
fig.tight_layout(); fig.savefig(OUT/'graficos/candidatos.png',dpi=160); plt.close(fig)
fig,axes=plt.subplots(1,2,figsize=(10,4)); axes[0].hist(seg.horas_candidatas,bins=np.arange(.5,seg.horas_candidatas.max()+1.5)); axes[0].set_xlabel('Horas consecutivas'); axes[0].set_ylabel('Tramos'); axes[1].scatter(seg.horas_candidatas,seg.max_promedio_horario_ms,s=6,alpha=.4); axes[1].set_xlabel('Horas consecutivas'); axes[1].set_ylabel('Máximo de promedio horario (m/s)'); fig.tight_layout(); fig.savefig(OUT/'graficos/tramos.png',dpi=160); plt.close(fig)
fig,axes=plt.subplots(1,2,figsize=(11,5)); axes[0].barh(sens.configuracion,sens.horas_retenidas); axes[0].set_xlabel('Horas candidatas retenidas'); axes[1].barh(sens.configuracion,sens.tramos); axes[1].set_xlabel('Tramos o grupos (puente)'); fig.tight_layout(); fig.savefig(OUT/'graficos/sensibilidad.png',dpi=160); plt.close(fig)
fig,ax=plt.subplots(figsize=(9,3)); window=wide.loc['2015-07-20','presion']; ax.plot(window.index,window.values,'o-',label='prom fuente'); bad=raw[raw.variable.eq('presion') & raw.fecha.between('2015-07-20 00:00','2015-07-20 23:00') & ~raw.valido]; ax.scatter(bad.fecha,bad['prom'],color='red',label='no válido según revisión fuente',zorder=3); ax.set_ylabel('Presión (hPa declarados)'); ax.set_title('Problema concreto: cuatro valores de 11–12 hPa; sin corrección'); ax.legend(); fig.autofmt_xdate(); fig.tight_layout(); fig.savefig(OUT/'graficos/presion_sospechosa_2015.png',dpi=160); plt.close(fig)
audit={'periodo':[str(START),str(END)],'archivos_abiertos':[m['archivo'] for m in manifest],'filas_leidas':sum(m['filas'] for m in manifest),'filas_variables_analizadas':len(raw),'horas_esperadas':len(IDX),'todas_fechas_en_periodo':bool(raw.fecha.between(START,END).all()),'duplicados_fecha_variable':int(raw.duplicated(['fecha','variable']).sum()),'marcas_exactamente_horarias':True,'timezone':None,'rellenos':0,'modificaciones_fuente':0,'protocolo_sha256':hashlib.sha256((OUT/'protocolo.json').read_bytes()).hexdigest(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'python':platform.python_version(),'pandas':pd.__version__,'numpy':np.__version__,'matplotlib':matplotlib.__version__,'conjunta_valida':int(joint.sum()),'estados':hourly.estado.value_counts().to_dict(),'verificacion_suma_estados':bool(hourly.estado.value_counts().sum()==len(IDX))}
(OUT/'comprobaciones.json').write_text(json.dumps(audit,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(audit,ensure_ascii=False,indent=2)); print(sens.to_string(index=False))
