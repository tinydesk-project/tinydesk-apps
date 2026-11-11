"""Check every app and write the store's catalog.

    python tools/make_index.py [--out site]     check, then write the site
    python tools/make_index.py --check          check only

Needs only Python: it reads each apps/<id>/<id>.tdapp itself (TDAPP format
1: payloads, a JSON manifest, then b"TDAPP001", the manifest's offset and
length, little-endian) and checks every entry's SHA-256. The site gets:

  index.json    the catalog for people and web pages
  catalog.txt   the same for TinyDesk's Store app, one "key value" per line
  <id>.tdapp    the packages
  index.html    a plain list

catalog.txt (format 1):

  TDSTORE 1
  app <id>                  starts an entry; id: a-z 0-9 _ -, up to 31
  title <text>
  version <x.y.z>
  summary <text>            up to 160 bytes
  category <text>
  file <id>.tdapp           next to catalog.txt
  size <bytes>
  sha256 <64 hex>           of the whole file
  cache .tdapp-<16 hex>     the folder the package unpacks into
  api <major>.<minor>       tdui API it needs
  cells <n>                 canvas cells it needs (2000: every board)
  needs <cap> ...           tdui capabilities, if any
  cpu <arch>                native code for this CPU only, if any
  author <text>             who made it, up to 40 bytes
  repo <url>                where its source is (https://), up to 84 bytes
  license <text>            its licence, e.g. MIT, up to 16 bytes
  end

Lines are at most 200 bytes, UTF-8; unknown keys are ignored, so later
formats can add some.
"""
from pathlib import Path
import argparse
import hashlib
import html
import json
import re
import shutil
import struct
import sys

ROOT = Path(__file__).resolve().parent.parent
FOOTER = b'TDAPP001'
MAX_SIZE = 16 * 1024 * 1024
ID = re.compile(r'^[a-z0-9_-]{1,31}$')
VERSION = re.compile(r'^\d+\.\d+\.\d+$')
CAPABILITIES = {'gradient_fills', 'rgb_pictures'}
CATEGORIES = {'Examples', 'Tools', 'Games', 'Industrial', 'Education'}


class Bad(Exception):
    pass


def read_package(data):
    if not 16 <= len(data) <= MAX_SIZE or data[-16:-8] != FOOTER:
        raise Bad('not a TDAPP package')
    offset, length = struct.unpack('<II', data[-8:])
    if length > 262144 or offset + length != len(data) - 16:
        raise Bad('bad manifest position')
    raw = data[offset:offset + length]
    manifest = json.loads(raw)
    if manifest.get('format') != 1 or manifest.get('runtime', {}).get('api') != 1:
        raise Bad('unknown package format or tdui API')
    files = {}
    for item in manifest['files']:
        start, size = item['offset'], item['size']
        if not (0 <= start and 0 <= size and start + size <= offset):
            raise Bad('entry out of range: ' + item['path'])
        payload = data[start:start + size]
        if hashlib.sha256(payload).hexdigest() != item['sha256']:
            raise Bad('checksum mismatch: ' + item['path'])
        files[item['path']] = payload
    if 'project.json' not in files:
        raise Bad('no project.json')
    return manifest, raw, json.loads(files['project.json'])


def one_line(text, limit, what):
    if not isinstance(text, str) or not text or len(text.encode()) > limit or any(ord(c) < 32 for c in text):
        raise Bad('%s: one line of 1 to %d bytes' % (what, limit))
    return text


def entry(folder):
    app_id = folder.name
    if not ID.match(app_id):
        raise Bad('folder name must be a-z 0-9 _ -, up to 31 characters')
    meta = json.loads((folder / 'store.json').read_text(encoding='utf-8'))
    source = json.loads((folder / 'app.json').read_text(encoding='utf-8'))
    package = folder / (app_id + '.tdapp')
    if not package.is_file():
        raise Bad('%s.tdapp is missing: run tools/build_apps.py' % app_id)
    data = package.read_bytes()
    manifest, raw, project = read_package(data)
    app = manifest.get('application', {})
    version = app.get('version', '')
    if not VERSION.match(version):
        raise Bad('application.version must be x.y.z')
    if source.get('name') != project.get('name') or source.get('application', {}).get('version') != version:
        raise Bad('app.json and the package differ: run tools/build_apps.py')
    runtime = manifest['runtime']
    needs = runtime.get('capabilities', [])
    if not set(needs) <= CAPABILITIES:
        raise Bad('unknown capability: %s' % sorted(set(needs) - CAPABILITIES))
    if meta.get('category') not in CATEGORIES:
        raise Bad('category must be one of %s' % sorted(CATEGORIES))
    native = runtime.get('native')
    repo = one_line(meta.get('repo'), 84, 'repo')
    if not repo.startswith('https://') or ' ' in repo:
        raise Bad('repo must be an https:// address')
    return {
        'id': app_id,
        'title': one_line(meta.get('title'), 40, 'title'),
        'version': version,
        'summary': one_line(meta.get('summary'), 160, 'summary'),
        'category': meta['category'],
        'file': app_id + '.tdapp',
        'size': len(data),
        'sha256': hashlib.sha256(data).hexdigest(),
        'cache': '.tdapp-' + hashlib.sha256(raw).hexdigest()[:16],
        'api': [1, runtime.get('apiMinor', 0)],
        'cells': int(project.get('board', 2000)),
        'needs': needs,
        'cpu': native['arch'] if native else None,
        'builder': manifest.get('studio'),
        'author': one_line(meta.get('author'), 40, 'author'),
        'repo': repo,
        'license': one_line(meta.get('license'), 16, 'license'),
    }


def catalog_text(apps):
    lines = ['TDSTORE 1']
    for a in apps:
        lines += ['app ' + a['id'], 'title ' + a['title'], 'version ' + a['version'], 'summary ' + a['summary'],
                  'category ' + a['category'], 'file ' + a['file'], 'size %d' % a['size'], 'sha256 ' + a['sha256'],
                  'cache ' + a['cache'], 'api %d.%d' % tuple(a['api']), 'cells %d' % a['cells']]
        if a['needs']:
            lines.append('needs ' + ' '.join(a['needs']))
        if a['cpu']:
            lines.append('cpu ' + a['cpu'])
        lines += ['author ' + a['author'], 'repo ' + a['repo'], 'license ' + a['license']]
        lines.append('end')
    for line in lines:
        assert len(line.encode()) <= 200, line
    return '\n'.join(lines) + '\n'


def page(apps):
    rows = ''.join('<tr><td><a href="%s">%s</a></td><td>%s</td><td>%s</td><td><a href="%s">%s</a> (%s)</td><td>%d KB</td></tr>\n' % (
        html.escape(a['file']), html.escape(a['title']), html.escape(a['version']), html.escape(a['summary']),
        html.escape(a['repo']), html.escape(a['author']), html.escape(a['license']), (a['size'] + 1023) // 1024) for a in apps)
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>TinyDesk apps</title></head><body>\n<h1>TinyDesk apps</h1>\n'
            '<p>App packages for TinyDesk. Install them with the Store app on the board, '
            'or download one and run it with <code>py NAME.tdapp</code>.</p>\n'
            '<table><tr><th>App</th><th>Version</th><th>What it is</th><th>By</th><th>Size</th></tr>\n%s</table>\n'
            '</body></html>\n' % rows)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--out', type=Path, default=ROOT / 'site')
    p.add_argument('--check', action='store_true', help='check only, write nothing')
    args = p.parse_args()
    apps, failed = [], False
    for folder in sorted(d for d in (ROOT / 'apps').iterdir() if d.is_dir()):
        try:
            apps.append(entry(folder))
        except (Bad, OSError, ValueError, KeyError) as e:
            print('apps/%s: %s' % (folder.name, e), file=sys.stderr)
            failed = True
    if failed:
        sys.exit(1)
    print('%d apps checked' % len(apps))
    if args.check:
        return
    if args.out.exists():
        shutil.rmtree(args.out)
    args.out.mkdir(parents=True)
    for a in apps:
        shutil.copyfile(ROOT / 'apps' / a['id'] / a['file'], args.out / a['file'])
    (args.out / 'index.json').write_text(json.dumps({'format': 1, 'apps': apps}, indent=1, ensure_ascii=False) + '\n',
                                         encoding='utf-8', newline='\n')
    (args.out / 'catalog.txt').write_text(catalog_text(apps), encoding='utf-8', newline='\n')
    (args.out / 'index.html').write_text(page(apps), encoding='utf-8', newline='\n')
    print('wrote', args.out)


if __name__ == '__main__':
    main()
