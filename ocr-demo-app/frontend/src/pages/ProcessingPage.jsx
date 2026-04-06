import { useState } from 'react'
import { processingAPI } from '../services/api'
import StatusBar from '../components/StatusBar'
import FileUploader from '../components/FileUploader'
import QualityGate from '../components/QualityGate'
import ResultsViewer from '../components/ResultsViewer'
import CompletionSummary from '../components/CompletionSummary'

export default function ProcessingPage() {
  const [currentStep, setCurrentStep] = useState('upload')
  const [sessionId, setSessionId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [loadingMessage, setLoadingMessage] = useState('Processing...')

  // Step data
  const [gateResult, setGateResult] = useState(null)
  const [formDetection, setFormDetection] = useState(null)
  const [results, setResults] = useState(null)
  const [biasResult, setBiasResult] = useState(null)
  const [summary, setSummary] = useState(null)

  const runStep = async (msg, apiCall) => {
    setLoading(true)
    setLoadingMessage(msg)
    setError(null)
    try {
      return await apiCall()
    } catch (e) {
      setError(e.response?.data?.detail || e.message)
      return null
    } finally {
      setLoading(false)
    }
  }

  // Upload → Quality Detect → Auto-Correct → Quality Gate (all automated)
  const handleUpload = async (file) => {
    const formData = new FormData()
    formData.append('file', file)

    // Step 1: Upload
    const uploadResult = await runStep('Uploading document...', async () => {
      const r = await processingAPI.upload(formData)
      setSessionId(r.data.session_id)
      return r.data
    })
    if (!uploadResult) return
    const sid = uploadResult.session_id

    // Step 2: Quality detect
    setCurrentStep('quality_check')
    await runStep('Analyzing page quality...', async () => {
      await processingAPI.qualityDetect(sid)
    })

    // Step 3: Auto-correct
    await runStep('Applying auto-corrections...', async () => {
      await processingAPI.autoCorrect(sid)
    })

    // Step 4: Quality gate
    const gate = await runStep('Evaluating quality gate...', async () => {
      const r = await processingAPI.qualityGate(sid)
      setGateResult(r.data)
      return r.data
    })

    // Always show quality gate so user can see before/after images
    // User clicks Continue to proceed
  }

  const handleGateProceed = async () => {
    const sid = sessionId
    if (!gateResult?.passed) {
      await processingAPI.qualityGateProceed(sid)
    }
    await handleFormDetectAndOCR(sid)
  }

  const handleGateReject = () => {
    setCurrentStep('upload')
    setSessionId(null)
    setGateResult(null)
  }

  const handleFormDetectAndOCR = async (sid) => {
    // Step 5: Form detection
    setCurrentStep('form_detect')
    const detection = await runStep('Detecting form type...', async () => {
      const r = await processingAPI.detectForm(sid)
      setFormDetection(r.data)
      return r.data
    })
    if (!detection) return

    // Step 6: OCR + Classification
    setCurrentStep('ocr_classify')
    const ocr = await runStep('Running OCR and field classification...', async () => {
      const r = await processingAPI.ocrClassify(sid)
      return r.data
    })
    if (!ocr) return

    // Step 7: Load results
    setCurrentStep('results')
    await runStep('Loading results...', async () => {
      const r = await processingAPI.getResults(sid)
      setResults(r.data)
    })
  }

  const handleFieldEdit = async (fieldIdx, value) => {
    try {
      await processingAPI.updateField(sessionId, fieldIdx, value)
    } catch (e) {
      console.error('Field update failed:', e)
    }
  }

  const handleValidateBias = async () => {
    try {
      const r = await processingAPI.validateBias(sessionId)
      setBiasResult(r.data)
      if (r.data.passed) {
        setResults((prev) => ({ ...prev, bias_challenge_passed: true }))
      }
    } catch (e) {
      setError(e.response?.data?.detail || e.message)
    }
  }

  const handleComplete = async () => {
    const result = await runStep('Completing...', async () => {
      const r = await processingAPI.complete(sessionId)
      setSummary(r.data)
      return r.data
    })
    if (result) setCurrentStep('complete')
  }

  return (
    <div className="pb-20">
      <h2 className="text-2xl font-bold text-gray-800 mb-6">Document Processing</h2>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-4 text-red-700 text-sm">
          {error}
          <button onClick={() => setError(null)} className="ml-2 font-bold">&times;</button>
        </div>
      )}

      <div className="bg-white rounded-lg shadow p-6 min-h-[450px]">
        {loading && (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="animate-spin w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full mb-4" />
            <p className="text-gray-500">{loadingMessage}</p>
          </div>
        )}

        {!loading && currentStep === 'upload' && (
          <FileUploader onUpload={handleUpload} uploading={false} />
        )}

        {!loading && currentStep === 'quality_check' && gateResult && (
          <QualityGate
            gateResult={gateResult}
            sessionId={sessionId}
            onProceed={handleGateProceed}
            onReject={handleGateReject}
          />
        )}

        {!loading && currentStep === 'results' && results && (
          <ResultsViewer
            sessionId={sessionId}
            results={results}
            onFieldEdit={handleFieldEdit}
            onValidateBias={handleValidateBias}
            biasResult={biasResult}
            onComplete={handleComplete}
          />
        )}

        {!loading && currentStep === 'complete' && (
          <CompletionSummary summary={summary} />
        )}
      </div>

      <StatusBar currentStep={currentStep} />
    </div>
  )
}
