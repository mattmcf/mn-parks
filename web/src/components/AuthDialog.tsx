import { useState, type FormEvent } from "react"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api } from "@/lib/api"
import type { SessionPayload } from "@/types"

type Props = {
  open: boolean
  googleOAuth: boolean
  onOpenChange: (open: boolean) => void
  onAuthed: (session: SessionPayload) => void
}

export function AuthDialog({ open, googleOAuth, onOpenChange, onAuthed }: Props) {
  const [mode, setMode] = useState<"login" | "signup">("login")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const session =
        mode === "login" ? await api.login(email, password) : await api.signup(email, password)
      onAuthed(session)
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign in.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={mode === "login" ? "Sign in" : "Create an account"}>
        <p className="mb-4 text-sm text-[hsl(var(--muted-foreground))]">
          Browse the map without an account. Sign in to save favorites and mark parks visited.
        </p>
        <form className="space-y-3" onSubmit={submit}>
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              required
              minLength={6}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>
          {error && <p className="text-sm text-[hsl(var(--destructive))]">{error}</p>}
          <Button className="w-full" disabled={busy} type="submit">
            {busy ? "Working…" : mode === "login" ? "Sign in" : "Create account"}
          </Button>
        </form>
        {googleOAuth && (
          <a
            className="mt-3 flex h-9 items-center justify-center rounded-md border border-[hsl(var(--border))] text-sm hover:bg-[hsl(var(--muted))]"
            href="/api/auth/google_oauth2"
          >
            Continue with Google
          </a>
        )}
        <button
          type="button"
          className="mt-4 text-sm text-[hsl(var(--accent))] underline"
          onClick={() => {
            setMode(mode === "login" ? "signup" : "login")
            setError(null)
          }}
        >
          {mode === "login" ? "Need an account? Create one" : "Already have an account? Sign in"}
        </button>
      </DialogContent>
    </Dialog>
  )
}
