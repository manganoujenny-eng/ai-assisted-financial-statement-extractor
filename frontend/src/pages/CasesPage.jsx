/* Cases: create one, attach a document, run the extraction.
 *
 * This page is fully written and is your reference for the other two. The
 * shape it follows — `loading` / `error` / data, one async function per user
 * action, a reload after anything that changes the server — is the same in
 * every React page you will ever write. Copy it deliberately.
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import * as api from '../api/client.js'
import StatusPill from '../components/StatusPill.jsx'

export default function CasesPage() {
  const navigate = useNavigate()
  const [cases, setCases] = useState([])
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState({ client: '', fiscalYear: new Date().getFullYear() - 1 })

  async function reload() {
    try {
      setCases(await api.listCases())
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    reload()
  }, [])

  async function onCreate(event) {
    event.preventDefault()
    setBusy(true)
    try {
      await api.createCase(form.client, form.fiscalYear)
      setForm({ ...form, client: '' })
      await reload()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function onUpload(analysisCase, file) {
    if (!file) return
    setBusy(true)
    try {
      // Upload, then extract. Two calls rather than one, because they are two
      // different things: a document can be filed without being extracted,
      // and an extraction can be rerun on a document already filed (§15,
      // comparing two prompt versions on the same document).
      const document = await api.uploadDocument(analysisCase.id, file)
      const run = await api.runExtraction(document.id)
      navigate(`/cases/${analysisCase.id}/review/${run.id}`)
    } catch (err) {
      setError(err.message)
      await reload()
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <h2 className="page-title">Analysis cases</h2>
      <p className="page-subtitle">
        One case per client and fiscal year. Attach a reporting package to start.
      </p>

      {error && <div className="banner fail">{error}</div>}

      <div className="card">
        <h2>New case</h2>
        <form className="row" onSubmit={onCreate}>
          <input
            placeholder="Client"
            value={form.client}
            onChange={(e) => setForm({ ...form, client: e.target.value })}
            style={{ minWidth: 260 }}
            required
          />
          <input
            className="num"
            type="number"
            value={form.fiscalYear}
            onChange={(e) => setForm({ ...form, fiscalYear: e.target.value })}
            style={{ width: 110 }}
            required
          />
          <button className="primary" disabled={busy}>Create</button>
        </form>
      </div>

      <div className="card">
        <h2>Cases</h2>
        {cases.length === 0 && <p className="muted">No case yet.</p>}
        {cases.length > 0 && (
          <table>
            <thead>
              <tr>
                <th>Client</th>
                <th>Year</th>
                <th>Status</th>
                <th>Documents</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {cases.map((analysisCase) => (
                <tr key={analysisCase.id}>
                  <td className="code">{analysisCase.client}</td>
                  <td className="num">{analysisCase.fiscal_year}</td>
                  <td><StatusPill status={analysisCase.status} /></td>
                  <td className="label">
                    {analysisCase.documents.length === 0
                      ? '—'
                      : analysisCase.documents.map((d) => d.file_name).join(', ')}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <div className="row" style={{ justifyContent: 'flex-end' }}>
                      <label className="pill neutral" style={{ cursor: 'pointer' }}>
                        Upload &amp; extract
                        <input
                          type="file"
                          accept=".pdf,.xlsx,.xls"
                          hidden
                          disabled={busy}
                          onChange={(e) => onUpload(analysisCase, e.target.files[0])}
                        />
                      </label>
                      {['VALIDATED', 'ANALYSED'].includes(analysisCase.status) && (
                        <button onClick={() => navigate(`/cases/${analysisCase.id}/dashboard`)}>
                          Dashboard
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  )
}
