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
})
