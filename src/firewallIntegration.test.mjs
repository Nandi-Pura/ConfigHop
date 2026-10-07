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
    assert.equal(calls[1].url, `${API_BASE}/projects/synthetic-project/candidate`)
    assert.equal(calls[1].init.headers['X-ConfigHop-Client'], 'web')
    assert.deepEqual(JSON.parse(calls[1].init.body), { mappings: [{ source_interface: 'ethernet1/12', target_interface: 'ethernet1/50' }], allow_review: false })
  } finally { globalThis.fetch = previous; await vite.close() }
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
