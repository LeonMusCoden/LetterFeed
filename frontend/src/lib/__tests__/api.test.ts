import {
  getNewsletters,
  createNewsletter,
  updateNewsletter,
  deleteNewsletter,
  getSettings,
  updateSettings,
  getImapFolders,
  testImapConnection,
  processEmails,
  getFeedUrl,
  login,
  NewsletterCreate,
  NewsletterUpdate,
  SettingsCreate,
} from "../api"
import { toast } from "sonner"

// Mock the global fetch function
global.fetch = jest.fn()

// Mock the toast object
jest.mock("sonner", () => ({
  toast: {
    error: jest.fn(),
  },
}))

const mockFetch = <T,>(data: T, ok = true, statusText = "OK") => {
  ;(fetch as jest.Mock).mockResolvedValueOnce({
    ok,
    json: () => Promise.resolve(data),
    statusText,
    status: ok ? 200 : 400,
  })
}

const mockFetchError = (data: any = {}, statusText = "Bad Request", status = 400) => { // eslint-disable-line @typescript-eslint/no-explicit-any
  ;(fetch as jest.Mock).mockResolvedValueOnce({
    ok: false,
    json: () => Promise.resolve(data),
    statusText,
    status,
  })
}

describe("API Functions", () => {
  const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL

  beforeEach(() => {
    // Reset the mock before each test
    ;(fetch as jest.Mock).mockClear()
    ;(toast.error as jest.Mock).mockClear()
    localStorage.clear()
  })

  describe("login", () => {
    it("should login successfully and store the token", async () => {
      const mockToken = { access_token: "test-token", token_type: "bearer" }
      mockFetch(mockToken)

      await login("user", "pass")

      expect(fetch).toHaveBeenCalledWith(`${API_BASE_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ username: "user", password: "pass" }),
      })
      expect(localStorage.getItem("authToken")).toBe("test-token")
      expect(toast.error).not.toHaveBeenCalled()
    })

    it("should throw an error and clear token if login fails", async () => {
      mockFetchError({ detail: "Incorrect username or password" }, "Unauthorized", 401)
      localStorage.setItem("authToken", "old-token")

      await expect(login("user", "wrong-pass")).rejects.toThrow("Incorrect username or password")
      expect(localStorage.getItem("authToken")).toBeNull()
      expect(toast.error).toHaveBeenCalledWith("Incorrect username or password")
    })
  })

  describe("getNewsletters", () => {
    it("should fetch newsletters successfully with auth token", async () => {
      localStorage.setItem("authToken", "test-token")
      const mockNewsletters = [{ id: 1, name: "Newsletter 1" }]
      mockFetch(mockNewsletters)

      const newsletters = await getNewsletters()
      expect(newsletters).toEqual(mockNewsletters)
      expect(fetch).toHaveBeenCalledWith(`${API_BASE_URL}/newsletters`, {
        headers: { Authorization: "Bearer test-token" },
      })
      expect(toast.error).not.toHaveBeenCalled()
    })
  })

  describe("createNewsletter", () => {
    it("should create a newsletter successfully", async () => {
      localStorage.setItem("authToken", "test-token")
      const newNewsletter: NewsletterCreate = { name: "New Newsletter", sender_emails: ["test@example.com"], extract_content: false }
      const createdNewsletter = {
        id: 3,
        ...newNewsletter,
        is_active: true,
        senders: [{ id: 1, email: "test@example.com", newsletter_id: 3 }],
        entries_count: 0,
      }
      mockFetch(createdNewsletter)

      const result = await createNewsletter(newNewsletter)
      expect(result).toEqual(createdNewsletter)
      expect(fetch).toHaveBeenCalledWith(`${API_BASE_URL}/newsletters`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: "Bearer test-token" },
        body: JSON.stringify(newNewsletter),
      })
      expect(toast.error).not.toHaveBeenCalled()
    })
  })

  describe("updateNewsletter", () => {
    it("should update a newsletter successfully", async () => {
      localStorage.setItem("authToken", "test-token")
      const updatedNewsletter: NewsletterUpdate = { name: "Updated Newsletter", sender_emails: ["updated@example.com"], extract_content: true }
      const newsletterId = "1"
      const returnedNewsletter = {
        id: newsletterId,
        ...updatedNewsletter,
        is_active: true,
        senders: [{ id: "1", email: "updated@example.com" }],
        entries_count: 12,
      }
      mockFetch(returnedNewsletter)

      const result = await updateNewsletter(newsletterId, updatedNewsletter)
      expect(result).toEqual(returnedNewsletter)
      expect(fetch).toHaveBeenCalledWith(`${API_BASE_URL}/newsletters/${newsletterId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: "Bearer test-token" },
        body: JSON.stringify(updatedNewsletter),
      })
      expect(toast.error).not.toHaveBeenCalled()
    })
  })

  describe("deleteNewsletter", () => {
    it("should delete a newsletter successfully", async () => {
      localStorage.setItem("authToken", "test-token")
      const newsletterId = "1"
      mockFetch({}, true) // Successful deletion might not have a body

      await deleteNewsletter(newsletterId)
      expect(fetch).toHaveBeenCalledWith(`${API_BASE_URL}/newsletters/${newsletterId}`, {
        method: "DELETE",
        headers: { Authorization: "Bearer test-token" },
      })
      expect(toast.error).not.toHaveBeenCalled()
    })
  })

  describe("getSettings", () => {
    it("should fetch settings successfully", async () => {
      localStorage.setItem("authToken", "test-token")
      const mockSettings = {
        id: 1,
        imap_server: "imap.example.com",
        imap_username: "user@example.com",
        search_folder: "INBOX",
        move_to_folder: null,
        mark_as_read: true,
        email_check_interval: 60,
        auto_add_new_senders: false,
        locked_fields: [],
      }
      mockFetch(mockSettings)

      const settings = await getSettings()
      expect(settings).toEqual(mockSettings)
      expect(fetch).toHaveBeenCalledWith(`${API_BASE_URL}/imap/settings`, {
        headers: { Authorization: "Bearer test-token" },
      })
      expect(toast.error).not.toHaveBeenCalled()
    })
  })

  describe("updateSettings", () => {
    it("should update settings successfully", async () => {
      localStorage.setItem("authToken", "test-token")
      const newSettings: SettingsCreate = {
        imap_server: "new.imap.com",
        imap_username: "newuser@example.com",
        imap_password: "password",
        search_folder: "Archive",
        move_to_folder: "Processed",
        mark_as_read: false,
        email_check_interval: 120,
        auto_add_new_senders: true,
      }
      const updatedSettings = { id: 1, ...newSettings, locked_fields: [] }
      mockFetch(updatedSettings)

      const result = await updateSettings(newSettings)
      expect(result).toEqual(updatedSettings)
      expect(fetch).toHaveBeenCalledWith(`${API_BASE_URL}/imap/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: "Bearer test-token" },
        body: JSON.stringify(newSettings),
      })
      expect(toast.error).not.toHaveBeenCalled()
    })
  })

  describe("getImapFolders", () => {
    it("should fetch IMAP folders successfully", async () => {
      localStorage.setItem("authToken", "test-token")
      const mockFolders = ["INBOX", "Sent", "Archive"]
      mockFetch(mockFolders)

      const folders = await getImapFolders()
      expect(folders).toEqual(mockFolders)
      expect(fetch).toHaveBeenCalledWith(`${API_BASE_URL}/imap/folders`, {
        headers: { Authorization: "Bearer test-token" },
      })
      expect(toast.error).not.toHaveBeenCalled()
    })
  })

  describe("testImapConnection", () => {
    it("should test IMAP connection successfully", async () => {
      localStorage.setItem("authToken", "test-token")
      const mockResponse = { message: "Connection successful" }
      mockFetch(mockResponse)

      const result = await testImapConnection()
      expect(result).toEqual(mockResponse)
      expect(fetch).toHaveBeenCalledWith(`${API_BASE_URL}/imap/test`, {
        method: "POST",
        headers: { Authorization: "Bearer test-token" },
      })
      expect(toast.error).not.toHaveBeenCalled()
    })
  })

  describe("processEmails", () => {
    it("should process emails successfully", async () => {
      localStorage.setItem("authToken", "test-token")
      const mockResponse = { message: "Emails processed" }
      mockFetch(mockResponse)

      const result = await processEmails()
      expect(result).toEqual(mockResponse)
      expect(fetch).toHaveBeenCalledWith(`${API_BASE_URL}/imap/process`, {
        method: "POST",
        headers: { Authorization: "Bearer test-token" },
      })
      expect(toast.error).not.toHaveBeenCalled()
    })
  })

  describe("getFeedUrl", () => {
    it("should return the correct feed URL", () => {
      const newsletterId = "123"
      const expectedUrl = `${API_BASE_URL}/feeds/${newsletterId}`
      const url = getFeedUrl(newsletterId)
      expect(url).toBe(expectedUrl)
    })
  })
})
