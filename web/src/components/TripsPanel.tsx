import { useEffect, useMemo, useState, type FormEvent } from "react"
import { Globe, Lock, Plus, Trash2, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api"
import { TYPE_COLORS, TYPE_LABELS } from "@/lib/constants"
import { rankParkNameMatches } from "@/lib/park-search"
import {
  TRIP_STATUS_LABELS,
  TRIP_STATUSES,
  canEditTrip,
  formatTripDates,
  type Trip,
  type TripRoute,
  type TripStatus,
  visibilityLabel,
} from "@/lib/trips"
import { cn } from "@/lib/utils"
import type { Park, SessionUser } from "@/types"

const fieldClass =
  "flex h-9 w-full rounded-md border border-[hsl(var(--input))] bg-[hsl(var(--card))] px-3 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--ring))]"

type Tab = "public" | "mine"

type Props = {
  open: boolean
  route: TripRoute
  user: SessionUser | null
  parks: Park[]
  pendingPark: Park | null
  onClose: () => void
  onNeedAuth: () => void
  onOpenList: () => void
  onOpenTrip: (id: number) => void
  onSelectPark: (park: Park) => void
  onClearPendingPark: () => void
}

export function TripsPanel({
  open,
  route,
  user,
  parks,
  pendingPark,
  onClose,
  onNeedAuth,
  onOpenList,
  onOpenTrip,
  onSelectPark,
  onClearPendingPark,
}: Props) {
  const [tab, setTab] = useState<Tab>(pendingPark ? "mine" : "public")
  const [mine, setMine] = useState<Trip[] | null>(null)
  const [published, setPublished] = useState<Trip[] | null>(null)
  const [current, setCurrent] = useState<Trip | null>(null)
  const [listError, setListError] = useState<string | null>(null)
  const [showError, setShowError] = useState<string | null>(null)
  const [listLoading, setListLoading] = useState(false)
  const [showLoading, setShowLoading] = useState(false)
  const [composing, setComposing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [parkQuery, setParkQuery] = useState("")

  useEffect(() => {
    if (!open) return
    if (pendingPark) setTab("mine")
  }, [open, pendingPark])

  useEffect(() => {
    if (!open || route.kind === "show") return
    let cancelled = false
    setListLoading(true)
    setListError(null)
    const requests: Promise<void>[] = [
      api
        .publicTrips()
        .then((payload) => {
          if (!cancelled) setPublished(payload.trips)
        }),
    ]
    if (user) {
      requests.push(
        api.myTrips().then((payload) => {
          if (!cancelled) setMine(payload.trips)
        }),
      )
    } else {
      setMine(null)
    }
    Promise.all(requests)
      .catch((err: unknown) => {
        if (!cancelled) setListError(err instanceof Error ? err.message : "Could not load trip lists.")
      })
      .finally(() => {
        if (!cancelled) setListLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, route.kind, user])

  useEffect(() => {
    if (!open || route.kind !== "show") {
      setCurrent(null)
      setShowError(null)
      return
    }
    let cancelled = false
    setShowLoading(true)
    setShowError(null)
    setConfirmDelete(false)
    api
      .trip(route.id)
      .then((payload) => {
        if (!cancelled) setCurrent(payload.trip)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setCurrent(null)
          setShowError(err instanceof Error ? err.message : "Could not open that trip list.")
        }
      })
      .finally(() => {
        if (!cancelled) setShowLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, route, user])

  const owned = Boolean(current && canEditTrip(current))
  const tripParks = current?.parks ?? []
  const parkMatches = useMemo(() => {
    if (!owned) return []
    const taken = new Set(tripParks.map((park) => park.id))
    const available = parks.filter((park) => !taken.has(park.id))
    const q = parkQuery.trim()
    if (q.length < 3) return []
    return rankParkNameMatches(available, q, 8)
  }, [owned, parkQuery, parks, tripParks])

  if (!open) return null

  const addPendingTo = async (tripId: number) => {
    if (!pendingPark) {
      onOpenTrip(tripId)
      return
    }
    setBusy(true)
    setFormError(null)
    try {
      await api.addTripPark(tripId, pendingPark.id)
      onClearPendingPark()
      onOpenTrip(tripId)
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Could not add that park.")
    } finally {
      setBusy(false)
    }
  }

  const createTrip = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!user) {
      onNeedAuth()
      return
    }
    const form = new FormData(event.currentTarget)
    setBusy(true)
    setFormError(null)
    try {
      const { trip } = await api.createTrip({
        name: String(form.get("name") || ""),
        notes: String(form.get("notes") || "").trim() || null,
        status: String(form.get("status") || "planned") as TripStatus,
        public: form.get("public") === "on",
        starts_on: String(form.get("starts_on") || "").trim() || null,
        ends_on: String(form.get("ends_on") || "").trim() || null,
      })
      if (pendingPark) {
        const { trip: withPark } = await api.addTripPark(trip.id, pendingPark.id)
        onClearPendingPark()
        onOpenTrip(withPark.id)
      } else {
        onOpenTrip(trip.id)
      }
      setComposing(false)
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Could not create that list.")
    } finally {
      setBusy(false)
    }
  }

  const saveTrip = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!current || !owned) return
    const form = new FormData(event.currentTarget)
    setBusy(true)
    setFormError(null)
    try {
      const { trip } = await api.updateTrip(current.id, {
        name: String(form.get("name") || ""),
        notes: String(form.get("notes") || "").trim() || null,
        status: String(form.get("status") || current.status) as TripStatus,
        public: form.get("public") === "on",
        starts_on: String(form.get("starts_on") || "").trim() || null,
        ends_on: String(form.get("ends_on") || "").trim() || null,
      })
      setCurrent(trip)
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Could not save that list.")
    } finally {
      setBusy(false)
    }
  }

  const addPark = async (park: Park) => {
    if (!current || !owned) return
    setBusy(true)
    setFormError(null)
    try {
      const { trip } = await api.addTripPark(current.id, park.id)
      setCurrent(trip)
      setParkQuery("")
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Could not add that park.")
    } finally {
      setBusy(false)
    }
  }

  const removePark = async (parkId: number) => {
    if (!current || !owned) return
    setBusy(true)
    setFormError(null)
    try {
      const { trip } = await api.removeTripPark(current.id, parkId)
      setCurrent(trip)
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Could not remove that park.")
    } finally {
      setBusy(false)
    }
  }

  const destroyTrip = async () => {
    if (!current || !owned) return
    setBusy(true)
    setFormError(null)
    try {
      await api.deleteTrip(current.id)
      onOpenList()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Could not delete that list.")
    } finally {
      setBusy(false)
      setConfirmDelete(false)
    }
  }

  return (
    <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose}>
      <div
        className="absolute inset-0 flex h-full w-full flex-col bg-[hsl(var(--card))] shadow-xl md:inset-auto md:right-0 md:top-0 md:w-[min(28rem,100%)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-2 border-b border-[hsl(var(--border))] px-4 py-3">
          <div className="min-w-0">
            <p className="font-[family-name:var(--font-sans)] text-xl">
              {route.kind === "show" ? "Trip list" : "Trip lists"}
            </p>
            <p className="text-xs text-[hsl(var(--muted-foreground))]">
              Named lists of Minnesota parks — public ones are open to everyone.
            </p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close trip lists">
            <X />
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          {route.kind === "show" ? (
            <TripShow
              trip={current}
              loading={showLoading}
              error={showError}
              owned={owned}
              parks={tripParks}
              parkQuery={parkQuery}
              parkMatches={parkMatches}
              busy={busy}
              formError={formError}
              confirmDelete={confirmDelete}
              onBack={onOpenList}
              onRetry={() => onOpenTrip(route.id)}
              onChangeQuery={setParkQuery}
              onSave={saveTrip}
              onAddPark={addPark}
              onRemovePark={removePark}
              onSelectPark={onSelectPark}
              onAskDelete={() => setConfirmDelete(true)}
              onCancelDelete={() => setConfirmDelete(false)}
              onConfirmDelete={() => void destroyTrip()}
            />
          ) : (
            <TripBrowse
              tab={tab}
              user={user}
              pendingPark={pendingPark}
              mine={mine}
              published={published}
              loading={listLoading}
              error={listError}
              composing={composing}
              busy={busy}
              formError={formError}
              onTab={setTab}
              onNeedAuth={onNeedAuth}
              onRetry={onOpenList}
              onOpenTrip={(id) => void addPendingTo(id)}
              onCompose={() => {
                if (!user) {
                  onNeedAuth()
                  return
                }
                setComposing(true)
                setFormError(null)
              }}
              onCancelCompose={() => setComposing(false)}
              onCreate={createTrip}
              onClearPending={onClearPendingPark}
            />
          )}
        </div>
      </div>
    </div>
  )
}

function TripBrowse({
  tab,
  user,
  pendingPark,
  mine,
  published,
  loading,
  error,
  composing,
  busy,
  formError,
  onTab,
  onNeedAuth,
  onRetry,
  onOpenTrip,
  onCompose,
  onCancelCompose,
  onCreate,
  onClearPending,
}: {
  tab: Tab
  user: SessionUser | null
  pendingPark: Park | null
  mine: Trip[] | null
  published: Trip[] | null
  loading: boolean
  error: string | null
  composing: boolean
  busy: boolean
  formError: string | null
  onTab: (tab: Tab) => void
  onNeedAuth: () => void
  onRetry: () => void
  onOpenTrip: (id: number) => void
  onCompose: () => void
  onCancelCompose: () => void
  onCreate: (event: FormEvent<HTMLFormElement>) => void
  onClearPending: () => void
}) {
  const rows = tab === "mine" ? mine : published

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-1 rounded-lg bg-[hsl(var(--muted))] p-1">
        <button
          type="button"
          className={cn("rounded-md px-3 py-1.5 text-sm", tab === "public" && "bg-[hsl(var(--card))] shadow-sm")}
          onClick={() => onTab("public")}
        >
          Public lists
        </button>
        <button
          type="button"
          className={cn("rounded-md px-3 py-1.5 text-sm", tab === "mine" && "bg-[hsl(var(--card))] shadow-sm")}
          onClick={() => onTab("mine")}
        >
          My lists
        </button>
      </div>

      {pendingPark && (
        <div className="rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--muted))]/60 px-3 py-2 text-sm">
          Adding <span className="font-medium">{pendingPark.name}</span> to a list.
          <button type="button" className="ml-2 text-[hsl(var(--accent))] underline" onClick={onClearPending}>
            Cancel
          </button>
        </div>
      )}

      {tab === "mine" && !user && (
        <div className="rounded-lg border border-dashed border-[hsl(var(--border))] px-3 py-4 text-sm">
          <p>Sign in to create trip lists and keep private ones to yourself.</p>
          <Button className="mt-3" size="sm" onClick={onNeedAuth}>
            Sign in
          </Button>
          <p className="mt-2 text-xs text-[hsl(var(--muted-foreground))]">
            Public lists are still open without an account.
          </p>
        </div>
      )}

      {tab === "mine" && user && (
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm text-[hsl(var(--muted-foreground))]">Your lists, public and private.</p>
          <Button size="sm" onClick={onCompose} disabled={composing}>
            <Plus />
            New list
          </Button>
        </div>
      )}

      {composing && user && <TripFields onSubmit={onCreate} onCancel={onCancelCompose} busy={busy} error={formError} />}

      {error && (
        <ErrorState message={error} onRetry={onRetry} />
      )}

      {loading && !rows && <p className="text-sm text-[hsl(var(--muted-foreground))]">Loading trip lists…</p>}

      {!loading && !error && tab === "public" && published && published.length === 0 && (
        <p className="text-sm text-[hsl(var(--muted-foreground))]">
          No one has published a trip list yet. Sign in and mark one of yours public to share it.
        </p>
      )}

      {!loading && !error && tab === "mine" && user && mine && mine.length === 0 && !composing && (
        <p className="text-sm text-[hsl(var(--muted-foreground))]">
          You do not have any trip lists yet. Create one for a planned weekend, a want-to-go set, or parks you have already gone to.
        </p>
      )}

      {rows && rows.length > 0 && (
        <ul className="divide-y divide-[hsl(var(--border))] rounded-lg border border-[hsl(var(--border))]">
          {rows.map((trip) => (
            <li key={trip.id}>
              <button
                type="button"
                className="flex w-full flex-col items-start gap-1 px-3 py-3 text-left hover:bg-[hsl(var(--muted))]"
                onClick={() => onOpenTrip(trip.id)}
                disabled={busy}
              >
                <span className="flex w-full items-center justify-between gap-2">
                  <span className="truncate font-medium">{trip.name}</span>
                  <span className="inline-flex shrink-0 items-center gap-1 text-xs text-[hsl(var(--muted-foreground))]">
                    {trip.public ? <Globe className="h-3 w-3" /> : <Lock className="h-3 w-3" />}
                    {visibilityLabel(trip.public)}
                  </span>
                </span>
                <span className="flex flex-wrap items-center gap-2 text-xs text-[hsl(var(--muted-foreground))]">
                  <Badge>{TRIP_STATUS_LABELS[trip.status]}</Badge>
                  <span>
                    {trip.park_count} park{trip.park_count === 1 ? "" : "s"}
                  </span>
                  {formatTripDates(trip) && <span>{formatTripDates(trip)}</span>}
                  {trip.mine && tab === "public" && <span>Yours</span>}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function TripShow({
  trip,
  loading,
  error,
  owned,
  parks,
  parkQuery,
  parkMatches,
  busy,
  formError,
  confirmDelete,
  onBack,
  onRetry,
  onChangeQuery,
  onSave,
  onAddPark,
  onRemovePark,
  onSelectPark,
  onAskDelete,
  onCancelDelete,
  onConfirmDelete,
}: {
  trip: Trip | null
  loading: boolean
  error: string | null
  owned: boolean
  parks: Park[]
  parkQuery: string
  parkMatches: Park[]
  busy: boolean
  formError: string | null
  confirmDelete: boolean
  onBack: () => void
  onRetry: () => void
  onChangeQuery: (value: string) => void
  onSave: (event: FormEvent<HTMLFormElement>) => void
  onAddPark: (park: Park) => void
  onRemovePark: (parkId: number) => void
  onSelectPark: (park: Park) => void
  onAskDelete: () => void
  onCancelDelete: () => void
  onConfirmDelete: () => void
}) {
  if (loading) {
    return <p className="text-sm text-[hsl(var(--muted-foreground))]">Opening trip list…</p>
  }
  if (error || !trip) {
    return (
      <div className="space-y-3">
        <button type="button" className="text-sm text-[hsl(var(--accent))] underline" onClick={onBack}>
          Back to lists
        </button>
        <ErrorState
          message={error || "This trip list is private or was removed."}
          onRetry={onRetry}
        />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <button type="button" className="text-sm text-[hsl(var(--accent))] underline" onClick={onBack}>
        Back to lists
      </button>

      {owned ? (
        <TripFields key={trip.id} trip={trip} onSubmit={onSave} busy={busy} error={formError} submitLabel="Save list" />
      ) : (
        <div className="space-y-2">
          <h2 className="font-[family-name:var(--font-sans)] text-2xl leading-tight">{trip.name}</h2>
          <div className="flex flex-wrap items-center gap-2 text-xs text-[hsl(var(--muted-foreground))]">
            <Badge>{TRIP_STATUS_LABELS[trip.status]}</Badge>
            <span className="inline-flex items-center gap-1">
              <Globe className="h-3 w-3" />
              Public
            </span>
            {formatTripDates(trip) && <span>{formatTripDates(trip)}</span>}
          </div>
          {trip.notes ? (
            <p className="text-sm leading-relaxed">{trip.notes}</p>
          ) : (
            <p className="text-sm text-[hsl(var(--muted-foreground))]">No notes on this list.</p>
          )}
        </div>
      )}

      <section>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-[hsl(var(--muted-foreground))]">
          Parks
        </h3>
        {owned && (
          <div className="relative mt-2">
            <Input
              value={parkQuery}
              onChange={(event) => onChangeQuery(event.target.value)}
              placeholder="Search parks to add"
              autoComplete="off"
              spellCheck={false}
            />
            {parkQuery.trim().length >= 3 && (
              <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] shadow-lg">
                {parkMatches.length === 0 ? (
                  <p className="px-3 py-2 text-sm text-[hsl(var(--muted-foreground))]">No parks match that name.</p>
                ) : (
                  <ul>
                    {parkMatches.map((park) => (
                      <li key={park.id}>
                        <button
                          type="button"
                          className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-[hsl(var(--muted))]"
                          onClick={() => onAddPark(park)}
                          disabled={busy}
                        >
                          <span
                            className="h-2.5 w-2.5 shrink-0 rounded-full"
                            style={{ background: TYPE_COLORS[park.park_type] }}
                          />
                          <span className="min-w-0 flex-1 truncate">{park.name}</span>
                          <span className="text-xs text-[hsl(var(--muted-foreground))]">
                            {TYPE_LABELS[park.park_type]}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        )}
        {parks.length === 0 ? (
          <p className="mt-2 text-sm text-[hsl(var(--muted-foreground))]">
            {owned ? "No parks on this list yet. Search by name to add one." : "This list has no parks yet."}
          </p>
        ) : (
          <ul className="mt-2 divide-y divide-[hsl(var(--border))] rounded-lg border border-[hsl(var(--border))]">
            {parks.map((park) => (
              <li key={park.id} className="flex items-center gap-2 px-3 py-2">
                <button
                  type="button"
                  className="flex min-w-0 flex-1 items-center gap-2 text-left text-sm hover:underline"
                  onClick={() => onSelectPark(park)}
                >
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ background: TYPE_COLORS[park.park_type] }}
                  />
                  <span className="truncate">{park.name}</span>
                </button>
                {owned && (
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Remove ${park.name}`}
                    onClick={() => onRemovePark(park.id)}
                    disabled={busy}
                  >
                    <X />
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {owned && (
        <div className="border-t border-[hsl(var(--border))] pt-4">
          {confirmDelete ? (
            <div className="space-y-2">
              <p className="text-sm">Delete this list? Parks are not removed from the map.</p>
              <div className="flex gap-2">
                <Button variant="destructive" size="sm" onClick={onConfirmDelete} disabled={busy}>
                  Delete list
                </Button>
                <Button variant="outline" size="sm" onClick={onCancelDelete}>
                  Keep it
                </Button>
              </div>
            </div>
          ) : (
            <Button variant="ghost" size="sm" onClick={onAskDelete}>
              <Trash2 />
              Delete list
            </Button>
          )}
        </div>
      )}
    </div>
  )
}

function TripFields({
  trip,
  onSubmit,
  onCancel,
  busy,
  error,
  submitLabel = "Create list",
}: {
  trip?: Trip
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  onCancel?: () => void
  busy: boolean
  error: string | null
  submitLabel?: string
}) {
  return (
    <form className="space-y-3 rounded-lg border border-[hsl(var(--border))] p-3" onSubmit={onSubmit}>
      <div className="space-y-1.5">
        <Label htmlFor="trip-name">Name</Label>
        <Input id="trip-name" name="name" required maxLength={120} defaultValue={trip?.name ?? ""} placeholder="North Shore weekend" />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="trip-status">Status</Label>
        <select id="trip-status" name="status" className={fieldClass} defaultValue={trip?.status ?? "planned"}>
          {TRIP_STATUSES.map((status) => (
            <option key={status} value={status}>
              {TRIP_STATUS_LABELS[status]}
            </option>
          ))}
        </select>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1.5">
          <Label htmlFor="trip-starts">Start (optional)</Label>
          <Input id="trip-starts" name="starts_on" type="date" defaultValue={trip?.starts_on ?? ""} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="trip-ends">End (optional)</Label>
          <Input id="trip-ends" name="ends_on" type="date" defaultValue={trip?.ends_on ?? ""} />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="trip-notes">Notes</Label>
        <Textarea id="trip-notes" name="notes" maxLength={4000} defaultValue={trip?.notes ?? ""} placeholder="Campgrounds, ferry times, who is driving…" />
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          name="public"
          defaultChecked={trip?.public ?? false}
          className="h-4 w-4 rounded border border-[hsl(var(--primary))] accent-[hsl(var(--primary))]"
        />
        Make this list public
      </label>
      <p className="text-xs text-[hsl(var(--muted-foreground))]">
        Private lists are only visible when you are signed in. Public lists can be opened by anyone with the link.
      </p>
      {error && <p className="text-sm text-[hsl(var(--destructive))]">{error}</p>}
      <div className="flex gap-2">
        <Button type="submit" disabled={busy}>
          {busy ? "Saving…" : submitLabel}
        </Button>
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  )
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded-lg border border-[#3f1d1d] bg-[#3f1d1d]/40 px-3 py-3 text-sm">
      <p>{message}</p>
      <Button className="mt-2" size="sm" variant="outline" onClick={onRetry}>
        Try again
      </Button>
    </div>
  )
}
