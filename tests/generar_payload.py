"""Fixture sintético generado en memoria para las pruebas de presentación."""
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aplicacion_terral import demo

with tempfile.TemporaryDirectory(prefix='terral-test-') as root:
    demo.preparar(root)
    payload = b''.join(demo.crear_aplicacion(root)(
        dict(PATH_INFO='/api/actual', QUERY_STRING='', REQUEST_METHOD='GET'),
        lambda *args: None))
    assert json.loads(payload)['datos_sinteticos']
    print(payload.decode())
