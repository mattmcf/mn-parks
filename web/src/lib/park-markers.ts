import { TYPE_COLORS, TYPE_LABELS } from "@/lib/constants"
import type { Park, ParkType } from "@/types"

const ICON_ATTRS =
  'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"'

const TYPE_ICONS: Record<ParkType, string> = {
  national: `<svg ${ICON_ATTRS}><path d="m4 19 5.5-11 3 6 2-4L20 19H4Z"/><path d="M4 19h16"/></svg>`,
  state: `<svg ${ICON_ATTRS}><path d="M12 21v-6"/><path d="m6 13 6-9 6 9"/><path d="m7.5 18 4.5-6 4.5 6H7.5Z"/></svg>`,
  regional: `<svg ${ICON_ATTRS}><circle cx="12" cy="9" r="3.2"/><path d="M12 3.2v1.5M12 13.3v1.5M5.2 9h1.5M17.3 9h1.5"/><path d="M5 19.5c1.2-2.2 3.6-3.4 7-3.4s5.8 1.2 7 3.4"/></svg>`,
  county: `<svg ${ICON_ATTRS}><path d="M12 21s6.5-5.1 6.5-10.2a6.5 6.5 0 1 0-13 0C5.5 15.9 12 21 12 21Z"/><circle cx="12" cy="10.8" r="1.8" fill="currentColor" stroke="none"/></svg>`,
}

export function createParkMarkerElement(park: Park, onSelect: (park: Park) => void) {
  const button = document.createElement("button")
  button.type = "button"
  button.className = "park-marker"
  button.dataset.parkId = String(park.id)
  button.dataset.parkType = park.park_type
  button.title = `${park.name} · ${TYPE_LABELS[park.park_type]}`
  button.setAttribute("aria-label", `${park.name}, ${TYPE_LABELS[park.park_type]} park`)
  button.setAttribute("aria-pressed", "false")
  button.innerHTML = `<span class="park-marker__dot" style="background:${TYPE_COLORS[park.park_type]}">${TYPE_ICONS[park.park_type]}</span>`

  const stop = (event: Event) => event.stopPropagation()
  button.addEventListener("pointerdown", stop)
  button.addEventListener("pointerup", stop)
  button.addEventListener("click", (event) => {
    event.preventDefault()
    event.stopPropagation()
    onSelect(park)
  })
  return button
}

export function setParkMarkerSelected(element: HTMLElement, selected: boolean) {
  element.classList.toggle("is-selected", selected)
  element.setAttribute("aria-pressed", selected ? "true" : "false")
  element.style.zIndex = selected ? "4" : ""
}
