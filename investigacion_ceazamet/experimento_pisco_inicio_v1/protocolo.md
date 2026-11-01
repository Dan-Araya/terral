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
