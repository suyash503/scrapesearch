import { useEffect, useRef, useState } from 'react'
import { getBook } from '../api'
import { formatPrice, stockLabel } from '../format'
import Stars from './Stars'

// Book details, loaded from /api/books/<id> (MySQL, the source of truth).
// Uses the native <dialog>: it traps focus, closes on Esc and restores focus for free.
// The parent renders it with key={bookId}, so opening another book mounts a fresh dialog with fresh state.
export default function BookDialog({ bookId, onClose }) {
  const dialogRef = useRef(null)
  const [book, setBook] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    dialogRef.current.showModal()
    const controller = new AbortController()
    getBook(bookId, controller.signal)
      .then(setBook)
      .catch((err) => err.name !== 'AbortError' && setError(err.message))
    return () => controller.abort()
  }, [bookId])

  // Close button + backdrop: close and tell the parent right away. Esc is handled natively by <dialog>
  // and reaches the parent through the `close` event (onClose below). Calling onClose twice is harmless.
  function close() {
    dialogRef.current?.close()
    onClose()
  }

  return (
    <dialog
      ref={dialogRef}
      className="book-dialog"
      onClose={onClose}
      // A click on the backdrop lands on the <dialog> element itself.
      onClick={(e) => e.target === dialogRef.current && close()}
    >
      <button type="button" className="close" aria-label="Close" onClick={close}>
        ×
      </button>
      {error && <p className="field-error">{error}</p>}
      {!book && !error && <p className="muted">Loading…</p>}
      {book && (
        <div className="book-detail">
          <img src={book.image_url} alt={`Cover of ${book.title}`} width="160" />
          <div>
            <h2>{book.title}</h2>
            <p className="meta">
              <span className="chip">{book.category}</span>
              <Stars rating={book.rating} />
            </p>
            <p className="detail-price">
              {formatPrice(book.price)}{' '}
              <span className={book.availability ? 'stock' : 'stock out'}>{stockLabel(book.availability)}</span>
            </p>
            <p className="description">{book.description || 'No description available.'}</p>
            <a href={book.url} target="_blank" rel="noreferrer">View on books.toscrape.com ↗</a>
          </div>
        </div>
      )}
    </dialog>
  )
}
