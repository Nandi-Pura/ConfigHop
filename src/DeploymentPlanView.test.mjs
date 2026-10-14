import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

test('migration plan separates candidate operations from unverified physical tasks', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  try {
    const { default: View } = await vite.ssrLoadModule('/src/DeploymentPlanView.tsx')
    const requirement = { id: 'optic:ethernet1/5:ethernet1/6', category: 'PHYSICAL_OPTIC', phase: 'PRE_CHANGE',
      source_interface: 'ethernet1/5', target_interface: 'ethernet1/6', title: 'Verify Target Transceiver',
      description: 'Engineer must inspect installed optic.', status: 'ENGINEER_ACTION_REQUIRED',
      target_port_type: 'SFP+', target_rate_capabilities: ['1G', '10G'], selected_optic_rate: '10G',
      source_configured_speed: null, finding_codes: [], evidence_ids: ['PAN-HW-PA5200-FRONT'] }
    const plan = { assessment_status: 'REVIEW_REQUIRED', candidate_validation: { valid: true, candidate_parse_ok: true,
      expected_inventory_match: true, preservation_audit_ok: true, operations_applied: 1 },
      physical_verification_status: 'NOT_VERIFIED', configuration_operations: [{ sequence: 1,
        operation_type: 'RENAME_INTERFACE', object_type: 'interface', object_name: 'ethernet1/5', scope: 'network',
        source_value: 'ethernet1/5', target_value: 'ethernet1/6' }], deployment_requirements: [requirement], blockers: [] }
    const render = (value, evidence = [{ id: 'PAN-HW-PA5200-FRONT' }]) => renderToStaticMarkup(
      React.createElement(View, { plan: value, evidence, onEvidence() {} }))
    const html = render(plan)
    assert.match(html, /Configuration Operations/)
    assert.match(html, /RENAME_INTERFACE/)
    assert.match(html, /Deployment Requirements/)
    assert.match(html, /Verify Target Transceiver/)
    assert.match(html, /Candidate validation<\/span><strong>PASS/)
    assert.match(html, /Physical deployment verification<\/span><strong>NOT VERIFIED/)
    assert.match(html, /PAN-HW-PA5200-FRONT/)
    assert.doesNotMatch(html, /VERIFIED<\/span><\/td>/)
    const blocked = render({ ...plan, assessment_status: 'BLOCKED', candidate_validation: null,
      configuration_operations: [], blockers: [{ code: 'TARGET_MEDIA_INCOMPATIBLE',
        message: 'Media mismatch', source_interface: 'ethernet1/1', target_interface: 'ethernet1/5', evidence_ids: [] }] })
    assert.match(blocked, /Blocked Migration Scope/)
    assert.match(blocked, /TARGET_MEDIA_INCOMPATIBLE/)
    assert.match(blocked, /NOT AVAILABLE/)
    assert.match(blocked, /No candidate is implied by this preview/)
    assert.doesNotMatch(blocked, /RENAME_INTERFACE/)
    const references = [
      { id: 'blocked-unmodeled_interface_reference:d21f2304b65e7709903c2889e07f6e56aa3d1d9bc3b82608ed5aac9d9f17c635', description: 'Unmodeled OSPF reference' },
      { id: 'blocked-unmodeled_interface_reference:866e3e80600e909bdaf48cfad16c5a83940a5346159451d6b8e3c89f8e69f0f7', description: 'Unmodeled BGP reference' },
    ].map((item) => ({ ...requirement, ...item, title: 'Unmodeled Interface Reference',
      category: 'DEPENDENCY_BOUNDARY', status: 'BLOCKED', finding_codes: ['UNMODELED_INTERFACE_REFERENCE'], evidence_ids: [] }))
    assert.equal(new Set(references.map((item) => item.id)).size, 2)
    const multiple = render({ ...plan, candidate_validation: null, configuration_operations: [],
      assessment_status: 'BLOCKED', deployment_requirements: references })
    assert.match(multiple, /Unmodeled OSPF reference/)
    assert.match(multiple, /Unmodeled BGP reference/)
    assert.equal((multiple.match(/Unmodeled Interface Reference/g) ?? []).length, 2)
  } finally {
    await vite.close()
  }
})
