import { useI18n } from '../i18n/index.jsx'

export default function ChecksPanel({ checks }) {
  const { t, checkLabel } = useCheckText()
  if (!checks?.length) return null

  const ordered = [...checks].sort((a, b) => {
    const weight = (check) => {
      if (!check.passed && check.severity === 'BLOCKING') return 0
      if (!check.passed) return 1
      return 2
    }

    return weight(a) - weight(b)
  })

  return (
    <div className="card review-checks-card">
      <div className="review-section-heading">
        <div>
          <div className="review-section-label">
            {t('checks.engine')}
          </div>

          <h2>{t('checks.title')}</h2>

          <p className="faint">
            {t('checks.subtitle')}
          </p>
        </div>

        <div className="checks-summary">
          <span className="pill neutral">
            {t('checks.count', { count: checks.length })}
          </span>

          <span className="pill ok">
            {t('checks.passed', { count: checks.filter((check) => check.passed).length })}
          </span>

          {checks.some((check) => !check.passed) && (
            <span className="pill fail">
              {t('checks.failed', { count: checks.filter((check) => !check.passed).length })}
            </span>
          )}
        </div>
      </div>

      <div className="checks-list">
        {ordered.map((check) => (
          <details
            key={check.code}
            className={[
              'check-detail',
              !check.passed && check.severity === 'BLOCKING'
                ? 'check-blocking'
                : '',
              !check.passed && check.severity !== 'BLOCKING'
                ? 'check-warning'
                : '',
              check.passed ? 'check-passed' : '',
            ]
              .filter(Boolean)
              .join(' ')}
          >
            <summary className="check-summary">
              <span className="check-code">
                {check.code}
              </span>

              <span className="check-label">
                {checkLabel(check)}
              </span>

              {check.gap !== null &&
                check.gap !== undefined && (
                  <span className="num check-gap">
                    {t('checks.gap')} {check.gap}
                  </span>
                )}

              <span
                className={`pill ${
                  check.passed
                    ? 'ok'
                    : check.severity === 'BLOCKING'
                      ? 'fail'
                      : 'warn'
                }`}
              >
                {check.passed
                  ? t('checks.pass')
                  : check.severity === 'BLOCKING'
                    ? t('checks.blocking')
                    : t('checks.warning')}
              </span>

              <span className="check-view">
                {t('checks.viewDetails')}
              </span>
            </summary>

            <div className="check-detail-body">
              <div className="check-message">
                {check.message}
              </div>

              <div className="check-detail-grid">

                <div>
                  <span>{t('checks.severity')}</span>
                  <strong>
                    {check.severity ? t(`severity.${check.severity}`) : '—'}
                  </strong>
                </div>

                <div>
                  <span>{t('checks.gap')}</span>
                  <strong>
                    {check.gap !== null &&
                    check.gap !== undefined
                      ? check.gap
                      : '—'}
                  </strong>
                </div>

                <div>
                  <span>{t('checks.itemsUsed')}</span>
                  <strong>
                    {Array.isArray(check.items_used) &&
                    check.items_used.length
                      ? check.items_used.join(', ')
                      : '—'}
                  </strong>
                </div>

              </div>
            </div>
          </details>
        ))}
      </div>
    </div>
  )
}

/* The check's name in the screen's language, by its code (CHK001…). The
 * backend's label is the fallback for a check added later. The message
 * under each check comes from the backend's rule engine and is in English. */
export function useCheckText() {
  const { t } = useI18n()
  return {
    t,
    checkLabel: (check) => {
      const key = `check.${check.code}`
      const text = t(key)
      return text === key ? check.label : text
    },
  }
}