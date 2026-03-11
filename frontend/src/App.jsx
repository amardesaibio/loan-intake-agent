import { useEffect, useRef, useState } from 'react'
import { useChat } from './hooks/useChat'
import StageProgress   from './components/StageProgress'
import MessageBubble   from './components/MessageBubble'
import TypingIndicator from './components/TypingIndicator'
import ChatInput       from './components/ChatInput'

// ── Decision outcome badge shown in the header ────────────────
function DecisionBadge({ outcome }) {
  const styles = {
    auto_approve:      'bg-emerald-100 text-emerald-800 border-emerald-200',
    auto_decline:      'bg-red-100 text-red-800 border-red-200',
    refer_underwriter: 'bg-amber-100 text-amber-800 border-amber-200',
  }
  const labels = {
    auto_approve:      '✅ Approved',
    auto_decline:      '❌ Declined',
    refer_underwriter: '⏳ Under Review',
  }
  return (
    <span className={`border rounded-lg px-3 py-1.5 text-xs font-semibold ${styles[outcome] || 'bg-gray-100 text-gray-700 border-gray-200'}`}>
      {labels[outcome] || outcome}
    </span>
  )
}

// ── Human-handoff confirmation modal ─────────────────────────
function HandoffModal({ onConfirm, onCancel }) {
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 px-4">
      <div className="bg-white rounded-2xl p-6 max-w-sm w-full shadow-2xl">
        <h2 className="text-lg font-semibold text-gray-900 mb-2">Talk to a Specialist?</h2>
        <p className="text-gray-500 text-sm mb-5">
          A loan specialist will contact you within 2 business hours.
          Your application progress will be saved.
        </p>
        <div className="flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 px-4 py-2.5 border border-gray-300 rounded-xl text-gray-700 text-sm hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="flex-1 px-4 py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 transition-colors"
          >
            Connect me
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main App ──────────────────────────────────────────────────
export default function App() {
  const {
    sessionId, messages, streamingContent, isStreaming, isStarting,
    stage, stageLabel, progress,
    decision, signingUrl, humanHandoff, toolCalling, error,
    startSession, sendMessage, requestHandoff, resetSession,
  } = useChat()

  const messagesEndRef        = useRef(null)
  const [showHandoffModal, setShowHandoffModal] = useState(false)

  // Start session on mount; restart when sessionId is cleared (reset)
  useEffect(() => {
    if (!sessionId) startSession()
  }, [sessionId])

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent])

  const handleHandoffConfirm = () => {
    requestHandoff('Customer requested human assistance')
    setShowHandoffModal(false)
  }

  const onlineLabel = humanHandoff
    ? '🔴 Transferred to specialist'
    : isStreaming
    ? '⏳ Typing…'
    : '🟢 Online'

  return (
    <div className="flex h-screen bg-slate-100 font-sans overflow-hidden">

      {/* ── Sidebar ─────────────────────────────────────────── */}
      <aside className="w-64 flex-shrink-0 bg-gradient-to-b from-blue-950 to-blue-900 flex flex-col select-none">

        {/* Logo + current stage */}
        <div className="px-5 py-6 border-b border-blue-800/50">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-9 h-9 bg-white rounded-xl flex items-center justify-center shadow">
              <span className="text-blue-800 text-lg font-black">F</span>
            </div>
            <div>
              <div className="text-white font-bold text-sm leading-tight">First Digital</div>
              <div className="text-blue-300 text-xs">Bank & Trust</div>
            </div>
          </div>

          <div className="text-blue-400 text-xs font-medium uppercase tracking-wider mb-0.5">
            Current Step
          </div>
          <div className="text-white text-sm font-semibold leading-snug">{stageLabel}</div>
        </div>

        {/* Progress bar */}
        <div className="px-5 pt-4 pb-3">
          <div className="flex justify-between text-xs text-blue-400 mb-1.5">
            <span>Progress</span>
            <span>{progress}%</span>
          </div>
          <div className="h-1.5 bg-blue-800/60 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-400 rounded-full transition-all duration-500 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* Stage list */}
        <div className="flex-1 overflow-y-auto px-2 pb-2">
          <StageProgress stage={stage} />
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-blue-800/50">
          {sessionId && (
            <div className="text-blue-500 text-xs font-mono mb-2">
              Session: {sessionId.slice(0, 8).toUpperCase()}
            </div>
          )}
          <button
            onClick={resetSession}
            className="text-xs text-blue-400 hover:text-blue-200 transition-colors"
          >
            ↩ Start new application
          </button>
        </div>
      </aside>

      {/* ── Chat Area ───────────────────────────────────────── */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">

        {/* Header */}
        <header className="flex-shrink-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between gap-4">
          <div>
            <h1 className="text-gray-900 font-semibold text-base">Alex — Loan Advisor</h1>
            <p className="text-gray-400 text-xs mt-0.5">{onlineLabel}</p>
          </div>
          <div className="flex items-center gap-3 flex-shrink-0">
            {decision && <DecisionBadge outcome={decision.outcome} />}
          </div>
        </header>

        {/* Tool-call banner */}
        {toolCalling && (
          <div className="flex-shrink-0 bg-blue-50 border-b border-blue-100 px-6 py-2 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse inline-block" />
            <span className="text-blue-700 text-xs">Checking: {toolCalling}…</span>
          </div>
        )}

        {/* Error banner */}
        {error && (
          <div className="flex-shrink-0 bg-red-50 border-b border-red-100 px-6 py-2.5 flex items-center justify-between gap-4">
            <span className="text-red-600 text-xs">⚠️ {error}</span>
            <button onClick={() => {}} className="text-red-400 hover:text-red-600 text-xs underline">
              Dismiss
            </button>
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto chat-scroll px-6 py-6 bg-gray-50">

          {/* Loading state */}
          {isStarting && (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                <p className="text-gray-400 text-sm">Connecting…</p>
              </div>
            </div>
          )}

          {/* Chat history */}
          {messages.map(msg => (
            <MessageBubble key={msg.id} message={msg} />
          ))}

          {/* In-progress streaming message */}
          {streamingContent && (
            <MessageBubble
              message={{ id: 'streaming', role: 'assistant', content: streamingContent }}
              isStreaming
            />
          )}

          {/* Typing indicator (stream started but no tokens yet) */}
          {isStreaming && !streamingContent && <TypingIndicator />}

          {/* DocuSign signing button */}
          {signingUrl && (
            <div className="flex justify-center my-5">
              <a
                href={signingUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 bg-emerald-600 text-white px-6 py-3 rounded-xl font-medium shadow-sm hover:bg-emerald-700 transition-colors text-sm"
              >
                📝 Sign Your Loan Agreement
              </a>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input bar */}
        <ChatInput
          onSend={sendMessage}
          onHandoff={() => setShowHandoffModal(true)}
          disabled={isStreaming || isStarting || humanHandoff}
          humanHandoff={humanHandoff}
          stage={stage}
          sessionId={sessionId}
        />
      </main>

      {/* Human-handoff modal */}
      {showHandoffModal && (
        <HandoffModal
          onConfirm={handleHandoffConfirm}
          onCancel={() => setShowHandoffModal(false)}
        />
      )}
    </div>
  )
}
