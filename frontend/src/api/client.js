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
  } catch {
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
// An extraction or an AI analysis can take minutes (the model reads every
// page). While one runs, the page announces it on window as a "long-task"
// event; components/BusyOverlay.jsx shows a blocking progress screen, so
// nobody clicks the button again thinking nothing happened.
let runningTasks = 0

function longTask(kind, promise) {
  runningTasks += 1
  window.dispatchEvent(new CustomEvent('long-task', { detail: { kind, running: runningTasks } }))
  return promise.finally(() => {
    runningTasks -= 1
    window.dispatchEvent(new CustomEvent('long-task', { detail: { kind, running: runningTasks } }))
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

/* --- users (supervisor) --------------------------------------------------- */
export const listUsers = () => request('/users')
export const createUser = (user) => request('/users', json('POST', user))
export const updateUser = (userId, changes) => request(`/users/${userId}`, json('PATCH', changes))

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
export const runExtraction = (caseId) =>
  longTask('extraction', request(`/cases/${caseId}/extractions`, { method: 'POST' }))
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
// The analyst asks for validation of the case's newest extraction.
export const submitCase = (caseId, note) =>
  request(`/cases/${caseId}/submission`, json('POST', { note: note || '' }))
// The supervisor sends the case back to its analyst; the message is required.
export const requestCorrection = (caseId, message) =>
  request(`/cases/${caseId}/correction-request`, json('POST', { message }))
// Submissions, correction requests, reopenings and validations, oldest first.
export const getCaseHistory = (caseId) => request(`/cases/${caseId}/history`)
// What is waiting for the signed-in user (derived from the cases' state).
export const getNotifications = () => request('/notifications')

/* --- analysis ------------------------------------------------------------ */
export const analyseDataset = (datasetId) =>
  longTask('analysis', request(`/datasets/${datasetId}/analysis`, { method: 'POST' }))
export const getCaseAnalysis = (caseId) => request(`/cases/${caseId}/analysis`)

/* --- AI commentary (item 4) — a draft until an analyst approves it ------- */
export const regenerateAiAnalysis = (caseId, author) =>
  longTask('analysis', request(`/cases/${caseId}/ai-analysis`, json('POST', { author })))
export const approveAiAnalysis = (analysisId, sections, author) =>
  request(`/ai-analyses/${analysisId}/approval`, json('POST', { sections, author }))
/* --- evaluation ---------------------------------------------------------- */
export const runSensitivity = (groundTruth, items) =>
  request('/evaluations', json('POST', { ground_truth: groundTruth, items }))