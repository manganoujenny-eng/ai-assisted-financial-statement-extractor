/* Key in an item the extraction missed.
 *
 * The analyst has found the item in the source document (left panel) but
 * the extractor did not propose it — typically a scanned page whose table
 * OCR could not rebuild. The backend records it as KEYED (never proposed,
 * so it does not distort the extraction-accuracy figures), audits it under
 * the analyst's name and reruns every check.
 *
 * `missingCodes` are the required items the completeness check says are
 * absent; clicking one fills the code in.
 */

import { useState } from 'react'
import { useI18n } from '../i18n/index.jsx'

const EMPTY = { item_code: '', year: 'N', amount: '', document_id: '', source_page: '' }

export default function AddItemForm({ documents, missingCodes = [], disabled, onAdd }) {
  const [open, setOpen] = useState(false)
  const [item, setItem] = useState(EMPTY)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const { t } = useI18n()

  function update(key, value) {
    setItem((current) => ({ ...current, [key]: value }))
    setError(null)
  }

  async function submit(event) {
    event.preventDefault()
    const code = item.item_code.trim().toUpperCase()
    if (!/^[A-Z]{2}$/.test(code)) {
      setError(t('addItem.badCode'))
      return
    }
    if (!item.amount.trim()) {
      setError(t('addItem.noAmount'))
      return
    }

    try {
      setSaving(true)
      await onAdd({
        item_code: code,
        year: item.year,
        // Spaces as thousands separators are accepted and removed.
        amount: item.amount.replace(/\s/g, '').replace(',', '.'),
        document_id: item.document_id || null,
        source_page: item.source_page ? Number(item.source_page) : null,
      })
      setItem({ ...EMPTY, document_id: item.document_id })
      setOpen(false)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  if (!open) {
    return (
      <div className="card" style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <button type="button" disabled={disabled} onClick={() => setOpen(true)}>
          {t('addItem.open')}
        </button>
        <span className="faint">
          {missingCodes.length > 0
            ? t('addItem.requiredMissing', { codes: missingCodes.join(', ') })
            : t('addItem.hint')}
        </span>
      </div>
    )
  }

  return (
    <form className="card" onSubmit={submit}>
      <h3 style={{ marginTop: 0 }}>{t('addItem.title')}</h3>
      <p className="faint" style={{ marginTop: 0 }}>
        {t('addItem.intro')}
      </p>

      {missingCodes.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
          <span className="faint">{t('addItem.missing')}</span>
          {missingCodes.map((code) => (
            <button
              key={code}
              type="button"
              className={item.item_code === code ? 'selected-action' : ''}
              onClick={() => update('item_code', code)}
            >
              {code}
            </button>
          ))}
        </div>
      )}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: 10,
        }}
      >
        <label>
          {t('addItem.code')}
          <input
            value={item.item_code}
            maxLength={2}
            placeholder="XB"
            onChange={(event) => update('item_code', event.target.value.toUpperCase())}
            style={{ display: 'block', width: '100%' }}
          />
        </label>

        <label>
          {t('addItem.year')}
          <select
            value={item.year}
            onChange={(event) => update('year', event.target.value)}
            style={{ display: 'block', width: '100%' }}
          >
            <option value="N">{t('addItem.yearN')}</option>
            <option value="N-1">{t('addItem.yearN1')}</option>
          </select>
        </label>

        <label>
          {t('addItem.amount')}
          <input
            value={item.amount}
            inputMode="decimal"
            placeholder="5 198 800 000"
            onChange={(event) => update('amount', event.target.value)}
            style={{ display: 'block', width: '100%' }}
          />
        </label>

        <label>
          {t('addItem.foundIn')}
          <select
            value={item.document_id}
            onChange={(event) => update('document_id', event.target.value)}
            style={{ display: 'block', width: '100%' }}
          >
            <option value="">{t('addItem.notSpecified')}</option>
            {documents.map((document) => (
              <option key={document.id} value={document.id}>
                {document.display_name || document.file_name}
              </option>
            ))}
          </select>
        </label>

        <label>
          {t('addItem.page')}
          <input
            type="number"
            min="1"
            value={item.source_page}
            onChange={(event) => update('source_page', event.target.value)}
            style={{ display: 'block', width: '100%' }}
          />
        </label>
      </div>

      {error && (
        <div className="banner fail" style={{ marginTop: 12 }}>
          {error}
        </div>
      )}

      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 12 }}>
        <button
          type="button"
          disabled={saving}
          onClick={() => {
            setOpen(false)
            setError(null)
          }}
        >
          {t('common.cancel')}
        </button>
        <button type="submit" className="primary" disabled={saving || disabled}>
          {saving ? t('addItem.adding') : t('addItem.add')}
        </button>
      </div>
    </form>
  )
}