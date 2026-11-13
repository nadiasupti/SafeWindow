import 'leaflet/dist/leaflet.css'
import { Shield } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { CircleMarker, MapContainer, TileLayer, Tooltip } from 'react-leaflet'
import { Link } from 'react-router-dom'
import PageHead from '../components/PageHead.jsx'
import { ErrorLine, PriorityPill, PrototypeNotice, ReasonButton, StatusPill, When } from '../components/RescueBits.jsx'
import { useT } from '../i18n/language.js'
import { errorKey } from '../lib/errors.js'
import { useLoader } from '../lib/useLoader.js'
import { ACTIVE, GOV_ASSIGN_FROM, GOV_CANCEL_FROM, GOV_CLOSE_FROM, GOV_EARLY_END_FROM, PRIORITIES, STATUSES, summarize } from '../lib/rescue.js'
import { useAccount } from '../services/account.js'
import {
  allNgos, allRequests, auditEvents, decideNgo, govChange, officialAlerts, publishAlert, readPrivate, readSensitive, timeline, withdrawAlert,
} from '../services/rescue.js'
import { loadLayer } from '../services/data.js'
import { useAppState } from '../state/appState.js'

const COLOR = { CRITICAL: '#7a1020', HIGH: '#d94c4c', MEDIUM: '#e6a52e', LOW: '#268b65' }

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

function Overview({ requests }) {
  const t = useT()
  const s = useMemo(() => summarize(requests), [requests])
  // Average time from the request to its last change, for completed requests: a rough response measure.
  const done = requests.filter((r) => ['RESCUED', 'ASSISTANCE_DELIVERED', 'CLOSED'].includes(r.status) && r.created_at?.toMillis && r.updated_at?.toMillis)
  const avg = done.length ? Math.round(done.reduce((sum, r) => sum + (r.updated_at.toMillis() - r.created_at.toMillis()), 0) / done.length / 60000) : null
  const tiles = [['rp_ov_total', s.total], ['rp_ov_new', s.new], ['rp_ov_active', s.active], ['rp_ov_completed', s.completed],
    ['rp_ov_urgent_open', s.unassigned_urgent], ['rp_ov_overdue', s.overdue]]
  return (
    <>
      <div className="stat-grid">
        {tiles.map(([k, v]) => <div className="card stat" key={k}><strong>{v}</strong><span>{t(k)}</span></div>)}
      </div>
      <div className="card">
        <h2>{t('rp_ov_by_status')}</h2>
        <ul className="plain">
          {STATUSES.filter((st) => s.by_status[st]).map((st) => <li key={st} className="row spread"><StatusPill status={st} /><strong>{s.by_status[st]}</strong></li>)}
        </ul>
        <p className="muted small">{t('rp_ov_avg', { m: avg ?? '—' })}</p>
        <p className="muted small">{t('rp_ov_privacy')}</p>
      </div>
    </>
  )
}

function RequestMap({ requests, shelters, show }) {
  const t = useT()
  const first = requests[0]
  const center = first ? [first.coarse_lat, first.coarse_lon] : [25.07, 91.4]
  return (
    <div className="map-box">
      <MapContainer center={center} zoom={9} style={{ height: 320 }} scrollWheelZoom={false}>
        <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution="© OpenStreetMap contributors" maxZoom={18} />
        {show.requests && requests.filter((r) => ACTIVE.includes(r.status)).map((r) => (
          <CircleMarker key={r.id} center={[r.coarse_lat, r.coarse_lon]} radius={9} pathOptions={{ color: COLOR[r.priority] || '#555', fillOpacity: 0.7 }}>
            <Tooltip>{t(`pr_${r.priority}`)} · {t(`st_${r.status}`)} · {t('rp_people_n', { n: r.people_count })}</Tooltip>
          </CircleMarker>
        ))}
        {show.shelters && shelters.map((f) => (
          <CircleMarker key={f.properties.shelter_id} center={[f.geometry.coordinates[1], f.geometry.coordinates[0]]} radius={6} pathOptions={{ color: '#1572c4', fillOpacity: 0.5 }}>
            <Tooltip>{f.properties.name} · {t('rp_shelter_unverified')}</Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  )
}

function RequestDetail({ req, ngos, uid, reload }) {
  const t = useT()
  const [ngoId, setNgoId] = useState('')
  const [priority, setPriority] = useState(req.priority)
  const act = useAction(reload)
  const requestId = req.id
  const version = req.version
  const fetcher = useCallback(async () => {
    const [priv, sens, log] = await Promise.all([readPrivate(requestId), readSensitive(requestId), timeline(requestId).catch(() => [])])
    return { priv, sens, log, version }
  }, [requestId, version])
  const { data: extra } = useLoader(fetcher)
  const { priv, sens, log } = extra || {}
  const approved = ngos.filter((n) => n.status === 'approved')
  const g = (patch, reason, action) => act.run(() => govChange(req, uid, patch, reason, action))
  return (
    <div className="card detail">
      <div className="row spread"><StatusPill status={req.status} /><PriorityPill priority={req.priority} /></div>
      <p className="small muted">{t('rp_why_priority')}: {(req.priority_factors || []).map((f) => t(`rp_factor_${f}`)).join(', ') || '—'}</p>
      {req.priority_reason && <p className="small">{t('rp_override_reason')}: {req.priority_reason}</p>}
      {req.assigned_ngo_id && <p className="small">{t('rp_assigned_to')}: {ngos.find((n) => n.id === req.assigned_ngo_id)?.legal_name || req.assigned_ngo_id}</p>}
      {priv && <p className="small"><strong>{t('rp_exact')}</strong>: {priv.exact.latitude}, {priv.exact.longitude} · {priv.address_text || '—'} · <a href={`tel:${priv.phone}`}>{priv.phone}</a></p>}
      {sens && <p className="small"><strong>{t('rp_sensitive')}</strong>: {Object.keys(sens.vulnerability_flags).filter((k) => sens.vulnerability_flags[k]).map((k) => t(`rp_flag_${k}`)).join(', ') || '—'}{sens.notes ? ` · ${sens.notes}` : ''}</p>}
      <ErrorLine keyName={act.error} />
      <div className="actions">
        {req.status === 'PENDING' && <button type="button" className="btn secondary" disabled={act.busy} onClick={() => g({ status: 'TRIAGED' }, t('rp_triaged_reason'), 'triage')}>{t('rp_gov_triage')}</button>}
        {GOV_ASSIGN_FROM.includes(req.status) && (
          <div className="reason-box">
            <label className="field"><span>{t('rp_gov_assign_to')}</span>
              <select value={ngoId} onChange={(e) => setNgoId(e.target.value)}>
                <option value="">—</option>
                {approved.map((n) => <option key={n.id} value={n.id}>{n.legal_name}</option>)}
              </select></label>
            {ngoId && <ReasonButton busy={act.busy} label={req.status === 'ASSIGNED' || req.assigned_ngo_id ? t('rp_gov_reassign') : t('rp_gov_assign')}
              onConfirm={(reason) => g({ status: 'ASSIGNED', assigned_ngo_id: ngoId, accepted_by: null, assigned_by: uid, status_reason: reason }, reason, 'assign')} />}
          </div>
        )}
        {ACTIVE.includes(req.status) && (
          <div className="reason-box">
            <label className="field"><span>{t('rp_gov_priority')}</span>
              <select value={priority} onChange={(e) => setPriority(e.target.value)}>{PRIORITIES.map((p) => <option key={p} value={p}>{t(`pr_${p}`)}</option>)}</select></label>
            {priority !== req.priority && <ReasonButton busy={act.busy} label={t('rp_gov_override')}
              onConfirm={(reason) => g({ priority, priority_reason: reason }, reason, 'priority_override')} />}
          </div>
        )}
        {GOV_CLOSE_FROM.includes(req.status) && <ReasonButton busy={act.busy} label={t('rp_gov_close')} onConfirm={(reason) => g({ status: 'CLOSED', status_reason: reason }, reason, 'close')} />}
        {GOV_EARLY_END_FROM.includes(req.status) && (
          <>
            <ReasonButton danger busy={act.busy} label={t('rp_gov_duplicate')} onConfirm={(reason) => g({ status: 'DUPLICATE', status_reason: reason }, reason, 'duplicate')} />
            <ReasonButton danger busy={act.busy} label={t('rp_gov_reject')} onConfirm={(reason) => g({ status: 'REJECTED', status_reason: reason }, reason, 'reject')} />
          </>
        )}
        {GOV_CANCEL_FROM.includes(req.status) && <ReasonButton danger busy={act.busy} label={t('rp_gov_cancel')} onConfirm={(reason) => g({ status: 'CANCELLED', status_reason: reason }, reason, 'cancel')} />}
      </div>
      {log && <ol className="timeline">{log.map((l) => <li key={l.id}><When value={l.created_at} /> · {t(`st_${l.to_status}`)} · {t(`rp_actor_${l.actor_role}`)}{l.note ? ` · ${l.note}` : ''}</li>)}</ol>}
    </div>
  )
}

function Requests({ requests, ngos, uid, reload }) {
  const t = useT()
  const { floodId } = useAppState()
  const [status, setStatus] = useState('')
  const [priority, setPriority] = useState('')
  const [open, setOpen] = useState(null)
  const [shelters, setShelters] = useState([])
  const [show, setShow] = useState({ requests: true, shelters: false })
  useEffect(() => { loadLayer(floodId, 'shelters').then((g) => setShelters(g?.features || [])).catch(() => setShelters([])) }, [floodId])
  const shown = requests.filter((r) => (!status || r.status === status) && (!priority || r.priority === priority))
  return (
    <>
      <div className="card">
        <div className="row">
          <label className="check"><input type="checkbox" checked={show.requests} onChange={(e) => setShow({ ...show, requests: e.target.checked })} /><span>{t('rp_layer_requests')}</span></label>
          <label className="check"><input type="checkbox" checked={show.shelters} onChange={(e) => setShow({ ...show, shelters: e.target.checked })} /><span>{t('rp_layer_shelters')}</span></label>
        </div>
        <RequestMap requests={shown} shelters={shelters} show={show} />
        <p className="muted small">{t('rp_map_note')}</p>
      </div>
      <div className="row">
        <select aria-label={t('rp_filter_status')} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">{t('rp_filter_status')}</option>{STATUSES.map((s) => <option key={s} value={s}>{t(`st_${s}`)}</option>)}</select>
        <select aria-label={t('rp_filter_priority')} value={priority} onChange={(e) => setPriority(e.target.value)}>
          <option value="">{t('rp_filter_priority')}</option>{PRIORITIES.map((p) => <option key={p} value={p}>{t(`pr_${p}`)}</option>)}</select>
      </div>
      {shown.length === 0 && <p className="muted">{t('rp_none_yet')}</p>}
      {shown.map((r) => (
        <article className="card req-card" key={r.id}>
          <button type="button" className="row spread link-row" onClick={() => setOpen(open === r.id ? null : r.id)} aria-expanded={open === r.id}>
            <span><StatusPill status={r.status} /> <PriorityPill priority={r.priority} /></span>
            <span className="small muted">{t('rp_people_n', { n: r.people_count })} · <When value={r.created_at} /></span>
          </button>
          {open === r.id && <RequestDetail req={r} ngos={ngos} uid={uid} reload={reload} />}
        </article>
      ))}
    </>
  )
}

function Ngos({ ngos, uid, reload }) {
  const t = useT()
  const act = useAction(reload)
  return (
    <>
      <ErrorLine keyName={act.error} />
      {ngos.length === 0 && <p className="muted">{t('rp_none_yet')}</p>}
      {ngos.map((n) => (
        <article className="card" key={n.id}>
          <div className="row spread"><strong>{n.legal_name}</strong><span className="pill">{t(`rp_ngo_status_${n.status}`)}</span></div>
          <p className="small muted">{(n.operating_areas || []).join(', ')} · {(n.capabilities || []).map((c) => t(`rp_cap_${c}`)).join(', ')}</p>
          <p className="small">{t('rp_ngo_reg')}: {n.registration_details}</p>
          {n.status_reason && <p className="small">{t('rp_reason_shown')}: {n.status_reason}</p>}
          <div className="row">
            {['pending', 'info_requested', 'rejected'].includes(n.status) && <ReasonButton busy={act.busy} label={t('rp_ngo_approve')} onConfirm={(r) => act.run(() => decideNgo(n, uid, 'approved', r))} />}
            {['pending', 'info_requested'].includes(n.status) && <ReasonButton busy={act.busy} label={t('rp_ngo_more_info')} onConfirm={(r) => act.run(() => decideNgo(n, uid, 'info_requested', r))} />}
            {['pending', 'info_requested'].includes(n.status) && <ReasonButton danger busy={act.busy} label={t('rp_ngo_reject')} onConfirm={(r) => act.run(() => decideNgo(n, uid, 'rejected', r))} />}
            {n.status === 'approved' && <ReasonButton danger busy={act.busy} label={t('rp_ngo_suspend')} onConfirm={(r) => act.run(() => decideNgo(n, uid, 'suspended', r))} />}
            {n.status === 'suspended' && <ReasonButton busy={act.busy} label={t('rp_ngo_reinstate')} onConfirm={(r) => act.run(() => decideNgo(n, uid, 'approved', r))} />}
          </div>
        </article>
      ))}
    </>
  )
}

function Alerts({ uid }) {
  const t = useT()
  const { floodId } = useAppState()
  const [form, setForm] = useState({ severity: 'watch', title: '', body: '', source: '', hours: 12, area_text: '' })
  const fetcher = useCallback(() => officialAlerts().catch(() => []), [])
  const { data, reload } = useLoader(fetcher)
  const list = data || []
  const act = useAction(reload)
  return (
    <>
      <form className="card" onSubmit={(e) => { e.preventDefault(); act.run(() => publishAlert(uid, { ...form, flood: floodId })) }}>
        <h2>{t('rp_alert_new')}</h2>
        <p className="muted small">{t('rp_alert_note')}</p>
        <div className="two">
          <label className="field"><span>{t('rp_alert_severity')}</span>
            <select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}>
              {['watch', 'warning', 'critical'].map((s) => <option key={s} value={s}>{t(`rp_sev_${s}`)}</option>)}</select></label>
          <label className="field"><span>{t('rp_alert_hours')}</span>
            <input type="number" min="1" max="72" value={form.hours} onChange={(e) => setForm({ ...form, hours: e.target.value })} /></label>
        </div>
        <label className="field"><span>{t('rp_alert_title')}</span>
          <input type="text" required minLength={3} maxLength={100} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
        <label className="field"><span>{t('rp_alert_body')}</span>
          <textarea rows="3" required minLength={3} maxLength={500} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} /></label>
        <label className="field"><span>{t('rp_alert_area')}</span>
          <input type="text" maxLength={120} value={form.area_text} onChange={(e) => setForm({ ...form, area_text: e.target.value })} /></label>
        <label className="field"><span>{t('rp_alert_source')}</span>
          <input type="text" required minLength={3} maxLength={120} value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} /></label>
        <ErrorLine keyName={act.error} />
        <button className="btn wide" type="submit" disabled={act.busy}>{t('rp_alert_publish')}</button>
      </form>
      {list.map((a) => (
        <article className="card" key={a.id}>
          <div className="row spread"><strong>{a.title}</strong><span className="pill">{t(`rp_sev_${a.severity}`)} · {t(`rp_alert_${a.status}`)}</span></div>
          <p className="small">{a.body}</p>
          <p className="small muted">{t('rp_alert_source')}: {a.source} · <When value={a.starts_at} /> → <When value={a.expires_at} /></p>
          {a.status === 'published' && <ReasonButton danger busy={act.busy} label={t('rp_alert_withdraw')} onConfirm={(r) => act.run(() => withdrawAlert(a, uid, r))} />}
        </article>
      ))}
    </>
  )
}

function Audit() {
  const t = useT()
  const fetcher = useCallback(() => auditEvents().catch(() => []), [])
  const { data: list } = useLoader(fetcher)
  return (
    <>
      <p className="muted small">{t('rp_audit_note')}</p>
      {(list || []).map((a) => (
        <div className="card" key={a.id}>
          <div className="row spread"><strong>{a.action}</strong><span className="small muted"><When value={a.created_at} /></span></div>
          <p className="small">{a.entity_type} · <code>{a.entity_id}</code></p>
          <p className="small muted">{a.reason}</p>
        </div>
      ))}
    </>
  )
}

function GovDesk({ uid }) {
  const t = useT()
  const [tab, setTab] = useState('overview')
  const fetcher = useCallback(async () => {
    const [requests, ngos] = await Promise.all([allRequests(), allNgos()])
    return { requests, ngos }
  }, [])
  const { data, error, reload } = useLoader(fetcher)
  useEffect(() => {
    const timer = setInterval(reload, 20000)
    return () => clearInterval(timer)
  }, [reload])
  const requests = data?.requests || []
  const ngos = data?.ngos || []
  return (
    <>
      <ErrorLine keyName={error ? errorKey(error) : null} />
      <div className="seg-row" role="tablist">
        {['overview', 'requests', 'ngos', 'alerts', 'audit'].map((k) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? 'chip on' : 'chip'} onClick={() => setTab(k)}>{t(`rp_gtab_${k}`)}</button>
        ))}
      </div>
      {tab === 'overview' && <Overview requests={requests} />}
      {tab === 'requests' && <Requests requests={requests} ngos={ngos} uid={uid} reload={reload} />}
      {tab === 'ngos' && <Ngos ngos={ngos} uid={uid} reload={reload} />}
      {tab === 'alerts' && <Alerts uid={uid} />}
      {tab === 'audit' && <Audit />}
    </>
  )
}

export default function GovPage() {
  const t = useT()
  const account = useAccount()
  return (
    <>
      <PageHead Icon={Shield} title={t('rp_gov_title')} sub={t('rp_gov_sub')} />
      <PrototypeNotice />
      {account.state === 'loading' && <p className="muted">{t('loading')}</p>}
      {account.state === 'out' && <div className="card"><p>{t('rp_need_account')}</p><Link className="btn wide" to="/account">{t('rp_sign_in')}</Link></div>}
      {account.state === 'in' && !account.gov && <div className="card"><p>{t('rp_gov_only')}</p></div>}
      {account.state === 'in' && account.gov && <GovDesk uid={account.user.uid} />}
    </>
  )
}
