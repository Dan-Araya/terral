"""Verificación separada de cobertura y pérdidas desde siete marcas por emisión."""
import estudio as e
from pathlib import Path
import sys
import numpy as np
import pandas as pd

def verify(out):
 e.OUT=Path(out);e.setup();p,pe=e.s.load_extra([]);checks={}
 def ck(n,v):assert bool(v),n;checks[n]=True
 q=pd.read_csv(e.OUT/'tablas/elegibilidad_huanta.csv',parse_dates=['emision']).fillna({'id_inicio_objetivo':''})
 impact=pd.read_csv(e.OUT/'tablas/efecto_huecos_huanta.csv');cov=pd.read_csv(e.OUT/'tablas/cobertura_anual_huanta.csv');gaps=pd.read_csv(e.OUT/'tablas/huecos_por_sensor.csv',parse_dates=['inicio','fin'])
 for r in cov.itertuples():
  z=pe.loc[pe.index.year==r.ano,r.variable];ck(f'cobertura_{r.ano}_{r.sensor}',len(z)==r.horas_calendario and z.notna().sum()==r.utilizables and z.eq(0).sum()==r.ceros_validos)
 for variable in pe:
  z=gaps[gaps.variable.eq(variable)];expected=pd.Series(False,index=pe.index)
  for r in z.itertuples():expected.loc[r.inicio:r.fin]=True;ck(f'duracion_{variable}_{r.Index}',r.horas==int((r.fin-r.inicio)/pd.Timedelta(hours=1))+1)
  ck('huecos_'+variable,np.array_equal(expected,pe[variable].isna()))
 long=gaps[gaps.variable.eq('temperatura')].sort_values('horas').iloc[-1]
 getids=lambda z:{i for value in z.id_inicio_objetivo for i in value.split('|') if i}
 for (bl,role,h),z in q.groupby(['bloque','rol','horizonte_h']):
  times=pd.DatetimeIndex(z.emision)
  bad={v:np.stack([pe[v].reindex(times-pd.Timedelta(hours=k)).isna() for k in range(7)]).any(axis=0) for v in pe}
  bad['hueco_largo_T']=np.stack([((times-pd.Timedelta(hours=k)>=long.inicio)&(times-pd.Timedelta(hours=k)<=long.fin)) for k in range(7)]).any(axis=0)
  included=~np.stack([bad[v] for v in pe]).any(axis=0)
  ck(f'inclusion_{bl}_{role}_{h}',np.array_equal(included,z.incluida))
  support=pd.read_csv(e.OUT/f'soportes/{bl}_{role}_{h}.csv',parse_dates=['emision'])
  ck(f'soporte_{bl}_{role}_{h}',list(support.emision)==list(z.loc[included,'emision']))
  for cause,mask in bad.items():
   ck(f'flag_{bl}_{role}_{h}_{cause}',np.array_equal(mask,z['ausencia_'+cause]))
   rest=np.ones(len(z),bool)
   for v in pe:
    if v!=('temperatura' if cause=='hueco_largo_T' else cause):rest &= ~bad[v]
   for year in sorted(set(times.year)):
    yr=times.year==year;g=z.loc[yr];affected=mask[yr];lost=(rest&mask)[yr];common=included[yr];recover=common|lost
    r=impact[impact.bloque.eq(bl)&impact.rol.eq(role)&impact.horizonte_h.eq(h)&impact.ano.eq(year)&impact.causa.eq(cause)].iloc[0]
    values=[len(g),common.sum(),g.objetivo.sum(),g.loc[common].objetivo.sum(),len(getids(g)),len(getids(g.loc[common])),affected.sum(),g.loc[affected].objetivo.sum(),len(getids(g.loc[affected])),lost.sum(),g.loc[lost].objetivo.sum(),len(getids(g)-getids(g.loc[~affected])),len(getids(g.loc[recover])-getids(g.loc[common]))]
    cols=['base_horas','comun_horas','positivos_base','positivos_comun','inicios_base','inicios_comun','ventanas_afectadas','positivos_afectados','inicios_afectados','perdidas_marginales_horas','perdidas_marginales_positivos','inicios_perdidos_sin_otras_oportunidades','inicios_recuperables_marginalmente']
    ck(f'perdidas_{bl}_{role}_{h}_{year}_{cause}',np.array_equal(values,r[cols].to_numpy()))
 e.js(e.OUT/'verificacion_huecos.json',{'resultado':'conforme','comprobaciones':checks,'limite':'lectura compartida, ventanas reconstruidas desde cada una de las siete marcas; causas no excluyentes'})
 print('Verificación de huecos conforme',len(checks),flush=True)
if __name__=='__main__':verify(sys.argv[1])
