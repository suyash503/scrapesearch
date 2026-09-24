import { useSyncExternalStore } from 'react'

// Live boolean for a CSS media query, e.g. useMediaQuery('(min-width: 768px)').
// Re-renders when it flips (window resized, phone rotated).
// useSyncExternalStore is React's built-in way to subscribe to something outside React.
export function useMediaQuery(query) {
  return useSyncExternalStore(
    (onChange) => {
      const mql = window.matchMedia(query)
      mql.addEventListener('change', onChange)
      return () => mql.removeEventListener('change', onChange)
    },
    () => window.matchMedia(query).matches,
  )
}
