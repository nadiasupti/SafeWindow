import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// Installable, offline-capable app with village alerts (app plan, steps 1চ and 2).
// The service worker is our own (src/sw.js): offline caching plus Firebase Cloud Messaging.
// Satellite tiles are never cached.
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw.js',
      registerType: 'autoUpdate',
      includeAssets: ['icons/favicon-64.png', 'icons/apple-touch-icon.png', 'brand/logo-header.png'],
      manifest: {
        name: 'SafeWindow',
        short_name: 'SafeWindow',
        description: 'Village road access during floods. Research prototype, not an official warning.',
        lang: 'bn',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        orientation: 'portrait',
        background_color: '#F3F6F8',
        theme_color: '#FFFFFF',
        icons: [
          { src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: 'icons/maskable-192.png', sizes: '192x192', type: 'image/png', purpose: 'maskable' },
          { src: 'icons/maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      injectManifest: {
        globPatterns: ['**/*.{js,css,html,svg,woff2}', 'icons/*.png', 'brand/*.png'],
        globIgnores: ['data/**'],
      },
    }),
  ],
})
