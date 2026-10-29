/* Administration — Archive: everything deleted, kept so it can be undone.
 *
 * When anyone deletes a case, a document, an account, a corpus file or
 * package, or a campaign, it disappears for them — and a complete copy
 * lands here. The administrator (and the super administrator):
 *   - restores an entry exactly as it was (same identifiers, same history);
 *     a restore that would clash with what exists now is refused with the
 *     reason (e.g. the username was taken again), and the entry stays;
 *   - or deletes it for good (red confirmation).
 * Both are written to the audit log (RESTORED / PURGED).
 * Data: GET /api/admin/archive, POST …/restore, DELETE /api/admin/archive/<id>.
 */

import { useEffect, useState } from 'react'
import * as api from '../api/client.js'
import DangerDialog from '../components/DangerDialog.jsx'
import { fileSize } from '../components/AdminBits.jsx'
import { useI18n } from '../i18n/index.jsx'

const KINDS = ['CASE', 'DOCUMENT', 'USER', 'CORPUS_FILE', 'CORPUS_PACKAGE', 'CAMPAIGN']

function Detail({ entry }) {
  const { t } = useI18n()
  const d = entry.detail || {}
  switch (entry.kind) {
    case 'CASE':
      return t('arc.detail.CASE', {
        documents: d.documents ?? 0,
        runs: d.runs ?? 0,
        datasets: d.datasets ?? 0,
        status: t(`status.case.${d.status}`),
        analyst: d.analyst || t('sup.unassigned'),
      })
    case 'DOCUMENT':
      return t('arc.detail.DOCUMENT', { type: d.doc_type || '—' })
    case 'USER':
      return t('arc.detail.USER', {
        username: d.username,
        role: t(`role.${d.role}`),
        state: d.active ? t('users.active') : t('users.deactivated'),
      })
    case 'CORPUS_FILE':
      return t('arc.detail.CORPUS_FILE', { package: d.package, size: fileSize(d.size || 0) })
    case 'CAMPAIGN':
      return t('arc.detail.CAMPAIGN', {
        kind: t(`adm.kind.${d.kind}`),
        packages: d.packages ?? 0,
      })
    default:
      return null
  }
}

export default function AdminArchivePage() {
  const [data, setData] = useState(null)
  const [kind, setKind] = useState('')
  const [typed, setTyped] = useState('')
  const [q, setQ] = useState('')
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [purging, setPurging] = useState(null) // { entry, working, error }
  const { t, formatDateTime } = useI18n()

  async function reload() {
    try {
      setData(await api.getArchive({ kind, q }))
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    reload()
  }, [kind, q])

  useEffect(() => {
    const timer = setTimeout(() => setQ(typed.trim()), 300)
    return () => clearTimeout(timer)
  }, [typed])

  useEffect(() => {
    if (!message) return undefined
    const timer = setTimeout(() => setMessage(null), 6000)
    return () => clearTimeout(timer)
  }, [message])

  async function restore(entry) {
    try {
      setBusyId(entry.id)
      setError(null)
      await api.restoreArchived(entry.id)
      setMessage(t('arc.restored', { label: entry.label }))
      await reload()
    } catch (err) {
      setError(t('arc.restoreRefused', { label: entry.label, reason: err.message }))
    } finally {
      setBusyId(null)
    }
  }

  async function confirmPurge() {
    try {
      setPurging({ ...purging, working: true, error: null })
      await api.purgeArchived(purging.entry.id)
      setMessage(t('arc.purged', { label: purging.entry.label }))
      setPurging(null)
      await reload()
    } catch (err) {
      setPurging({ ...purging, working: false, error: err.message })
    }
  }

  const counts = data?.counts || {}
  const total = Object.values(counts).reduce((sum, n) => sum + n, 0)

  return (
    <>
      <h2 className="page-title">{t('arc.title')}</h2>
      <p className="page-subtitle">{t('arc.subtitle')}</p>

      {error && <div className="banner fail">{error}</div>}
      {message && <div className="banner info">{message}</div>}

      <div className="card arc-bar">
        <div className="arc-chips" role="tablist" aria-label={t('arc.kindLabel')}>
          <button
            type="button"
            role="tab"
            aria-selected={kind === ''}
            className={kind === '' ? 'selected' : ''}
            onClick={() => setKind('')}
          >
            {t('arc.all')} <span className="num">{total}</span>
          </button>
          {KINDS.map((k) => (
            <button
              key={k}
              type="button"
              role="tab"
              aria-selected={kind === k}
              className={kind === k ? 'selected' : ''}
              onClick={() => setKind(k)}
            >
              {t(`arc.kind.${k}`)} <span className="num">{counts[k] || 0}</span>
            </button>
          ))}
        </div>
        <input
          type="search"
          value={typed}
          placeholder={t('arc.search')}
          aria-label={t('arc.search')}
          onChange={(event) => setTyped(event.target.value)}
          className="adm-table-search"
        />
      </div>

      <div className="card">
        {data === null ? (
          <p className="muted">{t('common.loading')}</p>
        ) : data.entries.length === 0 ? (
          <div className="dt-empty">
            <h3 style={{ marginTop: 0 }}>{t('arc.empty')}</h3>
            <p className="muted" style={{ margin: 0 }}>{t('arc.emptyHelp')}</p>
          </div>
        ) : (
          <div className="fields-table-wrap">
            <table className="arc-table">
              <thead>
                <tr>
                  <th>{t('arc.when')}</th>
                  <th>{t('arc.what')}</th>
                  <th>{t('arc.by')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.entries.map((entry) => (
                  <tr key={entry.id}>
                    <td className="adm-nowrap adm-when">{formatDateTime(entry.deleted_at)}</td>
                    <td>
                      <span className="pill neutral arc-kind">{t(`arc.one.${entry.kind}`)}</span>
                      <strong className="arc-label">{entry.label}</strong>
                      <span className="faint arc-detail"><Detail entry={entry} /></span>
                    </td>
                    <td>{entry.deleted_by || <span className="faint">—</span>}</td>
                    <td className="arc-actions">
                      <button
                        type="button"
                        className="primary"
                        disabled={busyId === entry.id}
                        onClick={() => restore(entry)}
                      >
                        {busyId === entry.id ? t('arc.restoring') : t('arc.restore')}
                      </button>
                      <button
                        type="button"
                        className="danger"
                        disabled={busyId === entry.id}
                        onClick={() => setPurging({ entry, working: false, error: null })}
                      >
                        {t('arc.purge')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {purging && (
        <DangerDialog
          title={t('arc.purgeTitle', { label: purging.entry.label })}
          confirmLabel={t('arc.purge')}
          workingLabel={t('common.deleting')}
          working={purging.working}
          onConfirm={confirmPurge}
          onCancel={() => setPurging(null)}
        >
          <p>{t('arc.purgeBody')}</p>
          {purging.error && <div className="banner fail">{purging.error}</div>}
        </DangerDialog>
      )}
    </>
  )
}
