import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

test('Firewall starts without fabricated inventory or candidate and keeps manual mapping', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  try {
    const { default: App } = await vite.ssrLoadModule('/src/App.tsx')
    const html = renderToStaticMarkup(React.createElement(App))
    assert.ok(html.includes('No migration generated yet'))
    assert.ok(html.includes('No configuration loaded'))
    assert.ok(html.includes('Auto Map Suggestions'))
    assert.match(html, /disabled=""[^>]*>.*Auto Map Suggestions/)
    assert.ok(!html.includes('92%'))
    assert.ok(!html.includes('Verified Compatible'))
    assert.ok(html.includes('Synthetic Target FW (Development)') || html.includes('Select target profile'))
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
