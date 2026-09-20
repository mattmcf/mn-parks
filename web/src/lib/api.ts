import type { ParksPayload, SessionPayload, Park } from "@/types"

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }
  const res = await fetch(path, {
    credentials: "include",
    ...init,
    headers,
  })
  const text = await res.text()
  const data = text ? JSON.parse(text) : {}
  if (!res.ok) {
    throw new Error(data.error || `Request failed (${res.status})`)
  }
  return data as T
}

export const api = {
  session: () => request<SessionPayload>("/api/me"),
  login: (email: string, password: string) =>
    request<SessionPayload>("/api/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  signup: (email: string, password: string) =>
    request<SessionPayload>("/api/signup", {
      method: "POST",
      body: JSON.stringify({ email, password, password_confirmation: password }),
    }),
  logout: () => request<SessionPayload>("/api/logout", { method: "DELETE" }),
  parks: () => request<ParksPayload>("/api/parks"),
  randomPark: () => request<{ park: Park }>("/api/parks/random"),
  setUserState: (parkId: number, body: { favorited?: boolean; visited?: boolean }) =>
    request<{ park: Park }>(`/api/parks/${parkId}/user_state`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
}
