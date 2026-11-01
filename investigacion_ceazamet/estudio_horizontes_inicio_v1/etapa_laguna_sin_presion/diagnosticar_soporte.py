"""Pérdidas secuenciales por causa/año/rol; no entrena ni altera máscaras."""
import estudio as e
import sys
from pathlib import Path
import numpy as np
import pandas as pd

def diagnose(out):
 e.OUT=Path(out);x,state,cat,f,cols,yy,ids,future,ds=e.prepare();p,pe=e.s.load_extra([])
 cov=[];gaps=[]
 for sid,(v,height) in e.s.EXPECTED.items():
  for year,z in pe[v].groupby(pe.index.year):cov.append(dict(ano=year,sensor=sid,variable=v,altura_m=height,horas_calendario=len(z),utilizables=int(z.notna().sum()),no_utilizables=int(z.isna().sum()),ceros_validos=int(z.eq(0).sum())))
  edges=np.diff(np.r_[False,pe[v].isna(),False].astype(int));aa=np.flatnonzero(edges==1);bb=np.flatnonzero(edges==-1)-1
  gaps.extend(dict(sensor=sid,variable=v,inicio=e.b.IDX[i],fin=e.b.IDX[j],horas=j-i+1) for i,j in zip(aa,bb))
 e.save(pd.DataFrame(cov),e.OUT/'tablas/cobertura_anual_laguna_sin_presion.csv');e.save(pd.DataFrame(gaps),e.OUT/'tablas/huecos_por_sensor.csv')
 idx=e.b.IDX
 raw=pd.read_csv(e.ROOT/'estaciones_complementarias/la_laguna_elqui/derivados/horarias.csv',dtype={'sensor':str});raw=raw[raw.sensor.isin(e.s.EXPECTED)]
 raw['fecha']=pd.to_datetime(raw.fecha_sin_zona)
 available=pd.DataFrame({sid:z.set_index('fecha').presente.eq(1).reindex(idx,fill_value=False) & np.isfinite(z.set_index('fecha').prom.reindex(idx)) for sid,z in raw.groupby('sensor')})
 inia=pd.concat([pd.read_csv(e.ROOT/f'historico_inia/derivados/observaciones_{y}.csv',usecols=['fecha_sin_zona','variable','prom']) for y in range(2013,2024)])
 inia=inia[inia.variable.isin(e.b.MAIN+['presion'])];inia['fecha']=pd.to_datetime(inia.fecha_sin_zona)
 av_inia=np.isfinite(inia.pivot(index='fecha',columns='variable',values='prom').reindex(idx)).all(axis=1)
 availability=available.all(axis=1)&av_inia
 quality=x.notna().all(axis=1)&p.notna()&pe.notna().all(axis=1)
 rows=[];loss=[];detail=[];getids=lambda z:{v for value in z for v in value.split('|') if v}
 old_counts=pd.read_csv(e.ROOT/'experimento_laguna_sin_presion_inicio_v1/tablas/particiones.csv')
 for block,ty,vs,ve in e.b.BLOCKS:
  for role,lo,hi in [('train',pd.Timestamp('2013-01-01'),pd.Timestamp(f'{ty}-12-31 23:00')),('val',pd.Timestamp(f'{vs}-01-01'),pd.Timestamp(f'{ve}-12-31 23:00'))]:
   domain=pd.Series((idx>=lo)&(idx<=hi),index=idx)
   bounds=pd.Series((idx-pd.Timedelta(hours=6)>=lo)&(idx+pd.Timedelta(hours=24)<=hi),index=idx)
   purge=pd.Series(True,index=idx)
   for r in cat.itertuples():
    if r.inicio<lo<=r.fin or r.inicio<=hi<r.fin:purge &= ~((idx-pd.Timedelta(hours=6)<=r.fin)&(idx+pd.Timedelta(hours=24)>=r.inicio))
   stages=[('calendario',domain),('disponibilidad',availability),('calidad',quality),('antecedentes',e.COMPLETE & f.notna().all(axis=1)),('estado_fuera_evento',state.eq(0)),('etiquetas_futuro24',~future),('fronteras24',bounds),('purga_tramos',purge)]
   keep=domain.copy();primary=pd.Series('incluida',index=idx)
   for stage,mask in stages[1:]:
    primary.loc[keep&~mask]=stage;keep &= mask
   assert idx[keep].equals(ds[block,role,24].index)
   detail.append(pd.DataFrame({'emision':idx[domain],'bloque':block,'rol':role,'motivo_primario':primary[domain].to_numpy()}))
   for h in e.H:
    prior=domain.copy()
    for stage,mask in stages:
     current=prior&mask
     for year in range(lo.year,hi.year+1):
      yr=idx.year==year;a=prior&yr;z=current&yr
      rows.append(dict(bloque=block,rol=role,horizonte_h=h,ano=year,etapa_filtro=stage,horas_antes=int(a.sum()),horas_despues=int(z.sum()),horas_perdidas=int((a&~z).sum()),positivos_antes=int(yy[h][a].sum()),positivos_despues=int(yy[h][z].sum()),positivos_perdidos=int(yy[h][a&~z].sum()),inicios_antes=len(getids(ids[h][a])),inicios_despues=len(getids(ids[h][z])),inicios_perdidos=len(getids(ids[h][a])-getids(ids[h][z]))))
     prior=current
    if h in [1,3]:
     old=e.dataset(f,state,cat,yy,ids,future,lo,hi,h,False);old=old.loc[e.COMPLETE.reindex(old.index)];new=ds[block,role,h]
     r=old_counts[old_counts.bloque.eq(block)&old_counts.horizonte_h.eq(h)&old_counts.rol.eq('entrenamiento' if role=='train' else 'validacion')].iloc[0]
     assert (len(old),int(old.y.sum()),len(getids(old.id_inicio_objetivo)))==(r.n,r.positivos,r.inicios_con_oportunidad)
     for year in range(lo.year,hi.year+1):
      a=old[old.index.year==year];z=new[new.index.year==year]
      loss.append(dict(bloque=block,rol=role,horizonte_h=h,ano=year,horas_previo=len(a),horas_comun24=len(z),horas_perdidas=len(a)-len(z),positivos_previo=int(a.y.sum()),positivos_comun24=int(z.y.sum()),positivos_perdidos=int(a.y.sum()-z.y.sum()),inicios_previo=len(getids(a.id_inicio_objetivo)),inicios_comun24=len(getids(z.id_inicio_objetivo)),inicios_perdidos=len(getids(a.id_inicio_objetivo)-getids(z.id_inicio_objetivo))))
 e.save(pd.DataFrame(rows),e.OUT/'tablas/perdidas_por_causa.csv');e.save(pd.DataFrame(loss),e.OUT/'tablas/perdidas_vs_previo_anual.csv');e.save(pd.concat(detail),e.OUT/'tablas/elegibilidad_laguna_sin_presion.csv')
 e.js(e.OUT/'diagnostico_soporte.json',{'resultado':'completo','referencia_previa':'soporte 1–3 h reconstruido y conteos idénticos al experimento sin presión; sin reutilizar métricas o modelos','perdidas':'secuenciales en orden publicado; positivos/inicios potenciales antes de evaluar etiquetas, no objetivos asumidos conocidos; año de emisión, eventos en bordes pueden repetirse entre años','entrenamientos':'expansivos, no sumar','presion_laguna':'excluida de todo cálculo'})
 print('Diagnóstico completo y soporte previo reconciliado',flush=True)
if __name__=='__main__':diagnose(sys.argv[1])
