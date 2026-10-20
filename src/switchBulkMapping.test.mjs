import test from 'node:test'
import assert from 'node:assert/strict'
import { previewSequentialMapping } from './switchBulkMapping.ts'

test('bulk mapping previews explicit target names and checks collisions', () => {
  const sources = ['1/1/1', '1/1/3', '1/1/49']
  assert.deepEqual(previewSequentialMapping(sources, 'GigabitEthernet1/0/10', {}), {
    '1/1/1': 'GigabitEthernet1/0/10', '1/1/3': 'GigabitEthernet1/0/11', '1/1/49': 'GigabitEthernet1/0/12',
  })
  assert.throws(() => previewSequentialMapping(sources, '1/1/1', {}))
  assert.throws(() => previewSequentialMapping(sources, 'GigabitEthernet1/0/10', { other: 'GigabitEthernet1/0/11' }))
})
