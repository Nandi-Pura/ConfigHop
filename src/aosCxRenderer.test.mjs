import test from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'

test('AOS-CX renderer is deterministic, traceable, fail-closed, and secret-free', async () => {
  const vite = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
  try {
    const { renderAosCx } = await vite.ssrLoadModule('/src/switch/render/aosCx.ts')
    const selection = { hardware: { id: 'cx-test', hardwareRole: 'fixed-switch', ports: [{ id: '1/1/1' }, { id: '1/1/2' }], capabilities: { vlan: 'SUPPORTED', accessVlan: 'SUPPORTED', trunk: 'SUPPORTED', nativeVlan: 'SUPPORTED' } }, os: { id: 'aos-cx-test', train: '10.16', lifecycleStatus: 'ACTIVE' }, compatibility: { status: 'READY', evidenceIds: ['ARUBA-EVD-CX6400V2-1016'] } }
    const intent = { targetPlatform: { hardwareId: 'cx-test', hardwareModel: 'Test', productNumber: 'TEST', osTrain: '10.16', osId: 'aos-cx-test', compatibilityStatus: 'READY' }, vlans: [{ vlanId: 20, name: 'Users', status: 'READY', sourceRefs: [{ startLine: 2 }] }, { vlanId: 10, name: 'Admin', status: 'READY', sourceRefs: [{ startLine: 1 }] }], interfaces: [{ targetInterfaceId: '1/1/2', sourceInterfaceId: 'Gi1/0/2', adminState: 'down', role: 'access', accessVlan: 20, status: 'READY', sourceRefs: [{ startLine: 4 }] }, { targetInterfaceId: '1/1/1', sourceInterfaceId: 'Gi1/0/1', adminState: 'up', role: 'trunk', trunkNativeVlan: 10, trunkAllowedVlans: [{ start: 10, end: 20 }], status: 'READY', sourceRefs: [{ startLine: 3 }] }], lags: [], svis: [], acls: [], vrfs: [] }
    const before = structuredClone(intent)
    const first = renderAosCx(intent, selection)
    assert.equal(first.configuration, 'vlan 10\n    name Admin\n\nvlan 20\n    name Users\n\ninterface 1/1/1\n    no shutdown\n    vlan trunk native 10\n    vlan trunk allowed 10-20\n\ninterface 1/1/2\n    shutdown\n    vlan access 20')
    assert.deepEqual(renderAosCx(intent, selection), first)
    assert.deepEqual(intent, before)
    assert.deepEqual(first.emitted[0].sourceRefs, [{ startLine: 1 }])
    assert.ok(!JSON.stringify(first).match(/secret|password/i))

    for (const status of ['UNKNOWN', 'REVIEW_REQUIRED', 'UNSUPPORTED']) {
      const blocked = renderAosCx({ ...intent, vlans: [{ ...intent.vlans[0], status }] }, selection)
      assert.ok(blocked.findings.some((finding) => finding.code === 'RENDER_BLOCKED'))
    }
    const unavailable = renderAosCx(intent, { ...selection, compatibility: { status: 'UNKNOWN', evidenceIds: [] } })
    assert.equal(unavailable.blocked, true)
    assert.equal(unavailable.configuration, '')
    assert.equal(renderAosCx(intent).blocked, true)
    for (const [hardwareRole, lifecycleStatus] of [['management-module', 'ACTIVE'], ['fixed-switch', 'END_OF_SUPPORT']]) {
      const blockedTarget = renderAosCx(intent, { ...selection, hardware: { ...selection.hardware, hardwareRole }, os: { ...selection.os, lifecycleStatus } })
      assert.equal(blockedTarget.blocked, true)
      assert.equal(blockedTarget.configuration, '')
    }
    const visible = renderAosCx({ ...intent, acls: [{ name: 'SECRET-ACL', status: 'UNSUPPORTED', sourceRefs: [{ startLine: 9 }] }] }, selection)
    assert.ok(visible.findings.some((finding) => finding.message.includes('acls') && finding.sourceRefs[0].startLine === 9))
  } finally { await vite.close() }
})
