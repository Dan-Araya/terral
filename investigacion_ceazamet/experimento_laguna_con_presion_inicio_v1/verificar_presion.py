#!/usr/bin/env python3
"""Reconstrucción separada de pérdidas e intervalos de presión y máscara previa."""
import os,sys,json,hashlib
os.environ['OPENBLAS_NUM_THREADS']='1'; sys.modules['numexpr']=None; sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np
import pandas as pd
BASE=Path(__file__).resolve().parent; ROOT=BASE.parent
OUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else BASE
checks={}
def check(k,v):
 assert v,k
 checks[k]=True
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
idx=pd.date_range('2013-01-01','2023-12-31 23:00',freq='h')
raw=pd.concat([z[z.sensor.eq('LAGELPA')] for z in pd.read_csv(ROOT/'estaciones_complementarias/la_laguna_elqui/derivados/horarias.csv',chunksize=50000,dtype={'sensor':str})])
valid=pd.Series(raw.utilizable_revision.eq(1).to_numpy(),index=pd.to_datetime(raw.fecha_sin_zona)).reindex(idx,fill_value=False)
check('66569_horas_utilizables',valid.sum()==66569)
mask=pd.read_csv(OUT/'tablas/mascaras_horarias.csv',parse_dates=['emision']).set_index('emision')
check('mascara_presion_exacta',mask.index.equals(idx) and np.array_equal(mask.LAG_presion_valida,valid.astype(int)))
pwin=pd.Series(True,index=idx)
for k in range(7): pwin &= valid.shift(k,fill_value=False)
check('ventanas_siete_horas',np.array_equal(mask.LAGELPA_ventana7_valida,pwin.astype(int)))
oldwin=mask.entrada_sin_presion_valida.eq(1); newwin=oldwin&pwin
check('entradas_interseccion',np.array_equal(mask.entrada_con_presion_valida,newwin.astype(int)))
extra=pd.read_csv(OUT/'tablas/elegibilidad_adicional.csv',parse_dates=['emision']).fillna({'id_inicio_objetivo':''})
previous=pd.read_csv(ROOT/'experimento_laguna_sin_presion_inicio_v1/tablas/ejemplos_comunes.csv',parse_dates=['emision']).fillna({'id_inicio_objetivo':''})
comparison=pd.read_csv(OUT/'tablas/comparacion_soporte_anterior.csv')
summary=pd.read_csv(OUT/'tablas/presion_soporte_por_ano_particion.csv')
intervals=pd.read_csv(OUT/'tablas/intervalos_presion_por_ano_particion.csv',parse_dates=['inicio','fin'])
def ids(d): return {s for v in d.id_inicio_objetivo for s in v.split('|') if s}
for (h,bl,role),d in extra.groupby(['horizonte_h','bloque','rol']):
 a=d[d.emision.isin(idx[oldwin])]; z=d[d.emision.isin(idx[newwin])]; lost=a[~a.emision.isin(z.emision)]
 prev=previous[(previous.horizonte_h==h)&previous.bloque.eq(bl)&previous.rol.eq(role)]
 check(f'anterior_{h}_{bl}_{role}',np.array_equal(a.emision,prev.emision) and np.array_equal(a.objetivo,prev.y) and np.array_equal(a.id_inicio_objetivo,prev.id_inicio_objetivo))
 check(f'comun_{h}_{bl}_{role}',np.array_equal(z.emision,d[d.motivo_primario.eq('incluida')].emision))
 r=comparison[(comparison.horizonte_h==h)&comparison.bloque.eq(bl)&comparison.rol.eq(role)].iloc[0]
 cols=['elegibles_sin_presion','elegibles_con_presion','ventanas_perdidas','positivos_sin_presion','positivos_con_presion','positivos_perdidos','inicios_sin_presion','inicios_con_presion','inicios_afectados','inicios_completamente_perdidos']
 vals=[len(a),len(z),len(lost),a.objetivo.sum(),z.objetivo.sum(),lost.objetivo.sum(),len(ids(a)),len(ids(z)),len(ids(lost)),len(ids(a)-ids(z))]
 check(f'perdidas_{h}_{bl}_{role}',np.array_equal(r[cols],vals))
for r in summary.itertuples():
 t=idx[idx.year==r.ano]
 check(f'entradas_{r.Index}',r.horas_calendario==len(t) and r.presion_horas_utilizables==valid.loc[t].sum() and r.presion_horas_excluidas==(~valid.loc[t]).sum() and r.ventanas_presion_incompletas==(~pwin.loc[t]).sum() and r.entradas_sin_presion==oldwin.loc[t].sum() and r.entradas_con_presion==newwin.loc[t].sum() and r.entradas_perdidas_por_presion==(oldwin&~newwin).loc[t].sum())
 if r.bloque!='global':
  d=extra[(extra.horizonte_h==r.horizonte_h)&extra.bloque.eq(r.bloque)&extra.rol.eq(r.rol)&extra.emision.dt.year.eq(r.ano)]
  a=d[d.emision.isin(idx[oldwin])]; z=d[d.emision.isin(idx[newwin])]; lost=a[~a.emision.isin(z.emision)]
  vals=[len(a),len(z),len(lost),a.objetivo.sum(),z.objetivo.sum(),lost.objetivo.sum(),len(ids(a)),len(ids(z)),len(ids(lost)),len(ids(a)-ids(z))]
  cols=['elegibles_sin_presion','elegibles_con_presion','ventanas_elegibles_perdidas','positivos_sin_presion','positivos_con_presion','positivos_perdidos','inicios_sin_presion','inicios_con_presion','inicios_afectados','inicios_completamente_perdidos']
  check(f'elegibilidad_anual_{r.Index}',np.array_equal([getattr(r,c) for c in cols],vals))
# Interval lists must cover every calendar hour exactly once per scope and match raw quality.
for (bl,role,year),d in intervals.groupby(['bloque','rol','ano']):
 t=idx[idx.year==year]; rebuilt=pd.Series(-1,index=t); previous_end=None; previous_status=None
 for r in d.sort_values('inicio').itertuples():
  tt=pd.date_range(r.inicio,r.fin,freq='h')
  check(f'intervalo_{r.Index}',len(tt)==r.horas and rebuilt.loc[tt].eq(-1).all())
  value=int(r.estado=='utilizable'); rebuilt.loc[tt]=value
  check(f'intervalo_maximal_{r.Index}',previous_end is None or r.inicio!=previous_end+pd.Timedelta(hours=1) or r.estado!=previous_status)
  previous_end=r.fin; previous_status=r.estado
 check(f'intervalos_exactos_{bl}_{role}_{year}',np.array_equal(rebuilt,valid.loc[t].astype(int)))
cols=json.loads((OUT/'predictores.json').read_text())
check('columnas_35_41_66_72_72_78',[len(cols[a]) for a in 'ABCDEF']==[35,41,66,72,72,78])
pcols=['LAG_presion','LAG_presion_lag1','LAG_presion_delta1','LAG_presion_lag3','LAG_presion_delta3','LAG_presion_media_previa6']
check('aporte_solo_seis_transformaciones',cols['E']==cols['C']+pcols and cols['F']==cols['D']+pcols and all(not any(c.startswith('LAG_presion') for c in cols[a]) for a in 'ABCD'))
reg=json.loads((OUT/'registro_preentrenamiento.json').read_text())
for n,h in reg['tablas_previas_sha256'].items(): check('registro_mascara_'+n,sha(OUT/'tablas'/n)==h)
ci=pd.read_csv(OUT/'tablas/intervalos_pareados.csv'); pairs=pd.read_csv(OUT/'tablas/diferencias_por_particion.csv'); contrasts=['E-C','F-D','C-A','D-B','E-A','F-B']
check('todos_contrastes_IC',set(ci[ci.contraste.str.contains('-')].contraste)==set(contrasts))
check('todos_contrastes_particiones',set(pairs.contraste)==set(contrasts))
# Independently reconstruct point differences for every partition and all original metrics.
hm=pd.read_csv(OUT/'tablas/metricas_horarias.csv'); am=pd.read_csv(OUT/'tablas/metricas_avisos.csv')
for r in pairs.itertuples():
 table=hm if r.metrica in ['AP','Brier'] else am
 d=table[(table.horizonte_h==r.horizonte_h)&table.bloque.eq(r.bloque)&table.epoca.eq('ALL')]
 if table is am: d=d[d.politica.eq(r.politica)]
 d=d.set_index('modelo'); new,old=r.contraste.split('-')
 check(f'delta_{r.Index}',np.isclose(d.loc[new,r.metrica]-d.loc[old,r.metrica],r.delta,rtol=3e-8,atol=1e-10,equal_nan=True))
(OUT/'verificacion_presion.json').write_text(json.dumps({'resultado':'conforme','n_comprobaciones':len(checks),'comprobaciones':checks,'limites':'Fuentes derivadas auditadas compartidas. No verifica modelo, calibración ni referencia instrumental.'},indent=2,ensure_ascii=False)+'\n')
print(f'Presión, intervalos, pérdidas y contrastes: {len(checks)} controles conformes.')
