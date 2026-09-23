import { apiDelete, apiGet, apiPatch, apiPost } from './api'
import type { CronTrigger, HistoryArtifact, IntervalTrigger, OneShotTrigger } from './routines'
import { formatDurationMs, formatRoutineHistoryTime, historySucceeded } from './routines'

export type TestScheduleTrigger = IntervalTrigger | CronTrigger | OneShotTrigger

export interface TestScheduleTarget {
  kind: 'agent' | 'fleet'
  agent_id?: string
  fleet?: string
}

export interface TestScheduleCheck {
  kind: 'harness_health' | 'blueprint_smoke' | 'script' | 'remote_harness' | string
  name: string
  command?: string
}

export interface TestScheduleHistoryRow {
  id: string
  ran_at: string
  status: string
  source: string
  summary?: string
  duration_ms?: number
  token_cost?: number
  artifact?: HistoryArtifact
  error?: string
}

export interface TestSchedule {
  id: string
  name: string
  active: boolean
  trigger: TestScheduleTrigger
  target: TestScheduleTarget
  check: TestScheduleCheck
  history: TestScheduleHistoryRow[]
  next_run?: string | null
  when_to_run?: string
}

export interface TestScheduleList {
  object: string
  schedules: TestSchedule[]
  failure_count?: number
}

export interface TestScheduleStatus {
  object: string
  failure_count: number
  failures: Array<{ id?: string; name?: string; status?: string; summary?: string }>
}

export interface TestScheduleWrite {
  name?: string
  active?: boolean
  trigger?: Partial<TestScheduleTrigger> & { kind?: string; seconds?: number; expression?: string; run_at?: string }
  target?: Partial<TestScheduleTarget>
  check?: Partial<TestScheduleCheck>
}

export function defaultTestTrigger(): IntervalTrigger {
  return { kind: 'interval', seconds: 3600 }
}

export function testSchedulesPath(): string {
  return '/v1/test-schedules/'
}

export function testSchedulePath(scheduleId: string): string {
  return `${testSchedulesPath()}${encodeURIComponent(scheduleId)}/`
}

export async function fetchTestSchedules(): Promise<TestSchedule[]> {
  const data = await apiGet<TestScheduleList>(testSchedulesPath())
  return Array.isArray(data?.schedules) ? data.schedules : []
}

export async function fetchTestScheduleStatus(): Promise<TestScheduleStatus> {
  return apiGet<TestScheduleStatus>('/v1/test-schedules/status/')
}

export async function createTestSchedule(body: TestScheduleWrite = {}): Promise<TestSchedule> {
  return apiPost<TestSchedule>(testSchedulesPath(), {
    name: body.name ?? 'New test schedule',
    active: body.active ?? true,
    trigger: body.trigger ?? defaultTestTrigger(),
    target: body.target ?? { kind: 'fleet', fleet: 'all' },
    check: body.check ?? { kind: 'script', name: 'fleet_prove' },
  })
}

export async function updateTestSchedule(
  scheduleId: string,
  patch: TestScheduleWrite,
): Promise<TestSchedule> {
  return apiPatch<TestSchedule>(testSchedulePath(scheduleId), patch)
}

export async function deleteTestSchedule(scheduleId: string): Promise<void> {
  await apiDelete(testSchedulePath(scheduleId))
}

export async function runNowTestSchedule(scheduleId: string): Promise<TestSchedule> {
  return apiPost<TestSchedule>(`${testSchedulePath(scheduleId)}run-now/`, {})
}

export { formatDurationMs, formatRoutineHistoryTime, historySucceeded }
