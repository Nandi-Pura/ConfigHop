import type { DeploymentPlan, DeploymentRequirement, EvidenceRecord, RequirementPhase } from './api/types'

const phases: { key: RequirementPhase; title: string }[] = [
  { key: 'PRE_CHANGE', title: 'Pre-change' },
  { key: 'CUTOVER', title: 'Cutover' },
  { key: 'POST_CHANGE', title: 'Post-change' },
]

export default function DeploymentPlanView({ plan, evidence, onEvidence }: {
  plan: DeploymentPlan
  evidence: EvidenceRecord[]
  onEvidence: (ids: string[]) => void
}) {
  const available = new Set(evidence.map((item) => item.id))
  const evidenceCell = (ids: string[]) => ids.length ? <span className="deployment-evidence">{ids.map((id) => available.has(id)
    ? <button key={id} type="button" className="evidence-link" onClick={() => onEvidence([id])}>{id}</button>
    : <span key={id}>Evidence unavailable: {id}</span>)}</span> : <span>No hardware reference</span>
  const interfaceLabel = (item: DeploymentRequirement) => item.source_interface && item.target_interface
    ? `${item.source_interface} → ${item.target_interface}` : item.target_interface ?? 'Project'

  return <div className="deployment-plan">
    <div className="deployment-summary">
      <div><span>Backend assessment</span><strong>{plan.assessment_status}</strong></div>
      <div><span>Candidate validation</span><strong>{plan.candidate_validation?.valid ? 'PASS' : 'NOT AVAILABLE'}</strong></div>
      <div><span>Physical deployment verification</span><strong>NOT VERIFIED</strong></div>
    </div>
    <section className="deployment-section">
      <h4>Configuration Operations</h4>
      <p>Validated PAN-OS candidate operations. Physical tasks below are separate.</p>
      {plan.configuration_operations.length ? <div className="deployment-table-wrap"><table><thead><tr><th>#</th><th>Operation</th><th>Object</th><th>Scope</th><th>Source</th><th>Target</th></tr></thead><tbody>
        {plan.configuration_operations.map((item) => <tr key={item.sequence}><td>{item.sequence}</td><td>{item.operation_type}</td><td>{item.object_type}: {item.object_name}</td><td>{item.scope}</td><td>{item.source_value}</td><td>{item.target_value}</td></tr>)}
      </tbody></table></div> : <p className="deployment-empty">Configuration operations are available after candidate validation. No candidate is implied by this preview.</p>}
      {plan.candidate_validation?.valid && <p className="deployment-validation">Candidate parse: {plan.candidate_validation.candidate_parse_ok ? 'PASS' : 'FAIL'} · Expected inventory: {plan.candidate_validation.expected_inventory_match ? 'PASS' : 'FAIL'} · Preservation audit: {plan.candidate_validation.preservation_audit_ok ? 'PASS' : 'FAIL'} · Operations applied: {plan.candidate_validation.operations_applied}</p>}
    </section>
    {!!plan.blockers.length && <section className="deployment-section deployment-blockers"><h4>Blocked Migration Scope</h4><p>Resolve these backend errors before candidate generation.</p><ul>{plan.blockers.map((item, index) => <li key={`${item.code}-${item.source_interface}-${index}`}><strong>{item.code}</strong><span>{item.source_interface ?? 'Project'}{item.target_interface ? ` → ${item.target_interface}` : ''}: {item.message}</span>{evidenceCell(item.evidence_ids)}</li>)}</ul></section>}
    {!!plan.review_findings?.length && <section className="deployment-section deployment-blockers"><h4>Review Findings</h4><p>Backend warnings remain open for engineer review.</p><ul>{plan.review_findings.map((item, index) => <li key={`${item.code}-${item.source_interface}-${index}`}><strong>{item.code}</strong><span>{item.source_interface ?? 'Project'}{item.target_interface ? ` → ${item.target_interface}` : ''}: {item.message}</span>{evidenceCell(item.evidence_ids)}</li>)}</ul></section>}
    <section className="deployment-section"><h4>Deployment Requirements</h4><p>Engineer actions remain unverified even after review acknowledgement or candidate validation.</p>
      {phases.map(({ key, title }) => { const items = plan.deployment_requirements.filter((item) => item.phase === key); return items.length ? <div key={key} className="deployment-phase"><h5>{title}</h5><div className="deployment-table-wrap"><table><thead><tr><th>Requirement</th><th>Interface</th><th>Target context</th><th>Verification</th><th>Evidence</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><strong>{item.title}</strong><small>{item.description}</small>{item.finding_codes.length > 0 && <small>Backend: {item.finding_codes.join(', ')}</small>}</td><td>{interfaceLabel(item)}</td><td>{item.target_port_type ?? '—'}{item.target_rate_capabilities.length > 0 && <small>Documented rates: {item.target_rate_capabilities.join(', ')}</small>}{item.selected_optic_rate && <small>Selected optic: {item.selected_optic_rate}</small>}{item.source_interface && <small>Source configured speed: {item.source_configured_speed ?? 'Default / absent; actual speed unknown'}</small>}</td><td><span className={`deployment-status deployment-status-${item.status.toLowerCase()}`}>{item.status.replaceAll('_', ' ')}</span></td><td>{evidenceCell(item.evidence_ids)}</td></tr>)}</tbody></table></div></div> : null })}
    </section>
    <p className="deployment-limit">Hardware documents describe port capabilities. ConfigHop has not verified installed optics, live link state, cabling, or peer readiness. Rollback preparation is guidance; ConfigHop does not execute rollback.</p>
  </div>
}
