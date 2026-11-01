"""Utilidades locales sin red ni dependencias de entrenamiento."""
import csv
import hashlib
import json
from pathlib import Path
BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
HORIZONTES = (1, 3, 6, 8, 12, 24)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''): h.update(block)
    return h.hexdigest()

def guardar(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')

def leer(path): return json.loads(Path(path).read_text())
def filas(path):
    with Path(path).open(newline='') as f: yield from csv.DictReader(f)

# Altura del encabezado histórico, sin resolver la discrepancia con ficha INIA.
SENSORES = [
    ('6','39','temperatura','°C',2.,-50,60),
    ('6','40','humedad','%',2.,0,100),
    ('6','36','viento_2m','m/s',2.,0,75),
    ('6','37','direccion_2m','°',2.,0,360),
    ('6','VCNPA','presion','hPa',2.,800,1100),
    ('8','59','temperatura','°C',1.5,-50,60),
    ('8','60','humedad','%',1.5,0,100),
    ('8','56','viento','m/s',2.,0,75),
    ('8','57','direccion','°',2.,0,360),
    ('8','PEPA','presion','hPa',2.,300,1100),
]
SPECS = {(s[0],s[1]): s for s in SENSORES}
