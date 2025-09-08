"use client"

import { useState, useEffect, useCallback } from "react"

import withAuth from "@/components/withAuth"
import {
  getNewsletters,
  getSettings,
  getImapFolders,
  Newsletter,
  Settings as AppSettings,
} from "@/lib/api"
import { LoadingSpinner } from "@/components/letterfeed/LoadingSpinner"
import { Header } from "@/components/letterfeed/Header"
import { NewsletterList } from "@/components/letterfeed/NewsletterList"
import { EmptyState } from "@/components/letterfeed/EmptyState"
import { MasterFeedCard } from "@/components/letterfeed/MasterFeedCard"
import { NewsletterDialog } from "@/components/letterfeed/NewsletterDialog"
import { SettingsDialog } from "@/components/letterfeed/SettingsDialog"

function LetterFeedApp() {
  const [newsletters, setNewsletters] = useState<Newsletter[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [folderOptions, setFolderOptions] = useState<string[]>([])

  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [editingNewsletter, setEditingNewsletter] = useState<Newsletter | null>(null)

  const fetchData = useCallback(async () => {
    try {
      const [newslettersData, settingsData, foldersData] = await Promise.all([
        getNewsletters(),
        getSettings(),
        getImapFolders(),
      ])
      setNewsletters(newslettersData)
      setSettings(settingsData)
      setFolderOptions(foldersData)
    } catch (error) {
      console.error("Failed to fetch data:", error)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const openEditDialog = (newsletter: Newsletter) => {
    setEditingNewsletter(newsletter)
  }

  const closeEditDialog = () => {
    setEditingNewsletter(null)
  }

  if (isLoading) {
    return <LoadingSpinner />
  }

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Header
          onOpenAddNewsletter={() => setIsAddDialogOpen(true)}
          onOpenSettings={() => setIsSettingsOpen(true)}
        />

        {newsletters.length > 0 && <MasterFeedCard />}

        {newsletters.length > 0 ? (
          <NewsletterList newsletters={newsletters} onEditNewsletter={openEditDialog} />
        ) : (
          <EmptyState onAddNewsletter={() => setIsAddDialogOpen(true)} />
        )}

        <NewsletterDialog
          isOpen={isAddDialogOpen}
          folderOptions={folderOptions}
          onOpenChange={setIsAddDialogOpen}
          onSuccess={fetchData}
        />

        <NewsletterDialog
          newsletter={editingNewsletter}
          isOpen={!!editingNewsletter}
          folderOptions={folderOptions}
          onOpenChange={closeEditDialog}
          onSuccess={() => {
            closeEditDialog()
            fetchData()
          }}
        />

        {settings && (
          <SettingsDialog
            settings={settings}
            folderOptions={folderOptions}
            isOpen={isSettingsOpen}
            onOpenChange={setIsSettingsOpen}
            onSuccess={fetchData}
          />
        )}
      </div>
    </div>
  )
}

export default withAuth(LetterFeedApp)
