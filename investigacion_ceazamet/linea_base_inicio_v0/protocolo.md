# Protocolo previo: línea base de inicio v0

Fijado el 08/10/2026 antes de entrenar o inspeccionar desempeño. No se seleccionarán configuraciones por resultados de validación. Cambios posteriores solo corrigen errores de implementación y se registran. Alcance exclusivo: Vicuña–INIA, reloj registrado sin zona confirmada, 01/01/2013 00:00–31/12/2023 23:00. Sin red, otras estaciones, presión, viento de 5 m ni período reservado. Objetivo: anticipar primera marca de cumplimiento del criterio histórico, no validar el inicio físico de terral.

## Fuentes y etiquetas

Lista cerrada: once `historico_inia/derivados/observaciones_AAAA.csv`, AAAA=2013,…,2023, y `catalogo_provisional_v0/catalogo_referencia.csv`. Se leen únicamente columnas temporales y las cuatro variables autorizadas; los archivos anuales contienen también otras variables, que no se incorporan. Se registran hashes antes/después. Documentos de contexto: `modelo_predictivo_terral.md`, `hoja_de_ruta_terral.md`, informes del diagnóstico 2013–2023 y catálogo v0. No se reutilizan cuantiles o referencias exploratorias calculadas sobre toda la muestra. No se modifica fuente, umbral o catálogo.

Validez heredada: promedio finito, porcentaje>0, prom_utilizable_revision=1; HR en [0,100], viento≥0, dirección en [0,360]. Reconciliar v0 con T>11, HR<30, viento>2, dirección inclusiva [0,180]; 360 no cumple el sector. Estados separados cumple/no_cumple/desconocido. Inicio conocido exige primera marca v0 y marca inmediatamente anterior evaluable no_cumple. Emisiones solo cuando t es no_cumple. Para h=1,3, y indica inicio conocido en (t,t+h]. Excluir cualquier desconocida del objetivo, inicio no conocido dentro del objetivo o fin fuera del período: nunca imputar etiqueta negativa.

## Predictores y faltantes

Disponibilidad inmediata de promedios en t como supuesto: latencia y semántica de agregación desconocidas; anticipación retrospectiva potencialmente optimista. Horizontes en horas del reloj registrado, sin UTC ni conversión civil.

Ventana estricta completa [t−6,t], siete marcas con cuatro variables válidas; excluir si alguna falta, sin relleno ni interpolación. Las tres referencias se comparan sobre exactamente las mismas emisiones. Se distingue pérdida por ventana de pérdida por objetivo. Dirección mediante seno/coseno, incluso 360 equivalente a 0 como predictor circular, sin cambiar etiqueta.

Logística: 35 columnas fijas. Cinco valores actuales (T, HR, V, seno D, coseno D); los cinco a t−1 y t−3 y diferencias actual−anterior a cada retraso (20); cinco medias en [t−6,t−1] y máximo V en esa misma ventana (6); seno/coseno de hora/24 y (día_del_año−1)/365,25 (4). Sin interacciones, selección ni búsqueda. Escala media/desviación poblacional solo entrenamiento (constantes: escala 1). Sin imputación ni pesos de clase. Minimizar suma de pérdidas logísticas + 0,5 suma beta², intercepto sin penalizar (C=1). Optimización L-BFGS, tolerancia gradiente 1e−6, hasta 1000 iteraciones. No calibración posterior.

## Comparaciones fijas

1. Frecuencia del objetivo h por mes×hora, solo emisiones elegibles de entrenamiento. Para n<100, usar frecuencia de hora suavizada con 200 pseudocasos de prevalencia global. Para n≥100, suavizar mes×hora con 200 pseudocasos de esa referencia horaria. Sin consulta de validación.
2. Regla precursora: D∈[0,180], T>10 °C, HR<40%, V>1 m/s, ΔT1>0, ΔHR1<0 y ΔV1>0, simultáneos. Es un precursor hipotético fijado por firma cálida/seca/ventosa, no una nueva etiqueta. Aviso nativo cuando regla=1. Para PR/Brier/calibración asignar probabilidad a cada estado binario con 20 pseudocasos de prevalencia global de entrenamiento; no ajustar sus condiciones.
3. Logística regularizada anterior, separada por h y bloque. Sin configuración que necesite selección interna.

## Particiones y fronteras

Validación expansiva de desarrollo: 2013–2017→2018–2019; 2013–2019→2020–2021; 2013–2021→2022–2023. Cada soporte [t−6,t+h] debe estar entero dentro de su bloque de entrenamiento/validación; así excluir primeras seis emisiones del bloque y últimas h. Para cada frontera, excluir además cualquier soporte que toque un tramo v0 que cruce esa frontera (ambos lados del tramo completo). Documentar todos los conteos y filas de exclusión con motivos no excluyentes y un motivo primario ordenado. No son pruebas finales independientes. Reutilización de validaciones anteriores como entrenamiento posterior es propia del diseño expansivo, no autoriza optimización retrospectiva.

## Avisos y vinculación

Para cada modelo/h/bloque, rejilla fija p≥{0,001;0,003;0,01;0,03;0,1;0,3;0,5}, más regla nativa. No declarar ganador operacional. Agrupar exclusivamente avisos de emisiones consecutivas con separación exacta de una hora; una hora sin aviso, excluida, desconocida o activa rompe el grupo. No unir a través de huecos. Un grupo acierta si alguna de sus emisiones tiene un inicio conocido en (t,t+h]. Vincular cronológicamente al primer inicio aún no vinculado; máximo un grupo por inicio y un inicio por grupo. Avisos adicionales del mismo inicio son redundantes sin nuevo acierto y se contabilizan separadamente de falsas alarmas. Falsa alarma: ninguna emisión del grupo anticipa inicio. Anticipación del acierto = inicio−primera emisión del grupo que efectivamente lo anticipa (no la primera de una cadena arbitrariamente larga); informar también comienzo/fin de grupo. Intervalo de alerta no prolonga h desde una emisión sin renovarla.

Inicio evaluable por h/bloque: al menos una emisión elegible que lo pueda anticipar. Denominador incluye detectados y omitidos, y separa inicios sin oportunidad evaluable. Precisión de avisos = grupos acertados / todos los grupos (redundantes incluidos en denominador). Mes evaluable equivalente = emisiones elegibles / (365,25×24/12); falsas alarmas/mes usa exposición real de emisiones, y se informa número de meses calendario con alguna emisión. Avisos y exposición por estación se asignan por emisión inicial de grupo; inicios detectados/omitidos por época de inicio. Si un acierto cruza estación se conserva esa distinción; no se atribuye el mismo tramo a dos aciertos.

## Métricas e incertidumbre

PR completa con empates agrupados, average precision (AP, suma escalonada), prevalencia; Brier y referencia constante aprendida solo en entrenamiento; Brier skill frente a frecuencia mes×hora. Calibración descriptiva en intervalos fijos [0,0,001,0,003,0,01,0,03,0,1,0,3,0,5,1], con n, promedio previsto y observado. No usarla para recalibrar. Desgloses ALL/DJF/MAM/JJA/SON y por bloque, con denominadores horarios, positivos, inicios, grupos, exposición y anticipación. AP indefinida sin positivos.

Bootstrap pareado de bloques móviles de tres meses dentro de cada validación bienal, 300 réplicas, semilla 20132023. Muestrear ocho bloques trimestrales (inicio aleatorio entre 22 posibles, sin envoltura) para cada validación y juntar los tres bloques cronológicos; calcular AP, Brier y diferencias con frecuencia. Respetar horas contiguas dentro del bloque; meses se pueden repetir. Para avisos se remuestrean conteos ya vinculados, no se reagrupan horas artificialmente; asignar aciertos/omitidos a mes del inicio, grupos/falsas alarmas a mes del aviso. Intervalos percentiles 2,5–97,5%. Es una aproximación condicional a modelos entrenados y catálogo, no incertidumbre de etiquetas ni de entrenamiento; pocas validaciones y eventos limitan fiabilidad. Mostrar intervalos solo agregados y documentar limitación en estaciones sin inicios.

## Controles y entregables

Protocolo inmutable y hash previo al primer ajuste; scripts, versiones, manifiesto cerrado; predicciones (t, h, y, modelo, bloque, inicio asociado), exclusiones globales y por partición, referencias y parámetros aprendidos, PR/calibración, métricas de horas y avisos, correspondencia y estado de cada inicio, intervalos, PNG e informe. Controles de límites temporales, validez, reconciliación de 156 tramos/867 horas, inicio previo, soporte sin cruces, hashes inalterados, mismo conjunto comparativo, probabilidades finitas, unicidad de aciertos. Comprobar también invariancia de predictores al alterar todas las observaciones posteriores a un t de prueba. Sin alertas desplegadas.
