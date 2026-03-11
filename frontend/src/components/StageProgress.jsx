const STAGES = [
  { key: 'welcome',         label: 'Welcome & Consent'    },
  { key: 'gathering',       label: 'Information Gathering'},
  { key: 'document_upload', label: 'Documents'            },
  { key: 'review',          label: 'Review & Confirm'     },
  { key: 'credit_check',    label: 'Credit Check'         },
  { key: 'decision',        label: 'Decision'             },
  { key: 'signing',         label: 'Sign Agreement'       },
  { key: 'onboarding',      label: 'Onboarding'           },
]

export default function StageProgress({ stage }) {
  const activeIdx = STAGES.findIndex(s => s.key === stage)

  return (
    <div className="flex flex-col gap-0.5">
      {STAGES.map((s, i) => {
        const isComplete = i < activeIdx
        const isCurrent  = i === activeIdx
        const isFuture   = i > activeIdx

        return (
          <div
            key={s.key}
            className={`flex items-center gap-2.5 px-3 py-2 rounded-lg transition-all duration-200
              ${isCurrent  ? 'bg-blue-600/80'  : ''}
              ${isComplete ? 'opacity-80'       : ''}
              ${isFuture   ? 'opacity-40'       : ''}
            `}
          >
            {/* Stage indicator */}
            <div
              className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold
                ${isComplete ? 'bg-emerald-400 text-white'     : ''}
                ${isCurrent  ? 'bg-white text-blue-700'        : ''}
                ${isFuture   ? 'bg-blue-800/50 text-blue-400'  : ''}
              `}
            >
              {isComplete ? '✓' : i + 1}
            </div>

            <span className={`text-xs truncate
              ${isCurrent  ? 'text-white font-semibold' : ''}
              ${isComplete ? 'text-blue-200'            : ''}
              ${isFuture   ? 'text-blue-400'            : ''}
            `}>
              {s.label}
            </span>
          </div>
        )
      })}
    </div>
  )
}
