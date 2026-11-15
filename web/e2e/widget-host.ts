import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * An offline stand-in for an MCP Apps host (Claude web / Desktop): the model view runs in an iframe sandboxed with
 * allow-scripts only (an opaque origin, no storage), under the spec's DEFAULT CSP, and talks JSON-RPC over
 * postMessage: it answers ui/initialize, waits for ui/notifications/initialized, then sends the tool result.
 */
export const CSP =
  "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' data:; object-src 'none'; connect-src 'none'";

const here = fileURLToPath(new URL('.', import.meta.url));
export const widgetHtml = (): string => {
  try {
    return readFileSync(resolve(here, '../dist-widget/widget.html'), 'utf8');
  } catch {
    throw new Error('dist-widget/widget.html is missing: run `npm run build:widget` first');
  }
};
export const realOrder = (): Record<string, unknown> =>
  JSON.parse(readFileSync(resolve(here, '../src/mocks/fixtures/realOrder40.json'), 'utf8'));

const js = (v: unknown) => JSON.stringify(v).replace(/<\//g, '<\\/');

export function hostPage(opts: {
  widget: string;
  theme: 'light' | 'dark';
  result: unknown;
  width?: number;
  openLinks?: boolean;
  variables?: Record<string, string>;
}) {
  const srcdoc = opts.widget.replace(
    '<head>',
    `<head><meta http-equiv="Content-Security-Policy" content="${CSP}">`,
  );
  const bg = opts.theme === 'dark' ? '#1b1b1d' : '#f4f4f5';
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Stand-in MCP Apps host</title></head><body style="margin:0;background:${bg};padding:16px">
<iframe id="app" title="Plume model view" sandbox="allow-scripts" style="width:${opts.width ?? 760}px;height:120px;border:1px solid #888;border-radius:8px;background:transparent"></iframe>
<script>
const frame = document.getElementById('app');
window.__log = [];
window.__opened = [];
window.__sizes = [];
const reply = (id, result) => frame.contentWindow.postMessage({ jsonrpc: '2.0', id, result }, '*');
window.addEventListener('message', (e) => {
  if (e.source !== frame.contentWindow) return;
  const m = e.data;
  window.__log.push(m.method || ('result:' + m.id));
  if (m.method === 'ui/initialize') reply(m.id, {
    protocolVersion: '2026-01-26', hostInfo: { name: 'plume-test-host', version: '0' },
    hostCapabilities: ${opts.openLinks ? '{ openLinks: {} }' : '{}'},
    hostContext: { theme: ${js(opts.theme)}, displayMode: 'inline', locale: 'en-US', styles: { variables: ${js(opts.variables ?? {})} } } });
  if (m.method === 'ui/notifications/initialized') frame.contentWindow.postMessage({ jsonrpc: '2.0', method: 'ui/notifications/tool-result', params: ${js(opts.result)} }, '*');
  if (m.method === 'ui/open-link') { window.__opened.push(m.params.url); reply(m.id, {}); }
  if (m.method === 'ui/notifications/size-changed') { window.__sizes.push(m.params.height); frame.style.height = (m.params.height + 2) + 'px'; }
});
window.__send = (msg) => frame.contentWindow.postMessage(msg, '*');
frame.srcdoc = ${js(srcdoc)};
</script></body></html>`;
}
