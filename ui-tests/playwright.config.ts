import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for the LV3 Ops Portal (ADR 0243).
 *
 * Targets:
 *  - portal.spec.ts  — happy-path browser journeys against the running portal
 *  - accessibility.spec.ts — axe-core a11y scans of every major portal section
 *
 * PORTAL_URL defaults to http://localhost:8000 (the Uvicorn dev server).
 * Override with:  PORTAL_URL=https://ops.lv3.org npx playwright test
 */

const PORTAL_URL = process.env.PORTAL_URL || 'http://localhost:8000';

export default defineConfig({
  testDir: './playwright',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [['html', { outputFolder: 'playwright-report' }], ['github']] : 'html',

  use: {
    baseURL: PORTAL_URL,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    // Follow the same headers the portal expects in production
    extraHTTPHeaders: {
      'Accept': 'text/html,application/xhtml+xml',
    },
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    // Mobile viewport coverage
    {
      name: 'mobile-chrome',
      use: { ...devices['Pixel 5'] },
    },
  ],
});
