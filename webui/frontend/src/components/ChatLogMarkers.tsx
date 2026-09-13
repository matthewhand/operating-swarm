export function ChatGapLabel({ label }: { label: string }) {
  return (
    <div className="os-chat-gap" role="separator" aria-label={label}>
      {label}
    </div>
  )
}

export function ChatNewRule() {
  return (
    <div
      className="os-chat-new"
      role="separator"
      aria-label="New"
      data-testid="chat-new-divider"
    >
      <span className="os-chat-new__rule" aria-hidden="true" />
      <span className="os-chat-new__label">New</span>
      <span className="os-chat-new__rule" aria-hidden="true" />
    </div>
  )
}
