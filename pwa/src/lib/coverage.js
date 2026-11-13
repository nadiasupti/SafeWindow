// How much of the study area the radar actually saw on one date, from the pipeline's own metadata.
// Nothing is filled in between dates: a date the radar did not see stays unknown (grey), never the previous image.

export const PARTIAL_PCT = 5        // the same threshold the date slider has always used for its "radar missed" note
const NONE_PCT = 99.5               // practically the whole area unseen

/** 'none' (no radar image), 'partial' (part of the area unseen) or 'full', and the unseen share in %. */
export function coverage(flood, index) {
  const date = flood.status.dates[index]
  const unknown = flood.metadata.unknown_pct?.[date] ?? 0
  const source = flood.metadata.sources ? flood.metadata.sources[date] : 'sentinel1'
  if (!source || unknown >= NONE_PCT) return { kind: 'none', unknown: 100 }
  if (unknown >= PARTIAL_PCT) return { kind: 'partial', unknown }
  return { kind: 'full', unknown }
}
