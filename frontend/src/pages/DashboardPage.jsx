/* FR-15 to FR-20 — analysis dashboard.
 *
 * Uses the existing GET /api/cases/{caseId}/analysis contract.
 * Ratio values, reasons, inputs and interpretations come from the backend.
 * No ratio is calculated in the frontend.
 */

import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import * as api from '../api/client.js'
import ChecksPanel from '../components/ChecksPanel.jsx'
import AiCommentaryPanel from '../components/AiCommentaryPanel.jsx'
import { KeyFigures, RatioComparison } from '../components/YearComparisonChart.jsx'
import { labelByCode, useI18n } from '../i18n/index.jsx'
import { interpretationText, reasonText, referenceSourceText } from '../i18n/interpretation.js'

function RatioCard({ ratio, onViewDetails }) {
  const { t } = useI18n()
  const computed = ratio.status === 'COMPUTED'
  const items = ratio.items_used || []

  return (
    <article className="card dashboard-ratio-card">
      <div className="ratio-card-top">
        <span className="code">{ratio.code}</span>

        <span
          className={`pill ${
            computed ? 'ok' : 'warn'
          }`}
        >
          {t(`ratioStatus.${ratio.status || 'UNKNOWN'}`)}
        </span>
      </div>

      <div className="ratio-value">
        {computed ? (
          <>
            <span className="num">{ratio.value}</span>
            {ratio.unit && (
              <span className="ratio-unit">{ratio.unit}</span>
            )}
          </>
        ) : (
          <span className="ratio-unavailable">—</span>
        )}
      </div>

      <h3 className="ratio-name">{labelByCode(t, 'ratio', ratio.code, ratio.name)}</h3>

      {!computed && (
        <p className="ratio-reason">
          {reasonText(t, ratio.reason) || t('dash.cannotCompute')}
        </p>
      )}

      <div className="ratio-sources">
        <span className="faint">{t('dash.sourceItems')}</span>
        <p>
          {items.length > 0 ? items.join(' · ') : t('dash.noSourceItems')}
        </p>
      </div>

      <button
        type="button"
        onClick={() => onViewDetails(ratio)}
      >
        {computed ? t('checks.viewDetails') : t('dash.viewReason')}
      </button>
    </article>
  )
}

function RatioDetails({ ratio, onClose }) {
  const [showInterpretation, setShowInterpretation] = useState(false)
  const { t } = useI18n()
  const name = labelByCode(t, 'ratio', ratio.code, ratio.name)

  const computed = ratio.status === 'COMPUTED'
  const interpretation = ratio.interpretation
  const items = ratio.items_used || []
  const inputs = ratio.inputs || {}

  return (
    <section className="card ratio-details" id="ratio-details">
      <div className="ratio-details-heading">
        <div>
          <p className="faint">{t('dash.ratioDetails')}</p>
          <h2>{ratio.code} — {name}</h2>
        </div>

        <button type="button" onClick={onClose}>
          {t('common.close')}
        </button>
      </div>

      <div className="ratio-detail-summary">
        <div>
          <span className="faint">{t('myCases.value')}</span>
          <div className="detail-value">
            {computed
              ? `${ratio.value ?? '—'}${ratio.unit ? ` ${ratio.unit}` : ''}`
              : '—'}
          </div>
        </div>

        <div>
          <span className="faint">{t('users.status')}</span>
          <p>
            <span className={`pill ${computed ? 'ok' : 'warn'}`}>
              {t(`ratioStatus.${ratio.status || 'UNKNOWN'}`)}
            </span>
          </p>
        </div>
      </div>

      {!computed && (
        <div className="banner info">
          <strong>{t('dash.whyUnavailable')}</strong>
          <p>
            {reasonText(t, ratio.reason) || t('dash.noReason')}
          </p>
        </div>
      )}

      <h3>{t('dash.sourceItems')}</h3>
      {items.length > 0 ? (
        <ul>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">{t('dash.noSourceItemsBackend')}</p>
      )}

      {Object.keys(inputs).length > 0 && (
        <>
          <h3>{t('dash.inputs')}</h3>
          <table>
            <thead>
              <tr>
                <th>{t('dash.input')}</th>
                <th style={{ textAlign: 'right' }}>{t('myCases.value')}</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(inputs).map(([name, value]) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td className="num">
                    {typeof value === 'object' && value !== null
                      ? JSON.stringify(value)
                      : String(value ?? '—')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      <div className="interpretation-section">
        <h3>{t('ai.kicker')}</h3>

        {!interpretation ? (
          <p className="muted">
            {t('dash.noInterpretation')}
          </p>
        ) : (
          <>
            <button
              type="button"
              onClick={() => setShowInterpretation((current) => !current)}
            >
              {showInterpretation
                ? t('dash.hideInterpretation')
                : t('dash.viewInterpretation')}
            </button>

            {showInterpretation && (
              <div className="interpretation-content">
                <p>
                  <strong>{t('dash.ratioLabel')}</strong> {ratio.code} — {name}
                </p>
                <p>
                  <strong>{t('dash.valueLabel')}</strong>{' '}
                  {computed
                    ? `${ratio.value ?? '—'}${ratio.unit ? ` ${ratio.unit}` : ''}`
                    : t('ratioStatus.NOT_COMPUTABLE')}
                </p>

                <p>{interpretationText(t, ratio) || t('dash.noInterpretationText')}</p>

                {interpretation.reference_source && (
                  <p>
                    <strong>{t('dash.referenceApplied')}</strong>{' '}
                    {referenceSourceText(t, ratio)}
                  </p>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  )
}

function YearComparison({ data }) {
  /*
   * Shown when the API provides a comparison: Year N-1 from the same
   * validated package, or a validated case of the same client for the
   * previous year. Charts first; the same figures as a table underneath.
   */
  const comparison = data.year_comparison
  const { t } = useI18n()

  return (
    <section className="card">
      <h2>{t('dash.yearComparison')}</h2>

      {!comparison ? (
        <p className="muted">
          {t('dash.noComparison')}
        </p>
      ) : (
        <>
          <p className="faint">
            {t('dash.comparedWith', {
              current: comparison.current_year,
              previous: comparison.previous_year,
            })}
          </p>

          <RatioComparison comparison={comparison} />

          <KeyFigures
            dataset={data.dataset}
            previousYear={comparison.previous_year}
            currentYear={comparison.current_year}
          />

          <details className="yc-table">
            <summary>{t('dash.chartAsTable')}</summary>
            <div className="cases-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{t('myCases.ratio')}</th>
                    <th className="num">{t('dash.currentYear')}</th>
                    <th className="num">{t('dash.previousYear')}</th>
                    <th className="num">{t('dash.change')}</th>
                  </tr>
                </thead>
                <tbody>
                  {(comparison.ratios || []).map((item) => (
                    <tr key={item.code}>
                      <td>{labelByCode(t, 'ratio', item.code, item.name || item.code)}</td>
                      <td className="num">{item.current_value ?? '—'}</td>
                      <td className="num">{item.previous_value ?? '—'}</td>
                      <td className="num">{item.change ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </section>
  )
}

export default function DashboardPage() {
  const { caseId } = useParams()

  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [selectedRatio, setSelectedRatio] = useState(null)
  const { t, formatDateTime } = useI18n()

  useEffect(() => {
    let cancelled = false

    setData(null)
    setError(null)
    setSelectedRatio(null)

    api.getCaseAnalysis(caseId)
      .then((result) => {
        if (!cancelled) setData(result)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })

    return () => {
      cancelled = true
    }
  }, [caseId])

  function openRatio(ratio) {
    setSelectedRatio(ratio)

    // Move focus to the details section without opening another page.
    requestAnimationFrame(() => {
      document.getElementById('ratio-details')?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      })
    })
  }

  if (error) {
    return <div className="banner fail">{error}</div>
  }

  if (!data) {
    return <p className="muted">{t('dash.loading')}</p>
  }

  if (!data.dataset) {
    return (
      <div className="banner info">
        {t('dash.noDataset')}{' '}
        <Link to="/">{t('dash.backToCases')}</Link>.
      </div>
    )
  }

  const ratios = data.ratios || []

  // Validation no longer requires every blocking check to pass, so a
  // dataset can reach this page with known failures. Say so up front.
  const failedBlockingChecks = (data.checks || []).filter(
    (check) => !check.passed && check.severity === 'BLOCKING'
  )
  const computedCount = ratios.filter(
    (ratio) => ratio.status === 'COMPUTED'
  ).length
  const unavailableCount = ratios.filter(
    (ratio) => ratio.status === 'NOT_COMPUTABLE'
  ).length

  return (
    <>
      <div className="dashboard-header">
        <div>
          <p className="faint">{t('dash.kicker')}</p>
          <h2 className="page-title">
            {data.case.client} · {data.case.fiscal_year}
          </h2>
          <p className="page-subtitle">
            {t('dash.subtitle')}
          </p>
        </div>

        <Link to="/" className="dashboard-back-link">
          {t('dash.backToCases')}
        </Link>
      </div>

      {failedBlockingChecks.length > 0 && (
        <div className="banner fail" style={{ fontSize: '1.05em' }}>
          <strong>
            ⚠{' '}
            {t('dash.validatedWithFailures', {
              count: failedBlockingChecks.length,
              codes: failedBlockingChecks.map((check) => check.code).join(', '),
            })}
          </strong>{' '}
          {t('dash.mayBeWrong')}
        </div>
      )}

      <section className="card dataset-status-card">
        <div>
          <span className="faint">{t('dash.validatedDataset')}</span>
          <h2>
            <span className="pill ok">{t('dash.validatedPill')}</span>
          </h2>
          <p className="muted">
            {t('dash.validatedBy', { name: data.dataset.validated_by || '—' })}
          </p>
          <p className="faint">
            {data.dataset.validated_at
              ? formatDateTime(data.dataset.validated_at)
              : t('dash.noValidationDate')}
          </p>
        </div>

        <div className="dataset-item-count">
          <span className="faint">{t('dash.frozenItems')}</span>
          <strong>{data.dataset.item_count ?? '—'}</strong>
        </div>
      </section>

      <section className="dashboard-summary">
        <div className="summary-stat">
          <span className="faint">{t('dash.coreRatios')}</span>
          <strong>{ratios.length}</strong>
        </div>
        <div className="summary-stat">
          <span className="faint">{t('sup.computed')}</span>
          <strong>{computedCount}</strong>
        </div>
        <div className="summary-stat">
          <span className="faint">{t('sup.notComputable')}</span>
          <strong>{unavailableCount}</strong>
        </div>
      </section>

      <section className="dashboard-ratios-section">
        <h2 className="section-title">{t('dash.coreFinancialRatios')}</h2>

        {ratios.length === 0 ? (
          <div className="banner info">
            {t('dash.noRatios')}
          </div>
        ) : (
          <div className="grid-ratios dashboard-ratio-grid">
            {ratios.map((ratio) => (
              <RatioCard
                key={ratio.code}
                ratio={ratio}
                onViewDetails={openRatio}
              />
            ))}
          </div>
        )}
      </section>

      {selectedRatio && (
        <RatioDetails
          key={selectedRatio.code}
          ratio={selectedRatio}
          onClose={() => setSelectedRatio(null)}
        />
      )}

      <YearComparison data={data} />

      <ChecksPanel checks={data.checks || []} />

      <AiCommentaryPanel
        caseId={caseId}
        analysis={data.ai_analysis}
        ratios={ratios}
        onChange={(analysis) =>
          setData((current) => ({ ...current, ai_analysis: analysis }))
        }
      />

      <section className="card dashboard-export">
        <div>
          <h2>{t('dash.exportTitle')}</h2>
          <p className="muted">
            {t('dash.exportHint')}
          </p>
        </div>

        <button
          type="button"
          className="primary"
          onClick={() => {
            window.location.href = `/api/cases/${caseId}/export`
          }}
        >
          {t('dash.exportButton')}
        </button>
      </section>
    </>
  )
}