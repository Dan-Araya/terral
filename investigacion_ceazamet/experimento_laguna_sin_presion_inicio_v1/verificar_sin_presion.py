#!/usr/bin/env python3
"""Prueba contrafactual sintética: ninguna medición de presión complementaria se usa."""
import os,sys,json,importlib.util,ast
os.environ['OPENBLAS_NUM_THREADS']='1'; sys.modules['numexpr']=None; sys.dont_write_bytecode=True
from pathlib import Path
import numpy as np
import pandas as pd
BASE=Path(__file__).resolve().parent
OUT=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else BASE
spec=importlib.util.spec_from_file_location('exp',BASE/'ejecutar.py'); e=importlib.util.module_from_spec(spec); spec.loader.exec_module(e)
checks={}
def check(name,ok):
 assert ok,name
 checks[name]=True
e.b.save=lambda *args:None
x,state,cat,_=e.b.ingest(); p,pe=e.load_extra([])
check('whitelist_cuatro_sensores',set(e.EXPECTED)=={'LAGELTA','LAGELHR','LAGELVV10','LAGELDV10'})
check('sin_canal_presion',set(pe)=={'temperatura','humedad','viento','direccion'})
features=e.allfeatures(x,p,pe)
cols=json.loads((OUT/'predictores.json').read_text())
check('columnas_35_41_66_72',[len(cols[a]) for a in 'ABCD']==[35,41,66,72])
check('sin_predictores_presion_laguna',not any('presion' in c or 'LAGELPA' in c for c in features if c.startswith('LAG_')))
_,ds=e.b.eligibility(x,state,cat)
captured={}
e.save=lambda frame,name:captured.__setitem__(name,frame.copy())
expected=e.support(ds.copy(),features,p,pe); tables={k:v.copy() for k,v in captured.items()}
for label,synthetic in [('faltante',np.nan),('constante',700.),('arbitraria',np.arange(len(pe))%2000)]:
 extra=pe.assign(presion=synthetic)
 ff=e.allfeatures(x,p,extra); pd.testing.assert_frame_equal(features,ff)
 actual=e.support(ds.copy(),ff,p,extra)
 for key in expected: pd.testing.assert_frame_equal(expected[key],actual[key])
 for key in tables: pd.testing.assert_frame_equal(tables[key],captured[key])
 checks['contrafactual_'+label]=True
# Separate inspection of saved eligibility and predictions.
flags=pd.read_csv(OUT/'tablas/elegibilidad_adicional.csv',nrows=0).columns
check('sin_reglas_presion_complementaria',not any(('presion' in c.lower() and 'INIA' not in c) or 'LAGELPA' in c for c in flags))
code=(BASE/'ejecutar.py').read_text()
check('sin_referencia_codigo_LAGELPA','LAGELPA' not in code)
(OUT/'verificacion_sin_presion.json').write_text(json.dumps({'resultado':'conforme','comprobaciones':checks,'limites':'Presión adicional enteramente sintética: prueba invariancia de transformaciones, soporte, etiquetas y diagnósticos. No consulta ni evalúa valores de LAGELPA. La whitelist se verifica además contra configuración y metadatos mediante verificar_calidad.py.'},indent=2,ensure_ascii=False)+'\n')
print('Exclusión completa de presión complementaria: conforme.')
