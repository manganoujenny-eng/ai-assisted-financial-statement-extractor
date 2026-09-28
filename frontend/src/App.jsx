import { NavLink, Route, Routes } from 'react-router-dom'
import CasesPage from './pages/CasesPage.jsx'
import ReviewPage from './pages/ReviewPage.jsx'
import DashboardPage from './pages/DashboardPage.jsx'

export default function App() {
  return (
    <>
      <header className="app-header">
        <h1>SYSCOHADA financial analysis</h1>
        <span className="sub">prototype — EB Audit &amp; Advisory</span>
        <nav>
          <NavLink to="/" end>Cases</NavLink>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<CasesPage />} />
          <Route path="/cases/:caseId/review/:extractionId" element={<ReviewPage />} />
          <Route path="/cases/:caseId/dashboard" element={<DashboardPage />} />
        </Routes>
      </main>
    </>
  )
}
