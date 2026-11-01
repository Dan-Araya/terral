#!/usr/bin/env python3
"""Informe determinista; ninguna decisión modifica entrenamiento ni umbrales."""
import os,sys,json
os.environ['OPENBLAS_NUM_THREADS']='1'; os.environ['MPLCONFIGDIR']='/tmp/pisco-huanta-mpl'; sys.modules['numexpr']=None; sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
BASE=Path(__file__).resolve().parent; OUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else BASE
T=OUT/'tablas'; G=OUT/'graficos'; G.mkdir(exist_ok=True)
config=json.loads((OUT/'configuracion_experimento.json').read_text()); contrasts=config['contrastes_principales']+config['contrastes_secundarios']
ci=pd.read_csv(T/'intervalos_pareados.csv').fillna({'politica':''}); hourly=ci[ci.metrica.isin(['AP','Brier'])]
diffs=pd.read_csv(T/'diferencias_por_particion.csv'); hm=pd.read_csv(T/'metricas_horarias.csv'); hm=hm[hm.epoca.eq('ALL')]
parts=pd.read_csv(T/'particiones.csv'); losses=pd.read_csv(T/'perdidas_vs_individuales.csv'); alerts=pd.read_csv(T/'avisos_agregados.csv')
def md(d):
 def value(v):
  if pd.isna(v): return '—'
  if isinstance(v,(float,np.floating)): return f'{v:.7g}'
  return str(v).replace('|',';')
 return '| '+' | '.join(d.columns)+' |\n| '+' | '.join(['---']*len(d.columns))+' |\n'+'\n'.join('| '+' | '.join(value(v) for v in row)+' |' for row in d.itertuples(index=False,name=None))+'\n'
def classify(h,c):
 rows=hourly[(hourly.horizonte_h==h)&hourly.contraste.eq(c)].set_index('metrica')
 ds=diffs[(diffs.horizonte_h==h)&diffs.contraste.eq(c)&diffs.metrica.isin(['AP','Brier'])].pivot(index='bloque',columns='metrica',values='delta')
 improve=bool((ds.AP>0).all() and (ds.Brier<0).all() and rows.loc['AP','p025']>0 and rows.loc['Brier','p975']<0)
 worsen=bool((ds.AP<0).all() and (ds.Brier>0).all() and rows.loc['AP','p975']<0 and rows.loc['Brier','p025']>0)
 zero=bool((rows.p025<=0).all() and (rows.p975>=0).all())
 label='Mejora consistente' if improve else 'Empeoramiento consistente' if worsen else 'Ausencia de evidencia de mejora' if zero else 'Resultado incierto'
 return dict(horizonte_h=h,contraste=c,interpretacion=label,particiones_AP_favorable=int((ds.AP>0).sum()),particiones_Brier_favorable=int((ds.Brier<0).sum()),IC_AP_incluye_cero=bool(rows.loc['AP','p025']<=0<=rows.loc['AP','p975']),IC_Brier_incluye_cero=bool(rows.loc['Brier','p025']<=0<=rows.loc['Brier','p975']))
interpret=pd.DataFrame([classify(h,c) for h in [1,3] for c in contrasts]); interpret.to_csv(T/'interpretacion.csv',index=False)
summary=[]
for h in [1,3]:
 for pressure,pair in [(False,['G-C','G-E']),(True,['H-D','H-F'])]:
  rows=interpret[(interpret.horizonte_h==h)&interpret.contraste.isin(pair)]; good=rows[rows.interpretacion.eq('Mejora consistente')]
  txt='Mejora consistente frente a ambas estaciones individuales' if len(good)==2 else 'Mejora consistente solo en '+', '.join(good.contraste) if len(good)==1 else 'No se acredita mejora consistente frente a ninguna de las dos estaciones individuales'
  summary.append(dict(horizonte_h=h,presion_propia=pressure,conclusion=txt))
summary=pd.DataFrame(summary); summary.to_csv(T/'conclusion_combinacion.csv',index=False)
# Aggregate support without summing overlapping training partitions.
validation=parts[parts.rol.eq('validacion')]
agg_support=validation.groupby('horizonte_h')[['n','positivos','inicios_con_oportunidad']].sum().reset_index()
agg_support.to_csv(T/'soporte_validacion_agregado.csv',index=False)
# All aggregate metrics including unique event counts (event IDs do not cross validation partitions after purge).
agg=hourly[~hourly.contraste.str.contains('-')].pivot(index=['horizonte_h','contraste'],columns='metrica',values='estimacion').reset_index().rename(columns={'contraste':'modelo'})
agg=agg.merge(agg_support,on='horizonte_h'); agg.to_csv(T/'metricas_horarias_agregadas.csv',index=False)
# Quality/availability reason counts per sensor and eligibility partition, independent nonexclusive causes.
reason=pd.read_csv(T/'elegibilidad_adicional.csv'); flags=[c for c in reason if c.endswith('ventana_incompleta')]
r=[]
for key,z in reason.groupby(['horizonte_h','bloque','rol']):
 for flag in flags:
  bad=z[flag]; r.append(dict(zip(['horizonte_h','bloque','rol'],key),motivo=flag,horas=int(bad.sum()),positivos=int(z.loc[bad,'objetivo'].sum()),inicios_afectados=len({cid for ids in z.loc[bad,'id_inicio_objetivo'].fillna('') for cid in ids.split('|') if cid})))
pd.DataFrame(r).to_csv(T/'exclusiones_adicionales_resumen.csv',index=False)
# Graphics with the same complete arm order and all predeclared primary contrasts.
colors=plt.cm.tab10(np.arange(8)); plt.rcParams.update({'font.size':10})
for h in [1,3]:
 fig,axes=plt.subplots(1,2,figsize=(13,5))
 for ax,metric in zip(axes,['AP','Brier']):
  z=hourly[(hourly.horizonte_h==h)&hourly.metrica.eq(metric)&~hourly.contraste.str.contains('-')].set_index('contraste').loc[list('ABCDEFGH')]
  ax.errorbar(np.arange(8),z.estimacion,yerr=[z.estimacion-z.p025,z.p975-z.estimacion],fmt='none',ecolor='0.4',capsize=3)
  ax.scatter(np.arange(8),z.estimacion,c=colors,s=40); ax.set_xticks(range(8),list('ABCDEFGH')); ax.set_title(metric+(' (mayor es favorable)' if metric=='AP' else ' (menor es favorable)')); ax.grid(alpha=.2)
 fig.suptitle(f'Predicciones de validación agrupadas · horizonte {h} h · IC marginales 95%'); fig.tight_layout(); fig.savefig(G/f'metricas_{h}h.png',dpi=150); plt.close(fig)
 fig,axes=plt.subplots(1,2,figsize=(13,5))
 for ax,metric in zip(axes,['AP','Brier']):
  z=hourly[(hourly.horizonte_h==h)&hourly.metrica.eq(metric)&hourly.contraste.isin(config['contrastes_principales'])].set_index('contraste').loc[config['contrastes_principales']]
  ax.errorbar(z.estimacion,np.arange(4),xerr=[z.estimacion-z.p025,z.p975-z.estimacion],fmt='o',capsize=4); ax.axvline(0,c='0.5',ls='--'); ax.set_yticks(range(4),z.index); ax.set_xlabel('Δ '+metric); ax.grid(alpha=.2)
 fig.suptitle(f'Qué añade cada estación cuando ya está la otra · {h} h'); fig.tight_layout(); fig.savefig(G/f'contrastes_{h}h.png',dpi=150); plt.close(fig)
 cal=pd.read_csv(T/'calibracion_agregada.csv'); fig,ax=plt.subplots(figsize=(7,6))
 for arm,color in zip('ABCDEFGH',colors):
  z=cal[(cal.horizonte_h==h)&cal.modelo.eq(arm)&cal.n.gt(0)]; ax.plot(z.p_media,z.frecuencia_observada,'o-',label=arm,c=color)
 ax.plot([0,1],[0,1],'--',c='gray'); ax.set(xlabel='Probabilidad media',ylabel='Frecuencia observada',title=f'Calibración agregada · {h} h'); ax.legend(ncol=4); ax.grid(alpha=.2); fig.tight_layout(); fig.savefig(G/f'calibracion_{h}h.png',dpi=150); plt.close(fig)
 fig,axes=plt.subplots(1,2,figsize=(13,5))
 for arm,color in zip('ABCDEFGH',colors):
  z=alerts[(alerts.horizonte_h==h)&alerts.modelo.eq(arm)]
  for ax,y in zip(axes,['recall_inicios','precision_avisos']): ax.plot(z.falsas_alarmas_por_mes,z[y],'o-',c=color,label=arm); ax.set(xlabel='Falsas alarmas por mes equivalente',ylabel=y); ax.grid(alpha=.2)
 axes[1].legend(ncol=4); fig.suptitle(f'Rejilla completa de siete umbrales, sin selección · {h} h'); fig.tight_layout(); fig.savefig(G/f'avis_os_{h}h.png',dpi=150); plt.close(fig)
text='''# Pisco Elqui + Llanos de Huanta: inicio del criterio histórico en INIA

Experimento exploratorio local restringido a 2013–2023. Las ocho variantes se reentrenaron desde cero sobre el mismo soporte de entrenamiento y validación, con 48 ajustes por ejecución. No se reutilizaron modelos, predicciones o métricas anteriores. Las tablas de soporte anteriores solo sirven para comprobar pérdidas.

## Conclusión predefinida

'''+md(summary)+'''\nLa combinación solo cumple mejora consistente frente a ambas si cumplen simultáneamente G−C y G−E (sin presión propia), o H−D y H−F (con presión propia). Cada contraste exige ΔAP>0 y ΔBrier<0 en las tres particiones y ambos intervalos agregados estrictamente favorables. La ausencia de significación no demuestra redundancia. Los siguientes resultados incluyen expresamente intervalos que contienen cero y resultados desfavorables.

'''+md(interpret)+'''\n## Método y alcance

Objetivo: algún inicio conocido del catálogo histórico en (t,t+h], h=1,3; emisión con estado no_cumple y etiqueta futura evaluable. Ventana estricta [t−6,t]; purgas de ventana completa y de tramos que cruzan fronteras. Entrenamiento 2013–2017/2013–2019/2013–2021 y validación 2018–2019/2020–2021/2022–2023. Escalas poblacionales solo de entrenamiento, logística C=1, intercepto libre, L-BFGS-B y tolerancias originales. Ninguna búsqueda, imputación, corrección de presión, desplazamiento temporal, selección de variable o umbral.

A: INIA; B: +presión propia; C: +Pisco; D: +presión propia+Pisco; E: +Huanta; F: +presión propia+Huanta; G: +Pisco+Huanta; H: +presión propia+Pisco+Huanta. Predictores: 35/41/72/78/72/78/109/115. Dirección circular mediante seno/coseno. Viento y dirección a 2 m sin sustitución; Pisco T/HR 1.5 m y Huanta T/HR 2 m. Máximo previo de seis promedios horarios de viento: no es ráfaga. Sensores, máscaras y unidades contrastados con auditoría, configuración y metadatos locales.

AP no es porcentaje de aciertos. AP agregada mezcla las predicciones de tres modelos y no es promedio de AP de particiones. Brier es promedio por emisión. Calibración descriptiva en los bordes originales. Bootstrap pareado: 300 réplicas, semilla 20132023, ocho bloques móviles de tres meses dentro de cada bienio; mismas realizaciones para todas las variantes, contrastes y horizontes. Intervalos percentiles 95% por contraste, sin ajuste por múltiples comparaciones: no constituyen garantía conjunta del 95%. Intervalos condicionales a modelos y catálogo; no recogen incertidumbre de entrenamiento o etiquetado. Ponderación no uniforme de extremos mensuales; avisos remuestreados tras correspondencia original, sin reagrupar secuencias artificiales. Mediana de anticipación descriptiva, sin IC, como el protocolo.

## Soporte común

'''+md(parts)+'''\nLos entrenamientos expansivos se solapan y no se suman. Los inicios se cuentan por identificador; se distingue inicio afectado de inicio sin ninguna oportunidad restante.

### Pérdidas respecto a los dos experimentos individuales

'''+md(losses)+'''\nLas diferencias frente a informes anteriores también reflejan el cambio de soporte; no se atribuyen exclusivamente al modelo. Los conteos individuales se reconstruyeron desde las fuentes y se cotejaron con sus particiones guardadas. Las exclusiones básicas, fronteras y calidad están en tablas/exclusiones_resumen.csv y exclusiones_emisiones.csv; las exclusiones adicionales por estación/sensor son no excluyentes en elegibilidad_adicional.csv y exclusiones_adicionales_resumen.csv. La prioridad solo sirve para contabilizar una causa primaria (presión INIA, Pisco, Huanta). Cobertura, huecos y ceros válidos están separados por estación en las tablas. disponibilidad_calidad_ventanas.csv distingue ausencia de rechazo por calidad para cada partición y sensor.

## Métricas horarias

### Agregadas

'''+md(agg)+'''\n### Por partición

'''+md(hm[['horizonte_h','bloque','modelo','n_emisiones','positivos','AP','Brier']])+'''\n### Todos los contrastes agregados e IC 95%

'''+md(hourly[hourly.contraste.str.contains('-')][['horizonte_h','contraste','metrica','estimacion','p025','p975','replicas_validas']])+'''\n### Diferencias por partición

'''+md(diffs[diffs.metrica.isin(['AP','Brier'])])+'''\n## Avisos: toda la rejilla original

Reglas heredadas: p≥{.001,.003,.01,.03,.1,.3,.5}; agrupar emisiones consecutivas por una hora, asignación cronológica uno a uno, redundantes separados, anticipación desde la primera emisión que efectivamente anticipa. No se elige un umbral después de evaluar. Inicios evaluables exigen oportunidad en el soporte común y exposición en meses equivalentes.

'''+md(alerts[['horizonte_h','politica','modelo','grupos_avisos','inicios_anticipados','falsas_alarmas','redundantes','recall_inicios','precision_avisos','anticipacion_media_h']])+'''\nEl detalle de las 11 diferencias de aviso por umbral, partición y agregado, con intervalos, se conserva íntegro en [intervalos_pareados.csv](tablas/intervalos_pareados.csv) y [diferencias_por_particion.csv](tablas/diferencias_por_particion.csv). [metricas_avisos.csv](tablas/metricas_avisos.csv) incluye también estaciones del año, omitidos y mediana. [correspondencia_avisos.csv](tablas/correspondencia_avisos.csv) y [evaluacion_inicios.csv](tablas/evaluacion_inicios.csv) trazan todos los grupos e inicios.

## Calibración

'''+md(pd.read_csv(T/'calibracion_agregada.csv'))+'''\nLa calibración completa por partición y estación del año está en [calibracion.csv](tablas/calibracion.csv); no se recalibraron probabilidades sobre validación.

## Figuras

'''
for h in [1,3]:
 for name in ['metricas','contrastes','calibracion','avis_os']: text+=f'![{name} {h} h](graficos/{name}_{h}h.png)\n\n'
text+='''## Integridad, reproducción y limitaciones

El protocolo, configuración, código y hashes se registraron antes del primer ajuste. Ver registro_preentrenamiento.json y manifiesto_previo.json. Las fuentes se cotejan antes/después y los dos experimentos anteriores, catálogo y línea base se protegen mediante conservacion_previa.json. Las comprobaciones independientes reconstruyen soporte, etiquetas, fronteras y purgas, escalas, 115 características puntuales, probabilidades, AP con empates, Brier, calibración, bootstrap, sensores/máscaras y todos los avisos/intervalos. Comparten las fuentes derivadas auditadas y parte de ingestión; no certifican medidas instrumentales ni exactitud meteorológica. cierre.json y reproduccion.json documentan el resultado final y repetición completa.

Se mantiene el reloj registrado sin zona ni desfases: zona histórica, posición/duración del intervalo y disponibilidad efectiva de cada promedio siguen pendientes. La actualización horaria informada no resuelve esas cuestiones. Se asume disponibilidad inmediata en t únicamente como convenio del experimento. Persiste discrepancia documental INIA T/HR 1.5 vs 2 m; se respetan los sensores locales. INIA usa la máscara de promedio y las complementarias la de min/prom/max/%Datos, sin uniformarlas ni relajarlas. No se calcula gradiente ni reducción altimétrica de presión.

No se accedió deliberadamente al período reservado, descargaron datos, modificaron fuentes o catálogo, desplegaron alertas ni contactaron terceros. Las conclusiones corresponden al criterio histórico evaluado; no demuestran mecanismo físico ni capacidad operacional. No se demuestra redundancia por ausencia de evidencia de mejora. Reproducir con los comandos de LEEME.md.
'''
(OUT/'informe.md').write_text(text)
print(summary.to_string(index=False)); print('Informe y figuras guardados.')
