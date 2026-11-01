"""Orquestación de dos ajustes completos y auditorías, con logs separados."""
import estudio as e
import subprocess,sys
from pathlib import Path

def main():
 audit=e.BASE.parent/'auditoria_huanta';audit.mkdir(exist_ok=True)
 for label in ['huanta','huanta_reproduccion']:
  out=e.BASE.parent/'resultados'/label
  assert not (out/'registro_preentrenamiento.json').exists(),'Ejecución nueva requerida; no sobreescribir evidencia'
  commands=[('diagnostico','diagnosticar_soporte.py',[str(out)]),('ajustes','estudio.py',['ejecutar','--etapa','huanta','--activar-etapa-pendiente','--salida',str(out)]),('verificacion','estudio.py',['verificar','--etapa','huanta','--activar-etapa-pendiente','--salida',str(out)]),('intervalos','completar_intervalos.py',[str(out)]),('auditoria','auditoria_adicional.py',[str(out)]),('huecos','verificar_huecos.py',[str(out)]),('reanudacion','verificar_reanudacion.py',[str(out)])]
  for step,script,args in commands:
   print(label,step,flush=True)
   with (audit/f'{label}_{step}.log').open('x') as log:subprocess.run([sys.executable,str(e.BASE/script),*args],stdout=log,stderr=subprocess.STDOUT,check=True)
 print('Dos ejecuciones y auditorías terminadas; iniciando cierre',flush=True)
 with (audit/'cierre.log').open('x') as log:subprocess.run([sys.executable,str(e.BASE/'cerrar_huanta.py')],stdout=log,stderr=subprocess.STDOUT,check=True)
 print('Etapa completa, verificada y reproducida',flush=True)
if __name__=='__main__':main()
