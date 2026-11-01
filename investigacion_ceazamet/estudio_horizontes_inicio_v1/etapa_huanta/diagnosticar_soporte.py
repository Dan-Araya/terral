"""Descomposición descriptiva de pérdidas, sin modificar elegibilidad ni ajustar."""
import estudio as e
from pathlib import Path
import sys
import numpy as np
import pandas as pd

def diagnose(out):
 e.OUT=Path(out); x,state,cat,f,cols,yy,ids,future,ds=e.prepare()
 p,pe=e.s.load_extra([])
 cov=[];gaps=[]
 for sid,(v,height) in e.s.EXPECTED.items():
  for year,z in pe[v].groupby(pe.index.year):cov.append(dict(ano=year,sensor=sid,variable=v,altura_m=height,horas_calendario=len(z),utilizables=z.notna().sum(),no_utilizables=z.isna().sum(),ceros_validos=z.eq(0).sum()))
  edges=np.diff(np.r_[False,pe[v].isna(),False].astype(int)); a=np.flatnonzero(edges==1);b=np.flatnonzero(edges==-1)-1
  gaps.extend(dict(sensor=sid,variable=v,inicio=e.b.IDX[i],fin=e.b.IDX[j],horas=j-i+1) for i,j in zip(a,b))
 e.save(pd.DataFrame(cov),e.OUT/'tablas/cobertura_anual_huanta.csv');e.save(pd.DataFrame(gaps),e.OUT/'tablas/huecos_por_sensor.csv')
 long=pd.DataFrame(gaps).query("sensor=='LLHTA'").sort_values('horas').iloc[-1]
 assert long.inicio==pd.Timestamp('2015-04-28 11:00') and long.fin==pd.Timestamp('2016-04-30 23:00') and long.horas==8845
 history={v:pe[v].notna().rolling(7,min_periods=7).sum().eq(7) for v in pe}
 own=p.notna().rolling(7,min_periods=7).sum().eq(7)
 lg=pd.Series((e.b.IDX>=long.inicio)&(e.b.IDX<=long.fin),index=e.b.IDX).rolling(7,min_periods=1).max().eq(1)
 # Counterfactual support keeps the maximum future, partition boundaries and INIA history.
 complete=e.COMPLETE.copy();e.COMPLETE=e.BASIC&own
 base={}
 for bl,ty,vs,ve in e.b.BLOCKS:
  for role,lo,hi in [('train','2013-01-01',f'{ty}-12-31 23:00'),('val',f'{vs}-01-01',f'{ve}-12-31 23:00')]:
   for h in e.H:base[bl,role,h]=e.dataset(f[cols['B']],state,cat,yy,ids,future,lo,hi,h)
 e.COMPLETE=complete
 rows=[]; details=[]
 getids=lambda z:{i for value in z.id_inicio_objetivo for i in value.split('|') if i}
 for (bl,role,h),d in base.items():
  common=d.index.isin(ds[bl,role,h].index)
  bad={v:~history[v].reindex(d.index).to_numpy() for v in pe};bad['hueco_largo_T']=lg.reindex(d.index).to_numpy()
  for year in sorted(set(d.index.year)):
   yr=d.index.year==year;z=d.loc[yr]; keep=common[yr]
   for cause,mask in bad.items():
    affected=mask[yr]; rest=np.ones(len(d),bool)
    for v in pe:
     if v!=('temperatura' if cause=='hueco_largo_T' else cause):rest &= ~bad[v]
    lost=(rest&mask)[yr]; recovered=keep|lost
    rows.append(dict(bloque=bl,rol=role,horizonte_h=h,ano=year,causa=cause,base_horas=len(z),comun_horas=int(keep.sum()),positivos_base=int(z.y.sum()),positivos_comun=int(z.loc[keep].y.sum()),inicios_base=len(getids(z)),inicios_comun=len(getids(z.loc[keep])),ventanas_afectadas=int(affected.sum()),positivos_afectados=int(z.loc[affected].y.sum()),inicios_afectados=len(getids(z.loc[affected])),perdidas_marginales_horas=int(lost.sum()),perdidas_marginales_positivos=int(z.loc[lost].y.sum()),inicios_perdidos_sin_otras_oportunidades=len(getids(z)-getids(z.loc[~affected])),inicios_recuperables_marginalmente=len(getids(z.loc[recovered])-getids(z.loc[keep]))))
  q=pd.DataFrame({'emision':d.index,'objetivo':d.y,'id_inicio_objetivo':d.id_inicio_objetivo,'incluida':common,'bloque':bl,'rol':role,'horizonte_h':h})
  for cause,mask in bad.items():q['ausencia_'+cause]=mask
  details.append(q)
 e.save(pd.DataFrame(rows),e.OUT/'tablas/efecto_huecos_huanta.csv');e.save(pd.concat(details,ignore_index=True),e.OUT/'tablas/elegibilidad_huanta.csv')
 e.js(e.OUT/'diagnostico_soporte.json',{'resultado':'completo','hueco_largo_T':long.to_dict(),'referencia':'INIA básica + presión propia, futuro24 y purgas; causas no excluyentes; marginales mantienen los otros sensores','entrenamientos':'expansivos, no sumables','ano':'año de emisión; inicios en borde pueden tener oportunidades en dos años'})
 print('Diagnóstico de soporte completo',len(rows),flush=True)
if __name__=='__main__':diagnose(sys.argv[1] if len(sys.argv)>1 else e.OUT)
