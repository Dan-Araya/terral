#!/usr/bin/env python3
"""Legibilidad de rejilla completa de avisos; no modifica resultados."""
import os,sys
os.environ['MPLCONFIGDIR']='/tmp/laguna-v1-mpl'; sys.modules['numexpr']=None
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
O=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parent
m=pd.read_csv(O/'tablas/metricas_avisos.csv')
colors=dict(zip('ABCD',['#555555','#0072B2','#D55E00','#009E73']))
thresholds=[.001,.003,.01,.03,.1,.3,.5]; markers=['o','s','^','D','v','P','X']
for h in [1,3]:
 fig,axs=plt.subplots(1,3,figsize=(15,4.8)); fig.subplots_adjust(bottom=.25,wspace=.3)
 for ax,block in zip(axs,['2018-2019','2020-2021','2022-2023']):
  for arm in 'ABCD':
   d=m[m.horizonte_h.eq(h)&m.bloque.eq(block)&m.modelo.eq(arm)&m.epoca.eq('ALL')].set_index('politica')
   z=d.loc[[f'p>={t:g}' for t in thresholds]]
   ax.plot(z.falsas_alarmas_por_mes,z.recall_inicios,color=colors[arm],lw=1,label=arm)
   for i,r in enumerate(z.itertuples()): ax.scatter(r.falsas_alarmas_por_mes,r.recall_inicios,marker=markers[i],s=26,color=colors[arm])
  ax.set(xlabel='Falsas alarmas / mes equivalente',ylabel='Inicios detectados / evaluables',title=f'{block} · {h} h',ylim=(-.025,1.04)); ax.grid(alpha=.15); ax.legend(title='Brazo',fontsize=8,loc='lower right')
 handles=[Line2D([0],[0],marker=mark,color='#444',linestyle='',label=f'p≥{v:g}') for v,mark in zip(thresholds,markers)]
 fig.legend(handles=handles,loc='lower center',ncol=7,title='Todos los umbrales predefinidos',frameon=False)
 fig.savefig(O/f'graficos/avisos_{h}h.png',dpi=160,bbox_inches='tight'); plt.close(fig)
print('Rejilla completa de avisos con leyenda sin rótulos superpuestos.')
