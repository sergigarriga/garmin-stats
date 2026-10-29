import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { viteSingleFile } from 'vite-plugin-singlefile';

// Todo en un único index.html (JS, CSS y fuentes dentro) para que funcione abriéndolo
// como archivo, sin servidor. Los datos van aparte en site/data.js (los escribe Python).
const BUILD_ID = String(Date.now());

export default defineConfig(({ command }) => ({
  base: './',
  // Identificador de esta compilación: Python lo copia a data.js y la página se recarga sola
  // si detecta que hay una versión nueva del HTML.
  define: { __BUILD_ID__: JSON.stringify(BUILD_ID) },
  plugins: [
    react(),
    viteSingleFile(),
    { name: 'build-id', transformIndexHtml: (html) => html.replace('</head>', `<meta name="app-build" content="${BUILD_ID}" /></head>`) },
  ],
  publicDir: command === 'serve' ? 'public' : false,
  build: {
    outDir: '../site',
    emptyOutDir: false,
    chunkSizeWarningLimit: 4000,
  },
}));
