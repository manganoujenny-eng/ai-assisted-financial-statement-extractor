/*
 * Review workspace
 *
 * Handles:
 * - extraction context
 * - original source document
 * - extracted fields
 * - side-by-side review
 * - item inspection
 * - correction
 * - confidence / source information
 * - affected-data visibility
 * - correction history
 * - consistency checks
 * - submission (analyst) and validation / correction request (supervisor)
 *
 * Item 5 roles: the analyst who owns the case corrects, keys items and
 * submits it; the supervisor reads everything, then validates a submitted
 * case or sends it back with a correction request. The backend enforces
 * the same rules — hiding a button here is only for clarity.
 * Existing backend contracts are preserved.
 */

import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import * as api from '../api/client.js'
import ChecksPanel from '../components/ChecksPanel.jsx'
import StatusPill from '../components/StatusPill.jsx'
import ExcelSourceViewer from "../components/ExcelSourceViewer.jsx";
import DangerDialog from '../components/DangerDialog.jsx'
import AddItemForm from '../components/AddItemForm.jsx'
import { useCheckText } from '../components/ChecksPanel.jsx'
import { useI18n } from '../i18n/index.jsx'

function displayEngine(extraction, t) {
  if (extraction.engine === 'LLM') return 'Claude'
  if (extraction.engine === 'RULE_BASED') return t('review.ruleBased')
  return extraction.engine || t('ratioStatus.UNKNOWN')
}

// Native PDF / Scanned PDF / Excel — decided by the backend (type_label).
function documentKind(document, t) {
  if (!document) return t('review.sourceDocument')
  return document.type_label || document.doc_type || t('review.sourceDocument')
}

// The file name without the case-id prefix and extension (display_name).
function documentName(document) {
  return document?.display_name || document?.file_name || ''
}

function formatConfidence(value, t) {
  if (value === null || value === undefined || value === '') {
    return t('review.notAvailable')
  }

  const number = Number(value)

  if (Number.isNaN(number)) return String(value)

  return `${(number * 100).toFixed(1)}%`
}

// "helena  Ndongo" and "Helena Ndongo" are the same person.
function sameName(a, b) {
  const norm = (value) => (value || '').split(/\s+/).join(' ').trim().toLowerCase()
  return norm(a) !== '' && norm(a) === norm(b)
}

function formatDate(value, locale) {
  if (!value) return '—'

  try {
    return new Date(value).toLocaleString(locale)
  } catch {
    return value
  }
}

export default function ReviewPage() {
  const { caseId, extractionId } = useParams()
  const navigate = useNavigate()
  const { t, locale } = useI18n()
  const { checkLabel } = useCheckText()

  const [data, setData] = useState(null)
  const [caseData, setCaseData] = useState(null)

  const [error, setError] = useState(null)
  const [refusal, setRefusal] = useState(null)

  const [selectedFieldId, setSelectedFieldId] = useState(null)

  // Which of the run's several documents the left-hand panel is currently
  // showing. A run now spans every document the case had when it was
  // extracted (see the backend's ExtractionRun docstring), not just one —
  // so there is no longer a single "the" source document. null means
  // "whichever the selected field came from, or the first one" — the
  // effect below keeps that in sync; a manual click on a source pill
  // overrides it until the next field selection changes it again.
  const [activeDocumentId, setActiveDocumentId] = useState(null)

  const [editingId, setEditingId] = useState(null)
  const [editValue, setEditValue] = useState('')

  const [savingCorrection, setSavingCorrection] = useState(false)
  // Failing blocking checks waiting for the analyst's "validate anyway".
  // null = no confirmation dialog open.
  const [confirmChecks, setConfirmChecks] = useState(null)
  const [validating, setValidating] = useState(false)
  const [reopening, setReopening] = useState(false)

  // Submissions, correction requests and validations of this case.
  const [history, setHistory] = useState([])
  const [submitNote, setSubmitNote] = useState('')
  const [submitting, setSubmitting] = useState(false)
  // The supervisors a case can be submitted to, and the one chosen.
  const [supervisors, setSupervisors] = useState([])
  const [submitTo, setSubmitTo] = useState('')
  // The supervisor's "send back" dialog: null = closed.
  const [correctionRequest, setCorrectionRequest] = useState(null)

  async function reload() {
    try {
      const [extraction, currentCase, caseHistory] = await Promise.all([
        api.getExtractionFields(extractionId),
        api.getCase(caseId),
        api.getCaseHistory(caseId).catch(() => []),
      ])

      setData(extraction)
      setCaseData(currentCase)
      setHistory(caseHistory)
      setError(null)

      setSelectedFieldId((currentSelectedId) => {
        const stillExists = extraction.fields.some(
          (field) => field.id === currentSelectedId
        )

        if (stillExists) return currentSelectedId

        return extraction.fields[0]?.id ?? null
      })
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    reload()
  }, [caseId, extractionId])

  // An analyst assigns the submission to one supervisor: load the list.
  useEffect(() => {
    if (api.isSupervisor()) return
    api
      .listSupervisors()
      .then((list) => {
        setSupervisors(list)
        if (list.length === 1) setSubmitTo(list[0].full_name)
      })
      .catch(() => setSupervisors([]))
  }, [])

  // Every document this run was actually built from, in the case's own
  // attach order — a run can span several documents now, not just one.
  const runDocuments = useMemo(() => {
    if (!caseData?.documents || !data?.extraction?.document_ids) return []

    const ids = new Set(data.extraction.document_ids)
    return caseData.documents.filter((document) => ids.has(document.id))
  }, [caseData, data])

  const selectedField = useMemo(() => {
    return (
      data?.fields?.find((field) => field.id === selectedFieldId) ||
      data?.fields?.[0] ||
      null
    )
  }, [data, selectedFieldId])

    // How many extracted items each of the run's documents contributed.
  // A document can be part of the run and still yield nothing (a scan the
  // structurer could not read) — the run then looks like it only "has"
  // the other document. Counting per document makes that visible.
  const fieldCountByDocument = useMemo(() => {
    const counts = {}
    for (const field of data?.fields || []) {
      if (field.document_id) {
        counts[field.document_id] = (counts[field.document_id] || 0) + 1
      }
    }
    return counts
  }, [data])

  const emptyDocuments = useMemo(() => {
    return runDocuments.filter(
      (document) => !fieldCountByDocument[document.id]
    )
  }, [runDocuments, fieldCountByDocument])

  // Follow the selected field's own source document by default — "Inspect"
  // on a field from the income statement should show the income statement,
  // not whichever file happened to load first — but let a direct click on
  // a source pill below override that until the selection changes again.
  useEffect(() => {
    if (selectedField?.document_id) {
      setActiveDocumentId(selectedField.document_id)
    }
  }, [selectedField])

  const sourceDocument = useMemo(() => {
    if (runDocuments.length === 0) return null

    return (
      runDocuments.find((document) => document.id === activeDocumentId) ||
      runDocuments[0]
    )
  }, [runDocuments, activeDocumentId])

  const blockingChecks = useMemo(() => {
    return (
      data?.checks?.filter(
        (check) => !check.passed && check.severity === 'BLOCKING'
      ) || []
    )
  }, [data])

  const failedChecks = useMemo(() => {
    return data?.checks?.filter((check) => !check.passed) || []
  }, [data])

  // --- who may do what on this screen (item 5) -----------------------------
  const user = api.getCurrentUser()
  const authOff = user?.auth_required === false
  const supervisor = api.isSupervisor()
  const status = caseData?.status
  // The analyst who owns the case (or anyone, on a case nobody owns yet).
  const isOwner =
    authOff || !caseData?.analyst || sameName(caseData.analyst, user?.full_name)
  const canPrepare = (authOff || !supervisor) && isOwner
  // Correcting and keying items: only before submission.
  const canEdit = canPrepare && ['EXTRACTED', 'UNDER_REVIEW'].includes(status)
  const canSubmit =
    canEdit && data?.extraction?.status === 'EXTRACTED' && (data?.fields?.length || 0) > 0
  const canSupervise = supervisor

  const lastEvent = history.length > 0 ? history[history.length - 1] : null
  const pendingRequest =
    status === 'UNDER_REVIEW' && lastEvent?.action === 'CORRECTION_REQUESTED'
      ? lastEvent
      : null
  const lastSubmission =
    status === 'SUBMITTED'
      ? [...history].reverse().find((event) => event.action === 'SUBMITTED') || null
      : null


  // Only the supervisor a submission was assigned to may validate it or
  // send it back; once validated, only the supervisor who validated it may
  // send it back. Someone no longer active releases the case to everyone.
  // The backend enforces the same rules (403).
  // "supervisor_now" is that person's current name (it follows a rename on
  // My account); null when they are no longer an active supervisor.
  const assignedTo = lastSubmission?.supervisor_now || null
  const lastValidation = [...history].reverse().find((event) => event.action === 'VALIDATED')
  const validatedBy = lastValidation?.supervisor_now || null
  const isMine = (name) => authOff || !name || sameName(name, user?.full_name)
  const canValidate = canSupervise && status === 'SUBMITTED' && isMine(assignedTo)
  const canRequestCorrection =
    canSupervise &&
    ((status === 'SUBMITTED' && isMine(assignedTo)) ||
      (['VALIDATED', 'ANALYSED'].includes(status) && isMine(validatedBy)))
  const assignedToSomeoneElse = canSupervise && status === 'SUBMITTED' && !isMine(assignedTo)

  /*
   * Find checks which mention the selected item.
   *
   * items_used is already part of the backend check contract, so we use
   * that information rather than inventing another dependency API.
   */
  const affectedChecks = useMemo(() => {
    if (!selectedField || !data?.checks) return []

    return data.checks.filter((check) =>
      Array.isArray(check.items_used)
        ? check.items_used.includes(selectedField.item_code)
        : false
    )
  }, [selectedField, data])

  function startCorrection(field) {
    setSelectedFieldId(field.id)
    setEditingId(field.id)
    setEditValue(field.amount)
    setRefusal(null)
  }

  function cancelCorrection() {
    setEditingId(null)
    setEditValue('')
  }

  async function saveCorrection(field) {
    if (!editValue.trim()) return

    try {
      setSavingCorrection(true)

      const response = await api.correctField(
        field.id,
        editValue,
        api.getAnalystName() || 'analyst'
      )

      setData((current) => ({
        ...current,
        checks: response.checks,
        fields: current.fields.map((currentField) =>
          currentField.id === field.id
            ? response.field
            : currentField
        ),
      }))

      setSelectedFieldId(field.id)
      setEditingId(null)
      setEditValue('')
      setRefusal(null)
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingCorrection(false)
    }
  }

    // Required items the completeness check (CHK004) lists for year N but no
  // field provides — offered as one-click codes in the add-item form.
  const missingCodes = useMemo(() => {
    const completeness = data?.checks?.find((check) => check.code === 'CHK004')
    if (!completeness || completeness.passed) return []
    const present = new Set(
      (data?.fields || [])
        .filter((field) => field.year === 'N')
        .map((field) => field.item_code)
    )
    return (completeness.items_used || []).filter((code) => !present.has(code))
  }, [data])

  async function onAddItem(item) {
    const author = api.getAnalystName()
    if (!author) {
      throw new Error(t('review.needName'))
    }

    const response = await api.addField(extractionId, { ...item, author })

    setData((current) => ({
      ...current,
      checks: response.checks,
      fields: [...current.fields, response.field],
    }))
    setSelectedFieldId(response.field.id)
    setRefusal(null)
    setError(null)
  }
    // Failing checks no longer block validation. They open a confirmation
  // dialog first; "Validate anyway" sends acknowledgeFailedChecks, and the
  // backend records which checks were overridden in the audit log.
  async function onValidate(acknowledgeFailedChecks = false) {
    if (!acknowledgeFailedChecks && blockingChecks.length > 0) {
      setConfirmChecks(blockingChecks)
      return
    }

    try {
      setValidating(true)
      setRefusal(null)
      setError(null)

      const dataset = await api.validateExtraction(
        extractionId,
        api.getAnalystName() || 'supervisor',
        { acknowledgeFailedChecks }
      )

      setConfirmChecks(null)
      await api.analyseDataset(dataset.id)

      navigate(`/cases/${caseId}/dashboard`)
    } catch (err) {
      if (err.failingChecks?.length) {
        // The backend reran the checks and found failures this screen had
        // not shown yet (a correction landed in between) — ask, don't fail.
        setConfirmChecks(err.failingChecks)
      } else {
        setError(err.message)
      }
    } finally {
      setValidating(false)
    }
  }

  const needsReopen =
      caseData?.status === 'VALIDATED' || caseData?.status === 'ANALYSED'

  async function onSubmit() {
    if (supervisors.length > 0 && !submitTo) {
      setError(t('assign.required'))
      return
    }
    try {
      setSubmitting(true)
      setError(null)
      await api.submitCase(caseId, submitNote.trim(), submitTo)
      setSubmitNote('')
      await reload()
      window.dispatchEvent(new Event('notifications-changed'))
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  async function onSendCorrectionRequest() {
    const message = (correctionRequest?.message || '').trim()
    if (!message) {
      setCorrectionRequest({ ...correctionRequest, error: t('workflow.messageRequired') })
      return
    }
    try {
      setCorrectionRequest({ ...correctionRequest, working: true, error: null })
      await api.requestCorrection(caseId, message)
      setCorrectionRequest(null)
      await reload()
      window.dispatchEvent(new Event('notifications-changed'))
    } catch (err) {
      setCorrectionRequest({ ...correctionRequest, working: false, error: err.message })
    }
  }

    async function onReopen(){
      try {
          setReopening(true)
          setError(null)
          await api.reopenCase(
              caseId,
              'correction requested from the review screen'
          )
          await reload()
      } catch (err) {
          setError(err.message)
      } finally {
          setReopening(false)
      }
    }

  if (error && !data) {
    return <div className="banner fail">{error}</div>
  }

  if (!data) {
    return (
      <div className="card review-loading">
        <div className="review-loading-mark">{t('myCases.review')}</div>
        <p className="muted">{t('review.loading')}</p>
      </div>
    )
  }

  const clientName =
    caseData?.client ||
    t('review.case')

  const fiscalYear =
    caseData?.fiscal_year ||
    '—'

  const documentLabel = documentKind(sourceDocument, t)
  const engineLabel = displayEngine(data.extraction, t)

  return (
    <div className="review-page">

      {/* =========================================================
          HEADER
         ========================================================= */}

      <section className="review-header card">
        <div className="review-header-main">
          <div>
            <div className="review-kicker">
              {t('review.kicker')}
            </div>

            <h2 className="page-title">
              {t('review.title', { client: clientName, year: fiscalYear })}
            </h2>

            <p className="page-subtitle review-subtitle">
              {t('review.subtitle')}
            </p>
          </div>

          <div className="review-header-status">
            <StatusPill
              status={caseData?.status || data.extraction.status}
              kind="case"
            />
            {caseData?.analyst && (
              <span className="faint">
                {t('cases.analyst', { name: caseData.analyst })}
              </span>
            )}
          </div>
        </div>

        <div className="review-metadata">
          <div className="review-meta-item">
            <span className="review-meta-label">{t('review.extractedItems')}</span>
            <strong>{data.fields.length}</strong>
          </div>

          <div className="review-meta-item">
            <span className="review-meta-label">{t('review.structurer')}</span>
            <strong>{engineLabel}</strong>
          </div>

          {data.extraction.model && (
            <div className="review-meta-item">
              <span className="review-meta-label">{t('review.model')}</span>
              <strong>{data.extraction.model}</strong>
            </div>
          )}

          <div className="review-meta-item">
            <span className="review-meta-label">{t('review.source')}</span>
            <strong>{documentLabel}</strong>
          </div>

          <div className="review-meta-item">
            <span className="review-meta-label">{t('cases.documents')}</span>
            <strong>{runDocuments.length}</strong>
          </div>

          {sourceDocument?.file_name && (
            <div className="review-meta-item review-meta-file">
              <span className="review-meta-label">{t('review.file')}</span>
              <strong>{documentName(sourceDocument)}</strong>
            </div>
          )}
        </div>
      </section>

      {/* =========================================================
          ERROR / VALIDATION REFUSAL
         ========================================================= */}

      {error && (
        <div className="banner fail review-banner">
          {error}
        </div>
      )}

      {refusal && (
        <div className="banner fail review-banner">
          <strong>{t('review.refused')}</strong>

          <div className="review-refusal-list">
            {refusal.map((check) => (
              <div key={check.code}>
                <strong>{check.code}</strong>
                {' — '}
                {check.message}
              </div>
            ))}
          </div>
        </div>
      )}

      {pendingRequest && (
        <div className="banner warn review-banner">
          <strong>
            {t('workflow.requestedBy', {
              name: pendingRequest.author,
              date: formatDate(pendingRequest.at, locale),
            })}
          </strong>
          <div style={{ marginTop: 6, whiteSpace: 'pre-wrap' }}>{pendingRequest.message}</div>
          {canEdit && <div className="muted" style={{ marginTop: 6 }}>{t('workflow.requestedHint')}</div>}
        </div>
      )}

      {lastSubmission && (
        <div className="banner info review-banner">
          <strong>
            {t('workflow.submittedBy', {
              name: lastSubmission.author,
              date: formatDate(lastSubmission.at, locale),
            })}
          </strong>
          {lastSubmission.supervisor && (
            <div style={{ marginTop: 4 }}>
              {t('assign.assignedTo', { name: lastSubmission.supervisor })}
            </div>
          )}
          {lastSubmission.message && (
            <div style={{ marginTop: 6, whiteSpace: 'pre-wrap' }}>{lastSubmission.message}</div>
          )}
          <div className="muted" style={{ marginTop: 6 }}>
            {canSupervise ? t('workflow.submittedHintSupervisor') : t('workflow.submittedHintAnalyst')}
          </div>
        </div>
      )}

      {needsReopen && canSupervise && (
        <div className="banner warn review-banner">
          <strong>{t('review.alreadyValidated')}</strong>{' '}
          {canRequestCorrection ? (
            <>
              {t('workflow.sendBackValidatedHint')}{' '}
              <button
                className="primary"
                onClick={() => setCorrectionRequest({ message: '', working: false, error: null })}
              >
                {t('workflow.requestCorrection')}
              </button>
            </>
          ) : (
            t('assign.validatorOnly', { name: validatedBy })
          )}
        </div>
      )}

      {needsReopen && canPrepare && !canSupervise && (
            <div className="banner warn review-banner">
                <strong>{t('review.alreadyValidated')}</strong>{' '}
                {t('review.reopenHint')}{' '}
                <button
                    className="primary"
                    disabled={reopening}
                    onClick={onReopen}
                >
                    {reopening ? t('review.reopening') : t('review.reopen')}
                </button>
            </div>
      )}
      {emptyDocuments.length > 0 && (
        <div className="banner warn review-banner">
          <strong>
            {t('review.emptyDocuments', { count: emptyDocuments.length })}
          </strong>{' '}
          {emptyDocuments.map(documentName).join(', ')}.
          {' '}{t('review.emptyDocumentsHint')}
        </div>
      )}



      {/* =========================================================
          MAIN REVIEW WORKSPACE
         ========================================================= */}

      <section className="review-workspace">

        {/* ---------------------------------------------------------
            LEFT: SOURCE DOCUMENT
           --------------------------------------------------------- */}

        <div className="card review-source-card">
          <div className="review-section-heading">
            <div>
              <div className="review-section-label">
                {t('review.originalSource')}
              </div>

              <h2>{t('review.sourceDocument')}</h2>

              <p className="faint">
                {t('review.sourceHint')}
              </p>
            </div>

            <span className="pill neutral">
              {documentLabel}
            </span>
          </div>

          {/* A run spans every document it was built from now, not one —
              this switches which one the panel below is showing. Selecting
              a field (see the effect above) jumps here automatically; this
              row lets the analyst also browse the other source files on
              their own, e.g. to check the income statement while BK (from
              the balance sheet) is still selected. */}
          {runDocuments.length > 1 && (
            <div className="source-document-switcher">
              {runDocuments.map((document) => (
                <button
                  key={document.id}
                  className={
                    document.id === sourceDocument?.id
                      ? 'selected-action'
                      : ''
                  }
                  onClick={() => setActiveDocumentId(document.id)}
                >
                  {documentName(document)}
                  {' · '}
                  {t('review.items', { count: fieldCountByDocument[document.id] || 0 })}
                </button>
              ))}
            </div>
          )}

          <div className="source-file-bar">
            <div>
              <strong>
                {documentName(sourceDocument) || t('review.originalDocument')}
              </strong>

              {sourceDocument?.page_count && (
                <span className="faint">
                  {' · '}
                  {t('review.pages', { count: sourceDocument.page_count })}
                </span>
              )}
            </div>

            {sourceDocument?.id && (
              <a
                href={api.getDocumentFileUrl(sourceDocument.id)}
                target="_blank"
                rel="noreferrer"
                className="source-open-link"
              >
                {t('review.openSource')}
              </a>
            )}
          </div>

          {sourceDocument?.doc_type === 'PDF' ? (
                       <div className="source-viewer">
                             <iframe
                                 title={t('review.originalDocument')}
                                 src={api.getDocumentFileUrl(sourceDocument.id)}
                             />
                       </div>
          ) : sourceDocument?.doc_type === 'XLSX' ? (
                           <ExcelSourceViewer
                               documentId={sourceDocument.id}
                           />
          ) : (
                 <div className="source-non-pdf">
                     <div className="source-file-icon">
                              FILE
                     </div>

                     <h3>{t('review.sourceFile')}</h3>

                     <p className="muted">
                         {t('review.noViewer')}
                     </p>

                     {sourceDocument?.id && (
                       <a
                             className="button-like primary"
                             href={api.getDocumentFileUrl(sourceDocument.id)}
                             target="_blank"
                             rel="noreferrer"
                       >
                             {t('review.openOriginal')}
                       </a>
                     )}
                 </div>
          )}
        </div>

        {/* ---------------------------------------------------------
            RIGHT: EXTRACTED FIELDS
           --------------------------------------------------------- */}

        <div className="review-fields-column">

          <div className="card review-fields-card">
            <div className="review-section-heading">
              <div>
                <div className="review-section-label">
                  {t('review.extraction')}
                </div>

                <h2>{t('review.extractedFields')}</h2>

                <p className="faint">
                  {t('review.fieldsHint')}
                </p>
              </div>

              <span className="pill accent">
                {t('review.items', { count: data.fields.length })}
              </span>
            </div>

            <div className="fields-table-wrap fields-scroll">
              <table className="review-fields-table">
                <thead>
                  <tr>
                    <th>{t('addItem.code')}</th>
                    <th>{t('review.item')}</th>
                    <th>{t('review.amount')}</th>
                    <th>{t('review.source')}</th>
                    <th>{t('review.confidence')}</th>
                    <th>{t('users.status')}</th>
                    <th>{t('review.action')}</th>
                  </tr>
                </thead>

                <tbody>
                  {data.fields.map((field) => {
                    const isSelected =
                      selectedField?.id === field.id

                    return (
                      <tr
                        key={field.id}
                        className={[
                          field.was_corrected ? 'corrected' : '',
                          isSelected ? 'selected' : '',
                        ]
                          .filter(Boolean)
                          .join(' ')}
                      >
                        <td className="code">
                          {field.item_code}
                        </td>

                        <td className="label">
                          {field.label}

                          {field.was_corrected && (
                            <div className="was">
                              {t('review.proposed', { amount: field.proposed_amount })}
                            </div>
                          )}
                        </td>

                        <td className="num review-amount">
                          {field.amount_display}
                        </td>

                        <td className="review-source-cell">
                          {field.source_page
                            ? t('review.pageShort', { page: field.source_page })
                            : '—'}
                        </td>

                        <td className="review-confidence">
                          {formatConfidence(field.confidence, t)}
                        </td>

                        <td>
                          <StatusPill
                            status={field.status}
                            kind="field"
                          />
                        </td>

                        <td>
                          <div className="review-actions">
                            <button
                              className={
                                isSelected
                                  ? 'selected-action'
                                  : ''
                              }
                              onClick={() =>
                                setSelectedFieldId(field.id)
                              }
                            >
                              {t('review.inspect')}
                            </button>

                            {canEdit && (
                              <button
                                disabled={field.status === 'VALIDATED'}
                                onClick={() =>
                                  startCorrection(field)
                                }
                              >
                                {t('review.correct')}
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
          </div>

          {canEdit && (
            <AddItemForm
              documents={runDocuments}
              missingCodes={missingCodes}
              disabled={!canEdit}
              onAdd={onAddItem}
            />
          )}
          {/* -------------------------------------------------------
              SELECTED ITEM INSPECTOR
             ------------------------------------------------------- */}

          {selectedField && (
            <div className="card field-inspector">

              <div className="inspector-header">
                <div>
                  <div className="review-section-label">
                    {t('review.itemDetails')}
                  </div>

                  <h2>
                    {selectedField.item_code}{' '}
                    <span>·</span>{' '}
                    {selectedField.label}
                  </h2>
                </div>

                <StatusPill
                  status={selectedField.status}
                  kind="field"
                />
              </div>

              <div className="inspector-grid">

                <div className="inspector-value-box">
                  <span>{t('review.currentValue')}</span>

                  <strong className="inspector-number">
                    {selectedField.amount_display}
                  </strong>
                </div>

                <div className="inspector-value-box">
                  <span>{t('review.proposedValue')}</span>

                  <strong className="inspector-number">
                    {selectedField.proposed_amount || '—'}
                  </strong>
                </div>

                <div className="inspector-value-box">
                  <span>{t('addItem.year')}</span>

                  <strong>
                    {selectedField.year || 'N'}
                  </strong>
                </div>

                <div className="inspector-value-box">
                  <span>{t('review.sourcePage')}</span>

                  <strong>
                    {selectedField.source_page
                      ? t('review.pageLong', { page: selectedField.source_page })
                      : t('review.notAvailable')}
                  </strong>
                </div>

                <div className="inspector-value-box">
                  <span>{t('review.confidence')}</span>

                  <strong>
                    {formatConfidence(
                      selectedField.confidence, t
                    )}
                  </strong>
                </div>

                <div className="inspector-value-box">
                  <span>{t('review.correctionAuthor')}</span>

                  <strong>
                    {selectedField.corrected_by || '—'}
                  </strong>
                </div>
              </div>

              {/* Correction editor */}

              {editingId === selectedField.id ? (
                <div className="correction-editor">
                  <div>
                    <div className="review-section-label">
                      {t('review.correctValue')}
                    </div>

                    <p className="muted">
                      {t('review.correctHint')}
                    </p>
                  </div>

                  <div className="correction-form">
                    <input
                      className="num correction-input"
                      value={editValue}
                      autoFocus
                      onChange={(event) =>
                        setEditValue(event.target.value)
                      }
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') {
                          saveCorrection(selectedField)
                        }

                        if (event.key === 'Escape') {
                          cancelCorrection()
                        }
                      }}
                    />

                    <button
                      className="primary"
                      disabled={savingCorrection}
                      onClick={() =>
                        saveCorrection(selectedField)
                      }
                    >
                      {savingCorrection
                        ? t('common.saving')
                        : t('review.saveCorrection')}
                    </button>

                    <button
                      disabled={savingCorrection}
                      onClick={cancelCorrection}
                    >
                      {t('common.cancel')}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="inspector-actions">
                  {canEdit && (
                    <button
                      className="primary"
                      disabled={selectedField.status === 'VALIDATED'}
                      onClick={() =>
                        startCorrection(selectedField)
                      }
                    >
                      {t('review.correctThis')}
                    </button>
                  )}

                  {selectedField.source_page && (
                    <span className="muted">
                      {t('review.sourcePageIs', { page: selectedField.source_page })}
                    </span>
                  )}
                </div>
              )}

              {/* Correction history */}

              {selectedField.was_corrected && (
                <div className="correction-history">
                  <div className="review-section-label">
                    {t('review.history')}
                  </div>

                  <div className="history-row">
                    <div>
                      <span className="history-label">
                        {t('review.proposedByExtraction')}
                      </span>

                      <strong>
                        {selectedField.proposed_amount}
                      </strong>
                    </div>

                    <div className="history-arrow">
                      →
                    </div>

                    <div>
                      <span className="history-label">
                        {t('review.correctedValue')}
                      </span>

                      <strong>
                        {selectedField.amount_display}
                      </strong>
                    </div>

                    <div>
                      <span className="history-label">
                        {t('review.author')}
                      </span>

                      <strong>
                        {selectedField.corrected_by || '—'}
                      </strong>
                    </div>

                    <div>
                      <span className="history-label">
                        {t('review.time')}
                      </span>

                      <strong>
                        {formatDate(
                          selectedField.corrected_at, locale
                        )}
                      </strong>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* -------------------------------------------------------
              AFFECTED DATA
             ------------------------------------------------------- */}

          <div className="card affected-data-card">
            <div className="review-section-heading">
              <div>
                <div className="review-section-label">
                  {t('review.propagation')}
                </div>

                <h2>{t('review.affected')}</h2>

                <p className="faint">
                  {t('review.affectedHint')}
                </p>
              </div>

              <span className="pill neutral">
                {t('checks.count', { count: affectedChecks.length })}
              </span>
            </div>

            {affectedChecks.length === 0 ? (
              <div className="empty-inline">
                {t('review.noAffected', { code: selectedField?.item_code || '' })}
              </div>
            ) : (
              <div className="affected-list">
                {affectedChecks.map((check) => (
                  <div
                    key={check.code}
                    className="affected-row"
                  >
                    <span className="code">
                      {check.code}
                    </span>

                    <span className="label">
                      {checkLabel(check)}
                    </span>

                    <span
                      className={`pill ${
                        check.passed
                          ? 'ok'
                          : check.severity === 'BLOCKING'
                            ? 'fail'
                            : 'warn'
                      }`}
                    >
                      {check.passed
                        ? t('review.passed')
                        : check.severity === 'BLOCKING'
                          ? t('review.blocking')
                          : t('review.warning')}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* =========================================================
          CONSISTENCY CHECKS
         ========================================================= */}

      <section className="review-full-section">
        <ChecksPanel checks={data.checks} />
      </section>

      {/* =========================================================
          VALIDATION
         ========================================================= */}

      <section className="card validation-card">

        <div className="validation-status">

          <div>
            <div className="review-section-label">
              {t('review.datasetValidation')}
            </div>

            <h2>{t('review.freezeTitle')}</h2>

            <p className="muted">
              {t('review.freezeHint')}
            </p>
          </div>

          <div className="validation-summary">
            {blockingChecks.length > 0 ? (
              <>
                <span className="pill fail">
                  {t('review.nBlocking', { count: blockingChecks.length })}
                </span>

                <span className="muted">
                  {t('review.checksFailing', { count: blockingChecks.length })}
                </span>
              </>
            ) : failedChecks.length > 0 ? (
              <>
                <span className="pill warn">
                  {t('review.nWarnings', { count: failedChecks.length })}
                </span>

                <span className="muted">
                  {t('review.noBlocking')}
                </span>
              </>
            ) : (
              <>
                <span className="pill ok">
                  {t('review.allPassed')}
                </span>
              </>
            )}
          </div>
        </div>

        <div className="validation-action-row">

          <div className="validation-explanation">
            {!canSupervise ? (
              canSubmit ? (
                <>
                  <strong>{t('workflow.submitTitle')}</strong>{' '}
                  {t('workflow.submitHint')}
                  {supervisors.length > 0 && (
                    <label className="assign-field">
                      <span>{t('assign.label')}</span>
                      <select
                        value={submitTo}
                        disabled={submitting}
                        onChange={(event) => setSubmitTo(event.target.value)}
                        required
                      >
                        <option value="">{t('assign.choose')}</option>
                        {supervisors.map((item) => (
                          <option key={item.username} value={item.full_name}>
                            {item.full_name}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  <textarea
                    rows={2}
                    style={{ display: 'block', width: '100%', marginTop: 8 }}
                    placeholder={t('workflow.notePlaceholder')}
                    value={submitNote}
                    disabled={submitting}
                    onChange={(event) => setSubmitNote(event.target.value)}
                  />
                </>
              ) : status === 'SUBMITTED' ? (
                <>
                  <strong>{t('workflow.waitingTitle')}</strong>{' '}
                  {t('workflow.submittedHintAnalyst')}
                </>
              ) : (
                <>
                  <strong>{t('review.bySupervisor')}</strong>{' '}
                  {t('review.bySupervisorHint')}
                </>
              )
            ) : assignedToSomeoneElse ? (
              <>
                <strong>{t('assign.otherTitle', { name: assignedTo })}</strong>{' '}
                {t('assign.otherHint')}
              </>
            ) : !canValidate ? (
              <>
                <strong>{t('workflow.notSubmittedTitle')}</strong>{' '}
                {t('workflow.notSubmittedHint')}
              </>
            ) : blockingChecks.length > 0 ? (
              <>
                <strong>
                  {t('review.blockingFailing')}
                </strong>{' '}
                {t('review.blockingFailingHint')}
              </>
            ) : (
              <>
                <strong>
                  {t('review.ready')}
                </strong>{' '}
                {t('review.readyHint')}
              </>
            )}
          </div>

          {canSubmit && !canSupervise && (
            <button
              className="primary validation-button"
              disabled={submitting}
              onClick={onSubmit}
            >
                            {submitting
                ? t('workflow.submitting')
                : submitTo
                ? t('assign.submitTo', { name: submitTo })
                : t('workflow.submit')}
            </button>
          )}

          {canSupervise && (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {canRequestCorrection && (
                <button
                  disabled={validating}
                  onClick={() => setCorrectionRequest({ message: '', working: false, error: null })}
                >
                  {t('workflow.requestCorrection')}
                </button>
              )}
              <button
                className="primary validation-button"
                disabled={validating || !canValidate}
                onClick={() => onValidate(false)}
              >
                {validating
                  ? t('review.validating')
                  : blockingChecks.length > 0
                  ? t('review.validateFailing')
                  : t('review.validate')}
              </button>
            </div>
          )}
        </div>
      </section>

      {correctionRequest && (
        <DangerDialog
          title={t('workflow.requestTitle', { name: caseData?.analyst || t('sup.unassigned') })}
          confirmLabel={t('workflow.sendRequest')}
          workingLabel={t('workflow.sending')}
          working={correctionRequest.working}
          onConfirm={onSendCorrectionRequest}
          onCancel={() => setCorrectionRequest(null)}
        >
          <p>{t('workflow.requestBody')}</p>
          <textarea
            rows={4}
            autoFocus
            style={{ width: '100%' }}
            placeholder={t('workflow.requestPlaceholder')}
            value={correctionRequest.message}
            disabled={correctionRequest.working}
            onChange={(event) =>
              setCorrectionRequest({ ...correctionRequest, message: event.target.value, error: null })
            }
          />
          {correctionRequest.error && (
            <div className="banner fail" style={{ marginTop: 12 }}>
              {correctionRequest.error}
            </div>
          )}
          {needsReopen && <p className="muted">{t('workflow.requestValidatedNote')}</p>}
        </DangerDialog>
      )}

           {confirmChecks && (
        <DangerDialog
          title={t('review.confirmTitle', { count: confirmChecks.length })}
          confirmLabel={t('review.validateAnyway')}
          workingLabel={t('review.validating')}
          cancelLabel={t('review.keepCorrecting')}
          working={validating}
          onConfirm={() => onValidate(true)}
          onCancel={() => setConfirmChecks(null)}
        >
          <p>
            <strong>
              {t('review.confirmWarning')}
            </strong>{' '}
            {t('review.confirmBody')}
          </p>

          <div className="banner fail" style={{ margin: '12px 0' }}>
            {confirmChecks.map((check) => (
              <div key={check.code}>
                <strong>{check.code}</strong>
                {check.label ? ` ${checkLabel(check)}` : ''}
                {' — '}
                {check.message}
              </div>
            ))}
          </div>

          <p className="muted">
            {t('review.confirmAudit')}
          </p>
        </DangerDialog>
      )}
    </div>
  )
}