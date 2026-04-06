export default function CompletionSummary({ summary }) {
  if (!summary) return null

  const corrections = summary.user_corrections || []
  const correctionCount = summary.user_corrections_count || 0

  return (
    <div className="max-w-2xl mx-auto text-center py-10">
      <div className="text-5xl mb-4">&#9989;</div>
      <h3 className="text-2xl font-bold text-green-700 mb-2">Processing Complete</h3>
      <p className="text-gray-500 mb-8">Document has been successfully processed and verified.</p>

      <div className="grid grid-cols-2 gap-6">
        {/* Processing Summary */}
        <div className="bg-white rounded-lg shadow p-6 text-left">
          <h4 className="font-semibold text-gray-700 mb-4">Processing Summary</h4>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="text-gray-500">Form Type</div>
            <div className="font-medium">{summary.form_type?.replace(/_/g, ' ') || 'Unknown'}</div>

            <div className="text-gray-500">Pages Processed</div>
            <div className="font-medium">{summary.pages_processed}</div>

            <div className="text-gray-500">Total Fields</div>
            <div className="font-medium">{summary.total_fields}</div>

            <div className="text-gray-500">Avg. Confidence</div>
            <div className="font-medium text-blue-600">
              {(summary.avg_confidence * 100).toFixed(1)}%
            </div>

            <div className="text-gray-500">Low Confidence Fields</div>
            <div className="font-medium text-amber-600">{summary.low_confidence_count}</div>

            <div className="text-gray-500">Model Used</div>
            <div className="font-medium">{summary.model_used}</div>

            <div className="text-gray-500">Processing Time</div>
            <div className="font-medium">{summary.processing_time_seconds?.toFixed(1)}s</div>
          </div>
        </div>

        {/* Accuracy & Corrections */}
        <div className="bg-white rounded-lg shadow p-6 text-left">
          <h4 className="font-semibold text-gray-700 mb-4">Human Verification</h4>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="text-gray-500">Bias Detection Attempts</div>
            <div className="font-medium">{summary.bias_attempts || 0}</div>

            <div className="text-gray-500">User Corrections (non-bias)</div>
            <div className={`font-bold text-lg ${correctionCount === 0 ? 'text-green-600' : 'text-amber-600'}`}>
              {correctionCount}
            </div>

            <div className="text-gray-500">OCR Accuracy Rate</div>
            <div className="font-medium text-blue-600">
              {summary.total_fields > 0
                ? ((1 - correctionCount / summary.total_fields) * 100).toFixed(1)
                : 100}%
            </div>
          </div>

          {corrections.length > 0 && (
            <div className="mt-4 border-t pt-3">
              <p className="text-xs font-semibold text-gray-500 mb-2">Fields Corrected:</p>
              <div className="space-y-1.5 max-h-40 overflow-auto">
                {corrections.map((c, i) => (
                  <div key={i} className="text-xs bg-amber-50 rounded px-2 py-1">
                    <span className="font-medium">{c.field_type?.replace(/_/g, ' ')}</span>
                    <span className="text-gray-400 mx-1">:</span>
                    <span className="text-red-500 line-through">{c.old_value}</span>
                    <span className="text-gray-400 mx-1">&rarr;</span>
                    <span className="text-green-600">{c.new_value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <button
        onClick={() => window.location.reload()}
        className="mt-8 px-6 py-2 bg-blue-600 text-white rounded-md font-medium hover:bg-blue-700"
      >
        Process Another Document
      </button>
    </div>
  )
}
