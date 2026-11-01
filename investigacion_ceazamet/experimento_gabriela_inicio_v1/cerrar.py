#!/usr/bin/env python3
"""Cierre documental: requiere auditorías conformes y reproducción exacta."""
from pathlib import Path
import sys,json,hashlib,datetime
sys.modules['numexpr']=None
import pandas as pd
OUT=Path(__file__).resolve().parent; ROOT=OUT.parent.parent
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
for name in ['verificacion.json','verificacion_independiente.json','verificacion_avisos.json','reproduccion.json']:
 assert json.loads((OUT/name).read_text())['resultado']=='conforme',name
protected=json.loads((OUT/'conservacion_previa.json').read_text())
for row in protected: assert sha(ROOT/row['archivo'])==row['sha256']
man=pd.read_csv(OUT/'tablas/manifiesto_fuentes.csv')
for row in man.itertuples(): assert sha(ROOT/row.archivo)==row.sha256_antes==row.sha256_despues
reg=json.loads((OUT/'registro_preentrenamiento.json').read_text())
assert sha(OUT/'ejecutar.py')==reg['codigo_sha256'] and sha(OUT/'protocolo.md')==reg['protocolo_sha256']
pairs=pd.read_csv(OUT/'tablas/diferencias_por_particion.csv').fillna({'politica':''})
hm=pd.read_csv(OUT/'tablas/metricas_horarias.csv'); am=pd.read_csv(OUT/'tablas/metricas_avisos.csv')
import numpy as np
for row in pairs.itertuples():
 table=hm if row.metrica in ['AP','Brier'] else am
 z=table[(table.horizonte_h==row.horizonte_h)&table.bloque.eq(row.bloque)&table.epoca.eq('ALL')]
 if 'politica' in z: z=z[z.politica.eq(row.politica)]
 z=z.set_index('modelo'); new,old=row.contraste.split('-')
 assert np.isclose(z.loc[new,row.metrica]-z.loc[old,row.metrica],row.delta,rtol=5e-7,atol=1e-10,equal_nan=True),str(row)
pressure=pd.read_csv(OUT/'tablas/presion_RMPPA_excluida.csv')
assert len(pressure)==908 and pressure.utilizable_revision.eq(0).all()
inside=pressure.prom.between(300,1100)
assert inside.sum()==52 and pressure.loc[inside,'min'].lt(300).all()
impact=pd.read_csv(OUT/'tablas/efecto_presion_RMPPA.csv')
assert impact[impact.rol.eq('validacion')].perdidas_marginales_por_908.eq(0).all()
rep=json.loads((OUT/'reproduccion.json').read_text())
text='''\n## Cierre de integridad e interpretación de soporte\n\nLa presión RMPPA conserva las **908 horas rechazadas** (905 en 2014 y 3 en 2015), incluidas las **52 con promedio en rango y mínimo fuera**. Sus ventanas excluyen marginalmente **1.236 emisiones de entrenamiento** en cada partición expansiva y en cada horizonte, después de exigir todas las otras variables. Son las mismas horas históricas reutilizadas en entrenamientos expansivos; no son 1.236 pérdidas nuevas por partición. No se pierde ningún ejemplo positivo por estas 908 horas ni ninguna ventana de validación por ese motivo.\n\nLa pérdida total frente a INIA básica incluye además ausencias o calidad de los demás sensores y presión INIA. En validación, las pérdidas totales son 0 / 125 / 0 emisiones para 2018–2019 / 2020–2021 / 2022–2023 en ambos horizontes, sin perder positivos. Los cuatro brazos usan siempre la intersección estricta; estos resultados describen rendimiento condicionado a disponibilidad completa y no evalúan cobertura operacional durante huecos.\n\nAP evalúa ordenamiento de probabilidades y **no es porcentaje de aciertos**. No se interpreta un contraste agregado favorable como mejora consistente si falla la estabilidad por partición o el criterio conjunto AP/Brier. «Ausencia de evidencia de mejora» corresponde aquí a evidencia no concluyente, no demuestra equivalencia ni ausencia de cualquier señal. Los resultados conciernen solo al inicio del criterio histórico y no establecen validación meteorológica independiente del terral. No se ordena Gabriela frente a Pisco usando soportes diferentes.\n\nEl sitio se actualiza cada hora para todas las estaciones. No se añadieron demoras hipotéticas ni se buscaron desplazamientos; la disponibilidad inmediata en t y la equivalencia física de marcas siguen siendo supuestos. No se corrigió presión ni referencia altimétrica.\n\n'''
parts=pd.read_csv(OUT/'tablas/particiones.csv')
text+='Denominadores agregados de validación sobre soporte común (idénticos en A/B/C/D):\n\n| Horizonte | Emisiones por brazo | Ejemplos positivos | Inicios distintos evaluables |\n| --- | --- | --- | --- |\n'
for h in [1,3]:
 z=parts[(parts.horizonte_h==h)&parts.rol.eq('validacion')]
 text+=f'| {h} h | {int(z.n.sum())} | {int(z.positivos.sum())} | {int(z.inicios_con_oportunidad.sum())} |\n'
text+='\nLos bienios de validación no se solapan; los entrenamientos expansivos sí.\n\n'
ci=pd.read_csv(OUT/'tablas/intervalos_pareados.csv')
r=ci[(ci.horizonte_h==1)&ci.contraste.eq('D-B')&ci.metrica.eq('Brier')].iloc[0]
text+=f'A 1 hora, D−B aumenta Brier en {r.estimacion:.6g} (IC 95 % [{r.p025:.6g}, {r.p975:.6g}]); el intervalo de AP incluye cero y los cambios de AP no mantienen signo entre particiones. Por eso la regla conjunta lo clasifica como resultado incierto, aunque Brier muestre deterioro. Para C−A en ambos horizontes y D−B a 3 horas, ambos intervalos agregados incluyen cero: evidencia no concluyente de mejora.\n\n'
text+=f'La repetición completa reajustó los **24 modelos** y reprodujo exactamente por SHA-256 **{rep["n_archivos_identicos"]} archivos** deterministas de protocolo, columnas, predicciones, tablas y ajustes. Los registros con fechas de ejecución se conservan separados. Fuentes, Pisco y línea base permanecen intactos según sus hashes.\n\n'
text+='''La verificación independiente reconstruye ventanas, etiquetas, exclusiones, fronteras y purgas, verifica sensores/máscaras, escala de entrenamiento y probabilidades, recalcula AP/Brier/calibración y los intervalos horarios, y regenera las multiplicidades bootstrap. La auditoría adicional verificar_avisos.py reconstruye todos los grupos de la rejilla, su vinculación cronológica, métricas por partición/estación y agregadas, e intervalos de avisos. Este último verificador se añadió durante la evaluación sin cambiar el diseño o los ajustes; su hash consta en verificacion_avisos.json y el manifiesto final.\n\nEstas comprobaciones detectan inconsistencias de implementación y artefactos; no prueban exactitud instrumental, cronología física, validez meteorológica del catálogo ni ausencia absoluta de errores. Comparten ingestión con el ejecutor, aunque reconstruyen soporte y métricas por separado. Bootstrap y reproducción no incorporan incertidumbre de etiquetas, entrenamiento o medición. No se impuso un número de controles como criterio de éxito.\n'''
p=OUT/'informe.md'; s=p.read_text(); marker='\n## Cierre de integridad e interpretación de soporte'
if marker in s: s=s[:s.index(marker)]
p.write_text(s+text)
record={'resultado':'conforme','fecha_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'fuentes_conservadas':True,'pisco_y_linea_base_conservados':True,'protocolo_y_codigo_registrados_intactos':True,'sin_lectura_observaciones_reservadas':True,'sin_descargas_ni_despliegue':True,'reproduccion_archivos_identicos':rep['n_archivos_identicos']}
(OUT/'cierre.json').write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n')
files=[]
for p in sorted(OUT.rglob('*')):
 if p.is_file() and '__pycache__' not in p.parts and p.name!='manifiesto_entregables.json': files.append({'archivo':str(p.relative_to(OUT)),'bytes':p.stat().st_size,'sha256':sha(p)})
(OUT/'manifiesto_entregables.json').write_text(json.dumps({'fecha_utc':record['fecha_utc'],'archivos':files},indent=2,ensure_ascii=False)+'\n')
print('Cierre conforme; informe y manifiesto final guardados.')
