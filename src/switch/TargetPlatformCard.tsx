import { AlertTriangle, CircleCheck, X } from 'lucide-react'
import type { SwitchPlatformSelection } from './types.ts'
import { getArubaSeries, getArubaHardwareBySeries, getArubaHardwareById, getCompatibleOs } from './catalog.ts'
import { buildSelection, compatibilityLabel } from './compatibility.ts'

interface TargetPlatformCardProps {
  title: string
  subtitle: string
  value: SwitchPlatformSelection
  onChange: (value: SwitchPlatformSelection) => void
}

export function TargetPlatformCard({ title, subtitle, value, onChange }: TargetPlatformCardProps) {
  const seriesList = getArubaSeries()
  const currentSeries = value.hardware.series
  const modelsInSeries = getArubaHardwareBySeries(currentSeries)
  const compatibleOs = getCompatibleOs(value.hardware, false)
  // UI FILTER FIX: dropdown shows only OS releases compatible with the selected hardware
  // never AOS_CX_RELEASES global list — prevents incompatible OS from appearing

  const handleSeriesChange = (series: string) => {
    const models = getArubaHardwareBySeries(series)
    const newHw = models[0] || value.hardware
    const newOsList = getCompatibleOs(newHw, true)
    const newOs = newOsList[0] || value.os
    onChange(buildSelection(newHw, newOs))
  }

  const handleModelChange = (hardwareId: string) => {
    const newHw = getArubaHardwareById(hardwareId) || value.hardware
    const newOsList = getCompatibleOs(newHw, true)
    const newOs = newOsList.find((os) => os.id === value.os.id) || newOsList[0] || value.os
    onChange(buildSelection(newHw, newOs))
  }

  const handleOsChange = (osId: string) => {
    // look up only within the filtered compatibleOs list — guarantees no incompatible OS can be selected
    const newOs = compatibleOs.find((os) => os.id === osId) || value.os
    onChange(buildSelection(value.hardware, newOs))
  }

  const status = value.compatibility.status
  const badgeLabel = compatibilityLabel(status)
  const pillClass = status === 'READY' ? 'success-pill' : status === 'REVIEW_REQUIRED' ? 'warn-pill' : status === 'BLOCKED' ? 'error-pill' : 'unknown-pill'
  const primaryEvidence = value.compatibility.evidenceIds[0] || value.hardware.evidenceIds[0] || 'No verified evidence'

  return (
    <div className="platform-card">
      <div className="platform-card-head">
        <div className="platform-title">
          <strong>{title}</strong>
          <span>{subtitle}</span>
        </div>
        <div className="compatibility">
          <span className={pillClass} title={value.compatibility.reason}>
            {status === 'READY' && <CircleCheck size={14} />}
            {status === 'REVIEW_REQUIRED' && <AlertTriangle size={14} />}
            {status === 'BLOCKED' && <X size={14} />}
            {badgeLabel}
          </span>
          <small>Evidence: <b>{primaryEvidence}</b></small>
        </div>
      </div>
      <div className="platform-fields">
        <label className="field">
          <span>Vendor</span>
          <div className="select-wrap">
            <select value="HPE Aruba Networking" disabled>
              <option value="HPE Aruba Networking">HPE Aruba Networking</option>
            </select>
          </div>
          <small>AOS-CX Architecture</small>
        </label>
        <label className="field">
          <span>Series</span>
          <div className="select-wrap">
            <select value={currentSeries} onChange={(event) => handleSeriesChange(event.target.value)}>
              {seriesList.map((series) => (
                <option key={series} value={series}>{series}</option>
              ))}
            </select>
          </div>
          <small>{value.hardware.marketingModel}</small>
        </label>
        <label className="field">
          <span>Hardware Model / SKU</span>
          <div className="select-wrap">
            <select value={value.hardware.id} onChange={(event) => handleModelChange(event.target.value)}>
              {modelsInSeries.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.marketingModel} {item.productNumber !== 'UNKNOWN' ? `(${item.productNumber})` : ''}
                </option>
              ))}
            </select>
          </div>
          <small>
            {value.hardware.totalAccessPorts} Ports · {value.hardware.vsf.vsfStatus === 'SUPPORTED' ? `VSF (${value.hardware.vsf.maxMembers ? value.hardware.vsf.maxMembers + ' members' : 'supported'})` : value.hardware.vsf.vsfStatus === 'UNKNOWN' ? 'VSF: Unknown' : 'No VSF'}
          </small>
        </label>
        <label className="field">
          <span>Compatible OS</span>
          <div className="select-wrap">
            <select value={value.os.id} onChange={(event) => handleOsChange(event.target.value)}>
              {compatibleOs.map((os) => (
                <option key={os.id} value={os.id}>
                  {os.product} {os.train} ({os.releaseType})
                </option>
              ))}
            </select>
          </div>
          <small>{value.compatibility.reason}</small>
        </label>
      </div>
    </div>
  )
}
