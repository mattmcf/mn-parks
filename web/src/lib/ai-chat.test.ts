import assert from "node:assert/strict"
import test from "node:test"
import {
  AI_CHAT_STORAGE_KEY,
  clearTurns,
  loadTurns,
  memoryStorage,
  persistTurns,
  saveProposedTrip,
  turnsToMessages,
  type ChatTurn,
  type ProposedTrip,
} from "./ai-chat.ts"

const userTurn: ChatTurn = { id: "u1", role: "user", content: "dark sky" }
const assistantTurn: ChatTurn = {
  id: "a1",
  role: "assistant",
  content: "Voyageurs and the Boundary Waters.",
  parks: [],
  proposed_trip: {
    name: "Dark Sky parks",
    notes: "Official DarkSky places only.",
    status: "planned",
    park_ids: [2, 3],
  },
}

test("persists a tab-session thread and drops it on clear", () => {
  const storage = memoryStorage()
  persistTurns([userTurn, assistantTurn], storage)
  const loaded = loadTurns(storage)
  assert.equal(loaded.length, 2)
  assert.equal(loaded[0]?.content, "dark sky")
  assert.equal(loaded[1]?.proposed_trip?.name, "Dark Sky parks")
  assert.ok(storage.getItem(AI_CHAT_STORAGE_KEY))
  clearTurns(storage)
  assert.deepEqual(loadTurns(storage), [])
})

test("does not persist a pending spinner turn", () => {
  const storage = memoryStorage()
  persistTurns(
    [userTurn, { id: "p", role: "assistant", content: "", pending: true }],
    storage,
  )
  const loaded = loadTurns(storage)
  assert.equal(loaded.length, 1)
  assert.equal(loaded[0]?.role, "user")
})

test("turnsToMessages omits pending and error turns so retries send the real thread", () => {
  const messages = turnsToMessages([
    userTurn,
    { id: "e", role: "assistant", content: "Couldn't plan that. Try again.", error: true },
    { id: "p", role: "assistant", content: "", pending: true },
  ])
  assert.deepEqual(messages, [{ role: "user", content: "dark sky" }])
})

test("corrupt sessionStorage is treated as an empty thread", () => {
  const storage = memoryStorage("not-json")
  assert.deepEqual(loadTurns(storage), [])
})

test("saveProposedTrip creates a private planned list then adds each park", async () => {
  const created: unknown[] = []
  const added: unknown[] = []
  const proposal: ProposedTrip = {
    name: "Dark Sky parks",
    notes: "Official inventory only.",
    status: "planned",
    park_ids: [2, 3],
  }
  const trip = await saveProposedTrip(proposal, {
    createTrip: async (body) => {
      created.push(body)
      return {
        trip: {
          id: 41,
          name: body.name ?? "",
          notes: body.notes ?? null,
          status: "planned",
          public: body.public ?? false,
          starts_on: null,
          ends_on: null,
          park_count: 0,
          mine: true,
          updated_at: "2026-10-27T00:00:00Z",
        },
      }
    },
    addTripPark: async (tripId, parkId) => {
      added.push({ tripId, parkId })
      return {
        trip: {
          id: tripId,
          name: "Dark Sky parks",
          notes: "Official inventory only.",
          status: "planned",
          public: false,
          starts_on: null,
          ends_on: null,
          park_count: added.length,
          mine: true,
          updated_at: "2026-10-27T00:00:00Z",
        },
      }
    },
  })
  assert.deepEqual(created, [
    { name: "Dark Sky parks", notes: "Official inventory only.", status: "planned", public: false },
  ])
  assert.deepEqual(added, [
    { tripId: 41, parkId: 2 },
    { tripId: 41, parkId: 3 },
  ])
  assert.equal(trip.id, 41)
  assert.equal(trip.public, false)
})
