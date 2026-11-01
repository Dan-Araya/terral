#!/usr/bin/env python3
"""Presentación de avisos con leyenda de umbrales sin superposición de etiquetas."""
import os,sys
os.environ['MPLCONFIGDIR']='/tmp/huanta-v1-mpl'; sys.modules['numexpr']=None
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
OUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parent
m=pd.read_csv(OUT/'tablas/metricas_avisos.csv')
colors=dict(zip('ABCD',['#555555','#0072B2','#D55E00','#009E73']))
thresholds=[.001,.003,.01,.03,.1,.3,.5]; markers=['o','s','^','D','v','P','X']
for h in [1,3]:
 fig,axs=plt.subplots(1,3,figsize=(15,5)); fig.subplots_adjust(left=.06,right=.99,top=.90,bottom=.29,wspace=.25)
 for ax,block in zip(axs,['2018-2019','2020-2021','2022-2023']):
  for arm in 'ABCD':
   z=m[(m.horizonte_h==h)&m.bloque.eq(block)&m.modelo.eq(arm)&m.epoca.eq('ALL')]
   ax.plot(z.falsas_alarmas_por_mes,z.recall_inicios,color=colors[arm],lw=1.5)
   for threshold,marker in zip(thresholds,markers):
    r=z[z.politica.eq(f'p>={threshold:g}')].iloc[0]
    ax.scatter(r.falsas_alarmas_por_mes,r.recall_inicios,color=colors[arm],marker=marker,s=36,edgecolor='white',linewidth=.4,zorder=3)
  ax.set(xlabel='Falsas alarmas / mes equivalente',title=f'{block} · {h} h',ylim=(-.025,1.025))
  ax.grid(alpha=.15)
 axs[0].set_ylabel('Inicios detectados / evaluables')
 arms=[Line2D([],[],color=colors[a],lw=2,label=a) for a in 'ABCD']
 fig.legend(handles=arms,loc='lower center',bbox_to_anchor=(.5,.12),ncol=4,title='Modelo (definiciones A–D en el informe)',frameon=False)
 levels=[Line2D([],[],color='black',marker=mk,ls='',label=f'p ≥ {t:g}') for t,mk in zip(thresholds,markers)]
 fig.legend(handles=levels,loc='lower center',bbox_to_anchor=(.5,-.01),ncol=7,title='Rejilla completa de umbrales predefinidos',frameon=False)
 fig.savefig(OUT/f'graficos/avisos_{h}h.png',dpi=160,bbox_inches='tight'); plt.close(fig)
print('Figuras de avisos con leyendas legibles guardadas; métricas intactas.')
cov=pd.read_csv(OUT/'tablas/cobertura_anual_huanta.csv')
sup=pd.read_csv(OUT/'tablas/soporte_potencial_y_perdidas.csv')
fig,axs=plt.subplots(1,2,figsize=(14,5),layout='constrained')
for v,z in cov.groupby('variable'):
 axs[0].plot(z.ano,100*z.utilizables/z.horas_calendario,'o-',label=v)
axs[0].set(title='Disponibilidad Huanta por sensor a 2 m',xlabel='Año',ylabel='Horas utilizables / calendario (%)',ylim=(0,103)); axs[0].legend(fontsize=8); axs[0].grid(alpha=.15)
z=sup[sup.horizonte_h.eq(1)&sup.brazo_potencial.eq('A')]
for role,color in [('entrenamiento','#0072B2'),('validacion','#D55E00')]:
 zz=z[z.rol.eq(role)]
 axs[1].plot(zz.bloque,100*zz.comun_4_brazos/zz.base_elegible_A,'o-',label=role,color=color)
axs[1].set(title='Soporte común frente a INIA básica · 1 h',ylabel='Emisiones retenidas (%)',ylim=(65,101)); axs[1].legend(); axs[1].grid(alpha=.15)
fig.savefig(OUT/'graficos/cobertura_huanta.png',dpi=160,bbox_inches='tight'); plt.close(fig)
