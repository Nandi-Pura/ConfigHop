import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

let vite, ui
before(async () => {
  vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  ui = await vite.ssrLoadModule('/src/interfaceMappingSuggestions.ts')
})
after(async () => { await vite?.close() })

const port = (name, media = ['SFP', 'SFP_PLUS'], rates = ['1G', '10G'], extra = {}) => ({ name, media_capabilities: media, speed_capabilities: rates, availability: 'NATIVE', candidate_support: 'SUPPORTED', required_condition: 'NONE', evidence_ids: [], parent_interface: null, ...extra })
const profile = (ports, support = 'SUPPORTED') => ({ port_details: ports, target_render_support: support })
const source = { name: 'ethernet1/5' }
const sourceProfile = profile([port(source.name)])
const rank = (ports, extra = {}) => ui.rankTargetInterfaces({ source, sourceProfile, targetProfile: profile(ports), mappings: [], sources: [source], preview: null, ...extra })

test('exact media and rates rank before overlapping capabilities, with natural ties', () => {
  const ports = [port('ethernet1/10'), port('ethernet1/3', ['SFP'], ['1G']), port('ethernet1/2'), port('ethernet1/1', ['RJ45'], ['1G'])]
  const result = rank(ports)
  assert.deepEqual(result.map(x => x.port.name), ['ethernet1/2', 'ethernet1/10', 'ethernet1/3', 'ethernet1/1'])
  assert.equal(result[0].fit.status, 'COMPATIBLE')
  assert.equal(result[2].fit.status, 'COMPATIBLE')
  assert.equal(result[3].fit.status, 'MISMATCH')
  assert.equal(result[3].group, 'OTHER AVAILABLE')
  assert.deepEqual(rank([...ports].reverse()), result)
  assert.deepEqual(rank(ports), result)
})

test('rate overlap is required and exact rate capability ranks before partial overlap', () => {
  const result = rank([port('ethernet1/1', undefined, ['1G']), port('ethernet1/2'), port('ethernet1/3', undefined, ['40G'])])
  assert.equal(result[0].port.name, 'ethernet1/2')
  assert.deepEqual(result[1].fit.sharedRates, ['1G'])
  assert.equal(result[2].fit.status, 'MISMATCH')
  assert.notEqual(result[2].group, 'RECOMMENDED')
})

test('missing source profile or empty metadata remains unknown without recommendations', () => {
  for (const missing of [null, profile([]), profile([port(source.name, [])]), profile([port(source.name, undefined, [])])]) {
    const result = rank([port('ethernet1/5')], { sourceProfile: missing })
    assert.equal(result[0].fit.status, 'UNKNOWN')
    assert.equal(result[0].group, 'OTHER AVAILABLE')
  }
  for (const unknown of [port('ethernet1/1', []), port('ethernet1/1', undefined, [])]) {
    assert.equal(rank([unknown])[0].fit.status, 'UNKNOWN')
  }
})

test('copper and optics never imply a direct hardware match in either direction', () => {
  for (const [from, to] of [[['RJ45'], ['SFP']], [['SFP'], ['RJ45']]]) {
    const result = rank([port('ethernet1/1', to, ['1G'])], { sourceProfile: profile([port(source.name, from, ['1G'])]) })
    assert.equal(result[0].fit.status, 'MISMATCH')
    assert.equal(result[0].group, 'OTHER AVAILABLE')
    assert.equal(result[0].selectable, true)
  }
})

test('explicit and preserved assignments are not recommended, own selection stays eligible', () => {
  const mappings = [{ source_interface: 'ethernet1/8', target_interface: 'ethernet1/2' }, { source_interface: source.name, target_interface: 'ethernet1/3', target_settings: { optic_rate: '10G' } }]
  const before = structuredClone(mappings)
  const result = rank([port('ethernet1/2'), port('ethernet1/3'), port('ethernet1/9')], { mappings, sources: [source, { name: 'ethernet1/8' }, { name: 'ethernet1/9' }] })
  assert.equal(result.find(x => x.port.name === 'ethernet1/3').group, 'RECOMMENDED')
  for (const name of ['ethernet1/2', 'ethernet1/9']) {
    assert.equal(result.find(x => x.port.name === name).group, 'OTHER AVAILABLE')
    assert.equal(result.find(x => x.port.name === name).assigned, true)
    assert.equal(result.find(x => x.port.name === name).selectable, true)
  }
  assert.deepEqual(mappings, before)
})

test('unqualified and breakout choices keep existing analysis selection rules', () => {
  const ports = [port('ethernet1/2', undefined, undefined, { candidate_support: 'BLOCKED', required_condition: 'TARGET_LINK_SERIALIZATION_UNVERIFIED' }), port('ethernet1/3', undefined, undefined, { availability: 'BREAKOUT_CHILD', candidate_support: 'BLOCKED', required_condition: 'BREAKOUT_MODE' })]
  const result = rank(ports, { targetProfile: profile(ports, 'SCOPED') })
  assert.ok(result.every(x => x.group === 'NOT QUALIFIED / UNAVAILABLE'))
  assert.equal(result[0].selectable, true)
  assert.equal(result[1].selectable, false)
  assert.ok(rank([port('ethernet1/1')], { targetProfile: profile([port('ethernet1/1')], 'ANALYSIS_ONLY') }).every(x => x.group !== 'RECOMMENDED'))
})

test('native and better qualified conditions break otherwise equal capability ties', () => {
  const result = rank([port('ethernet1/1', undefined, undefined, { availability: 'NATIVE_CONDITIONAL', candidate_support: 'CONDITIONAL', required_condition: 'MANUAL_NATIVE_PORT_SPEED' }), port('ethernet1/2', undefined, undefined, { candidate_support: 'CONDITIONAL', required_condition: 'OPTIC_CONTEXT_LINK_FIELDS_ABSENT' }), port('ethernet1/3')])
  assert.deepEqual(result.map(x => x.port.name), ['ethernet1/3', 'ethernet1/2', 'ethernet1/1'])
})

test('current backend blockers prevent a recommendation without disabling analysis selection', () => {
  const preview = { status: 'BLOCKED', impacts: [], findings: [], hardware_assessment: { effective_assignments: [{ source_interface: source.name, target_interface: 'ethernet1/2', status: 'BLOCKED', findings: [] }], findings: [] } }
  const result = rank([port('ethernet1/2'), port('ethernet1/3')], { preview })
  assert.equal(result.find(x => x.port.name === 'ethernet1/2').group, 'NOT QUALIFIED / UNAVAILABLE')
  assert.equal(result.find(x => x.port.name === 'ethernet1/2').selectable, true)
  assert.equal(ui.backendMappingStatus(source.name, 'ethernet1/2', preview), 'BLOCKED')
  assert.equal(ui.backendMappingStatus(source.name, 'ethernet1/3', null), 'Pending backend validation')
})

test('global backend blockers and review remain visible even for matching hardware', () => {
  for (const status of ['BLOCKED', 'REVIEW_REQUIRED', 'READY']) {
    const preview = { status, overall_status: status, findings: [], impacts: [] }
    assert.equal(ui.backendMappingStatus(source.name, 'ethernet1/1', preview), status)
  }
})

test('grouped selector preserves selected, unknown, conflicting and analysis-only choices', async () => {
  const { TargetInterfaceChoice } = await vite.ssrLoadModule('/src/FirewallApp.tsx')
  const ports = [port('ethernet1/2'), port('ethernet1/3', ['RJ45']), port('ethernet1/4', undefined, undefined, { candidate_support: 'BLOCKED', required_condition: 'TARGET_LINK_SERIALIZATION_UNVERIFIED' }), port('ethernet1/6', undefined, undefined, { candidate_support: 'BLOCKED', required_condition: 'BREAKOUT_MODE' })]
  const suggestions = rank(ports, { targetProfile: profile(ports, 'SCOPED') })
  let changed = false
  for (const value of ['ethernet1/3', 'ethernet1/4', 'ethernet1/99']) {
    const props = { source: source.name, value, suggestions, disabled: false, showSuggestions: true, onChange() { changed = true } }
    const html = renderToStaticMarkup(React.createElement(TargetInterfaceChoice, props))
    for (const group of ui.suggestionGroups) assert.ok(html.includes(`label="${group}"`))
    assert.match(html, new RegExp(`value="${value}" selected=""`))
    assert.ok(html.includes(`aria-label="Target interface for ${source.name}"`))
    assert.ok(html.includes('SFP/SFP+ | 1G/10G'))
    assert.ok(html.includes('Suggested: ethernet1/2'))
    assert.ok(!html.includes('READY'))
    assert.ok(!html.includes('value="ethernet1/4" disabled'))
    assert.ok(html.includes('value="ethernet1/6" disabled'))
  }
  assert.equal(changed, false)
})

test('fixed and mixed optic controls require explicit action and reject unsupported values', async () => {
  const { OpticRateChoice } = await vite.ssrLoadModule('/src/FirewallApp.tsx')
  const { interfaceMappings } = await vite.ssrLoadModule('/src/scopedRenderingUI.ts')
  for (const rates of [['40G'], ['1G', '10G'], ['40G', '100G']]) {
    const decisions = []
    const props = { source: source.name, target: 'ethernet1/21', rates, value: '', onChange: rate => decisions.push(rate) }
    const element = OpticRateChoice(props)
    const select = element.props.children[0].props.children[1]
    const html = renderToStaticMarkup(element)
    assert.ok(html.includes('value="" selected=""'))
    assert.ok(html.includes('NOT_VERIFIED'))
    assert.equal(decisions.length, 0)
    assert.equal(interfaceMappings({ [source.name]: props.target }, {}, {})[0].target_settings, undefined)
    select.props.onChange({ target: { value: '25G' } })
    assert.equal(decisions.length, 0)
    select.props.onChange({ target: { value: rates[0] } })
    assert.deepEqual(decisions, [rates[0]])
    const confirmed = renderToStaticMarkup(React.createElement(OpticRateChoice, { ...props, value: rates[0] }))
    assert.ok(confirmed.includes(`${rates[0]} — operator confirmed`))
    assert.ok(confirmed.includes('NOT_VERIFIED'))
  }
})

test('source explicit auto, manual speed and duplex never override backend blockers', () => {
  for (const fields of [{ link_speed: 'auto', link_speed_explicit: true }, { link_speed: '1000', link_speed_explicit: true }, { link_duplex: 'full', link_duplex_explicit: true }]) {
    const finding = { code: 'TARGET_AUTO_ONLY_LINK_SERIALIZATION_UNVERIFIED', severity: 'ERROR', message: 'Explicit source link field is blocked', source_interface: source.name, target_interface: 'ethernet1/1' }
    const preview = { status: 'BLOCKED', impacts: [], findings: [finding] }
    const result = rank([port('ethernet1/1', ['RJ45'], ['1G'])], { source: { ...source, ...fields }, sourceProfile: profile([port(source.name, ['RJ45'], ['1G'])]), preview })
    assert.equal(result[0].fit.status, 'COMPATIBLE')
    assert.equal(result[0].group, 'NOT QUALIFIED / UNAVAILABLE')
    assert.equal(ui.backendMappingStatus(source.name, 'ethernet1/1', preview), 'BLOCKED')
  }
})
