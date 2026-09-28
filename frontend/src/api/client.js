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

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, options)
  const isJson = (response.headers.get('content-type') || '').includes('application/json')
  const payload = isJson ? await response.json() : null

  if (!response.ok) throw new ApiError(response.status, payload)
  return payload
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
export const createCase = (client, fiscalYear) =>
  request('/cases', json('POST', { client, fiscal_year: Number(fiscalYear) }))

/* --- documents ----------------------------------------------------------- */
export function uploadDocument(caseId, file) {
  const form = new FormData()
  form.append('file', file)
  // No Content-Type header here on purpose: the browser must set it itself,
  // because it has to append the multipart boundary. Setting it by hand is a
  // classic way to spend an hour on a 400.
  return request(`/cases/${caseId}/documents`, { method: 'POST', body: form })
}

/* --- extraction and review ----------------------------------------------- */
export const runExtraction = (documentId) =>
  request(`/documents/${documentId}/extractions`, { method: 'POST' })
export const getExtractionFields = (extractionId) =>
  request(`/extractions/${extractionId}/fields`)
export const correctField = (fieldId, amount, author) =>
  request(`/fields/${fieldId}`, json('PATCH', { amount, author }))
export const validateExtraction = (extractionId, supervisor) =>
  request(`/extractions/${extractionId}/validation`, json('POST', { supervisor }))

/* --- analysis ------------------------------------------------------------ */
export const analyseDataset = (datasetId) =>
  request(`/datasets/${datasetId}/analysis`, { method: 'POST' })
export const getCaseAnalysis = (caseId) => request(`/cases/${caseId}/analysis`)

/* --- evaluation ---------------------------------------------------------- */
export const runSensitivity = (groundTruth, items) =>
  request('/evaluations', json('POST', { ground_truth: groundTruth, items }))
