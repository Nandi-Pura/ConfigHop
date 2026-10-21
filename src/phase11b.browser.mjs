import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { readFile, mkdir } from 'node:fs/promises'
import { switchBrowserServer } from './switchBrowserServer.mjs'

let app, browser
const source = 'version 10.13.1110\nhostname LAB-CX\nvlan 101\n name USERS\ninterface 1/1/1\n no shutdown\n vlan access 101\ninterface 1/1/2\n no shutdown\n vlan access 101\n'
before(async () => {
  app = await switchBrowserServer()
  const { chromium } = await import(process.env.CONFIGHOP_PLAYWRIGHT_MODULE || 'playwright')
  browser = await chromium.launch({ headless: true, executablePath: process.env.CONFIGHOP_CHROMIUM_EXECUTABLE })
  await mkdir('artifacts/phase11b', { recursive: true })
})
after(async () => { await browser?.close(); await app?.close() })

async function workspace(t, text = source) {
  const page = await browser.newPage({ viewport: { width: 1680, height: 980 } })
  t.after(() => page.close())
  await page.goto(app.url)
  await page.getByLabel('Domain').selectOption('Switch')
  await page.getByLabel('Source vendor').selectOption('HPE Aruba Networking')
  await page.getByLabel('Source Network OS').selectOption('10.13')
  await page.getByLabel('Target vendor').selectOption('Cisco')
  await page.getByLabel('Target Network OS').selectOption('17.18')
  await page.locator('.switch-workspace input[type=file]').setInputFiles({ name: 'synthetic-aruba.cfg', mimeType: 'text/plain', buffer: Buffer.from(text) })
  await page.getByLabel('Target interface for 1/1/1').waitFor()
  return page
}

test('Aruba to Cisco bulk preview, feature review, and validated export', { timeout: 60000 }, async t => {
  const page = await workspace(t)
  await page.getByLabel('Sequential target start').fill('GigabitEthernet1/0/10')
  await page.getByRole('button', { name: 'Preview Bulk Mapping' }).click()
  await page.getByText('1/1/2 -> GigabitEthernet1/0/11').waitFor()
  assert.equal(await page.getByLabel('Target interface for 1/1/1').inputValue(), '')
  await page.getByRole('button', { name: 'Apply Mapping' }).click()
  await page.locator('.live-heading').getByText('REVIEW_REQUIRED', { exact: true }).waitFor()
  await page.getByRole('tab', { name: 'VLANs', exact: true }).click()
  await page.getByText('Line 3: vlan').waitFor()
  await page.getByRole('tab', { name: 'Interface Mapping', exact: true }).click()
  await page.screenshot({ path: 'artifacts/phase11b/reverse-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: 'artifacts/phase11b/reverse-narrow.png', fullPage: true })
  await page.setViewportSize({ width: 1680, height: 980 })
  await page.getByLabel('I reviewed the current findings and deployment limitations.').check()
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export', exact: true }).click()
  const text = await readFile(await (await download).path(), 'utf8')
  assert.match(text, /interface GigabitEthernet1\/0\/10/)
  assert.match(text, /switchport access vlan 101/)
  assert.doesNotMatch(text, /interface 1\/1\/1/)
})

test('security-bearing Aruba source yields a redacted draft and blocks validated export', { timeout: 60000 }, async t => {
  const page = await workspace(t, source + 'user lab-admin password ciphertext SYNTHETIC_SECRET\n')
  await page.getByLabel('Target interface for 1/1/1').fill('GigabitEthernet1/0/10')
  await page.getByLabel('Target interface for 1/1/2').fill('GigabitEthernet1/0/11')
  await page.locator('.live-heading').getByText('BLOCKED', { exact: true }).waitFor()
  assert.ok(await page.getByRole('button', { name: 'Export', exact: true }).isDisabled())
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download Draft / Review Report' }).click()
  const draft = await readFile(await (await download).path(), 'utf8')
  assert.match(draft, /MANUAL_REQUIRED/)
  assert.doesNotMatch(draft, /SYNTHETIC_SECRET/)
})

test('Cisco aliases collide in manual and confirmed bulk mapping', { timeout: 60000 }, async t => {
  const page = await workspace(t)
  await page.getByLabel('Target interface for 1/1/2').fill('Gi1/0/11')
  await page.getByLabel('Target interface for 1/1/1').fill('GigabitEthernet1/0/11')
  await page.getByText('Target interface is already assigned.').waitFor()
  assert.equal(await page.getByLabel('Target interface for 1/1/1').inputValue(), '')
  await page.getByLabel('Source range end').selectOption('1/1/1')
  await page.getByLabel('Sequential target start').fill('GigabitEthernet1/0/11')
  await page.getByRole('button', { name: 'Preview Bulk Mapping' }).click()
  await page.getByText('Bulk mapping collides with an existing assignment.').waitFor()
  assert.equal(await page.getByRole('button', { name: 'Apply Mapping' }).count(), 0)
})
