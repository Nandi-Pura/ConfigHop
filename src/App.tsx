import { useMemo, useRef, useState, type ReactNode } from 'react'
import SwitchWorkspace, { type SwitchActions } from './SwitchWorkspace'
import {
  AlertTriangle,
  ArrowRight,
  Check,
  ChevronDown,
  CircleAlert,
  CircleCheck,
  Clipboard,
  Code2,
  Download,
  FileText,
  FolderOpen,
  GitCompareArrows,
  HardDrive,
  Layers3,
  Network,
  Plus,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  RotateCcw,
  Save,
  Search,
  Settings2,
  ShieldCheck,
  Trash2,
  Upload,
  X,
} from 'lucide-react'

type MappingStatus = 'Mapped' | 'Review' | 'Unmapped' | 'Conflict'
type Confidence = 'High' | 'Medium' | 'Low' | '-'

type MappingRow = {
  id: number
  source: string
  type: string
  ip: string
  zone: string
  usedBy: string
  suggested: string
  target: string
  status: MappingStatus
  confidence: Confidence
  notes: string
}

type ResultTab =
  | 'Overview'
  | 'Raw Comparison'
  | 'Semantic Changes'
  | 'Interface Mapping'
  | 'Migration Plan'
  | 'Candidate Configuration'
  | 'Findings'

const defaultConfig = `set deviceconfig system hostname PA-3410
set deviceconfig system domain corp.local
set deviceconfig system timezone Asia/Jakarta
set network interface ethernet ethernet1/1 layer3
set network interface ethernet ethernet1/1 ip 203.0.113.2/30
set network interface ethernet ethernet1/1 description WAN-Uplink
set network interface ethernet ethernet1/1 manage-profile ping
set network interface ethernet ethernet1/1.100 layer3
set network interface ethernet ethernet1/1.100 tag 100
set network interface ethernet ethernet1/1.100 ip 10.100.0.1/24
set network interface ethernet ethernet1/2 layer3
set network interface ethernet ethernet1/2 ip 10.10.10.1/24
set network interface ethernet ethernet1/3 layer3
set network interface ethernet ethernet1/3 ip 172.16.10.1/24
set network interface ethernet ethernet1/4 layer3
set network interface ethernet ethernet1/4 ip 10.20.0.1/24
set network zone untrust network layer3 ethernet1/1
set network zone trust network layer3 ethernet1/2
set network zone dmz network layer3 ethernet1/3
set network virtual-router default interface ethernet1/1
set network virtual-router default interface ethernet1/2
set network virtual-router default interface ethernet1/3
set address HQ-NET ip-netmask 10.0.0.0/8
set rulebase security rules Allow-Web from trust
set rulebase security rules Allow-Web to untrust
set rulebase security rules Allow-Web source any
set rulebase security rules Allow-Web destination any
set rulebase security rules Allow-Web application web-browsing
set rulebase security rules Allow-Web service application-default
set rulebase security rules Allow-Web action allow`

const mappingsSeed: MappingRow[] = [
  { id: 1, source: 'ethernet1/1', type: 'Physical', ip: '203.0.113.2/30', zone: 'untrust / WAN', usedBy: '12 policies, 4 NAT, 1 route', suggested: 'ethernet1/5', target: 'ethernet1/5', status: 'Mapped', confidence: 'High', notes: 'Internet uplink' },
  { id: 2, source: 'ethernet1/2', type: 'Physical', ip: '10.10.10.1/24', zone: 'trust / LAN', usedBy: '22 policies, 2 NAT', suggested: 'ethernet1/6', target: 'ethernet1/6', status: 'Mapped', confidence: 'High', notes: 'User LAN' },
  { id: 3, source: 'ethernet1/3', type: 'Physical', ip: '172.16.10.1/24', zone: 'dmz / DMZ', usedBy: '7 policies, 1 NAT', suggested: 'ethernet1/7', target: 'ethernet1/7', status: 'Mapped', confidence: 'High', notes: 'DMZ network' },
  { id: 4, source: 'ethernet1/4', type: 'Physical', ip: '10.20.0.1/24', zone: 'server / Servers', usedBy: '5 policies, 1 route', suggested: 'ethernet1/8', target: 'ethernet1/8', status: 'Review', confidence: 'Medium', notes: 'Check dependent rules' },
  { id: 5, source: 'ae1', type: 'Aggregate', ip: '10.30.0.1/24', zone: 'trust / Core', usedBy: '6 policies, 1 route', suggested: 'ae1', target: 'ae1', status: 'Mapped', confidence: 'High', notes: 'Aggregate link to core' },
  { id: 6, source: 'ethernet1/5.100', type: 'Subinterface', ip: '192.168.100.1/24', zone: 'trust / VLAN100', usedBy: '3 policies', suggested: 'ethernet1/9.100', target: 'ethernet1/9.100', status: 'Mapped', confidence: 'High', notes: 'VLAN 100 - Guest' },
]

const targetOptions = ['None', 'ethernet1/5', 'ethernet1/6', 'ethernet1/7', 'ethernet1/8', 'ethernet1/9', 'ethernet1/9.100', 'ae1']

type Platform = {
  vendor: string
  hardware: { model: string; series: string }
  software: { product: string; version: string; train: string }
}

const platforms: Platform[] = [
  { vendor: 'Palo Alto Networks', hardware: { model: 'PA-3410', series: 'PA-3400 Series' }, software: { product: 'PAN-OS', version: '11.1', train: '11.x' } },
  { vendor: 'Palo Alto Networks', hardware: { model: 'PA-3420', series: 'PA-3400 Series' }, software: { product: 'PAN-OS', version: '11.1', train: '11.x' } },
  { vendor: 'Palo Alto Networks', hardware: { model: 'PA-5410', series: 'PA-5400 Series' }, software: { product: 'PAN-OS', version: '11.1', train: '11.x' } },
  { vendor: 'Palo Alto Networks', hardware: { model: 'PA-5440', series: 'PA-5400 Series' }, software: { product: 'PAN-OS', version: '11.1', train: '11.x' } },
  { vendor: 'Cisco', hardware: { model: 'FPR-3110', series: 'Secure Firewall 3100 Series' }, software: { product: 'FTD', version: '7.4.2', train: '7.4' } },
  { vendor: 'Fortinet', hardware: { model: 'FortiGate 200F', series: 'FortiGate 200F Series' }, software: { product: 'FortiOS', version: '7.4.5', train: '7.4' } },
]

const osLabel = (platform: Platform) => `${platform.software.product} ${platform.software.version}`

const sourceDiff = [
  'set network zone trust network layer3 ethernet1/2',
  'set network zone dmz network layer3 ethernet1/3',
  'set rulebase security rules Allow-Web from trust',
  'set rulebase security rules Allow-Web to untrust',
  'set rulebase security rules Allow-Web source any',
  'set rulebase security rules Allow-Web destination any',
  'set rulebase security rules Allow-Web application web-browsing',
  'set rulebase security rules Allow-Web service application-default',
]

const targetDiff = [
  'set network zone trust network layer3 ethernet1/6',
  'set network zone dmz network layer3 ethernet1/7',
  'set rulebase security rules Allow-Web from trust',
  'set rulebase security rules Allow-Web to untrust',
  'set rulebase security rules Allow-Web source any',
  'set rulebase security rules Allow-Web destination any',
  'set rulebase security rules Allow-Web application web-browsing',
  'set rulebase security rules Allow-Web service application-default',
]

const candidate = `set deviceconfig system hostname PA-5410
set network interface ethernet ethernet1/5 layer3
set network interface ethernet ethernet1/5 ip 203.0.113.2/30
set network interface ethernet ethernet1/5 description WAN-Uplink
set network interface ethernet ethernet1/6 layer3
set network interface ethernet ethernet1/6 ip 10.10.10.1/24
set network interface ethernet ethernet1/7 layer3
set network interface ethernet ethernet1/7 ip 172.16.10.1/24
set network interface ethernet ethernet1/8 layer3
set network interface ethernet ethernet1/8 ip 10.20.0.1/24
set network zone untrust network layer3 ethernet1/5
set network zone trust network layer3 ethernet1/6
set network zone dmz network layer3 ethernet1/7
set network virtual-router default interface ethernet1/5
set network virtual-router default interface ethernet1/6
set network virtual-router default interface ethernet1/7`

function App() {
  const [sourceVendor, setSourceVendor] = useState('Palo Alto Networks')
  const [sourceHardware, setSourceHardware] = useState('PA-3410')
  const [sourceOs, setSourceOs] = useState('PAN-OS 11.1')
  const [targetVendor, setTargetVendor] = useState('Palo Alto Networks')
  const [targetHardware, setTargetHardware] = useState('PA-5410')
  const [targetOs, setTargetOs] = useState('PAN-OS 11.1')
  const [sourceConfig, setSourceConfig] = useState(defaultConfig)
  const [fileName, setFileName] = useState('pa-3410-config.txt')
  const [fileSize, setFileSize] = useState('2.4 MB')
  const [mappings, setMappings] = useState(mappingsSeed)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<'All' | MappingStatus>('All')
  const [viewMode, setViewMode] = useState<'Table' | 'Hardware'>('Table')
  const [activeTab, setActiveTab] = useState<ResultTab>('Overview')
  const [generated, setGenerated] = useState(true)
  const [projectName, setProjectName] = useState('PA-3410 → PA-5410')
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [domain, setDomain] = useState<'Firewall' | 'Switch'>('Firewall')
  const [switchProjectName, setSwitchProjectName] = useState('C9300-48P → CX 6300M 48G')
  const switchActionsRef = useRef<SwitchActions | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const counts = useMemo(() => {
    const result: Record<MappingStatus, number> = { Mapped: 0, Review: 0, Unmapped: 0, Conflict: 0 }
    mappings.forEach((m) => result[m.status]++)
    return result
  }, [mappings])

  const filteredMappings = useMemo(() => {
    return mappings.filter((row) => {
      const matchesFilter = filter === 'All' || row.status === filter
      const haystack = `${row.source} ${row.type} ${row.ip} ${row.zone} ${row.usedBy} ${row.target} ${row.notes}`.toLowerCase()
      return matchesFilter && haystack.includes(search.toLowerCase())
    })
  }, [mappings, search, filter])

  const ready = counts.Conflict === 0 && counts.Unmapped === 0

  const handleMapping = (id: number, target: string) => {
    setMappings((rows) => rows.map((row) => {
      if (row.id !== id) return row
      if (target === 'None') return { ...row, target, status: 'Unmapped', confidence: '-' }
      return { ...row, target, status: target === row.suggested ? 'Mapped' : 'Review', confidence: target === row.suggested ? 'High' : 'Medium' }
    }))
  }

  const autoMap = () => setMappings((rows) => rows.map((row) => ({ ...row, target: row.suggested, status: 'Mapped', confidence: 'High' })))
  const clearMappings = () => setMappings((rows) => rows.map((row) => ({ ...row, target: 'None', status: 'Unmapped', confidence: '-' })))

  const handleFile = async (file?: File) => {
    if (!file) return
    const text = await file.text()
    setSourceConfig(text || defaultConfig)
    setFileName(file.name)
    setFileSize(`${Math.max(file.size / 1024, 1).toFixed(1)} KB`)
  }

  const pasteClipboard = async () => {
    try {
      const text = await navigator.clipboard.readText()
      if (text.trim()) {
        setSourceConfig(text)
        setFileName('clipboard-config.txt')
        setFileSize(`${Math.max(text.length / 1024, 1).toFixed(1)} KB`)
      }
    } catch {
      alert('Clipboard access is not available in this browser context.')
    }
  }

  const saveProject = () => {
    const platformData = (vendor: string, hardware: string, os: string) => {
      const match = platforms.find((platform) => platform.vendor === vendor && platform.hardware.model === hardware && osLabel(platform) === os)
      return match ?? platforms.find((platform) => platform.vendor === vendor && platform.hardware.model === hardware)
    }
    localStorage.setItem('configmorph-project', JSON.stringify({ sourcePlatform: platformData(sourceVendor, sourceHardware, sourceOs), targetPlatform: platformData(targetVendor, targetHardware, targetOs), sourceConfig, fileName, fileSize, mappings, projectName }))
  }

  const loadProject = () => {
    const raw = localStorage.getItem('configmorph-project')
    if (!raw) return alert('No saved project found.')
    const p = JSON.parse(raw)
    setSourceVendor(p.sourcePlatform?.vendor ?? p.sourceVendor)
    setSourceHardware(p.sourcePlatform?.hardware.model ?? p.sourceHardware)
    setSourceOs(p.sourcePlatform ? osLabel(p.sourcePlatform) : p.sourceOs)
    setTargetVendor(p.targetPlatform?.vendor ?? p.targetVendor)
    setTargetHardware(p.targetPlatform?.hardware.model ?? p.targetHardware)
    setTargetOs(p.targetPlatform ? osLabel(p.targetPlatform) : p.targetOs)
    setSourceConfig(p.sourceConfig)
    setFileName(p.fileName)
    setFileSize(p.fileSize)
    setMappings(p.mappings)
    setProjectName(p.projectName)
  }

  const clearProject = () => {
    setSourceConfig('')
    setFileName('No configuration loaded')
    setFileSize('')
    setGenerated(false)
  }

  const resetProject = () => {
    setSourceVendor('Palo Alto Networks')
    setSourceHardware('PA-3410')
    setSourceOs('PAN-OS 11.1')
    setTargetVendor('Palo Alto Networks')
    setTargetHardware('PA-5410')
    setTargetOs('PAN-OS 11.1')
    setSourceConfig(defaultConfig)
    setFileName('pa-3410-config.txt')
    setFileSize('2.4 MB')
    setMappings(mappingsSeed)
    setGenerated(false)
    setActiveTab('Overview')
  }

  return (
    <div className={`app-shell ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <aside className="project-sidebar" aria-label="Project actions">
        <button className="sidebar-toggle" onClick={() => setSidebarCollapsed((value) => !value)} aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'} title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}>{sidebarCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}</button>
        <button className="sidebar-action new-project" onClick={domain === 'Switch' ? () => switchActionsRef.current?.reset() : resetProject} title="New Project"><Plus size={18} /><span>New Project</span></button>
        <button className="sidebar-action" onClick={domain === 'Switch' ? () => switchActionsRef.current?.save() : saveProject} title="Save Project"><Save size={17} /><span>Save Project</span></button>
        <button className="sidebar-action" onClick={domain === 'Switch' ? () => switchActionsRef.current?.load() : loadProject} title="Load Project"><FolderOpen size={17} /><span>Load Project</span></button>
        <button className="sidebar-action" onClick={domain === 'Switch' ? () => switchActionsRef.current?.clear() : clearProject} title="Clear Project"><Trash2 size={17} /><span>Clear Project</span></button>
      </aside>
      <div className="app-content">
      <Header projectName={domain === 'Switch' ? switchProjectName : projectName} setProjectName={domain === 'Switch' ? setSwitchProjectName : setProjectName} />

      {domain === 'Switch' ? <SwitchWorkspace onDomainChange={() => setDomain('Firewall')} actionsRef={switchActionsRef} onTitleChange={setSwitchProjectName} /> :

      <main className="workspace">

        <Section number="1" title="Migration Setup" subtitle="Select source and target platforms for this migration project">
          <div className="setup-grid">
            <div className="migration-type-card">
              <div className="small-label">Migration Type</div>
              <span className="type-subtitle">Select the technology domain</span>
              <label htmlFor="migration-domain">Domain</label>
              <select id="migration-domain" value={domain} onChange={() => setDomain('Switch')}><option>Firewall</option><option>Switch</option></select>
            </div>
            <PlatformCard title="Source Platform" eyebrow="Current Environment" vendor={sourceVendor} setVendor={setSourceVendor} hardware={sourceHardware} setHardware={setSourceHardware} os={sourceOs} setOs={setSourceOs} />
            <div className="migration-arrow"><ArrowRight size={30} /></div>
            <PlatformCard title="Target Platform" eyebrow="Migration Destination" vendor={targetVendor} setVendor={setTargetVendor} hardware={targetHardware} setHardware={setTargetHardware} os={targetOs} setOs={setTargetOs} />
          </div>
        </Section>

        <div className="two-up source-row">
          <Section number="2" title="Source Configuration" subtitle="Upload or paste your source configuration">
            <div className="source-config-grid">
              <div className="source-actions">
                <button className="btn accent-outline" onClick={() => fileRef.current?.click()}><Upload size={15} /> Upload File</button>
                <button className="btn secondary" onClick={pasteClipboard}><Clipboard size={15} /> Paste from Clipboard</button>
                <input ref={fileRef} type="file" accept=".txt,.conf,.cfg" hidden onChange={(e) => handleFile(e.target.files?.[0])} />
                <div className="file-card">
                  <FileText size={20} />
                  <div className="grow">
                    <div className="file-name">{fileName}</div>
                    <div className="file-meta">{fileSize} {sourceConfig && <><span>•</span> <span className="success-text">Uploaded successfully</span></>}</div>
                  </div>
                  <X size={15} className="muted-icon" />
                </div>
              </div>
              <CodeViewer text={sourceConfig || '# No configuration loaded'} />
            </div>
          </Section>

          <Section number="3" title="Source Inventory" subtitle="Configuration analyzed successfully">
            <div className="inventory-head">
              <span className="success-pill"><CircleCheck size={14} /> Parsed successfully</span>
              <span className="muted">Today, 14:23:11</span>
            </div>
            <div className="inventory-grid">
              <Metric icon={<Network size={18} />} value="16" label="Interfaces" />
              <Metric icon={<Layers3 size={18} />} value="8" label="Zones" />
              <Metric icon={<HardDrive size={18} />} value="64" label="Address Objects" />
              <Metric icon={<Settings2 size={18} />} value="14" label="Services" />
              <Metric icon={<ShieldCheck size={18} />} value="22" label="Security Policies" />
              <Metric icon={<GitCompareArrows size={18} />} value="7" label="NAT Rules" />
              <Metric icon={<Network size={18} />} value="3" label="Virtual Routers" />
              <Metric icon={<ShieldCheck size={18} />} value="2" label="VPN Tunnels" />
            </div>
          </Section>
        </div>

        <Section number="4" title="Physical Interface Mapping" subtitle="Map source hardware interfaces to target hardware interfaces. Logical configuration will follow the mapping.">
          <div className="mapping-toolbar">
            <div className="search-wrap"><Search size={15} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search interfaces..." /></div>
            <div className="filter-group">
              {(['All', 'Mapped', 'Unmapped', 'Review', 'Conflict'] as const).map((item) => {
                const count = item === 'All' ? mappings.length : counts[item]
                return <button key={item} onClick={() => setFilter(item)} className={`chip ${filter === item ? 'active' : ''}`}>{item === 'Conflict' ? 'Conflicts' : item} ({count})</button>
              })}
            </div>
            <div className="toolbar-spacer" />
            <button className="btn accent-outline" onClick={autoMap}><CircleCheck size={15} /> Auto Map Suggestions</button>
            <button className="btn secondary" onClick={clearMappings}><RotateCcw size={15} /> Clear All</button>
            <div className="segmented">
              <button className={viewMode === 'Table' ? 'selected' : ''} onClick={() => setViewMode('Table')}>Table</button>
              <button className={viewMode === 'Hardware' ? 'selected' : ''} onClick={() => setViewMode('Hardware')}>Hardware</button>
            </div>
          </div>

          {viewMode === 'Table' ? (
            <div className="mapping-table-wrap">
              <table className="mapping-table">
                <thead><tr><th>#</th><th>Source Interface</th><th>Type</th><th>IP Address</th><th>Zone / Role</th><th>Used By</th><th>Suggested Target</th><th>Target Interface</th><th>Status</th><th>Confidence</th><th>Notes</th></tr></thead>
                <tbody>
                  {filteredMappings.map((row) => <MappingRowView key={row.id} row={row} onChange={handleMapping} />)}
                </tbody>
              </table>
            </div>
          ) : <HardwareMap mappings={mappings} />}
        </Section>

        <Section number="5" title="Migration Readiness" subtitle="Validate migration prerequisites before generating the target configuration">
          <div className="readiness-grid">
            <ReadinessItem label="Source Platform" detail={`${sourceVendor} ${sourceHardware}`} ok />
            <ReadinessItem label="Target Platform" detail={`${targetVendor} ${targetHardware}`} ok />
            <ReadinessItem label="Source Configuration" detail={`${sourceConfig.split('\n').filter(Boolean).length} lines loaded`} ok={!!sourceConfig} />
            <ReadinessItem label="Interface Mapping" detail={`${mappings.length - counts.Unmapped} / ${mappings.length} mapped`} ok={counts.Unmapped === 0} warn={counts.Review > 0} />
            <ReadinessItem label="Conflict Check" detail={`${counts.Conflict} conflicts detected`} ok={counts.Conflict === 0} />
            <div className={`readiness-summary ${ready ? 'good' : 'warn'}`}>
              {ready ? <CircleCheck size={19} /> : <AlertTriangle size={19} />}
              <div><strong>{ready ? (counts.Review ? 'Review Required' : 'Ready to Generate') : 'Action Required'}</strong><span>{ready ? (counts.Review ? `${counts.Review} mapping requires attention` : 'All checks passed') : 'Resolve unmapped interfaces or conflicts'}</span></div>
            </div>
            <button className="generate-btn" onClick={() => { setGenerated(true); setActiveTab('Overview') }}>Generate Migration <ArrowRight size={18} /></button>
          </div>
        </Section>

        <Section number="6" title="Migration Results" subtitle="Review migration analysis and generated configuration">
          <div className="results-tabs">
            {(['Overview', 'Raw Comparison', 'Semantic Changes', 'Interface Mapping', 'Migration Plan', 'Candidate Configuration', 'Findings'] as ResultTab[]).map((tab) => (
              <button key={tab} onClick={() => setActiveTab(tab)} className={activeTab === tab ? 'active' : ''}>{tab}</button>
            ))}
          </div>
          {!generated ? <EmptyResults /> : <ResultsContent tab={activeTab} mappings={mappings} />}
        </Section>
      </main>
      }
      </div>
    </div>
  )
}

function Header({ projectName, setProjectName }: { projectName: string, setProjectName: (s: string) => void }) {
  return <header className="app-header">
    <div className="brand-mark">CM</div>
    <div className="brand-text"><strong>ConfigMorph</strong><span>Network Configuration Migration</span></div>
    <div className="header-divider" />
    <div className="project-name"><input value={projectName} onChange={(e) => setProjectName(e.target.value)} aria-label="Project name" /><Pencil size={13} aria-hidden="true" /></div>
  </header>
}

function Section({ number, title, subtitle, children }: { number: string, title: string, subtitle?: string, children: ReactNode }) {
  return <section className="section-card">
    <div className="section-heading"><span className="section-number">{number}</span><strong>{title}</strong>{subtitle && <span>{subtitle}</span>}</div>
    {children}
  </section>
}

function PlatformCard({ title, eyebrow, vendor, setVendor, hardware, setHardware, os, setOs }: { title: string; eyebrow: string; vendor: string; setVendor: (value: string) => void; hardware: string; setHardware: (value: string) => void; os: string; setOs: (value: string) => void }) {
  const vendorPlatforms = platforms.filter((platform) => platform.vendor === vendor)
  const selected = vendorPlatforms.find((platform) => platform.hardware.model === hardware) ?? vendorPlatforms[0]
  const osOptions = [...new Set(vendorPlatforms.map(osLabel))]
  const selectedOs = vendorPlatforms.find((platform) => osLabel(platform) === os)?.software ?? selected?.software
  const changeVendor = (value: string) => {
    const first = platforms.find((platform) => platform.vendor === value)!
    setVendor(value)
    setHardware(first.hardware.model)
    setOs(osLabel(first))
  }
  const changeHardware = (value: string) => {
    const next = vendorPlatforms.find((platform) => platform.hardware.model === value)!
    setHardware(value)
    setOs(osLabel(next))
  }
  return <div className="platform-card">
    <div className="platform-card-head">
      <div className="platform-title"><strong>{title}</strong><span>{eyebrow}</span></div>
      <div className="compatibility"><span className="success-pill"><CircleCheck size={14} /> Verified Compatible</span><small>Evidence ID: <b>CM-EVD-{hardware.replace(/[^a-zA-Z0-9]/g, '')}-111</b></small></div>
    </div>
    <div className="platform-fields">
      <Field label="Vendor" value={vendor} onChange={changeVendor} options={[...new Set(platforms.map((platform) => platform.vendor))]} />
      <Field label="Hardware Model" value={selected?.hardware.model ?? hardware} onChange={changeHardware} options={[...new Set(vendorPlatforms.map((platform) => platform.hardware.model))]} helper={selected?.hardware.series} />
      <Field label="OS Version" value={osOptions.includes(os) ? os : osLabel(selected)} onChange={setOs} options={osOptions} helper={selectedOs && `${selectedOs.product} ${selectedOs.train}`} />
    </div>
  </div>
}

function Field({ label, value, onChange, options, helper }: { label: string; value: string; onChange: (value: string) => void; options: string[]; helper?: string }) {
  return <label className="field"><span>{label}</span><div className="select-wrap"><select value={value} onChange={(e) => onChange(e.target.value)}>{options.map((option) => <option key={option}>{option}</option>)}</select><ChevronDown size={14} /></div><small>{helper ?? '\u00a0'}</small></label>
}

function CodeViewer({ text }: { text: string }) {
  const lines = text.split('\n')
  return <div className="code-viewer">
    <div className="code-toolbar"><span>{lines.length} lines</span></div>
    <pre>{lines.map((line, i) => <div className="code-line" key={i}><span className="line-no">{i + 1}</span><code>{line}</code></div>)}</pre>
  </div>
}

function Metric({ icon, value, label }: { icon: ReactNode, value: string, label: string }) {
  return <div className="metric-tile"><div className="metric-icon">{icon}</div><div><strong>{value}</strong><span>{label}</span></div></div>
}

function MappingRowView({ row, onChange }: { row: MappingRow, onChange: (id: number, target: string) => void }) {
  return <tr>
    <td>{row.id}</td><td className="mono emphasis">{row.source}</td><td>{row.type}</td><td className="mono">{row.ip}</td><td>{row.zone}</td><td>{row.usedBy}</td><td className="mono suggested">{row.suggested}</td>
    <td><select className="table-select" value={row.target} onChange={(e) => onChange(row.id, e.target.value)}>{targetOptions.map((o) => <option key={o}>{o}</option>)}</select></td>
    <td><StatusBadge status={row.status} /></td><td><ConfidenceBars value={row.confidence} /></td><td>{row.notes}</td>
  </tr>
}

function StatusBadge({ status }: { status: MappingStatus }) {
  const icon = status === 'Mapped' ? <Check size={11} /> : status === 'Review' ? <AlertTriangle size={11} /> : status === 'Conflict' ? <CircleAlert size={11} /> : <span className="dot" />
  return <span className={`status-badge ${status.toLowerCase()}`}>{icon}{status}</span>
}

function ConfidenceBars({ value }: { value: Confidence }) {
  const count = value === 'High' ? 3 : value === 'Medium' ? 2 : value === 'Low' ? 1 : 0
  return <div className={`confidence ${value.toLowerCase()}`}><div>{[1, 2, 3].map((n) => <span key={n} className={n <= count ? 'on' : ''} />)}</div><small>{value}</small></div>
}

function HardwareMap({ mappings }: { mappings: MappingRow[] }) {
  return <div className="hardware-map">
    <div className="hardware-panel"><div className="hardware-title">PA-3410</div>{mappings.map((m) => <div className="port-row" key={m.id}><span>{m.source}</span><small>{m.zone}</small></div>)}</div>
    <div className="hardware-links">{mappings.map((m) => <div key={m.id}>→</div>)}</div>
    <div className="hardware-panel"><div className="hardware-title">PA-5410</div>{mappings.map((m) => <div className="port-row target" key={m.id}><span>{m.target}</span><small>{m.status}</small></div>)}</div>
  </div>
}

function ReadinessItem({ label, detail, ok, warn }: { label: string, detail: string, ok: boolean, warn?: boolean }) {
  return <div className="readiness-item">{ok && !warn ? <CircleCheck className="ok-icon" size={22} /> : <AlertTriangle className="warn-icon" size={22} />}<div><strong>{label}</strong><span>{detail}</span></div></div>
}

function ResultsContent({ tab, mappings }: { tab: ResultTab, mappings: MappingRow[] }) {
  if (tab === 'Overview') return <Overview />
  if (tab === 'Raw Comparison') return <RawComparison />
  if (tab === 'Semantic Changes') return <SemanticChanges />
  if (tab === 'Interface Mapping') return <MappingResults mappings={mappings} />
  if (tab === 'Migration Plan') return <MigrationPlan />
  if (tab === 'Candidate Configuration') return <CandidateConfig />
  return <Findings />
}

function Overview() {
  return <div className="results-overview">
    <div className="overview-card"><div className="donut"><div><strong>92%</strong><span>READY</span></div></div><Stat value="42" label="Total Objects" /><Stat value="37" label="Converted" green /><Stat value="3" label="Requires Review" warn /><Stat value="2" label="Unsupported" danger /></div>
    <div className="summary-card"><h4>Configuration Summary</h4>{[['Interfaces','15 / 16 mapped'],['Zones','8 converted'],['Security Policies','22 converted'],['NAT Rules','7 converted'],['Address Objects','64 converted'],['Services','14 converted'],['Routes','12 converted'],['VPN Tunnels','2 converted']].map(([k,v]) => <div className="summary-row" key={k}><span>{k}</span><b><CircleCheck size={12}/>{v}</b></div>)}</div>
    <div className="findings-card"><h4>Findings Summary</h4><div className="finding-grid"><MiniFinding value="5" label="Total"/><MiniFinding value="2" label="Unsupported" danger/><MiniFinding value="1" label="Warning" warn/><MiniFinding value="1" label="Note" info/></div><button className="btn secondary wide">View Findings <ArrowRight size={14}/></button></div>
  </div>
}

function Stat({ value, label, green, warn, danger }: any) { return <div className={`stat ${green?'green':''} ${warn?'warn':''} ${danger?'danger':''}`}><strong>{value}</strong><span>{label}</span></div> }
function MiniFinding({ value, label, danger, warn, info }: any){ return <div className={`mini-finding ${danger?'danger':''} ${warn?'warn':''} ${info?'info':''}`}><strong>{value}</strong><span>{label}</span></div> }

function RawComparison() {
  return <div className="raw-wrap">
    <div className="raw-toolbar"><span className="small-label">View</span><button className="chip active">Side by Side</button><button className="chip">Changed Only</button><div className="search-wrap narrow"><Search size={14}/><input placeholder="Search in configuration..."/></div><button className="btn secondary"><Code2 size={14}/> Expanded</button></div>
    <div className="diff-grid">
      <DiffPanel title="Source Configuration (PA-3410)" lines={sourceDiff} source />
      <DiffPanel title="Target Configuration (PA-5410)" lines={targetDiff} />
      <div className="diff-summary"><h4>Conversion Summary</h4><div className="donut small"><div><strong>92%</strong><span>SUCCESS</span></div></div><div className="summary-row"><span>Total Objects</span><b>42</b></div><div className="summary-row"><span>Converted</span><b>37</b></div><div className="summary-row"><span>Review</span><b className="warn-text">3</b></div><div className="summary-row"><span>Unsupported</span><b className="danger-text">2</b></div></div>
    </div>
  </div>
}

function DiffPanel({ title, lines, source }: { title: string, lines: string[], source?: boolean }) {
  return <div className="diff-panel"><div className="diff-title">{title}</div><pre>{lines.map((l,i) => <div className={`diff-line ${i===0||i===1 ? (source?'removed':'added') : ''}`} key={i}><span>{i+45}</span><code>{l}</code></div>)}</pre></div>
}

function SemanticChanges(){ const rows=[['Interface','ethernet1/1','ethernet1/5','Mapped','Physical port changed, L3 intent preserved'],['Interface','ethernet1/2','ethernet1/6','Mapped','Trust/LAN attachment preserved'],['Zone','trust','trust','Preserved','Zone identity unchanged'],['Security Policy','Allow-Web','Allow-Web','Review','Interface references updated'],['Static Route','Default Route','Default Route','Preserved','Egress moved to ethernet1/5']]; return <div className="simple-table"><table><thead><tr><th>Category</th><th>Source</th><th>Target</th><th>Status</th><th>Explanation</th></tr></thead><tbody>{rows.map(r=><tr key={r.join()}>{r.map((c,i)=><td key={i}>{c}</td>)}</tr>)}</tbody></table></div> }

function MappingResults({ mappings }: { mappings: MappingRow[] }){ return <div className="simple-table"><table><thead><tr><th>Source</th><th>Target</th><th>Dependencies</th><th>Policies Impacted</th><th>Result</th><th>Notes</th></tr></thead><tbody>{mappings.map((m,i)=><tr key={m.id}><td className="mono">{m.source}</td><td className="mono">{m.target}</td><td>{17-i*2}</td><td>{Math.max(3,12-i)}</td><td><StatusBadge status={m.status==='Unmapped'?'Review':m.status}/></td><td>{m.notes}</td></tr>)}</tbody></table></div> }

function MigrationPlan(){ const items=[['Pre-Migration','Validate target interface assignments','Review'],['Pre-Migration','Backup source PA-3410 configuration','Ready'],['Validation','Review interface dependency propagation','Review'],['Deployment','Load candidate configuration to PA-5410','Pending'],['Validation','Validate routing and policy behavior','Pending'],['Post-Migration','Confirm rollback checkpoint','Pending']]; return <div className="simple-table"><table><thead><tr><th>Stage</th><th>Task</th><th>Status</th></tr></thead><tbody>{items.map(r=><tr key={r[1]}><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td></tr>)}</tbody></table></div> }

function CandidateConfig(){ return <div><div className="candidate-toolbar"><span><FileText size={14}/> candidate-config.conf</span><div><button className="btn secondary"><Clipboard size={14}/> Copy All</button><button className="btn secondary"><Download size={14}/> Download</button></div></div><CodeViewer text={candidate}/></div> }

function Findings(){ const rows=[['Unsupported','Management','Management profile requires target capability review','Object: mgmt-prof-1'],['Unsupported','Feature','Hardware-specific feature not available on target','Feature: legacy-port-mode'],['Warning','Interface','ethernet1/4 dependency review required','Interface: ethernet1/4'],['Warning','Routing','One static route uses interface-specific next hop','Route: default'],['Note','Object','Object names preserved','Multiple objects']]; return <div className="simple-table"><table><thead><tr><th>Type</th><th>Category</th><th>Description</th><th>Reference</th></tr></thead><tbody>{rows.map(r=><tr key={r[2]}><td>{r[0]}</td><td>{r[1]}</td><td>{r[2]}</td><td className="mono">{r[3]}</td></tr>)}</tbody></table></div> }

function EmptyResults(){ return <div className="empty-results"><GitCompareArrows size={28}/><strong>No migration generated yet</strong><span>Complete interface mapping and generate the migration to review results.</span></div> }

export default App
