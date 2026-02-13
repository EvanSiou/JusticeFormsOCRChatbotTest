import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import ManageFormsPage from './pages/ManageFormsPage'
import SyntheticDataPage from './pages/SyntheticDataPage'
import RunTestsPage from './pages/RunTestsPage'
import ResultsPage from './pages/ResultsPage'
import VerifyPage from './pages/VerifyPage'
import ViewDataPage from './pages/ViewDataPage'
import MetricsPage from './pages/MetricsPage'
import CleanDocumentPage from './pages/CleanDocumentPage'
import ClassifyPage from './pages/ClassifyPage'
import Layout from './components/Layout/Layout'

// Protected route wrapper
function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-lg">Loading...</div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return children
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="forms" element={<ManageFormsPage />} />
        <Route path="synthetic" element={<SyntheticDataPage />} />
        <Route path="data" element={<ViewDataPage />} />
        <Route path="tests" element={<RunTestsPage />} />
        <Route path="clean" element={<CleanDocumentPage />} />
        <Route path="verify" element={<VerifyPage />} />
        <Route path="verify/:testRunId" element={<VerifyPage />} />
        <Route path="results" element={<ResultsPage />} />
        <Route path="results/:testRunId" element={<ResultsPage />} />
        <Route path="classify" element={<ClassifyPage />} />
        <Route path="metrics" element={<MetricsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
