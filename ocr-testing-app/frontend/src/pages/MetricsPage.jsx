import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { metricsAPI, testsAPI } from '../services/api'

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

function formatSeconds(s) {
  if (s == null) return '-'
  if (s < 60) return `${Math.round(s)}s`
  const m = Math.floor(s / 60)
  const rem = Math.round(s % 60)
  if (m < 60) return `${m}m ${rem}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

function accuracyColor(v) {
  if (v >= 0.8) return 'bg-green-100 text-green-800'
  if (v >= 0.5) return 'bg-yellow-100 text-yellow-800'
  return 'bg-red-100 text-red-800'
}

function speedColor(s) {
  if (s == null) return 'bg-gray-50 text-gray-400'
  if (s <= 60) return 'bg-green-100 text-green-800'
  if (s <= 300) return 'bg-yellow-100 text-yellow-800'
  return 'bg-red-100 text-red-800'
}

// ─── Matrix Section ───────────────────────────────────────
function MatrixSection({ matrixData, isLoading }) {
  const [filters, setFilters] = useState({
    user: '',
    date: '',
    batch: '',
    batchType: '',
    field: '',
    testRun: '',
    document: '',
  })

  const availableFilters = matrixData?.data?.filters || {}
  const rows = matrixData?.data?.rows || []

  // Apply filters
  const filteredRows = useMemo(() => {
    return rows.filter((r) => {
      if (filters.user && r.user !== filters.user) return false
      if (filters.date && r.date !== filters.date) return false
      if (filters.batch && r.batch_id !== filters.batch) return false
      if (filters.batchType && r.batch_type !== filters.batchType) return false
      if (filters.testRun && r.test_run_id !== filters.testRun) return false
      if (filters.document && r.document_id !== filters.document) return false
      return true
    })
  }, [rows, filters])

  // Build the accuracy matrix: { layout -> { ocr -> { sum, count } } }
  const { accuracyMatrix, speedMatrix, layoutLibs, ocrLibs } = useMemo(() => {
    const accMap = {}
    const spdMap = {}
    const layouts = new Set()
    const ocrs = new Set()

    for (const row of filteredRows) {
      const lay = row.layout_library
      const ocr = row.ocr_library
      layouts.add(lay)
      ocrs.add(ocr)

      // Accuracy
      if (!accMap[lay]) accMap[lay] = {}
      if (!accMap[lay][ocr]) accMap[lay][ocr] = { sum: 0, count: 0 }

      if (filters.field && row.field_accuracies?.[filters.field] != null) {
        accMap[lay][ocr].sum += row.field_accuracies[filters.field]
        accMap[lay][ocr].count += 1
      } else if (!filters.field) {
        const acc = row.verified_accuracy != null ? row.verified_accuracy : row.overall_accuracy
        accMap[lay][ocr].sum += acc
        accMap[lay][ocr].count += 1
      }

      // Speed: duration_s is for the whole test run, divide by total_documents
      if (row.duration_s != null && row.total_documents > 0) {
        if (!spdMap[lay]) spdMap[lay] = {}
        if (!spdMap[lay][ocr]) spdMap[lay][ocr] = { sum: 0, count: 0 }
        const perDoc = row.duration_s / row.total_documents
        spdMap[lay][ocr].sum += perDoc
        spdMap[lay][ocr].count += 1
      }
    }

    return {
      accuracyMatrix: accMap,
      speedMatrix: spdMap,
      layoutLibs: [...layouts].sort(),
      ocrLibs: [...ocrs].sort(),
    }
  }, [filteredRows, filters.field])

  const clearFilters = () =>
    setFilters({ user: '', date: '', batch: '', batchType: '', field: '', testRun: '', document: '' })

  const activeFilterCount = Object.values(filters).filter(Boolean).length

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h3 className="text-lg font-semibold mb-4">Performance Matrices</h3>
        <p className="text-gray-500">Loading matrix data...</p>
      </div>
    )
  }

  if (rows.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h3 className="text-lg font-semibold mb-4">Performance Matrices</h3>
        <p className="text-gray-500">No completed test runs yet. Run some tests to see the Layout vs OCR comparison matrices.</p>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold">Performance Matrices</h3>
        {activeFilterCount > 0 && (
          <button
            onClick={clearFilters}
            className="text-sm text-blue-600 hover:text-blue-800"
          >
            Clear filters ({activeFilterCount})
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7 gap-3 mb-6">
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">User</label>
          <select
            value={filters.user}
            onChange={(e) => setFilters((f) => ({ ...f, user: e.target.value }))}
            className="w-full text-sm border rounded px-2 py-1.5"
          >
            <option value="">All users</option>
            {availableFilters.users?.map((u) => (
              <option key={u} value={u}>{u}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">Date</label>
          <select
            value={filters.date}
            onChange={(e) => setFilters((f) => ({ ...f, date: e.target.value }))}
            className="w-full text-sm border rounded px-2 py-1.5"
          >
            <option value="">All dates</option>
            {availableFilters.dates?.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">Batch</label>
          <select
            value={filters.batch}
            onChange={(e) => setFilters((f) => ({ ...f, batch: e.target.value }))}
            className="w-full text-sm border rounded px-2 py-1.5"
          >
            <option value="">All batches</option>
            {availableFilters.batches?.map((b) => (
              <option key={b.id} value={b.id}>{b.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">Type</label>
          <select
            value={filters.batchType}
            onChange={(e) => setFilters((f) => ({ ...f, batchType: e.target.value }))}
            className="w-full text-sm border rounded px-2 py-1.5"
          >
            <option value="">All types</option>
            {availableFilters.batch_types?.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">Field</label>
          <select
            value={filters.field}
            onChange={(e) => setFilters((f) => ({ ...f, field: e.target.value }))}
            className="w-full text-sm border rounded px-2 py-1.5"
          >
            <option value="">All fields (overall)</option>
            {availableFilters.fields?.map((fld) => (
              <option key={fld} value={fld}>{fld}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">Test Run</label>
          <select
            value={filters.testRun}
            onChange={(e) => setFilters((f) => ({ ...f, testRun: e.target.value }))}
            className="w-full text-sm border rounded px-2 py-1.5"
          >
            <option value="">All runs</option>
            {availableFilters.test_runs?.map((tr) => (
              <option key={tr.id} value={tr.id}>{tr.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">Document</label>
          <select
            value={filters.document}
            onChange={(e) => setFilters((f) => ({ ...f, document: e.target.value }))}
            className="w-full text-sm border rounded px-2 py-1.5"
          >
            <option value="">All docs</option>
            {availableFilters.documents?.map((d) => (
              <option key={d} value={d}>{d.slice(0, 12)}...</option>
            ))}
          </select>
        </div>
      </div>

      <p className="text-xs text-gray-400 mb-4">
        Showing {filteredRows.length} document result{filteredRows.length !== 1 ? 's' : ''} across {layoutLibs.length} layout lib{layoutLibs.length !== 1 ? 's' : ''} and {ocrLibs.length} OCR engine{ocrLibs.length !== 1 ? 's' : ''}
        {filters.field ? ` (field: ${filters.field})` : ''}
      </p>

      {layoutLibs.length > 0 && ocrLibs.length > 0 ? (
        <div className="space-y-8">
          {/* Accuracy Matrix */}
          <div>
            <h4 className="text-md font-semibold mb-3">
              Accuracy Rate {filters.field ? `(${filters.field})` : '(Overall)'}
            </h4>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr>
                    <th className="border px-3 py-2 bg-gray-50 text-left text-xs font-medium text-gray-500">
                      Layout \ OCR
                    </th>
                    {ocrLibs.map((ocr) => (
                      <th key={ocr} className="border px-3 py-2 bg-gray-50 text-center text-xs font-medium text-gray-700">
                        {ocr}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {layoutLibs.map((lay) => (
                    <tr key={lay}>
                      <td className="border px-3 py-2 font-medium text-gray-700 bg-gray-50 text-xs">
                        {lay}
                      </td>
                      {ocrLibs.map((ocr) => {
                        const cell = accuracyMatrix[lay]?.[ocr]
                        if (!cell || cell.count === 0) {
                          return (
                            <td key={ocr} className="border px-3 py-2 text-center text-gray-300 text-xs">
                              -
                            </td>
                          )
                        }
                        const avg = cell.sum / cell.count
                        return (
                          <td key={ocr} className={`border px-3 py-2 text-center font-semibold text-sm ${accuracyColor(avg)}`}>
                            {(avg * 100).toFixed(1)}%
                            <div className="text-[10px] font-normal opacity-60">n={cell.count}</div>
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Speed Matrix */}
          <div>
            <h4 className="text-md font-semibold mb-3">Speed (avg per document)</h4>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr>
                    <th className="border px-3 py-2 bg-gray-50 text-left text-xs font-medium text-gray-500">
                      Layout \ OCR
                    </th>
                    {ocrLibs.map((ocr) => (
                      <th key={ocr} className="border px-3 py-2 bg-gray-50 text-center text-xs font-medium text-gray-700">
                        {ocr}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {layoutLibs.map((lay) => (
                    <tr key={lay}>
                      <td className="border px-3 py-2 font-medium text-gray-700 bg-gray-50 text-xs">
                        {lay}
                      </td>
                      {ocrLibs.map((ocr) => {
                        const cell = speedMatrix[lay]?.[ocr]
                        if (!cell || cell.count === 0) {
                          return (
                            <td key={ocr} className="border px-3 py-2 text-center text-gray-300 text-xs">
                              -
                            </td>
                          )
                        }
                        const avg = cell.sum / cell.count
                        return (
                          <td key={ocr} className={`border px-3 py-2 text-center font-semibold text-sm ${speedColor(avg)}`}>
                            {formatSeconds(avg)}
                            <div className="text-[10px] font-normal opacity-60">n={cell.count}</div>
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : (
        <p className="text-gray-500">No data matches the current filters.</p>
      )}
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────
function MetricsPage() {
  const [selectedTestRuns, setSelectedTestRuns] = useState([])

  // Fetch matrix data
  const { data: matrixData, isLoading: matrixLoading } = useQuery({
    queryKey: ['metrics-matrix'],
    queryFn: () => metricsAPI.getMatrix(),
  })

  // Fetch aggregate metrics
  const { data: aggregateData, isLoading: aggregateLoading } = useQuery({
    queryKey: ['metrics-aggregate'],
    queryFn: () => metricsAPI.getAggregate(),
  })

  // Fetch field metrics
  const { data: fieldData, isLoading: fieldLoading } = useQuery({
    queryKey: ['metrics-by-field'],
    queryFn: () => metricsAPI.getByField(),
  })

  // Fetch test runs for comparison
  const { data: testsData } = useQuery({
    queryKey: ['tests'],
    queryFn: () => testsAPI.list(),
  })

  // Fetch comparison data
  const { data: comparisonData } = useQuery({
    queryKey: ['metrics-comparison', selectedTestRuns],
    queryFn: () => metricsAPI.getComparison(selectedTestRuns),
    enabled: selectedTestRuns.length >= 2,
  })

  const handleExport = async (format) => {
    try {
      const response = await metricsAPI.export(format)
      if (format === 'csv') {
        const blob = new Blob([response.data], { type: 'text/csv' })
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'metrics.csv'
        a.click()
      } else {
        // JSON - show in new tab or download
        const blob = new Blob([JSON.stringify(response.data, null, 2)], {
          type: 'application/json',
        })
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = 'metrics.json'
        a.click()
      }
    } catch (error) {
      console.error('Export failed:', error)
    }
  }

  const toggleTestRun = (id) => {
    setSelectedTestRuns((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
    )
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold">Metrics & Analytics</h2>
        <div className="flex gap-2">
          <button
            onClick={() => handleExport('csv')}
            className="px-4 py-2 border rounded-lg hover:bg-gray-50"
          >
            Export CSV
          </button>
          <button
            onClick={() => handleExport('json')}
            className="px-4 py-2 border rounded-lg hover:bg-gray-50"
          >
            Export JSON
          </button>
        </div>
      </div>

      {/* Layout x OCR Matrices — at the top */}
      <MatrixSection matrixData={matrixData} isLoading={matrixLoading} />

      {/* Aggregate Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-6">
        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-sm text-gray-500">Total Test Runs</p>
          <p className="text-3xl font-bold">
            {aggregateData?.data?.total_test_runs || 0}
          </p>
        </div>
        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-sm text-gray-500">Documents Processed</p>
          <p className="text-3xl font-bold">
            {aggregateData?.data?.total_documents_processed || 0}
          </p>
        </div>
        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-sm text-gray-500">Overall Accuracy</p>
          <p className="text-3xl font-bold text-blue-600">
            {((aggregateData?.data?.average_accuracy || 0) * 100).toFixed(1)}%
          </p>
        </div>
        <div className="bg-white rounded-lg shadow p-6">
          <p className="text-sm text-gray-500">Fields Tracked</p>
          <p className="text-3xl font-bold">
            {fieldData?.data?.total_fields || 0}
          </p>
        </div>
      </div>

      {/* Performance by Library */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        {/* By Layout Library */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold mb-4">By Layout Library</h3>
          {aggregateLoading ? (
            <p>Loading...</p>
          ) : aggregateData?.data?.by_layout_library &&
            Object.keys(aggregateData.data.by_layout_library).length > 0 ? (
            <div className="space-y-3">
              {Object.entries(aggregateData.data.by_layout_library).map(
                ([lib, accuracy]) => (
                  <div key={lib} className="flex items-center gap-3">
                    <span className="w-32 text-sm truncate">{lib}</span>
                    <div className="flex-1 bg-gray-200 rounded-full h-4">
                      <div
                        className="bg-blue-500 h-4 rounded-full"
                        style={{ width: `${accuracy * 100}%` }}
                      />
                    </div>
                    <span className="w-16 text-sm text-right">
                      {(accuracy * 100).toFixed(1)}%
                    </span>
                  </div>
                )
              )}
            </div>
          ) : (
            <p className="text-gray-500">No data yet.</p>
          )}
        </div>

        {/* By OCR Library */}
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold mb-4">By OCR Library</h3>
          {aggregateLoading ? (
            <p>Loading...</p>
          ) : aggregateData?.data?.by_ocr_library &&
            Object.keys(aggregateData.data.by_ocr_library).length > 0 ? (
            <div className="space-y-3">
              {Object.entries(aggregateData.data.by_ocr_library).map(
                ([lib, accuracy]) => (
                  <div key={lib} className="flex items-center gap-3">
                    <span className="w-32 text-sm truncate">{lib}</span>
                    <div className="flex-1 bg-gray-200 rounded-full h-4">
                      <div
                        className="bg-green-500 h-4 rounded-full"
                        style={{ width: `${accuracy * 100}%` }}
                      />
                    </div>
                    <span className="w-16 text-sm text-right">
                      {(accuracy * 100).toFixed(1)}%
                    </span>
                  </div>
                )
              )}
            </div>
          ) : (
            <p className="text-gray-500">No data yet.</p>
          )}
        </div>
      </div>

      {/* Per-Field Accuracy */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h3 className="text-lg font-semibold mb-4">Per-Field Accuracy</h3>
        {fieldLoading ? (
          <p>Loading...</p>
        ) : fieldData?.data?.fields &&
          Object.keys(fieldData.data.fields).length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left border-b">
                  <th className="py-2">Field Name</th>
                  <th className="py-2">Accuracy</th>
                  <th className="py-2">Sample Count</th>
                  <th className="py-2">Visual</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(fieldData.data.fields).map(([field, data]) => (
                  <tr key={field} className="border-b">
                    <td className="py-2">{field}</td>
                    <td className="py-2">
                      <span
                        className={`font-medium ${
                          data.average_accuracy >= 0.8
                            ? 'text-green-600'
                            : data.average_accuracy >= 0.5
                            ? 'text-yellow-600'
                            : 'text-red-600'
                        }`}
                      >
                        {(data.average_accuracy * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td className="py-2">{data.sample_count}</td>
                    <td className="py-2 w-40">
                      <div className="bg-gray-200 rounded-full h-2">
                        <div
                          className={`h-2 rounded-full ${
                            data.average_accuracy >= 0.8
                              ? 'bg-green-500'
                              : data.average_accuracy >= 0.5
                              ? 'bg-yellow-500'
                              : 'bg-red-500'
                          }`}
                          style={{ width: `${data.average_accuracy * 100}%` }}
                        />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-gray-500">No field data yet.</p>
        )}
      </div>

      {/* Compare Test Runs */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">Compare Test Runs</h3>
        <p className="text-sm text-gray-600 mb-4">
          Select 2 or more test runs to compare:
        </p>

        {/* Test Run Selector */}
        <div className="flex flex-wrap gap-2 mb-4">
          {testsData?.data?.test_runs
            ?.filter((tr) => tr.status === 'completed')
            .map((run) => (
              <button
                key={run.id}
                onClick={() => toggleTestRun(run.id)}
                className={`px-3 py-1 rounded-full text-sm ${
                  selectedTestRuns.includes(run.id)
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 hover:bg-gray-200'
                }`}
              >
                {run.layout_library} + {run.ocr_library}
              </button>
            ))}
        </div>

        {/* Comparison Results */}
        {comparisonData?.data?.comparisons?.length >= 2 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left border-b">
                  <th className="py-2">Configuration</th>
                  <th className="py-2">Documents</th>
                  <th className="py-2">Accuracy</th>
                  <th className="py-2">Duration</th>
                  <th className="py-2">Date</th>
                </tr>
              </thead>
              <tbody>
                {comparisonData.data.comparisons.map((comp) => (
                  <tr key={comp.test_run_id} className="border-b">
                    <td className="py-2 font-medium">
                      {comp.layout_library} + {comp.ocr_library}
                    </td>
                    <td className="py-2">{comp.document_count}</td>
                    <td className="py-2">
                      <span
                        className={`font-bold ${
                          comp.average_accuracy >= 0.8
                            ? 'text-green-600'
                            : comp.average_accuracy >= 0.5
                            ? 'text-yellow-600'
                            : 'text-red-600'
                        }`}
                      >
                        {(comp.average_accuracy * 100).toFixed(1)}%
                      </span>
                    </td>
                    <td className="py-2 text-gray-600">
                      {formatDuration(comp.started_at, comp.completed_at) || '-'}
                    </td>
                    <td className="py-2">
                      {new Date(comp.started_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

export default MetricsPage
