/* Administration — Data: the database tables, read-only (no more pgAdmin).
 *
 * Left, the tables grouped by what they hold (cases and documents,
 * extraction and checks, results, accounts and audit, evaluation), each with
 * its number of rows. Right, the chosen table: what it holds, then its rows,
 * newest first, 50 per page, with a search across every column. Cells are
 * made readable — dates in the screen's language, long identifiers
 * shortened (the full value on hover), yes / no, JSON on one line.
 * Nothing can be changed here. Passwords never leave the backend.
 * Data: GET /api/admin/tables, /api/admin/tables/<name>.
 */

import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import * as api from '../api/client.js'
import { Pager } from '../components/AdminBits.jsx'
import { labelByCode, useI18n } from '../i18n/index.jsx'

const GROUPS = [
  ['cases', ['analysis_case', 'document', 'case_comment', 'case_discussion_read', 'case_discussion_hidden']],
  ['extraction', ['extraction_run', 'extracted_field', 'check_result']],
  ['results', ['validated_dataset', 'ratio_result', 'interpretation', 'ai_analysis']],
  ['people', ['app_user', 'audit_log', 'archive_entry']],
  ['evaluation', ['evaluation_campaign', 'evaluation_package']],
]
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const ISO_DATE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/

function Cell({ value }) {
  const { t, formatDateTime } = useI18n()
  if (value === null || value === undefined || value === '') return <span className="faint">—</span>
  if (typeof value === 'boolean') return value ? t('adm.yes') : t('adm.no')
  if (typeof value === 'object') {
    const text = JSON.stringify(value)
    return (
      <span className="adm-cell-json" title={JSON.stringify(value, null, 2)}>
        {text.length > 60 ? `${text.slice(0, 60)}…` : text}
      </span>
    )
  }
  const text = String(value)
  if (UUID.test(text)) return <span className="adm-cell-id" title={text}>{text.slice(0, 8)}…</span>
  if (ISO_DATE.test(text)) return <span className="adm-nowrap" title={text}>{formatDateTime(text)}</span>
  return <span title={text.length > 48 ? text : undefined}>{text.length > 48 ? `${text.slice(0, 48)}…` : text}</span>
}

export default function AdminDataPage() {
  const [tables, setTables] = useState(null)
  const [rows, setRows] = useState(null)
  const [typed, setTyped] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const [error, setError] = useState(null)
  const [params, setParams] = useSearchParams()
  const { t, formatNumber } = useI18n()
  const name = params.get('table')

  useEffect(() => {
    api.getTables().then(setTables).catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => {
      setQ(typed)
      setPage(1)
    }, 300)
    return () => clearTimeout(timer)
  }, [typed])

  useEffect(() => {
    if (!name) {
      setRows(null)
      return undefined
    }
    let cancelled = false
    setError(null)
    setRows(null)
    api
      .getTableRows(name, { page, q })
      .then((answer) => !cancelled && setRows(answer))
      .catch((err) => !cancelled && setError(err.message))
    return () => {
      cancelled = true
    }
  }, [name, page, q])

  // The tables, grouped; a table no group knows goes to "other".
  const grouped = useMemo(() => {
    if (!tables) return []
    const byName = Object.fromEntries(tables.tables.map((table) => [table.name, table]))
    const known = new Set(GROUPS.flatMap(([, names]) => names))
    const groups = GROUPS.map(([key, names]) => [key, names.filter((n) => byName[n]).map((n) => byName[n])])
    const other = tables.tables.filter((table) => !known.has(table.name))
    if (other.length) groups.push(['other', other])
    return groups.filter(([, list]) => list.length)
  }, [tables])

  function choose(table) {
    setTyped('')
    setQ('')
    setPage(1)
    setParams({ table })
  }

  if (tables && !tables.available) {
    return (
      <>
        <h2 className="page-title">{t('adm.dataTitle')}</h2>
        <div className="banner warn">{t('adm.noDatabase')}</div>
      </>
    )
  }

  const chosen = tables?.tables.find((table) => table.name === name)
  const total = rows?.total || 0
  const perPage = rows?.per_page || 50
  const first = total === 0 ? 0 : (page - 1) * perPage + 1
  const last = Math.min(page * perPage, total)

  return (
    <>
      <h2 className="page-title">{t('adm.dataTitle')}</h2>
      <p className="page-subtitle">{t('adm.dataSubtitle')}</p>
      {error && <div className="banner fail">{error}</div>}

      <div className="adm-data">
        <nav className="card adm-table-list" aria-label={t('adm.tables')}>
          {tables === null ? (
            <p className="muted">{t('common.loading')}</p>
          ) : (
            grouped.map(([key, list]) => (
              <div key={key} className="dt-group">
                <h3 className="dt-group-title">{t(`adm.tableGroup.${key}`)}</h3>
                <ul>
                  {list.map((table) => (
                    <li key={table.name}>
                      <button
                        type="button"
                        className={name === table.name ? 'selected' : ''}
                        aria-current={name === table.name ? 'true' : undefined}
                        onClick={() => choose(table.name)}
                      >
                        <span className="dt-name">{labelByCode(t, 'adm.tableTitle', table.name, table.name)}</span>
                        <span className="dt-count num">{formatNumber(table.rows)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))
          )}
        </nav>

        <section className="card adm-rows">
          {!name || !chosen ? (
            <div className="dt-empty">
              <h3 style={{ marginTop: 0 }}>{t('adm.chooseTable')}</h3>
              <p className="muted" style={{ margin: 0 }}>{t('adm.chooseTableHelp')}</p>
            </div>
          ) : (
            <>
              <div className="dt-head">
                <div>
                  <h3 style={{ margin: 0 }}>{labelByCode(t, 'adm.tableTitle', name, name)}</h3>
                  <p className="muted dt-what">{labelByCode(t, 'adm.tableHelp', name, '')}</p>
                  <span className="faint">
                    <span className="adm-table-name">{name}</span>
                    {' · '}{t('adm.columnsCount', { count: chosen.columns.length })}
                    {' · '}{total === 0
                      ? t('adm.noRow')
                      : t('adm.rowsRange', { first: formatNumber(first), last: formatNumber(last), total: formatNumber(total) })}
                  </span>
                </div>
                <input
                  type="search"
                  value={typed}
                  placeholder={t('adm.searchTable')}
                  aria-label={t('adm.searchTable')}
                  onChange={(event) => setTyped(event.target.value)}
                  className="adm-table-search"
                />
              </div>
              {rows === null ? (
                <p className="muted">{t('common.loading')}</p>
              ) : (
                <div className="fields-table-wrap adm-grid-wrap">
                  <table className="adm-data-table">
                    <thead>
                      <tr>{rows.columns.map((column) => <th key={column}>{column}</th>)}</tr>
                    </thead>
                    <tbody>
                      {rows.rows.map((row, index) => (
                        <tr key={index}>
                          {row.map((value, column) => <td key={column}><Cell value={value} /></td>)}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="adm-table-foot">
                <Pager page={page} last={last} total={total} onPage={setPage} />
              </div>
            </>
          )}
        </section>
      </div>
    </>
  )
}