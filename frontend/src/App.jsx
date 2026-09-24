import { useEffect, useState } from 'react'
import { searchBooks } from './api'
import BookDialog from './components/BookDialog'
import Facets from './components/Facets'
import Pagination from './components/Pagination'
import ResultList from './components/ResultList'
import SearchBox from './components/SearchBox'
import { useMediaQuery } from './hooks/useMediaQuery'

const EMPTY_FILTERS = { q: '', category: '', min_price: '', max_price: '', min_rating: '', page: 1 }
const MAX_PAGE = 50 // the API refuses deeper pages (see backend/search/queries.py)

// The filters live in the URL (?q=harry&category=Fantasy&page=2), so refresh, back and shared links work.
function filtersFromUrl() {
  const params = new URLSearchParams(window.location.search)
  const filters = { ...EMPTY_FILTERS }
  for (const key of Object.keys(EMPTY_FILTERS)) if (params.has(key)) filters[key] = params.get(key)
  filters.page = Math.max(1, Number(filters.page) || 1)
  return filters
}

function toQueryString(filters) {
  return new URLSearchParams(
    Object.entries(filters).filter(([key, v]) => v !== '' && !(key === 'page' && v === 1)),
  ).toString()
}

export default function App() {
  const [filters, setFilters] = useState(filtersFromUrl)
  // The last finished request: which filters it was for, and what came back.
  const [response, setResponse] = useState({ query: null, data: null, error: '' })
  const [openBookId, setOpenBookId] = useState(null)
  const isDesktop = useMediaQuery('(min-width: 768px)')

  const query = toQueryString(filters)
  // Derived, not stored: we're loading whenever the last response was for different filters.
  const loading = response.query !== query
  const { data, error } = response

  // Changing any filter goes back to page 1. Changing only the page keeps the filters.
  const updateFilters = (changes) => setFilters((f) => ({ ...f, page: 1, ...changes }))

  useEffect(() => {
    window.history.replaceState(null, '', query ? `?${query}` : window.location.pathname)
    const controller = new AbortController()
    searchBooks(Object.fromEntries(new URLSearchParams(query)), controller.signal)
      .then((result) => setResponse({ query, data: result, error: '' }))
      .catch((err) => {
        // Keep the previous results on screen and show the error above them.
        if (err.name !== 'AbortError') setResponse((r) => ({ ...r, query, error: err.message }))
      })
    // Clicking filters quickly fires several searches. Aborting the previous one means a slow,
    // stale response can never overwrite the results of the latest click.
    return () => controller.abort()
  }, [query])

  const hasFilters = filters.q || filters.category || filters.min_price || filters.max_price || filters.min_rating
  const totalPages = data ? Math.min(Math.ceil(data.total / data.page_size), MAX_PAGE) : 0

  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="/" onClick={(e) => { e.preventDefault(); setFilters(EMPTY_FILTERS) }}>
          <img src="/favicon.svg" alt="" width="28" height="28" />
          ScrapeSearch
        </a>
        <SearchBox value={filters.q} onSearch={(q) => updateFilters({ q })} />
      </header>

      <div className="layout">
        <aside className="sidebar" aria-label="Filters">
          {/* Phones: a collapsible "Filters" panel, closed by default, the user toggles it freely.
              Desktop: forced open, and CSS hides the toggle. */}
          <details open={isDesktop || undefined}>
            <summary>Filters</summary>
            {data && <Facets facets={data.facets} filters={filters} onChange={updateFilters} />}
          </details>
        </aside>

        <main className="main" aria-busy={loading}>
          <div className="results-head">
            <p role="status">
              {data && !error && (
                <>
                  <strong>{data.total.toLocaleString()}</strong> {data.total === 1 ? 'book' : 'books'}
                  {filters.q && <> for “{filters.q}”</>}
                  <span className="muted"> · {data.took_ms} ms in Elasticsearch</span>
                </>
              )}
            </p>
            {hasFilters && (
              <button type="button" className="link" onClick={() => setFilters(EMPTY_FILTERS)}>
                Clear all
              </button>
            )}
          </div>

          {error && <div className="notice error">{error}</div>}

          {data && !error && data.total === 0 && (
            <div className="notice">
              No books match. Try fewer words, check the spelling, or clear some filters.
            </div>
          )}

          {data && !error && (
            <div className={loading ? 'fading' : undefined}>
              <ResultList results={data.results} onOpen={setOpenBookId} />
              <Pagination
                page={filters.page}
                totalPages={totalPages}
                onPage={(page) => {
                  setFilters((f) => ({ ...f, page }))
                  window.scrollTo({ top: 0, behavior: 'smooth' })
                }}
              />
            </div>
          )}

          {!data && !error && <div className="notice muted">Loading…</div>}
        </main>
      </div>

      {openBookId != null && (
        <BookDialog key={openBookId} bookId={openBookId} onClose={() => setOpenBookId(null)} />
      )}
    </div>
  )
}
