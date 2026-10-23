import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

test('Firewall starts in disclosed preview mode without a generated candidate', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  try {
    const { default: App } = await vite.ssrLoadModule('/src/App.tsx')
    const html = renderToStaticMarkup(React.createElement(App))
    assert.ok(html.includes('No mock candidate generated yet'))
    assert.ok(html.includes('UI Preview / Mock Data'))
    assert.ok(html.includes('Auto Map Suggestions'))
    assert.ok(html.includes('Frontend Fixture'))
    assert.ok(!html.includes('92%'))
    assert.ok(!html.includes('Verified Compatible'))
    assert.ok(html.includes('Backend Adapter Not Connected'))
    assert.ok(!html.includes('TARGET_PROFILE_RENDERING_NOT_VERIFIED'))
  } finally { await vite.close() }
})

test('Firewall API client sends mutation guard and candidate mappings to one versioned API root', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  const previous = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init })
    return new Response(JSON.stringify({ project_id: 'synthetic-project' }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }
  try {
    const { api, API_BASE } = await vite.ssrLoadModule('/src/api/client.ts')
    await api.createProject()
    await api.candidate('synthetic-project', [{ source_interface: 'ethernet1/12', target_interface: 'ethernet1/50' }], false)
    assert.equal(calls[0].url, `${API_BASE}/projects`)
    assert.equal(calls[0].init.headers['X-ConfigHop-Client'], 'web')
    assert.equal(calls[0].init.credentials, 'include')
    assert.equal(calls[1].url, `${API_BASE}/projects/synthetic-project/candidate`)
    assert.equal(calls[1].init.headers['X-ConfigHop-Client'], 'web')
    assert.deepEqual(JSON.parse(calls[1].init.body), { mappings: [{ source_interface: 'ethernet1/12', target_interface: 'ethernet1/50' }], allow_review: false })
  } finally { globalThis.fetch = previous; await vite.close() }
})

test('source API test and collect use the project endpoints with an explicit TLS input', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  const previous = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init })
    return new Response(JSON.stringify({ host: '192.0.2.10', port: 443, tested_at_utc: '2026-10-15T00:00:00Z', tls_verification: 'CA_VERIFIED', identity: { hostname: 'pa-source', serial: 'SERIAL1', model: 'PA-5410', panos_version: '11.1.4' } }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }
  try {
    const { api, API_BASE } = await vite.ssrLoadModule('/src/api/client.ts')
    const input = { host: '192.0.2.10', port: 443, api_key: 'memory-only-key', ca_certificate_pem: 'test-ca' }
    await api.testSourceConnection('synthetic-project', input)
    await api.collectSource('synthetic-project', input)
    assert.equal(calls[0].url, `${API_BASE}/projects/synthetic-project/source/connection/test`)
    assert.equal(calls[1].url, `${API_BASE}/projects/synthetic-project/source/collect`)
    assert.equal(calls[0].init.headers['X-ConfigHop-Client'], 'web')
    assert.deepEqual(JSON.parse(calls[0].init.body), input)
    assert.deepEqual(JSON.parse(calls[1].init.body), input)
    assert.equal(calls[0].init.credentials, 'include')
    assert.equal(calls[1].init.credentials, 'include')
  } finally { globalThis.fetch = previous; await vite.close() }
})

test('target review client binds connection, package review, and preflight requests to one project', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  const previous = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url, init })
    return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
  }
  try {
    const { api, API_BASE } = await vite.ssrLoadModule('/src/api/client.ts')
    const connection = { host: '192.0.2.20', port: 443, api_key: 'request-only-key', ca_certificate_pem: 'test-ca' }
    await api.testTargetConnection('project-1', connection)
    await api.collectTargetBaseline('project-1', { ...connection, expected_serial: 'TARGET1', expected_model: 'PA-5410' })
    await api.buildTargetPackage('project-1')
    await api.reviewTargetPackage('project-1', 'target-fw', ['TARGET_POLICY_ORDER_REVIEW_REQUIRED'])
    await api.checkTargetPreflight('project-1', { ...connection, expected_serial: 'TARGET1', expected_model: 'PA-5410', recovery_path_confirmed: true })
    await api.stageTargetPackage('project-1', { ...connection, expected_serial: 'TARGET1', expected_model: 'PA-5410', confirmed_target_hostname: 'target-fw' })
    await api.reconcileTargetStage('project-1', { ...connection, expected_serial: 'TARGET1', expected_model: 'PA-5410', confirmed_target_hostname: 'target-fw' })
    assert.deepEqual(calls.map((call) => call.url), [
      `${API_BASE}/projects/project-1/target/connection/test`,
      `${API_BASE}/projects/project-1/target/baseline/collect`,
      `${API_BASE}/projects/project-1/target/package/build`,
      `${API_BASE}/projects/project-1/target/package/review`,
      `${API_BASE}/projects/project-1/target/preflight/check`,
      `${API_BASE}/projects/project-1/target/stage`,
      `${API_BASE}/projects/project-1/target/stage/reconcile`,
    ])
    assert.ok(calls.every((call) => call.init.headers['X-ConfigHop-Client'] === 'web'))
    assert.deepEqual(JSON.parse(calls[3].init.body), { confirmed_target_hostname: 'target-fw', accepted_finding_codes: ['TARGET_POLICY_ORDER_REVIEW_REQUIRED'] })
    assert.equal(JSON.parse(calls[4].init.body).recovery_path_confirmed, true)
    assert.equal(JSON.parse(calls[5].init.body).confirmed_target_hostname, 'target-fw')
    assert.equal(JSON.parse(calls[6].init.body).expected_serial, 'TARGET1')
  } finally { globalThis.fetch = previous; await vite.close() }
})

test('target migration panel discloses the separate staging and commit boundaries before any request', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  try {
    const { default: TargetMigrationPanel } = await vite.ssrLoadModule('/src/TargetMigrationPanel.tsx')
    const html = renderToStaticMarkup(React.createElement(TargetMigrationPanel,
      { projectId: 'project-1', candidateAvailable: true, targetModel: 'PA-5410' }))
    assert.ok(html.includes('Direct-firewall, single-vsys workflow'))
    assert.ok(html.includes('Staging stops after full validation'))
    assert.ok(html.includes('commit requires a separate approval flow'))
    assert.ok(html.includes('Loading target baseline and package state'))
    assert.ok(!html.includes('Deploy to Target'))
  } finally { await vite.close() }
})

test('manual source provenance stays unverified in the dashboard', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  try {
    const { SourceProvenanceDetails } = await vite.ssrLoadModule('/src/FirewallApp.tsx')
    const html = renderToStaticMarkup(React.createElement(SourceProvenanceDetails, { provenance: {
      origin: 'FILE_UPLOADED', snapshot_kind: 'UNVERIFIED', sha256: 'a'.repeat(64),
      received_at_utc: '2026-10-15T00:00:00Z', serial: null, model: null, panos_version: null,
    } }))
    assert.ok(html.includes('Manual XML upload'))
    assert.ok(html.includes('Source device identity not verified'))
    assert.ok(html.includes('Snapshot type not verified'))
    assert.ok(html.includes('SHA-256'))
    assert.ok(html.includes('a'.repeat(64)))
    assert.ok(!html.includes('Running configuration'))
  } finally { await vite.close() }
})

test('raw source XML is masked until the operator explicitly reveals it', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  try {
    const { SourceXmlAccessPanel } = await vite.ssrLoadModule('/src/FirewallApp.tsx')
    const props = { available: true, sizeBytes: 128, lines: ['<config>sensitive-token</config>'], busy: null, error: '', onReveal() {}, onHide() {}, onDownload() {} }
    const hidden = renderToStaticMarkup(React.createElement(SourceXmlAccessPanel, { ...props, revealed: false }))
    assert.ok(hidden.includes('Raw XML hidden'))
    assert.ok(hidden.includes('Reveal source XML'))
    assert.ok(hidden.includes('Download source XML'))
    assert.ok(!hidden.includes('sensitive-token'))

    const revealed = renderToStaticMarkup(React.createElement(SourceXmlAccessPanel, { ...props, revealed: true }))
    assert.ok(revealed.includes('Raw source XML visible'))
    assert.ok(revealed.includes('Hide XML'))
    assert.ok(revealed.includes('sensitive-token'))
  } finally { await vite.close() }
})

test('Large XML viewer renders only visible lines', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  try {
    const { default: VirtualCodeViewer } = await vite.ssrLoadModule('/src/VirtualCodeViewer.tsx')
    const lines = Array.from({ length: 50000 }, (_, index) => `<entry name="${index}"/>`)
    const html = renderToStaticMarkup(React.createElement(VirtualCodeViewer, { lines }))
    assert.ok(html.includes('50000 lines'))
    assert.ok((html.match(/class="code-line"/g) || []).length < 100)
    assert.ok(!html.includes('name="49999"'))
  } finally { await vite.close() }
})

test('Verified hardware selector displays official context and manual PAN-OS trains', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  try {
    const { PlatformCard } = await vite.ssrLoadModule('/src/FirewallApp.tsx')
    const profile = { id: 'paloalto-pa-5410', model: 'PA-5410', series: 'PA-5400', profile_status: 'verified',
      evidence_ids: ['PAN-HW-PA5400-FRONT'], supported_panos_trains: ['10.2', '11.1'], interfaces: [], port_details: [] }
    const html = renderToStaticMarkup(React.createElement(PlatformCard, { title: 'Target Platform', eyebrow: 'Migration Destination', profile,
      profiles: [profile], selected: profile.id, onSelect() {}, train: '11.1', onTrain() {}, onEvidence() {} }))
    assert.ok(html.includes('Verified Profile'))
    assert.ok(html.includes('Evidence: 1 official sources'))
    assert.ok(html.includes('View Evidence'))
    assert.ok(html.includes('PA-5410'))
    assert.ok(html.includes('11.1'))
  } finally { await vite.close() }
})

test('Native QSFP speed selector requires an explicit 40G or 100G choice', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  try {
    const { NativeSpeedChoice } = await vite.ssrLoadModule('/src/FirewallApp.tsx')
    const html = renderToStaticMarkup(React.createElement(NativeSpeedChoice,
      { source: 'ethernet1/12', target: 'ethernet1/41', value: '', onChange() {} }))
    assert.ok(html.includes('Native QSFP'))
    assert.ok(html.includes('Native Link Speed'))
    assert.ok(html.includes('40G'))
    assert.ok(html.includes('100G'))
    assert.ok(html.includes('Select speed'))
    assert.ok(!html.includes('10G</option>'))
    assert.ok(!html.includes('25G</option>'))
    assert.ok(!html.includes('auto</option>'))
  } finally { await vite.close() }
})

test('Native QSFP target settings are sent to the compatibility API', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  const previous = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init })
    return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })
  }
  try {
    const { api } = await vite.ssrLoadModule('/src/api/client.ts')
    const mappings = [{ source_interface: 'ethernet1/12', target_interface: 'ethernet1/41', target_settings: { link_speed: '100G' } }]
    await api.compatibility('synthetic-project', mappings)
    assert.deepEqual(JSON.parse(calls[0].init.body), { mappings })
  } finally { globalThis.fetch = previous; await vite.close() }
})
