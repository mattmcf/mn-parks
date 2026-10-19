import assert from "node:assert/strict"
import test from "node:test"
import { MAX_NAME_MATCHES, rankParkNameMatches, scoreParkName } from "./park-search.ts"

const parks = [
  { id: 1, name: "Itasca State Park" },
  { id: 2, name: "Jay Cooke State Park" },
  { id: 3, name: "Voyageurs National Park" },
  { id: 4, name: "Aitkin County Campground (Ripple Lake)" },
  { id: 5, name: "Gooseberry Falls State Park" },
  { id: 6, name: "Split Rock Lighthouse State Park" },
  { id: 7, name: "Minneopa State Park" },
  { id: 8, name: "William O'Brien State Park" },
  { id: 9, name: "Grand Portage National Monument" },
  { id: 10, name: "Tamarac Wilderness" },
]

test("ignores queries shorter than three characters", () => {
  assert.deepEqual(rankParkNameMatches(parks, "it"), [])
  assert.equal(scoreParkName("Itasca State Park", "it"), null)
})

test("ranks a name prefix first", () => {
  const matches = rankParkNameMatches(parks, "ita")
  assert.equal(matches[0]?.name, "Itasca State Park")
  assert.ok((scoreParkName("Itasca State Park", "ita") ?? 0) > (scoreParkName("Minneopa State Park", "ita") ?? 0))
})

test("matches a later word prefix", () => {
  const matches = rankParkNameMatches(parks, "cook")
  assert.equal(matches[0]?.name, "Jay Cooke State Park")
})

test("matches a substring inside the name", () => {
  const matches = rankParkNameMatches(parks, "ripple")
  assert.equal(matches[0]?.name, "Aitkin County Campground (Ripple Lake)")
})

test("allows a one-character typo against a name word", () => {
  const matches = rankParkNameMatches(parks, "voyageurx")
  assert.equal(matches[0]?.name, "Voyageurs National Park")
})

test("returns at most five results, best scores first", () => {
  const matches = rankParkNameMatches(parks, "state")
  assert.ok(matches.length <= MAX_NAME_MATCHES)
  assert.ok(matches.every((park) => park.name.toLowerCase().includes("state")))
  const scores = matches.map((park) => scoreParkName(park.name, "state") ?? 0)
  const sorted = [...scores].sort((a, b) => b - a)
  assert.deepEqual(scores, sorted)
})

test("returns nothing when no name is close", () => {
  assert.deepEqual(rankParkNameMatches(parks, "xyzzy"), [])
})
