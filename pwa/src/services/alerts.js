// Village alerts: subscribe this phone to one village, and receive alerts while the app is open.
// Privacy: no account or login for the user. Firebase gives an anonymous id, and Firestore keeps only
// subscriptions/{id} = {token, flood, village, lang, updated}. The phone's location never leaves it.
//
// The subscription is written with one plain HTTPS request (Firestore REST) instead of the Firestore
// SDK: the SDK's streaming connection sometimes took minutes to make its first write.
import { getApp, getApps, initializeApp } from 'firebase/app'
import { getAuth, signInAnonymously } from 'firebase/auth'
import { deleteToken, getMessaging, getToken, isSupported, onMessage } from 'firebase/messaging'
import { VAPID_KEY, firebaseConfig } from '../firebaseConfig.js'
import { alertFromData, saveAlert } from '../lib/alertStore.js'

const DOCS = `https://firestore.googleapis.com/v1/projects/${firebaseConfig.projectId}/databases/(default)/documents`
const TIMEOUT_MS = 60000         // a phone's first push registration can take a while

let app
function firebase() {
  // one shared Firebase app: the account code (services/firebase.js) may have started it first
  app = app || (getApps().length ? getApp() : initializeApp(firebaseConfig))
  return app
}

/** 'ready' | 'not_configured' (no web push key yet) | 'unsupported' (browser cannot receive push). */
export async function alertsAvailability() {
  if (!VAPID_KEY) return 'not_configured'
  if (!('Notification' in window) || !('serviceWorker' in navigator) || !(await isSupported())) return 'unsupported'
  return 'ready'
}

async function anonymousUser() {
  const auth = getAuth(firebase())
  return auth.currentUser || (await signInAnonymously(auth)).user
}

/** A promise that gives up after TIMEOUT_MS, so a button never spins for ever. */
function inTime(promise) {
  return Promise.race([promise, new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), TIMEOUT_MS))])
}

async function firestore(user, method, path, body) {
  const response = await fetch(`${DOCS}/${path}`, {
    method,
    headers: { Authorization: `Bearer ${await user.getIdToken()}`, 'Content-Type': 'application/json' },
    body: body && JSON.stringify(body),
  })
  if (!response.ok) throw new Error(`firestore ${response.status}`)
}

/** The service worker once it is fully active: push subscription waits for that state. */
async function activeRegistration() {
  const registration = await navigator.serviceWorker.ready
  const worker = registration.active
  if (worker && worker.state !== 'activated') {
    await new Promise((resolve) => {
      worker.addEventListener('statechange', () => worker.state === 'activated' && resolve())
    })
  }
  return registration
}

/** Ask permission, get this phone's push token and store the subscription. Returns the anonymous id. */
export async function subscribe({ flood, village, lang }) {
  if ((await Notification.requestPermission()) !== 'granted') throw new Error('permission')
  return inTime((async () => {
    const registration = await activeRegistration()
    const token = await getToken(getMessaging(firebase()), { vapidKey: VAPID_KEY, serviceWorkerRegistration: registration })
    const user = await anonymousUser()
    const name = `projects/${firebaseConfig.projectId}/databases/(default)/documents/subscriptions/${user.uid}`
    // "updated" is set to the server's time, as firestore.rules requires
    await commit(user, {
      update: {
        name,
        fields: {
          token: { stringValue: token }, flood: { stringValue: flood },
          village: { stringValue: village }, lang: { stringValue: lang },
        },
      },
      updateTransforms: [{ fieldPath: 'updated', setToServerValue: 'REQUEST_TIME' }],
    })
    return user.uid
  })())
}

async function commit(user, write) {
  const response = await fetch(`${DOCS}:commit`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${await user.getIdToken()}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ writes: [write] }),
  })
  if (!response.ok) throw new Error(`firestore ${response.status}`)
}

/** Stop alerts: remove the subscription and the push token. */
export async function unsubscribe() {
  await inTime((async () => {
    const user = await anonymousUser()
    await firestore(user, 'DELETE', `subscriptions/${user.uid}`)
    try {
      await deleteToken(getMessaging(firebase()))
    } catch {
      // the token may already be gone
    }
  })())
}

/** This phone's anonymous id, shown in Settings so it can be registered as a test phone. */
export async function deviceId() {
  return (await anonymousUser()).uid
}

/** Alerts that arrive while the app is open: stored like background ones, then passed to `onAlert`. */
export async function listenInApp(onAlert) {
  if ((await alertsAvailability()) !== 'ready') return () => {}
  return onMessage(getMessaging(firebase()), async ({ data }) => {
    if (!data?.id) return
    const alert = alertFromData(data)
    await saveAlert(alert)
    onAlert(alert)
  })
}
