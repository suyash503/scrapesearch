// Page numbers with a window around the current page: 1 … 4 5 [6] 7 8 … 12
export default function Pagination({ page, totalPages, onPage }) {
  if (totalPages <= 1) return null

  const pages = new Set([1, totalPages])
  for (let p = page - 2; p <= page + 2; p++) if (p > 1 && p < totalPages) pages.add(p)
  const sorted = [...pages].sort((a, b) => a - b)

  return (
    <nav className="pagination" aria-label="Pagination">
      <button type="button" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        ← Prev
      </button>
      {sorted.map((p, i) => (
        <span key={p} className="page-slot">
          {i > 0 && p - sorted[i - 1] > 1 && <span className="gap" aria-hidden="true">…</span>}
          <button type="button" aria-current={p === page ? 'page' : undefined} onClick={() => onPage(p)}>
            {p}
          </button>
        </span>
      ))}
      <button type="button" disabled={page >= totalPages} onClick={() => onPage(page + 1)}>
        Next →
      </button>
    </nav>
  )
}
