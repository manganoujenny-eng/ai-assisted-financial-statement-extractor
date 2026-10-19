import { useEffect, useMemo, useState } from 'react'
import * as api from '../api/client.js'
import { useI18n } from '../i18n/index.jsx'

export default function ExcelSourceViewer({ documentId }) {
  const [data, setData] = useState(null)
  const [selectedSheet, setSelectedSheet] = useState(null)
  const [error, setError] = useState(null)
  const { t } = useI18n()

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const preview = await api.getExcelPreview(documentId)

        if (cancelled) return

        setData(preview)

        if (preview.sheets?.length) {
          setSelectedSheet(preview.sheets[0].name)
        }

        setError(null)
      } catch (err) {
        if (!cancelled) {
          setError(err.message)
        }
      }
    }

    load()

    return () => {
      cancelled = true
    }
  }, [documentId])

  const sheet = useMemo(() => {
    if (!data?.sheets?.length) return null

    return (
      data.sheets.find(
        (item) => item.name === selectedSheet
      ) || data.sheets[0]
    )
  }, [data, selectedSheet])

  if (error) {
    return (
      <div className="excel-preview-error">
        <strong>{t('excel.unable')}</strong>
        <p>{error}</p>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="excel-preview-loading">
        {t('excel.loading')}
      </div>
    )
  }

  if (!data.sheets?.length) {
    return (
      <div className="excel-preview-empty">
        {t('excel.empty')}
      </div>
    )
  }

  return (
    <div className="excel-viewer">

      <div className="excel-viewer-header">
        <div>
          <span className="review-section-label">
            {t('excel.source')}
          </span>

          <strong>
            {data.file_name}
          </strong>
        </div>

        <span className="pill neutral">
          {t('excel.sheets', { count: data.sheets.length })}
        </span>
      </div>

      <div className="excel-sheet-tabs">
        {data.sheets.map((item) => (
          <button
            key={item.name}
            className={
              item.name === sheet?.name
                ? 'excel-sheet-tab active'
                : 'excel-sheet-tab'
            }
            onClick={() =>
              setSelectedSheet(item.name)
            }
          >
            {item.name}
          </button>
        ))}
      </div>

      <div className="excel-table-container">
        <table className="excel-table">
          <tbody>
            {sheet.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                <td className="excel-row-number">
                  {rowIndex + 1}
                </td>

                {row.map((value, columnIndex) => (
                  <td
                    key={`${rowIndex}-${columnIndex}`}
                    className={
                      rowIndex === 0
                        ? 'excel-header-cell'
                        : ''
                    }
                  >
                    {value}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="excel-viewer-footer">
        <span>
          {t('excel.sheet')} <strong>{sheet.name}</strong>
        </span>

        <span>
          {t('excel.rows', { count: sheet.rows.length })}
        </span>
      </div>
    </div>
  )
}