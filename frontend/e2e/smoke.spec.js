import { test, expect } from '@playwright/test';

test.describe('E2E Auth & Navigation Smoke Suite', () => {
  test.beforeEach(async ({ context }) => {
    // Clear cookies before each test
    await context.clearCookies();
  });

  test('Student login, httpOnly cookie check, protected page access, logout, and post-logout redirect', async ({ page, context }) => {
    // 1. Visit login page at http://localhost:5173/login
    await page.goto('/login');
    await expect(page).toHaveURL(/.*\/login/);

    // 2. Fill login credentials for throwaway student
    await page.fill('input[type="email"]', 'e2e_student@test.local');
    await page.fill('input[type="password"]', 'E2ePass123!');
    await page.click('button[type="submit"]');

    // 3. Confirm student lands on /dashboard
    await page.waitForURL('**/dashboard', { timeout: 10000 });
    expect(page.url()).toContain('/dashboard');

    // 4. Verify access_token cookie is present and httpOnly
    const cookies = await context.cookies();
    const authCookie = cookies.find((c) => c.name === 'access_token');
    expect(authCookie).toBeDefined();
    expect(authCookie.httpOnly).toBe(true);

    // 5. Verify protected UI elements are rendered
    await expect(page.locator('text=SAIS')).toBeVisible();

    // 6. Click Sign out
    const signOutBtn = page.locator('button:has-text("Sign out")');
    await signOutBtn.click();

    // 7. Verify redirected to /login
    await page.waitForURL('**/login', { timeout: 10000 });
    expect(page.url()).toContain('/login');

    // 8. Verify protected page (/dashboard) is blocked after logout
    await page.goto('/dashboard');
    await page.waitForURL('**/login**', { timeout: 10000 });
    expect(page.url()).toContain('/login');
  });

  test('Admin login lands on /admin', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[type="email"]', 'e2e_admin@test.local');
    await page.fill('input[type="password"]', 'E2ePass123!');
    await page.click('button[type="submit"]');

    await page.waitForURL('**/admin', { timeout: 10000 });
    expect(page.url()).toContain('/admin');
  });

  test('Super Admin login lands on /super-admin', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[type="email"]', 'e2e_superadmin@test.local');
    await page.fill('input[type="password"]', 'E2ePass123!');
    await page.click('button[type="submit"]');

    await page.waitForURL('**/super-admin', { timeout: 10000 });
    expect(page.url()).toContain('/super-admin');
  });
});
