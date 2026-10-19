/* One component for every status in the system, so that a given state always
 * looks the same wherever it appears. The moment two screens colour
 * EXTRACTION_FAILED differently, the user stops trusting the colours. */

import { useI18n } from '../i18n/index.jsx'

const CASE_TONE = {
  CREATED: 'neutral',
  EXTRACTING: 'accent',
  EXTRACTED: 'accent',
  EXTRACTION_FAILED: 'fail',
  UNDER_REVIEW: 'accent',
  SUBMITTED: 'warn',
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
  const { t } = useI18n()
  const tone = (kind === 'field' ? FIELD_TONE : CASE_TONE)[status] || 'neutral'
  // Field and case statuses share some names (VALIDATED) but not all
  // translations, hence the two key prefixes. Unknown statuses fall back
  // to the raw name.
  const key = `status.${kind === 'field' ? 'field' : 'case'}.${status}`
  const text = t(key)
  return (
    <span className={`pill ${tone}`}>
      {text === key ? status.replaceAll('_', ' ').toLowerCase() : text}
    </span>
  )
}