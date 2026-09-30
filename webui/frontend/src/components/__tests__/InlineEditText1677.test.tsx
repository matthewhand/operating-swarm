/**
 * #1677 — the click-to-edit inline field behind the agent Details fields.
 *
 * Three properties, in the order they matter:
 *
 * 1. **It is not a div with onClick.** Idle is a real `<button>` with an
 *    accessible name that says what the value is *and* that it is editable.
 *    Editing is a real focusable input/textarea with a real label. Clicking
 *    moves focus into it.
 * 2. **A failed save is loud.** `onSave` rejecting keeps the editor open, marks
 *    it `aria-invalid`, keeps the draft, and puts the reason in a `role="alert"`
 *    region. It does not exit edit mode and — critically — it does not present
 *    the new value as saved. This is the case that made the old per-keystroke
 *    handlers dangerous: they set local state first and fired the patch after,
 *    so a rejected write left the whole UI showing a value that was never
 *    stored.
 * 3. **No handler is swallowed.** Every standard handler AGENTS.md names is
 *    forwarded to the real input. The test asserts on the forwarded prop
 *    NAMES as well as on the calls, because a future refactor that drops
 *    `onKeyDown` would otherwise pass every behavioural test in this file
 *    while silently breaking Enter-to-send at a call site.
 */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { useState } from 'react'
import InlineEditText from '../InlineEditText'

const FORWARDED = [
  'onKeyDown',
  'onKeyUp',
  'onKeyPress',
  'onChange',
  'onInput',
  'onFocus',
  'onBlur',
  'onPaste',
  'onCompositionStart',
  'onCompositionEnd',
] as const

/**
 * The field is a CONTROLLED component: it shows the parent's `value` and calls
 * `onSave`. So the harness has to behave like a real parent — adopt the value
 * only after the write resolves — otherwise "the trigger now shows the new
 * name" can never be true and every commit assertion would be a lie about the
 * component rather than about the parent.
 */
function Harness(
  props: Partial<React.ComponentProps<typeof InlineEditText>> & {
    initial?: string
    onSaveImpl?: (next: string) => Promise<void>
  } = {},
) {
  const { initial = 'Codey', onSaveImpl, ...rest } = props
  const onSave = vi.fn(async (next: string) => {
    if (onSaveImpl) await onSaveImpl(next)
  })
  function Parent() {
    const [value, setValue] = useState(initial)
    return (
      <InlineEditText
        testId="f"
        label="Name"
        value={value}
        onSave={async (next) => {
          await onSave(next)
          // A real parent adopts the value only once the write landed.
          setValue(next)
        }}
        {...rest}
      />
    )
  }
  const result = render(<Parent />)
  return { onSave, ...result }
}

describe('#1677 idle state is a real, announced control', () => {
  it('is a focusable button, not a div with a click handler', () => {
    Harness()
    const trigger = screen.getByTestId('f-trigger')
    expect(trigger.tagName).toBe('BUTTON')
    expect(trigger).toHaveAttribute('type', 'button')
    expect(trigger.getAttribute('tabindex')).toBeNull()
    expect(trigger).toHaveTextContent('Codey')
  })

  it('announces the value AND that it is editable', () => {
    Harness()
    const label = screen.getByTestId('f-trigger').getAttribute('aria-label') || ''
    expect(label).toContain('Name')
    expect(label).toContain('Codey')
    expect(label).toMatch(/edit/i)
  })

  it('shows an honest placeholder when there is no value yet', () => {
    render(
      <InlineEditText
        testId="f"
        label="Title"
        value=""
        placeholder="Add a label"
        onSave={vi.fn()}
      />,
    )
    const trigger = screen.getByTestId('f-trigger')
    expect(trigger).toHaveTextContent('Add a label')
    expect(trigger.getAttribute('aria-label')).toContain('Add a label')
  })
})

describe('#1677 click focuses the editor', () => {
  it('clicking swaps the button for a focused, labelled input seeded with the value', () => {
    Harness()
    fireEvent.click(screen.getByTestId('f-trigger'))

    const editor = screen.getByLabelText('Name')
    expect(editor.tagName).toBe('INPUT')
    expect(editor).toHaveValue('Codey')
    expect(document.activeElement).toBe(editor)
    // The trigger is gone while editing, so there is no ambiguous duplicate.
    expect(screen.queryByTestId('f-trigger')).not.toBeInTheDocument()
  })

  it('the multiline variant is a real textarea, still labelled and focusable', () => {
    render(
      <InlineEditText
        testId="f"
        label="Description"
        value="A blurb"
        multiline
        onSave={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByTestId('f-trigger'))
    const editor = screen.getByLabelText('Description')
    expect(editor.tagName).toBe('TEXTAREA')
    expect(editor).toHaveValue('A blurb')
    expect(document.activeElement).toBe(editor)
  })
})

describe('#1677 commit and cancel', () => {
  it('Enter commits the draft and returns focus to the trigger', async () => {
    const { onSave } = Harness()
    fireEvent.click(screen.getByTestId('f-trigger'))
    const editor = screen.getByLabelText('Name')
    fireEvent.change(editor, { target: { value: '  Honey Bee  ' } })
    fireEvent.keyDown(editor, { key: 'Enter' })

    await waitFor(() => expect(onSave).toHaveBeenCalledWith('Honey Bee'))
    await waitFor(() => expect(screen.getByTestId('f-trigger')).toHaveTextContent('Honey Bee'))
    expect(document.activeElement).toBe(screen.getByTestId('f-trigger'))
  })

  it('blur commits too', async () => {
    const { onSave } = Harness()
    fireEvent.click(screen.getByTestId('f-trigger'))
    const editor = screen.getByLabelText('Name')
    fireEvent.change(editor, { target: { value: 'On blur' } })
    fireEvent.blur(editor)
    await waitFor(() => expect(onSave).toHaveBeenCalledWith('On blur'))
  })

  it('Esc cancels: no save, previous value restored, focus back on the trigger', () => {
    const { onSave } = Harness()
    fireEvent.click(screen.getByTestId('f-trigger'))
    const editor = screen.getByLabelText('Name')
    fireEvent.change(editor, { target: { value: 'Discard me' } })
    fireEvent.keyDown(editor, { key: 'Escape' })

    expect(onSave).not.toHaveBeenCalled()
    expect(screen.getByTestId('f-trigger')).toHaveTextContent('Codey')
    expect(document.activeElement).toBe(screen.getByTestId('f-trigger'))
  })

  it('Enter then the trailing blur does not save twice', async () => {
    const { onSave } = Harness()
    fireEvent.click(screen.getByTestId('f-trigger'))
    const editor = screen.getByLabelText('Name')
    fireEvent.change(editor, { target: { value: 'Once' } })
    fireEvent.keyDown(editor, { key: 'Enter' })
    fireEvent.blur(editor)
    await waitFor(() => expect(screen.getByTestId('f-trigger')).toHaveTextContent('Once'))
    expect(onSave).toHaveBeenCalledTimes(1)
  })

  it('an unchanged value is not a write', async () => {
    const { onSave } = Harness()
    fireEvent.click(screen.getByTestId('f-trigger'))
    fireEvent.keyDown(screen.getByLabelText('Name'), { key: 'Enter' })
    await waitFor(() => expect(screen.getByTestId('f-trigger')).toBeInTheDocument())
    expect(onSave).not.toHaveBeenCalled()
  })

  it('Enter inserts a newline in the multiline variant instead of committing', () => {
    const { onSave } = Harness({ multiline: true })
    fireEvent.click(screen.getByTestId('f-trigger'))
    const editor = screen.getByLabelText('Name') as HTMLTextAreaElement
    fireEvent.change(editor, { target: { value: 'line one\nline two' } })
    fireEvent.keyDown(editor, { key: 'Enter' })
    expect(onSave).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Name')).toBeInTheDocument()
  })

  it('Cmd+Enter commits the multiline variant', async () => {
    const { onSave } = Harness({ multiline: true })
    fireEvent.click(screen.getByTestId('f-trigger'))
    const editor = screen.getByLabelText('Name')
    fireEvent.change(editor, { target: { value: 'Two lines' } })
    fireEvent.keyDown(editor, { key: 'Enter', metaKey: true })
    await waitFor(() => expect(onSave).toHaveBeenCalledWith('Two lines'))
  })

  it('Esc cancels the multiline variant too', () => {
    const { onSave } = Harness({ multiline: true })
    fireEvent.click(screen.getByTestId('f-trigger'))
    const editor = screen.getByLabelText('Name')
    fireEvent.change(editor, { target: { value: 'Discard' } })
    fireEvent.keyDown(editor, { key: 'Escape' })
    expect(onSave).not.toHaveBeenCalled()
    expect(screen.getByTestId('f-trigger')).toHaveTextContent('Codey')
  })
})

describe('#1677 validation blocks an unusable value', () => {
  it('refuses an empty required field and says why, without saving', () => {
    const { onSave } = Harness()
    fireEvent.click(screen.getByTestId('f-trigger'))
    const editor = screen.getByLabelText('Name')
    fireEvent.change(editor, { target: { value: '   ' } })
    fireEvent.keyDown(editor, { key: 'Enter' })

    expect(onSave).not.toHaveBeenCalled()
    // Stays open, marked invalid, reason announced.
    expect(screen.getByLabelText('Name')).toBeInTheDocument()
    expect(screen.getByLabelText('Name')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByRole('alert')).toHaveTextContent(/cannot be empty/i)
  })

  it('allows empty when the field is optional', async () => {
    const { onSave } = Harness({ allowEmpty: true })
    fireEvent.click(screen.getByTestId('f-trigger'))
    const editor = screen.getByLabelText('Name')
    fireEvent.change(editor, { target: { value: '' } })
    fireEvent.keyDown(editor, { key: 'Enter' })
    await waitFor(() => expect(onSave).toHaveBeenCalledWith(''))
  })

  it('refuses a value over the field limit', () => {
    const { onSave } = Harness({ maxLength: 4 })
    fireEvent.click(screen.getByTestId('f-trigger'))
    const editor = screen.getByLabelText('Name')
    fireEvent.change(editor, { target: { value: 'far too long' } })
    fireEvent.keyDown(editor, { key: 'Enter' })
    expect(onSave).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent(/4 characters or fewer/i)
  })
})

describe('#1677 a failed save is surfaced, never silently reverted or faked', () => {
  it('keeps the editor open, announces the reason, and does NOT show the new value as saved', async () => {
    const onSave = vi.fn(async () => {
      throw new Error('profile endpoint returned 503')
    })
    const { rerender } = render(
      <InlineEditText testId="f" label="Name" value="Codey" onSave={onSave} />,
    )
    fireEvent.click(screen.getByTestId('f-trigger'))
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Honey Bee' } })
    fireEvent.keyDown(screen.getByLabelText('Name'), { key: 'Enter' })

    await waitFor(() => expect(onSave).toHaveBeenCalledWith('Honey Bee'))

    // The write really was attempted.
    expect(onSave).toHaveBeenCalledTimes(1)
    // Still editing, still invalid, reason announced as an alert.
    const editor = await screen.findByLabelText('Name')
    expect(editor).toBeInTheDocument()
    expect(editor).toHaveAttribute('aria-invalid', 'true')
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('profile endpoint returned 503')
    // The draft is preserved so the user can fix it, and focus is back in it.
    expect(editor).toHaveValue('Honey Bee')
    expect(document.activeElement).toBe(editor)

    // Now the parent admits the save did not land: the value is still 'Codey'.
    rerender(<InlineEditText testId="f" label="Name" value="Codey" onSave={onSave} />)
    fireEvent.click(screen.getByTestId('f-cancel'))
    expect(screen.getByTestId('f-trigger')).toHaveTextContent('Codey')
    expect(screen.getByTestId('f-trigger')).not.toHaveTextContent('Honey Bee')
  })

  it('does not call onSave again when the same failing value is re-submitted as unchanged', async () => {
    const onSave = vi.fn(async () => {
      throw new Error('nope')
    })
    render(<InlineEditText testId="f" label="Name" value="Codey" onSave={onSave} />)
    fireEvent.click(screen.getByTestId('f-trigger'))
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Nope' } })
    fireEvent.keyDown(screen.getByLabelText('Name'), { key: 'Enter' })
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(onSave).toHaveBeenCalledTimes(1)
  })

  it('a rejected save is not mistaken for a settled one by the trailing blur', async () => {
    let reject: (reason: Error) => void = () => undefined
    const onSave = vi.fn(
      () =>
        new Promise<void>((_resolve, rej) => {
          reject = rej
        }),
    )
    render(<InlineEditText testId="f" label="Name" value="Codey" onSave={onSave} />)
    fireEvent.click(screen.getByTestId('f-trigger'))
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Pending' } })
    fireEvent.keyDown(screen.getByLabelText('Name'), { key: 'Enter' })
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1))

    // A blur while the write is still in flight must not fire a second write.
    fireEvent.blur(screen.getByLabelText('Name'))
    expect(onSave).toHaveBeenCalledTimes(1)

    reject(new Error('later failure'))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('later failure'))
    expect(screen.getByLabelText('Name')).toBeInTheDocument()
  })

  it('cancelling a slow save does not leave a stale error under the trigger', async () => {
    let reject: (reason: Error) => void = () => undefined
    const onSave = vi.fn(
      () =>
        new Promise<void>((_resolve, rej) => {
          reject = rej
        }),
    )
    render(<InlineEditText testId="f" label="Name" value="Codey" onSave={onSave} />)
    fireEvent.click(screen.getByTestId('f-trigger'))
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Pending' } })
    fireEvent.keyDown(screen.getByLabelText('Name'), { key: 'Enter' })
    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1))

    // The user walks away from a save that is still in flight.
    fireEvent.click(screen.getByTestId('f-cancel'))
    reject(new Error('too late'))
    await waitFor(() => expect(screen.getByTestId('f-trigger')).toBeInTheDocument())
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByTestId('f-trigger')).toHaveTextContent('Codey')
  })
})

describe('#1677 no event handler is dropped', () => {
  it('forwards every standard handler to the real input', async () => {
    const spies: Record<string, ReturnType<typeof vi.fn>> = {}
    const props: Record<string, unknown> = {}
    for (const name of FORWARDED) {
      spies[name] = vi.fn()
      props[name] = spies[name]
    }
    const onSave = vi.fn(async () => undefined)
    render(<InlineEditText testId="f" label="Name" value="Codey" onSave={onSave} {...props} />)

    fireEvent.click(screen.getByTestId('f-trigger'))
    const editor = screen.getByLabelText('Name')
    expect(editor.tagName).toBe('INPUT')

    fireEvent.keyDown(editor, { key: 'a' })
    fireEvent.keyUp(editor, { key: 'a' })
    fireEvent.keyPress(editor, { key: 'a', charCode: 97 })
    fireEvent.compositionStart(editor)
    fireEvent.change(editor, { target: { value: 'Zed' } })
    fireEvent.input(editor)
    fireEvent.compositionEnd(editor)
    fireEvent.paste(editor)
    fireEvent.focus(editor)
    fireEvent.blur(editor)

    for (const name of FORWARDED) {
      expect(spies[name], `${name} was not forwarded`).toHaveBeenCalled()
    }
    // The forwarded handlers received the REAL event, not a synthetic stub —
    // a wrapper that fabricates an object here would pass a `.toHaveBeenCalled`
    // check while breaking whatever the caller actually reads off it.
    expect(spies.onChange.mock.calls[0][0].target.value).toBe('Zed')
    expect(spies.onPaste.mock.calls[0][0].type).toBe('paste')
    expect(spies.onCompositionStart.mock.calls[0][0].type).toBe('compositionstart')
    expect(spies.onKeyUp.mock.calls[0][0].key).toBe('a')
    expect(spies.onKeyPress.mock.calls[0][0].key).toBe('a')
  })

  it('Enter is still handled internally even though onKeyDown is forwarded', async () => {
    const onKeyDown = vi.fn()
    const onSave = vi.fn(async () => undefined)
    render(
      <InlineEditText
        testId="f"
        label="Name"
        value="Codey"
        onSave={onSave}
        onKeyDown={onKeyDown}
      />,
    )
    fireEvent.click(screen.getByTestId('f-trigger'))
    const editor = screen.getByLabelText('Name')
    fireEvent.change(editor, { target: { value: 'Entered' } })
    fireEvent.keyDown(editor, { key: 'Enter' })

    await waitFor(() => expect(onSave).toHaveBeenCalledWith('Entered'))
    // Forwarded AND observed — not swallowed to make the commit work.
    expect(onKeyDown).toHaveBeenCalled()
  })

  it('declares all of them on the public props type', () => {
    const source = readFileSync(
      join(process.cwd(), 'src/components/InlineEditText.tsx'),
      'utf8',
    )
    const propsBlock = source.slice(
      source.indexOf('export interface InlineEditTextProps'),
      source.indexOf('function messageOf'),
    )
    for (const name of FORWARDED) {
      expect(propsBlock, `props type is missing ${name}`).toContain(`${name}?:`)
    }
  })
})
