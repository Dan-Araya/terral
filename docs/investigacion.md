# Recorrido de la investigación

La aplicación publicada utiliza INIA Vicuña y Pisco Elqui. Antes de elegir esa configuración se exploraron otras estaciones, variables y horizontes. El código conserva la estructura de los experimentos originales; los datos y evidencias detalladas permanecen en el archivo de investigación.

| Carpeta dentro de `investigacion_ceazamet/` | Trabajo |
| --- | --- |
| `historico_inia/` | Transporte y gestión del histórico INIA |
| `estaciones_complementarias/` | Descarga secuencial y reanudable de las siete estaciones configuradas, 2013–2023 |
| `catalogo_provisional_v0/` | Construcción del criterio histórico de referencia |
| `linea_base_inicio_v0/` | Línea base predictiva de inicios |
| `simulacion_causal_inia_v0/` | Simulación de disponibilidad y avisos |
| `evaluacion_avisos_v1/` | Evaluación por episodios y falsas alarmas |
| `experimento_*_inicio_v1/` | Comparaciones independientes por estación y presión |
| `estudio_horizontes_inicio_v1/` | Ventanas 1, 3, 6, 8, 12 y 24 h; etapas Pisco, Huanta y La Laguna |
| `extension_horizontes_pisco_v1/` | Exploración de ventanas acumuladas y tramos hasta 72 h |

Se conservaron configuraciones y protocolos, junto con los scripts originales seleccionados. No todos son puntos de entrada: también hay verificadores y reparaciones documentales ligados a una ejecución particular. Las rutas de resultados y manifiestos requieren el archivo externo descrito en [Datos y reproducibilidad](datos.md). No se ejecutan al iniciar el panel o las pruebas públicas.

Las comparaciones se hicieron por estación y soporte. No corresponde ordenar sus resultados como si todos utilizaran los mismos episodios. Algarrobal no tiene cobertura en el período de desarrollo; Rivadavia dispone de un histórico más corto. La presión de La Laguna requiere aclaraciones instrumentales y no se incluyó en la aplicación actual.

El estudio utilizó NumPy, pandas, scikit-learn, SciPy y Matplotlib, además de los lectores XLS. Las versiones exactas y las huellas de las ejecuciones originales están en los manifiestos del archivo de investigación; no se promete equivalencia numérica al instalar versiones arbitrarias actuales. La inferencia publicada no necesita esas bibliotecas: utiliza coeficientes y escalas congelados con la biblioteca estándar de Python.
