"""Build every app's .tdapp from its App Builder project.

    python tools/build_apps.py --builder ../tinydesk-app-builder --compiler PATH/mpy-cross [ID ...]

For each apps/<id>/app.json this runs App Builder's generator
(tools/export.cjs) and its package builder (tools/app_package.py in App
Builder), the same steps as App Builder's Export app button, and writes
apps/<id>/app.py (the generated source, for reading and review) and
apps/<id>/<id>.tdapp. Resource files a project names are taken from its
folder. Builds are deterministic: the same project, App Builder and
mpy-cross give the same bytes.

An app can also be handwritten Python. Its app.json is then a small
project that names the source and its modules (<name>.py in its folder):

  {"version": 1, "name": "<id>", "application": {"version": "1.0.0"},
   "board": 2000, "source": "main.py", "modules": ["qr"]}

These are compiled and packed with the same package code; no app.py is
generated.
"""
from pathlib import Path
import argparse
import base64
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--builder', type=Path, required=True, help='an App Builder checkout')
    p.add_argument('--compiler', type=Path, required=True, help='mpy-cross 1.29 (TinyDesk builds one)')
    p.add_argument('ids', nargs='*', help='apps to build (default: all)')
    args = p.parse_args()
    sys.path.insert(0, str(args.builder.resolve() / 'tools'))
    from app_package import build, inspect  # App Builder's own package code

    ids = args.ids or sorted(d.name for d in (ROOT / 'apps').iterdir() if (d / 'app.json').is_file())
    for app_id in ids:
        folder = ROOT / 'apps' / app_id
        project = json.loads((folder / 'app.json').read_text(encoding='utf-8'))
        if project.get('source'):
            modules = {}
            for name in project.get('modules', []):
                if not (folder / (name + '.py')).is_file():
                    sys.exit('%s: module %s is not in apps/%s' % (app_id, name, app_id))
                modules[name + '.py'] = (folder / (name + '.py')).read_text(encoding='utf-8')
            source = (folder / project['source']).read_text(encoding='utf-8')
            write(folder, app_id, build(args.compiler, project, source, None, modules, None), inspect)
            continue
        out = subprocess.run(['node', str(ROOT / 'tools' / 'export.cjs'), str(args.builder), str(folder / 'app.json')],
                             capture_output=True, text=True, encoding='utf-8')
        if out.returncode:
            sys.exit(app_id + ': ' + out.stderr.strip())
        export = json.loads(out.stdout)
        project = export['project']
        assets = {a['name']: base64.b64decode(a['data']) for a in project.get('assets', []) if a.get('data')}
        binaries = {b['name']: base64.b64decode(b['data']) for b in project.get('binaryDependencies', []) if b.get('data')}
        for name in export['paths']:
            name = Path(name).name
            if name not in assets:
                if not (folder / name).is_file():
                    sys.exit('%s: resource %s is not in apps/%s' % (app_id, name, app_id))
                assets[name] = (folder / name).read_bytes()
        modules = {}
        for name in project.get('modules', []):
            if (folder / (name + '.py')).is_file():
                modules[name + '.py'] = (folder / (name + '.py')).read_text(encoding='utf-8')
            elif (folder / (name + '.mpy')).is_file():
                binaries[name + '.mpy'] = (folder / (name + '.mpy')).read_bytes()
            else:
                sys.exit('%s: module %s is not in apps/%s' % (app_id, name, app_id))
        (folder / 'app.py').write_text(export['source'], encoding='utf-8', newline='\n')
        write(folder, app_id, build(args.compiler, project, export['source'], assets, modules, binaries), inspect)


def write(folder, app_id, data, inspect):
    inspect(data)
    target = folder / (app_id + '.tdapp')
    changed = not target.is_file() or target.read_bytes() != data
    target.write_bytes(data)
    print('%-20s %7d bytes%s' % (app_id, len(data), '' if changed else ' (unchanged)'))


if __name__ == '__main__':
    main()
