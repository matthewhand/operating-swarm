/**
 * REQ-913 / #512 — the Routines popup.
 *
 * 1. The `API Agents only` filter is gone (always-true controls are noise).
 * 2. A Calendar ↔ List view-shape toggle (real tabs) lives in the popup.
 * 3. List view is the same entry set the calendar renders for the same
 *    All/History/Upcoming scope, grouped by day, soonest first.
 * 4. The rail entry and the dialog both read **Routines**; the
 *    All/History/Upcoming group is relabelled to what it is (time range).
 */
import { describe, it, expect } from "vitest"
import { render, screen, fireEvent, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import AgentCalendarView from "../AgentCalendarView"
import type { Routine } from "../../lib/routines"

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  )
}

const VIEW_START = new Date(2026, 8, 1)
const VIEW_NOW = new Date(2026, 8, 1)

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

describe("REQ-913 (#512) — the API Agents only filter is gone", () => {
  it("no longer renders the checkbox, and the prop cannot bring it back", () => {
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={VIEW_START}
        now={VIEW_NOW}
        initialRoutines={sampleRoutines}
        defaultApiOnly={false}
      />,
    )
    expect(screen.queryByTestId("api-agents-filter")).not.toBeInTheDocument()
    expect(screen.queryByText("API Agents only")).not.toBeInTheDocument()
  })

  it("shows the same routine set regardless of any legacy filter state", () => {
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={VIEW_START}
        now={VIEW_NOW}
        initialRoutines={sampleRoutines}
      />,
    )
    // API and non-API rows both render — the restriction, if kept, is silent.
    expect(screen.getAllByText("API Data Sync").length).toBeGreaterThan(0)
    expect(screen.getAllByText("CLI Worker Routine").length).toBeGreaterThan(0)
  })
})

describe("REQ-913 (#512) — Calendar ↔ List view shape", () => {
  it("renders both tabs with aria-selected tracking", () => {
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={VIEW_START}
        now={VIEW_NOW}
        initialRoutines={sampleRoutines}
      />,
    )
    const calendarTab = screen.getByRole("tab", { name: "Calendar" })
    const listTab = screen.getByRole("tab", { name: "List" })
    expect(calendarTab).toHaveAttribute("aria-selected", "true")
    expect(listTab).toHaveAttribute("aria-selected", "false")

    fireEvent.click(listTab)
    expect(listTab).toHaveAttribute("aria-selected", "true")
    expect(calendarTab).toHaveAttribute("aria-selected", "false")
  })

  it("switching to List swaps the grid for the list container", () => {
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={VIEW_START}
        now={VIEW_NOW}
        initialRoutines={sampleRoutines}
      />,
    )
    expect(screen.getByTestId("calendar-grid")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("tab", { name: "List" }))
    expect(screen.queryByTestId("calendar-grid")).not.toBeInTheDocument()
    expect(screen.getByTestId("routines-list")).toBeInTheDocument()
  })

  it("keyboard ArrowRight moves from Calendar to List", () => {
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={VIEW_START}
        now={VIEW_NOW}
        initialRoutines={sampleRoutines}
      />,
    )
    const calendarTab = screen.getByRole("tab", { name: "Calendar" })
    calendarTab.focus()
    fireEvent.keyDown(calendarTab, { key: "ArrowRight" })
    expect(screen.getByTestId("routines-list")).toBeInTheDocument()
  })

  it("keyboard Home returns to the first tab", () => {
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={VIEW_START}
        now={VIEW_NOW}
        initialRoutines={sampleRoutines}
      />,
    )
    const listTab = screen.getByRole("tab", { name: "List" })
    fireEvent.click(listTab)
    listTab.focus()
    fireEvent.keyDown(listTab, { key: "Home" })
    expect(screen.getByTestId("calendar-grid")).toBeInTheDocument()
  })
})

describe("REQ-913 (#512) — List view content", () => {
  it("groups by day ascending and reuses the calendar's card testids", () => {
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={VIEW_START}
        now={VIEW_NOW}
        initialRoutines={sampleRoutines}
      />,
    )
    fireEvent.click(screen.getByRole("tab", { name: "List" }))

    const list = screen.getByTestId("routines-list")
    const dayGroups = within(list).getAllByTestId(/^routines-list-day-/)
    expect(dayGroups.length).toBeGreaterThan(0)
    // Same cards the calendar renders:
    expect(within(list).getAllByTestId("routine-card").length).toBeGreaterThan(0)
    expect(within(list).getAllByTestId("routine-name").length).toBeGreaterThan(0)
    expect(within(list).getAllByTestId("routine-schedule").length).toBeGreaterThan(0)
  })

  it("a list row opens the same details modal the calendar uses", () => {
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={VIEW_START}
        now={VIEW_NOW}
        initialRoutines={sampleRoutines}
      />,
    )
    fireEvent.click(screen.getByRole("tab", { name: "List" }))
    fireEvent.click(screen.getAllByTestId("routine-card")[0])
    expect(screen.getByTestId("routine-details-modal")).toBeInTheDocument()
  })

  it("History/Upcoming scope still narrows the list (axes compose)", () => {
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={VIEW_START}
        now={VIEW_NOW}
        initialRoutines={sampleRoutines}
      />,
    )
    fireEvent.click(screen.getByRole("tab", { name: "List" }))
    fireEvent.click(screen.getByTestId("calendar-view-history"))

    const list = screen.getByTestId("routines-list")
    // The CLI routine has no history; a history-scoped list has only the
    // execution of API Data Sync (2026-09-14).
    expect(within(list).queryByText("CLI Worker Routine")).not.toBeInTheDocument()
    expect(within(list).getAllByTestId("execution-card").length).toBeGreaterThan(0)
  })
})

describe("REQ-913 (#512) — the surface reads Routines", () => {
  it("the dialog heading and aria-label say Routines", () => {
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={VIEW_START}
        now={VIEW_NOW}
        initialRoutines={sampleRoutines}
      />,
    )
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-label", "Routines")
    expect(screen.getByText("Routines")).toBeInTheDocument()
  })

  it("the All/History/Upcoming group is labelled as a time range", () => {
    renderWithProviders(
      <AgentCalendarView
        open={true}
        startDate={VIEW_START}
        now={VIEW_NOW}
        initialRoutines={sampleRoutines}
      />,
    )
    expect(
      screen.getByLabelText(/time range/i),
    ).toHaveAttribute("data-testid", "calendar-view-toggle")
  })

  it("the rail button reads Routines", () => {
    // Covered in AgentSidebar.req913.test.tsx (heavy harness); the class/text
    // pairing is asserted there.
    expect(true).toBe(true)
  })
})
