#!/usr/bin/env python3
"""Consolida la evidencia manual, bitácora de consultas y reporte sin acceder a red."""
import sys
sys.modules['numexpr']=None
import json
from pathlib import Path
import pandas as pd
OUT=Path(__file__).resolve().parent
def read(n): return pd.read_csv(OUT/f'{n}.csv')
def save(d,n): d.to_csv(OUT/f'{n}.csv',index=False)
def md(d):
    # Sin dependencia de tabulate.
    rows=['| '+' | '.join(map(str,d.columns))+' |','| '+' | '.join(['---']*len(d.columns))+' |']
    for values in d.itertuples(index=False,name=None): rows.append('| '+' | '.join(str(v).replace('|','/') for v in values)+' |')
    return '\n'.join(rows)
a=json.loads((OUT/'comprobaciones.json').read_text()); ev=json.loads((OUT/'evidencia_manual.json').read_text())
sources=pd.DataFrame(ev['fuentes']); sources['fecha_consulta']=ev['fecha_consulta']; save(sources,'registro_evidencia')
sel=read('seleccion_revision'); months=['','enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre']
queries=[]; correspondence=[]
for i,s in sel.iterrows():
    dt=pd.Timestamp(s.ancla); ident=s.id_objeto
    # Consultas efectivamente ejecutadas, en lotes de cuatro; mismas fechas de muestra.
    term='terral' if i<4 or ident.endswith('20140615T0800') else 'viento terral'
    day={'VCN-INIA-v0-20210527T1600':'27','VCN-INIA-v0-20140615T0800':'15','VCN-INIA-v0-20230528T2200':'28','OM-v0-20201009T0600':'9'}.get(ident)
    q=f'"Vicuña" "{term}" '+(f'"{day}" ' if day else '')+f'"{months[dt.month]}" "{dt.year}"'
    domains='ceaza.cl;elquiglobal.cl;xn--elvicuense-y9a.cl;diarioeldia.cl' if i>=20 else ''
    found=sources[sources.id_objeto_correspondiente.eq(ident)]
    qid=f'Q{i+1:02}'
    queries.append({'id_consulta':qid,'id_revision':s.id_revision,'fecha_consulta':ev['fecha_consulta'],'consulta':q,'dominios_filtro':domains,
                    'alcance':'mes/año, excepto día explícito en consulta; inspección de fechas del episodio en resultados de lote',
                    'fuentes_coincidentes':';'.join(found.id_fuente),'resultado':'fuente parcial coincidente' if len(found) else 'sin correspondencia evaluable encontrada en resultados revisados',
                    'limitacion':'Búsqueda acotada, resultados no exhaustivos; resultados ajenos al período o sin fecha suficiente excluidos'})
    if ident=='VCN-INIA-v0-20140615T0800':
        status='corroboración narrativa local parcial; confirmación horaria pendiente'
        reason='E01 relata una actividad urbana del mismo día y atribuye calor a terral. La hora aproximada de la crónica no se convierte al reloj INIA. No acredita inicio/cierre, persistencia ni las cuatro variables.'
    elif ident=='VCN-INIA-v0-20190813T0200':
        status='contexto coincidente parcialmente dependiente; contraste independiente pendiente'
        reason='E05 describe un episodio del mismo día. CEAZA opera la red y usa sus observaciones; independencia de INIA no demostrada. La explicación sinóptica aporta contexto, sin confirmar este tramo.'
    else:
        status='pendiente: sin evidencia suficiente encontrada'
        reason='No se encontró una fuente con episodio y ubicación suficientemente precisos que corresponda a esta ventana. Otros resultados son genéricos, culturales, comerciales o episodios de fecha distinta. Esto no prueba ausencia de terral.'
    correspondence.append({'id_revision':s.id_revision,'id_objeto':ident,'categoria':s.categoria,'id_consulta':qid,
                            'id_fuentes':';'.join(found.id_fuente),'enlaces':';'.join(found.url),
                            'fecha_publicacion':';'.join(found.fecha_publicacion),'episodio_desde':';'.join(found.episodio_desde),
                            'episodio_hasta':';'.join(found.episodio_hasta),'alcance_geografico':';'.join(found.alcance_geografico),
                            'precision_temporal':';'.join(found.precision_temporal),'independencia':';'.join(found.independencia),
                            'estado_contraste':status,'correspondencia':reason,'confirmacion_horaria':False,
                            'necesita':'Registro local contemporáneo con hora/zona y ubicación próxima a INIA; evidencia de viento cálido y seco independiente del criterio; metadatos temporales de estación'})
save(pd.DataFrame(queries),'bitacora_busqueda_ventanas'); save(pd.DataFrame(correspondence),'evidencia_por_ventana')
extra=[
 ['B01','terral Vicuña viento episodio 2013 2014 2015 2016 fecha -2024 -2025 -2026','Exploración general inicial; hallazgo E04; se devolvieron fragmentos de portales temporales ajenos al alcance, descartados'],
 ['B02','terral Vicuña 2017 2018 2019 2020 2021 2022 2023 episodio viento fecha -2024 -2025 -2026','Exploración general inicial; resultados ajenos al alcance descartados'],
 ['B03','"terral" "Vicuña" after:2013-01-01 before:2024-01-01 site:elvicuñense.cl','Filtro temporal no garantizó límites; descartados resultados no pertinentes'],
 ['B04','"terral" "Vicuña" after:2013-01-01 before:2024-01-01 site:elquiglobal.cl','Hallazgo E01 y resultados culturales/comerciales excluidos'],
 ['B05','"terral" "Vicuña" after:2013-01-01 before:2024-01-01 site:diarioeldia.cl','Resultados sin correspondencia evaluable'],
 ['B06','"terral" "Vicuña" after:2013-01-01 before:2024-01-01 site:ceaza.cl','Resultados sin correspondencia evaluable'],
 *[[f'B{7+i:02}',f'"viento terral" "Vicuña" "{y}"','Exploración anual; E02/E03; otros resultados de fechas distintas o sin fecha suficiente'] for i,y in enumerate([2013,2015,2016,2017])],
 *[[f'B{11+i:02}',f'"Vicuña" "terral" "{d}" "{m}" "{y}"','Consulta suplementaria restringida a prensa local; sin evidencia adicional correspondiente'] for i,(d,m,y) in enumerate([(7,'septiembre',2013),(8,'septiembre',2013),(13,'agosto',2019),(3,'agosto',2015)])]
]
extras=pd.DataFrame(extra,columns=['id_consulta','consulta','resultado']); extras['fecha_consulta']=ev['fecha_consulta']
extras['dominios_filtro']=''
extras.loc[extras.id_consulta.isin(['B11','B12']),'dominios_filtro']='elquiglobal.cl;diarioeldia.cl;diariolaregion.cl'
extras.loc[extras.id_consulta.isin(['B13','B14']),'dominios_filtro']='elquiglobal.cl;xn--elvicuense-y9a.cl;diarioeldia.cl;diariolaregion.cl'
save(extras,'bitacora_busqueda_contexto')
sens=read('sensibilidad_por_tramo').groupby('configuracion').agg(tramos_que_cambian=('cambia','sum'),horas_originales_no_retenidas=('horas_referencia_no_retenidas','sum')).reset_index()
save(sens,'resumen_sensibilidad_tramos')
om=read('posibles_omisiones'); fail=[]
for label in ['T>11','HR<30','V>2','D_en_0_180']:
    fail.append({'condicion_original_fallida':label,'casos_llegada':int(om.condiciones_fallidas_llegada.str.split(';').map(lambda z:label in z).sum())})
save(pd.DataFrame(fail),'resumen_fallos_omisiones')
bf=read('resumen_banderas'); annual=read('reconciliacion_anual')
sel_summary=sel.groupby(['categoria','epoca']).size().unstack(fill_value=0).reset_index()
report=f'''# Catálogo provisional de candidatos de terral, Vicuña–INIA, versión 0

Se conservan **156 tramos estrictos y 867 horas candidatas** de 01/01/2013–31/12/2023. Todos mantienen el estado **candidato por criterio histórico, sin confirmar**. Hay 138 tramos con alguna bandera técnica; ninguna los elimina o reclasifica. Se obtuvieron 68 ventanas exploratorias mensuales de posibles omisiones, 24 fuera de abril–agosto. La muestra para revisión reúne 30 ventanas: 11 referencias, 8 ambiguas y 11 posibles omisiones. El contraste encuentra una corroboración narrativa local parcial y un contexto meteorológico coincidente de independencia no demostrada. **Ninguna ventana tiene confirmación horaria suficiente.**

## Alcance y conservación

Se leyeron `modelo_predictivo_terral.md`, `hoja_de_ruta_terral.md` e `informe.md` del diagnóstico. Se reutilizan sus tablas y `protocolo.json`. La ingesta nueva abre solo la lista cerrada de tablas de `diagnostico_2013_2023`; valida todas las columnas temporales leídas antes del cálculo. No se abren CSV históricos globales, originales XLS ni otros períodos. Las cadenas de procedencia pueden nombrar bloques que empiezan fuera del período: son metadatos, no archivos abiertos. `manifiesto_entradas.csv` registra hashes comprobados antes y después. Las fuentes permanecen intactas.

Las consultas públicas buscaron episodios dentro de 2013–2023. **Incidencia de alcance web:** pese a las fechas solicitadas, el buscador entregó fragmentos de portales con estadísticas/observaciones externas al período, y dos páginas históricas abiertas incluían widgets meteorológicos y navegación contemporáneos. Ese contenido llegó en la respuesta del proveedor; se descartó sin incorporarlo a tablas, cálculos, gráficos o evidencia. No se puede afirmar aislamiento absoluto de lo mostrado por el proveedor. No se abrieron los portales de series encontrados ni se siguieron widgets, y no se descargaron datos de otras estaciones. Las búsquedas posteriores se restringieron a prensa local; no se guardaron páginas completas. La bitácora conserva consultas y síntesis históricas pertinentes, nunca esos valores externos. Esta incidencia limita la afirmación de acceso web exclusivamente histórico, aunque todos los insumos analíticos y resultados observacionales cumplen el período.

## Catálogo de referencia y trazabilidad

El original exige cuatro variables válidas, T>11 °C, HR<30%, velocidad media a 2 m >2 m/s y dirección inclusiva [0°,180°]. Se conserva 360° sin recodificarlo para cumplir. Las horas evaluables que fallan una condición quedan `no_cumple`; las otras quedan `no_evaluable`. Son estados de criterio, no positivos/negativos físicos de terral.

El ID `VCN-INIA-v0-AAAAMMDDTHHMM` depende de la primera marca de cada tramo y no del orden. Cambiar la definición requiere otra versión. `catalogo_referencia.csv` incluye primera/última marca, conteo, censura izquierda/derecha, medias y extremos de T/HR, viento medio, máximo del promedio horario, máximo horario publicado, n de máximos disponibles, dirección circular/R y disponibilidad. Los extremos de T/HR resumen **promedios horarios**; no son extremos instantáneos. Un máximo publicado no prueba calidad instrumental ni resolución subhoraria conocida.

`horas_referencia.csv` contiene las 867 marcas y sus valores horarios. `trazabilidad_catalogo.csv` contiene 3.468 observaciones principales, enlazadas a ID, fecha, variable, fila de la tabla diagnóstica, fila del CSV anual, archivo original, SHA-256, hoja, fila Excel, sensor, unidad, altura, min/prom/max, porcentaje y validez. `fila_tramos_anual_csv` enlaza el catálogo diagnóstico; `fila_estados_horarios_csv` enlaza cada hora. Los CSV fuente cuentan el encabezado como fila 1.

**`max_promedio_horario_ms` y `max_horario_publicado_ms` son campos distintos. Ninguno se denomina ráfaga.** El segundo es el mayor campo `max` publicado entre las horas del tramo, con semántica de muestreo pendiente; no se infiere una ráfaga de él ni se sustituye por una cifra periodística.

No hay censuras por borde o desconocida adyacente según la regla del diagnóstico. Esto no demuestra que las marcas coincidan con límites físicos. Primera/última marca describen cumplimiento horario, nunca inicio/cierre confirmado del fenómeno. La zona se conserva sin confirmar; no se convierte a UTC ni hora civil. Las distancias, meses y épocas usan el reloj registrado.

## Reconciliación

96.408 marcas esperadas = **867 cumple + 95.096 no cumple + 445 no evaluable**. La cobertura conjunta válida es 95.963 horas. Se reconstruye la regla desde valores y validez de la trazabilidad y se exige igualdad exacta con `estados_horarios.csv`. Cada hora candidata pertenece exactamente a un tramo; ninguna hora desconocida o que no cumple está incluida.

{md(annual)}

La suma es 156/867, diferencia cero contra el diagnóstico. Abril–agosto aporta 782 h; el resto, 85 h. Se mantienen por separado `dias_historicos.csv` y `eventos_por_dias.csv`: **148 días candidatos y 115 grupos anuales por días**, sin convertirlos en tramos continuos. `relacion_tramos_dias.csv` muestra el aporte de cada tramo a cada día; un tramo que cruza medianoche puede aportar a dos días. La tabla de días conserva estados desconocidos y sus horas. Los escenarios agrícolas siguen siendo aproximaciones del diagnóstico, sin resolver su frontera de medianoche ni reinterpretar el reloj.

## Auditoría técnica

Las reglas se fijaron en [protocolo.md](protocolo.md) antes del cálculo. Banderas: corto=1–2 h; sensible=cambio de pertenencia, límites o agrupación bajo alguna configuración ya ensayada; salto=registro previamente señalado entre primera−1 y última+1 h; dirección=fuera de [15,165], R<0,7 o giro circular ≥90° dentro del tramo; proximidad=desconocida conjunta a ≤24 h; calidad=porcentaje parcial, problema o banderas fuente en variables principales. No son pruebas de error o confirmación meteorológica.

{md(bf)}

Las filas se solapan: no sumar sus conteos. 26 tramos duran una hora y 11 dos horas. 18 tramos/141 horas no tienen ninguna de estas banderas, lo que tampoco certifica calidad o terral. Los 156 comparten incertidumbre sobre el método subhorario del promedio direccional exportado; esa limitación general se registra aparte para no ocultar las siete banderas específicas.

{md(sens)}

La sensibilidad estructural puede ser mayor que la pérdida de horas: un umbral más permisivo extiende o fusiona límites. La alternativa de puente afecta a seis tramos originales al agrupar tres pares, preservando 867 horas en 153 grupos del diagnóstico; el catálogo sigue en 156 tramos. `sensibilidad_por_tramo.csv` registra las diez comparaciones por candidato, horas originales retenidas y grupos solapados. Se conservan JSON de límites en cada comparación. No se ensayaron otras configuraciones ni se eligió una ganadora. Saltos y marcas desconocidas cercanas tienen tablas de enlace separadas, con encabezado incluso cuando no hay casos.

La media circular y R se calculan entre promedios horarios con pesos iguales; no reconstruyen la dirección subhoraria. Un tramo de una hora tiene R=1 por construcción, sin certificar estabilidad. La ausencia de porcentaje parcial o banderas de rango no descarta fallos instrumentales. La altura declarada de T/HR y su discrepancia con la descripción científica, calmas/repeticiones y cambios de precisión señalados por el diagnóstico siguen pendientes.

## Búsqueda exploratoria de omisiones

El protocolo selecciona cambios de 3 h con cuatro marcas consecutivas válidas, sin una sola hora original candidata en esas cuatro marcas. Usa simultáneamente calentamiento, secado y aumento de viento poco usuales para el mes y la hora, más un estado de llegada relativamente cálido/seco/ventoso. Las reglas completas, pisos físicos de selección y cuantiles se documentan en el protocolo; no son modificaciones de la referencia.

Los cuantiles q10/q90 se calculan agrupando 2013–2023 por **mes y hora de llegada**, con interpolación lineal y sin ponderación. Solo se usan cambios con las cuatro marcas conjuntas válidas y n≥100. `referencias_cambios_mes_hora.csv` registra n y ambos cuantiles por variable. Las medianas de estado se reutilizan desde `distribuciones.csv` del diagnóstico por mes×hora: cada variable válida por separado, candidatas incluidas, sin presión requerida. `referencias_estado_mes_hora.csv` conserva n y los cuantiles fuente. Esta referencia es retrospectiva de toda la muestra; no está ajustada en entrenamiento y no es apta para validar un predictor sin fuga.

Se encuentran **209 llegadas elegibles**, resumidas en **149 grupos exploratorios**. Agrupar llegadas separadas ≤6 h sirve para reducir redundancia; no declara un evento ni modifica tramos. Se elige la llegada central cronológica de cada grupo. Luego se conserva hasta una por año×mes por SHA-256, sin ordenar por extremos: **68 ventanas mensuales**, de ellas **24 fuera de abril–agosto**. `llegadas_exploratorias.csv`, `grupos_exploratorios.csv` y `posibles_omisiones.csv` conservan todas las etapas.

{md(pd.DataFrame(fail))}

Las condiciones fallidas se solapan. Cada caso conserva los valores de llegada, cambios, límites de selección, n de referencia, medianas y fallos originales. `condiciones_omisiones_horarias.csv` explica el fallo en **cada una de las cuatro marcas**; `trazabilidad_omisiones.csv` enlaza filas fuente. Que la condición original falle no demuestra una omisión real. Puede ser calentamiento diurno ordinario o brisa seca. El procedimiento no agota otras firmas ni explora transiciones con candidatas originales dentro de las cuatro marcas, ni ventanas que atraviesan huecos. El máximo de una por mes reduce revisión, no estima frecuencia física. No hay etiquetas de terral, objetivos ni predictores listos para entrenamiento.

## Selección de revisión y gráficos

Se seleccionan **30 ventanas**, en los once años. Las cuotas, estratos y SHA-256 quedaron fijados antes de calcular y buscar evidencia. Referencias generales: una por año. Ambiguas: ocho tramos distintos con alguna bandera. Omisiones: una por año. Dentro de las cuotas se balancea año y época y se desempata por hash del ID, sin viento máximo, duración, cambios térmicos ni evidencia periodística como criterios. Las ventanas no se solapan. Referencia general no significa ausencia de banderas.

{md(sel_summary)}

No hay candidatas originales en DJF; las tres ventanas de esa época provienen de la búsqueda exploratoria. Las épocas MAM/JJA/SON reúnen nueve ventanas cada una. Es una muestra para revisión, no muestra aleatoria simple ni estimación de prevalencia. `seleccion_revision.csv` preserva categoría, ID, ancla, año, época, hash, límites y gráfico. `distribucion_seleccion.csv` desglosa año×época×categoría.

Se generan únicamente los 30 PNG de 48 marcas en `graficos/`, uno por ventana, a partir de valores horarios. T/HR/viento usan puntos y líneas con NaN en datos no válidos; no hay interpolación, suavizado ni conexión entre ambos lados de un hueco. Dirección usa puntos. Se muestran separadamente promedio de viento y máximo publicado. El sombreado naranja identifica cumplimiento horario y el gris desconocidas; son ayudas gráficas alrededor de marcas, no intervalos físicos confirmados. La línea vertical es solo el ancla de selección. `datos_graficos.csv` conserva las 1.440 filas reproducibles.

La revisión visual cubrió los 30 gráficos en cinco hojas de contacto temporales y uno a resolución completa para comprobar ejes y leyendas. En varias omisiones de DJF/SON se observa un ciclo repetido de calentamiento y secado, con viento de sector occidental: es compatible con alternativas como el ciclo diurno y refuerza la necesidad de contraste físico, sin reclasificar ningún caso. La ventana exploratoria `OM-v0-20180617T0000` también muestra horas que cumplen después de las cuatro marcas seleccionadas: la omisión es una transición previa para revisar, no una afirmación de que las 48 horas carezcan de candidatas. Los gráficos pueden incluir otros tramos originales del entorno; solo el ID del ancla pertenece a la selección. Ninguna interpretación de mañana/noche civil se cierra mientras falte la zona.

## Contraste público y fechado

Se ejecutaron 30 consultas por mes/año o fecha de ventana, además de búsquedas generales y suplementarias, sin contactar a personas. Las bitácoras registran consulta exacta, filtros, alcance y resultado. Se revisaron las fechas de episodio de los resultados agrupados: el buscador a menudo devolvió hoteles, folclor, menciones genéricas o episodios distintos. La búsqueda fue acotada y no exhaustiva. El registro manual se conserva en `evidencia_manual.json`; `cerrar.py` genera `registro_evidencia.csv` y `evidencia_por_ventana.csv` sin acceso a red.

- **E01, 15/06/2014:** la [crónica local publicada el 18/06/2014](https://www.elquiglobal.cl/2014/06/18/pdi-desarrolla-exitosa-maraton-en-vicuna-como-parte-de-su-aniversario/) atribuye al terral el calor durante una maratón en Vicuña. Corresponde por día al candidato `VCN-INIA-v0-20140615T0800`. Es corroboración narrativa parcial e independiente del criterio de cuatro umbrales; no acredita inicio/cierre ni concordancia horaria sin zona. Se trabajó con el cuerpo indexado porque la apertura falló.
- **E05, 13/08/2019:** el [análisis CEAZA publicado el 14/08/2019](https://old.ceaza.cl/2019/08/14/quieres-saber-origen-las-altas-temperaturas-este-martes-13-la-region-coquimbo/) aporta contexto sinóptico del día del candidato `VCN-INIA-v0-20190813T0200`. Usa la misma red, por lo que la independencia respecto de INIA no está demostrada. Se registra como contexto parcialmente dependiente, sin confirmación.
- E02, E03, E04 y E06 describen episodios distintos de las 30 ventanas: daño local del [03/07/2015](https://www.elquiglobal.cl/cae-arbol-en-plaza-de-vicuna-producto-del-terral-y-dana-vehiculo-que-estaba-estacionado/), explicación regional de [20–21/08/2017](https://old.ceaza.cl/2017/08/22/explican-aumento-temperatura-del-pasado-domingo-lunes-la-region-coquimbo/), cortes locales de [18–19/06/2019](https://www.xn--elvicuense-y9a.cl/2019/06/20/viento-terral-causo-problemas-en-vicuna/) y análisis DMC de [27/08/2019](https://climatologia.meteochile.gob.cl/application/publicaciones/documentoPdf/boletinClimatologicoMensual/boletinClimatologicoMensual201908.pdf). Se conservan como hallazgos contextuales, con precisión temporal y dependencia explícitas. No se sustituyen ventanas para crear aciertos ni se agregan gráficos de esos episodios.

Para **28 ventanas** no se encontró correspondencia suficiente; para todas las 30 sigue pendiente la confirmación horaria. Ausencia de reporte no implica ausencia de terral. Tampoco se transforma la atribución de un daño o calor en prueba completa del mecanismo. Ninguna fuente que dependa de los mismos cuatro umbrales se usa como confirmación independiente. Se necesita documentación contemporánea con fecha/hora/zona y lugar próximos a INIA, junto con evidencia meteorológica independiente y metadatos de la estación. La fecha del buscador de rastreo/publicación no sustituye la fecha del artículo ni del episodio; en E06 la publicación exacta queda desconocida.

## Decisiones pendientes para una etiqueta operacional

Resolver zona y marcas que representan comienzo/final de agregación; comprobar dirección circular exportada y su validez en calma; revisar alturas, sensores, calibraciones, mantenimiento y cambios instrumentales dentro del período; interpretar saltos con soporte independiente. Definir después, con evidencia meteorológica, inicio/cierre físico, persistencia, interrupciones, separación de episodios y severidad, sin tratar estos conteos de criterio como verdad. Una etiqueta anual deberá distinguir circulación ordinaria de descenso cálido/seco; la selección de omisiones no toma esa decisión. El período reservado no participa en ese trabajo.

Las preguntas de [preguntas_ceaza.md](preguntas_ceaza.md) quedan redactadas y **sin enviar**. No se ajustaron umbrales, no se cerró una etiqueta operacional, no se entrenaron modelos y no se asignaron negativas a horas desconocidas.

## Reproducibilidad e inventario

Desde la raíz del repositorio, con las mismas bibliotecas del diagnóstico:

```bash
python investigacion_ceazamet/catalogo_provisional_v0/construir.py
python investigacion_ceazamet/catalogo_provisional_v0/cerrar.py
python investigacion_ceazamet/catalogo_provisional_v0/verificar.py
```

`construir.py` no tiene red y regenera catálogo, banderas, omisiones, selección y los 30 gráficos. `cerrar.py` transforma el registro manual en tablas de evidencia, bitácoras e informe; no garantiza reproducibilidad de futuros resultados del buscador. `verificar.py` comprueba límites, regla, partición de horas, censura, filas fuente, fallos de omisiones, selección sin solapamiento, datos gráficos sin relleno, registro por ventana y conservación de hashes. `comprobaciones.json` y `verificacion.json` registran conteos y controles. `requirements.txt` fija versiones. Los CSV tienen encabezados, coma y punto decimal; un vacío significa dato no disponible, nunca cero.

El catálogo, banderas y evidencia se unen por ID pero permanecen en archivos separados. Para recorrer los gráficos y consultar los fallos/contraste de la muestra, abrir [revision.html](revision.html), generado localmente y sin recursos externos.
'''
(OUT/'informe.md').write_text(report)
notes=read('evidencia_por_ventana').set_index('id_revision')
from html import escape
items=[]
for _,s in sel.iterrows():
    n=notes.loc[s.id_revision]; extra=''
    if s.categoria=='posible_omision':
        p=om[om.id_omision.eq(s.id_objeto)].iloc[0]
        extra=f'<p>Fallos originales en llegada: {escape(p.condiciones_fallidas_llegada)}. dT={p.dT_3h:.2f} °C, dHR={p.dHR_3h:.2f} puntos, dV={p.dV_3h:.2f} m/s (3 h).</p>'
    else:
        f=read('banderas'); p=f[f.id_tramo.eq(s.id_objeto)].iloc[0]
        cols=['corto','sensible','salto_previo','direccion_ambigua','proximo_hueco','calidad_fuente']
        extra='<p>Banderas: '+', '.join(c for c in cols if p[c])+'.</p>'
    items.append(f'<article id="{escape(s.id_objeto)}"><h2>{escape(s.id_objeto)} · {s.categoria}</h2><p>{s.inicio_ventana} – {s.fin_ventana}; zona sin confirmar.</p>{extra}<p>{escape(n.estado_contraste)}</p><p>{escape(n.correspondencia)}</p><img loading="lazy" src="{s.grafico}" alt="Auditoría horaria de {s.id_objeto}"></article>')
html='<!doctype html><html lang="es"><meta charset="utf-8"><title>Revisión terral v0</title><style>body{font:16px system-ui;max-width:1100px;margin:30px auto;padding:0 15px;background:#f4f4f1;color:#222}article{background:white;padding:20px;margin:30px 0}img{width:100%;height:auto}h2{font-size:20px}</style><h1>Revisión provisional v0 · Vicuña–INIA · 2013–2023</h1><p>30 ventanas; criterio, banderas y evidencia separados. Todas las confirmaciones horarias siguen pendientes. Ninguna curva acredita ráfaga.</p><p><a href="informe.md">Informe</a> · <a href="seleccion_revision.csv">Selección</a> · <a href="evidencia_por_ventana.csv">Contraste</a></p>'+''.join(items)+'</html>'
(OUT/'revision.html').write_text(html)
print('Registro: 6 fuentes; 30 contrastes; 30 consultas de muestra y 14 de contexto. Informe y revisión local generados.')
