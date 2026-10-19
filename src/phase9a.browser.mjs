import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { readFile, mkdir } from 'node:fs/promises'
import { switchBrowserServer } from './switchBrowserServer.mjs'

let app, browser
const source = await readFile('backend/tests/fixtures/switch/phase9a-iosxe.cfg', 'utf8')
before(async () => {
  app = await switchBrowserServer()
  const { chromium } = await import(process.env.CONFIGHOP_PLAYWRIGHT_MODULE || 'playwright')
  browser = await chromium.launch({ headless: true, executablePath: process.env.CONFIGHOP_CHROMIUM_EXECUTABLE })
  await mkdir('artifacts/phase9a', { recursive: true })
})
after(async () => { await browser?.close(); await app?.close() })

async function uploaded(t) {
  const page = await browser.newPage({ viewport: { width: 1680, height: 980 } })
  t.after(() => page.close())
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  t.after(() => assert.deepEqual(errors, []))
  await page.goto(app.url)
  await page.getByLabel('Domain').selectOption('Switch')
  await page.locator('.switch-workspace input[type=file]').setInputFiles({ name: 'synthetic-phase9a.cfg', mimeType: 'text/plain', buffer: Buffer.from(source) })
  await page.getByLabel('Logical target slot for GigabitEthernet1/0/1').waitFor()
  return page
}
async function mapped(page) {
  await page.getByText('Target capability and translation report', { exact: true }).click()
  await page.getByLabel('Optional target capability').selectOption('hpe-aruba-jl663a')
  for (const [index, slot] of [24, 10, 48, 7, 8].entries()) await page.getByLabel(`Logical target slot for GigabitEthernet1/0/${index + 1}`).selectOption(String(slot))
  await page.locator('.live-heading').getByText('REVIEW_REQUIRED', { exact: true }).waitFor()
}

test('real Switch path parses, renders globals and mappings, copies, expands and exports latest candidate', { timeout: 60000 }, async t => {
  const page = await uploaded(t)
  assert.equal(await page.locator('.locked-interface-row').count(), 7)
  await mapped(page)
  assert.equal(await page.getByLabel('Logical target slot for GigabitEthernet1/0/2').locator('option[value="24"]').count(), 0)
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.getByRole('button', { name: 'Copy All', exact: true }).click()
  const text = await page.evaluate(() => navigator.clipboard.readText())
  assert.match(text, /hostname LAB-SWITCH/)
  assert.match(text, /interface 1\/1\/24/)
  assert.match(text, /ip route 0.0.0.0\/0 192.0.2.1/)
  assert.ok(await page.locator('.syntax-tag').count() > 0)
  await page.getByRole('button', { name: 'Expand configuration preview' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Restore' }).click()
  await page.getByText('Target capability and translation report', { exact: true }).click()
  await page.screenshot({ path: 'artifacts/phase9a/switch-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: 'artifacts/phase9a/switch-narrow.png', fullPage: true })
  await page.getByLabel('I reviewed the current findings and deployment limitations.').check()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export', exact: true }).click()
  const file = await download
  assert.equal(await readFile(await file.path(), 'utf8'), text.replace(/\r\n/g, '\n'))
  await page.setViewportSize({ width: 1680, height: 980 })
  await page.getByRole('button', { name: 'Save Project', exact: true }).click()
  const storage = await page.evaluate(() => ({ ...localStorage }))
  assert.ok(!JSON.stringify(storage).includes('hostname LAB-SWITCH'))
  assert.ok(storage['confighop-switch-session-v2'])
})

test('older real preview response cannot replace a newer mapping; removal invalidates export', { timeout: 60000 }, async t => {
  const page = await uploaded(t)
  await mapped(page)
  let release, started
  const gate = new Promise(resolve => { release = resolve })
  const seen = new Promise(resolve => { started = resolve })
  let held = false
  await page.route('**/switch-projects/*/preview', async route => {
    const response = await route.fetch()
    if (!held) { held = true; started(); await gate }
    await route.fulfill({ response }).catch(() => {})
  })
  await page.getByLabel('Logical target slot for GigabitEthernet1/0/1').selectOption('22')
  assert.ok(await page.getByRole('button', { name: 'Export', exact: true }).isDisabled())
  await seen
  await page.getByLabel('Logical target slot for GigabitEthernet1/0/1').selectOption('23')
  await page.locator('.live-heading').getByText('REVIEW_REQUIRED', { exact: true }).waitFor()
  release()
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.getByRole('button', { name: 'Copy All', exact: true }).click()
  let text = await page.evaluate(() => navigator.clipboard.readText())
  assert.match(text, /interface 1\/1\/23/)
  assert.doesNotMatch(text, /interface 1\/1\/22/)
  await page.getByLabel('Logical target slot for GigabitEthernet1/0/1').selectOption('')
  assert.ok(await page.getByRole('button', { name: 'Export', exact: true }).isDisabled())
  await page.locator('.live-heading').getByText('REVIEW_REQUIRED', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Copy All', exact: true }).click()
  text = await page.evaluate(() => navigator.clipboard.readText())
  assert.doesNotMatch(text, /interface 1\/1\/23/)
  assert.match(text, /vlan 20/)
  await page.getByRole('tab', { name: /Validation/ }).click()
  await page.getByText('REVIEW_REQUIRED: UNMAPPED_INTERFACE', { exact: true }).first().waitFor()
})

test('legacy plaintext persistence is removed and missing VLAN dependency blocks export', { timeout: 60000 }, async t => {
  const page = await uploaded(t)
  await page.evaluate(() => localStorage.setItem('confighop-switch-workspace-v1', JSON.stringify({ config: 'synthetic-legacy-config' })))
  await page.reload()
  await page.getByLabel('Domain').selectOption('Switch')
  assert.equal(await page.evaluate(() => localStorage.getItem('confighop-switch-workspace-v1')), null)
  await page.locator('.switch-workspace input[type=file]').setInputFiles({ name: 'synthetic-missing-vlan.cfg', mimeType: 'text/plain', buffer: Buffer.from(source.replace('vlan 20\n name SERVERS\n!\n', '')) })
  await page.getByLabel('Logical target slot for GigabitEthernet1/0/1').waitFor()
  await page.getByRole('tab', { name: /Validation/ }).click()
  await page.getByText('BLOCKED: DEPENDENCY_UNRESOLVED', { exact: true }).first().waitFor()
  assert.ok(await page.getByRole('button', { name: 'Export', exact: true }).isDisabled())
  await page.screenshot({ path: 'artifacts/phase9a/dependency-blocked.png', fullPage: true })
})
