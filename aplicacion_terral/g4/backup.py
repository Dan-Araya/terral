"""Respaldo consistente: exclusión G2 + backup SQLite + evidencia y hashes."""
import datetime as dt
import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path


def backup(root, destination):
    root,destination=Path(root),Path(destination)
    destination.mkdir(parents=True,exist_ok=True,mode=0o700)
    lock=root/'runtime/evidencia/adquisicion.lock'
    with lock.open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)  # Esperar al cierre; evidencia y DB del mismo corte.
        with tempfile.TemporaryDirectory(dir=destination,prefix='.backup-') as tmp:
            temp=Path(tmp)
            for name in ('adquisiciones','revisiones','DETENIDO.json','operacion.json'):
                p=root/name
                if p.is_dir(): shutil.copytree(p,temp/name)
                elif p.exists(): shutil.copy2(p,temp/name)
            if (root/'terral.sqlite3').exists():
                src=sqlite3.connect((root/'terral.sqlite3').resolve().as_uri()+'?mode=ro',uri=True)
                dst=sqlite3.connect(temp/'terral.sqlite3')
                try:
                    src.backup(dst)
                    assert dst.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
                finally: src.close();dst.close()
            manifest={str(p.relative_to(temp)):hashlib.sha256(p.read_bytes()).hexdigest() for p in temp.rglob('*') if p.is_file()}
            (temp/'SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n')
            name='terral-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            archive=shutil.make_archive(str(destination/name),'gztar',temp)
            Path(archive).chmod(0o600)
            return archive

if __name__=='__main__':
    os.umask(0o077)
    print(backup(os.environ.get('TERRAL_DATA','/var/lib/terral'),os.environ.get('TERRAL_BACKUPS','/var/backups/terral')))
