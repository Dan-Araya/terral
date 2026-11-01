#!/usr/bin/env python3
"""Reconstruye diagnósticos de huecos y conservación; sin entrenamiento."""
import sys,os,json,importlib.util
os.environ['OPENBLAS_NUM_THREADS']='1'; sys.modules['numexpr']=None; sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np
import pandas as pd
BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('exp',BASE/'ejecutar.py'); e=importlib.util.module_from_spec(spec); spec.loader.exec_module(e)
OUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else BASE
checks={}
def check(name,v):
 assert v,name
 checks[name]=True
e.b.save=lambda *args:None
x,state,cat,_=e.b.ingest(); p,pe=e.load_extra([])
q=pd.read_csv(OUT/'tablas/elegibilidad_adicional.csv',parse_dates=['emision']).fillna({'id_inicio_objetivo':''})
impact=pd.read_csv(OUT/'tablas/efecto_huecos_laguna.csv'); gaps=pd.read_csv(OUT/'tablas/huecos_por_sensor.csv',parse_dates=['inicio','fin'])
for v in pe:
 missing=pe[v].isna().to_numpy(); edges=np.diff(np.r_[False,missing,False].astype(int)); lo=np.where(edges==1)[0]; hi=np.where(edges==-1)[0]-1
 z=gaps[gaps.variable.eq(v)]
 check('huecos_'+v,np.array_equal(z.inicio,e.IDX[lo]) and np.array_equal(z.fin,e.IDX[hi]) and np.array_equal(z.horas,hi-lo+1))
cov=pd.read_csv(OUT/'tablas/cobertura_anual_laguna.csv')
for r in cov.itertuples():
 z=pe.loc[pe.index.year==r.ano,r.variable]
 check(f'cobertura_{r.ano}_{r.variable}',len(z)==r.horas_calendario and z.notna().sum()==r.utilizables and z.isna().sum()==r.no_utilizables and z.eq(0).sum()==r.ceros_validos)
def ids(z): return {c for val in z.loc[z.objetivo.eq(1),'id_inicio_objetivo'] for c in val.split('|') if c}
for (h,bl,role),rows in q.groupby(['horizonte_h','bloque','rol']):
 times=pd.DatetimeIndex(rows.emision); common=rows.motivo_primario.eq('incluida').to_numpy()
 # For each emission inspect raw masked series at all seven times, independent of rolling.
 absent={v:np.any(np.stack([pe[v].reindex(times-pd.Timedelta(hours=k)).isna().to_numpy() for k in range(7)]),axis=0) for v in pe}
 inia=np.all(np.stack([p.reindex(times-pd.Timedelta(hours=k)).notna().to_numpy() for k in range(7)]),axis=0)
 for cause,bad in absent.items():
  rest=inia.copy()
  for v in pe:
   if v!=cause: rest &= ~absent[v]
  lost=rest&bad; recovered=common|lost
  r=impact[(impact.horizonte_h==h)&impact.bloque.eq(bl)&impact.rol.eq(role)&impact.causa.eq(cause)].iloc[0]
  vals=[bad.sum(),rows.loc[bad,'objetivo'].sum(),len(ids(rows.loc[bad])),lost.sum(),rows.loc[lost,'objetivo'].sum(),len(ids(rows)-ids(rows.loc[~bad])),len(ids(rows.loc[recovered])-ids(rows.loc[common]))]
  cols=['ventanas_afectadas','positivos_afectados','inicios_afectados','perdidas_marginales_horas','perdidas_marginales_positivos','inicios_perdidos_sin_otras_oportunidades','inicios_recuperables_marginalmente']
  check(f'efecto_{h}_{bl}_{role}_{cause}',np.array_equal(vals,r[cols].to_numpy()))
 members=pd.read_csv(OUT/'tablas/ejemplos_comunes.csv',parse_dates=['emision']).fillna({'id_inicio_objetivo':''}) if 'members' not in globals() else members
 z=members[(members.horizonte_h==h)&members.bloque.eq(bl)&members.rol.eq(role)]
 check(f'ejemplos_{h}_{bl}_{role}',np.array_equal(z.emision,rows.loc[common,'emision']) and np.array_equal(z.y,rows.loc[common,'objetivo']) and np.array_equal(z.id_inicio_objetivo,rows.loc[common,'id_inicio_objetivo']) and z.brazos.eq('A|B|C|D|E|F').all())
for row in json.loads((BASE/'conservacion_previa.json').read_text()): check('conservacion_'+row['archivo'],e.b.digest(e.b.ROOT/row['archivo'])==row['sha256'])
(OUT/'verificacion_huecos.json').write_text(json.dumps({'resultado':'conforme','comprobaciones':checks,'limites':'Reconstrucción independiente de ventanas y conteos; ingestión y máscaras de carga compartidas. No acredita causas instrumentales de los huecos.'},indent=2,ensure_ascii=False)+'\n')
print('Huecos, soporte, eventos y conservación conformes.')
