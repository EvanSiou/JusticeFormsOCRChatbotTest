import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams, useNavigate } from 'react-router-dom'
import { testsAPI, classifyVerifyAPI } from '../services/api'
import MagnifyImage from '../components/MagnifyImage'

const ERROR_REASONS = [
  { value: 'wrong_classification', label: 'Wrong Classification' },
  { value: 'wrong_value', label: 'Wrong Value' },
  { value: 'partial_match', label: 'Partial Match' },
  { value: 'not_found', label: 'Not Found' },
]

const TYPE_COLORS = {
  defendant_name: 'bg-blue-100 text-blue-700',
  county: 'bg-green-100 text-green-700',
  cause_number: 'bg-purple-100 text-purple-700',
  charge: 'bg-red-100 text-red-700',
  condition_order: 'bg-yellow-100 text-yellow-700',
  assessed_amount: 'bg-orange-100 text-orange-700',
  address: 'bg-teal-100 text-teal-700',
}

const MODEL_LABELS = {
  claude_bedrock: 'Claude Sonnet 4.5',
  claude_haiku_bedrock: 'Claude Haiku 4.5',
  nova_pro: 'Nova Pro',
  nova_lite: 'Nova Lite',
  pixtral_large: 'Pixtral Large',
  llama4_maverick_bedrock: 'Llama 4 Maverick',
  llama4_scout: 'Llama 4 Scout',
  gpt5: 'GPT-5',
  gpt5_mini: 'GPT-5 mini',
  // Legacy names for old test runs
  claude: 'Claude Sonnet 4.5',
  llama4_maverick: 'Llama 4 Maverick',
  mistral_medium3: 'Mistral Medium 3',
}

function ClassifyVerifyPage() {
  const { testRunId: paramTestRunId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [selectedTestRunId, setSelectedTestRunId] = useState(paramTestRunId || '')
  const [selectedDocumentId, setSelectedDocumentId] = useState(null)
  const [userFilter, setUserFilter] = useState('')
  const [fieldVerifications, setFieldVerifications] = useState({})
  const [missedFields, setMissedFields] = useState([])

  // Fetch completed test runs
  const { data: testsData } = useQuery({
    queryKey: ['tests'],
    queryFn: () => testsAPI.list(),
  })

  const allCompletedRuns = testsData?.data?.test_runs?.filter(
    (r) => r.status === 'completed'
  ) || []

  const uniqueUsers = [...new Set(
    allCompletedRuns
      .map(r => r.started_by_name)
      .filter(Boolean)
      .map(name => name.split('@')[0])
  )].sort()

  const completedRuns = userFilter
    ? allCompletedRuns.filter(r => r.started_by_name && r.started_by_name.split('@')[0] === userFilter)
    : allCompletedRuns

  // Fetch documents for classification verification
  const { data: docsData } = useQuery({
    queryKey: ['classify-verify-docs', selectedTestRunId],
    queryFn: () => classifyVerifyAPI.getDocuments(selectedTestRunId),
    enabled: !!selectedTestRunId,
  })

  // Fetch verification summary
  const { data: summaryData } = useQuery({
    queryKey: ['classify-verify-summary', selectedTestRunId],
    queryFn: () => classifyVerifyAPI.getSummary(selectedTestRunId),
    enabled: !!selectedTestRunId,
  })

  const documents = docsData?.data?.documents || []
  const classifiedDocs = documents.filter(d => d.has_classification)
  const summary = summaryData?.data

  // Fetch document detail
  const { data: docDetail } = useQuery({
    queryKey: ['classify-verify-doc', selectedTestRunId, selectedDocumentId],
    queryFn: () => classifyVerifyAPI.getDocument(selectedTestRunId, selectedDocumentId),
    enabled: !!selectedTestRunId && !!selectedDocumentId,
  })

  const docData = docDetail?.data

  // Load document image
  const { data: imageUrl } = useQuery({
    queryKey: ['classify-verify-image', selectedTestRunId, selectedDocumentId],
    queryFn: () => classifyVerifyAPI.getDocumentImage(selectedTestRunId, selectedDocumentId),
    enabled: !!selectedTestRunId && !!selectedDocumentId,
  })

  // Initialize verifications when document data loads
  useEffect(() => {
    if (docData?.classification_results) {
      const cr = docData.classification_results
      const fields = cr.classified_fields || []

      // Check if previously verified
      const existingVerification = cr.verification
      if (existingVerification) {
        const verif = {}
        for (const fv of existingVerification.field_verifications || []) {
          verif[fv.field_index] = {
            is_correct: fv.is_correct,
            error_reason: fv.error_reason || '',
            corrected_field_type: fv.corrected_field_type || '',
            corrected_value: fv.corrected_value || '',
          }
        }
        setFieldVerifications(verif)
        setMissedFields(
          (existingVerification.missed_fields || []).map(mf => ({
            field_type: mf.field_type,
            value: mf.value,
          }))
        )
      } else {
        // Initialize all fields as unverified
        const initial = {}
        fields.forEach((_, idx) => {
          initial[idx] = {
            is_correct: true,
            error_reason: '',
            corrected_field_type: '',
            corrected_value: '',
          }
        })
        setFieldVerifications(initial)
        setMissedFields([])
      }
    }
  }, [docData])

  // Reset when document changes
  useEffect(() => {
    setFieldVerifications({})
    setMissedFields([])
  }, [selectedDocumentId])

  // Submit verification
  const verifyMutation = useMutation({
    mutationFn: () => {
      const fieldVerifs = Object.entries(fieldVerifications).map(([idx, data]) => ({
        field_index: parseInt(idx),
        is_correct: data.is_correct,
        error_reason: !data.is_correct && data.error_reason ? data.error_reason : null,
        corrected_field_type: !data.is_correct && data.corrected_field_type ? data.corrected_field_type : null,
        corrected_value: !data.is_correct && data.corrected_value ? data.corrected_value : null,
      }))
      const missed = missedFields.filter(mf => mf.field_type.trim() && mf.value.trim())
      return classifyVerifyAPI.verify(selectedTestRunId, selectedDocumentId, {
        field_verifications: fieldVerifs,
        missed_fields: missed,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries(['classify-verify-docs', selectedTestRunId])
      queryClient.invalidateQueries(['classify-verify-summary', selectedTestRunId])
      queryClient.invalidateQueries(['classify-verify-doc', selectedTestRunId, selectedDocumentId])
      // Auto-advance to next unverified classified document
      const currentIdx = classifiedDocs.findIndex(d => d.document_id === selectedDocumentId)
      const nextUnverified = classifiedDocs.find(
        (d, i) => i > currentIdx && !d.classification_verified
      )
      if (nextUnverified) {
        setSelectedDocumentId(nextUnverified.document_id)
      }
    },
  })

  const handleFieldCorrectness = (idx, isCorrect) => {
    setFieldVerifications(prev => ({
      ...prev,
      [idx]: { ...prev[idx], is_correct: isCorrect },
    }))
  }

  const handleErrorReason = (idx, reason) => {
    setFieldVerifications(prev => ({
      ...prev,
      [idx]: { ...prev[idx], error_reason: reason },
    }))
  }

  const handleCorrectedFieldType = (idx, value) => {
    setFieldVerifications(prev => ({
      ...prev,
      [idx]: { ...prev[idx], corrected_field_type: value },
    }))
  }

  const handleCorrectedValue = (idx, value) => {
    setFieldVerifications(prev => ({
      ...prev,
      [idx]: { ...prev[idx], corrected_value: value },
    }))
  }

  const classifiedFields = docData?.classification_results?.classified_fields || []

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Verify Classification</h2>

      {/* Top Filter Bar */}
      <div className="bg-white rounded-lg shadow p-4 mb-4">
        <div className="flex flex-wrap items-end gap-4">
          {uniqueUsers.length > 0 && (
            <div className="min-w-[150px]">
              <label className="block text-sm font-medium text-gray-700 mb-1">User</label>
              <select
                value={userFilter}
                onChange={(e) => {
                  setUserFilter(e.target.value)
                  setSelectedDocumentId(null)
                  setSelectedTestRunId('')
                  navigate('/classify-verify')
                }}
                className="w-full px-3 py-2 border rounded-md text-sm"
              >
                <option value="">All Users</option>
                {uniqueUsers.map((user) => (
                  <option key={user} value={user}>{user}</option>
                ))}
              </select>
            </div>
          )}

          <div className="flex-1 min-w-[250px]">
            <label className="block text-sm font-medium text-gray-700 mb-1">Test Run</label>
            <select
              value={selectedTestRunId || ''}
              onChange={(e) => {
                const val = e.target.value
                setSelectedTestRunId(val)
                setSelectedDocumentId(null)
                if (val) navigate(`/classify-verify/${val}`)
                else navigate('/classify-verify')
              }}
              className="w-full px-3 py-2 border rounded-md text-sm"
            >
              <option value="">-- Select a test run --</option>
              {completedRuns.map((run) => (
                <option key={run.id} value={run.id}>
                  {run.layout_library || 'N/A'} + {run.ocr_library}
                  {run.started_by_name ? ` - ${run.started_by_name.split('@')[0]}` : ''}
                  {' - '}{new Date(run.started_at).toLocaleDateString()}
                  {` (${run.total_documents} docs)`}
                </option>
              ))}
            </select>
          </div>

          <div className="flex-1 min-w-[250px]">
            <label className="block text-sm font-medium text-gray-700 mb-1">Document</label>
            <select
              value={selectedDocumentId || ''}
              onChange={(e) => setSelectedDocumentId(e.target.value || null)}
              className="w-full px-3 py-2 border rounded-md text-sm"
              disabled={!selectedTestRunId || classifiedDocs.length === 0}
            >
              <option value="">-- Select a classified document --</option>
              {classifiedDocs.map((d, idx) => (
                <option key={d.document_id} value={d.document_id}>
                  Doc {idx + 1} ({d.document_id.slice(0, 8)})
                  {d.classifier_model && ` [${MODEL_LABELS[d.classifier_model] || d.classifier_model}]`}
                  {d.classification_verified && ' [Verified]'}
                  {d.classification_verified_accuracy != null && ` ${Math.round(d.classification_verified_accuracy * 100)}%`}
                </option>
              ))}
            </select>
          </div>

          {summary && summary.total_classified > 0 && (
            <div className="flex items-center gap-3">
              <div className="w-32 bg-gray-200 rounded-full h-2">
                <div
                  className="bg-green-600 h-2 rounded-full transition-all"
                  style={{ width: `${summary.progress_percent || 0}%` }}
                />
              </div>
              <span className="text-sm text-gray-600 whitespace-nowrap">
                {summary.verified}/{summary.total_classified} verified
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Main Content */}
      {!selectedTestRunId ? (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <p className="text-gray-500">Select a test run to begin classification verification.</p>
        </div>
      ) : !selectedDocumentId ? (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <p className="text-gray-500">
            {classifiedDocs.length === 0
              ? 'No classified documents in this test run. Run classification first.'
              : 'Select a classified document to verify.'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Left Column: Image */}
          <div className="space-y-4">
            {imageUrl && (
              <div className="bg-white rounded-lg shadow p-4">
                <h3 className="font-semibold mb-3">Document Image</h3>
                <MagnifyImage src={imageUrl} alt="Document" />
              </div>
            )}

            {/* Classification metadata */}
            {docData?.classification_results && (
              <div className="bg-white rounded-lg shadow p-4">
                <h3 className="font-semibold mb-3">Classification Info</h3>
                <div className="flex items-center gap-3 flex-wrap text-sm">
                  {docData.classification_results.form_type && (
                    <span>
                      <span className="text-gray-500">Form:</span>
                      <span className="ml-1 px-2 py-0.5 bg-blue-50 text-blue-700 rounded font-medium">
                        {docData.classification_results.form_type}
                      </span>
                    </span>
                  )}
                  {docData.classification_results.classifier_model && (
                    <span>
                      <span className="text-gray-500">Model:</span>
                      <span className="ml-1 px-2 py-0.5 bg-purple-100 text-purple-700 rounded font-medium">
                        {MODEL_LABELS[docData.classification_results.classifier_model] || docData.classification_results.classifier_model}
                      </span>
                    </span>
                  )}
                  {docData.classification_results.text_source && (
                    <span>
                      <span className="text-gray-500">Text:</span>
                      <span className="ml-1 px-2 py-0.5 bg-gray-100 text-gray-600 rounded">
                        {docData.classification_results.text_source}
                      </span>
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Right Column: Verification Panel */}
          <div className="space-y-4">
            <div className="bg-white rounded-lg shadow p-4">
              <h3 className="font-semibold mb-3">Field Verification</h3>

              {classifiedFields.length > 0 ? (
                <div className="space-y-3">
                  {classifiedFields.map((field, idx) => {
                    const verif = fieldVerifications[idx] || { is_correct: true, error_reason: '', corrected_field_type: '', corrected_value: '' }
                    return (
                      <div key={idx} className={`border-2 rounded-lg p-3 transition-colors ${
                        verif.is_correct ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'
                      }`}>
                        <div className="flex items-center gap-2 mb-2">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                            TYPE_COLORS[field.field_type] || 'bg-gray-100 text-gray-700'
                          }`}>
                            {field.field_type}
                          </span>
                          {field.confidence != null && (
                            <span className="text-xs text-gray-500">
                              {Math.round(field.confidence * 100)}%
                            </span>
                          )}
                        </div>

                        <p className="text-sm font-medium mb-1">{field.value}</p>
                        {field.context && (
                          <p className="text-xs text-gray-500 mb-2">Context: {field.context}</p>
                        )}

                        {/* Correct / Incorrect */}
                        <div className="flex items-center gap-3 mb-2">
                          <label className="flex items-center gap-1 text-sm cursor-pointer">
                            <input
                              type="radio"
                              name={`verify-field-${idx}`}
                              checked={verif.is_correct}
                              onChange={() => handleFieldCorrectness(idx, true)}
                            />
                            <span className="text-green-700">Correct</span>
                          </label>
                          <label className="flex items-center gap-1 text-sm cursor-pointer">
                            <input
                              type="radio"
                              name={`verify-field-${idx}`}
                              checked={!verif.is_correct}
                              onChange={() => handleFieldCorrectness(idx, false)}
                            />
                            <span className="text-red-700">Incorrect</span>
                          </label>
                        </div>

                        {/* Error details when incorrect */}
                        {!verif.is_correct && (
                          <div className="space-y-2 ml-4">
                            <div>
                              <label className="block text-xs text-gray-500 mb-1">Error Reason</label>
                              <select
                                value={verif.error_reason}
                                onChange={(e) => handleErrorReason(idx, e.target.value)}
                                className="w-full px-2 py-1 border rounded text-sm"
                              >
                                <option value="">Select reason...</option>
                                {ERROR_REASONS.map((r) => (
                                  <option key={r.value} value={r.value}>{r.label}</option>
                                ))}
                              </select>
                            </div>

                            {verif.error_reason === 'wrong_classification' && (
                              <div>
                                <label className="block text-xs text-gray-500 mb-1">Correct Field Type</label>
                                <input
                                  type="text"
                                  value={verif.corrected_field_type}
                                  onChange={(e) => handleCorrectedFieldType(idx, e.target.value)}
                                  placeholder="e.g., defendant_name"
                                  className="w-full px-2 py-1 border rounded text-sm"
                                />
                              </div>
                            )}

                            {(verif.error_reason === 'wrong_value' || verif.error_reason === 'partial_match') && (
                              <div>
                                <label className="block text-xs text-gray-500 mb-1">Correct Value</label>
                                <input
                                  type="text"
                                  value={verif.corrected_value}
                                  onChange={(e) => handleCorrectedValue(idx, e.target.value)}
                                  placeholder="Enter correct value"
                                  className="w-full px-2 py-1 border rounded text-sm"
                                />
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="text-sm text-gray-500">No classified fields to verify.</p>
              )}

              {/* Missed Fields Section */}
              <div className="border-t mt-4 pt-4">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-sm font-medium">Add Missed Fields</h4>
                  <button
                    type="button"
                    onClick={() => setMissedFields(prev => [...prev, { field_type: '', value: '' }])}
                    className="px-3 py-1 bg-blue-100 text-blue-700 rounded text-xs hover:bg-blue-200"
                  >
                    + Add Field
                  </button>
                </div>
                {missedFields.length > 0 ? (
                  <div className="space-y-2">
                    {missedFields.map((mf, idx) => (
                      <div key={idx} className="flex items-center gap-2">
                        <input
                          type="text"
                          value={mf.field_type}
                          onChange={(e) => {
                            setMissedFields(prev => {
                              const copy = [...prev]
                              copy[idx] = { ...copy[idx], field_type: e.target.value }
                              return copy
                            })
                          }}
                          placeholder="Field type"
                          className="w-1/3 px-2 py-1 border rounded text-sm"
                        />
                        <input
                          type="text"
                          value={mf.value}
                          onChange={(e) => {
                            setMissedFields(prev => {
                              const copy = [...prev]
                              copy[idx] = { ...copy[idx], value: e.target.value }
                              return copy
                            })
                          }}
                          placeholder="Value"
                          className="flex-1 px-2 py-1 border rounded text-sm"
                        />
                        <button
                          type="button"
                          onClick={() => setMissedFields(prev => prev.filter((_, i) => i !== idx))}
                          className="px-2 py-1 text-red-500 hover:text-red-700 text-sm"
                        >
                          Remove
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-gray-400">No missed fields added.</p>
                )}
              </div>

              {/* Submit Button */}
              <div className="mt-4 flex justify-end">
                <button
                  onClick={() => verifyMutation.mutate()}
                  disabled={verifyMutation.isPending}
                  className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
                >
                  {verifyMutation.isPending ? 'Submitting...' : 'Submit Verification'}
                </button>
              </div>

              {verifyMutation.isSuccess && (
                <p className="text-green-600 text-sm mt-2">
                  Classification verification submitted.
                  {verifyMutation.data?.data?.verified_accuracy != null && (
                    <span className="font-medium ml-1">
                      Accuracy: {Math.round(verifyMutation.data.data.verified_accuracy * 100)}%
                    </span>
                  )}
                </p>
              )}
              {verifyMutation.isError && (
                <p className="text-red-600 text-sm mt-2">
                  {verifyMutation.error?.response?.data?.detail || 'Verification failed'}
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default ClassifyVerifyPage
