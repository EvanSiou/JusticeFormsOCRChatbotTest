import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

const api = axios.create({
  baseURL: API_BASE,
})

// Processing endpoints
export const processingAPI = {
  upload: (formData) =>
    api.post('/processing/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  qualityDetect: (sessionId) =>
    api.post(`/processing/${sessionId}/quality-detect`),
  autoCorrect: (sessionId) =>
    api.post(`/processing/${sessionId}/auto-correct`),
  qualityGate: (sessionId) =>
    api.post(`/processing/${sessionId}/quality-gate`),
  qualityGateProceed: (sessionId) =>
    api.post(`/processing/${sessionId}/quality-gate/proceed`),
  detectForm: (sessionId) =>
    api.post(`/processing/${sessionId}/detect-form`),
  ocrClassify: (sessionId) =>
    api.post(`/processing/${sessionId}/ocr-classify`),
  getResults: (sessionId) =>
    api.get(`/processing/${sessionId}/results`),
  validateBias: (sessionId) =>
    api.post(`/processing/${sessionId}/validate-bias`),
  updateField: (sessionId, fieldIdx, value) =>
    api.post(`/processing/${sessionId}/field/${fieldIdx}`, { value }),
  complete: (sessionId) =>
    api.post(`/processing/${sessionId}/complete`),
  getStatus: (sessionId) =>
    api.get(`/processing/${sessionId}/status`),
  getPageImage: (sessionId, pageNum, corrected = false) =>
    api.get(`/processing/${sessionId}/page/${pageNum}/image`, {
      params: { corrected },
      responseType: 'blob',
    }),
}

// Setup endpoints
export const setupAPI = {
  getConfig: () => api.get('/setup/config'),
  updateConfig: (config) => api.put('/setup/config', config),
  listPrompts: () => api.get('/setup/prompts'),
  getPrompt: (id) => api.get(`/setup/prompts/${id}`),
  createPrompt: (prompt) => api.post('/setup/prompts', prompt),
  updatePrompt: (id, prompt) => api.put(`/setup/prompts/${id}`, prompt),
  deletePrompt: (id) => api.delete(`/setup/prompts/${id}`),
  listModels: () => api.get('/setup/models'),
  getSystemPrompts: () => api.get('/setup/system-prompts'),
  listFormTypes: () => api.get('/setup/form-types'),
  createFormType: (formType) => api.post('/setup/form-types', formType),
  deleteFormType: (id) => api.delete(`/setup/form-types/${id}`),
}

export default api
