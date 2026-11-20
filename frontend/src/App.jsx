import { useEffect, useMemo, useState } from 'react'
import './App.css'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')
const PAGE_SIZE = 10

const columns = [
  { key: 'id', label: 'Song ID' },
  { key: 'title', label: 'Title' },
  { key: 'danceability', label: 'Danceability' },
  { key: 'energy', label: 'Energy' },
  { key: 'mood', label: 'Mood' },
  { key: 'acousticness', label: 'Acousticness' },
  { key: 'tempo', label: 'Tempo' },
  { key: 'duration_ms', label: 'Duration (ms)' },
  { key: 'num_sections', label: 'Sections' },
  { key: 'num_segments', label: 'Segments' },
  { key: 'valence', label: 'Valence' },
]

async function requestJson(path, signal) {
  const response = await fetch(`${API_BASE_URL}${path}`, { signal })
  const payload = await response.json().catch(() => null)

  if (!response.ok) {
    const detail = payload?.detail
    throw new Error(typeof detail === 'string' ? detail : `Request failed (${response.status})`)
  }
  return payload
}

async function fetchAllSongs(signal) {
  const firstPage = await requestJson('/songs?page=1&size=100&sort_by=id&order=asc', signal)
  const songs = [...firstPage.items]
  const pageCount = Math.ceil(firstPage.total / firstPage.size)

  for (let page = 2; page <= pageCount; page += 1) {
    const nextPage = await requestJson(
      `/songs?page=${page}&size=100&sort_by=id&order=asc`,
      signal,
    )
    songs.push(...nextPage.items)
  }
  return songs
}

function displayValue(value, column) {
  if (value === null || value === undefined) return '—'
  if (column === 'duration_ms') return `${Number(value).toLocaleString()} ms`
  return String(value)
}

function csvCell(value) {
  const text = value === null || value === undefined ? '' : String(value)
  return `"${text.replaceAll('"', '""')}"`
}

function SongsTable({ songs, sort, onSort, caption }) {
  return (
    <div className="table-scroll">
      <table>
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            {columns.map(({ key, label }) => {
              const active = sort?.key === key
              const ariaSort = active
                ? sort.direction === 'asc'
                  ? 'ascending'
                  : 'descending'
                : 'none'

              return (
                <th key={key} scope="col" aria-sort={ariaSort}>
                  {onSort ? (
                    <button
                      className="sort-button"
                      type="button"
                      onClick={() => onSort(key)}
                      aria-label={`Sort by ${label}${
                        active ? `, currently ${ariaSort}` : ''
                      }`}
                    >
                      {label}
                      <span className="sort-indicator" aria-hidden="true">
                        {active ? (sort.direction === 'asc' ? ' ↑' : ' ↓') : ' ↕'}
                      </span>
                    </button>
                  ) : (
                    label
                  )}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {songs.map((song) => (
            <tr key={song.id}>
              {columns.map(({ key }) => (
                <td key={key} className={key === 'id' ? 'id-cell' : ''}>
                  {displayValue(song[key], key)}
                </td>
              ))}
            </tr>
          ))}
          {songs.length === 0 && (
            <tr>
              <td className="empty-cell" colSpan={columns.length}>
                No songs to display.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

function DanceEnergyChart({ songs }) {
  const width = 680
  const height = 340
  const margin = { top: 20, right: 24, bottom: 52, left: 58 }
  const plotWidth = width - margin.left - margin.right
  const plotHeight = height - margin.top - margin.bottom
  const ticks = [0, 0.25, 0.5, 0.75, 1]
  const points = songs.filter(
    (song) =>
      Number.isFinite(song.danceability) &&
      Number.isFinite(song.energy) &&
      song.danceability >= 0 &&
      song.danceability <= 1 &&
      song.energy >= 0 &&
      song.energy <= 1,
  )

  return (
    <div className="chart-wrap">
      <svg
        className="scatter-chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`Scatter plot of danceability versus energy for ${points.length} songs`}
      >
        <title>Danceability and energy for songs with valid values</title>
        {ticks.map((tick) => {
          const x = margin.left + tick * plotWidth
          const y = margin.top + (1 - tick) * plotHeight
          return (
            <g key={tick}>
              <line
                className="chart-grid"
                x1={margin.left}
                x2={width - margin.right}
                y1={y}
                y2={y}
              />
              <line
                className="chart-grid"
                x1={x}
                x2={x}
                y1={margin.top}
                y2={height - margin.bottom}
              />
              <text className="chart-tick" x={margin.left - 10} y={y + 4} textAnchor="end">
                {tick.toFixed(2).replace(/0+$/, '').replace(/\.$/, '')}
              </text>
              <text
                className="chart-tick"
                x={x}
                y={height - margin.bottom + 22}
                textAnchor="middle"
              >
                {tick.toFixed(2).replace(/0+$/, '').replace(/\.$/, '')}
              </text>
            </g>
          )
        })}
        <line
          className="chart-axis"
          x1={margin.left}
          x2={margin.left}
          y1={margin.top}
          y2={height - margin.bottom}
        />
        <line
          className="chart-axis"
          x1={margin.left}
          x2={width - margin.right}
          y1={height - margin.bottom}
          y2={height - margin.bottom}
        />
        {points.map((song) => {
          const cx = margin.left + song.danceability * plotWidth
          const cy = margin.top + (1 - song.energy) * plotHeight
          return (
            <circle className="chart-point" key={song.id} cx={cx} cy={cy} r="5">
              <title>
                {song.title}: danceability {song.danceability}, energy {song.energy}
              </title>
            </circle>
          )
        })}
        <text
          className="chart-label"
          x={margin.left + plotWidth / 2}
          y={height - 10}
          textAnchor="middle"
        >
          Danceability
        </text>
        <text
          className="chart-label"
          transform={`translate(16 ${margin.top + plotHeight / 2}) rotate(-90)`}
          textAnchor="middle"
        >
          Energy
        </text>
      </svg>
      <p className="chart-note">
        {points.length} of {songs.length} songs shown. Records missing either value are omitted.
      </p>
    </div>
  )
}

function App() {
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState({ key: 'title', direction: 'asc' })
  const [pageState, setPageState] = useState(null)
  const [reloadToken, setReloadToken] = useState(0)
  const [chartState, setChartState] = useState(null)
  const [lookupTitle, setLookupTitle] = useState('')
  const [lookupResult, setLookupResult] = useState(null)
  const [lookupLoading, setLookupLoading] = useState(false)
  const [lookupError, setLookupError] = useState('')
  const pageRequestKey = `${page}:${sort.key}:${sort.direction}:${reloadToken}`
  const chartRequestKey = String(reloadToken)

  useEffect(() => {
    const controller = new AbortController()
    const requestKey = pageRequestKey
    const params = new URLSearchParams({
      page: String(page),
      size: String(PAGE_SIZE),
      sort_by: sort.key,
      order: sort.direction,
    })

    requestJson(`/songs?${params}`, controller.signal)
      .then((result) =>
        setPageState({
          key: requestKey,
          status: 'loaded',
          data: { total: result.total, items: result.items },
        }),
      )
      .catch((requestError) => {
        if (requestError.name !== 'AbortError') {
          setPageState({
            key: requestKey,
            status: 'error',
            error: requestError.message,
          })
        }
      })

    return () => controller.abort()
  }, [page, sort.key, sort.direction, reloadToken, pageRequestKey])

  useEffect(() => {
    const controller = new AbortController()
    const requestKey = chartRequestKey
    fetchAllSongs(controller.signal)
      .then((songs) =>
        setChartState({ key: requestKey, status: 'loaded', songs }),
      )
      .catch((requestError) => {
        if (requestError.name !== 'AbortError') {
          setChartState({
            key: requestKey,
            status: 'error',
            error: requestError.message,
          })
        }
      })
    return () => controller.abort()
  }, [reloadToken, chartRequestKey])

  const currentPageState =
    pageState?.key === pageRequestKey ? pageState : null
  const pageData = currentPageState?.data || { total: 0, items: [] }
  const loading = !currentPageState || currentPageState.status === 'loading'
  const error =
    currentPageState?.status === 'error' ? currentPageState.error : ''
  const currentChartState =
    chartState?.key === chartRequestKey ? chartState : null
  const chartSongs = currentChartState?.songs || []
  const chartLoading =
    !currentChartState || currentChartState.status === 'loading'
  const chartError =
    currentChartState?.status === 'error' ? currentChartState.error : ''
  const pageCount = Math.max(1, Math.ceil(pageData.total / PAGE_SIZE))
  const visibleRows = pageData.items
  const formattedCount = useMemo(
    () => new Intl.NumberFormat().format(pageData.total),
    [pageData.total],
  )

  function changeSort(key) {
    setPage(1)
    setSort((current) => ({
      key,
      direction: current.key === key && current.direction === 'asc' ? 'desc' : 'asc',
    }))
  }

  function downloadCsv() {
    if (visibleRows.length === 0) return
    const lines = [
      columns.map(({ label }) => csvCell(label)).join(','),
      ...visibleRows.map((song) => columns.map(({ key }) => csvCell(song[key])).join(',')),
    ]
    const blob = new Blob([`\uFEFF${lines.join('\r\n')}`], {
      type: 'text/csv;charset=utf-8',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `songs-page-${page}.csv`
    document.body.append(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  async function searchByTitle(event) {
    event.preventDefault()
    const title = lookupTitle.trim()
    setLookupResult(null)
    setLookupError('')
    if (!title) {
      setLookupError('Enter a song title to search.')
      return
    }

    setLookupLoading(true)
    try {
      const params = new URLSearchParams({ title })
      const result = await requestJson(`/songs/lookup?${params}`)
      setLookupResult(result)
    } catch (requestError) {
      setLookupError(requestError.message)
    } finally {
      setLookupLoading(false)
    }
  }

  return (
    <main className="dashboard">
      <header className="page-header">
        <div className="brand-lockup" aria-label="Soundboard">
          <span className="brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
            <span />
          </span>
          <span>soundboard</span>
        </div>
        <p className="eyebrow">CATALOG EXPLORER</p>
        <div className="heading-row">
          <div>
            <h1>Every song has a story.</h1>
            <p className="lede">
              Explore the details behind the tracks, one data point at a time.
            </p>
          </div>
          <div className="catalog-count">
            <strong>{formattedCount}</strong>
            <span>tracks in catalog</span>
          </div>
        </div>
      </header>

      <section className="panel search-panel" aria-labelledby="lookup-heading">
        <div>
          <p className="eyebrow">FIND A TRACK</p>
          <h2 id="lookup-heading">Search by title</h2>
        </div>
        <form className="search-form" onSubmit={searchByTitle}>
          <label className="visually-hidden" htmlFor="title-search">
            Song title
          </label>
          <input
            id="title-search"
            type="search"
            value={lookupTitle}
            onChange={(event) => setLookupTitle(event.target.value)}
            placeholder="Try “Perfect”"
            autoComplete="off"
          />
          <button className="button button-dark" type="submit" disabled={lookupLoading}>
            {lookupLoading ? 'Searching…' : 'Get song'}
          </button>
        </form>
        <div className="lookup-message" aria-live="polite">
          {lookupError && <p className="error-text">{lookupError}</p>}
          {lookupResult && lookupResult.count === 0 && (
            <p>No matches for “{lookupResult.query}”. Check the title and try again.</p>
          )}
          {lookupResult && lookupResult.count > 0 && (
            <div className="lookup-results">
              <p className="result-count">
                {lookupResult.count === 1
                  ? '1 matching track'
                  : `${lookupResult.count} matching tracks`}
              </p>
              <SongsTable
                songs={lookupResult.matches}
                caption={`Search results for ${lookupResult.query}`}
              />
            </div>
          )}
        </div>
      </section>

      <section className="panel catalog-panel" aria-labelledby="catalog-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">THE COLLECTION</p>
            <h2 id="catalog-heading">Song catalog</h2>
          </div>
          <button
            className="button button-light"
            type="button"
            onClick={downloadCsv}
            disabled={visibleRows.length === 0 || loading}
          >
            <span aria-hidden="true">↓</span> Download this page
          </button>
        </div>

        {error ? (
          <div className="status-card error-card" role="alert">
            <p>Couldn’t load songs: {error}</p>
            <button
              className="button button-light"
              type="button"
              onClick={() => setReloadToken((token) => token + 1)}
            >
              Try again
            </button>
          </div>
        ) : (
          <>
            <p className="table-help" id="sort-help">
              Select a column heading to sort the full catalog. Select it again to reverse the order.
            </p>
            <div className="catalog-table" aria-describedby="sort-help">
              {loading ? (
                <p className="status-card" role="status">
                  Loading songs…
                </p>
              ) : (
                <SongsTable
                  songs={visibleRows}
                  sort={sort}
                  onSort={changeSort}
                  caption="Song catalog. Select a column heading to sort."
                />
              )}
            </div>
            <div className="pagination">
              <p aria-live="polite">
                {pageData.total === 0
                  ? 'No tracks'
                  : `Showing ${(page - 1) * PAGE_SIZE + 1}–${Math.min(
                      page * PAGE_SIZE,
                      pageData.total,
                    )} of ${formattedCount}`}
              </p>
              <div className="pagination-controls">
                <button
                  className="button button-light page-button"
                  type="button"
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  disabled={page <= 1 || loading}
                  aria-label="Previous page"
                >
                  ← <span>Previous</span>
                </button>
                <span className="page-number" aria-live="polite">
                  Page {page} of {pageCount}
                </span>
                <button
                  className="button button-light page-button"
                  type="button"
                  onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
                  disabled={page >= pageCount || loading}
                  aria-label="Next page"
                >
                  <span>Next</span> →
                </button>
              </div>
            </div>
          </>
        )}
      </section>

      <section className="panel chart-panel" aria-labelledby="chart-heading">
        <div className="section-heading">
          <div>
            <p className="eyebrow">A CLOSER LISTEN</p>
            <h2 id="chart-heading">Danceability meets energy</h2>
          </div>
          <span className="chart-tag">AUDIO FEATURES</span>
        </div>
        <p className="chart-intro">
          A track’s danceability and energy are related, but they describe different things.
          Compare the two scores across the catalog.
        </p>
        {chartError ? (
          <p className="error-text" role="alert">
            Couldn’t load chart data: {chartError}
          </p>
        ) : chartLoading ? (
          <p className="status-card" role="status">
            Loading chart data…
          </p>
        ) : chartSongs.length === 0 ? (
          <p className="status-card">No songs available to chart.</p>
        ) : (
          <DanceEnergyChart songs={chartSongs} />
        )}
      </section>

      <footer className="page-footer">
        <span>SONG DATA, MADE EXPLORABLE</span>
        <span>Soundboard · Catalog view</span>
      </footer>
    </main>
  )
}

export default App
