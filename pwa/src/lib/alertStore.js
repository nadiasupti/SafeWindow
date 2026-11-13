// Alerts received on this phone, kept in IndexedDB so the last ones can be read offline.
// Used by both the app and the service worker (src/sw.js).
const DB = 'safewindow'
const STORE = 'alerts'
const KEEP = 20

function open() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1)
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: 'id' })
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

function done(tx) {
  return new Promise((resolve, reject) => {
    tx.oncomplete = resolve
    tx.onerror = () => reject(tx.error)
  })
}

/** All stored alerts, newest first. */
export async function listAlerts() {
  const db = await open()
  const all = await new Promise((resolve, reject) => {
    const req = db.transaction(STORE).objectStore(STORE).getAll()
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
  return all.sort((a, b) => (b.sent_at || '').localeCompare(a.sent_at || ''))
}

/** Store one alert and keep only the newest ones. */
export async function saveAlert(alert) {
  const db = await open()
  const tx = db.transaction(STORE, 'readwrite')
  tx.objectStore(STORE).put(alert)
  await done(tx)
  const old = (await listAlerts()).slice(KEEP)
  if (old.length) {
    const clean = db.transaction(STORE, 'readwrite')
    old.forEach((a) => clean.objectStore(STORE).delete(a.id))
    await done(clean)
  }
}

/** An FCM data message -> the alert record the app shows. */
export function alertFromData(data) {
  return {
    id: data.id, level: data.level, flood: data.flood, village: data.village,
    title: data.title, body: data.body, simulation: data.simulation === '1', cancelled: data.cancelled === '1',
    sent_at: data.sent_at, expires_at: data.expires_at, link: data.link, kind: data.kind || 'village',
  }
}

/** An admin notice ("alerts wait for approval") is shown on the admin's phone but never kept as a village alert. */
export function isAdminNotice(alert) {
  return alert.kind === 'admin'
}

/** Notifications for one village replace each other; admin notices replace each other. */
export function notificationTag(alert) {
  return isAdminNotice(alert) ? 'safewindow-admin' : `${alert.flood}-${alert.village}`
}

export function isActive(alert, now = new Date()) {
  return !alert.cancelled && (!alert.expires_at || new Date(alert.expires_at) > now)
}

/** Fired on window when an alert arrives while the app is open (components/AlertListener.jsx). */
export const ALERT_EVENT = 'safewindow:alert'

/** Remove every stored alert from this phone. */
export async function clearAlerts() {
  const db = await open()
  const tx = db.transaction(STORE, 'readwrite')
  tx.objectStore(STORE).clear()
  await done(tx)
}

// "Seen" marker for the bell's count: alerts sent after it are new.
const SEEN_KEY = 'safewindow.alerts_seen'

export function lastSeen() {
  try {
    return localStorage.getItem(SEEN_KEY) || ''
  } catch {
    return ''
  }
}

export function markSeen(iso = new Date().toISOString()) {
  try {
    localStorage.setItem(SEEN_KEY, iso)
  } catch {
    // the count simply is not remembered
  }
  window.dispatchEvent(new CustomEvent(ALERT_EVENT))
}
