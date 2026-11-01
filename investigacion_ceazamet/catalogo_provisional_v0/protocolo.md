# Protocolo v0 fijado antes de la ejecución

## Alcance y referencia

Solo se leen tablas de `diagnostico_2013_2023`; no se ejecuta ni modifica el diagnóstico. Lista cerrada en `construir.py`. Cada tabla temporal debe superar controles de 2013-01-01 00:00 a 2023-12-31 23:00 antes del cálculo. Las marcas no tienen zona confirmada. Identificador: `VCN-INIA-v0-AAAAMMDDTHHMM`, derivado de la primera marca, nunca del orden de filas. Una negativa o desconocida rompe el tramo. Se conservan los 156 tramos y 867 horas, los cuatro umbrales originales y los estados desconocidos. Las agrupaciones por días se copian separadamente.

## Banderas técnicas, sin exclusión ni reclasificación

- `corto`: 1–2 horas candidatas; desglose separado de 1 y 2 h.
- `sensible`: cambia pertenencia, primera/última marca o agrupación al comparar con cualquiera de las diez configuraciones ya ensayadas. Para cada configuración se enumeran tramos que solapan la referencia, sus límites y horas. La alternativa puente se compara por límites y no convierte su hora negativa en candidata. No se prueban configuraciones nuevas.
- `salto_previo`: al menos un salto de `saltos_revision.csv` en [primera−1 h, última+1 h], acotado al período. Se preserva variable, fecha y cambio; puede ser meteorológico.
- `direccion_ambigua`: al menos un ángulo fuera de [15,165], R circular entre horas del tramo <0,7, o cambio circular absoluto entre horas consecutivas del tramo ≥90°. R usa media no ponderada de senos/cosenos; estas reglas revisan la representación, no validan el flujo. El cálculo circular subhorario del exportador es desconocido para todos los tramos, y se registra como limitación general aparte.
- `proximo_hueco`: una marca no evaluable conjunta a distancia ≤24 h del intervalo candidato. Distancia en reloj registrado; registrar la menor y la fecha. Censura conserva la regla original: inmediatamente adyacente a desconocida o borde del período. Proximidad no implica censura.
- `calidad_fuente`: alguna de las cuatro variables durante el tramo con porcentaje <100, bandera de rango/orden o problema fuente distinto de lista vacía. La presión se audita aparte y no modifica el criterio.

## Posibles omisiones: procedimiento exploratorio pequeño

1. Usar cambios de exactamente 3 h de T, HR y viento a 2 m. Exigir cuatro marcas consecutivas con las cuatro variables válidas (sin atravesar huecos). Excluir ventanas de estas cuatro marcas que contengan alguna hora que cumple el original.
2. Calcular referencias por mes calendario y hora de llegada, agrupando todos los años 2013–2023: para cada variable, cuantiles lineales 0,10 y 0,90 de los cambios de 3 h con las cuatro marcas válidas; registrar n. Exigir n≥100. No ponderar ni rellenar grupos. Para el estado de llegada reutilizar las medianas mes×hora de `distribuciones.csv`, calculadas por variable válida en el diagnóstico, incluyendo candidatas y ordinarias.
3. Buscar simultáneamente dT≥max(2 °C,q90), dHR≤min(−10 puntos,q10), dV≥max(0,5 m/s,q90); además T llegada≥mediana, HR llegada≤mediana y V llegada≥mediana. No filtrar por dirección, mes u hora. Estas reglas seleccionan cambios inusuales para inspección, no terrales. Pueden seleccionar calentamiento solar o brisas ordinarias.
4. Conservar todas las llegadas elegibles en una tabla. Formar grupos de llegadas separadas ≤6 h solo para evitar revisar la misma transición muchas veces. Elegir la llegada central cronológica (índice floor((n−1)/2)) de cada grupo. No unir tramos del catálogo ni declarar duración física. Registrar cada condición original que falla en la llegada y en las cuatro marcas de cada caso.
5. Seleccionar hasta una llegada central por año×mes con orden SHA-256 de `terral-v0|id`; no usar magnitud. Guardar el conjunto completo de grupos y el subconjunto mensual. Todo cálculo es retrospectivo de auditoría; no produce etiquetas, objetivos ni predictores disponibles para entrenamiento. No ajustar reglas tras ver resultados.

## Selección para contraste y gráficos: máximo 30 ventanas

Cuotas: 11 referencias (una por año si hay), 8 referencias ambiguas (alguna bandera), 11 posibles omisiones (una por año si hay). Las dos categorías de referencia son disjuntas en la selección; referencia general puede también tener banderas, que se mantienen. Si una categoría no cubre cuota, no se rellena con otra. Primero referencias generales, luego ambiguas, luego omisiones. Dentro de cada categoría elegir iterativamente la ventana del año menos representado en esa categoría; desempatar por época menos representada en la selección global, luego SHA-256 `terral-v0|id`. Para referencia general y omisiones, máximo una por año. Épocas: DJF, MAM, JJA, SON según mes del reloj registrado. Descartar para selección (sin eliminar del catálogo) ventanas que solapen alguna ya seleccionada. No usar evidencia externa para alterar esta muestra.

Ventanas de 48 marcas: referencia [primera−9 h, primera+38 h], omisión [llegada−18 h, llegada+29 h]. En bordes desplazar para mantener 48 marcas dentro del período. Las de referencia incluyen todo tramo (máximo 29 h). Gráficos con valores horarios, sin suavizado ni imputación; líneas de T/HR/viento se cortan con NaN según validez por variable. Dirección solo puntos, no línea. Mostrar `prom` del viento y `max` publicado como series distintas. Ni uno ni otro es una ráfaga acreditada.

## Evidencia independiente

Buscar noticias y documentos de episodios de 2013–2023 con consultas fechadas y preferencia por archivos locales. Registrar consulta, alcance y resultado para las 30 ventanas; una búsqueda puede cubrir varias ventanas del mismo mes. Abrir únicamente piezas históricas pertinentes, nunca portales de datos o series globales. Separar fecha de publicación de fecha del episodio; precisar ubicación, independencia y resolución temporal. No asignar coincidencia horaria sin zona confirmada. Informes que identifican el episodio con los mismos umbrales de INIA son contexto dependiente. Noticias con daños/relatos locales pueden aportar evidencia de episodio regional, sin confirmar la hora INIA ni el mecanismo por sí solas. Ausencia de reporte no implica ausencia del fenómeno. No contactar a nadie.

El buscador puede devolver fragmentos ajenos al período pese a filtros. No abrir, conservar observaciones, extraer estadísticas ni usar esos resultados; registrar cualquier incidencia de alcance en el informe. No presentar la búsqueda como exhaustiva.
