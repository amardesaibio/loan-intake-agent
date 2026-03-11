import { useState, useCallback, useRef } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

// The same welcome message the backend would send when messages == [].
// We display it immediately on the frontend so the user sees it without
// having to send a first message.
const WELCOME_MSG = `Hi there! 👋 I'm Alex, your personal loan advisor at First Digital Bank.

I'll guide you through our simple loan application — it takes about 10 minutes and I'll be with you every step of the way.

Before we begin, I need your consent to collect and process your personal and financial information to evaluate your loan application. This includes a soft credit check which **won't affect your credit score**.

Do you agree to proceed? (yes / no)`

/**
 * Strip qwen3 / DeepSeek-style <think>...</think> blocks from LLM output.
 * react-markdown drops raw HTML silently, leaving empty bubbles when the
 * entire response is wrapped in a think block.
 */
function stripThinkTags(text) {
  return text.replace(/<think>[\s\S]*?<\/think>/gi, '').trim()
}

/**
 * Parse a raw SSE chunk string into an array of { type, data } events.
 * Handles partial chunks by working on already-split blocks.
 */
function parseSSEBlock(block) {
  const lines = block.split('\n')
  let eventType = 'message'
  let data = ''
  for (const line of lines) {
    if (line.startsWith('event: ')) eventType = line.slice(7).trim()
    else if (line.startsWith('data: '))  data      = line.slice(6).trim()
  }
  if (!data) return null
  try {
    return { type: eventType, data: JSON.parse(data) }
  } catch {
    return null
  }
}

export function useChat() {
  const [sessionId,       setSessionId]       = useState(null)
  const [messages,        setMessages]        = useState([])
  const [streamingContent,setStreamingContent]= useState('')
  const [isStreaming,     setIsStreaming]      = useState(false)
  const [isStarting,      setIsStarting]      = useState(false)

  const [stage,      setStage]      = useState('welcome')
  const [stageLabel, setStageLabel] = useState('Welcome & Consent')
  const [progress,   setProgress]   = useState(0)

  const [decision,     setDecision]     = useState(null)   // { outcome, details }
  const [signingUrl,   setSigningUrl]   = useState(null)
  const [humanHandoff, setHumanHandoff] = useState(false)
  const [toolCalling,  setToolCalling]  = useState(null)
  const [error,        setError]        = useState(null)

  // Ref so the streaming content value is always current inside the async loop
  const streamingRef = useRef('')

  // ── Start / resume session ──────────────────────────────────
  const startSession = useCallback(async () => {
    setIsStarting(true)
    try {
      const saved = localStorage.getItem('loan_session_id')
      const res = await fetch(`${API_BASE}/chat/session/start`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ session_id: saved || undefined }),
      })
      if (!res.ok) throw new Error('Failed to start session')
      const data = await res.json()
      const sid  = data.session_id
      setSessionId(sid)
      localStorage.setItem('loan_session_id', sid)
      setStage(data.stage      || 'welcome')
      setStageLabel(data.stage_label || 'Welcome & Consent')

      if (data.resumed) {
        // Restore chat history
        const [histRes, statusRes] = await Promise.all([
          fetch(`${API_BASE}/chat/history/${sid}`),
          fetch(`${API_BASE}/chat/session/${sid}`),
        ])
        const histData   = await histRes.json()
        const statusData = await statusRes.json()

        const msgs = (histData.messages || []).map((m, i) => ({
          id:      `hist-${i}`,
          role:    m.role,
          content: m.role === 'assistant' ? stripThinkTags(m.content) : m.content,
        })).filter(m => m.content)   // drop any that are empty after stripping
        setMessages(msgs)
        setStage(statusData.current_stage || 'welcome')
        setStageLabel(statusData.stage_label || 'Welcome & Consent')
        setProgress(statusData.progress_pct || 0)
        if (statusData.decision_outcome) setDecision({ outcome: statusData.decision_outcome })
        if (statusData.human_handoff)    setHumanHandoff(true)
      } else {
        // New session — show the welcome message immediately without waiting
        // for a user message (the backend only sends it when messages == [],
        // which can't happen via the /message API).
        setMessages([{ id: 'welcome', role: 'assistant', content: WELCOME_MSG }])
      }
    } catch (err) {
      setError('Could not connect to the server. Please refresh.')
      console.error('startSession error:', err)
    } finally {
      setIsStarting(false)
    }
  }, [])

  // ── Send message + stream response ─────────────────────────
  const sendMessage = useCallback(async (message) => {
    if (!sessionId || isStreaming) return

    const userMsg = { id: `user-${Date.now()}`, role: 'user', content: message }
    setMessages(prev => [...prev, userMsg])
    setIsStreaming(true)
    setError(null)
    streamingRef.current = ''
    setStreamingContent('')
    setToolCalling(null)

    try {
      const res = await fetch(`${API_BASE}/chat/message`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ session_id: sessionId, message }),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `HTTP ${res.status}`)
      }

      const reader  = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer    = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // Process every complete SSE block (blocks are separated by \n\n)
        const parts = buffer.split('\n\n')
        buffer = parts.pop() // keep the incomplete tail

        for (const part of parts) {
          if (!part.trim()) continue
          const event = parseSSEBlock(part)
          if (!event) continue

          switch (event.type) {
            case 'token':
              streamingRef.current += event.data.text || ''
              // Strip think tags for display — complete <think>...</think> blocks
              // are removed; content inside an unclosed block stays visible until
              // the closing tag arrives, then disappears (acceptable streaming UX).
              setStreamingContent(stripThinkTags(streamingRef.current))
              break

            case 'stage_change':
              setStage(event.data.stage)
              setStageLabel(event.data.stage_label)
              setProgress(event.data.progress || 0)
              break

            case 'tool_call':
              setToolCalling(event.data.tool)
              // Auto-clear after 3 s
              setTimeout(() => setToolCalling(null), 3000)
              break

            case 'decision':
              setDecision({ outcome: event.data.outcome, details: event.data.details })
              break

            case 'signing_url':
              setSigningUrl(event.data.url)
              break

            case 'human_handoff':
              setHumanHandoff(true)
              break

            case 'message_end': {
              // A chained node is about to start — commit the current bubble
              const completed = stripThinkTags(streamingRef.current)
              if (completed) {
                setMessages(prev => [
                  ...prev,
                  { id: `ai-${Date.now()}`, role: 'assistant', content: completed },
                ])
              }
              streamingRef.current = ''
              setStreamingContent('')
              break
            }

            case 'done': {
              const final = stripThinkTags(streamingRef.current)
              if (final) {
                setMessages(prev => [
                  ...prev,
                  { id: `ai-${Date.now()}`, role: 'assistant', content: final },
                ])
              }
              streamingRef.current = ''
              setStreamingContent('')
              break
            }

            case 'error':
              setError(event.data.message || 'Something went wrong. Please try again.')
              break

            default:
              break
          }
        }
      }
    } catch (err) {
      setError(err.message || 'Connection error. Please try again.')
      console.error('sendMessage error:', err)
    } finally {
      // If we exited without a 'done' event, flush whatever was streaming
      const remaining = stripThinkTags(streamingRef.current)
      if (remaining) {
        setMessages(prev => [
          ...prev,
          { id: `ai-${Date.now()}`, role: 'assistant', content: remaining },
        ])
      }
      streamingRef.current = ''
      setStreamingContent('')
      setIsStreaming(false)
    }
  }, [sessionId, isStreaming])

  // ── Request human handoff ───────────────────────────────────
  const requestHandoff = useCallback(async (reason = 'Customer requested human assistance') => {
    if (!sessionId) return
    try {
      const res  = await fetch(`${API_BASE}/chat/handoff`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ session_id: sessionId, reason }),
      })
      const data = await res.json()
      setHumanHandoff(true)
      setMessages(prev => [
        ...prev,
        {
          id:        `system-${Date.now()}`,
          role:      'system',
          content:   data.message || 'A loan specialist will contact you shortly.',
          reference: data.reference,
        },
      ])
    } catch (err) {
      console.error('handoff error:', err)
    }
  }, [sessionId])

  // ── Reset / start over ──────────────────────────────────────
  const resetSession = useCallback(() => {
    localStorage.removeItem('loan_session_id')
    setSessionId(null)
    setMessages([])
    setStreamingContent('')
    streamingRef.current = ''
    setStage('welcome')
    setStageLabel('Welcome & Consent')
    setProgress(0)
    setDecision(null)
    setSigningUrl(null)
    setHumanHandoff(false)
    setToolCalling(null)
    setError(null)
    // Re-start a fresh session
    // (App.jsx will call startSession again via useEffect on sessionId change)
  }, [])

  return {
    sessionId,
    messages,
    streamingContent,
    isStreaming,
    isStarting,
    stage,
    stageLabel,
    progress,
    decision,
    signingUrl,
    humanHandoff,
    toolCalling,
    error,
    startSession,
    sendMessage,
    requestHandoff,
    resetSession,
  }
}
