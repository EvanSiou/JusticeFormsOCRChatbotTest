import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams, useNavigate } from 'react-router-dom'
import { testsAPI, resultsAPI } from '../services/api'

function formatDuration(startedAt, completedAt) {
  if (!startedAt || !completedAt) return null
  const start = new Date(startedAt)
  const end = new Date(completedAt)
  const seconds = Math.round((end - start) / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  if (minutes < 60) return `${minutes}m ${remainingSeconds}s`
  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60
  return `${hours}h ${remainingMinutes}m`
}

function ResultsPage() {
  const { testRunId } = useParams()
  const navigate = useNavigate()
  const [selectedDocument, setSelectedDocument] = useState(null)
  const [userFilter, setUserFilter] = useState('')

  // Fetch test runs
  const { data: testsData, isLoading: testsLoading } = useQuery({
    queryKey: ['tests'],
    queryFn: () => testsAPI.list(),
  })

  // Fetch results for selected test run
  const { data: resultsData, isLoading: resultsLoading } = useQuery({
    queryKey: ['results', testRunId],
    queryFn: () => resultsAPI.getForTestRun(testRunId),
    enabled: !!testRunId,
  })

  // Fetch summary for selected test run
  const { data: summaryData } = useQuery({
    queryKey: ['results-summary', testRunId],
    queryFn: () => resultsAPI.getSummary(testRunId),
    enabled: !!testRunId,
  })

  // Fetch document details
  const { data: documentData, isLoading: documentLoading } = useQuery({
    queryKey: ['document-result', testRunId, selectedDocument],
    queryFn: () => resultsAPI.getDocument(testRunId, selectedDocument),
    enabled: !!testRunId && !!selectedDocument,
  })

  // Fetch document image as blob
  const [documentImageUrl, setDocumentImageUrl] = useState(null)
  const [imageLoading, setImageLoading] = useState(false)

  useEffect(() => {
    if (testRunId && selectedDocument) {
      setImageLoading(true)
      setDocumentImageUrl(null)
      resultsAPI.getDocumentImage(testRunId, selectedDocument)
        .then((url) => setDocumentImageUrl(url))
        .catch(() => setDocumentImageUrl(null))
        .finally(() => setImageLoading(false))
    } else {
      setDocumentImageUrl(null)
    }
    return () => {
      if (documentImageUrl) {
        URL.revokeObjectURL(documentImageUrl)
      }
    }
  }, [testRunId, selectedDocument])

  const allCompletedRuns = testsData?.data?.test_runs?.filter(
    (tr) => tr.status === 'completed'
  ) || []

  // Extract unique users from test runs
  const uniqueUsers = [...new Set(
    allCompletedRuns
      .map(r => r.started_by_name)
      .filter(Boolean)
      .map(name => name.split('@')[0])
  )].sort()

  // Filter by user
  const completedRuns = userFilter
    ? allCompletedRuns.filter(r => r.started_by_name && r.started_by_name.split('@')[0] === userFilter)
    : allCompletedRuns

  const results = resultsData?.data?.results || []

  // Build a lookup of layout region ID -> OCR region for combined display
  const layoutRegions = documentData?.data?.layout_results?.regions || []
  const ocrRegions = documentData?.data?.ocr_results?.regions || []
  const ocrByRegionId = {}
  ocrRegions.forEach((r) => {
    ocrByRegionId[r.region_id] = r
  })

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">View Results</h2>

      {/* Top Filter Bar */}
      <div className="bg-white rounded-lg shadow p-4 mb-4">
        <div className="flex flex-wrap items-end gap-4">
          {/* User Filter */}
          {uniqueUsers.length > 0 && (
            <div className="min-w-[150px]">
              <label className="block text-sm font-medium text-gray-700 mb-1">User</label>
              <select
                value={userFilter}
                onChange={(e) => {
                  setUserFilter(e.target.value)
                  setSelectedDocument(null)
                  navigate('/results')
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

          {/* Test Run Dropdown */}
          <div className="flex-1 min-w-[250px]">
            <label className="block text-sm font-medium text-gray-700 mb-1">Test Run</label>
            <select
              value={testRunId || ''}
              onChange={(e) => {
                const val = e.target.value
                setSelectedDocument(null)
                if (val) navigate(`/results/${val}`)
                else navigate('/results')
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

          {/* Document Dropdown */}
          <div className="flex-1 min-w-[250px]">
            <label className="block text-sm font-medium text-gray-700 mb-1">Document</label>
            <select
              value={selectedDocument || ''}
              onChange={(e) => setSelectedDocument(e.target.value || null)}
              className="w-full px-3 py-2 border rounded-md text-sm"
              disabled={!testRunId || results.length === 0}
            >
              <option value="">-- Select a document --</option>
              {results.map((result, idx) => {
                const acc = result.verified_accuracy != null ? result.verified_accuracy : result.overall_accuracy
                return (
                  <option key={result.document_id} value={result.document_id}>
                    Doc {idx + 1} ({result.document_id.slice(0, 8)}...) - {(acc * 100).toFixed(0)}%
                    {result.verified_accuracy != null ? ' [V]' : ''}
                  </option>
                )
              })}
            </select>
          </div>
        </div>
      </div>

      {/* Summary */}
      {testRunId && summaryData?.data && (
        <div className="bg-white rounded-lg shadow p-6 mb-4">
          <h3 className="font-semibold mb-4">Summary</h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div>
              <p className="text-sm text-gray-500">Documents</p>
              <p className="text-xl font-bold">{summaryData.data.total_documents}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Avg. Accuracy</p>
              <p className="text-xl font-bold text-blue-600">
                {(summaryData.data.average_accuracy * 100).toFixed(1)}%
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-500">Layout</p>
              <p className="text-sm font-medium">{summaryData.data.layout_library || 'N/A'}</p>
            </div>
            <div>
              <p className="text-sm text-gray-500">OCR</p>
              <p className="text-sm font-medium">{summaryData.data.ocr_library}</p>
            </div>
            {(() => {
              const currentRun = allCompletedRuns.find(r => r.id === testRunId)
              const duration = currentRun ? formatDuration(currentRun.started_at, currentRun.completed_at) : null
              return duration ? (
                <div>
                  <p className="text-sm text-gray-500">Duration</p>
                  <p className="text-xl font-bold text-gray-700">{duration}</p>
                </div>
              ) : null
            })()}
          </div>

          {/* Field Accuracies */}
          {Object.keys(summaryData.data.field_accuracies || {}).length > 0 && (
            <div className="mt-4 pt-4 border-t">
              <h4 className="text-sm font-medium mb-2">Per-Field Accuracy</h4>
              <div className="space-y-2">
                {Object.entries(summaryData.data.field_accuracies).map(
                  ([field, accuracy]) => (
                    <div key={field} className="flex items-center gap-2">
                      <span className="text-sm w-32 truncate">{field}</span>
                      <div className="flex-1 bg-gray-200 rounded-full h-2">
                        <div
                          className={`h-2 rounded-full ${
                            accuracy >= 0.8 ? 'bg-green-500'
                              : accuracy >= 0.5 ? 'bg-yellow-500'
                              : 'bg-red-500'
                          }`}
                          style={{ width: `${accuracy * 100}%` }}
                        />
                      </div>
                      <span className="text-sm w-12 text-right">
                        {(accuracy * 100).toFixed(0)}%
                      </span>
                    </div>
                  )
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Document Details - Full Width */}
      {!testRunId ? (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <p className="text-gray-600">Select a test run to view results.</p>
        </div>
      ) : !selectedDocument ? (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <p className="text-gray-600">Select a document to view details.</p>
        </div>
      ) : documentLoading ? (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <p className="text-gray-500">Loading...</p>
        </div>
      ) : documentData?.data ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Left: Document Image */}
          <div className="bg-white rounded-lg shadow p-4">
            <h3 className="font-semibold mb-3">Document Image</h3>
            <div className="border rounded overflow-hidden">
              {imageLoading ? (
                <p className="text-sm text-gray-500 p-4">Loading image...</p>
              ) : documentImageUrl ? (
                <img src={documentImageUrl} alt="Document" className="w-full" />
              ) : (
                <p className="text-sm text-gray-400 p-4">Image unavailable</p>
              )}
            </div>
          </div>

          {/* Right: Extracted Fields + Layout + OCR */}
          <div className="space-y-4">
            {/* Extracted Fields */}
            {documentData.data.extracted_fields?.length > 0 && (
              <div className="bg-white rounded-lg shadow p-4">
                <h3 className="font-semibold mb-3">Extracted Fields</h3>
                <div className="space-y-2">
                  {documentData.data.extracted_fields.map((field, idx) => (
                    <div key={idx} className="p-2 bg-gray-50 rounded text-sm">
                      <div className="flex justify-between">
                        <span className="font-medium">{field.field_name}</span>
                        <span className={`${
                          field.match_score >= 0.8 ? 'text-green-600'
                            : field.match_score >= 0.5 ? 'text-yellow-600'
                            : 'text-red-600'
                        }`}>
                          {(field.match_score * 100).toFixed(0)}%
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-2 mt-1">
                        <div>
                          <span className="text-xs text-gray-500">Expected:</span>
                          <p className="text-xs">{field.expected_value}</p>
                        </div>
                        <div>
                          <span className="text-xs text-gray-500">Extracted:</span>
                          <p className="text-xs">{field.extracted_value || '(empty)'}</p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Layout Regions with inline OCR text */}
            {(layoutRegions.length > 0 || ocrRegions.length > 0) && (
              <div className="bg-white rounded-lg shadow p-4">
                <h3 className="font-semibold mb-3">
                  Layout Regions & OCR Text
                </h3>

                {layoutRegions.length > 0 ? (
                  <div className="space-y-2">
                    {layoutRegions.map((region, idx) => {
                      const regionId = region.id ?? idx + 1
                      const ocrForRegion = ocrByRegionId[regionId]
                      return (
                        <div key={idx} className="border rounded-lg p-3">
                          {/* Region header */}
                          <div className="flex items-center gap-2 mb-1">
                            <span className="w-6 h-6 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold flex-shrink-0">
                              {regionId}
                            </span>
                            <span className="text-sm font-medium">{region.type}</span>
                            <span className="text-xs text-gray-400">
                              ({region.bbox?.x1},{region.bbox?.y1})-({region.bbox?.x2},{region.bbox?.y2})
                            </span>
                            <span className="text-xs text-gray-500 ml-auto">
                              {Math.round((region.confidence || 0) * 100)}%
                            </span>
                          </div>

                          {/* OCR text for this region */}
                          {ocrForRegion ? (
                            <div className="ml-8">
                              {ocrForRegion.full_text && (
                                <div className="bg-gray-50 px-3 py-2 rounded text-sm font-mono mb-1">
                                  {ocrForRegion.full_text}
                                </div>
                              )}
                              {ocrForRegion.lines?.length > 0 && (
                                <div className="space-y-0.5">
                                  {ocrForRegion.lines.map((line, lineIdx) => (
                                    <div key={lineIdx} className="flex items-center gap-2 text-xs">
                                      <span className="text-gray-400 w-4">{lineIdx + 1}</span>
                                      <span className="font-mono flex-1">{line.text}</span>
                                      <span className="text-gray-400">
                                        {Math.round((line.confidence || 0) * 100)}%
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          ) : (
                            <p className="ml-8 text-xs text-gray-400 italic">No OCR text for this region</p>
                          )}
                        </div>
                      )
                    })}
                  </div>
                ) : ocrRegions.length > 0 ? (
                  /* If no layout regions but OCR regions exist (e.g., full-text mode) */
                  <div className="space-y-2">
                    {ocrRegions.map((ocrRegion, idx) => (
                      <div key={idx} className="border rounded-lg p-3">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="w-6 h-6 rounded-full bg-green-100 text-green-700 flex items-center justify-center text-xs font-bold flex-shrink-0">
                            {ocrRegion.region_id != null ? ocrRegion.region_id : idx + 1}
                          </span>
                          <span className="text-sm font-medium">
                            Region {ocrRegion.region_id != null ? ocrRegion.region_id : idx + 1}
                          </span>
                        </div>
                        {ocrRegion.full_text && (
                          <div className="bg-gray-50 px-3 py-2 rounded text-sm font-mono mb-1 ml-8">
                            {ocrRegion.full_text}
                          </div>
                        )}
                        {ocrRegion.lines?.length > 0 && (
                          <div className="space-y-0.5 ml-8">
                            {ocrRegion.lines.map((line, lineIdx) => (
                              <div key={lineIdx} className="flex items-center gap-2 text-xs">
                                <span className="text-gray-400 w-4">{lineIdx + 1}</span>
                                <span className="font-mono flex-1">{line.text}</span>
                                <span className="text-gray-400">
                                  {Math.round((line.confidence || 0) * 100)}%
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}

export default ResultsPage
