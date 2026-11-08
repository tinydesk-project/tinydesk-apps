# TinyDesk apps

App packages (`.tdapp`) for [TinyDesk](https://github.com/tinydesk-project/tinydesk),
with their sources. TinyDesk's **Store** app lists them and installs them
on a board; each package also runs on its own with `py NAME.tdapp`.

The catalog is published with GitHub Pages at
`https://tinydesk-project.github.io/tinydesk-apps/`:

| File | For |
| --- | --- |
| `catalog.txt` | the Store app (one `key value` per line; format in `tools/make_index.py`) |
| `index.json` | people and web pages: the same entries as JSON |
| `<id>.tdapp` | the packages |
| `index.html` | a plain list |

## An app's folder

```
apps/<id>/
  app.json        the app's project: the source
  app.py          the Python generated from it (for reading)
  store.json      title, summary and category shown in the Store
  <id>.tdapp      the package, built from app.json
  (pictures, modules)  files the project names
```

`<id>` is the app's name in the Store and on the board: lowercase letters,
digits, `_` and `-`, up to 31 characters. `store.json`:

```json
{"title": "Device monitor", "summary": "One line, up to 160 bytes.", "category": "Examples"}
```

Categories: Examples, Tools, Games, Industrial, Education. The version is
the project's `application.version` (x.y.z); raise it for every change, so
boards offer the update.

## Checking

`make_index.py` needs only Python 3: it checks every package (format,
every entry's SHA-256, that it matches `app.json`) and writes the site
into `site/`. CI runs the check on every push and pull request, and
publishes the site from `main`.

```bash
python tools/make_index.py
```

The packages are built with TinyDesk's app tools and `mpy-cross` 1.29
(`tools/build_apps.py`); the tools are published later.

## What a board checks

The Store installs an app only if the board can run it: the tdui API
(`api`), the canvas cells (`cells`: 2000 runs on every board, more needs
PSRAM), capabilities such as `rgb_pictures` (`needs`) and, for native
code, the CPU (`cpu`). It downloads into `~/Apps`, checks the size and
SHA-256 before keeping the file, and adds the app to the user's Start menu.
SHA-256 catches damaged downloads; it is not a signature. The catalog is
fetched over HTTPS.

## Adding an app

New apps can be proposed once TinyDesk's app tools are published. Only
apps whose sources are in this repository are accepted.

## Licence

MIT, see [LICENSE](LICENSE), for the tools and the apps unless an app's
folder says otherwise.
