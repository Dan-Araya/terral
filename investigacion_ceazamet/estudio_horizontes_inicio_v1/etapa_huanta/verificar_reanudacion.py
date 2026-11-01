"""Prueba de checkpoints en carpeta temporal; no entrena ni altera unidades."""
import os,sys
os.environ['OPENBLAS_NUM_THREADS']='1';sys.modules['numexpr']=None;sys.dont_write_bytecode=True
import tempfile,shutil,json
from pathlib import Path
import estudio as e
out=Path(sys.argv[1]) if len(sys.argv)>1 else e.OUT
reg=json.loads((out/'registro_preentrenamiento.json').read_text())
with tempfile.TemporaryDirectory(prefix='horizontes-checkpoint-') as temp:
 dest=Path(temp)/'unidad'; shutil.copytree(out/'unidades/2018-2019/1h/A',dest)
 assert e.unit_valid(dest,reg['firma'])
 (dest/'predicciones.csv').write_text('incompleto\n')
 assert not e.unit_valid(dest,reg['firma'])
 assert not e.unit_valid(dest,'firma_distinta')
 (dest/'estado.json').unlink()
 assert not e.unit_valid(dest,reg['firma'])
 e.js(out/'verificacion_reanudacion.json',{'resultado':'conforme','casos':['unidad completa aceptada','artefacto alterado rechazado','firma distinta rechazada','estado ausente rechazado'],'fuentes_alteradas':False})
print('Checkpoints conformes')
