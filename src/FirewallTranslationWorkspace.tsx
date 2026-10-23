import { useEffect, useRef, useState, type RefObject } from 'react'
import { Clipboard, Download, Upload } from 'lucide-react'
import LiveConfigEditor from './LiveConfigEditor'
import type { MockActions } from './MockWorkspace'
import { firewallApi, type FirewallEntity, type FirewallMappings, type FirewallPreview, type FirewallProject } from './api/firewall'

const STORE = 'confighop-firewall-cross-vendor-v1'
const emptyMappings = (): FirewallMappings => ({ interfaces: {}, zones: {}, addresses: {}, services: {}, policies: {}, nat: {} })
const sourceOptions = { fortios: ['7.4'], panos: ['11.1'] }
const label = { fortios: 'Fortinet FortiOS', panos: 'Palo Alto PAN-OS' }
type Vendor = 'fortios' | 'panos'
type Props = { onDomainChange: (domain: 'Firewall' | 'Switch') => void; onTitleChange: (title: string) => void; actionsRef: RefObject<MockActions | null>; initialSourceOS?: Vendor }

export default function FirewallTranslationWorkspace({ onDomainChange, onTitleChange, actionsRef, initialSourceOS = 'fortios' }: Props) {
  const [sourceOS, setSourceOS] = useState<Vendor>(initialSourceOS)
  const [sourceVersion, setSourceVersion] = useState(initialSourceOS === 'fortios' ? '7.4' : '11.1')
  const [targetVersion, setTargetVersion] = useState(initialSourceOS === 'fortios' ? '11.1' : '7.4')
  const targetOS: Vendor = sourceOS === 'fortios' ? 'panos' : 'fortios'
  const [project, setProject] = useState<FirewallProject | null>(null)
  const [preview, setPreview] = useState<FirewallPreview | null>(null)
  const [mappings, setMappings] = useState<FirewallMappings>(emptyMappings)
  const [name, setName] = useState('No configuration loaded')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [ack, setAck] = useState(false)
  const [category, setCategory] = useState<keyof FirewallMappings>('interfaces')
  const fileRef = useRef<HTMLInputElement>(null)
  const serial = useRef(0)
  const revision = useRef(0)
  const abort = useRef<AbortController | null>(null)
  const projectRef = useRef<FirewallProject | null>(null)
  const reset = () => {
    serial.current++; abort.current?.abort()
    const old = projectRef.current
    projectRef.current = null; setProject(null); setPreview(null); setMappings(emptyMappings()); setName('No configuration loaded'); setError(''); setAck(false); setLoading(false)
    if (old) void firewallApi.delete(old.project_id).catch(() => {})
  }
  useEffect(() => { return () => { serial.current++; abort.current?.abort() } }, [])
  useEffect(() => {
    if (!project) return
    const current = ++serial.current
    const controller = new AbortController(); abort.current = controller
    setPreview(null); setAck(false); setLoading(true)
    const timer = setTimeout(() => {
      const next = ++revision.current
      void firewallApi.preview(project.project_id, next, targetOS, targetVersion, mappings, controller.signal)
        .then(value => { if (current === serial.current) setPreview(value) })
        .catch(cause => { if (current === serial.current && !controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Preview failed.') })
        .finally(() => { if (current === serial.current) setLoading(false) })
    }, 250)
    return () => { clearTimeout(timer); controller.abort(); if (current === serial.current) serial.current++ }
  }, [project, targetOS, targetVersion, mappings])
  const upload = async (text: string, filename: string) => {
    reset(); const current = serial.current
    if (new Blob([text]).size > 2 * 1024 * 1024) { setError('Source exceeds the 2 MB limit.'); return }
    const controller = new AbortController(); abort.current = controller; setLoading(true)
    try {
      const value = await firewallApi.inspect(text, sourceOS, sourceVersion, controller.signal)
      if (current !== serial.current) { void firewallApi.delete(value.project_id).catch(() => {}); return }
      projectRef.current = value; setProject(value); revision.current = value.revision; setName(filename); setError('')
    } catch (cause) { if (current === serial.current && !controller.signal.aborted) setError(cause instanceof Error ? cause.message : 'Source inspection failed.') }
    finally { if (current === serial.current) setLoading(false) }
  }
  const uploadFile = async (file: File) => {
    reset(); const current = serial.current
    if (file.size > 2 * 1024 * 1024) { setError('Source exceeds the 2 MB limit.'); return }
    try {
      const text = await file.text()
      if (current === serial.current) await upload(text, file.name)
    } catch { if (current === serial.current) setError('Could not read the source file.') }
  }
  const paste = async () => {
    reset(); const current = serial.current
    try {
      const text = await navigator.clipboard.readText()
      if (current === serial.current) await upload(text, 'Clipboard source')
    } catch { if (current === serial.current) setError('Clipboard access is unavailable.') }
  }
  const changeSource = (next: Vendor) => {
    reset(); setSourceOS(next); setSourceVersion(sourceOptions[next][0]); setTargetVersion(sourceOptions[next === 'fortios' ? 'panos' : 'fortios'][0]); onTitleChange(`${label[next]} to ${label[next === 'fortios' ? 'panos' : 'fortios']}`)
  }
  const rename = (kind: keyof FirewallMappings, source: string, value: string) => {
    setMappings(current => ({ ...current, [kind]: { ...current[kind], [source]: value } }))
    setError('')
  }
  const save = () => {
    if (!project) { setError('Upload a source before saving this session.'); return }
    localStorage.setItem(STORE, JSON.stringify({ project_id: project.project_id, sourceOS, sourceVersion, targetVersion, mappings, name }))
  }
  const load = async () => {
    const raw = localStorage.getItem(STORE)
    if (!raw) { setError('No saved cross-vendor session found.'); return }
    try {
      const saved = JSON.parse(raw) as { project_id: string; sourceOS: Vendor; sourceVersion: string; targetVersion: string; mappings: FirewallMappings; name: string }
      if (projectRef.current?.project_id !== saved.project_id) reset()
      else { serial.current++; abort.current?.abort(); setPreview(null); setAck(false) }
      const current = serial.current
      const value = await firewallApi.get(saved.project_id)
      if (current !== serial.current) return
      projectRef.current = value; setProject(value); revision.current = value.revision; setSourceOS(saved.sourceOS); setSourceVersion(saved.sourceVersion); setTargetVersion(saved.targetVersion); setMappings(saved.mappings); setName(saved.name)
    } catch { setError('Saved session expired. Re-upload the source configuration.') }
  }
  actionsRef.current = { save, load: () => void load(), clear: reset, reset }
  const inventory = project?.inventory
  const categories: [keyof FirewallMappings, FirewallEntity[]][] = [
    ['interfaces', inventory?.interfaces ?? []], ['zones', inventory?.zones ?? []],
    ['addresses', [...(inventory?.addresses ?? []), ...(inventory?.address_groups ?? [])]],
    ['services', [...(inventory?.services ?? []), ...(inventory?.service_groups ?? [])]],
    ['policies', inventory?.policies ?? []], ['nat', inventory?.nat ?? []],
  ]
  const active = categories.find(([key]) => key === category)?.[1] ?? []
  const candidate = preview?.candidate
  const firstBlocker = candidate?.findings.find(finding => finding.severity === 'BLOCKED')
  const canExport = !!candidate?.text && candidate.status !== 'BLOCKED' && candidate.status !== 'INCOMPLETE' && (!loading) && (candidate.status !== 'REVIEW_REQUIRED' || ack)
  const exportCandidate = async () => {
    if (!preview || !canExport) return
    const current = serial.current
    try {
      const result = await firewallApi.export(preview, ack)
      if (current !== serial.current) return
      const url = URL.createObjectURL(new Blob([result.text], { type: targetOS === 'panos' ? 'application/xml' : 'text/plain' }))
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = result.filename; anchor.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (cause) { if (current === serial.current) setError(cause instanceof Error ? cause.message : 'Export failed.') }
  }
  return <main className="workspace locked-workspace firewall-workspace phase9b-workspace">
    <div className="locked-title"><div><h1>Firewall Migration</h1><p>FortiOS and PAN-OS cross-vendor candidate translation</p></div><label>Migration Type<select value="Firewall" onChange={() => onDomainChange('Switch')}><option>Firewall</option><option>Switch</option></select></label></div>
    {error && <div className="api-error" role="alert">{error}</div>}
    <section className="section-card locked-top">
      <div className="locked-platform"><strong>Source Platform</strong><label>Vendor and OS<select aria-label="Source firewall OS" value={sourceOS} onChange={event => changeSource(event.target.value as Vendor)}><option value="fortios">Fortinet FortiOS</option><option value="panos">Palo Alto PAN-OS</option></select></label><label>OS version<select aria-label="Source firewall version" value={sourceVersion} onChange={event => { reset(); setSourceVersion(event.target.value) }}>{sourceOptions[sourceOS].map(version => <option key={version}>{version}</option>)}</select></label></div>
      <div className="locked-platform"><strong>Target Platform</strong><span>{label[targetOS]}</span><label>OS version<select aria-label="Target firewall version" value={targetVersion} onChange={event => setTargetVersion(event.target.value)}>{sourceOptions[targetOS].map(version => <option key={version}>{version}</option>)}</select></label><small>Hardware suitability requires separate verification.</small></div>
      <div className="locked-platform"><strong>Source Configuration</strong><div className="locked-upload"><button className="btn accent-outline" onClick={() => fileRef.current?.click()}><Upload size={14} /> Upload File</button><button className="btn secondary" onClick={() => void paste()}><Clipboard size={14} /> Paste</button></div><input ref={fileRef} type="file" hidden accept={sourceOS === 'panos' ? '.xml,text/xml' : '.conf,.cfg,.txt,text/plain'} onChange={event => { const file = event.target.files?.[0]; if (file) void uploadFile(file); event.target.value = '' }} /><small>{name}</small></div>
    </section>
    <section className="section-card locked-inventory"><strong>Source Inventory</strong><div className="locked-metrics">{[
      ['Interfaces', inventory?.interfaces.length], ['Zones', inventory?.zones.length], ['Addresses', inventory?.addresses.length], ['Address groups', inventory?.address_groups.length],
      ['Services', inventory?.services.length], ['Service groups', inventory?.service_groups.length], ['Policies', inventory?.policies.length], ['NAT', inventory?.nat.length], ['Routes', inventory?.routes.length], ['Schedules', inventory?.schedules.length],
    ].map(([title, count]) => <div key={title}><b>{count ?? '—'}</b><span>{title}</span></div>)}</div>{inventory?.findings.length ? <small>{inventory.findings.length} source findings require review.</small> : null}</section>
    <div className="locked-main"><section className="section-card locked-mapping"><div className="section-heading"><strong>Configuration Mapping</strong><span>Names and interfaces must be checked on the target platform</span></div><div className="results-tabs">{categories.map(([key, values]) => <button key={key} className={category === key ? 'active' : ''} onClick={() => setCategory(key)}>{key} ({values.length})</button>)}</div><div className="phase9b-list">{active.map(item => <label key={`${item.scope}:${item.name}`}><span>{item.name}<small>{item.scope}{item.line ? ` · line ${item.line}` : ''}</small></span><input aria-label={`Target ${category} for ${item.name}`} placeholder={category === 'interfaces' ? 'Required target interface' : item.name} value={mappings[category][item.name] ?? ''} onChange={event => rename(category, item.name, event.target.value)} /></label>)}{!active.length && <div className="viewer-placeholder">No {category} parsed from this source.</div>}</div></section>
      <LiveConfigEditor text={candidate?.text ?? ''} syntax={candidate?.syntax ?? (targetOS === 'panos' ? 'xml' : 'cli')} configurationLabel="Candidate Configuration" status={candidate?.status ?? (loading ? 'Updating' : 'Awaiting source')} message={candidate?.status === 'BLOCKED' ? 'Resolve blocking findings before a candidate can be rendered.' : 'Upload a source and provide target mappings.'} findings={candidate?.findings ?? inventory?.findings ?? []} loading={loading} onCopyError={() => setError('Clipboard access is unavailable.')} />
    </div>
    <section className="section-card phase9b-report"><strong>Translation Coverage</strong><div className="phase9b-coverage">{(candidate?.coverage ?? []).map(row => <span key={row.category}>{row.category}: {row.parsed} parsed · {row.translated} translated · {row.rendered} rendered · {row.validated} validated · {row.blocked} blocked</span>)}</div><div role="status" aria-live="polite"><p>{candidate?.status ?? 'INCOMPLETE'} · Candidate is for engineering review, not hardware deployment certification.</p>{firstBlocker && <p>Blocking finding: {firstBlocker.code} — {firstBlocker.message} Open Validation for all findings.</p>}</div></section>
    <div className="locked-export">{candidate?.status === 'REVIEW_REQUIRED' && <label><input type="checkbox" checked={ack} onChange={event => setAck(event.target.checked)} /> I acknowledge the current review findings.</label>}<button className="btn accent" disabled={!canExport} onClick={() => void exportCandidate()}><Download size={14} /> Export Migration Candidate</button></div>
  </main>
}
