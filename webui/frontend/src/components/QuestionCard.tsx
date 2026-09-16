import { useState, type FormEvent } from 'react'
import type { DecisionQuestion } from '../lib/decisionQuestion'

/**
 * User-answerable decision card: multiple-choice chips plus a last open-string.
 * Not a system pill — Support (or any agent) can receive the answer.
 */
export function QuestionCard({
  question,
  disabled = false,
  onChoose,
}: {
  question: DecisionQuestion
  disabled?: boolean
  onChoose: (value: string) => void
}) {
  const [other, setOther] = useState('')

  const submitOther = (event: FormEvent) => {
    event.preventDefault()
    const value = other.trim()
    if (!value || disabled) return
    onChoose(value)
    setOther('')
  }

  return (
    <div
      className={`os-question-card${disabled ? ' os-question-card--answered' : ''}`}
      role="radiogroup"
      aria-label={question.ask}
      data-testid="question-card"
      data-question-id={question.id}
    >
      <p className="os-question-ask">{question.ask}</p>
      <div className="os-question-choices">
        {question.choices.map((choice) => (
          <button
            key={choice}
            type="button"
            role="radio"
            aria-checked="false"
            className="os-question-choice"
            disabled={disabled}
            onClick={() => onChoose(choice)}
          >
            {choice}
          </button>
        ))}
      </div>
      <form className="os-question-other" onSubmit={submitOther}>
        <label className="sr-only" htmlFor={`os-q-other-${question.id}`}>
          {question.other}
        </label>
        <input
          id={`os-q-other-${question.id}`}
          type="text"
          className="os-question-other-input"
          placeholder={question.other}
          value={other}
          disabled={disabled}
          onChange={(event) => setOther(event.target.value)}
          aria-label={question.other}
        />
        <button
          type="submit"
          className="os-question-other-send"
          disabled={disabled || other.trim().length === 0}
        >
          Send
        </button>
      </form>
    </div>
  )
}
