import test from 'node:test'
import assert from 'node:assert/strict'
import { readProjectStorage } from './projectStorage.ts'

test('reads and copies a saved ConfigMorph project to the ConfigHop key', () => {
  const values = new Map([['configmorph-project', '{"project":"old"}']])
  const storage = { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) }
  assert.equal(readProjectStorage('confighop-project', 'configmorph-project', storage), '{"project":"old"}')
  assert.equal(values.get('confighop-project'), '{"project":"old"}')
  assert.equal(values.get('configmorph-project'), '{"project":"old"}')
  values.set('confighop-project', '{"project":"new"}')
  assert.equal(readProjectStorage('confighop-project', 'configmorph-project', storage), '{"project":"new"}')
})
