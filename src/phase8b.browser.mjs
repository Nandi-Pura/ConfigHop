// Run with node --test src/phase8b.browser.mjs and an installed Playwright module.
import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'
import { switchBrowserServer } from './switchBrowserServer.mjs'

let server, browser, url, backendServer
before(async () => {
  const { chromium } = await import(process.env.CONFIGHOP_PLAYWRIGHT_MODULE || 'playwright')
  backendServer = await switchBrowserServer()
  server = backendServer.server
  url = backendServer.url
  browser = await chromium.launch({ headless: true, executablePath: process.env.CONFIGHOP_CHROMIUM_EXECUTABLE })
  await mkdir('artifacts/phase8b', { recursive: true })
})
after(async () => { await browser?.close(); await backendServer?.close() })

test('Switch UI parses configured declarations, prevents duplicate slots and blocks unresolved output', async t => {
  const page = await browser.newPage({ viewport: { width: 1680, height: 980 } })
  t.after(() => page.close())
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto(url)
  await page.getByLabel('Domain').selectOption('Switch')
  const source = 'hostname sw\ninterface GigabitEthernet1/0/1\n description user\ninterface GigabitEthernet1/0/2\ninterface Port-channel10\ninterface Vlan99'
  await page.locator('.switch-workspace input[type=file]').setInputFiles({ name: 'synthetic-switch.cfg', mimeType: 'text/plain', buffer: Buffer.from(source) })
  await page.getByLabel('Target interface for GigabitEthernet1/0/1').waitFor()
  await page.getByText('Target capability and translation report', { exact: true }).click()
  await page.getByLabel('Optional target capability').selectOption('hpe-aruba-jl663a')
  assert.equal(await page.getByText('Configured physical declarations').locator('..').locator('b').innerText(), '2')
  assert.equal(await page.locator('.locked-interface-row').count(), 4)
  const first = page.getByLabel('Logical target slot for GigabitEthernet1/0/1')
  const second = page.getByLabel('Logical target slot for GigabitEthernet1/0/2')
  await first.selectOption('24')
  assert.equal(await second.locator('option[value="24"]').count(), 0)
  assert.equal(await page.locator('.locked-port-grid .assigned').count(), 1)
  assert.ok(await page.getByRole('button', { name: 'Export', exact: true }).isDisabled())
  await page.getByRole('button', { name: 'Expand configuration preview' }).click()
  assert.equal(await page.getByRole('dialog', { name: 'Expanded configuration preview' }).count(), 1)
  await page.keyboard.press('Escape')
  assert.equal(await page.getByRole('dialog', { name: 'Expanded configuration preview' }).count(), 0)
  await page.screenshot({ path: 'artifacts/phase8b/switch-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: 'artifacts/phase8b/switch-narrow.png', fullPage: true })
  await page.getByLabel('Target vendor').selectOption('Cisco')
  assert.match(await page.getByLabel('Target Network OS').locator('option').first().innerText(), /IOS-XE/)
  assert.equal(await page.locator('.locked-port-grid .assigned').count(), 0)
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.evaluate(() => navigator.clipboard.writeText('interface Gi1/0/5'))
  await page.getByRole('button', { name: 'Paste from Clipboard' }).click()
  await page.getByLabel('Target interface for GigabitEthernet1/0/5').waitFor()
  assert.equal(await page.locator('.locked-interface-row').count(), 1)
  assert.equal(await page.getByText('Configured physical declarations').locator('..').locator('b').innerText(), '1')
  assert.deepEqual(errors, [])
})

test('Firewall UI preserves backend controls and current-candidate export gate', async t => {
  const page = await browser.newPage({ viewport: { width: 1680, height: 980 } })
  t.after(() => page.close())
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.route('**/api/v1/**', route => route.fulfill({ json: [] }))
  await page.goto(url)
  await page.getByRole('heading', { name: 'Firewall Migration' }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Export Candidate' }).isDisabled(), true)
  assert.equal(await page.getByRole('button', { name: 'Expand configuration preview' }).count(), 1)
  await page.getByRole('button', { name: 'Expand configuration preview' }).click()
  await page.getByRole('dialog', { name: 'Expanded configuration preview' }).getByRole('button', { name: 'Restore' }).click()
  await page.screenshot({ path: 'artifacts/phase8b/firewall-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: 'artifacts/phase8b/firewall-narrow.png', fullPage: true })
  assert.deepEqual(errors, [])
})

test('supported Firewall preview refreshes automatically and invalidates the old export', { timeout: 30000 }, async t => {
  const page = await browser.newPage({ viewport: { width: 1680, height: 980 } })
  t.after(() => page.close())
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  const profile = { id: 'synthetic-profile', model: 'Synthetic PA', vendor: 'Palo Alto Networks', profile_status: 'verified', target_render_support: 'SUPPORTED', evidence_ids: [], supported_panos_trains: ['11.1'], interfaces: ['ethernet1/1', 'ethernet1/2', 'ethernet1/3'], port_details: ['ethernet1/1', 'ethernet1/2', 'ethernet1/3'].map(name => ({ name, availability: 'NATIVE', candidate_support: 'SUPPORTED', required_condition: 'NONE', speed_capabilities: ['1G'], media_capabilities: ['RJ45'], evidence_ids: [] })) }
  const summary = { submitted_mappings: 1, valid_mappings: 1, derived_subinterface_mappings: 0, zone_reference_changes: 0, virtual_router_reference_changes: 0, static_route_reference_changes: 0, nat_reference_changes: 0, aggregate_membership_changes: 0, review_findings: 0, blocking_findings: 0 }
  const source = { name: 'ethernet1/1', mode: 'layer3', link_state: null, link_speed: null, link_duplex: null, link_speed_explicit: false, link_duplex_explicit: false, ip_addresses: [], management_profile: null, aggregate_group: null, subinterface_count: 0, subinterface_names: [], zone_names: [], dependency_count: 0, dependency_summary: { zone_references: 0, virtual_router_references: 0, static_route_references: 0, nat_references: 0, aggregate_memberships: 0, child_count: 0 } }
  let target = 'ethernet1/2', releaseCandidate, candidateRequested
  const calls = []
  const candidateGate = new Promise(resolve => { releaseCandidate = resolve })
  const candidateStarted = new Promise(resolve => { candidateRequested = resolve })
  await page.route('**/api/v1/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname.replace('/api/v1', '')
    calls.push(`${req.method()} ${path}`)
    const body = req.headers()['content-type'] === 'application/json' ? req.postDataJSON() : null
    if (path === '/hardware-profiles') return route.fulfill({ json: [profile] })
    if (path.startsWith('/hardware-profiles/')) return route.fulfill({ json: profile })
    if (path === '/evidence') return route.fulfill({ json: [] })
    if (path.endsWith('/inventory')) return route.fulfill({ json: { platform: { vendor: 'Palo Alto Networks', detail_version: '11.1' }, summary: { physical_interfaces: 1, parser_warnings: 0 }, physical_interfaces: [source], parser_warnings: [] } })
    if (path.endsWith('/preview')) {
      const decisions = body?.mappings ?? [{ source_interface: 'ethernet1/1', target_interface: target }]
      target = decisions[0]?.target_interface || 'ethernet1/1'
      const assessment = { status: 'READY', source_version_status: 'SUPPORTED', target_version_status: 'SUPPORTED', findings: [], effective_assignments: [] }
      return route.fulfill({ json: { mappings: decisions, impacts: [], findings: [], summary, status: 'READY', overall_status: 'READY', platform_assessment: assessment, hardware_assessment: assessment } })
    }
    if (path.endsWith('/candidate') && req.method() === 'POST') {
      candidateRequested()
      await candidateGate
      return route.fulfill({ json: { status: 'READY', candidate_available: true, candidate_size_bytes: 42, findings: [], summary, semantic_diff: { changes: [] }, validation: { valid: true, candidate_parse_ok: true, expected_inventory_match: true, preservation_audit_ok: true, operations_applied: 0 }, plan: { operations: [] } } }).catch(() => {})
    }
    if (path.endsWith('/candidate/download')) return route.fulfill({ body: `<config><target>${target}</target></config>`, contentType: 'application/xml' })
    if (path.endsWith('/source') && req.method() === 'GET') return route.fulfill({ body: '<config/>', contentType: 'application/xml' })
    return route.fulfill({ json: { project_id: 'synthetic-session', source_available: true, source_filename: 'synthetic.xml', source_size_bytes: 9, source_profile_id: profile.id, target_profile_id: profile.id, source_panos_train: '11.1', target_panos_train: '11.1', preview_available: true, candidate_available: false } })
  })
  await page.goto(url)
  await page.evaluate(() => localStorage.setItem('confighop-project', JSON.stringify({ project_id: 'synthetic-session', project_name: 'Synthetic supported path', mappings: [{ source_interface: 'ethernet1/1', target_interface: 'ethernet1/2' }] })))
  await page.getByRole('button', { name: 'Load Project', exact: true }).click()
  try { await Promise.race([candidateStarted, new Promise((_, reject) => setTimeout(() => reject(new Error(`Candidate not requested: ${calls.join(', ')}; UI: ${page.url()}`)), 5000))]) }
  catch (error) { releaseCandidate(); throw error }
  assert.ok(await page.getByRole('button', { name: 'Export Candidate' }).isDisabled())
  releaseCandidate()
  await page.getByRole('button', { name: 'Export Candidate' }).waitFor()
  await page.locator('.live-editor .syntax-tag').first().waitFor()
  assert.equal(await page.getByRole('button', { name: 'Export Candidate' }).isDisabled(), false)
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.locator('.live-editor').getByRole('button', { name: 'Copy All' }).click()
  assert.match(await page.evaluate(() => navigator.clipboard.readText()), /ethernet1\/2/)
  await page.screenshot({ path: 'artifacts/phase8b/firewall-synthetic-candidate.png', fullPage: true })
  await page.getByLabel('Target interface for ethernet1/1', { exact: true }).selectOption('ethernet1/3')
  assert.ok(await page.getByRole('button', { name: 'Export Candidate' }).isDisabled())
  await page.locator('.live-editor').getByText('ethernet1/3', { exact: false }).first().waitFor()
  await page.getByRole('button', { name: 'Export Candidate', exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Export Candidate' }).isDisabled(), false)
  assert.deepEqual(errors, [])
})
