import { spawn } from 'node:child_process'
import { createServer as netServer } from 'node:net'
import { resolve } from 'node:path'
import { createServer } from 'vite'

export async function switchBrowserServer() {
  const socket = netServer()
  await new Promise(resolve => socket.listen(0, '127.0.0.1', resolve))
  const port = socket.address().port
  await new Promise(resolve => socket.close(resolve))
  const api = `http://127.0.0.1:${port}/api/v1`
  const server = await createServer({ configFile: false, define: { 'import.meta.env.VITE_CONFIGHOP_API_URL': JSON.stringify(api) }, server: { host: '127.0.0.1', port: 0 }, logLevel: 'silent' })
  await server.listen()
  const url = `http://127.0.0.1:${server.httpServer.address().port}`
  const backend = spawn(process.env.PYTHON || 'python', ['-m', 'uvicorn', 'confighop_api.main:app', '--host', '127.0.0.1', '--port', String(port), '--no-access-log'], {
    cwd: resolve('backend'), windowsHide: true, stdio: 'ignore', env: { ...process.env, PYTHONPATH: resolve('backend/src'), CONFIGHOP_CORS_ORIGINS: url },
  })
  let spawnError
  backend.on('error', error => { spawnError = error })
  const close = async () => { backend.kill(); await server.close() }
  for (let attempt = 0; attempt < 100; attempt++) {
    if (spawnError || backend.exitCode !== null) { await close(); throw new Error('Browser backend failed to start') }
    if (await fetch(`${api}/health`).then(r => r.ok).catch(() => false)) return { server, backend, url, api, close }
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  await close(); throw new Error('Browser backend readiness timed out')
}
