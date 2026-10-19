/* A full-screen red confirmation dialog for decisions that are hard to
 * undo: validating data that fails blocking checks, deleting a case or a
 * document. One component so every such moment looks and behaves the same.
 *
 * The parent decides when it is open (render it or don't) and what happens
 * on confirm; this only lays it out. Styles: .dialog-* in styles/app.css.
 */

import { useI18n } from '../i18n/index.jsx'

export default function DangerDialog({
  title,
  children,
  confirmLabel,
  workingLabel,
  cancelLabel,
  working = false,
  confirmDisabled = false,
  onConfirm,
  onCancel,
}) {
  const { t } = useI18n()
  return (
    <div
      className="dialog-scrim"
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="danger-dialog-title"
      onKeyDown={(event) => {
        if (event.key === 'Escape' && !working) onCancel()
      }}
    >
      <div className="card dialog-card">
        <h2 id="danger-dialog-title">
          <span className="dialog-icon" aria-hidden="true">⚠</span>
          {title}
        </h2>

        {children}

        <div className="dialog-actions">
          <button disabled={working} onClick={onCancel}>
            {cancelLabel || t('common.cancel')}
          </button>
          <button
            className="primary danger"
            disabled={working || confirmDisabled}
            onClick={onConfirm}
          >
            {working ? workingLabel || t('common.working') : confirmLabel || t('common.confirm')}
          </button>
        </div>
      </div>
    </div>
  )
}