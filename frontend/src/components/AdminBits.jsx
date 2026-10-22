/* Small pieces shared by the administration pages. */

import { labelByCode, useI18n } from '../i18n/index.jsx'

/* "0.9285714" -> "92.9 %" (in the screen's language). */
export function usePercent() {
  const { formatNumber } = useI18n()
  return (value) =>
    value === null || value === undefined || value === ''
      ? '—'
      : `${formatNumber(Number(value) * 100, { maximumFractionDigits: 1 })} %`
}

/* One headline figure. */
export function StatTile({ label, value, hint }) {
  return (
    <div className="summary-stat">
      <span className="faint">{label}</span>
      <strong>{value}</strong>
      {hint && <span className="faint adm-stat-hint">{hint}</span>}
    </div>
  )
}

/* The name of an audit action / entity, translated when known. */
export function useAuditText() {
  const { t } = useI18n()
  return {
    actionLabel: (action) => labelByCode(t, 'audit.action', action, action),
    entityLabel: (entity) => labelByCode(t, 'audit.entity', entity, entity),
  }
}

/* An audit "detail" in one readable line: {"active": [true, false]} ->
 * "active: true → false". Passwords are never in the audit, only "reset". */
export function detailText(detail) {
  if (!detail || typeof detail !== 'object') return ''
  return Object.entries(detail)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => {
      if (Array.isArray(value) && value.length === 2 && typeof value[0] !== 'object') {
        return `${key}: ${value[0]} → ${value[1]}`
      }
      if (typeof value === 'object') return `${key}: ${JSON.stringify(value)}`
      return `${key}: ${value}`
    })
    .join(' · ')
}

/* Bytes -> "1.2 MB". */
export function fileSize(bytes) {
  if (bytes === null || bytes === undefined) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/* Previous / next under a paged table. */
export function Pager({ page, last, total, onPage }) {
  const { t } = useI18n()
  if (total <= last && page === 1) return null
  return (
    <div className="adm-pager">
      <button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        ← {t('adm.previous')}
      </button>
      <span className="faint">{t('adm.page', { page })}</span>
      <button type="button" disabled={last >= total} onClick={() => onPage(page + 1)}>
        {t('adm.next')} →
      </button>
    </div>
  )
}