/** What a failed call means, in plain words. Permission errors are what the rules say: not allowed. */
export function errorKey(error) {
  const code = String(error?.code || '')
  if (code.includes('permission-denied')) return 'rp_err_denied'
  if (code.includes('unavailable') || code.includes('network') || code.includes('deadline')) return 'rp_err_network'
  if (code.includes('failed-precondition') || code.includes('aborted') || code.includes('already-exists')) return 'rp_err_conflict'
  return 'rp_err_generic'
}
