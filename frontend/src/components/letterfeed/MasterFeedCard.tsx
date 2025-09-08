"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Rss, ExternalLink } from "lucide-react"
import { getMasterFeedUrl } from "@/lib/api"

export function MasterFeedCard() {
  const feedUrl = getMasterFeedUrl()

  return (
    <Card className="mb-8">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Rss className="w-5 h-5 text-orange-500" />
          Master Feed
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          This feed contains all entries from all your newsletters in one place.
        </p>
        <div>
          <h4 className="text-sm font-medium text-gray-700 mb-2">RSS Feed URL</h4>
          <div className="flex items-center gap-2">
            <a
              href={feedUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 hover:underline"
            >
              <ExternalLink className="w-3 h-3" />
              {feedUrl}
            </a>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
