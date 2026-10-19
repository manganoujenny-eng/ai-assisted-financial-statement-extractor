/* A blocking "work in progress" screen for the long operations: extracting a
 * case's documents and writing the AI analysis. Both can take minutes, and
 * without this the analyst sees nothing happen and clicks again.
 *
 * It listens for the "long-task" events api/client.js sends around those
 * calls, so no page has to manage it. While it is shown:
 *   - the whole app is covered, so nothing can be clicked twice;
 *   - a timer shows the time spent, so "still working" is visible;
 *   - closing or reloading the tab asks for confirmation first.
 *
 * Its few texts live here, in both languages, so en.js / fr.js stay as they are.
 */

import { useEffect, useState } from 'react'
import { useI18n } from '../i18n/index.jsx'
import { BrandSymbol } from './BrandMark.jsx'

const TEXTS = {
  en: {
    extraction: 'Extraction in progress',
    extractionHint:
      'The documents are being read and the accounting items extracted. ' +
      'With Claude this usually takes 1 to 5 minutes, longer for scanned files.',
    analysis: 'Analysis in progress',
    analysisHint: 'The ratios are computed and the AI commentary is being written. This can take a minute or two.',
    keepOpen: 'Keep this page open. It will continue by itself when the work is done.',
    elapsed: 'Elapsed',
  },
  fr: {
    extraction: 'Extraction en cours',
    extractionHint:
      'Les documents sont lus et les postes comptables extraits. ' +
      'Avec Claude cela prend en général 1 à 5 minutes, plus pour les fichiers scannés.',
    analysis: 'Analyse en cours',
    analysisHint: "Les ratios sont calculés et le commentaire IA est rédigé. Cela peut prendre une ou deux minutes.",
    keepOpen: 'Gardez cette page ouverte. Elle continuera toute seule une fois le travail terminé.',
    elapsed: 'Temps écoulé',
  },
}

export default function BusyOverlay() {
  const { lang } = useI18n()
  const [task, setTask] = useState(null) // { kind, startedAt } while something runs
  const [now, setNow] = useState(Date.now())

  useEffect(() => {
    const onTask = (event) => {
      const { kind, running } = event.detail || {}
      setTask((current) => {
        if (running > 0) return current || { kind, startedAt: Date.now() }
        return null
      })
    }
    window.addEventListener('long-task', onTask)
    return () => window.removeEventListener('long-task', onTask)
  }, [])

  // The timer, and a warning if the tab is closed mid-way.
  useEffect(() => {
    if (!task) return undefined
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

  if (!task) return null

  const text = TEXTS[lang] || TEXTS.en
  const seconds = Math.max(0, Math.floor((now - task.startedAt) / 1000))
  const elapsed = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
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
        <div className="busy-bar" aria-hidden="true"><span /></div>
        <p className="busy-elapsed">
          {text.elapsed} <strong className="num">{elapsed}</strong>
        </p>
        <p className="faint busy-keep">{text.keepOpen}</p>
      </div>
    </div>
  )
}