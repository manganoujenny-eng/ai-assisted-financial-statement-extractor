/* The rule-based interpretation of a ratio, in the screen's language.
 *
 * The backend writes each interpretation in English from one of three
 * templates (domain/interpretation/templates.py) and sends, with the text,
 * which template it used and the threshold applied. The sentence is
 * rebuilt here from those same facts, so it reads in French or English
 * while saying exactly what the backend's template says:
 *
 *   T_NOT_COMPUTABLE         "{name} could not be computed: {reason}. …"
 *   T_FACTUAL_NO_REFERENCE   "{name} stands at {value}. No documented reference …"
 *   T_COMPARED_TO_THRESHOLD  "{name} stands at {value}, at or above / below the {threshold} reference."
 *
 * An unknown template falls back to the backend's own text.
 */

import { labelByCode } from './index.jsx'

/* The reasons the ratio engine gives (domain/ratios/engine.py). */
export function reasonText(t, reason) {
  if (!reason) return ''
  const missing = /^missing item\(s\):\s*(.+)$/i.exec(reason)
  if (missing) return t('interp.reason.missing', { items: missing[1] })
  const known = {
    'zero denominator': 'interp.reason.zeroDenominator',
    'undefined arithmetic operation': 'interp.reason.undefined',
    'ratio not implemented yet': 'interp.reason.notImplemented',
    'negative equity': 'interp.reason.negativeEquity',
  }[reason.trim().toLowerCase()]
  return known ? t(known) : reason
}

export function interpretationText(t, ratio) {
  const interpretation = ratio?.interpretation
  if (!interpretation) return ''
  const name = labelByCode(t, 'ratio', ratio.code, ratio.name)
  const value = `${ratio.value ?? ''} ${ratio.unit || ''}`.trim()

  switch (interpretation.template_id) {
    case 'T_NOT_COMPUTABLE':
      return t('interp.notComputable', { name, reason: reasonText(t, ratio.reason) })
    case 'T_FACTUAL_NO_REFERENCE':
      return t('interp.noReference', { name, value })
    case 'T_COMPARED_TO_THRESHOLD': {
      const threshold = Number(interpretation.threshold_applied)
      const above = Number(ratio.value) >= threshold
      const coverage = ratio.code === 'R3'
      const key = above
        ? coverage ? 'interp.aboveCoverage' : 'interp.above'
        : coverage ? 'interp.belowCoverage' : 'interp.below'
      return t(key, { name, value, threshold: interpretation.threshold_applied })
    }
    default:
      return interpretation.text || ''
  }
}

/* Where a documented threshold comes from (templates.py THRESHOLDS). */
export function referenceSourceText(t, ratio) {
  const source = ratio?.interpretation?.reference_source
  if (!source) return ''
  const key = `interp.source.${ratio.code}`
  const text = t(key)
  return text === key ? source : text
}