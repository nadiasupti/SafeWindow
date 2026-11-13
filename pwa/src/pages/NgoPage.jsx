import { Ship, Users } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import PageHead from '../components/PageHead.jsx'
import { ErrorLine, PriorityPill, PrototypeNotice, ReasonButton, StatusPill, When } from '../components/RescueBits.jsx'
import { useT } from '../i18n/language.js'
import { errorKey } from '../lib/errors.js'
import { isStale, ngoNextSteps } from '../lib/rescue.js'
import { useLoader } from '../lib/useLoader.js'
import { useAccount } from '../services/account.js'
import {
  applyNgo, assignedTo, claim, createInvite, decline, members, ngoStep, openQueue, readPrivate, readSensitive, redeemInvite,
  resources, saveResource, timeline, updateMember,
} from '../services/rescue.js'

const CAPS = ['boat', 'vehicle', 'medical', 'food', 'water', 'shelter', 'volunteers']
const PRIORITY_ORDER = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 }

function useAction(onDone) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const run = async (fn) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
      await onDone?.()
    } catch (err) {
      setError(errorKey(err))
    } finally {
      setBusy(false)
    }
  }
  return { busy, error, run }
}

function Apply({ account }) {
  const t = useT()
  const [form, setForm] = useState({ legal_name: '', registration_details: '', operating_areas: '', contact_phone: '', capabilities: [] })
  const [code, setCode] = useState('')
  const a = useAction(account.reload)
  const b = useAction(account.reload)
  return (
    <>
      <form className="card" onSubmit={(e) => { e.preventDefault(); a.run(() => applyNgo(account.user.uid, form)) }}>
        <h2>{t('rp_ngo_apply')}</h2>
        <p className="muted small">{t('rp_ngo_apply_note')}</p>
        <label className="field"><span>{t('rp_ngo_name')}</span>
          <input type="text" required minLength={2} maxLength={120} value={form.legal_name} onChange={(e) => setForm({ ...form, legal_name: e.target.value })} /></label>
        <label className="field"><span>{t('rp_ngo_reg')}</span>
          <textarea rows="3" required minLength={3} maxLength={600} value={form.registration_details} onChange={(e) => setForm({ ...form, registration_details: e.target.value })} /></label>
        <label className="field"><span>{t('rp_ngo_areas')}</span>
          <input type="text" required value={form.operating_areas} onChange={(e) => setForm({ ...form, operating_areas: e.target.value })} /></label>
        <label className="field"><span>{t('rp_contact_phone')}</span>
          <input type="tel" inputMode="tel" value={form.contact_phone} onChange={(e) => setForm({ ...form, contact_phone: e.target.value })} /></label>
        <fieldset className="checks">
          <legend>{t('rp_ngo_caps')}</legend>
          {CAPS.map((c) => (
            <label key={c} className="check">
              <input type="checkbox" checked={form.capabilities.includes(c)}
                onChange={(e) => setForm({ ...form, capabilities: e.target.checked ? [...form.capabilities, c] : form.capabilities.filter((x) => x !== c) })} />
              <span>{t(`rp_cap_${c}`)}</span>
            </label>
          ))}
        </fieldset>
        <ErrorLine keyName={a.error} />
        <button className="btn wide" type="submit" disabled={a.busy}>{t('rp_ngo_submit')}</button>
      </form>
      <form className="card" onSubmit={(e) => { e.preventDefault(); b.run(() => redeemInvite(account.user.uid, code.trim())) }}>
        <h2>{t('rp_join_title')}</h2>
        <label className="field"><span>{t('rp_join_code')}</span>
          <input type="text" value={code} onChange={(e) => setCode(e.target.value)} required /></label>
        <ErrorLine keyName={b.error} />
        <button className="btn wide" type="submit" disabled={b.busy || !code}>{t('rp_join')}</button>
      </form>
    </>
  )
}

const sortQueue = (list) => list.sort((x, y) => (PRIORITY_ORDER[x.priority] ?? 9) - (PRIORITY_ORDER[y.priority] ?? 9))

function Queue({ account, ngo }) {
  const t = useT()
  const fetcher = useCallback(async () => sortQueue(await openQueue()), [])
  const { data: list, error, reload } = useLoader(fetcher)
  const act = useAction(reload)
  return (
    <>
      <p className="muted small">{t('rp_queue_note')}</p>
      <ErrorLine keyName={error ? errorKey(error) : act.error} />
      {list && list.length === 0 && <p className="muted">{t('rp_queue_empty')}</p>}
      {(list || []).map((r) => (
        <article className="card req-card" key={r.id}>
          <div className="row spread"><StatusPill status={r.status} /><PriorityPill priority={r.priority} /></div>
          <p>{t('rp_people_n', { n: r.people_count })} · {t(`rp_urgency_${r.urgency}`)}</p>
          <p className="small">{t('rp_area')}: {r.coarse_lat}, {r.coarse_lon} ({t('rp_coarse')})</p>
          <p className="small">{(r.hazards || []).map((h) => t(`rp_hazard_${h}`)).join(', ')}</p>
          <p className="small">{Object.keys(r.needs || {}).filter((k) => r.needs[k]).map((k) => t(`rp_need_${k}`)).join(', ')}</p>
          <p className="small muted">{t('rp_why_priority')}: {(r.priority_factors || []).map((f) => t(`rp_factor_${f}`)).join(', ') || '—'}</p>
          <p className="small muted"><When value={r.created_at} /></p>
          <button type="button" className="btn" disabled={act.busy} onClick={() => act.run(() => claim(r, account.user.uid, ngo.id))}>{t('rp_accept')}</button>
        </article>
      ))}
    </>
  )
}

function Mission({ req, account, ngo, onChanged }) {
  const t = useT()
  const [detail, setDetail] = useState({})
  const [assisted, setAssisted] = useState('')
  const [log, setLog] = useState(null)
  const act = useAction(onChanged)
  useEffect(() => {
    let alive = true
    const visible = ['ASSIGNED', 'ACCEPTED', 'PREPARING', 'DISPATCHED', 'IN_PROGRESS'].includes(req.status)
    Promise.all(visible ? [readPrivate(req.id), readSensitive(req.id)] : [null, null])
      .then(([priv, sens]) => alive && setDetail({ priv, sens, loaded: true }))
    return () => { alive = false }
  }, [req.id, req.status])
  const uid = account.user.uid
  const steps = ngoNextSteps(req.status)
  return (
    <article className="card req-card">
      <div className="row spread"><StatusPill status={req.status} /><PriorityPill priority={req.priority} /></div>
      <p>{t('rp_people_n', { n: req.people_count })} · {t(`rp_urgency_${req.urgency}`)}</p>
      {detail.priv ? (
        <p className="small">
          <strong>{t('rp_exact')}</strong>: {detail.priv.exact.latitude}, {detail.priv.exact.longitude}
          {detail.priv.address_text ? ` · ${detail.priv.address_text}` : ''} · <a href={`tel:${detail.priv.phone}`}>{detail.priv.phone}</a>
        </p>
      ) : detail.loaded && <p className="small muted">{t('rp_not_shared_location')}</p>}
      {detail.sens ? (
        <p className="small"><strong>{t('rp_sensitive')}</strong>: {Object.keys(detail.sens.vulnerability_flags).filter((k) => detail.sens.vulnerability_flags[k]).map((k) => t(`rp_flag_${k}`)).join(', ') || '—'}
          {detail.sens.notes ? ` · ${detail.sens.notes}` : ''}</p>
      ) : detail.loaded && <p className="small muted">{t('rp_not_shared_sensitive')}</p>}
      {req.citizen_confirmation && <p className="small">{t('rp_citizen_said')}: {t(`rp_confirm_${req.citizen_confirmation}`)}</p>}
      <ErrorLine keyName={act.error} />
      {req.status === 'ASSIGNED' && (
        <div className="row">
          <button type="button" className="btn" disabled={act.busy} onClick={() => act.run(() => claim(req, uid, ngo.id))}>{t('rp_accept')}</button>
          <ReasonButton danger busy={act.busy} label={t('rp_decline')} onConfirm={(reason) => act.run(() => decline(req, uid, reason))} />
        </div>
      )}
      {steps.some(([to]) => to === 'RESCUED') && (
        <label className="field"><span>{t('rp_assisted')}</span>
          <input type="number" min="0" max="1000" value={assisted} onChange={(e) => setAssisted(e.target.value)} /></label>
      )}
      {steps.length > 0 && (
        <div className="row">
          {steps.map(([to, needsReason]) => {
            if (needsReason) {
              return <ReasonButton key={to} busy={act.busy} label={t(`rp_step_${to}`)} onConfirm={(reason) => act.run(() => ngoStep(req, uid, to, { status_reason: reason }))} />
            }
            if (to === 'RESCUED' || to === 'ASSISTANCE_DELIVERED') {
              return <button key={to} type="button" className="btn" disabled={act.busy || assisted === ''} onClick={() => act.run(() => ngoStep(req, uid, to, { people_assisted: Number(assisted) }))}>{t(`rp_step_${to}`)}</button>
            }
            return <button key={to} type="button" className="btn" disabled={act.busy} onClick={() => act.run(() => ngoStep(req, uid, to))}>{t(`rp_step_${to}`)}</button>
          })}
        </div>
      )}
      <button type="button" className="btn link" onClick={async () => setLog(log ? null : await timeline(req.id).catch(() => []))}>{t('rp_history')}</button>
      {log && <ol className="timeline">{log.map((l) => <li key={l.id}><When value={l.created_at} /> · {t(`st_${l.to_status}`)} · {t(`rp_actor_${l.actor_role}`)}{l.note ? ` · ${l.note}` : ''}</li>)}</ol>}
    </article>
  )
}

function Missions({ account, ngo }) {
  const t = useT()
  const fetcher = useCallback(() => assignedTo(ngo.id), [ngo.id])
  const { data: list, error, reload } = useLoader(fetcher)
  return (
    <>
      <ErrorLine keyName={error ? errorKey(error) : null} />
      {list && list.length === 0 && <p className="muted">{t('rp_missions_empty')}</p>}
      {(list || []).map((r) => <Mission key={r.id} req={r} account={account} ngo={ngo} onChanged={reload} />)}
    </>
  )
}

function Resources({ ngo, manager }) {
  const t = useT()
  const [form, setForm] = useState({ type: 'boat', quantity: 1, availability: 'available', location_text: '', condition: 'good' })
  const fetcher = useCallback(() => resources(ngo.id).catch(() => []), [ngo.id])
  const { data: list, reload } = useLoader(fetcher)
  const act = useAction(reload)
  return (
    <>
      <p className="muted small">{t('rp_resources_note', { h: 12 })}</p>
      {(list || []).filter((r) => !r.retired).map((r) => (
        <div className="card" key={r.id}>
          <div className="row spread">
            <strong>{t(`rp_res_${r.type}`)}: {r.quantity}</strong>
            <span className={`pill ${isStale(r.last_reported_at) ? 'pr-high' : 'st-accepted'}`}>{isStale(r.last_reported_at) ? t('rp_stale') : t(`rp_avail_${r.availability}`)}</span>
          </div>
          <p className="small muted">{r.location_text || '—'} · {t('rp_last_update')}: <When value={r.last_reported_at} /></p>
          {manager && (
            <div className="row">
              <button type="button" className="btn secondary" disabled={act.busy} onClick={() => act.run(() => saveResource(ngo.id, { ...r, retired: true }, r.id))}>{t('rp_retire')}</button>
              <button type="button" className="btn secondary" disabled={act.busy} onClick={() => act.run(() => saveResource(ngo.id, r, r.id))}>{t('rp_confirm_still')}</button>
            </div>
          )}
        </div>
      ))}
      {manager && (
        <form className="card" onSubmit={(e) => { e.preventDefault(); act.run(() => saveResource(ngo.id, form)) }}>
          <h2>{t('rp_res_add')}</h2>
          <div className="two">
            <label className="field"><span>{t('rp_res_type')}</span>
              <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
                {['boat', 'vehicle', 'medical_supplies', 'food', 'drinking_water', 'volunteers'].map((k) => <option key={k} value={k}>{t(`rp_res_${k}`)}</option>)}
              </select></label>
            <label className="field"><span>{t('rp_res_qty')}</span>
              <input type="number" min="0" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></label>
          </div>
          <div className="two">
            <label className="field"><span>{t('rp_res_avail')}</span>
              <select value={form.availability} onChange={(e) => setForm({ ...form, availability: e.target.value })}>
                {['available', 'limited', 'unavailable'].map((k) => <option key={k} value={k}>{t(`rp_avail_${k}`)}</option>)}
              </select></label>
            <label className="field"><span>{t('rp_res_cond')}</span>
              <select value={form.condition} onChange={(e) => setForm({ ...form, condition: e.target.value })}>
                {['good', 'fair', 'poor'].map((k) => <option key={k} value={k}>{t(`rp_cond_${k}`)}</option>)}
              </select></label>
          </div>
          <label className="field"><span>{t('rp_res_loc')}</span>
            <input type="text" maxLength={120} value={form.location_text} onChange={(e) => setForm({ ...form, location_text: e.target.value })} /></label>
          <ErrorLine keyName={act.error} />
          <button className="btn wide" type="submit" disabled={act.busy}>{t('rp_save')}</button>
        </form>
      )}
    </>
  )
}

function Team({ account, ngo }) {
  const t = useT()
  const [code, setCode] = useState(null)
  const fetcher = useCallback(() => members(ngo.id).catch(() => []), [ngo.id])
  const { data: list, reload } = useLoader(fetcher)
  const act = useAction(reload)
  return (
    <>
      <div className="card">
        <h2>{t('rp_invite_title')}</h2>
        <p className="muted small">{t('rp_invite_note')}</p>
        <button type="button" className="btn" disabled={act.busy} onClick={() => act.run(async () => setCode(await createInvite(account.user.uid, ngo.id)))}>{t('rp_invite_make')}</button>
        {code && <p role="status"><code className="big-code">{code}</code></p>}
        <ErrorLine keyName={act.error} />
      </div>
      {(list || []).map((m) => (
        <div className="card" key={m.id}>
          <div className="row spread">
            <strong>{m.id === account.user.uid ? t('rp_you') : m.id.slice(0, 8)}</strong>
            <span className="pill">{t(`rp_member_${m.member_role}`)}</span>
          </div>
          <p className="small muted">{m.active ? t('rp_active') : t('rp_paused')} {m.team ? `· ${m.team}` : ''}</p>
          {m.id !== account.user.uid && (
            <button type="button" className="btn secondary" disabled={act.busy} onClick={() => act.run(() => updateMember(m.id, { active: !m.active }))}>
              {m.active ? t('rp_pause') : t('rp_resume')}
            </button>
          )}
        </div>
      ))}
    </>
  )
}

export default function NgoPage() {
  const t = useT()
  const account = useAccount()
  const [tab, setTab] = useState('queue')
  const ngo = account.ngo
  const approved = ngo?.status === 'approved' && account.member?.active
  const manager = account.member?.member_role === 'manager'
  return (
    <>
      <PageHead Icon={Users} title={t('rp_ngo_title')} sub={t('rp_ngo_sub')} />
      <PrototypeNotice />
      {account.state === 'loading' && <p className="muted">{t('loading')}</p>}
      {account.state === 'out' && <div className="card"><p>{t('rp_need_account')}</p><Link className="btn wide" to="/account">{t('rp_sign_in')}</Link></div>}
      {account.state === 'in' && !account.member && <Apply account={account} />}
      {account.state === 'in' && account.member && !ngo && <p className="muted">{t('rp_ngo_missing')}</p>}
      {account.state === 'in' && ngo && !approved && (
        <div className="card">
          <h2>{ngo.legal_name}</h2>
          <p><span className="pill">{t(`rp_ngo_status_${ngo.status}`)}</span></p>
          <p className="muted small">{t('rp_ngo_locked')}</p>
          {ngo.status_reason && <p className="small">{t('rp_reason_shown')}: {ngo.status_reason}</p>}
        </div>
      )}
      {approved && (
        <>
          <h2><Ship size={20} aria-hidden="true" /> {ngo.legal_name}</h2>
          <div className="seg-row" role="tablist">
            {['queue', 'missions', 'resources', ...(manager ? ['team'] : [])].map((k) => (
              <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? 'chip on' : 'chip'} onClick={() => setTab(k)}>{t(`rp_tab_${k}`)}</button>
            ))}
          </div>
          {tab === 'queue' && <Queue account={account} ngo={ngo} />}
          {tab === 'missions' && <Missions account={account} ngo={ngo} />}
          {tab === 'resources' && <Resources ngo={ngo} manager={manager} />}
          {tab === 'team' && manager && <Team account={account} ngo={ngo} />}
        </>
      )}
    </>
  )
}
