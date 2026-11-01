"""Conservación histórica, comparación íntegra y cierre La Laguna sin presión tras dos ejecuciones."""
import estudio as e
import json
import completar_informe
from pathlib import Path

def main():
 base=e.BASE.parent;a=base/'resultados/laguna_sin_presion';b=base/'resultados/laguna_sin_presion_reproduccion'
 for out in [a,b]:
  reg=json.loads((out/'registro_preentrenamiento.json').read_text());assert reg['fuentes']==e.sources()
  for name in ['verificacion_independiente','auditoria_adicional','verificacion_huecos','verificacion_reanudacion']:assert json.loads((out/f'{name}.json').read_text())['resultado']=='conforme'
  units=list((out/'unidades').glob('*/*/*/estado.json'));assert len(units)==72 and all(e.unit_valid(p.parent,reg['firma']) for p in units)
 excluded={'registro_preentrenamiento.json','verificacion_independiente.json','reproduccion.json','preparacion.json','manifiesto_entregables.json','cierre.md','cierre.json','estados.json','estado_etapa.json'}
 files=lambda root:{str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name not in excluded}
 assert files(a)==files(b),(files(a)^files(b))
 dif=[n for n in sorted(files(a)) if e.digest(a/n)!=e.digest(b/n)];assert not dif,dif
 hist=json.loads((base/'auditoria_laguna_sin_presion/conservacion_previa.json').read_text());assert all(e.digest(p)==sha for p,sha in hist.items())
 repro={'resultado':'conforme','archivos_comparados':len(files(a)),'diferencias':dif,'ajustes_por_ejecucion':216,'reajuste_interno_y_externo_completo':True,'excepciones':sorted(excluded),'conservacion_historica_archivos':len(hist)}
 for out in [a,b]:e.js(out/'reproduccion.json',repro);completar_informe.complete(out)
 assert e.digest(a/'cierre.md')==e.digest(b/'cierre.md')
 assert files(a)==files(b)
 assert all(e.digest(a/n)==e.digest(b/n) for n in files(a))
 repro['archivos_comparados']=len(files(a))+1
 repro['incluye_derivados_de_cierre']=True
 for out in [a,b]:e.js(out/'reproduccion.json',repro)
 for out in [a,b]:
  e.js(out/'cierre.json',{'resultado':'conforme','etapa':'laguna_sin_presion','modelos_externos_por_ejecucion':72,'modelos_internos_por_ejecucion':144,'reproduccion':repro,'fuentes_y_experimentos_previos_intactos':True,'otras_etapas_entrenadas':False})
  e.js(out/'estado_etapa.json',{'estado':'verificada_y_reproducida','etapa':'laguna_sin_presion','unidades':72})
  e.js(out/'manifiesto_entregables.json',{str(p.relative_to(out)):e.digest(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='manifiesto_entregables.json'})
 e.js(base/'auditoria_laguna_sin_presion/conservacion_final.json',{'resultado':'conforme','archivos':len(hist),'manifiesto_previo_sha256':e.digest(base/'auditoria_laguna_sin_presion/conservacion_previa.json')})
 print('Cierre La Laguna sin presión conforme',repro,flush=True)
if __name__=='__main__':main()
