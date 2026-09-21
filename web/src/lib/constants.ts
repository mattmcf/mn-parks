export const MN_BOUNDS: [[number, number], [number, number]] = [
  [-97.5, 43.4],
  [-89.34, 49.38],
]

/** Initial camera still fits Minnesota; pan/zoom may travel this far around it. */
export const MAP_MAX_BOUNDS: [[number, number], [number, number]] = [
  [-108, 38],
  [-80, 53],
]

export const MN_CENTER: [number, number] = [-94.3, 46.1]

export const TYPE_LABELS = {
  national: "National",
  state: "State",
  wilderness: "Wilderness",
  regional: "Regional",
  county: "County",
} as const

export const TYPE_COLORS = {
  national: "#9a3412",
  state: "#166534",
  wilderness: "#0f766e",
  regional: "#0369a1",
  county: "#b45309",
} as const

export const AMENITY_LABELS: Record<string, string> = {
  hiking: "Hiking trails",
  camping: "Camping",
  swimming: "Swimming",
  fishing: "Fishing",
  boating: "Boating",
  picnic: "Picnic areas",
  visitor_center: "Visitor center",
  playground: "Playground",
  biking: "Biking",
  wildlife: "Wildlife viewing",
  climbing: "Climbing",
  horseback: "Horseback riding",
  disc_golf: "Disc golf",
  beach: "Beach",
  canoeing: "Canoeing / kayaking",
  cross_country_skiing: "Cross-country skiing",
  snowshoeing: "Snowshoeing",
  winter_sports: "Winter sports",
  waterfall: "Waterfall",
  historic: "Historic site",
}

export const ACTIVITY_LABELS: Record<string, string> = {
  hiking: "Hiking",
  camping: "Camping",
  swimming: "Swimming",
  fishing: "Fishing",
  boating: "Boating",
  biking: "Biking",
  climbing: "Climbing",
  "horseback riding": "Horseback riding",
  "disc golf": "Disc golf",
  paddling: "Paddling",
  "cross-country skiing": "Cross-country skiing",
  snowshoeing: "Snowshoeing",
  "winter sports": "Winter sports",
  "wildlife watching": "Wildlife watching",
}

export function labelFor(kind: "amenity" | "activity", value: string) {
  const table = kind === "amenity" ? AMENITY_LABELS : ACTIVITY_LABELS
  return table[value] ?? value.replaceAll("_", " ")
}
