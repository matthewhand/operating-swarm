import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, fireEvent, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import AgentSidebar from "../AgentSidebar"
import AgentCalendarView, {
  calendarEntriesForDay,
  executionChatHref,
  executionSourceLabel,
  formatDuration,
  getCalendarDays,
  isApiAgentRoutine,
  routineRunsOnDate,
  scheduledRunLabel,
} from "../AgentCalendarView"
import type { Routine } from "../../lib/routines"

const mockNavigate = vi.fn()
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom")
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

const VIEW_START = new Date(2026, 8, 1)
const VIEW_NOW = new Date(2026, 8, 1)
const HISTORY_NOW = new Date(2026, 8, 16)

describe("AgentCalendarView unit helpers", () => {
  it("getCalendarDays returns exactly 30 days starting from base date", () => {
    const start = new Date(2026, 8, 1) // 2026-09-01
    const days = getCalendarDays(start, 30)
    expect(days).toHaveLength(30)
    expect(days[0].dateKey).toBe("2026-09-01")
    expect(days[29].dateKey).toBe("2026-09-30")
    expect(days[0].dayNumber).toBe(1)
    expect(days[0].monthName).toBe("Sep")
  })

  it("isApiAgentRoutine correctly identifies API agents", () => {
    const apiRoutine: Routine = {
      id: "r1",
      name: "API Sync",
      instruction: "Do things",
      active: true,
      trigger: { kind: "github_pr_merged", owner_repo: "a/b", event: "merged", actor: "anyone" },
      history: [],
      agent_id: "api_agent",
    }
    expect(isApiAgentRoutine(apiRoutine)).toBe(true)

    const prefixedApiRoutine: Routine = {
      ...apiRoutine,
      agent_id: "api:custom-agent",
    }
    expect(isApiAgentRoutine(prefixedApiRoutine)).toBe(true)

    const nonApiRoutine: Routine = {
      ...apiRoutine,
      agent_id: "codey",
    }
    expect(isApiAgentRoutine(nonApiRoutine)).toBe(false)

    expect(
      isApiAgentRoutine(nonApiRoutine, [{ id: "codey", name: "Codey", kind: "api" }]),
    ).toBe(true)
  })

  it("routineRunsOnDate checks weekday, specific date, and daily schedules", () => {
    const monday: any = {
      date: new Date(2026, 8, 7),
      dateKey: "2026-09-07",
      dayNumber: 7,
      monthNumber: 9,
      monthName: "Sep",
      weekday: "Mon",
      dayOfWeek: 1,
    }
    const sunday: any = {
      date: new Date(2026, 8, 6),
      dateKey: "2026-09-06",
      dayNumber: 6,
      monthNumber: 9,
      monthName: "Sep",
      weekday: "Sun",
      dayOfWeek: 0,
    }

    const weekdayRoutine: Routine = {
      id: "r1",
      name: "Weekday Job",
      instruction: "run",
      active: true,
      trigger: { kind: "github_pr_merged", owner_repo: "a/b", event: "merged", actor: "anyone" },
      history: [],
      cron: "0 9 * * 1-5",
    }
    expect(routineRunsOnDate(weekdayRoutine, monday)).toBe(true)
    expect(routineRunsOnDate(weekdayRoutine, sunday)).toBe(false)

    const exactDateRoutine: Routine = {
      ...weekdayRoutine,
      cron: undefined,
      next_run: "2026-09-07T09:00:00Z",
    }
    expect(routineRunsOnDate(exactDateRoutine, monday)).toBe(true)
    expect(routineRunsOnDate(exactDateRoutine, sunday)).toBe(false)

    const dailyRoutine: Routine = {
      ...weekdayRoutine,
      cron: "0 0 * * *",
    }
    expect(routineRunsOnDate(dailyRoutine, monday)).toBe(true)
    expect(routineRunsOnDate(dailyRoutine, sunday)).toBe(true)
  })

  it("routineRunsOnDate does not treat history as a schedule", () => {
    const monday: any = {
      date: new Date(2026, 8, 7),
      dateKey: "2026-09-07",
      dayNumber: 7,
      monthNumber: 9,
      monthName: "Sep",
      weekday: "Mon",
      dayOfWeek: 1,
    }
    const eventRoutine: Routine = {
      id: "r-event",
      name: "PR Reviewer",
      instruction: "review",
      active: true,
      trigger: { kind: "github_pr_merged", owner_repo: "a/b", event: "merged", actor: "anyone" },
      history: [{ id: "h1", ran_at: "2026-09-07T15:00:00Z", status: "success", source: "github_webhook" }],
    }
    expect(routineRunsOnDate(eventRoutine, monday)).toBe(false)
  })

  it("executionSourceLabel and duration helpers describe executed runs", () => {
    const routine: Routine = {
      id: "r1",
      name: "API Data Sync",
      instruction: "run",
      active: true,
      cron: "0 9 * * *",
      trigger: { kind: "github_pr_merged", owner_repo: "owner/repo", event: "merged", actor: "anyone" },
      history: [],
    }
    expect(
      executionSourceLabel(routine, {
        id: "h1",
        ran_at: "2026-09-14T09:00:00Z",
        status: "success",
        source: "github_webhook",
        event: "pull_request.opened #42",
      }),
    ).toBe("GitHub PR #42")
    expect(
      executionSourceLabel(routine, {
        id: "h2",
        ran_at: "2026-09-14T09:00:00Z",
        status: "success",
        source: "cron",
      }),
    ).toBe("Daily Cron")
    expect(formatDuration(12_500)).toBe("12s")
    expect(formatDuration(125_000)).toBe("2m 5s")
    expect(formatDuration(undefined)).toBe("")
    expect(scheduledRunLabel(routine)).toBe("9:00 AM · Scheduled")
    expect(executionChatHref("api_agent", "conv-github-pr-42")).toContain("conversation_id=conv-github-pr-42")
    expect(executionChatHref("api_agent", "conv-github-pr-42")).toContain("agent=api_agent")
  })

  it("calendarEntriesForDay overlays executed history and upcoming schedules by view mode", () => {
    const days = getCalendarDays(VIEW_START, 30, HISTORY_NOW)
    const sept14 = days.find((d) => d.dateKey === "2026-09-14")!
    const sept17 = days.find((d) => d.dateKey === "2026-09-17")!
    const routine: Routine = {
      id: "routine-api-1",
      name: "API Data Sync",
      instruction: "Fetch remote telemetry daily",
      active: true,
      agent_id: "api_agent",
      cron: "0 9 * * 1-5",
      trigger: { kind: "github_pr_merged", owner_repo: "owner/repo", event: "merged", actor: "anyone" },
      history: [
        {
          id: "h1",
          ran_at: "2026-09-14T09:00:00Z",
          status: "success",
          source: "cron",
          conversation_id: "conv-cron-h1",
        },
      ],
    }

    const allPast = calendarEntriesForDay([routine], sept14, "all", HISTORY_NOW)
    expect(allPast.map((e) => e.kind)).toEqual(["executed"])
    expect(allPast[0].kind === "executed" && allPast[0].history.conversation_id).toBe("conv-cron-h1")

    const historyOnly = calendarEntriesForDay([routine], sept14, "history", HISTORY_NOW)
    expect(historyOnly).toHaveLength(1)
    expect(historyOnly[0].kind).toBe("executed")

    const upcomingPast = calendarEntriesForDay([routine], sept14, "upcoming", HISTORY_NOW)
    expect(upcomingPast).toHaveLength(0)

    const allFuture = calendarEntriesForDay([routine], sept17, "all", HISTORY_NOW)
    expect(allFuture.map((e) => e.kind)).toEqual(["scheduled"])
    const historyFuture = calendarEntriesForDay([routine], sept17, "history", HISTORY_NOW)
    expect(historyFuture).toHaveLength(0)
  })
})

describe("AgentCalendarView component", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const sampleRoutines: Routine[] = [
    {
      id: "routine-api-1",
      name: "API Data Sync",
      instruction: "Fetch remote telemetry daily",
      active: true,
      agent_id: "api_agent",
      cron: "0 9 * * 1-5",
      trigger: { kind: "github_pr_merged", owner_repo: "owner/repo", event: "merged", actor: "anyone" },
      history: [
        {
          id: "h1",
          ran_at: "2026-09-14T09:00:00Z",
          status: "success",
          source: "cron",
          conversation_id: "conv-cron-h1",
          duration_ms: 12500,
          summary: "Synced telemetry successfully.",
        },
      ],
    },
    {
      id: "routine-api-paused",
      name: "Paused Routine",
      instruction: "Nightly backup",
      active: false,
      agent_id: "api:backup-bot",
      cron: "0 0 * * *",
      trigger: { kind: "github_pr_merged", owner_repo: "owner/repo", event: "merged", actor: "anyone" },
      history: [],
    },
    {
      id: "routine-cli-1",
      name: "CLI Worker Routine",
      instruction: "Process code",
      active: true,
      agent_id: "codey",
      cron: "0 9 * * 1-5",
      trigger: { kind: "github_pr_merged", owner_repo: "owner/repo", event: "merged", actor: "anyone" },
      history: [],
    },
    {
      id: "routine-gh-1",
      name: "PR Reviewer",
      instruction: "Review the pull request",
      active: true,
      agent_id: "api_agent",
      trigger: { kind: "github_pr_merged", owner_repo: "owner/repo", event: "merged", actor: "anyone" },
      history: [
        {
          id: "gh1",
          ran_at: "2026-09-14T15:00:00Z",
          status: "success",
          source: "github_webhook",
          event: "pull_request.opened #42",
          conversation_id: "conv-github-pr-42",
          duration_ms: 4500,
          summary: "Reviewed GitHub PR #42.",
        },
        {
          id: "gh-error",
          ran_at: "2026-09-13T18:00:00Z",
          status: "error",
          source: "github_webhook",
          event: "issues.opened #9",
          conversation_id: "conv-github-issue-9",
          duration_ms: 800,
          summary: "Triage failed.",
        },
        {
          id: "gh-running",
          ran_at: "2026-09-16T08:00:00Z",
          status: "running",
          source: "github_webhook",
          event: "push main",
          conversation_id: "conv-github-push-main",
        },
      ],
    },
  ]

  it("renders 30-day calendar days grid", () => {
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={VIEW_START}
        now={VIEW_NOW}
        initialRoutines={[]}
      />,
    )

    expect(screen.getByTestId("agent-calendar-view")).toBeInTheDocument()
    expect(screen.getByTestId("calendar-grid")).toBeInTheDocument()

    const dayCells = screen.getAllByTestId("calendar-day-cell")
    expect(dayCells).toHaveLength(30)

    expect(screen.getByTestId("calendar-day-2026-09-01")).toBeInTheDocument()
    expect(screen.getByTestId("calendar-day-2026-09-30")).toBeInTheDocument()
  })

  it("overlays routines on scheduled dates", () => {
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={VIEW_START}
        now={VIEW_NOW}
        initialRoutines={sampleRoutines}
        defaultApiOnly={false}
      />,
    )

    const tuesdayCell = screen.getByTestId("calendar-day-2026-09-01")
    expect(within(tuesdayCell).getByText("API Data Sync")).toBeInTheDocument()
    expect(within(tuesdayCell).getByText("CLI Worker Routine")).toBeInTheDocument()

    const sundayCell = screen.getByTestId("calendar-day-2026-09-06")
    expect(within(sundayCell).queryByText("API Data Sync")).not.toBeInTheDocument()
    expect(within(sundayCell).getByText("Paused Routine")).toBeInTheDocument()
  })

  it("filters and highlights API agent routines with badges and schedule info", () => {
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={VIEW_START}
        now={VIEW_NOW}
        initialRoutines={sampleRoutines}
        defaultApiOnly={true}
      />,
    )

    const tuesdayCell = screen.getByTestId("calendar-day-2026-09-01")
    expect(within(tuesdayCell).getByText("API Data Sync")).toBeInTheDocument()
    expect(within(tuesdayCell).queryByText("CLI Worker Routine")).not.toBeInTheDocument()

    const routineCard = within(tuesdayCell).getByText("API Data Sync").closest('[data-testid="routine-card"]') as HTMLElement
    expect(routineCard).toHaveAttribute("data-api-agent", "true")

    expect(within(routineCard).getByTestId("routine-agent-badge")).toHaveTextContent(/api_agent/i)
    expect(within(routineCard).getByTestId("agent-badge")).toHaveTextContent("API")
    expect(within(routineCard).getByTestId("routine-schedule")).toHaveTextContent(/Weekdays at 09:00|0 9 \* \* 1-5/)
    expect(within(routineCard).getByTestId("routine-status")).toHaveTextContent("Active")

    const dailyCell = screen.getByTestId("calendar-day-2026-09-02")
    const pausedCard = within(dailyCell).getByText("Paused Routine").closest('[data-testid="routine-card"]') as HTMLElement
    expect(within(pausedCard).getByTestId("routine-status")).toHaveTextContent("Paused")

    const filterCheckbox = screen.getByTestId("api-agents-filter")
    fireEvent.click(filterCheckbox)
    expect(within(screen.getByTestId("calendar-day-2026-09-01")).getByText("CLI Worker Routine")).toBeInTheDocument()
  })

  it("clicking routine card opens details and triggers onSelectRoutine", () => {
    const onSelectRoutine = vi.fn()
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={VIEW_START}
        now={VIEW_NOW}
        initialRoutines={sampleRoutines}
        onSelectRoutine={onSelectRoutine}
      />,
    )

    const tuesdayCell = screen.getByTestId("calendar-day-2026-09-01")
    const routineCard = within(tuesdayCell).getByText("API Data Sync").closest('[data-testid="routine-card"]') as HTMLElement

    fireEvent.click(routineCard)

    expect(onSelectRoutine).toHaveBeenCalledWith(expect.objectContaining({ name: "API Data Sync" }))
    expect(screen.getByTestId("routine-details-modal")).toBeInTheDocument()
    expect(within(screen.getByTestId("routine-details-modal")).getByText("Fetch remote telemetry daily")).toBeInTheDocument()

    fireEvent.click(screen.getByTestId("routine-details-close-button"))
    expect(screen.queryByTestId("routine-details-modal")).not.toBeInTheDocument()
  })

  it("clicking agent link navigates to chat and triggers onSelectAgent", () => {
    const onSelectAgent = vi.fn()
    const onClose = vi.fn()

    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={VIEW_START}
        now={VIEW_NOW}
        initialRoutines={sampleRoutines}
        onSelectAgent={onSelectAgent}
        onClose={onClose}
      />,
    )

    const tuesdayCell = screen.getByTestId("calendar-day-2026-09-01")
    const agentLink = within(tuesdayCell).getAllByTestId("routine-agent-link")[0]

    fireEvent.click(agentLink)

    expect(onSelectAgent).toHaveBeenCalledWith("api_agent")
    expect(mockNavigate).toHaveBeenCalledWith("/chat?blueprint=api_agent")
    expect(onClose).toHaveBeenCalled()
  })

  it("clicking chat button inside routine details navigates to agent chat", () => {
    const onSelectAgent = vi.fn()
    const onClose = vi.fn()

    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={VIEW_START}
        now={VIEW_NOW}
        initialRoutines={sampleRoutines}
        onSelectAgent={onSelectAgent}
        onClose={onClose}
      />,
    )

    const tuesdayCell = screen.getByTestId("calendar-day-2026-09-01")
    const routineCard = within(tuesdayCell).getByText("API Data Sync").closest('[data-testid="routine-card"]') as HTMLElement
    fireEvent.click(routineCard)

    const chatButton = screen.getByTestId("routine-details-chat-button")
    fireEvent.click(chatButton)

    expect(onSelectAgent).toHaveBeenCalledWith("api_agent")
    expect(mockNavigate).toHaveBeenCalledWith("/chat?blueprint=api_agent")
  })

  it("clicking calendar close button triggers onClose", () => {
    const onClose = vi.fn()
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={VIEW_START}
        now={VIEW_NOW}
        initialRoutines={[]}
        onClose={onClose}
      />,
    )

    fireEvent.click(screen.getByTestId("calendar-close-button"))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it("returns null when open is false", () => {
    const { container } = renderWithProviders(
      <AgentCalendarView open={false} />,
    )
    expect(container.firstChild).toBeNull()
  })

  it("fetches routines from /v1/routines when initialRoutines is omitted", async () => {
    const originalFetch = globalThis.fetch
    globalThis.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes("/v1/routines")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ object: "routine_list", routines: sampleRoutines }),
        })
      }
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({}),
      })
    })

    try {
      renderWithProviders(
        <AgentCalendarView
          open={true}
          startDate={VIEW_START}
          now={VIEW_NOW}
        />,
      )

      const tuesdayCell = await screen.findByTestId("calendar-day-2026-09-01")
      expect(await within(tuesdayCell).findByText("API Data Sync")).toBeInTheDocument()
    } finally {
      globalThis.fetch = originalFetch
    }
  })

  it("AgentSidebar footer contains Calendar button that opens AgentCalendarView", () => {
    renderWithProviders(<AgentSidebar open={true} />)

    const calendarBtn = screen.getByTestId("os-calendar-button")
    expect(calendarBtn).toBeInTheDocument()
    expect(calendarBtn).toHaveAttribute("title", "Calendar")
    expect(within(calendarBtn).getByText("Calendar")).toBeInTheDocument()

    expect(screen.queryByTestId("agent-calendar-view")).not.toBeInTheDocument()

    fireEvent.click(calendarBtn)
    expect(screen.getByTestId("agent-calendar-view")).toBeInTheDocument()
  })

  it("renders executed runs in calendar day cells with status styling", () => {
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={VIEW_START}
        now={HISTORY_NOW}
        initialRoutines={sampleRoutines}
        defaultApiOnly={false}
      />,
    )

    const sept14 = screen.getByTestId("calendar-day-2026-09-14")
    const executed = within(sept14).getAllByTestId("execution-card")
    expect(executed.length).toBeGreaterThanOrEqual(2)

    const cronRun = executed.find((el) => el.getAttribute("data-source") === "cron") as HTMLElement
    expect(cronRun).toHaveAttribute("data-status", "success")
    expect(within(cronRun).getByTestId("execution-status")).toHaveTextContent("success")
    expect(within(cronRun).getByTestId("execution-source")).toHaveTextContent(/Weekdays at 09:00|Daily Cron/)

    const prRun = executed.find((el) => el.getAttribute("data-conversation-id") === "conv-github-pr-42") as HTMLElement
    expect(prRun).toHaveAttribute("data-status", "success")
    expect(within(prRun).getByTestId("execution-source")).toHaveTextContent("GitHub PR #42")

    const sept13 = screen.getByTestId("calendar-day-2026-09-13")
    const errorCard = within(sept13).getByTestId("execution-card")
    expect(errorCard).toHaveAttribute("data-status", "error")
    expect(within(errorCard).getByTestId("execution-status")).toHaveTextContent("error")

    const sept16 = screen.getByTestId("calendar-day-2026-09-16")
    const runningCard = within(sept16).getByTestId("execution-card")
    expect(runningCard).toHaveAttribute("data-status", "running")
    expect(runningCard.className).toMatch(/animate-pulse/)
  })

  it("view filter toggle filters between upcoming and historical runs", () => {
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={VIEW_START}
        now={HISTORY_NOW}
        initialRoutines={sampleRoutines}
        defaultApiOnly={false}
      />,
    )

    expect(screen.getByTestId("calendar-view-toggle")).toBeInTheDocument()
    expect(screen.getByTestId("calendar-view-all")).toHaveAttribute("aria-pressed", "true")

    const sept14 = () => screen.getByTestId("calendar-day-2026-09-14")
    const sept17 = () => screen.getByTestId("calendar-day-2026-09-17")

    expect(within(sept14()).getAllByTestId("execution-card").length).toBeGreaterThan(0)
    expect(within(sept14()).queryByTestId("routine-card")).not.toBeInTheDocument()
    expect(within(sept17()).getAllByTestId("routine-card").length).toBeGreaterThan(0)
    expect(within(sept17()).queryByTestId("execution-card")).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId("calendar-view-history"))
    expect(screen.getByTestId("calendar-view-history")).toHaveAttribute("aria-pressed", "true")
    expect(within(sept14()).getAllByTestId("execution-card").length).toBeGreaterThan(0)
    expect(within(sept17()).queryByTestId("routine-card")).not.toBeInTheDocument()
    expect(within(sept17()).queryByTestId("execution-card")).not.toBeInTheDocument()

    fireEvent.click(screen.getByTestId("calendar-view-upcoming"))
    expect(screen.getByTestId("calendar-view-upcoming")).toHaveAttribute("aria-pressed", "true")
    expect(within(sept14()).queryByTestId("execution-card")).not.toBeInTheDocument()
    expect(within(sept17()).getAllByTestId("routine-card").length).toBeGreaterThan(0)
  })

  it("clicking an executed run shows details and Open Agent Chat navigates with conversation_id", () => {
    const onSelectExecution = vi.fn()
    const onSelectAgent = vi.fn()
    const onClose = vi.fn()

    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={VIEW_START}
        now={HISTORY_NOW}
        initialRoutines={sampleRoutines}
        onSelectExecution={onSelectExecution}
        onSelectAgent={onSelectAgent}
        onClose={onClose}
      />,
    )

    const sept14 = screen.getByTestId("calendar-day-2026-09-14")
    const prCard = within(sept14)
      .getAllByTestId("execution-card")
      .find((el) => el.getAttribute("data-conversation-id") === "conv-github-pr-42") as HTMLElement
    fireEvent.click(prCard)

    const details = screen.getByTestId("routine-details-modal")
    expect(details).toHaveAttribute("data-kind", "executed")
    expect(within(details).getByTestId("execution-ran-at")).toHaveTextContent("2026-09-14")
    expect(within(details).getByTestId("execution-trigger-source")).toHaveTextContent("GitHub PR #42")
    expect(within(details).getByTestId("execution-duration")).toHaveTextContent("4s")
    expect(within(details).getByTestId("execution-summary")).toHaveTextContent("Reviewed GitHub PR #42.")

    fireEvent.click(screen.getByTestId("execution-open-chat-button"))

    expect(onSelectAgent).toHaveBeenCalledWith("api_agent")
    expect(onSelectExecution).toHaveBeenCalledWith(
      expect.objectContaining({
        agentId: "api_agent",
        conversationId: "conv-github-pr-42",
      }),
    )
    expect(mockNavigate).toHaveBeenCalled()
    const href = String(mockNavigate.mock.calls[0][0])
    expect(href).toContain("conversation_id=conv-github-pr-42")
    expect(href).toContain("agent=api_agent")
    expect(onClose).toHaveBeenCalled()
  })
})
