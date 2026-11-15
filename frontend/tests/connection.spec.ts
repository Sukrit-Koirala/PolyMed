import { test, expect } from '@playwright/test';

// No database reset or backend mutations: simulate the proxy failing in the browser.
test.beforeEach(async ({ page }) => {
  await page.route('**/api/auth/me', route => route.fulfill({ status: 401, json: { detail: 'Sign in' } }));
});

test('proxy failures show an actionable backend message instead of a JSON parse error', async ({ page }) => {
  await page.route('**/api/auth/login', route => route.fulfill({ status: 502, contentType: 'text/plain', body: 'Bad Gateway' }));
  await page.goto('/');
  await page.getByRole('button', { name: 'Enter workspace', exact: true }).click();
  const alert = page.getByRole('alert').filter({ hasText: 'The EHR Bridge backend is unavailable' });
  await expect(alert).toBeVisible();
  await expect(alert).toContainText('port 8000');
});

test('a disconnected request shows the same recoverable backend message', async ({ page }) => {
  await page.route('**/api/auth/login', route => route.abort('connectionreset'));
  await page.goto('/');
  await page.getByRole('button', { name: 'Enter workspace', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'The EHR Bridge backend is unavailable' })).toBeVisible();
});
