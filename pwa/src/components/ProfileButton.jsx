import { getApp, getApps, initializeApp } from 'firebase/app'
import { getAuth, onAuthStateChanged } from 'firebase/auth'
import { Shield, UserRound } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { firebaseConfig } from '../firebaseConfig.js'
import { useT } from '../i18n/language.js'

// The profile button next to the alert bell: "sign in" when nobody is signed in, the person's initial (and a shield
// for a government account) when they are. It opens /account, which shows the profile or the sign-in form.
//
// Only Firebase Auth is used here, which the village-alert code already ships in the main file, so the button adds
// almost nothing to the app's first download (the account pages themselves still load only when opened). Only the
// sign-in state and the role claim are read (no database read): what a person may do is decided by firestore.rules.

function useSignedIn() {
  const [who, setWho] = useState({ state: 'loading' })
  useEffect(() => {
    let alive = true
    const app = getApps().length ? getApp() : initializeApp(firebaseConfig)
    const stop = onAuthStateChanged(getAuth(app), async (user) => {
      if (!user || user.isAnonymous) {
        if (alive) setWho({ state: 'out' })
        return
      }
      let gov = false
      try {
        gov = (await user.getIdTokenResult()).claims.role === 'gov'
      } catch { /* offline: the role is shown on the account page when it can be read */ }
      if (alive) setWho({ state: 'in', email: user.email || '', gov })
    })
    return () => {
      alive = false
      stop()
    }
  }, [])
  return who
}

export default function ProfileButton() {
  const t = useT()
  const who = useSignedIn()
  const signedIn = who.state === 'in'
  const label = signedIn
    ? t('profile_signed_in', { email: who.email, role: t(who.gov ? 'rp_role_gov' : 'profile_role_account') })
    : t('profile_sign_in')
  const initial = signedIn ? (who.email.trim()[0] || '?').toUpperCase() : null
  return (
    <Link to="/account" className={signedIn ? 'profile-btn in' : 'profile-btn'} aria-label={label} title={label}>
      {signedIn ? <span className="profile-initial" aria-hidden="true">{initial}</span>
        : <UserRound size={22} aria-hidden="true" />}
      {signedIn && who.gov && <span className="profile-badge" aria-hidden="true"><Shield size={11} /></span>}
    </Link>
  )
}
