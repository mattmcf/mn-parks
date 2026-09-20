export function haversineMiles(
  a: { latitude: number; longitude: number },
  b: { latitude: number; longitude: number },
) {
  const r = 3958.8
  const p1 = (a.latitude * Math.PI) / 180
  const p2 = (b.latitude * Math.PI) / 180
  const dp = p2 - p1
  const dl = ((b.longitude - a.longitude) * Math.PI) / 180
  const h =
    Math.sin(dp / 2) ** 2 +
    Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2
  return 2 * r * Math.asin(Math.min(1, Math.sqrt(h)))
}

export function formatMiles(miles: number) {
  if (miles < 10) return `${miles.toFixed(1)} mi`
  return `${Math.round(miles)} mi`
}
