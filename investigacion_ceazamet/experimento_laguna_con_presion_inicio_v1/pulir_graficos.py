#!/usr/bin/env python3
"""Ajustes de legibilidad posteriores a revisión visual; solo lee tablas cerradas."""
import os,sys,json,hashlib
os.environ['OPENBLAS_NUM_THREADS']='1'; os.environ['MPLCONFIGDIR']='/tmp/laguna-presion-mpl'; sys.modules['numexpr']=None
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
OUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parent
T=OUT/'tablas'; G=OUT/'graficos'
ci=pd.read_csv(T/'intervalos_pareados.csv'); cov=pd.read_csv(T/'cobertura_anual_laguna.csv'); comparison=pd.read_csv(T/'comparacion_soporte_anterior.csv')
colors=dict(zip('ABCDEF',['#555555','#0072B2','#D55E00','#009E73','#CC79A7','#6A3D9A']))
fig,axs=plt.subplots(1,2,figsize=(12,7),layout='constrained')
for ax,metric in zip(axs,['AP','Brier']):
 z=ci[ci.metrica.eq(metric)&ci.contraste.str.contains('-')]
 for i,r in enumerate(z.itertuples()):
  ax.plot([r.p025,r.p975],[i,i],color=colors[r.contraste[0]]); ax.scatter(r.estimacion,i,color=colors[r.contraste[0]],s=25)
 ax.set_yticks(range(len(z)),[f'{r.contraste} · {r.horizonte_h} h' for r in z.itertuples()]); ax.axvline(0,color='black',lw=.7)
 ax.set(title=f'Δ {metric} · IC 95% por contraste',xlabel='Brazo añadido − referencia'); ax.xaxis.set_major_locator(MaxNLocator(5))
 if metric=='Brier': ax.ticklabel_format(axis='x',style='sci',scilimits=(0,0),useMathText=True)
fig.savefig(G/'diferencias_pareadas.png',dpi=150); plt.close(fig)
fig,axs=plt.subplots(3,1,figsize=(11,9),layout='constrained',gridspec_kw={'height_ratios':[1.3,1,1]})
pivot=cov.assign(cobertura=100*cov.utilizables/cov.horas_calendario).pivot(index='variable',columns='ano',values='cobertura')
im=axs[0].imshow(pivot,aspect='auto',vmin=0,vmax=100,cmap='viridis'); axs[0].set_xticks(range(len(pivot.columns)),pivot.columns); axs[0].set_yticks(range(len(pivot)),pivot.index); axs[0].set_title('La Laguna: cobertura utilizable por sensor'); fig.colorbar(im,ax=axs[0],label='% del calendario')
for ax,role in zip(axs[1:],['entrenamiento','validacion']):
 z=comparison[comparison.horizonte_h.eq(1)&comparison.rol.eq(role)].sort_values('bloque'); xx=list(range(len(z)))
 ax.bar([x-.18 for x in xx],z.elegibles_sin_presion,width=.36,label='Soporte anterior sin presión Laguna',color='#aaa')
 ax.bar([x+.18 for x in xx],z.elegibles_con_presion,width=.36,label='Soporte común seis brazos',color='#0072B2')
 ax.set_xticks(xx,z.bloque); ax.set(ylabel='Emisiones elegibles',title=f'{role.capitalize()} · horizonte 1 h'); ax.yaxis.set_major_locator(MaxNLocator(5))
axs[1].legend(loc='upper left',fontsize=8)
fig.savefig(G/'cobertura_y_soporte.png',dpi=150); plt.close(fig)
record={'tipo':'solo_legibilidad_visual','cambios':['Notación científica y menos marcas en Brier para evitar superposición','Barras separadas y roles entrenamiento/validación explícitos'], 'sin_cambios_numericos':True,'codigo_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
(OUT/'revision_visual.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
print('Figuras revisadas sin cambios de métricas, protocolo o código registrado.')
