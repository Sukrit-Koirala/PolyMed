import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests', fullyParallel: false, workers: 1, timeout: 45_000,
  testIgnore: process.env.E2E_LEGACY === 'true' ? ['**/bridge.spec.ts', '**/connection.spec.ts'] : '**/legacy/**',
  reporter: 'list',
  use: { baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:3000', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [{ name: 'desktop', use: { ...devices['Desktop Chrome'], permissions: ['microphone'], launchOptions: { args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] }, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) } }]
});
