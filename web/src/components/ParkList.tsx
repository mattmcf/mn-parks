import { Heart, MapPin } from "lucide-react"
import { TYPE_COLORS, TYPE_LABELS } from "@/lib/constants"
import { formatMiles } from "@/lib/geo"
import type { Origin, Park } from "@/types"

type Props = {
  parks: Park[]
  selectedId: number | null
  origin: Origin | null
  distances: Map<number, number>
  onSelect: (park: Park) => void
}

export function ParkList({ parks, selectedId, origin, distances, onSelect }: Props) {
  if (parks.length === 0) {
    return (
      <p className="px-4 py-6 text-sm text-[hsl(var(--muted-foreground))]">
        No parks in this view match your filters. Pan the map or clear a filter.
      </p>
    )
  }

  return (
    <ul className="divide-y divide-[hsl(var(--border))]">
      {parks.map((park) => {
        const miles = distances.get(park.id)
        return (
          <li key={park.id}>
            <button
              type="button"
              onClick={() => onSelect(park)}
              className={`flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-[hsl(var(--muted))] ${
                selectedId === park.id ? "bg-[hsl(var(--muted))]" : ""
              }`}
            >
              <span
                className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ background: TYPE_COLORS[park.park_type] }}
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{park.name}</span>
                <span className="mt-0.5 flex items-center gap-2 text-xs text-[hsl(var(--muted-foreground))]">
                  <span>{TYPE_LABELS[park.park_type]}</span>
                  {origin && miles != null && (
                    <span className="inline-flex items-center gap-0.5">
                      <MapPin className="h-3 w-3" />
                      {formatMiles(miles)}
                    </span>
                  )}
                  {park.favorited && <Heart className="h-3 w-3 fill-current" />}
                </span>
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
