import { useEffect, useMemo, useState } from "react"
import {
  ChevronLeft,
  ChevronRight,
  Dices,
  Filter,
  List,
  LocateFixed,
  LogOut,
  Pin,
  X,
} from "lucide-react"
import { AuthDialog } from "@/components/AuthDialog"
import { FilterPanel, defaultFilters } from "@/components/FilterPanel"
import { MapCanvas } from "@/components/MapCanvas"
import { ParkDetail } from "@/components/ParkDetail"
import { ParkList } from "@/components/ParkList"
import { Button } from "@/components/ui/button"
import { api } from "@/lib/api"
import { TYPE_COLORS, TYPE_LABELS } from "@/lib/constants"
import { formatMiles, haversineMiles } from "@/lib/geo"
import type { Filters, Origin, Park, SessionUser } from "@/types"

const ORIGIN_KEY = "mn-parks-origin"

type StoredOrigin = { gps: Origin | null; pin: Origin | null }

function loadStoredOrigin(): StoredOrigin {
  try {
    const raw = localStorage.getItem(ORIGIN_KEY)
    if (!raw) return { gps: null, pin: null }
    const parsed = JSON.parse(raw) as StoredOrigin | Origin
    if ("kind" in parsed) {
      return parsed.kind === "pin" ? { gps: null, pin: parsed } : { gps: parsed, pin: null }
    }
    return { gps: parsed.gps ?? null, pin: parsed.pin ?? null }
  } catch {
    return { gps: null, pin: null }
  }
}

export default function App() {
  const [parks, setParks] = useState<Park[]>([])
  const [amenities, setAmenities] = useState<string[]>([])
  const [activities, setActivities] = useState<string[]>([])
  const [attribution, setAttribution] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [user, setUser] = useState<SessionUser | null>(null)
  const [googleOAuth, setGoogleOAuth] = useState(false)
  const [filters, setFilters] = useState<Filters>(defaultFilters)
  const [gpsOrigin, setGpsOrigin] = useState<Origin | null>(() => loadStoredOrigin().gps)
  const [pinOrigin, setPinOrigin] = useState<Origin | null>(() => loadStoredOrigin().pin)
  const origin = pinOrigin ?? gpsOrigin
  const [placingPin, setPlacingPin] = useState(false)
  const [viewportIds, setViewportIds] = useState<number[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [flyTo, setFlyTo] = useState<{ id: number; longitude: number; latitude: number } | null>(null)
  const [listOpen, setListOpen] = useState(true)
  const [mobileListOpen, setMobileListOpen] = useState(false)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [authOpen, setAuthOpen] = useState(false)
  const [gpsBusy, setGpsBusy] = useState(false)
  const [gpsError, setGpsError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([api.parks(), api.session()])
      .then(([parkPayload, session]) => {
        if (cancelled) return
        setParks(parkPayload.parks)
        setAmenities(parkPayload.meta.amenities)
        setActivities(parkPayload.meta.activities)
        setAttribution(parkPayload.meta.attribution)
        setUser(session.user)
        setGoogleOAuth(session.google_oauth)
        setError(null)
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load parks.")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    localStorage.setItem(ORIGIN_KEY, JSON.stringify({ gps: gpsOrigin, pin: pinOrigin }))
  }, [gpsOrigin, pinOrigin])

  const distances = useMemo(() => {
    const map = new Map<number, number>()
    if (!origin) return map
    for (const park of parks) {
      map.set(park.id, haversineMiles(origin, park))
    }
    return map
  }, [origin, parks])

  const filtered = useMemo(() => {
    return parks.filter((park) => {
      if (!filters.types.includes(park.park_type)) return false
      if (filters.amenities.some((item) => !park.amenities.includes(item))) return false
      if (filters.activities.some((item) => !park.activities.includes(item))) return false
      if (filters.favorited && !park.favorited) return false
      if (filters.visited && !park.visited) return false
      if (filters.unvisited && park.visited) return false
      if (origin && filters.maxMiles != null) {
        const miles = distances.get(park.id) ?? Infinity
        if (miles > filters.maxMiles) return false
      }
      return true
    })
  }, [parks, filters, origin, distances])

  const listParks = useMemo(() => {
    const inView = filtered.filter((park) => viewportIds.includes(park.id))
    return [...inView].sort((a, b) => {
      if (origin) {
        return (distances.get(a.id) ?? Infinity) - (distances.get(b.id) ?? Infinity)
      }
      return a.name.localeCompare(b.name)
    })
  }, [filtered, viewportIds, origin, distances])

  const selected = parks.find((park) => park.id === selectedId) ?? null
  const noFilterMatch = !loading && parks.length > 0 && filtered.length === 0

  const selectPark = (park: Park) => {
    setSelectedId(park.id)
    setFlyTo({ id: park.id, longitude: park.longitude, latitude: park.latitude })
    setMobileListOpen(false)
  }

  const useGps = () => {
    if (!navigator.geolocation) {
      setGpsError("This browser does not support geolocation.")
      return
    }
    setGpsBusy(true)
    setGpsError(null)
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setGpsOrigin({
          kind: "gps",
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        })
        setGpsBusy(false)
        if (pinOrigin) {
          setGpsError("GPS saved. Distance still uses your From pin until you clear it.")
        }
      },
      () => {
        setGpsBusy(false)
        setGpsError("Location permission was denied or unavailable.")
      },
      { enableHighAccuracy: true, timeout: 12000 },
    )
  }

  const dropPin = (lng: number, lat: number) => {
    setPinOrigin({ kind: "pin", latitude: lat, longitude: lng })
    setPlacingPin(false)
    setGpsError(null)
  }

  const randomPark = async () => {
    try {
      const { park } = await api.randomPark()
      setParks((current) => current.map((item) => (item.id === park.id ? park : item)))
      selectPark(park)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Random pick failed.")
    }
  }

  const toggleState = async (field: "favorited" | "visited", value: boolean) => {
    if (!selected) return
    try {
      const { park } = await api.setUserState(selected.id, { [field]: value })
      setParks((current) => current.map((item) => (item.id === park.id ? park : item)))
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save that.")
    }
  }

  const reloadParks = async () => {
    const payload = await api.parks()
    setParks(payload.parks)
  }

  return (
    <div className="flex h-full flex-col bg-[hsl(var(--background))]">
      <header className="z-20 flex items-center gap-2 border-b border-[hsl(var(--border))] bg-[hsl(var(--card))] px-3 py-2 md:px-4">
        <div className="min-w-0 flex-1">
          <p className="font-[family-name:var(--font-sans)] text-lg leading-none md:text-xl">MN Parks</p>
          <p className="hidden truncate text-xs text-[hsl(var(--muted-foreground))] sm:block">
            State, national, regional, and county parks inside Minnesota
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setFiltersOpen(true)}>
          <Filter />
          Filters
        </Button>
        <Button variant="accent" size="sm" onClick={() => void randomPark()}>
          <Dices />
          <span className="hidden sm:inline">Random</span>
        </Button>
        {user ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              void api.logout().then((session) => {
                setUser(session.user)
                void reloadParks()
              })
            }}
          >
            <LogOut />
            <span className="hidden max-w-32 truncate sm:inline">{user.email}</span>
          </Button>
        ) : (
          <Button size="sm" onClick={() => setAuthOpen(true)}>
            Sign in
          </Button>
        )}
      </header>

      {(error || gpsError) && (
        <div className="flex items-center justify-between gap-3 bg-[#3f1d1d] px-4 py-2 text-sm text-[#fde8e8]">
          <span>{error || gpsError}</span>
          <button type="button" onClick={() => { setError(null); setGpsError(null) }}>
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <div className="relative min-h-0 flex-1">
        <div className="absolute inset-0 min-h-0">
          {loading ? (
            <div className="flex h-full items-center justify-center bg-[#d7e4d8] text-[hsl(var(--muted-foreground))]">
              Loading Minnesota parks…
            </div>
          ) : parks.length === 0 && !error ? (
            <div className="flex h-full items-center justify-center bg-[#d7e4d8] p-6 text-center text-[hsl(var(--muted-foreground))]">
              No parks are loaded yet. Run `bin/rails db:seed` and refresh.
            </div>
          ) : (
            <MapCanvas
              parks={filtered}
              selectedId={selectedId}
              origin={origin}
              placingPin={placingPin}
              onSelect={selectPark}
              onMove={setViewportIds}
              onDropPin={dropPin}
              flyTo={flyTo}
            />
          )}
        </div>

        {noFilterMatch && (
          <div className="absolute left-1/2 top-4 z-10 w-[min(24rem,calc(100%-2rem))] -translate-x-1/2 rounded-lg bg-[hsl(var(--card))] px-4 py-3 text-center text-sm shadow">
            No parks match those filters. Clear a type, amenity, or distance chip and try again.
          </div>
        )}

        <div className="pointer-events-none absolute right-3 top-3 z-10 flex flex-col gap-2">
          <Button className="pointer-events-auto shadow" variant="secondary" size="sm" onClick={useGps} disabled={gpsBusy}>
            <LocateFixed />
            {gpsBusy ? "Locating…" : "Use my location"}
          </Button>
          <Button
            className="pointer-events-auto shadow"
            variant={placingPin ? "accent" : "secondary"}
            size="sm"
            onClick={() => setPlacingPin((value) => !value)}
          >
            <Pin />
            {placingPin ? "Click the map…" : "Drop From pin"}
          </Button>
          {origin && (
            <Button
              className="pointer-events-auto shadow"
              variant="outline"
              size="sm"
              onClick={() => {
                setPinOrigin(null)
                setGpsOrigin(null)
                setPlacingPin(false)
              }}
            >
              Clear origin
            </Button>
          )}
        </div>

        {origin && (
          <div className="absolute bottom-16 right-3 z-10 rounded-md bg-[hsl(var(--card))]/95 px-3 py-1.5 text-xs shadow">
            Measuring from {origin.kind === "pin" ? "your From pin" : "GPS"}
            {selected && distances.get(selected.id) != null && ` · ${formatMiles(distances.get(selected.id)!)} to selection`}
          </div>
        )}

        <aside
          className={`absolute bottom-0 left-0 top-0 z-10 hidden w-[min(22rem,100%)] flex-col border-r border-[hsl(var(--border))] bg-[hsl(var(--card))]/95 shadow-lg backdrop-blur md:flex ${
            listOpen ? "" : "w-10"
          }`}
        >
          {listOpen ? (
            <>
              <div className="flex items-center justify-between gap-2 border-b border-[hsl(var(--border))] px-3 py-2">
                <div>
                  <p className="text-sm font-medium">In this view</p>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                    {listParks.length} park{listParks.length === 1 ? "" : "s"} · sorted{" "}
                    {origin ? "by distance" : "by name"}
                  </p>
                </div>
                <Button variant="ghost" size="icon" onClick={() => setListOpen(false)} aria-label="Collapse list">
                  <ChevronLeft />
                </Button>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto">
                {selected && (
                  <div className="border-b border-[hsl(var(--border))]">
                    <ParkDetail
                      park={selected}
                      origin={origin}
                      miles={distances.get(selected.id) ?? null}
                      user={user}
                      onClose={() => setSelectedId(null)}
                      onNeedAuth={() => setAuthOpen(true)}
                      onToggle={toggleState}
                    />
                  </div>
                )}
                <ParkList
                  parks={listParks}
                  selectedId={selectedId}
                  origin={origin}
                  distances={distances}
                  onSelect={selectPark}
                />
              </div>
            </>
          ) : (
            <Button variant="ghost" className="h-full rounded-none" onClick={() => setListOpen(true)}>
              <ChevronRight />
            </Button>
          )}
        </aside>

        <button
          type="button"
          className="absolute bottom-4 left-1/2 z-10 flex -translate-x-1/2 items-center gap-2 rounded-full bg-[hsl(var(--card))] px-4 py-2 text-sm shadow md:hidden"
          onClick={() => setMobileListOpen(true)}
        >
          <List className="h-4 w-4" />
          {listParks.length} in view
        </button>
      </div>

      <footer className="hidden items-center gap-3 overflow-x-auto border-t border-[hsl(var(--border))] bg-[hsl(var(--card))] px-4 py-1.5 text-[11px] text-[hsl(var(--muted-foreground))] md:flex">
        {(Object.keys(TYPE_LABELS) as Array<keyof typeof TYPE_LABELS>).map((type) => (
          <span key={type} className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ background: TYPE_COLORS[type] }} />
            {TYPE_LABELS[type]}
          </span>
        ))}
        <span className="ml-auto truncate">{attribution[0]}</span>
      </footer>

      {mobileListOpen && (
        <div className="fixed inset-0 z-30 bg-black/40 md:hidden" onClick={() => setMobileListOpen(false)}>
          <div
            className="absolute inset-x-0 bottom-0 max-h-[80vh] overflow-hidden rounded-t-2xl bg-[hsl(var(--card))]"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between px-4 py-3">
              <p className="font-medium">Parks in this view</p>
              <Button variant="ghost" size="icon" onClick={() => setMobileListOpen(false)}>
                <X />
              </Button>
            </div>
            <div className="max-h-[70vh] overflow-y-auto">
              {selected && (
                <ParkDetail
                  park={selected}
                  origin={origin}
                  miles={distances.get(selected.id) ?? null}
                  user={user}
                  onClose={() => setSelectedId(null)}
                  onNeedAuth={() => setAuthOpen(true)}
                  onToggle={toggleState}
                />
              )}
              <ParkList
                parks={listParks}
                selectedId={selectedId}
                origin={origin}
                distances={distances}
                onSelect={selectPark}
              />
            </div>
          </div>
        </div>
      )}

      {filtersOpen && (
        <div className="fixed inset-0 z-40 bg-black/40" onClick={() => setFiltersOpen(false)}>
          <div
            className="absolute right-0 top-0 h-full w-[min(22rem,100%)] overflow-y-auto bg-[hsl(var(--card))] p-4 shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="font-[family-name:var(--font-sans)] text-xl">Filters</h2>
              <Button variant="ghost" size="icon" onClick={() => setFiltersOpen(false)}>
                <X />
              </Button>
            </div>
            <FilterPanel
              filters={filters}
              origin={origin}
              amenityOptions={amenities}
              activityOptions={activities}
              loggedIn={Boolean(user)}
              onChange={setFilters}
            />
            <Button className="mt-4 w-full" variant="outline" onClick={() => setFilters(defaultFilters())}>
              Reset filters
            </Button>
          </div>
        </div>
      )}

      <AuthDialog
        open={authOpen}
        googleOAuth={googleOAuth}
        onOpenChange={setAuthOpen}
        onAuthed={(session) => {
          setUser(session.user)
          void reloadParks()
        }}
      />
    </div>
  )
}
