#!/usr/bin/env python3
"""Cierra el experimento solo después de verificar y reproducir."""
import sys,os,json,hashlib,datetime
sys.modules['numexpr']=None; os.environ['MPLCONFIGDIR']='/tmp/huanta-v1-mpl'
from pathlib import Path
import numpy as np
import pandas as pd
OUT=Path(__file__).resolve().parent; ROOT=OUT.parent.parent
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
for name in ['verificacion.json','verificacion_independiente.json','verificacion_avisos.json','verificacion_huecos.json','verificacion_calidad.json','reproduccion.json']:
 assert json.loads((OUT/name).read_text())['resultado']=='conforme',name
for row in json.loads((OUT/'conservacion_previa.json').read_text()): assert sha(ROOT/row['archivo'])==row['sha256']
for row in pd.read_csv(OUT/'tablas/manifiesto_fuentes.csv').itertuples(): assert sha(ROOT/row.archivo)==row.sha256_antes==row.sha256_despues
reg=json.loads((OUT/'registro_preentrenamiento.json').read_text())
assert sha(OUT/'ejecutar.py')==reg['codigo_sha256'] and sha(OUT/'protocolo.md')==reg['protocolo_sha256']
pairs=pd.read_csv(OUT/'tablas/diferencias_por_particion.csv').fillna({'politica':''})
hm=pd.read_csv(OUT/'tablas/metricas_horarias.csv'); am=pd.read_csv(OUT/'tablas/metricas_avisos.csv')
for row in pairs.itertuples():
 table=hm if row.metrica in ['AP','Brier'] else am
 z=table[(table.horizonte_h==row.horizonte_h)&table.bloque.eq(row.bloque)&table.epoca.eq('ALL')]
 if 'politica' in z: z=z[z.politica.eq(row.politica)]
 z=z.set_index('modelo'); new,old=row.contraste.split('-')
 assert np.isclose(z.loc[new,row.metrica]-z.loc[old,row.metrica],row.delta,rtol=5e-7,atol=1e-10,equal_nan=True),str(row)
for logfile in ['ejecucion.log','reproduccion.log']:
 log=(OUT/logfile).read_text()
 assert sum(line.startswith('Ajuste ') for line in log.splitlines())==24,logfile
 assert 'Finalizado; fuentes intactas y controles conformes.' in log,logfile
parts=pd.read_csv(OUT/'tablas/particiones.csv'); support=pd.read_csv(OUT/'tablas/soporte_potencial_y_perdidas.csv'); effect=pd.read_csv(OUT/'tablas/efecto_huecos_huanta.csv')
rep=json.loads((OUT/'reproduccion.json').read_text())
text='\n## Cierre verificado y lectura del soporte\n\n'
text+='La comparación evalúa Huanta frente a INIA sobre el soporte común de Huanta. No permite ordenar Huanta, Pisco o Gabriela a partir de sus métricas en soportes diferentes. La hipótesis física del usuario permanece como hipótesis; utilidad predictiva del criterio histórico no demuestra mecanismo físico ni validación meteorológica independiente del terral.\n\n'
text+='Denominadores agregados fuera de muestra, por brazo:\n\n| Horizonte | Emisiones | Positivos | Inicios distintos evaluables |\n| --- | --- | --- | --- |\n'
for h in [1,3]:
 z=parts[(parts.horizonte_h==h)&parts.rol.eq('validacion')]
 text+=f'| {h} h | {int(z.n.sum())} | {int(z.positivos.sum())} | {int(z.inicios_con_oportunidad.sum())} |\n'
text+='\nLos bienios de validación no se solapan. Los entrenamientos son expansivos: reutilizan los mismos huecos históricos y no deben sumarse como pérdidas independientes.\n\n'
for h in [1,3]:
 for role in ['entrenamiento','validacion']:
  z=support[(support.horizonte_h==h)&support.rol.eq(role)&support.brazo_potencial.eq('A')]
  text+=f'A {h} h, las pérdidas totales de {role} frente a INIA básica son '+', '.join(f'{r.bloque}: {r.perdidas_vs_A} emisiones, {r.positivos_A-r.positivos_comunes} positivos y {r.inicios_sin_oportunidad_por_exclusion} inicios sin oportunidad restante' for r in z.itertuples())+'.\n\n'
ex=pd.read_csv(OUT/'tablas/elegibilidad_adicional.csv')
text+='Motivos adicionales no excluyentes agregados de validación (sin duplicar bienios; no sumar entre motivos):\n\n| Horizonte | Motivo | Emisiones afectadas | Positivos afectados |\n| --- | --- | --- | --- |\n'
for h in [1,3]:
 z=ex[(ex.horizonte_h==h)&ex.rol.eq('validacion')]
 for cause in ['presion_INIA_ventana_incompleta','Huanta_ventana_incompleta']+[v+'_Huanta_ventana_incompleta' for v in ['temperatura','humedad','viento','direccion','presion']]:
  bad=z[cause]
  text+=f'| {h} h | {cause} | {int(bad.sum())} | {int(z.loc[bad,"objetivo"].sum())} |\n'
text+='\n'
text+='El mayor hueco de LLHTA comprende 2015-04-28 11:00 a 2016-04-30 23:00: 8.845 horas no utilizables. Su efecto sobre ventanas se extiende seis horas después del hueco. Los otros sensores también pueden faltar simultáneamente; por eso se muestran pérdidas no excluyentes y marginales.\n\n'
for h in [1,3]:
 z=effect[(effect.horizonte_h==h)&effect.causa.eq('hueco_largo_T')&effect.rol.eq('entrenamiento')]
 text+=f'Hueco largo de temperatura, {h} h: '+ '; '.join(f'{r.bloque}: {r.ventanas_afectadas} emisiones base afectadas ({r.positivos_afectados} positivos, {r.inicios_afectados} inicios), {r.perdidas_marginales_horas} pérdidas marginales tras exigir los demás sensores' for r in z.itertuples())+'. No afecta directamente las validaciones 2018–2023.\n\n'
 z=effect[(effect.horizonte_h==h)&effect.causa.eq('presion')]
 text+=f'Presión LLHPA, {h} h: '+ '; '.join(f'{r.bloque}/{r.rol}: {r.ventanas_afectadas} ventanas incompletas, {r.perdidas_marginales_horas} pérdidas marginales, {r.perdidas_marginales_positivos} positivos marginales y {r.inicios_recuperables_marginalmente} inicios recuperables marginalmente' for r in z.itertuples())+'.\n\n'
text+='![Cobertura de Huanta y soporte común](graficos/cobertura_huanta.png)\n\n'
text+='Estos resultados condicionan el rendimiento a disponibilidad completa. No evalúan capacidad operacional durante los huecos y no se ha imputado ningún dato.\n\n'
text+=f'La repetición completa reajustó 24 modelos y reprodujo exactamente por SHA-256 {rep["n_archivos_identicos"]} archivos deterministas. Fuentes, catálogo y archivos anteriores de INIA, Pisco y Gabriela incluidos en el inventario protegido permanecieron intactos. El inventario conserva los artefactos de línea base y catálogo; no se abren archivos de observaciones fuera de 2013–2023 para comprobar conservación.\n\n'
text+='verificar.py reconstruye soporte, etiquetas, purgas, ventanas, escalas de entrenamiento, probabilidades, AP/Brier, calibración e intervalos horarios y regenera el bootstrap. verificar_avisos.py reconstruye todos los grupos, correspondencias, métricas e intervalos de la rejilla completa. verificar_huecos.py reconstruye huecos, cobertura, efectos por sensor y ejemplos comunes en entrenamiento/validación. La carga comprueba sensores, alturas, unidades y máscaras auditadas contra min/prom/max/%Datos y conserva ceros. Las comprobaciones de invariancia alteran observaciones posteriores a tres emisiones sin cambiar sus predictores.\n\n'
text+='verificar_calidad.py lee directamente los CSV y configuración/metadatos sin importar el ejecutor: recalcula máscaras, conserva ceros y comprueba que las siete marcas de cada ejemplo usan solo sensores válidos. Esta auditoría adicional se añadió después de entrenar sin cambiar protocolo ni ajustes; su hash consta en su resultado y en el manifiesto final. Las verificaciones tienen reconstrucciones independientes pero comparten ingestión; detectan inconsistencias de implementación, no prueban ausencia absoluta de errores, exactitud instrumental, significado físico de marcas, mecanismo del terral ni validez meteorológica del catálogo. El bootstrap es condicional a ajustes y etiquetas y no incluye incertidumbre de entrenamiento ni medición. No se fijó una cantidad de controles como objetivo.\n'
p=OUT/'informe.md'; s=p.read_text(); marker='\n## Cierre verificado y lectura del soporte'
if marker in s: s=s[:s.index(marker)]
p.write_text(s+text)
record={'resultado':'conforme','fecha_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'fuentes_y_experimentos_conservados':True,'codigo_y_protocolo_registrados_intactos':True,'sin_descargas_ni_despliegue':True,'reproduccion_archivos_identicos':rep['n_archivos_identicos'],'limites':'No acredita calidad instrumental ni mecanismo físico; ver informe.'}
(OUT/'cierre.json').write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n')
files=[]
for p in sorted(OUT.rglob('*')):
 if p.is_file() and '__pycache__' not in p.parts and p.name!='manifiesto_entregables.json': files.append({'archivo':str(p.relative_to(OUT)),'bytes':p.stat().st_size,'sha256':sha(p)})
(OUT/'manifiesto_entregables.json').write_text(json.dumps({'fecha_utc':record['fecha_utc'],'archivos':files},indent=2,ensure_ascii=False)+'\n')
print('Cierre conforme; informe y manifiesto final guardados.')
