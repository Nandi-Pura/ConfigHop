import { useEffect, useRef, useState, type RefObject } from 'react'
import { Clipboard, Search, Upload } from 'lucide-react'
import LiveConfigEditor from './LiveConfigEditor'
import { platform, platformCatalog, vendors, type Domain, type PlatformSelection } from './platformCatalog'
import type { MockActions } from './MockWorkspace'
import { switchApi, type SwitchProject, type SwitchPreview } from './api/switch'

const KEY = 'confighop-switch-session-v2'
const MAX_SOURCE_BYTES = 2 * 1024 * 1024

type Props = { onDomainChange: (domain: Domain) => void; onTitleChange: (title: string) => void; actionsRef: RefObject<MockActions | null> }
export default function SwitchWorkspace({ onDomainChange, onTitleChange, actionsRef }: Props) {
  const [source, setSource] = useState(() => platform('Switch', 'Cisco', 'C9300-48P', '17.12'))
  const [target, setTarget] = useState(() => platform('Switch', 'HPE Aruba Networking', 'CX 6300M 48G', '10.15'))
  const [project, setProject] = useState<SwitchProject | null>(null)
  const [preview, setPreview] = useState<SwitchPreview | null>(null)
  const [capability, setCapability] = useState<'hpe-aruba-jl663a' | ''>('')
  const [acknowledged, setAcknowledged] = useState(false)
  const [loading, setLoading] = useState(false)
  const [fileName, setFileName] = useState('No configuration loaded')
  const [assignments, setAssignments] = useState<Record<string, string | number>>({})
  const [filter, setFilter] = useState<'All' | 'Mapped' | 'Unmapped'>('All')
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  const serial = useRef(0)
  const revision = useRef(0)
  const controller = useRef<AbortController | null>(null)
  const projectRef = useRef<SwitchProject | null>(null)
  const config = !!project
  const declarations = (project?.inventory.interfaces ?? []).map(item => ({ ...item, type: item.kind }))
  const physical = declarations.filter((item) => item.type === 'Physical')
  const used = new Set(Object.values(assignments))
  const visible = declarations.filter((item) => (filter === 'All' || (filter === 'Mapped' ? !!assignments[item.name] : !assignments[item.name])) && item.name.toLowerCase().includes(search.toLowerCase()))
  const supported = source.vendor === 'Cisco' && target.vendor === 'HPE Aruba Networking'
  const versionsSupported = (['17.12', '17.15', '17.18'].includes(source.softwareVersion) && ['10.10', '10.13', '10.16'].includes(target.softwareVersion)) || (source.softwareVersion === '17.12' && target.softwareVersion === '10.15')
  const invalidate = () => { serial.current++; controller.current?.abort(); setPreview(null); setAcknowledged(false); setLoading(false) }
  const resetSource = () => {
    invalidate()
    const old = projectRef.current
    projectRef.current = null; setProject(null); setFileName('No configuration loaded'); setAssignments({}); setError('')
    if (old) void switchApi.delete(old.project_id).catch(() => {})
  }
  useEffect(() => {
    localStorage.removeItem('confighop-switch-workspace-v1')
    return () => { serial.current++; controller.current?.abort() }
  }, [])
  useEffect(() => {
    if (!project || !supported) return
    const current = ++serial.current
    const abort = new AbortController(); controller.current = abort
    setPreview(null); setAcknowledged(false); setLoading(true)
    const timer = setTimeout(() => {
      const nextRevision = ++revision.current
      void switchApi.preview(project.project_id, { revision: nextRevision, target_os: 'AOS_CX', target_version: target.softwareVersion, capability_id: capability || null, mappings: assignments }, abort.signal)
        .then(result => { if (current === serial.current) setPreview(result) })
        .catch(cause => { if (current === serial.current && !abort.signal.aborted) setError(cause.message) })
        .finally(() => { if (current === serial.current) setLoading(false) })
    }, 250)
    return () => { clearTimeout(timer); abort.abort(); if (current === serial.current) serial.current++ }
  }, [project, assignments, target, capability, supported])
  const ingest = async (text: string, name: string, current: number) => {
    if (current !== serial.current) return
    if (source.vendor !== 'Cisco') { setError('Only Cisco IOS XE source parsing is implemented.'); return }
    if (new Blob([text]).size > MAX_SOURCE_BYTES) { setError('Source exceeds the 2 MB limit.'); return }
    const abort = new AbortController(); controller.current = abort; setLoading(true)
    try {
      const result = await switchApi.inspect(text, source.softwareVersion, abort.signal)
      if (current !== serial.current) { void switchApi.delete(result.project_id).catch(() => {}); return }
      projectRef.current = result; setProject(result); revision.current = result.revision; setFileName(name)
    } catch (cause) { if (current === serial.current && !abort.signal.aborted) setError(cause instanceof Error ? cause.message : 'Source inspection failed.') }
    finally { if (current === serial.current) setLoading(false) }
  }
  const readFile = async (file?: File) => {
    if (!file) return
    resetSource(); const current = serial.current
    if (file.size > MAX_SOURCE_BYTES) { setError('Source exceeds the 2 MB limit.'); return }
    try { await ingest(await file.text(), file.name, current) }
    catch { if (current === serial.current) setError('Could not read the source file.') }
  }
  const paste = async () => {
    resetSource(); const current = serial.current
    try { await ingest(await navigator.clipboard.readText(), 'Clipboard source', current) }
    catch { if (current === serial.current) setError('Clipboard access is unavailable. Upload a file instead.') }
  }
  const updatePlatform = (side: 'source' | 'target', vendor: string, version?: string) => {
    const previous = side === 'source' ? source : target
    const next = platform('Switch', vendor, vendor === previous.vendor ? previous.model : undefined, version)
    invalidate()
    if (side === 'source') { setSource(next); resetSource(); onTitleChange(`${next.softwareProduct} to ${target.softwareProduct}`) }
    else { setTarget(next); if (next.vendor !== previous.vendor) { setAssignments({}); setCapability('') }; onTitleChange(`${source.softwareProduct} to ${next.softwareProduct}`) }
  }
  const choose = (name: string, targetName: string | number) => {
    if (targetName && Object.entries(assignments).some(([other, value]) => other !== name && value === targetName)) { setError('Target interface is already assigned.'); return }
    invalidate(); setError('')
    setAssignments(current => { const next = { ...current }; if (targetName) next[name] = targetName; else delete next[name]; return next })
  }
  const exportCandidate = async () => {
    if (!preview) return
    const current = serial.current
    try {
      const result = await switchApi.export(preview, acknowledged)
      if (current !== serial.current) return
      const url = URL.createObjectURL(new Blob([result.text], { type: 'text/plain' }))
      const link = document.createElement('a'); link.href = url; link.download = result.filename; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (cause) { if (current === serial.current) setError(cause instanceof Error ? cause.message : 'Export failed.') }
  }
  const load = async () => {
    invalidate(); const current = serial.current
    try {
      const saved = JSON.parse(localStorage.getItem(KEY) || 'null')
      if (!saved?.project_id || typeof saved.project_id !== 'string') { setError('No saved Switch session found.'); return }
      const result = await switchApi.get(saved.project_id)
      if (current !== serial.current) return
      if (projectRef.current && projectRef.current.project_id !== result.project_id) void switchApi.delete(projectRef.current.project_id).catch(() => {})
      projectRef.current = result; revision.current = result.revision; setProject(result)
      setSource(platform('Switch', 'Cisco', 'C9300-48P', result.inventory.source_version))
      setTarget(platform('Switch', 'HPE Aruba Networking', 'CX 6300M 48G', result.settings?.target_version || '10.15'))
      setAssignments(result.settings?.mappings || {}); setCapability(result.settings?.capability_id || ''); setFileName('Restored backend session'); setError('Session loaded. Review the current findings.')
    } catch { if (current === serial.current) setError('Saved session is unavailable. Upload the source again.') }
  }
  actionsRef.current = {
    save: () => { if (!project || loading || !preview) { setError('Wait for the current preview before saving.'); return }; localStorage.setItem(KEY, JSON.stringify({ project_id: project.project_id })); setError('Session reference saved. Source configuration is not stored in this browser.') },
    load: () => { void load() },
    clear: resetSource,
    reset: () => { resetSource(); setSource(platform('Switch', 'Cisco', 'C9300-48P', '17.12')); setTarget(platform('Switch', 'HPE Aruba Networking', 'CX 6300M 48G', '10.15')); setCapability(''); onTitleChange('IOS XE to AOS-CX') },
  }
  const platformCard = (label: string, value: PlatformSelection, side: 'source' | 'target') => <div className="section-card locked-platform"><strong>{label} Platform</strong><span>{side === 'source' ? 'Current environment' : 'Migration destination'}</span><div className="locked-fields"><label>Vendor<select aria-label={`${label} vendor`} value={value.vendor} onChange={(event) => updatePlatform(side, event.target.value)}>{vendors('Switch').map((vendor) => <option key={vendor}>{vendor}</option>)}</select></label><label>Network OS<select aria-label={`${label} Network OS`} value={value.softwareVersion} onChange={(event) => updatePlatform(side, value.vendor, event.target.value)}>{(platformCatalog.Switch as Record<string, { versions: string[] }>)[value.vendor].versions.map((version) => <option key={version} value={version}>{value.softwareProduct} {version}</option>)}</select></label></div><small>{supported ? versionsSupported ? 'Limited OS-based IOS XE to AOS-CX translation' : 'Version outside tested subset; preview blocked' : 'Unsupported translation pair'}</small></div>
  return <main className="workspace locked-workspace switch-workspace">
    <div className="locked-title"><div><h1>Switch Migration</h1><p>Translate supported switch configuration and review dependencies</p></div><label>Migration Type<select value="Switch" onChange={() => onDomainChange('Firewall')}><option>Switch</option><option>Firewall</option></select></label></div>
    {error && <div className="api-error" role="status">{error}</div>}
    <div className="locked-top"><div className="section-card locked-platform"><strong>Select Domain</strong><span>Network technology domain</span><select aria-label="Domain" value="Switch" onChange={() => onDomainChange('Firewall')}><option>Switch</option><option>Firewall</option></select></div>{platformCard('Source', source, 'source')}{platformCard('Target', target, 'target')}<div className="section-card locked-platform"><strong>Source Configuration</strong><span>Upload or paste a running configuration</span><div className="locked-upload"><button className="btn accent-outline" onClick={() => fileRef.current?.click()}><Upload size={15} /> Upload File</button><button className="btn secondary" onClick={() => void paste()}><Clipboard size={15} /> Paste from Clipboard</button><input ref={fileRef} type="file" accept=".txt,.cfg,.conf,text/plain" hidden onChange={(event) => { void readFile(event.target.files?.[0]); event.target.value = '' }} /></div><small>{fileName}</small></div></div>
    <div className="section-card locked-inventory"><strong>Source Inventory <small>(parsed by the local backend)</small></strong><div className="locked-metrics"><div><b>{config ? physical.length : '—'}</b><span>Configured physical declarations</span></div><div><b>{config ? declarations.filter((item) => ['LAG', 'SVI', 'Loopback'].includes(item.type)).length : '—'}</b><span>Logical declarations</span></div><div><b>{config ? declarations.filter((item) => item.type === 'Other').length : '—'}</b><span>Unrecognized declarations</span></div></div><small>Declarations do not prove operational link state. Physical capabilities and deployment readiness require separate review.</small></div>
    <div className="locked-main"><section className="section-card locked-mapping"><div className="live-heading"><strong>Interface Mapping</strong><span className="muted">Explicit target interfaces</span></div><div className="mapping-toolbar"><div className="search-wrap"><Search size={14} /><input aria-label="Search switch interfaces" placeholder="Search interfaces..." value={search} onChange={(event) => setSearch(event.target.value)} /></div>{(['All', 'Mapped', 'Unmapped'] as const).map((item) => <button key={item} className={`chip ${filter === item ? 'active' : ''}`} onClick={() => setFilter(item)}>{item}</button>)}<button className="btn secondary" onClick={() => { invalidate(); setAssignments({}) }}>Clear All</button></div><div className={capability ? 'locked-map-body' : 'locked-map-body manual-mapping'}><div className="locked-interface-list">{visible.length ? visible.map((item) => <div className="locked-interface-row" key={item.name}><span>{item.name}<small>{item.type} declaration</small></span>{capability ? <select aria-label={`Logical target slot for ${item.name}`} disabled={item.type !== 'Physical'} value={assignments[item.name] ?? ''} onChange={(event) => choose(item.name, Number(event.target.value))}><option value="">Unmapped</option>{Array.from({ length: 48 }, (_, index) => index + 1).filter((slot) => !used.has(slot) || assignments[item.name] === slot).map((slot) => <option key={slot} value={slot}>Slot {slot}</option>)}</select> : item.type === 'Physical' ? <input aria-label={`Target interface for ${item.name}`} placeholder="1/1/24" value={String(assignments[item.name] ?? '')} onChange={event => choose(item.name, event.target.value.trim())} /> : <span className="muted">OS-derived</span>}</div>) : <div className="live-empty">{config ? 'No matching interface declarations.' : 'Upload a configuration to inspect interface declarations.'}</div>}</div>{capability && <div className="locked-slot-panel"><strong>JL663A target slots (48)</strong><small>Selected SKU inventory; verify actual device and cabling separately.</small><div className="locked-port-grid">{Array.from({ length: 48 }, (_, index) => { const slot = index + 1; const owner = Object.entries(assignments).find(([, value]) => value === slot)?.[0]; return <span key={slot} className={owner ? 'assigned' : ''} title={owner ? `${owner} -> logical slot ${slot}` : `Logical slot ${slot} available`}>{slot}</span> })}</div></div>}</div></section><LiveConfigEditor syntax="cli" text={preview?.candidate.text || ''} status={preview?.candidate.status || (supported ? 'AWAITING SOURCE' : 'UNSUPPORTED')} loading={loading} message={supported ? 'Upload an IOS XE configuration, then map interfaces to preview the limited AOS-CX candidate.' : 'Switch configuration generation is unavailable for this source-target pair.'} findings={preview?.candidate.findings.map(f => ({ ...f, message: `${f.scope}: ${f.message}` }))} onCopyError={() => setError('Clipboard access is unavailable.')} /></div>
    <details className="section-card"><summary>Target capability and translation report</summary><label>Optional target capability<select aria-label="Optional target capability" value={capability} onChange={event => { invalidate(); setAssignments({}); setCapability(event.target.value as typeof capability) }}><option value="">Unknown hardware - planning only</option><option value="hpe-aruba-jl663a">JL663A standalone - ports 1/1/1 through 1/1/48</option></select></label><p>Exact SKU port naming only. No operational, cabling, firmware patch, or deployment certification.</p><p>{preview && `Constructs ${preview.candidate.translation_summary.meaningful_constructs}; translated ${preview.candidate.translation_summary.translated_constructs}; blocked ${preview.candidate.translation_summary.blocked_constructs}; unresolved dependencies ${preview.candidate.translation_summary.unresolved_dependencies}; hardware ${preview.candidate.translation_summary.hardware_compatibility_status}.`}</p><p>{Object.entries(preview?.candidate.coverage || {}).map(([status, count]) => `${status}: ${count}`).join(' / ')}</p><div className="live-findings">{preview?.candidate.report.map((s, index) => <p key={index}>Line {s.line} / {s.scope} / {s.status}<br /><code>{s.source}</code></p>)}</div></details>
    <div className="locked-export"><label><input type="checkbox" checked={acknowledged} disabled={!preview || preview.candidate.status === 'BLOCKED'} onChange={event => setAcknowledged(event.target.checked)} /> I reviewed the current findings and deployment limitations.</label><button className="btn accent" disabled={!preview || loading || preview.candidate.status === 'BLOCKED' || !acknowledged} onClick={() => void exportCandidate()}>Export</button></div>
  </main>
}
