import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { formsAPI, syntheticAPI, referenceAPI } from '../services/api'

const FIELD_TYPES = [
  { value: 'text_short', label: 'Text Short' },
  { value: 'numeric_short', label: 'Numeric Short' },
  { value: 'sentence', label: 'Sentence' },
  { value: 'full_name', label: 'Full Name' },
  { value: 'day_month', label: 'Day Month' },
  { value: '2_digit_year', label: '2 Digit Year' },
  { value: '4_digit_year', label: '4 Digit Year' },
]

function SyntheticDataPage() {
  const [searchParams] = useSearchParams()
  const [step, setStep] = useState(1)
  const [selectedFormId, setSelectedFormId] = useState(searchParams.get('formId') || '')
  const [fieldMappings, setFieldMappings] = useState([])
  const [count, setCount] = useState(10)
  const [skewPreset, setSkewPreset] = useState('medium')
  const [isDrawing, setIsDrawing] = useState(false)
  const [currentField, setCurrentField] = useState({ name: '', x: 0, y: 0, width: 0, height: 0 })
  const [startPos, setStartPos] = useState({ x: 0, y: 0 })
  const [pickMode, setPickMode] = useState('click') // 'click' or 'drag'
  const [hoverPos, setHoverPos] = useState(null)
  const [showFieldForm, setShowFieldForm] = useState(null) // {x, y, width?, height?}
  const [newFieldName, setNewFieldName] = useState('')
  const [newFieldType, setNewFieldType] = useState('text_short')

  const canvasRef = useRef(null)
  const imageRef = useRef(null)
  const queryClient = useQueryClient()

  // Fetch forms
  const { data: formsData } = useQuery({
    queryKey: ['forms'],
    queryFn: () => formsAPI.list(),
  })

  // Fetch selected form
  const { data: formData } = useQuery({
    queryKey: ['form', selectedFormId],
    queryFn: () => formsAPI.get(selectedFormId),
    enabled: !!selectedFormId,
  })

  // Fetch form image
  const { data: imageData } = useQuery({
    queryKey: ['form-image', selectedFormId],
    queryFn: () => formsAPI.getImage(selectedFormId),
    enabled: !!selectedFormId,
  })

  // Fetch batches
  const { data: batchesData } = useQuery({
    queryKey: ['batches'],
    queryFn: () => syntheticAPI.listBatches(),
  })

  // Update field mappings mutation
  const updateFieldsMutation = useMutation({
    mutationFn: () => formsAPI.updateFields(selectedFormId, fieldMappings),
    onSuccess: () => {
      queryClient.invalidateQueries(['form', selectedFormId])
    },
  })

  // Generate batch mutation
  const generateMutation = useMutation({
    mutationFn: () => {
      return syntheticAPI.generate(
        selectedFormId,
        count,
        null,
        skewPreset === 'none' ? null : skewPreset
      )
    },
    onSuccess: () => {
      queryClient.invalidateQueries(['batches'])
      setStep(1)
      setSelectedFormId('')
      setFieldMappings([])
    },
  })

  const isHandwritten = formData?.data?.form_type === 'handwritten'

  // Load existing field mappings when form is selected
  useEffect(() => {
    if (formData?.data?.field_mappings) {
      setFieldMappings(formData.data.field_mappings)
    }
  }, [formData])

  // Draw canvas
  useEffect(() => {
    if (canvasRef.current && imageRef.current && step === 2) {
      const canvas = canvasRef.current
      const ctx = canvas.getContext('2d')
      const img = imageRef.current

      canvas.width = img.naturalWidth
      canvas.height = img.naturalHeight

      ctx.drawImage(img, 0, 0)

      // Draw existing field mappings
      fieldMappings.forEach((field, idx) => {
        if (pickMode === 'click') {
          // Draw red dot with number (like notebook)
          ctx.beginPath()
          ctx.arc(field.x, field.y, 10, 0, 2 * Math.PI)
          ctx.fillStyle = 'red'
          ctx.fill()
          ctx.strokeStyle = 'darkred'
          ctx.lineWidth = 2
          ctx.stroke()
          ctx.fillStyle = 'white'
          ctx.font = 'bold 12px Arial'
          ctx.textAlign = 'center'
          ctx.textBaseline = 'middle'
          ctx.fillText(idx + 1, field.x, field.y)
          // Show name + type
          ctx.fillStyle = '#3B82F6'
          ctx.font = '14px Arial'
          ctx.textAlign = 'left'
          ctx.textBaseline = 'bottom'
          const typeLabel = FIELD_TYPES.find(ft => ft.value === field.field_type)?.label || field.field_type || ''
          ctx.fillText(`${field.name} [${typeLabel}]`, field.x + 14, field.y + 4)
        } else {
          // Draw rectangle
          ctx.strokeStyle = '#3B82F6'
          ctx.lineWidth = 2
          ctx.strokeRect(field.x, field.y, field.width, field.height)
          ctx.fillStyle = '#3B82F6'
          ctx.font = '14px Arial'
          ctx.textAlign = 'left'
          ctx.textBaseline = 'bottom'
          const typeLabel = FIELD_TYPES.find(ft => ft.value === field.field_type)?.label || field.field_type || ''
          ctx.fillText(`${field.name} [${typeLabel}]`, field.x + 2, field.y - 5)
        }
      })
    }
  }, [fieldMappings, step, imageData, pickMode])

  const getScaledCoords = (e) => {
    const rect = canvasRef.current.getBoundingClientRect()
    const scaleX = canvasRef.current.width / rect.width
    const scaleY = canvasRef.current.height / rect.height
    return {
      x: Math.round((e.clientX - rect.left) * scaleX),
      y: Math.round((e.clientY - rect.top) * scaleY),
    }
  }

  const handleCanvasClick = (e) => {
    if (pickMode !== 'click') return
    const { x, y } = getScaledCoords(e)
    setShowFieldForm({ x, y, width: 200, height: 30 })
    setNewFieldName('')
    setNewFieldType('text_short')
  }

  const handleCanvasMouseDown = (e) => {
    if (pickMode !== 'drag') return
    const { x, y } = getScaledCoords(e)
    setIsDrawing(true)
    setStartPos({ x, y })
    setCurrentField({ ...currentField, x, y })
  }

  const handleCanvasMouseMove = (e) => {
    const coords = getScaledCoords(e)
    setHoverPos(coords)

    if (pickMode !== 'drag' || !isDrawing) return

    // Redraw canvas
    const ctx = canvasRef.current.getContext('2d')
    ctx.drawImage(imageRef.current, 0, 0)

    // Draw existing fields
    fieldMappings.forEach((field) => {
      ctx.strokeStyle = '#3B82F6'
      ctx.lineWidth = 2
      ctx.strokeRect(field.x, field.y, field.width, field.height)
      ctx.fillStyle = '#3B82F6'
      ctx.font = '14px Arial'
      ctx.fillText(field.name, field.x + 2, field.y - 5)
    })

    // Draw current selection
    ctx.strokeStyle = '#10B981'
    ctx.lineWidth = 2
    ctx.strokeRect(startPos.x, startPos.y, coords.x - startPos.x, coords.y - startPos.y)
  }

  const handleCanvasMouseUp = (e) => {
    if (pickMode !== 'drag' || !isDrawing) return
    setIsDrawing(false)

    const { x, y } = getScaledCoords(e)
    const width = Math.abs(x - startPos.x)
    const height = Math.abs(y - startPos.y)

    if (width > 10 && height > 10) {
      setShowFieldForm({
        x: Math.min(startPos.x, x),
        y: Math.min(startPos.y, y),
        width,
        height,
      })
      setNewFieldName('')
      setNewFieldType('text_short')
    }
  }

  const addFieldFromForm = () => {
    if (!newFieldName || !showFieldForm) return
    setFieldMappings([...fieldMappings, {
      name: newFieldName,
      x: showFieldForm.x,
      y: showFieldForm.y,
      width: showFieldForm.width || 200,
      height: showFieldForm.height || 30,
      font_size: 12,
      font_color: '#000000',
      field_type: newFieldType,
    }])
    setShowFieldForm(null)
    setNewFieldName('')
    setNewFieldType('text_short')
  }

  const removeField = (index) => {
    setFieldMappings(fieldMappings.filter((_, i) => i !== index))
  }

  const undoLast = () => {
    setFieldMappings(fieldMappings.slice(0, -1))
  }

  // For handwritten forms, skip Step 2 (field mapping)
  const handleNextFromStep1 = () => {
    if (isHandwritten) {
      setStep(3) // Skip to generate
    } else {
      setStep(2) // Go to field mapping
    }
  }

  return (
    <div>
      <h2 className="text-2xl font-bold mb-6">Generate Synthetic Data</h2>

      {/* Step Indicator */}
      <div className="flex items-center mb-8">
        {(isHandwritten ? [1, 3] : [1, 2, 3]).map((s, idx, arr) => (
          <div key={s} className="flex items-center">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center ${
                step >= s ? 'bg-blue-600 text-white' : 'bg-gray-200'
              }`}
            >
              {idx + 1}
            </div>
            {idx < arr.length - 1 && (
              <div
                className={`w-24 h-1 ${
                  step > s ? 'bg-blue-600' : 'bg-gray-200'
                }`}
              />
            )}
          </div>
        ))}
      </div>

      {/* Step 1: Select Form */}
      {step === 1 && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold mb-4">Step 1: Select Base Form</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {formsData?.data?.forms?.map((form) => (
              <div
                key={form.id}
                onClick={() => setSelectedFormId(form.id)}
                className={`p-4 border-2 rounded-lg cursor-pointer transition-colors ${
                  selectedFormId === form.id
                    ? 'border-blue-600 bg-blue-50'
                    : 'border-gray-200 hover:border-gray-400'
                }`}
              >
                <div className="flex items-center gap-2">
                  <h4 className="font-medium">{form.name}</h4>
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-medium ${
                      form.form_type === 'handwritten'
                        ? 'bg-purple-100 text-purple-700'
                        : 'bg-blue-100 text-blue-700'
                    }`}
                  >
                    {form.form_type === 'handwritten' ? 'Handwritten' : 'Empty'}
                  </span>
                </div>
                <p className="text-sm text-gray-500">
                  {form.form_type === 'handwritten'
                    ? 'Skew copies'
                    : `${form.field_mappings?.length || 0} fields`}
                </p>
              </div>
            ))}
          </div>
          <div className="mt-6 flex justify-end">
            <button
              onClick={handleNextFromStep1}
              disabled={!selectedFormId}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {isHandwritten ? 'Next: Generate Copies' : 'Next: Define Fields'}
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Define Field Coordinates (Empty forms only) */}
      {step === 2 && !isHandwritten && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold mb-2">
            Step 2: Define Field Coordinates
          </h3>

          {/* Mode toggle */}
          <div className="flex items-center gap-4 mb-4">
            <span className="text-sm font-medium text-gray-700">Mode:</span>
            <button
              onClick={() => setPickMode('click')}
              className={`px-3 py-1 text-sm rounded ${
                pickMode === 'click'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-200 hover:bg-gray-300'
              }`}
            >
              Click to Mark
            </button>
            <button
              onClick={() => setPickMode('drag')}
              className={`px-3 py-1 text-sm rounded ${
                pickMode === 'drag'
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-200 hover:bg-gray-300'
              }`}
            >
              Drag Rectangle
            </button>
            <span className="text-sm text-gray-500 ml-2">
              {pickMode === 'click'
                ? 'Click where text should be placed'
                : 'Click and drag to draw field areas'}
            </span>
          </div>

          {/* Coordinate display */}
          {hoverPos && (
            <div className="text-xs font-mono text-gray-500 mb-2">
              x={hoverPos.x}, y={hoverPos.y}
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Canvas */}
            <div className="lg:col-span-2 overflow-auto border rounded relative">
              {imageData?.data?.url && (
                <>
                  <img
                    ref={imageRef}
                    src={imageData.data.url}
                    alt="Form"
                    className="hidden"
                    crossOrigin="anonymous"
                    onLoad={() => {
                      if (canvasRef.current && imageRef.current) {
                        const canvas = canvasRef.current
                        const ctx = canvas.getContext('2d')
                        canvas.width = imageRef.current.naturalWidth
                        canvas.height = imageRef.current.naturalHeight
                        ctx.drawImage(imageRef.current, 0, 0)
                      }
                    }}
                  />
                  <canvas
                    ref={canvasRef}
                    className="max-w-full cursor-crosshair"
                    onClick={handleCanvasClick}
                    onMouseDown={handleCanvasMouseDown}
                    onMouseMove={handleCanvasMouseMove}
                    onMouseUp={handleCanvasMouseUp}
                  />
                </>
              )}

              {/* Field Name + Type Popover */}
              {showFieldForm && (
                <div className="absolute top-4 right-4 bg-white border shadow-lg rounded-lg p-4 z-10 w-72">
                  <h4 className="font-medium mb-3 text-sm">Add Field</h4>
                  <div className="mb-3">
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Field Name
                    </label>
                    <input
                      type="text"
                      value={newFieldName}
                      onChange={(e) => setNewFieldName(e.target.value)}
                      placeholder="e.g., defendant_name"
                      className="w-full px-2 py-1 border rounded text-sm"
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') addFieldFromForm()
                        if (e.key === 'Escape') setShowFieldForm(null)
                      }}
                    />
                  </div>
                  <div className="mb-3">
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Field Type
                    </label>
                    <select
                      value={newFieldType}
                      onChange={(e) => setNewFieldType(e.target.value)}
                      className="w-full px-2 py-1 border rounded text-sm"
                    >
                      {FIELD_TYPES.map((ft) => (
                        <option key={ft.value} value={ft.value}>
                          {ft.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={addFieldFromForm}
                      disabled={!newFieldName}
                      className="flex-1 px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 disabled:opacity-50"
                    >
                      Add
                    </button>
                    <button
                      onClick={() => setShowFieldForm(null)}
                      className="px-3 py-1 border text-sm rounded hover:bg-gray-50"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Field List */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <h4 className="font-medium">Mapped Fields ({fieldMappings.length})</h4>
                {fieldMappings.length > 0 && (
                  <button
                    onClick={undoLast}
                    className="text-sm text-blue-600 hover:underline"
                  >
                    Undo Last
                  </button>
                )}
              </div>
              {fieldMappings.length > 0 ? (
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {fieldMappings.map((field, idx) => (
                    <div
                      key={idx}
                      className="flex justify-between items-center p-2 bg-gray-50 rounded"
                    >
                      <div>
                        <span className="text-sm font-medium">{idx + 1}. {field.name}</span>
                        <span className="text-xs text-gray-400 ml-2">
                          ({field.x}, {field.y})
                        </span>
                        <span className="block text-xs text-purple-600">
                          {FIELD_TYPES.find(ft => ft.value === field.field_type)?.label || field.field_type}
                        </span>
                      </div>
                      <button
                        onClick={() => removeField(idx)}
                        className="text-red-600 text-sm"
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-gray-500 text-sm">
                  No fields mapped yet. {pickMode === 'click' ? 'Click' : 'Draw'} on the image to add fields.
                </p>
              )}
            </div>
          </div>

          <div className="mt-6 flex justify-between">
            <button
              onClick={() => setStep(1)}
              className="px-6 py-2 border rounded-lg hover:bg-gray-50"
            >
              Back
            </button>
            <div className="flex gap-3">
              <button
                onClick={() => updateFieldsMutation.mutate()}
                disabled={updateFieldsMutation.isPending}
                className="px-6 py-2 border rounded-lg hover:bg-gray-50"
              >
                {updateFieldsMutation.isPending ? 'Saving...' : 'Save Fields'}
              </button>
              <button
                onClick={async () => {
                  await updateFieldsMutation.mutateAsync()
                  setStep(3)
                }}
                disabled={fieldMappings.length === 0 || updateFieldsMutation.isPending}
                className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {updateFieldsMutation.isPending ? 'Saving...' : 'Next: Generate'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Step 3: Generate */}
      {step === 3 && (
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-semibold mb-4">
            {isHandwritten ? 'Step 2: Generate Skewed Copies' : 'Step 3: Generate Filled Forms'}
          </h3>
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Number of {isHandwritten ? 'copies' : 'documents'} to generate
            </label>
            <input
              type="number"
              value={count}
              onChange={(e) => setCount(parseInt(e.target.value) || 1)}
              min={1}
              max={100}
              className="w-32 px-3 py-2 border rounded-md"
            />
          </div>

          {/* Skew Preset */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Scan Simulation (Skew)
            </label>
            <select
              value={skewPreset}
              onChange={(e) => setSkewPreset(e.target.value)}
              className="w-48 px-3 py-2 border rounded-md"
            >
              <option value="none">None</option>
              <option value="light">Light (subtle effects)</option>
              <option value="medium">Medium (moderate effects)</option>
              <option value="heavy">Heavy (strong effects)</option>
            </select>
            <p className="text-xs text-gray-500 mt-1">
              Controls rotation, noise, blur, brightness, and contrast variation.
            </p>
          </div>

          <div className="bg-gray-50 p-4 rounded-lg mb-6">
            <h4 className="font-medium mb-2">Summary</h4>
            <p className="text-sm text-gray-600">
              Form: {formData?.data?.name}
              {isHandwritten && (
                <span className="ml-2 px-2 py-0.5 bg-purple-100 text-purple-700 rounded text-xs">
                  Handwritten
                </span>
              )}
            </p>
            {!isHandwritten && (
              <p className="text-sm text-gray-600">
                Fields: {fieldMappings.length}
              </p>
            )}
            <p className="text-sm text-gray-600">
              Scan Simulation: {skewPreset === 'none' ? 'None' : skewPreset}
            </p>
            <p className="text-sm text-gray-600">
              {isHandwritten ? 'Copies' : 'Documents'}: {count}
            </p>
          </div>

          <div className="mt-6 flex justify-between">
            <button
              onClick={() => setStep(isHandwritten ? 1 : 2)}
              className="px-6 py-2 border rounded-lg hover:bg-gray-50"
            >
              Back
            </button>
            <button
              onClick={() => generateMutation.mutate()}
              disabled={generateMutation.isPending}
              className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
            >
              {generateMutation.isPending
                ? 'Generating...'
                : isHandwritten
                  ? 'Generate Skewed Copies'
                  : 'Generate Batch'}
            </button>
          </div>

          {generateMutation.isError && (
            <p className="text-red-600 text-sm mt-4">
              {generateMutation.error?.response?.data?.detail || 'Generation failed'}
            </p>
          )}
        </div>
      )}

      {/* ===== Reference Data Templates ===== */}
      <ReferenceTemplatesSection />

      {/* ===== Upload Filled Forms with Reference Data ===== */}
      <UploadWithReferenceSection />

      {/* Existing Batches */}
      <div className="mt-8 bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-4">Existing Batches</h3>
        {batchesData?.data?.batches?.length > 0 ? (
          <div className="space-y-3">
            {batchesData.data.batches.map((batch) => (
              <div
                key={batch.id}
                className="flex justify-between items-center p-3 bg-gray-50 rounded-lg"
              >
                <div>
                  <p className="font-medium">
                    {batch.batch_number} - {batch.form_name} - {new Date(batch.created_at).toLocaleDateString()}
                    {batch.created_by_name && ` - ${batch.created_by_name.split('@')[0]}`}
                    <span
                      className={`ml-2 px-2 py-0.5 rounded text-xs font-medium ${
                        batch.batch_type === 'handwritten'
                          ? 'bg-purple-100 text-purple-700'
                          : 'bg-blue-100 text-blue-700'
                      }`}
                    >
                      {batch.batch_type === 'handwritten' ? 'Handwritten' : 'Synthetic'}
                    </span>
                  </p>
                  <p className="text-sm text-gray-600">
                    {batch.count} documents
                    {batch.skew_preset && ` • ${batch.skew_preset} skew`}
                  </p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-gray-600">No batches generated yet.</p>
        )}
      </div>
    </div>
  )
}

function ReferenceTemplatesSection() {
  const queryClient = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [templateName, setTemplateName] = useState('')
  const [templateDescription, setTemplateDescription] = useState('')
  const [templateFields, setTemplateFields] = useState([])
  const [newFieldName, setNewFieldName] = useState('')
  const [newFieldDesc, setNewFieldDesc] = useState('')

  const { data: templatesData } = useQuery({
    queryKey: ['reference-templates'],
    queryFn: () => referenceAPI.listTemplates(),
  })
  const templates = templatesData?.data || []

  const createMutation = useMutation({
    mutationFn: (data) => referenceAPI.createTemplate(data),
    onSuccess: () => {
      queryClient.invalidateQueries(['reference-templates'])
      resetForm()
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }) => referenceAPI.updateTemplate(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries(['reference-templates'])
      resetForm()
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id) => referenceAPI.deleteTemplate(id),
    onSuccess: () => queryClient.invalidateQueries(['reference-templates']),
  })

  const resetForm = () => {
    setShowCreate(false)
    setEditingId(null)
    setTemplateName('')
    setTemplateDescription('')
    setTemplateFields([])
    setNewFieldName('')
    setNewFieldDesc('')
  }

  const addField = () => {
    if (!newFieldName.trim()) return
    setTemplateFields([...templateFields, { field_name: newFieldName.trim(), description: newFieldDesc.trim() }])
    setNewFieldName('')
    setNewFieldDesc('')
  }

  const startEdit = (template) => {
    setEditingId(template.id)
    setTemplateName(template.name)
    setTemplateDescription(template.form_type_description || '')
    setTemplateFields(template.fields || [])
    setShowCreate(true)
  }

  const handleSave = () => {
    const data = {
      name: templateName,
      form_type_description: templateDescription,
      fields: templateFields,
    }
    if (editingId) {
      updateMutation.mutate({ id: editingId, data })
    } else {
      createMutation.mutate(data)
    }
  }

  return (
    <div className="mt-8 bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">Reference Data Templates</h3>
        <button
          onClick={() => { resetForm(); setShowCreate(true) }}
          className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
        >
          Create Template
        </button>
      </div>

      {/* Template List */}
      {templates.length > 0 ? (
        <div className="space-y-2 mb-4">
          {templates.map((t) => (
            <div key={t.id} className="flex items-center justify-between p-3 bg-gray-50 rounded">
              <div>
                <span className="font-medium text-sm">{t.name}</span>
                {t.form_type_description && (
                  <span className="ml-2 text-xs text-gray-500">{t.form_type_description}</span>
                )}
                <span className="ml-2 text-xs text-gray-400">{t.fields?.length || 0} fields</span>
              </div>
              <div className="flex gap-2">
                <button onClick={() => startEdit(t)} className="text-xs text-blue-600 hover:underline">Edit</button>
                <button onClick={() => deleteMutation.mutate(t.id)} className="text-xs text-red-600 hover:underline">Delete</button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-gray-500 mb-4">No templates yet.</p>
      )}

      {/* Create/Edit Form */}
      {showCreate && (
        <div className="border rounded-lg p-4 bg-blue-50">
          <h4 className="font-medium mb-3">{editingId ? 'Edit Template' : 'Create Template'}</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Template Name</label>
              <input
                type="text"
                value={templateName}
                onChange={(e) => setTemplateName(e.target.value)}
                className="w-full px-3 py-2 border rounded text-sm"
                placeholder="e.g., Prisoner Registration Fields"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Form Type Description</label>
              <input
                type="text"
                value={templateDescription}
                onChange={(e) => setTemplateDescription(e.target.value)}
                className="w-full px-3 py-2 border rounded text-sm"
                placeholder="e.g., Prison intake form"
              />
            </div>
          </div>

          {/* Fields */}
          <div className="mb-3">
            <label className="block text-xs font-medium text-gray-600 mb-1">Fields ({templateFields.length})</label>
            {templateFields.length > 0 && (
              <div className="space-y-1 mb-2 max-h-40 overflow-y-auto">
                {templateFields.map((f, idx) => (
                  <div key={idx} className="flex items-center gap-2 text-xs bg-white px-2 py-1 rounded">
                    <span className="font-medium flex-1">{f.field_name}</span>
                    <span className="text-gray-400 flex-1 truncate">{f.description}</span>
                    <button onClick={() => setTemplateFields(prev => prev.filter((_, i) => i !== idx))} className="text-red-500">x</button>
                  </div>
                ))}
              </div>
            )}
            <div className="flex gap-2">
              <input
                type="text"
                value={newFieldName}
                onChange={(e) => setNewFieldName(e.target.value)}
                className="flex-1 px-2 py-1 border rounded text-sm"
                placeholder="Field name"
                onKeyDown={(e) => { if (e.key === 'Enter') addField() }}
              />
              <input
                type="text"
                value={newFieldDesc}
                onChange={(e) => setNewFieldDesc(e.target.value)}
                className="flex-1 px-2 py-1 border rounded text-sm"
                placeholder="Description (optional)"
                onKeyDown={(e) => { if (e.key === 'Enter') addField() }}
              />
              <button onClick={addField} className="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700">Add</button>
            </div>
          </div>

          <div className="flex gap-2">
            <button
              onClick={handleSave}
              disabled={!templateName || templateFields.length === 0 || createMutation.isPending || updateMutation.isPending}
              className="px-4 py-2 text-sm bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
            >
              {createMutation.isPending || updateMutation.isPending ? 'Saving...' : 'Save'}
            </button>
            <button onClick={resetForm} className="px-4 py-2 text-sm bg-gray-100 rounded hover:bg-gray-200">Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}


function UploadWithReferenceSection() {
  const queryClient = useQueryClient()
  const [selectedFormId, setSelectedFormId] = useState('')
  const [selectedTemplateId, setSelectedTemplateId] = useState('')
  const [docFiles, setDocFiles] = useState(null)
  const [referenceFile, setReferenceFile] = useState(null)

  const { data: formsData } = useQuery({
    queryKey: ['forms'],
    queryFn: () => formsAPI.list(),
  })

  const { data: templatesData } = useQuery({
    queryKey: ['reference-templates'],
    queryFn: () => referenceAPI.listTemplates(),
  })
  const templates = templatesData?.data || []

  const uploadMutation = useMutation({
    mutationFn: (formData) => syntheticAPI.uploadWithReference(formData),
    onSuccess: () => {
      queryClient.invalidateQueries(['batches'])
      setDocFiles(null)
      setReferenceFile(null)
      setSelectedFormId('')
      setSelectedTemplateId('')
    },
  })

  const handleUpload = () => {
    if (!docFiles || docFiles.length === 0 || !selectedFormId) return
    const formData = new FormData()
    for (const file of docFiles) {
      formData.append('files', file)
    }
    if (referenceFile) {
      formData.append('reference_file', referenceFile)
    }
    formData.append('form_id', selectedFormId)
    if (selectedTemplateId) {
      formData.append('reference_template_id', selectedTemplateId)
    }
    uploadMutation.mutate(formData)
  }

  return (
    <div className="mt-8 bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold mb-4">Upload Filled Forms with Reference Data</h3>
      <p className="text-sm text-gray-500 mb-4">
        Upload handwritten/filled form images alongside an Excel (.xlsx) or CSV file with the expected field values.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Form</label>
          <select
            value={selectedFormId}
            onChange={(e) => setSelectedFormId(e.target.value)}
            className="w-full px-3 py-2 border rounded-md text-sm"
          >
            <option value="">-- Select a form --</option>
            {formsData?.data?.forms?.map((form) => (
              <option key={form.id} value={form.id}>{form.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Reference Template (optional)</label>
          <select
            value={selectedTemplateId}
            onChange={(e) => setSelectedTemplateId(e.target.value)}
            className="w-full px-3 py-2 border rounded-md text-sm"
          >
            <option value="">-- None --</option>
            {templates.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Document Files (PDF/PNG)</label>
          <input
            type="file"
            multiple
            accept=".pdf,.png,.jpg,.jpeg,.tiff,.tif"
            onChange={(e) => setDocFiles(e.target.files)}
            className="w-full px-3 py-2 border rounded-md text-sm"
          />
          {docFiles && (
            <p className="text-xs text-gray-500 mt-1">{docFiles.length} file(s) selected</p>
          )}
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Reference Data (Excel/CSV)</label>
          <input
            type="file"
            accept=".xlsx,.csv"
            onChange={(e) => setReferenceFile(e.target.files?.[0] || null)}
            className="w-full px-3 py-2 border rounded-md text-sm"
          />
          <p className="text-xs text-gray-500 mt-1">
            Columns: field_name | raw_value | resolved_value
          </p>
        </div>
      </div>

      <button
        onClick={handleUpload}
        disabled={!docFiles || docFiles.length === 0 || !selectedFormId || uploadMutation.isPending}
        className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
      >
        {uploadMutation.isPending ? 'Uploading...' : 'Upload'}
      </button>

      {uploadMutation.isError && (
        <p className="text-red-600 text-sm mt-2">
          {uploadMutation.error?.response?.data?.detail || 'Upload failed'}
        </p>
      )}
      {uploadMutation.isSuccess && (
        <p className="text-green-600 text-sm mt-2">Upload successful!</p>
      )}
    </div>
  )
}


export default SyntheticDataPage
