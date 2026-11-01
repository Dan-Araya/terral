#!/usr/bin/env python3
"""Contraste estructural con implementación original; no importa datos ni ejecuta ajustes."""
from pathlib import Path
import ast,json,hashlib
O=Path(__file__).resolve().parent; R=O.parent
new=ast.parse((O/'ejecutar.py').read_text()); old=ast.parse((R/'experimento_pisco_inicio_v1/ejecutar.py').read_text())
def function(tree,name): return ast.dump(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name),include_attributes=False)
checks={}
for name in ['extension','bootstrap']:
 assert function(new,name)==function(old,name),name
 checks[name+'_identica_Pisco']=True
base=(R/'linea_base_inicio_v0/ejecutar.py').read_text()
for clause in ["THRESHOLDS=[.001,.003,.01,.03,.1,.3,.5]","'maxiter':1000,'gtol':1e-6,'ftol':1e-12",".5*penalty@penalty","sd=X.std(axis=0)"]:
 assert clause in base,clause
checks['algoritmo_escalas_regularizacion_umbrales_heredados']=True
code=(O/'ejecutar.py').read_text()
assert 'b.fit_predict(train,val,cols[arm],h,block)' in code
assert '[35,41,66,72]' in code
checks['ajuste_independiente_24_modelos_y_columnas']=True
reg=json.loads((O/'registro_preentrenamiento.json').read_text())
assert hashlib.sha256((O/'ejecutar.py').read_bytes()).hexdigest()==reg['codigo_sha256']
checks['ejecutor_inalterado_desde_registro']=True
corr=json.loads((O/'correccion_verificador.json').read_text())
for k in ['original','corregido']:
 assert hashlib.sha256((O/corr['archivo_'+k]).read_bytes()).hexdigest()==corr['sha256_'+k]
checks['cadena_correccion_verificador']=True
(O/'auditoria_metodo.json').write_text(json.dumps({'resultado':'conforme','comprobaciones':checks,'limites':'Igualdad estructural de extensión y bootstrap con Pisco y uso del ajustador heredado. No sustituye la reconstrucción numérica independiente ni valida supuestos físicos.'},indent=2,ensure_ascii=False)+'\n')
print('Método, código registrado y corrección documentada: conformes.')
