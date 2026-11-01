# Modelos y evaluación

El objetivo es anticipar el **inicio de condiciones identificadas mediante un criterio histórico**, no estimar la intensidad o duración del terral. Los umbrales de referencia son temperatura superior a 11 °C, humedad relativa inferior al 30 %, viento superior a 2 m/s y dirección entre 0° y 180° (procedencia oriental). Fuente: [Montes et al. (2016)](https://doi.org/10.1175/JAMC-D-15-0275.1).

Los seis modelos publicados son regresiones logísticas con regularización L2. La configuración D utiliza INIA Vicuña con su presión propia y Pisco Elqui. Cada horizonte tiene su propio modelo; por eso sus probabilidades no tienen que aumentar al ampliar la ventana.

Una ventana de seis horas significa «inicio dentro de las seis horas siguientes a la referencia del modelo», no «inicio exactamente seis horas después». La política experimental actual trabaja con etiquetas nominales: no afirma que esa referencia sea el instante físico de consulta.

Entrenamiento: 2013–2021. Evaluación final de estos modelos: 2022–2023, 17.350 oportunidades por horizonte y 21 inicios. Las comparaciones exploratorias anteriores utilizaron otras particiones y soportes; sus cifras no deben mezclarse con esta evaluación.

| Ventana | Reducción relativa de Brier frente a referencia fija | Episodios anticipados¹ | Anticipación mediana² | Falsas alarmas/mes evaluable¹ |
| --- | ---: | ---: | ---: | ---: |
| 1 h | 17,9 % | 14 de 21 (67 %) | 1 h | 2,61 |
| 3 h | 20,2 % | 16 de 21 (76 %) | 3 h | 2,61 |
| 6 h | 20,3 % | 16 de 21 (76 %) | 5 h | 1,56 |
| 8 h | 18,8 % | 16 de 21 (76 %) | 6,5 h | 2,32 |
| 12 h | 15,6 % | 14 de 21 (67 %) | 5,5 h | 1,22 |
| 24 h | 18,4 % | 18 de 21 (86 %) | 8 h | 2,19 |

¹ Umbrales seleccionados durante entrenamiento con tolerancia de cuatro falsas alarmas mensuales. Esa tolerancia no garantiza la carga observada o futura. ² Entre los episodios detectados.

El Brier mide error de probabilidades, no porcentaje de episodios acertados. La reducción se calcula como `100 × (Brier_referencia − Brier_modelo) / Brier_referencia`. La referencia se ajusta a la temporalidad; 21 episodios no equivalen a 21 horas positivas para todas las ventanas. Un mismo inicio puede hacer positivas varias oportunidades anteriores.

Las métricas probabilísticas agregadas, sin observaciones individuales, están en [resultados_evaluacion.json](../aplicacion_terral/g3/resultados_evaluacion.json). Los resultados sintéticos de la demo no deben utilizarse para medir capacidad predictiva.

## Trabajo pendiente

- Ampliar la evaluación independiente con datos posteriores a 2023, siguiendo un protocolo previo.
- Evaluar la disponibilidad real de cada entrada al emitir, incluidas revisiones y demoras de publicación.
- Confirmar zona horaria, posición de los intervalos y continuidad instrumental de las estaciones.
- Comparar estaciones sobre el mismo soporte y estudiar la utilidad de diferentes anticipaciones y cargas de avisos.
- Investigar intensidad, duración y hora aproximada de inicio como objetivos adicionales.

Las exploraciones de horizontes acumulados hasta 72 horas con Pisco no acreditan una anticipación efectiva de 72 horas ni un límite físico del fenómeno. El observatorio publicado utiliza los seis horizontes indicados arriba.
