/* One stored campaign, opened (administration — Campaigns).
 *
 * CORPUS campaign — the extraction compared with the hand readings:
 *   the headline figures and, in plain words, what they mean; then one
 *   panel per package with EVERY item (hand reading, what the system read,
 *   the gap, right / wrong / missing / silent), every ratio (true value,
 *   computed value, gap, and the wrong items that caused it), the checks
 *   run on the extraction, and, for a rejected hand reading, the check it
 *   fails and what to correct.
 *
 * SENSITIVITY test — one correct statement damaged on purpose: for each
 *   item, how far each ratio moves when that item is 10 % off, and whether
 *   the checks would have noticed. No extraction involved.
 *
 * Both end with the criticality bars: which items do the most damage.
 * Campaigns stored before these details existed show what they kept.
 */

import { useState } from 'react'
import { StatTile, usePercent } from './AdminBits.jsx'
import { labelByCode, useI18n } from '../i18n/index.jsx'

const RATIOS = ['R1', 'R2', 'R3', 'R4', 'R5']

/* ------------------------------------------------------------ shared */
export function CriticalityBars({ criticality }) {
  const { t, formatNumber } = useI18n()
  const [active, setActive] = useState(null)
  const rows = Object.entries(criticality || {})
    .map(([code, value]) => ({ code, value: Number(value) }))
    .filter((row) => row.value > 0)
    .sort((a, b) => b.value - a.value)
  if (rows.length === 0) return <p className="faint">{t('adm.noCriticality')}</p>
  const max = rows[0].value
  // Below 0.1 %, two decimals: a tiny effect must not read as "0 %".
  const show = (value) =>
    `${formatNumber(value * 100, { maximumFractionDigits: value * 100 < 0.1 ? 2 : 1 })} %`

  return (
    <div className="adm-bars" role="list">
      {rows.map((row) => (
        <div
          key={row.code}
          className={`adm-bar-row${active === row.code ? ' active' : ''}`}
          role="listitem"
          tabIndex={0}
          onMouseEnter={() => setActive(row.code)}
          onMouseLeave={() => setActive(null)}
          onFocus={() => setActive(row.code)}
          onBlur={() => setActive(null)}
          aria-label={`${row.code}: ${show(row.value)}`}
        >
          <span className="adm-bar-label">
            <span className="code">{row.code}</span>{' '}
            <span className="faint">{labelByCode(t, 'adm.item', row.code, '')}</span>
          </span>
          <span className="adm-bar-track">
            <span className="adm-bar" style={{ width: `${(row.value / max) * 100}%` }} />
            {active === row.code && (
              <span className="adm-bar-tip" role="tooltip">
                {t('adm.criticalityTip', { code: row.code, value: show(row.value) })}
              </span>
            )}
          </span>
          <span className="adm-bar-value num">{show(row.value)}</span>
        </div>
      ))}
    </div>
  )
}

function useFormat() {
  const { formatNumber } = useI18n()
  return {
    amount: (value) =>
      value === null || value === undefined ? '—' : formatNumber(Number(value), { maximumFractionDigits: 2 }),
    signed: (value) => {
      if (value === null || value === undefined) return '—'
      const n = Number(value)
      return `${n > 0 ? '+' : ''}${formatNumber(n, { maximumFractionDigits: 2 })}`
    },
    share: (value) => {
      if (value === null || value === undefined) return '—'
      const n = Number(value) * 100
      return `${n > 0 ? '+' : ''}${formatNumber(n, { maximumFractionDigits: Math.abs(n) < 0.1 ? 3 : 1 })} %`
    },
    ratio: (row) => {
      if (!row) return '—'
      if (row.value === null || row.value === undefined) return row.status
      return formatNumber(Number(row.value), { maximumFractionDigits: 3 })
    },
  }
}

/* ------------------------------------------------------- one package */
function Verdict({ p }) {
  const { t } = useI18n()
  if (p.status === 'REFERENCE_REJECTED') return <div className="banner warn">{t('adm.vRejected')}</div>
  if (p.status === 'EXTRACTION_FAILED') return <div className="banner fail">{t('adm.vExtractionFailed', { reason: p.reason })}</div>
  if (p.status === 'UNREADABLE') return <div className="banner warn">{t('adm.vUnreadable', { reason: p.reason })}</div>
  const wrongFields = (p.wrong_fields || []).length
  const wrongRatios = (p.wrong_ratios || []).length
  const silent = (p.silent_false_positives || []).length
  if (wrongFields === 0) return <div className="banner info">{t('adm.vPerfect', { fields: p.judged_fields, ratios: p.ratios })}</div>
  const caught = (p.checks_failed_on_extraction || []).length > 0 && silent === 0
  return (
    <div className={`banner ${silent ? 'fail' : 'warn'}`}>
      {t('adm.vWrong', { count: wrongFields, total: p.judged_fields, ratios: wrongRatios, ratioTotal: p.ratios })}{' '}
      {silent
        ? <strong>{t('adm.vSilent', { codes: p.silent_false_positives.join(', ') })}</strong>
        : caught
          ? t('adm.vCaught', { checks: p.checks_failed_on_extraction.join(', ') })
          : null}
    </div>
  )
}

function FieldsTable({ p }) {
  const { t } = useI18n()
  const f = useFormat()
  const [onlyErrors, setOnlyErrors] = useState(false)
  const rows = (p.fields || []).filter((row) => !onlyErrors || row.status !== 'RIGHT')
  return (
    <>
      <div className="adm-table-head">
        <h5 className="cd-title">{t('adm.dItems')}</h5>
        <label className="cd-toggle">
          <input type="checkbox" checked={onlyErrors} onChange={(event) => setOnlyErrors(event.target.checked)} />
          {t('adm.dOnlyErrors')}
        </label>
      </div>
      <div className="fields-table-wrap">
        <table className="cd-table">
          <thead>
            <tr>
              <th>{t('adm.item')}</th>
              <th className="num">{t('adm.dTruth')}</th>
              <th className="num">{t('adm.dRead')}</th>
              <th className="num">{t('adm.dGap')}</th>
              <th className="num">{t('adm.dGapShare')}</th>
              <th>{t('adm.state')}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.code} className={row.status === 'RIGHT' ? '' : 'cd-wrong'}>
                <td><span className="code">{row.code}</span> <span className="faint">{labelByCode(t, 'adm.item', row.code, '')}</span></td>
                <td className="num">{f.amount(row.truth)}</td>
                <td className="num">{row.extracted === null ? <span className="faint">{t('adm.nothing')}</span> : f.amount(row.extracted)}</td>
                <td className="num">{row.status === 'RIGHT' ? <span className="faint">0</span> : f.signed(row.difference)}</td>
                <td className="num">{row.status === 'RIGHT' ? <span className="faint">0 %</span> : f.share(row.relative)}</td>
                <td>
                  <span className={`pill ${row.status === 'RIGHT' ? 'neutral' : 'fail'}`}>
                    {row.status === 'RIGHT' ? '✓ ' : '✗ '}{t(`adm.fieldStatus.${row.status}`)}
                  </span>
                  {row.silent && <span className="pill fail cd-silent">{t('adm.dSilentTag')}</span>}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={6} className="faint">{t('adm.dNoError')}</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  )
}

function RatiosTable({ p }) {
  const { t } = useI18n()
  const f = useFormat()
  return (
    <>
      <h5 className="cd-title">{t('adm.dRatios')}</h5>
      <div className="fields-table-wrap">
        <table className="cd-table">
          <thead>
            <tr>
              <th>{t('adm.dRatio')}</th>
              <th className="num">{t('adm.dTrueValue')}</th>
              <th className="num">{t('adm.dComputed')}</th>
              <th className="num">{t('adm.dGapShare')}</th>
              <th>{t('adm.state')}</th>
              <th>{t('adm.dCause')}</th>
            </tr>
          </thead>
          <tbody>
            {(p.ratio_rows || []).map((row) => (
              <tr key={row.code} className={row.right ? '' : 'cd-wrong'}>
                <td><span className="code">{row.code}</span> <span className="faint">{labelByCode(t, 'ratio', row.code, row.name)}</span></td>
                <td className="num">{f.ratio(row.truth)}</td>
                <td className="num">{f.ratio(row.extracted)}</td>
                <td className="num">{row.right ? <span className="faint">{t('adm.dWithin')}</span> : f.share(row.relative)}</td>
                <td>
                  <span className={`pill ${row.right ? 'neutral' : 'fail'}`}>
                    {row.right ? `✓ ${t('adm.dRatioRight')}` : `✗ ${t('adm.dRatioWrong')}`}
                  </span>
                </td>
                <td>
                  {row.caused_by && row.caused_by.length
                    ? row.caused_by.map((code) => <span key={code} className="code cd-cause">{code}</span>)
                    : <span className="faint">{t('adm.dUses', { items: (row.items || []).join(', ') })}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function ChecksList({ checks, title }) {
  const { t } = useI18n()
  if (!checks || checks.length === 0) return null
  return (
    <>
      <h5 className="cd-title">{title}</h5>
      <ul className="cd-checks">
        {checks.map((check) => (
          <li key={check.code}>
            <span className={`pill ${check.passed ? 'ok' : check.blocking ? 'fail' : 'warn'}`}>
              {check.passed ? '✓' : '✗'} {check.code}
            </span>
            <span>{labelByCode(t, 'check', check.code, check.label)}</span>
            {!check.passed && check.message && <span className="faint cd-message">{check.message}</span>}
          </li>
        ))}
      </ul>
    </>
  )
}

function PackagePanel({ p }) {
  const { t } = useI18n()
  const pct = usePercent()
  const detailed = Array.isArray(p.fields) && p.fields.length > 0
  const problems = p.status !== 'EVALUATED' || (p.wrong_fields || []).length > 0
  return (
    <details className={`cd-package${problems ? ' problem' : ''}`} open={problems}>
      <summary>
        <strong className="code">{p.package}</strong>
        <span className={`pill ${p.status === 'EVALUATED' ? 'accent' : 'neutral'}`}>{t(`adm.pkgStatus.${p.status}`)}</span>
        {p.status === 'EVALUATED' && (
          <span className="cd-figures num">
            {t('adm.dItemsShort')} {p.judged_fields - (p.wrong_fields || []).length}/{p.judged_fields}
            {' · '}{t('adm.dRatiosShort')} {p.ratios - (p.wrong_ratios || []).length}/{p.ratios}
            {' · '}{t('adm.silent')} {(p.silent_false_positives || []).length}
          </span>
        )}
        <span className="faint cd-docs">{(p.documents || []).join(', ')}</span>
      </summary>
      <div className="cd-body">
        <Verdict p={p} />

        {p.status === 'REFERENCE_REJECTED' && (
          <>
            <ChecksList checks={(p.reference_checks || []).filter((c) => !c.passed)} title={t('adm.dRefChecks')} />
            {!(p.reference_checks || []).length && p.reason && <p className="faint">{p.reason}</p>}
            <p className="muted">{t('adm.dRefAdvice')}</p>
          </>
        )}

        {p.status === 'EVALUATED' && detailed && (
          <>
            <FieldsTable p={p} />
            <RatiosTable p={p} />
            <ChecksList checks={p.checks} title={t('adm.dChecks')} />
          </>
        )}

        {p.status === 'EVALUATED' && !detailed && (
          <div className="fields-table-wrap">
            <p className="faint">{t('adm.dOldCampaign')}</p>
            <table className="cd-table">
              <tbody>
                <tr><td>{t('adm.fieldAccuracy')}</td><td className="num">{pct(p.field_accuracy)}</td></tr>
                <tr><td>{t('adm.ratioAccuracy')}</td><td className="num">{pct(p.ratio_accuracy)}</td></tr>
                {(p.wrong_fields || []).map((w) => (
                  <tr key={w.code} className="cd-wrong"><td className="code">{w.code}</td><td>{t('adm.readVsTruth', { read: w.extracted ?? t('adm.nothing'), truth: w.truth })}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {p.other_lines?.annotated > 0 && (
          <p className="faint cd-other">
            {t('adm.dOtherLines', { same: p.other_lines.identical, total: p.other_lines.annotated })}
            {p.other_lines.different?.length ? ` — ${p.other_lines.different.map((d) => d.code).join(', ')}` : ''}
          </p>
        )}
        {(p.annotation_problems || []).length > 0 && (
          <div className="banner warn">
            {t('adm.dAnnotationProblems')}
            <ul>{p.annotation_problems.map((text) => <li key={text}>{text}</li>)}</ul>
          </div>
        )}
      </div>
    </details>
  )
}

/* ------------------------------------------------- sensitivity matrix */
function SensitivityMatrix({ cells }) {
  const { t, formatNumber } = useI18n()
  if (!cells || cells.length === 0) return null
  // The strongest perturbation tested (10 % by default).
  const strongest = Math.max(...cells.map((c) => Number(c.perturbation)))
  const rows = {}
  cells
    .filter((c) => Number(c.perturbation) === strongest)
    .forEach((c) => {
      rows[c.item] = rows[c.item] || { item: c.item, caught: c.intercepted_by_checks, ratios: {} }
      rows[c.item].ratios[c.ratio] = c.relative_deviation === null ? null : Number(c.relative_deviation)
    })
  const list = Object.values(rows).sort((a, b) => a.item.localeCompare(b.item))
  const max = Math.max(0.0001, ...list.flatMap((r) => Object.values(r.ratios).filter((v) => v !== null)))
  const show = (value) =>
    value === null ? '—' : value === 0 ? '0' : `${formatNumber(value * 100, { maximumFractionDigits: 1 })} %`

  return (
    <>
      <h4 className="adm-sub-title">{t('adm.sMatrixTitle', { pct: formatNumber(strongest * 100) })}</h4>
      <p className="muted" style={{ marginTop: 0 }}>{t('adm.sMatrixHelp')}</p>
      <div className="fields-table-wrap">
        <table className="cd-table cd-matrix">
          <thead>
            <tr>
              <th>{t('adm.item')}</th>
              {RATIOS.map((code) => <th key={code} className="num">{code}</th>)}
              <th>{t('adm.sCaught')}</th>
            </tr>
          </thead>
          <tbody>
            {list.map((row) => {
              const moves = Object.values(row.ratios).some((v) => v)
              return (
                <tr key={row.item}>
                  <td><span className="code">{row.item}</span> <span className="faint">{labelByCode(t, 'adm.item', row.item, '')}</span></td>
                  {RATIOS.map((code) => {
                    const value = row.ratios[code] ?? null
                    const strength = value ? Math.min(1, value / max) : 0
                    return (
                      <td key={code} className="num">
                        <span className="cd-heat" style={{ '--heat': strength }}>{show(value)}</span>
                      </td>
                    )
                  })}
                  <td>
                    {row.caught ? (
                      <span className="pill ok">✓ {t('adm.sYes')}</span>
                    ) : moves ? (
                      <span className="pill fail">✗ {t('adm.sNoSilent')}</span>
                    ) : (
                      <span className="pill neutral">{t('adm.sNoHarmless')}</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}

/* ---------------------------------------------------------------- main */
export default function CampaignDetail({ campaign, onClose, onDelete }) {
  const { t, formatDateTime } = useI18n()
  const pct = usePercent()
  const s = campaign.summary || {}
  const corpus = campaign.kind === 'CORPUS'
  const silent = (s.silent_false_positives || []).length

  return (
    <section className="card adm-detail" aria-labelledby="campaign-title">
      <div className="adm-detail-head">
        <div>
          <h3 id="campaign-title" style={{ margin: 0 }}>
            {t(`adm.kind.${campaign.kind}`)} · {formatDateTime(campaign.run_at)}
          </h3>
          <p className="faint" style={{ margin: '2px 0 0' }}>
            {campaign.author}
            {campaign.engine ? ` · ${campaign.engine}` : ''}
            {campaign.note ? ` · ${campaign.note}` : ''}
          </p>
        </div>
        <div className="cd-head-actions">
          {onDelete && (
            <button type="button" className="danger" onClick={onDelete}>{t('adm.deleteCampaign')}</button>
          )}
          <button type="button" onClick={onClose}>{t('common.close')}</button>
        </div>
      </div>
      <p className="muted cd-kind-help">{t(`adm.kindHelp.${campaign.kind}`)}</p>

      {corpus ? (
        <>
          <div className="adm-stats">
            <StatTile label={t('adm.packagesEvaluated')} value={`${s.evaluated ?? 0}/${s.packages ?? 0}`} />
            <StatTile
              label={t('adm.fieldAccuracy')}
              value={pct(s.field_accuracy)}
              hint={s.fields_judged ? t('adm.dRightOf', { right: s.fields_judged - s.fields_wrong, total: s.fields_judged }) : null}
            />
            <StatTile
              label={t('adm.ratioAccuracy')}
              value={pct(s.ratio_accuracy)}
              hint={s.ratios_judged ? t('adm.dRightOf', { right: s.ratios_judged - s.ratios_wrong, total: s.ratios_judged }) : null}
            />
            <StatTile label={t('adm.amplification')} value={s.amplification ?? '—'} hint={s.amplification ? t('adm.dAmplifyHint') : t('adm.noAmplification')} />
            <StatTile label={t('adm.silent')} value={silent} hint={silent ? (s.silent_false_positives || []).map((x) => `${x.package}:${x.code}`).join(', ') : null} />
            <StatTile label={t('adm.interception')} value={pct(s.interception_rate)} hint={t('adm.dInterceptHint')} />
          </div>

          <details className="cd-glossary">
            <summary>{t('adm.gTitle')}</summary>
            <dl>
              <dt>{t('adm.fieldAccuracy')}</dt><dd>{t('adm.gField')}</dd>
              <dt>{t('adm.ratioAccuracy')}</dt><dd>{t('adm.gRatio')}</dd>
              <dt>{t('adm.amplification')}</dt><dd>{t('adm.gAmplification')}</dd>
              <dt>{t('adm.silent')}</dt><dd>{t('adm.gSilent')}</dd>
              <dt>{t('adm.interception')}</dt><dd>{t('adm.gInterception')}</dd>
            </dl>
          </details>

          {['reference_rejected', 'extraction_failed', 'unreadable'].map((key) =>
            (s[key] || []).length ? (
              <div key={key} className="banner warn">
                {t(`adm.left.${key}`)} <strong>{s[key].join(', ')}</strong>
              </div>
            ) : null
          )}

          <h4 className="adm-sub-title">{t('adm.perPackage')}</h4>
          <div className="cd-packages">
            {(campaign.packages || []).map((p) => <PackagePanel key={p.package} p={p} />)}
          </div>
        </>
      ) : (
        <>
          <div className="adm-stats">
            <StatTile label={t('adm.interception')} value={pct(s.interception_rate)} hint={t('adm.dInterceptHint')} />
            <StatTile label={t('adm.itemsTested')} value={Object.keys(campaign.inputs?.ground_truth || {}).length} />
            {campaign.inputs?.package && <StatTile label={t('adm.package')} value={campaign.inputs.package} />}
          </div>
          <SensitivityMatrix cells={s.cells} />
        </>
      )}

      <h4 className="adm-sub-title">{t('adm.criticalityTitle')}</h4>
      <p className="muted" style={{ marginTop: 0 }}>{t('adm.criticalityHelp')}</p>
      <CriticalityBars criticality={s.criticality} />
      <details className="yc-table">
        <summary>{t('adm.inputsTitle')}</summary>
        <pre className="adm-json">{JSON.stringify(campaign.inputs || {}, null, 2)}</pre>
      </details>
    </section>
  )
}