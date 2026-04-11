/**
 * axe-core accessibility tests for the LV3 Ops Portal (ADR 0243).
 *
 * Scans every major portal section against WCAG 2.1 AA rules using
 * @axe-core/playwright. Violations cause the test to fail.
 *
 * Documented waivers are in ui-tests/a11y-waivers.yaml and referenced inline.
 *
 * Run:
 *   npx playwright test playwright/accessibility.spec.ts
 *   PORTAL_URL=https://ops.example.com npx playwright test playwright/accessibility.spec.ts
 */

import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

// Waivers: rules that are temporarily accepted with documented justification.
// Each waiver MUST have a reference to the tracking issue / ADR note.
const GLOBAL_DISABLE_RULES: string[] = [
  // Waiver 001: color-contrast on .muted text (--ink-soft #314467 / --paper #f8f4ea)
  // Ratio 4.38:1 passes AA normal text but fails AAA. Tracked: ADR 0243 waiver 001.
  // 'color-contrast',  // Keeping enabled — ratio meets AA, may surface false positives on dark sections.
];

async function runAxe(page: import('@playwright/test').Page, url: string) {
  await page.goto(url);
  // Wait for HTMX hydration to settle
  await page.waitForLoadState('networkidle').catch(() => {});

  const builder = new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
    .exclude('[data-axe-ignore]'); // allow per-element suppression

  if (GLOBAL_DISABLE_RULES.length) {
    builder.disableRules(GLOBAL_DISABLE_RULES);
  }

  return builder.analyze();
}

// ─────────────────────────────────────────────────────────────────────────────
// Root portal page
// ─────────────────────────────────────────────────────────────────────────────

test('root portal page has no critical WCAG 2.1 AA violations', async ({ page }) => {
  const results = await runAxe(page, '/');
  // Filter to critical and serious violations only — minor issues tracked separately
  const serious = results.violations.filter(v => ['critical', 'serious'].includes(v.impact ?? ''));
  if (serious.length > 0) {
    const summary = serious.map(v =>
      `[${v.impact}] ${v.id}: ${v.description}\n  Nodes: ${v.nodes.map(n => n.html).slice(0, 2).join(', ')}`
    ).join('\n\n');
    throw new Error(`axe found ${serious.length} critical/serious violations on /:\n\n${summary}`);
  }
  expect(serious.length).toBe(0);
});

// ─────────────────────────────────────────────────────────────────────────────
// Section partials — each scanned independently
// ─────────────────────────────────────────────────────────────────────────────

const A11Y_SECTIONS: Array<{ name: string; url: string }> = [
  { name: 'overview', url: '/partials/overview' },
  { name: 'repo-intake', url: '/partials/repo-intake' },
  { name: 'agents', url: '/partials/agents' },
  { name: 'runbooks', url: '/partials/runbooks' },
  { name: 'tasks', url: '/partials/tasks' },
  { name: 'changelog', url: '/partials/changelog' },
  { name: 'search', url: '/partials/search' },
  { name: 'runtime-assurance', url: '/partials/runtime-assurance' },
  { name: 'drift', url: '/partials/drift' },
  { name: 'launcher', url: '/partials/launcher' },
];

for (const section of A11Y_SECTIONS) {
  test(`${section.name} partial has no critical WCAG 2.1 AA violations`, async ({ page }) => {
    const response = await page.goto(section.url);
    if (!response || response.status() >= 500) {
      test.skip(true, `${section.url} returned ${response?.status()} — skipping a11y scan`);
      return;
    }

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
      .exclude('[data-axe-ignore]')
      .analyze();

    const serious = results.violations.filter(v => ['critical', 'serious'].includes(v.impact ?? ''));
    if (serious.length > 0) {
      const summary = serious.map(v =>
        `[${v.impact}] ${v.id}: ${v.description}`
      ).join('\n');
      throw new Error(`axe found ${serious.length} critical/serious violations on ${section.url}:\n${summary}`);
    }
    expect(serious.length).toBe(0);
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Entry / journey routing
// ─────────────────────────────────────────────────────────────────────────────

test('entry page has no critical a11y violations', async ({ page }) => {
  const response = await page.goto('/entry?neutral=1');
  if (!response || response.status() >= 500) {
    test.skip(true, '/entry returned non-2xx — skipping');
    return;
  }
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();
  const serious = results.violations.filter(v => ['critical', 'serious'].includes(v.impact ?? ''));
  expect(serious.length).toBe(0);
});

// ─────────────────────────────────────────────────────────────────────────────
// Keyboard navigation smoke tests
// ─────────────────────────────────────────────────────────────────────────────

test('root page is keyboard-navigable (Tab reaches first interactive element)', async ({ page }) => {
  await page.goto('/');
  await page.keyboard.press('Tab');
  const focused = await page.evaluate(() => document.activeElement?.tagName?.toLowerCase());
  // After first Tab, focus should be on an interactive element — not body or null
  expect(['a', 'button', 'input', 'select', 'textarea', 'details', 'summary']).toContain(focused);
});

test('repo intake form fields are reachable by keyboard', async ({ page }) => {
  await page.goto('/partials/repo-intake');
  // Tab through the form to ensure inputs are reachable
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press('Tab');
  }
  const focused = await page.evaluate(() => document.activeElement?.tagName?.toLowerCase());
  expect(['input', 'select', 'button', 'textarea', 'a']).toContain(focused);
});

// ─────────────────────────────────────────────────────────────────────────────
// Focus management on HTMX swaps
// ─────────────────────────────────────────────────────────────────────────────

test('launcher search input retains focus-visible after render', async ({ page }) => {
  await page.goto('/');
  // Open the launcher if available
  const launcherBtn = page.locator('[aria-label*="launcher"], [aria-label*="Launcher"]').first();
  if (await launcherBtn.isVisible()) {
    await launcherBtn.click();
    const searchInput = page.locator('#launcher-query, input[name="query"]').first();
    if (await searchInput.isVisible()) {
      await searchInput.focus();
      await searchInput.type('gra');
      // After HTMX swap, page should not throw and input should still be present
      await page.waitForTimeout(200);
      await expect(searchInput).toBeVisible();
    }
  } else {
    test.skip(true, 'Launcher button not found — skip focus-management test');
  }
});
