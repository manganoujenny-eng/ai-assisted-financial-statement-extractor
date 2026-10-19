/* Supervisor dashboard — every analyst's work in one view .
 *
 * Work queues first (what needs the supervisor now), then each analyst's
 * activity and extraction quality, then statistics of every ratio across
 * all current validated results, the checks that fail most, and every case.
 * All figures come from GET /api/supervisor/overview, computed by the same
 * rule-based engine as each case's own dashboard. Read-only.
 *
 * Item 5: "awaiting validation" holds the cases an analyst has SUBMITTED —
 * the only ones a supervisor can validate. "Validated by me" lists the
 * current results this supervisor signed, with the analyst behind each.
 */

import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import * as api from '../api/client.js'
import StatusPill from '../components/StatusPill.jsx'
import { useCheckText } from '../components/ChecksPanel.jsx'
import { labelByCode, useI18n } from '../i18n/index.jsx'

const STATUSES = [
  'CREATED',
  'EXTRACTING',
  'EXTRACTION_FAILED',
  'EXTRACTED',
  'UNDER_REVIEW',
  'SUBMITTED',
  'VALIDATED',
  'ANALYSED',
]

function Stat({ label, value, tone }) {
  return (
    <div className="summary-stat">
      <span className="faint">{label}</span>
      <strong style={tone === 'fail' && value > 0 ? { color: '#c62828' } : undefined}>{value}</strong>
    </div>
  )
}

function caseLink(row, t) {
  if (row.status === 'VALIDATED' || row.status === 'ANALYSED') {
    return <Link to={`/cases/${row.id}/dashboard`}>{t('myCases.dashboard')}</Link>
  }
  if (row.latest_extraction_id && row.latest_extraction_status !== 'EXTRACTION_FAILED') {
    return (
      <Link to={`/cases/${row.id}/review/${row.latest_extraction_id}`}>
        {row.status === 'SUBMITTED' ? t('workflow.reviewAndValidate') : t('myCases.review')}
      </Link>
    )
  }
  return <Link to="/">{t('nav.cases')}</Link>
}

// "helena  Ndongo" and "Helena Ndongo" are the same person.
function sameName(a, b) {
  const norm = (value) => (value || '').split(/\s+/).join(' ').trim().toLowerCase()
  return norm(a) !== '' && norm(a) === norm(b)
}

function Queue({ title, rows, empty, extra }) {
  const { t } = useI18n()
  return (
    <section className="card">
      <h3 style={{ marginTop: 0 }}>
        {title} <span className="pill neutral">{rows.length}</span>
      </h3>
      {rows.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>{empty}</p>
      ) : (
        <div>
          {rows.map((row) => (
            <div
              key={row.id}
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: '4px 10px',
                alignItems: 'center',
                padding: '8px 0',
                borderTop: '1px solid var(--line)',
              }}
            >
              <strong>{row.client}</strong>
              <span className="faint">{row.fiscal_year}</span>
              <span>{row.analyst || <span className="faint">{t('sup.unassigned')}</span>}</span>
              {extra ? extra(row) : <StatusPill status={row.status} kind="case" />}
              <span style={{ marginLeft: 'auto' }}>{caseLink(row, t)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

export default function SupervisorPage() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [analystFilter, setAnalystFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const { t, formatDateTime } = useI18n()
  const { checkLabel } = useCheckText()

  useEffect(() => {
    api
      .getSupervisorOverview()
      .then(setData)
      .catch((err) => setError(err.message))
  }, [])

  const ratioCodes = useMemo(() => (data?.ratios || []).map((ratio) => ratio.code), [data])

  const filteredCases = useMemo(
    () =>
      (data?.cases || []).filter(
        (row) =>
          (!analystFilter || (row.analyst || '') === analystFilter) &&
          (!statusFilter || row.status === statusFilter)
      ),
    [data, analystFilter, statusFilter]
  )

  const validatedByMe = useMemo(
    () =>
      (data?.cases || [])
        .filter((row) => row.validated_by && sameName(row.validated_by, api.getAnalystName()))
        .sort((a, b) => (b.validated_at || '').localeCompare(a.validated_at || '')),
    [data]
  )

  if (error) return <div className="banner fail">{error}</div>
  if (!data) return <p className="muted">{t('sup.loading')}</p>

  const { totals, queues } = data

  return (
    <>
      <h2 className="page-title">{t('nav.supervisor')}</h2>
      <p className="page-subtitle">
        {t('sup.subtitle')}
      </p>

      <section
        className="dashboard-summary"
        style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}
      >
        <Stat label={t('sup.statCases')} value={totals.cases} />
        <Stat label={t('sup.statAwaiting')} value={totals.awaiting_validation} />
        <Stat label={t('sup.statValidated')} value={totals.validated} />
        <Stat label={t('sup.statValidatedFailing')} value={totals.validated_with_failures} tone="fail" />
        <Stat label={t('sup.statAiDrafts')} value={totals.ai_drafts_pending} />
        <Stat label={t('sup.statFailed')} value={totals.extraction_failed} tone="fail" />
        <Stat label={t('sup.statAnalysts')} value={totals.analysts} />
      </section>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: 16,
        }}
      >
        <Queue
          title={t('sup.qAwaiting')}
          rows={queues.awaiting_validation}
          empty={t('sup.qAwaitingEmpty')}
        />
        <Queue
          title={t('sup.statValidatedFailing')}
          rows={queues.validated_with_failures}
          empty={t('sup.qFailingEmpty')}
          extra={(row) => (
            <span className="pill fail">{row.failed_blocking_checks.join(', ')}</span>
          )}
        />
        <Queue
          title={t('sup.qAiDrafts')}
          rows={queues.ai_drafts_pending}
          empty={t('sup.qAiDraftsEmpty')}
        />
        <Queue
          title={t('sup.statFailed')}
          rows={queues.extraction_failed}
          empty={t('sup.qFailedEmpty')}
          extra={(row) => <span className="faint">{row.failure_reason || '—'}</span>}
        />
      </div>

      <section className="card">
        <h3 style={{ marginTop: 0 }}>
          {t('workflow.validatedByMe')} <span className="pill neutral">{validatedByMe.length}</span>
        </h3>
        <p className="faint" style={{ marginTop: 0 }}>{t('workflow.validatedByMeHint')}</p>
        {validatedByMe.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>{t('workflow.validatedByMeEmpty')}</p>
        ) : (
          <div className="fields-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t('cases.client')}</th>
                  <th>{t('addItem.year')}</th>
                  <th>{t('users.analyst')}</th>
                  <th>{t('users.status')}</th>
                  <th>{t('workflow.validatedOn')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {validatedByMe.map((row) => (
                  <tr key={row.id}>
                    <td><strong>{row.client}</strong></td>
                    <td>{row.fiscal_year}</td>
                    <td>{row.analyst || <span className="faint">{t('sup.unassigned')}</span>}</td>
                    <td><StatusPill status={row.status} kind="case" /></td>
                    <td>{formatDateTime(row.validated_at)}</td>
                    <td>{caseLink(row, t)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h3 style={{ marginTop: 0 }}>{t('sup.analysts')}</h3>
        <p className="faint" style={{ marginTop: 0 }}>
          {t('sup.analystsHint')}
        </p>
        <div className="fields-table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('users.analyst')}</th>
                <th className="num">{t('sup.statCases')}</th>
                <th className="num">{t('sup.inProgress')}</th>
                <th className="num">{t('sup.statValidated')}</th>
                <th className="num">{t('sup.withFailing')}</th>
                <th className="num">{t('sup.aiPending')}</th>
                <th className="num">{t('sup.proposed')}</th>
                <th className="num">{t('sup.corrected')}</th>
                <th className="num">{t('sup.keyed')}</th>
                <th className="num">{t('sup.correctionRate')}</th>
              </tr>
            </thead>
            <tbody>
              {data.analysts.map((row) => (
                <tr key={row.analyst || 'unassigned'}>
                  <td>
                    {row.analyst ? (
                      <button
                        type="button"
                        style={{
                          background: 'none',
                          border: 'none',
                          padding: 0,
                          color: 'var(--accent)',
                          cursor: 'pointer',
                          font: 'inherit',
                        }}
                        onClick={() => setAnalystFilter(row.analyst)}
                        title={t('sup.showAnalyst')}
                      >
                        {row.analyst}
                      </button>
                    ) : (
                      <span className="faint">{t('sup.unassigned')}</span>
                    )}
                    {row.active === false && <span className="faint"> ({t('users.deactivated')})</span>}
                    {row.role === 'SUPERVISOR' && <span className="faint"> ({t('role.SUPERVISOR')})</span>}
                  </td>
                  <td className="num">{row.cases}</td>
                  <td className="num">{row.in_progress}</td>
                  <td className="num">{row.validated}</td>
                  <td className="num">{row.validated_with_failures}</td>
                  <td className="num">{row.ai_drafts_pending}</td>
                  <td className="num">{row.fields_proposed}</td>
                  <td className="num">{row.fields_corrected}</td>
                  <td className="num">{row.fields_keyed}</td>
                  <td className="num">{row.correction_rate != null ? `${row.correction_rate} %` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h3 style={{ marginTop: 0 }}>{t('sup.ratiosTitle')}</h3>
        <div className="fields-table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t('myCases.ratio')}</th>
                <th className="num">{t('sup.computed')}</th>
                <th className="num">{t('sup.notComputable')}</th>
                <th className="num">{t('sup.min')}</th>
                <th className="num">{t('sup.median')}</th>
                <th className="num">{t('sup.mean')}</th>
                <th className="num">{t('sup.max')}</th>
                <th className="num">{t('sup.reference')}</th>
                <th className="num">{t('sup.below')}</th>
              </tr>
            </thead>
            <tbody>
              {data.ratios.map((ratio) => (
                <tr key={ratio.code}>
                  <td>
                    <span className="code">{ratio.code}</span> {labelByCode(t, 'ratio', ratio.code, ratio.name)}
                  </td>
                  <td className="num">{ratio.computed}</td>
                  <td className="num">{ratio.not_computable}</td>
                  <td className="num">{ratio.min ?? '—'}</td>
                  <td className="num">{ratio.median ?? '—'}</td>
                  <td className="num">{ratio.mean ?? '—'}</td>
                  <td className="num">{ratio.max ?? '—'}</td>
                  <td className="num">{ratio.threshold ? `${ratio.threshold} ${ratio.unit}` : t('sup.none')}</td>
                  <td className="num">{ratio.below_threshold ?? '—'}</td>
                </tr>
              ))}
              {data.ratios.length === 0 && (
                <tr>
                  <td colSpan={9} className="muted">{t('sup.noValidated')}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="faint" style={{ marginBottom: 0 }}>
          {t('sup.noReferenceHint')}
        </p>
      </section>

      {data.checks.length > 0 && (
        <section className="card">
          <h3 style={{ marginTop: 0 }}>{t('sup.checksTitle')}</h3>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {data.checks.map((check) => (
              <span key={check.code} className={`pill ${check.failed ? 'fail' : 'ok'}`}>
                {check.code} {checkLabel(check)}: {check.failed}
              </span>
            ))}
          </div>
        </section>
      )}

      <section className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <h3 style={{ margin: 0 }}>{t('sup.allCases')}</h3>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <select value={analystFilter} onChange={(event) => setAnalystFilter(event.target.value)}>
              <option value="">{t('sup.allAnalysts')}</option>
              {data.analysts
                .filter((row) => row.analyst)
                .map((row) => (
                  <option key={row.analyst} value={row.analyst}>
                    {row.analyst}
                  </option>
                ))}
            </select>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="">{t('sup.allStatuses')}</option>
              {STATUSES.map((status) => (
                <option key={status} value={status}>
                  {t(`status.case.${status}`)}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="fields-table-wrap" style={{ marginTop: 12 }}>
          <table>
            <thead>
              <tr>
                <th>{t('cases.client')}</th>
                <th>{t('addItem.year')}</th>
                <th>{t('users.analyst')}</th>
                <th>{t('users.status')}</th>
                <th>{t('sup.validatedBy')}</th>
                {ratioCodes.map((code) => (
                  <th key={code} className="num">{code}</th>
                ))}
                <th />
              </tr>
            </thead>
            <tbody>
              {filteredCases.map((row) => (
                <tr key={row.id}>
                  <td>
                    <strong>{row.client}</strong>
                    {row.failed_blocking_checks.length > 0 && (
                      <span className="pill fail" style={{ marginLeft: 6 }}>
                        {row.failed_blocking_checks.join(', ')}
                      </span>
                    )}
                  </td>
                  <td>{row.fiscal_year}</td>
                  <td>{row.analyst || <span className="faint">{t('sup.unassigned')}</span>}</td>
                  <td><StatusPill status={row.status} kind="case" /></td>
                  <td>{row.validated_by || '—'}</td>
                  {ratioCodes.map((code) => (
                    <td key={code} className="num">{row.ratios[code] ?? '—'}</td>
                  ))}
                  <td>{caseLink(row, t)}</td>
                </tr>
              ))}
              {filteredCases.length === 0 && (
                <tr>
                  <td colSpan={6 + ratioCodes.length} className="muted">{t('sup.noMatch')}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}