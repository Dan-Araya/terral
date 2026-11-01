#!/usr/bin/env python3
"""Informe solo desde salidas de validación autorizadas. No modifica configuraciones."""
import sys,json
sys.modules['numexpr']=None
from pathlib import Path
import numpy as np
import pandas as pd
OUT=Path(__file__).resolve().parent

def read(name): return pd.read_csv(OUT/'tablas'/f'{name}.csv')
def md(df):
 def fmt(v):
  if pd.isna(v): return '—'
  if isinstance(v,(float,np.floating)): return f'{v:.5g}'
  return str(v)
 return '| '+' | '.join(df.columns)+' |\n| '+' | '.join(['---']*len(df.columns))+' |\n'+'\n'.join('| '+' | '.join(fmt(v) for v in row)+' |' for row in df.itertuples(index=False,name=None))+'\n'
pred=pd.read_csv(OUT/'predicciones_validacion.csv',parse_dates=['emision'])
hm=read('metricas_horarias'); am=read('metricas_avisos'); ex=read('exclusiones_resumen'); part=read('particiones'); ci=read('incertidumbre'); cal=read('calibracion'); a=read('correspondencia_avisos'); e=read('evaluacion_inicios')
pooled=[]; seasonal=[]
from ejecutar import pr
for (h,m),d in pred.groupby(['horizonte_h','modelo']):
 for epoch in ['ALL','DJF','MAM','JJA','SON']:
  g=d if epoch=='ALL' else d[d.epoca.eq(epoch)]
  ap,_=pr(g.objetivo,g.probabilidad); bs=((g.probabilidad-g.objetivo)**2).mean(); ref=((g.p_frecuencia-g.objetivo)**2).mean()
  pooled.append({'h':h,'modelo':m,'epoca':epoch,'emisiones':len(g),'positivos':int(g.objetivo.sum()),'prevalencia':g.objetivo.mean(),'AP':ap,'Brier':bs,'skill_vs_frecuencia':1-bs/ref if ref else np.nan})
pooled=pd.DataFrame(pooled); pooled.to_csv(OUT/'tablas/metricas_horarias_agregadas.csv',index=False)
summary=[]
for (h,m,p),d in am[am.epoca.eq('ALL')].groupby(['horizonte_h','modelo','politica']):
 aa=a[(a.horizonte_h==h)&(a.modelo==m)&(a.politica==p)]
 ev=d.inicios_evaluables.sum(); tp=d.inicios_anticipados.sum(); groups=d.grupos_avisos.sum(); fp=d.falsas_alarmas.sum(); months=d.meses_equivalentes.sum()
 summary.append({'h':h,'modelo':m,'politica':p,'inicios':ev,'anticipados':tp,'omitidos':ev-tp,'recall':tp/ev,'avisos':groups,'precision':d.aciertos_avisos.sum()/groups if groups else np.nan,'falsas':fp,'redundantes':d.redundantes.sum(),'falsas_mes':fp/months,'anticipacion_media':aa.anticipacion_h.mean(),'meses_equivalentes':months})
summary=pd.DataFrame(summary); summary.to_csv(OUT/'tablas/metricas_avisos_agregadas.csv',index=False)
for (h,epoch),d in am[am.modelo.eq('logistica')&am.politica.eq('p>=0.1')&am.epoca.ne('ALL')].groupby(['horizonte_h','epoca']):
 ev=d.inicios_evaluables.sum(); tp=d.inicios_anticipados.sum(); groups=d.grupos_avisos.sum(); months=d.meses_equivalentes.sum()
 seasonal.append({'h':h,'epoca':epoch,'emisiones':d.n_emisiones.sum(),'meses_eq':months,'inicios':ev,'anticipados':tp,'omitidos':ev-tp,'avisos':groups,'precision':d.aciertos_avisos.sum()/groups if groups else np.nan,'falsas_mes':d.falsas_alarmas.sum()/months})
seasonal=pd.DataFrame(seasonal); seasonal.to_csv(OUT/'tablas/avisos_estacionales_ejemplo.csv',index=False)
# Aggregate descriptive calibration with fixed bins, never recalibrate.
cagg=[]
for (h,m,lo,hi),g in cal[cal.epoca.eq('ALL')].groupby(['horizonte_h','modelo','limite_inf','limite_sup']):
 n=g.n.sum(); positives=g.positivos.sum()
 cagg.append({'h':h,'modelo':m,'p_desde':lo,'p_hasta':hi,'n':n,'positivos':positives,'p_media':(g.p_media.fillna(0)*g.n).sum()/n if n else np.nan,'observado':positives/n if n else np.nan})
cagg=pd.DataFrame(cagg); cagg.to_csv(OUT/'tablas/calibracion_agregada.csv',index=False)
globalex=ex[ex.ambito.eq('global_2013_2023')][['horizonte_h','motivo','n_con_motivo','n_primario','incluidas']]
front=ex[ex.motivo.isin(['soporte_cruza_frontera','tramo_cruza_frontera'])][['horizonte_h','ambito','motivo','n_con_motivo','n_primario']]
blockhour=hm[hm.epoca.eq('ALL')][['horizonte_h','bloque','modelo','n_emisiones','positivos','prevalencia','AP','Brier','Brier_skill_vs_frecuencia']]
blockevents=am[am.epoca.eq('ALL')&am.modelo.eq('logistica')&am.politica.eq('p>=0.1')][['horizonte_h','bloque','inicios_evaluables','inicios_anticipados','inicios_omitidos','grupos_avisos','precision_avisos','falsas_alarmas_por_mes','anticipacion_media_h']]
interval=ci[ci.politica.isna()|ci.politica.eq('')][['horizonte_h','modelo','metrica','estimacion','p025','p975']]
exampleci=ci[ci.modelo.eq('logistica')&ci.politica.eq('p>=0.1')][['horizonte_h','metrica','estimacion','p025','p975']]
leadrows=[]
for (h,m,p),g in a[a.estado.eq('acierto')].groupby(['horizonte_h','modelo','politica']):
 for lead,z in g.groupby('anticipacion_h'): leadrows.append({'h':h,'modelo':m,'politica':p,'anticipacion_h':lead,'n_inicios':len(z)})
leads=pd.DataFrame(leadrows); leads.to_csv(OUT/'tablas/distribucion_anticipacion.csv',index=False)
text=f'''# Primera línea base retrospectiva de inicio candidato v0

**Hay evidencia de anticipación del cumplimiento del criterio histórico por las observaciones previas de INIA frente a las referencias simples. No se ha validado un predictor del fenómeno físico de terral.** La logística mejora AP y Brier frente a la frecuencia mes×hora en los tres bloques y ambos horizontes. La utilidad práctica permanece abierta: la detección aumenta a costa de numerosas falsas alarmas, las probabilidades no tienen calibración operacional demostrada y la anticipación presupone disponibilidad inmediata de promedios horarios.

## Alcance y protocolo

Solo Vicuña–INIA, 2013–2023. Primera marca del tramo v0, con una marca previa evaluable que no cumple. Los 156 inicios v0 satisfacen esa condición; se conservan 867 horas candidatas, 95.096 horas no_cumple y 445 desconocidas. Las fuentes permanecen intactas. No se abre el período reservado ni se usan otras estaciones, presión o sensores de 5 m como predictores. No se cambian umbrales ni catálogo. No hay consulta web ni despliegue.

El [protocolo previo](protocolo.md) fija antes del entrenamiento tres referencias, 35 predictores, regularización C=1, ventanas completas, particiones, métricas, rejilla y agrupación de avisos. No hubo búsqueda, selección de predictores, pesos de clase ni recalibración. La regla hipotética requiere sector [0,180], T>10, HR<40, V>1 y en una hora calentamiento, secado y aumento de viento. Sus constantes no modifican las etiquetas. Su probabilidad binaria se estima únicamente en entrenamiento. Frecuencia mes×hora con n<100 recurre a hora; ambas referencias tienen suavizado prefijado, ajustado solo con entrenamiento. Las referencias exploratorias del catálogo sobre toda la muestra no se reutilizan.

Las fechas se mantienen sin zona. Una hora significa una hora del reloj registrado. T y HR tienen altura de encabezado 2 m, discrepante con 1,5 m de la referencia científica; se hereda esa limitación. Latencia, comienzo/final de agregación horaria y calidad instrumental aún no están resueltos. La disponibilidad inmediata en t puede exagerar la anticipación operativa.

## Denominadores y exclusiones

Se exige validez de las cuatro variables en las siete marcas [t−6,t]; medias y máximo previos usan [t−6,t−1]. Sin imputación, relleno o interpolación. Objetivos con cualquier desconocida se excluyen, aunque exista un inicio conocido en ese intervalo. Una emisión puede tener varios inicios en su objetivo: el binario cuenta una vez, pero la correspondencia conserva todos. Ninguna hora desconocida es una negativa.

{md(globalex)}

Sobre 96.408 emisiones potenciales globales, quedan excluidas **1.404 a 1 h** y **1.430 a 3 h**; quedan 95.004 y 94.978 antes de fronteras de partición. `n_con_motivo` se solapa: no sumarlo. `n_primario` sigue la prioridad del protocolo y sí suma las exclusiones. Parte de objetivo_desconocido coincide con t desconocido; las pérdidas primarias adicionales son 13 y 37. La ventana previa aporta 78 exclusiones primarias adicionales en cada horizonte (incluidas las seis primeras horas autorizadas).

En validación 2018–2023 hay **51.919 emisiones a 1 h (79 positivas)** y **51.905 a 3 h (233 positivas)**, cada una repetida solo por modelo en el CSV. Hay **79 inicios con oportunidad evaluable**, 29/29/21 por bloque, sin inicios sin oportunidad en validación. A 3 h no hay siempre tres emisiones positivas por inicio: algunas horas previas ya pertenecen a otro tramo activo. Los bloques aportan cerca de 71,1 meses equivalentes de exposición, no 72 meses completos de emisión posible.

### Fronteras y desarrollo cronológico

Cada soporte [t−6,t+h] debe estar entero dentro de su partición. Las últimas h emisiones y primeras seis marcas de cada partición se purgan; las seis primeras del período global ya fallan la ventana previa. Ningún tramo v0 cruza estas fronteras, pero se implementa la purga de su soporte completo para ese caso.

{md(front)}

{md(part)}

Estos son tres bloques de **validación de desarrollo**, no tres pruebas finales independientes. Las validaciones anteriores se incorporan al entrenamiento expansivo posterior según lo fijado, sin usar sus resultados para escoger configuraciones.

## Probabilidades y discriminación

AP es average precision escalonada, con empates agrupados, no área trapezoidal. La prevalencia de emisiones es mucho menor que la proporción de horas candidatas, pues se pronostica inicio cuando no hay tramo activo.

{md(blockhour)}

Agregación descriptiva de las emisiones de los tres modelos congelados por bloque:

{md(pooled[pooled.epoca.eq('ALL')])}

La logística supera la frecuencia y la regla en AP en todos los bloques. En Brier, la regla supera ligeramente a la logística en 2018–2019 a 1 h (0,001567 frente a 0,001598); la logística mejora en los otros casos. El Brier bajo en términos absolutos refleja también la escasa prevalencia: se informa Brier skill y Brier de la constante aprendida en entrenamiento en la tabla completa.

![PR 1 h](graficos/precision_recall_1h.png)
![PR 3 h](graficos/precision_recall_3h.png)

### Calibración descriptiva

En la agregación, las probabilidades logísticas ≥0,5 tienen media 0,736 y frecuencia observada 0,600 a 1 h (20 emisiones); a 3 h, 0,629 frente a 0,486 (37 emisiones). Es evidencia descriptiva de sobreestimación en esa celda, con muestra pequeña y dependencia temporal.

Sin calibración posterior ni elección de umbral en validación. Las celdas fijas permiten comparar probabilidad media y frecuencia observada, con conteos. Las probabilidades altas reúnen pocas emisiones y fluctúan por bloque: buena discriminación no equivale a probabilidades fiables. Los gráficos anotan n; las tablas conservan también celdas vacías. DJF no tiene inicios v0, por lo que AP y recall de eventos son indefinidos, no cero certificado del fenómeno.

{md(cagg[cagg.modelo.eq('logistica')&cagg.n.gt(0)])}

![Calibración 1 h](graficos/calibracion_1h.png)
![Calibración 3 h](graficos/calibracion_3h.png)

## Avisos, anticipación y omisiones

Agrupar solo emisiones con aviso consecutivas, con separación exacta de una hora. Cualquier ausencia de aviso, exclusión, desconocida o tramo activo rompe la cadena. Vinculación cronológica uno a uno: un inicio y un grupo producen como máximo un acierto. Los grupos adicionales que alcanzan solo inicios ya vinculados son redundantes y permanecen en el denominador de precisión; no son nuevas detecciones ni falsas alarmas sin inicio.

La anticipación usa la primera emisión del grupo que realmente tiene el inicio en su intervalo objetivo. No se atribuye toda la longitud de una cadena a la anticipación. Un pronóstico de 3 h puede acertar con solo 1 h de aviso: el horizonte no garantiza tres horas útiles.

Todas las políticas prefijadas, agregadas; una celda sin avisos no tiene precisión definida:

{md(summary)}

**Ejemplo descriptivo de la rejilla, sin selección operacional: p≥0,1.** A 1 h la logística anticipa 34/79 (43,0%), omite 45, con 34 aciertos en 86 grupos (39,5% de precisión), 52 falsas alarmas y aproximadamente 0,73 por mes equivalente. Su aviso acertado está necesariamente a una hora registrada. A 3 h anticipa 57/79 (72,2%), omite 22; el promedio de anticipación ronda 2,10 h, no 3 h. La regla nativa aporta 26/79 a 1 h y 31/79 a 3 h, con menor carga de avisos. Estas políticas tienen costos diferentes y no están comparadas a una tolerancia de falsas alarmas acordada.

{md(blockevents)}

{md(leads[leads.modelo.eq('logistica')&leads.politica.eq('p>=0.1')])}

![Compromiso 1 h](graficos/compromiso_avisos_1h.png)
![Compromiso 3 h](graficos/compromiso_avisos_3h.png)

Las curvas muestran todos los umbrales prefijados; no se maximiza F1 ni se declara un ganador. Avisos con probabilidades muy bajas detectan casi todos los inicios, pero generan decenas de falsas alarmas por mes equivalente. Probabilidades altas reducen las falsas alarmas y pierden numerosos inicios. El distinto comportamiento de 2018–2019 frente a 2020–2021 ilustra variación temporal sustancial.

## Estacionalidad y dónde falla

Tabla horaria por estación y horizonte, para logística:

{md(pooled[pooled.modelo.eq('logistica')&pooled.epoca.ne('ALL')])}

Ejemplo p≥0,1, denominadores de inicios por estación del inicio, avisos por estación de primera emisión:

{md(seasonal)}

JJA reúne 58/79 inicios: con p≥0,1 se anticipan 30/58 a 1 h y 47/58 a 3 h, pero se producen respectivamente 2,43 y 5,98 falsas alarmas por mes equivalente de JJA. SON falla especialmente en detección: solo 1/11 a 1 h y 4/11 a 3 h. MAM aporta 10 inicios, con 3 y 6 anticipados. En SON hay pocos inicios y los porcentajes son inestables. DJF tiene cero inicios v0 pero puede generar avisos: ese fallo del objetivo está en las tablas, sin inferir ausencia física de terral. La proporción elevada de falsos avisos frente a la referencia significa que transiciones cálidas/secas/ventosas no bastan para anticipar de forma selectiva este criterio. No se investigan aquí mecanismos sinópticos ni se atribuyen causalmente errores a instrumentos.

La tabla de correspondencia permite examinar avisos falsos y redundantes, y `evaluacion_inicios.csv` enumera cada inicio anticipado u omitido en cada política. No se rescatan omisiones cambiando el catálogo o excluyendo candidatos cortos, ambiguos o con banderas técnicas.

## Incertidumbre temporal

300 réplicas pareadas de bloques móviles contiguos de tres meses dentro de cada validación bienal, semilla 20132023. Intervalos percentiles; los mismos bloques para los tres modelos. No se remuestrean horas independientes. Para avisos se agregan conteos previamente vinculados por mes, sin unir horas artificialmente.

{md(interval)}

Para el ejemplo p≥0,1:

{md(exampleci)}

Los intervalos agregados de diferencia AP y Brier respaldan el aporte frente a frecuencia bajo esta aproximación. Solo hay tres bloques bienales y 79 inicios de criterio: la inferencia sigue siendo exploratoria. El bootstrap es condicional al catálogo y ajustes, no incluye error de etiqueta, incertidumbre de entrenamiento, latencia ni cambios de instrumentación. Las ventanas móviles sin envoltura representan menos los meses de los extremos; la asignación por mes conserva correspondencias originales, pero no representa toda la incertidumbre de grupos que atraviesan límites. No permite intervalos estacionales fiables donde no hay o hay muy pocos inicios. Estos límites impiden interpretar los intervalos como garantía operacional.

## Comprobaciones y reproducción

`comprobaciones.json` registra límites, hashes, versiones, validez, ausencia de información futura, soportes dentro de particiones y unicidad de aciertos. `verificar.py` recalcula desde los CSV autorizados etiquetas, ventanas, todas las listas de inicios del objetivo, escalado de entrenamiento, predictores/logística en emisiones de prueba, continuidad de avisos y denominadores. El ensayo contrafactual cambia todas las observaciones posteriores a un t y exige que los predictores anteriores permanezcan idénticos. La lista de entradas es cerrada y los hashes antes/después coinciden.

Correcciones de implementación documentadas en [correcciones_implementacion.md](correcciones_implementacion.md); ninguna introduce selección por desempeño. El registro previo preserva el hash del protocolo antes de entrenar.

Desde la raíz del repositorio, Python y versiones de `requirements.txt`:

```bash
python investigacion_ceazamet/linea_base_inicio_v0/ejecutar.py
python investigacion_ceazamet/linea_base_inicio_v0/verificar.py
python investigacion_ceazamet/linea_base_inicio_v0/informar.py
```

No requiere scikit-learn: la logística se implementa con pérdida y gradiente explícitos, optimizados con SciPy; las probabilidades y el escalado quedan auditables en `ajustes/`. CSV separados por coma, encabezados y punto decimal; vacío significa no disponible/indefinido, no cero.

Entregables: protocolo, scripts, `predicciones_validacion.csv` (instante, horizonte, objetivo, modelo, bloque, probabilidad, todos los inicios asociados y soporte), tablas de exclusiones por emisión/resumen, particiones, referencias aprendidas, métricas horarias/avisos, PR, calibración, correspondencia, estado de cada inicio, anticipación, incertidumbre, seis PNG, manifiesto, registros y verificaciones. No se guarda ni despliega un servicio de alertas.

## Qué queda por comprobar

La mejora retrospectiva indica que INIA contiene información previa útil **para el inicio de los tramos v0**; resulta insuficiente para declarar utilidad operativa o validación meteorológica. Falta resolver zona y semántica de marcas, latencia real de publicación, altura/calibración/mantenimiento de sensores y corroboración meteorológica independiente de inicios y negativas. También faltan costos de falsa alarma/omisión y anticipación mínima para una decisión concreta, y evaluar de forma prospectiva una política congelada. Nada de ello se prueba usando el período reservado en este encargo. No se confunde predicción del criterio con confirmación del terral físico.
'''
(OUT/'informe.md').write_text(text)
print('Informe y agregaciones generados sin ajuste de modelos.')
