// Rescue-request rules shared by the app screens: the controlled states, the transparent triage suggestion,
// the privacy split of a request and its validation. Pure functions, no Firebase: tested by tests/rescue.test.mjs.
//
// SAFETY, in plain words (spec section 24): a request received is not an assignment, an assignment is not a
// dispatch and a dispatch is not a rescue. The status texts below never say more than the data shows.
// The state rules are ALSO enforced by firestore.rules; rules-tests/rules.test.mjs checks the two agree.

export const STATUSES = [
  'PENDING', 'TRIAGED', 'ASSIGNED', 'ACCEPTED', 'PREPARING', 'DISPATCHED', 'IN_PROGRESS',
  'RESCUED', 'ASSISTANCE_DELIVERED', 'CLOSED', 'CANCELLED', 'DUPLICATE', 'UNABLE_TO_REACH', 'REFERRED', 'REJECTED',
]

export const TERMINAL = ['CLOSED', 'CANCELLED', 'DUPLICATE', 'REJECTED']
export const ACTIVE = ['PENDING', 'TRIAGED', 'ASSIGNED', 'ACCEPTED', 'PREPARING', 'DISPATCHED', 'IN_PROGRESS', 'UNABLE_TO_REACH']

/** Who may move a request from one state to the next. Mirrors firestore.rules. */
export const NGO_STEPS = {
  ACCEPTED: ['PREPARING'],
  PREPARING: ['DISPATCHED'],
  DISPATCHED: ['IN_PROGRESS'],
  IN_PROGRESS: ['RESCUED', 'ASSISTANCE_DELIVERED'],
}
export const NGO_EXITS = ['ACCEPTED', 'PREPARING', 'DISPATCHED', 'IN_PROGRESS']   // may end as UNABLE_TO_REACH or REFERRED
export const CITIZEN_CANCEL_FROM = ['PENDING', 'TRIAGED', 'ASSIGNED', 'ACCEPTED', 'PREPARING', 'DISPATCHED']
export const CLAIM_FROM = ['PENDING', 'TRIAGED']
export const GOV_ASSIGN_FROM = ['PENDING', 'TRIAGED', 'ASSIGNED', 'ACCEPTED', 'PREPARING', 'DISPATCHED', 'UNABLE_TO_REACH']
export const GOV_CLOSE_FROM = ['RESCUED', 'ASSISTANCE_DELIVERED', 'UNABLE_TO_REACH', 'REFERRED']
export const GOV_EARLY_END_FROM = ['PENDING', 'TRIAGED']          // duplicate / rejected
export const GOV_CANCEL_FROM = ACTIVE

export function ngoCanStep(from, to) {
  if (NGO_STEPS[from]?.includes(to)) return true
  return NGO_EXITS.includes(from) && (to === 'UNABLE_TO_REACH' || to === 'REFERRED')
}

/** An NGO may claim an unclaimed request, or accept one that government assigned to it. */
export function ngoCanClaim(from) {
  return CLAIM_FROM.includes(from) || from === 'ASSIGNED'
}

export function govCanStep(from, to) {
  if (to === 'TRIAGED') return from === 'PENDING'
  if (to === 'ASSIGNED') return GOV_ASSIGN_FROM.includes(from)
  if (to === 'CLOSED') return GOV_CLOSE_FROM.includes(from)
  if (to === 'DUPLICATE' || to === 'REJECTED') return GOV_EARLY_END_FROM.includes(from)
  if (to === 'CANCELLED') return GOV_CANCEL_FROM.includes(from)
  return false
}

/** The next buttons an NGO team may press for a request, as [status, needsReason]. */
export function ngoNextSteps(status) {
  const next = (NGO_STEPS[status] || []).map((s) => [s, false])
  if (NGO_EXITS.includes(status)) next.push(['UNABLE_TO_REACH', true], ['REFERRED', true])
  return next
}

// --- triage: a suggestion from explicit factors, never an automatic decision ---------------------------------

export const NEEDS = ['boat_rescue', 'medical', 'food', 'drinking_water', 'medicine', 'mobility_assistance']
export const FLAGS = ['children', 'older_adults', 'disability_or_limited_mobility', 'pregnancy']
export const HAZARDS = ['rising_water', 'trapped', 'no_exit_route', 'fire_or_electric', 'other']
export const URGENCIES = ['immediate', 'within_hours', 'within_day']
export const PRIORITIES = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL']

// Weights are visible and adjustable. Income, ability to pay, age, gender and disability are never used to
// deny help; vulnerability only raises the suggestion so a trained person looks at the case sooner.
export const FACTOR_WEIGHTS = {
  immediate_danger: 4,
  rising_water: 3,
  trapped: 3,
  fire_or_electric: 3,
  medical_need: 3,
  no_exit_route: 2,
  mobility_need: 2,
  vulnerability_flagged: 2,
  many_people: 1,
}
export const PRIORITY_CUTS = { CRITICAL: 8, HIGH: 5, MEDIUM: 2 }
export const PUBLIC_FACTORS = Object.keys(FACTOR_WEIGHTS)

/**
 * Suggested priority and the reasons for it. `factors` holds codes only: the specific vulnerability
 * (children, older adults ...) is never copied into the part of the request that every NGO can read.
 */
export function suggestPriority(input) {
  const factors = []
  if (input.urgency === 'immediate') factors.push('immediate_danger')
  for (const h of input.hazards || []) if (h in FACTOR_WEIGHTS) factors.push(h)
  if (input.needs?.medical) factors.push('medical_need')
  if (input.needs?.mobility_assistance) factors.push('mobility_need')
  if (Object.values(input.vulnerability_flags || {}).some(Boolean)) factors.push('vulnerability_flagged')
  if ((input.people_count || 0) >= 5) factors.push('many_people')
  const score = factors.reduce((sum, f) => sum + FACTOR_WEIGHTS[f], 0)
  const level = score >= PRIORITY_CUTS.CRITICAL ? 'CRITICAL' : score >= PRIORITY_CUTS.HIGH ? 'HIGH' : score >= PRIORITY_CUTS.MEDIUM ? 'MEDIUM' : 'LOW'
  return { priority: level, factors, score }
}

// --- privacy split --------------------------------------------------------------------------------------------

/** About 1 km: enough for a team to see the area, not the house. */
export function coarse(value) {
  return Math.round(Number(value) * 100) / 100
}

/** Light check before sending; the same limits are enforced by firestore.rules. Returns {field: messageKey}. */
export function validateRequest(form) {
  const errors = {}
  const lat = Number(form.latitude)
  const lon = Number(form.longitude)
  if (!Number.isFinite(lat) || lat < -90 || lat > 90 || !Number.isFinite(lon) || lon < -180 || lon > 180 || form.latitude === '' || form.longitude === '') {
    errors.location = 'rp_err_location'
  }
  const n = Number(form.people_count)
  if (!Number.isInteger(n) || n < 1 || n > 200) errors.people_count = 'rp_err_people'
  if (!URGENCIES.includes(form.urgency)) errors.urgency = 'rp_err_urgency'
  const phone = String(form.phone || '').replace(/[\s-]/g, '')
  if (!/^\+?\d{6,15}$/.test(phone)) errors.phone = 'rp_err_phone'
  if (String(form.notes || '').length > 500) errors.notes = 'rp_err_notes'
  return errors
}

/**
 * Splits one form into the three documents (see firestore.rules):
 *  request   - what every verified NGO may read: coarse location, how many people, urgency, needs, priority;
 *  priv      - exact location and contact: only the citizen, the assigned team (if allowed) and government;
 *  sensitive - vulnerability flags and notes: only if the citizen agrees to share them with the assigned team.
 */
export function buildRequestDocs(form, uid, serverTime) {
  const needs = Object.fromEntries(NEEDS.map((k) => [k, Boolean(form.needs?.[k])]))
  const flags = Object.fromEntries(FLAGS.map((k) => [k, Boolean(form.vulnerability_flags?.[k])]))
  const hazards = HAZARDS.filter((h) => form.hazards?.includes(h))
  const { priority, factors } = suggestPriority({ ...form, needs, vulnerability_flags: flags, hazards, people_count: Number(form.people_count) })
  const request = {
    citizen_id: uid,
    people_count: Number(form.people_count),
    urgency: form.urgency,
    needs,
    hazards,
    coarse_lat: coarse(form.latitude),
    coarse_lon: coarse(form.longitude),
    suggested_priority: priority,
    priority,
    priority_factors: factors,
    status: 'PENDING',
    version: 1,
    created_at: serverTime,
    updated_at: serverTime,
  }
  if (form.region) request.region = String(form.region)
  const priv = {
    citizen_id: uid,
    exact: {
      latitude: Number(form.latitude),
      longitude: Number(form.longitude),
      accuracy_m: form.accuracy_m == null || form.accuracy_m === '' ? null : Number(form.accuracy_m),
      source: form.location_source === 'gps' ? 'gps' : 'manual',
    },
    address_text: String(form.address_text || '').slice(0, 200),
    phone: String(form.phone).replace(/[\s-]/g, ''),
    consent_location: Boolean(form.consent_location),
    created_at: serverTime,
  }
  const sensitive = {
    citizen_id: uid,
    vulnerability_flags: flags,
    notes: String(form.notes || '').slice(0, 500),
    consent_sensitive: Boolean(form.consent_sensitive),
    created_at: serverTime,
  }
  return { request, priv, sensitive }
}

/** Resource records and shelter capacity go stale: a report older than this is labelled. */
export const STALE_HOURS = 12

export function isStale(timestamp, now = Date.now(), hours = STALE_HOURS) {
  const ms = typeof timestamp?.toMillis === 'function' ? timestamp.toMillis() : Date.parse(timestamp)
  return !Number.isFinite(ms) || now - ms > hours * 3600 * 1000
}

/** A random id made on the phone. Reusing it on a retry cannot create a second request. */
export function newId(prefix = 'rr') {
  const bytes = new Uint8Array(12)
  crypto.getRandomValues(bytes)
  return `${prefix}_${Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')}`
}

/** Plain counts for the government overview. */
export function summarize(requests, now = Date.now(), overdueHours = 2) {
  const out = { total: requests.length, by_status: {}, new: 0, active: 0, completed: 0, unassigned_urgent: 0, overdue: 0 }
  for (const r of requests) {
    out.by_status[r.status] = (out.by_status[r.status] || 0) + 1
    if (r.status === 'PENDING') out.new += 1
    if (ACTIVE.includes(r.status)) out.active += 1
    if (['RESCUED', 'ASSISTANCE_DELIVERED', 'CLOSED'].includes(r.status)) out.completed += 1
    if (['PENDING', 'TRIAGED'].includes(r.status) && ['HIGH', 'CRITICAL'].includes(r.priority)) out.unassigned_urgent += 1
    const updated = typeof r.updated_at?.toMillis === 'function' ? r.updated_at.toMillis() : Date.parse(r.updated_at)
    if (ACTIVE.includes(r.status) && Number.isFinite(updated) && now - updated > overdueHours * 3600 * 1000) out.overdue += 1
  }
  return out
}
