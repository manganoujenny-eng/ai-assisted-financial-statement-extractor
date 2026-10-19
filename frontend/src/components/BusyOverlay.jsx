/* A blocking "work in progress" screen for the long operations: extracting a
 * case's documents and writing the AI analysis. Both can take minutes, and
 * without this the analyst sees nothing happen and clicks again.
 *
 * It listens for the events api/client.js sends around those calls, so no
 * page has to manage it:
 *   - "long-task": something started or finished. While it runs the whole
 *     app is covered (nothing can be clicked twice), the time spent is shown
 *     against the time limit on a timeline, and closing the tab asks first.
 *   - "long-task-timeout": the time limit (api/client.js TIME_LIMITS_MS)
 *     passed. The page stopped waiting; the overlay turns into an error
 *     with "Reload the page" and "Close", instead of loading for ever.
 *
 * Its few texts live here, in both languages, so en.js / fr.js stay as they are.
 */

import { useEffect, useState } from 'react'
import { TIME_LIMITS_MS } from '../api/client.js'
import { useI18n } from '../i18n/index.jsx'
import { BrandSymbol } from './BrandMark.jsx'

const TEXTS = {
  en: {
    extraction: 'Extraction in progress',
    extractionHint:
      'The documents are being read and the accounting items extracted. ' +
      'A typed PDF or an Excel file takes a few seconds; scanned pages are read ' +
      'by OCR and can take several minutes for a large package.',
    analysis: 'Analysis in progress',
    analysisHint:
      'The ratios are computed and Claude is writing the AI commentary. This can take a minute or two.',
    keepOpen: 'Keep this page open. It will continue by itself when the work is done.',
    elapsed: 'Elapsed',
    limit: 'time limit',
    timeoutTitle: 'This is taking too long',
    reload: 'Reload the page',
    close: 'Close',
  },
  fr: {
    extraction: 'Extraction en cours',
    extractionHint:
      'Les documents sont lus et les postes comptables extraits. ' +
      'Un PDF texte ou un fichier Excel prend quelques secondes ; les pages scannées ' +
      'sont lues par OCR et peuvent prendre plusieurs minutes pour un gros dossier.',
    analysis: 'Analyse en cours',
    analysisHint:
      "Les ratios sont calculés et Claude rédige le commentaire IA. Cela peut prendre une ou deux minutes.",
    keepOpen: 'Gardez cette page ouverte. Elle continuera toute seule une fois le travail terminé.',
    elapsed: 'Temps écoulé',
    limit: 'limite',
    timeoutTitle: 'Cela prend trop de temps',
    reload: 'Recharger la page',
    close: 'Fermer',
  },
}

const clock = (ms) => {
  const seconds = Math.max(0, Math.floor(ms / 1000))
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}

export default function BusyOverlay() {
  const { lang } = useI18n()
  const [task, setTask] = useState(null) // { kind, startedAt } while something runs
  const [timeout, setTimeoutInfo] = useState(null) // { kind, message } after the limit
  const [now, setNow] = useState(Date.now())

  useEffect(() => {
    const onTask = (event) => {
      const { kind, running } = event.detail || {}
      setTask((current) => {
        if (running > 0) return current || { kind, startedAt: Date.now() }
        return null
      })
    }
    const onTimeout = (event) => setTimeoutInfo(event.detail || {})
    window.addEventListener('long-task', onTask)
    window.addEventListener('long-task-timeout', onTimeout)
    return () => {
      window.removeEventListener('long-task', onTask)
      window.removeEventListener('long-task-timeout', onTimeout)
    }
  }, [])

  // The clock, and a warning if the tab is closed mid-way.
  useEffect(() => {
    if (!task) return undefined
    setTimeoutInfo(null)
    setNow(Date.now())
    const timer = setInterval(() => setNow(Date.now()), 1000)
    const onLeave = (event) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', onLeave)
    return () => {
      clearInterval(timer)
      window.removeEventListener('beforeunload', onLeave)
    }
  }, [task])

  const text = TEXTS[lang] || TEXTS.en

  // --- the time limit passed: an error the user can act on ---------------
  if (timeout && !task) {
    return (
      <div className="busy-scrim" role="alertdialog" aria-modal="true" aria-labelledby="busy-timeout-title">
        <div className="busy-card busy-timeout">
          <div className="dialog-icon busy-timeout-icon" aria-hidden="true">⏱</div>
          <h2 id="busy-timeout-title">{text.timeoutTitle}</h2>
          <p className="muted">{timeout.message}</p>
          <div className="busy-actions">
            <button type="button" onClick={() => setTimeoutInfo(null)}>
              {text.close}
            </button>
            <button type="button" className="primary" onClick={() => window.location.reload()}>
              {text.reload}
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (!task) return null

  // --- still running: the timeline from 0 to the time limit ---------------
  const limit = TIME_LIMITS_MS[task.kind] || 5 * 60 * 1000
  const spent = now - task.startedAt
  const share = Math.min(100, (spent / limit) * 100)
  const isExtraction = task.kind === 'extraction'

  return (
    <div className="busy-scrim" role="alertdialog" aria-modal="true" aria-busy="true" aria-live="polite">
      <div className="busy-card">
        <div className="busy-mark">
          <span className="busy-ring" aria-hidden="true" />
          <BrandSymbol />
        </div>
        <h2>{isExtraction ? text.extraction : text.analysis}</h2>
        <p className="muted">{isExtraction ? text.extractionHint : text.analysisHint}</p>
        <div
          className={`busy-timeline${share > 80 ? ' late' : ''}`}
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={Math.round(limit / 1000)}
          aria-valuenow={Math.round(spent / 1000)}
          aria-label={text.elapsed}
        >
          <span style={{ width: `${share}%` }} />
        </div>
        <p className="busy-elapsed">
          {text.elapsed} <strong className="num">{clock(spent)}</strong>
          <span className="faint"> / {text.limit} {clock(limit)}</span>
        </p>
        <p className="faint busy-keep">{text.keepOpen}</p>
      </div>
    </div>
  )
}