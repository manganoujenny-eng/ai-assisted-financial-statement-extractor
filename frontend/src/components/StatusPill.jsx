/* One component for every status in the system, so that a given state always
 * looks the same wherever it appears. The moment two screens colour
 * EXTRACTION_FAILED differently, the user stops trusting the colours. */

const CASE_TONE = {
  CREATED: 'neutral',
  EXTRACTING: 'accent',
  EXTRACTED: 'accent',
  EXTRACTION_FAILED: 'fail',
  UNDER_REVIEW: 'accent',
  VALIDATED: 'ok',
  ANALYSED: 'ok',
}

const FIELD_TONE = {
  PROPOSED: 'neutral',
  CORRECTED: 'accent',
  VALIDATED: 'ok',
  KEYED: 'warn',
}

export default function StatusPill({ status, kind = 'case' }) {
  const tone = (kind === 'field' ? FIELD_TONE : CASE_TONE)[status] || 'neutral'
  return <span className={`pill ${tone}`}>{status.replaceAll('_', ' ').toLowerCase()}</span>
}
