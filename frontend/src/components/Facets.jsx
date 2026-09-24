import { useState } from 'react'
import { formatPrice } from '../format'
import Stars from './Stars'

// Sidebar filters built from the search response's aggregations.
export default function Facets({ facets, filters, onChange }) {
  // The API returns a count per exact rating (1..5). "4★ & up" needs the sum of 4 and 5.
  const ratingAtLeast = (r) => facets.ratings.filter((b) => b.value >= r).reduce((sum, b) => sum + b.count, 0)
  const selectedRating = Number(filters.min_rating) || null

  return (
    <div className="facets">
      <section>
        <div className="facet-head">
          <h2>Category</h2>
          {filters.category && (
            <button type="button" className="link" onClick={() => onChange({ category: '' })}>
              Clear
            </button>
          )}
        </div>
        <ul className="facet-list">
          {facets.categories.map((c) => (
            <li key={c.value}>
              <button
                type="button"
                className="facet-option"
                aria-pressed={filters.category === c.value}
                onClick={() => onChange({ category: filters.category === c.value ? '' : c.value })}
              >
                <span>{c.value}</span>
                <span className="count">{c.count}</span>
              </button>
            </li>
          ))}
          {facets.categories.length === 0 && <li className="muted">No categories</li>}
        </ul>
      </section>

      <section>
        <div className="facet-head">
          <h2>Rating</h2>
          {selectedRating && (
            <button type="button" className="link" onClick={() => onChange({ min_rating: '' })}>
              Clear
            </button>
          )}
        </div>
        <ul className="facet-list">
          {[5, 4, 3, 2, 1].map((r) => (
            <li key={r}>
              <button
                type="button"
                className="facet-option"
                aria-pressed={selectedRating === r}
                onClick={() => onChange({ min_rating: selectedRating === r ? '' : String(r) })}
              >
                <span>
                  <Stars rating={r} />
                  {r < 5 && ' & up'}
                </span>
                <span className="count">{ratingAtLeast(r)}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <PriceFilter
        min={filters.min_price}
        max={filters.max_price}
        range={facets.price}
        onApply={(min_price, max_price) => onChange({ min_price, max_price })}
      />
    </div>
  )
}

function PriceFilter({ min, max, range, onApply }) {
  // Local draft values: the search only runs when you press Apply (or Enter), not on every keystroke.
  const [draftMin, setDraftMin] = useState(min)
  const [draftMax, setDraftMax] = useState(max)
  // Reset the drafts when the applied values change from outside (Clear, Clear all).
  const [applied, setApplied] = useState({ min, max })
  if (applied.min !== min || applied.max !== max) {
    setApplied({ min, max })
    setDraftMin(min)
    setDraftMax(max)
  }

  const invalid = draftMin !== '' && draftMax !== '' && Number(draftMin) > Number(draftMax)
  const active = min !== '' || max !== ''

  return (
    <section>
      <div className="facet-head">
        <h2>Price</h2>
        {active && (
          <button type="button" className="link" onClick={() => onApply('', '')}>
            Clear
          </button>
        )}
      </div>
      <form
        className="price-filter"
        onSubmit={(e) => {
          e.preventDefault()
          if (!invalid) onApply(draftMin, draftMax)
        }}
      >
        <label>
          <span className="sr-only">Minimum price</span>
          <input
            type="number" min="0" step="0.01" inputMode="decimal"
            placeholder={range.min != null ? formatPrice(range.min) : 'Min'}
            value={draftMin}
            onChange={(e) => setDraftMin(e.target.value)}
          />
        </label>
        <span aria-hidden="true">–</span>
        <label>
          <span className="sr-only">Maximum price</span>
          <input
            type="number" min="0" step="0.01" inputMode="decimal"
            placeholder={range.max != null ? formatPrice(range.max) : 'Max'}
            value={draftMax}
            onChange={(e) => setDraftMax(e.target.value)}
          />
        </label>
        <button type="submit" disabled={invalid}>Apply</button>
      </form>
      {invalid && <p className="field-error">Min must be less than max.</p>}
    </section>
  )
}
