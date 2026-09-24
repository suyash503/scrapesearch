import { useEffect, useState } from 'react'
import { suggestTitles } from '../api'
import { useDebounce } from '../hooks/useDebounce'

// Search input with debounced autocomplete. Keyboard: ↑/↓ to move, Enter to pick, Esc to close.
export default function SearchBox({ value, onSearch }) {
  const [text, setText] = useState(value)
  const [suggestions, setSuggestions] = useState([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1) // index of the keyboard-highlighted suggestion
  const prefix = useDebounce(text, 200).trim()

  // Keep the input in sync when the query changes from outside (e.g. "Clear all").
  // Adjusting state during render (not in an effect) avoids an extra render with the stale text.
  const [prevValue, setPrevValue] = useState(value)
  if (value !== prevValue) {
    setPrevValue(value)
    setText(value)
  }

  useEffect(() => {
    if (prefix.length < 2) return // 1 letter matches half the catalogue, not useful
    const controller = new AbortController()
    suggestTitles(prefix, controller.signal)
      .then((data) => {
        setSuggestions(data.suggestions)
        setActive(-1)
      })
      .catch(() => {}) // aborted or failed: autocomplete is optional, just show nothing
    // If the user keeps typing, the next effect run aborts this request, so a slow response
    // for "har" can never overwrite the suggestions for "harry".
    return () => controller.abort()
  }, [prefix])

  // Below 2 characters we don't fetch, so hide whatever the last fetch returned.
  const visible = prefix.length >= 2 ? suggestions : []
  const showList = open && visible.length > 0

  function submit(query) {
    setOpen(false)
    onSearch(query.trim())
  }

  function pick(suggestion) {
    setText(suggestion.title)
    submit(suggestion.title)
  }

  function onKeyDown(e) {
    if (!showList) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActive((i) => (i + 1) % visible.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActive((i) => (i <= 0 ? visible.length : i) - 1)
    } else if (e.key === 'Escape') {
      setOpen(false)
    } else if (e.key === 'Enter' && active >= 0) {
      e.preventDefault()
      pick(visible[active])
    }
  }

  return (
    <form
      className="searchbox"
      role="search"
      onSubmit={(e) => {
        e.preventDefault()
        submit(text)
      }}
    >
      <input
        type="search"
        value={text}
        placeholder="Search 1,000 books: try “harry poter” or “mystery”"
        aria-label="Search books"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={showList}
        aria-controls="suggestions"
        aria-activedescendant={showList && active >= 0 ? `suggestion-${visible[active].id}` : undefined}
        autoComplete="off"
        onChange={(e) => {
          setText(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
      />
      <button type="submit">Search</button>

      {showList && (
        <ul id="suggestions" className="suggestions" role="listbox">
          {visible.map((s, i) => (
            <li
              key={s.id}
              id={`suggestion-${s.id}`}
              role="option"
              aria-selected={i === active}
              // mousedown + preventDefault: fires before the input's blur, which would close the list first
              onMouseDown={(e) => {
                e.preventDefault()
                pick(s)
              }}
              onMouseEnter={() => setActive(i)}
            >
              {s.title}
            </li>
          ))}
        </ul>
      )}
    </form>
  )
}
