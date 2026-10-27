import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react"
import { Loader2, Send, Star, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api"
import {
  EMPTY_COMPOSER,
  PLAN_ERROR,
  clearTurns,
  loadTurns,
  persistTurns,
  saveProposedTrip,
  turnsToMessages,
  type ChatTurn,
  type ProposedTrip,
} from "@/lib/ai-chat"
import { TYPE_COLORS, TYPE_LABELS } from "@/lib/constants"
import { cn } from "@/lib/utils"
import type { Origin, Park, SessionUser } from "@/types"

type Props = {
  open: boolean
  user: SessionUser | null
  origin: Origin | null
  onClose: () => void
  onNeedAuth: () => void
  onSelectPark: (park: Park) => void
  onSavedTrip: (tripId: number) => void
}

function newId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID()
  return `t-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function tabStorage(): Storage | null {
  try {
    return sessionStorage
  } catch {
    return null
  }
}

export function AiChatPanel({
  open,
  user,
  origin,
  onClose,
  onNeedAuth,
  onSelectPark,
  onSavedTrip,
}: Props) {
  const [turns, setTurns] = useState<ChatTurn[]>(() => loadTurns(tabStorage()))
  const [draft, setDraft] = useState("")
  const [sending, setSending] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [pendingSave, setPendingSave] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const saveLock = useRef(false)

  useEffect(() => {
    persistTurns(turns, tabStorage())
  }, [turns])

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ block: "end" })
  }, [open, turns, sending])

  const lastProposal = [...turns].reverse().find((turn) => turn.proposed_trip)?.proposed_trip ?? null
  const prevUserId = useRef(user?.id ?? null)

  const send = async (event?: FormEvent) => {
    event?.preventDefault()
    const content = draft.trim()
    if (!content || sending) return
    const userTurn: ChatTurn = { id: newId(), role: "user", content }
    const pending: ChatTurn = { id: newId(), role: "assistant", content: "", pending: true }
    const nextTurns = [...turns.filter((turn) => !turn.pending), userTurn]
    setTurns([ ...nextTurns, pending ])
    setDraft("")
    setSending(true)
    setSaveError(null)
    try {
      const originBody = origin ? { latitude: origin.latitude, longitude: origin.longitude } : undefined
      const payload = await api.aiChat({
        messages: turnsToMessages([ ...nextTurns ]),
        origin: originBody,
      })
      setTurns([
        ...nextTurns,
        {
          id: pending.id,
          role: "assistant",
          content: payload.message,
          parks: payload.parks,
          proposed_trip: payload.proposed_trip ?? null,
        },
      ])
    } catch {
      setTurns([
        ...nextTurns,
        { id: pending.id, role: "assistant", content: PLAN_ERROR, error: true },
      ])
    } finally {
      setSending(false)
    }
  }

  const onComposerKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault()
      void send()
    }
  }

  const clear = () => {
    clearTurns(tabStorage())
    setTurns([])
    setDraft("")
    setSaveError(null)
    setPendingSave(false)
  }

  const commitTrip = async (proposal: ProposedTrip) => {
    if (!user) {
      setPendingSave(true)
      onNeedAuth()
      return
    }
    if (saveLock.current) return
    saveLock.current = true
    setSaving(true)
    setSaveError(null)
    try {
      const trip = await saveProposedTrip(proposal, api)
      setPendingSave(false)
      onSavedTrip(trip.id)
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Could not save that trip.")
    } finally {
      saveLock.current = false
      setSaving(false)
    }
  }

  useEffect(() => {
    const becameUser = Boolean(user) && prevUserId.current !== user?.id
    prevUserId.current = user?.id ?? null
    if (!open || !becameUser || !pendingSave || !lastProposal) return
    void commitTrip(lastProposal)
  }, [open, user, pendingSave, lastProposal])

  if (!open) return null

  const empty = turns.length === 0

  return (
    <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose}>
      <div
        className="absolute inset-0 flex h-full w-full flex-col bg-[hsl(var(--card))] shadow-xl md:inset-auto md:right-0 md:top-0 md:h-full md:w-[min(28rem,100%)]"
        role="dialog"
        aria-label="Ask AI"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-[hsl(var(--border))] px-3 py-2">
          <Star className="h-4 w-4 shrink-0 text-[hsl(var(--accent))]" />
          <div className="min-w-0 flex-1">
            <h2 className="font-[family-name:var(--font-sans)] text-lg leading-tight">Ask AI</h2>
            <p className="truncate text-xs text-[hsl(var(--muted-foreground))]">
              Uses our park inventory only — not Google or AllTrails
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={clear} disabled={empty && !draft}>
            Clear chat
          </Button>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close Ask AI">
            <X />
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
          {empty ? (
            <div className="flex h-full flex-col justify-end">
              <p className="text-sm text-[hsl(var(--muted-foreground))]">{EMPTY_COMPOSER}</p>
            </div>
          ) : (
            <ol className="space-y-3">
              {turns.map((turn) => (
                <li key={turn.id}>
                  {turn.role === "user" ? (
                    <div className="ml-8 rounded-lg bg-[hsl(var(--primary))] px-3 py-2 text-sm text-[hsl(var(--primary-foreground))]">
                      {turn.content}
                    </div>
                  ) : (
                    <AssistantTurn
                      turn={turn}
                      saving={saving}
                      saveError={turn.proposed_trip ? saveError : null}
                      onSelectPark={onSelectPark}
                      onSave={(proposal) => void commitTrip(proposal)}
                    />
                  )}
                </li>
              ))}
            </ol>
          )}
          <div ref={bottomRef} />
        </div>

        <form className="border-t border-[hsl(var(--border))] p-3" onSubmit={(event) => void send(event)}>
          <label className="sr-only" htmlFor="ai-composer">
            Ask for parks
          </label>
          <Textarea
            id="ai-composer"
            value={draft}
            placeholder={EMPTY_COMPOSER}
            className="min-h-20"
            disabled={sending}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={onComposerKey}
          />
          <div className="mt-2 flex items-center justify-between gap-2">
            <p className="text-[11px] text-[hsl(var(--muted-foreground))]">
              Enter to send · Shift+Enter for a new line
            </p>
            <Button type="submit" size="sm" disabled={sending || draft.trim().length === 0}>
              {sending ? <Loader2 className="animate-spin" /> : <Send />}
              Send
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}

function AssistantTurn({
  turn,
  saving,
  saveError,
  onSelectPark,
  onSave,
}: {
  turn: ChatTurn
  saving: boolean
  saveError: string | null
  onSelectPark: (park: Park) => void
  onSave: (proposal: ProposedTrip) => void
}) {
  if (turn.pending) {
    return (
      <div className="mr-8 flex items-center gap-2 rounded-lg bg-[hsl(var(--muted))] px-3 py-2 text-sm text-[hsl(var(--muted-foreground))]">
        <Loader2 className="h-4 w-4 animate-spin" />
        Planning…
      </div>
    )
  }

  return (
    <div
      className={cn(
        "mr-8 space-y-2 rounded-lg px-3 py-2 text-sm",
        turn.error ? "bg-[#3f1d1d] text-[#fde8e8]" : "bg-[hsl(var(--muted))]",
      )}
    >
      <p className="whitespace-pre-wrap leading-relaxed">{turn.content}</p>
      {turn.parks && turn.parks.length > 0 && (
        <ul className="space-y-1">
          {turn.parks.map((park) => (
            <li key={park.id}>
              <button
                type="button"
                className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-[hsl(var(--card))]"
                onClick={() => onSelectPark(park)}
              >
                <span
                  className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ background: TYPE_COLORS[park.park_type] }}
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{park.name}</span>
                  <span className="text-xs text-[hsl(var(--muted-foreground))]">
                    {TYPE_LABELS[park.park_type]}
                    {park.dark_sky_certified ? " · Dark Sky" : ""}
                    {park.camping_score != null ? ` · camping ${park.camping_score}` : ""}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {turn.proposed_trip && (
        <div className="rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-2">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="font-medium">{turn.proposed_trip.name}</p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                Private · Planned · {turn.proposed_trip.park_ids.length} park
                {turn.proposed_trip.park_ids.length === 1 ? "" : "s"}
              </p>
            </div>
            <Badge>Trip</Badge>
          </div>
          {turn.proposed_trip.notes && (
            <p className="mt-1 text-xs text-[hsl(var(--muted-foreground))]">{turn.proposed_trip.notes}</p>
          )}
          <Button
            className="mt-2 w-full"
            size="sm"
            disabled={saving}
            onClick={() => onSave(turn.proposed_trip!)}
          >
            {saving ? <Loader2 className="animate-spin" /> : null}
            Save trip
          </Button>
          {saveError && <p className="mt-1 text-xs text-[hsl(var(--destructive))]">{saveError}</p>}
        </div>
      )}
    </div>
  )
}
