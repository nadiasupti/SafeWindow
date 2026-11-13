// Dates and numbers in the chosen language. Intl ships with the browser, so this works offline.
const LOCALE = { bn: 'bn-BD', en: 'en-GB' }

/** '2022-05-23' -> '২৩ মে' (bn) or '23 May' (en). Dates are calendar days, read as UTC. */
export function formatDate(iso, lang, withYear = false) {
  if (!iso) return '–'
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`)
  return new Intl.DateTimeFormat(LOCALE[lang], {
    day: 'numeric', month: 'long', ...(withYear ? { year: 'numeric' } : {}), timeZone: 'UTC',
  }).format(d)
}

export function formatDateTime(iso, lang) {
  if (!iso) return null
  return new Intl.DateTimeFormat(LOCALE[lang], { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso))
}

export function formatNumber(n, lang, digits = 0) {
  if (n === null || n === undefined) return '–'
  return new Intl.NumberFormat(LOCALE[lang], { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(n)
}

export function addDays(iso, days) {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

export function daysBetween(fromIso, toIso) {
  return Math.round((new Date(`${toIso}T00:00:00Z`) - new Date(`${fromIso}T00:00:00Z`)) / 86400000)
}
