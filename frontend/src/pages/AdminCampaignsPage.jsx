/* Administration — Evaluation campaigns (week 7), without the command line.
 *
 * 1. The corpus: one folder per package (RP001, RP002...) holding the
 *    statement(s) and ONE annotation workbook (your hand reading). Add a
 *    package, add or remove its files, see whether it is ready.
 * 2. Run a campaign over the whole corpus (same code as
 *    backend/evaluate_corpus.py). It is stored, and written to the audit log.
 * 3. A sensitivity test on one package's hand reading (no extraction:
 *    each item is damaged on purpose to see which ratios move and whether
 *    the checks notice).
 * 4. Charts of all the corpus campaigns, then every stored campaign; open
 *    one to read it item by item (components/CampaignDetail.jsx).
 *
 * Data: /api/admin/corpus..., /api/evaluations... Campaigns are never edited.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import * as api from '../api/client.js'
import DangerDialog from '../components/DangerDialog.jsx'
import CampaignDetail from '../components/CampaignDetail.jsx'
import CampaignTrend from '../components/CampaignTrend.jsx'
import { fileSize, usePercent } from '../components/AdminBits.jsx'
import { useI18n } from '../i18n/index.jsx'

/* ------------------------------------------------------------------ corpus */
function PackageCard({ pkg, onChanged, onError, onAskDelete, onSensitivity }) {
  const { t, formatDateTime } = useI18n()
  const input = useRef(null)
  const [busy, setBusy] = useState(false)

  async function upload(files) {
    if (!files || files.length === 0) return
    try {
      setBusy(true)
      onError(null)
      await api.uploadCorpusFiles(pkg.name, files)
      onChanged(t('adm.filesAdded', { count: files.length, name: pkg.name }))
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
    }
  }

  return (
    <div className={`adm-package${pkg.ready ? ' ready' : ''}`}>
      <div className="adm-package-head">
        <strong className="code">{pkg.name}</strong>
        {pkg.ready ? (
          <span className="pill accent">{t('adm.ready')}</span>
        ) : (
          <span className="pill neutral">{t(`adm.problem.${pkg.problem}`)}</span>
        )}
        <span className="adm-package-tools">
          <input
            ref={input}
            type="file"
            multiple
            accept=".pdf,.xlsx,.xls"
            className="adm-hidden-input"
            onChange={(event) => upload(event.target.files)}
            id={`files-${pkg.name}`}
          />
          <label htmlFor={`files-${pkg.name}`} className="button-like" aria-disabled={busy}>
            {busy ? t('adm.uploading') : t('adm.addFiles')}
          </label>
          {pkg.files.some((file) => file.kind === 'ANNOTATION') && (
            <button type="button" onClick={() => onSensitivity(pkg.name)} title={t('adm.sensitivityButtonHint')}>
              {t('adm.sensitivityButton')}
            </button>
          )}
          {pkg.files.length === 0 && (
            <button type="button" onClick={() => onAskDelete({ kind: 'package', pkg })}>
              {t('adm.deletePackage')}
            </button>
          )}
        </span>
      </div>
      {pkg.files.length === 0 ? (
        <p className="faint" style={{ margin: '6px 0 0' }}>{t('adm.emptyPackage')}</p>
      ) : (
        <ul className="adm-files">
          {pkg.files.map((file) => (
            <li key={file.name}>
              <span className={`pill ${file.kind === 'ANNOTATION' ? 'accent' : 'neutral'}`}>
                {t(`adm.fileKind.${file.kind}`)}
              </span>
              <span className="adm-file-name">{file.name}</span>
              <span className="faint num">{fileSize(file.size)}</span>
              <span className="faint">{formatDateTime(file.modified)}</span>
              <button
                type="button"
                className="adm-icon-button"
                aria-label={t('adm.deleteFile', { name: file.name })}
                title={t('adm.deleteFile', { name: file.name })}
                onClick={() => onAskDelete({ kind: 'file', pkg, file })}
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function CorpusSection({ corpus, reload, onMessage, onError, onSensitivity }) {
  const { t } = useI18n()
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState(null) // { kind, pkg, file, working, error }

  async function create(event) {
    event.preventDefault()
    try {
      setBusy(true)
      onError(null)
      await api.createCorpusPackage(name.trim())
      onMessage(t('adm.packageCreated', { name: name.trim() }))
      setName('')
      await reload()
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function confirmDelete() {
    try {
      setPending({ ...pending, working: true, error: null })
      if (pending.kind === 'file') {
        await api.deleteCorpusFile(pending.pkg.name, pending.file.name)
        onMessage(t('adm.fileDeleted', { name: pending.file.name }))
      } else {
        await api.deleteCorpusPackage(pending.pkg.name)
        onMessage(t('adm.packageDeleted', { name: pending.pkg.name }))
      }
      setPending(null)
      await reload()
    } catch (err) {
      setPending({ ...pending, working: false, error: err.message })
    }
  }

  const ready = corpus.packages.filter((pkg) => pkg.ready).length

  return (
    <section className="card">
      <h3 className="adm-card-title">
        {t('adm.corpusTitle')}{' '}
        <span className="pill neutral">{t('adm.readyCount', { ready, total: corpus.packages.length })}</span>
      </h3>
      <p className="muted" style={{ marginTop: 0 }}>{t('adm.corpusHelp')}</p>
      <p className="faint adm-break">{corpus.path}</p>

      {corpus.packages.length === 0 && <p className="muted">{t('adm.noPackage')}</p>}
      <div className="adm-packages">
        {corpus.packages.map((pkg) => (
          <PackageCard
            key={pkg.name}
            pkg={pkg}
            onError={onError}
            onAskDelete={(target) => setPending({ ...target, working: false, error: null })}
            onSensitivity={onSensitivity}
            onChanged={async (text) => {
              onMessage(text)
              await reload()
            }}
          />
        ))}
      </div>

      <form className="adm-inline-form" onSubmit={create}>
        <label>
          {t('adm.newPackage')}
          <input
            value={name}
            placeholder="RP002"
            maxLength={40}
            onChange={(event) => setName(event.target.value.replace(/[^A-Za-z0-9_-]/g, ''))}
          />
        </label>
        <button type="submit" disabled={busy || !name.trim()}>{t('adm.createPackage')}</button>
      </form>

      {pending && (
        <DangerDialog
          title={
            pending.kind === 'file'
              ? t('adm.deleteFileTitle', { name: pending.file.name, pkg: pending.pkg.name })
              : t('adm.deletePackageTitle', { name: pending.pkg.name })
          }
          confirmLabel={t('common.delete')}
          workingLabel={t('common.deleting')}
          working={pending.working}
          onConfirm={confirmDelete}
          onCancel={() => setPending(null)}
        >
          <p>{pending.kind === 'file' ? t('adm.deleteFileBody') : t('adm.deletePackageBody')}</p>
          {pending.error && <div className="banner fail">{pending.error}</div>}
        </DangerDialog>
      )}
    </section>
  )
}

/* ------------------------------------------------------------------- page */
export default function AdminCampaignsPage() {
  const [corpus, setCorpus] = useState(null)
  const [campaigns, setCampaigns] = useState(null)
  const [selected, setSelected] = useState(null)
  const [note, setNote] = useState('')
  const [kind, setKind] = useState('')
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)
  const [deleting, setDeleting] = useState(null) // { working, error } while the dialog is open
  const [params, setParams] = useSearchParams()
  const { t, formatDateTime } = useI18n()
  const pct = usePercent()
  const selectedId = params.get('id')

  async function reloadCorpus() {
    try {
      setCorpus(await api.getCorpus())
    } catch (err) {
      setError(err.message)
    }
  }

  async function reloadCampaigns() {
    try {
      setCampaigns((await api.listCampaigns(kind)).campaigns)
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    reloadCorpus()
  }, [])

  useEffect(() => {
    reloadCampaigns()
  }, [kind])

  useEffect(() => {
    if (!selectedId) {
      setSelected(null)
      return
    }
    api.getCampaign(selectedId).then(setSelected).catch((err) => setError(err.message))
  }, [selectedId])

  useEffect(() => {
    if (!message) return undefined
    const timer = setTimeout(() => setMessage(null), 5000)
    return () => clearTimeout(timer)
  }, [message])

  async function run() {
    try {
      setError(null)
      const campaign = await api.runCorpusCampaign(note.trim())
      setNote('')
      setMessage(t('adm.campaignDone'))
      await reloadCampaigns()
      setParams({ id: campaign.id })
    } catch (err) {
      if (!err.timedOut) setError(err.message)
    }
  }

  async function sensitivity(packageName) {
    try {
      setError(null)
      const { id } = await api.runPackageSensitivity(packageName)
      setMessage(t('adm.sensitivityDone', { name: packageName }))
      await reloadCampaigns()
      setParams({ id })
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (err) {
      setError(err.message)
    }
  }

  async function confirmDeleteCampaign() {
    try {
      setDeleting({ working: true, error: null })
      await api.deleteCampaign(selected.id)
      setDeleting(null)
      setParams({})
      setMessage(t('adm.campaignDeleted'))
      await reloadCampaigns()
    } catch (err) {
      setDeleting({ working: false, error: err.message })
    }
  }

  const readyPackages = useMemo(() => (corpus?.packages || []).filter((p) => p.ready).length, [corpus])

  return (
    <>
      <h2 className="page-title">{t('adm.campaignsTitle')}</h2>
      <p className="page-subtitle">{t('adm.campaignsSubtitle')}</p>

      {error && <div className="banner fail">{error}</div>}
      {message && <div className="banner info">{message}</div>}

      <section className="card adm-kinds">
        <div>
          <h3 className="adm-card-title">{t('adm.kind.CORPUS')}</h3>
          <p className="muted">{t('adm.kindHelp.CORPUS')}</p>
        </div>
        <div>
          <h3 className="adm-card-title">{t('adm.kind.SENSITIVITY')}</h3>
          <p className="muted">{t('adm.kindHelp.SENSITIVITY')}</p>
        </div>
      </section>

      {selected && (
        <CampaignDetail
          campaign={selected}
          onClose={() => setParams({})}
          onDelete={() => setDeleting({ working: false, error: null })}
        />
      )}

      {selected && deleting && (
        <DangerDialog
          title={t('adm.deleteCampaignTitle', {
            kind: t(`adm.kind.${selected.kind}`),
            when: formatDateTime(selected.run_at),
          })}
          confirmLabel={t('common.delete')}
          workingLabel={t('common.deleting')}
          working={deleting.working}
          onConfirm={confirmDeleteCampaign}
          onCancel={() => setDeleting(null)}
        >
          <p>{t('adm.deleteCampaignBody')}</p>
          {deleting.error && <div className="banner fail">{deleting.error}</div>}
        </DangerDialog>
      )}

      <section className="card">
        <h3 className="adm-card-title">{t('adm.trendTitle')}</h3>
        {campaigns === null ? (
          <p className="muted">{t('common.loading')}</p>
        ) : (
          <CampaignTrend campaigns={campaigns} onOpen={(id) => {
            setParams({ id })
            window.scrollTo({ top: 0, behavior: 'smooth' })
          }} />
        )}
      </section>

      {corpus === null ? (
        <p className="muted">{t('common.loading')}</p>
      ) : (
        <CorpusSection
          corpus={corpus}
          reload={reloadCorpus}
          onMessage={setMessage}
          onError={setError}
          onSensitivity={sensitivity}
        />
      )}

      <section className="card">
        <h3 className="adm-card-title">{t('adm.runTitle')}</h3>
        <p className="muted" style={{ marginTop: 0 }}>{t('adm.runHelp')}</p>
        <div className="adm-inline-form">
          <label className="adm-filter-wide">
            {t('adm.note')}
            <input
              value={note}
              maxLength={200}
              placeholder={t('adm.notePlaceholder')}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
          <button type="button" className="primary" disabled={readyPackages === 0} onClick={run}>
            {t('adm.runButton', { count: readyPackages })}
          </button>
        </div>
        {readyPackages === 0 && corpus && <p className="faint" style={{ margin: '8px 0 0' }}>{t('adm.nothingReady')}</p>}
      </section>

      <section className="card">
        <div className="adm-table-head">
          <h3 className="adm-card-title" style={{ margin: 0 }}>{t('adm.storedTitle')}</h3>
          <select value={kind} onChange={(event) => setKind(event.target.value)} style={{ width: 'auto' }}>
            <option value="">{t('adm.allKinds')}</option>
            <option value="CORPUS">{t('adm.kind.CORPUS')}</option>
            <option value="SENSITIVITY">{t('adm.kind.SENSITIVITY')}</option>
          </select>
        </div>
        {campaigns === null ? (
          <p className="muted">{t('common.loading')}</p>
        ) : campaigns.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>{t('adm.noCampaignYet')}</p>
        ) : (
          <div className="fields-table-wrap">
            <table className="adm-campaigns">
              <thead>
                <tr>
                  <th>{t('adm.when')}</th>
                  <th>{t('adm.kindLabel')}</th>
                  <th>{t('adm.who')}</th>
                  <th>{t('adm.note')}</th>
                  <th className="num">{t('adm.packagesShort')}</th>
                  <th className="num">{t('adm.fieldAccuracy')}</th>
                  <th className="num">{t('adm.ratioAccuracy')}</th>
                  <th className="num">{t('adm.amplification')}</th>
                  <th className="num">{t('adm.silent')}</th>
                  <th className="num">{t('adm.interception')}</th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c) => (
                  <tr
                    key={c.id}
                    className={`adm-click${selectedId === c.id ? ' selected' : ''}`}
                    tabIndex={0}
                    onClick={() => {
                      setParams({ id: c.id })
                      window.scrollTo({ top: 0, behavior: 'smooth' })
                    }}
                    onKeyDown={(event) => event.key === 'Enter' && setParams({ id: c.id })}
                  >
                    <td className="adm-nowrap adm-when">{formatDateTime(c.run_at)}</td>
                    <td><span className={`pill ${c.kind === 'CORPUS' ? 'accent' : 'neutral'}`} title={t(`adm.kindHelp.${c.kind}`)}>{t(`adm.kind.${c.kind}`)}</span></td>
                    <td>{c.author}</td>
                    <td className="adm-ellipsis">{c.note || <span className="faint">—</span>}</td>
                    <td className="num">{c.kind === 'CORPUS' ? `${c.headline.evaluated}/${c.headline.packages}` : '—'}</td>
                    <td className="num">{pct(c.headline.field_accuracy)}</td>
                    <td className="num">{pct(c.headline.ratio_accuracy)}</td>
                    <td className="num">{c.headline.amplification ?? '—'}</td>
                    <td className="num">{c.headline.silent_false_positives ?? '—'}</td>
                    <td className="num">{pct(c.headline.interception_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}