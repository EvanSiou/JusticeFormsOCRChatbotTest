import axios from 'axios'

const API_BASE_URL = 'https://ocr-app-backend-206256614025.us-central1.run.app/api'

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
  getImage: (id) =>
    api.get(`/forms/${id}/image`, { responseType: 'blob' }).then(response => {
      // Handle both blob (PDF->PNG) and JSON (signed URL) responses
      if (response.data instanceof Blob) {
        const url = URL.createObjectURL(response.data)
        return { data: { url } }
      }
      return response
    }).catch(() => {
      // Fallback: try without blob responseType (for signed URLs)
      return api.get(`/forms/${id}/image`)
    }),
  exportConfig: (id) =>
    api.get(`/forms/${id}/config`),
  importConfig: (id, fields) =>
    api.put(`/forms/${id}/config`, { fields }),
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
  getDocumentImage: (batchId, documentId) =>
    api.get(`/synthetic/batches/${batchId}/documents/${documentId}/image`, {
      responseType: 'blob',
    }).then((response) => {
      const url = URL.createObjectURL(response.data)
      return url
    }),
}

// Tests API
export const testsAPI = {
  run: (batchIds, layoutLibrary, ocrLibrary) =>
    api.post('/tests/run', {
      batch_ids: batchIds,
      layout_library: layoutLibrary,
      ocr_library: ocrLibrary,
    }),
  runBatchJob: (batchIds, layoutLibraries, ocrLibraries) =>
    api.post('/tests/batch-job', {
      batch_ids: batchIds,
      layout_libraries: layoutLibraries,
      ocr_libraries: ocrLibraries,
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
  getDocumentImage: (testRunId, documentId) =>
    api.get(`/results/${testRunId}/document/${documentId}/image`, {
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
  getDocumentImage: (testRunId, documentId) =>
    api.get(`/verify/${testRunId}/document/${documentId}/image`, {
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
  export: (format = 'csv', testRunId = null) => {
    let url = `/metrics/export?format=${format}`
    if (testRunId) url += `&test_run_id=${testRunId}`
    return api.get(url, { responseType: format === 'csv' ? 'blob' : 'json' })
  },
}

// Health check
export const healthAPI = {
  check: () =>
    api.get('/health'),
  info: () =>
    api.get('/info'),
}

export default api
