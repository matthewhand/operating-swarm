import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'

describe('Alt Hotkey Tip Position (REQ-182)', () => {
  it('positions .os-fav-tile__shortcut at the top-right of favourite card', () => {
    const cssPath = path.resolve(__dirname, '../../index.css')
    const css = fs.readFileSync(cssPath, 'utf-8')

    const match = css.match(/\.os-fav-tile__shortcut\s*\{([^}]+)\}/)
    expect(match).not.toBeNull()
    const ruleBody = match![1]

    expect(ruleBody).toMatch(/top:\s*0\.\d+rem/)
    expect(ruleBody).not.toMatch(/bottom:/)
    expect(ruleBody).toMatch(/right:\s*0\.\d+rem/)
    expect(ruleBody).toMatch(/z-index:\s*10/)

    expect(css).toContain('.os-fav-tile:hover .os-fav-tile__shortcut')
    expect(css).not.toContain('.os-fav-tile:focus-within .os-fav-tile__shortcut')
  })

  it('#691 (supersedes #579): the pinned role badge holds the top-LEFT corner, not the avatar centre', () => {
    const cssPath = path.resolve(__dirname, '../../index.css')
    const css = fs.readFileSync(cssPath, 'utf-8')
    const match = css.match(/\.os-fav-tile__badge\s*\{([^}]+)\}/)
    expect(match).not.toBeNull()
    const ruleBody = match![1]

    // #691 flips the corner: left edge, same top.
    expect(ruleBody).toMatch(/left:\s*0\.\d+rem/)
    expect(ruleBody).toMatch(/top:\s*0\.\d+rem/)
    // Centring over the avatar is what the badge must stop doing.
    expect(ruleBody).not.toMatch(/left:\s*50%/)  
    expect(ruleBody).not.toMatch(/translate\(-50%/)  
    // Still absolutely positioned: the pinned grid must not grow.
    expect(ruleBody).toContain('position: absolute')
  })

  it('#579: the two tenants of the top-right corner have stated rules', () => {
    const cssPath = path.resolve(__dirname, '../../index.css')
    const css = fs.readFileSync(cssPath, 'utf-8')
    // The ⌥N hint wins the corner on hover; the badge slides left of it.
    expect(css).toContain(
      '.os-fav-tile:hover:has(.os-fav-tile__shortcut) .os-fav-tile__badge',
    )
    // The NEEDS APPROVAL band wins the top edge; the badge drops below it.
    expect(css).toContain('.os-fav-tile:has(.os-fav-tile__attention) .os-fav-tile__badge')
  })
})
