import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { syntheticAPI, referenceAPI } from '../services/api'
import MagnifyImage from '../components/MagnifyImage'
import PageNavigator from '../components/PageNavigator'

function ViewDataPage() {
  const queryClient = useQueryClient()
  const [selectedBatchId, setSelectedBatchId] = useState('')
  const [userFilter, setUserFilter] = useState('')
  const [currentDocIndex, setCurrentDocIndex] = useState(0)
  const [currentPage, setCurrentPage] = useState(0)
  const [documentImageUrl, setDocumentImageUrl] = useState(null)
  const [imageLoading, setImageLoading] = useState(false)

  // Management mode state
  const [managementMode, setManagementMode] = useState(null) // null | 'merge' | 'remove' | 'append' | 'upload-ref'
  const [selectedBatchIds, setSelectedBatchIds] = useState([]) // for merge
  const [selectedDocIds, setSelectedDocIds] = useState([]) // for remove / append
  const [appendTargetBatchId, setAppendTargetBatchId] = useState('')
  const [deleteConfirmBatchId, setDeleteConfirmBatchId] = useState(null)

  // Fetch all batches
  const { data: batchesData, isLoading: batchesLoading } = useQuery({
    queryKey: ['batches'],
    queryFn: () => syntheticAPI.listBatches(),
  })

  // Fetch selected batch details (includes documents)
  const { data: batchData, isLoading: batchLoading } = useQuery({
    queryKey: ['batch', selectedBatchId],
    queryFn: () => syntheticAPI.getBatch(selectedBatchId),
    enabled: !!selectedBatchId,
  })

  const batches = batchesData?.data?.batches || []
  const documents = batchData?.data?.documents || []
  const pageCount = batchData?.data?.page_count || 1

  // Extract unique users from batches
  const uniqueUsers = [...new Set(
    batches
      .map(b => b.created_by_name)
      .filter(Boolean)
      .map(name => name.split('@')[0])
  )].sort()

  // Filter batches by user
  const filteredBatches = userFilter
    ? batches.filter(b => b.created_by_name && b.created_by_name.split('@')[0] === userFilter)
    : batches

  // Reset doc index and page when batch changes
  useEffect(() => {
    setCurrentDocIndex(0)
    setCurrentPage(0)
    setDocumentImageUrl(null)
    exitMode()
  }, [selectedBatchId])

  // Reset page when document index changes
  useEffect(() => {
    setCurrentPage(0)
  }, [currentDocIndex])

  // Fetch document image when index or page changes
  useEffect(() => {
    if (selectedBatchId && documents.length > 0 && currentDocIndex < documents.length) {
      const doc = documents[currentDocIndex]
      setImageLoading(true)
      setDocumentImageUrl(null)
      syntheticAPI.getDocumentImage(selectedBatchId, doc.id, currentPage)
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
  }, [selectedBatchId, currentDocIndex, documents.length, currentPage])

  const currentDoc = documents[currentDocIndex] || null

  const goToPrev = () => {
    if (currentDocIndex > 0) setCurrentDocIndex(currentDocIndex - 1)
  }
  const goToNext = () => {
    if (currentDocIndex < documents.length - 1) setCurrentDocIndex(currentDocIndex + 1)
  }

  // --- Mutations ---
  const mergeMutation = useMutation({
    mutationFn: (sourceBatchIds) => syntheticAPI.mergeBatches(sourceBatchIds),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['batches'] })
      setSelectedBatchId(response.data.id)
      exitMode()
    },
  })

  const removeMutation = useMutation({
    mutationFn: ({ batchId, documentIds }) => syntheticAPI.removeDocuments(batchId, documentIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['batches'] })
      queryClient.invalidateQueries({ queryKey: ['batch', selectedBatchId] })
      setCurrentDocIndex(0)
      exitMode()
    },
  })

  const appendMutation = useMutation({
    mutationFn: ({ targetBatchId, sourceBatchId, documentIds }) =>
      syntheticAPI.appendDocuments(targetBatchId, sourceBatchId, documentIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['batches'] })
      exitMode()
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (batchId) => syntheticAPI.deleteBatch(batchId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['batches'] })
      setSelectedBatchId('')
      setDeleteConfirmBatchId(null)
    },
  })

  const exitMode = () => {
    setManagementMode(null)
    setSelectedBatchIds([])
    setSelectedDocIds([])
    setAppendTargetBatchId('')
  }

  const toggleDocSelection = (docId) => {
    setSelectedDocIds(prev =>
      prev.includes(docId) ? prev.filter(id => id !== docId) : [...prev, docId]
    )
  }

  const toggleBatchSelection = (batchId) => {
    setSelectedBatchIds(prev =>
      prev.includes(batchId) ? prev.filter(id => id !== batchId) : [...prev, batchId]
    )
  }

  // Current batch's form_id for filtering merge/append candidates
  const currentFormId = batchData?.data?.form_id
  const samFormBatches = batches.filter(b => b.form_id === currentFormId && b.id !== selectedBatchId)

  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">View Data</h2>

      {/* Filter Bar */}
      <div className="bg-white rounded-lg shadow p-4 mb-4">
        <div className="flex flex-wrap items-end gap-4">
          {/* User Filter */}
          <div className="min-w-[180px]">
            <label className="block text-sm font-medium text-gray-700 mb-1">User</label>
            <select
              value={userFilter}
              onChange={(e) => {
                setUserFilter(e.target.value)
                setSelectedBatchId('')
              }}
              className="w-full px-3 py-2 border rounded-md text-sm"
            >
              <option value="">All Users</option>
              {uniqueUsers.map((user) => (
                <option key={user} value={user}>{user}</option>
              ))}
            </select>
          </div>

          {/* Batch Dropdown */}
          <div className="flex-1 min-w-[300px]">
            <label className="block text-sm font-medium text-gray-700 mb-1">Batch</label>
            <select
              value={selectedBatchId}
              onChange={(e) => setSelectedBatchId(e.target.value)}
              className="w-full px-3 py-2 border rounded-md text-sm"
            >
              <option value="">-- Select a batch --</option>
              {filteredBatches.map((batch) => (
                <option key={batch.id} value={batch.id}>
                  {batch.batch_number} - {batch.form_name}
                  {' - '}{new Date(batch.created_at).toLocaleDateString()}
                  {batch.created_by_name ? ` - ${batch.created_by_name.split('@')[0]}` : ''}
                  {` (${batch.count} docs)`}
                  {batch.batch_type === 'handwritten' ? ' [Handwritten]' : ''}
                </option>
              ))}
            </select>
          </div>

          {/* Document count */}
          {selectedBatchId && documents.length > 0 && !managementMode && (
            <div className="text-sm text-gray-600 pb-2">
              Document {currentDocIndex + 1} of {documents.length}
            </div>
          )}
        </div>

        {/* Action Toolbar - shown when a batch is selected */}
        {selectedBatchId && !managementMode && (
          <div className="flex items-center gap-2 mt-3 pt-3 border-t">
            <button
              onClick={() => {
                setManagementMode('merge')
                setSelectedBatchIds([selectedBatchId])
              }}
              className="px-3 py-1.5 text-xs font-medium bg-blue-50 text-blue-700 rounded hover:bg-blue-100"
            >
              Merge Batches
            </button>
            <button
              onClick={() => setManagementMode('remove')}
              className="px-3 py-1.5 text-xs font-medium bg-yellow-50 text-yellow-700 rounded hover:bg-yellow-100"
            >
              Remove Documents
            </button>
            <button
              onClick={() => setManagementMode('append')}
              className="px-3 py-1.5 text-xs font-medium bg-green-50 text-green-700 rounded hover:bg-green-100"
            >
              Append To...
            </button>
            <button
              onClick={() => setManagementMode('upload-ref')}
              className="px-3 py-1.5 text-xs font-medium bg-purple-50 text-purple-700 rounded hover:bg-purple-100"
            >
              Upload Reference Data
            </button>
            <div className="flex-1" />
            <button
              onClick={() => setDeleteConfirmBatchId(selectedBatchId)}
              className="px-3 py-1.5 text-xs font-medium bg-red-50 text-red-700 rounded hover:bg-red-100"
            >
              Delete Batch
            </button>
          </div>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirmBatchId && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-sm mx-4">
            <h3 className="text-lg font-semibold mb-2">Delete Batch?</h3>
            <p className="text-sm text-gray-600 mb-4">
              This will permanently delete the batch <strong>{batchData?.data?.batch_number}</strong> and all its {documents.length} documents. This action cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setDeleteConfirmBatchId(null)}
                className="px-4 py-2 text-sm bg-gray-100 rounded hover:bg-gray-200"
              >
                Cancel
              </button>
              <button
                onClick={() => deleteMutation.mutate(deleteConfirmBatchId)}
                disabled={deleteMutation.isPending}
                className="px-4 py-2 text-sm bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
              >
                {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
              </button>
            </div>
            {deleteMutation.isError && (
              <p className="text-xs text-red-600 mt-2">
                Error: {deleteMutation.error?.response?.data?.detail || 'Failed to delete batch'}
              </p>
            )}
          </div>
        </div>
      )}

      {/* ===== MERGE MODE ===== */}
      {managementMode === 'merge' && (
        <div className="bg-white rounded-lg shadow p-4 mb-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold">Select Batches to Merge</h3>
            <span className="text-xs text-gray-500">Only batches with the same form are shown</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 max-h-[400px] overflow-y-auto">
            {batches
              .filter(b => b.form_id === currentFormId)
              .map(batch => (
                <div
                  key={batch.id}
                  onClick={() => toggleBatchSelection(batch.id)}
                  className={`cursor-pointer rounded-lg border-2 p-3 transition-all hover:shadow-md ${
                    selectedBatchIds.includes(batch.id)
                      ? 'border-blue-500 bg-blue-50 shadow-sm'
                      : 'border-gray-200 bg-white hover:border-gray-300'
                  }`}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2">
                      <h4 className="font-semibold text-sm">{batch.batch_number}</h4>
                      <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                        batch.batch_type === 'handwritten'
                          ? 'bg-purple-100 text-purple-700'
                          : 'bg-blue-100 text-blue-700'
                      }`}>
                        {batch.batch_type === 'handwritten' ? 'Handwritten' : 'Synthetic'}
                      </span>
                    </div>
                    <input
                      type="checkbox"
                      checked={selectedBatchIds.includes(batch.id)}
                      onChange={() => toggleBatchSelection(batch.id)}
                      className="rounded mt-0.5"
                    />
                  </div>
                  <p className="text-xs text-gray-600 mt-1 truncate">{batch.form_name}</p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {batch.count} docs · {new Date(batch.created_at).toLocaleDateString()}
                  </p>
                </div>
              ))}
          </div>
          <div className="flex items-center justify-between mt-3">
            <span className="text-sm text-gray-600">
              {selectedBatchIds.length} batch{selectedBatchIds.length !== 1 ? 'es' : ''} selected
              ({batches.filter(b => selectedBatchIds.includes(b.id)).reduce((s, b) => s + b.count, 0)} total docs)
            </span>
            <div className="flex gap-2">
              <button
                onClick={exitMode}
                className="px-4 py-2 text-sm bg-gray-100 rounded hover:bg-gray-200"
              >
                Cancel
              </button>
              <button
                onClick={() => mergeMutation.mutate(selectedBatchIds)}
                disabled={selectedBatchIds.length < 2 || mergeMutation.isPending}
                className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
              >
                {mergeMutation.isPending ? 'Merging...' : 'Create Merged Batch'}
              </button>
            </div>
          </div>
          {mergeMutation.isError && (
            <p className="text-xs text-red-600 mt-2">
              Error: {mergeMutation.error?.response?.data?.detail || 'Failed to merge batches'}
            </p>
          )}
        </div>
      )}

      {/* ===== UPLOAD REFERENCE DATA MODE ===== */}
      {managementMode === 'upload-ref' && selectedBatchId && (
        <BatchReferenceUploader
          batchId={selectedBatchId}
          documentCount={documents.length}
          onDone={() => {
            exitMode()
            queryClient.invalidateQueries(['batch', selectedBatchId])
          }}
          onCancel={exitMode}
        />
      )}

      {/* Main Content */}
      {!selectedBatchId ? (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <p className="text-gray-600">Select a batch to view its documents.</p>
        </div>
      ) : batchLoading ? (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <p className="text-gray-500">Loading batch...</p>
        </div>
      ) : documents.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <p className="text-gray-600">No documents in this batch.</p>
        </div>
      ) : managementMode === 'merge' || managementMode === 'upload-ref' ? null : (
        <>
          {/* Remove / Append action bar */}
          {(managementMode === 'remove' || managementMode === 'append') && (
            <div className={`rounded-lg shadow p-3 mb-4 flex items-center gap-3 ${
              managementMode === 'remove' ? 'bg-yellow-50 border border-yellow-200' : 'bg-green-50 border border-green-200'
            }`}>
              <span className="text-sm font-medium">
                {selectedDocIds.length} document{selectedDocIds.length !== 1 ? 's' : ''} selected
              </span>

              {managementMode === 'append' && (
                <select
                  value={appendTargetBatchId}
                  onChange={(e) => setAppendTargetBatchId(e.target.value)}
                  className="px-2 py-1 text-sm border rounded"
                >
                  <option value="">-- Target batch --</option>
                  {samFormBatches.map(b => (
                    <option key={b.id} value={b.id}>
                      {b.batch_number} - {b.form_name} ({b.count} docs)
                    </option>
                  ))}
                </select>
              )}

              <div className="flex-1" />

              <button
                onClick={exitMode}
                className="px-3 py-1.5 text-xs bg-gray-100 rounded hover:bg-gray-200"
              >
                Cancel
              </button>

              {managementMode === 'remove' && (
                <button
                  onClick={() => removeMutation.mutate({ batchId: selectedBatchId, documentIds: selectedDocIds })}
                  disabled={selectedDocIds.length === 0 || removeMutation.isPending}
                  className="px-3 py-1.5 text-xs bg-yellow-600 text-white rounded hover:bg-yellow-700 disabled:opacity-50"
                >
                  {removeMutation.isPending ? 'Removing...' : 'Remove Selected'}
                </button>
              )}

              {managementMode === 'append' && (
                <button
                  onClick={() => appendMutation.mutate({
                    targetBatchId: appendTargetBatchId,
                    sourceBatchId: selectedBatchId,
                    documentIds: selectedDocIds,
                  })}
                  disabled={selectedDocIds.length === 0 || !appendTargetBatchId || appendMutation.isPending}
                  className="px-3 py-1.5 text-xs bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
                >
                  {appendMutation.isPending ? 'Appending...' : 'Append'}
                </button>
              )}

              {(removeMutation.isError || appendMutation.isError) && (
                <span className="text-xs text-red-600">
                  {removeMutation.error?.response?.data?.detail || appendMutation.error?.response?.data?.detail || 'Operation failed'}
                </span>
              )}
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Left: Document Image with Carousel */}
            <div className="bg-white rounded-lg shadow p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold">Document Image</h3>
                <div className="flex items-center gap-2">
                  <button
                    onClick={goToPrev}
                    disabled={currentDocIndex === 0}
                    className="px-3 py-1 text-sm bg-gray-100 rounded hover:bg-gray-200 disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    Prev
                  </button>
                  <span className="text-sm text-gray-600 min-w-[60px] text-center">
                    {currentDocIndex + 1} / {documents.length}
                  </span>
                  <button
                    onClick={goToNext}
                    disabled={currentDocIndex === documents.length - 1}
                    className="px-3 py-1 text-sm bg-gray-100 rounded hover:bg-gray-200 disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    Next
                  </button>
                </div>
              </div>

              {/* Thumbnail strip with optional selection checkboxes */}
              <div className="flex gap-1 mb-3 overflow-x-auto pb-2">
                {documents.map((doc, idx) => (
                  <button
                    key={doc.id}
                    onClick={() => {
                      if (managementMode === 'remove' || managementMode === 'append') {
                        toggleDocSelection(doc.id)
                      } else {
                        setCurrentDocIndex(idx)
                      }
                    }}
                    className={`flex-shrink-0 w-10 h-10 rounded border-2 text-xs font-medium flex items-center justify-center relative ${
                      (managementMode === 'remove' || managementMode === 'append') && selectedDocIds.includes(doc.id)
                        ? managementMode === 'remove'
                          ? 'border-yellow-500 bg-yellow-50 text-yellow-700'
                          : 'border-green-500 bg-green-50 text-green-700'
                        : idx === currentDocIndex
                          ? 'border-blue-600 bg-blue-50 text-blue-700'
                          : 'border-gray-200 bg-gray-50 text-gray-500 hover:border-gray-400'
                    }`}
                  >
                    {(managementMode === 'remove' || managementMode === 'append') && selectedDocIds.includes(doc.id) && (
                      <span className="absolute -top-1 -right-1 w-3.5 h-3.5 bg-current rounded-full flex items-center justify-center">
                        <span className="text-white text-[8px]">✓</span>
                      </span>
                    )}
                    {idx + 1}
                  </button>
                ))}
              </div>

              {/* Select all / deselect all helpers in selection modes */}
              {(managementMode === 'remove' || managementMode === 'append') && (
                <div className="flex gap-2 mb-2">
                  <button
                    onClick={() => setSelectedDocIds(documents.map(d => d.id))}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    Select All
                  </button>
                  <button
                    onClick={() => setSelectedDocIds([])}
                    className="text-xs text-blue-600 hover:underline"
                  >
                    Deselect All
                  </button>
                </div>
              )}

              {/* Image display */}
              <div className="border rounded overflow-hidden">
                {imageLoading ? (
                  <div className="p-8 text-center text-gray-500">Loading image...</div>
                ) : documentImageUrl ? (
                  <MagnifyImage src={documentImageUrl} alt={`Document ${currentDocIndex + 1}`} />
                ) : (
                  <div className="p-8 text-center text-gray-400">Image unavailable</div>
                )}
              </div>
              <PageNavigator
                currentPage={currentPage}
                pageCount={pageCount}
                onPageChange={setCurrentPage}
              />
            </div>

            {/* Right: Document Details */}
            <div className="space-y-4">
              {/* Document Info */}
              <div className="bg-white rounded-lg shadow p-4">
                <h3 className="font-semibold mb-3">Document Info</h3>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Document ID:</span>
                    <span className="font-mono text-xs">{currentDoc?.id}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Batch:</span>
                    <span>{batchData?.data?.batch_number}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Form:</span>
                    <span>{batchData?.data?.form_name}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Type:</span>
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                      batchData?.data?.batch_type === 'handwritten'
                        ? 'bg-purple-100 text-purple-700'
                        : batchData?.data?.batch_type === 'mixed'
                          ? 'bg-orange-100 text-orange-700'
                          : 'bg-blue-100 text-blue-700'
                    }`}>
                      {batchData?.data?.batch_type === 'handwritten' ? 'Handwritten'
                        : batchData?.data?.batch_type === 'mixed' ? 'Mixed'
                        : 'Synthetic'}
                    </span>
                  </div>
                  {batchData?.data?.source_batch_ids && (
                    <div className="flex justify-between">
                      <span className="text-gray-500">Merged from:</span>
                      <span className="text-xs text-gray-600">{batchData.data.source_batch_ids.length} batches</span>
                    </div>
                  )}
                  {batchData?.data?.skew_preset && (
                    <div className="flex justify-between">
                      <span className="text-gray-500">Skew Preset:</span>
                      <span className="capitalize">{batchData.data.skew_preset}</span>
                    </div>
                  )}
                  {currentDoc?.is_skewed && (
                    <div className="flex justify-between">
                      <span className="text-gray-500">Skewed:</span>
                      <span className="text-green-600">Yes</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Field Values (Ground Truth) */}
              {currentDoc?.field_values && Object.keys(currentDoc.field_values).length > 0 && (
                <div className="bg-white rounded-lg shadow p-4">
                  <h3 className="font-semibold mb-3">Field Values (Ground Truth)</h3>
                  <div className="space-y-2">
                    {(() => {
                      // Group by section if reference_data has sections
                      const refData = currentDoc.reference_data || []
                      const hasSections = refData.some(r => r.section)
                      if (hasSections) {
                        const sections = []
                        let currentSection = null
                        for (const r of refData) {
                          if (!r.resolved_value && !r.raw_value) continue
                          if (r.section !== currentSection) {
                            currentSection = r.section
                            sections.push({ section: r.section, page: r.page, fields: [] })
                          }
                          sections[sections.length - 1].fields.push(r)
                        }
                        return sections.map((sec, si) => (
                          <div key={si}>
                            <div className="text-xs font-semibold text-blue-600 mt-2 mb-1">
                              {sec.page && <span className="text-gray-400 mr-1">P{sec.page}</span>}
                              {sec.section}
                            </div>
                            {sec.fields.map((r, fi) => (
                              <div key={fi} className="p-1.5 bg-gray-50 rounded text-sm mb-1">
                                <div className="flex justify-between gap-2">
                                  <span className="font-medium text-gray-700 text-xs font-mono">{r.field_name}</span>
                                  <span className="font-mono text-xs text-right">{r.resolved_value || r.raw_value}</span>
                                </div>
                              </div>
                            ))}
                          </div>
                        ))
                      }
                      return Object.entries(currentDoc.field_values).map(([field, value]) => (
                        <div key={field} className="p-2 bg-gray-50 rounded text-sm">
                          <div className="flex justify-between">
                            <span className="font-medium text-gray-700">{field}</span>
                            <span className="font-mono">{value}</span>
                          </div>
                        </div>
                      ))
                    })()}
                  </div>
                </div>
              )}

              {/* Inline Reference Data Editing */}
              {currentDoc && (
                <ReferenceDataEditor
                  batchId={selectedBatchId}
                  documentId={currentDoc.id}
                  referenceData={currentDoc.reference_data}
                  hasFieldValues={currentDoc.field_values && Object.keys(currentDoc.field_values).length > 0}
                  batchType={batchData?.data?.batch_type}
                />
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function BatchReferenceUploader({ batchId, documentCount, onDone, onCancel }) {
  const fileInputRef = useRef(null)
  const [selectedFile, setSelectedFile] = useState(null)
  const [previewRows, setPreviewRows] = useState(null)
  const [parseError, setParseError] = useState(null)

  const uploadMutation = useMutation({
    mutationFn: (formData) => referenceAPI.uploadBatchRef(batchId, formData),
    onSuccess: (response) => {
      onDone()
    },
  })

  const handleFileSelect = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setSelectedFile(file)
    setParseError(null)

    // Client-side preview for CSV files
    if (file.name.endsWith('.csv')) {
      const reader = new FileReader()
      reader.onload = (evt) => {
        try {
          const text = evt.target.result
          const lines = text.split('\n').filter(l => l.trim())
          const rows = []
          // Detect 5-column format by checking first header
          const headerParts = lines[0]?.split(',').map(s => s.trim().replace(/^"|"$/g, '').toLowerCase()) || []
          const is5col = ['page', 'page_number', 'page_num', 'pg'].includes(headerParts[0])
          for (let i = 1; i < lines.length; i++) {
            const parts = lines[i].split(',').map(s => s.trim().replace(/^"|"$/g, ''))
            if (is5col) {
              if (parts[2]) {
                rows.push({
                  page: parts[0] || '',
                  section: parts[1] || '',
                  field_name: parts[2]?.replace(/^\*/, '') || '',
                  raw_value: parts[3] || '',
                  resolved_value: parts[4] || '',
                })
              }
            } else {
              if (parts[0] && parts[0].toLowerCase() !== 'field_name') {
                rows.push({
                  field_name: parts[0]?.replace(/^\*/, '') || '',
                  raw_value: parts[1] || '',
                  resolved_value: parts[2] || '',
                })
              }
            }
          }
          setPreviewRows(rows)
        } catch {
          setParseError('Failed to parse CSV')
        }
      }
      reader.readAsText(file)
    } else {
      // For Excel files, show file info but can't preview client-side
      setPreviewRows(null)
    }
  }

  const updatePreviewRow = (idx, field, value) => {
    setPreviewRows(prev => prev.map((r, i) => i === idx ? { ...r, [field]: value } : r))
  }

  const addPreviewRow = () => {
    setPreviewRows(prev => [...(prev || []), { field_name: '', raw_value: '', resolved_value: '' }])
  }

  const removePreviewRow = (idx) => {
    setPreviewRows(prev => prev.filter((_, i) => i !== idx))
  }

  const handleUpload = () => {
    if (!selectedFile) return
    const formData = new FormData()
    formData.append('reference_file', selectedFile)
    uploadMutation.mutate(formData)
  }

  return (
    <div className="bg-white rounded-lg shadow p-4 mb-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold">Upload Reference Data for Entire Batch</h3>
        <button onClick={onCancel} className="text-xs text-gray-500 hover:text-gray-700">Cancel</button>
      </div>

      <p className="text-sm text-gray-600 mb-3">
        Upload an Excel (.xlsx) or CSV file with reference data. This will apply to <strong>all {documentCount} documents</strong> in the batch.
        <br />
        <span className="text-xs text-gray-500">
          Supported formats: <strong>5-column</strong> (Page | Section | Field | Raw Value | Resolved Value) or <strong>3-column</strong> (field_name | raw_value | resolved_value)
        </span>
      </p>

      <div className="mb-3">
        <button
          onClick={() => referenceAPI.downloadTemplate('prisoner-registration')}
          className="text-xs text-purple-600 hover:text-purple-800 underline"
        >
          Download Prisoner Registration Template (.xlsx)
        </button>
      </div>

      <div className="flex items-center gap-3 mb-4">
        <input
          ref={fileInputRef}
          type="file"
          accept=".xlsx,.csv"
          onChange={handleFileSelect}
          className="hidden"
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          className="px-4 py-2 text-sm border-2 border-dashed border-gray-300 rounded-lg hover:border-purple-400 hover:bg-purple-50"
        >
          {selectedFile ? selectedFile.name : 'Choose Excel/CSV file...'}
        </button>
        {selectedFile && (
          <button
            onClick={() => { setSelectedFile(null); setPreviewRows(null); if (fileInputRef.current) fileInputRef.current.value = '' }}
            className="text-xs text-red-500 hover:underline"
          >
            Clear
          </button>
        )}
      </div>

      {/* Preview table for CSV (editable before upload) */}
      {previewRows && previewRows.length > 0 && (() => {
        const has5col = previewRows.some(r => r.page || r.section)
        return (
        <div className="mb-4">
          <h4 className="text-sm font-medium mb-2">Preview & Edit ({previewRows.length} fields) {has5col && <span className="text-xs text-purple-600 ml-1">5-column format</span>}</h4>
          <div className="overflow-x-auto max-h-[400px] overflow-y-auto border rounded">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr className="text-xs text-gray-500 border-b">
                  {has5col && <th className="text-left py-2 px-2 w-12">Pg</th>}
                  {has5col && <th className="text-left py-2 px-2">Section</th>}
                  <th className="text-left py-2 px-2">Field Name</th>
                  <th className="text-left py-2 px-2">Raw Value</th>
                  <th className="text-left py-2 px-2">Resolved Value</th>
                  <th className="w-8 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {previewRows.map((row, idx) => (
                  <tr key={idx} className="border-b last:border-b-0 hover:bg-gray-50">
                    {has5col && (
                      <td className="py-1 px-2">
                        <input type="text" value={row.page || ''} onChange={(e) => updatePreviewRow(idx, 'page', e.target.value)} className="w-full px-1 py-0.5 border rounded text-xs" />
                      </td>
                    )}
                    {has5col && (
                      <td className="py-1 px-2">
                        <input type="text" value={row.section || ''} onChange={(e) => updatePreviewRow(idx, 'section', e.target.value)} className="w-full px-1 py-0.5 border rounded text-xs" />
                      </td>
                    )}
                    <td className="py-1 px-2">
                      <input
                        type="text"
                        value={row.field_name}
                        onChange={(e) => updatePreviewRow(idx, 'field_name', e.target.value)}
                        className="w-full px-1 py-0.5 border rounded text-xs font-mono"
                      />
                    </td>
                    <td className="py-1 px-2">
                      <input
                        type="text"
                        value={row.raw_value}
                        onChange={(e) => updatePreviewRow(idx, 'raw_value', e.target.value)}
                        className="w-full px-1 py-0.5 border rounded text-xs"
                      />
                    </td>
                    <td className="py-1 px-2">
                      <input
                        type="text"
                        value={row.resolved_value}
                        onChange={(e) => updatePreviewRow(idx, 'resolved_value', e.target.value)}
                        className="w-full px-1 py-0.5 border rounded text-xs"
                      />
                    </td>
                    <td className="py-1 px-1">
                      <button onClick={() => removePreviewRow(idx)} className="text-red-500 text-xs">x</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            onClick={addPreviewRow}
            className="mt-2 text-xs text-blue-600 hover:underline"
          >
            + Add Row
          </button>
        </div>
        )
      })()}

      {selectedFile && !previewRows && (
        <p className="text-sm text-gray-500 mb-4 italic">
          Excel files will be parsed on the server. Click "Apply to All Documents" to upload and apply.
        </p>
      )}

      {parseError && (
        <p className="text-xs text-red-600 mb-3">{parseError}</p>
      )}

      <div className="flex gap-2">
        <button
          onClick={handleUpload}
          disabled={!selectedFile || uploadMutation.isPending}
          className="px-4 py-2 text-sm bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50"
        >
          {uploadMutation.isPending ? 'Applying...' : `Apply to All ${documentCount} Documents`}
        </button>
        <button
          onClick={onCancel}
          className="px-4 py-2 text-sm bg-gray-100 rounded hover:bg-gray-200"
        >
          Cancel
        </button>
      </div>

      {uploadMutation.isSuccess && (
        <p className="text-sm text-green-600 mt-2">
          Reference data applied to all documents!
        </p>
      )}
      {uploadMutation.isError && (
        <p className="text-xs text-red-600 mt-2">
          {uploadMutation.error?.response?.data?.detail || 'Failed to upload reference data'}
        </p>
      )}
    </div>
  )
}


function ReferenceDataEditor({ batchId, documentId, referenceData, hasFieldValues, batchType }) {
  const queryClient = useQueryClient()
  const [editMode, setEditMode] = useState(false)
  const [rows, setRows] = useState([])

  // Initialize rows from referenceData
  useEffect(() => {
    if (referenceData && referenceData.length > 0) {
      setRows(referenceData.map(r => ({ ...r })))
    } else {
      setRows([])
    }
    setEditMode(false)
  }, [referenceData, documentId])

  const saveMutation = useMutation({
    mutationFn: (data) => referenceAPI.updateDocumentRef(batchId, documentId, data),
    onSuccess: () => {
      queryClient.invalidateQueries(['batch', batchId])
      setEditMode(false)
    },
  })

  const handleSave = () => {
    saveMutation.mutate({ reference_data: rows })
  }

  const updateRow = (idx, field, value) => {
    setRows(prev => prev.map((r, i) => i === idx ? { ...r, [field]: value } : r))
  }

  const hasSections = rows.some(r => r.section || r.page)

  const addRow = () => {
    setRows(prev => [...prev, { page: '', section: '', field_name: '', raw_value: '', resolved_value: '' }])
  }

  const removeRow = (idx) => {
    setRows(prev => prev.filter((_, i) => i !== idx))
  }

  // Don't show if there's no reference data and this is a synthetic doc with field_values
  if (!referenceData && hasFieldValues) return null

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold">
          Reference Data
          {rows.length > 0 && <span className="ml-1 text-xs text-gray-400">({rows.length} fields)</span>}
        </h3>
        <div className="flex gap-2">
          {!editMode ? (
            <button
              onClick={() => {
                if (rows.length === 0) addRow()
                setEditMode(true)
              }}
              className="px-3 py-1 text-xs bg-blue-50 text-blue-700 rounded hover:bg-blue-100"
            >
              {rows.length > 0 ? 'Edit' : 'Add Reference Data'}
            </button>
          ) : (
            <>
              <button
                onClick={handleSave}
                disabled={saveMutation.isPending}
                className="px-3 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
              >
                {saveMutation.isPending ? 'Saving...' : 'Save'}
              </button>
              <button
                onClick={() => {
                  setRows(referenceData ? referenceData.map(r => ({ ...r })) : [])
                  setEditMode(false)
                }}
                className="px-3 py-1 text-xs bg-gray-100 rounded hover:bg-gray-200"
              >
                Cancel
              </button>
            </>
          )}
        </div>
      </div>

      {rows.length === 0 && !editMode ? (
        <p className="text-sm text-gray-500 italic">
          No reference data.{' '}
          {batchType === 'handwritten' && 'Click "Add Reference Data" to add ground truth values.'}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-gray-500 border-b">
                {hasSections && <th className="text-left py-1 pr-1 w-8">Pg</th>}
                {hasSections && <th className="text-left py-1 pr-2">Section</th>}
                <th className="text-left py-1 pr-2">Field Name</th>
                <th className="text-left py-1 pr-2">Raw Value</th>
                <th className="text-left py-1">Resolved Value</th>
                {editMode && <th className="w-8"></th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => (
                <tr key={idx} className="border-b last:border-b-0">
                  {hasSections && (
                    <td className="py-1 pr-1">
                      {editMode ? (
                        <input
                          type="text"
                          value={row.page || ''}
                          onChange={(e) => updateRow(idx, 'page', e.target.value)}
                          className="w-full px-1 py-0.5 border rounded text-xs"
                          style={{ width: '2rem' }}
                        />
                      ) : (
                        <span className="text-xs text-gray-400">{row.page}</span>
                      )}
                    </td>
                  )}
                  {hasSections && (
                    <td className="py-1 pr-2">
                      {editMode ? (
                        <input
                          type="text"
                          value={row.section || ''}
                          onChange={(e) => updateRow(idx, 'section', e.target.value)}
                          className="w-full px-1 py-0.5 border rounded text-xs"
                        />
                      ) : (
                        <span className="text-xs text-blue-600">{row.section}</span>
                      )}
                    </td>
                  )}
                  <td className="py-1 pr-2">
                    {editMode ? (
                      <input
                        type="text"
                        value={row.field_name}
                        onChange={(e) => updateRow(idx, 'field_name', e.target.value)}
                        className="w-full px-1 py-0.5 border rounded text-xs"
                      />
                    ) : (
                      <span className="font-medium text-xs font-mono">{row.field_name}</span>
                    )}
                  </td>
                  <td className="py-1 pr-2">
                    {editMode ? (
                      <input
                        type="text"
                        value={row.raw_value}
                        onChange={(e) => updateRow(idx, 'raw_value', e.target.value)}
                        className="w-full px-1 py-0.5 border rounded text-xs"
                      />
                    ) : (
                      <span className="text-xs text-gray-600">{row.raw_value}</span>
                    )}
                  </td>
                  <td className="py-1">
                    {editMode ? (
                      <input
                        type="text"
                        value={row.resolved_value}
                        onChange={(e) => updateRow(idx, 'resolved_value', e.target.value)}
                        className="w-full px-1 py-0.5 border rounded text-xs"
                      />
                    ) : (
                      <span className="text-xs font-mono">{row.resolved_value}</span>
                    )}
                  </td>
                  {editMode && (
                    <td className="py-1">
                      <button onClick={() => removeRow(idx)} className="text-red-500 text-xs">x</button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          {editMode && (
            <button
              onClick={addRow}
              className="mt-2 text-xs text-blue-600 hover:underline"
            >
              + Add Row
            </button>
          )}
        </div>
      )}

      {saveMutation.isError && (
        <p className="text-xs text-red-600 mt-2">
          {saveMutation.error?.response?.data?.detail || 'Failed to save'}
        </p>
      )}
    </div>
  )
}


export default ViewDataPage
