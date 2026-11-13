import { useEffect, useState } from 'react'
import { loadFlood, loadIndex } from '../services/data.js'
import { AppStateContext, readSaved, save } from './appState.js'

/** The radar date with the most isolated villages: the most telling date to open on. */
function peakIndex(status) {
  const n = status.dates.length
  let best = n - 1
  let most = -1
  for (let i = 0; i < n; i++) {
    const count = Object.values(status.villages).filter((codes) => codes[i] === 'i').length
    if (count > most) {
      most = count
      best = i
    }
  }
  return best
}

export default function AppStateProvider({ children }) {
  const [saved] = useState(readSaved)
  const [floods, setFloods] = useState(null)
  const [floodId, setFloodId] = useState(saved.floodId || null)
  const [flood, setFlood] = useState(null)
  const [villageId, setVillageId] = useState(saved.villageId || null)
  const [dateIndex, setDateIndex] = useState(null)
  const [supplyDays, setSupplyDays] = useState(saved.supplyDays || null)
  const [error, setError] = useState(null)

  useEffect(() => {
    loadIndex()
      .then((list) => {
        setFloods(list)
        setFloodId((current) => (list.some((f) => f.id === current) ? current : list[0]?.id ?? null))
      })
      .catch((e) => setError(String(e)))
  }, [])

  useEffect(() => {
    if (!floodId) return
    let alive = true
    loadFlood(floodId)
      .then((data) => {
        if (!alive) return
        setFlood({ id: floodId, ...data })
        setDateIndex(peakIndex(data.status))
        setVillageId((current) => (data.villages.some((v) => v.id === current) ? current : null))
        const [lo, hi] = data.metadata.supply_days_range || [2, 14]
        setSupplyDays((current) => (current >= lo && current <= hi ? current : data.metadata.default_supply_days || 7))
      })
      .catch((e) => alive && setError(String(e)))
    return () => {
      alive = false
    }
  }, [floodId])

  useEffect(() => save({ floodId, villageId, supplyDays }), [floodId, villageId, supplyDays])

  const village = flood?.villages.find((v) => v.id === villageId) || null
  const value = {
    floods, floodId, setFloodId, flood, village, villageId, setVillageId,
    dateIndex, setDateIndex, supplyDays, setSupplyDays, error,
    ready: Boolean(flood && flood.id === floodId),
  }
  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>
}
