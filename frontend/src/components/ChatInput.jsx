import { useState, useRef, useCallback } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

const DOC_TYPES = [
  { value: 'paystub',    label: 'Pay Stub'    },
  { value: 'tax_return', label: 'Tax Return'  },
]

export default function ChatInput({ onSend, onHandoff, disabled, humanHandoff, stage, sessionId }) {
  const [text, setText]           = useState('')
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState(null)
  const textareaRef = useRef(null)
  const fileRefs    = { paystub: useRef(null), tax_return: useRef(null) }

  const handleSubmit = useCallback((e) => {
    e?.preventDefault()
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setText('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }, [text, disabled, onSend])

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit() }
  }

  const handleChange = (e) => {
    setText(e.target.value)
    const ta = e.target
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 120) + 'px'
  }

  const handleFileChange = async (e, docType) => {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ''   // reset so same file can be re-selected if needed

    setUploading(true)
    setUploadError(null)
    try {
      const form = new FormData()
      form.append('session_id',    sessionId)
      form.append('document_type', docType)
      form.append('file',          file)

      const res = await fetch(`${API_BASE}/upload/document`, { method: 'POST', body: form })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `Upload failed (${res.status})`)
      }
      const data = await res.json()
      const label = DOC_TYPES.find(d => d.value === docType)?.label || docType
      // Notify the agent so it can re-evaluate the document_upload stage
      onSend(`I've uploaded my ${label}: ${file.name}`)
    } catch (err) {
      setUploadError(err.message)
    } finally {
      setUploading(false)
    }
  }

  if (humanHandoff) {
    return (
      <div className="flex-shrink-0 p-4 bg-amber-50 border-t border-amber-200 text-center text-sm text-amber-700">
        This session has been transferred to a loan specialist. They will contact you shortly.
      </div>
    )
  }

  const showUpload = stage === 'document_upload' && sessionId

  return (
    <div className="flex-shrink-0 bg-white border-t border-gray-200">

      {/* Document upload bar (only shown during document_upload stage) */}
      {showUpload && (
        <div className="px-4 pt-3 pb-2 flex items-center gap-2 flex-wrap">
          <span className="text-xs text-gray-500 font-medium">Upload:</span>
          {DOC_TYPES.map(({ value, label }) => (
            <div key={value}>
              <input
                ref={fileRefs[value]}
                type="file"
                accept=".pdf,.jpg,.jpeg,.png,.webp"
                className="hidden"
                onChange={(e) => handleFileChange(e, value)}
                disabled={uploading || disabled}
              />
              <button
                type="button"
                onClick={() => fileRefs[value].current?.click()}
                disabled={uploading || disabled}
                className="
                  flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-blue-200
                  bg-blue-50 text-blue-700 text-xs font-medium
                  hover:bg-blue-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors
                "
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                </svg>
                {uploading ? 'Uploading…' : label}
              </button>
            </div>
          ))}
          {uploadError && (
            <span className="text-xs text-red-500 ml-1">{uploadError}</span>
          )}
        </div>
      )}

      {/* Text input */}
      <div className="p-4 pt-2">
        <form onSubmit={handleSubmit} className="flex items-end gap-3">
          <div className="flex-1">
            <textarea
              ref={textareaRef}
              value={text}
              onChange={handleChange}
              onKeyDown={handleKeyDown}
              placeholder="Type your message…"
              disabled={disabled}
              rows={1}
              className="
                w-full resize-none rounded-xl border border-gray-300 px-4 py-3 text-sm
                focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                disabled:bg-gray-50 disabled:text-gray-400 placeholder:text-gray-400
                transition-all
              "
              style={{ minHeight: '44px', maxHeight: '120px' }}
            />
          </div>

          <button
            type="submit"
            disabled={disabled || !text.trim()}
            className="
              flex-shrink-0 w-11 h-11 rounded-xl bg-blue-600 text-white
              flex items-center justify-center
              hover:bg-blue-700 active:scale-95
              disabled:opacity-40 disabled:cursor-not-allowed
              transition-all
            "
            aria-label="Send"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
          </button>
        </form>

        <div className="mt-2 flex justify-between items-center">
          <p className="text-xs text-gray-400">Enter to send · Shift+Enter for new line</p>
          <button
            type="button"
            onClick={onHandoff}
            className="text-xs text-blue-500 hover:text-blue-700 transition-colors"
          >
            Speak to a human agent
          </button>
        </div>
      </div>
    </div>
  )
}
