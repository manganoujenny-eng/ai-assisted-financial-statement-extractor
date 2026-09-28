/* UC-04 — review and correct, then UC-06 — validate.
 *
 * The screen the analyst spends the most time on, so the one where NFR-07
 * ("reviewing one package in under ten minutes by a staff member untrained on
 * the system") is won or lost.
 *
 * What is built: the field table, inline correction, the check panel
 * rerunning after every correction, and a Validate button that is disabled —
 * and says why — while a blocking check fails.
 *
 * What is left to you: the left-hand pane, the original document displayed
 * beside its extracted fields (FR-10). See the placeholder below.
 */

import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import * as api from '../api/client.js'
import ChecksPanel from '../components/ChecksPanel.jsx'
import StatusPill from '../components/StatusPill.jsx'

export default function ReviewPage() {
  const { caseId, extractionId } = useParams()
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [refusal, setRefusal] = useState(null)
  const [editing, setEditing] = useState({})

  async function reload() {
    try {
      setData(await api.getExtractionFields(extractionId))
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    reload()
  }, [extractionId])

  async function onCorrect(field) {
    const value = editing[field.id]
    if (value === undefined || value === '') return
    try {
      const response = await api.correctField(field.id, value, 'analyst')
      // The API returns the rerun checks with the corrected field, so the
      // panel below is always consistent with the table above it. BR-11.
      setData((current) => ({
        ...current,
        checks: response.checks,
        fields: current.fields.map((f) => (f.id === field.id ? response.field : f)),
      }))
      setEditing(({ [field.id]: _removed, ...rest }) => rest)
      setRefusal(null)
    } catch (err) {
      setError(err.message)
    }
  }

  async function onValidate() {
    try {
      const dataset = await api.validateExtraction(extractionId, 'supervisor')
      await api.analyseDataset(dataset.id)
      navigate(`/cases/${caseId}/dashboard`)
    } catch (err) {
      // A 409 here is the system working, not breaking. The supervisor must
      // see exactly which checks refused the validation (UC-06 / E1).
      setRefusal(err.failingChecks?.length ? err.failingChecks : null)
      setError(err.message)
    }
  }

  if (error && !data) return <div className="banner fail">{error}</div>
  if (!data) return <p className="muted">Loading…</p>

  const blocking = data.checks.filter((c) => !c.passed && c.severity === 'BLOCKING')

  return (
    <>
      <h2 className="page-title">Review</h2>
      <p className="page-subtitle">
        {data.fields.length} extracted items · engine {data.extraction.engine}
        {data.extraction.model ? ` · ${data.extraction.model}` : ''}
      </p>

      {refusal && (
        <div className="banner fail">
          Validation refused — {refusal.map((c) => `${c.code} ${c.message}`).join(' · ')}
        </div>
      )}

      <div className="split">
        {/* ------------------------------------------------------------ */}
        <div className="card">
          <h2>Source document</h2>
          <div className="todo">
            <strong>FR-10 — your exercise.</strong> The original document belongs
            here, beside its extracted fields, so the analyst can check an
            amount without leaving the screen.
            <br /><br />
            Two steps. First, the backend has to serve the file: add
            <code> GET /api/documents/&lt;id&gt;/file </code> in
            <code> backend/app/api/routes.py </code> using Flask's
            <code> send_file </code> on <code>document.stored_path</code>.
            Then display it here in an <code>&lt;iframe&gt;</code> — the
            browser has a PDF viewer built in, so you need no library at all
            for the first version.
            <br /><br />
            The refinement worth having afterwards: each field carries
            <code> source_page</code>, so clicking a row can jump the viewer to
            the right page (<code>#page=3</code> in the iframe URL). That one
            detail is most of what NFR-07 asks for.
          </div>
        </div>

        {/* ------------------------------------------------------------ */}
        <div>
          <div className="card">
            <h2>Extracted fields</h2>
            <table>
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Item</th>
                  <th style={{ textAlign: 'right' }}>Amount</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.fields.map((field) => (
                  <tr key={field.id} className={field.was_corrected ? 'corrected' : ''}>
                    <td className="code">{field.item_code}</td>
                    <td className="label">
                      {field.label}
                      {field.was_corrected && (
                        // BR-10 made visible: what the extractor proposed
                        // stays on screen next to what the human retained.
                        <div className="was">proposed {field.proposed_amount}</div>
                      )}
                    </td>
                    <td className="num">
                      {editing[field.id] !== undefined ? (
                        <input
                          className="num"
                          value={editing[field.id]}
                          autoFocus
                          style={{ width: 150 }}
                          onChange={(e) => setEditing({ ...editing, [field.id]: e.target.value })}
                          onKeyDown={(e) => e.key === 'Enter' && onCorrect(field)}
                        />
                      ) : (
                        field.amount_display
                      )}
                    </td>
                    <td><StatusPill status={field.status} kind="field" /></td>
                    <td style={{ textAlign: 'right' }}>
                      {editing[field.id] !== undefined ? (
                        <button className="primary" onClick={() => onCorrect(field)}>Save</button>
                      ) : (
                        <button
                          disabled={field.status === 'VALIDATED'}
                          onClick={() => setEditing({ ...editing, [field.id]: field.amount })}
                        >
                          Correct
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <ChecksPanel checks={data.checks} />

          <div className="card">
            <div className="row">
              <button className="primary" disabled={blocking.length > 0} onClick={onValidate}>
                Validate the dataset
              </button>
              <span className="muted">
                {blocking.length > 0
                  ? `${blocking.length} blocking check${blocking.length > 1 ? 's' : ''} failing — BR-12 forbids validation`
                  : 'Freezes the data and makes the ratios computable (BR-01)'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
