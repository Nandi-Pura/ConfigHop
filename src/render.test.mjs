import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

test('Firewall remains the default workflow and Switch has its own sections', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  try {
    const { default: App } = await vite.ssrLoadModule('/src/App.tsx')
    const { default: SwitchWorkspace } = await vite.ssrLoadModule('/src/SwitchWorkspace.tsx')
    const firewall = renderToStaticMarkup(React.createElement(App))
    const activeActions = { current: null }
    const switchPage = renderToStaticMarkup(React.createElement(SwitchWorkspace, { onDomainChange() {}, actionsRef: activeActions, onTitleChange() {} }))
    assert.ok(firewall.includes('ConfigHop'))
    assert.ok(!firewall.includes('brand-logo'))
    assert.ok(!firewall.includes('brand-mark'))
    assert.ok(!firewall.includes('ConfigMorph'))
    for (const heading of ['Migration Setup', 'Source Configuration', 'Source Inventory', 'Physical Interface Mapping', 'Migration Readiness', 'Migration Results']) assert.ok(firewall.includes(heading), heading)
    assert.ok(!firewall.includes('VLAN &amp; LAG Mapping'))
    for (const heading of ['Physical Port Mapping', 'VLAN &amp; LAG Mapping', 'IOS XE 17.12', 'AOS-CX 10.13', 'C9300-48P', 'CX 6300M 48G']) assert.ok(switchPage.includes(heading), heading)
    assert.ok(!switchPage.includes('Security Policies'))
    assert.ok(!switchPage.includes('NAT Rules'))
  } finally {
    await vite.close()
  }
})
