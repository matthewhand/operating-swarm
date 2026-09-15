import { memo, useMemo, useState } from "react"
import { useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import {
  Calendar as CalendarIcon,
  Clock,
  ExternalLink,
  MessageSquare,
  Sparkles,
  X,
} from "lucide-react"
import { fetchAllRoutines, type Routine } from "../lib/routines"
import { isApiBlueprintId } from "../lib/cliAgentContext"
import { humanizeCron } from "./RemotesSettings"

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

export interface AgentCalendarViewProps {
  open?: boolean
  onClose?: () => void
  initialRoutines?: Routine[]
  agents?: Array<{ id: string; name?: string; kind?: string; description?: string }>
  startDate?: Date | string | number
  onSelectRoutine?: (routine: Routine) => void
  onSelectAgent?: (agentId: string) => void
  defaultApiOnly?: boolean
}

export function getCalendarDays(baseDate: Date, count: number = 30): CalendarDay[] {
  const days: CalendarDay[] = []
  const today = new Date()
  const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`

  for (let i = 0; i < count; i++) {
    const d = new Date(baseDate.getFullYear(), baseDate.getMonth(), baseDate.getDate() + i)
    const year = d.getFullYear()
    const month = String(d.getMonth() + 1).padStart(2, "0")
    const day = String(d.getDate()).padStart(2, "0")
    const dateKey = `${year}-${month}-${day}`
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
  agentsList?: Array<{ id: string; name?: string; kind?: string }>,
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
  // Check exact next_run ISO date
  if (routine.next_run && routine.next_run.slice(0, 10) === day.dateKey) {
    return true
  }

  const sched = getRoutineScheduleString(routine).toLowerCase()
  if (!sched) {
    // If routine ran in history on this day
    if (routine.history?.some((h) => h.ran_at && h.ran_at.slice(0, 10) === day.dateKey)) {
      return true
    }
    return false
  }

  // Exact date match (e.g. 2026-09-15)
  if (sched === day.dateKey || sched.startsWith(day.dateKey)) {
    return true
  }

  // Standard 5-part cron
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

  // Human word schedules
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

export const AgentCalendarView = memo(function AgentCalendarView({
  open = true,
  onClose,
  initialRoutines,
  agents = [],
  startDate,
  onSelectRoutine,
  onSelectAgent,
  defaultApiOnly = true,
}: AgentCalendarViewProps) {
  const navigate = useNavigate()
  const [apiOnly, setApiOnly] = useState(defaultApiOnly)
  const [selectedRoutine, setSelectedRoutine] = useState<Routine | null>(null)

  const routinesQuery = useQuery({
    queryKey: ["all-routines"],
    queryFn: fetchAllRoutines,
    enabled: open && !initialRoutines,
    retry: 1,
  })

  const rawRoutines = initialRoutines ?? routinesQuery.data ?? []

  const baseDate = useMemo(() => {
    if (startDate) return new Date(startDate)
    const now = new Date()
    return new Date(now.getFullYear(), now.getMonth(), 1)
  }, [startDate])

  const days = useMemo(() => getCalendarDays(baseDate, 30), [baseDate])

  const filteredRoutines = useMemo(() => {
    if (!apiOnly) return rawRoutines
    return rawRoutines.filter((r) => isApiAgentRoutine(r, agents))
  }, [rawRoutines, apiOnly, agents])

  const apiCount = useMemo(
    () => rawRoutines.filter((r) => isApiAgentRoutine(r, agents)).length,
    [rawRoutines, agents],
  )

  if (!open) return null

  const handleAgentClick = (agentId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    onSelectAgent?.(agentId)
    navigate(`/chat?blueprint=${encodeURIComponent(agentId)}`)
    onClose?.()
  }

  const handleRoutineClick = (routine: Routine) => {
    setSelectedRoutine(routine)
    onSelectRoutine?.(routine)
  }

  return (
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
        {/* Header */}
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
            {/* API Agent MVP Filter Toggle */}
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

        {/* Main Content Area: Grid + Optional Details Pane */}
        <div className="flex-1 overflow-auto p-3 sm:p-4 flex gap-4 min-h-0">
          {/* 30-Day Grid */}
          <div
            data-testid="calendar-grid"
            className="flex-1 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 xl:grid-cols-6 gap-2.5 auto-rows-fr overflow-y-auto"
          >
            {days.map((day) => {
              const dayRoutines = filteredRoutines.filter((r) => routineRunsOnDate(r, day))

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
                  {/* Day Header */}
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

                  {/* Routines List for Day */}
                  <div className="flex-1 space-y-1.5 overflow-y-auto max-h-[140px] pr-0.5">
                    {dayRoutines.length === 0 ? (
                      <span className="text-[11px] text-base-content/30 italic block text-center pt-2 select-none">
                        No routines
                      </span>
                    ) : (
                      dayRoutines.map((routine) => {
                        const isApi = isApiAgentRoutine(routine, agents)
                        const sched = getRoutineScheduleString(routine)
                        const humanSched = humanizeCron(sched) || sched || routine.when_to_run || "Scheduled"
                        const agentId = routine.agent_id || "api_agent"
                        const agentName =
                          agents.find((a) => a.id === routine.agent_id)?.name ||
                          routine.agent_name ||
                          routine.agent_id ||
                          "API Agent"

                        return (
                          <div
                            key={`${day.dateKey}-${routine.id}`}
                            role="button"
                            tabIndex={0}
                            data-testid="routine-card"
                            data-api-agent={isApi ? "true" : "false"}
                            onClick={() => handleRoutineClick(routine)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                handleRoutineClick(routine)
                              }
                            }}
                            className={`group relative flex flex-col gap-1 rounded-md p-1.5 text-xs text-left cursor-pointer border transition-all ${
                              isApi
                                ? "border-primary/40 bg-primary/10 hover:border-primary hover:shadow-xs"
                                : "border-base-300 bg-base-200/60 hover:border-base-content/30"
                            } ${selectedRoutine?.id === routine.id ? "ring-2 ring-primary" : ""}`}
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

                            {/* Schedule info */}
                            <div className="flex items-center gap-1 text-[10px] text-base-content/70">
                              <Clock className="h-3 w-3 shrink-0 text-base-content/50" />
                              <span
                                data-testid="routine-schedule"
                                className="truncate"
                                title={sched || humanSched}
                              >
                                {humanSched}
                              </span>
                            </div>

                            {/* Agent Badge & Link */}
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

          {/* Routine Details Pane (when a routine is clicked) */}
          {selectedRoutine && (
            <div
              data-testid="routine-details-modal"
              className="w-80 shrink-0 flex flex-col rounded-lg border border-base-300 bg-base-200/60 p-4 shadow-md overflow-y-auto"
            >
              <div className="flex items-start justify-between gap-2 pb-3 border-b border-base-300">
                <div>
                  <div className="flex items-center gap-1.5 mb-1">
                    <span
                      data-testid="details-status-badge"
                      className={`badge badge-xs ${
                        selectedRoutine.active ? "badge-success" : "badge-ghost text-base-content/50"
                      }`}
                    >
                      {selectedRoutine.active ? "Active" : "Paused"}
                    </span>
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
                  onClick={() => setSelectedRoutine(null)}
                  aria-label="Close routine details"
                  data-testid="routine-details-close-button"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              <div className="space-y-3 py-3 text-xs">
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
                    <span className="font-medium">
                      {agents.find((a) => a.id === selectedRoutine.agent_id)?.name ||
                        selectedRoutine.agent_name ||
                        selectedRoutine.agent_id ||
                        "api_agent"}
                    </span>
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
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
})

export default AgentCalendarView
