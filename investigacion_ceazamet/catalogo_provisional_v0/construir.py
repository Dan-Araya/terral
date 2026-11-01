#!/usr/bin/env python3
"""Auditoría v0. Solo tablas diagnósticas de 2013–2023; sin red."""
import sys
sys.modules['numexpr'] = None
import os, json, hashlib, shutil, platform
from pathlib import Path
os.environ['MPLCONFIGDIR'] = '/tmp/terral-v0-matplotlib'
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

OUT = Path(__file__).resolve().parent
SRC = OUT.parent/'diagnostico_2013_2023'
ROOT = OUT.parent.parent
LO, HI = pd.Timestamp('2013-01-01'), pd.Timestamp('2023-12-31 23:00')
MAIN = ['temperatura','humedad','viento_2m','direccion_2m']
FILES = ['estados_horarios','tramos_anual','trazabilidad_observaciones',
         'sensibilidad_tramos','saltos_revision','huecos','distribuciones',
         'dias_historicos','eventos_por_dias','conteos_candidatos']
DATES = {'estados_horarios':['fecha_sin_zona'],'tramos_anual':['inicio','fin'],
         'trazabilidad_observaciones':['fecha'],'sensibilidad_tramos':['inicio','fin'],
         'saltos_revision':['fecha'],'huecos':['inicio','fin'],
         'dias_historicos':['dia'],'eventos_por_dias':['inicio_dia','fin_dia']}
manifest = []
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def save(df, name): df.to_csv(OUT/f'{name}.csv', index=False, float_format='%.6f')
def load(name):
    p = SRC/'tablas'/f'{name}.csv'
    d = pd.read_csv(p)
    for c in DATES.get(name,[]):
        d[c] = pd.to_datetime(d[c], errors='raise')
        assert d[c].dropna().between(LO,HI).all(), (name,c,'fuera de período')
    manifest.append({'archivo':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'filas':len(d)})
    return d
T = {n:load(n) for n in FILES}
protocol = json.loads((SRC/'protocolo.json').read_text())
assert protocol['periodo'] == ['2013-01-01 00:00:00','2023-12-31 23:00:00']
manifest.append({'archivo':(SRC/'protocolo.json').relative_to(ROOT).as_posix(),'sha256':sha(SRC/'protocolo.json'),'filas':None})
h = T['estados_horarios'].set_index('fecha_sin_zona')
idx = pd.date_range(LO,HI,freq='h')
assert h.index.equals(idx) and len(h)==96408
r = T['trazabilidad_observaciones']
assert not r.duplicated(['fecha','variable']).any()
r['fila_tabla_diagnostico'] = np.arange(len(r))+2
valid = r.pivot(index='fecha',columns='variable',values='valido').reindex(idx).fillna(False).astype(bool)
x = h[MAIN].where(valid[MAIN])
joint = valid[MAIN].all(axis=1)
orig = joint & x.temperatura.gt(11) & x.humedad.lt(30) & x.viento_2m.gt(2) & x.direccion_2m.between(0,180)
assert orig.equals(h.estado.eq('cumple'))
assert (~joint).equals(h.estado.eq('no_evaluable'))
seg = T['tramos_anual'].copy()
assert len(seg)==156 and seg.horas_candidatas.sum()==867
def sid(dt): return 'VCN-INIA-v0-'+dt.strftime('%Y%m%dT%H%M')
def oid(dt): return 'OM-v0-'+dt.strftime('%Y%m%dT%H%M')
def circular(a):
    sn,cs=np.sin(np.deg2rad(a)).mean(),np.cos(np.deg2rad(a)).mean()
    R=np.hypot(sn,cs)
    return (float(np.rad2deg(np.arctan2(sn,cs))%360) if R>1e-12 else np.nan,float(R))
def rank(s): return hashlib.sha256(('terral-v0|'+s).encode()).hexdigest()
def season(m): return 'DJF' if m in (12,1,2) else 'MAM' if m in (3,4,5) else 'JJA' if m in (6,7,8) else 'SON'
cat,links,flags,sensitivity,jumplinks,gaplinks = [],[],[],[],[],[]
unknown = idx[~joint]
covered = pd.Series(0,index=idx)
for _,s in seg.iterrows():
    ident=sid(s.inicio); dates=pd.date_range(s.inicio,s.fin,freq='h'); g=x.loc[dates]
    assert orig.loc[dates].all() and len(dates)==s.horas_candidatas
    covered.loc[dates]+=1
    assert s.inicio==LO or not orig.loc[s.inicio-pd.Timedelta(hours=1)]
    assert s.fin==HI or not orig.loc[s.fin+pd.Timedelta(hours=1)]
    z=r[r.fecha.isin(dates) & r.variable.isin(MAIN)].copy()
    w=z[z.variable.eq('viento_2m')]
    mu,R=circular(g.direccion_2m.values)
    angular=((g.direccion_2m.diff()+180)%360-180).abs()
    row={'id_tramo':ident,'tramo_diagnostico':int(s.tramo),
         'fila_tramos_anual_csv':int(s.tramo)+1,'primera_marca':s.inicio,'ultima_marca':s.fin,
         'horas_candidatas':len(dates),'censura_izq':bool(s.censura_izq),'censura_der':bool(s.censura_der),
         'zona_confirmada':False,'semantica_intervalo_confirmada':False,
         'viento_medio_ms':g.viento_2m.mean(),'max_promedio_horario_ms':g.viento_2m.max(),
         'max_horario_publicado_ms':w['max'].max(),'n_max_publicados':int(w['max'].notna().sum()),
         'direccion_media_circular_grados':mu,'direccion_R':R,'max_cambio_circular_grados':angular.max(),
         'n_horas_sector_borde':int((~g.direccion_2m.between(15,165)).sum()),
         'n_observaciones_principales':len(z),'n_validas_principales':int(z.valido.sum()),
         'porcentaje_datos_min':z.porcentaje_datos.min(),
         'estado':'candidato por criterio histórico, sin confirmar',
         'evidencia_independiente':'pendiente','direccion_exportador_metodo':'desconocido',
         'referencia_horas':'horas_referencia.csv','referencia_fuentes':'trazabilidad_catalogo.csv'}
    for v in ['temperatura','humedad']:
        for stat in ['min','mean','max']: row[f'{v}_{stat}']=getattr(g[v],stat)()
    assert abs(row['viento_medio_ms']-s.viento_medio_ms)<2e-6
    assert abs(row['max_promedio_horario_ms']-s.max_promedio_horario_ms)<2e-6
    cat.append(row)
    for dt in dates: links.append({'id_tramo':ident,'fecha_sin_zona':dt,'fila_estados_horarios_csv':int(idx.get_loc(dt))+2,**h.loc[dt].to_dict()})
    changed=[]
    for cfg,sg in T['sensibilidad_tramos'].groupby('configuracion',sort=True):
        if cfg=='original': continue
        overlap=sg[sg.inicio.le(s.fin)&sg.fin.ge(s.inicio)]
        same=len(overlap)==1 and overlap.iloc[0].inicio==s.inicio and overlap.iloc[0].fin==s.fin and overlap.iloc[0].horas_candidatas==len(dates) and overlap.iloc[0].horas_puente==0
        if not same: changed.append(cfg)
        retained=0
        c=next(c for c in protocol['sensibilidad_prefijada'] if c['id']==cfg)
        for dt in dates:
            q=x.loc[dt]
            condition=q.temperatura>c['t'] and q.humedad<c['rh'] and q.viento_2m>c['v'] and c['dlo']<=q.direccion_2m<=c['dhi']
            if condition and ((overlap.inicio<=dt)&(overlap.fin>=dt)).any(): retained+=1
        sensitivity.append({'id_tramo':ident,'configuracion':cfg,'cambia':not same,'horas_referencia_retenidas':retained,
                            'horas_referencia_no_retenidas':len(dates)-retained,'n_grupos_solapados':len(overlap),
                            'grupos_solapados_json':overlap[['tramo','inicio','fin','horas_candidatas','horas_puente']].to_json(orient='records',date_format='iso')})
    nearby=T['saltos_revision'][T['saltos_revision'].fecha.between(max(LO,s.inicio-pd.Timedelta(hours=1)),min(HI,s.fin+pd.Timedelta(hours=1)))]
    for _,j in nearby.iterrows(): jumplinks.append({'id_tramo':ident,**j.to_dict()})
    dist=np.where(unknown<s.inicio,(s.inicio-unknown).total_seconds()/3600,np.where(unknown>s.fin,(unknown-s.fin).total_seconds()/3600,0))
    nearest=int(np.argmin(dist)) if len(dist) else None
    for dt,d in zip(unknown[dist<=24],dist[dist<=24]): gaplinks.append({'id_tramo':ident,'marca_desconocida':dt,'distancia_h_reloj':float(d)})
    quality=bool(z.porcentaje_datos.lt(100).any() or z.bandera_rango.any() or z.bandera_orden.any() or (~z.problemas.fillna('[]').isin(['[]',''])).any())
    flags.append({'id_tramo':ident,'corto':len(dates)<=2,'una_hora':len(dates)==1,'dos_horas':len(dates)==2,
                  'sensible':bool(changed),'configuraciones_sensibles':';'.join(changed),
                  'salto_previo':bool(len(nearby)),'n_saltos':len(nearby),
                  'direccion_ambigua':bool(row['n_horas_sector_borde']>0 or R<.7 or angular.ge(90).any()),
                  'R_bajo':R<.7,'cambio_angular_90':bool(angular.ge(90).any()),'sector_borde':row['n_horas_sector_borde']>0,
                  'proximo_hueco':bool(len(dist) and dist.min()<=24),
                  'distancia_hueco_min_h':float(dist.min()) if len(dist) else np.nan,
                  'marca_desconocida_mas_cercana':unknown[nearest] if nearest is not None else pd.NaT,
                  'calidad_fuente':quality})
assert covered[orig].eq(1).all() and covered[~orig].eq(0).all()
cat=pd.DataFrame(cat); flags=pd.DataFrame(flags)
flagcols=['corto','sensible','salto_previo','direccion_ambigua','proximo_hueco','calidad_fuente']
flags['alguna_bandera']=flags[flagcols].any(axis=1)
save(cat,'catalogo_referencia'); save(pd.DataFrame(links),'horas_referencia'); save(flags,'banderas')
save(pd.DataFrame(sensitivity),'sensibilidad_por_tramo')
save(pd.DataFrame(jumplinks,columns=['id_tramo','fecha','variable','anterior','actual','cambio']),'saltos_por_tramo')
save(pd.DataFrame(gaplinks,columns=['id_tramo','marca_desconocida','distancia_h_reloj']),'huecos_proximos')
rr=r[r.fecha.isin(idx[orig]) & r.variable.isin(MAIN)].copy()
mapid={d:l['id_tramo'] for l in links for d in [l['fecha_sin_zona']]}
rr.insert(0,'id_tramo',rr.fecha.map(mapid)); save(rr,'trazabilidad_catalogo')
for name in ['dias_historicos','eventos_por_dias']: save(T[name],name)
dayslinks=pd.DataFrame(links)[['id_tramo','fecha_sin_zona']]; dayslinks['dia']=dayslinks.fecha_sin_zona.dt.normalize()
save(dayslinks.groupby(['id_tramo','dia']).size().rename('horas_candidatas').reset_index(),'relacion_tramos_dias')
reconciliation=[]
for year in range(2013,2024):
    hm=idx.year==year; a=cat[cat.primera_marca.dt.year.eq(year)]
    table=T['conteos_candidatos']; expected=table[table.aplicacion.eq('anual')&table.escala.eq('ano')&table.grupo.astype(str).eq(str(year))].iloc[0]
    assert int(orig[hm].sum())==expected.cumple
    reconciliation.append({'ano':year,'tramos':len(a),'horas_catalogo':int(a.horas_candidatas.sum()),'horas_diagnostico':int(expected.cumple),
                           'no_cumple':int(h.estado[hm].eq('no_cumple').sum()),'no_evaluable':int((~joint)[hm].sum()),'diferencia':0})
save(pd.DataFrame(reconciliation),'reconciliacion_anual')
save(pd.DataFrame([{'bandera':c,'tramos':int(flags[c].sum()),'horas_candidatas_en_tramos':int(cat.loc[flags[c].values,'horas_candidatas'].sum())} for c in flagcols+['alguna_bandera','una_hora','dos_horas']]),'resumen_banderas')

# Referencias exploratorias: cuatro marcas conjuntas válidas, lags exactos.
continuous=joint.copy()
for lag in range(1,4): continuous &= joint.shift(lag,fill_value=False)
delta=x[['temperatura','humedad','viento_2m']]-x[['temperatura','humedad','viento_2m']].shift(3)
refs=[]; qlookup={}; medlookup={}
for (month,hour),g in delta[continuous].groupby([idx[continuous].month,idx[continuous].hour]):
    for v in delta.columns:
        row={'mes':month,'hora_llegada':hour,'variable':v,'n':len(g),'q10':g[v].quantile(.1),'q90':g[v].quantile(.9)}
        refs.append(row); qlookup[(month,hour,v)]=row
dist=T['distribuciones']; dist=dist[dist.escala.eq('mes_hora') & dist.variable.isin(delta.columns)]
for _,d in dist.iterrows(): medlookup[(int(d.grupo[:2]),int(d.grupo[3:]),d.variable)]={'mediana':d.q50,'n':d.n}
save(pd.DataFrame(refs),'referencias_cambios_mes_hora')
save(dist,'referencias_estado_mes_hora')
no_orig=~orig
for lag in range(1,4): no_orig &= ~orig.shift(lag,fill_value=False)
eligible=[]
def fails(q):
    return ';'.join(c for c,b in [('T>11',q.temperatura>11),('HR<30',q.humedad<30),('V>2',q.viento_2m>2),('D_en_0_180',0<=q.direccion_2m<=180)] if not b)
for dt in idx[continuous & no_orig]:
    m,hh=dt.month,dt.hour
    qr=[qlookup[(m,hh,v)] for v in delta.columns]
    if min(q['n'] for q in qr)<100: continue
    limits=[max(2,qr[0]['q90']),min(-10,qr[1]['q10']),max(.5,qr[2]['q90'])]
    dv=delta.loc[dt]; q=x.loc[dt]; meds=[medlookup[(m,hh,v)]['mediana'] for v in delta.columns]
    if dv.temperatura>=limits[0] and dv.humedad<=limits[1] and dv.viento_2m>=limits[2] and q.temperatura>=meds[0] and q.humedad<=meds[1] and q.viento_2m>=meds[2]:
        eligible.append({'id_omision':oid(dt),'primera_marca':dt-pd.Timedelta(hours=3),'ultima_marca':dt,'llegada':dt,
                         'ano':dt.year,'mes':m,'epoca':season(m),'fuera_abril_agosto':not 4<=m<=8,
                         **q.to_dict(),'dT_3h':dv.temperatura,'dHR_3h':dv.humedad,'dV_3h':dv.viento_2m,
                         'limite_dT':limits[0],'limite_dHR':limits[1],'limite_dV':limits[2],
                         'n_referencia_cambios':min(z['n'] for z in qr),
                         'mediana_T':meds[0],'mediana_HR':meds[1],'mediana_V':meds[2],
                         'condiciones_fallidas_llegada':fails(q),'estado':'posible omisión para revisión; sin etiqueta'})
elig=pd.DataFrame(eligible)
assert len(elig)>0, 'Procedimiento sin casos: informar sin retocar reglas'
save(elig,'llegadas_exploratorias')
groupnum=(elig.llegada.diff()>pd.Timedelta(hours=6)).cumsum()
groups=[]
for number,g in elig.groupby(groupnum):
    z=g.iloc[(len(g)-1)//2].to_dict()
    z.update({'grupo_transicion':int(number)+1,'n_llegadas_grupo':len(g),'primera_llegada_grupo':g.llegada.iloc[0],'ultima_llegada_grupo':g.llegada.iloc[-1]})
    groups.append(z)
groups=pd.DataFrame(groups); groups['orden_sha256']=groups.id_omision.map(rank)
om=groups.sort_values('orden_sha256').groupby(['ano','mes'],sort=True).head(1).sort_values('llegada').reset_index(drop=True)
save(groups,'grupos_exploratorios'); save(om,'posibles_omisiones')
omhours=[]
for _,s in om.iterrows():
    for dt in pd.date_range(s.primera_marca,s.ultima_marca,freq='h'):
        omhours.append({'id_omision':s.id_omision,'fecha_sin_zona':dt,'condiciones_fallidas':fails(x.loc[dt]),'estado_original':h.loc[dt,'estado'],
                        'fila_estados_horarios_csv':idx.get_loc(dt)+2,**x.loc[dt].to_dict()})
omh=pd.DataFrame(omhours); assert omh.estado_original.eq('no_cumple').all()
save(omh,'condiciones_omisiones_horarias')
omtrace=r[r.fecha.isin(omh.fecha_sin_zona)&r.variable.isin(MAIN)].merge(omh[['id_omision','fecha_sin_zona']],left_on='fecha',right_on='fecha_sin_zona')
save(omtrace,'trazabilidad_omisiones')

# Muestra estratificada determinista. Intensidad nunca entra al ranking.
base=cat.merge(flags,on='id_tramo'); pool=[]
for _,s in base.iterrows(): pool.append({'id_objeto':s.id_tramo,'ancla':s.primera_marca,'ano':s.primera_marca.year,'epoca':season(s.primera_marca.month),'ambigua':bool(s.alguna_bandera),'horas_objeto':s.horas_candidatas})
pool=pd.DataFrame(pool)
opool=pd.DataFrame([{'id_objeto':s.id_omision,'ancla':s.llegada,'ano':s.ano,'epoca':s.epoca,'ambigua':False,'horas_objeto':4} for _,s in om.iterrows()])
selected=[]; epoch_counts={e:0 for e in ['DJF','MAM','JJA','SON']}
def window(anchor,category):
    start=anchor-pd.Timedelta(hours=18 if category=='posible_omision' else 9)
    start=max(LO,min(start,HI-pd.Timedelta(hours=47)))
    return start,start+pd.Timedelta(hours=47)
for category,quota,source,one_year in [('referencia',11,pool,True),('ambigua',8,pool[pool.ambigua],False),('posible_omision',11,opool,True)]:
    yc={y:0 for y in range(2013,2024)}
    for step in range(quota):
        choices=[]
        for _,p in source.iterrows():
            if any(z['id_objeto']==p.id_objeto for z in selected) or (one_year and yc[p.ano]>0): continue
            a,b=window(p.ancla,category)
            if any(a<=z['fin_ventana'] and b>=z['inicio_ventana'] for z in selected): continue
            choices.append((yc[p.ano],epoch_counts[p.epoca],rank(p.id_objeto),p,a,b))
        if not choices: break
        _,_,key,p,a,b=min(choices,key=lambda z:z[:3]); yc[p.ano]+=1; epoch_counts[p.epoca]+=1
        selected.append({'id_revision':'REV-v0-'+p.id_objeto,'categoria':category,**p.to_dict(),
                         'inicio_ventana':a,'fin_ventana':b,'n_marcas':48,'orden_sha256':key,
                         'estado_contraste':'pendiente','grafico':'graficos/'+p.id_objeto+'.png'})
selection=pd.DataFrame(selected); assert len(selection)<=30
save(selection,'seleccion_revision')
save(selection.groupby(['categoria','ano','epoca']).size().rename('ventanas').reset_index(),'distribucion_seleccion')
plotdata=[]
windmax=r[r.variable.eq('viento_2m')].set_index('fecha')['max'].reindex(idx).where(valid.viento_2m)
for _,s in selection.iterrows():
    g=x.loc[s.inicio_ventana:s.fin_ventana]
    z=g.copy(); z['max_horario_publicado_ms']=windmax.loc[g.index]; z['estado_original']=h.estado.loc[g.index]
    z['id_revision']=s.id_revision; z.index.name='fecha_sin_zona'; plotdata.append(z.reset_index())
    fig,axes=plt.subplots(4,1,figsize=(12,9),sharex=True)
    for ax,v,label in zip(axes,MAIN,['T (°C)','HR (%)','V a 2 m (m/s)','Dirección (°)']):
        if v=='direccion_2m':
            ax.scatter(g.index,g[v],s=13,color='tab:purple'); ax.set_ylim(-5,365); ax.set_yticks([0,90,180,270,360])
        else: ax.plot(g.index,g[v],'.-',lw=.85,ms=4,label='promedio horario')
        ax.set_ylabel(label); ax.grid(alpha=.25)
        if v=='viento_2m':
            ax.plot(g.index,windmax.loc[g.index],'.--',lw=.75,ms=3,label='máximo horario publicado'); ax.legend(loc='upper left',fontsize=8,ncol=2)
        for dt in g.index[orig.loc[g.index]]: ax.axvspan(dt-pd.Timedelta(minutes=20),dt+pd.Timedelta(minutes=20),color='orange',alpha=.13)
        for dt in g.index[~joint.loc[g.index]]: ax.axvspan(dt-pd.Timedelta(minutes=30),dt+pd.Timedelta(minutes=30),color='gray',alpha=.2)
        ax.axvline(s.ancla,color='black',ls=':',lw=.7)
    axes[0].set_title(f'{s.id_objeto} · {s.categoria} · sin confirmación\n48 marcas horarias; naranja: cumple; gris: desconocida; línea vertical: ancla de selección')
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%d/%m %H:%M')); axes[-1].xaxis.set_major_locator(mdates.HourLocator(interval=6))
    axes[-1].set_xlabel('Reloj registrado, zona e inicio/cierre de agregación sin confirmar. Ninguna serie acredita ráfaga.')
    fig.autofmt_xdate(); fig.tight_layout(); fig.savefig(OUT/s.grafico,dpi=140); plt.close(fig)
save(pd.concat(plotdata,ignore_index=True),'datos_graficos')
save(pd.DataFrame(manifest),'manifiesto_entradas')
assert all(sha(ROOT/m['archivo'])==m['sha256'] for m in manifest)
audit={'periodo':[str(LO),str(HI)],'horas_esperadas':len(idx),'cumple':int(orig.sum()),'no_cumple':int(h.estado.eq('no_cumple').sum()),'no_evaluable':int((~joint).sum()),
       'tramos':len(cat),'horas_catalogo':int(cat.horas_candidatas.sum()),'dias_candidatos':int(T['dias_historicos'].horas_candidatas.gt(0).sum()),
       'eventos_por_dias_anual':int(T['eventos_por_dias'].aplicacion.eq('anual').sum()),'censuras':int((cat.censura_izq|cat.censura_der).sum()),
       'banderas':{c:int(flags[c].sum()) for c in flagcols+['alguna_bandera','una_hora','dos_horas']},
       'llegadas_exploratorias':len(elig),'grupos_exploratorios':len(groups),'omisiones_mensuales':len(om),'omisiones_fuera_abril_agosto':int(om.fuera_abril_agosto.sum()),
       'ventanas_revision':len(selection),'seleccion_categorias':selection.categoria.value_counts().to_dict(),'seleccion_epocas':selection.epoca.value_counts().to_dict(),
       'fuentes_intactas':True,'zona':None,'imputaciones':0,'entrenamientos':0,'confirmaciones_automaticas':0,
       'protocolo_sha256':sha(OUT/'protocolo.md'),'script_sha256':sha(Path(__file__)),
       'versiones':{'python':platform.python_version(),'pandas':pd.__version__,'numpy':np.__version__,'matplotlib':matplotlib.__version__}}
(OUT/'comprobaciones.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(audit,ensure_ascii=False,indent=2))
