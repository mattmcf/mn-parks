import type { Park } from "@/types"

export const TRIP_STATUSES = ["planned", "want_to_go", "gone"] as const

export type TripStatus = (typeof TRIP_STATUSES)[number]

export const TRIP_STATUS_LABELS: Record<TripStatus, string> = {
  planned: "Planned",
  want_to_go: "Want to go",
  gone: "Gone",
}

export type TripPark = Park & { position: number }

export type Trip = {
  id: number
  name: string
  notes: string | null
  status: TripStatus
  public: boolean
  starts_on: string | null
  ends_on: string | null
  park_count: number
  mine: boolean
  updated_at: string
  parks?: TripPark[]
}

export type TripRoute = { kind: "none" } | { kind: "browse" } | { kind: "show"; id: number }

export function isTripStatus(value: string): value is TripStatus {
  return (TRIP_STATUSES as readonly string[]).includes(value)
}

export function parseTripPath(pathname: string): TripRoute {
  const path = pathname.replace(/\/+$/, "") || "/"
  if (path === "/trips") return { kind: "browse" }
  const match = path.match(/^\/trips\/(\d+)$/)
  if (match) return { kind: "show", id: Number(match[1]) }
  return { kind: "none" }
}

export function tripListPath(): string {
  return "/trips"
}

export function tripPath(id: number): string {
  return `/trips/${id}`
}

export function formatIsoDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number)
  if (!year || !month || !day) return value
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  })
}

export function formatTripDates(trip: Pick<Trip, "starts_on" | "ends_on">): string | null {
  if (trip.starts_on && trip.ends_on) {
    return `${formatIsoDate(trip.starts_on)} – ${formatIsoDate(trip.ends_on)}`
  }
  if (trip.starts_on) return `From ${formatIsoDate(trip.starts_on)}`
  if (trip.ends_on) return `Until ${formatIsoDate(trip.ends_on)}`
  return null
}

export function visibilityLabel(isPublic: boolean): string {
  return isPublic ? "Public" : "Private"
}

export function canEditTrip(trip: Pick<Trip, "mine">): boolean {
  return trip.mine === true
}
