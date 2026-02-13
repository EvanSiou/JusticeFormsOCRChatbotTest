import { useState, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { testsAPI, classifyAPI } from '../services/api'
import MagnifyImage from '../components/MagnifyImage'

const DEFAULT_FIELD_TYPES =
  'full_name, date, case_number, address, monetary_amount, phone_number, id_number'

function ClassifyPage() {
  const [userFilter, setUserFilter] = useState('')
  const [selectedTestRun, setSelectedTestRun] = useState('')
  const [selectedDocumentId, setSelectedDocumentId] = useState('')
  const [fieldTypesInput, setFieldTypesInput] = useState(DEFAULT_FIELD_TYPES)
  const [useCleanedText, setUseCleanedText] = useState(true)
  const [classificationResult, setClassificationResult] = useState(null)
  const [saved, setSaved] = useState(false)
  const [textView, setTextView] = useState('important') // 'important' | 'cleaned' | 'full'

  // Fetch test runs (completed only)
  const { data: testsData } = useQuery({
    queryKey: ['tests'],
    queryFn: () => testsAPI.list(),
  })

  const allTestRuns = testsData?.data?.test_runs || []
  const completedRuns = allTestRuns.filter((r) => r.status === 'completed')

  // Extract unique users
  const uniqueUsers = [
    ...new Set(
      completedRuns
        .map((r) => r.started_by_name)
        .filter(Boolean)
        .map((n) => n.split('@')[0])
    ),
  ].sort()

  const filteredRuns = userFilter
    ? completedRuns.filter(
        (r) =>
          r.started_by_name &&
          r.started_by_name.split('@')[0] === userFilter
      )
    : completedRuns

  // Fetch documents for selected test run
  const { data: docsData } = useQuery({
    queryKey: ['classify-docs', selectedTestRun],
    queryFn: () => classifyAPI.getDocuments(selectedTestRun),
    enabled: !!selectedTestRun,
  })

  const documents = docsData?.data?.documents || []

  // Fetch document detail
  const { data: docDetail } = useQuery({
    queryKey: ['classify-doc', selectedTestRun, selectedDocumentId],
    queryFn: () =>
      classifyAPI.getDocument(selectedTestRun, selectedDocumentId),
    enabled: !!selectedTestRun && !!selectedDocumentId,
  })

  const docData = docDetail?.data

  // Load document image
  const { data: imageUrl } = useQuery({
    queryKey: ['classify-image', selectedTestRun, selectedDocumentId],
    queryFn: () =>
      classifyAPI.getDocumentImage(selectedTestRun, selectedDocumentId),
    enabled: !!selectedTestRun && !!selectedDocumentId,
  })

  // Reset classification when document changes
  useEffect(() => {
    setClassificationResult(null)
    setSaved(false)
  }, [selectedDocumentId])

  // Load existing classification if present
  useEffect(() => {
    if (docData?.existing_classification) {
      setClassificationResult(docData.existing_classification)
    }
  }, [docData])

  // Run classification mutation
  const runMutation = useMutation({
    mutationFn: () => {
      const fieldTypes = fieldTypesInput
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean)
      return classifyAPI.run(selectedTestRun, selectedDocumentId, {
        field_types: fieldTypes.length > 0 ? fieldTypes : null,
        use_cleaned_text: useCleanedText,
      })
    },
    onSuccess: (response) => {
      setClassificationResult(response.data)
      setSaved(false)
    },
  })

  // Save classification mutation
  const saveMutation = useMutation({
    mutationFn: () =>
      classifyAPI.save(selectedTestRun, selectedDocumentId, {
        classification_results: classificationResult,
      }),
    onSuccess: () => {
      setSaved(true)
    },
  })

  // Get the display text based on current view
  const getDisplayText = () => {
    if (!docData) return ''
    if (textView === 'cleaned' && docData.cleaned_text) return docData.cleaned_text
    if (textView === 'full') return docData.full_text
    return docData.important_text || '(No verified important text found)'
  }

  // Field type badge colors
  const typeColors = {
    full_name: 'bg-blue-100 text-blue-700',
    date: 'bg-green-100 text-green-700',
    case_number: 'bg-purple-100 text-purple-700',
    address: 'bg-yellow-100 text-yellow-700',
    monetary_amount: 'bg-red-100 text-red-700',
    phone_number: 'bg-indigo-100 text-indigo-700',
    id_number: 'bg-pink-100 text-pink-700',
    other: 'bg-gray-100 text-gray-700',
  }

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Classify</h2>

      {/* Top Bar: User + Test Run + Document */}
      <div className="bg-white rounded-lg shadow p-4 mb-6">
        <div className="flex items-end gap-4 flex-wrap">
          {uniqueUsers.length > 0 && (
            <div className="min-w-[150px]">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                User
              </label>
              <select
                value={userFilter}
                onChange={(e) => {
                  setUserFilter(e.target.value)
                  setSelectedTestRun('')
                  setSelectedDocumentId('')
                }}
                className="w-full px-3 py-2 border rounded-md text-sm"
              >
                <option value="">All Users</option>
                {uniqueUsers.map((user) => (
                  <option key={user} value={user}>
                    {user}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="flex-1 min-w-[250px]">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Test Run
            </label>
            <select
              value={selectedTestRun}
              onChange={(e) => {
                setSelectedTestRun(e.target.value)
                setSelectedDocumentId('')
                setClassificationResult(null)
              }}
              className="w-full px-3 py-2 border rounded-md text-sm"
            >
              <option value="">Select a completed test run...</option>
              {filteredRuns.map((run) => (
                <option key={run.id} value={run.id}>
                  {run.layout_library || 'N/A'} + {run.ocr_library} -{' '}
                  {run.total_documents} docs -{' '}
                  {new Date(run.started_at).toLocaleDateString()}
                  {run.started_by_name && ` - ${run.started_by_name.split('@')[0]}`}
                </option>
              ))}
            </select>
          </div>

          {selectedTestRun && documents.length > 0 && (
            <div className="flex-1 min-w-[250px]">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Document
              </label>
              <select
                value={selectedDocumentId}
                onChange={(e) => setSelectedDocumentId(e.target.value)}
                className="w-full px-3 py-2 border rounded-md text-sm"
              >
                <option value="">Select a document...</option>
                {documents.map((doc, i) => (
                  <option key={doc.document_id} value={doc.document_id}>
                    Doc {i + 1} ({doc.document_id.slice(0, 8)})
                    {doc.verification_status === 'verified' && ' [Verified]'}
                    {doc.verification_status === 'corrected' && ' [Corrected]'}
                    {doc.has_classification && ' [Classified]'}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </div>

      {/* Main content: two columns when document selected */}
      {selectedDocumentId && docData && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left column: Image + Text */}
          <div className="space-y-4">
            {/* Document image */}
            {imageUrl && (
              <div className="bg-white rounded-lg shadow p-4">
                <h3 className="text-sm font-semibold mb-2">Document Image</h3>
                <MagnifyImage src={imageUrl} alt="Document" />
              </div>
            )}

            {/* Text display */}
            <div className="bg-white rounded-lg shadow p-4">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold">Text</h3>
                <div className="flex gap-1">
                  <button
                    onClick={() => setTextView('important')}
                    className={`px-2 py-1 text-xs rounded ${
                      textView === 'important'
                        ? 'bg-blue-100 text-blue-700'
                        : 'bg-gray-100 text-gray-600'
                    }`}
                  >
                    Important
                  </button>
                  {docData.cleaned_text && (
                    <button
                      onClick={() => setTextView('cleaned')}
                      className={`px-2 py-1 text-xs rounded ${
                        textView === 'cleaned'
                          ? 'bg-blue-100 text-blue-700'
                          : 'bg-gray-100 text-gray-600'
                      }`}
                    >
                      Cleaned
                    </button>
                  )}
                  <button
                    onClick={() => setTextView('full')}
                    className={`px-2 py-1 text-xs rounded ${
                      textView === 'full'
                        ? 'bg-blue-100 text-blue-700'
                        : 'bg-gray-100 text-gray-600'
                    }`}
                  >
                    Full
                  </button>
                </div>
              </div>
              <pre className="bg-gray-50 border rounded p-3 text-xs whitespace-pre-wrap max-h-[400px] overflow-y-auto">
                {getDisplayText()}
              </pre>
            </div>
          </div>

          {/* Right column: Classification panel */}
          <div className="space-y-4">
            {/* Classification config */}
            <div className="bg-white rounded-lg shadow p-4">
              <h3 className="text-sm font-semibold mb-3">
                Classification Settings
              </h3>

              <div className="mb-3">
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Field types to classify (comma-separated)
                </label>
                <input
                  type="text"
                  value={fieldTypesInput}
                  onChange={(e) => setFieldTypesInput(e.target.value)}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                  placeholder={DEFAULT_FIELD_TYPES}
                />
              </div>

              <label className="flex items-center gap-2 cursor-pointer mb-4">
                <input
                  type="checkbox"
                  checked={useCleanedText}
                  onChange={(e) => setUseCleanedText(e.target.checked)}
                />
                <span className="text-sm">
                  Use cleaned text if available
                </span>
              </label>

              <button
                onClick={() => runMutation.mutate()}
                disabled={runMutation.isPending}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 w-full"
              >
                {runMutation.isPending
                  ? 'Classifying...'
                  : 'Classify with Claude'}
              </button>

              {runMutation.isError && (
                <p className="text-red-600 text-sm mt-2">
                  {runMutation.error?.response?.data?.detail ||
                    'Classification failed'}
                </p>
              )}
            </div>

            {/* Classification results */}
            {classificationResult && (
              <div className="bg-white rounded-lg shadow p-4">
                <h3 className="text-sm font-semibold mb-3">
                  Classification Results
                </h3>

                {/* Form type */}
                {classificationResult.form_type && (
                  <div className="mb-4">
                    <span className="text-xs text-gray-500">Form Type:</span>
                    <span className="ml-2 px-2 py-1 bg-blue-50 text-blue-700 rounded text-sm font-medium">
                      {classificationResult.form_type}
                    </span>
                  </div>
                )}

                {/* Error */}
                {classificationResult.error && (
                  <p className="text-red-600 text-sm mb-3">
                    Error: {classificationResult.error}
                  </p>
                )}

                {/* Classified fields */}
                {classificationResult.classified_fields?.length > 0 ? (
                  <div className="space-y-2">
                    {classificationResult.classified_fields.map((field, i) => (
                      <div
                        key={i}
                        className="border rounded p-3 bg-gray-50"
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <span
                            className={`px-2 py-0.5 rounded text-xs font-medium ${
                              typeColors[field.field_type] ||
                              typeColors.other
                            }`}
                          >
                            {field.field_type}
                          </span>
                          {field.confidence != null && (
                            <span className="text-xs text-gray-500">
                              {Math.round(field.confidence * 100)}%
                            </span>
                          )}
                        </div>
                        <p className="text-sm font-medium">{field.value}</p>
                        {field.context && (
                          <p className="text-xs text-gray-500 mt-1">
                            Context: {field.context}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-gray-500 text-sm">
                    No fields classified.
                  </p>
                )}

                {/* Save button */}
                <div className="mt-4 flex items-center gap-3">
                  <button
                    onClick={() => saveMutation.mutate()}
                    disabled={saveMutation.isPending || saved}
                    className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
                  >
                    {saveMutation.isPending
                      ? 'Saving...'
                      : saved
                      ? 'Saved!'
                      : 'Save Classification'}
                  </button>

                  {saved && (
                    <span className="text-green-600 text-sm">
                      Classification saved.
                    </span>
                  )}

                  {saveMutation.isError && (
                    <span className="text-red-600 text-sm">
                      {saveMutation.error?.response?.data?.detail ||
                        'Save failed'}
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {selectedTestRun && !selectedDocumentId && documents.length === 0 && (
        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-gray-600">
            No documents found in this test run.
          </p>
        </div>
      )}
    </div>
  )
}

export default ClassifyPage
