/* The supervisors' discussion of one case (review page and dashboard).
 *
 * What it is for: only the supervisor a case is assigned to acts on it. A
 * supervisor with an opinion on someone else's case opens that case and
 * writes here; the assigned supervisor is told (bell, My cases) and
 * replies. So:
 *   - on someone else's case: you can always write to its supervisor;
 *   - on your own case: you see nothing until another supervisor writes,
 *     and then you reply (nobody writes to themselves);
 *   - before the case has a supervisor: nothing to discuss yet.
 * The backend decides (can_write / why_not); this screen follows it.
 *
 * Each message shows its author. Hover a message (or tap ⋯ on a phone) for
 * Copy, and on your own messages Edit and Delete; the others then see
 * "edited" or "message deleted". While someone types, the others see
 * "X is writing…". The thread refreshes every 3 seconds while the page is
 * visible; opening it marks it read. Enter sends, Shift+Enter is a new line.
 * Data: /api/cases/<id>/discussion (GET, POST, PATCH, DELETE, POST typing).
 */

import { useEffect, useRef, useState } from 'react'
import * as api from '../api/client.js'
import { useI18n } from '../i18n/index.jsx'

const REFRESH_MS = 3000
const TYPING_SIGNAL_MS = 2500
const MAX_LENGTH = 2000

export default function CaseDiscussion({ caseId }) {
  const [thread, setThread] = useState(null)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [editing, setEditing] = useState(null) // { id, text }
  const [confirmDelete, setConfirmDelete] = useState(null) // message id
  const [openMenu, setOpenMenu] = useState(null) // message id (touch screens)
  const [copied, setCopied] = useState(null) // message id
  const list = useRef(null)
  const lastTypingSignal = useRef(0)
  const seenCount = useRef(null)
  const { t, formatDateTime } = useI18n()

  async function load() {
    try {
      const answer = await api.getDiscussion(caseId)
      setThread(answer)
      setError(null)
      // Tell the bell when something new was read.
      const count = answer.messages.length
      if (seenCount.current !== count) {
        seenCount.current = count
        window.dispatchEvent(new Event('notifications-changed'))
      }
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    seenCount.current = null
    load()
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') load()
    }, REFRESH_MS)
    return () => clearInterval(timer)
  }, [caseId])

  // Arrived from the bell or My cases (…#discussion): bring it into view.
  const loaded = thread !== null
  useEffect(() => {
    if (loaded && window.location.hash === '#discussion') {
      document.getElementById('discussion')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [loaded])

  // Keep the newest message in view when one arrives.
  const messageCount = thread?.messages.length ?? 0
  useEffect(() => {
    if (list.current) list.current.scrollTop = list.current.scrollHeight
  }, [messageCount])

  function signalTyping() {
    const now = Date.now()
    if (now - lastTypingSignal.current < TYPING_SIGNAL_MS) return
    lastTypingSignal.current = now
    api.discussionTyping(caseId).catch(() => {}) // a hint only: never an error
  }

  async function send(event) {
    event?.preventDefault()
    const message = text.trim()
    if (!message || busy) return
    try {
      setBusy(true)
      setError(null)
      const posted = await api.postDiscussion(caseId, message)
      setThread((current) => ({
        ...current,
        can_write: true,
        why_not: null,
        messages: [...(current?.messages || []), posted],
      }))
      seenCount.current = (seenCount.current ?? 0) + 1
      setText('')
      lastTypingSignal.current = 0
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function saveEdit() {
    const message = editing?.text.trim()
    if (!message) return
    try {
      setBusy(true)
      const saved = await api.editDiscussionMessage(caseId, editing.id, message)
      setThread((current) => ({
        ...current,
        messages: current.messages.map((m) => (m.id === saved.id ? saved : m)),
      }))
      setEditing(null)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function remove(id, scope) {
    try {
      setBusy(true)
      await api.deleteDiscussionMessage(caseId, id, scope)
      setConfirmDelete(null)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function copy(message) {
    try {
      await navigator.clipboard.writeText(message.message)
    } catch {
      // Older browsers / no permission: the classic way.
      const area = document.createElement('textarea')
      area.value = message.message
      document.body.appendChild(area)
      area.select()
      document.execCommand('copy')
      area.remove()
    }
    setCopied(message.id)
    setTimeout(() => setCopied((current) => (current === message.id ? null : current)), 1500)
  }

  if (thread === null) {
    return (
      <section className="card discussion">
        <h2 style={{ margin: 0 }}>{t('disc.title')}</h2>
        {error ? <div className="banner fail">{error}</div> : <p className="muted">{t('common.loading')}</p>}
      </section>
    )
  }

  const me = api.getAnalystName()
  const supervisor = thread.assigned_to
  const myCase = thread.why_not === 'WAIT_FOR_MESSAGE' ||
    (supervisor && sameName(supervisor, me))
  const subtitle = !supervisor
    ? t('disc.noSupervisor')
    : myCase
      ? t('disc.helpMine')
      : t('disc.helpOther', { name: supervisor })
  const visible = thread.messages
  const typing = thread.typing || []

  return (
    <section id="discussion" className="card discussion" aria-labelledby={`discussion-${caseId}`}>
      <div className="discussion-head">
        <div>
          <h2 id={`discussion-${caseId}`} style={{ margin: 0 }}>{t('disc.title')}</h2>
          <p className="muted" style={{ margin: '4px 0 0' }}>{subtitle}</p>
        </div>
        {visible.length > 0 && (
          <span className="pill neutral">{t('disc.count', { count: visible.length })}</span>
        )}
      </div>

      {error && <div className="banner fail">{error}</div>}

      {visible.length === 0 ? (
        <p className="faint discussion-empty-note">
          {!supervisor
            ? t('disc.emptyNoSupervisor')
            : myCase
              ? t('disc.emptyMine')
              : t('disc.emptyOther', { name: supervisor })}
        </p>
      ) : (
        <div className="discussion-list" ref={list} aria-live="polite">
          {visible.map((m) => {
            const isEditing = editing?.id === m.id
            return (
              <div
                key={m.id}
                className={
                  'discussion-message' +
                  (m.mine ? ' mine' : '') +
                  (m.deleted ? ' deleted' : '') +
                  (openMenu === m.id ? ' menu-open' : '')
                }
              >
                <div className="discussion-meta">
                  <strong>{m.mine ? t('disc.you') : m.author}</strong>
                  <span className="faint">{formatDateTime(m.at)}</span>
                  {m.edited_at && !m.deleted && <span className="faint">· {t('disc.edited')}</span>}
                </div>

                {m.deleted ? (
                  <p className="discussion-deleted">
                    {m.mine ? t('disc.deletedMine') : t('disc.deletedOther', { name: m.author })}
                  </p>
                ) : isEditing ? (
                  <div className="discussion-edit">
                    <textarea
                      value={editing.text}
                      rows={2}
                      maxLength={MAX_LENGTH}
                      autoFocus
                      aria-label={t('disc.edit')}
                      onChange={(event) => {
                        setEditing({ ...editing, text: event.target.value })
                        signalTyping()
                      }}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' && !event.shiftKey) {
                          event.preventDefault()
                          saveEdit()
                        }
                        if (event.key === 'Escape') setEditing(null)
                      }}
                    />
                    <div className="discussion-edit-buttons">
                      <button type="button" onClick={() => setEditing(null)} disabled={busy}>
                        {t('common.cancel')}
                      </button>
                      <button
                        type="button"
                        className="primary"
                        onClick={saveEdit}
                        disabled={busy || !editing.text.trim()}
                      >
                        {t('disc.save')}
                      </button>
                    </div>
                  </div>
                ) : (
                  <p>{m.message}</p>
                )}

                {confirmDelete === m.id && (
                  <div className="discussion-confirm" role="alert">
                    <span>
                      {m.mine && !m.deleted ? t('disc.confirmDelete') : t('disc.confirmDeleteForMe')}
                    </span>
                    <button type="button" onClick={() => setConfirmDelete(null)} disabled={busy}>
                      {t('common.cancel')}
                    </button>
                    <button type="button" onClick={() => remove(m.id, 'me')} disabled={busy}>
                      {t('disc.deleteForMe')}
                    </button>
                    {m.mine && !m.deleted && (
                      <button type="button" className="danger" onClick={() => remove(m.id, 'everyone')} disabled={busy}>
                        {t('disc.deleteForEveryone')}
                      </button>
                    )}
                  </div>
                )}

                {!isEditing && confirmDelete !== m.id && (
                  <>
                    <button
                      type="button"
                      className="discussion-more"
                      aria-label={t('disc.actions')}
                      aria-expanded={openMenu === m.id}
                      onClick={() => setOpenMenu(openMenu === m.id ? null : m.id)}
                    >
                      ⋯
                    </button>
                    <div className="discussion-actions">
                      {!m.deleted && (
                        <button type="button" onClick={() => copy(m)} title={t('disc.copy')}>
                          <span aria-hidden="true">⧉</span>{' '}
                          {copied === m.id ? t('disc.copied') : t('disc.copy')}
                        </button>
                      )}
                      {m.mine && !m.deleted && (
                        <button
                          type="button"
                          onClick={() => {
                            setOpenMenu(null)
                            setEditing({ id: m.id, text: m.message })
                          }}
                          title={t('disc.edit')}
                        >
                          <span aria-hidden="true">✎</span> {t('disc.edit')}
                        </button>
                      )}
                      <button
                        type="button"
                        className="discussion-delete"
                        onClick={() => {
                          setOpenMenu(null)
                          setConfirmDelete(m.id)
                        }}
                        title={t('disc.delete')}
                      >
                        <span aria-hidden="true">🗑</span> {t('disc.delete')}
                      </button>
                    </div>
                  </>
                )}
              </div>
            )
          })}
        </div>
      )}

      <p className="discussion-typing" aria-live="polite">
        {typing.length === 1 && (
          <>{t('disc.typingOne', { name: typing[0] })} <span className="typing-dots"><i /><i /><i /></span></>
        )}
        {typing.length > 1 && (
          <>{t('disc.typingMany', { names: typing.join(', ') })} <span className="typing-dots"><i /><i /><i /></span></>
        )}
      </p>

      {thread.can_write ? (
        <>
          <form className="discussion-form" onSubmit={send}>
            <textarea
              value={text}
              rows={2}
              maxLength={MAX_LENGTH}
              placeholder={
                myCase ? t('disc.placeholderReply') : t('disc.placeholderOther', { name: supervisor })
              }
              aria-label={t('disc.placeholderReply')}
              onChange={(event) => {
                setText(event.target.value)
                if (event.target.value.trim()) signalTyping()
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) send(event)
              }}
            />
            <button type="submit" className="primary" disabled={busy || !text.trim()}>
              {busy ? t('disc.sending') : myCase ? t('disc.reply') : t('disc.send')}
            </button>
          </form>
          <p className="faint discussion-hint">{t('disc.hint')}</p>
        </>
      ) : thread.why_not === 'WAIT_FOR_MESSAGE' ? (
        <p className="faint discussion-hint">{t('disc.waitHint')}</p>
      ) : null}
    </section>
  )
}

function sameName(a, b) {
  const norm = (s) => (s || '').trim().replace(/\s+/g, ' ').toLowerCase()
  return norm(a) === norm(b)
}