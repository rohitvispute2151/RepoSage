import { mergeConfig, defineConfig } from 'vitest/config'
import viteConfig from './vite.config'

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      include: ['tests/**/*.test.ts'],
      setupFiles: ['tests/setup.ts'],
      env: { VITE_API_BASE: 'http://api.test' },
      restoreMocks: true,
      testTimeout: 15000,
    },
  }),
)
