import { Checkbox } from "@/components/ui/checkbox"
import { labelFor, TYPE_LABELS } from "@/lib/constants"
import type { Filters, Origin, ParkType } from "@/types"

const TYPES: ParkType[] = ["national", "state", "wilderness", "regional", "county"]
const DISTANCES = [15, 30, 60, 120]

type Props = {
  filters: Filters
  origin: Origin | null
  amenityOptions: string[]
  activityOptions: string[]
  loggedIn: boolean
  onChange: (next: Filters) => void
}

export function FilterPanel({
  filters,
  origin,
  amenityOptions,
  activityOptions,
  loggedIn,
  onChange,
}: Props) {
  const toggleType = (type: ParkType) => {
    const types = filters.types.includes(type)
      ? filters.types.filter((item) => item !== type)
      : [...filters.types, type]
    onChange({ ...filters, types })
  }

  const toggleValue = (key: "amenities" | "activities", value: string) => {
    const current = filters[key]
    const next = current.includes(value) ? current.filter((item) => item !== value) : [...current, value]
    onChange({ ...filters, [key]: next })
  }

  return (
    <div className="space-y-5 text-sm">
      <fieldset>
        <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-[hsl(var(--muted-foreground))]">
          Park type
        </legend>
        <div className="grid grid-cols-2 gap-2">
          {TYPES.map((type) => (
            <label key={type} className="flex items-center gap-2">
              <Checkbox
                checked={filters.types.includes(type)}
                onCheckedChange={() => toggleType(type)}
              />
              {TYPE_LABELS[type]}
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-[hsl(var(--muted-foreground))]">
          Night sky
        </legend>
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            className={`rounded-full border px-2.5 py-1 text-xs ${
              filters.darkSky
                ? "border-[hsl(var(--primary))] bg-[hsl(var(--primary))] text-white"
                : "border-[hsl(var(--border))]"
            }`}
            onClick={() => onChange({ ...filters, darkSky: !filters.darkSky })}
            aria-pressed={filters.darkSky}
          >
            Dark Sky
          </button>
        </div>
        <p className="mt-2 text-xs text-[hsl(var(--muted-foreground))]">
          Certified DarkSky International places only. Nearby dark sites are not guessed.
        </p>
      </fieldset>

      <fieldset>
        <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-[hsl(var(--muted-foreground))]">
          Distance
        </legend>
        {origin ? (
          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              className={`rounded-full border px-2.5 py-1 text-xs ${filters.maxMiles == null ? "border-[hsl(var(--primary))] bg-[hsl(var(--primary))] text-white" : "border-[hsl(var(--border))]"}`}
              onClick={() => onChange({ ...filters, maxMiles: null })}
            >
              Any
            </button>
            {DISTANCES.map((miles) => (
              <button
                key={miles}
                type="button"
                className={`rounded-full border px-2.5 py-1 text-xs ${filters.maxMiles === miles ? "border-[hsl(var(--primary))] bg-[hsl(var(--primary))] text-white" : "border-[hsl(var(--border))]"}`}
                onClick={() => onChange({ ...filters, maxMiles: miles })}
              >
                {miles} mi
              </button>
            ))}
          </div>
        ) : (
          <p className="text-[hsl(var(--muted-foreground))]">
            Set your location or drop a From pin to filter by distance.
          </p>
        )}
      </fieldset>

      <ChipFilter
        title="Amenities"
        kind="amenity"
        options={amenityOptions}
        selected={filters.amenities}
        onToggle={(value) => toggleValue("amenities", value)}
      />
      <ChipFilter
        title="Activities"
        kind="activity"
        options={activityOptions}
        selected={filters.activities}
        onToggle={(value) => toggleValue("activities", value)}
      />

      <fieldset>
        <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-[hsl(var(--muted-foreground))]">
          Your parks
        </legend>
        {loggedIn ? (
          <div className="space-y-2">
            <label className="flex items-center gap-2">
              <Checkbox
                checked={filters.favorited}
                onCheckedChange={(value) => onChange({ ...filters, favorited: value === true })}
              />
              Favorited
            </label>
            <label className="flex items-center gap-2">
              <Checkbox
                checked={filters.visited}
                onCheckedChange={(value) => onChange({ ...filters, visited: value === true })}
              />
              Visited
            </label>
            <label className="flex items-center gap-2">
              <Checkbox
                checked={filters.unvisited}
                onCheckedChange={(value) => onChange({ ...filters, unvisited: value === true })}
              />
              Not yet visited
            </label>
          </div>
        ) : (
          <p className="text-[hsl(var(--muted-foreground))]">
            Sign in to filter by favorites and visited parks.
          </p>
        )}
      </fieldset>
    </div>
  )
}

function ChipFilter({
  title,
  kind,
  options,
  selected,
  onToggle,
}: {
  title: string
  kind: "amenity" | "activity"
  options: string[]
  selected: string[]
  onToggle: (value: string) => void
}) {
  return (
    <fieldset>
      <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-[hsl(var(--muted-foreground))]">
        {title}
      </legend>
      {options.length === 0 ? (
        <p className="text-[hsl(var(--muted-foreground))]">None listed in the current inventory.</p>
      ) : (
        <div className="flex max-h-36 flex-wrap gap-1.5 overflow-y-auto">
          {options.map((value) => {
            const active = selected.includes(value)
            return (
              <button
                key={value}
                type="button"
                onClick={() => onToggle(value)}
                className={`rounded-full border px-2.5 py-1 text-xs ${
                  active
                    ? "border-[hsl(var(--primary))] bg-[hsl(var(--primary))] text-white"
                    : "border-[hsl(var(--border))]"
                }`}
              >
                {labelFor(kind, value)}
              </button>
            )
          })}
        </div>
      )}
    </fieldset>
  )
}

export function defaultFilters(): Filters {
  return {
    types: ["national", "state", "wilderness", "regional", "county"],
    amenities: [],
    activities: [],
    maxMiles: null,
    favorited: false,
    visited: false,
    unvisited: false,
    darkSky: false,
  }
}
