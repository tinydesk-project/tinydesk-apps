/* Turn an App Builder project into what its Export app button sends to the
 * package builder: the stamped project, the generated Python and the
 * resource paths. Uses App Builder's own generator (no second copy).
 *
 *   node tools/export.cjs BUILDER_DIR apps/<id>/app.json  > export.json
 */
'use strict';
const fs = require('node:fs'), path = require('node:path');
const [builder, input] = process.argv.slice(2);
if (!builder || !input) throw Error('Usage: node tools/export.cjs BUILDER_DIR PROJECT.json');
const TD = require(path.resolve(builder, 'core.js'));
const V = require(path.resolve(builder, 'version.js'));
const R = require(path.resolve(builder, 'resources.js'));
const design = V.stamp(TD.parse(fs.readFileSync(input, 'utf8')));
const check = TD.validate(design);
if (check.errors.length) throw Error(check.errors.join('\n'));
// The catalog serves boards with TinyDesk 0.2.x, which have no tdapp library:
// keep the self-contained export (App Builder 0.13+ imports tdapp by
// default). Set TDAPP_LIBRARY=1 once the catalog requires TinyDesk 0.3.
const source = TD.generate(design, {bundle: true, embedRuntime: process.env.TDAPP_LIBRARY !== '1'});
process.stdout.write(JSON.stringify({project: design, source,
                                     paths: [...R.required(design).values()]}));
