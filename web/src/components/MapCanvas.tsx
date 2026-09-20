import { useEffect, useRef } from "react"
import * as maplibregl from "maplibre-gl"
import type { GeoJSONSource, MapLayerMouseEvent, Map as MapLibreMap } from "maplibre-gl"
import { MN_BOUNDS, TYPE_COLORS } from "@/lib/constants"
import type { Origin, Park } from "@/types"

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
  const pinRef = useRef<maplibregl.Marker | null>(null)
  const onSelectRef = useRef(onSelect)
  const onMoveRef = useRef(onMove)
  const onDropPinRef = useRef(onDropPin)
  parksRef.current = parks
  onSelectRef.current = onSelect
  onMoveRef.current = onMove
  onDropPinRef.current = onDropPin

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: "https://tiles.openfreemap.org/styles/liberty",
      center: [-94.3, 46.1],
      zoom: 6,
      maxBounds: [
        [-99.2, 41.8],
        [-87.2, 50.6],
      ],
      attributionControl: { compact: true },
    })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right")
    mapRef.current = map

    const emitViewport = () => {
      const bounds = map.getBounds()
      const ids = parksRef.current
        .filter((park) => bounds.contains([park.longitude, park.latitude]))
        .map((park) => park.id)
      onMoveRef.current(ids)
    }

    map.on("load", () => {
      map.fitBounds(MN_BOUNDS, { padding: 48, duration: 0 })
      map.addSource("parks", { type: "geojson", data: toGeoJSON(parksRef.current) })
      map.addLayer({
        id: "parks-circles",
        type: "circle",
        source: "parks",
        paint: {
          "circle-radius": 6.5,
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
          "circle-stroke-width": 1.4,
          "circle-stroke-color": "#fff",
          "circle-opacity": 0.95,
        },
      })
      map.addLayer({
        id: "parks-selected",
        type: "circle",
        source: "parks",
        filter: ["==", ["get", "id"], -1],
        paint: {
          "circle-radius": 11,
          "circle-color": "transparent",
          "circle-stroke-width": 3,
          "circle-stroke-color": "#111",
        },
      })
      emitViewport()
    })

    map.on("click", "parks-circles", (event: MapLayerMouseEvent) => {
      const feature = event.features?.[0]
      const id = Number(feature?.properties?.id)
      const park = parksRef.current.find((item) => item.id === id)
      if (park) onSelectRef.current(park)
    })

    map.on("mouseenter", "parks-circles", () => {
      map.getCanvas().style.cursor = "pointer"
    })
    map.on("mouseleave", "parks-circles", () => {
      map.getCanvas().style.cursor = ""
    })
    map.on("moveend", emitViewport)

    map.on("click", (event: MapLayerMouseEvent) => {
      if (containerRef.current?.dataset.placing === "true") {
        onDropPinRef.current(event.lngLat.lng, event.lngLat.lat)
      }
    })

    return () => {
      pinRef.current?.remove()
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
    const marker = new maplibregl.Marker({ color: "#be123c", draggable: true })
      .setLngLat([origin.longitude, origin.latitude])
      .setPopup(new maplibregl.Popup({ offset: 18 }).setText("Distance is measured from here"))
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

  return <div ref={containerRef} className="h-full w-full" />
}
