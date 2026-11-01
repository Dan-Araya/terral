#!/usr/bin/env python3
"""Informe y figuras desde resultados; ninguna selección o ajuste adicional."""
import os,sys,json
os.environ['MPLCONFIGDIR']='/tmp/laguna-presion-mpl'; sys.modules['numexpr']=None
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
OUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parent
T=OUT/'tablas'; G=OUT/'graficos'
contrasts=['E-C','F-D','C-A','D-B','E-A','F-B']; arms=list('ABCDEF')
labels={'A':'INIA básica','B':'INIA + P propia','C':'INIA + Laguna sin P','D':'INIA + P propia + Laguna sin P','E':'INIA + Laguna con P','F':'INIA + P propia + Laguna con P'}
colors=dict(zip(arms,['#555555','#0072B2','#D55E00','#009E73','#CC79A7','#6A3D9A']))
pred=pd.read_csv(OUT/'predicciones_validacion.csv',parse_dates=['emision']).fillna({'id_inicio_objetivo':''})
hm=pd.read_csv(T/'metricas_horarias.csv'); ci=pd.read_csv(T/'intervalos_pareados.csv').fillna({'politica':''})
pairs=pd.read_csv(T/'diferencias_por_particion.csv'); parts=pd.read_csv(T/'particiones.csv')
cal=pd.read_csv(T/'calibracion.csv'); ca=pd.read_csv(T/'calibracion_agregada.csv'); curve=pd.read_csv(T/'curvas_precision_recall.csv')
am=pd.read_csv(T/'metricas_avisos.csv'); agg=pd.read_csv(T/'avisos_agregados.csv')
comparison=pd.read_csv(T/'comparacion_soporte_anterior.csv'); cov=pd.read_csv(T/'cobertura_anual_laguna.csv')
annual=pd.read_csv(T/'presion_soporte_por_ano_particion.csv'); ints=pd.read_csv(T/'intervalos_presion_por_ano_particion.csv')
def ids(d): return {c for s in d.id_inicio_objetivo for c in s.split('|') if c}
def fmt(v):
 if pd.isna(v): return '—'
 return f'{v:.7g}' if isinstance(v,(float,np.floating)) else str(v)
def table(df):
 return '| '+' | '.join(df.columns)+' |\n| '+' | '.join(['---']*len(df.columns))+' |\n'+'\n'.join('| '+' | '.join(map(fmt,row))+' |' for row in df.itertuples(index=False,name=None))+'\n'
def classification(h,c):
 z=pairs[pairs.horizonte_h.eq(h)&pairs.contraste.eq(c)]; ap=z[z.metrica.eq('AP')].delta; br=z[z.metrica.eq('Brier')].delta
 a=ci[ci.horizonte_h.eq(h)&ci.contraste.eq(c)&ci.metrica.eq('AP')].iloc[0]; b=ci[ci.horizonte_h.eq(h)&ci.contraste.eq(c)&ci.metrica.eq('Brier')].iloc[0]
 if ap.gt(0).all() and br.lt(0).all() and a.p025>0 and b.p975<0: return 'Mejora consistente'
 if ap.lt(0).all() and br.gt(0).all() and a.p975<0 and b.p025>0: return 'Empeoramiento consistente'
 if a.p025<=0<=a.p975 and b.p025<=0<=b.p975: return 'Ausencia de evidencia de mejora'
 return 'Resultado incierto'
interpret=pd.DataFrame([{'horizonte_h':h,'contraste':c,'tipo':'principal' if c in contrasts[:2] else 'secundario','interpretacion':classification(h,c)} for h in [1,3] for c in contrasts]); interpret.to_csv(T/'interpretacion.csv',index=False)
summary=[]
for h in [1,3]:
 z=pred[pred.horizonte_h.eq(h)&pred.modelo.eq('A')]; prev=comparison[comparison.horizonte_h.eq(h)&comparison.rol.eq('validacion')]
 summary.append(dict(horizonte_h=h,horas=len(z),positivos=int(z.objetivo.sum()),inicios_distintos=len(ids(z)),horas_anteriores=int(prev.elegibles_sin_presion.sum()),ventanas_perdidas=int(prev.ventanas_perdidas.sum()),positivos_perdidos=int(prev.positivos_perdidos.sum()),inicios_perdidos=int(prev.inicios_completamente_perdidos.sum())))
summary=pd.DataFrame(summary); summary.to_csv(T/'soporte_validacion_agregado.csv',index=False)
ci[ci.politica.eq('')].to_csv(T/'metricas_y_diferencias_agregadas.csv',index=False)
# Add exact aggregated support, exposure, and descriptive median lead for every threshold.
rows=[]
a=pd.read_csv(T/'correspondencia_avisos.csv')
for r in agg.to_dict('records'):
 d=pred[pred.horizonte_h.eq(r['horizonte_h'])&pred.modelo.eq(r['modelo'])]
 aa=a[a.horizonte_h.eq(r['horizonte_h'])&a.modelo.eq(r['modelo'])&a.politica.eq(r['politica'])]
 rows.append(dict(**r,n_emisiones=len(d),positivos=int(d.objetivo.sum()),inicios_distintos=len(ids(d)),meses_equivalentes=len(d)/(365.25*24/12),aciertos_avisos=int(aa.estado.eq('acierto').sum()),anticipacion_mediana_h=aa.anticipacion_h.median()))
agg=pd.DataFrame(rows); agg.to_csv(T/'avisos_agregados_completos.csv',index=False,float_format='%.10g')
for h in [1,3]:
 fig,axs=plt.subplots(1,3,figsize=(14,4),layout='constrained')
 for ax,block in zip(axs,['2018-2019','2020-2021','2022-2023']):
  for arm in arms:
   z=curve[curve.horizonte_h.eq(h)&curve.bloque.eq(block)&curve.modelo.eq(arm)]
   ax.step(np.r_[0,z.recall],np.r_[z.precision.iloc[0],z.precision],where='pre',color=colors[arm],label=arm)
  prev=hm[hm.horizonte_h.eq(h)&hm.bloque.eq(block)&hm.epoca.eq('ALL')].prevalencia.iloc[0]
  ax.axhline(prev,ls=':',color='black'); ax.set(xlabel='Recobrado horario',ylabel='Precisión',title=f'{block} · {h} h',xlim=(0,1),ylim=(0,1)); ax.legend(fontsize=8,ncol=2)
 fig.savefig(G/f'PR_{h}h.png',dpi=150); plt.close(fig)
 fig,axs=plt.subplots(1,3,figsize=(14,4),layout='constrained')
 for ax,block in zip(axs,['2018-2019','2020-2021','2022-2023']):
  for arm in arms:
   z=cal[cal.horizonte_h.eq(h)&cal.bloque.eq(block)&cal.modelo.eq(arm)&cal.epoca.eq('ALL')&cal.n.gt(0)]
   ax.plot(z.p_media,z.frecuencia_observada,'o-',ms=3,color=colors[arm],label=arm)
  ax.plot([0,1],[0,1],'k--',lw=.7); ax.set(xlabel='Probabilidad prevista media',ylabel='Frecuencia observada',title=f'{block} · {h} h',xlim=(0,1),ylim=(0,1)); ax.legend(fontsize=8,ncol=2)
 fig.savefig(G/f'calibracion_{h}h.png',dpi=150); plt.close(fig)
 fig,axs=plt.subplots(1,3,figsize=(14,4),layout='constrained'); markers=['o','s','^','D','v','P','X']
 for ax,block in zip(axs,['2018-2019','2020-2021','2022-2023']):
  for arm in arms:
   z=am[am.horizonte_h.eq(h)&am.bloque.eq(block)&am.modelo.eq(arm)&am.epoca.eq('ALL')].set_index('politica')
   ax.plot(z.falsas_alarmas_por_mes,z.recall_inicios,color=colors[arm],lw=.8)
   for threshold,marker in zip([.001,.003,.01,.03,.1,.3,.5],markers):
    r=z.loc[f'p>={threshold:g}']; ax.scatter(r.falsas_alarmas_por_mes,r.recall_inicios,color=colors[arm],marker=marker,s=25)
  ax.set(xlabel='Falsas alarmas / mes equivalente',ylabel='Inicios detectados / evaluables',title=f'{block} · {h} h',ylim=(-.03,1.03))
 from matplotlib.lines import Line2D
 handles=[Line2D([],[],color=colors[a],label=a) for a in arms]+[Line2D([],[],color='black',ls='',marker=m,label=f'p≥{v:g}') for m,v in zip(markers,[.001,.003,.01,.03,.1,.3,.5])]
 fig.legend(handles=handles,loc='outside lower center',ncol=7,fontsize=8)
 fig.savefig(G/f'avisos_{h}h.png',dpi=150); plt.close(fig)
fig,axs=plt.subplots(1,2,figsize=(12,7),layout='constrained')
for ax,metric in zip(axs,['AP','Brier']):
 z=ci[ci.metrica.eq(metric)&ci.contraste.isin(contrasts)]
 for i,r in enumerate(z.itertuples()):
  ax.plot([r.p025,r.p975],[i,i],color=colors[r.contraste[0]]); ax.scatter(r.estimacion,i,color=colors[r.contraste[0]],s=25)
 ax.set_yticks(range(len(z)),[f'{r.contraste} · {r.horizonte_h} h' for r in z.itertuples()]); ax.axvline(0,color='black',lw=.7); ax.set(title=f'Δ {metric} · IC 95% por contraste',xlabel='Brazo añadido − referencia')
fig.savefig(G/'diferencias_pareadas.png',dpi=150); plt.close(fig)
fig,axs=plt.subplots(2,1,figsize=(11,6),layout='constrained')
pivot=cov.assign(cobertura=100*cov.utilizables/cov.horas_calendario).pivot(index='variable',columns='ano',values='cobertura')
im=axs[0].imshow(pivot,aspect='auto',vmin=0,vmax=100,cmap='viridis'); axs[0].set_xticks(range(len(pivot.columns)),pivot.columns); axs[0].set_yticks(range(len(pivot)),pivot.index); axs[0].set_title('La Laguna: cobertura utilizable de cada sensor'); fig.colorbar(im,ax=axs[0],label='% del calendario')
z=comparison[comparison.horizonte_h.eq(1)&comparison.rol.eq('validacion')]
axs[1].bar(z.bloque,z.elegibles_sin_presion,label='Soporte anterior sin presión Laguna',color='#aaa'); axs[1].bar(z.bloque,z.elegibles_con_presion,label='Soporte común seis brazos',color='#0072B2'); axs[1].set(ylabel='Emisiones elegibles',title='Validación · horizonte 1 h'); axs[1].legend()
fig.savefig(G/'cobertura_y_soporte.png',dpi=150); plt.close(fig)
lines=['# Evaluación secundaria: La Laguna–Elqui con presión utilizable','',
'Se entrenaron desde cero los seis brazos sobre idénticas emisiones y etiquetas de entrenamiento y validación: 36 modelos, horizontes de 1 y 3 horas. Solo observaciones locales 2013–2023. Las conclusiones corresponden al inicio conocido del criterio histórico INIA; no demuestran mecanismo físico ni capacidad operacional.','',
'## Conclusiones separadas','',
'**La Laguna con presión frente a INIA:**',table(interpret[interpret.contraste.isin(['E-A','F-B'])]),
'**Aporte específico de LAGELPA frente a La Laguna sin presión:**',table(interpret[interpret.contraste.isin(['E-C','F-D'])]),
'**Histórico y límites:** presión local con modelo instrumental y referencia sin confirmar. Se preservan las 4.004 horas sospechosas como excluidas. El hueco continuo de 17.180 horas, 2015-05-19 12:00 a 2017-05-04 07:00, reduce especialmente entrenamiento y algunos inicios. La inferencia queda condicionada a los períodos realmente utilizables; no representa continuidad de todo el histórico. No se contrastan E/F con métricas del experimento anterior.','',
'Todas las categorías aplican AP/Brier y los tres bloques conjuntamente según protocolo previo. Los IC son por contraste, no simultáneos. Ausencia de evidencia de mejora no demuestra equivalencia. No se escoge umbral ni configuración ganadora.','',
'## Brazos y contraste','',table(pd.DataFrame([dict(brazo=a,definicion=labels[a],predictores=n) for a,n in zip(arms,[35,41,66,72,72,78])])),table(interpret),'',
'## Soporte y pérdida por presión','',table(summary),table(parts),
'La tabla siguiente reconstruye exactamente las emisiones del experimento sin presión y separa positivos afectados e inicios que pierden todas sus oportunidades. Los entrenamientos expansivos se solapan: no se suman. Los totales anuales de inicios tampoco deben sumarse si un inicio tiene oportunidades a ambos lados de año.','',table(comparison),
'![Cobertura](graficos/cobertura_y_soporte.png)','',
'La disponibilidad de entrada exige siete observaciones válidas y se contabiliza antes de etiquetas y purgas. La elegibilidad final añade estado no_cumple, objetivos conocidos, fronteras y purgas. `presion_soporte_por_ano_particion.csv` separa ambos niveles, horas sin presión, ventanas afectadas, pérdidas marginales frente al soporte anterior, positivos e inicios. `mascaras_horarias.csv` permite reconstruir cada ventana. Los intervalos utilizables y huecos exactos están en `intervalos_presion_por_ano_particion.csv`, recortados por año y rol; una ventana puede perderse por un hueco en el año anterior. Los intervalos globales de todos los sensores se conservan en `huecos_por_sensor.csv`.','',
'Cobertura anual LAGELPA:',table(cov[cov.variable.eq('presion')]),
'Intervalos de presión por año (ámbito global, también recortados en tablas para cada partición):',table(ints[ints.bloque.eq('global')]),
'## Métricas horarias e incertidumbre','',
'AP agregada se obtiene juntando predicciones de tres modelos fuera de muestra; no es media de AP por partición ni porcentaje de aciertos. Brier es promedio por emisión. AP positiva y Brier negativa favorecen el brazo añadido. Se reportan todos los signos.','',table(ci[ci.politica.eq('')][['horizonte_h','contraste','metrica','estimacion','p025','p975','replicas_validas']]),
'![Diferencias](graficos/diferencias_pareadas.png)','',
'Por partición:',table(hm[hm.epoca.eq('ALL')][['horizonte_h','bloque','modelo','n_emisiones','positivos','AP','Brier']]),
'Diferencias por partición:',table(pairs[pairs.metrica.isin(['AP','Brier'])][['horizonte_h','bloque','contraste','metrica','delta']]),
'## Avisos: rejilla completa','',
'Grupos de horas consecutivas con p≥umbral, correspondencia cronológica uno a uno; redundantes separados e incluidos en precisión. Inicios evaluables requieren oportunidad en soporte común. Falsas alarmas/mes usan exposición real en meses equivalentes. Media y mediana de anticipación solo entre aciertos; son descriptivas y condicionales a detección.','',
 table(agg[['horizonte_h','politica','modelo','grupos_avisos','aciertos_avisos','falsas_alarmas','redundantes','inicios_evaluables','inicios_anticipados','inicios_omitidos','recall_inicios','precision_avisos','falsas_alarmas_por_mes','anticipacion_media_h','anticipacion_mediana_h']]),
'Todos los deltas de avisos por partición en `diferencias_por_particion.csv`; todos los deltas agregados e IC 95% pareados en `intervalos_pareados.csv`, incluidos conteos y anticipación media. No hay IC para mediana según protocolo original. `correspondencia_avisos.csv` y `evaluacion_inicios.csv` trazan cada aviso e inicio. Desgloses estacionales completos en `metricas_avisos.csv`.','',
'## Calibración y curvas','',table(ca),'',
'Bordes fijos, sin recalibración. Se entregan conteos/positivos y frecuencias por intervalo y partición en calibracion.csv, y agregadas en calibracion_agregada.csv. Las colas con pocos casos limitan la interpretación visual.','']
for h in [1,3]: lines += [f'![PR {h}h](graficos/PR_{h}h.png)',f'![Calibración {h}h](graficos/calibracion_{h}h.png)',f'![Avisos {h}h](graficos/avisos_{h}h.png)','']
lines += ['## Método, límites y trazabilidad','',
'Validaciones: 2013–2017→2018–2019; 2013–2019→2020–2021; 2013–2021→2022–2023. Escalas poblacionales solo de entrenamiento común. Logística L2 C=1, sin pesos, mismas tolerancias e inicialización; no se buscaron variables, hiperparámetros, desfases o umbrales. Presión añade las seis transformaciones escalares heredadas; dirección circular seno/coseno y derivados. T/HR a 1,5 m, viento a 10 m, presión a 2 m. Sin conversiones de altura, gradientes, reducción al nivel del mar o imputación. Se mantiene íntegra la máscara utilizable_revision, incluida la exclusión de los 4.004 sospechosos, y se coteja por lectura independiente.','',
'Bootstrap pareado original: 300 réplicas, semilla 20132023, ocho bloques móviles de tres meses por bienio, sin envolver; mismas multiplicidades para todos los brazos y horizontes. Se guardan en bootstrap_muestras.csv. IC percentiles agregados 2,5–97,5% por contraste, sin corrección de multiplicidad. Las diferencias por partición son puntuales como en el protocolo original. Avisos se remuestrean tras correspondencia usando mes del aviso e inicio, sin recrear cronología artificial. Condicional a ajustes y catálogo; no incluye incertidumbre de entrenamiento, etiquetas ni medidas. Extremos no uniformes, pocos inicios y validaciones de desarrollo reutilizadas limitan la inferencia.','',
'La observación marcada t se supone disponible en t. Actualización horaria no confirma zona histórica, posición/cálculo del intervalo, latencia o alineación física entre estaciones. Modelo y referencia de presión siguen sin confirmar; no se deducen por desempeño. Se conserva la discrepancia documental de altura T/HR INIA y la diferencia entre calidad del promedio INIA y calidad de min/prom/max complementarios. No se consultó el período reservado, ni red, ni originales con bordes externos. No se desplegaron alertas ni se contactó a terceros.','',
'Código, protocolo, configuración, columnas, máscaras, soporte, semilla y hashes se registraron antes del primer ajuste en registro_preentrenamiento.json y manifiesto_previo.json. Coeficientes/escalas y convergencia en ajustes/<brazo>/ajustes; predicciones con hora, horizonte, etiqueta, identificadores y límites en predicciones_validacion.csv. Conservación de catálogo, fuentes y experimentos anteriores en conservacion_previa.json y hashes antes/después en tablas/manifiesto_fuentes.csv. Verificaciones y repetición completa se incorporan al cierre; consultar cierre.json para su estado definitivo.','']
(OUT/'informe.md').write_text('\n'.join(lines)+'\n')
print(table(interpret)); print(table(summary)); print('Informe y figuras generados.')
