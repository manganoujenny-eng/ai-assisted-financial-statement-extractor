/* AI commentary on the validated analysis .
 *
 * The figures, checks, ratios and their template sentences above this panel
 * are rule-based. This panel holds what the language model wrote ABOUT
 * them — and BR-13 decides how it is shown:
 *
 *   DRAFT     editable, clearly marked as not part of the analysis yet;
 *             "Approve" records the analyst's name and the edited text.
 *   APPROVED  read-only, with who approved it and whether it was edited.
 *   FAILED    the reason (no API key, network, budget…) and "Try again".
 *
 * The model's original text is kept by the backend whatever the analyst
 * changes, so the edits stay measurable.
 *
 * Since prompt v3 the model reads the values as an advisor would for the
 * company's management: a diagnosis of what is going wrong and why, and
 * concrete recommendations. A commentary written before v3 has neither;
 * those two blocks are then simply not shown.
 */

import { useEffect, useState } from 'react'
import * as api from '../api/client.js'
import { LANGUAGES, labelByCode, useI18n } from '../i18n/index.jsx'

function toForm(sections, ratios) {
  const s = sections || {}
  const byCode = s.ratios || {}
  return {
    overview: s.overview || '',
    diagnosis: s.diagnosis || '',
    ratios: Object.fromEntries(ratios.map((ratio) => [ratio.code, byCode[ratio.code] || ''])),
    checks: s.checks || '',
    comparison: s.comparison || '',
    recommendations: (s.recommendations || []).join('\n'),
    attention: (s.attention || []).join('\n'),
  }
}

const lines = (text) =>
  text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)

function fromForm(form) {
  return {
    overview: form.overview,
    diagnosis: form.diagnosis,
    ratios: Object.fromEntries(
      Object.entries(form.ratios).filter(([, text]) => text.trim())
    ),
    checks: form.checks,
    comparison: form.comparison,
    recommendations: lines(form.recommendations),
    attention: lines(form.attention),
  }
}

function Block({ title, children }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div className="faint" style={{ fontWeight: 600, marginBottom: 4 }}>
        {title}
      </div>
      {children}
    </div>
  )
}

function Text({ value }) {
  return <p style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{value || '—'}</p>
}

function Points({ items }) {
  return (
    <ul style={{ margin: 0 }}>
      {items.map((point, index) => (
        <li key={index}>{point}</li>
      ))}
    </ul>
  )
}

function Area({ value, onChange, rows = 3, disabled }) {
  return (
    <textarea
      value={value}
      rows={rows}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
      style={{ width: '100%', boxSizing: 'border-box', font: 'inherit' }}
    />
  )
}

// canAct: the signed-in user is the case's analyst — the only one who may
// draft the commentary again and approve it (the backend refuses anyone
// else with 403). Everyone else reads it, and is told who decides.
export default function AiCommentaryPanel({ caseId, analysis, ratios, onChange, canAct = true, owner }) {
  const [form, setForm] = useState(() => toForm(analysis?.sections, ratios))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const { t, lang, formatDateTime } = useI18n()

  useEffect(() => {
    setForm(toForm(analysis?.sections, ratios))
  }, [analysis?.id, analysis?.status])

  const ratioName = (code) =>
    labelByCode(t, 'ratio', code, ratios.find((ratio) => ratio.code === code)?.name || code)

  // The commentary is written in the language of the screen that asked for
  // it ("language" from the backend). If the analyst has switched language
  // since, a redraft writes it again in the current one.
  const languageName = (code) => LANGUAGES.find((item) => item.code === code)?.label || code
  const otherLanguage = analysis?.language && analysis.language !== lang

  async function regenerate() {
    try {
      setBusy(true)
      setError(null)
      onChange(await api.regenerateAiAnalysis(caseId, api.getAnalystName() || 'analyst'))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function approve() {
    const author = api.getAnalystName()
    if (!author) {
      setError(t('ai.needName'))
      return
    }
    try {
      setBusy(true)
      setError(null)
      onChange(await api.approveAiAnalysis(analysis.id, fromForm(form), author))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const meta = analysis && (
    <p className="faint" style={{ marginTop: 0 }}>
      {t('ai.model', { model: analysis.model || '—' })}
      {analysis.prompt_version ? ` · ${t('ai.prompt', { version: analysis.prompt_version })}` : ''}
      {analysis.language ? ` · ${languageName(analysis.language)}` : ''}
      {analysis.cost_usd ? ` · ${t('ai.cost', { cost: analysis.cost_usd })}` : ''}
      {analysis.generated_at
        ? ` · ${t('ai.drafted', { when: formatDateTime(analysis.generated_at) })}`
        : ''}
    </p>
  )

  return (
    <section className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <p className="faint" style={{ margin: 0 }}>{t('ai.kicker')}</p>
          <h2 style={{ marginTop: 4 }}>{t('ai.title')}</h2>
        </div>
        {analysis && (
          <span
            className={`pill ${
              analysis.status === 'APPROVED' ? 'ok' : analysis.status === 'DRAFT' ? 'warn' : 'fail'
            }`}
            style={{ alignSelf: 'flex-start' }}
          >
            {t(`ai.status.${analysis.status}`)}
          </span>
        )}
      </div>

      {error && <div className="banner fail">{error}</div>}

      {!canAct && analysis?.status !== 'APPROVED' && (
        <p className="faint">{t('ai.onlyOwner', { name: owner || t('sup.unassigned') })}</p>
      )}

      {!analysis && (
        <>
          <p className="muted">{t('ai.none')}</p>
          {canAct && (
            <button type="button" className="primary" disabled={busy} onClick={regenerate}>
              {busy ? t('ai.drafting') : t('ai.draft')}
            </button>
          )}
        </>
      )}

      {analysis?.status === 'FAILED' && (
        <>
          <div className="banner warn">
            <strong>{t('ai.failedTitle')}</strong> {analysis.failure_reason}
            <br />
            {t('ai.failedBody')}
          </div>
          {canAct && (
            <button type="button" disabled={busy} onClick={regenerate}>
              {busy ? t('ai.drafting') : t('ai.tryAgain')}
            </button>
          )}
        </>
      )}

      {analysis?.status === 'DRAFT' && (
        <>
          <div className="banner warn">
            <strong>{t('ai.draftTitle')}</strong>{' '}
            {t('ai.draftBody')}
          </div>
          {otherLanguage && canAct && (
            <div className="banner info">
              {t('ai.otherLanguage', {
                written: languageName(analysis.language),
                current: languageName(lang),
              })}{' '}
              <button type="button" disabled={busy} onClick={regenerate}>
                {t('ai.redraftIn', { language: languageName(lang) })}
              </button>
            </div>
          )}
          {meta}

          <Block title={t('ai.overview')}>
            <Area value={form.overview} rows={4} disabled={busy || !canAct}
              onChange={(value) => setForm({ ...form, overview: value })} />
          </Block>

          <Block title={t('ai.diagnosis')}>
            <Area value={form.diagnosis} rows={5} disabled={busy || !canAct}
              onChange={(value) => setForm({ ...form, diagnosis: value })} />
          </Block>

          {ratios.map((ratio) => (
            <Block key={ratio.code} title={`${ratio.code} — ${ratioName(ratio.code)}`}>
              <Area
                value={form.ratios[ratio.code] || ''}
                disabled={busy || !canAct}
                onChange={(value) =>
                  setForm({ ...form, ratios: { ...form.ratios, [ratio.code]: value } })
                }
              />
            </Block>
          ))}

          <Block title={t('ai.checks')}>
            <Area value={form.checks} disabled={busy || !canAct}
              onChange={(value) => setForm({ ...form, checks: value })} />
          </Block>

          <Block title={t('ai.comparison')}>
            <Area value={form.comparison} disabled={busy || !canAct}
              onChange={(value) => setForm({ ...form, comparison: value })} />
          </Block>

          <Block title={t('ai.recommendationsEdit')}>
            <Area value={form.recommendations} rows={5} disabled={busy || !canAct}
              onChange={(value) => setForm({ ...form, recommendations: value })} />
          </Block>

          <Block title={t('ai.attentionEdit')}>
            <Area value={form.attention} rows={4} disabled={busy || !canAct}
              onChange={(value) => setForm({ ...form, attention: value })} />
          </Block>

          {canAct && (
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
              <button type="button" disabled={busy} onClick={regenerate}>
                {t('ai.redraft')}
              </button>
              <button type="button" className="primary" disabled={busy} onClick={approve}>
                {busy ? t('common.saving') : t('ai.approveAs', { name: api.getAnalystName() || '…' })}
              </button>
            </div>
          )}
        </>
      )}

      {analysis?.status === 'APPROVED' && (
        <>
          <p className="faint" style={{ marginTop: 0 }}>
            {t('ai.approvedBy')} <strong>{analysis.approved_by}</strong>
            {analysis.approved_at
              ? ` ${t('ai.on', { when: formatDateTime(analysis.approved_at) })}`
              : ''}
            {' · '}
            {analysis.was_edited ? t('ai.edited') : t('ai.asDrafted')}
            {` · ${t('ai.assisted')}`}
            {analysis.model ? ` (${analysis.model})` : ''}
            {analysis.language ? ` · ${languageName(analysis.language)}` : ''}
          </p>

          <Block title={t('ai.overview')}><Text value={analysis.sections?.overview} /></Block>
          {analysis.sections?.diagnosis && (
            <Block title={t('ai.diagnosis')}><Text value={analysis.sections.diagnosis} /></Block>
          )}
          {ratios
            .filter((ratio) => analysis.sections?.ratios?.[ratio.code])
            .map((ratio) => (
              <Block key={ratio.code} title={`${ratio.code} — ${ratioName(ratio.code)}`}>
                <Text value={analysis.sections.ratios[ratio.code]} />
              </Block>
            ))}
          <Block title={t('ai.checks')}><Text value={analysis.sections?.checks} /></Block>
          <Block title={t('ai.comparison')}>
            <Text value={analysis.sections?.comparison} />
          </Block>
          {(analysis.sections?.recommendations || []).length > 0 && (
            <Block title={t('ai.recommendations')}>
              <Points items={analysis.sections.recommendations} />
            </Block>
          )}
          {(analysis.sections?.attention || []).length > 0 && (
            <Block title={t('ai.attention')}>
              <Points items={analysis.sections.attention} />
            </Block>
          )}
        </>
      )}
    </section>
  )
}