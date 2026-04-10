import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

// Create axios instance
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor to handle auth errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// Auth API
export const authAPI = {
  login: (email, password) =>
    api.post('/auth/login', { email, password }),
  logout: () =>
    api.post('/auth/logout'),
  getMe: () =>
    api.get('/auth/me'),
}

// Forms API
export const formsAPI = {
  list: () =>
    api.get('/forms'),
  get: (id) =>
    api.get(`/forms/${id}`),
  upload: (formData) =>
    api.post('/forms', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  updateFields: (id, fieldMappings) =>
    api.put(`/forms/${id}/fields`, { field_mappings: fieldMappings }),
  delete: (id) =>
    api.delete(`/forms/${id}`),
  getImage: (id, page = 0) =>
    api.get(`/forms/${id}/image`, { params: { page }, responseType: 'blob' }).then(response => {
      // Handle both blob (PDF->PNG) and JSON (signed URL) responses
      if (response.data instanceof Blob) {
        const url = URL.createObjectURL(response.data)
        return { data: { url } }
      }
      return response
    }).catch(() => {
      // Fallback: try without blob responseType (for signed URLs)
      return api.get(`/forms/${id}/image`, { params: { page } })
    }),
  exportConfig: (id) =>
    api.get(`/forms/${id}/config`),
  importConfig: (id, fields) =>
    api.put(`/forms/${id}/config`, { fields }),
  getTemplateWords: (id) =>
    api.get(`/forms/${id}/template-words`),
  updateTemplateWords: (id, words) =>
    api.put(`/forms/${id}/template-words`, { template_words: words }),
  download: (id, name) =>
    api.get(`/forms/${id}/download`, { responseType: 'blob' }).then((response) => {
      const url = URL.createObjectURL(response.data)
      const a = document.createElement('a')
      a.href = url
      a.download = name || 'form'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    }),
}

// Synthetic Data API
export const syntheticAPI = {
  generate: (formId, count, fieldValueOptions = null, skewPreset = null) =>
    api.post('/synthetic/generate', {
      form_id: formId,
      count,
      field_value_options: fieldValueOptions,
      skew_preset: skewPreset,
    }),
  listBatches: () =>
    api.get('/synthetic/batches'),
  getBatch: (id) =>
    api.get(`/synthetic/batches/${id}`),
  getDocumentImage: (batchId, documentId, page = 0) =>
    api.get(`/synthetic/batches/${batchId}/documents/${documentId}/image`, {
      params: { page },
      responseType: 'blob',
    }).then((response) => {
      const url = URL.createObjectURL(response.data)
      return url
    }),
  mergeBatches: (sourceBatchIds) =>
    api.post('/synthetic/batches/merge', { source_batch_ids: sourceBatchIds }),
  removeDocuments: (batchId, documentIds) =>
    api.post(`/synthetic/batches/${batchId}/remove-documents`, { document_ids: documentIds }),
  appendDocuments: (targetBatchId, sourceBatchId, documentIds) =>
    api.post(`/synthetic/batches/${targetBatchId}/append`, { source_batch_id: sourceBatchId, document_ids: documentIds }),
  deleteBatch: (batchId) =>
    api.delete(`/synthetic/batches/${batchId}`),
  uploadWithReference: (formData) =>
    api.post('/synthetic/upload-with-reference', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
}

// Prompts API
export const promptsAPI = {
  list: (type) => api.get('/prompts', { params: type ? { prompt_type: type } : {} }),
  get: (id) => api.get(`/prompts/${id}`),
  create: (data) => api.post('/prompts', data),
  update: (id, data) => api.put(`/prompts/${id}`, data),
  delete: (id) => api.delete(`/prompts/${id}`),
  getDefaults: () => api.get('/prompts/defaults'),
}

// Reference Data API
export const referenceAPI = {
  listTemplates: () => api.get('/reference/templates'),
  getTemplate: (id) => api.get(`/reference/templates/${id}`),
  createTemplate: (data) => api.post('/reference/templates', data),
  updateTemplate: (id, data) => api.put(`/reference/templates/${id}`, data),
  deleteTemplate: (id) => api.delete(`/reference/templates/${id}`),
  getBatchRef: (batchId) => api.get(`/reference/batches/${batchId}`),
  getDocumentRef: (batchId, docId) => api.get(`/reference/batches/${batchId}/documents/${docId}`),
  updateDocumentRef: (batchId, docId, data) => api.put(`/reference/batches/${batchId}/documents/${docId}`, data),
  uploadBatchRef: (batchId, formData) =>
    api.post(`/reference/batches/${batchId}/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  downloadTemplate: (templateName) =>
    api.get(`/reference/templates/download/${templateName}`, { responseType: 'blob' }).then((response) => {
      const url = URL.createObjectURL(response.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `${templateName}_reference_template.xlsx`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    }),
}

// Tests API
export const testsAPI = {
  run: (batchIds, layoutLibrary, ocrLibrary, ocrPromptId = null, classifierModel = null, classificationPromptId = null, fieldTypes = null, judgeModel = null, judgePromptId = null) =>
    api.post('/tests/run', {
      batch_ids: batchIds,
      layout_library: layoutLibrary,
      ocr_library: ocrLibrary,
      ocr_prompt_id: ocrPromptId,
      classifier_model: classifierModel,
      classification_prompt_id: classificationPromptId,
      field_types: fieldTypes,
      judge_model: judgeModel,
      judge_prompt_id: judgePromptId,
    }),
  runBatchJob: (batchIds, layoutLibraries, ocrLibraries, ocrPromptId = null, classifierModels = null, classificationPromptId = null, fieldTypes = null, judgeModel = null, judgePromptId = null) =>
    api.post('/tests/batch-job', {
      batch_ids: batchIds,
      layout_libraries: layoutLibraries,
      ocr_libraries: ocrLibraries,
      ocr_prompt_id: ocrPromptId,
      classifier_models: classifierModels,
      classification_prompt_id: classificationPromptId,
      field_types: fieldTypes,
      judge_model: judgeModel,
      judge_prompt_id: judgePromptId,
    }),
  listBatchJobs: () =>
    api.get('/tests/batch-jobs'),
  getBatchJob: (id) =>
    api.get(`/tests/batch-jobs/${id}`),
  cancelBatchJob: (id) =>
    api.post(`/tests/batch-jobs/${id}/cancel`),
  list: () =>
    api.get('/tests'),
  get: (id) =>
    api.get(`/tests/${id}`),
  getStatus: (id) =>
    api.get(`/tests/${id}/status`),
  getLibraries: () =>
    api.get('/tests/options/libraries'),
  cancel: (id) =>
    api.post(`/tests/${id}/cancel`),
}

// Results API
export const resultsAPI = {
  list: (testRunId, batchId = null) => {
    let url = `/results?test_run_id=${testRunId}`
    if (batchId) url += `&batch_id=${batchId}`
    return api.get(url)
  },
  getForTestRun: (testRunId) =>
    api.get(`/results/${testRunId}`),
  getDocument: (testRunId, documentId) =>
    api.get(`/results/${testRunId}/document/${documentId}`),
  getDocumentImage: (testRunId, documentId, page = 0) =>
    api.get(`/results/${testRunId}/document/${documentId}/image`, {
      params: { page },
      responseType: 'blob',
    }).then((response) => {
      const url = URL.createObjectURL(response.data)
      return url
    }),
  getSummary: (testRunId) =>
    api.get(`/results/${testRunId}/summary`),
}

// Verification API
export const verificationAPI = {
  getDocuments: (testRunId) =>
    api.get(`/verify/${testRunId}/documents`),
  getDocument: (testRunId, documentId) =>
    api.get(`/verify/${testRunId}/document/${documentId}`),
  getDocumentImage: (testRunId, documentId, page = 0) =>
    api.get(`/verify/${testRunId}/document/${documentId}/image`, {
      params: { page },
      responseType: 'blob',
    }).then((response) => {
      const url = URL.createObjectURL(response.data)
      return url
    }),
  verifyDocument: (testRunId, documentId, fields, textRegions = null, addedRegions = null) => {
    const body = { fields }
    if (textRegions) body.text_regions = textRegions
    if (addedRegions) body.added_regions = addedRegions
    return api.put(`/verify/${testRunId}/document/${documentId}/verify`, body)
  },
  getSummary: (testRunId) =>
    api.get(`/verify/${testRunId}/summary`),
}

// Metrics API
export const metricsAPI = {
  getMatrix: () =>
    api.get('/metrics/matrix'),
  getAggregate: () =>
    api.get('/metrics/aggregate'),
  getByField: () =>
    api.get('/metrics/by-field'),
  getComparison: (testRunIds) =>
    api.get('/metrics/comparison', { params: { test_run_ids: testRunIds } }),
  getClassificationMatrix: () =>
    api.get('/metrics/classification-matrix'),
  export: (format = 'csv', testRunId = null) => {
    let url = `/metrics/export?format=${format}`
    if (testRunId) url += `&test_run_id=${testRunId}`
    return api.get(url, { responseType: format === 'csv' ? 'blob' : 'json' })
  },
}

// Cleaning API
export const cleaningAPI = {
  preview: (data) =>
    api.post('/clean/preview', data),
  save: (testRunId, data) =>
    api.put(`/clean/${testRunId}/save`, data),
  status: (testRunId) =>
    api.get(`/clean/${testRunId}/status`),
}

// Classification API
export const classifyAPI = {
  getDocuments: (testRunId) =>
    api.get(`/classify/${testRunId}/documents`),
  getDocument: (testRunId, documentId) =>
    api.get(`/classify/${testRunId}/document/${documentId}`),
  getDocumentImage: (testRunId, documentId, page = 0) =>
    api.get(`/classify/${testRunId}/document/${documentId}/image`, {
      params: { page },
      responseType: 'blob',
    }).then((response) => {
      const url = URL.createObjectURL(response.data)
      return url
    }),
  run: (testRunId, documentId, data) =>
    api.post(`/classify/${testRunId}/document/${documentId}/run`, data),
  save: (testRunId, documentId, data) =>
    api.put(`/classify/${testRunId}/document/${documentId}/save`, data),
}

// Classification Verification API
export const classifyVerifyAPI = {
  getDocuments: (testRunId) =>
    api.get(`/classify-verify/${testRunId}/documents`),
  getDocument: (testRunId, documentId) =>
    api.get(`/classify-verify/${testRunId}/document/${documentId}`),
  getDocumentImage: (testRunId, documentId, page = 0) =>
    api.get(`/classify-verify/${testRunId}/document/${documentId}/image`, {
      params: { page },
      responseType: 'blob',
    }).then((response) => {
      const url = URL.createObjectURL(response.data)
      return url
    }),
  verify: (testRunId, documentId, data) =>
    api.put(`/classify-verify/${testRunId}/document/${documentId}/verify`, data),
  getSummary: (testRunId) =>
    api.get(`/classify-verify/${testRunId}/summary`),
}

// Health check
export const healthAPI = {
  check: () =>
    api.get('/health'),
  info: () =>
    api.get('/info'),
}

export default api
