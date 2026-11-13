// Proves firestore.rules on the local Firestore emulator (no Firebase login needed):
//     cd pwa/rules-tests && npm install && npm test
//
// Covers the spec's minimum acceptance scenarios (section 13.1) and the safety rules of section 24, and checks that
// the state tables in src/lib/rescue.js (used by the screens) agree with what the rules really allow.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { after, before, describe, test } from 'node:test'
import { assertFails, assertSucceeds, initializeTestEnvironment } from '@firebase/rules-unit-testing'
import { Timestamp, collection, doc, getDoc, getDocs, query, serverTimestamp, setDoc, deleteDoc, updateDoc, where, writeBatch } from 'firebase/firestore'
import * as R from '../src/lib/rescue.js'

let env
const now = () => Timestamp.now()
const hours = (h) => Timestamp.fromMillis(Date.now() + h * 3600 * 1000)

before(async () => {
  env = await initializeTestEnvironment({
    projectId: 'demo-safewindow',
    firestore: { rules: readFileSync(new URL('../../firestore.rules', import.meta.url), 'utf8') },
  })
})
after(async () => env.cleanup())

const as = (uid, claims = {}) => env.authenticatedContext(uid, claims).firestore()
const anon = () => env.authenticatedContext('anon1', { firebase: { sign_in_provider: 'anonymous' } }).firestore()
const gov = (uid = 'gov1') => as(uid, { role: 'gov' })

async function reset() {
  await env.clearFirestore()
  await env.withSecurityRulesDisabled(async (ctx) => {
    const db = ctx.firestore()
    const ngo = (id, status, owner) => setDoc(doc(db, 'ngos', id), {
      legal_name: `NGO ${id}`, registration_details: 'reg 1', operating_areas: ['Sunamganj'], capabilities: ['boat'],
      contact_phone: '+8801700000000', status, owner_uid: owner, created_at: now(), updated_at: now() })
    const member = (uid, ngoId, role) => setDoc(doc(db, 'ngo_members', uid), {
      ngo_id: ngoId, member_role: role, active: true, created_at: now() })
    await ngo('A', 'approved', 'A_mgr'); await ngo('B', 'approved', 'B_mgr')
    await ngo('P', 'pending', 'P_mgr'); await ngo('S', 'suspended', 'S_mgr')
    await member('A_mgr', 'A', 'manager'); await member('A_w', 'A', 'worker')
    await member('B_mgr', 'B', 'manager'); await member('B_w', 'B', 'worker')
    await member('P_mgr', 'P', 'manager'); await member('S_mgr', 'S', 'manager')
  })
}

const NEEDS = Object.fromEntries(R.NEEDS.map((k) => [k, false]))
const FLAGS = Object.fromEntries(R.FLAGS.map((k) => [k, false]))

const requestDoc = (uid, over = {}) => ({
  citizen_id: uid, people_count: 3, urgency: 'immediate', needs: { ...NEEDS, boat_rescue: true }, hazards: ['rising_water'],
  coarse_lat: 25.07, coarse_lon: 91.4, suggested_priority: 'HIGH', priority: 'HIGH',
  priority_factors: ['immediate_danger', 'rising_water'], status: 'PENDING', version: 1,
  created_at: serverTimestamp(), updated_at: serverTimestamp(), ...over })
const privDoc = (uid, over = {}) => ({
  citizen_id: uid, exact: { latitude: 25.0657, longitude: 91.395, accuracy_m: 18, source: 'gps' }, address_text: 'Dholkotob',
  phone: '+8801700000001', consent_location: true, created_at: serverTimestamp(), ...over })
const sensDoc = (uid, over = {}) => ({
  citizen_id: uid, vulnerability_flags: { ...FLAGS, children: true }, notes: 'needs insulin', consent_sensitive: true,
  created_at: serverTimestamp(), ...over })
const logDoc = (uid, role, from, to, version, over = {}) => ({
  actor_id: uid, actor_role: role, ...(from ? { from_status: from } : {}), to_status: to, version, created_at: serverTimestamp(), ...over })

/** Create a request as a citizen: request + private + sensitive + history v1, in one batch. */
function createBatch(db, id, uid, { req = {}, priv = {}, sens = {}, log = {}, skipLog = false } = {}) {
  const b = writeBatch(db)
  b.set(doc(db, 'rescue_requests', id), requestDoc(uid, req))
  b.set(doc(db, 'rescue_private', id), privDoc(uid, priv))
  b.set(doc(db, 'rescue_sensitive', id), sensDoc(uid, sens))
  if (!skipLog) b.set(doc(db, 'rescue_requests', id, 'updates', 'v1'), logDoc(uid, 'citizen', null, 'PENDING', 1, log))
  return b
}

/** Seed a request directly (rules off), as it would be after some steps. */
async function seedRequest(id, uid, status, extra = {}, { priv = {}, sens = {}, version = 1 } = {}) {
  await env.withSecurityRulesDisabled(async (ctx) => {
    const db = ctx.firestore()
    await setDoc(doc(db, 'rescue_requests', id), requestDoc(uid, { status, version, created_at: now(), updated_at: now(), ...extra }))
    await setDoc(doc(db, 'rescue_private', id), privDoc(uid, { created_at: now(), ...priv }))
    await setDoc(doc(db, 'rescue_sensitive', id), sensDoc(uid, { created_at: now(), ...sens }))
    await setDoc(doc(db, 'rescue_requests', id, 'updates', `v${version}`), logDoc(uid, 'citizen', null, status, version, { created_at: now() }))
  })
}

let auditCounter = 0
/** A change to request `id` (currently `from`, `version`) plus its history entry (and an audit event for government). */
function moveBatch(db, id, uid, role, from, version, patch, { audit = role === 'gov', noLog = false, badVersion = false, note } = {}) {
  const b = writeBatch(db)
  const next = badVersion ? version : version + 1
  const fields = { ...patch, version: next, updated_at: serverTimestamp() }
  if (audit) {
    const aid = `aud_${++auditCounter}`
    fields.audit_id = aid
    b.set(doc(db, 'audit_events', aid), { actor_id: uid, action: 'test', entity_type: 'rescue_request', entity_id: id,
      reason: 'test reason', created_at: serverTimestamp() })
  }
  b.update(doc(db, 'rescue_requests', id), fields)
  if (!noLog) {
    b.set(doc(db, 'rescue_requests', id, 'updates', `v${version + 1}`),
      logDoc(uid, role, from, patch.status ?? from, version + 1, note ? { note } : {}))
  }
  return b
}

// ---------------------------------------------------------------------------------------------------------------

describe('existing village alerts keep working', () => {
  before(reset)
  test('a phone keeps only its own subscription', async () => {
    const sub = { token: 't', flood: 'sunamganj_2022', village: 'v1', lang: 'bn', updated: serverTimestamp() }
    await assertSucceeds(setDoc(doc(anon(), 'subscriptions', 'anon1'), sub))
    await assertFails(setDoc(doc(anon(), 'subscriptions', 'someone_else'), sub))
    await assertFails(getDoc(doc(anon(), 'alerts', 'x')))
  })
})

describe('profile and role', () => {
  before(reset)
  const profile = (over = {}) => ({ name: 'Rahim', lang: 'bn', assistance_profile: 'self_evacuation',
    created_at: serverTimestamp(), updated_at: serverTimestamp(), ...over })
  test('a citizen creates and reads their own profile', async () => {
    await assertSucceeds(setDoc(doc(as('c1'), 'users', 'c1'), profile()))
    await assertSucceeds(getDoc(doc(as('c1'), 'users', 'c1')))
    await assertFails(getDoc(doc(as('c2'), 'users', 'c1')))
  })
  test('a citizen cannot make themselves NGO or government by editing the payload (mass assignment)', async () => {
    await assertFails(setDoc(doc(as('c3'), 'users', 'c3'), profile({ role: 'gov' })))
    await assertFails(setDoc(doc(as('c3'), 'users', 'c3'), profile({ role: 'ngo', ngo_id: 'A' })))
    await assertFails(setDoc(doc(as('c3'), 'users', 'c3'), profile({ assistance_profile: 'admin' })))
  })
  test('an anonymous phone has no account profile', async () => {
    await assertFails(setDoc(doc(anon(), 'users', 'anon1'), profile()))
  })
  test('the assistance profile can be changed later', async () => {
    const db = as('c1')
    const snap = await getDoc(doc(db, 'users', 'c1'))
    await assertSucceeds(setDoc(doc(db, 'users', 'c1'), { ...snap.data(), assistance_profile: 'needs_assistance', updated_at: serverTimestamp() }))
  })
})

describe('citizen rescue request', () => {
  before(reset)
  test('creates a request whatever the assistance profile says (self-evacuation profile may still ask)', async () => {
    await assertSucceeds(createBatch(as('c1'), 'rr_ok', 'c1').commit())
  })
  test('anonymous phones cannot create a request', async () => {
    await assertFails(createBatch(anon(), 'rr_anon', 'anon1').commit())
  })
  test('cannot create a request for somebody else', async () => {
    await assertFails(createBatch(as('c1'), 'rr_other', 'c2').commit())
  })
  test('the client cannot choose the status, the version or the time', async () => {
    await assertFails(createBatch(as('c1'), 'rr_s', 'c1', { req: { status: 'ACCEPTED' } }).commit())
    await assertFails(createBatch(as('c1'), 'rr_v', 'c1', { req: { version: 5 } }).commit())
    await assertFails(createBatch(as('c1'), 'rr_t', 'c1', { req: { created_at: now() } }).commit())
  })
  test('unknown fields are refused (no mass assignment)', async () => {
    await assertFails(createBatch(as('c1'), 'rr_x1', 'c1', { req: { assigned_ngo_id: 'A' } }).commit())
    await assertFails(createBatch(as('c1'), 'rr_x2', 'c1', { req: { is_admin: true } }).commit())
  })
  test('bad values are refused', async () => {
    await assertFails(createBatch(as('c1'), 'rr_p0', 'c1', { req: { people_count: 0 } }).commit())
    await assertFails(createBatch(as('c1'), 'rr_p9', 'c1', { req: { people_count: 9999 } }).commit())
    await assertFails(createBatch(as('c1'), 'rr_u', 'c1', { req: { urgency: 'whenever' } }).commit())
    await assertFails(createBatch(as('c1'), 'rr_lat', 'c1', { req: { coarse_lat: 123 } }).commit())
    await assertFails(createBatch(as('c1'), 'rr_pr', 'c1', { req: { priority: 'CRITICAL' } }).commit())  // must equal the suggestion
    await assertFails(createBatch(as('c1'), 'rr_ph', 'c1', { priv: { phone: 'call me' } }).commit())
  })
  test('a request without its private part, sensitive part or history entry is refused', async () => {
    const db = as('c1')
    const b = writeBatch(db)
    b.set(doc(db, 'rescue_requests', 'rr_lonely'), requestDoc('c1'))
    await assertFails(b.commit())
    await assertFails(createBatch(db, 'rr_nolog', 'c1', { skipLog: true }).commit())
  })
  test('a retry with the same id cannot create a second request (idempotent)', async () => {
    await assertSucceeds(createBatch(as('c1'), 'rr_retry', 'c1').commit())
    await assertFails(createBatch(as('c1'), 'rr_retry', 'c1').commit())
  })
  test('the exact location and phone are not in the part every NGO can read', async () => {
    const d = requestDoc('c1')
    assert.ok(!('exact' in d) && !('phone' in d) && !('vulnerability_flags' in d) && !('notes' in d))
    const built = R.buildRequestDocs({ latitude: '25.06571', longitude: '91.39512', people_count: 4, urgency: 'immediate',
      phone: '01700000001', hazards: ['trapped'], needs: { medical: true }, vulnerability_flags: { children: true }, notes: 'secret' }, 'c1', 'T')
    assert.equal(built.request.coarse_lat, 25.07)
    assert.equal(JSON.stringify(built.request).includes('secret'), false)
    assert.equal(JSON.stringify(built.request).includes('children'), false)
    assert.ok(built.request.priority_factors.includes('vulnerability_flagged'))
  })
})

describe('read access to a request (IDOR)', () => {
  before(async () => {
    await reset()
    await seedRequest('rr1', 'c1', 'PENDING')
  })
  test('the owner reads all three parts and the history', async () => {
    const db = as('c1')
    for (const c of ['rescue_requests', 'rescue_private', 'rescue_sensitive']) await assertSucceeds(getDoc(doc(db, c, 'rr1')))
    await assertSucceeds(getDoc(doc(db, 'rescue_requests', 'rr1', 'updates', 'v1')))
  })
  test('another citizen changing the id in the URL reads nothing', async () => {
    const db = as('c2')
    for (const c of ['rescue_requests', 'rescue_private', 'rescue_sensitive']) await assertFails(getDoc(doc(db, c, 'rr1')))
    await assertFails(getDoc(doc(db, 'rescue_requests', 'rr1', 'updates', 'v1')))
    await assertFails(getDocs(collection(db, 'rescue_requests')))
  })
  test('a citizen can list only their own requests', async () => {
    await assertSucceeds(getDocs(query(collection(as('c1'), 'rescue_requests'), where('citizen_id', '==', 'c1'))))
    await assertFails(getDocs(query(collection(as('c2'), 'rescue_requests'), where('citizen_id', '==', 'c1'))))
  })
  test('an anonymous phone reads nothing', async () => {
    await assertFails(getDoc(doc(anon(), 'rescue_requests', 'rr1')))
  })
  test('the open queue shows an approved NGO the coarse part only', async () => {
    const db = as('A_w')
    await assertSucceeds(getDoc(doc(db, 'rescue_requests', 'rr1')))
    await assertFails(getDoc(doc(db, 'rescue_private', 'rr1')))
    await assertFails(getDoc(doc(db, 'rescue_sensitive', 'rr1')))
    await assertSucceeds(getDocs(query(collection(db, 'rescue_requests'), where('status', 'in', ['PENDING', 'TRIAGED']))))
  })
  test('an NGO that is not approved sees nothing: pending, suspended, not a member', async () => {
    for (const uid of ['P_mgr', 'S_mgr', 'nobody']) {
      await assertFails(getDoc(doc(as(uid), 'rescue_requests', 'rr1')))
      await assertFails(getDocs(query(collection(as(uid), 'rescue_requests'), where('status', 'in', ['PENDING', 'TRIAGED']))))
    }
  })
  test('government reads everything', async () => {
    for (const c of ['rescue_requests', 'rescue_private', 'rescue_sensitive']) await assertSucceeds(getDoc(doc(gov(), c, 'rr1')))
  })
  test('a user cannot become government by a claim on an anonymous login', async () => {
    const fake = env.authenticatedContext('x', { role: 'gov', firebase: { sign_in_provider: 'anonymous' } }).firestore()
    await assertFails(getDoc(doc(fake, 'rescue_private', 'rr1')))
  })
})

describe('claiming and the controlled steps', () => {
  before(reset)
  test('two NGOs claim the same request: only one succeeds', async () => {
    await seedRequest('rr_race', 'c1', 'PENDING')
    const claimA = moveBatch(as('A_w'), 'rr_race', 'A_w', 'ngo', 'PENDING', 1,
      { status: 'ACCEPTED', assigned_ngo_id: 'A', accepted_by: 'A_w' })
    const claimB = moveBatch(as('B_w'), 'rr_race', 'B_w', 'ngo', 'PENDING', 1,
      { status: 'ACCEPTED', assigned_ngo_id: 'B', accepted_by: 'B_w' })
    const results = await Promise.allSettled([claimA.commit(), claimB.commit()])
    assert.equal(results.filter((r) => r.status === 'fulfilled').length, 1)
    let snap
    await env.withSecurityRulesDisabled(async (ctx) => { snap = (await getDoc(doc(ctx.firestore(), 'rescue_requests', 'rr_race'))).data() })
    assert.equal(snap.version, 2)
    assert.equal(snap.status, 'ACCEPTED')
  })
  test('claiming for another organisation, as a non-member, or without a history entry fails', async () => {
    await seedRequest('rr_c1', 'c1', 'PENDING')
    await assertFails(moveBatch(as('A_w'), 'rr_c1', 'A_w', 'ngo', 'PENDING', 1, { status: 'ACCEPTED', assigned_ngo_id: 'B', accepted_by: 'A_w' }).commit())
    await assertFails(moveBatch(as('nobody'), 'rr_c1', 'nobody', 'ngo', 'PENDING', 1, { status: 'ACCEPTED', assigned_ngo_id: 'A', accepted_by: 'nobody' }).commit())
    await assertFails(moveBatch(as('P_mgr'), 'rr_c1', 'P_mgr', 'ngo', 'PENDING', 1, { status: 'ACCEPTED', assigned_ngo_id: 'P', accepted_by: 'P_mgr' }).commit())
    await assertFails(moveBatch(as('A_w'), 'rr_c1', 'A_w', 'ngo', 'PENDING', 1, { status: 'ACCEPTED', assigned_ngo_id: 'A', accepted_by: 'A_w' }, { noLog: true }).commit())
    await assertFails(moveBatch(as('A_w'), 'rr_c1', 'A_w', 'ngo', 'PENDING', 1, { status: 'ACCEPTED', assigned_ngo_id: 'A', accepted_by: 'A_w' }, { badVersion: true }).commit())
  })
  test('the full chain works step by step and no step can be skipped', async () => {
    await seedRequest('rr_chain', 'c1', 'PENDING')
    const db = as('A_w')
    let v = 1
    const go = (from, patch, ok = true) => {
      const b = moveBatch(db, 'rr_chain', 'A_w', 'ngo', from, v, patch)
      if (ok) v += 1
      return ok ? assertSucceeds(b.commit()) : assertFails(b.commit())
    }
    await go('PENDING', { status: 'ACCEPTED', assigned_ngo_id: 'A', accepted_by: 'A_w' })
    await go('ACCEPTED', { status: 'RESCUED', people_assisted: 3 }, false)         // dispatch is not rescue
    await go('ACCEPTED', { status: 'IN_PROGRESS' }, false)                         // no skipping
    await go('ACCEPTED', { status: 'PREPARING' })
    await go('PREPARING', { status: 'DISPATCHED' })
    await go('DISPATCHED', { status: 'RESCUED', people_assisted: 3 }, false)       // arrival comes first
    await go('DISPATCHED', { status: 'IN_PROGRESS' })
    await go('IN_PROGRESS', { status: 'RESCUED' }, false)                          // completion needs the people count
    await go('IN_PROGRESS', { status: 'RESCUED', people_assisted: -1 }, false)
    await go('IN_PROGRESS', { status: 'RESCUED', people_assisted: 3 })
    await go('RESCUED', { status: 'PREPARING' }, false)                            // no going back
  })
  test('another organisation cannot update a request assigned to someone else', async () => {
    await seedRequest('rr_mine', 'c1', 'ACCEPTED', { assigned_ngo_id: 'A', accepted_by: 'A_w' })
    await assertFails(moveBatch(as('B_w'), 'rr_mine', 'B_w', 'ngo', 'ACCEPTED', 1, { status: 'PREPARING' }).commit())
    await assertFails(getDoc(doc(as('B_w'), 'rescue_requests', 'rr_mine')))
    await assertSucceeds(getDoc(doc(as('A_w'), 'rescue_requests', 'rr_mine')))
    await assertSucceeds(getDocs(query(collection(as('A_w'), 'rescue_requests'), where('assigned_ngo_id', '==', 'A'))))
  })
  test('unable-to-reach and referral need a reason', async () => {
    await seedRequest('rr_utr', 'c1', 'DISPATCHED', { assigned_ngo_id: 'A', accepted_by: 'A_w' })
    await assertFails(moveBatch(as('A_w'), 'rr_utr', 'A_w', 'ngo', 'DISPATCHED', 1, { status: 'UNABLE_TO_REACH' }).commit())
    await assertSucceeds(moveBatch(as('A_w'), 'rr_utr', 'A_w', 'ngo', 'DISPATCHED', 1, { status: 'UNABLE_TO_REACH', status_reason: 'Channel blocked' }).commit())
  })
  test('an NGO can decline an assignment from government with a reason', async () => {
    await seedRequest('rr_dec', 'c1', 'ASSIGNED', { assigned_ngo_id: 'A', assigned_by: 'gov1' })
    await assertFails(moveBatch(as('A_w'), 'rr_dec', 'A_w', 'ngo', 'ASSIGNED', 1, { status: 'TRIAGED', assigned_ngo_id: null }).commit())
    await assertSucceeds(moveBatch(as('A_w'), 'rr_dec', 'A_w', 'ngo', 'ASSIGNED', 1, { status: 'TRIAGED', assigned_ngo_id: null, status_reason: 'No boat free' }).commit())
  })
  test('history entries cannot be edited or deleted', async () => {
    await seedRequest('rr_hist', 'c1', 'PENDING')
    for (const db of [as('c1'), gov(), as('A_w')]) {
      await assertFails(updateDoc(doc(db, 'rescue_requests', 'rr_hist', 'updates', 'v1'), { note: 'edited' }))
      await assertFails(deleteDoc(doc(db, 'rescue_requests', 'rr_hist', 'updates', 'v1')))
    }
    await assertFails(deleteDoc(doc(as('c1'), 'rescue_requests', 'rr_hist')))
    await assertFails(deleteDoc(doc(gov(), 'rescue_requests', 'rr_hist')))
  })
  test('a history entry that lies about the status is refused', async () => {
    await seedRequest('rr_lie', 'c1', 'PENDING')
    const db = as('A_w')
    const b = writeBatch(db)
    b.update(doc(db, 'rescue_requests', 'rr_lie'), { status: 'ACCEPTED', assigned_ngo_id: 'A', accepted_by: 'A_w', version: 2, updated_at: serverTimestamp() })
    b.set(doc(db, 'rescue_requests', 'rr_lie', 'updates', 'v2'), logDoc('A_w', 'ngo', 'PENDING', 'RESCUED', 2))
    await assertFails(b.commit())
  })
})

describe('citizen actions on their own request', () => {
  before(reset)
  test('cancel needs a reason and is possible only before completion', async () => {
    await seedRequest('rr_k1', 'c1', 'PENDING')
    await assertFails(moveBatch(as('c1'), 'rr_k1', 'c1', 'citizen', 'PENDING', 1, { status: 'CANCELLED' }).commit())
    await assertSucceeds(moveBatch(as('c1'), 'rr_k1', 'c1', 'citizen', 'PENDING', 1, { status: 'CANCELLED', status_reason: 'We got out' }).commit())
    await seedRequest('rr_k2', 'c1', 'RESCUED', { assigned_ngo_id: 'A' })
    await assertFails(moveBatch(as('c1'), 'rr_k2', 'c1', 'citizen', 'RESCUED', 1, { status: 'CANCELLED', status_reason: 'No longer needed' }).commit())
  })
  test('a citizen cannot mark their own request accepted, rescued or closed, or assign it', async () => {
    await seedRequest('rr_k3', 'c1', 'PENDING')
    for (const patch of [{ status: 'ACCEPTED', assigned_ngo_id: 'A', accepted_by: 'c1' }, { status: 'RESCUED', people_assisted: 3 },
      { status: 'CLOSED' }, { status: 'ASSIGNED', assigned_ngo_id: 'A' }, { priority: 'LOW' }]) {
      await assertFails(moveBatch(as('c1'), 'rr_k3', 'c1', 'citizen', 'PENDING', 1, patch).commit())
    }
  })
  test("a citizen cannot touch another citizen's request", async () => {
    await seedRequest('rr_k4', 'c1', 'PENDING')
    await assertFails(moveBatch(as('c2'), 'rr_k4', 'c2', 'citizen', 'PENDING', 1, { status: 'CANCELLED', status_reason: 'mine now' }).commit())
  })
  test('the citizen confirms or disputes the outcome', async () => {
    await seedRequest('rr_k5', 'c1', 'RESCUED', { assigned_ngo_id: 'A' })
    await assertFails(moveBatch(as('c1'), 'rr_k5', 'c1', 'citizen', 'RESCUED', 1, { citizen_confirmation: 'maybe' }).commit())
    await assertSucceeds(moveBatch(as('c1'), 'rr_k5', 'c1', 'citizen', 'RESCUED', 1, { citizen_confirmation: 'disputed' }).commit())
  })
})

describe('consent: who reads the exact location and the sensitive details', () => {
  before(reset)
  test('the assigned NGO reads them only after assignment and only with consent', async () => {
    await seedRequest('rr_a', 'c1', 'PENDING')
    await assertFails(getDoc(doc(as('A_w'), 'rescue_private', 'rr_a')))       // queue: not yet assigned
    await seedRequest('rr_b', 'c1', 'ACCEPTED', { assigned_ngo_id: 'A' })
    await assertSucceeds(getDoc(doc(as('A_w'), 'rescue_private', 'rr_b')))
    await assertSucceeds(getDoc(doc(as('A_w'), 'rescue_sensitive', 'rr_b')))
    await assertFails(getDoc(doc(as('B_w'), 'rescue_private', 'rr_b')))        // another organisation
    await assertFails(getDoc(doc(as('B_w'), 'rescue_sensitive', 'rr_b')))
  })
  test('location and sensitive needs have separate consent', async () => {
    await seedRequest('rr_c', 'c1', 'ACCEPTED', { assigned_ngo_id: 'A' }, { priv: { consent_location: true }, sens: { consent_sensitive: false } })
    await assertSucceeds(getDoc(doc(as('A_w'), 'rescue_private', 'rr_c')))
    await assertFails(getDoc(doc(as('A_w'), 'rescue_sensitive', 'rr_c')))
    await seedRequest('rr_d', 'c1', 'ACCEPTED', { assigned_ngo_id: 'A' }, { priv: { consent_location: false }, sens: { consent_sensitive: true } })
    await assertFails(getDoc(doc(as('A_w'), 'rescue_private', 'rr_d')))
    await assertSucceeds(getDoc(doc(as('A_w'), 'rescue_sensitive', 'rr_d')))
  })
  test('access ends when the request ends', async () => {
    await seedRequest('rr_e', 'c1', 'CLOSED', { assigned_ngo_id: 'A' })
    await assertFails(getDoc(doc(as('A_w'), 'rescue_private', 'rr_e')))
    await assertSucceeds(getDoc(doc(gov(), 'rescue_private', 'rr_e')))
  })
  test('private parts cannot be edited or deleted by anyone', async () => {
    await seedRequest('rr_f', 'c1', 'PENDING')
    for (const db of [as('c1'), gov(), as('A_w')]) {
      await assertFails(updateDoc(doc(db, 'rescue_private', 'rr_f'), { phone: '+8801999999999' }))
      await assertFails(deleteDoc(doc(db, 'rescue_private', 'rr_f')))
    }
  })
})

describe('government actions', () => {
  before(async () => {
    await reset()
  })
  const act = (id, from, version, patch, opts = {}, db = gov()) => moveBatch(db, id, 'gov1', 'gov', from, version, patch, opts)
  test('assign with reason and audit event succeeds; the history keeps the earlier entries', async () => {
    await seedRequest('rr_g1', 'c1', 'PENDING')
    await assertSucceeds(act('rr_g1', 'PENDING', 1, { status: 'ASSIGNED', assigned_ngo_id: 'A', assigned_by: 'gov1', accepted_by: null, status_reason: 'Closest boat' }).commit())
    // reassign
    await assertSucceeds(act('rr_g1', 'ASSIGNED', 2, { status: 'ASSIGNED', assigned_ngo_id: 'B', assigned_by: 'gov1', accepted_by: null, status_reason: 'Team A has no boat' }).commit())
    const v1 = await assertSucceeds(getDoc(doc(gov(), 'rescue_requests', 'rr_g1', 'updates', 'v1')))
    const v2 = await assertSucceeds(getDoc(doc(gov(), 'rescue_requests', 'rr_g1', 'updates', 'v2')))
    assert.ok(v1.exists() && v2.exists())
  })
  test('without a reason, without an audit event, or for an unapproved NGO it fails', async () => {
    await seedRequest('rr_g2', 'c1', 'PENDING')
    const base = { status: 'ASSIGNED', assigned_ngo_id: 'A', assigned_by: 'gov1', accepted_by: null, status_reason: 'Closest boat' }
    const { status_reason: _omitted, ...noReason } = base
    await assertFails(act('rr_g2', 'PENDING', 1, noReason).commit())
    await assertFails(act('rr_g2', 'PENDING', 1, { ...base, status_reason: 'x' }).commit())
    await assertFails(act('rr_g2', 'PENDING', 1, base, { audit: false }).commit())
    await assertFails(act('rr_g2', 'PENDING', 1, { ...base, assigned_ngo_id: 'P' }).commit())     // pending NGO
    await assertFails(act('rr_g2', 'PENDING', 1, { ...base, assigned_ngo_id: 'S' }).commit())     // suspended NGO
    await assertFails(act('rr_g2', 'PENDING', 1, { ...base, assigned_by: 'someone_else' }).commit())
  })
  test('the audit event must name this request and this actor', async () => {
    await seedRequest('rr_g3', 'c1', 'PENDING')
    const db = gov()
    const b = writeBatch(db)
    b.set(doc(db, 'audit_events', 'aud_wrong'), { actor_id: 'gov1', action: 'x', entity_type: 'rescue_request', entity_id: 'another_request', reason: 'test reason', created_at: serverTimestamp() })
    b.update(doc(db, 'rescue_requests', 'rr_g3'), { status: 'TRIAGED', audit_id: 'aud_wrong', version: 2, updated_at: serverTimestamp() })
    b.set(doc(db, 'rescue_requests', 'rr_g3', 'updates', 'v2'), logDoc('gov1', 'gov', 'PENDING', 'TRIAGED', 2))
    await assertFails(b.commit())
  })
  test('a user without the government claim cannot use any government action', async () => {
    await seedRequest('rr_g4', 'c1', 'PENDING')
    for (const db of [as('c1'), as('A_mgr'), as('gov1_without_claim')]) {
      await assertFails(moveBatch(db, 'rr_g4', 'gov1', 'gov', 'PENDING', 1, { status: 'TRIAGED' }).commit())
    }
  })
  test('priority override needs a reason', async () => {
    await seedRequest('rr_g5', 'c1', 'PENDING')
    await assertFails(act('rr_g5', 'PENDING', 1, { priority: 'LOW' }).commit())
    await assertSucceeds(act('rr_g5', 'PENDING', 1, { priority: 'LOW', priority_reason: 'Reported duplicate of a smaller case' }).commit())
  })
  test('closed requests cannot be reopened and nothing is deleted', async () => {
    await seedRequest('rr_g6', 'c1', 'CLOSED')
    await assertFails(act('rr_g6', 'CLOSED', 1, { status: 'ASSIGNED', assigned_ngo_id: 'A', assigned_by: 'gov1', accepted_by: null, status_reason: 'reopen' }).commit())
    await assertFails(deleteDoc(doc(gov(), 'rescue_requests', 'rr_g6')))
  })
})

describe('NGO application, approval, invitations and resources', () => {
  before(reset)
  const application = (uid, over = {}) => ({
    legal_name: 'Haor Rescue', registration_details: 'Reg 123, NGOAB', operating_areas: ['Sunamganj'], capabilities: ['boat', 'medical'],
    contact_phone: '+8801700000009', status: 'pending', owner_uid: uid, created_at: serverTimestamp(), updated_at: serverTimestamp(), ...over })
  const applyBatch = (db, uid, id, over = {}) => {
    const b = writeBatch(db)
    b.set(doc(db, 'ngos', id), application(uid, over))
    b.set(doc(db, 'ngo_members', uid), { ngo_id: id, member_role: 'manager', active: true, created_at: serverTimestamp() })
    return b
  }
  test('a registered user applies and becomes the manager of a pending organisation', async () => {
    await assertSucceeds(applyBatch(as('n1'), 'n1', 'ngo_n1').commit())
  })
  test('an application cannot start as approved, or be created by an anonymous phone or for someone else', async () => {
    await assertFails(applyBatch(as('n2'), 'n2', 'ngo_n2', { status: 'approved' }).commit())
    await assertFails(applyBatch(anon(), 'anon1', 'ngo_an').commit())
    await assertFails(applyBatch(as('n2'), 'n3', 'ngo_n3x').commit())
  })
  test('one person cannot open a second organisation', async () => {
    await assertFails(applyBatch(as('n1'), 'n1', 'ngo_n1_second').commit())
  })
  test('a pending organisation cannot approve itself; government can, with audit', async () => {
    const self = as('n1')
    await assertFails(updateDoc(doc(self, 'ngos', 'ngo_n1'), { status: 'approved', updated_at: serverTimestamp() }))
    await assertFails(updateDoc(doc(self, 'ngos', 'ngo_n1'), { status: 'approved', decided_by: 'n1', decided_at: serverTimestamp(), status_reason: 'trust me', updated_at: serverTimestamp() }))
    const g = gov()
    const decide = (status, audit = true, reason = 'Documents checked') => {
      const b = writeBatch(g)
      const fields = { status, status_reason: reason, decided_by: 'gov1', decided_at: serverTimestamp(), updated_at: serverTimestamp() }
      if (audit) {
        fields.audit_id = `aud_ngo_${++auditCounter}`
        b.set(doc(g, 'audit_events', fields.audit_id), { actor_id: 'gov1', action: `ngo_${status}`, entity_type: 'ngo', entity_id: 'ngo_n1', reason, created_at: serverTimestamp() })
      }
      b.update(doc(g, 'ngos', 'ngo_n1'), fields)
      return b
    }
    await assertFails(decide('approved', false).commit())
    await assertFails(decide('approved', true, '').commit())
    await assertSucceeds(decide('approved').commit())
    await assertSucceeds(decide('suspended', true, 'Complaint under review').commit())
    await assertSucceeds(decide('approved', true, 'Reinstated after review').commit())
  })
  test('the manager edits the profile but never the verification status', async () => {
    const db = as('A_mgr')
    await assertSucceeds(updateDoc(doc(db, 'ngos', 'A'), { operating_areas: ['Sunamganj', 'Sylhet'], updated_at: serverTimestamp() }))
    await assertFails(updateDoc(doc(db, 'ngos', 'A'), { status: 'suspended', updated_at: serverTimestamp() }))
    await assertFails(updateDoc(doc(as('A_w'), 'ngos', 'A'), { operating_areas: ['x'], updated_at: serverTimestamp() }))
    await assertFails(updateDoc(doc(as('B_mgr'), 'ngos', 'A'), { operating_areas: ['x'], updated_at: serverTimestamp() }))
  })
  test("an NGO cannot read another NGO's profile; government can read all", async () => {
    await assertFails(getDoc(doc(as('A_w'), 'ngos', 'B')))
    await assertSucceeds(getDoc(doc(as('A_w'), 'ngos', 'A')))
    await assertSucceeds(getDoc(doc(gov(), 'ngos', 'B')))
  })
  test('invitations: a worker joins with a valid code once; used, expired or unapproved-NGO codes fail', async () => {
    const m = as('A_mgr')
    const code = 'invite_code_abcdef12345'
    await assertSucceeds(setDoc(doc(m, 'ngo_invites', code), { ngo_id: 'A', created_by: 'A_mgr', expires_at: hours(24), created_at: serverTimestamp() }))
    await assertFails(setDoc(doc(as('A_w'), 'ngo_invites', 'invite_by_worker_12345'), { ngo_id: 'A', created_by: 'A_w', expires_at: hours(24), created_at: serverTimestamp() }))
    await assertFails(setDoc(doc(m, 'ngo_invites', 'invite_for_other_ngo_12'), { ngo_id: 'B', created_by: 'A_mgr', expires_at: hours(24), created_at: serverTimestamp() }))
    const join = (uid, c, ngoId = 'A') => {
      const db = as(uid); const b = writeBatch(db)
      b.update(doc(db, 'ngo_invites', c), { used_by: uid, used_at: serverTimestamp() })
      b.set(doc(db, 'ngo_members', uid), { ngo_id: ngoId, member_role: 'worker', active: true, invite_code: c, created_at: serverTimestamp() })
      return b
    }
    await assertSucceeds(join('w_new', code).commit())
    await assertFails(join('w_late', code).commit())                       // already used
    await env.withSecurityRulesDisabled(async (ctx) => {
      await setDoc(doc(ctx.firestore(), 'ngo_invites', 'expired_code_123456'), { ngo_id: 'A', created_by: 'A_mgr', expires_at: Timestamp.fromMillis(Date.now() - 1000), created_at: now() })
      await setDoc(doc(ctx.firestore(), 'ngo_invites', 'suspended_ngo_code_1'), { ngo_id: 'S', created_by: 'S_mgr', expires_at: hours(24), created_at: now() })
    })
    await assertFails(join('w_exp', 'expired_code_123456').commit())
    await assertFails(join('w_s', 'suspended_ngo_code_1', 'S').commit())
    await assertFails(getDocs(collection(as('w_new'), 'ngo_invites')))     // codes cannot be listed
  })
  test('a member cannot promote themselves or switch organisation', async () => {
    await assertFails(updateDoc(doc(as('A_w'), 'ngo_members', 'A_w'), { member_role: 'manager', updated_at: serverTimestamp() }))
    await assertFails(updateDoc(doc(as('A_w'), 'ngo_members', 'A_w'), { ngo_id: 'B', updated_at: serverTimestamp() }))
    await assertSucceeds(updateDoc(doc(as('A_mgr'), 'ngo_members', 'A_w'), { team: 'Boat 1', updated_at: serverTimestamp() }))
    await assertFails(updateDoc(doc(as('A_mgr'), 'ngo_members', 'B_w'), { team: 'Boat 1', updated_at: serverTimestamp() }))
  })
  test('resources: manager writes with a server time; bad values and other NGOs are refused', async () => {
    const res = (over = {}) => ({ ngo_id: 'A', type: 'boat', quantity: 3, availability: 'available', location_text: 'Dowarabazar', condition: 'good', last_reported_at: serverTimestamp(), ...over })
    await assertSucceeds(setDoc(doc(as('A_mgr'), 'resources', 'res1'), res()))
    await assertFails(setDoc(doc(as('A_mgr'), 'resources', 'res2'), res({ quantity: -1 })))
    await assertFails(setDoc(doc(as('A_mgr'), 'resources', 'res3'), res({ last_reported_at: now() })))
    await assertFails(setDoc(doc(as('A_mgr'), 'resources', 'res4'), res({ ngo_id: 'B' })))
    await assertFails(setDoc(doc(as('A_w'), 'resources', 'res5'), res()))
    await assertFails(setDoc(doc(as('P_mgr'), 'resources', 'res6'), res({ ngo_id: 'P' })))   // not approved
    await assertSucceeds(getDoc(doc(as('A_w'), 'resources', 'res1')))
    await assertFails(getDoc(doc(as('B_w'), 'resources', 'res1')))
    await assertSucceeds(getDoc(doc(gov(), 'resources', 'res1')))
    await assertSucceeds(setDoc(doc(as('A_mgr'), 'resources', 'res1'), res({ quantity: 2, retired: true })))
  })
})

describe('official alerts and audit', () => {
  before(reset)
  const alertDoc = (aid, over = {}) => ({ flood: 'sunamganj_2022', severity: 'warning', title: 'Rising water', body: 'Move to higher ground.',
    source: 'FFWC bulletin 12 Nov', starts_at: now(), expires_at: hours(24), status: 'published', author_id: 'gov1', audit_id: `aud_${aid}`,
    created_at: serverTimestamp(), ...over })
  const publish = (db, aid, over = {}, uid = 'gov1') => {
    const b = writeBatch(db)
    b.set(doc(db, 'audit_events', `aud_${aid}`), { actor_id: uid, action: 'publish_alert', entity_type: 'alert', entity_id: aid, reason: 'Official bulletin', created_at: serverTimestamp() })
    b.set(doc(db, 'official_alerts', aid), alertDoc(aid, over))
    return b
  }
  test('government publishes with a source, an expiry and an audit event', async () => {
    await assertSucceeds(publish(gov(), 'al1').commit())
  })
  test('no source, an expiry longer than 72 hours, or a missing audit event is refused', async () => {
    await assertFails(publish(gov(), 'al2', { source: '' }).commit())
    await assertFails(publish(gov(), 'al3', { expires_at: hours(100) }).commit())
    const db = gov(); const b = writeBatch(db)
    b.set(doc(db, 'official_alerts', 'al4'), alertDoc('al4'))
    await assertFails(b.commit())
  })
  test('citizens, NGOs and anonymous phones cannot publish', async () => {
    for (const db of [as('c1'), as('A_mgr'), anon()]) await assertFails(publish(db, `al_x${Math.random()}`.replace('.', '')).commit())
  })
  test('everyone can read alerts, signed in or not, but nobody except government can list audit or requests', async () => {
    for (const db of [as('c1'), anon(), as('A_w'), env.unauthenticatedContext().firestore()]) await assertSucceeds(getDoc(doc(db, 'official_alerts', 'al1')))
    await assertFails(getDocs(collection(env.unauthenticatedContext().firestore(), 'rescue_requests')))
  })
  test('withdrawing needs a reason and an audit event; alerts are never deleted', async () => {
    const db = gov(); const b = writeBatch(db)
    b.set(doc(db, 'audit_events', 'aud_w1'), { actor_id: 'gov1', action: 'withdraw_alert', entity_type: 'alert', entity_id: 'al1', reason: 'Issued in error', created_at: serverTimestamp() })
    b.update(doc(db, 'official_alerts', 'al1'), { status: 'withdrawn', status_reason: 'Issued in error', audit_id: 'aud_w1', withdrawn_at: serverTimestamp() })
    await assertSucceeds(b.commit())
    await assertFails(deleteDoc(doc(gov(), 'official_alerts', 'al1')))
    await assertFails(updateDoc(doc(gov(), 'official_alerts', 'al1'), { body: 'changed quietly' }))
  })
  test('the audit trail is government-only and append-only', async () => {
    await assertSucceeds(getDoc(doc(gov(), 'audit_events', 'aud_al1')))
    await assertFails(getDoc(doc(as('c1'), 'audit_events', 'aud_al1')))
    await assertFails(getDoc(doc(as('A_mgr'), 'audit_events', 'aud_al1')))
    await assertFails(updateDoc(doc(gov(), 'audit_events', 'aud_al1'), { reason: 'rewritten' }))
    await assertFails(deleteDoc(doc(gov(), 'audit_events', 'aud_al1')))
  })
})

// ---------------------------------------------------------------------------------------------------------------
// The tables the screens use must be exactly what the rules allow.

describe('state tables in src/lib/rescue.js agree with firestore.rules', () => {
  before(reset)
  const assigned = (s) => ({ assigned_ngo_id: 'A', accepted_by: 'A_w', ...(s === 'ASSIGNED' ? { assigned_by: 'gov1' } : {}) })

  test('every NGO transition', async () => {
    const wrong = []
    for (const from of R.STATUSES) {
      for (const to of R.STATUSES) {
        const id = `n_${from}_${to}`
        await seedRequest(id, 'c1', from, assigned(from))
        const progress = moveBatch(as('A_w'), id, 'A_w', 'ngo', from, 1, { status: to, status_reason: 'because', people_assisted: 2 })
        const claim = moveBatch(as('A_w'), id, 'A_w', 'ngo', from, 1, { status: to, assigned_ngo_id: 'A', accepted_by: 'A_w' })
        const got = (await progress.commit().then(() => true, () => false))
          || (to === 'ACCEPTED' && (await seedAgain(id, from) && await claim.commit().then(() => true, () => false)))
        const want = R.ngoCanStep(from, to) || (to === 'ACCEPTED' && R.ngoCanClaim(from))
        if (got !== want) wrong.push(`${from}->${to}: rules ${got}, table ${want}`)
      }
    }
    assert.deepEqual(wrong, [])
  })

  async function seedAgain(id, from) {
    await seedRequest(id, 'c1', from, assigned(from))
    return true
  }

  test('every government transition', async () => {
    const wrong = []
    const payload = (to) => {
      if (to === 'ASSIGNED') return { status: to, assigned_ngo_id: 'B', assigned_by: 'gov1', accepted_by: null, status_reason: 'coverage' }
      if (to === 'TRIAGED') return { status: to }
      return { status: to, status_reason: 'reason text' }
    }
    for (const from of R.STATUSES) {
      for (const to of R.STATUSES) {
        const id = `g_${from}_${to}`
        await seedRequest(id, 'c1', from, assigned(from))
        const got = await moveBatch(gov(), id, 'gov1', 'gov', from, 1, payload(to)).commit().then(() => true, () => false)
        if (got !== R.govCanStep(from, to)) wrong.push(`${from}->${to}: rules ${got}, table ${R.govCanStep(from, to)}`)
      }
    }
    assert.deepEqual(wrong, [])
  })

  test('every citizen transition', async () => {
    const wrong = []
    for (const from of R.STATUSES) {
      for (const to of R.STATUSES) {
        const id = `c_${from}_${to}`
        await seedRequest(id, 'c1', from, from === 'PENDING' || from === 'TRIAGED' ? {} : assigned(from))
        const got = await moveBatch(as('c1'), id, 'c1', 'citizen', from, 1, { status: to, status_reason: 'my reason' }).commit().then(() => true, () => false)
        const want = to === 'CANCELLED' && R.CITIZEN_CANCEL_FROM.includes(from)
        if (got !== want) wrong.push(`${from}->${to}: rules ${got}, table ${want}`)
      }
    }
    assert.deepEqual(wrong, [])
  })
})
