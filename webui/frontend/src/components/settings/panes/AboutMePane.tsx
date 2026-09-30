/** #1323 — operator About me profile. */
import { useEffect, useState, type FormEvent } from 'react'
import { Button, Input, Textarea, useToast } from '../.././DaisyUI'
import {
  EMPTY_OPERATOR_PROFILE,
  fetchUserPrefs,
  parseOperatorProfile,
  saveUserPrefs,
  type OperatorProfile,
} from '../../../lib/userPrefs'

export function AboutMePane() {
  const { success, error: toastError } = useToast()
  const [profile, setProfile] = useState<OperatorProfile>(EMPTY_OPERATOR_PROFILE)
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    void fetchUserPrefs().then((prefs) => {
      if (cancelled) return
      // A failed GET parses as null. Enabling Save on the empty form would
      // PATCH a blank card over the stored profile.
      if (!prefs) {
        toastError('About me unavailable', 'Could not load the operator profile for this account.')
        return
      }
      setProfile(parseOperatorProfile(prefs.operator_profile))
      setLoaded(true)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const handleSave = async (event: FormEvent) => {
    event.preventDefault()
    setSaving(true)
    const next = parseOperatorProfile(profile)
    const saved = await saveUserPrefs({ operator_profile: next })
    setSaving(false)
    if (saved) {
      setProfile(parseOperatorProfile(saved.operator_profile))
      success('About me saved', 'Agents will see this on the next turn.')
    } else {
      toastError('About me not saved', 'Could not store the operator profile for this account.')
    }
  }

  return (
    <form className="space-y-4" onSubmit={handleSave} data-testid="about-me-pane">
      <div>
        <h4 className="text-lg font-semibold">About me</h4>
        <p className="mt-1 text-sm text-base-content/70">
          What should agents know about you. Saved on this account. Empty fields
          are omitted from chat context.
        </p>
      </div>
      <Input
        id="os-about-me-name"
        label="Display name"
        name="operator-name"
        value={profile.name}
        onChange={(event) => setProfile((prev) => ({ ...prev, name: event.target.value }))}
        placeholder="How agents should address you"
        autoComplete="nickname"
        data-testid="about-me-name"
      />
      <Input
        id="os-about-me-timezone"
        label="Timezone"
        name="operator-timezone"
        value={profile.timezone}
        onChange={(event) => setProfile((prev) => ({ ...prev, timezone: event.target.value }))}
        placeholder="Australia/Sydney"
        autoComplete="off"
        spellCheck={false}
        data-testid="about-me-timezone"
      />
      <Textarea
        id="os-about-me-notes"
        label="Notes"
        name="operator-about"
        value={profile.about}
        onChange={(event) => setProfile((prev) => ({ ...prev, about: event.target.value }))}
        placeholder="Role, how you like answers, current focus…"
        rows={6}
        data-testid="about-me-notes"
      />
      <Button
        type="submit"
        variant="primary"
        size="sm"
        disabled={!loaded || saving}
        data-testid="about-me-save"
      >
        Save About me
      </Button>
    </form>
  )
}
