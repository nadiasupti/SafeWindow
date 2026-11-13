/** The phone's position. It stays on the phone: nothing here sends it anywhere. */
export function getPosition() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('no geolocation'))
      return
    }
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lon: p.coords.longitude, accuracy: p.coords.accuracy }),
      reject,
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },
    )
  })
}

/** 'granted' | 'prompt' | 'denied' | 'unknown' */
export async function gpsPermission() {
  try {
    return (await navigator.permissions.query({ name: 'geolocation' })).state
  } catch {
    return 'unknown'
  }
}
