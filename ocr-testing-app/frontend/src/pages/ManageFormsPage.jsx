import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { formsAPI } from '../services/api'

function ManageFormsPage() {
  const [showUpload, setShowUpload] = useState(false)
  const [selectedForm, setSelectedForm] = useState(null)
  const [formName, setFormName] = useState('')
  const [formType, setFormType] = useState('empty')
  const [file, setFile] = useState(null)
  const [deleteConfirm, setDeleteConfirm] = useState(null)

  const queryClient = useQueryClient()

  // Fetch forms
  const { data, isLoading, error } = useQuery({
    queryKey: ['forms'],
    queryFn: () => formsAPI.list(),
  })

  // Upload mutation
  const uploadMutation = useMutation({
    mutationFn: async () => {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('name', formName)
      formData.append('form_type', formType)
      return formsAPI.upload(formData)
    },
    onSuccess: () => {
      queryClient.invalidateQueries(['forms'])
      setShowUpload(false)
      setFormName('')
      setFormType('empty')
      setFile(null)
    },
  })

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (id) => formsAPI.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries(['forms'])
      setDeleteConfirm(null)
    },
  })

  const handleUpload = (e) => {
    e.preventDefault()
    if (file && formName) {
      uploadMutation.mutate()
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    const droppedFile = e.dataTransfer.files[0]
    if (droppedFile) {
      setFile(droppedFile)
    }
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold">Manage Forms</h2>
        <button
          onClick={() => setShowUpload(true)}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700"
        >
          + Upload Form
        </button>
      </div>

      {/* Upload Modal */}
      {showUpload && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md">
            <h3 className="text-lg font-semibold mb-4">Upload New Form</h3>
            <form onSubmit={handleUpload}>
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Form Name
                </label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="w-full px-3 py-2 border rounded-md"
                  placeholder="e.g., Demand Letter"
                  required
                />
              </div>

              {/* Form Type Toggle */}
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Form Type
                </label>
                <div className="flex gap-3">
                  <label
                    className={`flex-1 p-3 border-2 rounded-lg cursor-pointer text-center transition-colors ${
                      formType === 'empty'
                        ? 'border-blue-600 bg-blue-50 text-blue-700'
                        : 'border-gray-200 hover:border-gray-400'
                    }`}
                  >
                    <input
                      type="radio"
                      name="formType"
                      value="empty"
                      checked={formType === 'empty'}
                      onChange={() => setFormType('empty')}
                      className="sr-only"
                    />
                    <div className="font-medium">Empty Form</div>
                    <div className="text-xs text-gray-500 mt-1">
                      For synthetic data generation
                    </div>
                  </label>
                  <label
                    className={`flex-1 p-3 border-2 rounded-lg cursor-pointer text-center transition-colors ${
                      formType === 'handwritten'
                        ? 'border-purple-600 bg-purple-50 text-purple-700'
                        : 'border-gray-200 hover:border-gray-400'
                    }`}
                  >
                    <input
                      type="radio"
                      name="formType"
                      value="handwritten"
                      checked={formType === 'handwritten'}
                      onChange={() => setFormType('handwritten')}
                      className="sr-only"
                    />
                    <div className="font-medium">Handwritten</div>
                    <div className="text-xs text-gray-500 mt-1">
                      Pre-filled, skew only
                    </div>
                  </label>
                </div>
              </div>

              <div
                className="border-2 border-dashed rounded-lg p-8 text-center cursor-pointer hover:border-blue-500"
                onDrop={handleDrop}
                onDragOver={(e) => e.preventDefault()}
                onClick={() => document.getElementById('file-input').click()}
              >
                <input
                  id="file-input"
                  type="file"
                  accept="image/*,.pdf"
                  onChange={(e) => setFile(e.target.files[0])}
                  className="hidden"
                />
                {file ? (
                  <p className="text-green-600">{file.name}</p>
                ) : (
                  <p className="text-gray-500">
                    Drop file here or click to browse
                  </p>
                )}
              </div>

              <div className="flex justify-end gap-3 mt-4">
                <button
                  type="button"
                  onClick={() => {
                    setShowUpload(false)
                    setFile(null)
                    setFormName('')
                    setFormType('empty')
                  }}
                  className="px-4 py-2 border rounded-md hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!file || !formName || uploadMutation.isPending}
                  className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                >
                  {uploadMutation.isPending ? 'Uploading...' : 'Upload'}
                </button>
              </div>

              {uploadMutation.isError && (
                <p className="text-red-600 text-sm mt-2">
                  {uploadMutation.error?.response?.data?.detail || 'Upload failed'}
                </p>
              )}
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-sm">
            <h3 className="text-lg font-semibold mb-4">Confirm Delete</h3>
            <p className="text-gray-600 mb-4">
              Are you sure you want to delete "{deleteConfirm.name}"?
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="px-4 py-2 border rounded-md hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => deleteMutation.mutate(deleteConfirm.id)}
                disabled={deleteMutation.isPending}
                className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50"
              >
                {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Forms List */}
      {isLoading ? (
        <p>Loading forms...</p>
      ) : error ? (
        <p className="text-red-600">Error loading forms</p>
      ) : data?.data?.forms?.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {data.data.forms.map((form) => (
            <div
              key={form.id}
              className="bg-white rounded-lg shadow p-4 hover:shadow-md transition-shadow"
            >
              <div className="flex justify-between items-start">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold">
                      {form.name} - {new Date(form.uploaded_at).toLocaleDateString()}
                      {form.uploaded_by_name && ` - ${form.uploaded_by_name.split('@')[0]}`}
                    </h3>
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-medium ${
                        form.form_type === 'handwritten'
                          ? 'bg-purple-100 text-purple-700'
                          : 'bg-blue-100 text-blue-700'
                      }`}
                    >
                      {form.form_type === 'handwritten' ? 'Handwritten' : 'Empty'}
                    </span>
                  </div>
                  <p className="text-sm text-gray-500">
                    {form.form_type === 'handwritten'
                      ? 'Skew copies only'
                      : `${form.field_mappings?.length || 0} fields`}
                    {form.page_count > 1 && ` · ${form.page_count} pages`}
                  </p>
                </div>
                <button
                  onClick={() => setDeleteConfirm(form)}
                  className="text-red-600 hover:text-red-800"
                >
                  Delete
                </button>
              </div>
              <div className="mt-3 flex gap-2 flex-wrap">
                <button
                  onClick={() => setSelectedForm(form)}
                  className="text-sm text-blue-600 hover:underline"
                >
                  Preview
                </button>
                <button
                  onClick={() => formsAPI.download(form.id, form.name)}
                  className="text-sm text-indigo-600 hover:underline"
                >
                  Download
                </button>
                <a
                  href={`/synthetic?formId=${form.id}`}
                  className="text-sm text-green-600 hover:underline"
                >
                  {form.form_type === 'handwritten'
                    ? 'Generate Copies'
                    : 'Generate Data'}
                </a>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <p className="text-gray-600">No forms uploaded yet.</p>
          <button
            onClick={() => setShowUpload(true)}
            className="mt-4 text-blue-600 hover:underline"
          >
            Upload your first form
          </button>
        </div>
      )}

      {/* Preview Modal */}
      {selectedForm && (
        <FormPreviewModal
          form={selectedForm}
          onClose={() => setSelectedForm(null)}
        />
      )}

    </div>
  )
}

function FormPreviewModal({ form, onClose }) {
  const [currentPage, setCurrentPage] = useState(0)
  const pageCount = form.page_count || 1

  const { data } = useQuery({
    queryKey: ['form-image', form.id, currentPage],
    queryFn: () => formsAPI.getImage(form.id, currentPage),
  })

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 w-full max-w-4xl max-h-[90vh] overflow-auto">
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold">{form.name}</h3>
          <div className="flex items-center gap-2">
            {pageCount > 1 && (
              <>
                <button
                  onClick={() => setCurrentPage(p => Math.max(0, p - 1))}
                  disabled={currentPage === 0}
                  className="px-3 py-1 text-sm bg-gray-100 rounded hover:bg-gray-200 disabled:opacity-30"
                >
                  Prev
                </button>
                <span className="text-sm text-gray-600">
                  Page {currentPage + 1} of {pageCount}
                </span>
                <button
                  onClick={() => setCurrentPage(p => Math.min(pageCount - 1, p + 1))}
                  disabled={currentPage === pageCount - 1}
                  className="px-3 py-1 text-sm bg-gray-100 rounded hover:bg-gray-200 disabled:opacity-30"
                >
                  Next
                </button>
              </>
            )}
            <button
              onClick={onClose}
              className="text-gray-500 hover:text-gray-700 ml-4"
            >
              Close
            </button>
          </div>
        </div>
        {data?.data?.url ? (
          <img
            src={data.data.url}
            alt={`${form.name} - Page ${currentPage + 1}`}
            className="max-w-full border rounded"
          />
        ) : (
          <p className="text-gray-500">Loading preview...</p>
        )}
      </div>
    </div>
  )
}

export default ManageFormsPage
