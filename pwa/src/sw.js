// SafeWindow service worker: offline app + village alerts (app plan, steps 1চ and 2).
// Bundled by vite-plugin-pwa (injectManifest), so Firebase and Workbox come from our own build, not a CDN.
import { initializeApp } from 'firebase/app'
import { getMessaging, onBackgroundMessage } from 'firebase/messaging/sw'
import { clientsClaim } from 'workbox-core'
import { cleanupOutdatedCaches, createHandlerBoundToURL, precacheAndRoute } from 'workbox-precaching'
import { NavigationRoute, registerRoute } from 'workbox-routing'
import { NetworkFirst } from 'workbox-strategies'
import { firebaseConfig } from './firebaseConfig.js'
import { alertFromData, saveAlert } from './lib/alertStore.js'

self.skipWaiting()
clientsClaim()

// 1. The app shell (code, fonts, icons): stored on first visit.
precacheAndRoute(self.__WB_MANIFEST)
cleanupOutdatedCaches()
registerRoute(new NavigationRoute(createHandlerBoundToURL('index.html'), { denylist: [/^\/data\//] }))

// 2. Flood data: the network when there is one, else the copy on the phone. The app's
//    "download this area" button (src/services/offline.js) fills the same cache.
registerRoute(
  ({ url }) => url.origin === self.location.origin && url.pathname.startsWith('/data/'),
  new NetworkFirst({ cacheName: 'safewindow-data', networkTimeoutSeconds: 4 }),
)

// 3. Alerts. Messages are data-only, so this code decides what is shown and keeps a copy for offline.
const messaging = getMessaging(initializeApp(firebaseConfig))
onBackgroundMessage(messaging, async ({ data }) => {
  if (!data?.id) return
  const alert = alertFromData(data)
  await saveAlert(alert)
  await self.registration.showNotification(alert.title, {
    body: alert.body,
    icon: '/icons/icon-192.png',
    badge: '/icons/maskable-192.png',
    tag: `${alert.flood}-${alert.village}`,      // a newer alert for the same village replaces the old one
    renotify: true,
    data: { link: alert.link },
  })
})

// Tapping the notification opens that village's page.
self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const link = event.notification.data?.link || '/'
  event.waitUntil((async () => {
    const tabs = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    const open = tabs.find((c) => new URL(c.url).origin === self.location.origin)
    if (open) {
      await open.navigate(link)
      return open.focus()
    }
    return self.clients.openWindow(link)
  })())
})
