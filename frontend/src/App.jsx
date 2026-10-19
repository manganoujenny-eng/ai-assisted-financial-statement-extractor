import { useEffect, useState } from 'react'
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import * as api from './api/client.js'
import CasesPage from './pages/CasesPage.jsx'
import ReviewPage from './pages/ReviewPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'
import MyCasesPage from './pages/MyCasesPage.jsx'
import LoginPage from './pages/LoginPage.jsx'
import AccountPage from './pages/AccountPage.jsx'
import UsersPage from './pages/UsersPage.jsx'
import SupervisorPage from './pages/SupervisorPage.jsx'
import NotificationBell from './components/NotificationBell.jsx'
import BrandMark, { BrandSymbol } from './components/BrandMark.jsx'
import BusyOverlay from './components/BusyOverlay.jsx'
import { LanguageSwitcher, useI18n } from './i18n/index.jsx'

/* Item 5 — nothing is shown until someone is signed in. Who is signed in
 * comes from the backend session (GET /api/auth/me); every action is
 * recorded under that person, and supervisor screens only exist for
 * supervisors (the backend refuses them to anyone else regardless). */
export default function App() {
  const [user, setUser] = useState(undefined) // undefined = still checking
  const [menuOpen, setMenuOpen] = useState(false)
  const { t } = useI18n()
  const navigate = useNavigate()
  const location = useLocation()

  // On a phone the menu folds away; it closes again once a page is chosen.
  useEffect(() => setMenuOpen(false), [location.pathname])

  function signedIn(me) {
    api.setCurrentUser(me)
    setUser(me)
  }

  useEffect(() => {
    api
      .getMe()
      .then(signedIn)
      .catch(() => signedIn(null))

    const onSignedOut = () => signedIn(null)
    window.addEventListener('auth-required', onSignedOut)
    return () => window.removeEventListener('auth-required', onSignedOut)
  }, [])

  async function signOut() {
    try {
      await api.logout()
    } finally {
      signedIn(null)
      navigate('/')
    }
  }

  if (user === undefined) {
    return (
      <div className="app-loading" role="status">
        <BrandSymbol />
        <span><span className="spinner" /> {t('common.loading')}</span>
      </div>
    )
  }

  if (user === null) {
    return <LoginPage onSignedIn={signedIn} />
  }

  const supervisor = user.role === 'SUPERVISOR'

  return (
    <>
      <header className={`app-header${menuOpen ? ' open' : ''}`}>
        <div className="app-header-inner">
          <Link to="/" className="brand-link" aria-label="EB-PARTNERS AUDIT">
            <BrandMark />
          </Link>
          <div className="product">
            <h1>{t('app.title')}</h1>
            <span className="sub">{t('app.subtitle')}</span>
          </div>

          <button
            type="button"
            className="nav-toggle"
            aria-label="Menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((value) => !value)}
          >
            {menuOpen ? '✕' : '☰'}
          </button>

          <nav className="app-nav">
            <NavLink to="/" end>{t('nav.cases')}</NavLink>
            <NavLink to="/my-cases">{t('nav.myCases')}</NavLink>
            {supervisor && <NavLink to="/supervisor">{t('nav.supervisor')}</NavLink>}
            {supervisor && <NavLink to="/users">{t('nav.users')}</NavLink>}
          </nav>

          <div className="app-tools">
            <NotificationBell />
            <LanguageSwitcher />
            <NavLink to="/account" className="user-chip" title={t('nav.account')}>
              <span className="user-avatar" aria-hidden="true">{initials(user.full_name)}</span>
              <strong>{user.full_name}</strong>
              <span className={`pill ${supervisor ? 'accent' : 'neutral'}`}>
                {t(`role.${user.role}`)}
              </span>
            </NavLink>
            {user.auth_required !== false && (
              <button type="button" onClick={signOut}>
                {t('nav.signOut')}
              </button>
            )}
          </div>
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<CasesPage />} />
          <Route path="/my-cases" element={<MyCasesPage />} />
          <Route path="/account" element={<AccountPage user={user} />} />
          <Route
            path="/supervisor"
            element={supervisor ? <SupervisorPage /> : <Navigate to="/" replace />}
          />
          <Route
            path="/users"
            element={supervisor ? <UsersPage currentUser={user} /> : <Navigate to="/" replace />}
          />
          <Route path="/cases/:caseId/review/:extractionId" element={<ReviewPage />} />
          <Route path="/cases/:caseId/dashboard" element={<DashboardPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <BusyOverlay />
    </>
  )
}

/* "Helena Ngo" -> "HN", for the round badge next to the name. */
function initials(name) {
  const parts = String(name || '').trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  const first = parts[0][0]
  const last = parts.length > 1 ? parts[parts.length - 1][0] : ''
  return (first + last).toUpperCase()
}