import assert from "node:assert/strict"
import test from "node:test"
import {
  boundsAroundPin,
  lngLatOfPark,
  pinIsInViewfinder,
} from "./park-camera.ts"

test("lngLatOfPark is MapLibre order [longitude, latitude]", () => {
  const pair = lngLatOfPark({ longitude: -92.775729, latitude: 45.218471 })
  assert.deepEqual(pair, [-92.775729, 45.218471])
  assert.ok(Math.abs(pair[0]) > 80, "first number must be longitude (west of MN)")
  assert.ok(pair[1] > 40 && pair[1] < 50, "second number must be latitude")
})

test("lngLatOfPark rejects non-finite coords instead of flying to [0,0]", () => {
  assert.throws(() => lngLatOfPark({ longitude: Number.NaN, latitude: 45 }))
  assert.throws(() => lngLatOfPark({ longitude: -93, latitude: Number.POSITIVE_INFINITY }))
})

test("boundsAroundPin stays [sw, ne] in lng/lat — not swapped lat/lng", () => {
  const [sw, ne] = boundsAroundPin(-95.009081, 45.311289, 0.04)
  assert.ok(Math.abs(sw[0] - (-95.049081)) < 1e-9)
  assert.ok(Math.abs(sw[1] - 45.271289) < 1e-9)
  assert.ok(Math.abs(ne[0] - (-94.969081)) < 1e-9)
  assert.ok(Math.abs(ne[1] - 45.351289) < 1e-9)
  assert.ok(sw[0] < ne[0], "west < east")
  assert.ok(sw[1] < ne[1], "south < north")
  assert.ok(Math.abs(sw[0]) > 80, "bounds are longitude-first")
})

test("pinIsInViewfinder is false when the marker is outside the canvas", () => {
  const size = { width: 800, height: 600 }
  assert.equal(pinIsInViewfinder({ x: 400, y: 300 }, size), true)
  assert.equal(pinIsInViewfinder({ x: -20, y: 300 }, size), false)
  assert.equal(pinIsInViewfinder({ x: 400, y: 900 }, size), false)
  assert.equal(pinIsInViewfinder({ x: 4, y: 4 }, size, 8), false)
})
