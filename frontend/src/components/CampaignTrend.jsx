/* All the corpus campaigns, as charts (administration — Campaigns).
 *
 *  1. Accuracy over the campaigns: field accuracy and ratio accuracy, in %,
 *     one point per campaign in the order they were run. Both are shares of
 *     the same kind, so they share one axis (0–100 %). Field accuracy is the
 *     solid darker line, ratio accuracy the dashed lighter one: the dash
 *     tells them apart without colour.
 *  2. Silent false positives per campaign: the errors no check caught, the
 *     number that must fall to zero.
 *
 * Hovering (or focusing) a campaign shows its date, note and figures;
 * clicking it opens the campaign. The same figures are in the table of
 * stored campaigns below the charts.
 */

import { useEffect, useRef, useState } from 'react'
import { useI18n } from '../i18n/index.jsx'

const HEIGHT = 220
const PAD = { top: 14, right: 18, bottom: 34, left: 44 }

function useWidth() {
  const ref = useRef(null)
  const [width, setWidth] = useState(640)
  useEffect(() => {
    if (!ref.current || typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(280, entry.contentRect.width)))
    observer.observe(ref.current)
    return () => observer.disconnect()
  }, [])
  return [ref, width]
}

const pctOf = (value) => (value === null || value === undefined || value === '' ? null : Number(value) * 100)

export default function CampaignTrend({ campaigns, onOpen }) {
  const { t, formatDate, formatDateTime, formatNumber } = useI18n()
  const [active, setActive] = useState(null)
  const [ref, width] = useWidth()

  // Oldest first, corpus campaigns only.
  const points = [...campaigns]
    .filter((c) => c.kind === 'CORPUS')
    .sort((a, b) => String(a.run_at).localeCompare(String(b.run_at)))
    .map((c, index) => ({
      index,
      id: c.id,
      at: c.run_at,
      note: c.note,
      field: pctOf(c.headline.field_accuracy),
      ratio: pctOf(c.headline.ratio_accuracy),
      silent: c.headline.silent_false_positives ?? 0,
      evaluated: c.headline.evaluated,
      packages: c.headline.packages,
    }))

  if (points.length === 0) return <p className="muted" style={{ margin: 0 }}>{t('adm.trendEmpty')}</p>

  const innerW = width - PAD.left - PAD.right
  const innerH = HEIGHT - PAD.top - PAD.bottom
  const x = (index) =>
    PAD.left + (points.length === 1 ? innerW / 2 : (index / (points.length - 1)) * innerW)
  const y = (value) => PAD.top + innerH - (value / 100) * innerH
  const line = (key) =>
    points
      .filter((p) => p[key] !== null)
      .map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.index).toFixed(1)},${y(p[key]).toFixed(1)}`)
      .join(' ')
  const show = (value) => (value === null ? '—' : `${formatNumber(value, { maximumFractionDigits: 1 })} %`)
  const step = Math.max(1, Math.ceil(points.length / Math.max(1, Math.floor(innerW / 90))))
  const current = active !== null ? points[active] : null

  // Silent false positives: bars on their own small chart (another unit).
  const silentMax = Math.max(1, ...points.map((p) => p.silent))
  const barH = 120
  const barInner = barH - 22 - 24
  const barW = Math.min(36, Math.max(10, innerW / points.length - 10))

  return (
    <div className="ct" ref={ref}>
      <div className="ct-head">
        <h4>{t('adm.trendAccuracy')}</h4>
        <div className="yc-legend">
          <span><i className="ct-key solid" />{t('adm.fieldAccuracy')}</span>
          <span><i className="ct-key dashed" />{t('adm.ratioAccuracy')}</span>
        </div>
      </div>
      <div className="ct-plot">
        <svg width={width} height={HEIGHT} role="img" aria-label={t('adm.trendAccuracy')}>
          {[0, 25, 50, 75, 100].map((tick) => (
            <g key={tick}>
              <line className="ct-grid" x1={PAD.left} x2={width - PAD.right} y1={y(tick)} y2={y(tick)} />
              <text className="ct-tick" x={PAD.left - 8} y={y(tick) + 4} textAnchor="end">{tick} %</text>
            </g>
          ))}
          {points.map((p) =>
            p.index % step === 0 || p.index === points.length - 1 ? (
              <text key={p.id} className="ct-tick" x={x(p.index)} y={HEIGHT - 12} textAnchor="middle">
                {formatDate(p.at)}
              </text>
            ) : null
          )}
          {current && (
            <line className="ct-cross" x1={x(current.index)} x2={x(current.index)} y1={PAD.top} y2={PAD.top + innerH} />
          )}
          <path className="ct-line ratio" d={line('ratio')} />
          <path className="ct-line field" d={line('field')} />
          {points.map((p) => (
            <g key={p.id}>
              {p.ratio !== null && <circle className="ct-dot ratio" cx={x(p.index)} cy={y(p.ratio)} r={4.5} />}
              {p.field !== null && <circle className="ct-dot field" cx={x(p.index)} cy={y(p.field)} r={4.5} />}
              <rect
                className="ct-hit"
                x={x(p.index) - Math.max(12, innerW / points.length / 2)}
                y={PAD.top}
                width={Math.max(24, innerW / points.length)}
                height={innerH}
                tabIndex={0}
                role="button"
                aria-label={`${formatDateTime(p.at)} — ${t('adm.fieldAccuracy')} ${show(p.field)}, ${t('adm.ratioAccuracy')} ${show(p.ratio)}`}
                onMouseEnter={() => setActive(p.index)}
                onMouseLeave={() => setActive(null)}
                onFocus={() => setActive(p.index)}
                onBlur={() => setActive(null)}
                onClick={() => onOpen(p.id)}
                onKeyDown={(event) => event.key === 'Enter' && onOpen(p.id)}
              />
            </g>
          ))}
        </svg>
        {current && (
          <div
            className="ct-tip"
            role="tooltip"
            style={{ left: Math.min(Math.max(x(current.index) - 110, 0), width - 230) }}
          >
            <strong>{formatDateTime(current.at)}</strong>
            {current.note && <span className="faint">{current.note}</span>}
            <span><i className="ct-key solid" /> {t('adm.fieldAccuracy')} <b className="num">{show(current.field)}</b></span>
            <span><i className="ct-key dashed" /> {t('adm.ratioAccuracy')} <b className="num">{show(current.ratio)}</b></span>
            <span>{t('adm.silent')} <b className="num">{current.silent}</b></span>
            <span className="faint">{t('adm.packagesEvaluated')} {current.evaluated}/{current.packages} · {t('adm.clickToOpen')}</span>
          </div>
        )}
      </div>

      <div className="ct-head" style={{ marginTop: 18 }}>
        <h4>{t('adm.trendSilent')}</h4>
        <span className="faint">{t('adm.trendSilentHint')}</span>
      </div>
      <svg width={width} height={barH} role="img" aria-label={t('adm.trendSilent')}>
        <line className="ct-axis" x1={PAD.left} x2={width - PAD.right} y1={22 + barInner} y2={22 + barInner} />
        {points.map((p) => {
          const h = (p.silent / silentMax) * barInner
          const cx = x(p.index)
          return (
            <g key={p.id} className={active === p.index ? 'ct-bar-group active' : 'ct-bar-group'}>
              <rect
                className="ct-bar"
                x={cx - barW / 2}
                y={22 + barInner - Math.max(h, p.silent ? 2 : 0)}
                width={barW}
                height={Math.max(h, p.silent ? 2 : 0)}
                rx={3}
              />
              <text className="ct-value" x={cx} y={22 + barInner - Math.max(h, 0) - 6} textAnchor="middle">{p.silent}</text>
              {(p.index % step === 0 || p.index === points.length - 1) && (
                <text className="ct-tick" x={cx} y={barH - 6} textAnchor="middle">{formatDate(p.at)}</text>
              )}
              <rect
                className="ct-hit"
                x={cx - Math.max(12, innerW / points.length / 2)}
                y={0}
                width={Math.max(24, innerW / points.length)}
                height={barH}
                onMouseEnter={() => setActive(p.index)}
                onMouseLeave={() => setActive(null)}
                onClick={() => onOpen(p.id)}
              />
            </g>
          )
        })}
      </svg>
    </div>
  )
}