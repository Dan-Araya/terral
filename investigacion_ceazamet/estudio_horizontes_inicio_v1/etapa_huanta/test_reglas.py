import os,sys
os.environ["OPENBLAS_NUM_THREADS"]="1"
sys.modules["numexpr"]=None
import unittest
import pandas as pd
import numpy as np
import estudio as e
class Reglas(unittest.TestCase):
 def test_futuro_desconocido_y_multiples_inicios(self):
  state=pd.Series(0,index=e.b.IDX); cat=pd.DataFrame({'inicio':pd.to_datetime(['2013-01-02 01:00','2013-01-02 04:00']),'inicio_conocido':[True,True],'id_tramo':['uno','dos']}); state.loc['2013-01-02 08:00']=-1
  yy,ids,future=e.labels(state,cat)
  self.assertEqual(ids[6].loc['2013-01-02 00:00'],'uno|dos'); self.assertEqual(yy[1].loc['2013-01-02 01:00'],0); self.assertTrue(future.loc['2013-01-02 00:00'])
 def test_episodio_un_solo_evento_huecos_y_redundantes(self):
  times=pd.to_datetime(['2018-01-01 00:00','2018-01-01 01:00','2018-01-01 03:00','2018-01-01 05:00','2018-01-01 07:00'])
  cat=pd.DataFrame({'inicio':pd.to_datetime(['2018-01-01 06:00','2018-01-01 08:00']),'id_tramo':['uno','dos']})
  d=pd.DataFrame({'emision':times,'objetivo':[1,1,1,1,0],'id_inicio_objetivo':['uno|dos','uno|dos','uno','dos',''],'probabilidad':[.5]*5})
  a,ev,m=e.notice(d,cat,24,.3,'2018','A','test')
  self.assertEqual(list(a.estado),['acierto','redundante','acierto','falsa_alarma']); self.assertEqual(m['inicios_anticipados'],2); self.assertEqual(m['horas_bajo_aviso'],5); self.assertEqual(m['fraccion_eventos_ge_6h'],.5)
 def test_ningun_aviso_conserva_denominador(self):
  cat=pd.DataFrame({'inicio':pd.to_datetime(['2018-01-01 06:00']),'id_tramo':['uno']})
  d=pd.DataFrame({'emision':pd.to_datetime(['2018-01-01 00:00']),'objetivo':[1],'id_inicio_objetivo':['uno'],'probabilidad':[0.]})
  _,ev,m=e.notice(d,cat,6,.5,'2018','A','test'); self.assertEqual(m['inicios_omitidos'],1); self.assertEqual(m['fraccion_eventos_ge_6h'],0)
if __name__=='__main__': unittest.main()
