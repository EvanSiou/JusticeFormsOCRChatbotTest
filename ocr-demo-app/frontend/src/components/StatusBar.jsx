const STEPS = [
  { key: 'upload', label: 'Upload' },
  { key: 'quality_check', label: 'Quality Check' },
  { key: 'form_detect', label: 'Form Detection' },
  { key: 'ocr_classify', label: 'OCR & Classify' },
  { key: 'results', label: 'Review & Verify' },
  { key: 'complete', label: 'Complete' },
]

export default function StatusBar({ currentStep }) {
  const stepIndex = STEPS.findIndex((s) => s.key === currentStep)

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 shadow-lg z-50">
      <div className="max-w-7xl mx-auto px-4 py-2.5">
        <div className="flex items-center gap-0.5">
          {STEPS.map((step, idx) => (
            <div key={step.key} className="flex items-center flex-1">
              <div
                className={`flex items-center gap-1.5 px-2 py-1.5 rounded-md text-[11px] font-medium w-full justify-center transition-colors ${
                  idx < stepIndex
                    ? 'bg-green-100 text-green-700'
                    : idx === stepIndex
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-400'
                }`}
              >
                <span
                  className={`w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold flex-shrink-0 ${
                    idx < stepIndex
                      ? 'bg-green-500 text-white'
                      : idx === stepIndex
                      ? 'bg-white text-blue-600'
                      : 'bg-gray-300 text-white'
                  }`}
                >
                  {idx < stepIndex ? '\u2713' : idx + 1}
                </span>
                <span className="truncate">{step.label}</span>
              </div>
              {idx < STEPS.length - 1 && (
                <div className={`w-3 h-0.5 flex-shrink-0 ${idx < stepIndex ? 'bg-green-400' : 'bg-gray-200'}`} />
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export { STEPS }
