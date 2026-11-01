#!/usr/bin/env python3
"""Informe y figuras exclusivamente desde resultados de este experimento."""
import os,sys,json
os.environ['MPLCONFIGDIR']='/tmp/huanta-v1-mpl'; sys.modules['numexpr']=None
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
OUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parent
T=OUT/'tablas'; G=OUT/'graficos'
pred=pd.read_csv(OUT/'predicciones_validacion.csv',parse_dates=['emision'])
hm=pd.read_csv(T/'metricas_horarias.csv'); ci=pd.read_csv(T/'intervalos_pareados.csv').fillna({'politica':''})
cal=pd.read_csv(T/'calibracion.csv'); curve=pd.read_csv(T/'curvas_precision_recall.csv')
am=pd.read_csv(T/'metricas_avisos.csv'); agg=pd.read_csv(T/'avisos_agregados.csv'); pairs=pd.read_csv(T/'diferencias_por_particion.csv')
support=pd.read_csv(T/'soporte_potencial_y_perdidas.csv'); parts=pd.read_csv(T/'particiones.csv')
labels={'A':'A: INIA básica','B':'B: INIA + presión','C':'C: INIA + Huanta','D':'D: INIA + presión + Huanta'}
colors=dict(zip('ABCD',['#555555','#0072B2','#D55E00','#009E73']))
for h in [1,3]:
 fig,axs=plt.subplots(1,3,figsize=(14,4),layout='constrained')
 for ax,block in zip(axs,['2018-2019','2020-2021','2022-2023']):
  for arm in 'ABCD':
   z=curve[(curve.horizonte_h==h)&(curve.bloque==block)&(curve.modelo==arm)]
   ax.step(np.r_[0,z.recall],np.r_[z.precision.iloc[0],z.precision],where='pre',color=colors[arm],label=labels[arm])
  prev=hm[(hm.horizonte_h==h)&(hm.bloque==block)&hm.epoca.eq('ALL')].prevalencia.iloc[0]
  ax.axhline(prev,ls=':',color='black'); ax.set(xlabel='Recobrado horario',ylabel='Precisión',title=f'{block} · {h} h',xlim=(0,1),ylim=(0,1)); ax.legend(fontsize=7)
 fig.savefig(G/f'PR_{h}h.png',dpi=160,bbox_inches='tight'); plt.close(fig)
 fig,axs=plt.subplots(1,3,figsize=(14,4),layout='constrained')
 for ax,block in zip(axs,['2018-2019','2020-2021','2022-2023']):
  for arm in 'ABCD':
   z=cal[(cal.horizonte_h==h)&(cal.bloque==block)&(cal.modelo==arm)&cal.epoca.eq('ALL')&cal.n.gt(0)]
   ax.plot(z.p_media,z.frecuencia_observada,'o-',ms=3,color=colors[arm],label=arm)
  ax.plot([0,1],[0,1],'k--',lw=.7); ax.set(xlabel='Probabilidad prevista media',ylabel='Frecuencia observada',title=f'{block} · {h} h',xlim=(0,1),ylim=(0,1)); ax.legend()
 fig.savefig(G/f'calibracion_{h}h.png',dpi=160,bbox_inches='tight'); plt.close(fig)
 fig,axs=plt.subplots(1,3,figsize=(14,4),layout='constrained')
 for ax,block in zip(axs,['2018-2019','2020-2021','2022-2023']):
  for arm in 'ABCD':
   z=am[(am.horizonte_h==h)&(am.bloque==block)&(am.modelo==arm)&am.epoca.eq('ALL')]
   ax.plot(z.falsas_alarmas_por_mes,z.recall_inicios,'o-',color=colors[arm],label=arm)
   for r in z.itertuples(): ax.annotate(r.politica[3:],(r.falsas_alarmas_por_mes,r.recall_inicios),fontsize=6)
  ax.set(xlabel='Falsas alarmas / mes equivalente',ylabel='Inicios detectados / evaluables',title=f'{block} · {h} h',ylim=(0,1)); ax.legend()
 fig.savefig(G/f'avisos_{h}h.png',dpi=160,bbox_inches='tight'); plt.close(fig)
fig,axs=plt.subplots(1,2,figsize=(10,4),layout='constrained')
for ax,metric in zip(axs,['AP','Brier']):
 z=ci[ci.metrica.eq(metric)&ci.contraste.isin(['B-A','C-A','D-B'])]
 for i,r in enumerate(z.itertuples()):
  ax.errorbar(r.estimacion,i,xerr=[[r.estimacion-r.p025],[r.p975-r.estimacion]],fmt='o',color=colors[r.contraste[0]])
 ax.set_yticks(range(len(z)),[f'{r.contraste}, {r.horizonte_h}h' for r in z.itertuples()]); ax.axvline(0,color='black',lw=.7); ax.set(title=f'Diferencia {metric} · IC 95% temporal',xlabel='Brazo añadido − referencia')
fig.savefig(G/'diferencias_pareadas.png',dpi=160,bbox_inches='tight'); plt.close(fig)
def fmt(v):
 if pd.isna(v): return '—'
 if isinstance(v,(float,np.floating)): return f'{v:.6g}'
 return str(v)
def table(df):
 return '| '+' | '.join(df.columns)+' |\n| '+' | '.join(['---']*len(df.columns))+' |\n'+'\n'.join('| '+' | '.join(fmt(v) for v in row)+' |' for row in df.itertuples(index=False,name=None))+'\n'
def classification(h,contrast):
 z=pairs[(pairs.horizonte_h==h)&pairs.contraste.eq(contrast)&pairs.metrica.isin(['AP','Brier'])]
 ap=z[z.metrica.eq('AP')].delta; br=z[z.metrica.eq('Brier')].delta
 aa=ci[(ci.horizonte_h==h)&ci.contraste.eq(contrast)&ci.metrica.eq('AP')].iloc[0]; bb=ci[(ci.horizonte_h==h)&ci.contraste.eq(contrast)&ci.metrica.eq('Brier')].iloc[0]
 if ap.gt(0).all() and br.lt(0).all() and aa.p025>0 and bb.p975<0: return 'Mejora consistente'
 if ap.lt(0).all() and br.gt(0).all() and aa.p975<0 and bb.p025>0: return 'Empeoramiento consistente'
 if aa.p025<=0<=aa.p975 and bb.p025<=0<=bb.p975: return 'Ausencia de evidencia de mejora'
 return 'Resultado incierto'
lines=['# Experimento Llanos de Huanta e INIA: desarrollo 2013–2023','',
'Comparación retrospectiva del inicio conocido del criterio histórico del catálogo provisional. No valida el inicio físico de terral y no acredita anticipación operacional. No se desplegaron alertas. Los cuatro brazos se ajustaron desde cero sobre idénticas emisiones de entrenamiento y validación, sin selección posterior de configuración.',
'', '## Conclusión bajo el protocolo previo','']
summary=[]
for h in [1,3]:
 for contrast in ['B-A','C-A','D-B']: summary.append({'h':h,'contraste':contrast,'interpretación':classification(h,contrast)})
lines += [table(pd.DataFrame(summary)),
'Las categorías aplican la regla conjunta de AP/Brier y estabilidad entre bloques fijada antes de entrenar. Los compromisos de avisos dependen del umbral y no se selecciona uno como ganador. Una diferencia favorable aislada no demuestra mejora consistente.','',
'## Métricas agregadas fuera de muestra','',
'AP se calcula juntando predicciones de los tres ajustes fuera de muestra; no es la media simple de AP por partición. Esta mezcla de escalas de tres modelos tiene sus propias limitaciones. Brier es la media por emisión. Diferencias firmadas: AP positiva y Brier negativa favorecen el brazo añadido.','']
base=ci[ci.contraste.isin(list('ABCD'))&ci.metrica.isin(['AP','Brier'])]
lines += [table(base[['horizonte_h','contraste','metrica','estimacion','p025','p975']]),'',
'## Diferencias pareadas e incertidumbre','',table(ci[ci.contraste.isin(['B-A','C-A','D-B'])&ci.metrica.isin(['AP','Brier'])][['horizonte_h','contraste','metrica','estimacion','p025','p975','replicas_validas']]),
'![Diferencias pareadas](graficos/diferencias_pareadas.png)','',
'## Estabilidad por partición y denominadores','',table(hm[hm.epoca.eq('ALL')][['horizonte_h','bloque','modelo','n_emisiones','positivos','prevalencia','AP','Brier']]),'',
'Denominadores de inicios únicos y de entrenamiento:', '',table(parts),'',
'Diferencias por partición:', '',table(pairs[pairs.metrica.isin(['AP','Brier'])][['horizonte_h','bloque','contraste','metrica','delta']]),'',
'## Pérdida de soporte','',
'Estos conteos parten de emisiones elegibles con ventana INIA básica, objetivo y fronteras válidos. Las pérdidas adicionales no se confunden con pérdidas previas por historial/objetivo: esas constan en exclusiones_resumen.csv y exclusiones_emisiones.csv, con motivos no excluyentes y primario. elegibilidad_adicional.csv registra las ventanas extra hora a hora. No se entrenaron modelos sobre soportes potenciales separados.','',
 table(support[support.brazo_potencial.eq('A')][['horizonte_h','bloque','rol','base_elegible_A','comun_4_brazos','perdidas_vs_A','positivos_A','positivos_comunes']]),'',
'Los soportes potenciales A/B/C/D completos están en tablas/soporte_potencial_y_perdidas.csv. Huanta y presión propia se exigen en todas las siete marcas, aunque algunas columnas solo utilicen seis anteriores. La comparación principal pierde horas por ambas exigencias sin imputar.','',
'## Efecto de huecos de Huanta','',table(pd.read_csv(T/'efecto_huecos_huanta.csv')),'','Los motivos son no excluyentes. Las pérdidas marginales exigen todas las demás variables. Inicios afectados pueden conservar otra emisión elegible; inicios_recuperables_marginalmente cuenta los que ganarían al menos una oportunidad si se eliminara solo esa exigencia. Es un diagnóstico de soporte: no se rellenaron datos ni se entrenó sin sensores. Los entrenamientos expansivos se solapan. Detalle de huecos y disponibilidad en huecos_por_sensor.csv y cobertura_anual_huanta.csv.','','## Avisos en toda la rejilla fijada','',
'Grupos contiguos a una hora, emparejamiento cronológico uno a uno, redundantes en el denominador de precisión. Falsas alarmas por mes equivalente usan emisiones reales / (365.25×24/12). Inicios sin oportunidad se excluyen del denominador de recobrado y quedan explícitos en metricas_avisos.csv y evaluacion_inicios.csv. Anticipación media solo entre aciertos, no medida independiente de su selección.','',
 table(agg[['horizonte_h','politica','modelo','grupos_avisos','falsas_alarmas','redundantes','inicios_evaluables','inicios_anticipados','inicios_omitidos','recall_inicios','precision_avisos','falsas_alarmas_por_mes','anticipacion_media_h']]),'',
'Los cambios de cada métrica de avisos por partición están en diferencias_por_particion.csv; cambios agregados con IC pareados, incluidos conteos y anticipación media, en intervalos_pareados.csv. La mediana se informa descriptivamente por partición; no se usa para seleccionar umbral. Desgloses estacionales mantienen época de aviso e inicio según el procedimiento heredado.','',
'## Curvas y calibración descriptiva','',table(pd.read_csv(T/'calibracion_agregada.csv')),'',
'Calibración en intervalos fijos, sin reajuste. Los denominadores, positivos, probabilidad media y fracción observada de cada intervalo están en calibracion.csv. Intervalos de alta probabilidad pueden tener pocos casos; no inferir calibración fiable de una línea visual.','']
for h in [1,3]:
 lines += [f'![PR {h}h](graficos/PR_{h}h.png)',f'![Calibración {h}h](graficos/calibracion_{h}h.png)',f'![Avisos {h}h](graficos/avisos_{h}h.png)','']
lines += ['## Hipótesis física del usuario','', 'El usuario plantea que Huanta, al este de la zona de formación del terral, podría registrar condiciones precursoras; distingue esta situación de Gabriela y La Serena, al oeste, y la considera semejante a Pisco, más al sur. Es una hipótesis previa del usuario. El rendimiento observado no demuestra ese mecanismo físico.','', '## Fuentes, comprobaciones y límites','',
'Solo once CSV anuales INIA autorizados y la tabla horaria auditada de Huanta para 2013–2023. No se abrieron originales con bordes fuera del período ni otras observaciones, informes o gráficos globales. Se verifican códigos y alturas LLHTA/LLHHR/LLHVV2M/LLHDV2M/LLHPA a 2 m. Las columnas INIA se conservan a sus alturas declaradas; metadatos_inia.csv registra su evidencia, sin resolver la discrepancia documental T/HR. Ceros conservados, dirección circular; sin gradientes de presión ni variables de 10 m.','',
'La adaptación y revisión anterior a entrenar están en revision_previa.md. Se conserva la corrección de rutas documentada en Pisco. La repetición completa de este experimento y sus comparaciones de hashes constan en reproduccion.json. No se ordena Huanta frente a Pisco o Gabriela sobre soportes distintos.','',
'El protocolo y lista de columnas quedaron registrados con hash y fecha antes del primer ajuste; manifiesto_previo.json y manifiesto_fuentes.csv conservan hashes antes/después. Comprobaciones.json, verificacion.json y verificacion_independiente.json documentan controles de integridad, causalidad, etiquetas, fronteras, escalas, soporte y denominadores. Parámetros por brazo/partición/horizonte en ajustes/<brazo>/ajustes; referencias mes×hora auxiliares en ajustes/<brazo>/tablas.','',
'Bootstrap condicional a estos modelos y catálogo: 300 réplicas, semilla 20132023, bloques móviles de tres meses dentro de cada bienio, mismas multiplicidades para todos los brazos. Los meses extremos tienen menor probabilidad de selección al no envolver. No incluye incertidumbre del entrenamiento, etiqueta, medición o selección previa del desarrollo. Avisos se remuestrean después de vincular, asignando grupos al mes del aviso e inicios al mes del inicio, lo que aproxima pero no reconstruye una cronología simulada. Pocos inicios y tres validaciones limitan la estabilidad de los intervalos.','',
'El usuario informa actualización automática horaria para todas las estaciones. No se introdujeron retrasos hipotéticos ni se buscaron desplazamientos. La coincidencia física de las marcas y disponibilidad inmediata en t siguen siendo supuestos separados del significado de los intervalos. AP mide ordenamiento de probabilidades y no es porcentaje de aciertos. Ausencia de evidencia de mejora es evidencia no concluyente, no equivalencia.','',
'Antes de interpretar cualquier mejora como capacidad operacional se necesita confirmar zona horaria y cambios históricos, inicio/cierre y cálculo del intervalo, dirección/calmas, latencia y datos efectivamente disponibles al emitir, correspondencia física entre estaciones, continuidad de alturas/calibración y referencia de presión de los XLS. Se necesita además evaluación prospectiva o una prueba temporal independiente con reglas fijadas y criterios de utilidad operacional definidos. Este trabajo no consulta el período reservado ni convierte estas validaciones de desarrollo en prueba final.','']
(OUT/'informe.md').write_text('\n'.join(lines))
print(table(pd.DataFrame(summary)))
print(table(ci[ci.contraste.isin(['B-A','C-A','D-B'])&ci.metrica.isin(['AP','Brier'])][['horizonte_h','contraste','metrica','estimacion','p025','p975']]))
