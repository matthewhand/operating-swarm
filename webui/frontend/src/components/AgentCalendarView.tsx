import { memo, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Calendar as CalendarIcon,
  CheckCircle2,
  Clock,
  ExternalLink,
  Loader2,
  MessageSquare,
  Plus,
  Sparkles,
  X,
  XCircle,
} from "lucide-react"
import { setConversationIdForAgent } from "../lib/agentChat"
import {
  fetchAllRoutines,
  type Routine,
  type RoutineHistoryRow,
} from "../lib/routines"
import { isApiBlueprintId } from "../lib/cliAgentContext"
import { humanizeCron } from "./RemotesSettings"
import { OverlayFocusTrap } from "./OverlayFocusTrap"
import { RoutineEditorDialog } from "./RoutineEditorDialog"
import { railSelectionFromParams } from "../lib/railActive"
import { useLocation } from "react-router-dom"

export interface CalendarDay {
  date: Date
  dateKey: string
  dayNumber: number
  monthNumber: number
  monthName: string
  weekday: string
  dayOfWeek: number
  isToday: boolean
}

export type CalendarViewMode = "all" | "history" | "upcoming"

export interface CalendarExecutedEntry {
  kind: "executed"
  id: string
  routine: Routine
  history: RoutineHistoryRow
}

export interface CalendarScheduledEntry {
  kind: "scheduled"
  id: string
  routine: Routine
}

export type CalendarEntry = CalendarExecutedEntry | CalendarScheduledEntry

export interface ExecutionChatTarget {
  routine: Routine
  history: RoutineHistoryRow
  agentId: string
  conversationId?: string
}

export interface AgentCalendarViewProps {
  open?: boolean
  onClose?: () => void
  initialRoutines?: Routine[]
  agents?: Array<{
    id: string
    name?: string
    kind?: string | null
    description?: string | null
  }>
  startDate?: Date | string | number
  now?: Date | string | number
  onSelectRoutine?: (routine: Routine) => void
  onSelectAgent?: (agentId: string) => void
  onSelectExecution?: (target: ExecutionChatTarget) => void
  defaultApiOnly?: boolean
  defaultViewMode?: CalendarViewMode
}

export function localDateKey(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

/**
 * Days in the calendar month containing `date` — 28, 29, 30 or 31.
 *
 * Local-time by construction: `new Date(y, m + 1, 0)` resolves to the last day
 * of month `m`, so it accounts for leap Februaries without a table.
 */
export function daysInMonth(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0).getDate()
}

/**
 * The calendar month containing `reference` as days.
 *
 * REQ-915 / #514: the rail previously asked for a hard-coded 30 days, which
 * silently dropped the 31st from every 31-day month and spilled February into
 * March. The span must follow the real month length.
 */
export function getCalendarMonthDays(
  reference: Date,
  now: Date = new Date(),
): CalendarDay[] {
  const first = new Date(reference.getFullYear(), reference.getMonth(), 1)
  return getCalendarDays(first, daysInMonth(first), now)
}

export function getCalendarDays(
  baseDate: Date,
  count: number = 30,
  now: Date = new Date(),
): CalendarDay[] {
  const days: CalendarDay[] = []
  const todayKey = localDateKey(now)

  for (let i = 0; i < count; i++) {
    const d = new Date(baseDate.getFullYear(), baseDate.getMonth(), baseDate.getDate() + i)
    const dateKey = localDateKey(d)
    days.push({
      date: d,
      dateKey,
      dayNumber: d.getDate(),
      monthNumber: d.getMonth() + 1,
      monthName: d.toLocaleString("en-US", { month: "short" }),
      weekday: d.toLocaleString("en-US", { weekday: "short" }),
      dayOfWeek: d.getDay(),
      isToday: dateKey === todayKey,
    })
  }
  return days
}

export function isApiAgentRoutine(
  routine: Routine,
  agentsList?: Array<{ id: string; name?: string; kind?: string | null }>,
): boolean {
  if (routine.agent_kind === "api") return true
  const agentId = (routine.agent_id ?? "").trim().toLowerCase()
  if (
    agentId === "api_agent" ||
    agentId === "api" ||
    agentId.startsWith("api:") ||
    agentId.startsWith("api-") ||
    agentId.startsWith("api_") ||
    isApiBlueprintId(agentId)
  ) {
    return true
  }
  if (agentsList && agentId) {
    const found = agentsList.find((a) => a.id.toLowerCase() === agentId)
    if (found) {
      if (
        found.kind === "api" ||
        found.id === "api_agent" ||
        found.id.startsWith("api") ||
        isApiBlueprintId(found.id)
      ) {
        return true
      }
    }
  }
  return false
}

export function getRoutineScheduleString(routine: Routine): string {
  return (
    routine.cron ||
    routine.schedule ||
    (routine.trigger as any)?.cron ||
    (routine.trigger as any)?.schedule ||
    ((routine.trigger as any)?.kind === "cron" ? (routine.trigger as any)?.expression : "") ||
    ""
  ).trim()
}

function matchesDow(expr: string, dayOfWeek: number): boolean {
  if (expr === "*") return true
  if (expr === "1-5") return dayOfWeek >= 1 && dayOfWeek <= 5
  if (expr === "0,6" || expr === "6,0" || expr === "6-7" || expr === "0-1") {
    return dayOfWeek === 0 || dayOfWeek === 6
  }
  const parts = expr.split(",")
  for (const p of parts) {
    if (p.includes("-")) {
      const [start, end] = p.split("-").map(Number)
      if (!isNaN(start) && !isNaN(end) && dayOfWeek >= start && dayOfWeek <= end) {
        return true
      }
    } else {
      const n = Number(p)
      if (!isNaN(n)) {
        if (n === dayOfWeek || (n === 7 && dayOfWeek === 0)) return true
      }
    }
  }
  return false
}

function matchesDom(expr: string, dayNumber: number): boolean {
  if (expr === "*") return true
  if (expr.startsWith("*/")) {
    const step = Number(expr.slice(2))
    return !isNaN(step) && step > 0 && dayNumber % step === 0
  }
  const parts = expr.split(",")
  for (const p of parts) {
    if (p.includes("-")) {
      const [start, end] = p.split("-").map(Number)
      if (!isNaN(start) && !isNaN(end) && dayNumber >= start && dayNumber <= end) {
        return true
      }
    } else {
      const n = Number(p)
      if (!isNaN(n) && n === dayNumber) return true
    }
  }
  return false
}

function matchesMon(expr: string, monthNumber: number): boolean {
  if (expr === "*") return true
  const parts = expr.split(",")
  for (const p of parts) {
    const n = Number(p)
    if (!isNaN(n) && n === monthNumber) return true
  }
  return false
}

export function routineRunsOnDate(routine: Routine, day: CalendarDay): boolean {
  if (routine.next_run && routine.next_run.slice(0, 10) === day.dateKey) {
    return true
  }

  const sched = getRoutineScheduleString(routine).toLowerCase()
  if (!sched) return false

  if (sched === day.dateKey || sched.startsWith(day.dateKey)) {
    return true
  }

  const parts = sched.split(/\s+/)
  if (parts.length === 5) {
    const [, , dom, mon, dow] = parts
    const monOk = matchesMon(mon, day.monthNumber)
    if (!monOk) return false

    if (dom === "*" && dow === "*") return true
    if (dom !== "*" && dow === "*") return matchesDom(dom, day.dayNumber)
    if (dom === "*" && dow !== "*") return matchesDow(dow, day.dayOfWeek)
    return matchesDom(dom, day.dayNumber) || matchesDow(dow, day.dayOfWeek)
  }

  if (sched === "daily" || sched === "every day" || sched === "everyday") {
    return true
  }
  if (sched === "weekdays" || sched === "weekday" || sched === "every weekday") {
    return day.dayOfWeek >= 1 && day.dayOfWeek <= 5
  }
  if (sched === "weekends" || sched === "weekend" || sched === "every weekend") {
    return day.dayOfWeek === 0 || day.dayOfWeek === 6
  }
  const dayNames = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
  for (let i = 0; i < dayNames.length; i++) {
    if (sched === dayNames[i] || sched === `every ${dayNames[i]}` || sched === `${dayNames[i]}s`) {
      return day.dayOfWeek === i
    }
  }

  return false
}

export function historyDateKey(ranAt: string): string {
  return (ranAt || "").slice(0, 10)
}

export function isCalendarDayPast(day: CalendarDay, now: Date): boolean {
  return day.dateKey < localDateKey(now)
}

export function formatHourMinute(hour: number, minute: number): string {
  const period = hour >= 12 ? "PM" : "AM"
  const h12 = hour % 12 || 12
  return `${h12}:${String(minute).padStart(2, "0")} ${period}`
}

export function formatRunClock(iso: string): string {
  const ms = Date.parse(iso)
  if (!Number.isFinite(ms)) return ""
  const d = new Date(ms)
  return formatHourMinute(d.getUTCHours(), d.getUTCMinutes())
}

export function formatDuration(ms?: number | string | null): string {
  if (ms == null || ms === "") return ""
  const n = typeof ms === "number" ? ms : Number(ms)
  if (!Number.isFinite(n) || n < 0) return ""
  if (n < 1000) return `${Math.round(n)}ms`
  const totalSec = Math.floor(n / 1000)
  const mins = Math.floor(totalSec / 60)
  const secs = totalSec % 60
  if (mins === 0) return `${secs}s`
  return `${mins}m ${secs}s`
}

export function isExecutionInProgress(status: string | undefined): boolean {
  const value = (status || "").toLowerCase()
  return value === "running" || value === "in_progress" || value === "in-progress" || value === "pending"
}

export function scheduledRunLabel(routine: Routine): string {
  const sched = getRoutineScheduleString(routine)
  const parts = sched.split(/\s+/)
  if (parts.length === 5) {
    const [min, hour] = parts
    if (/^\d+$/.test(hour) && /^\d+$/.test(min)) {
      return `${formatHourMinute(Number(hour), Number(min))} · Scheduled`
    }
  }
  const human = humanizeCron(sched)
  if (human && human !== sched) return `${human} · Scheduled`
  return "Scheduled"
}

export function executionSourceLabel(
  routine: Routine,
  history?: RoutineHistoryRow,
): string {
  const event = (history?.event || "").trim()
  const source = (history?.source || "").toLowerCase()
  const blob = `${event} ${source}`
  const numberMatch = event.match(/#(\d+)/)

  if (numberMatch && /pull_request|\bpr\b|github_pr/i.test(blob)) {
    return `GitHub PR #${numberMatch[1]}`
  }
  if (numberMatch && /issues?/i.test(blob)) {
    return `GitHub issue #${numberMatch[1]}`
  }
  if (event) return event

  if (source === "cron" || source === "schedule") {
    const sched = getRoutineScheduleString(routine)
    const human = humanizeCron(sched)
    if (/daily/i.test(human) || sched === "0 0 * * *" || / \* \* \*$/.test(sched)) {
      return "Daily Cron"
    }
    return human || "Cron"
  }
  if (source === "github_pr_merged") {
    const repo = (routine.trigger as { owner_repo?: string } | undefined)?.owner_repo
    return repo ? `GitHub PR merged · ${repo}` : "GitHub PR merged"
  }
  if (source === "github_webhook") return "GitHub webhook"
  if (source === "test_run") return "Test run"
  if (source) return history?.source || source
  return "Scheduled"
}

export function executionChatHref(agentId: string, conversationId?: string): string {
  const params = new URLSearchParams()
  params.set("agent", agentId)
  params.set("blueprint", agentId)
  if (conversationId) {
    params.set("conversation_id", conversationId)
    params.set("session", conversationId)
  }
  return `/chat?${params.toString()}`
}

export function calendarEntriesForDay(
  routines: Routine[],
  day: CalendarDay,
  mode: CalendarViewMode,
  now: Date = new Date(),
): CalendarEntry[] {
  const entries: CalendarEntry[] = []
  const past = isCalendarDayPast(day, now)

  for (const routine of routines) {
    if (mode !== "upcoming") {
      for (const history of routine.history || []) {
        if (historyDateKey(history.ran_at) === day.dateKey) {
          entries.push({
            kind: "executed",
            id: `exec-${routine.id}-${history.id}`,
            routine,
            history,
          })
        }
      }
    }
    if (mode !== "history" && !past && routineRunsOnDate(routine, day)) {
      entries.push({
        kind: "scheduled",
        id: `sched-${day.dateKey}-${routine.id}`,
        routine,
      })
    }
  }
  return entries
}

function executionStatusClass(status: string | undefined): string {
  const value = (status || "").toLowerCase()
  if (value === "success" || value === "ok" || value === "completed") {
    return "border-success/50 bg-success/10 hover:border-success"
  }
  if (value === "error" || value === "failed" || value === "failure") {
    return "border-error/50 bg-error/10 hover:border-error"
  }
  if (isExecutionInProgress(value)) {
    return "border-warning/50 bg-warning/10 hover:border-warning animate-pulse"
  }
  return "border-base-300 bg-base-200/60 hover:border-base-content/30"
}

function ExecutionStatusIcon({ status }: { status: string | undefined }) {
  const value = (status || "").toLowerCase()
  if (value === "success" || value === "ok" || value === "completed") {
    return <CheckCircle2 className="h-3 w-3 shrink-0 text-success" aria-hidden="true" />
  }
  if (value === "error" || value === "failed" || value === "failure") {
    return <XCircle className="h-3 w-3 shrink-0 text-error" aria-hidden="true" />
  }
  if (isExecutionInProgress(value)) {
    return <Loader2 className="h-3 w-3 shrink-0 text-warning animate-spin" aria-hidden="true" />
  }
  return <Clock className="h-3 w-3 shrink-0 text-base-content/50" aria-hidden="true" />
}

export const AgentCalendarView = memo(function AgentCalendarView({
  open = true,
  onClose,
  initialRoutines,
  agents = [],
  startDate,
  now,
  onSelectRoutine,
  onSelectAgent,
  onSelectExecution,
  defaultApiOnly = true,
  defaultViewMode = "all",
}: AgentCalendarViewProps) {
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const [apiOnly, setApiOnly] = useState(defaultApiOnly)
  const [viewMode, setViewMode] = useState<CalendarViewMode>(defaultViewMode)
  const [selectedEntry, setSelectedEntry] = useState<CalendarEntry | null>(null)
  // #513: empty-day creation. The prefill date is the clicked cell; the agent
  // is the current seat (URL params, same source the rail highlights).
  const [editorPrefill, setEditorPrefill] = useState<{ date: string; agentId: string } | null>(null)
  const railSelection = railSelectionFromParams(new URLSearchParams(location.search))
  const currentAgentId = railSelection.blueprintId || "api_agent"

  const routinesQuery = useQuery({
    queryKey: ["all-routines"],
    queryFn: fetchAllRoutines,
    enabled: open && !initialRoutines,
    retry: 1,
  })

  const rawRoutines = initialRoutines ?? routinesQuery.data ?? []

  const clock = useMemo(() => (now != null ? new Date(now) : new Date()), [now])
  // #513: cells before today do not offer the empty-day `+`.
  const todayKey = useMemo(() => localDateKey(clock), [clock])

  const baseDate = useMemo(() => {
    if (startDate) return new Date(startDate)
    const origin = clock
    return new Date(origin.getFullYear(), origin.getMonth(), 1)
  }, [startDate, clock])

  // REQ-915 / #514: span the whole calendar month (28–31 days), not a fixed 30.
  const days = useMemo(() => getCalendarMonthDays(baseDate, clock), [baseDate, clock])

  const filteredRoutines = useMemo(() => {
    if (!apiOnly) return rawRoutines
    return rawRoutines.filter((r) => isApiAgentRoutine(r, agents))
  }, [rawRoutines, apiOnly, agents])

  const apiCount = useMemo(
    () => rawRoutines.filter((r) => isApiAgentRoutine(r, agents)).length,
    [rawRoutines, agents],
  )

  const selectedRoutine = selectedEntry?.routine ?? null

  if (!open) return null

  const handleAgentClick = (agentId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    onSelectAgent?.(agentId)
    navigate(`/chat?blueprint=${encodeURIComponent(agentId)}`)
    onClose?.()
  }

  const handleOpenExecutionChat = (
    routine: Routine,
    history: RoutineHistoryRow,
    e: React.MouseEvent,
  ) => {
    e.stopPropagation()
    const agentId = routine.agent_id || "api_agent"
    const conversationId = history.conversation_id?.trim() || undefined
    if (conversationId) {
      setConversationIdForAgent(agentId, conversationId)
    }
    onSelectAgent?.(agentId)
    onSelectExecution?.({ routine, history, agentId, conversationId })
    navigate(executionChatHref(agentId, conversationId))
    onClose?.()
  }

  const handleEntryClick = (entry: CalendarEntry) => {
    setSelectedEntry(entry)
    onSelectRoutine?.(entry.routine)
  }

  const agentDisplayName = (routine: Routine) =>
    agents.find((a) => a.id === routine.agent_id)?.name ||
    routine.agent_name ||
    routine.agent_id ||
    "API Agent"

  const editorDialog = editorPrefill ? (
    <RoutineEditorDialog
      open={true}
      prefill={editorPrefill}
      onClose={() => setEditorPrefill(null)}
      onSaved={() => {
        // #513: the created routine must appear on the clicked day
        // immediately — the calendar reads the ["all-routines"] cache.
        void queryClient.invalidateQueries({ queryKey: ["all-routines"] })
      }}
    />
  ) : null
  return (
    <>
      {editorDialog}
      <OverlayFocusTrap onClose={onClose}>
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-2 sm:p-4 backdrop-blur-xs"
      data-testid="agent-calendar-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose?.()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Calendar"
        data-testid="agent-calendar-view"
        className="relative flex flex-col w-full max-w-6xl h-[90vh] bg-base-100 rounded-xl shadow-2xl border border-base-300 overflow-hidden"
      >
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-base-300 px-4 py-3 bg-base-200/50">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
              <CalendarIcon className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <h2 className="text-base font-semibold leading-none flex items-center gap-2">
                <span>Routines Calendar</span>
                <span className="badge badge-sm badge-outline">30 Days</span>
              </h2>
              <p className="text-xs text-base-content/60 mt-0.5">
                {days[0]?.monthName} {days[0]?.dayNumber} – {days[days.length - 1]?.monthName}{" "}
                {days[days.length - 1]?.dayNumber}, {days[0]?.date.getFullYear()}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div
              className="join"
              role="group"
              aria-label="Calendar view"
              data-testid="calendar-view-toggle"
            >
              {(
                [
                  ["all", "All"],
                  ["history", "History"],
                  ["upcoming", "Upcoming"],
                ] as const
              ).map(([mode, label]) => (
                <button
                  key={mode}
                  type="button"
                  className={`join-item btn btn-xs ${viewMode === mode ? "btn-primary" : "btn-ghost"}`}
                  data-testid={`calendar-view-${mode}`}
                  aria-pressed={viewMode === mode}
                  onClick={() => setViewMode(mode)}
                >
                  {label}
                </button>
              ))}
            </div>

            <label
              className="flex items-center gap-2 text-xs font-medium cursor-pointer select-none bg-base-100 px-2.5 py-1.5 rounded-lg border border-base-300 hover:bg-base-200"
              title="Filter routines for API agents"
            >
              <Sparkles className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
              <span>API Agents only</span>
              <input
                type="checkbox"
                data-testid="api-agents-filter"
                className="checkbox checkbox-xs checkbox-primary"
                checked={apiOnly}
                onChange={(e) => setApiOnly(e.target.checked)}
              />
              <span className="badge badge-xs badge-primary">{apiCount}</span>
            </label>

            {onClose && (
              <button
                type="button"
                className="btn btn-ghost btn-xs btn-circle"
                aria-label="Close calendar"
                data-testid="calendar-close-button"
                onClick={onClose}
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            )}
          </div>
        </div>

        <div className="flex-1 overflow-auto p-3 sm:p-4 flex gap-4 min-h-0">
          <div
            data-testid="calendar-grid"
            className="flex-1 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6 gap-2.5 auto-rows-fr overflow-y-auto"
          >
            {days.map((day) => {
              const dayEntries = calendarEntriesForDay(filteredRoutines, day, viewMode, clock)

              return (
                <div
                  key={day.dateKey}
                  data-testid={`calendar-day-${day.dateKey}`}
                  data-date={day.dateKey}
                  className={`flex flex-col min-h-[120px] rounded-lg border p-2 transition-colors ${
                    day.isToday
                      ? "border-primary/60 bg-primary/5 shadow-xs"
                      : "border-base-300 bg-base-100/60 hover:border-base-content/20"
                  }`}
                >
                  <div className="flex items-center justify-between pb-1.5 mb-1.5 border-b border-base-200 text-xs">
                    <span data-testid="calendar-day-cell" className="font-semibold text-base-content/90 flex items-center gap-1">
                      <span>{day.dayNumber}</span>
                      <span className="text-[10px] text-base-content/50 font-normal">
                        {day.monthName}
                      </span>
                    </span>
                    <span
                      className={`text-[10px] px-1 rounded ${
                        day.isToday
                          ? "bg-primary text-primary-content font-bold"
                          : "text-base-content/60"
                      }`}
                    >
                      {day.weekday}
                    </span>
                  </div>

                  <div className="group/cell flex-1 space-y-1.5 overflow-y-auto max-h-[140px] pr-0.5">
                    {dayEntries.length === 0 ? (
                      day.dateKey >= todayKey && viewMode !== "history" ? (
                        <button
                          type="button"
                          className="hidden group-hover/cell:block group-focus-within/cell:block mx-auto mt-1 btn btn-ghost btn-xs btn-circle text-base-content/40 hover:text-primary focus-visible:text-primary"
                          data-testid={`calendar-add-${day.dateKey}`}
                          aria-label={`Add routine on ${day.dateKey}`}
                          onClick={() =>
                            setEditorPrefill({ date: day.dateKey, agentId: currentAgentId })
                          }
                        >
                          <Plus className="h-4 w-4" aria-hidden="true" />
                        </button>
                      ) : (
                        <span className="text-[11px] text-base-content/30 italic block text-center pt-2 select-none">
                          No routines
                        </span>
                      )
                    ) : (
                      dayEntries.map((entry) => {
                        const routine = entry.routine
                        const isApi = isApiAgentRoutine(routine, agents)
                        const sched = getRoutineScheduleString(routine)
                        const humanSched = humanizeCron(sched) || sched || routine.when_to_run || "Scheduled"
                        const agentId = routine.agent_id || "api_agent"
                        const agentName = agentDisplayName(routine)
                        const selected =
                          selectedEntry?.id === entry.id ||
                          (selectedEntry?.kind === entry.kind &&
                            selectedEntry.routine.id === routine.id &&
                            (entry.kind !== "executed" ||
                              (selectedEntry.kind === "executed" &&
                                selectedEntry.history.id === entry.history.id)))

                        if (entry.kind === "executed") {
                          const sourceLabel = executionSourceLabel(routine, entry.history)
                          const clockLabel = formatRunClock(entry.history.ran_at)
                          return (
                            <div
                              key={entry.id}
                              role="button"
                              tabIndex={0}
                              data-testid="execution-card"
                              data-kind="executed"
                              data-status={entry.history.status}
                              data-source={entry.history.source}
                              data-conversation-id={entry.history.conversation_id || ""}
                              data-api-agent={isApi ? "true" : "false"}
                              onClick={() => handleEntryClick(entry)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  handleEntryClick(entry)
                                }
                              }}
                              className={`group relative flex flex-col gap-1 rounded-md p-1.5 text-xs text-left cursor-pointer border border-solid transition-all ${executionStatusClass(
                                entry.history.status,
                              )} ${selected ? "ring-2 ring-primary" : ""}`}
                            >
                              <div className="flex items-center justify-between gap-1">
                                <span
                                  data-testid="routine-name"
                                  className="font-semibold truncate text-[11px] text-base-content leading-tight"
                                  title={routine.name}
                                >
                                  {routine.name}
                                </span>
                                <span
                                  data-testid="execution-status"
                                  className={`badge badge-xs shrink-0 text-[9px] ${
                                    entry.history.status === "success"
                                      ? "badge-success"
                                      : entry.history.status === "error"
                                        ? "badge-error"
                                        : isExecutionInProgress(entry.history.status)
                                          ? "badge-warning"
                                          : "badge-ghost"
                                  }`}
                                >
                                  {entry.history.status}
                                </span>
                              </div>
                              <div className="flex items-center gap-1 text-[10px] text-base-content/70">
                                <ExecutionStatusIcon status={entry.history.status} />
                                <span data-testid="execution-source" className="truncate" title={sourceLabel}>
                                  {clockLabel ? `${clockLabel} · ${sourceLabel}` : sourceLabel}
                                </span>
                              </div>
                            </div>
                          )
                        }

                        return (
                          <div
                            key={entry.id}
                            role="button"
                            tabIndex={0}
                            data-testid="routine-card"
                            data-kind="scheduled"
                            data-api-agent={isApi ? "true" : "false"}
                            onClick={() => handleEntryClick(entry)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                handleEntryClick(entry)
                              }
                            }}
                            className={`group relative flex flex-col gap-1 rounded-md p-1.5 text-xs text-left cursor-pointer border border-dashed transition-all ${
                              isApi
                                ? "border-primary/40 bg-primary/10 hover:border-primary hover:shadow-xs"
                                : "border-base-300 bg-base-200/60 hover:border-base-content/30"
                            } ${selected ? "ring-2 ring-primary" : ""}`}
                          >
                            <div className="flex items-center justify-between gap-1">
                              <span
                                data-testid="routine-name"
                                className="font-semibold truncate text-[11px] text-base-content leading-tight"
                                title={routine.name}
                              >
                                {routine.name}
                              </span>
                              <span
                                data-testid="routine-status"
                                className={`badge badge-xs shrink-0 ${
                                  routine.active
                                    ? "badge-success text-[9px]"
                                    : "badge-ghost text-base-content/40 text-[9px]"
                                }`}
                              >
                                {routine.active ? "Active" : "Paused"}
                              </span>
                            </div>

                            <div className="flex items-center gap-1 text-[10px] text-base-content/70">
                              <Clock className="h-3 w-3 shrink-0 text-base-content/50" />
                              <span
                                data-testid="routine-schedule"
                                className="truncate"
                                title={scheduledRunLabel(routine)}
                              >
                                {humanSched}
                              </span>
                            </div>
                            <span data-testid="scheduled-label" className="sr-only">
                              {scheduledRunLabel(routine)}
                            </span>

                            <div className="flex items-center justify-between gap-1 pt-0.5 mt-0.5 border-t border-base-200/60">
                              <span
                                data-testid="routine-agent-badge"
                                className={`badge badge-xs font-medium truncate max-w-[110px] ${
                                  isApi ? "badge-primary" : "badge-ghost"
                                }`}
                              >
                                {isApi ? `API: ${agentName}` : agentName}
                              </span>
                              {isApi && (
                                <span
                                  data-testid="agent-badge"
                                  className="badge badge-outline badge-primary badge-xs text-[9px] px-1 shrink-0"
                                >
                                  API
                                </span>
                              )}
                              <button
                                type="button"
                                data-testid="routine-agent-link"
                                aria-label={`Chat with ${agentName}`}
                                onClick={(e) => handleAgentClick(agentId, e)}
                                className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 hover:text-primary shrink-0 cursor-pointer"
                                title={`Chat with ${agentName}`}
                              >
                                <ExternalLink className="h-3 w-3" />
                              </button>
                            </div>
                          </div>
                        )
                      })
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          {selectedRoutine && selectedEntry && (
            <div
              data-testid="routine-details-modal"
              data-kind={selectedEntry.kind}
              className="w-80 shrink-0 flex flex-col rounded-lg border border-base-300 bg-base-200/60 p-4 shadow-md overflow-y-auto"
            >
              <div className="flex items-start justify-between gap-2 pb-3 border-b border-base-300">
                <div>
                  <div className="flex items-center gap-1.5 mb-1">
                    {selectedEntry.kind === "executed" ? (
                      <span
                        data-testid="details-status-badge"
                        className={`badge badge-xs ${
                          selectedEntry.history.status === "success"
                            ? "badge-success"
                            : selectedEntry.history.status === "error"
                              ? "badge-error"
                              : isExecutionInProgress(selectedEntry.history.status)
                                ? "badge-warning"
                                : "badge-ghost"
                        }`}
                      >
                        {selectedEntry.history.status}
                      </span>
                    ) : (
                      <span
                        data-testid="details-status-badge"
                        className={`badge badge-xs ${
                          selectedRoutine.active ? "badge-success" : "badge-ghost text-base-content/50"
                        }`}
                      >
                        {selectedRoutine.active ? "Active" : "Paused"}
                      </span>
                    )}
                    {isApiAgentRoutine(selectedRoutine, agents) && (
                      <span className="badge badge-primary badge-xs">API Agent</span>
                    )}
                  </div>
                  <h3 className="font-bold text-sm text-base-content leading-snug">
                    {selectedRoutine.name}
                  </h3>
                </div>
                <button
                  type="button"
                  className="btn btn-ghost btn-xs btn-circle"
                  onClick={() => setSelectedEntry(null)}
                  aria-label="Close routine details"
                  data-testid="routine-details-close-button"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="space-y-3 py-3 text-xs">
                {selectedEntry.kind === "executed" ? (
                  <>
                    <div>
                      <span className="text-base-content/50 uppercase text-[10px] font-bold block mb-0.5">
                        Ran at
                      </span>
                      <div className="flex items-center gap-1.5 font-medium" data-testid="execution-ran-at">
                        <Clock className="h-3.5 w-3.5 text-primary" />
                        <span>
                          {selectedEntry.history.ran_at.slice(0, 16).replace("T", " ")}
                          {formatRunClock(selectedEntry.history.ran_at)
                            ? ` (${formatRunClock(selectedEntry.history.ran_at)})`
                            : ""}
                        </span>
                      </div>
                    </div>
                    <div>
                      <span className="text-base-content/50 uppercase text-[10px] font-bold block mb-0.5">
                        Trigger source
                      </span>
                      <p className="font-medium" data-testid="execution-trigger-source">
                        {executionSourceLabel(selectedRoutine, selectedEntry.history)}
                      </p>
                    </div>
                    <div>
                      <span className="text-base-content/50 uppercase text-[10px] font-bold block mb-0.5">
                        Duration
                      </span>
                      <p data-testid="execution-duration">
                        {formatDuration(selectedEntry.history.duration_ms) || "—"}
                      </p>
                    </div>
                    <div>
                      <span className="text-base-content/50 uppercase text-[10px] font-bold block mb-0.5">
                        Status summary
                      </span>
                      <p data-testid="execution-summary" className="text-[11px] leading-relaxed">
                        {selectedEntry.history.summary || selectedEntry.history.status}
                      </p>
                    </div>
                    <button
                      type="button"
                      data-testid="execution-open-chat-button"
                      className="btn btn-sm btn-primary w-full gap-1"
                      onClick={(e) =>
                        handleOpenExecutionChat(selectedRoutine, selectedEntry.history, e)
                      }
                    >
                      <MessageSquare className="h-3.5 w-3.5" />
                      Open Agent Chat
                    </button>
                  </>
                ) : (
                  <>
                    <div>
                      <span className="text-base-content/50 uppercase text-[10px] font-bold block mb-0.5">
                        Schedule
                      </span>
                      <div className="flex items-center gap-1.5 font-medium">
                        <Clock className="h-3.5 w-3.5 text-primary" />
                        <span>
                          {humanizeCron(getRoutineScheduleString(selectedRoutine)) ||
                            getRoutineScheduleString(selectedRoutine) ||
                            selectedRoutine.when_to_run ||
                            "Event triggered"}
                        </span>
                      </div>
                      {getRoutineScheduleString(selectedRoutine) && (
                        <code className="text-[10px] text-base-content/60 bg-base-300 px-1 py-0.5 rounded mt-1 inline-block">
                          {getRoutineScheduleString(selectedRoutine)}
                        </code>
                      )}
                    </div>

                    <div>
                      <span className="text-base-content/50 uppercase text-[10px] font-bold block mb-0.5">
                        Assigned Agent
                      </span>
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium">{agentDisplayName(selectedRoutine)}</span>
                        <button
                          type="button"
                          data-testid="routine-details-chat-button"
                          className="btn btn-xs btn-primary gap-1"
                          onClick={(e) =>
                            handleAgentClick(selectedRoutine.agent_id || "api_agent", e)
                          }
                        >
                          <MessageSquare className="h-3 w-3" />
                          Chat
                        </button>
                      </div>
                    </div>

                    {selectedRoutine.instruction && (
                      <div>
                        <span className="text-base-content/50 uppercase text-[10px] font-bold block mb-0.5">
                          Instruction
                        </span>
                        <p className="p-2 rounded bg-base-100 border border-base-300/80 text-[11px] leading-relaxed break-words whitespace-pre-wrap">
                          {selectedRoutine.instruction}
                        </p>
                      </div>
                    )}

                    {selectedRoutine.when_to_run && (
                      <div>
                        <span className="text-base-content/50 uppercase text-[10px] font-bold block mb-0.5">
                          Trigger
                        </span>
                        <p className="text-[11px] text-base-content/70">
                          {selectedRoutine.when_to_run}
                        </p>
                      </div>
                    )}

                    {selectedRoutine.history && selectedRoutine.history.length > 0 && (
                      <div>
                        <span className="text-base-content/50 uppercase text-[10px] font-bold block mb-1">
                          Recent Runs ({selectedRoutine.history.length})
                        </span>
                        <div className="space-y-1">
                          {selectedRoutine.history.slice(0, 3).map((h) => (
                            <div
                              key={h.id}
                              className="flex items-center justify-between text-[10px] bg-base-100 px-1.5 py-1 rounded border border-base-200"
                            >
                              <span>{h.ran_at.slice(0, 16).replace("T", " ")}</span>
                              <span
                                className={
                                  h.status === "success" ? "text-success font-medium" : "text-error"
                                }
                              >
                                {h.status}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
      </OverlayFocusTrap>
    </>
  )
})

export default AgentCalendarView
