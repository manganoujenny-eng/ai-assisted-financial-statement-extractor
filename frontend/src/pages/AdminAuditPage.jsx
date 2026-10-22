/* Administration — Audit log: who did what, when, on what.
 *
 * Every action the system records (sign-ins, cases created, uploads,
 * extractions, corrections, submissions, validations, AI approvals, user
 * changes, corpus changes, campaigns), newest first. Filter by person,
 * action, kind of object, dates and free text; open a line to read its full
 * detail; download what the filters show as a CSV file (Excel).
 * Data: GET /api/admin/audit. Append-only: nothing here can change an entry.
 */

import { Fragment, useEffect, useState } from 'react'
import * as api from '../api/client.js'
import { Pager, detailText, useAuditText } from '../components/AdminBits.jsx'
import { useI18n } from '../i18n/index.jsx'

const EMPTY = { q: '', author: '', action: '', entity: '', from: '', to: '' }
const PER_PAGE = 50
// The "Who acted" list, grouped: the accounts by role, then the authors
// that are not a current account (scripts, the application, typed usernames).
const KINDS = ['ADMIN', 'SUPERVISOR', 'ANALYST', 'SCRIPT', 'SYSTEM', 'OTHER']

export default function AdminAuditPage() {
  const [filters, setFilters] = useState(EMPTY)
  const [typed, setTyped] = useState('') // the search box, applied after a pause
  const [page, setPage] = useState(1)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [open, setOpen] = useState(null) // the entry whose detail is shown
  const { t, formatDateTime, formatNumber } = useI18n()
  const { actionLabel, entityLabel } = useAuditText()

  // Typing in the search box waits 300 ms before asking the server.
  useEffect(() => {
    const timer = setTimeout(() => {
      setFilters((current) => (current.q === typed ? current : { ...current, q: typed }))
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [typed])

  useEffect(() => {
    let cancelled = false
    setError(null)
    api
      .getAudit({ ...filters, page, per_page: PER_PAGE })
      .then((answer) => !cancelled && setData(answer))
      .catch((err) => !cancelled && setError(err.message))
    return () => {
      cancelled = true
    }
  }, [filters, page])

  function set(name, value) {
    setFilters((current) => ({ ...current, [name]: value }))
    setPage(1)
  }

  function reset() {
    setTyped('')
    setFilters(EMPTY)
    setPage(1)
  }

  const facets = data?.facets || { authors: [], actions: [], entities: [] }
  const total = data?.total || 0
  const first = total === 0 ? 0 : (page - 1) * PER_PAGE + 1
  const last = Math.min(page * PER_PAGE, total)
  const filtered = Object.values(filters).some(Boolean)

  return (
    <>
      <h2 className="page-title">{t('adm.auditTitle')}</h2>
      <p className="page-subtitle">{t('adm.auditSubtitle')}</p>

      <details className="card au-legend" open>
        <summary>{t('adm.auHowTitle')}</summary>
        <dl>
          <div><dt>{t('adm.who')}</dt><dd>{t('adm.auWho')}</dd></div>
          <div><dt>{t('adm.action')}</dt><dd>{t('adm.auAction')}</dd></div>
          <div><dt>{t('adm.onWhat')}</dt><dd>{t('adm.auOnWhat')}</dd></div>
          <div><dt>{t('adm.details')}</dt><dd>{t('adm.auDetails')}</dd></div>
        </dl>
      </details>

      <div className="card adm-filters" role="search">
        <label className="adm-filter-wide">
          {t('adm.search')}
          <input
            type="search"
            value={typed}
            placeholder={t('adm.searchPlaceholder')}
            onChange={(event) => setTyped(event.target.value)}
          />
        </label>
        <label>
          {t('adm.whoActed')}
          <select value={filters.author} onChange={(event) => set('author', event.target.value)}>
            <option value="">{t('adm.everyone')}</option>
            {KINDS.map((kind) => {
              const names = facets.authors.filter((name) => (facets.author_kinds || {})[name] === kind)
              return names.length ? (
                <optgroup key={kind} label={t(`adm.authorKind.${kind}`)}>
                  {names.map((name) => <option key={name} value={name}>{name}</option>)}
                </optgroup>
              ) : null
            })}
          </select>
        </label>
        <label>
          {t('adm.action')}
          <select value={filters.action} onChange={(event) => set('action', event.target.value)}>
            <option value="">{t('adm.allActions')}</option>
            {facets.actions.map((action) => (
              <option key={action} value={action}>{actionLabel(action)}</option>
            ))}
          </select>
        </label>
        <label>
          {t('adm.objectType')}
          <select value={filters.entity} onChange={(event) => set('entity', event.target.value)}>
            <option value="">{t('adm.allObjects')}</option>
            {facets.entities.map((entity) => (
              <option key={entity} value={entity}>{entityLabel(entity)}</option>
            ))}
          </select>
        </label>
        <label>
          {t('adm.from')}
          <input type="date" value={filters.from} onChange={(event) => set('from', event.target.value)} />
        </label>
        <label>
          {t('adm.to')}
          <input type="date" value={filters.to} onChange={(event) => set('to', event.target.value)} />
        </label>
        <div className="adm-filter-actions">
          <button type="button" onClick={reset} disabled={!filtered && !typed}>{t('adm.reset')}</button>
          <a className="button-like" href={api.auditCsvUrl(filters)} download>
            {t('adm.downloadCsv')}
          </a>
        </div>
      </div>

      {error && <div className="banner fail">{error}</div>}

      <div className="card">
        <div className="adm-table-head">
          <strong>
            {total === 0
              ? t('adm.noEntry')
              : t('adm.entriesRange', { first: formatNumber(first), last: formatNumber(last), total: formatNumber(total) })}
          </strong>
          <Pager page={page} last={last} total={total} onPage={setPage} />
        </div>
        {data === null ? (
          <p className="muted">{t('common.loading')}</p>
        ) : (
          <div className="fields-table-wrap">
            <table className="adm-audit-table">
              <thead>
                <tr>
                  <th>{t('adm.when')}</th>
                  <th>{t('adm.who')}</th>
                  <th>{t('adm.action')}</th>
                  <th>{t('adm.onWhat')}</th>
                  <th>{t('adm.details')}</th>
                </tr>
              </thead>
              <tbody>
                {data.entries.map((entry) => (
                  <Fragment key={entry.id}>
                    <tr
                      className={`adm-audit-row${open === entry.id ? ' open' : ''}`}
                      onClick={() => setOpen(open === entry.id ? null : entry.id)}
                    >
                      <td className="adm-nowrap adm-when">{formatDateTime(entry.at)}</td>
                      <td>
                        <button
                          type="button"
                          className="adm-link"
                          title={t('adm.onlyThisPerson')}
                          onClick={(event) => {
                            event.stopPropagation()
                            set('author', entry.author)
                          }}
                        >
                          {entry.author}
                        </button>
                        {entry.author_kind && (
                          <span className="au-kind faint">{t(`adm.authorKindShort.${entry.author_kind}`)}</span>
                        )}
                      </td>
                      <td><span className={`pill ${toneOf(entry.action)}`}>{actionLabel(entry.action)}</span></td>
                      <td>
                        <span className="au-entity">{entityLabel(entry.entity)}</span>
                        {entry.about && entry.about !== entry.author && <span className="au-about">{entry.about}</span>}
                      </td>
                      <td className="adm-ellipsis" title={detailText(entry.detail)}>
                        {detailText(entry.detail) || <span className="faint">—</span>}
                      </td>
                    </tr>
                    {open === entry.id && (
                      <tr className="adm-audit-detail">
                        <td colSpan={5}>
                          <dl className="adm-settings adm-ids">
                            <dt>{t('adm.entryId')}</dt><dd>{entry.id}</dd>
                            <dt>{t('adm.objectId')}</dt><dd>{entry.entity_id}</dd>
                          </dl>
                          {entry.detail && Object.keys(entry.detail).length > 0 && (
                            <pre className="adm-json">{JSON.stringify(entry.detail, null, 2)}</pre>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="adm-table-foot">
          <Pager page={page} last={last} total={total} onPage={setPage} />
        </div>
      </div>
    </>
  )
}

/* Red only for a failure (red, amber and green keep their meaning
 * across the whole interface); the rest stays neutral. */
function toneOf(action) {
  return /FAILED/.test(action) ? 'fail' : 'neutral'
}