// End-to-end test of the three roles in a real browser, against the local Firebase emulators only
// (the app is started with VITE_EMULATORS=1, which also swaps the project id for a fake "demo-" one).
//
//     cd pwa/rules-tests && npm install && npm run test:e2e        (needs Microsoft Edge or Chrome installed)
//
// Flow: citizen asks for help -> NGO applies -> government approves -> NGO accepts and works the steps ->
// citizen sees the status and confirms -> government sees the audit trail. Also checks what each role must NOT see.
import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

const PORT = 5199
const BASE = `http://127.0.0.1:${PORT}`
const AUTH = 'http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1'
const PWA = fileURLToPath(new URL('../', import.meta.url))
const SHOTS = join(tmpdir(), 'safewindow-e2e')
mkdirSync(SHOTS, { recursive: true })
const PHONE = '+8801700000001'
const PASSWORD = 'test-password-1'

let vite
let browser
const log = (msg) => console.log(`  ✓ ${msg}`)

async function startVite() {
  vite = spawn(process.execPath, [join(PWA, 'node_modules/vite/bin/vite.js'), '--port', String(PORT), '--strictPort', '--host', '127.0.0.1'], {
    cwd: PWA, env: { ...process.env, VITE_EMULATORS: '1' }, stdio: ['ignore', 'pipe', 'pipe'],
  })
  vite.stderr.on('data', (d) => process.stderr.write(d))
  for (let i = 0; i < 60; i += 1) {
    try {
      if ((await fetch(BASE)).ok) return
    } catch { /* not yet */ }
    await sleep(500)
  }
  throw new Error('the app did not start')
}

async function governmentUser(email) {
  const sign = await fetch(`${AUTH}/accounts:signUp?key=fake`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ email, password: PASSWORD, returnSecureToken: true }) })
  const { localId } = await sign.json()
  // What scripts/provision_government.py does with the Admin SDK: a custom claim. The emulator accepts it with the owner token.
  const upd = await fetch(`${AUTH}/accounts:update?key=fake`, {
    method: 'POST', headers: { 'content-type': 'application/json', authorization: 'Bearer owner' },
    body: JSON.stringify({ localId, customAttributes: JSON.stringify({ role: 'gov' }) }) })
  if (!upd.ok) throw new Error(`could not set the government claim: ${upd.status}`)
}

async function newPage(name) {
  const ctx = await browser.newContext({ viewport: { width: 420, height: 900 } })
  await ctx.addInitScript(() => localStorage.setItem('safewindow.lang', 'en'))
  const page = await ctx.newPage()
  page.setDefaultTimeout(20000)
  page.on('pageerror', (e) => console.error(`[${name}] page error:`, e.message))
  return page
}

async function signUp(page, email) {
  await page.goto(`${BASE}/account`)
  await page.getByRole('tab', { name: 'Create account' }).click()
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password (6 or more characters)').fill(PASSWORD)
  await page.getByRole('button', { name: 'Create account' }).click()
  await page.getByText('Citizen account').waitFor()
}

async function signIn(page, email) {
  await page.goto(`${BASE}/account`)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password (6 or more characters)').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).last().click()
  await page.getByText(email).waitFor()
}

/** A button that asks for a reason: click it, type the reason, confirm. */
async function withReason(scope, label, reason) {
  await scope.getByRole('button', { name: label, exact: true }).click()
  await scope.getByLabel('Reason (needed, short)').fill(reason)
  await scope.getByRole('button', { name: label, exact: true }).click()
}

async function main() {
  await startVite()
  browser = await chromium.launch({ channel: 'msedge', headless: true })
  const run = Date.now()
  const citizenEmail = `citizen${run}@example.com`
  const ngoEmail = `ngo${run}@example.com`
  const govEmail = `gov${run}@example.com`
  await governmentUser(govEmail)
  log('government account provisioned with the claim (as the admin script does)')

  // ---- citizen asks for help
  const citizen = await newPage('citizen')
  await signUp(citizen, citizenEmail)
  await citizen.goto(`${BASE}/rescue`)
  await citizen.getByLabel('Name').fill('Rahim')
  await citizen.getByRole('button', { name: 'Save' }).click()
  await citizen.getByRole('button', { name: 'Request rescue or help' }).click()
  await citizen.getByLabel('Latitude').fill('25.06571')
  await citizen.getByLabel('Longitude').fill('91.39512')
  await citizen.getByLabel('Phone number to reach you').fill(PHONE)
  await citizen.getByLabel('Water is rising').check()
  await citizen.getByLabel('Boat rescue').check()
  await citizen.getByLabel('Children').check()
  await citizen.getByLabel('Share my exact location and phone with the team that takes my request').check()
  await citizen.getByRole('button', { name: 'Send request' }).click()
  await citizen.getByText('Your request has been received.').waitFor()
  await citizen.getByText('No responder has been assigned yet.').first().waitFor()
  const requestId = (await citizen.locator('code').first().textContent()).trim()
  log(`citizen sent a request (${requestId}) and is told no responder is assigned yet`)

  // the citizen must not be able to enter the other desks
  await citizen.goto(`${BASE}/gov`)
  await citizen.getByText('only for government accounts').waitFor()
  log('a citizen cannot use the government desk')

  // ---- NGO applies; sees nothing until approved
  const ngo = await newPage('ngo')
  await signUp(ngo, ngoEmail)
  await ngo.goto(`${BASE}/ngo`)
  await ngo.getByLabel('Legal name').fill('Haor Rescue Team')
  await ngo.getByLabel('Registration details').fill('NGOAB 1234, Sunamganj')
  await ngo.getByLabel('Areas you work in (separate with commas)').fill('Sunamganj, Sylhet')
  await ngo.getByLabel('Boats').check()
  await ngo.getByRole('button', { name: 'Send application' }).click()
  await ngo.getByText('Waiting for review').waitFor()
  assertNot(await ngo.content(), requestId, 'an unapproved NGO must not see requests')
  log('NGO applied; it sees no request while waiting for review')

  // ---- government approves the NGO
  const gov = await newPage('gov')
  await signIn(gov, govEmail)
  await gov.goto(`${BASE}/gov`)
  await gov.getByRole('tab', { name: 'NGOs' }).click()
  const card = gov.locator('article', { hasText: 'Haor Rescue Team' })
  await withReason(card, 'Approve', 'Registration documents checked')
  await card.getByText('Approved').first().waitFor()
  log('government approved the NGO with a reason')

  // ---- NGO accepts; sees the area only, then the exact details after accepting (the citizen agreed)
  await ngo.goto(`${BASE}/ngo`)
  await ngo.getByRole('tab', { name: 'Open requests' }).waitFor()
  await ngo.getByText('(rounded)').first().waitFor()
  const queueHtml = await ngo.content()
  assertNot(queueHtml, '25.06571', 'the queue must not show the exact latitude')
  assertNot(queueHtml, PHONE, 'the queue must not show the phone number')
  assertNot(queueHtml, 'Children', 'the queue must not show the vulnerability details')
  log('the open queue shows the rounded area only (no exact spot, no phone, no vulnerability details)')
  await ngo.getByRole('button', { name: 'Accept' }).first().click()
  await ngo.getByRole('tab', { name: 'My missions' }).click()
  await ngo.getByText(PHONE).waitFor()
  await ngo.getByText('Extra-needs details were not shared.').waitFor()
  assertNot(await ngo.content(), 'Children', 'sensitive details were shown without the citizen consent')
  log('after accepting, the team sees the exact location and phone (consent given); sensitive details stay hidden (no consent)')

  for (const step of ['Team preparing', 'Team has set out', 'Team has arrived and started']) {
    await ngo.getByRole('button', { name: step, exact: true }).click()
    await sleep(600)
  }
  await ngo.getByLabel('People helped').fill('4')
  await ngo.getByRole('button', { name: 'People moved to safety', exact: true }).click()
  await ngo.getByText('Reported rescued').first().waitFor()
  log('NGO worked the steps in order and closed with a people count')

  // ---- citizen sees the status and confirms
  await citizen.goto(`${BASE}/rescue`)
  await citizen.getByText('Reported rescued').first().waitFor()
  await citizen.getByRole('button', { name: 'Yes, this is right' }).click()
  await citizen.getByText('Confirmed').first().waitFor()
  log('citizen sees the status and confirms the outcome')

  // ---- government sees it, and the audit trail
  await gov.goto(`${BASE}/gov`)
  await gov.getByText('Completed').first().waitFor()
  await gov.getByRole('tab', { name: 'Audit' }).click()
  await gov.getByText('ngo_approved').first().waitFor()
  await gov.getByRole('tab', { name: 'Requests' }).click()
  await gov.locator('button.link-row').first().click()
  await gov.getByText('Exact location and phone').waitFor()
  await gov.getByText('Extra needs').waitFor()                      // government may see both
  log('government overview, audit trail and full request details work')

  await browser.close()
  vite.kill()
  console.log('\nEnd-to-end: all steps passed')
}

function assertNot(html, text, why) {
  if (html.includes(text)) throw new Error(`${why} (found "${text}")`)
}

main().catch(async (error) => {
  console.error('\nEND-TO-END FAILED:', error.message)
  try {
    for (const ctx of browser?.contexts() || []) for (const [i, p] of ctx.pages().entries()) await p.screenshot({ path: join(SHOTS, `fail-${Date.now()}-${i}.png`) })
    console.error(`screenshots in ${SHOTS}`)
  } catch { /* ignore */ }
  await browser?.close().catch(() => {})
  vite?.kill()
  process.exit(1)
})
