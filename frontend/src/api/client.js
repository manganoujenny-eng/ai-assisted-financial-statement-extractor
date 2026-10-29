/* The only place in the frontend that knows the API exists.
 *
 * Every component calls a named function from here — never `fetch` directly.
 * Two reasons, and the second is the one that will save you time:
 *
 *  1. The endpoint list below is the contract of dossier §17.1, readable on
 *     one screen. When the backend changes, you change it here, once.
 *  2. Error handling happens in one place. A 409 carrying a list of failing
 *     checks is not a crash — it is the system refusing a validation, and the
 *     review screen has to display it. Handling that in twelve components is
 *     how a UI ends up showing "Error: [object Object]".
 */

const BASE = '/api'

/* --- interface language --------------------------------------------------- */
// Set by the LanguageProvider (src/i18n). Sent as Accept-Language with every
// request, so the backend writes the AI commentary in the screen's language.
let language = 'en'

export function setLanguage(code) {
  language = code
}

export class ApiError extends Error {
  constructor(status, payload) {
    super(payload?.detail || payload?.error || `HTTP ${status}`)
    this.status = status
    this.payload = payload
    // The failing checks travel with the error, so the review screen can
    // list them exactly as UC-06 exception E1 requires.
    this.failingChecks = payload?.failing_checks || []
  }
}

// Item 5 — a 401 anywhere means the session ended (expired, signed out
// elsewhere, account deactivated): App listens and shows the sign-in page.
function signalSignedOut(status, path) {
  if (status === 401 && !path.startsWith('/auth/login')) {
    window.dispatchEvent(new Event('auth-required'))
  }
}

async function request(path, options = {}) {
  // Same-origin through the Vite proxy, so the session cookie goes along.
  let response
  try {
    response = await fetch(`${BASE}${path}`, {
      credentials: 'same-origin',
      ...options,
      headers: { 'Accept-Language': language, ...(options.headers || {}) },
    })
  } catch (err) {
    // Stopped on purpose by longTask's time limit: let longTask explain it.
    if (err?.name === 'AbortError') throw err
    // The request never reached Flask: backend stopped, or the network dropped.
    throw new ApiError(0, { detail: unreachableText(0) })
  }
  const isJson = (response.headers.get('content-type') || '').includes('application/json')
  const payload = isJson ? await response.json() : null

  if (!response.ok) {
    signalSignedOut(response.status, path)
    // A non-JSON error is not Flask answering but the Vite proxy (backend
    // down or crashed mid-request): say that instead of a bare "HTTP 500".
    throw new ApiError(response.status, payload ?? { detail: unreachableText(response.status) })
  }
  return payload
}

function unreachableText(status) {
  const code = status ? ` (HTTP ${status})` : ''
  return language === 'fr'
    ? `Le serveur n'a pas répondu${code}. Vérifiez que le backend Flask tourne toujours et regardez sa console.`
    : `The server did not answer${code}. Check that the Flask backend is still running and look at its console.`
}

/* --- long operations ------------------------------------------------------ */
// An extraction (OCR of scanned pages) or an AI analysis can take minutes.
// While one runs, the page announces it on window as a "long-task" event;
// components/BusyOverlay.jsx shows a blocking progress screen, so nobody
// clicks the button again thinking nothing happened.
//
// Each has a time limit. Past it the page stops waiting, the request is
// cancelled, and a "long-task-timeout" event makes the overlay show an
// error with a Reload button instead of spinning for ever. The server may
// still finish the work: reloading shows the case's real state.
export const TIME_LIMITS_MS = {
  extraction: 10 * 60 * 1000, // 10 minutes: a large scanned package by OCR
  analysis: 4 * 60 * 1000, //    4 minutes: ratios + the AI commentary
  campaign: 15 * 60 * 1000, //  15 minutes: every corpus package extracted
}

let runningTasks = 0

function announce(kind) {
  window.dispatchEvent(new CustomEvent('long-task', { detail: { kind, running: runningTasks } }))
}

const TASK_NAMES = {
  en: { extraction: 'extraction', analysis: 'analysis', campaign: 'campaign' },
  fr: { extraction: "L'extraction", analysis: "L'analyse", campaign: 'La campagne' },
}

function timeoutText(kind, minutes) {
  if (language === 'fr') {
    return (
      `${TASK_NAMES.fr[kind] || "L'opération"} n'a pas répondu en ${minutes} minutes : la page a arrêté d'attendre. ` +
      'Le serveur a peut-être terminé entre-temps, ou s\'est arrêté. Rechargez la page pour voir l\'état réel du dossier ; ' +
      's\'il reste bloqué, regardez la console du backend Flask.'
    )
  }
  return (
    `The ${TASK_NAMES.en[kind] || 'operation'} did not answer within ${minutes} minutes, so the page stopped waiting. ` +
    'The server may have finished in the meantime, or it may have stopped. Reload the page to see the case\'s real state; ' +
    'if it stays stuck, look at the Flask backend console.'
  )
}

/* run(signal) starts the request; signal cancels it when time is up. */
function longTask(kind, run) {
  const limit = TIME_LIMITS_MS[kind] || 5 * 60 * 1000
  const controller = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    controller.abort()
  }, limit)

  runningTasks += 1
  announce(kind)

  return run(controller.signal)
    .catch((err) => {
      if (!timedOut) throw err
      const minutes = Math.round(limit / 60000)
      const message = timeoutText(kind, minutes)
      window.dispatchEvent(new CustomEvent('long-task-timeout', { detail: { kind, minutes, message } }))
      const error = new ApiError(408, { detail: message })
      error.timedOut = true
      throw error
    })
    .finally(() => {
      clearTimeout(timer)
      runningTasks -= 1
      announce(kind)
    })
}

function json(method, body) {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

/* --- cases --------------------------------------------------------------- */
export const listCases = () => request('/cases')
export const getCase = (id) => request(`/cases/${id}`)
export const createCase = (client, fiscalYear, analyst) =>
  request(
    '/cases',
    json('POST', { client, fiscal_year: Number(fiscalYear), analyst: analyst || null })
  )

/* --- who is signed in (item 5) ------------------------------------------ */
// Set by App after GET /auth/me or a login. Every page reads the signed-in
// person from here; the backend records actions under the session's user
// whatever the browser sends, so this is for display only.
let currentUser = null

export function setCurrentUser(user) {
  currentUser = user
}

export function getCurrentUser() {
  return currentUser
}

export const isSupervisor = () => currentUser?.role === 'SUPERVISOR'
export const isAdmin = () => ['ADMIN', 'SUPERADMIN'].includes(currentUser?.role)
export const isSuperAdmin = () => currentUser?.role === 'SUPERADMIN'

// Kept for the pages that already call it: the signed-in person's name.
export function getAnalystName() {
  return currentUser?.full_name || ''
}

export const getMe = () => request('/auth/me')
export const login = (username, password) =>
  request('/auth/login', json('POST', { username, password }))
export const logout = () => request('/auth/logout', { method: 'POST' })
export const changePassword = (currentPassword, newPassword) =>
  request(
    '/auth/password',
    json('POST', { current_password: currentPassword, new_password: newPassword })
  )

/* --- users (supervisor or administrator) ---------------------------------- */
export const listUsers = () => request('/users')
// A supervisor adds analysts only; the administrator chooses ANALYST or
// SUPERVISOR (user.role). Administrator accounts: backend/create_admin.py.
export const createUser = (user) =>
  request('/users', json('POST', { role: 'ANALYST', ...user }))
export const updateUser = (userId, changes) => request(`/users/${userId}`, json('PATCH', changes))
// Only an analyst who owns no case; one with cases is deactivated instead.
export const deleteUser = (userId) => request(`/users/${userId}`, { method: 'DELETE' })
// My account: change my own full name.
export const updateMe = (fullName) => request('/auth/me', json('PATCH', { full_name: fullName }))

/* --- supervisor dashboard ------------------------------------------------- */
export const getSupervisorOverview = () => request('/supervisor/overview')

// No argument: the signed-in user's own cases. A supervisor may pass a
// name, or '' for the cases nobody owns.
export const getMyCases = (analyst) =>
  request(
    analyst === undefined
      ? '/my-cases'
      : `/my-cases?analyst=${encodeURIComponent(analyst || '')}`
  )
// Bookkeeping, not a lifecycle move — never touches status (see
// CaseService.update on the backend). client/fiscalYear are each optional
// so a caller can send only the field that changed.
export function updateCase(id, { client, fiscalYear, author } = {}) {
  const body = {}
  if (client !== undefined) body.client = client
  if (fiscalYear !== undefined) body.fiscal_year = Number(fiscalYear)
  if (author !== undefined) body.author = author
  return request(`/cases/${id}`, json('PATCH', body))
}

// Signed in, the backend ignores "role" and uses the user's real role: an
// analyst deletes their own case while nothing in it is validated; a
// supervisor deletes ANALYSED cases only. "role" only matters with
// AUTH_REQUIRED=false.
export const deleteCase = (id, { role = 'analyst', author } = {}) =>
  request(`/cases/${id}`, json('DELETE', { role, author: author || role }))

/* --- documents ----------------------------------------------------------- */
// XMLHttpRequest rather than fetch, only because fetch cannot report upload
// progress — and on a 100 MB scanned package the analyst needs to see that
// something is happening. onProgress(percent) is optional. Errors become the
// same ApiError as everywhere else, so callers handle them identically.
export function uploadDocument(caseId, file, onProgress) {
  const form = new FormData()
  form.append('file', file)

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${BASE}/cases/${caseId}/documents`)
    xhr.withCredentials = true
    xhr.setRequestHeader('Accept-Language', language)
    // No Content-Type header here on purpose: the browser must set it
    // itself, because it has to append the multipart boundary.

    xhr.upload.onprogress = (event) => {
      if (onProgress && event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    }

    xhr.onload = () => {
      let payload = null
      try {
        payload = JSON.parse(xhr.responseText)
      } catch {
        payload = null
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(payload)
      } else {
        signalSignedOut(xhr.status, '/cases')
        reject(new ApiError(xhr.status, payload))
      }
    }

    xhr.onerror = () =>
      reject(new ApiError(0, { detail: `network error while uploading "${file.name}"` }))

    xhr.send(form)
  })
}

// The server's upload limit, so the page can refuse an oversized file
// before spending minutes uploading it.
export const getHealth = () => request('/health')

/*Giving the browser a URL to the PDF so its built-in PDF viewer can display it */
export const getDocumentFileUrl = (documentId) =>
    `${BASE}/documents/${documentId}/file`

// Same role/supervisor-retry contract as deleteCase, scoped to one document.
export const deleteDocument = (documentId, { role = 'analyst', author } = {}) =>
  request(`/documents/${documentId}`, json('DELETE', { role, author: author || role }))

/* To get Excel Preview */
export async function getExcelPreview(documentId) {
  const response = await fetch(`${BASE}/documents/${documentId}/preview`, {
    headers: { 'Accept-Language': language },
  })

  if (!response.ok) {
    const body = await response.json().catch(() => ({}))

    throw new Error(
      body.error || `Unable to load Excel preview (${response.status})`
    )
  }

  return response.json()
}

/* --- extraction and review ----------------------------------------------- */
// Case-level, not document-level: this reads every document currently
// attached to the case and merges their proposed fields into one run (see
// the backend's ExtractionRun docstring). Calling it again later — after a
// document was deleted and a corrected one attached, say — starts a
// brand-new run over whatever the case's documents are at that moment.
// engine "vision": "Read with AI" — the model reads the PDF page images.
export const runExtraction = (caseId, engine) =>
  longTask('extraction', (signal) =>
    request(`/cases/${caseId}/extractions`, {
      ...(engine ? json('POST', { engine }) : { method: 'POST' }),
      signal,
    })
  )
export const getExtractionFields = (extractionId) =>
  request(`/extractions/${extractionId}/fields`)
// Key in an item the extractor missed (recorded as KEYED, audited).
export const addField = (extractionId, item) =>
  request(`/extractions/${extractionId}/fields`, json('POST', item))
export const correctField = (fieldId, amount, author) =>
  request(`/fields/${fieldId}`, json('PATCH', { amount, author }))
// acknowledgeFailedChecks: without it, a failing blocking check comes back
// as a 409 listing the checks (the review screen then asks for
// confirmation). With it, the backend validates anyway and records the
// failing checks in the audit log.
export const validateExtraction = (
  extractionId,
  supervisor,
  { acknowledgeFailedChecks = false } = {}
) =>
  request(
    `/extractions/${extractionId}/validation`,
    json('POST', {
      supervisor,
      acknowledge_failed_checks: acknowledgeFailedChecks === true,
    })
  )
export const reopenCase = (caseId, reason) =>
  request(`/cases/${caseId}/reopen`, json('POST' , { reason }))

/* --- hand-over between analyst and supervisor (item 5) -------------------- */
// The analyst asks for validation of the case's newest extraction, and
// names the supervisor who will validate it (only they are notified).
export const submitCase = (caseId, note, supervisor) =>
  request(
    `/cases/${caseId}/submission`,
    json('POST', { note: note || '', supervisor: supervisor || null })
  )
// The active supervisors a case can be submitted to (any signed-in user).
export const listSupervisors = () => request('/supervisors')
// The supervisor sends the case back to its analyst; the message is required.
export const requestCorrection = (caseId, message) =>
  request(`/cases/${caseId}/correction-request`, json('POST', { message }))
// Submissions, correction requests, reopenings and validations, oldest first.
export const getCaseHistory = (caseId) => request(`/cases/${caseId}/history`)
// What is waiting for the signed-in user (derived from the cases' state).
export const getNotifications = () => request('/notifications')

/* --- analysis ------------------------------------------------------------ */
export const analyseDataset = (datasetId) =>
  longTask('analysis', (signal) =>
    request(`/datasets/${datasetId}/analysis`, { method: 'POST', signal })
  )
export const getCaseAnalysis = (caseId) => request(`/cases/${caseId}/analysis`)

/* --- AI commentary (item 4) — a draft until an analyst approves it ------- */
export const regenerateAiAnalysis = (caseId, author) =>
  longTask('analysis', (signal) =>
    request(`/cases/${caseId}/ai-analysis`, { ...json('POST', { author }), signal })
  )
export const approveAiAnalysis = (analysisId, sections, author) =>
  request(`/ai-analyses/${analysisId}/approval`, json('POST', { sections, author }))
/* --- evaluation ---------------------------------------------------------- */
export const runSensitivity = (groundTruth, items) =>
  request('/evaluations', json('POST', { ground_truth: groundTruth, items }))


/* --- administration (administrator only) ---------------------------------- */
// Everything the administrator used to do in pgAdmin or with scripts.
function queryString(params = {}) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') query.set(key, value)
  })
  return query.toString()
}

export const getAdminOverview = () => request('/admin/overview')

// filters: { q, author, action, entity, from, to, page, per_page }
export const getAudit = (filters) => request(`/admin/audit?${queryString(filters)}`)
// A link the browser downloads (same filters, every matching line).
export const auditCsvUrl = (filters) => {
  const { page, per_page: perPage, ...rest } = filters || {}
  return `${BASE}/admin/audit.csv?${queryString(rest)}`
}

// The evaluation corpus: one folder per package (RP001, RP002...).
export const getCorpus = () => request('/admin/corpus')
export const createCorpusPackage = (name) =>
  request('/admin/corpus/packages', json('POST', { name }))
export function uploadCorpusFiles(packageName, files) {
  const form = new FormData()
  Array.from(files).forEach((file) => form.append('files', file))
  return request(`/admin/corpus/${encodeURIComponent(packageName)}/files`, {
    method: 'POST',
    body: form,
  })
}
export const deleteCorpusFile = (packageName, fileName) =>
  request(
    `/admin/corpus/${encodeURIComponent(packageName)}/files/${encodeURIComponent(fileName)}`,
    { method: 'DELETE' }
  )
// A sensitivity test on one package's hand reading (no extraction).
export const runPackageSensitivity = (packageName, note) =>
  request(
    `/admin/corpus/${encodeURIComponent(packageName)}/sensitivity`,
    json('POST', { note: note || null })
  )
export const deleteCorpusPackage = (packageName) =>
  request(`/admin/corpus/${encodeURIComponent(packageName)}`, { method: 'DELETE' })

// Delete one stored campaign (administrator only; kept in the archive).
export const deleteCampaign = (id) =>
  request(`/admin/campaigns/${encodeURIComponent(id)}`, { method: 'DELETE' })

// The supervisors' discussion of a case (supervisors only).
export const getDiscussion = (caseId) => request(`/cases/${caseId}/discussion`)
export const postDiscussion = (caseId, message) =>
  request(`/cases/${caseId}/discussion`, json('POST', { message }))
export const editDiscussionMessage = (caseId, messageId, message) =>
  request(`/cases/${caseId}/discussion/${messageId}`, json('PATCH', { message }))
// scope "everyone" (the author: the others see "deleted by ...") or "me"
// (any message, hidden from my own view only).
export const deleteDiscussionMessage = (caseId, messageId, scope = 'everyone') =>
  request(`/cases/${caseId}/discussion/${messageId}?for=${scope}`, { method: 'DELETE' })
// "I am writing": the others see it for a few seconds.
export const discussionTyping = (caseId) =>
  request(`/cases/${caseId}/discussion/typing`, { method: 'POST' })

// The archive: everything deleted, kept for the administrator.
export const getArchive = (filters) => request(`/admin/archive?${queryString(filters)}`)
export const restoreArchived = (id) =>
  request(`/admin/archive/${encodeURIComponent(id)}/restore`, { method: 'POST' })
export const purgeArchived = (id) =>
  request(`/admin/archive/${encodeURIComponent(id)}`, { method: 'DELETE' })

// Stored campaigns (exercise 20) — newest first; kind CORPUS or SENSITIVITY.
export const listCampaigns = (kind) =>
  request(`/evaluations${kind ? `?kind=${encodeURIComponent(kind)}` : ''}`)
export const getCampaign = (id) => request(`/evaluations/${id}`)
export const runCorpusCampaign = (note) =>
  longTask('campaign', (signal) =>
    request('/evaluations/corpus', { ...json('POST', { note: note || null }), signal })
  )

// The database, read-only.
export const getTables = () => request('/admin/tables')
export const getTableRows = (name, { page = 1, q = '' } = {}) =>
  request(`/admin/tables/${encodeURIComponent(name)}?${queryString({ page, q, per_page: 50 })}`)