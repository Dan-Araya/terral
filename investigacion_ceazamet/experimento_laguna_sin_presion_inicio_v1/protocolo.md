# Protocolo previo: La Laguna–Elqui SIN presión e INIA, v1

Fecha: 25/10/2026. Experimento de desarrollo retrospectivo, exclusivamente 2013-01-01 00:00 a 2023-12-31 23:00 del reloj registrado. Sin red, descarga, despliegue, búsqueda de desfases, selección de estaciones, variables o hiperparámetros. Los resultados no validan meteorológicamente el terral. No se elige una configuración ganadora después de validar.

Se heredan literalmente objetivo, catálogo provisional v0, validez básica INIA, ventana estricta [t−6,t], exclusiones de objetivos desconocidos, emisión no_cumple, fronteras y tramos que cruzan fronteras del protocolo de linea_base_inicio_v0. Se reconcilian 156 tramos y 867 horas; y indica algún inicio conocido en (t,t+h], h=1,3. Se conservan todos los identificadores si hay más de un inicio. Etiqueta no equivale al inicio físico del terral.

SUPUESTOS PROVISIONALES: promedio marcado t disponible inmediatamente en t; coincidencia de marcas de ambas estaciones representa la misma hora del reloj registrado. Zona, posición del intervalo, latencia y alineación física no confirmadas. No se infieren por desempeño ni correlación. Presión se usa como variable local, sin gradientes ni reducción altimétrica.

## Fuentes cerradas y calidad

Once CSV anuales historico_inia/derivados/observaciones_2013.csv,…,observaciones_2023.csv; catalogo_provisional_v0/catalogo_referencia.csv; estaciones_complementarias/la_laguna_elqui/derivados/horarias.csv e integridad.json; configuración local y documentos/código requeridos. No se abren XLS originales (algunos bloques originales incluyen bordes fuera del alcance), otros años ni resultados globales. Hash de toda fuente leída antes/después; La Laguna se coteja además con el hash de integridad auditada. Fechas fuera de alcance abortan.

INIA: promedio finito, 0<%Datos≤100, prom_utilizable_revision=1, HR [0,100], viento≥0, dirección [0,360], una fila por hora/variable. Presión propia con la misma máscara auditada INIA, sin nueva depuración. Alturas según CSV; persiste discrepancia documental T/HR 1.5 vs 2 m. La Laguna: códigos LAGELTA T 1.5 m, LAGELHR HR 1.5 m, LAGELVV10 V 10 m, LAGELDV10 D 10 m verificados contra configuración y filas. Se conserva máscara utilizable_revision auditada (incluye min/prom/max/%Datos, rangos, orden excepto dirección); duplicados excluidos. Ceros conservados. Sin imputación, interpolación, suavizado ni exclusión adicional por saltos/repeticiones.

## Brazos y columnas

A: 35 predictores exactos de la logística de línea base. B: A + 6 de presión propia. C: A + 31 de La Laguna. D: B + 31 de La Laguna. Total 35/41/66/72. El listado completo se fija en predictores.json antes del primer ajuste y se verifica en ejecución.

Cada escalar añadido (presión INIA y T, HR, V, seno D, coseno D de La Laguna) aporta actual, lag1, delta1, lag3, delta3 y media de [t−6,t−1]. La Laguna añade máximo de los seis promedios horarios de V en [t−6,t−1], como INIA; no es ráfaga ni máximo instrumental del CSV. Dirección solo seno/coseno y sus derivados. Calendario una sola vez, heredado de A.

Comparación principal: intersección estricta de todas las variables en las siete marcas [t−6,t], misma etiqueta y mismas emisiones de entrenamiento y validación para A/B/C/D. Se reportan soportes potenciales por brazo y pérdidas de soporte sin entrenar/evaluar sobre esos soportes distintos. Motivos adicionales no excluyentes y primarios; se preserva detalle de exclusiones base.

Logística por brazo/horizonte/partición. Escala poblacional aprendida solo de entrenamiento, constantes escala 1. Sin pesos de clase. Suma de log-loss + 0.5 suma beta², intercepto libre, C=1, L-BFGS-B gtol=1e−6, ftol=1e−12, maxiter=1000, inicial intercepto logit prevalencia y coeficientes 0. Misma configuración del código base, sin búsqueda ni calibración posterior.

## Validación y evaluación

2013–2017→2018–2019; 2013–2019→2020–2021; 2013–2021→2022–2023. Soportes [t−6,t+h] enteros en cada bloque; purga adicional de tramos completos cruzando frontera. Son validaciones de desarrollo reutilizadas, no prueba final independiente.

AP con empates agrupados, curvas PR, Brier y calibración en bordes [0,.001,.003,.01,.03,.1,.3,.5,1]. Referencias constante y mes×hora aprendidas en entrenamiento común como diagnóstico, no brazos adicionales. Avisos exactamente según función notices de línea base: p≥{.001,.003,.01,.03,.1,.3,.5}, grupos consecutivos a una hora, correspondencia cronológica uno a uno, redundantes separados; anticipación desde primera emisión que anticipa efectivamente. Inicios evaluables exigen oportunidad en soporte común; exposición en meses equivalentes, desglose por partición y estación del año. No se selecciona umbral.

Contrastes firmados B−A, C−A, D−B para AP, Brier y métricas de avisos en cada umbral, por partición y conjunto agregado. AP mayor/Brier menor es favorable. Bootstrap pareado 300 réplicas semilla 20132023, ocho bloques móviles de tres meses entre 22 inicios dentro de cada bienio; las mismas muestras para todos los brazos/horizontes. Guardar multiplicidades. Intervalos percentiles 2.5–97.5% solo agregados. Avisos remuestrean registros mensuales ya vinculados, sin reagrupar horas artificiales; se preserva asignación mes de aviso/inicio. Extensión: también diferencias de conteos y anticipación media; mediana descriptiva, sin intervalo bootstrap. Limitaciones: condicional a ajustes y catálogo, dependencia temporal aproximada, pocos inicios, ponderación no uniforme de extremos y sin incertidumbre de entrenamiento/etiquetas.

Interpretación fijada: mejora consistente requiere deltas AP>0 y Brier<0 en los tres bloques y ambos IC agregados favorables; empeoramiento consistente, lo contrario. Si ambos IC agregados incluyen cero: ausencia de evidencia de mejora; en los demás casos, resultado incierto, detallando signos, magnitudes y compromisos de avisos. No basta una métrica o partición. No implica utilidad operacional, ni se selecciona configuración.

## Revisión metodológica antes de entrenar

No se detecta contradicción que impida esta comparación provisional. Diferencias explícitas: la máscara auditada La Laguna exige todos los estadísticos mientras INIA hereda su promedio utilizable; no se uniforman silenciosamente. La línea base no comprueba explícitamente %Datos≤100 en ingest(), pero la auditoría sí: se comprueba que no cambia ninguna observación básica. El código usa ftol=1e−12 además de gtol; se conserva. «Máximo horario» en la extensión significa máximo de promedios horarios previos conforme al código base. El informe documental de octubre no entrenaba en aquella revisión; este nuevo trabajo independiente autoriza el entrenamiento bajo sus límites abiertos. No se interpreta como resolución de dudas instrumentales.

Controles: límites, hashes, igualdad exacta soporte/etiquetas, columnas, calidad, fronteras entrenamiento/validación, objetivos reconstruidos, finitud probabilidades, denominadores horarios/calibración/eventos, parámetros y escala solo entrenamiento, reconstrucción puntual independiente de features/probabilidades e invariancia al alterar datos posteriores a múltiples emisiones. Registrar hash/fecha de protocolo, columnas y código antes del primer ajuste. Correcciones de implementación registradas separadamente; no cambios por desempeño.

## Hipótesis previa del usuario y exclusión completa de presión complementaria

«La Laguna está en la misma cuenca que Llanos de Huanta, mucho más al este, y podría registrar condiciones precursoras útiles para anticipar el criterio histórico en INIA.» Es una hipótesis física aportada por el usuario antes del entrenamiento, no un mecanismo demostrado ni garantía de mejora.

Solo LAGELTA y LAGELHR a 1,5 m; LAGELVV10 y LAGELDV10 a 10 m. No convertir viento a 2 m, mezclar alturas ni incorporar otros canales. La diferencia con el viento de Pisco y Huanta a 2 m se mantiene explícita. LAGELPA queda completamente fuera de predictores, transformaciones, elegibilidad, antecedentes, selección de horas y eventos. Su falta nunca elimina horas; no se corrige, imputa ni evalúa su contribución. El archivo fuente multicanal se hashea completo para integridad, pero solo se seleccionan las cuatro filas-sensor autorizadas para cualquier cálculo. No se abren XLS ni datos fuera de 2013–2023.

La ventana estricta exige siete marcas de INIA básica, su presión propia y solo las cuatro variables de La Laguna, para todos los brazos y ambos roles. Sin columnas ficticias, 31 columnas añadidas: cinco canales escalares (T, HR, V, seno D, coseno D) × seis transformaciones, más máximo de seis promedios horarios previos de viento. No es ráfaga. No se exige otra estación. Los 24 modelos se ajustan desde cero.

Se registrarán cobertura anual y huecos por cada uno de los cuatro sensores, efecto no excluyente y marginal sobre horas, positivos e inicios, distinguiendo afectados de completamente perdidos. Los entrenamientos expansivos se solapan y no se suman. Se verificará independencia respecto de presión complementaria por inspección del código, whitelist de canales y prueba contrafactual sintética de columna adicional de presión (sin usar mediciones de LAGELPA).

El usuario informa actualización automática horaria de todas las estaciones. Se mantienen las convenciones temporales anteriores, sin retrasos hipotéticos ni búsqueda de desfases. La actualización horaria no confirma zona histórica, posición/duración del intervalo, latencia histórica o coincidencia física de las marcas. Estas incertidumbres se documentan por separado.

Semilla bootstrap 20132023, optimización determinista. Protocolo, código, columnas, configuración y fuentes registrados antes del primer ajuste. Se repetirá completamente el ajuste y se compararán hashes de artefactos deterministas. No se comparará la superioridad frente a Pisco/Huanta sobre horas diferentes. Las conclusiones solo corresponden al criterio histórico 2013–2023; no demuestran mecanismo físico ni capacidad operacional.
