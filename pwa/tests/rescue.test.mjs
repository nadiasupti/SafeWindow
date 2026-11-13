// Unit tests of the rescue logic that has no Firebase in it:  cd pwa && node --test tests/
import assert from 'node:assert/strict'
import { describe, test } from 'node:test'
import * as R from '../src/lib/rescue.js'

describe('triage suggestion', () => {
  test('immediate danger with rising water and a trapped household is critical or high', () => {
    const r = R.suggestPriority({ urgency: 'immediate', hazards: ['rising_water', 'trapped'], needs: {}, vulnerability_flags: {}, people_count: 3 })
    assert.equal(r.priority, 'CRITICAL')
    assert.deepEqual(r.factors, ['immediate_danger', 'rising_water', 'trapped'])
  })
  test('a calm request for water within a day is low', () => {
    const r = R.suggestPriority({ urgency: 'within_day', hazards: [], needs: { drinking_water: true }, vulnerability_flags: {}, people_count: 2 })
    assert.equal(r.priority, 'LOW')
    assert.deepEqual(r.factors, [])
  })
  test('vulnerability raises the suggestion but its detail never appears in the factors', () => {
    const r = R.suggestPriority({ urgency: 'within_hours', hazards: ['rising_water'], needs: {}, vulnerability_flags: { children: true, older_adults: true }, people_count: 3 })
    assert.ok(r.factors.includes('vulnerability_flagged'))
    assert.ok(!JSON.stringify(r.factors).includes('children'))
    assert.ok(R.PUBLIC_FACTORS.includes('vulnerability_flagged'))
  })
  test('nothing about money or ability to pay can lower a suggestion', () => {
    const base = { urgency: 'immediate', hazards: ['trapped'], needs: {}, vulnerability_flags: {}, people_count: 1 }
    const rich = R.suggestPriority({ ...base, can_pay: true, income: 99999 })
    assert.equal(rich.priority, R.suggestPriority(base).priority)
    assert.ok(!Object.keys(R.FACTOR_WEIGHTS).some((k) => /pay|income|money|wealth/i.test(k)))
  })
  test('every suggestion is one of the allowed levels', () => {
    for (const u of R.URGENCIES) for (const n of [1, 5, 50]) {
      assert.ok(R.PRIORITIES.includes(R.suggestPriority({ urgency: u, hazards: R.HAZARDS, needs: { medical: true, mobility_assistance: true }, vulnerability_flags: { children: true }, people_count: n }).priority))
    }
  })
})

describe('state tables', () => {
  test('dispatch is not rescue: an NGO cannot jump from DISPATCHED to RESCUED', () => {
    assert.equal(R.ngoCanStep('DISPATCHED', 'RESCUED'), false)
    assert.equal(R.ngoCanStep('DISPATCHED', 'IN_PROGRESS'), true)
    assert.equal(R.ngoCanStep('ACCEPTED', 'IN_PROGRESS'), false)
  })
  test('terminal states have no way out', () => {
    for (const from of R.TERMINAL) for (const to of R.STATUSES) {
      assert.equal(R.ngoCanStep(from, to), false, `${from}->${to}`)
      assert.equal(R.govCanStep(from, to), false, `${from}->${to}`)
    }
  })
  test('an NGO sees exactly the next steps', () => {
    assert.deepEqual(R.ngoNextSteps('IN_PROGRESS').map(([s]) => s), ['RESCUED', 'ASSISTANCE_DELIVERED', 'UNABLE_TO_REACH', 'REFERRED'])
    assert.deepEqual(R.ngoNextSteps('PENDING'), [])
    assert.deepEqual(R.ngoNextSteps('RESCUED'), [])
  })
  test('every status is reachable on paper from PENDING', () => {
    const seen = new Set(['PENDING'])
    let grew = true
    while (grew) {
      grew = false
      for (const from of [...seen]) for (const to of R.STATUSES) {
        if (!seen.has(to) && (R.ngoCanStep(from, to) || R.govCanStep(from, to) || (to === 'ACCEPTED' && R.ngoCanClaim(from))
          || (to === 'CANCELLED' && R.CITIZEN_CANCEL_FROM.includes(from)))) {
          seen.add(to); grew = true
        }
      }
    }
    assert.deepEqual([...seen].sort(), [...R.STATUSES].sort())
  })
})

describe('privacy split and validation', () => {
  const form = { latitude: '25.06571', longitude: '91.39512', accuracy_m: 18, location_source: 'gps', address_text: 'Dholkotob', people_count: '4',
    urgency: 'immediate', needs: { boat_rescue: true, medical: true }, hazards: ['trapped', 'bogus'], vulnerability_flags: { children: true },
    phone: '+880 1700-000001', notes: 'diabetic', consent_location: true, consent_sensitive: false }
  test('the public part has only the rounded area', () => {
    const { request, priv, sensitive } = R.buildRequestDocs(form, 'u1', 'T')
    assert.equal(request.coarse_lat, 25.07)
    assert.equal(request.coarse_lon, 91.4)
    const text = JSON.stringify(request)
    for (const secret of ['25.06571', '91.39512', '1700', 'diabetic', 'children', 'Dholkotob']) assert.ok(!text.includes(secret), secret)
    assert.equal(priv.exact.latitude, 25.06571)
    assert.equal(priv.phone, '+8801700000001')
    assert.equal(sensitive.notes, 'diabetic')
    assert.equal(sensitive.consent_sensitive, false)
    assert.deepEqual(request.hazards, ['trapped'])            // unknown hazard codes are dropped
    assert.equal(request.status, 'PENDING')
    assert.equal(request.version, 1)
  })
  test('validation catches the usual mistakes', () => {
    assert.deepEqual(R.validateRequest(form), {})
    assert.ok(R.validateRequest({ ...form, latitude: '' }).location)
    assert.ok(R.validateRequest({ ...form, latitude: '123' }).location)
    assert.ok(R.validateRequest({ ...form, people_count: '0' }).people_count)
    assert.ok(R.validateRequest({ ...form, people_count: '2.5' }).people_count)
    assert.ok(R.validateRequest({ ...form, phone: 'call me' }).phone)
    assert.ok(R.validateRequest({ ...form, urgency: 'whenever' }).urgency)
  })
  test('a new id is long, random and prefixed', () => {
    const a = R.newId('rr')
    const b = R.newId('rr')
    assert.match(a, /^rr_[0-9a-f]{24}$/)
    assert.notEqual(a, b)
  })
})

describe('stale records and the overview', () => {
  test('older than 12 hours, or with no time at all, is stale', () => {
    const now = Date.parse('2026-11-12T12:00:00Z')
    assert.equal(R.isStale('2026-11-12T10:00:00Z', now), false)
    assert.equal(R.isStale('2026-11-11T20:00:00Z', now), true)
    assert.equal(R.isStale(undefined, now), true)
    assert.equal(R.isStale({ toMillis: () => now - 3600 * 1000 }, now), false)
  })
  test('summary counts', () => {
    const now = Date.parse('2026-11-12T12:00:00Z')
    const at = (h) => ({ toMillis: () => now - h * 3600 * 1000 })
    const s = R.summarize([
      { status: 'PENDING', priority: 'HIGH', updated_at: at(0.1) },
      { status: 'TRIAGED', priority: 'LOW', updated_at: at(0.1) },
      { status: 'ACCEPTED', priority: 'HIGH', updated_at: at(5) },
      { status: 'RESCUED', priority: 'HIGH', updated_at: at(1) },
      { status: 'CLOSED', priority: 'LOW', updated_at: at(9) },
    ], now)
    assert.equal(s.total, 5)
    assert.equal(s.new, 1)
    assert.equal(s.active, 3)
    assert.equal(s.completed, 2)
    assert.equal(s.unassigned_urgent, 1)
    assert.equal(s.overdue, 1)
  })
})
