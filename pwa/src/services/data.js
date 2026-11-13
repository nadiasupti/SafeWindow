// Reads the files that scripts/build_pwa.py writes into public/data/.
export const DATA_BASE = `${import.meta.env.BASE_URL}data`

async function getJson(path) {
  const response = await fetch(`${DATA_BASE}/${path}`)
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`)
  return response.json()
}

/** The list of floods: [{id, name, country, first_date, observed_through, demonstration, villages, size_mb}]. */
export async function loadIndex() {
  return (await getJson('index.json')).floods
}

/** What every screen needs for one flood. */
export async function loadFlood(id) {
  const [metadata, villages, status] = await Promise.all([
    getJson(`${id}/metadata.json`),
    getJson(`${id}/villages.json`),
    getJson(`${id}/status.json`),
  ])
  return { metadata, villages, status }
}

/** A GeoJSON layer of one flood (roads, area, flooded_roads, routes, shelters, health); null if it has none. */
export async function loadLayer(id, name) {
  try {
    return await getJson(`${id}/${name}.geojson`)
  } catch {
    return null
  }
}

export function floodImageUrl(id, date) {
  return `${DATA_BASE}/${id}/flood/${date.replaceAll('-', '')}.png`
}
