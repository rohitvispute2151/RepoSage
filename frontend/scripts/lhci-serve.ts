/** Serves the production build plus the mock API for Lighthouse CI. Stays in the foreground until killed. */
const mock = Bun.spawn(['bun', 'run', 'mock/server.ts'], { env: { ...process.env, MOCK_PORT: '8788', MOCK_STEP_MS: '0', MOCK_OPEN: '1' }, stdout: 'inherit', stderr: 'inherit' })
const web = Bun.spawn(['bunx', 'vite', 'preview', '--host', '127.0.0.1', '--port', '4173', '--strictPort'], { env: { ...process.env, API_PROXY: 'http://127.0.0.1:8788' }, stdout: 'inherit', stderr: 'inherit' })
const stop = () => { mock.kill(); web.kill() }
process.on('SIGINT', stop)
process.on('SIGTERM', stop)
await Promise.race([mock.exited, web.exited])
stop()
export {}
