import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Loader2, CheckCircle, XCircle } from "lucide-react"
import {
  Settings as AppSettings,
  SettingsCreate,
  updateSettings,
  testImapConnection,
} from "@/lib/api"
import { toast } from "sonner"

interface SettingsDialogProps {
  settings: AppSettings
  folderOptions: string[]
  isOpen: boolean
  onOpenChange: (isOpen: boolean) => void
  onSuccess: () => void
}

export function SettingsDialog({
  settings,
  folderOptions,
  isOpen,
  onOpenChange,
  onSuccess,
}: SettingsDialogProps) {
  const [currentSettings, setCurrentSettings] = useState<SettingsCreate | null>(
    null
  )
  const [testConnectionStatus, setTestConnectionStatus] = useState<
    "idle" | "loading" | "success" | "error"
  >("idle")
  const [testConnectionMessage, setTestConnectionMessage] = useState("")

  useEffect(() => {
    if (settings) {
      setCurrentSettings({ ...settings, imap_password: "" })
    }
  }, [settings])

  if (!currentSettings) return null

  const handleSettingsChange = <K extends keyof SettingsCreate>(
    key: K,
    value: SettingsCreate[K]
  ) => {
    setCurrentSettings((prev) => (prev ? { ...prev, [key]: value } : null))
  }

  const handleSave = async () => {
    if (!currentSettings) return
    try {
      const payload: SettingsCreate = { ...currentSettings }
      if (payload.imap_password === "") {
        delete payload.imap_password
      }
      await updateSettings(payload)
      toast.success("Settings saved successfully!")
      onOpenChange(false)
      onSuccess()
    } catch (error) {
      console.error("Failed to save settings:", error)
      toast.error("Failed to save settings.")
    }
  }

  const handleTestConnection = async () => {
    if (!currentSettings) return
    setTestConnectionStatus("loading")
    try {
      await updateSettings(currentSettings)
      const result = await testImapConnection()
      setTestConnectionStatus("success")
      setTestConnectionMessage(result.message)
    } catch (error: unknown) {
      setTestConnectionStatus("error")
      if (error instanceof Error) {
        setTestConnectionMessage(error.message || "Connection failed")
      } else {
        setTestConnectionMessage("An unknown error occurred")
      }
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Settings</DialogTitle>
          <DialogDescription>
            Fields are locked if they are set by environment variables.
          </DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-6 py-4">
          {/* IMAP Configuration */}
          <div className="space-y-4">
            <h3 className="text-lg font-medium col-span-1 md:col-span-2">
              IMAP Configuration
            </h3>
            <div className="space-y-2">
              <Label htmlFor="imap-server">IMAP Server</Label>
              <Input
                id="imap-server"
                value={currentSettings.imap_server}
                onChange={(e) =>
                  handleSettingsChange("imap_server", e.target.value)
                }
                placeholder="imap.gmail.com"
                disabled={settings.locked_fields.includes("imap_server")}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="imap-username">IMAP Username</Label>
              <Input
                id="imap-username"
                value={currentSettings.imap_username}
                onChange={(e) =>
                  handleSettingsChange("imap_username", e.target.value)
                }
                placeholder="your-email@gmail.com"
                disabled={settings.locked_fields.includes("imap_username")}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="imap-password">IMAP Password</Label>
              <Input
                id="imap-password"
                type="password"
                value={currentSettings.imap_password ?? ""}
                onChange={(e) =>
                  handleSettingsChange("imap_password", e.target.value)
                }
                placeholder="Your password or app password"
                disabled={settings.locked_fields.includes("imap_password")}
              />
            </div>
            <div className="pt-2">
              <Button
                onClick={handleTestConnection}
                disabled={testConnectionStatus === "loading"}
                variant="outline"
                size="sm"
              >
                {testConnectionStatus === "loading" && (
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                )}
                Test Connection
              </Button>
              {testConnectionStatus !== "idle" && (
                <div
                  data-testid="connection-status"
                  className={`mt-2 flex items-center text-sm ${
                    testConnectionStatus === "success"
                      ? "text-green-600"
                      : "text-red-600"
                  }`}
                >
                  {testConnectionStatus === "success" && (
                    <CheckCircle className="w-4 h-4 mr-2" />
                  )}
                  {testConnectionStatus === "error" && (
                    <XCircle className="w-4 h-4 mr-2" />
                  )}
                  {testConnectionMessage}
                </div>
              )}
            </div>
          </div>

          {/* Email Processing */}
          <div className="space-y-4">
            <h3 className="text-lg font-medium col-span-1 md:col-span-2">
              Email Processing
            </h3>
            <div className="space-y-2">
              <Label htmlFor="search-folder">Folder to Search</Label>
              <Select
                value={currentSettings.search_folder}
                onValueChange={(value) =>
                  handleSettingsChange("search_folder", value)
                }
                disabled={settings.locked_fields.includes("search_folder")}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select folder" />
                </SelectTrigger>
                <SelectContent>
                  {folderOptions.map((folder) => (
                    <SelectItem key={folder} value={folder}>
                      {folder}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="move-folder">Move to Folder</Label>
              <Select
                value={currentSettings.move_to_folder || "None"}
                onValueChange={(value) =>
                  handleSettingsChange(
                    "move_to_folder",
                    value === "None" ? null : value
                  )
                }
                disabled={settings.locked_fields.includes("move_to_folder")}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select folder or leave empty" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="None">None (Don&apos;t move)</SelectItem>
                  {folderOptions.map((folder) => (
                    <SelectItem key={folder} value={folder}>
                      {folder}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="check-interval">Check Interval (minutes)</Label>
              <Input
                id="check-interval"
                type="number"
                min="1"
                max="1440"
                value={currentSettings.email_check_interval}
                onChange={(e) =>
                  handleSettingsChange(
                    "email_check_interval",
                    Number.parseInt(e.target.value) || 15
                  )
                }
                placeholder="15"
                disabled={settings.locked_fields.includes("email_check_interval")}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="max-entries">Max Entries Per Feed</Label>
              <Input
                id="max-entries"
                type="number"
                min="0"
                value={currentSettings.max_entries_per_feed}
                onChange={(e) =>
                  handleSettingsChange(
                    "max_entries_per_feed",
                    Number.parseInt(e.target.value) || 0
                  )
                }
                placeholder="0 (unlimited)"
                disabled={settings.locked_fields.includes("max_entries_per_feed")}
              />
              <p className="text-xs text-muted-foreground">
                0 = unlimited. Older entries are deleted when the limit is exceeded.
              </p>
            </div>
            <div className="flex items-center space-x-2 pt-2">
              <Checkbox
                id="mark-read"
                checked={currentSettings.mark_as_read}
                onCheckedChange={(checked) =>
                  handleSettingsChange("mark_as_read", !!checked)
                }
                disabled={settings.locked_fields.includes("mark_as_read")}
              />
              <Label htmlFor="mark-read" className="text-sm font-normal">
                Mark emails as read
              </Label>
            </div>
            <div className="flex items-center space-x-2">
              <Checkbox
                id="auto-add"
                checked={currentSettings.auto_add_new_senders}
                onCheckedChange={(checked) =>
                  handleSettingsChange("auto_add_new_senders", !!checked)
                }
                disabled={settings.locked_fields.includes("auto_add_new_senders")}
              />
              <Label htmlFor="auto-add" className="text-sm font-normal">
                Auto-add new senders
              </Label>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave}>Save Settings</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
