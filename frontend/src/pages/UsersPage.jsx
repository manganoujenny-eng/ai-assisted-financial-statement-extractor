/* Users — supervisor only .
 *
 * Add an analyst or supervisor, rename, change role, deactivate (a
 * deactivated user cannot sign in and is signed out at once; their cases
 * and every record they signed stay), and reset a forgotten password. The
 * backend refuses removing the last active supervisor or deactivating
 * yourself.
 */

import { useEffect, useState } from 'react'
import * as api from '../api/client.js'
import { useI18n } from '../i18n/index.jsx'

const EMPTY = { username: '', full_name: '', role: 'ANALYST', password: '' }

function UserRow({ user, isMe, onSaved, onError }) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ full_name: user.full_name, role: user.role, password: '' })
  const [busy, setBusy] = useState(false)
  const { t } = useI18n()

  async function save(changes) {
    try {
      setBusy(true)
      onError(null)
      onSaved(await api.updateUser(user.id, changes))
      setEditing(false)
      setForm((current) => ({ ...current, password: '' }))
    } catch (err) {
      onError(err.message)
    } finally {
      setBusy(false)
    }
  }

  if (editing) {
    return (
      <tr>
        <td>{user.username}</td>
        <td>
          <input
            value={form.full_name}
            onChange={(event) => setForm({ ...form, full_name: event.target.value })}
          />
        </td>
        <td>
          <select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}>
            <option value="ANALYST">{t('users.analyst')}</option>
            <option value="SUPERVISOR">{t('users.supervisor')}</option>
          </select>
        </td>
        <td>
          <input
            type="password"
            placeholder={t('users.newPasswordOptional')}
            autoComplete="new-password"
            value={form.password}
            onChange={(event) => setForm({ ...form, password: event.target.value })}
          />
        </td>
        <td>
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              type="button"
              className="primary"
              disabled={busy}
              onClick={() =>
                save({
                  full_name: form.full_name,
                  role: form.role,
                  ...(form.password ? { password: form.password } : {}),
                })
              }
            >
              {t('common.save')}
            </button>
            <button type="button" disabled={busy} onClick={() => setEditing(false)}>
              {t('common.cancel')}
            </button>
          </div>
        </td>
      </tr>
    )
  }

  return (
    <tr style={user.active ? undefined : { opacity: 0.55 }}>
      <td>{user.username}</td>
      <td>
        <strong>{user.full_name}</strong>
        {isMe && <span className="faint"> ({t('users.you')})</span>}
      </td>
      <td>
        <span className={`pill ${user.role === 'SUPERVISOR' ? 'accent' : 'neutral'}`}>
          {t(`role.${user.role}`)}
        </span>
      </td>
      <td>{user.active ? t('users.active') : t('users.deactivated')}</td>
      <td>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <button type="button" disabled={busy} onClick={() => setEditing(true)}>
            {t('users.editReset')}
          </button>
          {!isMe && (
            <button type="button" disabled={busy} onClick={() => save({ active: !user.active })}>
              {user.active ? t('users.deactivate') : t('users.reactivate')}
            </button>
          )}
        </div>
      </td>
    </tr>
  )
}

export default function UsersPage({ currentUser }) {
  const [users, setUsers] = useState(null)
  const [form, setForm] = useState(EMPTY)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)
  const { t } = useI18n()

  async function reload() {
    try {
      setUsers(await api.listUsers())
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => {
    reload()
  }, [])

  useEffect(() => {
    if (!message) return undefined
    const timer = setTimeout(() => setMessage(null), 5000)
    return () => clearTimeout(timer)
  }, [message])

  async function create(event) {
    event.preventDefault()
    try {
      setBusy(true)
      setError(null)
      const user = await api.createUser(form)
      setForm(EMPTY)
      setMessage(t('users.created', { name: user.full_name, username: user.username }))
      await reload()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <h2 className="page-title">{t('nav.users')}</h2>
      <p className="page-subtitle">
        {t('users.subtitle')}
      </p>

      {error && <div className="banner fail">{error}</div>}
      {message && <div className="banner info">{message}</div>}

      <form className="card" onSubmit={create}>
        <h3 style={{ marginTop: 0 }}>{t('users.addTitle')}</h3>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
            gap: 10,
            alignItems: 'end',
          }}
        >
          <label>
            {t('users.usernameSignIn')}
            <input
              value={form.username}
              autoComplete="off"
              onChange={(event) => setForm({ ...form, username: event.target.value.replace(/\s/g, '') })}
              style={{ display: 'block', width: '100%' }}
              required
            />
          </label>
          <label>
            {t('users.fullName')}
            <input
              value={form.full_name}
              onChange={(event) => setForm({ ...form, full_name: event.target.value })}
              style={{ display: 'block', width: '100%' }}
              required
            />
          </label>
          <label>
            {t('users.role')}
            <select
              value={form.role}
              onChange={(event) => setForm({ ...form, role: event.target.value })}
              style={{ display: 'block', width: '100%' }}
            >
              <option value="ANALYST">{t('users.analyst')}</option>
              <option value="SUPERVISOR">{t('users.supervisor')}</option>
            </select>
          </label>
          <label>
            {t('users.firstPassword')}
            <input
              type="password"
              autoComplete="new-password"
              value={form.password}
              onChange={(event) => setForm({ ...form, password: event.target.value })}
              style={{ display: 'block', width: '100%' }}
              required
              minLength={8}
            />
          </label>
          <button type="submit" className="primary" disabled={busy}>
            {busy ? t('addItem.adding') : t('users.add')}
          </button>
        </div>
      </form>

      <div className="card">
        {users === null ? (
          <p className="muted">{t('common.loading')}</p>
        ) : (
          <div className="fields-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>{t('login.username')}</th>
                  <th>{t('users.fullName')}</th>
                  <th>{t('users.role')}</th>
                  <th>{t('users.status')}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <UserRow
                    key={user.id}
                    user={user}
                    isMe={user.id === currentUser.id}
                    onError={setError}
                    onSaved={(saved) => {
                      setMessage(t('users.updated', { name: saved.full_name }))
                      reload()
                    }}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}