import { describe, expect, it } from 'vitest'
import {
  elicitQuestionsStorageKey,
  loadElicitQuestions,
  saveElicitQuestions,
} from '../elicitQuestions'

describe('elicitQuestions opt-in', () => {
  it('defaults off and round-trips per seat', () => {
    window.localStorage.clear()
    expect(loadElicitQuestions('chatbot')).toBe(false)
    expect(elicitQuestionsStorageKey('chatbot')).toBe('swarm_elicit_questions:chatbot')
    saveElicitQuestions('chatbot', true)
    expect(loadElicitQuestions('chatbot')).toBe(true)
    expect(loadElicitQuestions('codey')).toBe(false)
    saveElicitQuestions('chatbot', false)
    expect(loadElicitQuestions('chatbot')).toBe(false)
  })
})
