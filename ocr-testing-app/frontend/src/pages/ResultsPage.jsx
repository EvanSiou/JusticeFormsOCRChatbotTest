import { useState, useEffect, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useParams, useNavigate } from 'react-router-dom'
import { testsAPI, resultsAPI } from '../services/api'
import MagnifyImage from '../components/MagnifyImage'
import PageNavigator from '../components/PageNavigator'

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
  const [currentPage, setCurrentPage] = useState(0)
  const [pageCount, setPageCount] = useState(1)
  const [showOcr, setShowOcr] = useState(true)
  const [showClassification, setShowClassification] = useState(true)
  const [showJudge, setShowJudge] = useState(true)

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

  // Reset to first page when selected document changes
  useEffect(() => {
    setCurrentPage(0)
  }, [selectedDocument])

  // Store page count from document data
  useEffect(() => {
    if (documentData?.data?.page_count) {
      setPageCount(documentData.data.page_count)
    } else {
      setPageCount(1)
    }
  }, [documentData])

  // Fetch document image as blob
  const [documentImageUrl, setDocumentImageUrl] = useState(null)
  const [imageLoading, setImageLoading] = useState(false)

  useEffect(() => {
    if (testRunId && selectedDocument) {
      setImageLoading(true)
      setDocumentImageUrl(null)
      resultsAPI.getDocumentImage(testRunId, selectedDocument, currentPage)
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
  }, [testRunId, selectedDocument, currentPage])

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

  // Sort extracted fields by layout region position
  const sortedFields = useMemo(() => {
    const fields = documentData?.data?.extracted_fields || []
    if (fields.length === 0 || layoutRegions.length === 0) return fields

    return [...fields].sort((a, b) => {
      const findRegionPos = (field) => {
        for (const region of layoutRegions) {
          const ocrForRegion = ocrByRegionId[region.id]
          if (!ocrForRegion) continue
          if (ocrForRegion.full_text && ocrForRegion.full_text.includes(field.extracted_value)) {
            return { y: region.bbox?.y1 || 0, x: region.bbox?.x1 || 0 }
          }
          for (const line of (ocrForRegion.lines || [])) {
            if (line.text === field.extracted_value) {
              return { y: region.bbox?.y1 || 0, x: region.bbox?.x1 || 0 }
            }
          }
        }
        return { y: 99999, x: 99999 }
      }
      const posA = findRegionPos(a)
      const posB = findRegionPos(b)
      if (posA.y !== posB.y) return posA.y - posB.y
      return posA.x - posB.x
    })
  }, [documentData?.data?.extracted_fields, layoutRegions, ocrByRegionId])

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
                  {run.classifier_model ? ` cls:${run.classifier_model}` : ''}
                  {run.judge_model ? ` judge:${run.judge_model}` : ''}
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
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
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
          </div>

          {/* Dual Accuracy + Judge cards (shown only when data exists) */}
          {(summaryData.data.average_ocr_accuracy != null || summaryData.data.average_classification_accuracy != null || summaryData.data.average_judge_score != null) && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4 pt-4 border-t">
              {summaryData.data.average_ocr_accuracy != null && (
                <div>
                  <p className="text-sm text-gray-500">OCR Accuracy</p>
                  <p className="text-xl font-bold text-blue-600">
                    {(summaryData.data.average_ocr_accuracy * 100).toFixed(1)}%
                  </p>
                </div>
              )}
              {summaryData.data.average_classification_accuracy != null && (
                <div>
                  <p className="text-sm text-gray-500">Classification Accuracy</p>
                  <p className="text-xl font-bold text-purple-600">
                    {(summaryData.data.average_classification_accuracy * 100).toFixed(1)}%
                  </p>
                </div>
              )}
              {summaryData.data.average_judge_score != null && (
                <div>
                  <p className="text-sm text-gray-500">Judge Score</p>
                  <p className="text-xl font-bold text-amber-600">
                    {(summaryData.data.average_judge_score * 100).toFixed(1)}%
                  </p>
                </div>
              )}
              {summaryData.data.classifier_model && (
                <div>
                  <p className="text-sm text-gray-500">Classifier</p>
                  <p className="text-sm font-medium">{summaryData.data.classifier_model}</p>
                  {summaryData.data.judge_model && (
                    <>
                      <p className="text-sm text-gray-500 mt-1">Judge</p>
                      <p className="text-sm font-medium">{summaryData.data.judge_model}</p>
                    </>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Duration */}
          {(() => {
            const currentRun = allCompletedRuns.find(r => r.id === testRunId)
            const duration = currentRun ? formatDuration(currentRun.started_at, currentRun.completed_at) : null
            return duration ? (
              <div className="pt-2 border-t">
                <span className="text-sm text-gray-500">Duration: </span>
                <span className="text-sm font-bold text-gray-700">{duration}</span>
                {summaryData.data.is_unified && (
                  <span className="ml-2 px-2 py-0.5 bg-green-100 text-green-700 rounded text-xs">unified</span>
                )}
              </div>
            ) : null
          })()}
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
                <MagnifyImage src={documentImageUrl} alt="Document" />
              ) : (
                <p className="text-sm text-gray-400 p-4">Image unavailable</p>
              )}
            </div>
            <PageNavigator
              currentPage={currentPage}
              pageCount={pageCount}
              onPageChange={setCurrentPage}
            />
          </div>

          {/* Right: Extracted Fields + Layout + OCR */}
          <div className="space-y-4">
            {/* Extracted Fields — Table with toggle buttons */}
            {sortedFields.length > 0 && (
              <div className="bg-white rounded-lg shadow p-4">
                {/* Header: title + accuracy badges */}
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-semibold">Field Comparison</h3>
                  <div className="flex gap-1.5 text-xs">
                    {documentData.data.ocr_accuracy != null && (
                      <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded">
                        OCR: {(documentData.data.ocr_accuracy * 100).toFixed(0)}%
                      </span>
                    )}
                    {documentData.data.classification_accuracy != null && (
                      <span className="px-2 py-0.5 bg-purple-100 text-purple-700 rounded">
                        Cls: {(documentData.data.classification_accuracy * 100).toFixed(0)}%
                      </span>
                    )}
                    {documentData.data.judge_overall_score != null && (
                      <span className="px-2 py-0.5 bg-amber-100 text-amber-700 rounded">
                        Judge: {(documentData.data.judge_overall_score * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                </div>

                {/* Toggle buttons */}
                {(() => {
                  const hasOcrData = sortedFields.some(f => f.extracted_value && String(f.extracted_value).length > 0)
                  const hasClsData = sortedFields.some(f => f.classified_value != null && String(f.classified_value).length > 0)
                  const hasJudgeData = sortedFields.some(f => f.judge_score != null)
                  return (
                    <div className="flex gap-2 mb-3">
                      {hasOcrData && (
                        <button
                          onClick={() => setShowOcr(!showOcr)}
                          className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${showOcr ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-500'}`}
                        >
                          OCR
                        </button>
                      )}
                      {hasClsData && (
                        <button
                          onClick={() => setShowClassification(!showClassification)}
                          className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${showClassification ? 'bg-purple-600 text-white' : 'bg-gray-100 text-gray-500'}`}
                        >
                          Classification
                        </button>
                      )}
                      {hasJudgeData && (
                        <button
                          onClick={() => setShowJudge(!showJudge)}
                          className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${showJudge ? 'bg-amber-600 text-white' : 'bg-gray-100 text-gray-500'}`}
                        >
                          Judge
                        </button>
                      )}
                    </div>
                  )
                })()}

                {/* Field rows — original table layout with toggleable columns */}
                <div className="space-y-1">
                  {sortedFields.map((field, idx) => {
                    const displayValue = (val) => {
                      if (val == null) return '—'
                      if (typeof val === 'object') return JSON.stringify(val)
                      return String(val) || '—'
                    }
                    const hasClassification = field.classified_value != null && String(field.classified_value).length > 0
                    const hasJudge = field.judge_score != null
                    const scoreColor = (score) => score >= 0.8 ? 'text-green-600'
                      : score >= 0.5 ? 'text-yellow-600' : 'text-red-600'
                    const bgColor = (score) => score >= 0.8 ? 'bg-green-50'
                      : score >= 0.5 ? 'bg-yellow-50' : 'bg-red-50'

                    // Count visible columns: Expected is always shown
                    const visibleCols = 1 + (showOcr ? 1 : 0) + (showClassification ? 1 : 0)
                    const gridCols = visibleCols <= 1 ? 'grid-cols-1' : visibleCols === 2 ? 'grid-cols-2' : 'grid-cols-3'

                    return (
                      <div key={idx} className="border rounded p-2 text-xs">
                        {/* Row 1: Field name + judge score badge */}
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-semibold text-gray-800">{field.field_name}</span>
                          {showJudge && hasJudge && (
                            <span className={`px-2 py-0.5 rounded text-xs font-bold ${bgColor(field.judge_score)} ${scoreColor(field.judge_score)}`}>
                              Judge: {(field.judge_score * 100).toFixed(0)}%
                            </span>
                          )}
                        </div>

                        {/* Row 2: Expected / (optional OCR) / (optional Classification) */}
                        <div className={`grid ${gridCols} gap-2`}>
                          {/* Expected (Reference) */}
                          <div>
                            <div className="text-gray-400 mb-0.5">Expected</div>
                            <div className="font-mono text-gray-800 break-words">
                              {displayValue(field.expected_value)}
                            </div>
                          </div>

                          {/* OCR Result */}
                          {showOcr && (
                            <div>
                              <div className="text-gray-400 mb-0.5">
                                OCR
                                {field.match_score > 0 && (
                                  <span className={`ml-1 font-mono ${scoreColor(field.match_score)}`}>
                                    {(field.match_score * 100).toFixed(0)}%
                                  </span>
                                )}
                              </div>
                              <div className="font-mono text-gray-800 break-words">
                                {displayValue(field.extracted_value)}
                              </div>
                            </div>
                          )}

                          {/* Classification Result */}
                          {showClassification && (
                            <div>
                              <div className="text-gray-400 mb-0.5">
                                Classification
                                {hasClassification && field.classification_match_score != null && (
                                  <span className={`ml-1 font-mono ${scoreColor(field.classification_match_score)}`}>
                                    {(field.classification_match_score * 100).toFixed(0)}%
                                  </span>
                                )}
                                {field.classification_confidence != null && field.classification_confidence > 0 && (
                                  <span className="ml-1 text-gray-400 font-mono">
                                    conf:{(field.classification_confidence * 100).toFixed(0)}%
                                  </span>
                                )}
                              </div>
                              {field.classified_field_type && (
                                <div className="text-purple-500 text-[10px] mb-0.5">{field.classified_field_type}</div>
                              )}
                              <div className="font-mono text-gray-800 break-words">
                                {hasClassification ? displayValue(field.classified_value) : '—'}
                              </div>
                            </div>
                          )}
                        </div>

                        {/* Row 3: Judge reasoning (if toggled on) */}
                        {showJudge && field.judge_reasoning && (
                          <div className="mt-1 text-gray-500 italic border-t pt-1">
                            {field.judge_reasoning}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Classification Results */}
            {documentData?.data?.classification_results && (
              <div className="bg-white rounded-lg shadow p-4">
                <h3 className="font-semibold mb-3">
                  Classification
                  {documentData.data.classification_results.form_type && (
                    <span className="ml-2 text-sm font-normal text-purple-600">
                      — {documentData.data.classification_results.form_type}
                    </span>
                  )}
                </h3>
                {documentData.data.classification_results.classified_fields?.length > 0 ? (
                  <div className="space-y-1">
                    {documentData.data.classification_results.classified_fields.map((cf, idx) => (
                      <div key={idx} className="flex items-center gap-2 p-2 bg-gray-50 rounded text-sm">
                        <span className="px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-700 whitespace-nowrap">
                          {cf.field_type}
                        </span>
                        <span className="flex-1 font-mono text-xs">{typeof cf.value === 'object' ? JSON.stringify(cf.value) : String(cf.value ?? '')}</span>
                        {cf.context && (
                          <span className="text-xs text-gray-400 truncate max-w-[120px]" title={cf.context}>
                            {cf.context}
                          </span>
                        )}
                        <span className="text-xs text-gray-500">
                          {Math.round((cf.confidence || 0) * 100)}%
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-gray-500">No fields classified.</p>
                )}
                {documentData.data.classification_results.error && (
                  <p className="text-sm text-red-500 mt-2">
                    Error: {documentData.data.classification_results.error}
                  </p>
                )}
              </div>
            )}

            {/* Judge Results */}
            {documentData?.data?.judge_results && !documentData.data.judge_results.error && (
              <div className="bg-white rounded-lg shadow p-4">
                <h3 className="font-semibold mb-3">
                  Judge Evaluation
                  {documentData.data.judge_model && (
                    <span className="ml-2 text-sm font-normal text-amber-600">
                      {documentData.data.judge_model}
                    </span>
                  )}
                </h3>
                {/* Judge summary scores */}
                <div className="flex gap-4 mb-3">
                  {documentData.data.judge_results.overall_ocr_score != null && (
                    <div className="px-3 py-2 bg-blue-50 rounded">
                      <p className="text-xs text-gray-500">Judge OCR Score</p>
                      <p className="text-lg font-bold text-blue-600">
                        {(documentData.data.judge_results.overall_ocr_score * 100).toFixed(0)}%
                      </p>
                    </div>
                  )}
                  {documentData.data.judge_results.overall_classification_score != null && (
                    <div className="px-3 py-2 bg-purple-50 rounded">
                      <p className="text-xs text-gray-500">Judge Cls Score</p>
                      <p className="text-lg font-bold text-purple-600">
                        {(documentData.data.judge_results.overall_classification_score * 100).toFixed(0)}%
                      </p>
                    </div>
                  )}
                </div>
                {documentData.data.judge_results.summary && (
                  <p className="text-sm text-gray-700 mb-3 italic">
                    {documentData.data.judge_results.summary}
                  </p>
                )}
                {/* Per-field judge evaluations */}
                {documentData.data.judge_results.field_evaluations?.length > 0 && (
                  <div className="space-y-1">
                    {documentData.data.judge_results.field_evaluations.map((ev, idx) => (
                      <div key={idx} className="p-2 bg-gray-50 rounded text-sm">
                        <div className="flex items-center justify-between">
                          <span className="font-medium text-xs">{ev.field_name}</span>
                          <div className="flex gap-2 text-xs">
                            <span className={ev.ocr_score >= 0.8 ? 'text-green-600' : ev.ocr_score >= 0.5 ? 'text-yellow-600' : 'text-red-600'}>
                              OCR: {(ev.ocr_score * 100).toFixed(0)}%
                            </span>
                            <span className={ev.classification_score >= 0.8 ? 'text-green-600' : ev.classification_score >= 0.5 ? 'text-yellow-600' : 'text-red-600'}>
                              Cls: {(ev.classification_score * 100).toFixed(0)}%
                            </span>
                          </div>
                        </div>
                        {ev.reasoning && (
                          <p className="text-xs text-gray-500 mt-1">{ev.reasoning}</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
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
