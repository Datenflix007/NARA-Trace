import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';

const textMarkerViewer = fileURLToPath(
  new URL('../../TS_TextMarkerViewer/dist/ts-text-marker-viewer.js', import.meta.url)
);
const textMarkerCore = fileURLToPath(new URL('../../TS_TextMarkerCore/dist/index.js', import.meta.url));

export default defineConfig({
  plugins: [svelte()],
  resolve: {
    conditions: ['browser'],
    alias: {
      '@datenflix/ts-text-marker-viewer': textMarkerViewer,
      '@datenflix007/ts-text-marker-core': textMarkerCore
    }
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    fs: {
      allow: [fileURLToPath(new URL('../..', import.meta.url))]
    },
    proxy: {
      '/api': 'http://127.0.0.1:8765'
    }
  },
  preview: {
    host: '127.0.0.1'
  },
  test: {
    environment: 'jsdom'
  }
});
