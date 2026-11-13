// Firestore operations for the rescue platform. Every write here is one batch that matches firestore.rules:
//   - a change to a request also writes its history entry rescue_requests/{id}/updates/v{version};
//   - a government action also writes an audit event and names it in `audit_id`.
// The rules, not this file, decide what is allowed (pwa/rules-tests/rules.test.mjs proves them).
import {
  collection, doc, getDoc, getDocs, limit, orderBy, query, serverTimestamp, setDoc, updateDoc, where, writeBatch,
} from 'firebase/firestore'
import { newId, buildRequestDocs } from '../lib/rescue.js'
import { firestore } from './firebase.js'

const db = () => firestore()
const rows = (snap) => snap.docs.map((d) => ({ id: d.id, ...d.data() }))
const millis = (t) => (typeof t?.toMillis === 'function' ? t.toMillis() : 0)
export const byNewest = (a, b) => millis(b.created_at) - millis(a.created_at)

/** A document the caller may not read comes back as null instead of an error. */
async function tryGet(ref) {
  try {
    const snap = await getDoc(ref)
    return snap.exists() ? { id: snap.id, ...snap.data() } : null
  } catch {
    return null
  }
}

// ---------------------------------------------------------------------------------------------------------------
// citizen

export async function saveProfile(uid, form, existing) {
  const data = {
    name: form.name.trim(),
    phone: (form.phone || '').replace(/[\s-]/g, ''),
    lang: form.lang,
    assistance_profile: form.assistance_profile,
    created_at: existing?.created_at || serverTimestamp(),
    updated_at: serverTimestamp(),
  }
  await setDoc(doc(db(), 'users', uid), data)
}

/**
 * Sends a request. `id` is made once per form, so pressing the button twice or retrying on a weak network
 * cannot create two requests: a second create of the same id is refused by the rules.
 */
export async function submitRequest(uid, form, id) {
  const { request, priv, sensitive } = buildRequestDocs(form, uid, serverTimestamp())
  const b = writeBatch(db())
  b.set(doc(db(), 'rescue_requests', id), request)
  b.set(doc(db(), 'rescue_private', id), priv)
  b.set(doc(db(), 'rescue_sensitive', id), sensitive)
  b.set(doc(db(), 'rescue_requests', id, 'updates', 'v1'), {
    actor_id: uid, actor_role: 'citizen', to_status: 'PENDING', version: 1, created_at: serverTimestamp() })
  try {
    await b.commit()
  } catch (error) {
    // The first attempt may have reached the server although the answer was lost: then the request exists.
    if (await tryGet(doc(db(), 'rescue_requests', id))) return id
    throw error
  }
  return id
}

export async function myRequests(uid) {
  const snap = await getDocs(query(collection(db(), 'rescue_requests'), where('citizen_id', '==', uid)))
  return rows(snap).sort(byNewest)
}

export async function timeline(id) {
  const snap = await getDocs(query(collection(db(), 'rescue_requests', id, 'updates'), orderBy('version')))
  return rows(snap)
}

export const readPrivate = (id) => tryGet(doc(db(), 'rescue_private', id))
export const readSensitive = (id) => tryGet(doc(db(), 'rescue_sensitive', id))

/**
 * One controlled change: `req` is the request as last read (its version is the compare-and-swap), `patch` the new
 * fields. Writes the history entry in the same batch. `audit` is used for government actions.
 */
export async function change(req, uid, role, patch, { note, audit } = {}) {
  const b = writeBatch(db())
  const version = req.version + 1
  const fields = { ...patch, version, updated_at: serverTimestamp() }
  if (audit) {
    const auditId = newId('aud')
    fields.audit_id = auditId
    b.set(doc(db(), 'audit_events', auditId), {
      actor_id: uid, action: audit.action, entity_type: audit.entity_type || 'rescue_request', entity_id: req.id,
      reason: audit.reason, created_at: serverTimestamp() })
  }
  b.update(doc(db(), 'rescue_requests', req.id), fields)
  b.set(doc(db(), 'rescue_requests', req.id, 'updates', `v${version}`), {
    actor_id: uid, actor_role: role, from_status: req.status, to_status: patch.status ?? req.status, version,
    ...(note ? { note } : {}), created_at: serverTimestamp() })
  await b.commit()
}

export const cancelRequest = (req, uid, reason) => change(req, uid, 'citizen', { status: 'CANCELLED', status_reason: reason })
export const confirmOutcome = (req, uid, value) => change(req, uid, 'citizen', { citizen_confirmation: value })

// ---------------------------------------------------------------------------------------------------------------
// NGO

export async function applyNgo(uid, form) {
  const id = newId('ngo')
  const b = writeBatch(db())
  b.set(doc(db(), 'ngos', id), {
    legal_name: form.legal_name.trim(), registration_details: form.registration_details.trim(),
    operating_areas: form.operating_areas.split(',').map((s) => s.trim()).filter(Boolean).slice(0, 20),
    capabilities: form.capabilities, contact_phone: (form.contact_phone || '').replace(/[\s-]/g, ''),
    status: 'pending', owner_uid: uid, created_at: serverTimestamp(), updated_at: serverTimestamp() })
  b.set(doc(db(), 'ngo_members', uid), { ngo_id: id, member_role: 'manager', active: true, created_at: serverTimestamp() })
  await b.commit()
  return id
}

export async function redeemInvite(uid, code) {
  const invite = await getDoc(doc(db(), 'ngo_invites', code))
  if (!invite.exists()) throw Object.assign(new Error('invite'), { code: 'invite/not-found' })
  const b = writeBatch(db())
  b.update(doc(db(), 'ngo_invites', code), { used_by: uid, used_at: serverTimestamp() })
  b.set(doc(db(), 'ngo_members', uid), {
    ngo_id: invite.data().ngo_id, member_role: 'worker', active: true, invite_code: code, created_at: serverTimestamp() })
  await b.commit()
}

export async function createInvite(uid, ngoId) {
  const code = newId('inv')
  await setDoc(doc(db(), 'ngo_invites', code), {
    ngo_id: ngoId, created_by: uid, created_at: serverTimestamp(), expires_at: new Date(Date.now() + 48 * 3600 * 1000) })
  return code
}

export async function openQueue() {
  const snap = await getDocs(query(collection(db(), 'rescue_requests'), where('status', 'in', ['PENDING', 'TRIAGED'])))
  return rows(snap).sort(byNewest)
}

export async function assignedTo(ngoId) {
  const snap = await getDocs(query(collection(db(), 'rescue_requests'), where('assigned_ngo_id', '==', ngoId)))
  return rows(snap).sort(byNewest)
}

export const claim = (req, uid, ngoId) => change(req, uid, 'ngo', { status: 'ACCEPTED', assigned_ngo_id: ngoId, accepted_by: uid })
export const ngoStep = (req, uid, status, extra = {}, note) => change(req, uid, 'ngo', { status, ...extra }, { note })
export const decline = (req, uid, reason) => change(req, uid, 'ngo', { status: 'TRIAGED', assigned_ngo_id: null, status_reason: reason })

export async function members(ngoId) {
  return rows(await getDocs(query(collection(db(), 'ngo_members'), where('ngo_id', '==', ngoId))))
}

export const updateMember = (uid, patch) => updateDoc(doc(db(), 'ngo_members', uid), { ...patch, updated_at: serverTimestamp() })

export async function resources(ngoId) {
  return rows(await getDocs(query(collection(db(), 'resources'), where('ngo_id', '==', ngoId))))
}

export async function saveResource(ngoId, form, id) {
  const data = {
    ngo_id: ngoId, type: form.type, quantity: Number(form.quantity), availability: form.availability,
    location_text: form.location_text || '', condition: form.condition, retired: Boolean(form.retired),
    last_reported_at: serverTimestamp() }
  await setDoc(doc(db(), 'resources', id || newId('res')), data)
}

export const ngoProfile = (id) => tryGet(doc(db(), 'ngos', id))

// ---------------------------------------------------------------------------------------------------------------
// government

export async function allRequests() {
  const snap = await getDocs(query(collection(db(), 'rescue_requests'), orderBy('created_at', 'desc'), limit(500)))
  return rows(snap)
}

export async function allNgos() {
  return rows(await getDocs(collection(db(), 'ngos'))).sort(byNewest)
}

export const govChange = (req, uid, patch, reason, action) => change(req, uid, 'gov', patch, { audit: { action, reason }, note: reason })

export async function decideNgo(ngo, uid, status, reason) {
  const auditId = newId('aud')
  const b = writeBatch(db())
  b.set(doc(db(), 'audit_events', auditId), {
    actor_id: uid, action: `ngo_${status}`, entity_type: 'ngo', entity_id: ngo.id, reason, created_at: serverTimestamp() })
  b.update(doc(db(), 'ngos', ngo.id), {
    status, status_reason: reason, decided_by: uid, decided_at: serverTimestamp(), audit_id: auditId, updated_at: serverTimestamp() })
  await b.commit()
}

export async function publishAlert(uid, form) {
  const id = newId('al')
  const auditId = newId('aud')
  const start = new Date()
  const b = writeBatch(db())
  b.set(doc(db(), 'audit_events', auditId), {
    actor_id: uid, action: 'publish_alert', entity_type: 'alert', entity_id: id, reason: `Source: ${form.source}`, created_at: serverTimestamp() })
  b.set(doc(db(), 'official_alerts', id), {
    flood: form.flood, area_text: form.area_text || '', severity: form.severity, title: form.title.trim(), body: form.body.trim(),
    source: form.source.trim(), starts_at: start, expires_at: new Date(start.getTime() + Number(form.hours) * 3600 * 1000),
    status: 'published', author_id: uid, audit_id: auditId, created_at: serverTimestamp() })
  await b.commit()
  return id
}

export async function withdrawAlert(alert, uid, reason) {
  const auditId = newId('aud')
  const b = writeBatch(db())
  b.set(doc(db(), 'audit_events', auditId), {
    actor_id: uid, action: 'withdraw_alert', entity_type: 'alert', entity_id: alert.id, reason, created_at: serverTimestamp() })
  b.update(doc(db(), 'official_alerts', alert.id), {
    status: 'withdrawn', status_reason: reason, audit_id: auditId, withdrawn_at: serverTimestamp() })
  await b.commit()
}

export async function officialAlerts(max = 30) {
  const snap = await getDocs(query(collection(db(), 'official_alerts'), orderBy('created_at', 'desc'), limit(max)))
  return rows(snap)
}

export async function auditEvents(max = 100) {
  return rows(await getDocs(query(collection(db(), 'audit_events'), orderBy('created_at', 'desc'), limit(max))))
}
