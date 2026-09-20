export type ParkType = "national" | "state" | "regional" | "county"

export type Park = {
  id: number
  name: string
  park_type: ParkType
  managing_agency: string | null
  source: string
  source_id: string
  source_url: string | null
  latitude: number
  longitude: number
  highlights: string | null
  amenities: string[]
  activities: string[]
  favorited: boolean | null
  visited: boolean | null
}

export type SessionUser = {
  id: number
  email: string
}

export type SessionPayload = {
  user: SessionUser | null
  csrf_token: string
  google_oauth: boolean
}

export type ParksPayload = {
  parks: Park[]
  meta: {
    count: number
    types: ParkType[]
    amenities: string[]
    activities: string[]
    attribution: string[]
  }
}

export type Origin = {
  kind: "gps" | "pin"
  latitude: number
  longitude: number
}

export type Filters = {
  types: ParkType[]
  amenities: string[]
  activities: string[]
  maxMiles: number | null
  favorited: boolean
  visited: boolean
  unvisited: boolean
}
