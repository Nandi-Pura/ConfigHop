import { useEffect, useRef, useState } from 'react'

const LINE_HEIGHT = 16
const OVERSCAN = 12

export default function VirtualCodeViewer({ lines, height = 190, scrollTop, onScrollTop, lineKinds }: {
  lines: string[]
  height?: number
  scrollTop?: number
  onScrollTop?: (value: number) => void
  lineKinds?: string[]
}) {
  const viewport = useRef<HTMLDivElement>(null)
  const [localTop, setLocalTop] = useState(0)
  useEffect(() => {
    if (scrollTop === undefined || !viewport.current || Math.abs(viewport.current.scrollTop - scrollTop) < 1) return
    viewport.current.scrollTop = scrollTop
    setLocalTop(scrollTop)
  }, [scrollTop])
  const first = Math.max(0, Math.floor(localTop / LINE_HEIGHT) - OVERSCAN)
  const visible = Math.ceil(height / LINE_HEIGHT) + OVERSCAN * 2
  const last = Math.min(lines.length, first + visible)
  return <div className="code-viewer">
    <div className="code-toolbar"><span>{lines.length} lines</span></div>
    <div ref={viewport} className="virtual-code-scroll" tabIndex={0} aria-label="Read-only configuration" style={{ height, overflow: 'auto' }}
      onScroll={(event) => { const top = event.currentTarget.scrollTop; setLocalTop(top); onScrollTop?.(top) }}>
      <div style={{ height: lines.length * LINE_HEIGHT, position: 'relative', minWidth: 'max-content' }}>
        <div style={{ position: 'absolute', top: first * LINE_HEIGHT, left: 0, right: 0 }}>
          {lines.slice(first, last).map((line, offset) => <div className={`code-line ${lineKinds?.[first + offset] ?? ''}`.trim()} style={{ height: LINE_HEIGHT }} key={first + offset}>
            <span className="line-no">{first + offset + 1}</span><code>{line}</code>
          </div>)}
        </div>
      </div>
    </div>
  </div>
}
