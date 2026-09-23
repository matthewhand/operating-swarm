/**
 * REQ-861: theme-aware Open Swarm geometric mark (`currentColor`).
 * Geometry matches `assets/brand/webui-geometric-mono.svg`.
 */
export function BrandMarkMono({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 64 64"
      className={`os-brand-mark-geometric ${className}`}
      fill="currentColor"
      aria-hidden="true"
    >
      <g fill="currentColor" transform="rotate(-38 32 33)">
        <path d="M18 18 C8 8 4 22 16 28 C20 24 22 20 18 18 Z" />
        <path d="M22 14 C16 2 6 10 18 22 C24 18 26 16 22 14 Z" />
        <path d="M32 55.6 L28.6 50.2 H35.4 Z" />
        <ellipse cx="32" cy="38.2" rx="10.4" ry="15.6" />
        <ellipse cx="32" cy="22.2" rx="7.6" ry="7.1" />
        <circle cx="32" cy="12.6" r="5.4" />
        <circle cx="20.4" cy="2.4" r="1.35" />
        <circle cx="43.6" cy="2.4" r="1.35" />
        <g fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
          <path d="M29.6 8.2 C27.2 3.6 23.6 1.8 20.4 2.4" />
          <path d="M34.4 8.2 C36.8 3.6 40.4 1.8 43.6 2.4" />
        </g>
      </g>
    </svg>
  )
}

export default BrandMarkMono
