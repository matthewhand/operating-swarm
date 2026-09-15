import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, fireEvent, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import AgentSidebar from "../AgentSidebar"
import AgentCalendarView, {
  getCalendarDays,
  isApiAgentRoutine,
  routineRunsOnDate,
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

    // With agents list where kind is api
    expect(
      isApiAgentRoutine(nonApiRoutine, [{ id: "codey", name: "Codey", kind: "api" }]),
    ).toBe(true)
  })

  it("routineRunsOnDate checks weekday, specific date, and daily schedules", () => {
    const monday: any = {
      date: new Date(2026, 8, 7), // 2026-09-07 is Monday
      dateKey: "2026-09-07",
      dayNumber: 7,
      monthNumber: 9,
      monthName: "Sep",
      weekday: "Mon",
      dayOfWeek: 1,
    }
    const sunday: any = {
      date: new Date(2026, 8, 6), // 2026-09-06 is Sunday
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
        { id: "h1", ran_at: "2026-09-14T09:00:00Z", status: "success", source: "cron" },
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
  ]

  it("renders 30-day calendar days grid", () => {
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={new Date(2026, 8, 1)}
        initialRoutines={[]}
      />,
    )

    expect(screen.getByTestId("agent-calendar-view")).toBeInTheDocument()
    expect(screen.getByTestId("calendar-grid")).toBeInTheDocument()

    const dayCells = screen.getAllByTestId("calendar-day-cell")
    expect(dayCells).toHaveLength(30)

    // Check specific days in September 2026
    expect(screen.getByTestId("calendar-day-2026-09-01")).toBeInTheDocument()
    expect(screen.getByTestId("calendar-day-2026-09-30")).toBeInTheDocument()
  })

  it("overlays routines on scheduled dates", () => {
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={new Date(2026, 8, 1)} // Sept 1 is Tuesday
        initialRoutines={sampleRoutines}
        defaultApiOnly={false}
      />,
    )

    // 2026-09-01 is Tuesday (weekday): API Data Sync and CLI Worker Routine should be present
    const tuesdayCell = screen.getByTestId("calendar-day-2026-09-01")
    expect(within(tuesdayCell).getByText("API Data Sync")).toBeInTheDocument()
    expect(within(tuesdayCell).getByText("CLI Worker Routine")).toBeInTheDocument()

    // 2026-09-06 is Sunday: Weekday routines should NOT be present, but daily Paused Routine should be present
    const sundayCell = screen.getByTestId("calendar-day-2026-09-06")
    expect(within(sundayCell).queryByText("API Data Sync")).not.toBeInTheDocument()
    expect(within(sundayCell).getByText("Paused Routine")).toBeInTheDocument()
  })

  it("filters and highlights API agent routines with badges and schedule info", () => {
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={new Date(2026, 8, 1)}
        initialRoutines={sampleRoutines}
        defaultApiOnly={true}
      />,
    )

    // With API agents only, codey (CLI) should be filtered out
    const tuesdayCell = screen.getByTestId("calendar-day-2026-09-01")
    expect(within(tuesdayCell).getByText("API Data Sync")).toBeInTheDocument()
    expect(within(tuesdayCell).queryByText("CLI Worker Routine")).not.toBeInTheDocument()

    // Routine pill displays API badges, schedule info, and status
    const routineCard = within(tuesdayCell).getByText("API Data Sync").closest('[data-testid="routine-card"]') as HTMLElement
    expect(routineCard).toHaveAttribute("data-api-agent", "true")

    expect(within(routineCard).getByTestId("routine-agent-badge")).toHaveTextContent(/api_agent/i)
    expect(within(routineCard).getByTestId("agent-badge")).toHaveTextContent("API")
    expect(within(routineCard).getByTestId("routine-schedule")).toHaveTextContent(/Weekdays at 09:00|0 9 \* \* 1-5/)
    expect(within(routineCard).getByTestId("routine-status")).toHaveTextContent("Active")

    // Paused routine check
    const dailyCell = screen.getByTestId("calendar-day-2026-09-02")
    const pausedCard = within(dailyCell).getByText("Paused Routine").closest('[data-testid="routine-card"]') as HTMLElement
    expect(within(pausedCard).getByTestId("routine-status")).toHaveTextContent("Paused")

    // Toggle off API filter: CLI agent routine should now appear
    const filterCheckbox = screen.getByTestId("api-agents-filter")
    fireEvent.click(filterCheckbox)
    expect(within(screen.getByTestId("calendar-day-2026-09-01")).getByText("CLI Worker Routine")).toBeInTheDocument()
  })

  it("clicking routine card opens details and triggers onSelectRoutine", () => {
    const onSelectRoutine = vi.fn()
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={new Date(2026, 8, 1)}
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

    // Close details
    fireEvent.click(screen.getByTestId("routine-details-close-button"))
    expect(screen.queryByTestId("routine-details-modal")).not.toBeInTheDocument()
  })

  it("clicking agent link navigates to chat and triggers onSelectAgent", () => {
    const onSelectAgent = vi.fn()
    const onClose = vi.fn()

    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={new Date(2026, 8, 1)}
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
        startDate={new Date(2026, 8, 1)}
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
        startDate={new Date(2026, 8, 1)}
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
          startDate={new Date(2026, 8, 1)}
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

    // Calendar starts closed
    expect(screen.queryByTestId("agent-calendar-view")).not.toBeInTheDocument()

    // Clicking Calendar opens calendar view
    fireEvent.click(calendarBtn)
    expect(screen.getByTestId("agent-calendar-view")).toBeInTheDocument()
  })

})
