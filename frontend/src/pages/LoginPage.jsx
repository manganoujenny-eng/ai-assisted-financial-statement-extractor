/* Sign in . Username + password, checked by the backend; the
 * session cookie it sets is what identifies the user from then on.
 *
 * Left: the EB-PARTNERS AUDIT brand panel (hidden on small screens).
 * Right: the form, with the brand shown above it on small screens. */

import { useState } from 'react'
import * as api from '../api/client.js'
import { LanguageSwitcher, useI18n } from '../i18n/index.jsx'
import BrandMark, { BrandSymbol } from '../components/BrandMark.jsx'

export default function LoginPage({ onSignedIn }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const { t } = useI18n()

  async function submit(event) {
    event.preventDefault()
    try {
      setBusy(true)
      setError(null)
      await api.login(username.trim(), password)
      onSignedIn(await api.getMe())
    } catch (err) {
      setError(err.status === 401 ? t('login.wrong') : err.message)
      setPassword('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-page">
      <aside className="login-aside">
        <div>
          <BrandSymbol />
          <h2>EB-PARTNERS AUDIT</h2>
          <p className="login-tagline">Audit and Advisory</p>
        </div>
        <p className="login-product">{t('app.title')}</p>
      </aside>

      <div className="login-main">
        <form className="login-form" onSubmit={submit}>
          <div className="login-top">
            <BrandMark />
            <LanguageSwitcher />
          </div>

          <h2 className="page-title">{t('app.title')}</h2>
          <p className="page-subtitle">{t('login.subtitle')}</p>

          <label className="login-field">
            {t('login.username')}
            <input
              autoFocus
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
            />
          </label>

          <label className="login-field">
            {t('login.password')}
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>

          {error && <div className="banner fail">{error}</div>}

          <button type="submit" className="primary" disabled={busy}>
            {busy ? (
              <>
                <span className="spinner spinner-on-brand" /> {t('login.signingIn')}
              </>
            ) : (
              t('login.signIn')
            )}
          </button>

          <p className="faint login-help">{t('login.help')}</p>
        </form>
      </div>
    </div>
  )
}