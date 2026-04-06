import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import ProcessingPage from './pages/ProcessingPage'
import SetupPage from './pages/SetupPage'

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50">
        {/* Header */}
        <header className="bg-white border-b border-gray-200 shadow-sm">
          <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
            <h1 className="text-xl font-bold text-gray-800">
              OCR Document Processing
            </h1>
            <nav className="flex gap-1">
              <NavLink
                to="/"
                end
                className={({ isActive }) =>
                  `px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-600 hover:bg-gray-100'
                  }`
                }
              >
                Process
              </NavLink>
              <NavLink
                to="/setup"
                className={({ isActive }) =>
                  `px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-600 hover:bg-gray-100'
                  }`
                }
              >
                Setup
              </NavLink>
            </nav>
          </div>
        </header>

        {/* Content */}
        <main className="max-w-7xl mx-auto px-4 py-6">
          <Routes>
            <Route path="/" element={<ProcessingPage />} />
            <Route path="/setup" element={<SetupPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
