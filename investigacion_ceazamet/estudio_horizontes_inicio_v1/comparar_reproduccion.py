"""Comparación íntegra sin repetir verificaciones independientes ya conformes."""
import os,sys
os.environ['OPENBLAS_NUM_THREADS']='1';sys.modules['numexpr']=None;sys.dont_write_bytecode=True
from pathlib import Path
import json
import estudio as e
BASE=Path(__file__).resolve().parent; OUT=BASE/'resultados/pisco'; REPRO=BASE/'resultados/pisco_reproduccion'
def main():
 regs=[json.loads((p/'registro_preentrenamiento.json').read_text()) for p in [OUT,REPRO]]
 assert regs[0]['firma']==regs[1]['firma'] and regs[0]['fuentes']==regs[1]['fuentes']==e.sources()
 for p,reg in zip([OUT,REPRO],regs):
  assert json.loads((p/'verificacion_independiente.json').read_text())['resultado']=='conforme'
  assert json.loads((p/'estado_etapa.json').read_text())['estado']=='verificado'
  units=list((p/'unidades').glob('*/*/*')); assert len(units)==72
  assert all(e.unit_valid(unit,reg['firma']) for unit in units)
 exclude=['registro_preentrenamiento.json','verificacion_independiente.json','reproduccion.json','preparacion.json','manifiesto_entregables.json']
 paths=lambda p:{q.relative_to(p) for q in p.rglob('*') if q.is_file() and q.name not in exclude}
 first=paths(OUT);second=paths(REPRO);assert first==second,first.symmetric_difference(second)
 differences=[str(p) for p in sorted(first) if e.digest(OUT/p)!=e.digest(REPRO/p)]
 result={'resultado':'conforme' if not differences else 'discrepancias','archivos_comparados':len(first),'diferencias':differences,'directorio':str(REPRO),'ajustes_por_ejecucion':216,'excepciones':['registro con fecha UTC; verificación con rutas de ejecución; manifiesto de entregables; preparación opcional'],'verificacion':'Ambas ejecuciones verificadas íntegramente por separado. Se reutiliza la verificación conforme de la primera tras comprobar hashes; no se repite una tercera vez.'}
 e.js(OUT/'reproduccion.json',result);assert not differences,differences;print('Reproducción conforme',len(first),'archivos deterministas',flush=True)
if __name__=='__main__':main()
