/* My cases — the signed-in person's cases, where each stands, and what the
 * analysis says (items 4 and 5).
 *
 * An analyst sees their own cases only (the backend enforces it). A
 * supervisor can switch to any analyst, or to the cases nobody owns.
 * Read-only: ratios come with their rule-based interpretation; the AI
 * commentary shows only once approved (BR-13).
 */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import * as api from '../api/client.js'
import StatusPill from '../components/StatusPill.jsx'
import { labelByCode, useI18n } from '../i18n/index.jsx'

const STATUS_ORDER = [
  'CREATED',
  'EXTRACTING',
  'EXTRACTION_FAILED',
  'EXTRACTED',
  'UNDER_REVIEW',
  'SUBMITTED',
  'VALIDATED',
  'ANALYSED',
]

const UNASSIGNED = '__unassigned__'

function CaseCard({ analysisCase }) {
  const { t, formatDate } = useI18n()
  const run = analysisCase.latest_extraction
  const ai = analysisCase.ai_analysis
  const blocking = (analysisCase.failed_checks || []).filter(
    (check) => check.severity === 'BLOCKING'
  )

  return (
    <article className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <h3 style={{ margin: 0 }}>
            {analysisCase.client} · {analysisCase.fiscal_year}
          </h3>
          <p className="faint" style={{ margin: '4px 0 0' }}>
            {t('myCases.documents', { count: analysisCase.documents.length })}
            {run
              ? ` · ${t('myCases.lastExtraction', { status: t(`status.case.${run.status}`) })}`
              : ` · ${t('myCases.notExtracted')}`}
            {analysisCase.dataset
              ? ` · ${t('myCases.validatedBy', {
                  name: analysisCase.dataset.validated_by,
                  date: formatDate(analysisCase.dataset.validated_at),
                })}`
              : ''}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <StatusPill status={analysisCase.status} kind="case" />
          {run && run.status !== 'EXTRACTION_FAILED' && (
            <Link className="button-like" to={`/cases/${analysisCase.id}/review/${run.id}`}>
              {t('myCases.review')}
            </Link>
          )}
          {analysisCase.dataset && (
            <Link className="button-like primary" to={`/cases/${analysisCase.id}/dashboard`}>
              {t('myCases.dashboard')}
            </Link>
          )}
        </div>
      </div>

      {run?.status === 'EXTRACTION_FAILED' && (
        <div className="banner fail" style={{ marginTop: 12 }}>
          {t('myCases.extractionFailed', { reason: run.failure_reason || t('myCases.noReason') })}
        </div>
      )}

      {blocking.length > 0 && (
        <div className="banner fail" style={{ marginTop: 12 }}>
          {t('myCases.validatedWithFailures', {
            count: blocking.length,
            codes: blocking.map((check) => check.code).join(', '),
          })}
        </div>
      )}

      {analysisCase.ratios.length > 0 && (
        <div className="fields-table-wrap" style={{ marginTop: 12 }}>
          <table>
            <thead>
              <tr>
                <th>{t('myCases.ratio')}</th>
                <th className="num">{t('myCases.value')}</th>
                <th>{t('myCases.interpretation')}</th>
              </tr>
            </thead>
            <tbody>
              {analysisCase.ratios.map((ratio) => (
                <tr key={ratio.code}>
                  <td>
                    <span className="code">{ratio.code}</span> {labelByCode(t, 'ratio', ratio.code, ratio.name)}
                  </td>
                  <td className="num">
                    {ratio.status === 'COMPUTED' ? `${ratio.value} ${ratio.unit || ''}` : '—'}
                  </td>
                  <td>{ratio.interpretation?.text || ratio.reason || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {analysisCase.dataset && (
        <div style={{ marginTop: 12 }}>
          <strong>{t('ai.title')}: </strong>
          {!ai && <span className="muted">{t('myCases.aiNotDrafted')}</span>}
          {ai?.status === 'FAILED' && (
            <span className="muted">{t('myCases.aiUnavailable', { reason: ai.failure_reason })}</span>
          )}
          {ai?.status === 'DRAFT' && (
            <span>
              <span className="pill warn">{t('ai.status.DRAFT')}</span>{' '}
              <Link to={`/cases/${analysisCase.id}/dashboard`}>{t('myCases.reviewApprove')}</Link>
            </span>
          )}
          {ai?.status === 'APPROVED' && (
            <>
              <span className="faint">
                {t('myCases.approvedBy', { name: ai.approved_by })}
                {ai.was_edited ? ` (${t('myCases.edited')})` : ''}
              </span>
              <p style={{ whiteSpace: 'pre-wrap' }}>{ai.sections?.overview}</p>
              {(ai.sections?.attention || []).length > 0 && (
                <ul>
                  {ai.sections.attention.map((point, index) => (
                    <li key={index}>{point}</li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      )}
    </article>
  )
}

export default function MyCasesPage() {
  const me = api.getCurrentUser()
  const supervisor = api.isSupervisor()

  // '' = my own cases; a name = that analyst's (supervisor only).
  const [who, setWho] = useState('')
  const [users, setUsers] = useState([])
  const [cases, setCases] = useState(null)
  const [error, setError] = useState(null)
  const { t } = useI18n()

  useEffect(() => {
    if (supervisor) api.listUsers().then(setUsers).catch(() => setUsers([]))
  }, [supervisor])

  useEffect(() => {
    let cancelled = false
    setCases(null)
    setError(null)
    const request =
      who === '' ? api.getMyCases() : api.getMyCases(who === UNASSIGNED ? '' : who)
    request
      .then((result) => {
        if (!cancelled) setCases(result)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [who])

  const counts = (cases || []).reduce((acc, item) => {
    acc[item.status] = (acc[item.status] || 0) + 1
    return acc
  }, {})

  const sorted = [...(cases || [])].sort(
    (a, b) =>
      STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) ||
      String(b.created_at).localeCompare(String(a.created_at))
  )

  const title =
    who === ''
      ? t('myCases.titleMine', { name: me?.full_name || '' })
      : who === UNASSIGNED
        ? t('myCases.titleUnassigned')
        : t('myCases.titleOf', { name: who })

  return (
    <>
      <div className="cases-header">
        <div>
          <h2 className="page-title">{title}</h2>
          <p className="page-subtitle">
            {t('myCases.subtitle')}
          </p>
        </div>
        {supervisor && (
          <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            {t('myCases.show')}
            <select value={who} onChange={(event) => setWho(event.target.value)}>
              <option value="">{t('myCases.optionMine')}</option>
              {users
                .filter((user) => user.id !== me?.id)
                .map((user) => (
                  <option key={user.id} value={user.full_name}>
                    {user.full_name}
                    {user.active ? '' : ` (${t('users.deactivated')})`}
                  </option>
                ))}
              <option value={UNASSIGNED}>{t('myCases.optionUnassigned')}</option>
            </select>
          </label>
        )}
      </div>

      {error && <div className="banner fail">{error}</div>}

      {cases === null && !error && <p className="muted">{t('common.loading')}</p>}

      {cases && cases.length > 0 && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
          {STATUS_ORDER.filter((status) => counts[status]).map((status) => (
            <span key={status} style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
              <StatusPill status={status} kind="case" /> {counts[status]}
            </span>
          ))}
        </div>
      )}

      {cases && cases.length === 0 && <p className="muted">{t('myCases.empty')}</p>}

      {sorted.map((analysisCase) => (
        <CaseCard key={analysisCase.id} analysisCase={analysisCase} />
      ))}
    </>
  )
}