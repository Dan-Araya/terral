#!/usr/bin/env python3
import sys,os
sys.modules['numexpr']=None; os.environ.setdefault('MPLCONFIGDIR','/tmp/terral-matplotlib')
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
OUT=Path(__file__).resolve().parent

def read(name): return pd.read_csv(OUT/'tablas'/f'{name}.csv')
def table(df):
 def fmt(v):
  if pd.isna(v): return '—'
  if isinstance(v,(float,np.floating)): return f'{v:.6g}'
  return str(v)
 return '| '+' | '.join(df.columns)+' |\n| '+' | '.join('---' for _ in df.columns)+' |\n'+'\n'.join('| '+' | '.join(fmt(v) for v in row)+' |' for row in df.itertuples(index=False,name=None))+'\n'

def main():
 # Additional descriptors and explicit operational comparison against d=0.
 allmetrics=read('metricas'); eps=read('episodios')
 for i,row in allmetrics.iterrows():
  z=eps[(eps.retraso_h==row.retraso_h)&(eps.horizonte_h==row.horizonte_h)&(eps.modelo==row.modelo)&(eps.politica==row.politica)]
  if row.bloque!='AGREGADO': z=z[z.bloque==row.bloque]
  if row.epoca!='ALL': z=z[z.epoca==row.epoca]
  for col,cond in [('episodios_mayores_h',z.duracion_h>row.horizonte_h),('episodios_ge24h',z.duracion_h>=24),('episodios_ge168h',z.duracion_h>=168)]: allmetrics.loc[i,col]=int(cond.sum())
 allmetrics['avisos_sin_resultado']=allmetrics.avisos_desconocidos+allmetrics.avisos_fuera_alcance
 allmetrics['pronosticos_sin_resultado']=allmetrics.pronosticos_desconocidos+allmetrics.pronosticos_fuera_alcance
 allmetrics['horas_alerta_sin_pronostico']=allmetrics.horas_alerta-allmetrics.horas_alerta_disponibles
 allmetrics['precision_episodios_descriptiva']=allmetrics.episodios_con_inicio/allmetrics.episodios.replace(0,np.nan)
 allmetrics.to_csv(OUT/'tablas/metricas.csv',index=False,float_format='%.12g')
 allmetrics[allmetrics.bloque=='AGREGADO'].to_csv(OUT/'tablas/metricas_agregadas.csv',index=False,float_format='%.12g')
 keys=['bloque','horizonte_h','modelo','politica','epoca']
 baseline=allmetrics[allmetrics.retraso_h==0].drop(columns='retraso_h')
 delays=allmetrics[allmetrics.retraso_h.isin([1,2])].merge(baseline,on=keys,suffixes=('_retrasado','_d0'))
 for col in ['n_emisiones','emisiones_evaluables','inicios_anticipados','avisos_en_tramo_real_activo','precision_emisiones','recall_inicios','anticipacion_media_h','horas_alerta','horas_alerta_indeterminada_vigente','ocupacion_reloj_pct','episodios','duracion_max_h']:
  delays['delta_'+col]=delays[col+'_retrasado']-delays[col+'_d0']
 delays.to_csv(OUT/'tablas/comparacion_retrasos.csv',index=False,float_format='%.12g')
 m=read('metricas_agregadas'); m=m[m.epoca=='ALL']; comparison=read('comparacion_v1'); comparison=comparison[comparison.epoca=='ALL']; r=read('reconciliacion_v0'); checks=json.loads((OUT/'comprobaciones.json').read_text()); verify=json.loads((OUT/'verificacion.json').read_text())
 audit=m[((m.modelo=='logistica')&(m.politica=='p>=0.1'))|(m.modelo=='siempre')|((m.modelo=='regla')&(m.politica=='regla_nativa'))].sort_values(['horizonte_h','modelo','retraso_h'])
 availability=m[m.modelo=='siempre'][['retraso_h','horizonte_h','n_emisiones','emisiones_evaluables','pronosticos_desconocidos','pronosticos_fuera_alcance','inicios_catalogo','inicios_evaluables','inicios_sin_oportunidad']].sort_values(['horizonte_h','retraso_h'])
 pairs=read('comparacion_retrasos_pareada'); hourly=read('metricas_pronostico_agregadas')
 (OUT/'graficos').mkdir(exist_ok=True)
 fig,axes=plt.subplots(2,3,figsize=(14,8),sharey=True)
 colors={'logistica':'#2166ac','regla':'#b2182b','frecuencia':'#4d9221','siempre':'#555555'}
 for i,h in enumerate([1,3]):
  for j,d in enumerate([0,1,2]):
   ax=axes[i,j]; z=m[(m.horizonte_h==h)&(m.retraso_h==d)]
   for model in ['logistica','regla','frecuencia']:
    q=z[(z.modelo==model)&z.politica.str.startswith('p>=')].sort_values('ocupacion_reloj_pct')
    ax.plot(q.ocupacion_reloj_pct,100*q.recall_inicios,'o-',color=colors[model],label=model,markersize=4)
   q=z[z.modelo=='siempre']; ax.scatter(q.ocupacion_reloj_pct,100*q.recall_inicios,color=colors['siempre'],marker='*',s=90,label='siempre')
   ax.set_title(f'h={h} h, retraso hipotético d={d} h'); ax.set_xlim(-2,102); ax.set_ylim(-2,103); ax.grid(alpha=.2)
   if i==1: ax.set_xlabel('Tiempo del reloj bajo alerta (%)')
   if j==0: ax.set_ylabel('Inicios con oportunidad detectados (%)')
 axes[0,0].legend(fontsize=8); fig.suptitle('Rejilla congelada: detección y carga; sin selección de umbral'); fig.tight_layout(); fig.savefig(OUT/'graficos/deteccion_carga.png',dpi=160); plt.close(fig)
 text=['# Simulación temporal causal de Vicuña–INIA\n',
 '**La línea base queda documentada y reproducible para comparar el aporte incremental de otras estaciones dentro de los mismos bloques de desarrollo, con objetivos y políticas congelados. La reconstrucción corrige la disponibilidad retrospectiva de v0/v1. No demuestra utilidad operacional ni valida el inicio físico de terral.**\n',
 '## Alcance y decisión causal\n',
 'Se usaron exclusivamente los once archivos anuales 2013–2023 de INIA, el catálogo v0 y los artefactos v0/v1. Se recorrieron todas las marcas de 2018–2019, 2020–2021 y 2022–2023. No hubo acceso a observaciones, estadísticas o gráficos del período reservado, otras estaciones, red, ajuste, recalibración ni despliegue. El primer inventario de rutas fue demasiado amplio y mostró nombres de archivos de otros años; no abrió su contenido. Después se utilizó una lista cerrada. Los resultados anteriores se preservaron íntegros.\n',
 'En t solo se conoce hasta a=t−d. Se exige la ventana completa [a−6,a] y criterio v0 no_cumple en a; la detección usa cuatro valores actuales conocidos, sin consultar catálogo ni duración futura. Dirección 360 es equivalente a 0 como predictor circular, pero no cumple el sector de la etiqueta. No se arrastra la última marca válida a través de un hueco: si falta a no se emite. Las probabilidades y el calendario del modelo se anclan en a; el objetivo sigue siendo (t,t+h], desde la hora real de emisión. El motor recibe disponibilidad, decisión de umbral, estado conocido y h, nunca objetivos ni fechas de eventos.\n',
 'Los tres bloques arrancan apagados y sin ventana del bloque anterior. Las primeras 6+d marcas no emiten; la séptima marca completa permite emitir cuando d=0. La recuperación tras un hueco también necesita siete marcas consecutivas válidas. Se conservan las últimas h emisiones posibles, cuyos objetivos son fuera_de_alcance. Cada aviso conserva vencimiento t+h, incluso si excede el bloque, pero la duración se recorta a [primera marca,última marca): última celda peso cero. No se transfieren alertas.\n',
 '## Reconciliación con v0 y disponibilidad restaurada\n',
 f'Se reconciliaron las **{checks["reconciliacion_filas"]:,} filas** archivadas de los tres modelos, probabilidades, bit de regla, objetivos y todos los IDs de inicio. Error absoluto máximo **{checks["error_max"]:.3g}**, dentro de **{checks["tolerancia"]:.1g}**. Las referencias con diez cifras significativas se aplican tal como están archivadas; no se estiman nuevamente.\n',
 table(r),
 'Los conteos anteriores son por modelo, y las emisiones adicionales no se deben sumar entre modelos como si fueran horas distintas. A d=0, las probabilidades de todas las filas existentes coinciden y las ausentes se recuperan sin consultar su futuro. Para cada horizonte se informa una sola población de horas, común a los tres modelos y a siempre:\n',table(availability),
 'Positivo/negativo requiere que todas las observaciones necesarias de (t,t+h] sean conocidas. Desconocido conserva objetivo numérico vacío, incluso si hay un inicio conocido junto a una marca faltante. Fuera de alcance tiene prioridad cuando el objetivo supera el bloque. Ni uno ni otro se imputan como negativo, ni desaparecen del historial. Los inicios del catálogo se conservan y se distinguen de los que tienen oportunidad evaluable.\n',
 '## Cambio frente a v1\n',
 'Comparación d=0 con v1 sobre cada flujo completo. La ocupación del reloj conserva el mismo denominador; la ocupación evaluable usa una población de emisión distinta y su diferencia incluye el cambio de cobertura. Las diferencias son descriptivas, no inferencia causal meteorológica. p≥0,1 es el ejemplo de auditoría ya usado por v0/v1, no una selección por estos resultados.\n',
 table(comparison[((comparison.modelo=='logistica')&(comparison.politica=='p>=0.1'))|(comparison.modelo=='siempre')][['horizonte_h','modelo','politica','delta_n_emisiones','delta_emisiones_con_aviso','delta_inicios_anticipados','delta_precision_emisiones','delta_horas_alerta','delta_horas_alerta_desconocidas','delta_horas_alerta_indeterminada_vigente','delta_episodios']]),
 'Para logística p≥0,1 y d=0 no cambian avisos, detección ni duración respecto de v1. En la referencia siempre, a 1 h aparecen 7 avisos adicionales y 4 horas adicionales bajo alerta, con 4 horas indeterminadas; a 3 h aparecen 21 avisos adicionales, 12 horas adicionales bajo alerta y **7 horas sobre observaciones actuales desconocidas**, con **24 horas de resultado vigente indeterminado**. Este último total incluye tanto ventanas con pérdidas como fronteras, que antes estaban suprimidas.\n',
 'La tabla completa `comparacion_v1.csv` conserva todas las políticas, épocas, valores originales y diferencias. Que un umbral no cambie detección no vuelve causal la antigua máscara: las nuevas emisiones sin resultado y la carga alrededor de huecos siguen siendo parte del flujo operativo.\n',
 '## Pruebas de estrés de retraso\n',
 '**d=0,1,2 h son hipótesis de disponibilidad, no estimaciones de latencia CEAZA.** El modelo fue entrenado para disponibilidad inmediata. Las probabilidades retrasadas no quedan automáticamente calibradas para el objetivo real (t,t+h]. Los conteos de avisos en tramo real activo son diagnósticos posteriores: el motor no tenía acceso a ese estado real más reciente. Solo se vinculan avisos estrictamente anteriores al inicio, y con intervalo evaluable.\n',
 table(audit[['retraso_h','horizonte_h','modelo','politica','emisiones_con_aviso','avisos_evaluables','avisos_desconocidos','avisos_fuera_alcance','avisos_en_tramo_real_activo','inicios_anticipados','inicios_evaluables','precision_emisiones','anticipacion_media_h','ocupacion_reloj_pct']]),
 'En el ejemplo congelado logística p≥0,1, la detección pasa de **34 a 9 y 6 inicios a 1 h**, y de **57 a 42 y 31 a 3 h**, para d=0,1,2. La precisión por emisión pasa de 26,56% a 7,03% y 4,69% a 1 h; de 21,63% a 16,33% y 13,47% a 3 h. Los avisos emitidos durante un tramo real activo pasan de 0 a 34 y 42 a 1 h, y de 0 a 50 y 77 a 3 h. Son consecuencias de esta prueba hipotética con predictores retrasados. La anticipación media condicional de los pocos inicios detectados puede aumentar a 3 h mientras baja la detección: no significa mejora general, porque cambia el conjunto de aciertos.\n',
 'La precisión divide aciertos por avisos con resultado positivo/negativo, nunca por desconocidos convertidos en falsos. Se entrega también `precision_limite_inferior` (aciertos/total de avisos) para exponer el denominador íntegro; es un límite descriptivo, no una etiqueta negativa para el resto. `avisos_en_tramo_real_activo` no es automáticamente igual al número de avisos sin anticipación: otro inicio posterior puede caer dentro del mismo horizonte. Cada correspondencia conserva su inicio e instante real.\n',
 '![Detección y carga de todos los umbrales](graficos/deteccion_carga.png)\n',
 'Toda la rejilla logística, sin ganador:\n',table(m[m.modelo=='logistica'][['retraso_h','horizonte_h','politica','inicios_anticipados','precision_emisiones','emisiones_con_aviso','avisos_desconocidos','avisos_fuera_alcance','ocupacion_reloj_pct']].sort_values(['horizonte_h','retraso_h','politica'])),
 '## Tiempo bajo alerta y duración\n',
 'Se mantienen avisos previos durante pérdidas de observación hasta su vencimiento, sin renovaciones. La clase vigente examina a posteriori (t,último vencimiento vigente]: con_inicio, sin_inicio o indeterminada. Las tres suman el total. Se separan desconocidas actuales, pérdidas futuras necesarias y vencimientos externos; estas causas pueden solaparse y no deben sumarse entre sí. No se revoca una alerta porque aparezca un evento ni se atribuyen semanas de edad a anticipación útil. Duraciones medias, medianas, p95 y máximas son duración observada con censura de borde, asignadas por época de activación; horas se asignan a cada celda e inicios a su fecha.\n',
 table(audit[['retraso_h','horizonte_h','modelo','politica','horas_alerta','horas_alerta_con_inicio_vigente','horas_alerta_sin_inicio_vigente','horas_alerta_indeterminada_vigente','horas_alerta_desconocidas','horas_alerta_perdida_futura','horas_alerta_fuera_bloque','episodios','episodios_censurados','duracion_media_h','duracion_mediana_h','duracion_p95_h','duracion_max_h']]),
 '## Discriminación y evaluación pareada\n',
 'AP y Brier solo describen probabilidades con objetivo evaluable. Las métricas brutas operacionales entre retrasos tienen diferentes poblaciones; el soporte común siguiente compara las mismas horas reales y etiquetas, exigiendo disponibilidad en los tres escenarios. Eso evita confundir cambios de soporte con cambios de predictor, aunque sigue siendo una selección de cobertura y no representa todos los avisos operativos.\n',table(hourly),table(pairs),
 'La calibración descriptiva por bloque, horizonte, modelo y retraso está en `calibracion.csv`, con la rejilla original; no se usa para corregir probabilidades. AP sin positivos es indefinida. Los resultados estacionales y por bloque están en las tablas completas, incluidos DJF sin inicios, y no avalan ausencia física del fenómeno.\n',
 '## Controles y reproducción\n',
 f'Pasaron **{checks["controles_causales"]} controles causales** y la verificación independiente de **{verify["flujos_verificados"]} flujos**, disponibilidad de cada marca, etiquetas de cada emisión, todas las decisiones de umbral, renovaciones/episodios, unión de vigencias y clases de carga. Los hashes antes/después de **{checks["fuentes_preservadas"]} fuentes y artefactos anteriores** coinciden. La etiqueta de criterio reconcilia 156 tramos y 867 horas en 2013–2023; los límites temporales se comprueban antes de seleccionar validación.\n',
 'Los contrafactuales alteran y eliminan todo el futuro después de cortes fijos, huecos, recuperación y comienzos reales; verifican igualdad del prefijo de predictores, disponibilidad, probabilidades y estados del motor en cada retraso y ambos horizontes. Se prueba también truncación real de la serie, recuperación tras siete marcas, vencimiento exacto, continuidad adyacente y rechazo de anticipación para emisiones en o después del inicio. La interfaz sin etiquetas asegura que cambiar objetivos no puede influir en el motor.\n',
 '```bash\npython investigacion_ceazamet/simulacion_causal_inia_v0/simular.py\npython investigacion_ceazamet/simulacion_causal_inia_v0/verificar.py\npython investigacion_ceazamet/simulacion_causal_inia_v0/informar.py\npython investigacion_ceazamet/simulacion_causal_inia_v0/cerrar.py\n```\n',
 'Scripts autocontenidos, sin importación de programas de ajuste. `funciones_congeladas.py` copia literalmente solo `features` de v0 y `engine`, `classification`, `event_links` de v1. `registro_previo.json` registra protocolo, versiones y lista cerrada; `requirements.txt` fija dependencias. CSV con coma, punto decimal y vacío para no disponible; gzip sin pérdida. `disponibilidad.csv.gz` incluye cada marca y motivo; `predicciones.csv.gz` todas las emisiones de los tres modelos; `objetivos_posteriores.csv.gz` una fila por hora emitida/horizonte; historiales, emisiones y transiciones incluyen siempre y todas las políticas. `episodio` es local a la clave bloque/retraso/horizonte/modelo/política.\n',
 '## Incertidumbre y comparación de otras estaciones\n',
 '**Sí: documentación suficiente para una comparación retrospectiva de desarrollo, bajo este contrato explícito de disponibilidad y evaluación.** La contribución de otra estación deberá compararse manteniendo bloques, catálogo, objetivos desde la hora real, modelos/políticas de referencia, tratamiento de huecos y denominadores, informando tanto soporte común como cobertura total. Este trabajo no consultó ninguna otra estación. Las decisiones de usar arranque sin historia del bloque anterior y de no arrastrar marcas válidas durante huecos están fijadas y deberán conservarse o distinguirse como otro protocolo.\n',
 '**La evidencia todavía no basta para despliegue ni comparación prospectiva definitiva.** Persisten latencia y semántica real del promedio horario, zona/reloj, diferencias de altura instrumental, calidad y cambios de instrumentación, catálogo de criterio distinto del fenómeno físico, pocos inicios y solo tres validaciones reutilizadas en entrenamiento expansivo. Los resultados son exactos sobre estos artefactos y supuestos, no estimaciones con garantía de generalización. No se reutilizan los intervalos bootstrap v0 sobre las nuevas poblaciones; no se producen intervalos por horas independientes. La incertidumbre de carga y episodios largos requiere una evaluación temporal y prospectiva adicional, junto a costos y anticipación mínima útil acordados. No se elige un ganador.\n']
 (OUT/'informe.md').write_text('\n'.join(text))
 outputs=[{'archivo':str(p.relative_to(OUT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in sorted(OUT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.log' and p.name!='manifiesto_resultados.csv']
 pd.DataFrame(outputs).to_csv(OUT/'manifiesto_resultados.csv',index=False)
 print('Informe y gráfico generados')
if __name__=='__main__': main()
