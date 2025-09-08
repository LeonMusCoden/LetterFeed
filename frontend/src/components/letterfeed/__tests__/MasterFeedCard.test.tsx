import React from "react"
import { render, screen } from "@testing-library/react"
import "@testing-library/jest-dom"
import { MasterFeedCard } from "../MasterFeedCard"

// Mock the getMasterFeedUrl function
jest.mock("@/lib/api", () => ({
  ...jest.requireActual("@/lib/api"),
  getMasterFeedUrl: jest.fn(() => "http://mock-api/feeds/all"),
}))

// Mock the toast
jest.mock("sonner", () => ({
  toast: {
    success: jest.fn(),
  },
}))

// Mock navigator.clipboard
Object.assign(navigator, {
  clipboard: {
    writeText: jest.fn(),
  },
})

describe("MasterFeedCard", () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it("renders the master feed card with the correct URL", () => {
    render(<MasterFeedCard />)

    expect(screen.getByText("Master Feed")).toBeInTheDocument()
    expect(
      screen.getByText(
        "This feed contains all entries from all your newsletters in one place."
      )
    ).toBeInTheDocument()

    const feedLink = screen.getByRole("link")
    expect(feedLink).toHaveAttribute("href", "http://mock-api/feeds/all")
    expect(feedLink).toHaveTextContent("http://mock-api/feeds/all")
  })
})
