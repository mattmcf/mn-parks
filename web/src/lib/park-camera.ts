/** Shared camera target for Random, search, list, and map-marker selection. */

export type ParkCameraTarget = {
  id: number
  longitude: number
  latitude: number
}

/** MapLibre / GeoJSON order: longitude, latitude. Never [lat, lng]. */
export function lngLatOfPark(park: { longitude: number; latitude: number }): [number, number] {
  const lng = Number(park.longitude)
  const lat = Number(park.latitude)
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
    throw new Error("Park is missing a usable longitude/latitude")
  }
  return [lng, lat]
}

/** Small box around the pin so fitBounds keeps the marker on-screen with padding. */
export function boundsAroundPin(
  lng: number,
  lat: number,
  halfDegrees = 0.035,
): [[number, number], [number, number]] {
  return [
    [lng - halfDegrees, lat - halfDegrees],
    [lng + halfDegrees, lat + halfDegrees],
  ]
}

export function pinIsInViewfinder(
  point: { x: number; y: number },
  size: { width: number; height: number },
  pad = 8,
): boolean {
  return point.x >= pad && point.y >= pad && point.x <= size.width - pad && point.y <= size.height - pad
}

export const PARK_FRAME_PADDING = { top: 48, right: 56, bottom: 72, left: 24 } as const
export const PARK_FRAME_MAX_ZOOM = 12
