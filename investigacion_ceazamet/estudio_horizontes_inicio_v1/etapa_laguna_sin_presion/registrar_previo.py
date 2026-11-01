"""Congelar manifiesto y columnas antes de entrenar."""
import estudio as e
import sys,platform,hashlib
from pathlib import Path
out=Path(sys.argv[1]);e.OUT=out;e.setup()
initial=e.sources()
e.js(out/'manifiesto_fuentes_previo.json',initial)
e.js(out/'protocolo_previo.json',{'etapa':e.ETAPA,'protocolo_sha256':e.digest(e.BASE/'protocolo_etapa.md'),'estado':'antes del primer ajuste'})
x,state,cat,f,cols=e.load();e.js(out/'predictores.json',cols)
assert [len(cols[a]) for a in 'ABCD']==[35,41,66,72]
assert not any('LAG_presion' in c or 'LAGELPA' in c for c in f)
assert initial==e.sources()
print('Fuentes, protocolo y columnas registrados antes de entrenar',flush=True)
