import React from "react"
import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import "@testing-library/jest-dom"
import { MasterFeedCard } from "../MasterFeedCard"
import { toast } from "sonner"

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

  it("copies the feed URL to the clipboard when the copy button is clicked", async () => {
    render(<MasterFeedCard />)

    const copyButton = screen.getByRole("button", { name: /copy feed url/i })
    fireEvent.click(copyButton)

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(
        "http://mock-api/feeds/all"
      )
      expect(toast.success).toHaveBeenCalledWith(
        "Feed URL copied to clipboard!"
      )
    })
  })
})
