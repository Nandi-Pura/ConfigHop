export function readProjectStorage(key: string, oldKey: string, storage: Pick<Storage, 'getItem' | 'setItem'> = localStorage) {
  const current = storage.getItem(key)
  if (current !== null) return current
  const previous = storage.getItem(oldKey)
  if (previous !== null) storage.setItem(key, previous)
  return previous
}
