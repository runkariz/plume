import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';

/**
 * The model view for MCP Apps: ONE html file with the script, the styles and the fonts inlined (the host's default
 * CSP is default-src 'none'; script/style 'unsafe-inline'; img/media data: only; connect-src 'none').
 * `npm run build:widget` builds it and scripts/finish-widget.mjs checks it and copies it where Plume serves it.
 */
function inlineIntoHtml(): Plugin {
  return {
    name: 'plume-inline-widget',
    enforce: 'post',
    generateBundle(_options, bundle) {
      const htmlFile = bundle['widget.html'];
      if (!htmlFile || htmlFile.type !== 'asset') throw new Error('widget.html was not built');
      let html = String(htmlFile.source);
      for (const [name, file] of Object.entries(bundle)) {
        if (name === 'widget.html') continue;
        const ref = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        if (file.type === 'chunk') {
          // a script must not contain "</script" or "<!--" (they would end or change the element)
          const code = file.code.replace(/<\/(script)/gi, '<\\/$1').replace(/<!--/g, '<\\!--');
          html = html.replace(
            new RegExp(`<script[^>]*src="[^"]*${ref}"[^>]*></script>`),
            () => `<script type="module">${code}</script>`,
          );
        } else if (name.endsWith('.css')) {
          const css = String(file.source).replace(/<\/(style)/gi, '<\\/$1');
          html = html.replace(
            new RegExp(`<link[^>]*href="[^"]*${ref}"[^>]*>`),
            () => `<style>${css}</style>`,
          );
        } else {
          continue;
        }
        Reflect.deleteProperty(bundle, name);
      }
      htmlFile.source = html;
    },
  };
}

export default defineConfig({
  plugins: [react(), inlineIntoHtml()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      '@fonts': fileURLToPath(new URL('./node_modules/@fontsource-variable', import.meta.url)),
    },
  },
  build: {
    outDir: 'dist-widget',
    emptyOutDir: true,
    assetsInlineLimit: 100_000_000, // fonts and any image become data: URLs
    cssCodeSplit: false,
    modulePreload: false,
    rollupOptions: { input: fileURLToPath(new URL('./widget.html', import.meta.url)) },
  },
});
