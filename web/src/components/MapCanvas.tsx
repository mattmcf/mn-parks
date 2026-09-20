import { useEffect, useRef } from "react"
import {
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  Popup,
  type GeoJSONSource,
  type StyleSpecification,
} from "maplibre-gl"
import { MN_BOUNDS, TYPE_COLORS } from "@/lib/constants"
import type { Origin, Park } from "@/types"

const OSM_RASTER_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
}

type Props = {
  parks: Park[]
  selectedId: number | null
  origin: Origin | null
  placingPin: boolean
  onSelect: (park: Park) => void
  onMove: (ids: number[]) => void
  onDropPin: (lng: number, lat: number) => void
  flyTo: { id: number; longitude: number; latitude: number } | null
}

function toGeoJSON(parks: Park[]) {
  return {
    type: "FeatureCollection" as const,
    features: parks.map((park) => ({
      type: "Feature" as const,
      id: park.id,
      properties: { id: park.id, name: park.name, park_type: park.park_type },
      geometry: { type: "Point" as const, coordinates: [park.longitude, park.latitude] },
    })),
  }
}

function addParkLayers(map: MapLibreMap, parks: Park[]) {
  if (map.getSource("parks")) return
  map.addSource("parks", { type: "geojson", data: toGeoJSON(parks) })
  map.addLayer({
    id: "parks-halo",
    type: "circle",
    source: "parks",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 16, 6, 18, 9, 20, 12, 22],
      "circle-color": "#1c1915",
      "circle-opacity": 0.22,
    },
  })
  map.addLayer({
    id: "parks-circles",
    type: "circle",
    source: "parks",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 13, 6, 15, 9, 16, 12, 18],
      "circle-color": [
        "match",
        ["get", "park_type"],
        "national",
        TYPE_COLORS.national,
        "state",
        TYPE_COLORS.state,
        "regional",
        TYPE_COLORS.regional,
        "county",
        TYPE_COLORS.county,
        "#444",
      ],
      "circle-stroke-width": 2.5,
      "circle-stroke-color": "#fff",
      "circle-opacity": 1,
    },
  })
  map.addLayer({
    id: "parks-selected",
    type: "circle",
    source: "parks",
    filter: ["==", ["get", "id"], -1],
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 19, 6, 21, 9, 23, 12, 24],
      "circle-color": "transparent",
      "circle-stroke-width": 3,
      "circle-stroke-color": "#111",
    },
  })
}

const PARK_LAYERS = ["parks-circles", "parks-halo", "parks-selected"]

function parkAtPoint(map: MapLibreMap, point: { x: number; y: number }) {
  const pad = 22
  const hits = map.queryRenderedFeatures(
    [
      [point.x - pad, point.y - pad],
      [point.x + pad, point.y + pad],
    ],
    { layers: PARK_LAYERS.filter((id) => map.getLayer(id)) },
  )
  const id = Number(hits[0]?.properties?.id)
  return Number.isFinite(id) ? id : null
}

export function MapCanvas({
  parks,
  selectedId,
  origin,
  placingPin,
  onSelect,
  onMove,
  onDropPin,
  flyTo,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const parksRef = useRef(parks)
  const pinRef = useRef<Marker | null>(null)
  const onSelectRef = useRef(onSelect)
  const onMoveRef = useRef(onMove)
  const onDropPinRef = useRef(onDropPin)
  parksRef.current = parks
  onSelectRef.current = onSelect
  onMoveRef.current = onMove
  onDropPinRef.current = onDropPin

  useEffect(() => {
    const node = containerRef.current
    if (!node) return

    const map = new MapLibreMap({
      container: node,
      style: OSM_RASTER_STYLE,
      center: [-94.3, 46.1],
      zoom: 6,
      clickTolerance: 16,
      maxBounds: [
        [-99.2, 41.8],
        [-87.2, 50.6],
      ],
      attributionControl: { compact: true },
      canvasContextAttributes: {
        antialias: false,
        preserveDrawingBuffer: true,
        failIfMajorPerformanceCaveat: false,
        powerPreference: "default",
      },
    })
    map.addControl(new NavigationControl({ showCompass: false }), "bottom-right")
    mapRef.current = map

    const emitViewport = () => {
      const bounds = map.getBounds()
      const ids = parksRef.current
        .filter((park) => bounds.contains([park.longitude, park.latitude]))
        .map((park) => park.id)
      onMoveRef.current(ids)
    }

    const onReady = () => {
      map.resize()
      map.fitBounds(MN_BOUNDS, { padding: 48, duration: 0 })
      addParkLayers(map, parksRef.current)
      emitViewport()
    }

    const selectFromPoint = (point: { x: number; y: number }, lngLat?: { lng: number; lat: number }) => {
      if (containerRef.current?.dataset.placing === "true") {
        if (lngLat) onDropPinRef.current(lngLat.lng, lngLat.lat)
        return
      }
      const id = parkAtPoint(map, point)
      const park = parksRef.current.find((item) => item.id === id)
      if (park) onSelectRef.current(park)
    }

    map.on("load", onReady)
    map.on("moveend", emitViewport)
    map.on("mousemove", (event) => {
      if (containerRef.current?.dataset.placing === "true") return
      map.getCanvas().style.cursor = parkAtPoint(map, event.point) ? "pointer" : ""
    })

    let pointerDown: { x: number; y: number } | null = null
    const canvas = map.getCanvas()
    const onPointerDown = (event: PointerEvent) => {
      pointerDown = { x: event.clientX, y: event.clientY }
    }
    const onPointerUp = (event: PointerEvent) => {
      if (!pointerDown) return
      const moved = Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y)
      pointerDown = null
      if (moved > 14) return
      const rect = canvas.getBoundingClientRect()
      const point = { x: event.clientX - rect.left, y: event.clientY - rect.top }
      const lngLat = map.unproject([point.x, point.y])
      selectFromPoint(point, lngLat)
    }
    canvas.addEventListener("pointerdown", onPointerDown)
    canvas.addEventListener("pointerup", onPointerUp)

    const observer = new ResizeObserver(() => map.resize())
    observer.observe(node)
    const later = window.setTimeout(() => map.resize(), 200)

    return () => {
      window.clearTimeout(later)
      observer.disconnect()
      canvas.removeEventListener("pointerdown", onPointerDown)
      canvas.removeEventListener("pointerup", onPointerUp)
      pinRef.current?.remove()
      pinRef.current = null
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map?.getSource("parks")) return
    ;(map.getSource("parks") as GeoJSONSource).setData(toGeoJSON(parks))
    const bounds = map.getBounds()
    onMoveRef.current(
      parks.filter((park) => bounds.contains([park.longitude, park.latitude])).map((park) => park.id),
    )
  }, [parks])

  useEffect(() => {
    const map = mapRef.current
    if (!map?.getLayer("parks-selected")) return
    map.setFilter("parks-selected", ["==", ["get", "id"], selectedId ?? -1])
  }, [selectedId])

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.dataset.placing = placingPin ? "true" : "false"
      containerRef.current.style.cursor = placingPin ? "crosshair" : ""
    }
  }, [placingPin])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    pinRef.current?.remove()
    pinRef.current = null
    if (!origin || origin.kind !== "pin") return
    const marker = new Marker({ color: "#be123c", draggable: true })
      .setLngLat([origin.longitude, origin.latitude])
      .setPopup(new Popup({ offset: 18 }).setText("Distance is measured from here"))
      .addTo(map)
    marker.on("dragend", () => {
      const lngLat = marker.getLngLat()
      onDropPinRef.current(lngLat.lng, lngLat.lat)
    })
    pinRef.current = marker
  }, [origin])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !flyTo) return
    map.flyTo({ center: [flyTo.longitude, flyTo.latitude], zoom: 11, essential: true })
  }, [flyTo])

  return (
    <div
      ref={containerRef}
      className="map-canvas absolute inset-0 h-full w-full min-h-[240px]"
    />
  )
}
