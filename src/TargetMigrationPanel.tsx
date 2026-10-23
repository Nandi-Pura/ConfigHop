import { useEffect, useMemo, useState } from 'react'
import { api, ApiClientError } from './api/client'
import type { Capabilities, DeploymentPackage, SourceConnectionInput, SourceConnectionTest, TargetBaseline, TargetPreflight, TargetReconcile, TargetStage } from './api/types'


type BusyAction = 'loading' | 'testing' | 'collecting' | 'building' | 'reviewing' | 'preflight' | 'staging' | 'reconciling' | null

function errorMessage(error: unknown): string {
  return error instanceof ApiClientError ? `${error.code}: ${error.message}` : 'The target workflow could not complete the request.'
}

function checkLabel(value: string): string {
  return value.split('_').map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase()).join(' ')
}

export default function TargetMigrationPanel({ projectId, candidateAvailable, targetModel }: {
  projectId: string
  candidateAvailable: boolean
  targetModel: string | null
}) {
  const [host, setHost] = useState('')
  const [port, setPort] = useState(443)
  const [apiKey, setApiKey] = useState('')
  const [caPem, setCaPem] = useState('')
  const [connection, setConnection] = useState<SourceConnectionTest | null>(null)
  const [baseline, setBaseline] = useState<TargetBaseline | null>(null)
  const [deploymentPackage, setDeploymentPackage] = useState<DeploymentPackage | null>(null)
  const [accepted, setAccepted] = useState<string[]>([])
  const [confirmedHostname, setConfirmedHostname] = useState('')
  const [recoveryConfirmed, setRecoveryConfirmed] = useState(false)
  const [preflight, setPreflight] = useState<TargetPreflight | null>(null)
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null)
  const [stageConfirmation, setStageConfirmation] = useState('')
  const [stageResult, setStageResult] = useState<TargetStage | TargetReconcile | null>(null)
  const [busy, setBusy] = useState<BusyAction>('loading')
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    setBaseline(null); setDeploymentPackage(null); setAccepted([]); setPreflight(null); setStageResult(null); setError(''); setBusy('loading')
    Promise.allSettled([
      api.getTargetBaseline(projectId, controller.signal),
      api.getDeploymentPackage(projectId, controller.signal),
      api.getCapabilities(controller.signal),
    ]).then(([baselineResult, packageResult, capabilityResult]) => {
      if (controller.signal.aborted) return
      if (baselineResult.status === 'fulfilled') setBaseline(baselineResult.value)
      else if (!(baselineResult.reason instanceof ApiClientError && baselineResult.reason.status === 409)) setError(errorMessage(baselineResult.reason))
      if (packageResult.status === 'fulfilled') {
        setDeploymentPackage(packageResult.value)
        setAccepted(packageResult.value.target_findings.filter((item) => item.requires_acceptance && !!packageResult.value.review_id).map((item) => item.code))
      } else if (!(packageResult.reason instanceof ApiClientError && packageResult.reason.status === 409)) setError(errorMessage(packageResult.reason))
      if (capabilityResult.status === 'fulfilled') setCapabilities(capabilityResult.value)
      else setError(errorMessage(capabilityResult.reason))
      setBusy(null)
    })
    return () => controller.abort()
  }, [projectId])

  const requiredCodes = useMemo(() => new Set(deploymentPackage?.target_findings
    .filter((item) => item.requires_acceptance).map((item) => item.code) ?? []), [deploymentPackage])
  const hasBlockingFinding = deploymentPackage?.target_findings.some((item) => item.severity === 'ERROR') ?? false
  const input: SourceConnectionInput = { host: host.trim(), port, api_key: apiKey,
    ca_certificate_pem: caPem.trim() || null }
  const connectionReady = !!host.trim() && port > 0 && port <= 65535 && !!apiKey
  const baselineMatchesTarget = !!baseline && !!targetModel && baseline.model === targetModel

  function changeConnection(update: () => void) {
    update(); setConnection(null); setPreflight(null); setError('')
  }

  async function testConnection() {
    if (!connectionReady) { setError('Enter the target management IP, port, and XML API key.'); return }
    setBusy('testing'); setError('')
    try {
      const result = await api.testTargetConnection(projectId, input)
      if (targetModel && result.identity.model !== targetModel) {
        setConnection(null)
        setError(`TARGET_MODEL_MISMATCH: Connected device is ${result.identity.model}, expected ${targetModel}.`)
      } else setConnection(result)
    } catch (requestError) { setConnection(null); setError(errorMessage(requestError)) }
    finally { setBusy(null) }
  }

  async function collectBaseline() {
    if (!connection || !targetModel) return
    setBusy('collecting'); setError('')
    try {
      const result = await api.collectTargetBaseline(projectId, { ...input,
        expected_serial: connection.identity.serial, expected_model: targetModel })
      setBaseline(result); setDeploymentPackage(null); setAccepted([]); setConfirmedHostname(''); setPreflight(null)
      setApiKey(''); setCaPem(''); setConnection(null)
    } catch (requestError) { setError(errorMessage(requestError)) }
    finally { setBusy(null) }
  }

  async function buildPackage() {
    setBusy('building'); setError('')
    try { const result = await api.buildTargetPackage(projectId); setDeploymentPackage(result); setAccepted([]); setPreflight(null) }
    catch (requestError) { setError(errorMessage(requestError)) }
    finally { setBusy(null) }
  }

  function toggleFinding(code: string, checked: boolean) {
    setAccepted((current) => checked ? [...new Set([...current, code])] : current.filter((item) => item !== code))
  }

  async function reviewPackage() {
    if (!deploymentPackage || !baseline) return
    setBusy('reviewing'); setError('')
    try {
      const result = await api.reviewTargetPackage(projectId, confirmedHostname.trim(), accepted)
      setDeploymentPackage(result); setPreflight(null)
    } catch (requestError) { setError(errorMessage(requestError)) }
    finally { setBusy(null) }
  }

  async function runPreflight() {
    if (!connection || !baseline || !targetModel) return
    setBusy('preflight'); setError('')
    try {
      const result = await api.checkTargetPreflight(projectId, { ...input,
        expected_serial: baseline.serial, expected_model: targetModel,
        recovery_path_confirmed: recoveryConfirmed })
      setPreflight(result)
      if (result.deployment_allowed) { setApiKey(''); setCaPem(''); setConnection(null) }
      const refreshed = await api.getDeploymentPackage(projectId)
      setDeploymentPackage(refreshed)
    } catch (requestError) { setPreflight(null); setError(errorMessage(requestError)) }
    finally { setBusy(null) }
  }

  async function stagePackage() {
    if (!connection || !baseline || !targetModel) return
    setBusy('staging'); setError(''); setStageResult(null)
    try {
      const result = await api.stageTargetPackage(projectId, { ...input,
        expected_serial: baseline.serial, expected_model: targetModel,
        confirmed_target_hostname: baseline.hostname })
      setStageResult(result)
      setDeploymentPackage(await api.getDeploymentPackage(projectId))
      setApiKey(''); setCaPem(''); setConnection(null); setStageConfirmation('')
    } catch (requestError) {
      setError(errorMessage(requestError))
      try { setDeploymentPackage(await api.getDeploymentPackage(projectId)) } catch {}
    } finally { setBusy(null) }
  }

  async function reconcileStage() {
    if (!connection || !baseline || !targetModel) return
    setBusy('reconciling'); setError(''); setStageResult(null)
    try {
      const result = await api.reconcileTargetStage(projectId, { ...input,
        expected_serial: baseline.serial, expected_model: targetModel,
        confirmed_target_hostname: baseline.hostname })
      setStageResult(result)
      setApiKey(''); setCaPem(''); setConnection(null)
    } catch (requestError) { setError(errorMessage(requestError)) }
    finally { setBusy(null) }
  }

  const reviewReady = !!deploymentPackage?.deployable_candidate_sha256 && !deploymentPackage.review_id &&
    !hasBlockingFinding && [...requiredCodes].every((code) => accepted.includes(code)) &&
    confirmedHostname.trim() === baseline?.hostname
  const labStageEnabled = capabilities?.domains.firewall.panos_target_stage_validate === true
  const stageReady = !!connection && !!baseline && stageConfirmation === `STAGE ${baseline.hostname}`

  return <div className="target-workflow" aria-busy={busy ? 'true' : 'false'}>
    <div className="target-workflow-intro">
      <div><strong>Target package, preflight, and staging</strong><span>Direct-firewall, single-vsys workflow. Staging stops after full validation; commit requires a separate approval flow.</span></div>
      <span className={`target-state ${preflight?.status === 'PASSED' ? 'clear' : deploymentPackage?.review_id ? 'reviewed' : 'pending'}`}>{preflight?.status === 'PASSED' ? 'Preflight passed' : deploymentPackage?.review_id ? 'Package reviewed' : baseline ? 'Baseline collected' : 'Target not collected'}</span>
    </div>

    {busy === 'loading' ? <div className="target-state-message" role="status">Loading target baseline and package state.</div> : <>
      <fieldset className="target-connection" disabled={!!busy}>
        <legend>Target XML API connection</legend>
        <label><span>Management IP</span><input value={host} autoComplete="off" placeholder="192.0.2.20" onChange={(event) => changeConnection(() => setHost(event.target.value))} /></label>
        <label><span>Port</span><input type="number" min="1" max="65535" value={port} onChange={(event) => changeConnection(() => setPort(Number(event.target.value)))} /></label>
        <label><span>XML API key</span><input type="password" autoComplete="off" spellCheck={false} value={apiKey} onChange={(event) => changeConnection(() => setApiKey(event.target.value))} /></label>
        <label className="target-ca"><span>CA certificate PEM <small>Optional for a backend-trusted device certificate</small></span><textarea rows={3} autoComplete="off" spellCheck={false} placeholder="-----BEGIN CERTIFICATE-----" value={caPem} onChange={(event) => changeConnection(() => setCaPem(event.target.value))} /></label>
      </fieldset>
      <div className="target-actions">
        <button className="btn secondary" type="button" onClick={testConnection} disabled={!connectionReady || !!busy}>{busy === 'testing' ? 'Testing target connection...' : 'Test Target Connection'}</button>
        <button className="btn secondary" type="button" onClick={collectBaseline} disabled={!connection || !targetModel || !!busy}>{busy === 'collecting' ? 'Collecting target baseline...' : 'Collect Running Target Baseline'}</button>
      </div>
      {connection && <div className="target-identity" role="status"><strong>{connection.identity.hostname}</strong><span>{connection.identity.model} | PAN-OS {connection.identity.panos_version}</span><code>{connection.identity.serial}</code></div>}
      {error && <div className="target-error" role="alert"><strong>Target workflow stopped</strong><span>{error}</span></div>}

      {!baseline ? <div className="target-state-message">No target baseline yet. Test the exact device connection, then collect its running configuration twice.</div> : <div className="target-baseline-summary">
        <div><span>Target</span><strong>{baseline.hostname}</strong><small>{baseline.model} | PAN-OS {baseline.panos_version}</small></div>
        <div><span>Serial</span><code>{baseline.serial}</code></div>
        <div><span>Encrypted baseline</span><strong>{baseline.artifact_format ?? 'Unavailable'}</strong><small>{baseline.sha256.slice(0, 16)}...</small></div>
      </div>}
      {baseline && targetModel && !baselineMatchesTarget && <div className="target-error" role="alert"><strong>Selected target changed</strong><span>The collected baseline is for {baseline.model}, but the current target selection is {targetModel}. Select the matching model or collect a new baseline.</span></div>}

      <div className="target-package-stage">
        <div className="target-stage-heading"><div><strong>Deployable package</strong><span>Built on the encrypted target baseline, with protected target-local scopes left unchanged.</span></div><button className="btn secondary" type="button" onClick={buildPackage} disabled={!baselineMatchesTarget || !candidateAvailable || !!deploymentPackage?.deployable_candidate_sha256 || !!busy}>{busy === 'building' ? 'Building package...' : 'Build Target Package'}</button></div>
        {!candidateAvailable && <div className="target-state-message">Generate a validated migration candidate after collecting the target baseline.</div>}
        {deploymentPackage?.deployable_candidate_sha256 && <>
          <div className="target-preservation" aria-label="Target-local preservation checks">{Object.entries(deploymentPackage.target_preservation).map(([name, status]) => <div key={name}><span>{checkLabel(name)}</span><strong>{status}</strong></div>)}</div>
          <div className="target-change-table"><table><thead><tr><th>Action</th><th>Scope</th><th>Object</th></tr></thead><tbody>{deploymentPackage.target_changes.map((item, index) => <tr key={`${item.scope}-${item.object_name}-${index}`}><td>{item.action}</td><td><code>{item.scope}</code></td><td>{item.object_name}</td></tr>)}</tbody></table></div>
          <div className="target-findings">{deploymentPackage.target_findings.map((finding, index) => <label className={`target-finding ${finding.severity.toLowerCase()}`} key={`${finding.code}-${finding.scope}-${index}`}><input type="checkbox" checked={finding.requires_acceptance ? accepted.includes(finding.code) : true} disabled={!finding.requires_acceptance || !!deploymentPackage.review_id || !!busy} onChange={(event) => toggleFinding(finding.code, event.target.checked)} /><span><strong>{finding.severity}: {finding.code}</strong><small>{finding.scope}</small><span>{finding.message}</span>{finding.requires_acceptance && <em>Manual acceptance required</em>}</span></label>)}</div>
          {!deploymentPackage.review_id ? <div className="target-review-confirm"><label><span>Confirm target hostname</span><input value={confirmedHostname} autoComplete="off" placeholder={baseline?.hostname ?? ''} onChange={(event) => setConfirmedHostname(event.target.value)} /></label><button className="btn secondary" type="button" onClick={reviewPackage} disabled={!reviewReady || !!busy}>{busy === 'reviewing' ? 'Recording review...' : 'Approve Reviewed Package'}</button></div> : <div className="target-review-record"><strong>Manual review recorded</strong><span>Decision hash</span><code>{deploymentPackage.review_sha256}</code></div>}
        </>}
      </div>

      {deploymentPackage?.review_id && <div className="target-preflight-stage">
        <div><strong>Final read-only preflight</strong><span>Re-enter target credentials. ConfigHop rereads running and candidate state before allowing the internal package gate to pass.</span></div>
        <label className="recovery-confirm"><input type="checkbox" checked={recoveryConfirmed} onChange={(event) => setRecoveryConfirmed(event.target.checked)} /><span>I confirm tested out-of-band or console recovery access is available for this lab target.</span></label>
        <button className="btn secondary" type="button" onClick={runPreflight} disabled={!connection || !recoveryConfirmed || !!busy}>{busy === 'preflight' ? 'Running read-only preflight...' : 'Run Final Preflight'}</button>
        {!connection && <small>Test the target connection again with fresh request-scoped credentials before preflight.</small>}
        {preflight && <div className={`preflight-report ${preflight.status.toLowerCase()}`}><div><strong>{preflight.status}</strong><span>{preflight.deployment_allowed ? 'All implemented offline gates are clear. No device mutation has occurred.' : 'Resolve every blocked check and run preflight again.'}</span></div><div className="preflight-checks">{Object.entries(preflight.checks).map(([name, status]) => <div key={name}><span>{checkLabel(name)}</span><strong className={status.toLowerCase()}>{status}</strong></div>)}</div></div>}
      </div>}

      {deploymentPackage && ['PREFLIGHT_PASSED', 'STATUS_UNKNOWN', 'VALIDATED'].includes(deploymentPackage.status) && <div className="target-deploy-stage">
        <div className="target-stage-heading"><div><strong>Stage and validate candidate</strong><span>Creates encrypted backups, imports the reviewed XML, loads candidate state, and runs full validation. This step never commits.</span></div><span className={`target-state ${deploymentPackage.status === 'VALIDATED' ? 'clear' : deploymentPackage.status === 'STATUS_UNKNOWN' ? 'unknown' : 'reviewed'}`}>{checkLabel(deploymentPackage.status)}</span></div>
        {!labStageEnabled ? <div className="target-state-message"><strong>Staging unavailable</strong><span>Server deployment mode is disabled. Enable lab mode only for an approved lab target.</span></div> : <>
          {deploymentPackage.status === 'PREFLIGHT_PASSED' && <>
            <label className="target-stage-confirm"><span>Type <code>STAGE {baseline?.hostname}</code> to confirm this exact lab target.</span><input value={stageConfirmation} autoComplete="off" onChange={(event) => setStageConfirmation(event.target.value)} /></label>
            <button className="btn secondary" type="button" onClick={stagePackage} disabled={!stageReady || !!busy}>{busy === 'staging' ? 'Backing up, staging, and validating...' : 'Stage and Validate Candidate'}</button>
            {!connection && <small>Test the target connection again with fresh request-scoped credentials before staging.</small>}
          </>}
          {deploymentPackage.status === 'STATUS_UNKNOWN' && <div className="target-ambiguous" role="alert"><strong>Device result is unknown</strong><span>The {deploymentPackage.ambiguous_operation?.toLowerCase()} request may have reached the firewall. ConfigHop will not retry it automatically.</span><button className="btn secondary" type="button" onClick={reconcileStage} disabled={!connection || !!busy}>{busy === 'reconciling' ? 'Reading target state...' : 'Run Read-only Reconciliation'}</button>{!connection && <small>Test the same target connection again before reconciliation.</small>}</div>}
          {deploymentPackage.status === 'VALIDATED' && <div className="target-validation-evidence" role="status"><strong>Candidate validated, commit not created</strong><span>Running backup</span><code>{deploymentPackage.running_backup_sha256}</code><span>Candidate backup</span><code>{deploymentPackage.candidate_backup_sha256}</code><span>Loaded candidate</span><code>{deploymentPackage.loaded_candidate_sha256}</code><span>Validation evidence</span><code>{deploymentPackage.validation_sha256}</code>{deploymentPackage.validation_job_id && <><span>Validation job</span><code>{deploymentPackage.validation_job_id}</code></>}</div>}
          {stageResult && <div className={`target-stage-result ${'reconciliation' in stageResult ? stageResult.reconciliation.toLowerCase() : 'validated'}`} role="status"><strong>{'reconciliation' in stageResult ? checkLabel(stageResult.reconciliation) : 'Staging complete'}</strong><span>{stageResult.message}</span></div>}
        </>}
      </div>}
    </>}
  </div>
}
