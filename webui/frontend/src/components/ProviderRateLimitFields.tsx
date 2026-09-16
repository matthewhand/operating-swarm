import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Input, useToast } from './DaisyUI'
import { fetchRateLimits, patchRateLimits } from '../lib/api'
import {
  RATE_LIMIT_RULE_KEYS,
  RATE_LIMIT_RULE_LABELS,
  emptyRateLimitRules,
  parseLimitInput,
  parseRateLimitRules,
  rateLimitFieldId,
  type RateLimitRuleKey,
  type RateLimitRules,
} from '../lib/providerRateLimits'

export const RATE_LIMITS_QUERY_KEY = ['provider-rate-limits'] as const

export default function ProviderRateLimitFields({
  providerKey,
  autoFocus = false,
}: {
  providerKey: string
  autoFocus?: boolean
}) {
  const { success, error: toastError } = useToast()
  const queryClient = useQueryClient()
  const fieldId = rateLimitFieldId(providerKey)
  const query = useQuery({
    queryKey: RATE_LIMITS_QUERY_KEY,
    queryFn: fetchRateLimits,
    retry: 1,
  })
  const [draft, setDraft] = useState<RateLimitRules>(emptyRateLimitRules)
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    setDirty(false)
  }, [providerKey])

  useEffect(() => {
    if (dirty || !query.data) return
    const row = query.data.data?.find((item) => item.id === providerKey)
    setDraft(parseRateLimitRules(row?.rules))
  }, [dirty, providerKey, query.data])

  useEffect(() => {
    if (!autoFocus) return
    const node = document.getElementById(fieldId)
    if (node instanceof HTMLElement) {
      node.scrollIntoView({ block: 'center' })
      const input = node.querySelector('input')
      input?.focus()
    }
  }, [autoFocus, fieldId])

  const save = useMutation({
    mutationFn: (rules: RateLimitRules) => patchRateLimits(providerKey, rules),
    onSuccess: () => {
      setDirty(false)
      void queryClient.invalidateQueries({ queryKey: RATE_LIMITS_QUERY_KEY })
      success('Rate limits saved', 'Agents that send through this provider share one queue.')
    },
    onError: (err: Error) => {
      toastError('Could not save rate limits', err.message)
    },
  })

  const setField = (key: RateLimitRuleKey, value: string) => {
    setDirty(true)
    setDraft((prev) => ({ ...prev, [key]: parseLimitInput(value) }))
  }

  return (
    <fieldset
      id={fieldId}
      data-testid={fieldId}
      data-provider={providerKey}
      className="mt-2 space-y-2 rounded-box border border-base-300 p-3"
    >
      <legend className="px-1 text-sm font-semibold">Rate limits</legend>
      <p className="text-xs text-base-content/60">
        Optional caps for this provider. Empty means no limit. Every agent and
        team worker that sends through this provider waits on the same queue.
      </p>
      <div className="grid min-w-0 gap-2 sm:grid-cols-2 [&>*]:min-w-0">
        {RATE_LIMIT_RULE_KEYS.map((key) => (
          <Input
            key={key}
            label={RATE_LIMIT_RULE_LABELS[key]}
            name={`${fieldId}-${key}`}
            type="number"
            min={1}
            inputMode="numeric"
            placeholder="No limit"
            size="sm"
            value={draft[key] == null ? '' : String(draft[key])}
            onChange={(event) => setField(key, event.target.value)}
          />
        ))}
      </div>
      <Button
        type="button"
        variant="outline"
        size="xs"
        onClick={() => save.mutate(draft)}
        disabled={save.isPending || !providerKey}
      >
        Save rate limits
      </Button>
    </fieldset>
  )
}
