import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.FLOWFORGE_E2E_BASE_URL ?? 'http://127.0.0.1:5173';
const parsedBaseURL = new URL(baseURL);
const shouldStartLocalVite = ['127.0.0.1', 'localhost'].includes(parsedBaseURL.hostname) && parsedBaseURL.port === '5173';

/**
 * The Vite server is managed for convenience. Start FastAPI against a dedicated
 * development/test database before running this suite; this avoids silently
 * pointing a browser test at a production database.
 */
export default defineConfig({
  testDir: './tests/e2e',
  timeout: 45_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'line' : 'html',
  outputDir: 'test-results',
  use: {
    ...devices['Desktop Chrome'],
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: shouldStartLocalVite ? {
    command: 'npm run dev',
    url: baseURL,
    env: { VITE_API_BASE_URL: process.env.FLOWFORGE_E2E_API_URL ?? 'http://127.0.0.1:8000' },
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: 'ignore',
    stderr: 'pipe',
  } : undefined,
});
