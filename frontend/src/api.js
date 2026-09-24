// Thin wrappers around the Django API. Every call takes an AbortSignal so a newer request
// can cancel an older one that's still in flight (see the effects in App.jsx / SearchBox.jsx).

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

// DRF validation errors look like {"min_price": ["..."]} or {"non_field_errors": ["..."]}.
function firstError(data) {
  const first = Object.values(data ?? {})[0]
  return Array.isArray(first) ? first[0] : null
}

async function getJSON(path, params = {}, signal) {
  // Drop empty params so the URL stays clean: {q: "", page: 2} -> "?page=2"
  const query = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== '' && v !== null && v !== undefined),
  ).toString()
  const res = await fetch(`/api/${path}${query ? `?${query}` : ''}`, { signal })
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    throw new ApiError(data?.detail || firstError(data) || `Request failed (HTTP ${res.status})`, res.status)
  }
  return data
}

export const searchBooks = (params, signal) => getJSON('search', params, signal)
export const suggestTitles = (q, signal) => getJSON('suggest', { q }, signal)
export const getBook = (id, signal) => getJSON(`books/${id}`, {}, signal)
