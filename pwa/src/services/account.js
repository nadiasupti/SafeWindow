// Accounts: email + password sign-in, and the role of the signed-in person.
//
//   government  a custom claim `role: "gov"`, set only by scripts/provision_government.py (the Admin SDK)
//   ngo         an ngo_members/{uid} document (created when an organisation applies, or by an invitation)
//   citizen     everybody else who is signed in
//
// The screens only choose what to SHOW from this. What a person may actually read or write is decided by
// firestore.rules on the server side: hiding a button is not security.
import {
  createUserWithEmailAndPassword, onAuthStateChanged, sendPasswordResetEmail, signInWithEmailAndPassword, signOut as fbSignOut,
} from 'firebase/auth'
import { doc, getDoc } from 'firebase/firestore'
import { useEffect, useState } from 'react'
import { auth, firestore } from './firebase.js'

export const signUp = (email, password) => createUserWithEmailAndPassword(auth(), email, password)
export const signIn = (email, password) => signInWithEmailAndPassword(auth(), email, password)
export const signOut = () => fbSignOut(auth())
export const resetPassword = (email) => sendPasswordResetEmail(auth(), email)

/** Reads the role, the organisation and the citizen profile for a user. */
export async function loadAccount(user) {
  const token = await user.getIdTokenResult(true)
  const db = firestore()
  const gov = token.claims.role === 'gov'
  let member = null
  let ngo = null
  let profile = null
  try {
    const m = await getDoc(doc(db, 'ngo_members', user.uid))
    if (m.exists()) {
      member = m.data()
      const n = await getDoc(doc(db, 'ngos', member.ngo_id))
      if (n.exists()) ngo = { id: n.id, ...n.data() }
    }
  } catch { /* offline or denied: the person is a plain citizen for now */ }
  try {
    const p = await getDoc(doc(db, 'users', user.uid))
    if (p.exists()) profile = p.data()
  } catch { /* same */ }
  return { gov, member, ngo, profile }
}

/**
 * { state: 'loading' | 'out' | 'in', user, gov, member, ngo, profile, reload }
 * `anonymous` is true for the phone-only identity used by village alerts: it is not an account.
 */
export function useAccount() {
  const [value, setValue] = useState({ state: 'loading' })
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let alive = true
    const stop = onAuthStateChanged(auth(), async (user) => {
      if (!user || user.isAnonymous) {
        if (alive) setValue({ state: 'out', user: null })
        return
      }
      const info = await loadAccount(user)
      if (alive) setValue({ state: 'in', user, ...info })
    })
    return () => {
      alive = false
      stop()
    }
  }, [tick])
  return { ...value, reload: () => setTick((n) => n + 1) }
}

/** Plain-language key for a Firebase sign-in error. */
export function authErrorKey(error) {
  const code = String(error?.code || '')
  if (code.includes('invalid-credential') || code.includes('wrong-password') || code.includes('user-not-found')) return 'rp_auth_bad_login'
  if (code.includes('email-already-in-use')) return 'rp_auth_exists'
  if (code.includes('weak-password')) return 'rp_auth_weak'
  if (code.includes('invalid-email')) return 'rp_auth_email'
  if (code.includes('operation-not-allowed') || code.includes('configuration-not-found')) return 'rp_auth_not_enabled'
  if (code.includes('network') || code.includes('timeout')) return 'rp_err_network'
  if (code.includes('too-many-requests')) return 'rp_auth_many'
  return 'rp_err_generic'
}
