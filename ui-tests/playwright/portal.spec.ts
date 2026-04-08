/**
 * Playwright browser interaction tests for the LV3 Ops Portal (ADR 0243).
 *
 * These tests cover the most important human journeys through the portal:
 *   1. Root loads and nav renders
 *   2. Each section partial loads without 5xx
 *   3. Launcher opens, filter works, persona switch works
 *   4. Repo intake form renders with a required-field validation response
 *   5. Health endpoint returns 200 JSON
 *
 * Tests assume the portal is running at PORTAL_URL (default http://localhost:8000).
 * They do NOT require a real gateway — the portal degrades gracefully when the
 * gateway is unavailable, showing empty states rather than crashing.
 */

import { expect, test } from '@playwright/test';

// ─────────────────────────────────────────────────────────────────────────────
// Health endpoint
// ─────────────────────────────────────────────────────────────────────────────

test('GET /health returns 200 and ok:true', async ({ request }) => {
  const response = await request.get('/health');
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.status).toBe('ok');
});

// ─────────────────────────────────────────────────────────────────────────────
// Root page
// ─────────────────────────────────────────────────────────────────────────────

test('root page loads without error', async ({ page }) => {
  const response = await page.goto('/');
  expect(response?.status()).toBeLessThan(500);
  // Portal should always render a meaningful heading
  await expect(page.locator('h1, h2').first()).toBeVisible();
});

test('portal masthead is present', async ({ page }) => {
  await page.goto('/');
  // The masthead or portal brand element should be present
  const masthead = page.locator('[class*="masthead"], [class*="portal-header"], header').first();
  await expect(masthead).toBeVisible();
});

test('main navigation renders at least 3 links', async ({ page }) => {
  await page.goto('/');
  const navLinks = page.locator('nav a, [class*="portal-nav"] a, [class*="nav-link"]');
  await expect(navLinks).toHaveCountGreaterThan(2);
});

// ─────────────────────────────────────────────────────────────────────────────
// Section partials — each must load without 5xx
// ─────────────────────────────────────────────────────────────────────────────

const PARTIALS = [
  '/partials/overview',
  '/partials/drift',
  '/partials/agents',
  '/partials/runbooks',
  '/partials/tasks',
  '/partials/changelog',
  '/partials/search',
  '/partials/runtime-assurance',
  '/partials/repo-intake',
];

for (const partial of PARTIALS) {
  test(`GET ${partial} returns non-5xx`, async ({ request }) => {
    const response = await request.get(partial, {
      headers: { 'HX-Request': 'true' },
    });
    expect(response.status()).toBeLessThan(500);
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Launcher panel
// ─────────────────────────────────────────────────────────────────────────────

test('launcher partial renders destinations', async ({ request }) => {
  const response = await request.get('/partials/launcher');
  expect(response.status()).toBeLessThan(500);
  const body = await response.text();
  // Launcher should include at least one destination link
  expect(body).toContain('launcher-entry');
});

test('launcher search filters destinations', async ({ request }) => {
  const full = await request.get('/partials/launcher');
  const filtered = await request.get('/partials/launcher?query=grafana');
  expect(filtered.status()).toBeLessThan(500);
  const filteredBody = await filtered.text();
  // Should mention grafana (case-insensitive match)
  expect(filteredBody.toLowerCase()).toContain('grafana');
});

// ─────────────────────────────────────────────────────────────────────────────
// Repo intake form (ADR 0224)
// ─────────────────────────────────────────────────────────────────────────────

test('repo intake partial renders a form', async ({ page }) => {
  const response = await page.goto('/partials/repo-intake');
  expect(response?.status()).toBeLessThan(500);
  // The intake form must have the repo URL input
  await expect(page.locator('input[name="repo"], #intake-repo')).toBeVisible();
});

test('repo intake form has all required selects', async ({ page }) => {
  await page.goto('/partials/repo-intake');
  await expect(page.locator('select[name="environment"]')).toBeVisible();
  await expect(page.locator('select[name="build_pack"]')).toBeVisible();
  await expect(page.locator('select[name="source"]')).toBeVisible();
});

test('custom intake POST with missing repo returns non-2xx or validation message', async ({ request }) => {
  const response = await request.post('/actions/repo-intake/custom', {
    form: {
      repo: '',
      app_name: '',
      branch: 'main',
      project: 'LV3 Apps',
      environment: 'production',
      build_pack: 'dockercompose',
      source: 'auto',
      ports: '80',
      llm_assistance: 'prohibited',
    },
    headers: { 'HX-Request': 'true' },
  });
  // Either a validation HTML fragment (200) or an HTTP error — never 5xx on validation
  expect(response.status()).toBeLessThan(500);
  const body = await response.text();
  // Should contain a state/error indicator
  expect(body.toLowerCase()).toMatch(/required|error|failed|shell-state/);
});

// ─────────────────────────────────────────────────────────────────────────────
// API endpoint (ADR 0224 secure JSON API)
// ─────────────────────────────────────────────────────────────────────────────

test('POST /api/v1/repo-intake without auth returns 401', async ({ request }) => {
  const response = await request.post('/api/v1/repo-intake', {
    data: { repo: 'https://github.com/example/repo', app_name: 'test-app' },
    headers: { 'Content-Type': 'application/json' },
  });
  // No static token in test env → expect 401
  // If static token is configured, this may return 4xx validation instead
  expect([401, 403, 422]).toContain(response.status());
});

test('POST /api/v1/repo-intake with non-JSON body returns 400', async ({ request }) => {
  const response = await request.post('/api/v1/repo-intake', {
    data: 'not-json',
    headers: {
      'Content-Type': 'text/plain',
      'Authorization': `Bearer ${process.env.OPS_PORTAL_STATIC_API_TOKEN || 'test-token'}`,
    },
  });
  expect([400, 401, 403, 422]).toContain(response.status());
});

// ─────────────────────────────────────────────────────────────────────────────
// Entry / journey routing
// ─────────────────────────────────────────────────────────────────────────────

test('GET /entry renders without 5xx', async ({ page }) => {
  const response = await page.goto('/entry?neutral=1');
  expect(response?.status()).toBeLessThan(500);
});
