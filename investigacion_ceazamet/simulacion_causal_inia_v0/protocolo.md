# Protocolo previo — simulación temporal causal INIA v0

Fijado el 08/10/2026 antes de calcular resultados de esta reconstrucción. Solo Vicuña–INIA y observaciones anuales 2013–2023, catálogo v0, ajustes y referencias congelados v0, predicciones v0 y tablas v1. Sin red, otras estaciones ni lectura de observaciones, estadísticas o gráficos desde 2024. No ajustar modelos, probabilidades, umbrales ni catálogo. Preservar hashes de fuentes y resultados anteriores. Las fechas son el reloj registrado sin zona confirmada.

## Emisión y retrasos

Recorrer todas las marcas de los tres bloques originales 2018–2019, 2020–2021 y 2022–2023. En hora real t, retraso hipotético d=0,1,2: ancla a=t−d. La marca de corte es la última marca horaria potencialmente disponible, no la última marca válida arrastrada a través de un hueco. Exigir cuatro variables válidas en siete marcas [a−6,a] y estado actual conocido no_cumple en a. Si la marca a falta, no hay emisión ni renovación; no interpolar ni reutilizar una marca antigua. La detección de tramo activo depende exclusivamente del criterio v0 en a, sin conocer su duración futura.

Construcción exacta de los 35 predictores v0, incluidos calendarios anclados en a. Aplicar coeficientes, escala, intercepto, probabilidades binarias de regla y tabla mes×hora archivados del bloque/horizonte. Referencia frecuencia también anclada en a. No ejecutar/importar código de entrenamiento: extraer únicamente la función pura `features` como texto auditado. Tolerancia de reconciliación con CSV v0: error absoluto ≤1e−9 (CSV usa diez cifras significativas); comparar todas las filas archivadas, reglas e IDs/objetivos.

Reiniciar cada bloque sin historia previa ni alerta transferida. Ventana íntegramente dentro del bloque: primeras 6+d marcas no pueden emitir; tampoco usar observaciones del bloque anterior aunque sean de años autorizados. No purgar por fin futuro, desconocidas futuras ni tramo que empiece después de t. Mantener emisiones hasta la última marca. No ampliar reloj ni observaciones más allá del bloque.

Los retrasos son pruebas de estrés, no latencias observadas de CEAZA. Modelo entrenado con disponibilidad inmediata: calibración no transportable automáticamente. Avisos durante un tramo realmente activo pueden aparecer por retraso y se contabilizan; nunca asignar detección ni anticipación a una emisión t≥inicio.

## Evaluación posterior

Generar primero probabilidades y motor de alertas sin objetivos ni catálogo como entrada. Después evaluar (t,t+h]: fuera_de_alcance si supera la última marca del bloque; desconocido si contiene cualquier estado desconocido o comienzo de tramo sin previo no_cumple conocido; positivo si contiene inicio conocido; negativo si es completamente conocido sin inicio. Prioridad externa > desconocido > positivo/negativo. Conservar todas las emisiones, incluso sin resultado. Inicio con oportunidad: al menos una emisión causal con objetivo evaluable que lo contenga; reportar además catálogo completo y sin oportunidad.

## Alertas y carga

Reutilizar literalmente funciones puras engine, classification y event_links de v1, copiadas sin importar ni ejecutar el programa. Rejilla p≥{0,001;0,003;0,01;0,03;0,1;0,3;0,5}, regla nativa y siempre en toda emisión causal posible. Aviso (t,t+h], duración [t,t+h), renovaciones adyacentes/solapadas en un episodio; no revocar por bajo umbral, inicio ni hueco; no renovar sin ventana disponible. Vencimientos pueden superar bloque: conservar vencimiento real pero duración recortada a [primera,última marca), con última celda peso cero. No transferir a otro bloque.

Correspondencias y detección posteriores: t<inicio≤t+h, intervalo objetivo evaluable. Conservar todas las parejas y una primaria más temprana por inicio, edad desde activación y anticipación real de emisión. Precisión por emisión solo entre avisos con objetivo positivo/negativo; reportar denominador total, desconocidos y externos. Precisión con todos los avisos se presenta solo como límite inferior, no imputación negativa. No eliminar avisos sin etiqueta.

Carga restante en (t,vencimiento vigente]: clases sin inicio, con inicio o indeterminada; última incluye exterior, desconocidas e inicios sin oportunidad. Separar tiempo indeterminado por pérdida observacional y por frontera; reportar también observación actual desconocida. Ocupación en todo reloj, observación conocida, emisión disponible y emisión con objetivo evaluable; explicitar denominadores. Duraciones completas observadas de episodios por activación, con censura al borde. Detección/inicios por época de inicio y horas por época de cada celda, episodios por activación.

## Métricas, controles y comparación

Todos los modelos, horizontes, retrasos y políticas por bloque, agregado y DJF/MAM/JJA/SON, sin ganador. AP/Brier/calibración descriptivos en objetivos evaluables; comparación pareada en soporte común de retrasos y comparación bruta operacional con v1. No trasladar intervalos de confianza v0 a las nuevas poblaciones; no intervalos por horas independientes.

Controles reproducibles: reconciliación completa de probabilidades v0; hashes antes/después; criterio/catalogo; modificación y eliminación de observaciones posteriores a cortes, incluido antes de hueco, recuperación y comienzo de evento, comparando disponibilidad, predictores, probabilidades e historial anterior para d=0,1,2; invariancia a etiquetas; pruebas de hueco y recuperación a siete marcas completas, vigencia exacta, renovación adyacente, frontera y avisos después del inicio. Verificación independiente de la unión de intervalos y etiquetas desde archivos entregados.

Salidas: scripts, protocolo y registro previo, manifiestos, disponibilidad completa, predicciones sin filtrar, objetivos posteriores, historial/transiciones/emisiones, episodios, inicios y parejas, métricas, comparaciones e informe. No desplegar alertas.
