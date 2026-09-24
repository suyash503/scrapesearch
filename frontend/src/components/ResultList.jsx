import { formatPrice, stockLabel } from '../format'
import Stars from './Stars'

export default function ResultList({ results, onOpen }) {
  return (
    <ol className="results">
      {results.map((book) => (
        <li key={book.id}>
          <ResultCard book={book} onOpen={onOpen} />
        </li>
      ))}
    </ol>
  )
}

function ResultCard({ book, onOpen }) {
  const { highlight } = book
  return (
    <article className="card">
      {/* Images are hotlinked from books.toscrape.com. lazy = only fetched when scrolled into view. */}
      <img src={book.image_url} alt="" loading="lazy" width="72" height="104" />
      <div className="card-body">
        <h3>
          <button type="button" className="title-link" onClick={() => onOpen(book.id)}>
            {/* Highlights contain <mark> tags. Safe to render as HTML because the API asks ES to
                HTML-escape the original text (highlight "encoder": "html"). Never do this with raw data. */}
            {highlight.title ? <span dangerouslySetInnerHTML={{ __html: highlight.title }} /> : book.title}
          </button>
        </h3>
        <p className="meta">
          <span className="chip">{book.category}</span>
          <Stars rating={book.rating} />
          <span className={book.availability ? 'stock' : 'stock out'}>{stockLabel(book.availability)}</span>
        </p>
        {highlight.description && (
          <p className="snippet" dangerouslySetInnerHTML={{ __html: `…${highlight.description}…` }} />
        )}
      </div>
      <p className="price">{formatPrice(book.price)}</p>
    </article>
  )
}
