import { useState, useEffect } from 'react'
import { setupAPI } from '../services/api'

export default function SetupPage() {
  const [config, setConfig] = useState({
    quality_threshold: 0.4,
    default_model: 'claude_bedrock',
  })
  const [models, setModels] = useState([])
  const [prompts, setPrompts] = useState([])
  const [systemPrompts, setSystemPrompts] = useState([])
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    setupAPI.getConfig().then((r) => setConfig(r.data)).catch(() => {})
    setupAPI.listModels().then((r) => setModels(r.data.models || [])).catch(() => {})
    setupAPI.listPrompts().then((r) => setPrompts(r.data.prompts || [])).catch(() => {})
    setupAPI.getSystemPrompts().then((r) => setSystemPrompts(r.data.prompts || [])).catch(() => {})
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      await setupAPI.updateConfig(config)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      alert('Save failed: ' + (e.response?.data?.detail || e.message))
    }
    setSaving(false)
  }

  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-800 mb-6">Setup</h2>

      <div className="space-y-6">
        {/* Quality Threshold */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-700 mb-4">
            Page Quality Threshold
          </h3>
          <div className="flex items-center gap-4">
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={config.quality_threshold}
              onChange={(e) =>
                setConfig({ ...config, quality_threshold: parseFloat(e.target.value) })
              }
              className="flex-1"
            />
            <span className="text-lg font-mono font-bold text-blue-600 w-16 text-right">
              {(config.quality_threshold * 100).toFixed(0)}%
            </span>
          </div>
          <p className="text-sm text-gray-500 mt-2">
            Pages scoring below this threshold will require manual approval to proceed.
          </p>
        </div>

        {/* Model Selector */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-700 mb-4">
            OCR / Classification Model
          </h3>
          <select
            value={config.default_model}
            onChange={(e) =>
              setConfig({ ...config, default_model: e.target.value })
            }
            className="w-full border border-gray-300 rounded-md px-3 py-2"
          >
            {models.length > 0 ? (
              models.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))
            ) : (
              <option value="claude_bedrock">claude_bedrock</option>
            )}
          </select>
        </div>

        {/* System Prompts (read-only) */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-700 mb-4">
            System Prompts
          </h3>
          <p className="text-sm text-gray-500 mb-4">
            Built-in prompts used by the processing pipeline. These are read-only.
          </p>
          {systemPrompts.map((p, i) => (
            <div key={i} className="border rounded-md p-3 mb-3">
              <div className="flex justify-between items-center mb-2">
                <span className="font-medium text-sm">{p.name}</span>
                <span className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded">
                  {p.prompt_type}
                </span>
              </div>
              <p className="text-xs text-gray-500 mb-2">{p.description}</p>
              <textarea
                value={p.prompt_text}
                readOnly
                rows={10}
                className="w-full border border-gray-200 rounded text-sm p-2 font-mono bg-gray-50"
              />
            </div>
          ))}
        </div>

        {/* Custom Prompts */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold text-gray-700 mb-4">
            Custom Prompts
          </h3>
          {prompts.length === 0 ? (
            <p className="text-gray-500">No custom prompts configured. Defaults will be used.</p>
          ) : (
            <div className="space-y-4">
              {prompts.map((p) => (
                <div key={p.prompt_id || p.id} className="border rounded-md p-3">
                  <div className="flex justify-between items-center mb-2">
                    <span className="font-medium text-sm">{p.name}</span>
                    <span className="text-xs px-2 py-0.5 bg-gray-100 rounded">
                      {p.prompt_type}
                    </span>
                  </div>
                  <textarea
                    defaultValue={p.prompt_text}
                    rows={4}
                    className="w-full border border-gray-200 rounded text-sm p-2 font-mono"
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Save */}
        <div className="flex justify-end">
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-6 py-2 bg-blue-600 text-white rounded-md font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? 'Saving...' : saved ? 'Saved!' : 'Save Configuration'}
          </button>
        </div>
      </div>
    </div>
  )
}
