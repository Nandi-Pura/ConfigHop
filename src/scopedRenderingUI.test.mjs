import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

test('scoped rendering presentation follows current backend facts', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  try {
    const ui = await vite.ssrLoadModule('/src/scopedRenderingUI.ts')
    const scoped = { target_render_support: 'SCOPED' }
    const safePort = { name: 'ethernet1/1', candidate_support: 'CONDITIONAL', required_condition: 'AUTO_ONLY_LINK_FIELDS_ABSENT' }
    const optical = { name: 'ethernet1/13', candidate_support: 'BLOCKED', required_condition: 'TARGET_LINK_SERIALIZATION_UNVERIFIED' }
    const native = { name: 'ethernet1/41', candidate_support: 'CONDITIONAL', required_condition: 'MANUAL_NATIVE_PORT_SPEED' }
    const breakout = { name: 'ethernet1/25', candidate_support: 'BLOCKED', required_condition: 'BREAKOUT_MODE' }
    const preview = { overall_status: 'READY', impacts: [], findings: [], hardware_assessment: { effective_assignments: [], findings: [] } }
    const finding = (code, message = code) => ({ code, message, severity: 'ERROR', source_interface: 'ethernet1/1', target_interface: 'ethernet1/1' })
    const auto = { link_speed: 'auto', link_speed_explicit: true, link_duplex: null, link_duplex_explicit: false }
    const manual = { ...auto, link_speed: '1000' }

    assert.equal(ui.rowRenderScope(scoped, safePort, null, []), 'PENDING')
    assert.equal(ui.rowRenderScope(scoped, safePort, preview, []), 'SAFE_PATH')
    assert.equal(ui.rowRenderScope(scoped, safePort, preview, [{ ...finding('REVIEW'), severity: 'WARNING' }]), 'REVIEW')
    assert.equal(ui.rowRenderScope(scoped, safePort, preview, [finding('TARGET_AUTO_ONLY_LINK_SERIALIZATION_UNVERIFIED')]), 'BLOCKED')
    assert.equal(ui.rowRenderScope(scoped, optical, preview, [finding('TARGET_INTERFACE_GROUP_RENDERING_UNQUALIFIED')]), 'BLOCKED')
    assert.equal(ui.rowRenderScope({ target_render_support: 'SUPPORTED' }, native, preview, []), 'FULL')
    assert.equal(ui.rowRenderScope({ target_render_support: 'ANALYSIS_ONLY' }, safePort, preview, []), 'ANALYSIS_ONLY')
    assert.equal(ui.findingLabel(finding('TARGET_AUTO_ONLY_LINK_SERIALIZATION_UNVERIFIED'), auto), 'Explicit Auto Serialization Unverified')
    assert.equal(ui.findingLabel(finding('TARGET_AUTO_ONLY_LINK_SERIALIZATION_UNVERIFIED'), manual), 'Manual Link Setting Requires Resolution')
    assert.match(ui.linkFindingExplanation(finding('TARGET_AUTO_ONLY_LINK_SERIALIZATION_UNVERIFIED'), auto), /explicit link setting/)
    assert.match(ui.linkFindingExplanation(finding('TARGET_AUTO_ONLY_LINK_SERIALIZATION_UNVERIFIED'), manual), /Manual source speed/)
    assert.match(ui.linkFindingExplanation(finding('TARGET_AUTO_ONLY_LINK_SERIALIZATION_UNVERIFIED'), { ...auto, link_duplex: 'full', link_duplex_explicit: true }), /Manual source duplex/)
    assert.equal(ui.findingLabel(finding('SCOPED_TARGET_ACTIVE_INTERFACE_MAPPING_REQUIRED')), 'Explicit Mapping Required')
    assert.equal(ui.findingLabel(finding('TARGET_INTERFACE_GROUP_RENDERING_UNQUALIFIED')), 'Target Rendering Not Qualified')
    assert.equal(ui.sourceLinkFact(null, false), 'Default / absent')
    assert.equal(ui.sourceLinkFact('auto', true), 'auto · explicit')
    assert.equal(ui.sourceLinkFact('1000', true), '1000 · explicit')
    assert.equal(ui.sourceLinkFact('full', true), 'full · explicit')
    assert.equal(ui.shouldShowNativeSpeedChoice(native), true)
    assert.equal(ui.shouldShowNativeSpeedChoice(safePort), false)
    assert.equal(ui.canSelectPortForAnalysis(optical, 'SCOPED'), true)
    assert.equal(ui.canSelectPortForAnalysis(breakout, 'SUPPORTED'), false)
    assert.equal(ui.scopedReadiness(scoped, preview, 0, 1).status, 'READY')
    assert.equal(ui.scopedReadiness(scoped, { ...preview, overall_status: 'BLOCKED' }, 1, 0).status, 'BLOCKED')
    assert.equal(ui.scopedReadiness({ target_render_support: 'SUPPORTED' }, preview, 0, 1), null)

    const duplicated = { ...preview, findings: [finding('SCOPED_TARGET_ACTIVE_INTERFACE_MAPPING_REQUIRED')], hardware_assessment: { effective_assignments: [], findings: [finding('SCOPED_TARGET_ACTIVE_INTERFACE_MAPPING_REQUIRED')] } }
    assert.equal(ui.rowFindings('ethernet1/1', 'ethernet1/1', duplicated).length, 1)
  } finally { await vite.close() }
})

test('target platform card distinguishes supported, scoped, and analysis only', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  try {
    const { PlatformCard } = await vite.ssrLoadModule('/src/FirewallApp.tsx')
    for (const [support, label] of [
      ['SUPPORTED', 'Hardware Verified · Renderer Supported'],
      ['SCOPED', 'Hardware Verified · Scoped Rendering'],
      ['ANALYSIS_ONLY', 'Hardware Verified · Analysis Only'],
    ]) {
      const profile = { id: support, model: support, profile_status: 'verified', target_render_support: support, supported_panos_trains: [], evidence_ids: [] }
      const html = renderToStaticMarkup(React.createElement(PlatformCard, { title: 'Target Platform', eyebrow: 'Migration Destination', profile, profiles: [profile], selected: support, onSelect() {}, train: '', onTrain() {}, onEvidence() {} }))
      assert.ok(html.includes(label))
      assert.equal(html.includes('Candidate generation is limited to qualified interface paths.'), support === 'SCOPED')
    }
  } finally { await vite.close() }
})

test('optic context stays separate from native speed through UI, payload, and saved mappings', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  const previousFetch = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init })
    return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
  }
  try {
    const ui = await vite.ssrLoadModule('/src/scopedRenderingUI.ts')
    const { OpticRateChoice } = await vite.ssrLoadModule('/src/FirewallApp.tsx')
    const { api } = await vite.ssrLoadModule('/src/api/client.ts')
    const optical = { required_condition: 'OPTIC_CONTEXT_LINK_FIELDS_ABSENT' }
    const native = { required_condition: 'MANUAL_NATIVE_PORT_SPEED' }
    const rj45 = { required_condition: 'AUTO_ONLY_LINK_FIELDS_ABSENT' }
    assert.equal(ui.shouldShowOpticRateChoice(optical), true)
    assert.equal(ui.shouldShowNativeSpeedChoice(optical), false)
    assert.equal(ui.shouldShowOpticRateChoice(native), false)
    assert.equal(ui.shouldShowNativeSpeedChoice(native), true)
    assert.equal(ui.shouldShowOpticRateChoice(rj45), false)
    assert.equal(ui.shouldShowNativeSpeedChoice(rj45), false)
    for (const [rates, included, excluded] of [
      [['1G'], ['1G'], ['10G', '40G', '100G']],
      [['1G', '10G'], ['1G', '10G'], ['40G', '100G']],
      [['40G'], ['40G'], ['1G', '10G', '100G']],
      [['40G', '100G'], ['40G', '100G'], ['1G', '10G']],
    ]) {
      const html = renderToStaticMarkup(React.createElement(OpticRateChoice, { source: 'ethernet1/5', target: 'ethernet1/6', rates, value: '', onChange() {} }))
      assert.ok(html.includes('Installed Target Optic Rate'))
      assert.ok(html.includes('Select optic rate'))
      assert.ok(html.includes('not written to candidate XML'))
      for (const rate of included) assert.ok(html.includes(`>${rate}</option>`))
      for (const rate of excluded) assert.ok(!html.includes(`>${rate}</option>`))
    }
    const mappings = ui.interfaceMappings({ 'ethernet1/5': 'ethernet1/6' }, {}, { 'ethernet1/5': '10G' })
    assert.deepEqual(mappings[0].target_settings, { optic_rate: '10G' })
    assert.deepEqual(ui.restoredOpticRates(JSON.parse(JSON.stringify(mappings))), { 'ethernet1/5': '10G' })
    assert.equal(ui.sameMappingDecisions(mappings, [{ ...mappings[0], target_settings: { optic_rate: '10G', link_speed: null } }]), true)
    assert.equal(ui.sameMappingDecisions(mappings, [{ ...mappings[0], target_settings: { optic_rate: '1G' } }]), false)
    assert.deepEqual(ui.interfaceMappings({ 'ethernet1/5': 'ethernet1/41' }, { 'ethernet1/5': '100G' }, {} )[0].target_settings, { link_speed: '100G' })
    await api.preview('synthetic-project', mappings)
    assert.deepEqual(JSON.parse(calls[0].init.body).mappings[0].target_settings, { optic_rate: '10G' })
    const preview = { overall_status: 'REVIEW_REQUIRED', impacts: [], findings: [], hardware_assessment: { effective_assignments: [], findings: [] } }
    const warning = { code: 'PHYSICAL_OPTIC_VERIFICATION_REQUIRED', message: 'Verify target optics', severity: 'WARNING' }
    assert.equal(ui.rowRenderScope({ target_render_support: 'SCOPED' }, optical, null, []), 'PENDING')
    assert.equal(ui.rowRenderScope({ target_render_support: 'SCOPED' }, optical, preview, [warning]), 'REVIEW')
    assert.equal(ui.findingLabel(warning), 'Verify Target Optic / Cabling')
    assert.equal(ui.findingLabel({ ...warning, code: 'TARGET_OPTIC_RATE_REQUIRED', severity: 'ERROR' }), 'Target Optic Rate Required')
    assert.equal(ui.rowRenderScope({ target_render_support: 'SCOPED' }, optical, preview, [{ ...warning, code: 'TARGET_OPTIC_RATE_REQUIRED', severity: 'ERROR' }]), 'BLOCKED')
  } finally { globalThis.fetch = previousFetch; await vite.close() }
})
