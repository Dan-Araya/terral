# Protocolo previo: combinación Pisco Elqui y Llanos de Huanta, v1

Fecha local: 21/10/2026 (America/Santiago). Este documento y configuración, lista exacta de predictores, código, soporte y hashes se guardan antes del primer entrenamiento. Se conservan los protocolos individuales adjuntos a continuación; las precisiones de esta sección sustituyen únicamente sus cuatro brazos, soporte y contrastes. No se identifica error material previo que requiera cambiar el método. Ver revision_previa.md.

Hipótesis previa: Pisco y Huanta mostraron mejoras individuales consistentes a 3 horas. Se comprobará si combinarlas mejora frente a cada una por separado. También pueden aportar información redundante o la combinación puede empeorar. No se seleccionan variables, hiperparámetros, sensor, altura, umbral, retrasos ni transformaciones según resultados.

Solo observaciones 2013-01-01 00:00 a 2023-12-31 23:00. Sin red, descargas, otras estaciones, observaciones reservadas, despliegue, modificación del catálogo/datos INIA ni contactos. Se permite leer auditoría y documentación local multies­tación sin incorporar observaciones de otras estaciones. No se abren XLS originales ni históricos fuera del rango autorizado. Los CSV de cada estación contienen sensores a otras alturas, que se descartan por identidad y nunca se utilizan como predictores ni para rellenar huecos.

## Ocho variantes y soporte

A INIA básica (35); B A+presión propia (41); C A+Pisco (72); D B+Pisco (78); E A+Huanta (72); F B+Huanta (78); G A+Pisco+Huanta (109); H B+Pisco+Huanta (115). Los 37 predictores de cada estación y 6 de presión propia son exactamente los del experimento individual. Calendario compartido una sola vez. Predictores.json se fija antes del primer ajuste.

Sensores Pisco: 59 temperatura 1.5 m, 60 HR 1.5 m, 56 viento 2 m, 57 dirección 2 m, PEPA presión 2 m. Huanta: LLHTA T 2 m, LLHHR HR 2 m, LLHVV2M V 2 m, LLHDV2M D 2 m, LLHPA P 2 m. Configuración, metadatos, unidades y máscaras se contrastan contra filas e integridad auditada. Se usa exclusivamente viento a 2 m. Dirección circular; ceros válidos conservados. Sin sustitución ni interpolación ni suavizado ni máscaras nuevas. Presión como variable local, sin gradientes ni correcciones. Máximo de seis promedios horarios previos, nunca ráfaga.

Un único soporte estricto para las ocho variantes en entrenamiento y validación: todas las variables básicas INIA, presión propia y cinco variables de cada complementaria válidas en las siete marcas [t−6,t], con emisión no_cumple y etiqueta futura conocida. Cada modelo/horizonte/partición se ajusta desde cero: 48 ajustes por ejecución. Se conservan fronteras y purga de tramos completos que las cruzan. Se reportan horas, positivos e inicios distintos antes/después por partición/rol y pérdidas frente al soporte cerrado de cada experimento individual (incluida presión propia); no se reutilizan sus predicciones ni métricas. Los conteos de soporte se cotejan con las particiones originales, sin entrenar con ellos. Se distingue inicio afectado de totalmente perdido. No se suman entrenamientos expansivos solapados.

Se informan disponibilidad y calidad por sensor y ventanas: ausencia incluye campos requeridos no finitos, sin presencia o %Datos≤0; calidad es la máscara no utilizable restante con campos presentes. Son motivos descriptivos no excluyentes en ventanas, sin modificar ninguna máscara. Las exclusiones básicas y adicionales se conservan por separado. El soporte potencial de un brazo sirve solo para describir pérdidas.

## Contrastes fijados

Principales G−C (añadir Huanta a Pisco), G−E (añadir Pisco a Huanta), H−D y H−F (análogos con presión propia). Secundarios B−A, C−A, D−B, E−A, F−B, G−A, H−B. Se reportan todos aunque desfavorables; no se escoge retrospectivamente una estación como único comparador.

Cada contraste exige para mejora consistente ΔAP>0 y ΔBrier<0 en las tres particiones y IC agregado AP totalmente >0 y Brier totalmente <0. Empeoramiento consistente exige lo contrario. Si ambos intervalos incluyen cero: ausencia de evidencia de mejora; otros casos: resultado incierto detallando signos y métricas. Para afirmar mejora de combinación frente a ambas sin presión deben cumplir G−C Y G−E; con presión deben cumplir H−D Y H−F. Si solo mejora frente a una o algún IC incluye cero, se dirá expresamente. Falta de significación no demuestra redundancia.

Bootstrap original idéntico: 300 réplicas semilla 20132023, bloques móviles de tres meses, ocho por cada bienio, inicios 0..21. Mismas multiplicidades para todas las variantes, contrastes y los dos horizontes; guardadas para verificación. IC percentil 95% agregados por contraste, múltiples comparaciones sin ajuste: no garantía simultánea 95%. Avisos ya vinculados se remuestrean por mes original de aviso/inicio sin reagrupar horas artificiales; mediana descriptiva sin intervalo. Se usa toda la rejilla original y ninguna selección posterior de umbral.

Repetición completa con 48 nuevos ajustes y comparación exacta de artefactos deterministas, verificaciones independientes de soporte, etiquetas, ventanas, purgas, máscaras, sensores, tiempo, características, escalas entrenadas, probabilidades, métricas e intervalos y avisos. Protección por SHA-256 de fuentes y de ambos experimentos anteriores completos, línea base y catálogo. La comprobación de conservación no abre observaciones reservadas. Semilla solo para bootstrap; optimización determinista sin muestreo.

Limitaciones: reloj registrado sin zona confirmada, intervalo y latencia histórica pendientes; disponibilidad inmediata de t provisional. No se buscan desfases. Máscaras INIA y complementarias distintas heredadas, discrepancia documental alturas T/HR INIA pendiente. Bootstrap condicional a ajustes/catálogo, pocos inicios, extremos mensuales no uniformes, AP agregada mezcla modelos. Desarrollo exploratorio 2013–2023: criterio histórico, no mecanismo físico ni capacidad operacional. AP no es porcentaje de aciertos.

## Protocolo individual Pisco heredado (secciones de método)

# Protocolo previo: Pisco Elqui e INIA, v1

Fecha: 21/10/2026. Experimento de desarrollo retrospectivo, exclusivamente 2013-01-01 00:00 a 2023-12-31 23:00 del reloj registrado. Sin red, descarga, despliegue, búsqueda de desfases, selección de estaciones, variables o hiperparámetros. Los resultados no validan meteorológicamente el terral. No se elige una configuración ganadora después de validar.

Se heredan literalmente objetivo, catálogo provisional v0, validez básica INIA, ventana estricta [t−6,t], exclusiones de objetivos desconocidos, emisión no_cumple, fronteras y tramos que cruzan fronteras del protocolo de linea_base_inicio_v0. Se reconcilian 156 tramos y 867 horas; y indica algún inicio conocido en (t,t+h], h=1,3. Se conservan todos los identificadores si hay más de un inicio. Etiqueta no equivale al inicio físico del terral.

SUPUESTOS PROVISIONALES: promedio marcado t disponible inmediatamente en t; coincidencia de marcas de ambas estaciones representa la misma hora del reloj registrado. Zona, posición del intervalo, latencia y alineación física no confirmadas. No se infieren por desempeño ni correlación. Presión se usa como variable local, sin gradientes ni reducción altimétrica.

## Fuentes cerradas y calidad

Once CSV anuales historico_inia/derivados/observaciones_2013.csv,…,observaciones_2023.csv; catalogo_provisional_v0/catalogo_referencia.csv; estaciones_complementarias/pisco_elqui/derivados/horarias.csv e integridad.json; configuración local y documentos/código requeridos. No se abren XLS originales (algunos bloques originales incluyen bordes fuera del alcance), otros años ni resultados globales. Hash de toda fuente leída antes/después; Pisco se coteja además con el hash de integridad auditada. Fechas fuera de alcance abortan.

INIA: promedio finito, 0<%Datos≤100, prom_utilizable_revision=1, HR [0,100], viento≥0, dirección [0,360], una fila por hora/variable. Presión propia con la misma máscara auditada INIA, sin nueva depuración. Alturas según CSV; persiste discrepancia documental T/HR 1.5 vs 2 m. Pisco: códigos 59 T 1.5 m, 60 HR 1.5 m, 56 V 2 m, 57 D 2 m, PEPA P 2 m verificados contra configuración y filas. Se conserva máscara utilizable_revision auditada (incluye min/prom/max/%Datos, rangos, orden excepto dirección); duplicados excluidos. Ceros conservados. Sin imputación, interpolación, suavizado ni exclusión adicional por saltos/repeticiones.

## Brazos y columnas

A: 35 predictores exactos de la logística de línea base. B: A + 6 de presión propia. C: A + 37 de Pisco. D: B + 37 de Pisco. Total 35/41/72/78. El listado completo se fija en predictores.json antes del primer ajuste y se verifica en ejecución.

Cada escalar añadido (presión INIA y T, HR, V, seno D, coseno D, P Pisco) aporta actual, lag1, delta1, lag3, delta3 y media de [t−6,t−1]. Pisco añade máximo de los seis promedios horarios de V en [t−6,t−1], como INIA; no es ráfaga ni máximo instrumental del CSV. Dirección solo seno/coseno y sus derivados. Calendario una sola vez, heredado de A.

Comparación principal: intersección estricta de todas las variables en las siete marcas [t−6,t], misma etiqueta y mismas emisiones de entrenamiento y validación para A/B/C/D. Se reportan soportes potenciales por brazo y pérdidas de soporte sin entrenar/evaluar sobre esos soportes distintos. Motivos adicionales no excluyentes y primarios; se preserva detalle de exclusiones base.

Logística por brazo/horizonte/partición. Escala poblacional aprendida solo de entrenamiento, constantes escala 1. Sin pesos de clase. Suma de log-loss + 0.5 suma beta², intercepto libre, C=1, L-BFGS-B gtol=1e−6, ftol=1e−12, maxiter=1000, inicial intercepto logit prevalencia y coeficientes 0. Misma configuración del código base, sin búsqueda ni calibración posterior.

## Validación y evaluación

2013–2017→2018–2019; 2013–2019→2020–2021; 2013–2021→2022–2023. Soportes [t−6,t+h] enteros en cada bloque; purga adicional de tramos completos cruzando frontera. Son validaciones de desarrollo reutilizadas, no prueba final independiente.

AP con empates agrupados, curvas PR, Brier y calibración en bordes [0,.001,.003,.01,.03,.1,.3,.5,1]. Referencias constante y mes×hora aprendidas en entrenamiento común como diagnóstico, no brazos adicionales. Avisos exactamente según función notices de línea base: p≥{.001,.003,.01,.03,.1,.3,.5}, grupos consecutivos a una hora, correspondencia cronológica uno a uno, redundantes separados; anticipación desde primera emisión que anticipa efectivamente. Inicios evaluables exigen oportunidad en soporte común; exposición en meses equivalentes, desglose por partición y estación del año. No se selecciona umbral.

Contrastes firmados B−A, C−A, D−B para AP, Brier y métricas de avisos en cada umbral, por partición y conjunto agregado. AP mayor/Brier menor es favorable. Bootstrap pareado 300 réplicas semilla 20132023, ocho bloques móviles de tres meses entre 22 inicios dentro de cada bienio; las mismas muestras para todos los brazos/horizontes. Guardar multiplicidades. Intervalos percentiles 2.5–97.5% solo agregados. Avisos remuestrean registros mensuales ya vinculados, sin reagrupar horas artificiales; se preserva asignación mes de aviso/inicio. Extensión: también diferencias de conteos y anticipación media; mediana descriptiva, sin intervalo bootstrap. Limitaciones: condicional a ajustes y catálogo, dependencia temporal aproximada, pocos inicios, ponderación no uniforme de extremos y sin incertidumbre de entrenamiento/etiquetas.

Interpretación fijada: mejora consistente requiere deltas AP>0 y Brier<0 en los tres bloques y ambos IC agregados favorables; empeoramiento consistente, lo contrario. Si ambos IC agregados incluyen cero: ausencia de evidencia de mejora; en los demás casos, resultado incierto, detallando signos, magnitudes y compromisos de avisos. No basta una métrica o partición. No implica utilidad operacional, ni se selecciona configuración.

## Revisión metodológica antes de entrenar

No se detecta contradicción que impida esta comparación provisional. Diferencias explícitas: la máscara auditada Pisco exige todos los estadísticos mientras INIA hereda su promedio utilizable; no se uniforman silenciosamente. La línea base no comprueba explícitamente %Datos≤100 en ingest(), pero la auditoría sí: se comprueba que no cambia ninguna observación básica. El código usa ftol=1e−12 además de gtol; se conserva. «Máximo horario» en la extensión significa máximo de promedios horarios previos conforme al código base. El informe documental de octubre no entrenaba en aquella revisión; este nuevo trabajo independiente autoriza el entrenamiento bajo sus límites abiertos. No se interpreta como resolución de dudas instrumentales.

Controles: límites, hashes, igualdad exacta soporte/etiquetas, columnas, calidad, fronteras entrenamiento/validación, objetivos reconstruidos, finitud probabilidades, denominadores horarios/calibración/eventos, parámetros y escala solo entrenamiento, reconstrucción puntual independiente de features/probabilidades e invariancia al alterar datos posteriores a múltiples emisiones. Registrar hash/fecha de protocolo, columnas y código antes del primer ajuste. Correcciones de implementación registradas separadamente; no cambios por desempeño.

## Protocolo individual Huanta heredado (secciones de método)

# Protocolo previo: Llanos de Huanta e INIA, v1

Fecha: 21/10/2026. Experimento de desarrollo retrospectivo, exclusivamente 2013-01-01 00:00 a 2023-12-31 23:00 del reloj registrado. Sin red, descarga, despliegue, búsqueda de desfases, selección de estaciones, variables o hiperparámetros. Los resultados no validan meteorológicamente el terral. No se elige una configuración ganadora después de validar.

Se heredan literalmente objetivo, catálogo provisional v0, validez básica INIA, ventana estricta [t−6,t], exclusiones de objetivos desconocidos, emisión no_cumple, fronteras y tramos que cruzan fronteras del protocolo de linea_base_inicio_v0. Se reconcilian 156 tramos y 867 horas; y indica algún inicio conocido en (t,t+h], h=1,3. Se conservan todos los identificadores si hay más de un inicio. Etiqueta no equivale al inicio físico del terral.

SUPUESTOS PROVISIONALES: promedio marcado t disponible inmediatamente en t; coincidencia de marcas de ambas estaciones representa la misma hora del reloj registrado. Zona, posición del intervalo, latencia y alineación física no confirmadas. No se infieren por desempeño ni correlación. Presión se usa como variable local, sin gradientes ni reducción altimétrica.

## Fuentes cerradas y calidad

Once CSV anuales historico_inia/derivados/observaciones_2013.csv,…,observaciones_2023.csv; catalogo_provisional_v0/catalogo_referencia.csv; estaciones_complementarias/llanos_de_huanta/derivados/horarias.csv e integridad.json; configuración local y documentos/código requeridos. No se abren XLS originales (algunos bloques originales incluyen bordes fuera del alcance), otros años ni resultados globales. Hash de toda fuente leída antes/después; Huanta se coteja además con el hash de integridad auditada. Fechas fuera de alcance abortan.

INIA: promedio finito, 0<%Datos≤100, prom_utilizable_revision=1, HR [0,100], viento≥0, dirección [0,360], una fila por hora/variable. Presión propia con la misma máscara auditada INIA, sin nueva depuración. Alturas según CSV; persiste discrepancia documental T/HR 1.5 vs 2 m. Huanta: códigos LLHTA T 2 m, LLHHR HR 2 m, LLHVV2M V 2 m, LLHDV2M D 2 m, LLHPA P 2 m verificados contra configuración y filas. Se conserva máscara utilizable_revision auditada (incluye min/prom/max/%Datos, rangos, orden excepto dirección); duplicados excluidos. Ceros conservados. Sin imputación, interpolación, suavizado ni exclusión adicional por saltos/repeticiones.

## Brazos y columnas

A: 35 predictores exactos de la logística de línea base. B: A + 6 de presión propia. C: A + 37 de Huanta. D: B + 37 de Huanta. Total 35/41/72/78. El listado completo se fija en predictores.json antes del primer ajuste y se verifica en ejecución.

Cada escalar añadido (presión INIA y T, HR, V, seno D, coseno D, P Huanta) aporta actual, lag1, delta1, lag3, delta3 y media de [t−6,t−1]. Huanta añade máximo de los seis promedios horarios de V en [t−6,t−1], como INIA; no es ráfaga ni máximo instrumental del CSV. Dirección solo seno/coseno y sus derivados. Calendario una sola vez, heredado de A.

Comparación principal: intersección estricta de todas las variables en las siete marcas [t−6,t], misma etiqueta y mismas emisiones de entrenamiento y validación para A/B/C/D. Se reportan soportes potenciales por brazo y pérdidas de soporte sin entrenar/evaluar sobre esos soportes distintos. Motivos adicionales no excluyentes y primarios; se preserva detalle de exclusiones base.

Logística por brazo/horizonte/partición. Escala poblacional aprendida solo de entrenamiento, constantes escala 1. Sin pesos de clase. Suma de log-loss + 0.5 suma beta², intercepto libre, C=1, L-BFGS-B gtol=1e−6, ftol=1e−12, maxiter=1000, inicial intercepto logit prevalencia y coeficientes 0. Misma configuración del código base, sin búsqueda ni calibración posterior.

## Validación y evaluación

2013–2017→2018–2019; 2013–2019→2020–2021; 2013–2021→2022–2023. Soportes [t−6,t+h] enteros en cada bloque; purga adicional de tramos completos cruzando frontera. Son validaciones de desarrollo reutilizadas, no prueba final independiente.

AP con empates agrupados, curvas PR, Brier y calibración en bordes [0,.001,.003,.01,.03,.1,.3,.5,1]. Referencias constante y mes×hora aprendidas en entrenamiento común como diagnóstico, no brazos adicionales. Avisos exactamente según función notices de línea base: p≥{.001,.003,.01,.03,.1,.3,.5}, grupos consecutivos a una hora, correspondencia cronológica uno a uno, redundantes separados; anticipación desde primera emisión que anticipa efectivamente. Inicios evaluables exigen oportunidad en soporte común; exposición en meses equivalentes, desglose por partición y estación del año. No se selecciona umbral.

Contrastes firmados B−A, C−A, D−B para AP, Brier y métricas de avisos en cada umbral, por partición y conjunto agregado. AP mayor/Brier menor es favorable. Bootstrap pareado 300 réplicas semilla 20132023, ocho bloques móviles de tres meses entre 22 inicios dentro de cada bienio; las mismas muestras para todos los brazos/horizontes. Guardar multiplicidades. Intervalos percentiles 2.5–97.5% solo agregados. Avisos remuestrean registros mensuales ya vinculados, sin reagrupar horas artificiales; se preserva asignación mes de aviso/inicio. Extensión: también diferencias de conteos y anticipación media; mediana descriptiva, sin intervalo bootstrap. Limitaciones: condicional a ajustes y catálogo, dependencia temporal aproximada, pocos inicios, ponderación no uniforme de extremos y sin incertidumbre de entrenamiento/etiquetas.

Interpretación fijada: mejora consistente requiere deltas AP>0 y Brier<0 en los tres bloques y ambos IC agregados favorables; empeoramiento consistente, lo contrario. Si ambos IC agregados incluyen cero: ausencia de evidencia de mejora; en los demás casos, resultado incierto, detallando signos, magnitudes y compromisos de avisos. No basta una métrica o partición. No implica utilidad operacional, ni se selecciona configuración.

## Revisión metodológica antes de entrenar

No se detecta contradicción que impida esta comparación provisional. Diferencias explícitas: la máscara auditada Huanta exige todos los estadísticos mientras INIA hereda su promedio utilizable; no se uniforman silenciosamente. La línea base no comprueba explícitamente %Datos≤100 en ingest(), pero la auditoría sí: se comprueba que no cambia ninguna observación básica. El código usa ftol=1e−12 además de gtol; se conserva. «Máximo horario» en la extensión significa máximo de promedios horarios previos conforme al código base. El informe documental de octubre no entrenaba en aquella revisión; este nuevo trabajo independiente autoriza el entrenamiento bajo sus límites abiertos. No se interpreta como resolución de dudas instrumentales.

Controles: límites, hashes, igualdad exacta soporte/etiquetas, columnas, calidad, fronteras entrenamiento/validación, objetivos reconstruidos, finitud probabilidades, denominadores horarios/calibración/eventos, parámetros y escala solo entrenamiento, reconstrucción puntual independiente de features/probabilidades e invariancia al alterar datos posteriores a múltiples emisiones. Registrar hash/fecha de protocolo, columnas y código antes del primer ajuste. Correcciones de implementación registradas separadamente; no cambios por desempeño.

## Hipótesis física previa del usuario y alcance Huanta

El usuario plantea que Llanos de Huanta está al este de la zona de formación del terral y podría registrar condiciones precursoras. Distingue esta situación de Gabriela Mistral y La Serena, al oeste, y la considera semejante a Pisco Elqui, situado más al sur. Se registra como hipótesis física del usuario, sin asumir un mecanismo demostrado ni una mejora predictiva. No se añaden otras estaciones ni se intersectan sus coberturas. A y B se reajustan en el soporte propio de Huanta. No se comparan rendimientos entre experimentos con soportes diferentes.

Se usan exclusivamente los cinco sensores indicados a 2 m. Los sensores a 10 m permanecen separados y no sustituyen huecos. La máscara auditada se comprueba contra los campos numéricos; no se excluyen adicionalmente saltos o secuencias constantes. Se informa cobertura por sensor/año, huecos contiguos, motivos no excluyentes y pérdidas marginales después de exigir los otros sensores, además de positivos e inicios sin ninguna oportunidad restante. Se distingue un inicio afectado de uno totalmente perdido. Se examina explícitamente el hueco LLHTA 2015-04-28 11:00 a 2016-04-30 23:00 y la disponibilidad diferente de LLHPA. Los conteos expansivos de entrenamiento se solapan y no se suman. Ningún análisis de cobertura relaja el soporte.

El usuario informa actualización automática horaria de todas las estaciones. No se incorporan demoras hipotéticas ni se buscan desplazamientos temporales. Esto no resuelve zona horaria histórica, posición/duración del intervalo ni disponibilidad efectiva al emitir: se documentan esas incertidumbres separadamente.

Semilla única 20132023 para bootstrap; optimización determinista sin muestreo. Protocolo, configuración, columnas, fuentes y código se registran antes del primer ajuste. Se verifica conservación por hashes de catálogo y experimentos anteriores; no se abren archivos de observaciones reservadas para esa comprobación. Se ejecutará una repetición completa con 24 nuevos ajustes y comparación exacta de artefactos deterministas. Verificaciones independientes de soporte/etiquetas, escalas, métricas/IC, máscaras/alturas y avisos; comparten ingestión y no certifican exactitud meteorológica.
