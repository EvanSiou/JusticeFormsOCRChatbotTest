export default function QualityReport({ pages, onContinue }) {
  return (
    <div>
      <h3 className="text-lg font-semibold mb-4">Page Quality Analysis</h3>
      <div className="grid gap-3">
        {pages.map((p) => {
          const score = p.overall_quality_score || 0
          const color = score >= 0.8 ? 'green' : score >= 0.5 ? 'yellow' : 'red'
          return (
            <div key={p.page_num} className="bg-gray-50 rounded-lg p-4 flex items-center gap-4">
              <div className="text-sm font-medium text-gray-500 w-16">
                Page {p.page_num + 1}
              </div>
              <div className="flex-1">
                <div className="w-full bg-gray-200 rounded-full h-3">
                  <div
                    className={`h-3 rounded-full transition-all ${
                      color === 'green' ? 'bg-green-500' : color === 'yellow' ? 'bg-yellow-500' : 'bg-red-500'
                    }`}
                    style={{ width: `${score * 100}%` }}
                  />
                </div>
              </div>
              <span className={`font-bold text-sm ${
                color === 'green' ? 'text-green-600' : color === 'yellow' ? 'text-yellow-600' : 'text-red-600'
              }`}>
                {(score * 100).toFixed(0)}%
              </span>
              {p.rotation_needed > 0 && (
                <span className="text-xs bg-orange-100 text-orange-700 px-2 py-0.5 rounded">
                  Rotated {p.rotation_needed}&deg;
                </span>
              )}
              {p.issues && p.issues.length > 0 && (
                <span className="text-xs text-gray-500">{p.issues.join(', ')}</span>
              )}
            </div>
          )
        })}
      </div>
      <div className="mt-6 flex justify-end">
        <button
          onClick={onContinue}
          className="px-6 py-2 bg-blue-600 text-white rounded-md font-medium hover:bg-blue-700"
        >
          Continue to Auto-Correct
        </button>
      </div>
    </div>
  )
}
