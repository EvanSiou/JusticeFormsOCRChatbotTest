import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'

const navItems = [
  { path: '/', label: 'Dashboard', icon: '🏠' },
  { path: '/forms', label: 'Manage Forms', icon: '📄' },
  { path: '/synthetic', label: 'Generate Data', icon: '🔄' },
  { path: '/data', label: 'View Data', icon: '👁️' },
  { path: '/tests', label: 'Run Tests', icon: '▶️' },
  { path: '/clean', label: 'Clean Document', icon: '🧹' },
  { path: '/verify', label: 'Verify Results', icon: '✅' },
  { path: '/results', label: 'View Results', icon: '📊' },
  { path: '/prompts', label: 'Prompts', icon: '📝' },
  { path: '/classify', label: 'Classify', icon: '🏷️' },
  { path: '/classify-verify', label: 'Verify Classification', icon: '🔍' },
  { path: '/metrics', label: 'Metrics', icon: '📈' },
]

function Layout() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center py-4">
            <div className="flex-1" />
            <h1 className="text-xl font-bold text-gray-900 text-center">
              Form OCR Testing
            </h1>
            <div className="flex-1 flex justify-end items-center gap-4">
              <span className="text-sm text-gray-600">
                {user?.email}
              </span>
              <button
                onClick={handleLogout}
                className="text-sm text-red-600 hover:text-red-800"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </header>

      <div className="flex">
        {/* Sidebar */}
        <aside className="w-64 bg-white shadow min-h-[calc(100vh-64px)]">
          <nav className="p-4 space-y-2">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === '/'}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                    isActive
                      ? 'bg-blue-100 text-blue-700'
                      : 'text-gray-700 hover:bg-gray-100'
                  }`
                }
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </NavLink>
            ))}
          </nav>
        </aside>

        {/* Main content */}
        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

export default Layout
