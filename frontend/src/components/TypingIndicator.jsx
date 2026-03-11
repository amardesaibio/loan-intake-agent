export default function TypingIndicator() {
  return (
    <div className="flex items-end gap-2 mb-4">
      <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center flex-shrink-0 shadow-sm">
        <span className="text-white text-sm font-bold select-none">A</span>
      </div>
      <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
        <div className="flex gap-1 items-center h-4">
          <div className="typing-dot w-2 h-2 rounded-full bg-gray-400" />
          <div className="typing-dot w-2 h-2 rounded-full bg-gray-400" />
          <div className="typing-dot w-2 h-2 rounded-full bg-gray-400" />
        </div>
      </div>
    </div>
  )
}
