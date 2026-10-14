// Aruba hardware catalog barrel export.
// Adding a new Aruba switch = add catalog file + import here. No SwitchWorkspace.tsx changes needed.

import { CX5420_MODELS } from './cx5420.ts'
import { CX6000_MODELS } from './cx6000.ts'
import { CX6100_MODELS } from './cx6100.ts'
import { CX6200_MODELS } from './cx6200.ts'
import { CX6300_MODELS } from './cx6300.ts'
import { CX6300L_MODELS } from './cx6300l.ts'
import { CX6400_MODELS } from './cx6400.ts'

export * from './cx5420.ts'
export * from './cx6000.ts'
export * from './cx6100.ts'
export * from './cx6200.ts'
export * from './cx6300.ts'
export * from './cx6300l.ts'
export * from './cx6400.ts'

import type { SwitchHardware } from '../types.ts'

export const ALL_ARUBA_MODELS: SwitchHardware[] = [
  ...CX5420_MODELS,
  ...CX6000_MODELS,
  ...CX6100_MODELS,
  ...CX6200_MODELS,
  ...CX6300_MODELS,
  ...CX6300L_MODELS,
  ...CX6400_MODELS,
]
