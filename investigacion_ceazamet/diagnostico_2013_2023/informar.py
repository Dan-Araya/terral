#!/usr/bin/env python3
"""Construye el informe desde las tablas calculadas; no abre observaciones nuevas."""
import sys
sys.modules['numexpr']=None
import json
from pathlib import Path
import pandas as pd
O=Path(__file__).resolve().parent; T=O/'tablas'
def read(n): return pd.read_csv(T/f'{n}.csv')
def table(df):
 def fmt(v):
  if pd.isna(v): return '—'
  if isinstance(v,float): return f'{v:.3f}'
  return str(v)
 return '\n'.join(['| '+' | '.join(df.columns)+' |','| '+' | '.join(['---']*len(df.columns))+' |']+['| '+' | '.join(fmt(v) for v in r)+' |' for r in df.itertuples(index=False,name=None)])
c=read('cobertura'); h=read('huecos'); d=read('distribuciones'); changes=read('cambios_exactos'); s=read('sensibilidad_resumen'); st=read('sensibilidad_temporal'); days=read('dias_historicos'); ev=read('eventos_por_dias'); seg=read('tramos_anual'); audit=json.loads((O/'comprobaciones.json').read_text())
y=c[c.escala.eq('Y')&c.variable.eq('conjunta_4')][['periodo','horas_esperadas','validas','ausentes','cobertura_pct']].merge(read('conteos_candidatos').query("aplicacion=='anual' and escala=='ano'")[['grupo','cumple']],left_on='periodo',right_on='grupo').drop(columns='grupo'); y.columns=['Año','Horas esperadas','Válidas conjuntas','Ausentes','Cobertura %','Candidatas']
worst=c[c.escala.eq('M')&c.variable.eq('conjunta_4')].sort_values('cobertura_pct').head(4)[['periodo','validas','horas_esperadas','cobertura_pct']]
gaps=h[h.variable.eq('conjunta_4')&h.tipo.eq('no_valido')][['inicio','fin','horas']]
monthly=d[d.escala.eq('mes')&d.variable.isin(['temperatura','humedad','viento_2m'])].pivot(index='grupo',columns='variable',values='q50').astype(float); monthly.index=monthly.index.astype(int); monthly=monthly.sort_index().reset_index(); monthly.columns=['Mes','HR mediana (%)','T mediana (°C)','V mediana (m/s)']
cd=changes[changes.escala.eq('total')][['variable','lag_h','n','q05','q50','q95','pares_con_intermedias_invalidas']]
ss=s[['configuracion','horas_criterio','horas_retenidas','tramos','duracion_mediana_h','duracion_p95_h','duracion_max_h','delta_horas_vs_original']].copy()
rows=[]
for name,g in st[st.escala.eq('mes')].groupby('configuracion',sort=False):
 total=g.horas_retenidas.sum(); win=g[g.grupo.astype(int).between(4,8)].horas_retenidas.sum(); rows.append({'Configuración':name,'Abril–agosto':int(win),'Resto del año':int(total-win),'% abril–agosto':100*win/total})
time_summary=pd.DataFrame(rows)
grp=ev.groupby('aplicacion').agg(eventos=('evento','count'),dias=('dias','sum'),horas_candidatas=('horas_candidatas','sum'),max_dias=('dias','max')).reset_index()
qq=read('distribuciones_tramos').query("configuracion=='original'")[['variable','n','q05','q25','q50','q75','q95','q100']]
text=f'''# Diagnóstico cuantitativo de Vicuña–INIA, 2013–2023

El período contiene {len(days):,} días y {audit['horas_esperadas']:,} marcas horarias esperadas. Hay 95.963 horas con las cuatro variables principales válidas (99,538%), 445 horas desconocidas y 867 horas que cumplen simultáneamente el criterio solicitado. Esas candidatas forman 156 tramos horarios estrictos y 148 días candidatos. Son resultados del criterio, sin confirmación meteorológica automática.

## Alcance, fuentes y reserva temporal

Se leyeron `modelo_predictivo_terral.md` y `hoja_de_ruta_terral.md`. La ingesta abre exclusivamente la lista explícita de once CSV `observaciones_2013.csv` a `observaciones_2023.csv` en `historico_inia/derivados/`. Cada fila, incluidas las variables de 5 m que no entran al análisis, debe pertenecer a 01/01/2013 00:00–31/12/2023 23:00. Una fecha externa aborta la ejecución antes de producir estadísticas; no se descarta silenciosamente. No se abrieron originales XLS, informes históricos globales, gráficos previos ni datos de otros años o estaciones. Algunos nombres de bloques fuente contienen fechas externas: se conservan como metadatos de procedencia, sin abrir esos bloques.

La interpretación metodológica se contrastó con la sección 2c de [Montes et al. (2016)](https://journals.ametsoc.org/view/journals/apme/55/5/jamc-d-15-0275.1.xml). Su definición agrupa horas en días y días consecutivos en eventos. El filtro agrícola elimina días según la hora de inicio entre 08:00 y 00:00 LT (UTC−4), dentro de abril–agosto. El límite de medianoche y el significado del inicio al cruzar días requieren aclaración. Se conserva el intervalo angular 0°–180° pedido por el usuario.

`manifiesto_fuentes.csv` registra SHA-256 de los CSV, filas y extremos temporales. `trazabilidad_observaciones.csv` conserva fecha, variable, fila del CSV, sensor, unidad, altura, valores originales min/prom/max, porcentaje, banderas previas, archivo original, SHA-256 original, hoja y fila Excel. Cualquier resultado horario se enlaza por fecha y variable. No se alteran fuentes ni se imputan mediciones. `comprobaciones.json` registra límites, versiones y hashes del protocolo y script.

Las fechas permanecen sin zona. Todos los meses, horas, días y separaciones son del reloj registrado. Una separación exacta en ese reloj no acredita tiempo físico transcurrido ante posibles cambios de horario aún no documentados. No se ha aplicado UTC ni America/Santiago. La fecha puede representar el comienzo o final de la hora promediada: también está pendiente.

## Disponibilidad, denominadores y calidad

Una observación está **presente** si `prom` es finito y `porcentaje_datos > 0`. Está **válida para cálculo** si además `prom_utilizable_revision = 1`, HR ∈ [0,100], velocidad ≥ 0 y dirección ∈ [0,360]. Los promedios válidos de temperatura se conservan; no se aplica un detector nuevo ni se eliminan extremos por cuantiles. Los controles amplios T ∈ [−30,50] °C, viento ≤60 m/s y presión ∈ [500,1100] hPa solo generan banderas adicionales. La revisión heredada no sustituye una auditoría instrumental.

El denominador de cobertura es la grilla completa de cada año/mes, con 8.784 horas en 2016 y 2020 y 8.760 en los demás años. `ausentes + presentes_no_validas + validas = horas_esperadas`. Hay una fila por variable/hora en los CSV, pero una fila con porcentaje cero y promedio vacío representa ausencia observacional. En este conjunto, los faltantes de las cinco variables coinciden. Por ello, las cuatro coberturas individuales son iguales a la conjunta, sin que esto garantice independencia o calidad instrumental.

{table(y)}

La presión tiene 95.959 horas válidas: las mismas 445 ausencias más cuatro valores presentes rechazados. Se usa como complemento y esas cuatro horas siguen siendo evaluables para el criterio principal. No hay porcentajes parciales entre 0 y 100 en las variables analizadas, ni duplicados de fecha/variable, ni marcas fuera de la grilla horaria.

Los meses con menor cobertura conjunta son:

{table(worst)}

Existen **13 huecos conjuntos**, por 445 h, con duración mínima de 1 h y máxima de 217 h. Cada variable principal tiene los mismos 13 huecos. La presión añade un hueco de invalidez de 4 h (14 en total, 449 h no válidas). La duración cuenta posiciones horarias ausentes: inicio y fin están incluidos; la diferencia fin−inicio es una hora menor que esa duración. `huecos.csv` separa ausencia de invalidez y `distribucion_huecos.csv` ofrece cuantiles. Los 13 huecos conjuntos son:

{table(gaps)}

Los cuatro valores de presión del **20/07/2015, 11–14 h registradas**, son 11,554, 11,754, 12,015 y 12,368 hPa declarados. Ya tenían `prom_utilizable_revision=0`; se preservan sin corregir y se excluyen de las distribuciones válidas de presión. Su escala y parecido a valores térmicos requieren revisar exportación, sensor y columna original, sin afirmar un intercambio de columnas. No aparecieron infracciones adicionales de los rangos amplios ni del orden min≤prom≤max. La dirección se excluye de esa comparación lineal porque es circular.

Hay **361 ceros válidos de velocidad** y **319 de dirección**. Un cero de velocidad se cuenta como calma, un cero de dirección como norte; ninguno se convierte en faltante. Dos secuencias simultáneas de velocidad y dirección cero duran 13 y 12 h en febrero/marzo de 2018. Ese año reúne 170 ceros de velocidad y 155 de dirección, frente a 2–64 y 2–55 respectivamente en los otros años. Es una posible discontinuidad de registro, sensor o comportamiento de calmas que requiere metadatos; no demuestra un fallo. Las 18 repeticiones exactas de presión de 12–14 h pueden reflejar cuantización. No hay repeticiones de temperatura o HR de al menos 12 h.

Los controles prefijados de saltos de 1 h señalan **109 cambios de temperatura ≥8 °C en valor absoluto, 18 de HR ≥40 puntos porcentuales y uno de viento ≥5 m/s**. Se mantienen válidos; un cambio abrupto puede ser meteorológico. Los umbrales son solo banderas de revisión. `saltos_revision.csv`, `repeticiones_exactas.csv`, `calidad_anual.csv` y `continuidad_mensual.csv` permiten auditar fechas, ceros, precisión, sensores y cambios de medianas entre meses contiguos. Esos cambios mezclan estacionalidad, composición de la muestra y posibles cambios instrumentales, sin atribución causal. No se realizó una homogeneización ni una prueba confirmatoria de rupturas.

Requieren cautela especialmente **enero de 2015, marzo de 2016, febrero de 2019 y mayo de 2022** por huecos; **julio de 2015** por presión; y **febrero/marzo de 2018** por las secuencias de ceros. Las fronteras de todos los huecos quedan auditables. Ningún tramo candidato original toca un hueco desconocido; su duración sigue limitada por el período observado. Una cobertura anual elevada no certifica la completitud de cada mes ni la representatividad de su distribución.

Los encabezados CSV declaran 2 m para temperatura y humedad; el documento meteorológico describe 1,5 m. El viento empleado es exclusivamente `viento_2m` y `direccion_2m`. No se sustituyó por viento a 5 m. La continuidad de altura, calibración, sensor y ubicación precisa sigue pendiente aun si el código del sensor no cambia. En presión cambia claramente la frecuencia de promedios enteros: 59,278% en 2020, 36,119% en 2021, 0,080% en 2022 y 0,057% en 2023. Esto documenta una posible discontinuidad de precisión o procesamiento, aun con código VCNPA estable, y obliga a cautela al interpretar variabilidad y cambios de presión entre esas etapas. No demuestra por sí solo un cambio de sensor ni un salto físico de nivel.

![Cobertura mensual](graficos/cobertura.png)

## Distribuciones y cambios habituales

Se calculan n, mínimo, p1, p5, p25, mediana, p75, p95, p99 y máximo de promedios horarios válidos por mes calendario (los once años agrupados), hora registrada, mes×hora, año y año×mes, además del total. Los cuantiles usan interpolación lineal de pandas y no se ponderan por número de muestras subhorarias desconocido. Cada variable usa su propia validez, sin exigir presión o cobertura conjunta. Los n desiguales deben acompañar toda comparación. Las estadísticas incluyen candidatos y horas ordinarias del período; no son una climatología externa ni umbrales nuevos.

Medianas mensuales agrupadas:

{table(monthly)}

La temperatura mediana pasa de 19,975 °C en enero a 9,663 °C en julio. Sus p5–p95 son 11,645–30,024 °C en enero y 2,127–24,383 °C en julio. El viento mediano es 0,886 m/s en enero y 0,628 m/s en julio. Las colas secas de HR son amplias: p5 es 28,680% en enero y 11,264% en julio. Estos valores describen las observaciones y no validan terrales.

`direccion_circular.csv` usa media de seno/coseno, media circular y longitud resultante R ∈ [0,1]. Los cuantiles se refieren al **desvío angular firmado en [−180,180)** respecto de esa media, con columnas `desvio_qXX`, nunca a ángulos promediados linealmente. El punto de corte del desvío afecta sus extremos; se incluyen frecuencias de ocho sectores de 45° y conteos de dirección en calma en `sectores_direccion.csv`. Para esos sectores únicamente, 360° se identifica con 0° matemáticamente. El criterio pedido conserva el valor 360 y lo deja fuera de [0,180].

La media circular mensual es 276,091° (R=0,620) en enero y 358,403° (R=0,084) en julio. El R muy bajo de julio muestra que una sola dirección media resume mal su distribución y puede ocultar sectores opuestos. No se da interpretación predominante a ese ángulo. Las direcciones en calma se mantienen en la descripción y quedan identificadas; no acreditan un flujo. Los CSV aportan promedios horarios de dirección ya calculados: **no se conoce si el exportador los obtuvo circularmente**, y no se puede reconstruir el promedio circular subhorario con estos archivos.

`ciclo_horario.png` muestra medianas por hora registrada para enero, abril, julio y octubre, elegidos como meses de resumen fijos, sin selección de episodios. Las tablas incluyen los doce meses y 24 horas con sus cuantiles y n. El ciclo se interpreta exclusivamente en el reloj registrado.

Las diferencias son valor actual menos valor de 1 o 3 horas antes, con ambos extremos válidos y separación exactamente horaria en la grilla. Nunca se resta la última fila disponible ignorando un hueco. Para 3 h se permiten intermedias ausentes, siempre informadas: hay nueve pares de ese tipo por variable; exigir las intermedias reduciría n de 95.932 a 95.923. No se incorporan observaciones previas al comienzo del período.

{table(cd)}

Unidades de cambios: °C, puntos porcentuales de HR y m/s. `cambios_exactos.csv` contiene el total y las particiones por mes, hora de llegada y mes×hora. Los extremos de diferencias no demuestran errores ni son umbrales de un detector.

![Ciclo por hora registrada](graficos/ciclo_horario.png)

## Reproducción del criterio y agrupaciones

Una hora **cumple** con las cuatro variables válidas y dirección inclusiva [0,180], viento estrictamente >2 m/s, T estrictamente >11 °C y HR estrictamente <30%. Una hora **no cumple** exige las cuatro variables válidas y falla al menos una desigualdad. Toda hora que carece de alguna variable válida es **no evaluable**, incluso si otra observación ya falla un umbral. La presión no entra en esa decisión. No se denomina terral confirmado a ningún resultado.

La aplicación anual produce **867 cumple, 95.096 no cumple y 445 no evaluable**. Las candidatas son 0,903% de las 95.963 horas evaluables y 0,899% de todas las horas esperadas. `estados_horarios.csv` conserva los tres estados; los valores `no_cumple` y `no_evaluable` corresponden a esas expresiones. `conteos_candidatos.csv` informa conteos y denominadores por año, año×mes, mes, hora y mes×hora. Las tasas usan únicamente horas evaluables del ámbito, y el número de desconocidas se presenta aparte.

Las candidatas por mes son 0, 0, 5, 0, 96, 282, 238, 166, 48, 28, 4 y 0 de enero a diciembre. **782 h (90,196%)** caen en abril–agosto, con 24 h desconocidas entre las 40.392 esperadas en ese ámbito. La concentración por hora registrada alcanza 115 candidatas a las 10, seguida de 100 a las 9 y 93 a las 11. No se traducen esas horas a mañana civil ni se usan para inferir la zona. No observar candidatas en un mes no acredita ausencia física del fenómeno.

Un **tramo horario** es una secuencia de candidatos separados exactamente una hora. Cualquier negativa o desconocida lo rompe; no se rellenan huecos. La duración cuenta horas candidatas, y la amplitud inclusive inicio–fin coincide con ella en la referencia. Se informa viento medio de los promedios horarios y **máximo del promedio horario del viento** dentro del tramo, sin usar `max` subhorario como ráfaga. Los cuantiles de viento por tramo pesan cada tramo una vez, no cada hora.

{table(qq)}

Los 156 tramos suman 867 h; duración media 5,558 h, mediana 4 h, p95 14 h y máximo 29 h. El viento medio del tramo mediano es 4,206 m/s y el máximo horario del tramo mediano 5,231 m/s. El mayor promedio horario asociado es 8,530 m/s. `tramos_anual.csv` y `tramos_abril_agosto.csv` conservan inicio, fin, duración, medias, máximos horarios y censura en bordes desconocidos o del período. Las duraciones observadas no definen peligrosidad.

Un **día candidato** tiene al menos una hora candidata en el calendario registrado. Se conservan número total de horas candidatas, cantidad de tramos dentro del día, máxima secuencia consecutiva dentro del día, primera hora, desconocidas, incertidumbre del inicio y continuidad desde la víspera. La suma de horas de un día con interrupciones no se interpreta como una duración continua. Si no hay candidatas pero hay desconocidas, el día se marca desconocido; no se convierte en día negativo. Un **evento por días** agrupa días candidatos consecutivos, aun cuando sus tramos horarios estén separados por muchas negativas dentro de los días. Un día enteramente sin candidatos o un día desconocido rompe ese agrupamiento; nunca se une a través de un día desconocido. Un día candidato puede contener horas desconocidas: sus cantidades e incertidumbres se mantienen explícitas. No se confunde esta agrupación histórica con persistencia horaria continua.

{table(grp)}

Los 115 eventos anuales por días se distribuyen en 91 de un día, 17 de dos, cinco de tres y dos de cuatro. `dias_historicos.csv`, `eventos_por_dias.csv` y `distribuciones_dias_eventos.csv` incluyen catálogos, duraciones de días y horas, y distribuciones de tramos recortados a cada ámbito de días. En cuatro días anuales el primer candidato a medianoche continúa desde la víspera. No hay inicios inciertos por falta de datos según la regla conservadora prefijada, lo que no resuelve el significado agrícola del inicio.

La reproducción estacional sin filtro horario da 135 tramos, 128 días/97 eventos por días y 782 h. La **aproximación agrícola 00–07 registrada** retiene el día completo si su primera candidata está en esas horas y cae en abril–agosto: 72 días, 59 eventos y 599 h. No se eliminan todas las candidatas de 08–23 de un día admitido. La alternativa de frontera **01–07** da 61 días, 55 eventos y 462 h. En los días admitidos no hay desconocidas. Las 1.728 y 1.464 horas de ámbito de estas dos aproximaciones son las horas de los días seleccionados a posteriori, **no denominadores de prevalencia de toda la temporada**.

Estos dos cálculos son escenarios sobre el reloj registrado, sin afirmar reproducción exacta en LT UTC−4. La diferencia de 137 h y 11 días muestra la relevancia de medianoche/continuidad. No se desplazó la serie cuatro horas por conjetura, ni se eligió una convención para asemejar resultados publicados. La limitación de zona horaria, frontera 00:00 e inicio al cruzar días impide cerrar esa reproducción exacta. Tampoco se compara el total con el de once temporadas originales, que comprenden años fuera de este encargo.

![Conteos candidatos](graficos/candidatos.png)

![Duración y máximo horario](graficos/tramos.png)

## Sensibilidad prefijada, sin selección de configuración

`protocolo.json` se guardó antes de calcular candidatos. La referencia permanece intacta. Se varía una condición a la vez: T >10 o >12 °C, HR <25 o <35%, viento >1,5 o >2,5 m/s, sector inclusivo 15°–165°. Además se retienen solo tramos estrictos de ≥2 o ≥3 h. Una última alternativa agrupa tramos separados por exactamente una hora **evaluable negativa**, que sigue siendo negativa y no se añade a las horas candidatas. Ninguna configuración atraviesa una hora desconocida. No se ensayan combinaciones adicionales ni se elige un ganador.

{table(ss)}

Las variaciones de umbrales producen de 778 a 948 h candidatas y de 146 a 171 tramos. Variar T ±1 °C modifica −3/+2 h; variar viento ±0,5 m/s modifica −89/+81 h; variar HR ±5 puntos modifica −57/+45 h. Son dependencias del criterio en esta muestra y no indican mérito meteorológico. Las persistencias de 2 y 3 h conservan 841 y 819 h en 130 y 119 tramos; sus duraciones medianas son 5 y 6 h. La alternativa de puente conserva las 867 h y reduce 156 tramos a **153 grupos**; agrega tres negativas a sus amplitudes, sin volverlas candidatas. Su amplitud media es 5,686 h, frente a 5,558 h de la referencia.

La distribución temporal de las horas retenidas cambia así:

{table(time_summary)}

`sensibilidad_temporal.csv` también cuantifica la distribución por año, año×mes y hora. `sensibilidad_tramos.csv` conserva los grupos y `distribuciones_tramos.csv` incluye cuantiles completos de duración, amplitud, viento medio y máximo horario en cada configuración. No se hicieron decisiones de ajuste basadas en esos resultados. La sensibilidad es anual; las aproximaciones agrícolas se mantienen como comparación de interpretación histórica separada, sin optimizarlas conjuntamente.

![Sensibilidad](graficos/sensibilidad.png)

## Resultados comprobados, incertidumbres y decisiones pendientes

**Comprobado:** cobertura, 13 huecos principales, anomalía de cuatro presiones, conteos de ceros y banderas, distribuciones válidas y diferencias exactas, tres estados horarios, 867 candidatas/156 tramos, agrupaciones por días y comparación prefijada. `verificar.py` comprueba los límites del período, desigualdades inclusivas/estrictas, ausencia frente a negativa, persistencia y separación conocida/desconocida con casos sintéticos, y reconcilia tablas y conteos. Los gráficos se limitan a seis resúmenes, incluida una única ventana que documenta el problema concreto de presión.

**Incertidumbres:** zona y semántica temporal de los promedios, dirección horaria agregada por el exportador, altura de T/HR, estabilidad/calibración de instrumentos, causas de huecos y ceros de 2018, naturaleza de los saltos bruscos, inicio agrícola y medianoche. Los CSV horarios no aportan una medida independiente de ráfaga usada aquí. El cambio de precisión aparente de presión alrededor de 2021–2022 requiere revisar procesamiento e instrumentos. La continuidad estadística mensual no permite distinguir con certeza cambios de instrumentación de meteorología o estacionalidad.

**Para un catálogo fiable falta** recuperar metadatos y mantenimiento dentro del período autorizado; resolver las horas y la altura de medición; revisar manualmente los valores y secuencias señalados; y contrastar candidatos, negativas y casos ambiguos con evidencia meteorológica independiente y fechada. Esa revisión debe distinguir calentamiento/sequedad por circulación ordinaria de episodios de descenso por el valle, verificar inicio y final, y registrar motivos y confianza sin convertir toda hora desconocida en negativa. Es necesario acordar si el catálogo se organiza por tramos o por episodios con interrupciones, cómo tratar censura y qué evidencia acredita un episodio.

Requieren contraste meteorológico independiente la representatividad del sector direccional, los umbrales absolutos durante todo el año, la persistencia mínima, la admisión de interrupciones conocidas, la correspondencia de la aproximación agrícola con el estudio y cualquier clasificación de intensidad o peligro. La revisión no se realizó con otras estaciones ni con el período reservado. No se construyó etiqueta operacional definitiva, no se entrenaron modelos y no se confirmaron terrales automáticamente.

## Ejecución e inventario

Desde la raíz del repositorio, con las versiones de `requirements.txt` disponibles:

```bash
python investigacion_ceazamet/diagnostico_2013_2023/diagnostico.py
python investigacion_ceazamet/diagnostico_2013_2023/verificar.py
python investigacion_ceazamet/diagnostico_2013_2023/informar.py
```

El script usa el backend Agg para generar PNG; no instala paquetes ni necesita red. Se usó Python {audit['python']}, pandas {audit['pandas']}, NumPy {audit['numpy']} y Matplotlib {audit['matplotlib']}. `sys.modules['numexpr']=None` desactiva una extensión opcional incompatible del host sin alterar datos. La ejecución regenera las tablas y gráficos del mismo período; el informe se regenera exclusivamente a partir de esas tablas. Los controles reproducibles quedan en `verificacion.log` y `comprobaciones.json`. Un cambio futuro del protocolo requiere una nueva versión documentada, no seleccionar retrospectivamente una configuración.

Tablas principales: `cobertura`, `huecos`, `distribucion_huecos`, `calidad_anual`, `valores_sospechosos`, `repeticiones_exactas`, `saltos_revision`, `continuidad_mensual`, `distribuciones`, `direccion_circular`, `sectores_direccion`, `cambios_exactos`, `estados_horarios`, `conteos_candidatos`, `tramos_anual`, `tramos_abril_agosto`, `dias_historicos`, `eventos_por_dias`, `distribuciones_dias_eventos`, `sensibilidad_resumen`, `sensibilidad_temporal`, `sensibilidad_tramos`, `distribuciones_tramos`, más las tablas de tramos para cada conjunto de días y las dos tablas de trazabilidad. Todos son CSV con encabezado, separador coma y punto decimal; NaN se guarda vacío, nunca como cero. Las unidades se especifican en este informe y en los metadatos fuente; `q50` es mediana, `q100` es máximo. Escalas Y/M de cobertura representan año y año–mes; `mes_hora` usa `MM-HH`. No hay salidas de años externos.

![Ventana del problema de presión](graficos/presion_sospechosa_2015.png)
'''
(O/'informe.md').write_text(text,encoding='utf-8')
print('informe.md regenerado desde tablas autorizadas')
