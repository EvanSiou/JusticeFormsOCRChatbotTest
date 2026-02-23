import { useState, useEffect, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams, useNavigate } from 'react-router-dom'
import { testsAPI, verificationAPI } from '../services/api'
import MagnifyImage from '../components/MagnifyImage'
import PageNavigator from '../components/PageNavigator'

function VerifyPage() {
  const { testRunId: paramTestRunId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [selectedTestRunId, setSelectedTestRunId] = useState(paramTestRunId || '')
  const [selectedDocumentId, setSelectedDocumentId] = useState(null)
  const [documentImageUrl, setDocumentImageUrl] = useState(null)
  const [fieldVerifications, setFieldVerifications] = useState({})
  const [regionVerifications, setRegionVerifications] = useState({})
  const [addedRegions, setAddedRegions] = useState([])
  const [currentPage, setCurrentPage] = useState(0)
  const [pageCount, setPageCount] = useState(1)
  const [userFilter, setUserFilter] = useState('')

  // Fetch completed test runs
  const { data: testsData } = useQuery({
    queryKey: ['tests'],
    queryFn: () => testsAPI.list(),
  })

  const allCompletedRuns = testsData?.data?.test_runs?.filter(
    (r) => r.status === 'completed'
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

  // Fetch documents for verification
  const { data: documentsData } = useQuery({
    queryKey: ['verify-documents', selectedTestRunId],
    queryFn: () => verificationAPI.getDocuments(selectedTestRunId),
    enabled: !!selectedTestRunId,
  })

  // Fetch verification summary
  const { data: summaryData } = useQuery({
    queryKey: ['verify-summary', selectedTestRunId],
    queryFn: () => verificationAPI.getSummary(selectedTestRunId),
    enabled: !!selectedTestRunId,
  })

  // Fetch selected document details
  const { data: documentData } = useQuery({
    queryKey: ['verify-document', selectedTestRunId, selectedDocumentId],
    queryFn: () => verificationAPI.getDocument(selectedTestRunId, selectedDocumentId),
    enabled: !!selectedTestRunId && !!selectedDocumentId,
  })

  // Reset to first page when document changes
  useEffect(() => {
    setCurrentPage(0)
  }, [selectedDocumentId])

  // Load document image
  useEffect(() => {
    if (selectedTestRunId && selectedDocumentId) {
      verificationAPI.getDocumentImage(selectedTestRunId, selectedDocumentId, currentPage)
        .then((url) => setDocumentImageUrl(url))
        .catch(() => setDocumentImageUrl(null))
    }
    return () => {
      if (documentImageUrl) URL.revokeObjectURL(documentImageUrl)
    }
  }, [selectedTestRunId, selectedDocumentId, currentPage]) // eslint-disable-line react-hooks/exhaustive-deps

  // Initialize field verifications when document data loads
  useEffect(() => {
    if (documentData?.data) {
      const doc = documentData.data
      setPageCount(doc.page_count || 1)
      // Synthetic fields
      if (doc.extracted_fields?.length > 0) {
        const initial = {}
        doc.extracted_fields.forEach((f) => {
          initial[f.field_name] = {
            status: f.verification_status || 'unverified',
            corrected_value: f.corrected_value || '',
          }
        })
        setFieldVerifications(initial)
      }
      // Handwritten: init region verifications from existing data
      if (doc.ocr_results?.text_regions) {
        const regVerif = {}
        doc.ocr_results.text_regions.forEach((r, i) => {
          if (r.user_added) return // skip user-added ones; they'll be in addedRegions
          regVerif[i] = {
            is_important: r.is_important || false,
            status: r.verification_status || 'unverified',
            corrected_value: r.corrected_value || '',
          }
        })
        setRegionVerifications(regVerif)
        // Restore previously added regions
        const added = doc.ocr_results.text_regions
          .filter(r => r.user_added)
          .map(r => ({ text: r.text || '' }))
        setAddedRegions(added)
      } else {
        setRegionVerifications({})
        setAddedRegions([])
      }
    }
  }, [documentData])

  // Submit verification mutation
  const verifyMutation = useMutation({
    mutationFn: () => {
      const doc = documentData?.data
      const isHw = doc?.batch_type === 'handwritten'

      if (isHw) {
        // Build text_regions array from regionVerifications
        const textRegions = Object.entries(regionVerifications).map(([idx, data]) => ({
          region_index: parseInt(idx),
          text: doc.ocr_results.text_regions[parseInt(idx)]?.text || '',
          is_important: data.is_important,
          verification_status: data.status,
          corrected_value: data.status === 'corrected' ? data.corrected_value : null,
        }))
        const added = addedRegions.filter(r => r.text.trim())
        return verificationAPI.verifyDocument(
          selectedTestRunId, selectedDocumentId, [], textRegions, added.length > 0 ? added : null
        )
      } else {
        // Synthetic: all fields are important
        const fields = Object.entries(fieldVerifications).map(([name, data]) => ({
          field_name: name,
          verification_status: data.status,
          corrected_value: data.status === 'corrected' ? data.corrected_value : null,
          is_important: true,
        }))
        return verificationAPI.verifyDocument(selectedTestRunId, selectedDocumentId, fields)
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries(['verify-documents', selectedTestRunId])
      queryClient.invalidateQueries(['verify-summary', selectedTestRunId])
      queryClient.invalidateQueries(['verify-document', selectedTestRunId, selectedDocumentId])
      // Move to next unverified document
      const docs = documentsData?.data?.documents || []
      const currentIdx = docs.findIndex((d) => d.document_id === selectedDocumentId)
      const nextUnverified = docs.find(
        (d, i) => i > currentIdx && d.verification_status === 'unverified'
      )
      if (nextUnverified) {
        setSelectedDocumentId(nextUnverified.document_id)
      }
    },
  })

  const handleFieldStatus = (fieldName, newStatus) => {
    setFieldVerifications((prev) => ({
      ...prev,
      [fieldName]: { ...prev[fieldName], status: newStatus },
    }))
  }

  const handleCorrectedValue = (fieldName, value) => {
    setFieldVerifications((prev) => ({
      ...prev,
      [fieldName]: { ...prev[fieldName], corrected_value: value, status: 'corrected' },
    }))
  }

  const handleRegionImportant = (idx) => {
    setRegionVerifications((prev) => ({
      ...prev,
      [idx]: { ...prev[idx], is_important: !prev[idx]?.is_important },
    }))
  }

  const handleRegionStatus = (idx, newStatus) => {
    setRegionVerifications((prev) => ({
      ...prev,
      [idx]: { ...prev[idx], status: newStatus },
    }))
  }

  const handleRegionCorrectedValue = (idx, value) => {
    setRegionVerifications((prev) => ({
      ...prev,
      [idx]: { ...prev[idx], corrected_value: value, status: 'corrected' },
    }))
  }

  const summary = summaryData?.data
  const documents = documentsData?.data?.documents || []
  const doc = documentData?.data
  const isHandwritten = doc?.batch_type === 'handwritten'

  // Build layout + OCR region lookup
  const layoutRegions = doc?.layout_results?.regions || []
  const ocrRegions = doc?.ocr_results?.regions || []
  const ocrByRegionId = {}
  ocrRegions.forEach((r) => {
    ocrByRegionId[r.region_id] = r
  })

  // Collect all unique OCR text values for the dropdown
  const allOcrTexts = (() => {
    if (!doc?.ocr_results) return []
    const texts = new Set()
    // From regions' full_text
    for (const r of (doc.ocr_results.regions || [])) {
      if (r.full_text?.trim()) texts.add(r.full_text.trim())
      for (const line of (r.lines || [])) {
        if (line.text?.trim()) texts.add(line.text.trim())
      }
    }
    // From text_regions
    for (const r of (doc.ocr_results.text_regions || [])) {
      if (r.text?.trim()) texts.add(r.text.trim())
    }
    return [...texts].sort((a, b) => a.localeCompare(b))
  })()

  // Sort extracted fields by layout region position (top-to-bottom, left-to-right)
  const sortedFields = useMemo(() => {
    const fields = doc?.extracted_fields || []
    if (fields.length === 0 || layoutRegions.length === 0) return fields

    // For each field, find which layout region contains its best-matched OCR text
    return [...fields].sort((a, b) => {
      const findRegionY = (field) => {
        // Search layout regions for the one whose OCR text matches this field's extracted_value
        for (const region of layoutRegions) {
          const regionId = region.id
          const ocrForRegion = ocrByRegionId[regionId]
          if (!ocrForRegion) continue
          // Check full_text match
          if (ocrForRegion.full_text && ocrForRegion.full_text.includes(field.extracted_value)) {
            return { y: region.bbox?.y1 || 0, x: region.bbox?.x1 || 0 }
          }
          // Check individual lines
          for (const line of (ocrForRegion.lines || [])) {
            if (line.text === field.extracted_value) {
              return { y: region.bbox?.y1 || 0, x: region.bbox?.x1 || 0 }
            }
          }
        }
        return { y: 99999, x: 99999 }
      }
      const posA = findRegionY(a)
      const posB = findRegionY(b)
      if (posA.y !== posB.y) return posA.y - posB.y
      return posA.x - posB.x
    })
  }, [doc?.extracted_fields, layoutRegions, ocrByRegionId])

  // Filter text regions (exclude user_added ones for display)
  const textRegions = (doc?.ocr_results?.text_regions || []).filter(r => !r.user_added)

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">Verify Results</h2>

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
                  setSelectedDocumentId(null)
                  setSelectedTestRunId('')
                  navigate('/verify')
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
              value={selectedTestRunId || ''}
              onChange={(e) => {
                const val = e.target.value
                setSelectedTestRunId(val)
                setSelectedDocumentId(null)
                if (val) navigate(`/verify/${val}`)
                else navigate('/verify')
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
              value={selectedDocumentId || ''}
              onChange={(e) => setSelectedDocumentId(e.target.value || null)}
              className="w-full px-3 py-2 border rounded-md text-sm"
              disabled={!selectedTestRunId || documents.length === 0}
            >
              <option value="">-- Select a document --</option>
              {documents.map((d, idx) => {
                const statusIcon = d.verification_status === 'verified' ? '[V]'
                  : d.verification_status === 'corrected' ? '[C]'
                  : ''
                return (
                  <option key={d.document_id} value={d.document_id}>
                    Doc {idx + 1} - {Math.round(d.overall_accuracy * 100)}% {statusIcon}
                  </option>
                )
              })}
            </select>
          </div>

          {/* Verification Progress inline */}
          {summary && (
            <div className="flex items-center gap-3">
              <div className="w-32 bg-gray-200 rounded-full h-2">
                <div
                  className="bg-green-600 h-2 rounded-full transition-all"
                  style={{ width: `${summary.progress_percent || 0}%` }}
                />
              </div>
              <span className="text-sm text-gray-600 whitespace-nowrap">
                {summary.verified + summary.corrected}/{summary.total} verified
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Main Content - Full Width */}
      {!selectedTestRunId ? (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <p className="text-gray-500">Select a test run to begin verification.</p>
        </div>
      ) : !selectedDocumentId ? (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <p className="text-gray-500">Select a document to verify.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Left Column: Image + Layout/OCR */}
          <div className="space-y-4">
            {/* Document Image */}
            <div className="bg-white rounded-lg shadow p-4">
              <h3 className="font-semibold mb-3">Document Image</h3>
              {documentImageUrl ? (
                <MagnifyImage src={documentImageUrl} alt="Document" />
              ) : (
                <div className="h-48 bg-gray-100 rounded flex items-center justify-center">
                  <p className="text-gray-500">Loading image...</p>
                </div>
              )}
              {pageCount > 1 && (
                <PageNavigator
                  currentPage={currentPage}
                  pageCount={pageCount}
                  onPageChange={setCurrentPage}
                />
              )}
            </div>

            {/* Layout Regions with inline OCR text (synthetic only) */}
            {!isHandwritten && (layoutRegions.length > 0 || ocrRegions.length > 0) && (
              <div className="bg-white rounded-lg shadow p-4">
                <h3 className="font-semibold mb-3">Layout Regions & OCR Text</h3>

                {layoutRegions.length > 0 ? (
                  <div className="space-y-2">
                    {layoutRegions.map((region, idx) => {
                      const regionId = region.id ?? idx + 1
                      const ocrForRegion = ocrByRegionId[regionId]
                      return (
                        <div key={idx} className="border rounded-lg p-3">
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

          {/* Right Column: Verification Panel */}
          <div className="space-y-4">
            <div className="bg-white rounded-lg shadow p-4">
              <h3 className="font-semibold mb-3">
                {isHandwritten ? 'OCR Text Verification' : 'Field Verification'}
              </h3>

              {/* Synthetic batch: field-by-field verification */}
              {!isHandwritten && sortedFields.length > 0 && (
                <div className="space-y-3">
                  {sortedFields.map((field) => {
                    const verification = fieldVerifications[field.field_name] || {}
                    return (
                      <div key={field.field_name} className="border rounded-lg p-3">
                        <div className="flex justify-between items-start mb-2">
                          <div>
                            <span className="font-medium text-sm">{field.field_name}</span>
                            <span className="text-xs text-gray-400 ml-2">
                              ({Math.round(field.match_score * 100)}% match)
                            </span>
                          </div>
                          <span className={`text-xs px-2 py-0.5 rounded ${
                            field.match_score >= 0.8 ? 'bg-green-100 text-green-700'
                              : field.match_score >= 0.5 ? 'bg-yellow-100 text-yellow-700'
                              : 'bg-red-100 text-red-700'
                          }`}>
                            {Math.round(field.confidence * 100)}% conf
                          </span>
                        </div>

                        <div className="grid grid-cols-2 gap-4 text-sm mb-2">
                          <div>
                            <p className="text-xs text-gray-500">Expected</p>
                            <p className="font-mono bg-green-50 px-2 py-1 rounded">
                              {field.expected_value}
                            </p>
                          </div>
                          <div>
                            <p className="text-xs text-gray-500">Extracted</p>
                            <p className="font-mono bg-blue-50 px-2 py-1 rounded">
                              {field.extracted_value || '(empty)'}
                            </p>
                          </div>
                        </div>

                        {/* OCR values dropdown */}
                        {allOcrTexts.length > 0 && (
                          <div className="mb-2">
                            <select
                              value=""
                              onChange={(e) => {
                                if (e.target.value) {
                                  handleCorrectedValue(field.field_name, e.target.value)
                                }
                              }}
                              className="w-full px-2 py-1 border rounded text-sm text-gray-600"
                            >
                              <option value="">Select from OCR values...</option>
                              {allOcrTexts.map((text, i) => (
                                <option key={i} value={text}>
                                  {text.length > 80 ? text.slice(0, 80) + '...' : text}
                                </option>
                              ))}
                            </select>
                          </div>
                        )}

                        <div className="flex items-center gap-3">
                          <label className="flex items-center gap-1 text-sm cursor-pointer">
                            <input
                              type="radio"
                              name={`verify-${field.field_name}`}
                              checked={verification.status === 'verified'}
                              onChange={() => handleFieldStatus(field.field_name, 'verified')}
                            />
                            <span className="text-green-700">Correct</span>
                          </label>
                          <label className="flex items-center gap-1 text-sm cursor-pointer">
                            <input
                              type="radio"
                              name={`verify-${field.field_name}`}
                              checked={verification.status === 'corrected'}
                              onChange={() => handleFieldStatus(field.field_name, 'corrected')}
                            />
                            <span className="text-yellow-700">Incorrect</span>
                          </label>
                          {verification.status === 'corrected' && (
                            <input
                              type="text"
                              value={verification.corrected_value || ''}
                              onChange={(e) =>
                                handleCorrectedValue(field.field_name, e.target.value)
                              }
                              placeholder="Enter correct value"
                              className="flex-1 px-2 py-1 border rounded text-sm"
                            />
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}

              {/* Handwritten batch: text region verification with importance tagging */}
              {isHandwritten && doc?.ocr_results && (
                <div className="space-y-4">
                  <p className="text-sm text-gray-600">
                    Tag regions containing actual handwriting as "Important". Only important regions count toward accuracy.
                  </p>

                  {textRegions.length > 0 && (
                    <div className="space-y-2">
                      {textRegions.map((region, idx) => {
                        const rv = regionVerifications[idx] || { is_important: false, status: 'unverified', corrected_value: '' }
                        return (
                          <div
                            key={idx}
                            className={`border-2 rounded-lg p-3 transition-colors ${
                              rv.is_important
                                ? 'border-yellow-400 bg-yellow-50'
                                : 'border-gray-200 bg-white'
                            }`}
                          >
                            <div className="flex items-center gap-3 mb-2">
                              <span className="text-xs text-gray-400 w-6 flex-shrink-0">{idx + 1}</span>
                              <div className="font-mono text-sm flex-1 bg-gray-50 px-2 py-1 rounded">
                                {region.text}
                              </div>
                              <span className="text-xs text-gray-400 flex-shrink-0">
                                {Math.round((region.confidence || 0) * 100)}%
                              </span>
                              <button
                                type="button"
                                onClick={() => handleRegionImportant(idx)}
                                className={`px-3 py-1 rounded text-xs font-medium flex-shrink-0 ${
                                  rv.is_important
                                    ? 'bg-yellow-400 text-yellow-900'
                                    : 'bg-gray-200 text-gray-500 hover:bg-gray-300'
                                }`}
                              >
                                {rv.is_important ? 'IMPORTANT' : 'not important'}
                              </button>
                            </div>

                            {/* Correct/Incorrect controls - only when important */}
                            {rv.is_important && (
                              <div className="flex items-center gap-3 ml-9">
                                <label className="flex items-center gap-1 text-sm cursor-pointer">
                                  <input
                                    type="radio"
                                    name={`region-${idx}`}
                                    checked={rv.status === 'verified'}
                                    onChange={() => handleRegionStatus(idx, 'verified')}
                                  />
                                  <span className="text-green-700">Correct</span>
                                </label>
                                <label className="flex items-center gap-1 text-sm cursor-pointer">
                                  <input
                                    type="radio"
                                    name={`region-${idx}`}
                                    checked={rv.status === 'corrected'}
                                    onChange={() => handleRegionStatus(idx, 'corrected')}
                                  />
                                  <span className="text-yellow-700">Incorrect</span>
                                </label>
                                {rv.status === 'corrected' && (
                                  <input
                                    type="text"
                                    value={rv.corrected_value || ''}
                                    onChange={(e) =>
                                      handleRegionCorrectedValue(idx, e.target.value)
                                    }
                                    placeholder="Enter correct text"
                                    className="flex-1 px-2 py-1 border rounded text-sm"
                                  />
                                )}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}

                  {/* Add Missed Text Section */}
                  <div className="border-t pt-4">
                    <div className="flex items-center justify-between mb-2">
                      <h4 className="text-sm font-medium">Add Missed Handwriting</h4>
                      <button
                        type="button"
                        onClick={() => setAddedRegions((prev) => [...prev, { text: '' }])}
                        className="px-3 py-1 bg-blue-100 text-blue-700 rounded text-xs hover:bg-blue-200"
                      >
                        + Add Text
                      </button>
                    </div>
                    {addedRegions.length > 0 && (
                      <div className="space-y-2">
                        {addedRegions.map((added, idx) => (
                          <div key={idx} className="flex items-center gap-2">
                            <input
                              type="text"
                              value={added.text}
                              onChange={(e) => {
                                setAddedRegions((prev) => {
                                  const copy = [...prev]
                                  copy[idx] = { text: e.target.value }
                                  return copy
                                })
                              }}
                              placeholder="Enter missed handwriting text"
                              className="flex-1 px-2 py-1 border rounded text-sm font-mono"
                            />
                            <button
                              type="button"
                              onClick={() => setAddedRegions((prev) => prev.filter((_, i) => i !== idx))}
                              className="px-2 py-1 text-red-500 hover:text-red-700 text-sm"
                            >
                              Remove
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                    {addedRegions.length === 0 && (
                      <p className="text-xs text-gray-400">No missed text added yet.</p>
                    )}
                  </div>
                </div>
              )}

              {/* No fields case */}
              {!isHandwritten && (!doc?.extracted_fields || doc.extracted_fields.length === 0) && (
                <p className="text-sm text-gray-500">
                  No extracted fields to verify for this document.
                </p>
              )}

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
                  Verification submitted successfully.
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

export default VerifyPage
