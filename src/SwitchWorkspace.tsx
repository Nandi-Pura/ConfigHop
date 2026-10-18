import { useRef, useState, type RefObject } from 'react'
import { Clipboard, Search, Upload } from 'lucide-react'
import LiveConfigEditor from './LiveConfigEditor'
import { platform, platformCatalog, vendors, type Domain, type PlatformSelection } from './platformCatalog'
import type { MockActions } from './MockWorkspace'
import { inspectSwitchDeclarations, validSlotAssignments } from './switchInspection'

const KEY = 'confighop-switch-workspace-v1'
const MAX_SOURCE_BYTES = 2 * 1024 * 1024

type Props = { onDomainChange: (domain: Domain) => void; onTitleChange: (title: string) => void; actionsRef: RefObject<MockActions | null> }
export default function SwitchWorkspace({ onDomainChange, onTitleChange, actionsRef }: Props) {
  const [source, setSource] = useState(() => platform('Switch', 'Cisco', 'C9300-48P', '17.12'))
  const [target, setTarget] = useState(() => platform('Switch', 'HPE Aruba Networking', 'CX 6300M 48G', '10.15'))
  const [config, setConfig] = useState('')
  const [fileName, setFileName] = useState('No configuration loaded')
  const [assignments, setAssignments] = useState<Record<string, number>>({})
  const [filter, setFilter] = useState<'All' | 'Mapped' | 'Unmapped'>('All')
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  const serial = useRef(0)
  const declarations = inspectSwitchDeclarations(config)
  const physical = declarations.filter((item) => item.type === 'Physical')
  const used = new Set(Object.values(assignments))
  const visible = declarations.filter((item) => (filter === 'All' || (filter === 'Mapped' ? !!assignments[item.name] : !assignments[item.name])) && item.name.toLowerCase().includes(search.toLowerCase()))
  const resetSource = () => { serial.current++; setConfig(''); setFileName('No configuration loaded'); setAssignments({}); setError('') }
  const readFile = async (file?: File) => {
    if (!file) return
    resetSource()
    const current = serial.current
    if (file.size > MAX_SOURCE_BYTES) { setError('Source exceeds the 2 MB local inspection limit.'); return }
    try { const text = await file.text(); if (current !== serial.current) return; setConfig(text); setFileName(file.name) }
    catch { if (current === serial.current) setError('Could not read the source file.') }
  }
  const paste = async () => {
    const current = ++serial.current
    try { const text = await navigator.clipboard.readText(); if (current !== serial.current || !text.trim()) return; resetSource(); if (new Blob([text]).size > MAX_SOURCE_BYTES) { setError('Source exceeds the 2 MB local inspection limit.'); return }; setConfig(text); setFileName('Clipboard source') }
    catch { if (current === serial.current) setError('Clipboard access is unavailable. Upload a file instead.') }
  }
  const updatePlatform = (side: 'source' | 'target', vendor: string, version?: string) => {
    const previous = side === 'source' ? source : target
    const next = platform('Switch', vendor, vendor === previous.vendor ? previous.model : undefined, version)
    if (side === 'source') { setSource(next); resetSource(); onTitleChange(`${next.model} → ${target.model}`) }
    else { setTarget(next); setAssignments({}); onTitleChange(`${source.model} → ${next.model}`) }
  }
  const choose = (name: string, slot: number) => setAssignments((current) => {
    if (slot && Object.entries(current).some(([other, value]) => other !== name && value === slot)) return current
    const next = { ...current }; if (slot) next[name] = slot; else delete next[name]; return next
  })
  actionsRef.current = {
    save: () => { localStorage.setItem(KEY, JSON.stringify({ source, target, config, fileName, assignments })); setError('Project saved in this browser.') },
    load: () => { try { const raw = localStorage.getItem(KEY); if (!raw) { setError('No saved Switch project found.'); return }; const saved = JSON.parse(raw); const nextSource = platform('Switch', saved.source.vendor, saved.source.model, saved.source.softwareVersion); const nextTarget = platform('Switch', saved.target.vendor, saved.target.model, saved.target.softwareVersion); const text = typeof saved.config === 'string' && new Blob([saved.config]).size <= MAX_SOURCE_BYTES ? saved.config : ''; serial.current++; setSource(nextSource); setTarget(nextTarget); setConfig(text); setFileName(text && typeof saved.fileName === 'string' ? saved.fileName : 'No configuration loaded'); setAssignments(validSlotAssignments(text, saved.assignments)); setError('Project loaded. Recheck mappings before use.'); onTitleChange(`${nextSource.model} → ${nextTarget.model}`) } catch { setError('Saved Switch project could not be loaded.') } },
    clear: resetSource,
    reset: () => { resetSource(); setSource(platform('Switch', 'Cisco', 'C9300-48P', '17.12')); setTarget(platform('Switch', 'HPE Aruba Networking', 'CX 6300M 48G', '10.15')); onTitleChange('C9300-48P → CX 6300M 48G') },
  }
  const platformCard = (label: string, value: PlatformSelection, side: 'source' | 'target') => <div className="section-card locked-platform"><strong>{label} Platform</strong><span>{side === 'source' ? 'Current environment' : 'Migration destination'}</span><div className="locked-fields"><label>Vendor<select aria-label={`${label} vendor`} value={value.vendor} onChange={(event) => updatePlatform(side, event.target.value)}>{vendors('Switch').map((vendor) => <option key={vendor}>{vendor}</option>)}</select></label><label>Network OS<select aria-label={`${label} Network OS`} value={value.softwareVersion} onChange={(event) => updatePlatform(side, value.vendor, event.target.value)}>{(platformCatalog.Switch as Record<string, { versions: string[] }>)[value.vendor].versions.map((version) => <option key={version} value={version}>{value.softwareProduct} {version}</option>)}</select></label></div><small>Planned integration · no Switch translation API</small></div>
  return <main className="workspace locked-workspace switch-workspace">
    <div className="locked-title"><div><h1>Switch Migration</h1><p>Inspect a switch source and plan interface assignments</p></div><label>Migration Type<select value="Switch" onChange={() => onDomainChange('Firewall')}><option>Switch</option><option>Firewall</option></select></label></div>
    {error && <div className="api-error" role="status">{error}</div>}
    <div className="locked-top"><div className="section-card locked-platform"><strong>Select Domain</strong><span>Network technology domain</span><select aria-label="Domain" value="Switch" onChange={() => onDomainChange('Firewall')}><option>Switch</option><option>Firewall</option></select></div>{platformCard('Source', source, 'source')}{platformCard('Target', target, 'target')}<div className="section-card locked-platform"><strong>Source Configuration</strong><span>Upload or paste a running configuration</span><div className="locked-upload"><button className="btn accent-outline" onClick={() => fileRef.current?.click()}><Upload size={15} /> Upload File</button><button className="btn secondary" onClick={() => void paste()}><Clipboard size={15} /> Paste from Clipboard</button><input ref={fileRef} type="file" accept=".txt,.cfg,.conf,text/plain" hidden onChange={(event) => { void readFile(event.target.files?.[0]); event.target.value = '' }} /></div><small>{fileName}</small></div></div>
    <div className="section-card locked-inventory"><strong>Source Inventory <small>(local declaration inspection)</small></strong><div className="locked-metrics"><div><b>{config ? physical.length : '—'}</b><span>Configured physical declarations</span></div><div><b>{config ? declarations.filter((item) => item.type === 'Logical').length : '—'}</b><span>Logical declarations</span></div><div><b>{config ? declarations.filter((item) => item.type === 'Unrecognized').length : '—'}</b><span>Unrecognized declarations</span></div></div><small>Operational state, global features, dependencies, and device capacity are not verified by this local inspection.</small></div>
    <div className="locked-main"><section className="section-card locked-mapping"><div className="live-heading"><strong>Interface Mapping</strong><span className="muted">Logical slot planning only</span></div><div className="mapping-toolbar"><div className="search-wrap"><Search size={14} /><input aria-label="Search switch interfaces" placeholder="Search interfaces…" value={search} onChange={(event) => setSearch(event.target.value)} /></div>{(['All', 'Mapped', 'Unmapped'] as const).map((item) => <button key={item} className={`chip ${filter === item ? 'active' : ''}`} onClick={() => setFilter(item)}>{item}</button>)}<button className="btn secondary" onClick={() => setAssignments({})}>Clear All</button></div><div className="locked-map-body"><div className="locked-interface-list">{visible.length ? visible.map((item) => <div className="locked-interface-row" key={item.name}><span>{item.name}<small>{item.type} declaration</small></span><select aria-label={`Logical target slot for ${item.name}`} disabled={item.type !== 'Physical'} value={assignments[item.name] ?? ''} onChange={(event) => choose(item.name, Number(event.target.value))}><option value="">Unmapped</option>{Array.from({ length: 48 }, (_, index) => index + 1).filter((slot) => !used.has(slot) || assignments[item.name] === slot).map((slot) => <option key={slot} value={slot}>Slot {slot}</option>)}</select></div>) : <div className="live-empty">{config ? 'No matching interface declarations.' : 'Upload a configuration to inspect interface declarations.'}</div>}</div><div className="locked-slot-panel"><strong>Target logical slots (48)</strong><small>UI planning grid; physical port availability and naming require a verified target profile.</small><div className="locked-port-grid">{Array.from({ length: 48 }, (_, index) => { const slot = index + 1; const owner = Object.entries(assignments).find(([, value]) => value === slot)?.[0]; return <span key={slot} className={owner ? 'assigned' : ''} title={owner ? `${owner} → logical slot ${slot}` : `Logical slot ${slot} available`}>{slot}</span> })}</div></div></div></section><LiveConfigEditor text="" status="UNSUPPORTED" message="Switch configuration generation is unavailable. The backend has no Switch migration API; logical assignments are planning data only." findings={[{ severity: 'BLOCKED', code: 'SWITCH_TRANSLATION_UNAVAILABLE', message: 'Global and interface configuration cannot be validated or exported for this source-target pair.' }]} onCopyError={() => setError('Clipboard access is unavailable.')} /></div>
    <div className="locked-export"><span>Export unavailable · no validated Switch candidate exists.</span><button className="btn accent" disabled>Export</button></div>
  </main>
}
