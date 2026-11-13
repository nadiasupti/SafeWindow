import { LifeBuoy, LogIn, LogOut, Shield, Users } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ErrorLine, PrototypeNotice } from '../components/RescueBits.jsx'
import PageHead from '../components/PageHead.jsx'
import { useT } from '../i18n/language.js'
import { authErrorKey, resetPassword, signIn, signOut, signUp, useAccount } from '../services/account.js'

function SignInForm() {
  const t = useT()
  const [mode, setMode] = useState('in')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [info, setInfo] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setInfo(null)
    try {
      await (mode === 'in' ? signIn(email.trim(), password) : signUp(email.trim(), password))
    } catch (err) {
      setError(authErrorKey(err))
    } finally {
      setBusy(false)
    }
  }

  async function forgot() {
    setError(null)
    try {
      await resetPassword(email.trim())
      setInfo('rp_auth_reset_sent')
    } catch (err) {
      setError(authErrorKey(err))
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <div className="seg-row" role="tablist">
        <button type="button" className={mode === 'in' ? 'chip on' : 'chip'} role="tab" aria-selected={mode === 'in'} onClick={() => setMode('in')}>{t('rp_sign_in')}</button>
        <button type="button" className={mode === 'up' ? 'chip on' : 'chip'} role="tab" aria-selected={mode === 'up'} onClick={() => setMode('up')}>{t('rp_create_account')}</button>
      </div>
      <label className="field">
        <span>{t('rp_email')}</span>
        <input type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
      </label>
      <label className="field">
        <span>{t('rp_password')}</span>
        <input type="password" autoComplete={mode === 'in' ? 'current-password' : 'new-password'} minLength={6} value={password}
          onChange={(e) => setPassword(e.target.value)} required />
      </label>
      <ErrorLine keyName={error} />
      {info && <p className="muted" role="status">{t(info)}</p>}
      <button className="btn wide" type="submit" disabled={busy}><LogIn size={18} aria-hidden="true" /> {mode === 'in' ? t('rp_sign_in') : t('rp_create_account')}</button>
      {mode === 'in' && <button type="button" className="btn link" onClick={forgot} disabled={!email}>{t('rp_forgot')}</button>}
      <p className="muted small">{t('rp_account_why')}</p>
    </form>
  )
}

export default function AccountPage() {
  const t = useT()
  const account = useAccount()
  return (
    <>
      <PageHead Icon={Users} title={t('rp_account_title')} sub={t('rp_account_sub')} />
      <PrototypeNotice />
      {account.state === 'loading' && <p className="muted">{t('loading')}</p>}
      {account.state === 'out' && <SignInForm />}
      {account.state === 'in' && (
        <div className="card">
          <div className="profile-head">
            <span className="profile-avatar" aria-hidden="true">{(account.user.email || '?').trim()[0].toUpperCase()}</span>
            <div>
              <p className="profile-email"><strong>{account.user.email}</strong></p>
              <p className="muted small">
                {account.gov ? t('rp_role_gov') : account.member ? t('rp_role_ngo') : t('rp_role_citizen')}
                {account.ngo?.name ? ` · ${account.ngo.name}` : ''}
              </p>
            </div>
          </div>
          <div className="row">
            <Link className="btn" to="/rescue"><LifeBuoy size={18} aria-hidden="true" /> {t('rp_open_citizen')}</Link>
            <Link className="btn secondary" to="/ngo"><Users size={18} aria-hidden="true" /> {t('rp_open_ngo')}</Link>
            {account.gov && <Link className="btn secondary" to="/gov"><Shield size={18} aria-hidden="true" /> {t('rp_open_gov')}</Link>}
          </div>
          <button type="button" className="btn link" onClick={signOut}><LogOut size={18} aria-hidden="true" /> {t('rp_sign_out')}</button>
        </div>
      )}
    </>
  )
}
