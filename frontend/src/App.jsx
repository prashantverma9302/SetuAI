import { lazy, Suspense, useEffect, useState } from 'react'

const API_BASE = 'http://localhost:8010'
const Plot = lazy(async () => {
  const [{ default: createPlotlyComponent }, { default: Plotly }] =
    await Promise.all([
      import('react-plotly.js/factory'),
      import('plotly.js-dist-min'),
    ])
  return { default: createPlotlyComponent(Plotly) }
})

// Chip styling per node type. Obstacles read warm, attributed nodes read cool.
const NODE_STYLES = {
  unknown_eoa: 'bg-slate-100 text-slate-600 ring-slate-300',
  peel_chain: 'bg-slate-100 text-slate-600 ring-slate-300',
  deposit_address: 'bg-sky-50 text-sky-800 ring-sky-300',
  hot_wallet: 'bg-emerald-50 text-emerald-800 ring-emerald-300',
  bridge: 'bg-amber-50 text-amber-900 ring-amber-400',
  dex: 'bg-amber-50 text-amber-900 ring-amber-400',
  mixer: 'bg-rose-50 text-rose-900 ring-rose-400',
}

const NODE_LABELS = {
  unknown_eoa: 'unknown EOA',
  peel_chain: 'peel chain',
  deposit_address: 'deposit address',
  hot_wallet: 'hot wallet',
  bridge: 'bridge',
  dex: 'DEX',
  mixer: 'mixer',
}

const BAND_STYLES = {
  high: 'bg-emerald-600 text-white',
  medium: 'bg-amber-500 text-white',
  low: 'bg-rose-600 text-white',
}

function truncate(value, head = 10, tail = 8) {
  if (!value || value.length <= head + tail + 1) return value
  return `${value.slice(0, head)}…${value.slice(-tail)}`
}

function Chip({ nodeType }) {
  const style = NODE_STYLES[nodeType] ?? NODE_STYLES.unknown_eoa
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${style}`}
    >
      {NODE_LABELS[nodeType] ?? nodeType}
    </span>
  )
}

function ConfidenceBadge({ score, band }) {
  return (
    <div className="flex items-baseline gap-2">
      <span
        className={`rounded px-3 py-1 text-2xl font-semibold tabular-nums ${BAND_STYLES[band]}`}
      >
        {score}
      </span>
      <span className="text-xs uppercase tracking-wide text-slate-500">
        / 100 · {band} confidence
      </span>
    </div>
  )
}

function StatusBanner({ status, recommendedAction }) {
  const deadEnd = status === 'dead_end'
  return (
    <div
      className={`rounded border-l-4 p-4 ${
        deadEnd
          ? 'border-rose-600 bg-rose-50'
          : 'border-emerald-600 bg-emerald-50'
      }`}
    >
      <div className="flex items-center gap-2">
        <span
          className={`text-sm font-bold uppercase tracking-wider ${
            deadEnd ? 'text-rose-800' : 'text-emerald-800'
          }`}
        >
          {deadEnd ? '⛔ Dead end' : '✓ Clean path'}
        </span>
      </div>
      {deadEnd && recommendedAction && (
        <div className="mt-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-rose-900">
            Recommended next action
          </p>
          <p className="mt-1 text-sm leading-relaxed text-rose-950">
            {recommendedAction}
          </p>
        </div>
      )}
      {!deadEnd && (
        <p className="mt-1 text-sm text-emerald-900">
          Trail terminates at an attributable VASP. Proceed to legal request.
        </p>
      )}
    </div>
  )
}

function Field({ label, children }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </dt>
      <dd className="mt-1 text-sm text-slate-900">{children}</dd>
    </div>
  )
}

function HopGraph({ hops }) {
  const chainOrder = [...new Set(hops.map((hop) => hop.chain))]
  const chainY = (chain) => (chainOrder.length - 1) / 2 - chainOrder.indexOf(chain)
  const nodes = []
  const nodeIndexes = new Map()
  const links = []
  const chartHeight = Math.max(280, chainOrder.length * 170)
  const nodeColors = {
    unknown_eoa: '#64748b',
    peel_chain: '#94a3b8',
    deposit_address: '#0284c7',
    hot_wallet: '#059669',
    bridge: '#d97706',
    dex: '#ea580c',
    mixer: '#e11d48',
  }

  function addNode(chain, address, nodeType, x) {
    const key = `${chain}:${address}`
    if (!nodeIndexes.has(key)) {
      nodeIndexes.set(key, nodes.length)
      nodes.push({
        label: `${chain} ${truncate(address, 3, 3)}`,
        address,
        chain,
        nodeType,
        color: nodeColors[nodeType] ?? nodeColors.unknown_eoa,
        x,
        y: chainY(chain),
      })
    }
    return nodeIndexes.get(key)
  }

  hops.forEach((hop, index) => {
    const source = addNode(hop.chain, hop.from_address, 'unknown_eoa', index)
    const target = addNode(hop.chain, hop.to_address, hop.node_type, index + 1)
    links.push({
      source,
      target,
      color: '#64748b',
      dash: 'solid',
      detail: `Hop ${hop.seq} · ${hop.chain} · ${hop.value} ${hop.asset}`,
      tx: hop.tx_hash,
      timestamp: hop.timestamp,
      note: hop.note ?? '',
    })

    const nextHop = hops[index + 1]
    if (hop.node_type === 'bridge' && nextHop && hop.chain !== nextHop.chain) {
      const bridgeOutput = addNode(
        nextHop.chain,
        nextHop.from_address,
        'bridge',
        index + 1,
      )
      links.push({
        source: target,
        target: bridgeOutput,
        color: '#d97706',
        dash: 'dash',
        detail: `Inferred bridge link · ${hop.chain} to ${nextHop.chain}`,
        tx: '',
        timestamp: '',
        note: nextHop.note ?? 'Cross-chain relationship inferred',
      })
    }
  })

  const linkTraces = links.map((link) => {
    const source = nodes[link.source]
    const target = nodes[link.target]
    return {
      type: 'scatter',
      mode: 'lines',
      x: [source.x, target.x],
      y: [source.y, target.y],
      line: { color: link.color, width: 2, dash: link.dash },
      hoverinfo: 'skip',
      showlegend: false,
    }
  })
  const nodeTrace = {
    type: 'scatter',
    mode: 'markers+text',
    x: nodes.map((node) => node.x),
    y: nodes.map((node) => node.y),
    text: nodes.map((node) => node.label),
    textposition: 'top center',
    textfont: { size: 10 },
    marker: {
      size: 18,
      color: nodes.map((node) => node.color),
      line: { color: '#ffffff', width: 2 },
    },
    customdata: nodes.map((node) => [node.chain, node.address, node.nodeType]),
    hovertemplate:
      '%{customdata[0]}<br>%{customdata[1]}<br>Node type: %{customdata[2]}<extra></extra>',
    showlegend: false,
  }
  const linkHoverTrace = {
    type: 'scatter',
    mode: 'markers',
    x: links.map((link) => (nodes[link.source].x + nodes[link.target].x) / 2),
    y: links.map((link) => (nodes[link.source].y + nodes[link.target].y) / 2),
    marker: {
      size: 12,
      color: links.map((link) => link.color),
      opacity: 0.65,
    },
    customdata: links.map((link) => [
      link.detail,
      link.tx,
      link.timestamp,
      link.note,
    ]),
    hovertemplate:
      '%{customdata[0]}<br>Transaction: %{customdata[1]}<br>%{customdata[2]}<br>%{customdata[3]}<extra></extra>',
    showlegend: false,
  }
  const annotations = links.map((link) => {
    const source = nodes[link.source]
    const target = nodes[link.target]
    const distance = Math.hypot(target.x - source.x, target.y - source.y) || 1
    return {
      x: target.x - ((target.x - source.x) / distance) * 0.2,
      y: target.y - ((target.y - source.y) / distance) * 0.2,
      ax: source.x,
      ay: source.y,
      xref: 'x',
      yref: 'y',
      axref: 'x',
      ayref: 'y',
      showarrow: true,
      arrowhead: 3,
      arrowsize: 1,
      arrowwidth: 1.5,
      arrowcolor: link.color,
    }
  })

  return (
    <Suspense fallback={<div className="h-64 animate-pulse bg-slate-50" />}>
      <Plot
        data={[...linkTraces, nodeTrace, linkHoverTrace]}
        layout={{
          autosize: true,
          height: chartHeight,
          margin: { l: 60, r: 32, t: 38, b: 32 },
          font: { family: 'ui-monospace, SFMono-Regular, Menlo, monospace', size: 11 },
          xaxis: {
            range: [-0.5, hops.length + 0.5],
            showgrid: false,
            zeroline: false,
            showticklabels: false,
            fixedrange: true,
          },
          yaxis: {
            range: [-(chainOrder.length / 2), chainOrder.length / 2],
            tickmode: 'array',
            tickvals: chainOrder.map((chain) => chainY(chain)),
            ticktext: chainOrder,
            showgrid: false,
            zeroline: false,
            fixedrange: true,
          },
          annotations,
        }}
        config={{ responsive: true, displaylogo: false }}
        style={{ width: '100%', minWidth: '720px', height: `${chartHeight}px` }}
        useResizeHandler
      />
    </Suspense>
  )
}

function Result({ data, onDownloadPdf, downloading }) {
  const foreign = data.jurisdiction === 'foreign'
  const domestic = data.jurisdiction === 'domestic'

  return (
    <div className="mt-8 overflow-hidden rounded border border-slate-300 bg-white shadow-sm">
      {/* Case header */}
      <div className="border-b border-slate-200 bg-slate-50 px-6 py-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              Subject wallet
            </p>
            <p className="mt-1 break-all font-mono text-sm text-slate-900">
              {data.wallet_address}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <ConfidenceBadge
              score={data.confidence}
              band={data.confidence_breakdown.band}
            />
            <button
              type="button"
              disabled={downloading}
              onClick={onDownloadPdf}
              className="rounded bg-slate-900 px-3 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              {downloading ? 'Preparing PDF…' : 'Download PDF'}
            </button>
          </div>
        </div>
      </div>

      <div className="space-y-6 px-6 py-5">
        <StatusBanner
          status={data.status}
          recommendedAction={data.recommended_action}
        />

        {/* Attribution summary */}
        <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
          <Field label="Destination">
            {data.destination_label ?? '—'}
          </Field>
          <Field label="VASP">{data.vasp_name ?? 'Not attributed'}</Field>
          <Field label="Routing">
            <span
              className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${
                domestic
                  ? 'bg-sky-50 text-sky-900 ring-sky-400'
                  : foreign
                    ? 'bg-violet-50 text-violet-900 ring-violet-400'
                    : 'bg-slate-100 text-slate-700 ring-slate-300'
              }`}
            >
              {domestic ? 'DOMESTIC' : foreign ? 'FOREIGN' : 'UNKNOWN'}
            </span>
          </Field>
          <Field label="Path">
            {data.hop_count} hops · {data.chains_traversed.join(' → ')}
          </Field>
        </dl>

        {/* Confidence breakdown */}
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            How this score was reached
          </h3>
          <ul className="mt-2 divide-y divide-slate-100 rounded border border-slate-200">
            {data.confidence_breakdown.components.map((component, index) => (
              <li
                key={index}
                className="flex items-baseline gap-3 px-3 py-2 text-sm"
              >
                <span
                  className={`w-10 shrink-0 text-right font-mono font-semibold tabular-nums ${
                    component.points < 0 ? 'text-rose-700' : 'text-slate-700'
                  }`}
                >
                  {component.points > 0 ? '+' : ''}
                  {component.points}
                </span>
                <span className="font-medium text-slate-800">
                  {component.name}
                </span>
                <span className="text-slate-500">{component.reason}</span>
              </li>
            ))}
          </ul>
        </section>

        {/* Hop graph */}
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Transaction flow
          </h3>
          <div className="mt-2 overflow-x-auto rounded border border-slate-200 bg-white p-2">
            <HopGraph hops={data.hops} />
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Solid arrows are traced hops; dashed arrows mark inferred bridge links.
          </p>
        </section>

        {/* Hops */}
        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Traced hops
          </h3>
          <ol className="mt-2 space-y-2">
            {data.hops.map((hop) => (
              <li
                key={hop.seq}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded border border-slate-200 px-3 py-2 text-sm"
              >
                <span className="w-6 shrink-0 font-mono text-xs text-slate-400">
                  {hop.seq}
                </span>
                <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-xs text-white">
                  {hop.chain}
                </span>
                <span className="font-mono text-xs text-slate-600">
                  {truncate(hop.from_address)}
                </span>
                <span className="text-slate-400">→</span>
                <span className="font-mono text-xs text-slate-900">
                  {truncate(hop.to_address)}
                </span>
                <span className="font-mono text-xs text-slate-500">
                  {hop.value} {hop.asset}
                </span>
                <Chip nodeType={hop.node_type} />
                {hop.label && (
                  <span className="text-xs text-slate-500">{hop.label}</span>
                )}
              </li>
            ))}
          </ol>
        </section>

        {/* Raw payload */}
        <details className="rounded border border-slate-200">
          <summary className="cursor-pointer px-3 py-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Raw JSON response
          </summary>
          <pre className="overflow-x-auto border-t border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
            {JSON.stringify(data, null, 2)}
          </pre>
        </details>
      </div>
    </div>
  )
}

const CASE_FIELDS = [
  { key: 'fir_number', label: 'FIR / DD entry', placeholder: 'FIR 214/2026' },
  { key: 'police_station', label: 'Police station', placeholder: 'Cyber Crime PS' },
  { key: 'district', label: 'District', placeholder: 'NTR District' },
  { key: 'officer_name', label: 'Investigating officer', placeholder: 'Insp. A. Kumar' },
  {
    key: 'officer_designation',
    label: 'Designation',
    placeholder: 'Inspector of Police',
  },
]

const DOWNLOAD_FORMATS = [
  { format: 'pdf', label: 'PDF' },
  { format: 'md', label: 'Markdown' },
  { format: 'html', label: 'HTML (print to PDF)' },
  { format: 'json', label: 'JSON' },
]

function HashRow({ label, value, note }) {
  return (
    <div className="border-t border-slate-700 px-3 py-2 first:border-t-0">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">
          {label}
        </span>
        <span className="text-[10px] text-slate-500">{note}</span>
      </div>
      <p className="mt-1 break-all font-mono text-[11px] leading-relaxed text-emerald-300">
        {value}
      </p>
    </div>
  )
}

function ReportPanel({ report, onDownload, downloading }) {
  const instrument = report.legal_instrument
  const noInstrument = instrument.code === 'NO_INSTRUMENT'

  return (
    <div className="mt-6 overflow-hidden rounded border border-slate-300 bg-white shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-slate-200 bg-slate-50 px-6 py-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Report
          </p>
          <p className="mt-1 font-mono text-sm text-slate-900">
            {report.report_id}
          </p>
        </div>
        <p className="text-xs text-slate-500">
          Generated {report.generated_at} UTC
        </p>
      </div>

      <div className="space-y-6 px-6 py-5">
        {report.review_required && (
          <div className="rounded border-l-4 border-rose-600 bg-rose-50 p-4 text-sm font-semibold text-rose-900">
            Supervisory review required — confidence is below{' '}
            {report.review_threshold}/100. This draft is not cleared for service.
          </div>
        )}

        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Legal instrument selected
          </h3>
          <div
            className={`mt-2 rounded border-l-4 p-4 ${
              noInstrument
                ? 'border-slate-400 bg-slate-50'
                : 'border-sky-600 bg-sky-50'
            }`}
          >
            <p className="text-sm font-semibold text-slate-900">
              {instrument.short_name}
            </p>
            <dl className="mt-3 space-y-1.5 text-xs text-slate-700">
              <div>
                <dt className="inline font-semibold">Statutory basis: </dt>
                <dd className="inline">{instrument.statute}</dd>
              </div>
              <div>
                <dt className="inline font-semibold">Route: </dt>
                <dd className="inline">{instrument.route}</dd>
              </div>
              <div>
                <dt className="inline font-semibold">Response window: </dt>
                <dd className="inline">{instrument.response_window}</dd>
              </div>
            </dl>
            <p className="mt-3 text-xs italic leading-relaxed text-slate-600">
              {instrument.why}
            </p>
          </div>
        </section>

        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Draft — requires officer review and signature
          </h3>
          <pre className="mt-2 max-h-80 overflow-auto rounded border border-slate-200 bg-slate-50 p-3 font-mono text-[11px] leading-relaxed whitespace-pre-wrap text-slate-800">
            {report.draft_body}
          </pre>
        </section>

        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Integrity — {report.integrity.algorithm}
          </h3>
          <div className="mt-2 rounded bg-slate-900">
            <HashRow
              label="Findings hash"
              value={report.integrity.findings_hash}
              note="stable across re-runs"
            />
            <HashRow
              label="Document hash"
              value={report.integrity.document_hash}
              note="unique to this issuance"
            />
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-slate-500">
            The findings hash covers the attribution only, so the same wallet
            always produces the same value. The document hash additionally covers
            the case details, the draft and the timestamp. Export as JSON to
            recompute either.
          </p>
        </section>

        <section>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Download
          </h3>
          <div className="mt-2 flex flex-wrap gap-2">
            {DOWNLOAD_FORMATS.map((item) => (
              <button
                key={item.format}
                type="button"
                disabled={Boolean(downloading)}
                onClick={() => onDownload(item.format)}
                className="rounded border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm transition hover:border-slate-500 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {downloading === item.format ? 'Preparing…' : item.label}
              </button>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}

export default function App() {
  const [address, setAddress] = useState('')
  const [chain, setChain] = useState('BTC')
  const [cases, setCases] = useState([])
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [caseMeta, setCaseMeta] = useState({})
  const [report, setReport] = useState(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [downloading, setDownloading] = useState(null)

  useEffect(() => {
    fetch(`${API_BASE}/cases`)
      .then((response) => (response.ok ? response.json() : []))
      .then(setCases)
      .catch(() => setCases([]))
  }, [])

  async function runTrace(event) {
    event?.preventDefault()
    if (!address.trim()) return

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const response = await fetch(`${API_BASE}/trace`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ wallet_address: address.trim(), chain }),
      })
      const payload = await response.json()
      if (!response.ok) {
        setError(payload.detail ?? 'Trace failed.')
      } else {
        setResult(payload)
      }
    } catch {
      setError(
        `Could not reach the API at ${API_BASE}. Is the backend running?`,
      )
    } finally {
      setLoading(false)
    }
  }

  async function downloadPdf() {
    if (!result) return

    setDownloading(true)
    setError(null)
    try {
      const response = await fetch(`${API_BASE}/report/download?format=pdf`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          wallet_address: result.wallet_address,
          chain: result.chain,
          case: {},
        }),
      })
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}))
        throw new Error(payload.detail ?? 'Could not generate the PDF report.')
      }

      const blob = await response.blob()
      const downloadUrl = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = downloadUrl
      link.download = `wallet-attribution-${result.wallet_address.slice(0, 12)}.pdf`
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(downloadUrl)
    } catch (downloadError) {
      setError(downloadError.message)
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <header className="border-b border-slate-300 bg-white">
        <div className="mx-auto max-w-4xl px-6 py-5">
          <h1 className="text-lg font-semibold tracking-tight">
            VASP Attribution
          </h1>
          <p className="mt-0.5 text-sm text-slate-500">
            Trace wallet addresses across multiple chains
          </p>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-8">
        <form onSubmit={runTrace} className="flex flex-wrap gap-3">
          <input
            type="text"
            value={address}
            onChange={(event) => setAddress(event.target.value)}
            placeholder="Paste a wallet address"
            aria-label="Wallet address"
            className="min-w-0 flex-1 rounded border border-slate-300 bg-white px-3 py-2 font-mono text-sm shadow-sm outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-300"
          />
          <select
            value={chain}
            onChange={(event) => setChain(event.target.value)}
            aria-label="Chain"
            className="rounded border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-300"
          >
            <option>BTC</option>
            <option>ETH</option>
            <option>TRON</option>
            <option>BNB</option>
            <option>SOL</option>
            <option>MATIC</option>
          </select>
          <button
            type="submit"
            disabled={loading || !address.trim()}
            className="rounded bg-slate-900 px-5 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-400"
          >
            {loading ? 'Tracing…' : 'Trace'}
          </button>
        </form>

        {cases.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-xs uppercase tracking-wide text-slate-500">
              Fixture cases:
            </span>
            {cases.map((item) => (
              <button
                key={item.wallet_address}
                type="button"
                onClick={() => {
                  setAddress(item.wallet_address)
                  setChain(item.chain)
                }}
                title={item.case_note}
                className="rounded border border-slate-300 bg-white px-2 py-1 font-mono text-xs text-slate-600 shadow-sm transition hover:border-slate-500 hover:text-slate-900"
              >
                {truncate(item.wallet_address, 12, 6)}
              </button>
            ))}
          </div>
        )}

        {error && (
          <div className="mt-8 rounded border-l-4 border-slate-600 bg-white p-4 text-sm text-slate-700">
            {error}
          </div>
        )}

        {result && (
          <Result
            data={result}
            onDownloadPdf={downloadPdf}
            downloading={downloading}
          />
        )}

        {!result && !error && (
          <p className="mt-10 text-center text-sm text-slate-400">
            Enter a wallet address to trace its path to a destination VASP.
          </p>
        )}
      </main>
    </div>
  )
}
