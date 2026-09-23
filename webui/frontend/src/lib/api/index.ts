/** #856 slice A — package facade.
 *
 * `lib/api` resolves as a directory, so every existing `'./api'` specifier
 * keeps working unchanged. Star re-exports are disjoint by construction:
 * each name has exactly one owning module.
 */
export * from './client'
export * from './settings'
export * from './teams'
export * from './blueprints'
export * from './llm'
export * from './remotes'
export * from './herdr'
export * from './plugins'
export * from './marketplace'
export * from './types'
