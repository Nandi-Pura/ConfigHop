import { useRef, useState } from 'react'
import { Clipboard, Expand, X } from 'lucide-react'
import VirtualCodeViewer from './VirtualCodeViewer'

type Props = {
  text: string
  status: string
  message: string
  findings?: { severity: string; code: string; message: string }[]
  loading?: boolean
  syntax?: 'xml' | 'cli'
  onCopyError?: () => void
}

export default function LiveConfigEditor({ text, status, message, findings = [], loading = false, syntax = 'xml', onCopyError }: Props) {
  const [tab, setTab] = useState<'Configuration' | 'Validation'>('Configuration')
  const dialog = useRef<HTMLDialogElement>(null)
  const lines = text ? text.split('\n') : []
  const copy = () => navigator.clipboard.writeText(text).catch(onCopyError)
  const content = (height: number) => tab === 'Validation' ? <div className="live-findings" role="status"><strong>{status}</strong>{findings.length ? findings.map((finding, index) => <p key={`${finding.code}-${index}`}><b>{finding.severity}: {finding.code}</b><br />{finding.message}</p>) : <p>{message}</p>}</div> : text ? <VirtualCodeViewer lines={lines} height={height} syntax={syntax} /> : <div className="live-empty" role="status">{loading ? 'Generating current candidate…' : message}</div>
  return <section className="section-card live-editor" aria-label="Live target configuration preview">
    <div className="live-heading"><div><strong>Live Target Configuration Preview</strong><span className={status === 'READY' ? 'success-pill' : 'muted'}>{loading ? 'Updating…' : status}</span></div><div><button className="btn secondary" onClick={copy} disabled={!text}><Clipboard size={14} /> Copy All</button><button className="btn secondary" onClick={() => dialog.current?.showModal()} aria-label="Expand configuration preview"><Expand size={14} /> Expand</button></div></div>
    <div className="live-tabs" role="tablist" aria-label="Preview views"><button role="tab" aria-selected={tab === 'Configuration'} className={tab === 'Configuration' ? 'active' : ''} onClick={() => setTab('Configuration')}>Full Configuration</button><button role="tab" aria-selected={tab === 'Validation'} className={tab === 'Validation' ? 'active' : ''} onClick={() => setTab('Validation')}>Validation ({findings.length})</button></div>
    {content(440)}
    <dialog ref={dialog} className="live-dialog" aria-label="Expanded configuration preview"><div className="live-heading"><strong>Live Target Configuration Preview</strong><button className="btn secondary" onClick={() => dialog.current?.close()}><X size={14} /> Restore</button></div><div className="live-tabs"><button className={tab === 'Configuration' ? 'active' : ''} onClick={() => setTab('Configuration')}>Full Configuration</button><button className={tab === 'Validation' ? 'active' : ''} onClick={() => setTab('Validation')}>Validation ({findings.length})</button></div>{content(600)}</dialog>
  </section>
}
