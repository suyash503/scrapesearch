import { useEffect, useState } from 'react'

// Returns `value`, but only after it has stopped changing for `delay` ms.
// Typing "harry" fires one suggest request 200ms after the last key, not one per keystroke.
export function useDebounce(value, delay) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer) // a new keystroke cancels the pending update
  }, [value, delay])
  return debounced
}
