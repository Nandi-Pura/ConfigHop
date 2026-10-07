import test from 'node:test'
import assert from 'node:assert/strict'
import { autoMapSwitchPorts, changeSwitchPort, filterSwitchPorts, switchCatalog, switchOsLabel, switchPorts, switchSource, switchTarget } from './switchData.ts'

test('Switch catalog keeps vendor hardware and OS combinations separate', () => {
  assert.deepEqual([...new Set(switchCatalog.map((item) => item.vendor))], ['Cisco', 'HPE Aruba Networking', 'Juniper Networks', 'Huawei'])
  assert.equal(switchSource.hardware.model, 'C9300-48P')
  assert.equal(switchSource.hardware.series, 'Catalyst 9300 Series')
  assert.equal(switchOsLabel(switchSource), 'IOS XE 17.12')
  assert.equal(switchTarget.hardware.model, 'CX 6300M 48G')
  assert.equal(switchOsLabel(switchTarget), 'AOS-CX 10.15')
  assert.ok(switchCatalog.filter((item) => item.vendor === 'Cisco').every((item) => item.software.product === 'IOS XE'))
  assert.ok(switchCatalog.filter((item) => item.vendor === 'HPE Aruba Networking').every((item) => item.software.product === 'AOS-CX'))
  assert.ok(switchCatalog.filter((item) => item.vendor === 'Juniper Networks').every((item) => item.software.product === 'Junos'))
  assert.ok(switchCatalog.filter((item) => item.vendor === 'Huawei').every((item) => item.software.product === 'VRP'))
})

test('Switch port filters and local mapping updates', () => {
  assert.equal(switchPorts.length, 48)
  assert.equal(filterSwitchPorts(switchPorts, 'Mapped', '').length, 46)
  assert.equal(filterSwitchPorts(switchPorts, 'Unmapped', '').length, 2)
  assert.equal(filterSwitchPorts(switchPorts, 'Review', '').length, 2)
  assert.equal(filterSwitchPorts(switchPorts, 'All', 'Gi1/0/47').length, 1)
  const changed = changeSwitchPort(switchPorts, 1, '1/1/10')
  assert.equal(changed[0].status, 'Review')
  assert.equal(changed[0].target, '1/1/10')
  assert.equal(switchPorts[0].target, '1/1/1')
  assert.equal(filterSwitchPorts(autoMapSwitchPorts(switchPorts), 'Unmapped', '').length, 0)
})
