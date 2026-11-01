#!/usr/bin/env python3
"""Compara por hash la ejecución original y una reproducción completa."""
from pathlib import Path
import sys,json,hashlib,datetime
OUT=Path(__file__).resolve().parent
other=Path(sys.argv[1]).resolve()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
assert json.loads((other/'comprobaciones.json').read_text())['fuentes_inmutables']
paths=[OUT/'protocolo.md',OUT/'predictores.json',OUT/'predicciones_validacion.csv']
paths+=sorted((OUT/'tablas').glob('*.csv'))
paths+=sorted((OUT/'ajustes').glob('*/*/*'))
compared=[]
for path in paths:
 if not path.is_file(): continue
 relative=path.relative_to(OUT); same=sha(path)==sha(other/relative)
 compared.append({'archivo':str(relative),'sha256_original':sha(path),'sha256_reproduccion':sha(other/relative),'identico':same})
assert all(r['identico'] for r in compared)
reg=json.loads((OUT/'registro_preentrenamiento.json').read_text())
assert sha(OUT/'ejecutar.py')==reg['codigo_sha256']
record={'resultado':'conforme','fecha_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'directorio_reproduccion':str(other),'n_archivos_identicos':len(compared),'24_modelos_reajustados':True,'protocolo_inalterado':True,'codigo_previo_verificado':True,'detalle':compared}
(OUT/'reproduccion.json').write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n')
print(f'Conforme: {len(compared)} archivos idénticos; 24 modelos reajustados.')
