import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { promptsAPI } from '../services/api'

function PromptsPage() {
  const [activeTab, setActiveTab] = useState('ocr')
  const [editingPrompt, setEditingPrompt] = useState(null) // null | 'new' | prompt object
  const [formName, setFormName] = useState('')
  const [formText, setFormText] = useState('')

  const queryClient = useQueryClient()

  // Fetch prompts for active tab
  const { data: promptsData, isLoading } = useQuery({
    queryKey: ['prompts', activeTab],
    queryFn: () => promptsAPI.list(activeTab),
  })

  // Fetch default prompts
  const { data: defaultsData } = useQuery({
    queryKey: ['prompt-defaults'],
    queryFn: () => promptsAPI.getDefaults(),
  })

  const prompts = promptsData?.data || []
  const defaults = defaultsData?.data || {}
  const defaultPromptText = activeTab === 'ocr' ? defaults.ocr : defaults.classification

  // Create mutation
  const createMutation = useMutation({
    mutationFn: (data) => promptsAPI.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries(['prompts', activeTab])
      resetForm()
    },
  })

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }) => promptsAPI.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries(['prompts', activeTab])
      resetForm()
    },
  })

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (id) => promptsAPI.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries(['prompts', activeTab])
    },
  })

  const resetForm = () => {
    setEditingPrompt(null)
    setFormName('')
    setFormText('')
  }

  const startCreate = () => {
    setEditingPrompt('new')
    setFormName('')
    setFormText('')
  }

  const startEdit = (prompt) => {
    setEditingPrompt(prompt)
    setFormName(prompt.name)
    setFormText(prompt.prompt_text)
  }

  const handleSave = () => {
    if (!formName.trim() || !formText.trim()) return

    if (editingPrompt === 'new') {
      createMutation.mutate({
        name: formName.trim(),
        prompt_type: activeTab,
        prompt_text: formText,
      })
    } else {
      updateMutation.mutate({
        id: editingPrompt.id,
        data: {
          name: formName.trim(),
          prompt_text: formText,
        },
      })
    }
  }

  const handleDelete = (prompt) => {
    if (window.confirm(`Delete prompt "${prompt.name}"?`)) {
      deleteMutation.mutate(prompt.id)
    }
  }

  const isSaving = createMutation.isPending || updateMutation.isPending

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Prompts</h2>

      {/* Tabs */}
      <div className="flex gap-1 mb-6">
        <button
          onClick={() => { setActiveTab('ocr'); resetForm() }}
          className={`px-4 py-2 rounded-t-lg font-medium text-sm ${
            activeTab === 'ocr'
              ? 'bg-white shadow text-blue-700 border-b-2 border-blue-500'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          OCR Prompts
        </button>
        <button
          onClick={() => { setActiveTab('classification'); resetForm() }}
          className={`px-4 py-2 rounded-t-lg font-medium text-sm ${
            activeTab === 'classification'
              ? 'bg-white shadow text-blue-700 border-b-2 border-blue-500'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          Classification Prompts
        </button>
      </div>

      {/* Default Prompt */}
      <div className="bg-white rounded-lg shadow p-4 mb-4">
        <details>
          <summary className="cursor-pointer font-medium text-sm flex items-center gap-2">
            <span className="px-2 py-0.5 bg-gray-200 text-gray-600 rounded text-xs">Default</span>
            Default {activeTab === 'ocr' ? 'OCR' : 'Classification'} Prompt
            <span className="text-xs text-gray-400 ml-auto">Click to expand</span>
          </summary>
          <pre className="mt-3 bg-gray-50 border rounded p-3 text-xs whitespace-pre-wrap font-mono max-h-[300px] overflow-y-auto">
            {defaultPromptText || 'Loading...'}
          </pre>
        </details>
      </div>

      {/* Custom Prompts List */}
      <div className="bg-white rounded-lg shadow p-4 mb-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-sm">Custom Prompts</h3>
          {editingPrompt === null && (
            <button
              onClick={startCreate}
              className="px-3 py-1.5 bg-blue-600 text-white rounded text-sm hover:bg-blue-700"
            >
              + Create New
            </button>
          )}
        </div>

        {isLoading ? (
          <p className="text-gray-500 text-sm">Loading...</p>
        ) : prompts.filter(p => !p.is_default).length === 0 ? (
          <p className="text-gray-500 text-sm">No custom prompts yet. Create one to get started.</p>
        ) : (
          <div className="space-y-2">
            {prompts.filter(p => !p.is_default).map((prompt) => (
              <div key={prompt.id} className="border rounded p-3 flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm">{prompt.name}</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    by {prompt.created_by_name || 'unknown'} · {new Date(prompt.created_at).toLocaleDateString()}
                    {prompt.updated_at && ` · updated ${new Date(prompt.updated_at).toLocaleDateString()}`}
                  </p>
                  <pre className="mt-1 text-xs text-gray-600 truncate max-w-full">{prompt.prompt_text.slice(0, 120)}...</pre>
                </div>
                <div className="flex gap-1 flex-shrink-0">
                  <button
                    onClick={() => startEdit(prompt)}
                    className="px-2 py-1 text-xs bg-gray-100 text-gray-700 rounded hover:bg-gray-200"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDelete(prompt)}
                    disabled={deleteMutation.isPending}
                    className="px-2 py-1 text-xs bg-red-50 text-red-600 rounded hover:bg-red-100"
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create/Edit Form */}
      {editingPrompt !== null && (
        <div className="bg-white rounded-lg shadow p-4">
          <h3 className="font-semibold text-sm mb-3">
            {editingPrompt === 'new' ? 'Create New Prompt' : `Edit: ${editingPrompt.name}`}
          </h3>

          <div className="mb-3">
            <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
            <input
              type="text"
              value={formName}
              onChange={(e) => setFormName(e.target.value)}
              className="w-full px-3 py-2 border rounded-md text-sm"
              placeholder="e.g., Detailed OCR v2"
            />
          </div>

          <div className="mb-3">
            <label className="block text-sm font-medium text-gray-700 mb-1">Prompt Text</label>
            <textarea
              value={formText}
              onChange={(e) => setFormText(e.target.value)}
              className="w-full px-3 py-2 border rounded-md text-sm font-mono min-h-[200px]"
              placeholder={activeTab === 'ocr'
                ? "Enter your OCR prompt..."
                : "Enter your classification prompt. Use {field_types} and {ocr_text} as placeholders."
              }
            />
            {activeTab === 'classification' && (
              <p className="text-xs text-gray-500 mt-1">
                Use <code className="bg-gray-100 px-1 rounded">{'{field_types}'}</code> where the list of field types should be injected, and <code className="bg-gray-100 px-1 rounded">{'{ocr_text}'}</code> where the OCR text should be injected.
              </p>
            )}
          </div>

          <div className="flex gap-2">
            <button
              onClick={handleSave}
              disabled={isSaving || !formName.trim() || !formText.trim()}
              className="px-4 py-2 bg-green-600 text-white rounded text-sm hover:bg-green-700 disabled:opacity-50"
            >
              {isSaving ? 'Saving...' : 'Save'}
            </button>
            <button
              onClick={resetForm}
              className="px-4 py-2 bg-gray-100 text-gray-700 rounded text-sm hover:bg-gray-200"
            >
              Cancel
            </button>
          </div>

          {(createMutation.isError || updateMutation.isError) && (
            <p className="text-red-600 text-sm mt-2">
              {createMutation.error?.response?.data?.detail || updateMutation.error?.response?.data?.detail || 'Failed to save prompt'}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

export default PromptsPage
