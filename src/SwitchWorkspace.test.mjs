import test from 'node:test'
import assert from 'node:assert/strict'
import { inspectSwitchDeclarations, validSlotAssignments } from './switchInspection.ts'

test('Switch local inspection reports only declarations actually present', () => {
  assert.deepEqual(inspectSwitchDeclarations('hostname sw\ninterface GigabitEthernet1/0/1\n description user\ninterface Port-channel10\ninterface Vlan99\ninterface unknown0\ninterface GigabitEthernet1/0/1'), [
    { name: 'GigabitEthernet1/0/1', type: 'Physical' },
    { name: 'Port-channel10', type: 'Logical' },
    { name: 'Vlan99', type: 'Logical' },
    { name: 'unknown0', type: 'Unrecognized' },
  ])
  assert.deepEqual(inspectSwitchDeclarations(''), [])
  assert.deepEqual(inspectSwitchDeclarations('interface Gi1/0/24\ninterface Po10\ninterface 1/1/12'), [
    { name: 'Gi1/0/24', type: 'Physical' }, { name: 'Po10', type: 'Logical' }, { name: '1/1/12', type: 'Physical' },
  ])
})

test('saved Switch assignments reject unknown sources and duplicate logical slots', () => {
  const source = 'interface GigabitEthernet1/0/1\ninterface GigabitEthernet1/0/2\ninterface Vlan99'
  assert.deepEqual(validSlotAssignments(source, { 'GigabitEthernet1/0/1': 24, 'GigabitEthernet1/0/2': 24, Vlan99: 25, absent: 26 }), { 'GigabitEthernet1/0/1': 24 })
})
