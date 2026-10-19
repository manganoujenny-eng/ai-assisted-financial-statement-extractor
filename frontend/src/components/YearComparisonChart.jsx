/* Year N compared with year N-1, as charts (dashboard).
 *
 * Two views, both read from what the backend already sends:
 *
 *  - RatioComparison: one small panel per ratio, N-1 and N as two bars.
 *    Ratios have different units (x, %), so each panel has its own scale —
 *    one shared axis would mislead. Bars start at zero and a negative value
 *    goes left of the zero line.
 *  - KeyFigures: the main validated amounts (FCFA) of both years, one scale
 *    for all of them since they share a unit. Shown only when the package
 *    contained the N-1 column.
 *
 * Colours: two steps of the EB-Partners Audit blue (validated for colour
 * blindness), N the stronger one. Every bar carries its value as text, the
 * legend names both years, and hovering a panel shows the exact figures;
 * the table under the chart gives the same data as text.
 */

import { useState } from 'react'
import { labelByCode, useI18n } from '../i18n/index.jsx'

const KEY_ITEMS = ['XB', 'XI', 'BZ', 'CP', 'DD']

function toNumber(value) {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

/* Where zero sits and how wide a bar is, in % of the track. */
function scale(values) {
  const present = values.filter((value) => value !== null)
  const low = Math.min(0, ...present)
  const high = Math.max(0, ...present)
  const span = high - low || 1
  const zero = ((0 - low) / span) * 100
  return (value) => {
    if (value === null) return null
    const at = ((value - low) / span) * 100
    return { left: Math.min(zero, at), width: Math.max(Math.abs(at - zero), 0.8), zero }
  }
}

function Legend({ previousYear, currentYear }) {
  const { t } = useI18n()
  return (
    <div className="yc-legend" aria-hidden="true">
      <span><i className="yc-swatch yc-prev" />{t('dash.chartPrevious', { year: previousYear ?? 'N-1' })}</span>
      <span><i className="yc-swatch yc-curr" />{t('dash.chartCurrent', { year: currentYear ?? 'N' })}</span>
    </div>
  )
}

function Bar({ kind, label, value, text, place }) {
  const geometry = place(value)
  return (
    <div className="yc-row">
      <span className="yc-row-label">{label}</span>
      <div className="yc-track">
        {geometry && <span className="yc-zero" style={{ left: `${geometry.zero}%` }} />}
        {geometry && (
          <span
            className={`yc-bar ${kind}${value < 0 ? ' negative' : ''}`}
            style={{ left: `${geometry.left}%`, width: `${geometry.width}%` }}
          />
        )}
      </div>
      <span className="yc-value num">{text}</span>
    </div>
  )
}

function ChangeLine({ change, percent, unit }) {
  const { t, formatNumber } = useI18n()
  const delta = toNumber(change)
  if (delta === null) return <p className="yc-change faint">{t('dash.chartNoChange')}</p>
  const arrow = delta > 0 ? '▲' : delta < 0 ? '▼' : '■'
  const pct = toNumber(percent)
  return (
    <p className="yc-change">
      <span aria-hidden="true">{arrow}</span>{' '}
      {delta > 0 ? '+' : ''}
      {formatNumber(delta, { maximumFractionDigits: 2 })}
      {/* a change of a percentage is in points: 9.4 % -> 5 % is -4.4 pts */}
      {unit ? ` ${unit === '%' ? 'pts' : unit}` : ''}
      {pct !== null && ` (${pct > 0 ? '+' : ''}${formatNumber(pct, { maximumFractionDigits: 1 })} %)`}
    </p>
  )
}

export function RatioComparison({ comparison }) {
  const { t, formatNumber } = useI18n()
  const [active, setActive] = useState(null)
  const rows = comparison?.ratios || []
  if (rows.length === 0) return null

  const show = (value, unit) =>
    value === null ? t('dash.chartNotComputable') : `${formatNumber(value, { maximumFractionDigits: 2 })}${unit ? ` ${unit}` : ''}`

  return (
    <div className="yc-block">
      <div className="yc-head">
        <h3>{t('dash.chartRatiosTitle')}</h3>
        <Legend previousYear={comparison.previous_year} currentYear={comparison.current_year} />
      </div>
      <div className="yc-grid">
        {rows.map((row) => {
          const previous = toNumber(row.previous_value)
          const current = toNumber(row.current_value)
          const place = scale([previous, current])
          const name = labelByCode(t, 'ratio', row.code, row.name || row.code)
          return (
            <figure
              key={row.code}
              className={`yc-panel${active === row.code ? ' active' : ''}`}
              tabIndex={0}
              onMouseEnter={() => setActive(row.code)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(row.code)}
              onBlur={() => setActive(null)}
              aria-label={`${name}: ${comparison.previous_year} ${show(previous, row.unit)}, ${comparison.current_year} ${show(current, row.unit)}`}
            >
              <figcaption>
                <span className="code">{row.code}</span> {name}
              </figcaption>
              <Bar kind="yc-prev" label={comparison.previous_year ?? 'N-1'} value={previous}
                text={show(previous, row.unit)} place={place} />
              <Bar kind="yc-curr" label={comparison.current_year ?? 'N'} value={current}
                text={show(current, row.unit)} place={place} />
              <ChangeLine change={row.change} percent={row.percent_change} unit={row.unit} />
            </figure>
          )
        })}
      </div>
    </div>
  )
}

export function KeyFigures({ dataset, previousYear, currentYear }) {
  const { t, lang, formatNumber } = useI18n()
  const [active, setActive] = useState(null)
  const prior = dataset?.prior_year_amounts || {}
  const current = dataset?.amounts || {}
  const items = KEY_ITEMS.filter((code) => toNumber(prior[code]) !== null || toNumber(current[code]) !== null)
  if (Object.keys(prior).length === 0 || items.length === 0) return null

  // One unit (FCFA) for every item, so one shared scale.
  const all = items.flatMap((code) => [toNumber(prior[code]), toNumber(current[code])])
  const place = scale(all)
  const compact = new Intl.NumberFormat(lang === 'fr' ? 'fr-FR' : 'en-GB', {
    notation: 'compact',
    maximumFractionDigits: 1,
  })
  const short = (value) => (value === null ? '—' : compact.format(value))
  const full = (value) => (value === null ? '—' : `${formatNumber(value)} FCFA`)

  return (
    <div className="yc-block">
      <div className="yc-head">
        <h3>{t('dash.chartAmountsTitle')}</h3>
        <Legend previousYear={previousYear} currentYear={currentYear} />
      </div>
      <p className="faint yc-note">{t('dash.chartAmountsNote')}</p>
      <div className="yc-amounts">
        {items.map((code) => {
          const a = toNumber(prior[code])
          const b = toNumber(current[code])
          const name = t(`dash.item.${code}`)
          return (
            <div
              key={code}
              className={`yc-amount${active === code ? ' active' : ''}`}
              tabIndex={0}
              onMouseEnter={() => setActive(code)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(code)}
              onBlur={() => setActive(null)}
              aria-label={`${name}: ${previousYear} ${full(a)}, ${currentYear} ${full(b)}`}
            >
              <div className="yc-amount-name">
                <span className="code">{code}</span> {name}
                {active === code && (
                  <span className="yc-readout num">
                    {previousYear}: {full(a)} · {currentYear}: {full(b)}
                  </span>
                )}
              </div>
              <Bar kind="yc-prev" label={previousYear ?? 'N-1'} value={a} text={short(a)} place={place} />
              <Bar kind="yc-curr" label={currentYear ?? 'N'} value={b} text={short(b)} place={place} />
            </div>
          )
        })}
      </div>
    </div>
  )
}