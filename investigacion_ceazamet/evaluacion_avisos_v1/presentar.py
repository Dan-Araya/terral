#!/usr/bin/env python3
"""Agregaciones y presentación desde evaluación congelada; sin ajuste de modelos."""
import os,sys
sys.modules['numexpr']=None
os.environ.setdefault('MPLCONFIGDIR','/tmp/terral-matplotlib')
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
OUT=Path(__file__).resolve().parent

def aggregate(metrics,episodes,events):
 rows=[]
 additive=['n_emisiones','positivos_horarios','emisiones_con_aviso','emisiones_acertadas','emisiones_falsas','inicios_catalogo','inicios_evaluables','inicios_sin_oportunidad','inicios_anticipados','inicios_omitidos','activaciones_dentro_h','alerta_ya_activa_antes_h','episodios','episodios_con_inicio','episodios_sin_inicio','episodios_mayores_h','episodios_ge24h','episodios_ge168h']+[c for c in metrics if c.startswith('horas_')]
 for (h,m,p,s),g in metrics.groupby(['horizonte_h','modelo','politica','epoca']):
  r={'horizonte_h':h,'bloque':'AGREGADO','modelo':m,'politica':p,'epoca':s,**{c:g[c].sum() for c in additive}}
  def ratio(a,b): return r[a]/r[b] if r[b] else np.nan
  r['precision_emisiones']=ratio('emisiones_acertadas','emisiones_con_aviso'); r['recall_emisiones']=ratio('emisiones_acertadas','positivos_horarios'); r['recall_inicios']=ratio('inicios_anticipados','inicios_evaluables')
  r['ocupacion_evaluable_pct']=100*ratio('horas_alerta_evaluables','horas_evaluables_pronostico'); r['ocupacion_conocida_pct']=100*ratio('horas_alerta_conocidas','horas_observacion_conocida'); r['ocupacion_reloj_pct']=100*ratio('horas_alerta','horas_reloj')
  r['precision_episodios_descriptiva']=ratio('episodios_con_inicio','episodios')
  e=events[(events.horizonte_h==h)&(events.modelo==m)&(events.politica==p)]
  d=episodes[(episodes.horizonte_h==h)&(episodes.modelo==m)&(episodes.politica==p)]
  if s!='ALL': e=e[e.epoca.eq(s)]; d=d[d.epoca_inicio_alerta.eq(s)]
  r['anticipacion_media_h']=e.anticipacion_h.mean(); r['edad_alerta_media_h']=e.edad_alerta_al_inicio_h.mean()
  r.update({'duracion_media_h':d.duracion_h.mean(),'duracion_mediana_h':d.duracion_h.median(),'duracion_p95_h':d.duracion_h.quantile(.95),'duracion_max_h':d.duracion_h.max()})
  rows.append(r)
 return pd.DataFrame(rows)

def plots(metrics,agg,episodes,audit):
 colors={'frecuencia':'#888888','regla':'#d48b17','logistica':'#1769aa','siempre':'#aa2360'}
 for h in [1,3]:
  fig,axes=plt.subplots(1,3,figsize=(14,4.5),layout='constrained')
  for ax,(field,label) in zip(axes,[('ocupacion_evaluable_pct','% de tiempo evaluable bajo alerta'),('horas_alerta_sin_inicio_vigente','Horas bajo alerta sin inicio en vigencia restante'),('precision_emisiones','Precisión de emisiones con aviso')]):
   for model,c in colors.items():
    z=agg[(agg.horizonte_h==h)&agg.epoca.eq('ALL')&agg.modelo.eq(model)&agg.politica.ne('regla_nativa')].copy()
    ax.plot(z[field],z.recall_inicios,'o-' if model!='siempre' else '*',color=c,label=model,markersize=6 if model!='siempre' else 13)
    if model=='logistica':
     for r in z.itertuples(): ax.annotate(r.politica[3:],(getattr(r,field),r.recall_inicios),xytext=(3,3),textcoords='offset points',fontsize=7)
   ax.set(xlabel=label,ylabel='Fracción de inicios anticipados',ylim=(-.03,1.05),title=f'{h} h, validación 2018–2023'); ax.legend(fontsize=8); ax.grid(alpha=.15)
  fig.savefig(OUT/'graficos'/f'deteccion_carga_{h}h.png',dpi=160); plt.close(fig)
  fig,axes=plt.subplots(1,3,figsize=(14,4),layout='constrained')
  for ax,b in zip(axes,['2018-2019','2020-2021','2022-2023']):
   for model,c in colors.items():
    z=metrics[(metrics.horizonte_h==h)&metrics.epoca.eq('ALL')&metrics.bloque.eq(b)&metrics.modelo.eq(model)&metrics.politica.ne('regla_nativa')]
    ax.plot(z.ocupacion_evaluable_pct,z.recall_inicios,'o-' if model!='siempre' else '*',color=c,label=model)
   ax.set(xlabel='% de tiempo evaluable bajo alerta',ylabel='Fracción de inicios anticipados',title=f'{b}, {h} h',ylim=(-.03,1.05)); ax.legend(fontsize=8); ax.grid(alpha=.15)
  fig.savefig(OUT/'graficos'/f'bloques_carga_{h}h.png',dpi=160); plt.close(fig)
  fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
  for model,policy in [('siempre','toda_emision'),('regla','p>=0.001'),('logistica','p>=0.1')]:
   z=episodes[(episodes.horizonte_h==h)&episodes.modelo.eq(model)&episodes.politica.eq(policy)].duracion_h.sort_values()
   axes[0].step(z,np.arange(1,len(z)+1)/len(z),where='post',label=f'{model}: {policy}',color=colors[model]); axes[1].scatter(z,np.arange(1,len(z)+1)/len(z),s=10,color=colors[model],label=model)
  axes[0].set(xscale='log',xlabel='Duración de episodio (h, escala log)',ylabel='Fracción acumulada',title=f'Duración de alertas, {h} h'); axes[0].legend(fontsize=8)
  axes[1].set(xscale='log',xlabel='Duración de episodio (h, escala log)',ylabel='Fracción acumulada',title='Cola de episodios prolongados'); axes[1].set_xlim(24,max(25,episodes.duracion_h.max()*1.05)); axes[1].legend(fontsize=8)
  fig.savefig(OUT/'graficos'/f'duraciones_{h}h.png',dpi=160); plt.close(fig)
 # A verified earlier group starting outside the 3-hour target, not chosen by predictive success.
 z=audit[(audit.modelo=='logistica')&(audit.horizonte_h==3)&audit.politica.eq('p>=0.1')&audit.estado.eq('acierto')&audit.activacion_antes_del_horizonte].sort_values('primera_emision').iloc[0]
 grid=pd.date_range(z.primera_emision,z.inicio+pd.Timedelta(hours=3),freq='h')
 fig,ax=plt.subplots(figsize=(11,3.5),layout='constrained')
 warns=pd.date_range(z.primera_emision,z.ultima_emision,freq='h')
 for i,t in enumerate(warns):
  ax.plot([t,t+pd.Timedelta(hours=3)],[i,i],color='#1769aa',lw=3); ax.scatter([t],[i],s=15,color='#1769aa')
 ax.axvline(z.inicio,color='#aa2360',label='Primera marca del tramo v0'); ax.axvspan(z.inicio-pd.Timedelta(hours=3),z.inicio,alpha=.12,color='#aa2360',label='Emisiones que pueden anticipar el inicio')
 ax.set(yticks=np.arange(len(warns)),yticklabels=[f'Aviso {i+1}' for i in range(len(warns))],xlabel='Reloj registrado; cada línea conserva su propio vencimiento',title='Una activación temprana requiere renovaciones para alcanzar el inicio'); ax.legend(fontsize=8); fig.autofmt_xdate()
 fig.savefig(OUT/'graficos/cadena_y_vigencias.png',dpi=160); plt.close(fig)

def md(df):
 def fmt(x):
  if pd.isna(x): return '—'
  if isinstance(x,(float,np.floating)): return f'{x:.5g}'
  return str(x)
 return '| '+' | '.join(df.columns)+' |\n| '+' | '.join(['---']*len(df.columns))+' |\n'+'\n'.join('| '+' | '.join(map(fmt,row))+' |' for row in df.itertuples(index=False,name=None))+'\n'

def report(metrics,agg,episodes,events,audit):
 allm=agg[agg.epoca.eq('ALL')]
 cols=['horizonte_h','modelo','politica','precision_emisiones','recall_emisiones','inicios_anticipados','inicios_omitidos','recall_inicios','ocupacion_evaluable_pct','horas_alerta','horas_alerta_sin_inicio_vigente','episodios','precision_episodios_descriptiva','duracion_max_h']
 examples=allm[(allm.modelo.eq('logistica')&allm.politica.eq('p>=0.1'))|allm.modelo.eq('siempre')|(allm.modelo.eq('regla')&allm.politica.eq('p>=0.001'))]
 sample=allm[allm.modelo.eq('logistica')&allm.politica.eq('p>=0.1')]
 agecols=['horizonte_h','modelo','politica','inicios_evaluables','inicios_anticipados','anticipacion_media_h','activaciones_dentro_h','alerta_ya_activa_antes_h','edad_alerta_media_h']
 durationcols=['horizonte_h','modelo','politica','episodios','episodios_sin_inicio','duracion_media_h','duracion_mediana_h','duracion_p95_h','duracion_max_h','episodios_ge24h','episodios_ge168h']
 exposure=pd.read_csv(OUT/'tablas/exposicion.csv'); findings=pd.read_csv(OUT/'tablas/hallazgos_v0.csv')
 block=metrics[metrics.epoca.eq('ALL')&metrics.modelo.eq('logistica')&metrics.politica.eq('p>=0.1')]
 seasons=agg[agg.epoca.ne('ALL')&agg.modelo.eq('logistica')&agg.politica.eq('p>=0.1')]
 preserved=pd.read_csv(OUT/'horarias_preservadas/metricas_horarias_agregadas.csv')
 e3=events[(events.horizonte_h==3)&events.modelo.eq('logistica')&events.politica.eq('p>=0.1')&events.estado.eq('anticipado')]
 text=f'''# Auditoría y evaluación de avisos v1

**La evidencia horaria de anticipación permanece; la precisión por grupos v0 no demuestra selectividad de activación ni baja carga temporal.** Esta auditoría reutiliza exclusivamente probabilidades y objetivos congelados. No reentrena ni recalibra, no cambia el catálogo y conserva v0 íntegro. La evaluación distingue pronóstico de inicio en una ventana, renovación de aviso y episodio persistente de alerta.

## Resultados señalados, comprobados

La regla con p≥0,001 supera el umbral en las **51.919/51.919 emisiones a 1 h y 51.905/51.905 a 3 h**. En v0 produce 86 grupos por horizonte, de los cuales 79 contienen una emisión posterior acertada: **79/86=91,86%**. Sus precisiones horarias son solo **79/51.919=0,1522%** y **233/51.905=0,4489%**. Agrupar miles de avisos y atribuir éxito si alguno coincide después cambia el significado de la métrica.

En logística p≥0,1 a 3 h se verifican **19/57 grupos acertados** cuya primera emisión ocurre más de tres horas antes del inicio (máximo 11 h). V0 usaba correctamente una emisión posterior válida para calcular anticipación, pero la palabra “grupo acertado” ocultaba que su activación inicial no anticipaba ese inicio en su propio horizonte. La vinculación no extendía la ventana de cada probabilidad: favorecía cadenas extensas al evaluar selectividad por una unidad de longitud variable sin acompañarla de ocupación.

{md(findings)}

La métrica anterior mide “proporción de cadenas consecutivas que, en alguna actualización posterior, alcanzan al menos un inicio todavía no vinculado”. Los 7 grupos falsos de la regla que avisa siempre reflejan principalmente interrupciones del archivo y fronteras; no significa que casi todas sus emisiones fueran acertadas. Se conservan los grupos originales y sus edades en `auditoria_grupos_v0.csv`. No se altera su historia para corregirlos.

## Política fijada antes del recálculo

[Protocolo previo](protocolo.md): cada aviso emitido en t vence en t+h; objetivo (t,t+h]. Renovación en t conserva su instante y vencimiento. Avisos solapados o adyacentes forman un episodio continuo; un lapso positivo tras vencimiento obliga a reactivación. Bajo umbral o sin pronóstico no se renueva y no se revoca retrospectivamente lo vigente. Una indisponibilidad no es negativo y queda registrada. Durante tramos activos no se emiten nuevas predicciones; el aviso previo sigue solo hasta su vencimiento.

La carga se mide en intervalos [t,t+1): [t,t+h) consume exactamente h horas. Un inicio exactamente en el vencimiento pertenece al objetivo, pero no agrega una hora de duración. Los bloques se reinician sin arrastrar alertas; la última marca tiene peso de duración cero, sin extender medición fuera del período. No se selecciona un umbral ganador.

**Límite causal del archivo:** v0 excluyó emisiones cuyo objetivo tenía desconocidas futuras. No es posible reconstruir con estas filas una disponibilidad operativa íntegramente causal. El motor v1 decide solo con el registro recibido en t, umbral y estado actual; sus decisiones son causales **condicionales al flujo archivado**, cuya máscara ya contiene selección retrospectiva. Los motivos de ausencia se describen después y no se usan para cerrar o renovar. Esto preserva probabilidades, pero mantiene sesgo de cobertura y disponibilidad inmediata optimista; no se presenta como simulación operacional validada.

La correspondencia se calcula después. Un inicio se cuenta una vez y puede pertenecer a un episodio que detecte varios inicios próximos. Su anticipación procede de la emisión válida más temprana; la edad de alerta persistente es otra magnitud y se conserva por separado. No se penalizan cadenas por un plazo arbitrario: se muestra su carga.

## Pronóstico horario preservado

AP, Brier, PR y calibración originales están copiados **byte a byte** en `horarias_preservadas/`; las predicciones originales no se reescriben. Se agrega precisión/recall para cada umbral sobre esas mismas emisiones. No se atribuye AP ni Brier a la alerta persistente.

{md(preserved[preserved.epoca.eq('ALL')])}

La logística mantiene mejor discriminación que las referencias en todos los bloques; Brier también mejora frente a frecuencia. La ventaja horaria no convierte una precisión descriptiva por episodios en precisión de una probabilidad. Los intervalos v0 de AP/Brier permanecen aplicables a esas métricas congeladas; los de falsa alarma y precisión por grupos no cuantifican la carga temporal nueva.

## Detección frente a carga

Ejemplos solicitados y referencia siempre activa cuando existe una emisión evaluable:

{md(examples[cols])}

`ocupacion_evaluable_pct` usa como denominador las horas con predicción archivada; la regla p≥0,001 y la referencia siempre ocupan **100%** de ese tiempo por construcción. Su alta precisión por episodios, si aparece, se acompaña de alertas que duran semanas o meses. No aporta selección de emisiones útiles frente a la referencia siempre; son idénticas a ese umbral.

En logística p≥0,1 se conserva la evidencia de **34/79 inicios anticipados a 1 h y 57/79 a 3 h**, con anticipaciones válidas de 1 y 2,105 h de media. A 1 h hay 34 emisiones acertadas de 128 avisos (26,56% de precisión), 0,2465% de ocupación evaluable y 94 de 128 horas de alerta sin inicio en vigencia restante. A 3 h hay 106 emisiones acertadas de 490 avisos (21,63%), 1,4276% de ocupación evaluable y 720 de 840 horas bajo alerta sin inicio en vigencia restante. Son 741 horas de alerta en emisiones evaluables y 99 sin pronóstico nuevo, incluidas horas de tramos ya activos. La precisión horaria es distinta de la precisión v0 de grupos. La carga temporal muestra cuántas horas se consume para obtener esa detección y cuántas no tienen un inicio dentro de la vigencia restante; no se descartan horas posteriores a un acierto para hacer más cortos los episodios.

{md(examples[agecols])}

Para la logística a 3 h, **{int(e3.activacion_dentro_h.sum())}** inicios detectados proceden de activaciones dentro de las tres horas previas y **{int(e3.ya_activa_antes_h.sum())}** de episodios que ya llevaban más tiempo activos. Las cifras pueden diferir de los 19 grupos v0 porque una alerta v1 también puede mantener continuidad con avisos no consecutivos pero cuyas vigencias se solapan. No se presentan como la misma selectividad.

### Todas las políticas de la rejilla

{md(allm[cols])}

![Detección y carga 1 h](graficos/deteccion_carga_1h.png)
![Detección y carga 3 h](graficos/deteccion_carga_3h.png)

### Duración y episodios

{md(examples[durationcols])}

Precisión por episodios es meramente descriptiva: fracción de episodios con al menos un inicio evaluable vinculado. Un episodio largo puede tener varios inicios y mucho tiempo sin ninguno; el numerador no equivale a número de emisiones acertadas. Cada episodio conserva comienzo, último aviso, vencimiento final, horas por clase y todos los inicios correspondientes. ≥24 h y ≥168 h son descriptores predefinidos, no criterios para descalificar avisos.

![Duraciones 1 h](graficos/duraciones_1h.png)
![Duraciones 3 h](graficos/duraciones_3h.png)
![Cadena y vigencias](graficos/cadena_y_vigencias.png)

## Tiempo sin un inicio y desconocidas

La clase principal evalúa, a posteriori, (t, último vencimiento vigente] en cada hora activa. Si no contiene inicio y todo ese intervalo es conocido, la hora se clasifica `sin_inicio`. Si contiene un inicio evaluable, `con_inicio`; si contiene desconocidas o un inicio sin oportunidad, `indeterminada` (prioridad conservadora). Estas tres cargas suman exactamente el tiempo total bajo alerta. Una hora pasada sin inicio no desaparece porque una renovación futura acabó acertando.

Como complemento, las tablas incluyen clases para (t,t+h] desde la hora actual; ese intervalo puede superar la vigencia restante y **no es un pronóstico nuevo**. No se usa para renovar, cerrar o asignar anticipación. El tiempo bajo alerta durante un tramo activo también se conserva; el denominador de pronósticos lo excluye, por eso se muestran duración total y ocupación en observación conocida y en todo el reloj.

{md(examples[['horizonte_h','modelo','politica','horas_alerta','horas_alerta_con_inicio_vigente','horas_alerta_sin_inicio_vigente','horas_alerta_indeterminada_vigente','horas_alerta_evaluables','horas_alerta_sin_pronostico','horas_alerta_desconocidas','ocupacion_conocida_pct','ocupacion_reloj_pct']])}

Exposición por bloque; ausencia de pronóstico no equivale a ausencia de observación:

{md(exposure[exposure.epoca.eq('ALL')])}

Las 240 marcas desconocidas de 2018–2023 se informan separadamente; no son negativas. En este archivo no hay alerta sobre horas desconocidas: la exclusión retrospectiva de objetivos con desconocidas impidió emitir antes de esos huecos. Ese resultado no demuestra que una alerta real nunca atraviese una pérdida de datos; el caso sintético de hueco confirma que el aviso previo solo conserva su vigencia, sin renovación. Las exclusiones del archivo cerca de huecos y fronteras limitan el flujo. `ausencias_retrospectivas_v0.csv` conserva motivos primarios y superpuestos sin incorporarlos al motor. La última marca de cada bloque pesa cero únicamente para duración; no se elimina del inventario de marcas.

## Bloques y estaciones

Logística p≥0,1, ejemplo fijo de auditoría:

{md(block[['horizonte_h','bloque','precision_emisiones','recall_emisiones','inicios_evaluables','inicios_anticipados','ocupacion_evaluable_pct','horas_alerta_sin_inicio_vigente','episodios','duracion_max_h']])}

{md(seasons[['horizonte_h','epoca','n_emisiones','inicios_evaluables','inicios_anticipados','ocupacion_evaluable_pct','horas_alerta_sin_inicio_vigente','episodios','duracion_max_h']])}

Horas se asignan a estación de cada celda, inicios a estación del inicio, episodios a estación de activación. La duración completa de un episodio asignado a una estación puede cruzar su frontera; no se suman esas duraciones como si fueran exposición de esa estación. DJF sin inicios no permite recall de eventos ni demuestra ausencia física del fenómeno.

![Bloques 1 h](graficos/bloques_carga_1h.png)
![Bloques 3 h](graficos/bloques_carga_3h.png)

## Controles y reproducción

El motor no recibe objetivos ni fechas de futuros inicios. Las correspondencias y clases de carga se calculan después. Los casos sintéticos prueban semanas de avisos, aislados acertados/falsos, solapamiento/adyacencia, inicio posterior al vencimiento, indisponibilidad, varios inicios y supresión en tramo activo. Se compara el prefijo del historial al alterar todo el futuro y al truncar el flujo. Los controles reconcilian unión de vigencias, duración por episodios, clases de carga y exposición; cada inicio tiene una sola atribución primaria, conservando todas las emisiones válidas.

`manifiesto_preservacion.csv` comprueba hashes antes/después de todos los archivos v0 y las dos fuentes autorizadas; no se ejecutan ni importan sus rutinas de entrenamiento. `verificar.py` reconstruye independientemente vigencias desde las emisiones emitidas y controla sumas, renovaciones, cierres, umbrales, correspondencias e integridad de fuentes. Los resultados son medidas descriptivas del archivo, no intervalos inferenciales de población. No se calculan intervalos ingenuos por horas independientes; pocas validaciones y episodios de larga dependencia dificultan estimación fiable de incertidumbre de carga.

```bash
python investigacion_ceazamet/evaluacion_avisos_v1/evaluar.py
python investigacion_ceazamet/evaluacion_avisos_v1/verificar.py
```

`historial_horario.csv.gz` registra cada hora, ausencia y estado; `emisiones_renovaciones.csv.gz` conserva cada aviso y vencimiento; `transiciones.csv.gz` conserva activación/renovación/cierre/reactivación. CSV comprimidos sin pérdida, coma, punto decimal, vacío para no disponible. Clases de carga: 0=sin alerta, 1=sin inicio, 2=con inicio, 3=indeterminada. Tablas de episodios, inicios únicos y todas las correspondencias, métricas por bloque/estación/agregado, exposición, auditoría v0, gráficos, protocolo, scripts y comprobaciones están en este directorio.

## Evidencia que permanece

Permanece la discriminación horaria retrospectiva de la logística y la existencia de emisiones válidas que anticipan inicios v0 dentro de 1 o 3 horas. La regla con umbral muy bajo reproduce una referencia que avisa siempre: su 91,86% por grupos no es evidencia de utilidad selectiva. La logística consigue detección con una carga menor que avisar siempre, pero mantiene omisiones, tiempo bajo alerta sin inicio y episodios cuya activación fue temprana y solo una renovación posterior resultó acertada. El compromiso completo está en las tablas, sin umbral ganador.

Para concluir utilidad operacional faltan costos de tiempo bajo alerta y omisiones, anticipación mínima útil, disponibilidad causal sin exclusión por información futura, latencia y evaluación prospectiva de una política congelada. La carga aporta una dimensión ausente en v0; no transforma predicción del cumplimiento del criterio en validación meteorológica del terral. No se accedió al período reservado, no se cambió catálogo ni probabilidad y no se desplegaron alertas.
'''
 (OUT/'informe.md').write_text(text)
