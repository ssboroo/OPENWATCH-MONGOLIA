import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url());
    const body = url.pathname.endsWith('/system/reliability')
      ? { sources: { degraded: false, healthy: 0, total: 0, with_articles: 0, unverified: 0 }, queue: { pending: 0, progress_stalled: false } }
      : url.pathname.endsWith('/collector/status') ? { latest: null }
      : url.pathname.endsWith('/system/status') ? { worker_stale: false, ai_enabled: true }
      : { items: [], total: 0, sources: [], categories: [], data: {} };
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
});

test('followed topics remain saved after reload', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/?view=research');
  await page.getByRole('textbox', { name: 'Дагах сэдэв' }).fill('Төсвийн ил тод байдал');
  await page.getByRole('button', { name: 'Сэдэв дагах' }).click();
  await expect(page.getByText('Төсвийн ил тод байдал')).toBeVisible();
  await page.reload();
  await expect(page.getByText('Төсвийн ил тод байдал')).toBeVisible();
});

test('mobile navigation opens and the research view has no horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/?view=research');
  const menu = page.getByRole('button', { name: 'Цэс' });
  await expect(menu).toHaveAttribute('aria-expanded', 'false');
  await menu.click();
  await expect(menu).toHaveAttribute('aria-expanded', 'true');
  await page.getByRole('heading', { name: 'Сэдэв дагах ба мэдэгдэл' }).scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});
