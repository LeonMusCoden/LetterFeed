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
import { Plus } from "lucide-react"
import { Newsletter, createNewsletter, updateNewsletter, deleteNewsletter } from "@/lib/api"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { isValidEmail } from "@/lib/utils"

interface NewsletterDialogProps {
  newsletter?: Newsletter | null
  isOpen: boolean
  folderOptions: string[]
  onOpenChange: (isOpen: boolean) => void
  onSuccess: () => void
}

const getInitialState = (newsletter: Newsletter | null | undefined) => {
  if (newsletter) {
    return {
      name: newsletter.name,
      slug: newsletter.slug || "",
      emails: newsletter.senders.map((s) => s.email),
      search_folder: newsletter.search_folder || "",
      move_to_folder: newsletter.move_to_folder || "",
      extract_content: newsletter.extract_content,
    }
  }
  return {
    name: "",
    slug: "",
    emails: [""],
    search_folder: "",
    move_to_folder: "",
    extract_content: false,
  }
}

export function NewsletterDialog({ newsletter, isOpen, folderOptions, onOpenChange, onSuccess }: NewsletterDialogProps) {
  const isEditMode = !!newsletter
  const [formData, setFormData] = useState(getInitialState(newsletter))

  useEffect(() => {
    if (isOpen) {
      setFormData(getInitialState(newsletter))
    }
  }, [isOpen, newsletter])

  const handleEmailChange = (index: number, value: string) => {
    setFormData((prev) => ({
      ...prev,
      emails: prev.emails.map((email, i) => (i === index ? value : email)),
    }))
  }

  const handleAddEmail = () => {
    setFormData((prev) => ({
      ...prev,
      emails: [...prev.emails, ""],
    }))
  }

  const handleRemoveEmail = (index: number) => {
    setFormData((prev) => ({
      ...prev,
      emails: prev.emails.filter((_, i) => i !== index),
    }))
  }

  const handleSubmit = async () => {
    if (!formData.name || !formData.emails.some((email) => email.trim() && isValidEmail(email))) {
      return
    }

    const payload = {
      name: formData.name,
      slug: formData.slug,
      sender_emails: formData.emails.filter((email) => email.trim()),
      search_folder: formData.search_folder,
      move_to_folder: formData.move_to_folder,
      extract_content: formData.extract_content,
    }

    try {
      if (isEditMode) {
        await updateNewsletter(newsletter.id, payload)
      } else {
        await createNewsletter(payload)
      }
      onOpenChange(false)
      onSuccess()
    } catch (error) {
      console.error(`Failed to ${isEditMode ? "update" : "create"} newsletter:`, error)
    }
  }

  const handleDelete = async () => {
    if (isEditMode && window.confirm(`Are you sure you want to delete the "${newsletter.name}" newsletter?`)) {
      try {
        await deleteNewsletter(newsletter.id)
        onOpenChange(false)
        onSuccess()
      } catch (error) {
        console.error("Failed to delete newsletter:", error)
      }
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>{isEditMode ? "Edit" : "Register New"} Newsletter</DialogTitle>
          <DialogDescription>
            {isEditMode ? `Update the details for ${newsletter.name}.` : "Add a new newsletter."}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="name">Newsletter Name</Label>
            <Input
              id="name"
              value={formData.name}
              onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))}
              placeholder="Enter newsletter name"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="slug">Custom URL (optional)</Label>
            <Input
              id="slug"
              value={formData.slug}
              onChange={(e) => setFormData((prev) => ({ ...prev, slug: e.target.value }))}
              placeholder={isEditMode ? "my-custom-url" : "Generated from newsletter name"}
            />
            {!isEditMode && (
              <p className="text-sm text-muted-foreground">
                Leave blank to generate a URL from the newsletter name.
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="search_folder">Folder to Search</Label>
            <Select
              value={formData.search_folder || "None"}
              onValueChange={(value) =>
                setFormData((prev) => ({ ...prev, search_folder: value === "None" ? "" : value }))
              }
            >
              <SelectTrigger>
                <SelectValue placeholder="Select folder or leave empty" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="None">Default (use global setting)</SelectItem>
                {folderOptions.map((folder) => (
                  <SelectItem key={folder} value={folder}>
                    {folder}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="move_to_folder">Move To Folder</Label>
            <Select
              value={formData.move_to_folder || "None"}
              onValueChange={(value) =>
                setFormData((prev) => ({ ...prev, move_to_folder: value === "None" ? "" : value }))
              }
            >
              <SelectTrigger>
                <SelectValue placeholder="Select folder or leave empty" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="None">Default (use global setting)</SelectItem>
                {folderOptions.map((folder) => (
                  <SelectItem key={folder} value={folder}>
                    {folder}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Email Addresses</Label>
            {formData.emails.map((email, index) => (
              <div key={index} className="flex gap-2">
                <Input
                  value={email}
                  onChange={(e) => handleEmailChange(index, e.target.value)}
                  placeholder="Enter email address"
                  type="email"
                  aria-invalid={email.length > 0 && !isValidEmail(email)}
                />
                {formData.emails.length > 1 && (
                  <Button variant="outline" size="sm" onClick={() => handleRemoveEmail(index)}>
                    Remove
                  </Button>
                )}
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={handleAddEmail} className="w-full bg-transparent">
              <Plus className="w-4 h-4 mr-2" />
              Add Another Email
            </Button>
          </div>
          <div className="flex items-center space-x-2">
            <Checkbox
              id="extract-content"
              checked={formData.extract_content}
              onCheckedChange={(checked) =>
                setFormData((prev) => ({ ...prev, extract_content: !!checked }))
              }
            />
            <Label htmlFor="extract-content">Extract main content from emails</Label>
          </div>
        </div>
        <DialogFooter className={isEditMode ? "sm:justify-between" : ""}>
          {isEditMode && (
            <Button variant="destructive" onClick={handleDelete}>
              Delete Newsletter
            </Button>
          )}
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button onClick={handleSubmit}>
              {isEditMode ? "Save Changes" : "Register Newsletter"}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
