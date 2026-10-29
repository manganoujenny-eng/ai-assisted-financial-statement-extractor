/* Users — supervisors and the administrator.
 *
 * A supervisor manages ANALYSTS: add one, rename, reset a forgotten
 * password, deactivate / reactivate (a deactivated user cannot sign in and
 * is signed out at once; their cases and every record they signed stay),
 * and delete one who owns no case yet.
 *
 * The administrator does the same for SUPERVISORS too: add one (choosing
 * the role when the account is created), rename, reset, deactivate,
 * reactivate, delete — never the last active supervisor.
 *
 * The super administrator (exactly one, created once with
 * backend/create_superadmin.py) does the same for ADMINISTRATORS too.
 * An administrator never manages another administrator, and nobody manages
 * the super administrator here. Every user manages their own name and
 * password on My account. The backend refuses the same things (409), so
 * hiding the buttons only keeps the page honest.
 */

import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import * as api from '../api/client.js'
import DangerDialog from '../components/DangerDialog.jsx'
import { useI18n } from '../i18n/index.jsx'

const EMPTY = { username: '', full_name: '', password: '', role: 'ANALYST' }

/* May the signed-in person change this account? */
function canManage(viewer, user) {
  if (user.id === viewer.id) return false // their own: My account
  if (user.role === 'SUPERADMIN') return false
  if (user.role === 'ADMIN') return viewer.role === 'SUPERADMIN'
  if (user.role === 'SUPERVISOR') return ['ADMIN', 'SUPERADMIN'].includes(viewer.role)
  return true // an analyst: supervisor or administrator
}

function UserRow({ user, viewer, onSaved, onError, onDelete }) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ full_name: user.full_name, password: '' })
  const [busy, setBusy] = useState(false)
  const { t } = useI18n()
  const isMe = user.id === viewer.id
  const manageable = canManage(viewer, user)

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
          <span className="pill neutral">{t(`role.${user.role}`)}</span>
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
        <span className={`pill ${user.role === 'ANALYST' ? 'neutral' : 'accent'}`}>
          {t(`role.${user.role}`)}
        </span>
      </td>
      <td>{user.active ? t('users.active') : t('users.deactivated')}</td>
      <td>
        {isMe ? (
          <Link className="button-like" to="/account">{t('nav.account')}</Link>
        ) : !manageable ? (
          <span className="faint">{t('users.supervisorManagedElsewhere')}</span>
        ) : (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <button type="button" disabled={busy} onClick={() => setEditing(true)}>
              {t('users.editReset')}
            </button>
            <button type="button" disabled={busy} onClick={() => save({ active: !user.active })}>
              {user.active ? t('users.deactivate') : t('users.reactivate')}
            </button>
            <button type="button" disabled={busy} onClick={() => onDelete(user)}>
              {t('common.delete')}
            </button>
          </div>
        )}
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
  const [roleFilter, setRoleFilter] = useState('')
  const [search, setSearch] = useState('')
  // The account waiting for the delete confirmation, or null.
  const [pendingDelete, setPendingDelete] = useState(null)
  const { t } = useI18n()
  const superadmin = currentUser.role === 'SUPERADMIN'
  const admin = currentUser.role === 'ADMIN' || superadmin

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

  const shown = useMemo(() => {
    const wanted = search.trim().toLowerCase()
    return (users || []).filter(
      (user) =>
        (!roleFilter || user.role === roleFilter) &&
        (!wanted ||
          user.full_name.toLowerCase().includes(wanted) ||
          user.username.toLowerCase().includes(wanted))
    )
  }, [users, roleFilter, search])

  async function create(event) {
    event.preventDefault()
    try {
      setBusy(true)
      setError(null)
      const user = await api.createUser(admin ? form : { ...form, role: 'ANALYST' })
      setForm(EMPTY)
      setMessage(t('users.created', { name: user.full_name, username: user.username }))
      await reload()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function confirmDelete() {
    const user = pendingDelete.user
    try {
      setPendingDelete({ ...pendingDelete, working: true, error: null })
      await api.deleteUser(user.id)
      setPendingDelete(null)
      setMessage(t('users.deleted', { name: user.full_name }))
      await reload()
    } catch (err) {
      setPendingDelete({ ...pendingDelete, working: false, error: err.message })
    }
  }

  return (
    <>
      <h2 className="page-title">{t('nav.users')}</h2>
      <p className="page-subtitle">
        {superadmin
          ? t('users.subtitleSuperadmin')
          : admin
            ? t('users.subtitleAdmin')
            : t('users.subtitleAnalysts')}
      </p>

      {error && <div className="banner fail">{error}</div>}
      {message && <div className="banner info">{message}</div>}

      <form className="card" onSubmit={create}>
        <h3 style={{ marginTop: 0 }}>{admin ? t('users.addTitle') : t('users.addAnalystTitle')}</h3>
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
          {admin && (
            <label>
              {t('users.role')}
              <select
                value={form.role}
                onChange={(event) => setForm({ ...form, role: event.target.value })}
                style={{ display: 'block', width: '100%' }}
              >
                <option value="ANALYST">{t('users.analyst')}</option>
                <option value="SUPERVISOR">{t('users.supervisor')}</option>
                {superadmin && <option value="ADMIN">{t('users.administrator')}</option>}
              </select>
            </label>
          )}
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
            {busy ? t('addItem.adding') : admin ? t('users.add') : t('users.addAnalyst')}
          </button>
        </div>
        <p className="faint" style={{ margin: '12px 0 0' }}>
          {admin ? t('users.adminNote') : t('users.supervisorsNoteAdmin')}
          {superadmin && <> {t('users.superadminNote')}</>}
        </p>
      </form>

      <div className="card">
        <div className="adm-table-head">
          <select
            value={roleFilter}
            onChange={(event) => setRoleFilter(event.target.value)}
            aria-label={t('users.role')}
            style={{ width: 'auto' }}
          >
            <option value="">{t('users.allRoles')}</option>
            <option value="ANALYST">{t('users.analyst')}</option>
            <option value="SUPERVISOR">{t('users.supervisor')}</option>
            <option value="ADMIN">{t('users.administrator')}</option>
            <option value="SUPERADMIN">{t('users.superadministrator')}</option>
          </select>
          <input
            type="search"
            value={search}
            placeholder={t('users.searchPlaceholder')}
            aria-label={t('users.searchPlaceholder')}
            onChange={(event) => setSearch(event.target.value)}
            className="adm-table-search"
          />
        </div>
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
                {shown.map((user) => (
                  <UserRow
                    key={user.id}
                    user={user}
                    viewer={currentUser}
                    onError={setError}
                    onDelete={(target) => setPendingDelete({ user: target, working: false, error: null })}
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

      {pendingDelete && (
        <DangerDialog
          title={t('users.deleteTitle', { name: pendingDelete.user.full_name })}
          confirmLabel={t('common.delete')}
          workingLabel={t('common.deleting')}
          working={pendingDelete.working}
          onConfirm={confirmDelete}
          onCancel={() => setPendingDelete(null)}
        >
          <p>
            {pendingDelete.user.role === 'SUPERVISOR'
              ? t('users.deleteSupervisorBody')
              : pendingDelete.user.role === 'ADMIN'
                ? t('users.deleteAdminBody')
                : t('users.deleteBody')}
          </p>
          {pendingDelete.error && <div className="banner fail">{pendingDelete.error}</div>}
        </DangerDialog>
      )}
    </>
  )
}