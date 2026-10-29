/* What is waiting for the signed-in user.
 *
 * Supervisor: the cases analysts have submitted for validation, and the
 * cases whose discussion has new messages from another supervisor.
 * Analyst: their cases a supervisor sent back with a correction request.
 *
 * GET /api/notifications derives these from the cases' state, so there is
 * nothing to "mark as read": an item disappears once its case moves on
 * (validated, sent back, or submitted again). Refreshed every 30 seconds,
 * when the page changes, and when another screen says something changed
 * (the "notifications-changed" event). Styles: .notif-* in styles/app.css.
 */

import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import * as api from '../api/client.js'
import { useI18n } from '../i18n/index.jsx'

const REFRESH_MS = 30000

export default function NotificationBell() {
  const [items, setItems] = useState([])
  const [open, setOpen] = useState(false)
  const { t, formatDateTime } = useI18n()
  const navigate = useNavigate()
  const location = useLocation()
  const box = useRef(null)
  // Several refreshes can overlap (a page change, a "notifications-changed"
  // event...): only the answer to the latest one is shown, never an older
  // answer that happens to arrive last.
  const latest = useRef(0)

  async function refresh() {
    const asked = ++latest.current
    try {
      const answer = await api.getNotifications()
      if (asked === latest.current) setItems(answer)
    } catch {
      // A failed refresh keeps the last list; the next one will retry.
    }
  }

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, REFRESH_MS)
    window.addEventListener('notifications-changed', refresh)
    return () => {
      clearInterval(timer)
      window.removeEventListener('notifications-changed', refresh)
    }
  }, [])

  // A new page may be the result of acting on a notification.
  useEffect(() => {
    refresh()
    setOpen(false)
  }, [location.pathname])

  // Close when clicking anywhere else.
  useEffect(() => {
    if (!open) return undefined
    const onClick = (event) => {
      if (box.current && !box.current.contains(event.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  function go(item) {
    setOpen(false)
    const where = item.extraction_id ? `/cases/${item.case_id}/review/${item.extraction_id}` : '/'
    // A discussion message opens the case at its discussion.
    navigate(item.kind === 'DISCUSSION' && item.extraction_id ? `${where}#discussion` : where)
  }

  return (
    <span ref={box} className="notif">
      <button
        type="button"
        className={`notif-button${items.length > 0 ? ' primary' : ''}`}
        onClick={() => setOpen((value) => !value)}
        title={t('notifications.button', { count: items.length })}
        aria-label={t('notifications.button', { count: items.length })}
        aria-expanded={open}
      >
        {/* Compact: the bell and the count; the full text is the tooltip. */}
        <span aria-hidden="true">🔔</span>
        <span className="num">{items.length}</span>
      </button>

      {open && (
        <div role="dialog" aria-label={t('notifications.title')} className="notif-panel">
          <strong className="notif-panel-title">{t('notifications.title')}</strong>

          {items.length === 0 ? (
            <p className="muted notif-empty">{t('notifications.empty')}</p>
          ) : (
            items.map((item) => (
              <button
                key={`${item.kind}-${item.case_id}`}
                type="button"
                className="notif-item"
                onClick={() => go(item)}
              >
                <strong>
                  {item.kind === 'SUBMITTED'
                    ? t('notifications.submitted', {
                        name: item.author || item.analyst || t('sup.unassigned'),
                        client: item.client,
                        year: item.fiscal_year,
                      })
                    : item.kind === 'DISCUSSION'
                    ? t('notifications.discussion', {
                        count: item.count,
                        name: item.author,
                        client: item.client,
                        year: item.fiscal_year,
                      })
                    : t('notifications.correction', {
                        name: item.author,
                        client: item.client,
                        year: item.fiscal_year,
                      })}
                </strong>
                {item.message && <span className="muted">“{item.message}”</span>}
                <span className="faint">{formatDateTime(item.at)}</span>
              </button>
            ))
          )}
        </div>
      )}
    </span>
  )
}