import { DEMO_SCENARIOS, TOUR_PROMPT } from '../lib/demo/scenarios'

export function DemoTourBanner({
  disabled = false,
  compact = false,
  onChoose,
}: {
  disabled?: boolean
  compact?: boolean
  onChoose: (prompt: string) => void
}) {
  return (
    <div
      className={
        compact
          ? 'os-demo-tour os-demo-tour--compact px-3 py-2 space-y-2'
          : 'os-demo-tour px-3 py-3 space-y-2'
      }
      data-testid="demo-tour-banner"
      role="region"
      aria-label="Operating Swarm demo scenarios"
    >
      <div className="os-demo-tour__intro">
        <p className="font-medium text-sm">Demo mode</p>
        <p className="text-xs text-base-content/70">
          Explore Operating Swarm with mocked inference — no paid LLM, no local shells.
        </p>
      </div>
      <div className="os-demo-tour__cards flex flex-wrap gap-2" data-testid="demo-scenario-cards">
        {DEMO_SCENARIOS.filter((row) => row.id !== 'tour').map((row) => (
          <button
            key={row.id}
            type="button"
            className="btn btn-soft btn-sm"
            disabled={disabled}
            data-testid="demo-scenario-card"
            data-demo-scenario={row.id}
            onClick={() => {
              if (disabled) return
              onChoose(row.prompt)
            }}
          >
            {row.title}
          </button>
        ))}
        <button
          type="button"
          className="btn btn-primary btn-sm"
          disabled={disabled}
          data-testid="demo-play-tour"
          onClick={() => {
            if (disabled) return
            onChoose(TOUR_PROMPT)
          }}
        >
          Play guided tour
        </button>
      </div>
    </div>
  )
}

export default DemoTourBanner
