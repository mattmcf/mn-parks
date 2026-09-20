import { Check, Heart, X } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { labelFor, TYPE_COLORS, TYPE_LABELS } from "@/lib/constants"
import { formatMiles } from "@/lib/geo"
import type { Origin, Park, SessionUser } from "@/types"

type Props = {
  park: Park
  origin: Origin | null
  miles: number | null
  user: SessionUser | null
  onClose: () => void
  onNeedAuth: () => void
  onToggle: (field: "favorited" | "visited", value: boolean) => void
}

export function ParkDetail({ park, origin, miles, user, onClose, onNeedAuth, onToggle }: Props) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-start justify-between gap-3 border-b border-[hsl(var(--border))] px-4 py-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[hsl(var(--muted-foreground))]">
            {TYPE_LABELS[park.park_type]}
          </p>
          <h2 className="font-[family-name:var(--font-sans)] text-2xl leading-tight">{park.name}</h2>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close details">
          <X />
        </Button>
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span
            className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs text-white"
            style={{ background: TYPE_COLORS[park.park_type] }}
          >
            {TYPE_LABELS[park.park_type]}
          </span>
          {park.managing_agency && (
            <span className="text-[hsl(var(--muted-foreground))]">{park.managing_agency}</span>
          )}
        </div>

        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-[hsl(var(--muted-foreground))]">
            Distance
          </h3>
          {origin && miles != null ? (
            <p className="mt-1 text-sm">
              {formatMiles(miles)} straight-line from your {origin.kind === "pin" ? "From pin" : "current location"}.
            </p>
          ) : (
            <p className="mt-1 text-sm text-[hsl(var(--muted-foreground))]">
              Set your location or drop a From pin to see distance.
            </p>
          )}
        </section>

        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-[hsl(var(--muted-foreground))]">
            Highlights
          </h3>
          {park.highlights ? (
            <p className="mt-1 text-sm leading-relaxed">{park.highlights}</p>
          ) : (
            <p className="mt-1 text-sm text-[hsl(var(--muted-foreground))]">
              Not listed in our sources yet.
            </p>
          )}
        </section>

        <ChipBlock title="Amenities" kind="amenity" values={park.amenities} />
        <ChipBlock title="Activities" kind="activity" values={park.activities} />

        {park.source_url && (
          <a
            className="inline-block text-sm text-[hsl(var(--accent))] underline"
            href={park.source_url}
            target="_blank"
            rel="noreferrer"
          >
            Official source
          </a>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2 border-t border-[hsl(var(--border))] p-3">
        <Button
          variant={park.favorited ? "default" : "outline"}
          onClick={() => (user ? onToggle("favorited", !park.favorited) : onNeedAuth())}
        >
          <Heart className={park.favorited ? "fill-current" : ""} />
          {park.favorited ? "Saved" : "Favorite"}
        </Button>
        <Button
          variant={park.visited ? "accent" : "outline"}
          onClick={() => (user ? onToggle("visited", !park.visited) : onNeedAuth())}
        >
          <Check />
          {park.visited ? "Visited" : "Mark visited"}
        </Button>
      </div>
    </div>
  )
}

function ChipBlock({
  title,
  kind,
  values,
}: {
  title: string
  kind: "amenity" | "activity"
  values: string[]
}) {
  return (
    <section>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-[hsl(var(--muted-foreground))]">
        {title}
      </h3>
      {values.length ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {values.map((value) => (
            <Badge key={value}>{labelFor(kind, value)}</Badge>
          ))}
        </div>
      ) : (
        <p className="mt-1 text-sm text-[hsl(var(--muted-foreground))]">
          Not listed in our sources yet.
        </p>
      )}
    </section>
  )
}
