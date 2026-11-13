import { LifeBuoy, LocateFixed, Phone, Send } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import PageHead from '../components/PageHead.jsx'
import { CheckGroup, ErrorLine, PriorityPill, PrototypeNotice, ReasonButton, StatusPill, When } from '../components/RescueBits.jsx'
import { useLanguage, useT } from '../i18n/language.js'
import { errorKey } from '../lib/errors.js'
import { getPosition } from '../lib/gps.js'
import { FLAGS, HAZARDS, NEEDS, newId, validateRequest } from '../lib/rescue.js'
import { useLoader } from '../lib/useLoader.js'
import { useAccount } from '../services/account.js'
import { cancelRequest, confirmOutcome, myRequests, saveProfile, submitRequest, timeline } from '../services/rescue.js'
import { useAppState } from '../state/appState.js'

/** The emergency number comes first: this prototype does not call anybody for you. */
function EmergencyBanner() {
  const t = useT()
  const { lang } = useLanguage()
  const contacts = useAppState().flood?.metadata?.emergency_contacts || []
  const first = contacts[0] || { name: 'Emergency', number: '112' }
  return (
    <div className="card danger-card" role="note">
      <p><strong>{t('rp_call_first')}</strong></p>
      <a className="btn call" href={`tel:${first.number}`}>
        <Phone size={18} aria-hidden="true" /> {first[`name_${lang}`] || first.name}: <strong>{first.number}</strong>
      </a>
    </div>
  )
}

function ProfileForm({ account, onSaved }) {
  const t = useT()
  const { lang } = useLanguage()
  const [form, setForm] = useState({ name: '', phone: '', assistance_profile: 'self_evacuation', lang })
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  async function submit(e) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await saveProfile(account.user.uid, form, account.profile)
      onSaved()
    } catch (err) {
      setError(errorKey(err))
    } finally {
      setBusy(false)
    }
  }
  return (
    <form className="card" onSubmit={submit}>
      <h2>{t('rp_profile_title')}</h2>
      <label className="field"><span>{t('rp_name')}</span>
        <input type="text" value={form.name} maxLength={80} required onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
      <label className="field"><span>{t('rp_phone')}</span>
        <input type="tel" inputMode="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label>
      <fieldset className="checks">
        <legend>{t('rp_assist_profile')}</legend>
        {['self_evacuation', 'needs_assistance'].map((v) => (
          <label key={v} className="check">
            <input type="radio" name="assist" checked={form.assistance_profile === v} onChange={() => setForm({ ...form, assistance_profile: v })} />
            <span>{t(`rp_profile_${v}`)}</span>
          </label>
        ))}
        <p className="muted small">{t('rp_profile_note')}</p>
      </fieldset>
      <ErrorLine keyName={error} />
      <button className="btn wide" type="submit" disabled={busy}>{t('rp_save')}</button>
    </form>
  )
}

const EMPTY = {
  latitude: '', longitude: '', accuracy_m: '', location_source: 'manual', address_text: '', people_count: 1, urgency: 'immediate',
  needs: {}, hazards: [], vulnerability_flags: {}, phone: '', notes: '', consent_location: true, consent_sensitive: false,
}

function RequestForm({ account, onSent }) {
  const t = useT()
  const [form, setForm] = useState({ ...EMPTY, phone: account.profile?.phone || '' })
  const [id] = useState(() => newId('rr'))               // one id per form: a retry cannot make a second request
  const [errors, setErrors] = useState({})
  const [fail, setFail] = useState(null)
  const [gpsNote, setGpsNote] = useState(null)
  const [busy, setBusy] = useState(false)
  const set = (patch) => setForm((f) => ({ ...f, ...patch }))

  async function useGps() {
    setGpsNote('rp_gps_wait')
    try {
      const p = await getPosition()
      set({ latitude: p.lat.toFixed(5), longitude: p.lon.toFixed(5), accuracy_m: Math.round(p.accuracy), location_source: 'gps' })
      setGpsNote('rp_gps_ok')
    } catch {
      setGpsNote('rp_gps_fail')
    }
  }

  async function submit(e) {
    e.preventDefault()
    const found = validateRequest(form)
    setErrors(found)
    if (Object.keys(found).length) return
    setBusy(true)
    setFail(null)
    try {
      await submitRequest(account.user.uid, form, id)
      onSent(id)
    } catch (err) {
      setFail(errorKey(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card" onSubmit={submit} noValidate>
      <h2><LifeBuoy size={20} aria-hidden="true" /> {t('rp_request_title')}</h2>
      <p className="muted small">{t('rp_location_why')}</p>
      <div className="row">
        <button type="button" className="btn secondary" onClick={useGps}><LocateFixed size={18} aria-hidden="true" /> {t('rp_use_gps')}</button>
      </div>
      {gpsNote && <p className="muted small" role="status">{t(gpsNote)}</p>}
      <div className="two">
        <label className="field"><span>{t('rp_lat')}</span>
          <input type="text" inputMode="decimal" value={form.latitude} onChange={(e) => set({ latitude: e.target.value, location_source: 'manual' })} /></label>
        <label className="field"><span>{t('rp_lon')}</span>
          <input type="text" inputMode="decimal" value={form.longitude} onChange={(e) => set({ longitude: e.target.value, location_source: 'manual' })} /></label>
      </div>
      <ErrorLine keyName={errors.location} />
      <label className="field"><span>{t('rp_address')}</span>
        <input type="text" maxLength={200} value={form.address_text} onChange={(e) => set({ address_text: e.target.value })} /></label>

      <label className="field"><span>{t('rp_people')}</span>
        <input type="number" min="1" max="200" value={form.people_count} onChange={(e) => set({ people_count: e.target.value })} /></label>
      <ErrorLine keyName={errors.people_count} />

      <fieldset className="checks">
        <legend>{t('rp_urgency')}</legend>
        {['immediate', 'within_hours', 'within_day'].map((u) => (
          <label key={u} className="check">
            <input type="radio" name="urgency" checked={form.urgency === u} onChange={() => set({ urgency: u })} />
            <span>{t(`rp_urgency_${u}`)}</span>
          </label>
        ))}
      </fieldset>

      <CheckGroup legend={t('rp_hazards')} keys={HAZARDS} prefix="rp_hazard"
        value={Object.fromEntries(HAZARDS.map((h) => [h, form.hazards.includes(h)]))}
        onChange={(v) => set({ hazards: HAZARDS.filter((h) => v[h]) })} />
      <CheckGroup legend={t('rp_needs')} keys={NEEDS} prefix="rp_need" value={form.needs} onChange={(needs) => set({ needs })} />
      <CheckGroup legend={t('rp_flags')} keys={FLAGS} prefix="rp_flag" value={form.vulnerability_flags} onChange={(vulnerability_flags) => set({ vulnerability_flags })} />

      <label className="field"><span>{t('rp_contact_phone')}</span>
        <input type="tel" inputMode="tel" value={form.phone} onChange={(e) => set({ phone: e.target.value })} /></label>
      <ErrorLine keyName={errors.phone} />
      <label className="field"><span>{t('rp_notes')}</span>
        <textarea rows="3" maxLength={500} value={form.notes} onChange={(e) => set({ notes: e.target.value })} /></label>

      <fieldset className="checks">
        <legend>{t('rp_consent_title')}</legend>
        <label className="check">
          <input type="checkbox" checked={form.consent_location} onChange={(e) => set({ consent_location: e.target.checked })} />
          <span>{t('rp_consent_location')}</span>
        </label>
        <label className="check">
          <input type="checkbox" checked={form.consent_sensitive} onChange={(e) => set({ consent_sensitive: e.target.checked })} />
          <span>{t('rp_consent_sensitive')}</span>
        </label>
        <p className="muted small">{t('rp_consent_note')}</p>
      </fieldset>

      <ErrorLine keyName={fail} />
      <button className="btn wide" type="submit" disabled={busy}><Send size={18} aria-hidden="true" /> {t('rp_send')}</button>
    </form>
  )
}

function RequestCard({ req, account, onChanged }) {
  const t = useT()
  const [log, setLog] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const done = ['RESCUED', 'ASSISTANCE_DELIVERED'].includes(req.status)
  const canCancel = ['PENDING', 'TRIAGED', 'ASSIGNED', 'ACCEPTED', 'PREPARING', 'DISPATCHED'].includes(req.status)

  async function run(fn) {
    setBusy(true)
    setError(null)
    try {
      await fn()
      onChanged()
    } catch (err) {
      setError(errorKey(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <article className="card req-card">
      <div className="row spread">
        <StatusPill status={req.status} />
        <PriorityPill priority={req.priority} />
      </div>
      <p className="muted small">{t('rp_status_help_' + req.status)}</p>
      <p className="small">{t('rp_req_id')}: <code>{req.id}</code> · <When value={req.created_at} /></p>
      <p className="small">{t('rp_last_update')}: <When value={req.updated_at} /></p>
      {req.status_reason && <p className="small">{t('rp_reason_shown')}: {req.status_reason}</p>}
      {req.citizen_confirmation && <p className="small">{t('rp_your_answer')}: {t(`rp_confirm_${req.citizen_confirmation}`)}</p>}
      <ErrorLine keyName={error} />
      <div className="row">
        {done && !req.citizen_confirmation && (
          <>
            <button type="button" className="btn" disabled={busy} onClick={() => run(() => confirmOutcome(req, account.user.uid, 'confirmed'))}>{t('rp_confirm_yes')}</button>
            <button type="button" className="btn secondary" disabled={busy} onClick={() => run(() => confirmOutcome(req, account.user.uid, 'disputed'))}>{t('rp_confirm_no')}</button>
          </>
        )}
        {canCancel && <ReasonButton danger busy={busy} label={t('rp_cancel_request')} onConfirm={(reason) => run(() => cancelRequest(req, account.user.uid, reason))} />}
        <button type="button" className="btn link" onClick={async () => setLog(log ? null : await timeline(req.id).catch(() => []))}>{t('rp_history')}</button>
      </div>
      {log && (
        <ol className="timeline">
          {log.map((l) => (
            <li key={l.id}><When value={l.created_at} /> · {t(`st_${l.to_status}`)} · {t(`rp_actor_${l.actor_role}`)}{l.note ? ` · ${l.note}` : ''}</li>
          ))}
        </ol>
      )}
    </article>
  )
}

function MyRequests({ account, sentId, onSent }) {
  const t = useT()
  const [open, setOpen] = useState(false)
  const fetcher = useCallback(() => myRequests(account.user.uid), [account.user.uid])
  const { data: requests, error, reload } = useLoader(fetcher)
  useEffect(() => {
    const timer = setInterval(reload, 20000)          // pick up status changes
    return () => clearInterval(timer)
  }, [reload])
  return (
    <>
      {sentId && (
        <div className="card ok-card" role="status">
          <p><strong>{t('rp_sent_title')}</strong></p>
          <p>{t('rp_sent_body')}</p>
          <p className="small">{t('rp_req_id')}: <code>{sentId}</code></p>
        </div>
      )}
      {!open && <button type="button" className="btn wide big" onClick={() => setOpen(true)}><LifeBuoy size={20} aria-hidden="true" /> {t('rp_request_button')}</button>}
      {open && <RequestForm account={account} onSent={(id) => { setOpen(false); onSent(id); reload() }} />}
      <h2>{t('rp_my_requests')}</h2>
      <ErrorLine keyName={error ? errorKey(error) : null} />
      {requests && requests.length === 0 && <p className="muted">{t('rp_none_yet')}</p>}
      {(requests || []).map((r) => <RequestCard key={r.id} req={r} account={account} onChanged={reload} />)}
    </>
  )
}

export default function RescuePage() {
  const t = useT()
  const account = useAccount()
  const [sentId, setSentId] = useState(null)
  const needsProfile = useMemo(() => account.state === 'in' && !account.profile, [account])
  return (
    <>
      <PageHead Icon={LifeBuoy} title={t('rp_rescue_title')} sub={t('rp_rescue_sub')} tone="critical" />
      <EmergencyBanner />
      <PrototypeNotice />
      {account.state === 'loading' && <p className="muted">{t('loading')}</p>}
      {account.state === 'out' && (
        <div className="card">
          <p>{t('rp_need_account')}</p>
          <Link className="btn wide" to="/account">{t('rp_sign_in')}</Link>
        </div>
      )}
      {needsProfile && <ProfileForm account={account} onSaved={account.reload} />}
      {account.state === 'in' && !needsProfile && <MyRequests account={account} sentId={sentId} onSent={setSentId} />}
    </>
  )
}
