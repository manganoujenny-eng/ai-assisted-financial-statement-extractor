/* My account — who I am, my name, and my password (item 5).
 *
 * Every user manages their own account here. For a supervisor this is the
 * only place: supervisor accounts are created in the database with a
 * temporary password (backend/create_supervisor.py), and no other
 * supervisor can change them — so the first thing a new supervisor does is
 * sign in and replace that temporary password here.
 */

import { useState } from 'react'
import * as api from '../api/client.js'
import { useI18n } from '../i18n/index.jsx'

function NameForm({ user, onUpdated }) {
  const [name, setName] = useState(user.full_name)
  const [message, setMessage] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const { t } = useI18n()

  async function submit(event) {
    event.preventDefault()
    try {
      setBusy(true)
      setError(null)
      setMessage(null)
      const me = await api.updateMe(name.trim())
      onUpdated?.(me)
      setMessage(t('account.nameChanged'))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card" onSubmit={submit} style={{ maxWidth: 420 }}>
      <h3 style={{ marginTop: 0 }}>{t('account.detailsTitle')}</h3>
      <label style={{ display: 'block', marginBottom: 12 }}>
        {t('users.fullName')}
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          style={{ display: 'block', width: '100%' }}
          required
        />
      </label>
      <p className="faint" style={{ marginTop: 0 }}>{t('account.nameHint')}</p>
      {error && <div className="banner fail">{error}</div>}
      {message && <div className="banner info">{message}</div>}
      <button
        type="submit"
        className="primary"
        disabled={busy || !name.trim() || name.trim() === user.full_name}
      >
        {busy ? t('common.saving') : t('common.save')}
      </button>
    </form>
  )
}

export default function AccountPage({ user, onUpdated }) {
  const [form, setForm] = useState({ current: '', next: '', repeat: '' })
  const [message, setMessage] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const { t } = useI18n()

  async function submit(event) {
    event.preventDefault()
    setMessage(null)
    if (form.next !== form.repeat) {
      setError(t('account.differ'))
      return
    }
    try {
      setBusy(true)
      setError(null)
      await api.changePassword(form.current, form.next)
      setForm({ current: '', next: '', repeat: '' })
      setMessage(t('account.changed'))
    } catch (err) {
      setError(err.status === 401 ? t('account.wrongCurrent') : err.message)
    } finally {
      setBusy(false)
    }
  }

  const field = (key, label, autoComplete) => (
    <label style={{ display: 'block', marginBottom: 12 }}>
      {label}
      <input
        type="password"
        autoComplete={autoComplete}
        value={form[key]}
        onChange={(event) => setForm({ ...form, [key]: event.target.value })}
        style={{ display: 'block', width: '100%' }}
        required
      />
    </label>
  )

  return (
    <>
      <h2 className="page-title">{t('nav.account')}</h2>
      <p className="page-subtitle">
        {user.full_name} · {t(`role.${user.role}`)}
        {user.username ? ` · ${t('account.usernameIs', { username: user.username })}` : ''}
      </p>

      {user.auth_required === false ? (
        <div className="banner info">{t('account.authOff')}</div>
      ) : (
        <div className="split">
          <NameForm user={user} onUpdated={onUpdated} />

          <form className="card" onSubmit={submit} style={{ maxWidth: 420 }}>
            <h3 style={{ marginTop: 0 }}>{t('account.changeTitle')}</h3>
            {field('current', t('account.current'), 'current-password')}
            {field('next', t('account.new'), 'new-password')}
            {field('repeat', t('account.repeat'), 'new-password')}
            {error && <div className="banner fail">{error}</div>}
            {message && <div className="banner info">{message}</div>}
            <button type="submit" className="primary" disabled={busy}>
              {busy ? t('common.saving') : t('account.changeButton')}
            </button>
          </form>
        </div>
      )}
    </>
  )
}