import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { syntheticAPI, testsAPI, promptsAPI, referenceAPI } from '../services/api'

function formatDuration(startedAt, completedAt) {
  if (!startedAt || !completedAt) return null
  const start = new Date(startedAt)
  const end = new Date(completedAt)
  const seconds = Math.round((end - start) / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  if (minutes < 60) return `${minutes}m ${remainingSeconds}s`
  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60
  return `${hours}h ${remainingMinutes}m`
}

function RunTestsPage() {
  const [selectedBatches, setSelectedBatches] = useState([])
  const [selectedLayouts, setSelectedLayouts] = useState([])
  const [selectedOCRs, setSelectedOCRs] = useState([])
  const [runningTests, setRunningTests] = useState([])
  const [runningBatchJobs, setRunningBatchJobs] = useState([])
  const [selectedOcrPrompt, setSelectedOcrPrompt] = useState('')
  const [selectedClassifier, setSelectedClassifier] = useState('')
  const [selectedClassificationPrompt, setSelectedClassificationPrompt] = useState('')
  const [selectedFieldTypes, setSelectedFieldTypes] = useState([])
  const [selectedJudgeModel, setSelectedJudgeModel] = useState('')
  const [selectedJudgePrompt, setSelectedJudgePrompt] = useState('')
  const [userFilter, setUserFilter] = useState('')

  const navigate = useNavigate()
  const queryClient = useQueryClient()

  // Fetch batches
  const { data: batchesData, isLoading: batchesLoading } = useQuery({
    queryKey: ['batches'],
    queryFn: () => syntheticAPI.listBatches(),
  })

  // Fetch test runs
  const { data: testsData, isLoading: testsLoading } = useQuery({
    queryKey: ['tests'],
    queryFn: () => testsAPI.list(),
  })

  // Fetch available libraries
  const { data: librariesData } = useQuery({
    queryKey: ['libraries'],
    queryFn: () => testsAPI.getLibraries(),
  })

  const vlmEngines = librariesData?.data?.vlm_engines || ['got_ocr', 'mineru', 'claude', 'claude_bedrock', 'llama4_maverick_bedrock', 'llama4_maverick_vertex']
  const promptableEngines = [
    'claude',
    'claude_bedrock', 'claude_haiku_bedrock',
    'nova_pro_bedrock', 'nova_lite_bedrock',
    'pixtral_large_bedrock',
    'llama4_maverick_bedrock', 'llama4_scout_bedrock',
    'llama4_maverick_vertex', 'llama4_scout_vertex',
    'gpt5', 'gpt5_mini',
  ]

  // Fetch OCR prompts
  const { data: ocrPromptsData } = useQuery({
    queryKey: ['prompts', 'ocr'],
    queryFn: () => promptsAPI.list('ocr'),
  })
  const ocrPrompts = ocrPromptsData?.data?.prompts || []

  // Fetch classification prompts
  const { data: clsPromptsData } = useQuery({
    queryKey: ['prompts', 'classification'],
    queryFn: () => promptsAPI.list('classification'),
  })
  const classificationPrompts = clsPromptsData?.data?.prompts || []

  // Fetch judge prompts
  const { data: judgePromptsData } = useQuery({
    queryKey: ['prompts', 'judge'],
    queryFn: () => promptsAPI.list('judge'),
  })
  const judgePrompts = judgePromptsData?.data?.prompts || []

  // Fetch reference templates (for auto-populating field types)
  const { data: templatesData } = useQuery({
    queryKey: ['reference-templates'],
    queryFn: () => referenceAPI.listTemplates(),
  })
  const referenceTemplates = templatesData?.data || []

  // Available classifier and judge models from libraries endpoint
  const classifierModels = librariesData?.data?.classifier_models || []
  const judgeModels = librariesData?.data?.judge_models || []

  // Show prompt selector if any selected OCR engine supports prompting
  const showPromptSelector = selectedOCRs.some(lib => promptableEngines.includes(lib))

  // Auto-populate field types from reference template when batch is selected
  useEffect(() => {
    if (selectedBatches.length > 0 && selectedFieldTypes.length === 0) {
      const batch = allBatches.find(b => b.id === selectedBatches[0])
      if (batch?.reference_template_id) {
        const template = referenceTemplates.find(t => t.id === batch.reference_template_id)
        if (template?.fields) {
          setSelectedFieldTypes(template.fields.map(f => f.field_name))
        }
      }
    }
  }, [selectedBatches, referenceTemplates]) // eslint-disable-line react-hooks/exhaustive-deps

  // Poll for all running test statuses
  const { data: runningStatusData } = useQuery({
    queryKey: ['running-test-statuses', runningTests],
    queryFn: async () => {
      const statuses = await Promise.all(
        runningTests.map(async (id) => {
          try {
            const res = await testsAPI.getStatus(id)
            return { id, ...res.data }
          } catch {
            return { id, status: 'failed', error_message: 'Failed to fetch status' }
          }
        })
      )
      return statuses
    },
    enabled: runningTests.length > 0,
    refetchInterval: (data) => {
      const anyRunning = data?.data?.some(
        (s) => s.status !== 'completed' && s.status !== 'failed'
      )
      return anyRunning ? 2000 : false
    },
  })

  // Poll for running batch job statuses
  const { data: batchJobStatusData } = useQuery({
    queryKey: ['running-batch-jobs', runningBatchJobs],
    queryFn: async () => {
      const statuses = await Promise.all(
        runningBatchJobs.map(async (id) => {
          try {
            const res = await testsAPI.getBatchJob(id)
            return res.data
          } catch {
            return { id, status: 'failed', error_message: 'Failed to fetch status' }
          }
        })
      )
      return statuses
    },
    enabled: runningBatchJobs.length > 0,
    refetchInterval: (data) => {
      const anyRunning = data?.data?.some(
        (s) => s.status !== 'completed' && s.status !== 'failed'
      )
      return anyRunning ? 3000 : false
    },
  })

  // Handle test status changes
  useEffect(() => {
    if (runningStatusData?.data) {
      const finished = runningStatusData.data.filter(
        (s) => s.status === 'completed' || s.status === 'failed'
      )
      if (finished.length > 0) {
        setRunningTests((prev) =>
          prev.filter((id) => !finished.some((f) => f.id === id))
        )
        queryClient.invalidateQueries(['tests'])
      }
    }
  }, [runningStatusData, queryClient])

  // Handle batch job status changes
  useEffect(() => {
    if (batchJobStatusData?.data) {
      const finished = batchJobStatusData.data.filter(
        (s) => s.status === 'completed' || s.status === 'failed'
      )
      if (finished.length > 0) {
        setRunningBatchJobs((prev) =>
          prev.filter((id) => !finished.some((f) => f.id === id))
        )
        queryClient.invalidateQueries(['tests'])
      }
    }
  }, [batchJobStatusData, queryClient])

  // Auto-detect running tests on page load
  useEffect(() => {
    if (testsData?.data?.test_runs && runningTests.length === 0) {
      const running = testsData.data.test_runs
        .filter((r) => r.status === 'running')
        .map((r) => r.id)
      if (running.length > 0) {
        setRunningTests(running)
      }
    }
  }, [testsData]) // eslint-disable-line react-hooks/exhaustive-deps

  // Set default libraries when loaded
  useEffect(() => {
    if (librariesData?.data) {
      if (selectedLayouts.length === 0 && librariesData.data.layout_libraries?.length > 0) {
        setSelectedLayouts([librariesData.data.layout_libraries[0]])
      }
      if (selectedOCRs.length === 0 && librariesData.data.ocr_libraries?.length > 0) {
        setSelectedOCRs([librariesData.data.ocr_libraries[0]])
      }
    }
  }, [librariesData]) // eslint-disable-line react-hooks/exhaustive-deps

  // Extract unique users
  const allBatches = batchesData?.data?.batches || []
  const allTestRuns = testsData?.data?.test_runs || []
  const uniqueUsers = [...new Set([
    ...allBatches.map(b => b.created_by_name).filter(Boolean).map(n => n.split('@')[0]),
    ...allTestRuns.map(r => r.started_by_name).filter(Boolean).map(n => n.split('@')[0]),
  ])].sort()

  // Filter by user
  const filteredBatches = userFilter
    ? allBatches.filter(b => b.created_by_name && b.created_by_name.split('@')[0] === userFilter)
    : allBatches
  const filteredTestRuns = userFilter
    ? allTestRuns.filter(r => r.started_by_name && r.started_by_name.split('@')[0] === userFilter)
    : allTestRuns

  // Determine which selected OCRs can also act as classifiers
  const sameAsOcrMode = selectedClassifier === '__same_as_ocr__'
  const ocrsThatAreClassifiers = selectedOCRs.filter(ocr => classifierModels.includes(ocr))
  const ocrsNotClassifiers = selectedOCRs.filter(ocr => !classifierModels.includes(ocr))

  // Calculate combinations
  const allVlm = selectedOCRs.length > 0 && selectedOCRs.every(lib => vlmEngines.includes(lib))
  const comboCount = (() => {
    let count = 0
    const ocrsToCount = sameAsOcrMode ? ocrsThatAreClassifiers : selectedOCRs
    for (const ocr of ocrsToCount) {
      if (vlmEngines.includes(ocr)) {
        count += 1
      } else {
        count += selectedLayouts.length
      }
    }
    return count
  })()

  // Toggle helpers
  const toggleLayout = (lib) => {
    setSelectedLayouts((prev) =>
      prev.includes(lib) ? prev.filter((l) => l !== lib) : [...prev, lib]
    )
  }
  const toggleOCR = (lib) => {
    setSelectedOCRs((prev) =>
      prev.includes(lib) ? prev.filter((l) => l !== lib) : [...prev, lib]
    )
  }

  // Run mutation: single combo uses existing API, multi-combo uses batch job API
  const runMutation = useMutation({
    mutationFn: () => {
      const promptId = selectedOcrPrompt || null
      const clsPromptId = selectedClassificationPrompt || null
      const fieldTypes = selectedFieldTypes.length > 0 ? selectedFieldTypes : null
      const judgeModel = selectedJudgeModel || null
      const judgePromptId = selectedJudgePrompt || null

      if (sameAsOcrMode) {
        // "Same as OCR" mode: each OCR engine is its own classifier
        const validOCRs = ocrsThatAreClassifiers
        if (validOCRs.length === 1) {
          const ocrLib = validOCRs[0]
          const layoutLib = vlmEngines.includes(ocrLib) ? '' : selectedLayouts[0]
          return testsAPI.run(selectedBatches, layoutLib, ocrLib, promptId, ocrLib, clsPromptId, fieldTypes, judgeModel, judgePromptId)
        } else {
          return testsAPI.runBatchJob(selectedBatches, selectedLayouts, validOCRs, promptId, ['__same_as_ocr__'], clsPromptId, fieldTypes, judgeModel, judgePromptId)
        }
      }

      const clsModel = selectedClassifier || null
      if (comboCount === 1) {
        const ocrLib = selectedOCRs[0]
        const layoutLib = vlmEngines.includes(ocrLib) ? '' : selectedLayouts[0]
        return testsAPI.run(selectedBatches, layoutLib, ocrLib, promptId, clsModel, clsPromptId, fieldTypes, judgeModel, judgePromptId)
      } else {
        const clsModels = clsModel ? [clsModel] : null
        return testsAPI.runBatchJob(selectedBatches, selectedLayouts, selectedOCRs, promptId, clsModels, clsPromptId, fieldTypes, judgeModel, judgePromptId)
      }
    },
    onSuccess: (response) => {
      if (comboCount === 1) {
        setRunningTests((prev) => [...prev, response.data.id])
      } else {
        setRunningBatchJobs((prev) => [...prev, response.data.id])
      }
      queryClient.invalidateQueries(['tests'])
    },
  })

  const toggleBatch = (batchId) => {
    setSelectedBatches((prev) =>
      prev.includes(batchId)
        ? prev.filter((id) => id !== batchId)
        : [...prev, batchId]
    )
  }

  const handleRun = () => {
    const hasLayout = allVlm || selectedLayouts.length > 0
    if (selectedBatches.length > 0 && hasLayout && selectedOCRs.length > 0) {
      runMutation.mutate()
    }
  }

  const handleCancel = async (testId) => {
    try {
      await testsAPI.cancel(testId)
      setRunningTests((prev) => prev.filter((id) => id !== testId))
      queryClient.invalidateQueries(['tests'])
    } catch (e) {
      console.error('Cancel failed', e)
    }
  }

  const handleCancelBatchJob = async (jobId) => {
    try {
      await testsAPI.cancelBatchJob(jobId)
      setRunningBatchJobs((prev) => prev.filter((id) => id !== jobId))
      queryClient.invalidateQueries(['tests'])
    } catch (e) {
      console.error('Cancel batch job failed', e)
    }
  }

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Run Tests</h2>

      {/* User Filter */}
      {uniqueUsers.length > 0 && (
        <div className="bg-white rounded-lg shadow p-4 mb-6">
          <div className="flex items-end gap-4">
            <div className="min-w-[150px]">
              <label className="block text-sm font-medium text-gray-700 mb-1">User</label>
              <select
                value={userFilter}
                onChange={(e) => {
                  setUserFilter(e.target.value)
                  setSelectedBatches([])
                }}
                className="w-full px-3 py-2 border rounded-md text-sm"
              >
                <option value="">All Users</option>
                {uniqueUsers.map((user) => (
                  <option key={user} value={user}>{user}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
      )}

      {/* Running Tests Progress */}
      {runningStatusData?.data?.length > 0 && (
        <div className="space-y-3 mb-6">
          {runningStatusData.data.map((testStatus) => (
            <div
              key={testStatus.id}
              className="bg-blue-50 border border-blue-200 rounded-lg p-4"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="font-medium">
                  Test Running...{' '}
                  <span className="text-xs text-gray-500 font-normal">
                    {testStatus.id.slice(0, 8)}
                  </span>
                </span>
                <div className="flex items-center gap-4">
                  <span className="text-sm text-blue-600">
                    {testStatus.processed_documents} /{' '}
                    {testStatus.total_documents} documents
                  </span>
                  <button
                    onClick={() => handleCancel(testStatus.id)}
                    className="px-3 py-1 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200"
                  >
                    Cancel
                  </button>
                </div>
              </div>
              <div className="w-full bg-blue-200 rounded-full h-2">
                <div
                  className="bg-blue-600 h-2 rounded-full transition-all"
                  style={{
                    width: `${testStatus.progress_percent || 0}%`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Running Batch Jobs Progress */}
      {batchJobStatusData?.data?.length > 0 && (
        <div className="space-y-3 mb-6">
          {batchJobStatusData.data.map((job) => (
            <div
              key={job.id}
              className="bg-purple-50 border border-purple-200 rounded-lg p-4"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="font-medium">
                  Batch Job Running...{' '}
                  <span className="text-xs text-gray-500 font-normal">
                    {job.id?.slice(0, 8)}
                  </span>
                </span>
                <div className="flex items-center gap-4">
                  <span className="text-sm text-purple-600">
                    {job.completed_combinations} / {job.total_combinations} combinations
                  </span>
                  <button
                    onClick={() => handleCancelBatchJob(job.id)}
                    className="px-3 py-1 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200"
                  >
                    Cancel
                  </button>
                </div>
              </div>
              <div className="w-full bg-purple-200 rounded-full h-2">
                <div
                  className="bg-purple-600 h-2 rounded-full transition-all"
                  style={{
                    width: `${job.total_combinations > 0 ? (job.completed_combinations / job.total_combinations * 100) : 0}%`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Test Configuration */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h3 className="text-lg font-semibold mb-4">Step 1: Select Batches</h3>

        {batchesLoading ? (
          <p>Loading batches...</p>
        ) : filteredBatches.length > 0 ? (
          <div className="max-h-[250px] overflow-y-auto border rounded-md">
            {filteredBatches.map((batch) => (
              <div
                key={batch.id}
                onClick={() => toggleBatch(batch.id)}
                className={`flex items-center gap-3 px-3 py-2 cursor-pointer border-b last:border-b-0 transition-colors ${
                  selectedBatches.includes(batch.id)
                    ? 'bg-blue-50'
                    : 'hover:bg-gray-50'
                }`}
              >
                <input
                  type="checkbox"
                  checked={selectedBatches.includes(batch.id)}
                  onChange={() => toggleBatch(batch.id)}
                  className="rounded flex-shrink-0"
                />
                <span className="font-medium text-sm min-w-[60px]">{batch.batch_number}</span>
                <span className={`px-1.5 py-0.5 rounded text-xs font-medium flex-shrink-0 ${
                  batch.batch_type === 'handwritten'
                    ? 'bg-purple-100 text-purple-700'
                    : 'bg-blue-100 text-blue-700'
                }`}>
                  {batch.batch_type === 'handwritten' ? 'HW' : 'Syn'}
                </span>
                <span className="text-sm text-gray-700 truncate flex-1">{batch.form_name}</span>
                <span className="text-xs text-gray-400 flex-shrink-0">
                  {batch.count} docs
                  {batch.created_by_name ? ` · ${batch.created_by_name.split('@')[0]}` : ''}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-gray-600">
            No batches available. Generate synthetic data first.
          </p>
        )}
      </div>

      {/* Library Selection - Multi-select checkboxes */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h3 className="text-lg font-semibold mb-4">Step 2: Select Libraries</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Layout Libraries */}
          {!allVlm && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Layout Detection Libraries
              </label>
              <div className="space-y-2 border rounded-md p-3">
                {librariesData?.data?.layout_libraries?.map((lib) => (
                  <label key={lib} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedLayouts.includes(lib)}
                      onChange={() => toggleLayout(lib)}
                    />
                    <span className="text-sm">{lib}</span>
                  </label>
                ))}
              </div>
            </div>
          )}

          {/* OCR Libraries */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              OCR Libraries
            </label>
            <div className="space-y-2 border rounded-md p-3">
              {librariesData?.data?.ocr_libraries?.map((lib) => (
                <label key={lib} className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedOCRs.includes(lib)}
                    onChange={() => toggleOCR(lib)}
                  />
                  <span className="text-sm">
                    {lib}
                    {vlmEngines.includes(lib) && (
                      <span className="ml-1 text-xs text-purple-600 font-medium">(VLM)</span>
                    )}
                  </span>
                </label>
              ))}
            </div>
          </div>
        </div>

        {/* Combination count */}
        {comboCount > 0 && (
          <p className="text-sm text-gray-600 mt-3">
            This will run <span className="font-semibold text-purple-700">{comboCount}</span> combination{comboCount !== 1 ? 's' : ''}
            {comboCount > 1 && ' sequentially as a batch job'}
          </p>
        )}

        {/* OCR Prompt selector */}
        {showPromptSelector && (
          <div className="mt-4 pt-4 border-t">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              OCR Prompt
            </label>
            <select
              value={selectedOcrPrompt}
              onChange={(e) => setSelectedOcrPrompt(e.target.value)}
              className="w-full max-w-md px-3 py-2 border rounded-md text-sm"
            >
              <option value="">Default Prompt</option>
              {ocrPrompts.filter(p => !p.is_default).map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
            <p className="text-xs text-gray-500 mt-1">
              Only applies to promptable VLM engines (Bedrock models + GPT-5)
            </p>
          </div>
        )}
      </div>

      {/* Step 2.5: Classification Configuration (optional) */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h3 className="text-lg font-semibold mb-4">
          Classification (Optional)
          {selectedClassifier && !sameAsOcrMode && selectedOCRs.length === 1 && selectedOCRs[0] === selectedClassifier && (
            <span className="ml-2 px-2 py-0.5 bg-green-100 text-green-700 rounded text-xs font-medium">
              Single API Call
            </span>
          )}
          {sameAsOcrMode && (
            <span className="ml-2 px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs font-medium">
              Same as OCR — {ocrsThatAreClassifiers.length} matched pair{ocrsThatAreClassifiers.length !== 1 ? 's' : ''}
            </span>
          )}
        </h3>
        <p className="text-sm text-gray-500 mb-4">
          Run field classification alongside OCR. When the same model is used for both, a single API call is made.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Classifier Model */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Classifier Model
            </label>
            <select
              value={selectedClassifier}
              onChange={(e) => setSelectedClassifier(e.target.value)}
              className="w-full px-3 py-2 border rounded-md text-sm"
            >
              <option value="">None (OCR only)</option>
              <option value="__same_as_ocr__">Same as OCR (match each OCR to itself)</option>
              {classifierModels.map((model) => (
                <option key={model} value={model}>{model}</option>
              ))}
            </select>
            {sameAsOcrMode && ocrsThatAreClassifiers.length > 0 && (
              <div className="mt-2 text-xs text-gray-600">
                <span className="font-medium">Pairings:</span>{' '}
                {ocrsThatAreClassifiers.map((ocr, i) => (
                  <span key={ocr}>
                    {i > 0 && ', '}
                    <span className="text-blue-700">{ocr}↔{ocr}</span>
                  </span>
                ))}
              </div>
            )}
            {sameAsOcrMode && ocrsNotClassifiers.length > 0 && (
              <p className="mt-1 text-xs text-amber-600">
                Skipped (not classifiers): {ocrsNotClassifiers.join(', ')}
              </p>
            )}
          </div>

          {/* Classification Prompt */}
          {selectedClassifier && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Classification Prompt
              </label>
              <select
                value={selectedClassificationPrompt}
                onChange={(e) => setSelectedClassificationPrompt(e.target.value)}
                className="w-full px-3 py-2 border rounded-md text-sm"
              >
                <option value="">Default Prompt</option>
                {classificationPrompts.filter(p => !p.is_default).map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Field Types */}
        {selectedClassifier && (
          <div className="mt-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Field Types to Extract
            </label>
            <div className="flex flex-wrap gap-2 mb-2">
              {selectedFieldTypes.map((ft, idx) => (
                <span
                  key={idx}
                  className="inline-flex items-center gap-1 px-2 py-1 bg-purple-100 text-purple-700 rounded text-xs"
                >
                  {ft}
                  <button
                    onClick={() => setSelectedFieldTypes(prev => prev.filter((_, i) => i !== idx))}
                    className="text-purple-500 hover:text-purple-800"
                  >
                    x
                  </button>
                </span>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="Add field type (e.g., defendant_name)"
                className="flex-1 max-w-md px-3 py-2 border rounded-md text-sm"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && e.target.value.trim()) {
                    setSelectedFieldTypes(prev => [...prev, e.target.value.trim()])
                    e.target.value = ''
                  }
                }}
              />
              {referenceTemplates.length > 0 && (
                <select
                  onChange={(e) => {
                    if (e.target.value) {
                      const template = referenceTemplates.find(t => t.id === e.target.value)
                      if (template?.fields) {
                        setSelectedFieldTypes(template.fields.map(f => f.field_name))
                      }
                      e.target.value = ''
                    }
                  }}
                  className="px-3 py-2 border rounded-md text-sm"
                >
                  <option value="">Load from template...</option>
                  {referenceTemplates.map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
              )}
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Press Enter to add each field type. Or load from a reference template.
            </p>
            {selectedFieldTypes.length === 0 && selectedClassifier && (
              <p className="text-xs text-amber-600 mt-1">
                No field types selected. Classification needs at least one field type to extract.
              </p>
            )}
          </div>
        )}
      </div>

      {/* Step 2.75: LLM-as-a-Judge (optional) */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h3 className="text-lg font-semibold mb-4">LLM-as-a-Judge (Optional)</h3>
        <p className="text-sm text-gray-500 mb-4">
          Select a second model to independently evaluate OCR and classification results against reference data.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Judge Model
            </label>
            <select
              value={selectedJudgeModel}
              onChange={(e) => setSelectedJudgeModel(e.target.value)}
              className="w-full px-3 py-2 border rounded-md text-sm"
            >
              <option value="">None (skip judge)</option>
              {judgeModels.map((model) => (
                <option key={model} value={model}>{model}</option>
              ))}
            </select>
          </div>

          {selectedJudgeModel && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Judge Prompt
              </label>
              <select
                value={selectedJudgePrompt}
                onChange={(e) => setSelectedJudgePrompt(e.target.value)}
                className="w-full px-3 py-2 border rounded-md text-sm"
              >
                <option value="">Default Judge Prompt</option>
                {judgePrompts.filter(p => !p.is_default).map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
          )}
        </div>
      </div>

      {/* Run Button */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold">Step 3: Run Tests</h3>
            <p className="text-sm text-gray-600">
              {selectedBatches.length} batch(es) selected, {comboCount} combination(s)
              {runningTests.length > 0 && (
                <span className="ml-2 text-blue-600">
                  • {runningTests.length} test(s) running
                </span>
              )}
              {runningBatchJobs.length > 0 && (
                <span className="ml-2 text-purple-600">
                  • {runningBatchJobs.length} batch job(s) running
                </span>
              )}
            </p>
          </div>
          <button
            onClick={handleRun}
            disabled={
              selectedBatches.length === 0 ||
              (!allVlm && selectedLayouts.length === 0) ||
              selectedOCRs.length === 0 ||
              runMutation.isPending
            }
            className="px-6 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {runMutation.isPending
              ? 'Starting...'
              : comboCount > 1
              ? `Run ${comboCount} Combinations`
              : 'Run Tests'}
          </button>
        </div>

        {runMutation.isError && (
          <p className="text-red-600 text-sm mt-4">
            {runMutation.error?.response?.data?.detail || 'Failed to start tests'}
          </p>
        )}
      </div>

      {/* Previous Test Runs */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">Previous Test Runs</h3>
        {testsLoading ? (
          <p>Loading...</p>
        ) : filteredTestRuns.length > 0 ? (
          <div className="max-h-[300px] overflow-y-auto border rounded-md">
            {filteredTestRuns.map((run) => (
              <div
                key={run.id}
                className="flex items-center gap-2 px-3 py-2 border-b last:border-b-0 hover:bg-gray-50 text-sm"
              >
                {/* Status dot */}
                <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
                  run.status === 'completed' ? 'bg-green-500'
                    : run.status === 'running' ? 'bg-blue-500'
                    : run.status === 'failed' ? 'bg-red-500'
                    : 'bg-gray-400'
                }`} />
                {/* Libraries */}
                <span className="font-medium text-xs min-w-[120px]">
                  {run.layout_library || 'none'} + {run.ocr_library}
                </span>
                {run.ocr_prompt_name && (
                  <span className="px-1.5 py-0.5 bg-indigo-50 text-indigo-600 rounded text-xs flex-shrink-0">
                    {run.ocr_prompt_name}
                  </span>
                )}
                {run.classifier_model && (
                  <span className="px-1.5 py-0.5 bg-purple-50 text-purple-600 rounded text-xs flex-shrink-0">
                    cls:{run.classifier_model}
                  </span>
                )}
                {run.judge_model && (
                  <span className="px-1.5 py-0.5 bg-amber-50 text-amber-600 rounded text-xs flex-shrink-0">
                    judge:{run.judge_model}
                  </span>
                )}
                {run.is_unified && (
                  <span className="px-1 py-0.5 bg-green-100 text-green-700 rounded text-xs flex-shrink-0">
                    unified
                  </span>
                )}
                {run.batch_job_id && (
                  <span className="px-1 py-0.5 bg-purple-100 text-purple-700 rounded text-xs flex-shrink-0">
                    batch
                  </span>
                )}
                {/* Date + docs */}
                <span className="text-xs text-gray-500 flex-1 truncate">
                  {run.total_documents} docs · {new Date(run.started_at).toLocaleDateString()}{' '}
                  {new Date(run.started_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                  {run.started_by_name && ` · ${run.started_by_name.split('@')[0]}`}
                  {formatDuration(run.started_at, run.completed_at) && ` (${formatDuration(run.started_at, run.completed_at)})`}
                </span>
                {/* Actions */}
                <div className="flex items-center gap-2 flex-shrink-0">
                  {run.status === 'completed' && (
                    <button
                      onClick={() => navigate(`/results/${run.id}`)}
                      className="text-blue-600 hover:underline text-xs"
                    >
                      Results
                    </button>
                  )}
                  {run.status === 'running' && (
                    <button
                      onClick={() => handleCancel(run.id)}
                      className="text-red-600 hover:underline text-xs"
                    >
                      Cancel
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-gray-600">No test runs yet.</p>
        )}
      </div>
    </div>
  )
}

export default RunTestsPage
