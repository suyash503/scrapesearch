export const formatPrice = (value) => `£${Number(value).toFixed(2)}`

export function stockLabel(count) {
  if (!count) return 'Out of stock'
  return count <= 3 ? `Only ${count} left` : `${count} in stock`
}
