import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

test('Firewall remains the default workflow and Switch has its own sections', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  try {
    const { default: App } = await vite.ssrLoadModule('/src/App.tsx')
    const { default: MockWorkspace, RawComparison, rawComparisonRows } = await vite.ssrLoadModule('/src/MockWorkspace.tsx')
    const firewall = renderToStaticMarkup(React.createElement(App))
    const activeActions = { current: null }
    const switchPage = renderToStaticMarkup(React.createElement(MockWorkspace, { domain: 'Switch', onDomainChange() {}, onBackend() {}, actionsRef: activeActions, onTitleChange() {} }))
    assert.ok(firewall.includes('ConfigHop'))
    assert.ok(!firewall.includes('brand-logo'))
    assert.ok(!firewall.includes('brand-mark'))
    assert.ok(!firewall.includes('ConfigMorph'))
    for (const heading of ['Migration Setup', 'Source Configuration', 'Source Inventory', 'Interface &amp; Zone Mapping', 'Semantic Mapping', 'Migration Readiness', 'Migration Results']) assert.ok(firewall.includes(heading), heading)
    for (const heading of ['Interface Mapping', 'Semantic Mapping', 'IOS-XE 17.12', 'AOS-CX 10.15', 'C9300-48P', 'CX 6300M 48G', 'Huawei']) assert.ok(switchPage.includes(heading), heading)
    assert.ok(firewall.includes('Conflicts (0)'))
    assert.ok(switchPage.includes('Conflicts (0)'))
    assert.ok(switchPage.includes('Chassis View'))
    assert.ok(firewall.includes('>Hardware</button>'))
    assert.ok(!switchPage.includes('Security Policies'))
    assert.ok(!switchPage.includes('NAT Rules'))
    const raw = renderToStaticMarkup(React.createElement(RawComparison, { source: 'same\nold', candidate: 'same\nnew\nadded', sourceLabel: 'Source', targetLabel: 'Target' }))
    for (const control of ['Search raw comparison', 'Raw comparison filter', 'Changed', 'Added', 'Removed', 'Expanded', 'Copy All']) assert.ok(raw.includes(control), control)
    assert.deepEqual(rawComparisonRows('same\nold', 'same\nnew\nadded', 'Changed', '').map((row) => row.a), ['old'])
    assert.deepEqual(rawComparisonRows('same\nold', 'same\nnew\nadded', 'Added', '').map((row) => row.b), ['new', 'added'])
    assert.deepEqual(rawComparisonRows('same\nold', 'same\nnew\nadded', 'Removed', '').map((row) => row.a), ['old'])
    assert.equal(rawComparisonRows('same\nold', 'same\nnew\nadded', 'All', 'old').length, 1)
  } finally {
    await vite.close()
  }
})
