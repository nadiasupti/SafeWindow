// One shared Firebase app for the accounts and the rescue platform (Auth + Firestore).
// The village-alert code (alerts.js) keeps its own plain-HTTPS path and is not changed.
//
// Firestore uses long polling: the default streaming connection was slow to start on weak mobile networks.
//
// VITE_EMULATORS=1 (set only by the local end-to-end test, never in a production build) points Auth and Firestore
// at the local Firebase emulators, so the whole flow can be tried without touching the real project.
import { getApp, getApps, initializeApp } from 'firebase/app'
import { connectAuthEmulator, getAuth } from 'firebase/auth'
import { connectFirestoreEmulator, getFirestore, initializeFirestore } from 'firebase/firestore'
import { firebaseConfig } from '../firebaseConfig.js'

const EMULATORS = import.meta.env.VITE_EMULATORS === '1'
let authInstance
let db

export function app() {
  if (getApps().length) return getApp()
  // In emulator mode the project id is a fake "demo-" one, so nothing can ever reach the real project.
  return initializeApp(EMULATORS ? { ...firebaseConfig, projectId: 'demo-safewindow', apiKey: 'fake-api-key' } : firebaseConfig)
}

export function auth() {
  if (!authInstance) {
    authInstance = getAuth(app())
    if (EMULATORS) connectAuthEmulator(authInstance, 'http://127.0.0.1:9099', { disableWarnings: true })
  }
  return authInstance
}

export function firestore() {
  if (!db) {
    try {
      db = initializeFirestore(app(), { experimentalForceLongPolling: true })
      if (EMULATORS) connectFirestoreEmulator(db, '127.0.0.1', 8080)
    } catch {
      db = getFirestore(app())      // already initialised (hot reload)
    }
  }
  return db
}
