/* "Ratios across all validated cases", drawn (supervisor dashboard).
 *
 * One strip per ratio. Every dot is one validated case placed at its value,
 * so the supervisor sees at a glance where the companies sit, which ones
 * stand apart, and how many fall below the documented reference:
 *
 *   ●  a case (hover or focus it: client, year, analyst, exact value)
 *   ◆  the median of all cases
 *   ┆  the documented reference (R1, R3 only — the other ratios have none,
 *      BR-14, so no case is ever judged against one)
 *
 * Each strip has its own scale: the ratios have different units (x, %).
 * A dot below the reference is amber AND carries "▼" in its tooltip and in
 * the count under the strip, so colour is never the only signal. The exact
 * figures stay available in the table under the charts.
 *
 * Data: GET /api/supervisor/overview — "ratios" (statistics) and "cases"
 * (each case's current validated values).
 */

import { useState } from 'react'
import { labelByCode, useI18n } from '../i18n/index.jsx'

const num = (value) => {
  if (value === null || value === undefined || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

function Strip({ stat, cases }) {
  const { t, formatNumber } = useI18n()
  const [active, setActive] = useState(null)

  const points = cases
    .map((row) => ({ row, value: num(row.ratios?.[stat.code]) }))
    .filter((point) => point.value !== null)
  const reference = num(stat.threshold)
  const median = num(stat.median)
  const name = labelByCode(t, 'ratio', stat.code, stat.name)
  const unit = stat.unit ? ` ${stat.unit}` : ''
  const show = (value) => `${formatNumber(value, { maximumFractionDigits: 2 })}${unit}`

  // Scale: every value, the reference and the median, with some air.
  const all = [...points.map((p) => p.value), reference, median].filter((v) => v !== null)
  let low = Math.min(...all)
  let high = Math.max(...all)
  if (low === high) {
    low -= Math.abs(low) * 0.5 || 1
    high += Math.abs(high) * 0.5 || 1
  }
  const pad = (high - low) * 0.08
  low -= pad
  high += pad
  const at = (value) => ((value - low) / (high - low)) * 100

  // Cases with the same value stack upwards instead of hiding each other.
  const seen = {}
  const placed = points.map((point) => {
    const key = point.value.toFixed(4)
    const level = seen[key] || 0
    seen[key] = level + 1
    return { ...point, level, below: reference !== null && point.value < reference }
  })
  const levels = Math.max(1, ...placed.map((p) => p.level + 1))
  const below = placed.filter((p) => p.below).length

  return (
    <figure className="rs-strip">
      <figcaption>
        <span className="code">{stat.code}</span> {name}
        <span className="rs-what">{t(`sup.ratioMeaning.${stat.code}`)}</span>
      </figcaption>

      {placed.length === 0 ? (
        <p className="faint rs-empty">{t('sup.chartNoValue')}</p>
      ) : (
        <>
          <div className="rs-plot" style={{ height: 30 + levels * 16 }}>
            <div className="rs-axis" />
            {reference !== null && (
              <div className="rs-reference" style={{ left: `${at(reference)}%` }}>
                <span>{t('sup.chartReference', { value: show(reference) })}</span>
              </div>
            )}
            {median !== null && (
              <div
                className="rs-median"
                style={{ left: `${at(median)}%` }}
                title={t('sup.chartMedian', { value: show(median) })}
                aria-hidden="true"
              />
            )}
            {placed.map((point) => {
              const id = `${point.row.id}`
              return (
                <button
                  key={id}
                  type="button"
                  className={`rs-dot${point.below ? ' below' : ''}${active === id ? ' active' : ''}`}
                  style={{ left: `${at(point.value)}%`, bottom: 12 + point.level * 16 }}
                  onMouseEnter={() => setActive(id)}
                  onMouseLeave={() => setActive(null)}
                  onFocus={() => setActive(id)}
                  onBlur={() => setActive(null)}
                  aria-label={`${point.row.client} ${point.row.fiscal_year}: ${show(point.value)}`}
                >
                  {active === id && (
                    <span className="rs-tip" role="tooltip">
                      <strong>{point.row.client} · {point.row.fiscal_year}</strong>
                      <span>{point.below ? '▼ ' : ''}{show(point.value)}</span>
                      {point.row.analyst && <span className="faint">{point.row.analyst}</span>}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
          {/* The lowest and the highest case, labelled under their own dots. */}
          <div className="rs-scale num" aria-hidden="true">
            {num(stat.min) !== null && (
              <span style={{ left: `${at(num(stat.min))}%` }}>{t('sup.chartMin', { value: show(num(stat.min)) })}</span>
            )}
            {num(stat.max) !== null && num(stat.max) !== num(stat.min) && (
              <span style={{ left: `${at(num(stat.max))}%` }}>{t('sup.chartMax', { value: show(num(stat.max)) })}</span>
            )}
          </div>
        </>
      )}

      <p className="rs-summary">
        {t('sup.chartSummary', {
          count: placed.length,
          min: stat.min !== null ? show(num(stat.min)) : '—',
          max: stat.max !== null ? show(num(stat.max)) : '—',
          median: median !== null ? show(median) : '—',
        })}{' '}
        {reference !== null
          ? below > 0
            ? <strong className="rs-below-text">▼ {t('sup.chartBelow', { count: below, reference: show(reference) })}</strong>
            : t('sup.chartNoneBelow', { reference: show(reference) })
          : t('sup.chartNoReference')}
        {stat.not_computable > 0 && ` ${t('sup.chartNotComputable', { count: stat.not_computable })}`}
      </p>
    </figure>
  )
}

export default function RatioSpread({ ratios, cases }) {
  const { t } = useI18n()
  // Cases with a current validated result (their ratios were computed).
  const validated = (cases || []).filter((row) => row.ratios && Object.keys(row.ratios).length > 0)
  if (!ratios || ratios.length === 0) return null

  return (
    <div className="rs">
      <p className="rs-intro">{t('sup.chartIntro')}</p>
      <div className="rs-legend" aria-hidden="true">
        <span><i className="rs-key-dot" /> {t('sup.chartKeyCase')}</span>
        <span><i className="rs-key-median" /> {t('sup.chartKeyMedian')}</span>
        <span><i className="rs-key-reference" /> {t('sup.chartKeyReference')}</span>
        <span><i className="rs-key-dot below" /> {t('sup.chartKeyBelow')}</span>
      </div>
      {ratios.map((stat) => (
        <Strip key={stat.code} stat={stat} cases={validated} />
      ))}
    </div>
  )
}