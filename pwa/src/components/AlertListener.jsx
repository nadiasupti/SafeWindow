import { useEffect } from 'react'
import { ALERT_EVENT } from '../lib/alertStore.js'
import { listenInApp } from '../services/alerts.js'

/**
 * While the app is open, Firebase hands alerts to the page instead of showing them. This listener runs on every
 * screen: it keeps the alert (listenInApp stores it), shows the system notification anyway, and tells the alert
 * card to refresh.
 */
export default function AlertListener() {
  useEffect(() => {
    let stop = () => {}
    let alive = true
    listenInApp(async (alert) => {
      try {
        const registration = await navigator.serviceWorker.ready
        await registration.showNotification(alert.title, {
          body: alert.body, icon: '/icons/icon-192.png', badge: '/icons/maskable-192.png',
          tag: `${alert.flood}-${alert.village}`, renotify: true, data: { link: alert.link },
        })
      } catch {
        // no permission to show it: the alert card still has it
      }
      window.dispatchEvent(new CustomEvent(ALERT_EVENT))
    }).then((unsubscribe) => {
      if (alive) stop = unsubscribe
      else unsubscribe()
    })
    return () => {
      alive = false
      stop()
    }
  }, [])
  return null
}
