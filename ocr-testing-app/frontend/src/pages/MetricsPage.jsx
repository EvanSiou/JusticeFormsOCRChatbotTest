import { useState, useMemo, useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { metricsAPI } from '../services/api'

// ─── MultiSelect Component ───────────────────────────────
function MultiSelect({ label, value = [], onChange, options = [], placeholder = 'All', renderOption }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const toggle = (val) => {
    if (value.includes(val)) onChange(value.filter(v => v !== val))
    else onChange([...value, val])
  }

  const displayText = value.length === 0
    ? placeholder
    : value.length === 1
      ? (renderOption ? renderOption(value[0]) : value[0])
      : `${value.length} selected`

  return (
    <div ref={ref} className="relative">
      <label className="block text-xs font-medium text-gray-500 mb-1">{label}</label>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full text-sm border rounded px-2 py-1.5 text-left bg-white flex items-center justify-between hover:border-gray-400"
      >
        <span className={`truncate ${value.length === 0 ? 'text-gray-400' : 'text-gray-800'}`}>
          {displayText}
        </span>
        <svg className="w-3 h-3 text-gray-400 ml-1 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-full bg-white border rounded shadow-lg max-h-48 overflow-y-auto">
          {value.length > 0 && (
            <button
              type="button"
              onClick={() => { onChange([]); setOpen(false) }}
              className="w-full text-left px-2 py-1 text-xs text-blue-600 hover:bg-blue-50 border-b"
            >
              Clear selection
            </button>
          )}
          {options.map((opt) => {
            const optVal = typeof opt === 'object' ? opt.id : opt
            const optLabel = typeof opt === 'object' ? opt.label : (renderOption ? renderOption(opt) : opt)
            const checked = value.includes(optVal)
            return (
              <label
                key={optVal}
                className={`flex items-center gap-2 px-2 py-1.5 text-sm cursor-pointer hover:bg-gray-50 ${checked ? 'bg-blue-50' : ''}`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggle(optVal)}
                  className="rounded text-blue-600"
                />
                <span className="truncate">{optLabel}</span>
              </label>
            )
          })}
          {options.length === 0 && (
            <div className="px-2 py-1.5 text-xs text-gray-400">No options</div>
          )}
        </div>
      )}
    </div>
  )
}

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
    user: [],
    date: [],
    batch: [],
    batchJob: [],
    batchType: [],
    field: '',
    testRun: [],
    document: [],
    prompt: [],
  })

  const availableFilters = matrixData?.data?.filters || {}
  const rows = matrixData?.data?.rows || []

  // Apply filters (arrays use .includes, field stays single-select)
  const filteredRows = useMemo(() => {
    return rows.filter((r) => {
      if (filters.user.length && !filters.user.includes(r.user)) return false
      if (filters.date.length && !filters.date.includes(r.date)) return false
      if (filters.batch.length && !filters.batch.includes(r.batch_id)) return false
      if (filters.batchJob.length && !filters.batchJob.includes(r.batch_job_id)) return false
      if (filters.batchType.length && !filters.batchType.includes(r.batch_type)) return false
      if (filters.testRun.length && !filters.testRun.includes(r.test_run_id)) return false
      if (filters.document.length && !filters.document.includes(r.document_id)) return false
      if (filters.prompt.length && !filters.prompt.includes(r.ocr_prompt_id || '')) return false
      return true
    })
  }, [rows, filters])

  // Build the accuracy matrix: { layout -> { ocr -> { sum, count } } }
  const { accuracyMatrix, classificationMatrix, judgeMatrix, speedMatrix, layoutLibs, ocrLibs } = useMemo(() => {
    const accMap = {}
    const clsMap = {}
    const jdgMap = {}
    const spdMap = {}
    const layouts = new Set()
    const ocrs = new Set()

    for (const row of filteredRows) {
      const lay = row.layout_library
      const ocr = row.ocr_library
      layouts.add(lay)
      ocrs.add(ocr)

      // OCR Accuracy
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

      // Classification Accuracy
      if (filters.field && row.field_classification_scores?.[filters.field] != null) {
        if (!clsMap[lay]) clsMap[lay] = {}
        if (!clsMap[lay][ocr]) clsMap[lay][ocr] = { sum: 0, count: 0 }
        clsMap[lay][ocr].sum += row.field_classification_scores[filters.field]
        clsMap[lay][ocr].count += 1
      } else if (!filters.field && row.classification_accuracy != null) {
        if (!clsMap[lay]) clsMap[lay] = {}
        if (!clsMap[lay][ocr]) clsMap[lay][ocr] = { sum: 0, count: 0 }
        clsMap[lay][ocr].sum += row.classification_accuracy
        clsMap[lay][ocr].count += 1
      }

      // Judge Score
      if (filters.field && row.field_judge_scores?.[filters.field] != null) {
        if (!jdgMap[lay]) jdgMap[lay] = {}
        if (!jdgMap[lay][ocr]) jdgMap[lay][ocr] = { sum: 0, count: 0 }
        jdgMap[lay][ocr].sum += row.field_judge_scores[filters.field]
        jdgMap[lay][ocr].count += 1
      } else if (!filters.field && row.judge_overall_score != null) {
        if (!jdgMap[lay]) jdgMap[lay] = {}
        if (!jdgMap[lay][ocr]) jdgMap[lay][ocr] = { sum: 0, count: 0 }
        jdgMap[lay][ocr].sum += row.judge_overall_score
        jdgMap[lay][ocr].count += 1
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
      classificationMatrix: clsMap,
      judgeMatrix: jdgMap,
      speedMatrix: spdMap,
      layoutLibs: [...layouts].sort(),
      ocrLibs: [...ocrs].sort(),
    }
  }, [filteredRows, filters.field])

  // Check if any rows have classification or judge data
  const hasClassificationData = filteredRows.some(r => r.classification_accuracy != null)
  const hasJudgeData = filteredRows.some(r => r.judge_overall_score != null)

  const clearFilters = () =>
    setFilters({ user: [], date: [], batch: [], batchJob: [], batchType: [], field: '', testRun: [], document: [], prompt: [] })

  const activeFilterCount = Object.values(filters).filter(v => Array.isArray(v) ? v.length > 0 : Boolean(v)).length

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
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-8 gap-3 mb-6">
        <MultiSelect
          label="User"
          value={filters.user}
          onChange={(v) => setFilters((f) => ({ ...f, user: v }))}
          options={availableFilters.users || []}
          placeholder="All users"
        />
        <MultiSelect
          label="Date"
          value={filters.date}
          onChange={(v) => setFilters((f) => ({ ...f, date: v }))}
          options={availableFilters.dates || []}
          placeholder="All dates"
        />
        <MultiSelect
          label="Batch Job"
          value={filters.batchJob}
          onChange={(v) => setFilters((f) => ({ ...f, batchJob: v }))}
          options={availableFilters.batch_jobs || []}
          placeholder="All jobs"
        />
        <MultiSelect
          label="Batch"
          value={filters.batch}
          onChange={(v) => setFilters((f) => ({ ...f, batch: v }))}
          options={availableFilters.batches || []}
          placeholder="All batches"
        />
        <MultiSelect
          label="Type"
          value={filters.batchType}
          onChange={(v) => setFilters((f) => ({ ...f, batchType: v }))}
          options={availableFilters.batch_types || []}
          placeholder="All types"
        />
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
        <MultiSelect
          label="Test Run"
          value={filters.testRun}
          onChange={(v) => setFilters((f) => ({ ...f, testRun: v }))}
          options={availableFilters.test_runs || []}
          placeholder="All runs"
        />
        <MultiSelect
          label="Document"
          value={filters.document}
          onChange={(v) => setFilters((f) => ({ ...f, document: v }))}
          options={(availableFilters.documents || []).map(d => ({ id: d, label: d.slice(0, 12) + '...' }))}
          placeholder="All docs"
        />
        {availableFilters.prompts?.length > 0 && (
          <MultiSelect
            label="Prompt"
            value={filters.prompt}
            onChange={(v) => setFilters((f) => ({ ...f, prompt: v }))}
            options={availableFilters.prompts || []}
            placeholder="All prompts"
          />
        )}
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

          {/* Classification Accuracy Matrix (only if data exists) */}
          {hasClassificationData && (
          <div>
            <h4 className="text-md font-semibold mb-3">
              <span className="text-purple-700">Classification Accuracy</span> {filters.field ? `(${filters.field})` : '(Overall)'}
            </h4>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr>
                    <th className="border px-3 py-2 bg-purple-50 text-left text-xs font-medium text-purple-600">
                      Layout \ OCR
                    </th>
                    {ocrLibs.map((ocr) => (
                      <th key={ocr} className="border px-3 py-2 bg-purple-50 text-center text-xs font-medium text-purple-700">
                        {ocr}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {layoutLibs.map((lay) => (
                    <tr key={lay}>
                      <td className="border px-3 py-2 font-medium text-gray-700 bg-purple-50 text-xs">
                        {lay}
                      </td>
                      {ocrLibs.map((ocr) => {
                        const cell = classificationMatrix[lay]?.[ocr]
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
          )}

          {/* Judge Score Matrix (only if data exists) */}
          {hasJudgeData && (
          <div>
            <h4 className="text-md font-semibold mb-3">
              <span className="text-amber-700">Judge Score</span> {filters.field ? `(${filters.field})` : '(Overall)'}
            </h4>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr>
                    <th className="border px-3 py-2 bg-amber-50 text-left text-xs font-medium text-amber-600">
                      Layout \ OCR
                    </th>
                    {ocrLibs.map((ocr) => (
                      <th key={ocr} className="border px-3 py-2 bg-amber-50 text-center text-xs font-medium text-amber-700">
                        {ocr}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {layoutLibs.map((lay) => (
                    <tr key={lay}>
                      <td className="border px-3 py-2 font-medium text-gray-700 bg-amber-50 text-xs">
                        {lay}
                      </td>
                      {ocrLibs.map((ocr) => {
                        const cell = judgeMatrix[lay]?.[ocr]
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
          )}

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

// ─── Classification Matrix Section ────────────────────────
function ClassificationMatrixSection({ classMatrixData, isLoading }) {
  const [filters, setFilters] = useState({ user: [], date: [], classifierModel: [], prompt: [] })

  const availableFilters = classMatrixData?.data?.filters || {}
  const rows = classMatrixData?.data?.rows || []

  const filteredRows = useMemo(() => {
    return rows.filter((r) => {
      if (filters.user.length && !filters.user.includes(r.user)) return false
      if (filters.date.length && !filters.date.includes(r.date)) return false
      if (filters.classifierModel.length && !filters.classifierModel.includes(r.classifier_model)) return false
      if (filters.prompt.length && !filters.prompt.includes(r.prompt_id || '')) return false
      return true
    })
  }, [rows, filters])

  // Aggregate by classifier model — includes OCR accuracy, classification accuracy, and judge scores
  const modelStats = useMemo(() => {
    const stats = {}
    for (const row of filteredRows) {
      const model = row.classifier_model
      if (!stats[model]) stats[model] = {
        total: 0, verified: 0,
        verifiedAccSum: 0, verifiedAccCount: 0,
        ocrAccSum: 0, ocrAccCount: 0,
        clsAccSum: 0, clsAccCount: 0,
        judgeSum: 0, judgeCount: 0,
      }
      stats[model].total += 1
      if (row.is_verified) {
        stats[model].verified += 1
        if (row.classification_verified_accuracy != null) {
          stats[model].verifiedAccSum += row.classification_verified_accuracy
          stats[model].verifiedAccCount += 1
        }
      }
      if (row.ocr_accuracy != null) {
        stats[model].ocrAccSum += row.ocr_accuracy
        stats[model].ocrAccCount += 1
      }
      if (row.classification_accuracy != null) {
        stats[model].clsAccSum += row.classification_accuracy
        stats[model].clsAccCount += 1
      }
      if (row.judge_overall_score != null) {
        stats[model].judgeSum += row.judge_overall_score
        stats[model].judgeCount += 1
      }
    }
    return stats
  }, [filteredRows])

  const modelNames = Object.keys(modelStats).sort()

  const MODEL_LABELS = {
    claude_bedrock: 'Claude Sonnet 4.5',
    claude_haiku_bedrock: 'Claude Haiku 4.5',
    nova_pro_bedrock: 'Nova Pro',
    nova_lite_bedrock: 'Nova Lite',
    pixtral_large_bedrock: 'Pixtral Large',
    llama4_maverick_bedrock: 'Llama 4 Maverick',
    llama4_scout_bedrock: 'Llama 4 Scout',
    gpt5: 'GPT-5',
    gpt5_mini: 'GPT-5 mini',
    // Legacy names for old test runs
    claude: 'Claude Sonnet 4.5',
    llama4_maverick: 'Llama 4 Maverick',
    mistral_medium3: 'Mistral Medium 3',
  }

  const clearFilters = () => setFilters({ user: [], date: [], classifierModel: [], prompt: [] })
  const activeFilterCount = Object.values(filters).filter(v => Array.isArray(v) ? v.length > 0 : Boolean(v)).length

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h3 className="text-lg font-semibold mb-4">Classification Accuracy</h3>
        <p className="text-gray-500">Loading classification data...</p>
      </div>
    )
  }

  if (rows.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h3 className="text-lg font-semibold mb-4">Classification Accuracy</h3>
        <p className="text-gray-500">No classification results yet. Run classification on documents to see accuracy by model.</p>
      </div>
    )
  }

  return (
    <div className="bg-white rounded-lg shadow p-6 mb-6">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold">Classification Accuracy</h3>
        {activeFilterCount > 0 && (
          <button onClick={clearFilters} className="text-sm text-blue-600 hover:text-blue-800">
            Clear filters ({activeFilterCount})
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-4">
        <MultiSelect
          label="User"
          value={filters.user}
          onChange={(v) => setFilters(f => ({ ...f, user: v }))}
          options={availableFilters.users || []}
          placeholder="All users"
        />
        <MultiSelect
          label="Date"
          value={filters.date}
          onChange={(v) => setFilters(f => ({ ...f, date: v }))}
          options={availableFilters.dates || []}
          placeholder="All dates"
        />
        <MultiSelect
          label="Model"
          value={filters.classifierModel}
          onChange={(v) => setFilters(f => ({ ...f, classifierModel: v }))}
          options={(availableFilters.classifier_models || []).map(m => ({ id: m, label: MODEL_LABELS[m] || m }))}
          placeholder="All models"
        />
        {availableFilters.prompts?.length > 0 && (
          <MultiSelect
            label="Prompt"
            value={filters.prompt}
            onChange={(v) => setFilters(f => ({ ...f, prompt: v }))}
            options={availableFilters.prompts || []}
            placeholder="All prompts"
          />
        )}
      </div>

      <p className="text-xs text-gray-400 mb-4">
        Showing {filteredRows.length} classified document{filteredRows.length !== 1 ? 's' : ''} across {modelNames.length} model{modelNames.length !== 1 ? 's' : ''}
      </p>

      {modelNames.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr>
                <th className="border px-3 py-2 bg-gray-50 text-left text-xs font-medium text-gray-500">Classifier Model</th>
                <th className="border px-3 py-2 bg-blue-50 text-center text-xs font-medium text-blue-700">OCR Accuracy</th>
                <th className="border px-3 py-2 bg-purple-50 text-center text-xs font-medium text-purple-700">Classification Accuracy</th>
                <th className="border px-3 py-2 bg-amber-50 text-center text-xs font-medium text-amber-700">Judge Score</th>
                <th className="border px-3 py-2 bg-green-50 text-center text-xs font-medium text-green-700">Verified Accuracy</th>
                <th className="border px-3 py-2 bg-gray-50 text-center text-xs font-medium text-gray-700">Docs</th>
              </tr>
            </thead>
            <tbody>
              {modelNames.map(model => {
                const s = modelStats[model]
                const ocrAvg = s.ocrAccCount > 0 ? s.ocrAccSum / s.ocrAccCount : null
                const clsAvg = s.clsAccCount > 0 ? s.clsAccSum / s.clsAccCount : null
                const judgeAvg = s.judgeCount > 0 ? s.judgeSum / s.judgeCount : null
                const verifiedAvg = s.verifiedAccCount > 0 ? s.verifiedAccSum / s.verifiedAccCount : null
                return (
                  <tr key={model}>
                    <td className="border px-3 py-2 font-medium text-gray-700 bg-gray-50 text-xs">
                      {MODEL_LABELS[model] || model}
                    </td>
                    <td className={`border px-3 py-2 text-center font-semibold text-sm ${ocrAvg != null ? accuracyColor(ocrAvg) : 'text-gray-300'}`}>
                      {ocrAvg != null ? `${(ocrAvg * 100).toFixed(1)}%` : '-'}
                      {s.ocrAccCount > 0 && <div className="text-[10px] font-normal opacity-60">n={s.ocrAccCount}</div>}
                    </td>
                    <td className={`border px-3 py-2 text-center font-semibold text-sm ${clsAvg != null ? accuracyColor(clsAvg) : 'text-gray-300'}`}>
                      {clsAvg != null ? `${(clsAvg * 100).toFixed(1)}%` : '-'}
                      {s.clsAccCount > 0 && <div className="text-[10px] font-normal opacity-60">n={s.clsAccCount}</div>}
                    </td>
                    <td className={`border px-3 py-2 text-center font-semibold text-sm ${judgeAvg != null ? accuracyColor(judgeAvg) : 'text-gray-300'}`}>
                      {judgeAvg != null ? `${(judgeAvg * 100).toFixed(1)}%` : '-'}
                      {s.judgeCount > 0 && <div className="text-[10px] font-normal opacity-60">n={s.judgeCount}</div>}
                    </td>
                    <td className={`border px-3 py-2 text-center font-semibold text-sm ${verifiedAvg != null ? accuracyColor(verifiedAvg) : 'text-gray-300'}`}>
                      {verifiedAvg != null ? `${(verifiedAvg * 100).toFixed(1)}%` : '-'}
                      {s.verifiedAccCount > 0 && <div className="text-[10px] font-normal opacity-60">n={s.verifiedAccCount}</div>}
                    </td>
                    <td className="border px-3 py-2 text-center text-sm">{s.total}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-gray-500">No data matches the current filters.</p>
      )}
    </div>
  )
}

// ─── Main Page ────────────────────────────────────────────
function MetricsPage() {
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
  const { data: fieldData } = useQuery({
    queryKey: ['metrics-by-field'],
    queryFn: () => metricsAPI.getByField(),
  })

  // Fetch classification matrix
  const { data: classMatrixData, isLoading: classMatrixLoading } = useQuery({
    queryKey: ['metrics-classification-matrix'],
    queryFn: () => metricsAPI.getClassificationMatrix(),
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

      {/* Classification Accuracy by Model */}
      <ClassificationMatrixSection classMatrixData={classMatrixData} isLoading={classMatrixLoading} />

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

    </div>
  )
}

export default MetricsPage
