// 5 stars, the first `rating` in gold and the rest greyed out. Screen readers get "4 out of 5 stars".
export default function Stars({ rating }) {
  const filled = rating ?? 0
  return (
    <span className="stars" role="img" aria-label={`${filled} out of 5 stars`}>
      {'★'.repeat(filled)}
      <span className="stars-empty">{'★'.repeat(5 - filled)}</span>
    </span>
  )
}
