import { useState, useEffect } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { testsAPI, cleaningAPI, resultsAPI } from '../services/api'

const STANDARD_PATTERNS = [
  // Decoration patterns
  '____', '________', '____________', '________________',
  '____________________', '________________________',
  '----', '--------', '------------',
  '....', '........', '............',
  '::::', '========',
  '( )', '(  )', '[  ]', '[ ]',
  '__.m.',
  '20____',
  // Court form template unigrams (unique words from Personal Bond - Magistration)
  'CAUSE', 'NO.',
  'STATE', 'OF', 'TEXAS',
  'IN', 'THE', 'JUSTICE', 'COURT',
  'PRECINCT',
  'v.',
  'DEFENDANT', 'DEFENDANT.',
  'COUNTY,', 'COUNTY',
  'PERSONAL', 'BOND', 'MAGISTRATION',
  'On', 'Defendant', "Defendant's",
  'appeared', 'before', 'me', 'as', 'a', 'magistrate', 'on', 'the', 'charge', 'of',
  'which', 'is', 'is:',
  'This', 'this',
  'eligible', 'for', 'release', 'personal', 'bond', 'bond.',
  'under', 'Code', 'Criminal', 'Procedure', 'Art.', '17.03(b),',
  'and', 'not', 'civilly', 'committed', 'sexually', 'violent', 'predator',
  'Health', 'Safety', 'Chapter', '841.',
  'obligation', 'remains', 'in', 'full', 'effect', 'until',
  'court', 'court,', 'court.', 'disposes', 'discharges',
  'Additional', 'conditions', 'release,', 'if', 'any,', 'are', 'follows,',
  'or', 'an', 'attached', 'Condition', 'order:',
  'fee', 'authorized', 'by', '17.42',
  'Waived.', 'Assessed', 'amount',
  'ORDERED', 'to', 'be', 'paid', 'costs',
  'condition',
  'I,', 'I', 'case,', 'acknowledge', 'that', 'have', 'been', 'charged', 'with',
  'offense', 'indicated', 'above.',
  'enter', 'into', 'freely', 'voluntarily.',
  'swear', 'will', 'appear', 'appear.', 'at',
  'otherwise', 'directed',
  'pay', 'sum',
  'plus', 'all', 'necessary', 'reasonable', 'expenses', 'incurred', 'any', 'arrest',
  'failure',
  'payable',
  'Signature', 'Date',
  "Interpreter's", '(if', 'any)',
  'Printed', 'Name',
  // Standalone punctuation and short patterns
  '§',
  '_', '.', '(', ')', '$_',
  // Multi-word phrases
  'if any', '(if any)', '(ifany)',
  'Procedure Art', 'by Code of Criminal',
  // Additional template words
  'Art,', 'Interpreters',
]

function CleanDocumentPage() {
  const [userFilter, setUserFilter] = useState('')
  const [selectedTestRun, setSelectedTestRun] = useState('')
  const [useStandardPatterns, setUseStandardPatterns] = useState(true)
  const [customWords, setCustomWords] = useState('')
  const [showPatterns, setShowPatterns] = useState(false)
  const [previewData, setPreviewData] = useState(null)
  const [currentDocIndex, setCurrentDocIndex] = useState(0)
  const [saved, setSaved] = useState(false)
  const [savedCount, setSavedCount] = useState(0)
  const [documentImageUrl, setDocumentImageUrl] = useState(null)

  // Fetch test runs (completed only)
  const { data: testsData, isLoading: testsLoading } = useQuery({
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

  // Preview mutation
  const previewMutation = useMutation({
    mutationFn: () => {
      const customList = customWords
        .split('\n')
        .map((w) => w.trim())
        .filter(Boolean)
      return cleaningAPI.preview({
        test_run_id: selectedTestRun,
        use_standard_patterns: useStandardPatterns,
        custom_words: customList.length > 0 ? customList : null,
      })
    },
    onSuccess: (response) => {
      setPreviewData(response.data)
      setCurrentDocIndex(0)
      setSaved(false)
    },
  })

  // Save mutation
  const saveMutation = useMutation({
    mutationFn: () => {
      const customList = customWords
        .split('\n')
        .map((w) => w.trim())
        .filter(Boolean)
      return cleaningAPI.save(selectedTestRun, {
        test_run_id: selectedTestRun,
        use_standard_patterns: useStandardPatterns,
        custom_words: customList.length > 0 ? customList : null,
      })
    },
    onSuccess: (response) => {
      setSaved(true)
      setSavedCount(response.data?.documents_cleaned || 0)
    },
  })

  const currentDoc = previewData?.documents?.[currentDocIndex]
  const hasOptions = useStandardPatterns || customWords.trim().length > 0

  // Load document image when current document changes
  useEffect(() => {
    if (selectedTestRun && currentDoc?.document_id) {
      setDocumentImageUrl(null)
      resultsAPI.getDocumentImage(selectedTestRun, currentDoc.document_id)
        .then((url) => setDocumentImageUrl(url))
        .catch(() => setDocumentImageUrl(null))
    } else {
      setDocumentImageUrl(null)
    }
    return () => {
      if (documentImageUrl) URL.revokeObjectURL(documentImageUrl)
    }
  }, [selectedTestRun, currentDoc?.document_id]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Clean Document</h2>

      {/* User Filter + Test Run Selection */}
      <div className="bg-white rounded-lg shadow p-4 mb-6">
        <div className="flex items-end gap-4">
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
                  setPreviewData(null)
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

          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Test Run
            </label>
            <select
              value={selectedTestRun}
              onChange={(e) => {
                setSelectedTestRun(e.target.value)
                setPreviewData(null)
                setSaved(false)
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
        </div>
      </div>

      {/* Cleaning Options */}
      {selectedTestRun && (
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <h3 className="text-lg font-semibold mb-4">Cleaning Options</h3>

          {/* Standard patterns */}
          <div className="mb-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={useStandardPatterns}
                onChange={(e) => setUseStandardPatterns(e.target.checked)}
              />
              <span className="text-sm font-medium">
                Use standard pattern list
              </span>
            </label>
            {useStandardPatterns && (
              <div className="ml-6 mt-2">
                <button
                  onClick={() => setShowPatterns(!showPatterns)}
                  className="text-sm text-blue-600 hover:underline"
                >
                  {showPatterns ? 'Hide' : 'Show'} patterns (
                  {STANDARD_PATTERNS.length})
                </button>
                {showPatterns && (
                  <div className="mt-2 bg-gray-50 rounded p-3 text-xs font-mono max-h-40 overflow-y-auto">
                    {STANDARD_PATTERNS.map((p, i) => (
                      <div key={i} className="text-gray-600">
                        {JSON.stringify(p)}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Custom words */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Custom words/phrases to remove (one per line)
            </label>
            <textarea
              value={customWords}
              onChange={(e) => setCustomWords(e.target.value)}
              rows={5}
              className="w-full px-3 py-2 border rounded-md text-sm font-mono"
              placeholder={"CAUSE NO.\nSTATE OF TEXAS\nDEFENDANT\n..."}
            />
          </div>

          {/* Preview button */}
          <button
            onClick={() => previewMutation.mutate()}
            disabled={!hasOptions || previewMutation.isPending}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {previewMutation.isPending ? 'Generating preview...' : 'Preview Clean'}
          </button>

          {previewMutation.isError && (
            <p className="text-red-600 text-sm mt-2">
              {previewMutation.error?.response?.data?.detail ||
                'Failed to generate preview'}
            </p>
          )}
        </div>
      )}

      {/* Preview Section */}
      {previewData && previewData.documents.length > 0 && (
        <div className="bg-white rounded-lg shadow p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">
              Preview ({previewData.documents.length} documents)
            </h3>

            {/* Document navigator */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => setCurrentDocIndex(Math.max(0, currentDocIndex - 1))}
                disabled={currentDocIndex === 0}
                className="px-2 py-1 text-sm border rounded disabled:opacity-50"
              >
                Prev
              </button>
              <select
                value={currentDocIndex}
                onChange={(e) => setCurrentDocIndex(Number(e.target.value))}
                className="px-2 py-1 text-sm border rounded"
              >
                {previewData.documents.map((doc, i) => (
                  <option key={doc.document_id} value={i}>
                    Doc {i + 1} ({doc.document_id.slice(0, 8)})
                  </option>
                ))}
              </select>
              <button
                onClick={() =>
                  setCurrentDocIndex(
                    Math.min(previewData.documents.length - 1, currentDocIndex + 1)
                  )
                }
                disabled={currentDocIndex === previewData.documents.length - 1}
                className="px-2 py-1 text-sm border rounded disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>

          {/* Three-column: Image | Original | Cleaned */}
          {currentDoc && (
            <div className="grid grid-cols-3 gap-4">
              <div>
                <h4 className="text-sm font-medium text-gray-700 mb-2">
                  Document Image
                </h4>
                <div className="border border-gray-200 rounded bg-gray-50 max-h-[500px] overflow-y-auto">
                  {documentImageUrl ? (
                    <img
                      src={documentImageUrl}
                      alt="Document"
                      className="w-full h-auto"
                    />
                  ) : (
                    <div className="flex items-center justify-center h-48 text-gray-400 text-sm">
                      Loading image...
                    </div>
                  )}
                </div>
              </div>
              <div>
                <h4 className="text-sm font-medium text-red-700 mb-2">
                  Original Text
                </h4>
                <pre className="bg-red-50 border border-red-200 rounded p-3 text-xs whitespace-pre-wrap max-h-[500px] overflow-y-auto">
                  {currentDoc.original_text || '(empty)'}
                </pre>
              </div>
              <div>
                <h4 className="text-sm font-medium text-green-700 mb-2">
                  Cleaned Text
                </h4>
                <pre className="bg-green-50 border border-green-200 rounded p-3 text-xs whitespace-pre-wrap max-h-[500px] overflow-y-auto">
                  {currentDoc.cleaned_text || '(empty)'}
                </pre>
              </div>
            </div>
          )}

          {/* Save button */}
          <div className="mt-6 flex items-center gap-4">
            <button
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending || saved}
              className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
            >
              {saveMutation.isPending
                ? 'Saving...'
                : saved
                ? 'Saved!'
                : 'Save Cleaned Text'}
            </button>

            {saved && (
              <span className="text-green-600 text-sm">
                Cleaned text saved for {savedCount} of {previewData.documents.length} documents.
              </span>
            )}

            {saveMutation.isError && (
              <span className="text-red-600 text-sm">
                {saveMutation.error?.response?.data?.detail || 'Save failed'}
              </span>
            )}
          </div>
        </div>
      )}

      {previewData && previewData.documents.length === 0 && (
        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-gray-600">
            No documents with text found in this test run.
          </p>
        </div>
      )}
    </div>
  )
}

export default CleanDocumentPage
