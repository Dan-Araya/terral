"""Equivalencia del conteo OOF independiente con la implementación completa."""
import os,sys
os.environ['OPENBLAS_NUM_THREADS']='1';sys.modules['numexpr']=None;sys.dont_write_bytecode=True
from pathlib import Path
import json
import pandas as pd
import estudio as e
from verificar_rapido import oof_counts
out=e.OUT
cat=pd.read_csv(e.ROOT/'catalogo_provisional_v0/catalogo_referencia.csv');cat['inicio']=pd.to_datetime(cat.primera_marca)
d=pd.read_csv(out/'unidades/2018-2019/1h/A/oof.csv',parse_dates=['emision'],float_precision='round_trip').fillna({'id_inicio_objetivo':''})
checks={}
for year,g in d.groupby('fold'):
 for threshold in e.CONFIG['umbrales']:
  actual=e.notice(g,cat,1,threshold,str(year),'A','test')[2]; fast=oof_counts(g,cat,threshold)
  for metric,value in fast.items(): assert value==actual[metric],(year,threshold,metric)
  checks[f'{year}_{threshold}']=True
e.js(out.parent.parent/'test_verificador_rapido.json',{'resultado':'conforme','comprobaciones':checks,'alcance':'Dos folds anuales OOF de A, horizonte1, siete umbrales; ningún ajuste.'})
print('Conteo OOF optimizado equivalente',len(checks),flush=True)
