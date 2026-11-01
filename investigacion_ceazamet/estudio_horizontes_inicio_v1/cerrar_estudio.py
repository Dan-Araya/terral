"""Cierre de entregables derivados; ejecutar después de reproducir la etapa."""
import os,sys
os.environ['OPENBLAS_NUM_THREADS']='1'; sys.modules['numexpr']=None; sys.dont_write_bytecode=True
from pathlib import Path
import subprocess,json,hashlib,shutil
BASE=Path(__file__).resolve().parent; OUT=BASE/'resultados/pisco'; REPRO=BASE/'resultados/pisco_reproduccion'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def js(p,obj):Path(p).write_text(json.dumps(obj,indent=2,ensure_ascii=False,default=str)+'\n')
def main():
 reproduction=json.loads((OUT/'reproduccion.json').read_text()); assert reproduction['resultado']=='conforme'
 scripts=['completar_intervalos.py','auditoria_adicional.py','verificar_reanudacion.py','completar_informe.py']
 js(BASE/'registro_verificacion_adicional.json',{'alcance':'Comprobaciones y presentación; sin ajustes ni decisiones por desempeño','codigo':{n:sha(BASE/n) for n in scripts},'comandos':[f'python {BASE/n} DIRECTORIO' for n in scripts]})
 shutil.copy2(OUT/'reproduccion.json',REPRO/'reproduccion.json')
 for dest in [OUT,REPRO]:
  for script in scripts:subprocess.run([sys.executable,str(BASE/script),str(dest)],check=True)
 derived=['tablas/intervalos_politicas_disponibles.csv','tablas/intervalos_completos.csv','tablas/distribucion_anticipacion.csv','tablas/curvas_precision_recall.csv','auditoria_adicional.json','verificacion_reanudacion.json','cierre.md']+[f'graficos/politicas_{h}h.png' for h in [1,3,6,8,12,24]]
 differences=[p for p in derived if sha(OUT/p)!=sha(REPRO/p)]; assert not differences,differences
 for dest in [OUT,REPRO]:
  reg=json.loads((dest/'registro_preentrenamiento.json').read_text())
  assert all(sha(p)==h for p,h in reg['fuentes'].items())
  assert json.loads((dest/'verificacion_independiente.json').read_text())['resultado']=='conforme'
  assert json.loads((dest/'auditoria_adicional.json').read_text())['resultado']=='conforme'
  units={}
  for p in sorted((dest/'unidades').glob('*/*/*/estado.json')):
   z=json.loads(p.read_text()); assert z['estado']=='verificado' and z['firma']==reg['firma']; assert all(sha(p.parent/n)==h for n,h in z['archivos'].items()); units[str(p.parent.relative_to(dest))]='verificado'
  assert len(units)==72
  js(dest/'estados.json',{'pisco':{'estado':'verificada_y_reproducida','unidades':units},'huanta':{'estado':'pendiente_sin_entrenar'},'laguna_sin_presion':{'estado':'pendiente_sin_entrenar'},'sintesis':{'estado':'pendiente'}})
  js(dest/'cierre.json',{'resultado':'conforme','etapa':'pisco','modelos_externos_por_ejecucion':72,'modelos_internos_por_ejecucion':144,'reproduccion_principal':reproduction,'derivados_adicionales_identicos':derived,'fuentes_y_experimentos_previos_intactos':True,'otras_etapas_entrenadas':False,'protocolo_sha256':sha(BASE/'protocolo.md')})
  versions=reg['versiones']; (dest/'requirements.txt').write_text('\n'.join(f'{k}=={v}' for k,v in versions.items() if k!='python')+'\n')
  js(dest/'manifiesto_entregables.json',{str(p.relative_to(dest)):sha(p) for p in sorted(dest.rglob('*')) if p.is_file() and p.name!='manifiesto_entregables.json'})
 js(BASE/'manifiesto_codigo.json',{str(p.relative_to(BASE)):sha(p) for p in sorted(list(BASE.iterdir())+list((BASE/'verificar').glob('*.py'))) if p.is_file() and p.suffix in ['.py','.md','.json'] and p.name!='manifiesto_codigo.json'})
 print('Cierre conforme; modelos reproducidos y derivados idénticos.',flush=True)
if __name__=='__main__':main()
