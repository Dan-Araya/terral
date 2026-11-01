# Protocolo previo: evaluación causal de avisos v1

Guardado el 08/10/2026, después de comprobar los dos resultados denunciados y antes de recalcular las políticas v1. Auditoría descriptiva, sin selección de umbral ganador, entrenamiento, recalibración ni modificación de predicciones, objetivos o catálogo. Rejilla original p≥{0,001;0,003;0,01;0,03;0,1;0,3;0,5}, regla nativa como complemento, y referencia `siempre` que emite en cada instante con predicción archivada evaluable. Bloques 2018–2019, 2020–2021 y 2022–2023 separados. Horas del reloj registrado, sin zona confirmada; disponibilidad inmediata supuesta, todavía sin validar latencia.

## Entradas cerradas y preservación

Predicciones v0 de validación 2018–2023; documentos, scripts y tablas de v0 como auditoría; `diagnostico_2013_2023/tablas/estados_horarios.csv` (solo fecha, validez y estado) y `catalogo_provisional_v0/catalogo_referencia.csv` (fechas e IDs). Esos dos archivos contienen exclusivamente 2013–2023; validar todos sus límites antes de seleccionar 2018–2023. No abrir otros CSV observacionales, otros períodos, estaciones ni red. Leer tablas horarias de AP, Brier, PR y calibración solo para comprobar preservación y, en su caso, copiarlas byte a byte. Inventariar hashes de todos los archivos de v0, fuentes usadas y protocolo antes/después; no ejecutar ni importar sus scripts, pues importar `ejecutar.py` puede crear directorios en v0.

## Pronóstico y disponibilidad archivada

Pronóstico horario: cada fila original aporta probabilidad, objetivo binario e intervalo (t,t+h]. Política usa exclusivamente t, h, probabilidad (o bit de regla), existencia del registro recibido en t y estado observacional actual. Nunca consulta objetivo, lista de futuros inicios, observaciones posteriores ni motivos futuros de exclusión para decidir avisos. Un objetivo futuro es solo información de evaluación posterior.

Limitación fundamental: el conjunto de filas de v0 ya fue filtrado retrospectivamente por desconocidas futuras y bordes de validación. La causalidad del motor se garantiza **condicional al flujo archivado disponible**, no se afirma que su máscara de disponibilidad haya sido obtenida causalmente en vivo. Las filas ausentes se tratan como `sin_pronostico_archivado`, no como probabilidades cero. Los motivos retrospectivos de v0 se añaden al informe de disponibilidad después de simular; no gobiernan cierres o renovaciones. No reconstruir las probabilidades omitidas. Distinguir falta observacional actual, falta de pronóstico y tramo activo.

## Política persistente causal

- En cada t con fila disponible y sin tramo activo, emitir aviso si supera o iguala umbral; bajo umbral no emitir un nuevo aviso y no revocar uno anterior.
- Aviso válido únicamente para (t,t+h], con vencimiento t+h y sin extensión por observar posteriormente un evento. Se conserva cada renovación y su vencimiento propio.
- Para medir duración, el estado activo ocupa [t,t+h): h horas del reloj. El inicio exactamente en t+h pertenece al intervalo objetivo anterior; a ese instante, sin renovación, el aviso vence. No confundir el punto extremo (duración cero) con una hora adicional de alerta.
- Avisos con intervalos de duración solapados o adyacentes mantienen el mismo episodio; renovación en el instante exacto del vencimiento mantiene continuidad sin hueco. Si ya hubo un lapso positivo tras el vencimiento, un nuevo aviso reactiva otro episodio.
- El episodio cierra en el último vencimiento vigente, aunque haya llegado un inicio antes. Observar tramo activo impide nuevos pronósticos, pero no revoca avisos previos ni altera sus vencimientos.
- Indisponibilidad no permite nuevas emisiones; registrar si la alerta sigue vigente o vence. No cerrar inmediatamente por un hueco ni rellenarlo, y no prolongar sin renovación. El bit de calidad no equivale a negativo.
- Simular cada bloque desde estado apagado, sin transferir alertas entre modelos, horizontes o bloques. Medir solo [primera marca del bloque, última marca del bloque): la última marca se conserva con peso de duración cero, sin extrapolar más allá del período permitido.
- El motor devuelve historial causal (emisión/renovación, vigencia, cierre y reactivación). La correspondencia con futuros eventos se añade después, sin alterar ese historial.

## Detección y anticipación

Inicio evaluable: primera marca v0 con hora anterior evaluable no_cumple y al menos una emisión archivada cuya ventana lo contiene. Por política, inicio detectado si existe al menos un aviso emitido con t<inicio≤t+h. Contar cada inicio una sola vez; un aviso puede contener varios inicios próximos (su objetivo horario sigue siendo binario) y un episodio puede corresponder a varios inicios. No imponer un límite de un evento por episodio que oculte detecciones.

Vincular cada inicio a la emisión válida más temprana (máxima anticipación real dentro de h), conservar las demás emisiones válidas, último aviso válido, número de emisiones y episodio. Anticipación = inicio−emisión válida, nunca inicio−activación persistente. Conservar además activación del episodio y edad de alerta al inicio; clasificar `activacion_dentro_h` cuando inicio−activación≤h, y `ya_activa_antes_h` en otro caso. La segunda no recibe el mismo significado de selectividad que la primera. Inicios sin oportunidad y omitidos separados.

Precisión horaria = emisiones con aviso y objetivo=1 / emisiones con aviso; recall horario = emisiones positivas con aviso / todas las emisiones positivas. No equiparar positivos horarios con inicios únicos. Precisión descriptiva por episodios = episodios con alguna correspondencia / todos los episodios, siempre acompañada de duración y ocupación; no convertirla en precisión del pronóstico. Episodios sin correspondencia se cuentan sin aplicar penalizaciones por longitud.

## Carga y denominadores

Grilla horaria completa de cada validación; cada marca t salvo la final representa [t,t+1) y pesa una hora. Evaluable para pronóstico = existe fila v0, común a los modelos; observación conocida en t = estado no desconocido (incluye activo); desconocida = estado no_evaluable. Reportar ambos denominadores y horas totales de reloj. Por cada modelo/h/bloque/umbral y agregados ALL y DJF/MAM/JJA/SON: emisiones, positivos, precisión/recall horarios, inicios evaluables/detectados/omitidos, anticipación, horas bajo alerta totales, evaluables y desconocidas, porcentajes de ocupación en ambos denominadores, episodios y duraciones media/mediana/p95/máxima, >h, ≥24 h y ≥168 h (descriptores, no penalizaciones), episodios sin correspondencia y edad de alerta.

Carga sin inicio: en cada marca activa t, examinar posteriormente el intervalo restante (t, último_vencimiento_vigente] de los avisos activos. Clasificar `con_inicio_evaluable`, `sin_inicio` o `indeterminada` si contiene desconocidas o inicios sin oportunidad evaluable. Una desconocida no se vuelve falsa alarma; la clasificación indeterminada tiene prioridad. La clase sin_inicio requiere un intervalo completamente conocido y sin inicio evaluable. Medir horas en cada clase sobre la grilla, por separado para tiempo total y emisiones evaluables, reconciliando con todas las horas de alerta. Es una evaluación del tiempo consumido por avisos vigentes y no una decisión retrospectiva.

Como complemento literal de horizonte, también clasificar tiempo activo por (t,t+h] contado desde la hora actual, sin llamarlo nuevo pronóstico: este intervalo puede exceder la vigencia restante o el bloque, caso externo/ desconocido se marca indeterminado. Reportarlo separado para no atribuir una renovación inexistente. No usar estos diagnósticos para mover comienzo/fin de episodios.

## Verificación e incertidumbre

Verificar los dos resultados v0 y reconstruir sus grupos desde las filas congeladas; guardar duración y primera emisión de cada uno. Preservar hashes de predicciones y todas las métricas originales. Casos sintéticos con fechas dentro del período: avisos continuos por semanas, aviso aislado acertado/falso, renovaciones solapadas y adyacentes, inicio posterior a vencimiento, indisponibilidad (sin renovación, sin negativo), varios inicios próximos, aviso durante tramo activo rechazado. Verificar invariancia del historial prefijo al modificar todo el futuro y etiquetas; unicidad de eventos y reconciliación entre intervalos, grilla y tablas.

No producir intervalos de confianza ingenuos por horas independientes. Esta auditoría reporta medidas descriptivas exactas de seis años; incertidumbre inferencial de nuevas métricas de episodios largos queda limitada por dependencia y pocas validaciones. Los intervalos v0 de AP/Brier siguen referidos al pronóstico; los de precisión por grupos y falsas alarmas/grupos no avalan carga temporal v1. No escoger política por estos resultados.

## Salidas

En `evaluacion_avisos_v1/`: protocolo, scripts sin rutinas de ajuste, registro previo, manifiestos, comprobaciones y casos sintéticos, historial completo horario (pronóstico/indisponibilidad/estado de alerta), emisiones y renovaciones con vencimientos propios, cierres y episodios, correspondencia aviso–inicio completa e inicio único, auditoría de grupos v0, métricas por bloque/estación/agregadas, tablas de exposición y motivos de ausencia, gráficos de recall frente a ocupación/carga, duraciones y ejemplo de cadena prolongada, informe. V0 permanece intacto. Ninguna alerta se despliega.
