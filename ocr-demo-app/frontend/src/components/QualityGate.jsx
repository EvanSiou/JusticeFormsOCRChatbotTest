import { useState, useEffect } from 'react'
import { processingAPI } from '../services/api'

export default function QualityGate({ gateResult, sessionId, onProceed, onReject }) {
  if (!gateResult) return null

  const { passed, threshold, page_results } = gateResult
  const [selectedPage, setSelectedPage] = useState(0)
  const [originalUrl, setOriginalUrl] = useState(null)
  const [correctedUrl, setCorrectedUrl] = useState(null)

  useEffect(() => {
    if (!sessionId) return
    // Load before/after images for selected page
    processingAPI.getPageImage(sessionId, selectedPage, false).then((r) => {
      setOriginalUrl(URL.createObjectURL(r.data))
    }).catch(() => {})
    processingAPI.getPageImage(sessionId, selectedPage, true).then((r) => {
      setCorrectedUrl(URL.createObjectURL(r.data))
    }).catch(() => {})

    return () => {
      if (originalUrl) URL.revokeObjectURL(originalUrl)
      if (correctedUrl) URL.revokeObjectURL(correctedUrl)
    }
  }, [sessionId, selectedPage])

  return (
    <div>
      <h3 className="text-lg font-semibold mb-4">Quality Gate</h3>

      <div className={`rounded-lg p-6 mb-4 ${passed ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
        <div className="flex items-center gap-3">
          <span className={`text-3xl ${passed ? 'text-green-500' : 'text-red-500'}`}>
            {passed ? '\u2705' : '\u26a0\ufe0f'}
          </span>
          <div>
            <p className={`font-bold text-lg ${passed ? 'text-green-700' : 'text-red-700'}`}>
              {passed ? 'All pages pass quality threshold' : 'Some pages below quality threshold'}
            </p>
            <p className="text-sm text-gray-600">
              Threshold: {(threshold * 100).toFixed(0)}%
            </p>
          </div>
        </div>
      </div>

      {/* Page selector */}
      <div className="space-y-2 mb-4">
        {page_results.map((pr) => (
          <button
            key={pr.page_num}
            onClick={() => setSelectedPage(pr.page_num)}
            className={`flex items-center gap-3 text-sm w-full text-left px-3 py-2 rounded ${
              selectedPage === pr.page_num ? 'bg-blue-50 border border-blue-200' : 'hover:bg-gray-50'
            }`}
          >
            <span className={pr.passed ? 'text-green-500' : 'text-red-500'}>
              {pr.passed ? '\u2713' : '\u2717'}
            </span>
            <span>Page {pr.page_num + 1}</span>
            <span className="font-mono">{(pr.score * 100).toFixed(0)}%</span>
            <span className="text-gray-400">/ {(pr.threshold * 100).toFixed(0)}%</span>
          </button>
        ))}
      </div>

      {/* Before / After comparison */}
      <div className="mb-6">
        <h4 className="text-sm font-semibold text-gray-600 mb-2">
          Page {selectedPage + 1} — Before / After Correction
        </h4>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-gray-500 mb-1 text-center">Original</p>
            <div className="border rounded-lg overflow-hidden bg-gray-100 flex items-center justify-center min-h-[300px]">
              {originalUrl ? (
                <img src={originalUrl} alt="Original page" className="max-w-full max-h-[500px] object-contain" />
              ) : (
                <span className="text-gray-400 text-sm">Loading...</span>
              )}
            </div>
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-1 text-center">Corrected</p>
            <div className="border rounded-lg overflow-hidden bg-gray-100 flex items-center justify-center min-h-[300px]">
              {correctedUrl ? (
                <img src={correctedUrl} alt="Corrected page" className="max-w-full max-h-[500px] object-contain" />
              ) : (
                <span className="text-gray-400 text-sm">Loading...</span>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="flex gap-3 justify-end">
        {!passed && (
          <button
            onClick={onReject}
            className="px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
          >
            Re-upload Document
          </button>
        )}
        <button
          onClick={onProceed}
          className="px-6 py-2 bg-blue-600 text-white rounded-md font-medium hover:bg-blue-700"
        >
          {passed ? 'Continue' : 'Proceed Anyway'}
        </button>
      </div>
    </div>
  )
}
