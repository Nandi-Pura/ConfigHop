import { useState } from 'react'
import { Search } from 'lucide-react'
import type { SwitchProject, SwitchPreview, SwitchStatement } from './api/switch'
import { previewSequentialMapping } from './switchBulkMapping'

const tabs = ['Interface Mapping', 'VLANs', 'LAG / Port-channels', 'STP', 'ACLs', 'Routes', 'Management', 'Other Features'] as const
type Tab = typeof tabs[number]
type Props = {
  project: SwitchProject | null
  preview: SwitchPreview | null
  assignments: Record<string, string | number>
  capability: string
  reverse: boolean
  onChoose: (name: string, target: string | number) => void
  onApply: (values: Record<string, string>) => void
  onClear: () => void
  onError: (message: string) => void
}

function featureTab(statement: SwitchStatement): Tab {
  const feature = statement.feature
  if (['interface', 'description', 'admin', 'mode', 'switching', 'access_vlan', 'native_vlan', 'allowed_vlans'].includes(feature)) return 'Interface Mapping'
  if (['vlan', 'name'].includes(feature)) return 'VLANs'
  if (['lag_member', 'lacp_mode'].includes(feature)) return 'LAG / Port-channels'
  if (feature.startsWith('stp') || feature === 'edge' || feature === 'bpdu_guard') return 'STP'
  if (feature.startsWith('acl')) return 'ACLs'
  if (feature === 'route') return 'Routes'
  if (['management_security', 'local_user_reentry', 'dhcp_client', 'dns', 'syslog', 'ntp', 'timezone', 'banner'].includes(feature)) return 'Management'
  return 'Other Features'
}

export default function SwitchReview({ project, preview, assignments, capability, reverse, onChoose, onApply, onClear, onError }: Props) {
  const [tab, setTab] = useState<Tab>('Interface Mapping')
  const [filter, setFilter] = useState<'All' | 'Mapped' | 'Unmapped'>('All')
  const [search, setSearch] = useState('')
  const [bulkStart, setBulkStart] = useState('')
  const [bulkFamily, setBulkFamily] = useState('GigabitEthernet')
  const [bulkFrom, setBulkFrom] = useState('')
  const [bulkTo, setBulkTo] = useState('')
  const [bulkPreview, setBulkPreview] = useState<Record<string, string> | null>(null)
  const declarations = project?.inventory.interfaces ?? []
  const physical = declarations.filter(item => item.kind === 'Physical')
  const visible = declarations.filter(item => (filter === 'All' || (filter === 'Mapped' ? !!assignments[item.name] : !assignments[item.name])) && item.name.toLowerCase().includes(search.toLowerCase()))
  const used = new Set(Object.values(assignments))
  const statements = (preview?.candidate.report ?? project?.inventory.statements ?? []).filter(s => featureTab(s) === tab)
  const dependencies = preview?.candidate.dependencies ?? []
  return <section className="section-card locked-mapping switch-review">
    <div className="live-heading"><strong>Translation Review &amp; Dependencies</strong><span className="muted">Backend-derived source dispositions</span></div>
    <div className="switch-feature-tabs" role="tablist" aria-label="Switch translation features">{tabs.map(name => <button key={name} role="tab" aria-selected={tab === name} className={`chip ${tab === name ? 'active' : ''}`} onClick={() => setTab(name)}>{name}</button>)}</div>
    {tab === 'Interface Mapping' ? <>
      <div className="mapping-toolbar"><div className="search-wrap"><Search size={14} /><input aria-label="Search switch interfaces" placeholder="Search interfaces..." value={search} onChange={event => setSearch(event.target.value)} /></div>{(['All', 'Mapped', 'Unmapped'] as const).map(name => <button key={name} className={`chip ${filter === name ? 'active' : ''}`} onClick={() => setFilter(name)}>{name}</button>)}<button className="btn secondary" onClick={() => { setBulkPreview(null); onClear() }}>Clear All</button></div>
      {reverse && <div className="switch-bulk"><label>Source range start<select aria-label="Source range start" value={bulkFrom} onChange={event => { setBulkFrom(event.target.value); setBulkPreview(null) }}><option value="">First source</option>{physical.map(item => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label><label>Source range end<select aria-label="Source range end" value={bulkTo} onChange={event => { setBulkTo(event.target.value); setBulkPreview(null) }}><option value="">Last source</option>{physical.map(item => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label><label>Interface family<select aria-label="Target interface family" value={bulkFamily} onChange={event => { setBulkFamily(event.target.value); setBulkPreview(null) }}>{['GigabitEthernet', 'TenGigabitEthernet', 'TwentyFiveGigE', 'FortyGigabitEthernet', 'HundredGigE'].map(family => <option key={family}>{family}</option>)}</select></label><label>Sequential target start <input aria-label="Sequential target start" placeholder="GigabitEthernet1/0/1" value={bulkStart} onChange={event => { setBulkStart(event.target.value); setBulkPreview(null) }} /></label><button className="btn secondary" onClick={() => { try { const first = bulkFrom ? physical.findIndex(item => item.name === bulkFrom) : 0; const last = bulkTo ? physical.findIndex(item => item.name === bulkTo) : physical.length - 1; if (first < 0 || last < first || !bulkStart.startsWith(bulkFamily)) throw new Error('Choose an ordered source range and matching target interface family.'); setBulkPreview(previewSequentialMapping(physical.slice(first, last + 1).map(item => item.name), bulkStart.trim(), assignments)); onError('') } catch (cause) { setBulkPreview(null); onError(cause instanceof Error ? cause.message : 'Invalid bulk mapping.') } }}>Preview Bulk Mapping</button>{bulkPreview && <div className="switch-bulk-preview"><strong>Review {Object.keys(bulkPreview).length} assignments before applying</strong><div>{Object.entries(bulkPreview).map(([name, target]) => <p key={name}>{name}{' -> '}{target}</p>)}</div><button className="btn accent" onClick={() => { onApply(bulkPreview); setBulkPreview(null) }}>Apply Mapping</button></div>}</div>}
      <div className="switch-map-table"><div className="switch-map-head"><span>Source Interface</span><span>Type</span><span>Target Interface</span><span>Status</span><span>Dependencies</span><span>Actions</span></div><div className="locked-interface-list">{visible.length ? visible.map(item => { const related = dependencies.filter(d => d.source === item.name || d.target === item.name); const issues = preview?.candidate.findings.filter(f => f.scope === item.name) ?? []; return <div className="switch-map-row" key={item.name}><span>{item.name}</span><span>{item.kind}</span>{item.kind !== 'Physical' ? <span className="muted">OS-derived</span> : capability ? <select aria-label={`Logical target slot for ${item.name}`} value={assignments[item.name] ?? ''} onChange={event => { setBulkPreview(null); onChoose(item.name, Number(event.target.value)) }}><option value="">Unmapped</option>{Array.from({ length: 48 }, (_, i) => i + 1).filter(slot => !used.has(slot) || assignments[item.name] === slot).map(slot => <option key={slot} value={slot}>Slot {slot}</option>)}</select> : <input aria-label={`Target interface for ${item.name}`} placeholder={reverse ? 'GigabitEthernet1/0/1' : '1/1/24'} value={String(assignments[item.name] ?? '')} onChange={event => { setBulkPreview(null); onChoose(item.name, event.target.value.trim()) }} />}<span>{issues.some(f => f.severity === 'BLOCKED') ? 'Blocked' : assignments[item.name] ? 'Mapped' : 'Unmapped'}</span><span title={related.map(d => `${d.relation}: ${d.target} ${d.resolved ? 'resolved' : 'unresolved'}`).join('; ')}>{related.filter(d => !d.resolved).length} unresolved</span><button className="btn secondary" disabled={!assignments[item.name]} onClick={() => { setBulkPreview(null); onChoose(item.name, '') }}>Clear</button></div> }) : <div className="live-empty">{project ? 'No matching interface declarations.' : 'Upload a configuration to inspect interfaces.'}</div>}</div></div>
      {capability && <div className="locked-slot-panel"><strong>JL663A target slots (48)</strong><small>Selected SKU inventory; verify actual device and cabling separately.</small><div className="locked-port-grid">{Array.from({ length: 48 }, (_, i) => { const slot = i + 1; const owner = Object.entries(assignments).find(([, value]) => value === slot)?.[0]; return <span key={slot} className={owner ? 'assigned' : ''} title={owner ? `${owner} to logical slot ${slot}` : `Logical slot ${slot} available`}>{slot}</span> })}</div></div>}
    </> : <div className="switch-feature-list">{statements.length ? statements.map((s, i) => <div key={`${s.line}-${i}`}><strong>Line {s.line}: {s.feature}</strong><span>{s.scope} / {s.status}</span><code>{s.source}</code></div>) : <p>No source declarations in this feature group.</p>}</div>}
  </section>
}
