import { Loader2 } from "lucide-react"

export function LoadingSpinner() {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <Loader2 className="w-12 h-12 text-muted-foreground animate-spin" data-testid="loading-spinner" />
    </div>
  )
}
