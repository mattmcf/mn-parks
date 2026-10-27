import assert from "node:assert/strict"
import test from "node:test"
import {
  canEditTrip,
  formatIsoDate,
  formatTripDates,
  parseTripPath,
  tripPath,
  TRIP_STATUS_LABELS,
  visibilityLabel,
} from "./trips.ts"

test("parses trip list and show paths, ignoring trailing slashes", () => {
  assert.deepEqual(parseTripPath("/trips"), { kind: "browse" })
  assert.deepEqual(parseTripPath("/trips/"), { kind: "browse" })
  assert.deepEqual(parseTripPath("/trips/42"), { kind: "show", id: 42 })
  assert.deepEqual(parseTripPath("/trips/42/"), { kind: "show", id: 42 })
  assert.deepEqual(parseTripPath("/"), { kind: "none" })
  assert.deepEqual(parseTripPath("/parks"), { kind: "none" })
})

test("formats optional trip dates in UTC so the calendar day does not shift", () => {
  assert.equal(formatIsoDate("2026-07-04"), "Jul 4, 2026")
  assert.equal(
    formatTripDates({ starts_on: "2026-07-04", ends_on: "2026-07-06" }),
    "Jul 4, 2026 – Jul 6, 2026",
  )
  assert.equal(formatTripDates({ starts_on: "2026-07-04", ends_on: null }), "From Jul 4, 2026")
  assert.equal(formatTripDates({ starts_on: null, ends_on: "2026-07-06" }), "Until Jul 6, 2026")
  assert.equal(formatTripDates({ starts_on: null, ends_on: null }), null)
})

test("labels the three trip statuses and public/private visibility", () => {
  assert.equal(TRIP_STATUS_LABELS.planned, "Planned")
  assert.equal(TRIP_STATUS_LABELS.want_to_go, "Want to go")
  assert.equal(TRIP_STATUS_LABELS.gone, "Gone")
  assert.equal(visibilityLabel(true), "Public")
  assert.equal(visibilityLabel(false), "Private")
  assert.equal(canEditTrip({ mine: true }), true)
  assert.equal(canEditTrip({ mine: false }), false)
  assert.equal(tripPath(9), "/trips/9")
})
