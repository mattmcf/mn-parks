import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react"
import { Loader2, Search } from "lucide-react"
import { Input } from "@/components/ui/input"
import { TYPE_COLORS, TYPE_LABELS } from "@/lib/constants"
import { MAX_NAME_MATCHES, MIN_NAME_QUERY_LENGTH, nameMatchRange, rankParkNameMatches } from "@/lib/park-search"
import { cn } from "@/lib/utils"
import type { Park } from "@/types"

type Props = {
  parks: Park[]
  loading: boolean
  error: string | null
  selectedId: number | null
  onSelect: (park: Park) => void
}

function HighlightedName({ name, query }: { name: string; query: string }) {
  const range = nameMatchRange(name, query)
  if (!range) return name
  return (
    <>
      {name.slice(0, range.start)}
      <span className="rounded-sm bg-[hsl(var(--accent))]/15 font-semibold text-[hsl(var(--foreground))]">
        {name.slice(range.start, range.end)}
      </span>
      {name.slice(range.end)}
    </>
  )
}

export function ParkSearch({ parks, loading, error, selectedId, onSelect }: Props) {
  const listId = useId()
  const rootRef = useRef<HTMLDivElement>(null)
  const [query, setQuery] = useState("")
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)

  const trimmed = query.trim()
  const submitted = trimmed.length >= MIN_NAME_QUERY_LENGTH
  const namesReady = !loading && parks.length > 0
  const namesFailed = !loading && parks.length === 0 && Boolean(error)
  const namesEmpty = !loading && parks.length === 0 && !error
  const matches = useMemo(
    () => (submitted && namesReady ? rankParkNameMatches(parks, trimmed, MAX_NAME_MATCHES) : []),
    [parks, submitted, namesReady, trimmed],
  )

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener("pointerdown", onPointerDown)
    return () => document.removeEventListener("pointerdown", onPointerDown)
  }, [open])

  const showList = open && submitted
  const optionCount = matches.length
  const clampedIndex = optionCount ? Math.min(activeIndex, optionCount - 1) : 0
  const activePark = matches[clampedIndex] ?? null

  const pick = (park: Park) => {
    setQuery(park.name)
    setOpen(false)
    onSelect(park)
  }

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      setOpen(false)
      return
    }
    if (!submitted) return
    if (event.key === "ArrowDown") {
      event.preventDefault()
      setOpen(true)
      if (optionCount) setActiveIndex((index) => (Math.min(index, optionCount - 1) + 1) % optionCount)
      return
    }
    if (event.key === "ArrowUp") {
      event.preventDefault()
      setOpen(true)
      if (optionCount) setActiveIndex((index) => (Math.min(index, optionCount - 1) - 1 + optionCount) % optionCount)
      return
    }
    if (event.key === "Enter") {
      if (!showList || !activePark) return
      event.preventDefault()
      pick(activePark)
    }
  }

  let status: string | null = null
  if (!submitted) {
    status = null
  } else if (loading) {
    status = "Loading park names…"
  } else if (namesFailed) {
    status = "Park names could not load. Try refresh."
  } else if (namesEmpty) {
    status = "No park names are loaded yet."
  } else if (matches.length === 0) {
    status = "No parks match that name."
  }

  return (
    <div ref={rootRef} className="relative min-w-0">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[hsl(var(--muted-foreground))]" />
      <Input
        role="combobox"
        aria-label="Search parks by name"
        aria-autocomplete="list"
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={showList && activePark ? `${listId}-opt-${activePark.id}` : undefined}
        value={query}
        placeholder="Search parks"
        autoComplete="off"
        spellCheck={false}
        className="h-8 pl-8 pr-3"
        onChange={(event) => {
          setQuery(event.target.value)
          setActiveIndex(0)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />
      {showList && (
        <div
          className="absolute left-0 right-0 z-30 mt-1 overflow-hidden rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] shadow-lg sm:left-auto sm:right-auto sm:w-full sm:min-w-[20rem]"
        >
          {status ? (
            <p className="flex items-center gap-2 px-3 py-2.5 text-sm text-[hsl(var(--muted-foreground))]">
              {loading && <Loader2 className="h-4 w-4 shrink-0 animate-spin" />}
              {status}
            </p>
          ) : (
            <ul id={listId} role="listbox" aria-label="Park name matches">
              {matches.map((park, index) => {
                const active = index === clampedIndex
                return (
                  <li key={park.id} role="presentation">
                    <button
                      type="button"
                      id={`${listId}-opt-${park.id}`}
                      role="option"
                      aria-selected={active}
                      className={cn(
                        "flex w-full items-start gap-2 px-3 py-2 text-left text-sm hover:bg-[hsl(var(--muted))]",
                        active && "bg-[hsl(var(--muted))]",
                        selectedId === park.id && "font-medium",
                      )}
                      onMouseEnter={() => setActiveIndex(index)}
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => pick(park)}
                    >
                      <span
                        className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full"
                        style={{ background: TYPE_COLORS[park.park_type] }}
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate">
                          <HighlightedName name={park.name} query={trimmed} />
                        </span>
                        <span className="text-xs text-[hsl(var(--muted-foreground))]">
                          {TYPE_LABELS[park.park_type]}
                        </span>
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
