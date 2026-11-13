import { createContext, useContext } from 'react'

export const AppStateContext = createContext(null)

/** The chosen flood, village, radar date and supply days, shared by every screen. */
export function useAppState() {
  return useContext(AppStateContext)
}

const KEY = 'safewindow.state'

/** Saved choices; a link such as /village?flood=X&village=Y (from an alert) takes priority. */
export function readSaved() {
  let saved = {}
  try {
    saved = JSON.parse(localStorage.getItem(KEY)) || {}
  } catch {
    // private mode or blocked storage
  }
  const q = new URLSearchParams(window.location.search)
  if (q.get('flood')) saved = { ...saved, floodId: q.get('flood'), villageId: q.get('village') || saved.villageId }
  return saved
}

export function save(state) {
  try {
    localStorage.setItem(KEY, JSON.stringify(state))
  } catch {
    // private mode or blocked storage: the choices are simply not remembered
  }
}
