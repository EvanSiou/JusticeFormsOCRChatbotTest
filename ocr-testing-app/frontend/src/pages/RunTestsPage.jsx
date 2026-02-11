import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { syntheticAPI, testsAPI } from '../services/api'

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
  const [userFilter, setUserFilter] = useState('')

  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const vlmEngines = ['got_ocr', 'mineru']

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

  // Calculate combinations
  const allVlm = selectedOCRs.length > 0 && selectedOCRs.every(lib => vlmEngines.includes(lib))
  const comboCount = (() => {
    let count = 0
    for (const ocr of selectedOCRs) {
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
      if (comboCount === 1) {
        const ocrLib = selectedOCRs[0]
        const layoutLib = vlmEngines.includes(ocrLib) ? '' : selectedLayouts[0]
        return testsAPI.run(selectedBatches, layoutLib, ocrLib)
      } else {
        return testsAPI.runBatchJob(selectedBatches, selectedLayouts, selectedOCRs)
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
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredBatches.map((batch) => (
              <div
                key={batch.id}
                onClick={() => toggleBatch(batch.id)}
                className={`p-4 border-2 rounded-lg cursor-pointer transition-colors ${
                  selectedBatches.includes(batch.id)
                    ? 'border-blue-600 bg-blue-50'
                    : 'border-gray-200 hover:border-gray-400'
                }`}
              >
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={selectedBatches.includes(batch.id)}
                    onChange={() => {}}
                    className="pointer-events-none"
                  />
                  <div>
                    <div className="flex items-center gap-2">
                      <h4 className="font-medium">
                        {batch.batch_number} - {batch.form_name} - {new Date(batch.created_at).toLocaleDateString()}
                        {batch.created_by_name && ` - ${batch.created_by_name.split('@')[0]}`}
                      </h4>
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-medium ${
                          batch.batch_type === 'handwritten'
                            ? 'bg-purple-100 text-purple-700'
                            : 'bg-blue-100 text-blue-700'
                        }`}
                      >
                        {batch.batch_type === 'handwritten' ? 'Handwritten' : 'Synthetic'}
                      </span>
                    </div>
                    <p className="text-sm text-gray-500">
                      {batch.count} docs
                    </p>
                  </div>
                </div>
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
          <div className="space-y-3">
            {filteredTestRuns.map((run) => (
              <div
                key={run.id}
                className="flex items-center justify-between p-4 bg-gray-50 rounded-lg"
              >
                <div>
                  <p className="font-medium">
                    {run.layout_library || 'N/A'} + {run.ocr_library}
                    {run.started_by_name && ` - ${run.started_by_name.split('@')[0]}`}
                    {' - '}{new Date(run.started_at).toLocaleDateString()}
                    {run.batch_job_id && (
                      <span className="ml-2 px-1.5 py-0.5 bg-purple-100 text-purple-700 rounded text-xs font-medium">
                        batch
                      </span>
                    )}
                  </p>
                  <p className="text-sm text-gray-600">
                    {run.total_documents} documents •{' '}
                    {new Date(run.started_at).toLocaleString()}
                    {formatDuration(run.started_at, run.completed_at) && (
                      <span className="ml-2 text-gray-500">
                        ({formatDuration(run.started_at, run.completed_at)})
                      </span>
                    )}
                  </p>
                </div>
                <div className="flex items-center gap-4">
                  <span
                    className={`px-2 py-1 rounded text-sm ${
                      run.status === 'completed'
                        ? 'bg-green-100 text-green-700'
                        : run.status === 'running'
                        ? 'bg-blue-100 text-blue-700'
                        : run.status === 'failed'
                        ? 'bg-red-100 text-red-700'
                        : 'bg-gray-100 text-gray-700'
                    }`}
                  >
                    {run.status}
                  </span>
                  {run.status === 'completed' && (
                    <button
                      onClick={() => navigate(`/results/${run.id}`)}
                      className="text-blue-600 hover:underline text-sm"
                    >
                      View Results
                    </button>
                  )}
                  {run.status === 'running' && (
                    <button
                      onClick={() => handleCancel(run.id)}
                      className="text-red-600 hover:underline text-sm"
                    >
                      Cancel
                    </button>
                  )}
                  {run.status === 'failed' && run.error_message && (
                    <span
                      className="text-red-500 text-xs max-w-xs truncate"
                      title={run.error_message}
                    >
                      {run.error_message}
                    </span>
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
