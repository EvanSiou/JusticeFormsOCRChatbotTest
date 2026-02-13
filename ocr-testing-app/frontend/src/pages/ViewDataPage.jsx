import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { syntheticAPI } from '../services/api'
import MagnifyImage from '../components/MagnifyImage'

function ViewDataPage() {
  const queryClient = useQueryClient()
  const [selectedBatchId, setSelectedBatchId] = useState('')
  const [userFilter, setUserFilter] = useState('')
  const [currentDocIndex, setCurrentDocIndex] = useState(0)
  const [documentImageUrl, setDocumentImageUrl] = useState(null)
  const [imageLoading, setImageLoading] = useState(false)

  // Management mode state
  const [managementMode, setManagementMode] = useState(null) // null | 'merge' | 'remove' | 'append'
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

  // Reset doc index when batch changes
  useEffect(() => {
    setCurrentDocIndex(0)
    setDocumentImageUrl(null)
    exitMode()
  }, [selectedBatchId])

  // Fetch document image when index changes
  useEffect(() => {
    if (selectedBatchId && documents.length > 0 && currentDocIndex < documents.length) {
      const doc = documents[currentDocIndex]
      setImageLoading(true)
      setDocumentImageUrl(null)
      syntheticAPI.getDocumentImage(selectedBatchId, doc.id)
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
  }, [selectedBatchId, currentDocIndex, documents.length])

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
          <div className="max-h-[300px] overflow-y-auto border rounded">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="w-8 p-2"></th>
                  <th className="text-left p-2">Batch</th>
                  <th className="text-left p-2">Form</th>
                  <th className="text-left p-2">Type</th>
                  <th className="text-right p-2">Docs</th>
                  <th className="text-left p-2">Date</th>
                </tr>
              </thead>
              <tbody>
                {batches
                  .filter(b => b.form_id === currentFormId)
                  .map(batch => (
                    <tr
                      key={batch.id}
                      onClick={() => toggleBatchSelection(batch.id)}
                      className={`cursor-pointer border-t hover:bg-gray-50 ${
                        selectedBatchIds.includes(batch.id) ? 'bg-blue-50' : ''
                      }`}
                    >
                      <td className="p-2 text-center">
                        <input
                          type="checkbox"
                          checked={selectedBatchIds.includes(batch.id)}
                          onChange={() => toggleBatchSelection(batch.id)}
                          className="rounded"
                        />
                      </td>
                      <td className="p-2 font-medium">{batch.batch_number}</td>
                      <td className="p-2 text-gray-600">{batch.form_name}</td>
                      <td className="p-2">
                        <span className={`px-1.5 py-0.5 rounded text-xs ${
                          batch.batch_type === 'handwritten'
                            ? 'bg-purple-100 text-purple-700'
                            : 'bg-blue-100 text-blue-700'
                        }`}>
                          {batch.batch_type}
                        </span>
                      </td>
                      <td className="p-2 text-right">{batch.count}</td>
                      <td className="p-2 text-gray-500">{new Date(batch.created_at).toLocaleDateString()}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
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
      ) : managementMode === 'merge' ? null : (
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

              {/* Field Values (for synthetic documents) */}
              {currentDoc?.field_values && Object.keys(currentDoc.field_values).length > 0 && (
                <div className="bg-white rounded-lg shadow p-4">
                  <h3 className="font-semibold mb-3">Field Values (Ground Truth)</h3>
                  <div className="space-y-2">
                    {Object.entries(currentDoc.field_values).map(([field, value]) => (
                      <div key={field} className="p-2 bg-gray-50 rounded text-sm">
                        <div className="flex justify-between">
                          <span className="font-medium text-gray-700">{field}</span>
                          <span className="font-mono">{value}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Empty state for handwritten (no field values) */}
              {currentDoc && (!currentDoc.field_values || Object.keys(currentDoc.field_values).length === 0) && (
                <div className="bg-white rounded-lg shadow p-4">
                  <h3 className="font-semibold mb-3">Field Values</h3>
                  <p className="text-sm text-gray-500 italic">
                    No ground truth fields. This is a {batchData?.data?.batch_type === 'handwritten' ? 'handwritten' : 'synthetic'} document.
                  </p>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default ViewDataPage
