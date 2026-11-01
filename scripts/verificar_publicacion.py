"""Comprueba el contenido permitido y la integridad del motor publicado, sin red."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def ignore_text(paths):
    parents = {str(p) for name in paths for p in Path(name).parents if str(p) != '.'}
    return ('# Lista explícita: editar publicacion.json y regenerar con el verificador.\n'
            '# Lo que no figura aquí permanece local, incluidos datos y respaldos.\n*\n'
            + ''.join('!/'+p+'/\n' for p in sorted(parents, key=lambda p: (p.count('/'), p)))
            + ''.join('!/'+p+'\n' for p in sorted(paths)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generar-ignore', action='store_true')
    args = parser.parse_args()
    manifest = json.loads((ROOT/'publicacion.json').read_text())
    paths = manifest['archivos']
    assert len(paths) == len(set(paths)), 'Rutas repetidas'
    assert all(not Path(p).is_absolute() and '..' not in Path(p).parts for p in paths), 'Ruta inválida'
    expected = ignore_text(paths)
    if args.generar_ignore:
        (ROOT/'.gitignore').write_text(expected)
    assert (ROOT/'.gitignore').read_text() == expected, 'Regenerar .gitignore'
    forbidden = re.compile(r'(^|/)(\.ssh|\.aws|\.env[^/]*|evidencia|datos_G2|respaldos[^/]*|__pycache__)(/|$)|\.(xls[x]?|sqlite3?|db|pdf|pyc|pem|key)$', re.I)
    secret = re.compile(r'-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16}')
    for name in paths:
        p = ROOT/name
        assert p.is_file() and not p.is_symlink(), f'Archivo ausente o enlace: {name}'
        assert not forbidden.search(name), f'Ruta privada: {name}'
        assert p.stat().st_size < 2_000_000, f'Archivo grande: {name}'
        if p.suffix not in ('.png', '.jpg'):
            assert not secret.search(p.read_text()), f'Posible secreto: {name}'
    for name, digest in manifest['congelados_sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest, f'Cambió archivo congelado: {name}'
    if args.generar_ignore:
        print('Reglas regeneradas; preparar los archivos con Git y ejecutar de nuevo sin esta opción.')
        return
    tracked = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True).stdout.decode().split('\0')
    tracked = set(filter(None, tracked))
    assert tracked, 'No hay archivos en el índice Git; preparar los archivos antes de verificar'
    assert tracked == set(paths), f'Índice distinto de la lista: extra={tracked-set(paths)}; falta={set(paths)-tracked}'
    print(f'OK: {len(paths)} archivos permitidos; modelos y motor intactos; sin datos originales ni secretos reconocidos.')


if __name__ == '__main__':
    main()
