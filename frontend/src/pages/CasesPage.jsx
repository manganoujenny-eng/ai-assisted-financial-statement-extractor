/* Cases: create one, attach a document, run the extraction.
 *
 * The page keeps the original API workflow:
 *   createCase()
 *   uploadDocument()
 *   runExtraction()
 *
 * The interface now makes upload and extraction visually distinct.
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import * as api from '../api/client.js'
import StatusPill from '../components/StatusPill.jsx'
import DangerDialog from '../components/DangerDialog.jsx'
import { useI18n } from '../i18n/index.jsx'

// "helena  Ndongo" and "Helena Ndongo" are the same person.
function sameName(a, b) {
  const norm = (value) => (value || '').split(/\s+/).join(' ').trim().toLowerCase()
  return norm(a) !== '' && norm(a) === norm(b)
}

// Documents can be added, removed and extracted only before submission.
const PREPARABLE = ['CREATED', 'EXTRACTION_FAILED', 'EXTRACTED', 'UNDER_REVIEW']

export default function CasesPage() {
  const navigate = useNavigate()
  const { t } = useI18n()

  const [cases, setCases] = useState([])
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState({
    client: '',
    fiscalYear: new Date().getFullYear() - 1,
  })

  // Item 5 — the signed-in person. Only an analyst prepares a case:
  // create, edit, upload and delete documents, extract — and only on their
  // own cases. A supervisor opens the review (read-only), validates or
  // sends back, and deletes ANALYSED cases only. The backend refuses the
  // same things (403/409); hiding the buttons only keeps the page honest.
  // With sign-in switched off (AUTH_REQUIRED=false) everything is shown.
  const supervisor = api.isSupervisor()
  const authOff = api.getCurrentUser()?.auth_required === false
  const canCreate = !supervisor || authOff

  function canPrepare(analysisCase) {
    if (authOff) return true
    if (supervisor) return false
    return !analysisCase.analyst || sameName(analysisCase.analyst, api.getAnalystName())
  }

  function canDelete(analysisCase) {
    if (authOff) return true
    // A supervisor deletes only an ANALYSED case whose result they validated.
    if (supervisor) {
      return (
        analysisCase.status === 'ANALYSED' &&
        (!analysisCase.validator || sameName(analysisCase.validator, api.getAnalystName()))
      )
    }
    return canPrepare(analysisCase)
  }

  // Which case row is being renamed right now, if any — editing is done
  // in place in the table rather than in a separate dialog, since this
  // project has no modal component yet.
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({ client: '', fiscalYear: '' })

  // Upload limit announced by the backend (GET /api/health), so an
  // oversized file is refused here instead of after minutes of uploading.
  const [maxUploadMb, setMaxUploadMb] = useState(null)

  // { fileName, index, total, percent } while a file is uploading.
  const [uploadProgress, setUploadProgress] = useState(null)

  // The delete waiting for confirmation in the red dialog, or null.
  // { title, message, action, successMessage, working, error }
  const [pendingDelete, setPendingDelete] = useState(null)

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
    api
      .getHealth()
      .then((health) => setMaxUploadMb(health.max_upload_mb ?? null))
      .catch(() => setMaxUploadMb(null))
  }, [])

  // A confirmation ("Case … was deleted.", "… was updated.") disappears by
  // itself after a few seconds. Not while something is running: the
  // "Extracting…" notice must stay until the extraction finishes.
  useEffect(() => {
    if (!message || busy) return undefined
    const timer = setTimeout(() => setMessage(null), 5000)
    return () => clearTimeout(timer)
  }, [message, busy])

  async function onCreate(event) {
    event.preventDefault()

    setBusy(true)
    setError(null)

    try {
      // The backend records the signed-in analyst as the case's owner.
      await api.createCase(form.client, form.fiscalYear)

      setForm({
        ...form,
        client: '',
      })

      await reload()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function onRunExtraction(analysisCase) {
    /*
     * Case-level, not document-level: this reads every document currently
     * attached to the case and merges their fields into one run (see the
     * backend's ExtractionRun docstring) — so the analyst can upload the
     * balance sheet and the income statement as two separate files and
     * extract them together, and can run this again later (after deleting
     * a wrong document and attaching the right one, say) to pick up
     * whatever documents the case currently has.
     */
    setBusy(true)
    setError(null)
    setMessage(t('cases.extracting', { count: analysisCase.documents.length }))

    try {
      const run = await api.runExtraction(analysisCase.id)
      navigate(`/cases/${analysisCase.id}/review/${run.id}`)
    } catch (err) {
      setError(err.message)
      await reload()
    } finally {
      setBusy(false)
    }
  }

    async function onUpload(analysisCase, files) {
    const selected = Array.from(files || [])
    if (selected.length === 0) return

    if (maxUploadMb) {
      const tooBig = selected.filter(
        (file) => file.size > maxUploadMb * 1024 * 1024
      )
      if (tooBig.length > 0) {
        setError(
          t('cases.tooBig', {
            limit: maxUploadMb,
            files: tooBig
              .map((file) => `${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB)`)
              .join(', '),
          })
        )
        return
      }
    }

    setBusy(true)
    setError(null)

    try {
      /*
       * Upload and extraction are two separate, deliberate steps. This is
       * ALWAYS just the attach step, for the case's first document or its
       * fifth: an analyst uploads every document the case needs — a
       * balance sheet, then later an income statement — at their own
       * pace, and extraction only ever runs when "Extract documents" (or
       * "Re-extract documents") is pressed, over whatever the case's
       * documents are at that moment. Nothing here auto-navigates to
       * review any more: a single first upload used to, but that assumed
       * one document was always the whole reporting package, which is
       * exactly the assumption this change removes.
       */
      for (const [index, file] of selected.entries()) {
         setUploadProgress({
          fileName: file.name,
          index: index + 1,
          total: selected.length,
          percent: 0,
        })
        await api.uploadDocument(analysisCase.id, file, (percent) =>
          setUploadProgress((current) => current && { ...current, percent })
        )
      }

      await reload()
    } catch (err) {
      setError(err.message)
      await reload()
    } finally {
      setUploadProgress(null)
      setBusy(false)
    }
  }

  function onStartEdit(analysisCase) {
    setEditingId(analysisCase.id)
    setEditForm({ client: analysisCase.client, fiscalYear: analysisCase.fiscal_year })
  }

  function onCancelEdit() {
    setEditingId(null)
  }

    async function onSaveEdit(analysisCase) {
    setBusy(true)
    setError(null)
    setMessage(null)

    try {
      const updated = await api.updateCase(analysisCase.id, {
        client: editForm.client,
        fiscalYear: editForm.fiscalYear,
      })
      setEditingId(null)
      await reload()
      setMessage(t('cases.updated', { client: updated.client, year: updated.fiscal_year }))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

     /*
   * Shared by delete-case and delete-document. Opens the red confirmation
   * dialog. Who is deleting is the signed-in user (item 5): the backend
   * decides with their real role — free before anything is validated,
   * supervisor-only afterwards — so there is no name to type any more.
   */
  function askDelete({ title, message, action, successMessage }) {
    setError(null)
    setMessage(null)
    setPendingDelete({ title, message, action, successMessage, working: false, error: null })
  }

  async function confirmDelete() {
    const pending = pendingDelete
    if (!pending) return

    setPendingDelete({ ...pending, working: true, error: null })
    setBusy(true)

    try {
      const user = api.getCurrentUser()
      await pending.action(supervisor ? 'supervisor' : 'analyst', user?.full_name || 'analyst')
      setPendingDelete(null)
      await reload()
      setMessage(pending.successMessage)
    } catch (err) {
      setPendingDelete({
        ...pending,
        working: false,
        error:
          err.status === 409 && !supervisor
            ? t('cases.onlySupervisorDelete', { message: err.message })
            : err.message,
      })
    } finally {
      setBusy(false)
    }
  }

  function onDeleteCase(analysisCase) {
    const documentCount = analysisCase.documents?.length || 0
    const runCount = analysisCase.extractions?.length || 0
    askDelete({
      title: t('cases.deleteCaseTitle', { client: analysisCase.client, year: analysisCase.fiscal_year }),
      message: t('cases.deleteCaseMessage', { documents: documentCount, runs: runCount }),
      action: (role, author) => api.deleteCase(analysisCase.id, { role, author }),
      successMessage: t('cases.caseDeleted', {
        client: analysisCase.client,
        year: analysisCase.fiscal_year,
      }),
    })
  }

  function onDeleteDocument(analysisCase, document) {
    askDelete({
      title: t('cases.deleteDocTitle', { name: document.display_name || document.file_name }),
      message: t('cases.deleteDocMessage'),
      action: (role, author) => api.deleteDocument(document.id, { role, author }),
      successMessage: t('cases.docDeleted', { name: document.display_name || document.file_name }),
    })
  }

  return (
    <>
      <div className="cases-header">
        <div>
          <h2 className="page-title">{t('cases.title')}</h2>

          <p className="page-subtitle">
            {canCreate ? t('cases.subtitle') : t('cases.subtitleSupervisor')}
          </p>
        </div>

        <span className="pill neutral">
          {t('cases.count', { count: cases.length })}
        </span>
      </div>

      {error && (
        <div className="banner fail">
          {error}
        </div>
      )}

      {message && (
        <div className="banner info">
          {message}
        </div>
      )}

      {uploadProgress && (
        <div className="banner info">
          <strong>
            {t('cases.uploading', {
              index: uploadProgress.index,
              total: uploadProgress.total,
              name: uploadProgress.fileName,
              percent: uploadProgress.percent,
            })}
          </strong>
          <div
            style={{
              height: 8,
              marginTop: 8,
              borderRadius: 4,
              background: 'rgba(0, 0, 0, 0.12)',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${uploadProgress.percent}%`,
                height: '100%',
                background: 'currentColor',
                transition: 'width 0.2s',
              }}
            />
          </div>
          {uploadProgress.percent === 100 && (
            <div className="muted" style={{ marginTop: 4 }}>
              {t('cases.uploadComplete')}
            </div>
          )}
        </div>
      )}

      {pendingDelete && (
        <DangerDialog
          title={pendingDelete.title}
          confirmLabel={t('common.delete')}
          workingLabel={t('common.deleting')}
          working={pendingDelete.working}
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
        >
          <p>
            <strong>{pendingDelete.message}</strong>
          </p>


          {pendingDelete.error && (
            <div className="banner fail" style={{ marginTop: 12 }}>
              {pendingDelete.error}
            </div>
          )}

          <p className="muted">{t('cases.deleteAudited')}</p>
        </DangerDialog>
      )}

      {/* -----------------------------------------------------------
          CREATE CASE — analysts only (item 5 change)
      ------------------------------------------------------------ */}
      {canCreate ? (
        <div className="card create-case-card">
          <div className="section-heading">
            <div>
              <h2>{t('cases.newTitle')}</h2>
              <p className="faint">
                {t('cases.newHint')}
              </p>
            </div>
          </div>

          <form className="case-form" onSubmit={onCreate}>
            <label>
              <span>{t('cases.client')}</span>

              <input
                placeholder={t('cases.clientPlaceholder')}
                value={form.client}
                onChange={(e) =>
                  setForm({
                    ...form,
                    client: e.target.value,
                  })
                }
                required
              />
            </label>

            <label>
              <span>{t('cases.fiscalYear')}</span>

              <input
                className="num"
                type="number"
                value={form.fiscalYear}
                onChange={(e) =>
                  setForm({
                    ...form,
                    fiscalYear: e.target.value,
                  })
                }
                required
              />
            </label>

            <button
              className="primary"
              disabled={busy}
              type="submit"
            >
              {t('cases.create')}
            </button>
          </form>
        </div>
      ) : (
        <div className="banner info">
          {t('cases.supervisorCannotCreate')}
        </div>
      )}

      {/* -----------------------------------------------------------
          EXISTING CASES
      ------------------------------------------------------------ */}
      <div className="card">
        <div className="section-heading">
          <div>
            <h2>{t('cases.existing')}</h2>

            <p className="faint">
              {canCreate ? t('cases.existingHint') : t('cases.existingHintSupervisor')}
            </p>
          </div>
        </div>

        {cases.length === 0 ? (
          <div className="empty-state">
            <strong>{t('cases.empty')}</strong>

            <span>
              {canCreate ? t('cases.emptyHint') : t('cases.emptyHintSupervisor')}
            </span>
          </div>
        ) : (
          <div className="cases-table-wrap">
            <table className="cases-table">
              <thead>
                <tr>
                  <th>{t('cases.client')}</th>
                  <th>{t('addItem.year')}</th>
                  <th>{t('users.status')}</th>
                  <th>{t('cases.documents')}</th>
                  <th>{t('cases.actions')}</th>
                </tr>
              </thead>

              <tbody>
                {cases.map((analysisCase) => {
                  const latestExtraction =
                      analysisCase.extractions?.length > 0
                          ? analysisCase.extractions[analysisCase.extractions.length - 1]
                          : null
                  const mine = canPrepare(analysisCase)
                  const preparable = mine && PREPARABLE.includes(analysisCase.status)

                  return (
                      <tr key={analysisCase.id}>

                        {/* CLIENT */}
                        <td>
                          {editingId === analysisCase.id ? (
                              <input
                                  value={editForm.client}
                                  disabled={busy}
                                  onChange={(e) =>
                                      setEditForm({ ...editForm, client: e.target.value })
                                  }
                              />
                          ) : (
                              <div className="case-client">
                                      <span className="code">
                                         {analysisCase.client}
                                      </span>

                                <span className="faint">
                                           {t('cases.caseId', { id: analysisCase.id })}
                                      </span>
                                <span className="faint">
                                  {t('cases.analyst', { name: analysisCase.analyst || t('sup.unassigned') })}
                                </span>

                              </div>
                          )}
                        </td>

                        {/* YEAR */}
                        <td className="num">
                          {editingId === analysisCase.id ? (
                              <input
                                  className="num"
                                  type="number"
                                  value={editForm.fiscalYear}
                                  disabled={busy}
                                  onChange={(e) =>
                                      setEditForm({ ...editForm, fiscalYear: e.target.value })
                                  }
                              />
                          ) : (
                              analysisCase.fiscal_year
                          )}
                        </td>

                        {/* STATUS */}
                        <td>
                          <StatusPill
                              status={analysisCase.status}
                          />
                          {analysisCase.assigned_supervisor && (
                            <div className="faint" style={{ marginTop: 4 }}>
                              {t('assign.to', { name: analysisCase.assigned_supervisor })}
                            </div>
                          )}
                        </td>

                        {/* DOCUMENTS */}
                        <td>
                          {analysisCase.documents.length === 0 ? (
                              <span className="faint">
                                            {t('cases.noDocument')}
                                   </span>
                          ) : (
                              <div className="document-list">
                                {analysisCase.documents.map((document) => (
                                    <div
                                        className="document-row"
                                        key={document.id}
                                    >
                                              <span className="document-name" title={document.display_name}>
                                                 {document.display_name || document.file_name}
                                              </span>

                                      <span className="pill neutral">
                                        {document.type_label}
                                              </span>

                                      {preparable && (
                                        <button
                                            disabled={busy}
                                            title={t('cases.deleteDocument')}
                                            onClick={() =>
                                                onDeleteDocument(analysisCase, document)
                                            }
                                        >
                                          &times;
                                        </button>
                                      )}
                                    </div>
                                ))}
                              </div>
                          )}

                          {/* Always available: uploading is purely the
                              attach step now, for the case's first document
                              or its fifth, whether or not it has been
                              extracted yet. Extraction itself only ever
                              happens when "Extract documents" /
                              "Re-extract documents" below is pressed,
                              deliberately, over every document the case has
                              at that moment. */}
                          {preparable && (
                          <label
                              className="button-like"
                              title={t('cases.addDocumentHint')}
                          >
                            {t('cases.addDocument')}

                            <input
                                type="file"
                                accept=".pdf,.xlsx,.xls"
                                multiple
                                hidden
                                disabled={busy}
                                onChange={(e) => {
                                      onUpload(analysisCase, e.target.files)
                                      e.target.value = ''
                                }}
                            />
                          </label>
                          )}
                        </td>

                        {/* ACTIONS */}
                        <td>
                          <div className="case-actions">

                            {/* NO DOCUMENT YET -> nothing to extract */}
                            {analysisCase.documents.length === 0 && (
                                <span className="faint">
                                  {mine ? t('cases.uploadFirst') : t('cases.nothingYet')}
                                </span>
                            )}

                            {/* AT LEAST ONE DOCUMENT, NEVER EXTRACTED ->
                                EXTRACT (reads every document currently
                                attached and merges their fields into one
                                run — see onRunExtraction) */}
                            {preparable && analysisCase.documents.length > 0 && !latestExtraction && (
                                <button
                                    className="primary"
                                    disabled={busy}
                                    onClick={() => onRunExtraction(analysisCase)}
                                >
                                  {t('cases.extract')}
                                </button>
                            )}

                            {/* LATEST EXTRACTION FAILED -> RETRY (over the
                                case's current documents — the parser may
                                have been fixed since, or the bad document
                                may have been swapped out already) */}
                            {preparable && latestExtraction?.status === 'EXTRACTION_FAILED' && (
                                <button
                                  className="primary"
                                  disabled={busy}
                                  title={
                                    latestExtraction.failure_reason ||
                                    t('status.case.EXTRACTION_FAILED')
                                  }
                                  onClick={() => onRunExtraction(analysisCase)}
                                >
                                   {t('cases.retry')}
                                </button>
                            )}

                            {/* EXISTING, SUCCESSFUL EXTRACTION -> OPEN
                                REVIEW, plus an explicit RE-EXTRACT for
                                after a document was deleted and replaced */}
                            {latestExtraction && latestExtraction.status !== 'EXTRACTION_FAILED' && (
                                <>
                                  <button
                                    className="primary"
                                    onClick={() =>
                                       navigate(
                                         `/cases/${analysisCase.id}/review/${latestExtraction.id}`
                                       )
                                    }
                                  >
                                     {supervisor &&
                                     analysisCase.status === 'SUBMITTED' &&
                                     (!analysisCase.assigned_supervisor ||
                                       sameName(analysisCase.assigned_supervisor, api.getAnalystName()))
                                       ? t('workflow.reviewAndValidate')
                                       : t('cases.openReview')}
                                  </button>

                                  {preparable && (
                                    <button
                                        disabled={busy}
                                        title={t('cases.reextractHint')}
                                        onClick={() => onRunExtraction(analysisCase)}
                                    >
                                      {t('cases.reextract')}
                                    </button>
                                  )}
                                </>
                            )}

                            {/* VALIDATED / ANALYSED -> DASHBOARD */}
                            {['VALIDATED', 'ANALYSED'].includes(
                                analysisCase.status
                            ) && (
                                <button
                                    onClick={() =>
                                        navigate(
                                            `/cases/${analysisCase.id}/dashboard`
                                        )
                                    }
                                >
                                  {t('myCases.dashboard')}
                                </button>
                            )}

                            {/* RENAME / CORRECT FISCAL YEAR — bookkeeping,
                                allowed at any point in the case's life */}
                            {editingId === analysisCase.id ? (
                                <>
                                  <button
                                      className="primary"
                                      disabled={busy}
                                      onClick={() => onSaveEdit(analysisCase)}
                                  >
                                    {t('common.save')}
                                  </button>
                                  <button disabled={busy} onClick={onCancelEdit}>
                                    {t('common.cancel')}
                                  </button>
                                </>
                            ) : mine && (
                                <button
                                    disabled={busy}
                                    onClick={() => onStartEdit(analysisCase)}
                                >
                                  {t('common.edit')}
                                </button>
                            )}

                            {/* DELETE CASE — free while nothing in it has
                                been validated; refused with 409 otherwise
                                until confirmed as a supervisor (see
                                deleteWithSupervisorRetry) */}
                            {canDelete(analysisCase) && (
                              <button
                                  disabled={busy}
                                  onClick={() => onDeleteCase(analysisCase)}
                              >
                                {t('common.delete')}
                              </button>
                            )}

                          </div>
                        </td>
                      </tr>
                  )
                })}

              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}