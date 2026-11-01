"""Adaptación de rutas operativas; mantiene sin cambios el ciclo y transporte G2."""
import json
import os
from pathlib import Path
from .. import adquirir
from ..g2 import ciclo


def main():
    root = Path(os.environ.get('TERRAL_DATA','/var/lib/terral'))
    adquirir.TRANSPORTE = Path(__file__).parent/'transporte.py'
    ciclo.TRANSPORTE = adquirir.TRANSPORTE
    # G2 usa BASE solo para evidencia/lock; modelos/políticas permanecen en su módulo.
    ciclo.BASE = root/'runtime'
    (ciclo.BASE/'evidencia').mkdir(parents=True,exist_ok=True,mode=0o700)
    (ciclo.BASE/'evidencia/adquisicion.lock').touch(mode=0o600,exist_ok=True)
    from ..ha3.operacion import cerrar
    emitted=[]
    def close(*args, **kwargs):
        output=cerrar(*args, **kwargs)
        emitted.extend(output['emisiones_nuevas'])
        return output
    ciclo.cerrar = close
    result = ciclo.ejecutar(root)
    result['inferencias_actuales_emitidas']=len(emitted)
    result['politica']='HA-3' 
    print(json.dumps(result,ensure_ascii=False),flush=True)
    if result.get('fallos') or result['estado']=='detenido_requiere_revision_manual':
        raise SystemExit(1)

if __name__=='__main__': main()
