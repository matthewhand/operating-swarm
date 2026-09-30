/**
 * Referential stability for "the query has no data yet" defaults.
 *
 * `const rows = query.data?.data ?? []` looks free and is not: while the query
 * is empty it allocates a NEW array on every render, and any `useMemo` /
 * `useEffect` / `useCallback` that lists `rows` in its dependency array then
 * misses its cache on every single render and re-runs its body. An effect that
 * talks to the network re-runs it into a request burst; a memo that builds a
 * large list redoes the work; a callback handed to a memoized child re-renders
 * that subtree. The allocation is the defect, not the fallback.
 *
 * So the fallback is a module-level constant — same value, one identity, for
 * the lifetime of the tab. This is the same shape as the `EMPTY_BLUEPRINTS`
 * constants already used across the components, generalised.
 *
 * A `useMemo` is the wrong tool for this: it still costs a hook and a
 * comparison, and the constant is correct in every case. Reach for a `useMemo`
 * only when the whole expression is a call that allocates —
 * `parseTeamRosters(query.data ?? [])` returns fresh objects, and fixing only
 * the `[]` would leave the churn in place.
 *
 * Typed per call site via `emptyArray<T>()`, the same way `EMPTY_BLUEPRINTS` is
 * declared once per module with its element type.
 */

/**
 * The stable empty array, cast to whatever element type the caller needs.
 *
 * `readonly never[]` → `T[]` needs the `unknown` hop: TypeScript will not
 * narrow a readonly array to a mutable one directly, and the cast is the whole
 * point of the module. Callers must treat the result as READ-ONLY — it is one
 * array shared by every call site, so anything that mutates its "own" empty
 * fallback would corrupt every other one. `readonly T[]` in the signature would
 * force that at compile time, but most of these values feed APIs already typed
 * as mutable arrays, so a `readonly` return would not typecheck at the call
 * sites either. The comment is the contract.
 */
export function emptyArray<T>(): T[] {
  return EMPTY_ARRAY as unknown as T[]
}

/** The stable empty object, cast to whatever shape the caller needs. Read-only. */
export function emptyObject<T>(): T {
  return EMPTY_OBJECT as T
}

const EMPTY_ARRAY: readonly never[] = []
const EMPTY_OBJECT: Readonly<Record<string, never>> = {}
