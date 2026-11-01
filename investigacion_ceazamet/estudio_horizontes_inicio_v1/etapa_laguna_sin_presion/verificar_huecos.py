"""Verificación independiente de exclusión de presión y antecedentes/soporte internos."""
import estudio as e
import sys,json
from pathlib import Path
import numpy as np
import pandas as pd

def verify(out):
 e.OUT=Path(out);x,state,cat,f,cols,yy,ids,future,ds=e.prepare();p,pe=e.s.load_extra([]);checks={}
 def ck(n,v):assert bool(v),n;checks[n]=True
 ck('whitelist_exacta',set(e.s.EXPECTED)=={'LAGELTA','LAGELHR','LAGELVV10','LAGELDV10'})
 ck('columnas_35_41_66_72',[len(cols[a]) for a in 'ABCD']==[35,41,66,72])
 for value in [np.nan,0.,999999.]:
  altered=pe.copy();altered['presion']=value;altered['LAGELPA']=value
  ck('invariancia_presion_sintetica_'+str(value),e.s.allfeatures(x,p,altered).equals(f))
 ck('sin_columnas_presion_laguna',not any('LAG_presion' in c or 'LAGELPA' in c for c in f))
 # Independent seven-mark input and 24-mark future by timestamp reindex, no rolling.
 present=x.notna().all(axis=1)&p.notna()&pe.notna().all(axis=1);idx=e.b.IDX
 history=pd.Series(True,index=idx)
 for k in range(7):history &= present.reindex(idx-pd.Timedelta(hours=k),fill_value=False).to_numpy()
 ck('antecedentes_solo_canales_autorizados',history.equals(e.COMPLETE))
 starts=cat[cat.inicio_conocido];uncertain=set(cat.loc[~cat.inicio_conocido,'inicio']);unknown=state.eq(-1)
 def independent(lo,hi):
  ok=history&state.eq(0)&(idx-pd.Timedelta(hours=6)>=lo)&(idx+pd.Timedelta(hours=24)<=hi)
  for k in range(1,25):
   times=idx+pd.Timedelta(hours=k);ok &= ~unknown.reindex(times,fill_value=True).to_numpy()&~times.isin(uncertain)
  for r in cat.itertuples():
   if r.inicio<lo<=r.fin or r.inicio<=hi<r.fin:ok &= ~((idx-pd.Timedelta(hours=6)<=r.fin)&(idx+pd.Timedelta(hours=24)>=r.inicio))
  return idx[ok]
 for bl,ty,vs,ve in e.b.BLOCKS:
  for vy in [ty-1,ty]:
   for role,lo,hi in [('train',pd.Timestamp('2013-01-01'),pd.Timestamp(f'{vy-1}-12-31 23:00')),('oof',pd.Timestamp(f'{vy}-01-01'),pd.Timestamp(f'{vy}-12-31 23:00'))]:
    expected=independent(lo,hi)
    for h in e.H:
     d=e.dataset(f,state,cat,yy,ids,future,lo,hi,h)
     ck(f'soporte_interno_{bl}_{vy}_{role}_{h}',expected.equals(d.index))
  for role in ['train','val']:
   for h in e.H:ck(f'comun_{bl}_{role}_{h}',ds[bl,role,h].index.equals(ds[bl,role,24].index))
 prior=json.loads((e.OUT/'manifiesto_fuentes_previo.json').read_text());ck('manifiesto_antes_entrenamiento',prior==json.loads((e.OUT/'registro_preentrenamiento.json').read_text())['fuentes']==e.sources())
 e.js(e.OUT/'verificacion_huecos.json',{'resultado':'conforme','comprobaciones':checks,'limite':'presión sintética, sin leer ni evaluar contribución de mediciones LAGELPA; soporte interno independiente, modelos internos contrastados por verificador principal'})
 print('Sensores, presión excluida y purgas internas conformes',flush=True)
if __name__=='__main__':verify(sys.argv[1])
