import { useState, useRef } from 'react'

export default function FileUploader({ onUpload, uploading }) {
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef()

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) onUpload(file)
  }

  const handleSelect = (e) => {
    const file = e.target.files[0]
    if (file) onUpload(file)
  }

  return (
    <div
      className={`border-2 border-dashed rounded-xl p-16 text-center transition-colors cursor-pointer ${
        dragOver ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400'
      }`}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      onClick={() => fileRef.current?.click()}
    >
      <input
        ref={fileRef}
        type="file"
        accept=".pdf,.png,.jpg,.jpeg,.tiff"
        onChange={handleSelect}
        className="hidden"
      />
      {uploading ? (
        <div>
          <div className="animate-spin w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full mx-auto mb-4" />
          <p className="text-gray-600">Uploading and processing...</p>
        </div>
      ) : (
        <div>
          <svg className="w-12 h-12 text-gray-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
          <p className="text-lg font-medium text-gray-700 mb-1">
            Drop your document here
          </p>
          <p className="text-sm text-gray-500">
            PDF, PNG, JPG, or TIFF — multi-page supported
          </p>
        </div>
      )}
    </div>
  )
}
