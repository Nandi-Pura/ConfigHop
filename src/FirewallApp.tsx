import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import SwitchWorkspace, { type SwitchActions } from './SwitchWorkspace'
import VirtualCodeViewer from './VirtualCodeViewer'
import { api, ApiClientError, MAX_TEXT_PREVIEW_BYTES } from './api/client'
import type { CandidateMetadata, HardwareProfileDetail, HardwareProfileSummary, InterfaceMapping, InventoryView, MigrationPreview, ProjectState, PreviewStatus } from './api/types'
import { AlertTriangle, ArrowRight, Check, CircleAlert, CircleCheck, Clipboard, Download, FileText, FolderOpen, GitCompareArrows, HardDrive, Layers3, Network, Plus, PanelLeftClose, PanelLeftOpen, Pencil, RotateCcw, Save, Search, Settings2, ShieldCheck, Trash2, Upload } from 'lucide-react'

type MappingStatus = 'Mapped' | 'Review' | 'Unmapped' | 'Conflict'
type ResultTab = 'Overview' | 'Raw Comparison' | 'Semantic Changes' | 'Interface Mapping' | 'Migration Plan' | 'Candidate Configuration' | 'Findings'
type SavedProject = { project_id: string; project_name: string; source_filename: string | null; target_profile_id: string | null; mappings: InterfaceMapping[] }
const TABS: ResultTab[] = ['Overview', 'Raw Comparison', 'Semantic Changes', 'Interface Mapping', 'Migration Plan', 'Candidate Configuration', 'Findings']
const STORAGE = 'confighop-project'
const sizeLabel = (value: number | null) => value == null ? '' : value < 1024 * 1024 ? `${(value / 1024).toFixed(1)} KB` : `${(value / 1024 / 1024).toFixed(1)} MB`
const errorMessage = (error: unknown) => error instanceof ApiClientError ? error.message : 'The request could not be completed.'

export default function FirewallApp() {
  const [domain, setDomain] = useState<'Firewall' | 'Switch'>('Firewall')
  const [projectName, setProjectName] = useState('ConfigHop Firewall Project')
  const [switchProjectName, setSwitchProjectName] = useState('C9300-48P → CX 6300M 48G')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const switchActions = useRef<SwitchActions | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const uploadController = useRef<AbortController | null>(null)
  const candidateController = useRef<AbortController | null>(null)
  const serial = useRef(0)
  const projectRef = useRef<string | null>(null)
  const creating = useRef<Promise<string> | null>(null)
  const suppressPreview = useRef(false)
  const [projectId, setProjectId] = useState<string | null>(null)
  const [inventory, setInventory] = useState<InventoryView | null>(null)
  const [profiles, setProfiles] = useState<HardwareProfileSummary[]>([])
  const [profile, setProfile] = useState<HardwareProfileDetail | null>(null)
  const [sourceName, setSourceName] = useState('No configuration loaded')
  const [sourceBytes, setSourceBytes] = useState<number | null>(null)
  const [sourceText, setSourceText] = useState('')
  const [candidateBytes, setCandidateBytes] = useState<number | null>(null)
  const [candidateText, setCandidateText] = useState('')
  const [targets, setTargets] = useState<Record<string, string>>({})
  const [preview, setPreview] = useState<MigrationPreview | null>(null)
  const [candidate, setCandidate] = useState<CandidateMetadata | null>(null)
  const [statusText, setStatusText] = useState('No PAN-OS XML source loaded')
  const [errorText, setErrorText] = useState('')
  const [busy, setBusy] = useState(false)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<'All' | MappingStatus>('All')
  const [viewMode, setViewMode] = useState<'Table' | 'Hardware'>('Table')
  const [tab, setTab] = useState<ResultTab>('Overview')

  useEffect(() => {
    const controller = new AbortController()
    api.listProfiles(controller.signal).then(setProfiles).catch((error: unknown) => {
      if (!(error instanceof DOMException && error.name === 'AbortError')) setErrorText(errorMessage(error))
    })
    for (const key of [STORAGE, 'configmorph-project']) {
      const raw = localStorage.getItem(key)
      if (!raw) continue
      try {
        const saved = JSON.parse(raw) as Record<string, unknown>
        if ('sourceConfig' in saved || 'candidate' in saved) {
          if (key === STORAGE && typeof saved.project_id === 'string') {
            const safe: SavedProject = { project_id: saved.project_id, project_name: typeof saved.projectName === 'string' ? saved.projectName : 'ConfigHop Firewall Project', source_filename: typeof saved.fileName === 'string' ? saved.fileName : null, target_profile_id: null, mappings: [] }
            localStorage.setItem(STORAGE, JSON.stringify(safe))
          } else localStorage.removeItem(key)
        }
      } catch { localStorage.removeItem(key) }
    }
    return () => { controller.abort(); uploadController.current?.abort(); candidateController.current?.abort() }
  }, [])

  const mappings = useMemo<InterfaceMapping[]>(() => Object.entries(targets).filter(([, target]) => !!target).map(([source_interface, target_interface]) => ({ source_interface, target_interface })), [targets])
  const sourceLines = useMemo(() => sourceText ? sourceText.split('\n') : [], [sourceText])
  const candidateLines = useMemo(() => candidateText ? candidateText.split('\n') : [], [candidateText])
  const impacts = useMemo(() => new Map(preview?.impacts.map((item) => [item.source_interface, item]) ?? []), [preview])
  const rows = useMemo(() => inventory?.physical_interfaces.map((item, index) => {
    const impact = impacts.get(item.name)
    const status: MappingStatus = !targets[item.name] ? 'Unmapped' : impact?.mapping_status === 'CONFLICT' || impact?.mapping_status === 'UNSUPPORTED' ? 'Conflict' : impact?.mapping_status === 'REVIEW' ? 'Review' : 'Mapped'
    const refs = item.dependency_summary
    return { id: index + 1, source: item.name, type: item.mode, ip: item.ip_addresses.join(', ') || '—', zone: item.zone_names.join(', ') || '—', usedBy: `${refs.zone_references} zone, ${refs.virtual_router_references} VR, ${refs.static_route_references} route, ${refs.nat_references} NAT`, target: targets[item.name] || '', status, notes: item.aggregate_group ? `Aggregate: ${item.aggregate_group}` : `${item.subinterface_count} child interfaces` }
  }) ?? [], [inventory, impacts, targets])
  const counts = useMemo(() => rows.reduce<Record<MappingStatus, number>>((result, row) => { result[row.status]++; return result }, { Mapped: 0, Review: 0, Unmapped: 0, Conflict: 0 }), [rows])
  const visibleRows = useMemo(() => rows.filter((row) => (filter === 'All' || row.status === filter) && `${row.source} ${row.type} ${row.ip} ${row.zone} ${row.usedBy} ${row.target}`.toLowerCase().includes(search.toLowerCase())), [rows, filter, search])

  async function ensureProject(signal?: AbortSignal) {
    if (projectRef.current) return projectRef.current
    if (!creating.current) creating.current = api.createProject(signal).then((created) => { projectRef.current = created.project_id; setProjectId(created.project_id); return created.project_id }).finally(() => { creating.current = null })
    return creating.current
  }
  function invalidateResult() { setPreview(null); setCandidate(null); setCandidateText(''); setCandidateBytes(null) }
  function clearLocal() {
    serial.current++; uploadController.current?.abort(); candidateController.current?.abort()
    setInventory(null); setSourceName('No configuration loaded'); setSourceBytes(null); setSourceText('')
    setProfile(null); setTargets({}); invalidateResult(); setStatusText('No PAN-OS XML source loaded'); setErrorText(''); setTab('Overview')
    setBusy(false)
  }
  async function upload(file: File) {
    uploadController.current?.abort()
    const controller = new AbortController(); uploadController.current = controller
    const current = ++serial.current
    setBusy(true); setErrorText(''); setStatusText('Uploading and parsing…')
    try {
      const id = await ensureProject(controller.signal)
      const uploaded = await api.uploadSource(id, file, controller.signal)
      const nextInventory = await api.getInventory(id, controller.signal)
      const text = file.size <= MAX_TEXT_PREVIEW_BYTES ? await file.text() : ''
      if (current !== serial.current) return
      setInventory(nextInventory); setSourceName(uploaded.filename); setSourceBytes(uploaded.size_bytes)
      setSourceText(text)
      setTargets({}); invalidateResult()
      setStatusText(file.size <= MAX_TEXT_PREVIEW_BYTES ? 'Parsed successfully' : 'Parsed successfully; editor preview omitted because the file is large.')
    } catch (error) {
      if (current === serial.current && !(error instanceof DOMException && error.name === 'AbortError')) { setErrorText(errorMessage(error)); setStatusText('Parse failed') }
    } finally { if (current === serial.current) setBusy(false) }
  }
  async function pasteClipboard() {
    try { const text = await navigator.clipboard.readText(); if (text.trim()) await upload(new File([text], 'clipboard.xml', { type: 'application/xml' })) }
    catch { setErrorText('Clipboard access is unavailable. Upload a PAN-OS XML file instead.') }
  }
  async function selectProfile(id: string) {
    serial.current++; candidateController.current?.abort()
    const current = serial.current
    setBusy(false)
    invalidateResult(); setErrorText('')
    try { const project = await ensureProject(); await api.setProfile(project, id); const detail = id ? await api.getProfile(id) : null; if (current === serial.current) { setProfile(detail); setTargets({}) } }
    catch (error) { if (current === serial.current) setErrorText(errorMessage(error)) }
  }
  function changeTarget(source: string, target: string) { serial.current++; candidateController.current?.abort(); setBusy(false); setTargets((current) => ({ ...current, [source]: target })); invalidateResult(); setErrorText('') }
  useEffect(() => {
    if (suppressPreview.current) { suppressPreview.current = false; return }
    if (!projectId || !inventory || !profile) return
    const controller = new AbortController()
    const timer = window.setTimeout(() => api.preview(projectId, mappings, controller.signal).then(setPreview).catch((error: unknown) => {
      if (!(error instanceof DOMException && error.name === 'AbortError')) setErrorText(errorMessage(error))
    }), 350)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [projectId, inventory, profile, mappings])
  async function generate() {
    if (busy || !projectId || !inventory || !profile || !mappings.length) return
    const controller = new AbortController(); candidateController.current = controller
    const currentSerial = serial.current
    setBusy(true); setErrorText(''); setCandidate(null); setCandidateText(''); setCandidateBytes(null)
    try {
      const current = preview ?? await api.preview(projectId, mappings, controller.signal)
      if (currentSerial !== serial.current) return
      setPreview(current)
      if (current.status === 'BLOCKED') { setTab('Findings'); setErrorText('Preview is blocked. Review the findings.'); return }
      const allowReview = current.status === 'REVIEW_REQUIRED' && window.confirm('This mapping has findings requiring engineer review. Generate a candidate using the reviewed plan?')
      if (current.status === 'REVIEW_REQUIRED' && !allowReview) return
      const result = await api.candidate(projectId, mappings, allowReview, controller.signal)
      if (currentSerial !== serial.current) return
      setCandidate(result); setCandidateBytes(result.candidate_size_bytes); setTab(result.candidate_available ? 'Overview' : 'Findings')
      if (result.candidate_available && result.candidate_size_bytes != null && result.candidate_size_bytes <= MAX_TEXT_PREVIEW_BYTES) {
        const text = await (await api.downloadCandidate(projectId, controller.signal)).text()
        if (currentSerial === serial.current) setCandidateText(text)
      }
      if (!result.candidate_available) setErrorText('Candidate generation was blocked. Review the findings.')
    } catch (error) { if (currentSerial === serial.current && !(error instanceof DOMException && error.name === 'AbortError')) setErrorText(errorMessage(error)) }
    finally { if (currentSerial === serial.current) setBusy(false) }
  }
  async function download() {
    if (!projectId || !candidate?.candidate_available) return
    try { const blob = await api.downloadCandidate(projectId); const url = URL.createObjectURL(blob); const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'confighop-candidate.xml'; anchor.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000) }
    catch (error) { setErrorText(errorMessage(error)) }
  }
  async function newProject() {
    const old = projectRef.current; clearLocal(); projectRef.current = null; setProjectId(null)
    try { const id = await ensureProject(); if (old && old !== id) await api.deleteProject(old).catch(() => undefined) }
    catch (error) { setErrorText(errorMessage(error)) }
  }
  async function clearProject() {
    const old = projectRef.current; clearLocal(); projectRef.current = null; setProjectId(null); localStorage.removeItem(STORAGE)
    if (old) try { await api.deleteProject(old) } catch (error) { setErrorText(errorMessage(error)) }
  }
  function saveProject() {
    if (!projectId) { setErrorText('Create a project or upload a source before saving.'); return }
    const saved: SavedProject = { project_id: projectId, project_name: projectName, source_filename: inventory ? sourceName : null, target_profile_id: profile?.id ?? null, mappings }
    localStorage.setItem(STORAGE, JSON.stringify(saved)); setStatusText('Project reference saved in this browser.')
  }
  async function loadProject() {
    const raw = localStorage.getItem(STORAGE)
    if (!raw) { setErrorText('No saved project reference was found.'); return }
    try {
      const saved = JSON.parse(raw) as SavedProject
      if (!saved.project_id) throw new Error('Expired legacy project')
      const state: ProjectState = await api.getProject(saved.project_id)
      const restoredInventory = state.source_available ? await api.getInventory(state.project_id) : null
      const restoredProfile = state.target_profile_id ? await api.getProfile(state.target_profile_id) : null
      const restoredPreview = state.preview_available ? await api.getPreview(state.project_id) : null
      const restoredCandidate = state.candidate_available ? await api.getCandidate(state.project_id) : null
      const restoredSourceText = state.source_available && state.source_size_bytes != null && state.source_size_bytes <= MAX_TEXT_PREVIEW_BYTES ? await (await api.getSource(state.project_id)).text() : ''
      const restoredCandidateText = state.candidate_available && state.candidate_size_bytes != null && state.candidate_size_bytes <= MAX_TEXT_PREVIEW_BYTES ? await (await api.downloadCandidate(state.project_id)).text() : ''
      suppressPreview.current = true; projectRef.current = state.project_id; setProjectId(state.project_id)
      setProjectName(saved.project_name || 'ConfigHop Firewall Project'); setSourceName(state.source_filename || 'No configuration loaded'); setSourceBytes(state.source_size_bytes)
      setTargets(Object.fromEntries((saved.mappings || []).map((item) => [item.source_interface, item.target_interface])))
      setInventory(restoredInventory); setProfile(restoredProfile); setPreview(restoredPreview)
      setCandidate(restoredCandidate); setCandidateBytes(state.candidate_size_bytes)
      setSourceText(restoredSourceText); setCandidateText(restoredCandidateText)
      setStatusText(state.source_available ? 'Project session restored' : 'Project restored; upload a source configuration.'); setErrorText('')
    } catch (error) { setErrorText(error instanceof ApiClientError && error.code === 'PROJECT_NOT_FOUND' ? 'Backend project session expired. Re-upload the source configuration.' : errorMessage(error)) }
  }

  const ready: PreviewStatus | null = mappings.length ? preview?.status ?? null : null
  const canGenerate = !!inventory && !!profile && mappings.length > 0 && ready !== 'BLOCKED' && !busy
  return <div className={`app-shell ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
    <aside className="project-sidebar" aria-label="Project actions">
      <button className="sidebar-toggle" onClick={() => setSidebarCollapsed((value) => !value)} aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}>{sidebarCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}</button>
      <button className="sidebar-action new-project" onClick={domain === 'Switch' ? () => switchActions.current?.reset() : newProject}><Plus size={18} /><span>New Project</span></button>
      <button className="sidebar-action" onClick={domain === 'Switch' ? () => switchActions.current?.save() : saveProject}><Save size={17} /><span>Save Project</span></button>
      <button className="sidebar-action" onClick={domain === 'Switch' ? () => switchActions.current?.load() : loadProject}><FolderOpen size={17} /><span>Load Project</span></button>
      <button className="sidebar-action" onClick={domain === 'Switch' ? () => switchActions.current?.clear() : clearProject}><Trash2 size={17} /><span>Clear Project</span></button>
    </aside>
    <div className="app-content">
      <header className="app-header"><div className="brand-text"><strong>ConfigHop</strong><span>Network Configuration Migration</span></div><div className="header-divider" /><div className="project-name"><input value={domain === 'Switch' ? switchProjectName : projectName} onChange={(event) => domain === 'Switch' ? setSwitchProjectName(event.target.value) : setProjectName(event.target.value)} aria-label="Project name" /><Pencil size={13} /></div></header>
      {domain === 'Switch' ? <SwitchWorkspace onDomainChange={() => setDomain('Firewall')} actionsRef={switchActions} onTitleChange={setSwitchProjectName} /> :
        <main className="workspace">
          {errorText && <div className="api-error" role="alert"><CircleAlert size={15} />{errorText}</div>}
          <Section number="1" title="Migration Setup" subtitle="Select source and target platforms for this migration project"><div className="setup-grid">
            <div className="migration-type-card"><div className="small-label">Migration Type</div><span className="type-subtitle">Select the technology domain</span><label htmlFor="migration-domain">Domain</label><select id="migration-domain" value={domain} onChange={() => setDomain('Switch')}><option>Firewall</option><option>Switch</option></select></div>
            <PlatformCard title="Source Platform" eyebrow="Current Environment" model={inventory ? 'Model not identified' : 'No source loaded'} os={inventory ? `PAN-OS XML ${inventory.platform.config_version ?? ''}` : 'PAN-OS XML'} status={inventory ? 'Parsed PAN-OS' : 'Awaiting source'} />
            <div className="migration-arrow"><ArrowRight size={30} /></div>
            <PlatformCard title="Target Platform" eyebrow="Migration Destination" model={profile?.model ?? 'Select target profile'} os="PAN-OS candidate" status={profile ? 'Synthetic Profile' : 'Profile Not Available'} profiles={profiles} selected={profile?.id ?? ''} onSelect={selectProfile} />
          </div></Section>
          <div className="two-up source-row"><Section number="2" title="Source Configuration" subtitle="Upload or paste PAN-OS XML"><div className="source-config-grid"><div className="source-actions">
            <button className="btn accent-outline" onClick={() => fileRef.current?.click()} disabled={busy}><Upload size={15} /> Upload File</button><button className="btn secondary" onClick={pasteClipboard} disabled={busy}><Clipboard size={15} /> Paste from Clipboard</button>
            <input ref={fileRef} type="file" accept=".xml,text/xml,application/xml" hidden onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file); event.target.value = '' }} />
            <div className="file-card"><FileText size={20} /><div className="grow"><div className="file-name">{sourceName}</div><div className="file-meta">{sizeLabel(sourceBytes)} {statusText}</div></div></div>
          </div>{sourceText ? <VirtualCodeViewer lines={sourceLines} /> : <div className="viewer-placeholder">{inventory ? 'Configuration loaded; editor preview omitted because the file is large.' : 'No configuration loaded'}</div>}</div></Section>
          <Section number="3" title="Source Inventory" subtitle="Real parsed PAN-OS inventory"><div className="inventory-head"><span className={inventory ? 'success-pill' : 'muted'}>{inventory ? <CircleCheck size={14} /> : <CircleAlert size={14} />}{inventory ? 'Parsed successfully' : 'Awaiting source'}</span><span className="muted">{inventory ? `${inventory.summary.parser_warnings} parser warnings` : 'No inventory'}</span></div><div className="inventory-grid">
            <Metric icon={<Network size={18} />} value={inventory?.summary.physical_interfaces ?? 0} label="Physical Interfaces" /><Metric icon={<Network size={18} />} value={inventory?.summary.subinterfaces ?? 0} label="Subinterfaces" /><Metric icon={<Layers3 size={18} />} value={inventory?.summary.zones ?? 0} label="Zones" /><Metric icon={<HardDrive size={18} />} value={inventory?.summary.address_objects ?? 0} label="Address Objects" /><Metric icon={<Settings2 size={18} />} value={inventory?.summary.service_objects ?? 0} label="Services" /><Metric icon={<ShieldCheck size={18} />} value={inventory?.summary.security_rules ?? 0} label="Security Policies" /><Metric icon={<GitCompareArrows size={18} />} value={inventory?.summary.nat_rules ?? 0} label="NAT Rules" /><Metric icon={<Network size={18} />} value={inventory?.summary.static_routes ?? 0} label="Static Routes" />
          </div></Section></div>
          <Section number="4" title="Physical Interface Mapping" subtitle="Map physical source interfaces manually; child interfaces follow the parent mapping"><div className="mapping-toolbar"><div className="search-wrap"><Search size={15} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search interfaces..." /></div><div className="filter-group">{(['All', 'Mapped', 'Unmapped', 'Review', 'Conflict'] as const).map((item) => <button key={item} onClick={() => setFilter(item)} className={`chip ${filter === item ? 'active' : ''}`}>{item === 'Conflict' ? 'Conflicts' : item} ({item === 'All' ? rows.length : counts[item]})</button>)}</div><div className="toolbar-spacer" /><button className="btn accent-outline" disabled title="Automatic mapping is not available. Interface mapping is manual."><CircleCheck size={15} /> Auto Map Suggestions</button><button className="btn secondary" onClick={() => { setTargets({}); invalidateResult() }}><RotateCcw size={15} /> Clear All</button><div className="segmented"><button className={viewMode === 'Table' ? 'selected' : ''} onClick={() => setViewMode('Table')}>Table</button><button className={viewMode === 'Hardware' ? 'selected' : ''} onClick={() => setViewMode('Hardware')}>Hardware</button></div></div>
            {viewMode === 'Table' ? <div className="mapping-table-wrap"><table className="mapping-table"><thead><tr><th>#</th><th>Source Interface</th><th>Type</th><th>IP Address</th><th>Zone / Role</th><th>Used By</th><th>Suggested Target</th><th>Target Interface</th><th>Status</th><th>Confidence</th><th>Notes</th></tr></thead><tbody>{visibleRows.map((row) => <tr key={row.source}><td>{row.id}</td><td className="mono emphasis">{row.source}</td><td>{row.type}</td><td className="mono">{row.ip}</td><td>{row.zone}</td><td>{row.usedBy}</td><td>—</td><td><select className="table-select" value={row.target} disabled={!profile} onChange={(event) => changeTarget(row.source, event.target.value)}><option value="">None</option>{profile?.interfaces.map((name) => <option key={name} value={name}>{name}</option>)}</select></td><td><StatusBadge status={row.status} /></td><td>—</td><td>{row.notes}</td></tr>)}</tbody></table></div> : <HardwareMap rows={rows} target={profile?.model ?? 'No target profile'} />}
          </Section>
          <Section number="5" title="Migration Readiness" subtitle="Core v0.2 preview of submitted interface mappings"><div className="readiness-grid"><Readiness label="Source Platform" detail={inventory ? 'Parsed PAN-OS XML' : 'Upload source XML'} ok={!!inventory} /><Readiness label="Target Profile" detail={profile ? `${profile.model} (synthetic)` : 'Select a target profile'} ok={!!profile} /><Readiness label="Source Configuration" detail={inventory ? `${sizeLabel(sourceBytes)} loaded` : 'No source loaded'} ok={!!inventory} /><Readiness label="Interface Mapping" detail={`${mappings.length} submitted of ${rows.length} physical interfaces`} ok={mappings.length > 0} /><Readiness label="Preview" detail={mappings.length ? ready ?? 'Evaluating…' : 'Awaiting mapping'} ok={ready === 'READY'} warn={ready === 'REVIEW_REQUIRED'} /><div className={`readiness-summary ${ready === 'READY' ? 'good' : 'warn'}`}>{ready === 'READY' ? <CircleCheck size={19} /> : <AlertTriangle size={19} />}<div><strong>{ready ?? 'Action Required'}</strong><span>{ready === 'READY' ? 'Ready within modeled preview scope' : ready === 'REVIEW_REQUIRED' ? `${preview?.summary.review_findings ?? 0} review findings` : ready === 'BLOCKED' ? `${preview?.summary.blocking_findings ?? 0} blocking findings` : 'Select source, profile, and mapping'}</span></div></div><button className="generate-btn" onClick={generate} disabled={!canGenerate}>{busy ? 'Generating…' : 'Generate Migration'} <ArrowRight size={18} /></button></div>{!!preview?.findings.length && <div className="preview-findings">{preview.findings.map((finding, index) => <div key={`${finding.code}-${index}`}><strong>{finding.severity}: {finding.code}</strong><span>{finding.message}</span></div>)}</div>}</Section>
          <Section number="6" title="Migration Results" subtitle="Validated candidate and real migration analysis"><div className="results-tabs">{TABS.map((item) => <button key={item} onClick={() => setTab(item)} className={tab === item ? 'active' : ''}>{item}</button>)}</div>{candidate ? <Results tab={tab} candidate={candidate} preview={preview} inventory={inventory} sourceLines={sourceLines} candidateLines={candidateLines} sourceLoaded={!!sourceText} candidateLoaded={!!candidateText} candidateBytes={candidateBytes} onDownload={download} onCopy={() => navigator.clipboard.writeText(candidateText).catch(() => setErrorText('Clipboard access is unavailable.'))} onFindings={() => setTab('Findings')} /> : <div className="empty-results"><GitCompareArrows size={28} /><strong>No migration generated yet</strong><span>Upload PAN-OS XML, select a synthetic target profile, map physical interfaces, and generate a candidate.</span></div>}</Section>
        </main>}
    </div>
  </div>
}

function Section({ number, title, subtitle, children }: { number: string; title: string; subtitle?: string; children: ReactNode }) {
  return <section className="section-card"><div className="section-heading"><span className="section-number">{number}</span><strong>{title}</strong>{subtitle && <span>{subtitle}</span>}</div>{children}</section>
}

function PlatformCard({ title, eyebrow, model, os, status, profiles, selected, onSelect }: { title: string; eyebrow: string; model: string; os: string; status: string; profiles?: HardwareProfileSummary[]; selected?: string; onSelect?: (id: string) => void }) {
  return <div className="platform-card"><div className="platform-card-head"><div className="platform-title"><strong>{title}</strong><span>{eyebrow}</span></div><div className="compatibility"><span className={status === 'Parsed PAN-OS' || status === 'Synthetic Profile' ? 'success-pill' : 'muted'}><CircleCheck size={14} /> {status}</span><small>{status === 'Synthetic Profile' ? 'Development profile only; hardware compatibility is unverified.' : 'No production compatibility claim.'}</small></div></div><div className="platform-fields"><label className="field"><span>Vendor</span><div className="select-wrap"><select disabled value="Palo Alto Networks"><option>Palo Alto Networks</option></select></div><small>PAN-OS XML</small></label><label className="field"><span>{onSelect ? 'Target Hardware Profile' : 'Hardware Model'}</span><div className="select-wrap">{onSelect ? <select value={selected ?? ''} onChange={(event) => onSelect(event.target.value)}><option value="">Select target profile</option>{profiles?.map((profile) => <option key={profile.id} value={profile.id}>Synthetic Target FW (Development)</option>)}<option disabled>PA-5410 — profile not available</option></select> : <select disabled value={model}><option>{model}</option></select>}</div><small>{onSelect ? 'Synthetic test namespace only' : 'Not identified by current parser'}</small></label><label className="field"><span>OS / Format</span><div className="select-wrap"><select disabled value={os}><option>{os}</option></select></div><small>{onSelect ? 'Target release compatibility unverified' : 'Parsed source metadata'}</small></label></div></div>
}

function Metric({ icon, value, label }: { icon: ReactNode; value: number; label: string }) { return <div className="metric-tile"><div className="metric-icon">{icon}</div><div><strong>{value}</strong><span>{label}</span></div></div> }
function StatusBadge({ status }: { status: MappingStatus }) { return <span className={`status-badge ${status.toLowerCase()}`}>{status === 'Mapped' ? <Check size={11} /> : status === 'Unmapped' ? <span className="dot" /> : status === 'Review' ? <AlertTriangle size={11} /> : <CircleAlert size={11} />}{status}</span> }
function HardwareMap({ rows, target }: { rows: { source: string; target: string; zone: string; status: MappingStatus }[]; target: string }) { return <div className="hardware-map"><div className="hardware-panel"><div className="hardware-title">Parsed Source</div>{rows.map((row) => <div className="port-row" key={row.source}><span>{row.source}</span><small>{row.zone}</small></div>)}</div><div className="hardware-links">{rows.map((row) => <div key={row.source}>→</div>)}</div><div className="hardware-panel"><div className="hardware-title">{target}</div>{rows.map((row) => <div className="port-row target" key={row.source}><span>{row.target || 'Unmapped'}</span><small>{row.status}</small></div>)}</div></div> }
function Readiness({ label, detail, ok, warn }: { label: string; detail: string; ok: boolean; warn?: boolean }) { return <div className="readiness-item">{ok && !warn ? <CircleCheck className="ok-icon" size={22} /> : <AlertTriangle className="warn-icon" size={22} />}<div><strong>{label}</strong><span>{detail}</span></div></div> }

function Results({ tab, candidate, preview, inventory, sourceLines, candidateLines, sourceLoaded, candidateLoaded, candidateBytes, onDownload, onCopy, onFindings }: { tab: ResultTab; candidate: CandidateMetadata; preview: MigrationPreview | null; inventory: InventoryView | null; sourceLines: string[]; candidateLines: string[]; sourceLoaded: boolean; candidateLoaded: boolean; candidateBytes: number | null; onDownload: () => void; onCopy: () => void; onFindings: () => void }) {
  if (tab === 'Overview') {
    const summary = candidate.summary
    const references = summary.zone_reference_changes + summary.virtual_router_reference_changes + summary.static_route_reference_changes + summary.nat_reference_changes + summary.aggregate_membership_changes
    return <div className="results-overview"><div className="overview-card"><div className="donut"><div><strong>{candidate.status === 'REVIEW_REQUIRED' ? 'REVIEW' : candidate.status}</strong><span>PLAN</span></div></div><Stat value={summary.submitted_mappings} label="Mappings" /><Stat value={summary.derived_subinterface_mappings} label="Derived Children" /><Stat value={references} label="References" /><Stat value={summary.blocking_findings} label="Blocking" /></div><div className="summary-card"><h4>Configuration Summary</h4>{[['Preview Status', candidate.preview_status], ['Plan Status', candidate.plan_status], ['Candidate Parse', candidate.validation.candidate_parse_ok ? 'PASS' : 'FAIL'], ['Expected Inventory', candidate.validation.expected_inventory_match ? 'PASS' : 'FAIL'], ['Preservation Audit', candidate.validation.preservation_audit_ok ? 'PASS' : 'FAIL'], ['Operations Applied', `${candidate.validation.operations_applied}`], ['Review Findings', `${summary.review_findings}`], ['Blocking Findings', `${summary.blocking_findings}`]].map(([label, value]) => <div className="summary-row" key={label}><span>{label}</span><b>{value}</b></div>)}</div><div className="findings-card"><h4>Findings Summary</h4><div className="finding-grid"><MiniFinding value={summary.review_findings + summary.blocking_findings + candidate.findings.length} label="Total" /><MiniFinding value={summary.blocking_findings} label="Blocking" danger /><MiniFinding value={summary.review_findings} label="Review" warn /><MiniFinding value={candidate.findings.length} label="Renderer" info /></div><button className="btn secondary wide" onClick={onFindings}>View Findings <ArrowRight size={14} /></button></div></div>
  }
  if (tab === 'Raw Comparison') return <RawComparison candidate={candidate} sourceLines={sourceLines} candidateLines={candidateLines} sourceLoaded={sourceLoaded} candidateLoaded={candidateLoaded} />
  if (tab === 'Semantic Changes') return <SimpleTable headings={['Category', 'Object', 'Scope', 'Source', 'Target', 'Status']} rows={candidate.semantic_diff.changes.map((change) => [change.category, `${change.object_type}: ${change.object_name}`, change.scope, change.old_value, change.new_value, change.status])} />
  if (tab === 'Interface Mapping') return <SimpleTable headings={['Source', 'Target', 'Derived Children', 'Reference Changes', 'Result']} rows={preview?.impacts.map((impact) => [impact.source_interface, impact.target_interface, `${impact.derived_subinterfaces.length}`, `${impact.reference_changes.length}`, impact.mapping_status]) ?? []} />
  if (tab === 'Migration Plan') return <SimpleTable headings={['#', 'Operation', 'Object', 'Scope', 'Source', 'Target']} rows={candidate.plan.operations.map((operation) => [`${operation.sequence}`, operation.operation_type, `${operation.object_type}: ${operation.object_name}`, operation.scope, operation.source_value, operation.target_value])} />
  if (tab === 'Candidate Configuration') return <div><div className="candidate-toolbar"><span><FileText size={14} /> confighop-candidate.xml {sizeLabel(candidateBytes)}</span><div><button className="btn secondary" disabled={!candidateLoaded} onClick={onCopy}><Clipboard size={14} /> Copy All</button><button className="btn secondary" disabled={!candidate.candidate_available} onClick={onDownload}><Download size={14} /> Download</button></div></div>{candidateLoaded ? <VirtualCodeViewer lines={candidateLines} height={350} /> : <div className="viewer-placeholder">{candidate.candidate_available ? 'Candidate generated successfully. Preview omitted because the file is large.' : 'No validated candidate is available.'}</div>}</div>
  const findings = [...(inventory?.parser_warnings.map((warning) => ['Parser', 'WARNING', warning.code, warning.message, warning.object_name || warning.object_type]) ?? []), ...(preview?.findings.map((finding) => ['Preview', finding.severity, finding.code, finding.message, finding.object_name || finding.source_interface || '—']) ?? []), ...candidate.findings.map((finding) => ['Renderer', finding.severity, finding.code, finding.message, '—'])]
  return <SimpleTable headings={['Source', 'Severity', 'Code', 'Description', 'Object']} rows={findings} />
}

function Stat({ value, label }: { value: number; label: string }) { return <div className="stat"><strong>{value}</strong><span>{label}</span></div> }
function MiniFinding({ value, label, danger, warn, info }: { value: number; label: string; danger?: boolean; warn?: boolean; info?: boolean }) { return <div className={`mini-finding ${danger ? 'danger' : ''} ${warn ? 'warn' : ''} ${info ? 'info' : ''}`}><strong>{value}</strong><span>{label}</span></div> }
function SimpleTable({ headings, rows }: { headings: string[]; rows: string[][] }) { return <div className="simple-table"><table><thead><tr>{headings.map((heading) => <th key={heading}>{heading}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>)}</tbody></table>{!rows.length && <div className="viewer-placeholder">No records available.</div>}</div> }

function RawComparison({ candidate, sourceLines, candidateLines, sourceLoaded, candidateLoaded }: { candidate: CandidateMetadata; sourceLines: string[]; candidateLines: string[]; sourceLoaded: boolean; candidateLoaded: boolean }) {
  const [top, setTop] = useState(0)
  const [expanded, setExpanded] = useState(false)
  const [query, setQuery] = useState('')
  const references = candidate.summary.zone_reference_changes + candidate.summary.virtual_router_reference_changes + candidate.summary.static_route_reference_changes + candidate.summary.nat_reference_changes
  function search() { const index = sourceLines.findIndex((line) => line.toLowerCase().includes(query.toLowerCase())); if (query && index >= 0) setTop(index * 16) }
  return <div className="raw-wrap"><div className="raw-toolbar"><span className="small-label">View</span><button className="chip active">Side by Side</button><button className="chip" disabled title="Raw changed-line filtering is not available in v0.4. Use Semantic Changes.">Changed Only</button><div className="search-wrap narrow"><Search size={14} /><input placeholder="Search in configuration..." value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') search() }} /></div><button className="btn secondary" onClick={() => setExpanded((value) => !value)}>{expanded ? 'Collapse' : 'Expanded'}</button></div><div className={`diff-grid ${expanded ? 'expanded' : ''}`}><div className="diff-panel"><div className="diff-title">Source Configuration</div>{sourceLoaded ? <VirtualCodeViewer lines={sourceLines} height={expanded ? 520 : 270} scrollTop={top} onScrollTop={setTop} /> : <div className="viewer-placeholder">Source preview omitted because the file is large.</div>}</div><div className="diff-panel"><div className="diff-title">Candidate Configuration</div>{candidateLoaded ? <VirtualCodeViewer lines={candidateLines} height={expanded ? 520 : 270} scrollTop={top} onScrollTop={setTop} /> : <div className="viewer-placeholder">Candidate preview omitted because the file is large.</div>}</div><div className="diff-summary"><h4>Transformation Summary</h4><div className="donut small"><div><strong>{candidate.status === 'REVIEW_REQUIRED' ? 'REVIEW' : candidate.status}</strong><span>PLAN</span></div></div><div className="summary-row"><span>Mappings</span><b>{candidate.summary.valid_mappings}</b></div><div className="summary-row"><span>Derived Children</span><b>{candidate.summary.derived_subinterface_mappings}</b></div><div className="summary-row"><span>References</span><b>{references}</b></div></div></div></div>
}
