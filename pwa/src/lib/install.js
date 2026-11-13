import { useEffect, useState } from 'react'

/**
 * Chrome's "install this app" prompt, when the browser offers one. Returns a function that shows it,
 * or null (iPhone Safari never offers it: there the user taps Share, then "Add to Home Screen").
 */
export function useInstallPrompt() {
  const [event, setEvent] = useState(null)
  useEffect(() => {
    const keep = (e) => {
      e.preventDefault()
      setEvent(e)
    }
    window.addEventListener('beforeinstallprompt', keep)
    return () => window.removeEventListener('beforeinstallprompt', keep)
  }, [])
  if (!event) return null
  return async () => {
    event.prompt()
    await event.userChoice
    setEvent(null)
  }
}
