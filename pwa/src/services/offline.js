import { DATA_BASE } from './data.js'

// The same cache the service worker reads /data/ from (vite.config.js, runtimeCaching), so files
// stored here are what the app gets when there is no network.
export const DATA_CACHE = 'safewindow-data'

export function offlineSupported() {
  return typeof window !== 'undefined' && 'caches' in window
}

const url = (id, file) => `${DATA_BASE}/${id}/${file}`

async function fileList(id, cache) {
  const cached = cache && (await cache.match(url(id, 'files.json')))
  const response = cached || (await fetch(url(id, 'files.json'), { cache: 'no-cache' }))
  if (!response.ok) throw new Error(`files.json: HTTP ${response.status}`)
  return response.json()
}

/** Size of one flood's download in MB, or null if unknown. */
export async function downloadSize(id) {
  try {
    return (await fileList(id, null)).bytes / 1e6
  } catch {
    return null
  }
}

/** True when every file of the flood is stored on the phone. */
export async function isReady(id) {
  if (!offlineSupported()) return false
  const cache = await caches.open(DATA_CACHE)
  let list
  try {
    list = await fileList(id, cache)
  } catch {
    return false
  }
  for (const f of list.files) {
    if (!(await cache.match(url(id, f)))) return false
  }
  return true
}

/** Store every file of the flood on the phone. onProgress(0..100). Throws if any file fails. */
export async function downloadFlood(id, onProgress) {
  const cache = await caches.open(DATA_CACHE)
  const list = await fileList(id, null)          // always the newest list from the network
  let done = 0
  for (const f of list.files) {
    const response = await fetch(url(id, f), { cache: 'no-cache' })
    if (!response.ok) throw new Error(`${f}: HTTP ${response.status}`)
    await cache.put(url(id, f), response)
    done += 1
    onProgress?.(Math.round((100 * done) / list.files.length))
  }
}
