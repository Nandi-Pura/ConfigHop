// Run with node --test src/firewallAsync.browser.mjs. Use an installed Playwright
// via CONFIGHOP_PLAYWRIGHT_MODULE and, optionally, CONFIGHOP_CHROMIUM_EXECUTABLE.
import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'

let server, browser, url
before(async () => {
  const { chromium } = await import(process.env.CONFIGHOP_PLAYWRIGHT_MODULE || 'playwright')
  server = await createServer({ configFile: false, server: { host: '127.0.0.1', port: 0 }, logLevel: 'silent' })
  await server.listen()
  url = `http://127.0.0.1:${server.httpServer.address().port}`
  browser = await chromium.launch({ headless: true, executablePath: process.env.CONFIGHOP_CHROMIUM_EXECUTABLE })
})
after(async () => { await browser?.close(); await server?.close() })

const port = (name, optical = false) => ({ name, media_capabilities: optical ? ['SFP', 'SFP_PLUS'] : ['RJ45'], speed_capabilities: optical ? ['1G', '10G'] : ['10M', '100M', '1G'], availability: 'NATIVE', candidate_support: 'CONDITIONAL', required_condition: optical ? 'OPTIC_CONTEXT_LINK_FIELDS_ABSENT' : 'AUTO_ONLY_LINK_FIELDS_ABSENT', evidence_ids: [] })
const profiles = ['source-fixture', 'target-fixture'].map(id => ({ id, model: `Synthetic ${id}`, profile_status: 'verified', target_render_support: 'SCOPED', evidence_ids: [], supported_panos_trains: ['11.0', '11.1'], port_details: [port('ethernet1/1'), port('ethernet1/2'), ...[5, 6, 7, 8].map(n => port(`ethernet1/${n}`, true))] }))
const mappings = [{ source_interface: 'ethernet1/1', target_interface: 'ethernet1/2' }, { source_interface: 'ethernet1/5', target_interface: 'ethernet1/6', target_settings: { optic_rate: '10G' } }]
const summary = { submitted_mappings: 2, valid_mappings: 2, derived_subinterface_mappings: 0, zone_reference_changes: 0, virtual_router_reference_changes: 0, static_route_reference_changes: 0, nat_reference_changes: 0, aggregate_membership_changes: 0, review_findings: 1, blocking_findings: 0 }
const inventory = { platform: { vendor: 'Palo Alto Networks', detail_version: '11.1.4' }, summary: { physical_interfaces: 2, parser_warnings: 0 }, parser_warnings: [], physical_interfaces: ['ethernet1/1', 'ethernet1/5'].map(name => ({ name, mode: 'layer3', ip_addresses: [], zone_names: [], subinterface_count: 0, aggregate_group: null, dependency_summary: { zone_references: 0, virtual_router_references: 0, static_route_references: 0, nat_references: 0 } })) }
function previewFor(decisions) {
  const status = decisions.some(m => m.source_interface === 'ethernet1/5' && !m.target_settings?.optic_rate) ? 'BLOCKED' : 'REVIEW_REQUIRED'
  return { mappings: decisions, status, overall_status: status, summary, impacts: [], findings: [], platform_assessment: { status: 'READY', source_version_status: 'SUPPORTED', target_version_status: 'SUPPORTED', findings: [] }, hardware_assessment: { status, findings: [], effective_assignments: decisions.map(m => ({ ...m, status, findings: [], evidence_ids: [] })) } }
}
const candidate = { status: 'REVIEW_REQUIRED', candidate_available: true, candidate_size_bytes: 9, findings: [], summary, semantic_diff: { changes: [] }, validation: { candidate_parse_ok: true, expected_inventory_match: true, preservation_audit_ok: true, operations_applied: 0 }, plan: { operations: [] } }

async function workspace(t) {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
  page.setDefaultTimeout(5000)
  t.after(() => page.close())
  const errors = [], requests = [], gates = []
  let preview = previewFor(mappings), projectNumber = 0, sourceId = profiles[0].id, targetId = profiles[1].id
  page.on('pageerror', error => errors.push(error.message))
  page.on('dialog', dialog => dialog.accept())
  await page.route('**/api/v1/**', async route => {
    const req = route.request(), path = new URL(req.url()).pathname.replace('/api/v1', '')
    const body = req.headers()['content-type'] === 'application/json' ? req.postDataJSON() : null
    requests.push({ path, body, method: req.method() })
    let result = {}
    if (path === '/hardware-profiles') result = profiles
    else if (path.startsWith('/hardware-profiles/')) result = profiles.find(p => p.id === path.split('/').at(-1))
    else if (path === '/evidence') result = []
    else if (path.endsWith('/inventory')) result = inventory
    else if (path.endsWith('/source-profile')) sourceId = body.profile_id
    else if (path.endsWith('/target-profile')) targetId = body.profile_id
    else if (path.endsWith('/preview')) { if (body) preview = previewFor(body.mappings); result = preview }
    else if (path.endsWith('/candidate')) result = candidate
    else if (path.endsWith('/source') && req.method() === 'PUT') result = { filename: 'replacement.xml', size_bytes: 9 }
    else if (path === '/projects' && req.method() === 'POST') result = { project_id: `created-${++projectNumber}` }
    else result = { project_id: 'synthetic-session', source_available: true, source_filename: 'synthetic.xml', source_size_bytes: 9, source_profile_id: sourceId, target_profile_id: targetId, source_panos_train: '11.1', target_panos_train: '11.1', preview_available: true, candidate_available: true, candidate_size_bytes: 9 }
    const index = gates.findIndex(g => path.endsWith(g.path) && req.method() === g.method)
    if (index >= 0) {
      const gate = gates.splice(index, 1)[0]
      gate.enter()
      await gate.pending
      if (gate.fail) return route.fulfill({ status: 500, json: { error: { code: 'SYNTHETIC_ERROR', message: 'Stale request error' } } }).catch(() => {})
    }
    if ((path.endsWith('/source') && req.method() === 'GET') || path.endsWith('/candidate/xml')) return route.fulfill({ body: '<config/>', contentType: 'application/xml' })
    await route.fulfill({ json: result }).catch(() => {})
  })
  await page.goto(url, { timeout: 20000 })
  await page.evaluate(mappings => localStorage.setItem('confighop-project', JSON.stringify({ project_id: 'synthetic-session', project_name: 'Synthetic async review', mappings })), mappings)
  await page.getByRole('button', { name: 'Load Project', exact: true }).click()
  const target = page.getByLabel('Target interface for ethernet1/5', { exact: true })
  await target.waitFor()
  assert.equal(await target.inputValue(), 'ethernet1/6')
  t.after(() => assert.deepEqual(errors, []))
  const hold = (path, method = 'POST', fail = false) => {
    let enter, release
    const started = new Promise(resolve => { enter = resolve })
    const pending = new Promise(resolve => { release = resolve })
    gates.push({ path, method, fail, enter, pending })
    return { started, release }
  }
  return { page, target, hold, requests }
}

test('replacement source invalidates candidate immediately, including a failed upload', async t => {
  const { page, hold } = await workspace(t)
  const upload = hold('/source', 'PUT', true)
  await page.locator('input[type=file]').setInputFiles({ name: 'replacement.xml', mimeType: 'application/xml', buffer: Buffer.from('<config/>') })
  await upload.started
  assert.equal(await page.getByText('No migration generated yet', { exact: true }).count(), 1)
  upload.release()
  await page.getByRole('alert').waitFor()
  assert.equal(await page.getByText('No migration generated yet', { exact: true }).count(), 1)
  assert.ok(await page.getByRole('button', { name: 'Generate Migration', exact: true }).isDisabled())
})

for (const action of ['Source train', 'Load Project', 'Target mapping']) test(`cancelled candidate releases busy state after ${action}`, async t => {
  const { page, target, hold } = await workspace(t)
  const generation = hold('/candidate')
  await page.getByRole('button', { name: 'Generate Migration', exact: true }).click()
  await generation.started
  if (action === 'Source train') await page.locator('.platform-card').first().getByLabel('PAN-OS Train').selectOption('11.0')
  else if (action === 'Load Project') await page.getByRole('button', { name: action, exact: true }).click()
  else await target.selectOption('ethernet1/8')
  await page.getByRole('button', { name: 'Generate Migration', exact: true }).waitFor()
  generation.release()
  await page.waitForTimeout(100)
  assert.equal(await page.getByRole('button', { name: 'Generating...', exact: true }).count(), 0)
  if (action !== 'Load Project') assert.equal(await page.getByText('No migration generated yet', { exact: true }).count(), 1)
})

test('Clear Project cannot be undone by an earlier project creation response', async t => {
  const { page, hold } = await workspace(t)
  const creation = hold('/projects')
  await page.getByRole('button', { name: 'New Project', exact: true }).click()
  await creation.started
  await page.getByRole('button', { name: 'Clear Project', exact: true }).click()
  creation.release()
  await page.waitForTimeout(100)
  await page.getByRole('button', { name: 'Save Project', exact: true }).click()
  await page.getByText('Create a project or upload a source before saving.', { exact: true }).waitFor()
  assert.equal(await page.evaluate(() => localStorage.getItem('confighop-project')), null)
})

test('Load Project owns the session even when an earlier creation finishes later', async t => {
  const { page, target, hold } = await workspace(t)
  const creation = hold('/projects')
  await page.getByRole('button', { name: 'New Project', exact: true }).click()
  await creation.started
  await page.getByRole('button', { name: 'Load Project', exact: true }).click()
  await target.waitFor()
  creation.release()
  await page.waitForTimeout(100)
  await page.getByRole('button', { name: 'Save Project', exact: true }).click()
  assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem('confighop-project')).project_id), 'synthetic-session')
})

for (const action of ['mapping', 'source profile', 'source upload', 'target profile', 'target train', 'New Project', 'Clear Project', 'Load Project']) test(`stale preview errors are ignored after ${action}`, async t => {
  const { page, target, hold } = await workspace(t)
  const stale = hold('/preview', 'POST', true)
  await target.selectOption('ethernet1/7')
  await stale.started
  if (action === 'mapping') await target.selectOption('ethernet1/8')
  else if (action === 'source profile') { await page.locator('.platform-card').first().locator('.hardware-advanced summary').click(); await page.locator('.platform-card').first().getByLabel('Hardware Profile').selectOption('') }
  else if (action === 'source upload') await page.locator('input[type=file]').setInputFiles({ name: 'replacement.xml', mimeType: 'application/xml', buffer: Buffer.from('<config/>') })
  else if (action === 'target profile') { await page.locator('.platform-card').nth(1).locator('.hardware-advanced summary').click(); await page.locator('.platform-card').nth(1).getByLabel('Hardware Profile').selectOption(profiles[0].id) }
  else if (action === 'target train') await page.locator('.platform-card').nth(1).getByLabel('PAN-OS Train').selectOption('11.0')
  else await page.getByRole('button', { name: action, exact: true }).click()
  stale.release()
  await page.waitForTimeout(500)
  assert.equal(await page.getByText('Stale request error', { exact: true }).count(), 0)
  if (action === 'mapping') assert.equal(await target.inputValue(), 'ethernet1/8')
})

test('a pending project load cannot restore state after Clear Project', async t => {
  const { page, hold } = await workspace(t)
  const load = hold('/synthetic-session', 'GET')
  await page.getByRole('button', { name: 'Load Project', exact: true }).click()
  await load.started
  await page.getByRole('button', { name: 'Clear Project', exact: true }).click()
  load.release()
  await page.waitForTimeout(200)
  assert.equal(await page.getByLabel('Target interface for ethernet1/5', { exact: true }).count(), 0)
  assert.equal(await page.getByText('No migration generated yet', { exact: true }).count(), 1)
})

test('desktop, laptop and narrow layouts retain reachable statuses and seven sections', async t => {
  const { page, target } = await workspace(t)
  for (const width of [1600, 1280, 390]) {
    await page.setViewportSize({ width, height: 900 })
    assert.equal(await page.locator('.section-number').count(), 7)
    await target.selectOption('ethernet1/8')
    const blocked = page.getByText('Rendering: BLOCKED', { exact: true }).last()
    await blocked.waitFor()
    await blocked.scrollIntoViewIfNeeded()
    const box = await blocked.boundingBox()
    assert.ok(box.x >= 0 && box.x + box.width <= width)
    await page.getByLabel('Installed target optic rate for ethernet1/8 from ethernet1/5').selectOption('10G')
    const review = page.getByText('Rendering: REVIEW_REQUIRED', { exact: true }).last()
    await review.waitFor()
    await review.scrollIntoViewIfNeeded()
    assert.ok(await review.isVisible())
    await target.focus()
    assert.ok(await target.evaluate(el => document.activeElement === el))
  }
})
