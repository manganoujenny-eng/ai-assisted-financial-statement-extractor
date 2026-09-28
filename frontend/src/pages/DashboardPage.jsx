/* FR-18 — the dashboard: value, status, source items, explanation.
 *
 * Note what each card shows and, more importantly, what it refuses to show.
 * A NOT_COMPUTABLE ratio is displayed with its reason, not hidden and not
 * shown as zero (BR-02). A ratio with no documented reference is stated
 * without judgement (BR-14). Those two refusals are the most defensible
 * things on this screen, and a jury will ask about them — so the interface
 * has to make them visible rather than tidy them away.
 */

import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import * as api from '../api/client.js'
import ChecksPanel from '../components/ChecksPanel.jsx'

function RatioCard({ ratio }) {
  const computed = ratio.status === 'COMPUTED'
  return (
    <div className="card" style={{ marginBottom: 0 }}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <span className="code">{ratio.code}</span>
        <span className={`pill ${computed ? 'neutral' : 'warn'}`}>
          {computed ? ratio.unit : 'not computable'}
        </span>
      </div>

      <div style={{ fontSize: 30, fontWeight: 600, letterSpacing: '-0.02em', margin: '6px 0 2px' }}>
        {computed ? (
          <span className="num">{ratio.value}</span>
        ) : (
          <span className="muted" style={{ fontSize: 18, fontWeight: 400 }}>—</span>
        )}
      </div>
      <div className="muted" style={{ marginBottom: 10 }}>{ratio.name}</div>

      {ratio.interpretation && (
        <p style={{ margin: '0 0 10px', fontSize: 14 }}>{ratio.interpretation.text}</p>
      )}

      {/* BR-04 — the items the value was built from travel with the value.
          Also the most direct answer to "where does this number come from?",
          which is the first question anyone asks of a financial indicator. */}
      <div className="faint">
        from {ratio.items_used.join(' · ') || '—'}
      </div>

      {ratio.interpretation?.reference_source && (
        <details style={{ marginTop: 8 }}>
          <summary className="faint" style={{ cursor: 'pointer' }}>reference applied</summary>
          <p className="faint" style={{ marginTop: 6 }}>
            {ratio.interpretation.reference_source}
          </p>
        </details>
      )}
    </div>
  )
}

export default function DashboardPage() {
  const { caseId } = useParams()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.getCaseAnalysis(caseId).then(setData).catch((err) => setError(err.message))
  }, [caseId])

  if (error) return <div className="banner fail">{error}</div>
  if (!data) return <p className="muted">Loading…</p>
  if (!data.dataset) {
    return (
      <div className="banner info">
        No validated dataset on this case yet. Ratios are computed from validated
        data only (BR-01). <Link to="/">Back to the cases</Link>.
      </div>
    )
  }

  return (
    <>
      <h2 className="page-title">
        {data.case.client} · {data.case.fiscal_year}
      </h2>
      <p className="page-subtitle">
        Validated by {data.dataset.validated_by} on{' '}
        {new Date(data.dataset.validated_at).toLocaleString()} ·{' '}
        {data.dataset.item_count} items frozen
      </p>

      <div className="grid-ratios" style={{ marginBottom: 18 }}>
        {data.ratios.map((ratio) => (
          <RatioCard key={ratio.code} ratio={ratio} />
        ))}
      </div>

      <ChecksPanel checks={data.checks} />

      <div className="card">
        <h2>Export</h2>
        <div className="todo">
          <strong>FR-19 — your exercise, and a late one.</strong> Export is a
          &ldquo;should&rdquo;, not a &ldquo;must&rdquo;. Build it in week 6 if
          weeks 3 to 5 went to plan, and not before: the arbitration rule of
          dossier §3.3 says to cut the interface before the evaluation.
        </div>
      </div>
    </>
  )
}
