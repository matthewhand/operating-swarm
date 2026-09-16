import { describe, expect, it } from 'vitest'
import {
  composeModelId,
  defaultEffortForFamily,
  displayableModels,
  groupModelsByFamily,
  isHiddenRoutingLabel,
  joinRoutingPath,
  parseModelEffort,
  resolveComposedModel,
  routingFaceParts,
  routingPathFromSelection,
  splitRoutingPath,
} from '../routingPath'

const AGY_MODELS = [
  'gemini-3.8-flash-high',
  'gemini-3.8-flash-medium',
  'gemini-3.1-pro-high',
  'claude-sonnet-4-6',
  'claude-opus-4-6-thinking',
  'gpt-oss-120b-medium',
  'default',
  'You',
]

describe('routingPath (REQ-200)', () => {
  it('parses effort suffixes and leaves thinking / bare ids alone', () => {
    expect(parseModelEffort('gemini-3.8-flash-medium')).toEqual({
      base: 'gemini-3.8-flash',
      effort: 'medium',
    })
    expect(parseModelEffort('gemini-3.8-flash-high')).toEqual({
      base: 'gemini-3.8-flash',
      effort: 'high',
    })
    expect(parseModelEffort('gpt-oss-120b-low')).toEqual({
      base: 'gpt-oss-120b',
      effort: 'low',
    })
    expect(parseModelEffort('claude-opus-4-6-thinking')).toEqual({
      base: 'claude-opus-4-6-thinking',
      effort: null,
    })
    expect(parseModelEffort('grok-4.6')).toEqual({ base: 'grok-4.6', effort: null })
    expect(parseModelEffort('')).toEqual({ base: '', effort: null })
  })

  it('hides You/Default and groups discovered models by family', () => {
    expect(isHiddenRoutingLabel('You')).toBe(true)
    expect(isHiddenRoutingLabel('default')).toBe(true)
    expect(displayableModels(AGY_MODELS)).not.toContain('default')
    expect(displayableModels(AGY_MODELS)).not.toContain('You')
    const families = groupModelsByFamily(AGY_MODELS)
    expect(families.map((row) => row.base)).toEqual([
      'gemini-3.8-flash',
      'gemini-3.1-pro',
      'claude-sonnet-4-6',
      'claude-opus-4-6-thinking',
      'gpt-oss-120b',
    ])
    expect(families[0].efforts).toEqual(['medium', 'high'])
    expect(families.find((row) => row.base === 'claude-sonnet-4-6')?.efforts).toEqual([])
  })

  it('prefers medium then an existing id when composing', () => {
    const families = groupModelsByFamily(AGY_MODELS)
    const flash = families[0]
    expect(defaultEffortForFamily(flash)).toBe('medium')
    expect(defaultEffortForFamily(flash, 'high')).toBe('high')
    expect(composeModelId('gemini-3.8-flash', 'medium')).toBe('gemini-3.8-flash-medium')
    expect(resolveComposedModel(AGY_MODELS, 'gemini-3.8-flash')).toMatchObject({
      model: 'gemini-3.8-flash-medium',
      modelBase: 'gemini-3.8-flash',
      effort: 'medium',
    })
    expect(resolveComposedModel(AGY_MODELS, 'claude-sonnet-4-6')).toMatchObject({
      model: 'claude-sonnet-4-6',
      effort: null,
    })
  })

  it('keeps pi provider/model ids as pin-able options, not provider-only families', () => {
    const piModels = [
      'anthropic/claude-sonnet-4-6',
      'openai/gpt-4o',
      'bailian-coding-plan/glm-4.7',
      'default',
    ]
    expect(displayableModels(piModels)).toEqual([
      'anthropic/claude-sonnet-4-6',
      'openai/gpt-4o',
      'bailian-coding-plan/glm-4.7',
    ])
    const families = groupModelsByFamily(piModels)
    expect(families.map((row) => row.base)).toEqual([
      'anthropic/claude-sonnet-4-6',
      'openai/gpt-4o',
      'bailian-coding-plan/glm-4.7',
    ])
    expect(families.every((row) => row.efforts.length === 0)).toBe(true)
    expect(families.map((row) => row.ids[0])).not.toContain('anthropic')
    expect(families.map((row) => row.ids[0])).not.toContain('openai')
  })

  it('joins a closed path and splits it back', () => {
    expect(joinRoutingPath(['agy', 'gemini-3.8-flash', 'medium'])).toBe(
      'agy / gemini-3.8-flash / medium',
    )
    expect(joinRoutingPath(['agy', 'default', 'You'])).toBe('agy')
    expect(splitRoutingPath('agy / gemini-3.8-flash / medium')).toEqual([
      'agy',
      'gemini-3.8-flash',
      'medium',
    ])
    const path = routingPathFromSelection({
      agent: 'agy',
      model: 'gemini-3.8-flash-medium',
    })
    expect(routingFaceParts(path, AGY_MODELS)).toEqual([
      'agy',
      'gemini-3.8-flash',
      'medium',
    ])
  })
})
