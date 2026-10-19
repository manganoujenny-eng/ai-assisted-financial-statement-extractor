/* My cases — the signed-in person's own work .
 *
 * An analyst: their own cases, where each stands and what the analysis
 * says (the backend enforces "own cases only").
 * A supervisor: their validation work, in two lists —
 *   1. waiting for a validation (submitted by an analyst; any supervisor
 *      may validate it), with a direct "Review & validate" link;
 *   2. the cases whose current result they validated, with the analyst.
 * Every case of every analyst stays on the Cases page.
 *
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

function CaseCard({ analysisCase, showAnalyst = false }) {
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
          {showAnalyst && (
            <p className="muted" style={{ margin: '4px 0 0' }}>
              {t('myCases.analyst', { name: analysisCase.analyst || t('sup.unassigned') })}
            </p>
          )}
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
            <Link
              className={`button-like${analysisCase.my_queue === 'AWAITING_VALIDATION' ? ' primary' : ''}`}
              to={`/cases/${analysisCase.id}/review/${run.id}`}
            >
              {analysisCase.my_queue === 'AWAITING_VALIDATION'
                ? t('myCases.reviewValidate')
                : t('myCases.review')}
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
              {ai.sections?.diagnosis && (
                <p style={{ whiteSpace: 'pre-wrap' }}>{ai.sections.diagnosis}</p>
              )}
              {(ai.sections?.recommendations || []).length > 0 && (
                <>
                  <strong>{t('ai.recommendations')}</strong>
                  <ul>
                    {ai.sections.recommendations.map((point, index) => (
                      <li key={index}>{point}</li>
                    ))}
                  </ul>
                </>
              )}
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

function sortCases(cases) {
  return [...cases].sort(
    (a, b) =>
      STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) ||
      String(b.created_at).localeCompare(String(a.created_at))
  )
}

function StatusCounts({ cases }) {
  const counts = cases.reduce((acc, item) => {
    acc[item.status] = (acc[item.status] || 0) + 1
    return acc
  }, {})
  if (cases.length === 0) return null
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 16 }}>
      {STATUS_ORDER.filter((status) => counts[status]).map((status) => (
        <span key={status} style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <StatusPill status={status} kind="case" /> {counts[status]}
        </span>
      ))}
    </div>
  )
}

/* The supervisor's two lists. */
function SupervisorWork({ cases }) {
  const { t } = useI18n()
  const awaiting = sortCases(cases.filter((item) => item.my_queue === 'AWAITING_VALIDATION'))
  const validated = cases
    .filter((item) => item.my_queue === 'VALIDATED_BY_ME')
    .sort((a, b) =>
      String(b.dataset?.validated_at || '').localeCompare(String(a.dataset?.validated_at || ''))
    )

  return (
    <>
      <section className="my-queue">
        <div className="my-queue-head">
          <h3>{t('myCases.awaitingTitle')}</h3>
          <span className={`pill ${awaiting.length ? 'warn' : 'neutral'}`}>{awaiting.length}</span>
        </div>
        <p className="faint">{t('myCases.awaitingHint')}</p>
        {awaiting.length === 0 ? (
          <p className="muted">{t('myCases.awaitingEmpty')}</p>
        ) : (
          awaiting.map((item) => <CaseCard key={item.id} analysisCase={item} showAnalyst />)
        )}
      </section>

      <section className="my-queue">
        <div className="my-queue-head">
          <h3>{t('myCases.validatedTitle')}</h3>
          <span className="pill neutral">{validated.length}</span>
        </div>
        <p className="faint">{t('myCases.validatedHint')}</p>
        {validated.length === 0 ? (
          <p className="muted">{t('myCases.validatedEmpty')}</p>
        ) : (
          validated.map((item) => <CaseCard key={item.id} analysisCase={item} showAnalyst />)
        )}
      </section>
    </>
  )
}

export default function MyCasesPage() {
  const me = api.getCurrentUser()
  const supervisor = api.isSupervisor()

  const [cases, setCases] = useState(null)
  const [error, setError] = useState(null)
  const { t } = useI18n()

  useEffect(() => {
    let cancelled = false
    setCases(null)
    setError(null)
    // No argument: an analyst gets their own cases, a supervisor their
    // validation work (each case tagged with "my_queue").
    api
      .getMyCases()
      .then((result) => {
        if (!cancelled) setCases(result)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <>
      <div className="cases-header">
        <div>
          <h2 className="page-title">
            {supervisor
              ? t('myCases.titleSupervisor', { name: me?.full_name || '' })
              : t('myCases.titleMine', { name: me?.full_name || '' })}
          </h2>
          <p className="page-subtitle">
            {supervisor ? t('myCases.subtitleSupervisor') : t('myCases.subtitle')}
          </p>
        </div>
      </div>

      {error && <div className="banner fail">{error}</div>}

      {cases === null && !error && <p className="muted">{t('common.loading')}</p>}

      {cases && supervisor && <SupervisorWork cases={cases} />}

      {cases && !supervisor && (
        <>
          <StatusCounts cases={cases} />
          {cases.length === 0 && <p className="muted">{t('myCases.empty')}</p>}
          {sortCases(cases).map((analysisCase) => (
            <CaseCard key={analysisCase.id} analysisCase={analysisCase} />
          ))}
        </>
      )}
    </>
  )
}