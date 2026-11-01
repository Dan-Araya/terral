#!/usr/bin/env python3
"""Lectura de resultados cerrados: no ajusta ni elige variantes, métricas o umbrales."""
import os,sys,hashlib
os.environ['OPENBLAS_NUM_THREADS']='1'; sys.modules['numexpr']=None
from pathlib import Path
import pandas as pd
BASE=Path(__file__).resolve().parent; OUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else BASE
ci=pd.read_csv(OUT/'tablas/intervalos_pareados.csv'); rows=ci[ci.metrica.isin(['AP','Brier'])&ci.contraste.isin(['G-C','G-E','H-D','H-F'])]
text='''# Conclusiones de la combinación Pisco–Huanta

No se acredita mejora consistente de la combinación frente a cada estación individual en ninguno de los dos horizontes, con o sin presión propia. Esto no demuestra redundancia ni equivalencia: los intervalos permiten mejoras y empeoramientos de magnitud relevante.

A 3 horas, C−A, D−B, E−A, F−B, G−A y H−B cumplen mejora consistente de AP y Brier frente a INIA en el mismo soporte. Es decir, cada estación individual y la combinación mejoran frente a las referencias INIA correspondientes. Esa evidencia no basta para afirmar que combinarlas aporte información predictiva complementaria.

La AP agregada de G es 0.359535, frente a 0.351692 de C y 0.352296 de E. Para H es 0.368504, frente a 0.353256 de D y 0.363886 de F. AP no es porcentaje de aciertos. Se informan ambas estaciones como comparadores predefinidos, sin escoger retrospectivamente una sola.

En Brier agregado a 3 horas, añadir Huanta cuando está Pisco da diferencias favorables (G−C y H−D); añadir Pisco cuando está Huanta da diferencias desfavorables (G−E y H−F). Los ocho intervalos principales de AP/Brier a 3 horas incluyen cero. Además, los signos no son uniformes entre particiones: G−C tiene 2/3 particiones favorables en ambas métricas; G−E, 1/3 en AP y 0/3 en Brier; H−D, 2/3 en AP y 3/3 en Brier; H−F, 2/3 en ambas. Ninguno cumple la regla completa preregistrada.

A 1 hora, los cuatro contrastes principales tampoco cumplen mejora consistente. G−E presenta un empeoramiento de Brier en las tres particiones y un intervalo agregado completamente positivo; su intervalo de AP incluye cero. Por la regla conjunta original se clasifica como resultado incierto, sin afirmar empeoramiento consistente de ambas métricas. Los dos intervalos de G−C, H−D y H−F incluyen cero.

La inclusión de presión propia no cambia la conclusión sobre complementariedad: ni G−C/G−E sin presión, ni H−D/H−F con presión satisfacen conjuntamente el criterio. B−A tampoco demuestra mejora consistente de presión propia en ninguno de los dos horizontes. No se añade un contraste H−G fuera del plan ni se selecciona una configuración.

## Todos los contrastes principales: estimaciones e intervalos

ΔAP>0 y ΔBrier<0 son favorables. IC percentiles del 95% por contraste; múltiples comparaciones sin garantía conjunta del 95%.

| h | Contraste | Métrica | Diferencia | IC 95% |
| --- | --- | --- | --- | --- |
'''
for r in rows.itertuples(): text+=f'| {r.horizonte_h} | {r.contraste} | {r.metrica} | {r.estimacion:.8g} | [{r.p025:.8g}, {r.p975:.8g}] |\n'
text+='''
## Soporte y límites

Validación común: 49.771 horas, 79 positivos y 79 inicios a 1 hora; 49.759 horas, 233 positivos y 79 inicios a 3 horas. Se conservan todos los positivos e inicios de validación de los experimentos individuales. Respecto a Pisco se pierden 2.140/2.138 horas de validación (h=1/3); respecto a Huanta, 8 en cada horizonte. En entrenamiento se pierden 17 inicios respecto a Pisco en cada partición expansiva, sin sumarlos porque se solapan; a 1 hora son 17 positivos y a 3 horas 51. Respecto a Huanta se pierden 14/14/22 horas de entrenamiento por partición, sin positivos ni inicios. Las tablas completas incluyen otras pérdidas de horas por partición y roles.

Los cambios frente a los informes individuales combinan cambios de soporte y modelos: no son un efecto aislado de añadir predictores. Las ocho variantes de este experimento sí se comparan sobre exactamente el mismo soporte y se entrenaron desde cero. No se ajustó el diseño a los resultados ni se eligió un umbral de aviso favorable.

El análisis es exploratorio y condicionado al catálogo histórico y los ajustes dentro de 2013–2023. Las incertidumbres del reloj registrado, intervalos y disponibilidad efectiva continúan abiertas. No demuestra mecanismo físico ni capacidad operacional. El protocolo, resultados completos, calibración, avisos de toda la rejilla, gráficos, fuentes, verificaciones e instrucciones están en informe.md y LEEME.md.
'''
(OUT/'conclusiones.md').write_text(text)
rows.to_csv(OUT/'tablas/lectura_contrastes_principales.csv',index=False)
pd.DataFrame([{'archivo':'conclusiones.md','sha256':hashlib.sha256((OUT/'conclusiones.md').read_bytes()).hexdigest(),'codigo_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}]).to_csv(OUT/'tablas/huella_conclusiones.csv',index=False)
print('Conclusiones explícitas guardadas, sin modificar el experimento cerrado.')
