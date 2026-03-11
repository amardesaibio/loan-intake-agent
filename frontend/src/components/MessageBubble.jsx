import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export default function MessageBubble({ message, isStreaming }) {
  const { role, content, reference } = message

  // System / status messages — centred amber box
  if (role === 'system') {
    return (
      <div className="flex justify-center my-3">
        <div className="bg-amber-50 border border-amber-200 text-amber-800 text-sm px-4 py-2.5 rounded-xl max-w-sm text-center">
          {content}
          {reference && (
            <div className="text-xs text-amber-600 mt-1 font-mono">
              Ref: {reference}
            </div>
          )}
        </div>
      </div>
    )
  }

  const isUser = role === 'user'

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-4 items-end gap-2`}>
      {/* AI avatar */}
      {!isUser && (
        <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center flex-shrink-0 mb-0.5 shadow-sm">
          <span className="text-white text-sm font-bold select-none">A</span>
        </div>
      )}

      {/* Bubble */}
      <div
        className={`
          max-w-[75%] px-4 py-3 rounded-2xl text-sm leading-relaxed
          ${isUser
            ? 'bg-blue-600 text-white rounded-br-sm'
            : 'bg-white border border-gray-200 text-gray-800 rounded-bl-sm shadow-sm'
          }
          ${isStreaming ? 'streaming-cursor' : ''}
        `}
      >
        {isUser
          ? content
          : (
            <div className="ai-message">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {content}
              </ReactMarkdown>
            </div>
          )
        }
      </div>

      {/* User avatar */}
      {isUser && (
        <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center flex-shrink-0 mb-0.5">
          <span className="text-gray-500 text-sm select-none">👤</span>
        </div>
      )}
    </div>
  )
}
