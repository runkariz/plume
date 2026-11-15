// Checks the built model view and copies it to where Plume serves it (src/plume/interfaces/mcp/apps/model-view.html).
import { Buffer } from 'node:buffer';
import { copyFileSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const built = resolve(here, '../dist-widget/widget.html');
const target = resolve(here, '../../src/plume/interfaces/mcp/apps/model-view.html');
const html = readFileSync(built, 'utf8');

const problems = [];
// nothing may load from outside: the host's CSP blocks it anyway, and a stray reference would be a broken view
if (/<(script|link|img|iframe|source)[^>]+(src|href)="(?!data:|#)[^"]*"/i.test(html))
  problems.push('an element refers to a file or URL');
if (/url\(\s*(?!["']?(?:data:|#))/i.test(html)) problems.push('a CSS url() is not a data: URL');
if (/@import/i.test(html)) problems.push('a CSS @import');
if (/@font-face|font\/woff/i.test(html))
  problems.push('a font file: the host CSP has no font-src, it would be blocked');
if (!html.includes('ui/initialize')) problems.push('the handshake is missing');
if (!/<script type="module">/.test(html)) problems.push('the script is not inline');
const size = Buffer.byteLength(html);
if (size > 3_000_000) problems.push(`the file is ${size} bytes, over the 3 MB limit`);
if (problems.length) {
  process.stderr.write(`widget check failed:\n- ${problems.join('\n- ')}\n`);
  process.exit(1);
}
copyFileSync(built, target);
process.stdout.write(
  `model view: ${(size / 1024).toFixed(0)} KiB -> ${target.replace(resolve(here, '../..') + '/', '')}\n`,
);
