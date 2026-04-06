import { useState } from 'react'

export default function ResultsViewer({
  sessionId,
  results,
  onFieldEdit,
  onValidateBias,
  biasResult,
  onComplete,
}) {
  const [currentPage, setCurrentPage] = useState(0)
  const [showHints, setShowHints] = useState(false)

  const pageCount = results?.page_count || 1
  const biasPassed = results?.bias_challenge_passed || biasResult?.passed
  const attemptCount = biasResult?.attempt_count || 0
  const maxAttempts = 3
  const hintsRevealed = biasResult?.hints_revealed || false
  const hints = biasResult?.hints || []

  const handleFieldChange = (e) => {
    const el = e.target.closest('[data-field-index]')
    if (!el) return
    const idx = parseInt(el.dataset.fieldIndex)
    if (!isNaN(idx)) {
      // Strip out the confidence badge text — get only the actual value
      const badge = el.querySelector('.conf-badge')
      let newValue = el.textContent
      if (badge) {
        newValue = newValue.replace(badge.textContent, '').trim()
      }
      onFieldEdit?.(idx, newValue)
    }
  }

  const handleValidateBias = () => {
    onValidateBias?.()
  }

  return (
    <div>
      <h3 className="text-lg font-semibold mb-4">Review & Verify Results</h3>

      {/* Bias challenge banner */}
      {!biasPassed && (
        <div className="bg-amber-50 border border-amber-300 rounded-lg p-4 mb-4">
          <p className="font-semibold text-amber-800">
            Verification Required
          </p>
          <p className="text-sm text-amber-700 mt-1">
            Two fields have been intentionally modified to test your attention.
            Find and correct both errors, then click "Verify Corrections" to proceed.
            Fields highlighted in <span className="text-red-600 font-bold">red</span> have low confidence and should be reviewed carefully.
          </p>

          {/* Attempt counter */}
          {attemptCount > 0 && (
            <div className="mt-2 flex items-center gap-2">
              <span className="text-xs text-gray-500">Attempts:</span>
              {[1, 2, 3].map((n) => (
                <span
                  key={n}
                  className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                    n <= attemptCount
                      ? 'bg-red-500 text-white'
                      : 'bg-gray-200 text-gray-400'
                  }`}
                >
                  {n}
                </span>
              ))}
            </div>
          )}

          <div className="mt-3 flex gap-3 items-center flex-wrap">
            <button
              onClick={handleValidateBias}
              className="px-4 py-1.5 bg-amber-600 text-white rounded-md text-sm font-medium hover:bg-amber-700"
            >
              Verify Corrections ({attemptCount}/{maxAttempts})
            </button>

            {biasResult && !biasResult.passed && !hintsRevealed && (
              <span className="text-red-600 text-sm">
                Found {biasResult.found_count}/{biasResult.total_errors} errors.
                {attemptCount < maxAttempts
                  ? ` ${maxAttempts - attemptCount} attempt(s) remaining.`
                  : ''}
              </span>
            )}

            {/* Hints revealed after 3 attempts */}
            {hintsRevealed && (
              <button
                onClick={() => setShowHints(!showHints)}
                className="px-3 py-1.5 bg-blue-500 text-white rounded-md text-sm font-medium hover:bg-blue-600"
              >
                {showHints ? 'Hide Hints' : 'Show Hints'}
              </button>
            )}
          </div>

          {/* Hints panel */}
          {showHints && hints.length > 0 && (
            <div className="mt-3 bg-blue-50 border border-blue-200 rounded-md p-3">
              <p className="text-sm font-semibold text-blue-800 mb-2">
                The following fields were intentionally modified:
              </p>
              {hints.map((hint, i) => (
                <div key={i} className="text-sm mb-2 last:mb-0">
                  <span className="font-medium text-blue-700">
                    {hint.field_type.replace(/_/g, ' ')}
                  </span>
                  <span className="text-gray-500"> — shows </span>
                  <span className="text-red-600 font-mono">"{hint.injected_value}"</span>
                  <span className="text-gray-500"> should be </span>
                  <span className="text-green-600 font-mono">"{hint.correct_value}"</span>
                </div>
              ))}
              <p className="text-xs text-blue-600 mt-2">
                Correct the fields above and click "Verify Corrections" to proceed.
                You may also choose to submit as-is.
              </p>
              <button
                onClick={onComplete}
                className="mt-2 px-4 py-1.5 border border-gray-300 rounded-md text-sm text-gray-600 hover:bg-gray-50"
              >
                Skip & Complete Anyway
              </button>
            </div>
          )}
        </div>
      )}

      {biasPassed && (
        <div className="bg-green-50 border border-green-300 rounded-lg p-3 mb-4 flex items-center justify-between">
          <span className="text-green-700 font-medium">
            All verification errors found and corrected!
          </span>
          <button
            onClick={onComplete}
            className="px-6 py-2 bg-green-600 text-white rounded-md font-medium hover:bg-green-700"
          >
            Complete Processing
          </button>
        </div>
      )}

      {/* Split view */}
      <div className="grid grid-cols-2 gap-4" style={{ minHeight: '600px' }}>
        {/* Left: Original document */}
        <div className="border rounded-lg overflow-hidden">
          <div className="bg-gray-100 px-3 py-2 flex items-center justify-between">
            <span className="text-sm font-medium text-gray-600">Original Document</span>
            {pageCount > 1 && (
              <div className="flex items-center gap-2">
                <button
                  disabled={currentPage === 0}
                  onClick={() => setCurrentPage((p) => p - 1)}
                  className="px-2 py-0.5 text-xs bg-white border rounded disabled:opacity-40"
                >
                  Prev
                </button>
                <span className="text-xs text-gray-500">
                  {currentPage + 1} / {pageCount}
                </span>
                <button
                  disabled={currentPage >= pageCount - 1}
                  onClick={() => setCurrentPage((p) => p + 1)}
                  className="px-2 py-0.5 text-xs bg-white border rounded disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            )}
          </div>
          <div className="p-2 bg-gray-50 overflow-auto" style={{ maxHeight: '700px' }}>
            <img
              src={`/api/processing/${sessionId}/page/${currentPage}/image?corrected=true`}
              alt={`Page ${currentPage + 1}`}
              className="w-full"
            />
          </div>
        </div>

        {/* Right: Extracted fields in form template */}
        <div className="border rounded-lg overflow-hidden">
          <div className="bg-gray-100 px-3 py-2">
            <span className="text-sm font-medium text-gray-600">
              Extracted Data — {results?.form_type?.replace(/_/g, ' ') || 'Unknown Form'}
            </span>
          </div>
          <div
            className="p-4 overflow-auto"
            style={{ maxHeight: '700px' }}
            onBlur={handleFieldChange}
            dangerouslySetInnerHTML={{ __html: results?.rendered_html || '' }}
          />
        </div>
      </div>
    </div>
  )
}
