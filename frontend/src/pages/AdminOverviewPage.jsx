/* Administration — Overview: the whole system on one page.
 *
 * Read from top to bottom, every block the same width as its neighbour:
 *   1. six headline figures;
 *   2. the cases along their workflow, step by step;
 *   3. accounts | extractions and AI commentary  (two equal tables);
 *   4. latest campaign | settings                (two equal lists);
 *   5. the latest activity, as in the audit log.
 * Settings never show a password or a key, only whether one is set.
 * Data: GET /api/admin/overview. Read-only.
 */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import * as api from '../api/client.js'
import { StatTile, useAuditText, usePercent } from '../components/AdminBits.jsx'
import { useI18n } from '../i18n/index.jsx'

// The order a case goes through (EXTRACTION_FAILED sits beside EXTRACTING).
const FLOW = ['CREATED', 'EXTRACTING', 'EXTRACTED', 'UNDER_REVIEW', 'SUBMITTED', 'VALIDATED', 'ANALYSED']
const ROLES = ['SUPERADMIN', 'ADMIN', 'SUPERVISOR', 'ANALYST']

function Section({ title, action, children, className = '' }) {
  return (
    <section className={`card ov-card ${className}`}>
      <h3 className="adm-card-title">
        {title}
        {action}
      </h3>
      {children}
    </section>
  )
}

export default function AdminOverviewPage() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const { t, formatDateTime, formatNumber } = useI18n()
  const { actionLabel, entityLabel } = useAuditText()
  const pct = usePercent()

  useEffect(() => {
    api.getAdminOverview().then(setData).catch((err) => setError(err.message))
  }, [])

  if (error) return <div className="banner fail">{error}</div>
  if (!data) return <p className="muted">{t('common.loading')}</p>

  const money = (value) =>
    `${formatNumber(Number(value || 0), { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`
  const latest = data.campaigns.latest_corpus
  const settings = data.settings
  const byStatus = data.cases.by_status
  const runs = data.extractions.by_status
  const ai = data.ai_analyses.by_status
  const failedCases = byStatus.EXTRACTION_FAILED || 0

  return (
    <>
      <h2 className="page-title">{t('adm.overviewTitle')}</h2>
      <p className="page-subtitle">{t('adm.overviewSubtitle')}</p>

      {/* 1 — headline figures */}
      <div className="ov-stats">
        <StatTile label={t('adm.statUsers')} value={data.users.active} hint={t('adm.statUsersHint', { total: data.users.total })} />
        <StatTile label={t('adm.statCases')} value={data.cases.total} hint={t('adm.statCasesHint', { count: (byStatus.VALIDATED || 0) + (byStatus.ANALYSED || 0) })} />
        <StatTile label={t('adm.statDocuments')} value={data.documents.total} hint={t('adm.statScanned', { count: data.documents.scanned })} />
        <StatTile label={t('adm.statExtractions')} value={data.extractions.total} hint={t('adm.statFailed', { count: runs.EXTRACTION_FAILED || 0 })} />
        <StatTile label={t('adm.statValidated')} value={data.validated_datasets} />
        <StatTile label={t('adm.statCampaigns')} value={data.campaigns.total} hint={t('adm.statCampaignsHint', { corpus: data.campaigns.corpus, sensitivity: data.campaigns.sensitivity })} />
      </div>

      {/* 2 — the cases along the workflow */}
      <Section title={t('adm.flowTitle')}>
        <ol className="ov-flow">
          {FLOW.map((status) => (
            <li key={status} className={byStatus[status] ? 'has' : ''}>
              <strong className="num">{byStatus[status] || 0}</strong>
              <span>{t(`status.case.${status}`)}</span>
            </li>
          ))}
        </ol>
        <p className="faint ov-flow-note">
          {failedCases
            ? t('adm.flowFailed', { count: failedCases })
            : t('adm.flowNote')}
        </p>
      </Section>

      {/* 3 — accounts | extractions & AI */}
      <div className="ov-pair">
        <Section title={t('adm.usersTitle')} action={<Link to="/users" className="adm-more">{t('adm.manage')}</Link>}>
          <div className="fields-table-wrap">
          <table className="ov-table">
            <thead>
              <tr>
                <th>{t('users.role')}</th>
                <th className="num">{t('adm.activeCol')}</th>
                <th className="num">{t('adm.inactiveCol')}</th>
                <th className="num">{t('adm.totalCol')}</th>
              </tr>
            </thead>
            <tbody>
              {ROLES.map((role) => {
                const total = data.users.by_role[role] || 0
                const off = data.users.inactive_by_role[role] || 0
                return (
                  <tr key={role}>
                    <td>{t(`adm.roles.${role}`)}</td>
                    <td className="num">{total - off}</td>
                    <td className="num">{off || <span className="faint">0</span>}</td>
                    <td className="num"><strong>{total}</strong></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          </div>
        </Section>

        <Section title={t('adm.workTitle')}>
          <div className="fields-table-wrap">
          <table className="ov-table">
            <thead>
              <tr>
                <th />
                <th className="num">{t('adm.doneCol')}</th>
                <th className="num">{t('adm.failedCol')}</th>
                <th className="num">{t('adm.costCol')}</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>{t('adm.extractionsRow')}<span className="faint ov-sub">{Object.entries(data.extractions.by_engine).map(([k, v]) => `${k} ${v}`).join(' · ') || '—'}</span></td>
                <td className="num">{runs.EXTRACTED || 0}</td>
                <td className="num">{runs.EXTRACTION_FAILED || <span className="faint">0</span>}</td>
                <td className="num">{money(data.extractions.cost_usd)}</td>
              </tr>
              <tr>
                <td>
                  {t('adm.aiRow')}
                  <span className="faint ov-sub">
                    {t('adm.aiDrafts', { count: data.ai_analyses.pending ?? ai.DRAFT ?? 0 })}
                    {data.ai_analyses.replaced > 0 && ` · ${t('adm.aiReplaced', { count: data.ai_analyses.replaced })}`}
                  </span>
                </td>
                <td className="num">{ai.APPROVED || 0}</td>
                <td className="num">{ai.FAILED || <span className="faint">0</span>}</td>
                <td className="num">
                  {money(data.ai_analyses.cost_usd)}
                  {data.ai_analyses.calls > 0 && (
                    <span className="faint ov-sub">{t('adm.aiCalls', { count: data.ai_analyses.calls })}</span>
                  )}
                </td>
              </tr>
            </tbody>
          </table>
          </div>
        </Section>
      </div>

      {/* 4 — latest campaign | settings */}
      <div className="ov-pair">
        <Section title={t('adm.latestCampaign')} action={<Link to="/admin/campaigns" className="adm-more">{t('adm.open')}</Link>}>
          {latest ? (
            <dl className="ov-list">
              <dt>{t('adm.when')}</dt><dd>{formatDateTime(latest.run_at)}</dd>
              <dt>{t('adm.who')}</dt><dd>{latest.author}</dd>
              {latest.note && (<><dt>{t('adm.note')}</dt><dd>{latest.note}</dd></>)}
              <dt>{t('adm.packagesEvaluated')}</dt><dd>{latest.evaluated}/{latest.packages}</dd>
              <dt>{t('adm.fieldAccuracy')}</dt><dd>{pct(latest.field_accuracy)}</dd>
              <dt>{t('adm.ratioAccuracy')}</dt><dd>{pct(latest.ratio_accuracy)}</dd>
              <dt>{t('adm.amplification')}</dt><dd>{latest.amplification ?? '—'}</dd>
              <dt>{t('adm.silent')}</dt><dd>{latest.silent_false_positives ?? '—'}</dd>
            </dl>
          ) : (
            <p className="muted" style={{ margin: 0 }}>{t('adm.noCampaignYet')}</p>
          )}
        </Section>

        <Section title={t('adm.settingsTitle')}>
          <dl className="ov-list">
            <dt>{t('adm.set.storage')}</dt><dd>{settings.storage}</dd>
            <dt>{t('adm.set.database')}</dt><dd className="adm-break">{settings.database}</dd>
            <dt>{t('adm.set.structurer')}</dt><dd>{settings.structurer}{settings.extraction_model ? ` · ${settings.extraction_model}` : ''}</dd>
            <dt>{t('adm.set.ai')}</dt><dd>{settings.ai_analysis}{settings.analysis_model ? ` · ${settings.analysis_model}` : ''}</dd>
            <dt>{t('adm.set.apiKey')}</dt><dd>{t(`adm.set.key.${settings.anthropic_api_key === 'set' ? 'set' : 'unset'}`)}</dd>
            <dt>{t('adm.set.budget')}</dt><dd>{settings.max_cost_usd} $</dd>
            <dt>{t('adm.set.signIn')}</dt><dd>{settings.auth_required ? t('adm.set.on') : t('adm.set.off')}</dd>
            <dt>{t('adm.set.upload')}</dt><dd>{settings.max_upload_mb} MB</dd>
            <dt>{t('adm.set.corpus')}</dt><dd className="adm-break">{settings.corpus_dir}</dd>
          </dl>
          <p className="faint" style={{ margin: '10px 0 0' }}>{t('adm.settingsNote')}</p>
        </Section>
      </div>

      {/* 5 — latest activity */}
      <Section
        title={<>{t('adm.recentTitle')} <span className="pill neutral">{data.audit.total}</span></>}
        action={<Link to="/admin/audit" className="adm-more">{t('adm.seeAll')}</Link>}
      >
        {data.audit.recent.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>{t('adm.noActivity')}</p>
        ) : (
          <div className="fields-table-wrap">
            <table className="ov-table">
              <thead>
                <tr>
                  <th>{t('adm.when')}</th>
                  <th>{t('adm.who')}</th>
                  <th>{t('adm.action')}</th>
                  <th>{t('adm.onWhat')}</th>
                </tr>
              </thead>
              <tbody>
                {data.audit.recent.map((entry) => (
                  <tr key={entry.id}>
                    <td className="adm-nowrap adm-when">{formatDateTime(entry.at)}</td>
                    <td>{entry.author}</td>
                    <td><span className={`pill ${/FAILED/.test(entry.action) ? 'fail' : 'neutral'}`}>{actionLabel(entry.action)}</span></td>
                    <td>
                      <span className="faint">{entityLabel(entry.entity)}</span>
                      {entry.about && entry.about !== entry.author ? <> · {entry.about}</> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </>
  )
}