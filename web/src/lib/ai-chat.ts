import type { Park } from "@/types"
import type { Trip } from "@/lib/trips"

export const AI_CHAT_STORAGE_KEY = "mn-parks-ai-chat"

export const EMPTY_COMPOSER =
  "Ask for parks by what you want to do — camping with showers, dark skies, a North Shore weekend…"

export const PLAN_ERROR = "Couldn't plan that. Try again."

export const NO_MATCH =
  "Nothing in our inventory matches that. Many county and regional parks have no amenities listed yet, so a miss is often missing data, not a missing park."

export type ProposedTrip = {
  name: string
  notes: string | null
  status: "planned"
  park_ids: number[]
}

export type ChatTurn = {
  id: string
  role: "user" | "assistant"
  content: string
  parks?: Park[]
  proposed_trip?: ProposedTrip | null
  error?: boolean
  pending?: boolean
}

export type AiChatRequestMessage = {
  role: "user" | "assistant"
  content: string
}

export type AiChatResponse = {
  message: string
  parks: Park[]
  proposed_trip?: ProposedTrip
}

export type ChatStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">

export function turnsToMessages(turns: ChatTurn[]): AiChatRequestMessage[] {
  return turns
    .filter((turn) => !turn.pending && !turn.error && turn.content.trim().length > 0)
    .map((turn) => ({ role: turn.role, content: turn.content }))
}

export function loadTurns(storage: ChatStorage | null): ChatTurn[] {
  if (!storage) return []
  try {
    const raw = storage.getItem(AI_CHAT_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as { turns?: ChatTurn[] }
    if (!Array.isArray(parsed.turns)) return []
    return parsed.turns.filter(
      (turn) => turn && (turn.role === "user" || turn.role === "assistant") && typeof turn.content === "string",
    )
  } catch {
    return []
  }
}

export function persistTurns(turns: ChatTurn[], storage: ChatStorage | null) {
  if (!storage) return
  const persisted = turns.filter((turn) => !turn.pending)
  if (persisted.length === 0) {
    storage.removeItem(AI_CHAT_STORAGE_KEY)
    return
  }
  storage.setItem(AI_CHAT_STORAGE_KEY, JSON.stringify({ turns: persisted }))
}

export function clearTurns(storage: ChatStorage | null) {
  storage?.removeItem(AI_CHAT_STORAGE_KEY)
}

type TripClient = {
  createTrip: (body: {
    name?: string
    notes?: string | null
    status?: "planned"
    public?: boolean
  }) => Promise<{ trip: Trip }>
  addTripPark: (tripId: number, parkId: number) => Promise<{ trip: Trip }>
}

export async function saveProposedTrip(proposal: ProposedTrip, client: TripClient): Promise<Trip> {
  const { trip } = await client.createTrip({
    name: proposal.name,
    notes: proposal.notes,
    status: "planned",
    public: false,
  })
  let latest = trip
  for (const parkId of proposal.park_ids) {
    const added = await client.addTripPark(trip.id, parkId)
    latest = added.trip
  }
  return latest
}

export function memoryStorage(seed = ""): ChatStorage {
  const data = new Map<string, string>()
  if (seed) data.set(AI_CHAT_STORAGE_KEY, seed)
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => {
      data.set(key, value)
    },
    removeItem: (key) => {
      data.delete(key)
    },
  }
}
