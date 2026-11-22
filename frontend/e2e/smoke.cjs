// End-to-end smoke test against a running backend (API_URL) and frontend (APP_URL).
// Requires Playwright + Chromium: npx playwright install chromium. Run: npm run e2e
const { chromium } = require('playwright');
const API = (process.env.API_URL || 'http://localhost:8000') + '/api/v1/regions/houston-sw-pilot';
const shots = process.env.SHOTS_DIR || 'e2e/screenshots';
require('fs').mkdirSync(shots, { recursive: true });
(async () => {
  const b = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const errs = [];
  p.on('console', m => { if (m.type() === 'error' && !/basemaps\.cartocdn|Failed to load resource/.test(m.text())) errs.push(m.text()); });
  p.on('pageerror', e => errs.push('PAGEERROR ' + e.message));
  const t0 = Date.now();
  await p.goto((process.env.APP_URL || 'http://localhost:3000') + '/', { waitUntil: 'domcontentloaded' });
  await p.getByText('API connected').waitFor({ timeout: 30000 });
  await p.locator('aside').getByText('Estimated assistance demand').first().waitFor();
  await p.waitForFunction(() => !document.body.innerText.includes('Computing'), null, { timeout: 60000 });
  await p.waitForTimeout(2500);
  console.log('initial load + scenario', (Date.now() - t0) / 1000, 's');
  await p.screenshot({ path: `${shots}/01-overview.png` });
  // Overview stat equals backend accessibility summary
  const acc = await (await fetch(`${API}/accessibility/analyze`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ scenario: 'severe', access: { walk_max_m: 800 }, include_geometry: false }) })).json();
  const body = await p.innerText('aside');
  const demand = Math.round(acc.summary.total_demand_est).toLocaleString('en-US');
  console.log('overview demand shown', demand, body.includes(demand));

  // Scenario lab
  await p.getByRole('navigation').getByRole('button', { name: 'Scenario Lab' }).click();
  await p.getByText('Closed road segments').waitFor();
  const ev = await (await fetch(`${API}/scenarios/evaluate`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ scenario: 'severe', access: { walk_max_m: 800 } }) })).json();
  const lab = await p.innerText('aside');
  console.log('closed segments match', ev.closures.closed_segments, lab.includes(ev.closures.closed_segments.toLocaleString('en-US')));
  await p.screenshot({ path: `${shots}/02-scenario.png` });
  // switch to moderate & run
  await p.getByRole('radio', { name: 'Moderate' }).click();
  await p.getByText('Inputs changed').waitFor();
  await p.getByRole('button', { name: 'Run simulation' }).click();
  await p.getByText('Result: moderate').waitFor({ timeout: 60000 });
  const lab2 = await p.innerText('aside');
  const evm = await (await fetch(`${API}/scenarios/evaluate`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ scenario: 'moderate', access: { walk_max_m: 800 } }) })).json();
  console.log('moderate segments match', evm.closures.closed_segments, lab2.includes(String(evm.closures.closed_segments)));
  // back to severe
  await p.getByRole('radio', { name: 'Severe' }).click();
  await p.getByRole('button', { name: 'Run simulation' }).click();
  await p.getByText('Result: severe').waitFor({ timeout: 60000 });

  // Accessibility
  await p.getByRole('navigation').getByRole('button', { name: 'Accessibility' }).click();
  await p.getByText('Most affected tracts').waitFor();
  await p.waitForTimeout(800);
  await p.screenshot({ path: `${shots}/03-accessibility.png` });

  // Planner: invalid param then optimize
  await p.getByRole('navigation').getByRole('button', { name: 'Intervention Planner' }).click();
  const vehInput = p.getByLabel('Vehicles value');
  await vehInput.fill('500'); await vehInput.press('Enter');
  const shownVeh = await vehInput.inputValue();
  console.log('vehicles clamped to', shownVeh);
  await vehInput.fill('15'); await vehInput.press('Enter');
  await p.getByRole('button', { name: 'Optimize response' }).click();
  await p.getByText('Estimated people assisted').waitFor({ timeout: 90000 });
  await p.waitForTimeout(1200);
  const opt = await (await fetch(`${API}/optimize`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ scenario: 'severe', access: { walk_max_m: 800 }, resources: { max_active_hubs: 12, vehicles: 15, vehicle_capacity: 40, horizon_min: 480, dwell_min: 10, hub_capacity: 600, shelter_capacity: 400, shelters_per_hub: 4 }, weights: { mode: 'equity', beta_poverty: 0.5, beta_disability: 0.5, beta_age65: 0 }, include_geometry: false }) })).json();
  const plan = await p.innerText('aside');
  const served = Math.round(opt.totals.served).toLocaleString('en-US'), unmet = Math.round(opt.totals.unmet).toLocaleString('en-US');
  console.log('planner served/unmet', served, unmet, plan.includes(served), plan.includes(unmet), 'verified', plan.includes('Constraints verified'), 'hubs', opt.hubs.length);
  await p.getByRole('button', { name: /^1/ }).first().click().catch(() => {});
  await p.waitForTimeout(1200);
  await p.screenshot({ path: `${shots}/04-planner.png` });

  // Impact
  await p.getByRole('navigation').getByRole('button', { name: 'Impact Analysis' }).click();
  await p.getByRole('button', { name: 'Run comparison' }).click();
  await p.getByText('Assisted vs unmet, by case').waitFor({ timeout: 90000 });
  await p.waitForTimeout(1200);
  const cmp = await (await fetch(`${API}/demo`)).json();
  const imp = await p.innerText('aside');
  const cases = Object.fromEntries(cmp.result.cases.map(c => [c.case, c.totals]));
  console.log('impact', ['disrupted_no_intervention', 'disrupted_equity_optimized'].map(k => [k, Math.round(cases[k].served), imp.includes(Math.round(cases[k].served).toLocaleString('en-US'))]), 'same-total note', imp.includes('does not increase the number assisted'));
  await p.screenshot({ path: `${shots}/05-impact.png`, fullPage: false });
  await p.locator('aside').evaluate(e => e.scrollTo(0, 700));
  await p.screenshot({ path: `${shots}/05b-impact-charts.png` });

  // Guided demo
  await p.getByRole('navigation').getByRole('button', { name: 'Run guided demo' }).click();
  await p.getByText('step 1 of 8').waitFor();
  for (let i = 1; i < 8; i++) {
    if (i === 5) { await p.getByRole('button', { name: 'Run the optimiser' }).click(); await p.getByText(/Solved:/).waitFor({ timeout: 90000 }); }
    const next = p.getByRole('button', { name: 'Next' });
    await next.waitFor(); await p.waitForFunction(() => { const b = [...document.querySelectorAll('button')].find(x => x.textContent.trim().startsWith('Next')); return b && !b.disabled; }, null, { timeout: 60000 });
    await next.click();
    await p.getByText(`step ${i + 1} of 8`).waitFor();
    if (i === 6) await p.getByText('Headline (modelled)').waitFor({ timeout: 90000 });
    await p.waitForTimeout(700);
    if ([1, 2, 5, 6, 7].includes(i)) await p.screenshot({ path: `${shots}/06-demo-step${i + 1}.png` });
  }
  // tract click
  await p.getByRole('button', { name: 'Exit guided demo' }).click();
  await p.mouse.click(700, 450);
  await p.waitForTimeout(800);
  console.log('tract inspector after map click', (await p.innerText('aside')).includes('Observed (ACS 2020'));
  await p.screenshot({ path: `${shots}/07-tract.png` });

  // Methodology
  await p.getByRole('link', { name: 'Data & Methodology' }).click();
  await p.getByText('research and planning prototype').first().waitFor();
  await p.getByText('Census tracts (TIGER/Line)').waitFor({ timeout: 20000 });
  await p.screenshot({ path: `${shots}/08-methodology.png` });

  // Mobile
  const m = await b.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true });
  await m.goto((process.env.APP_URL || 'http://localhost:3000') + '/?view=planner', { waitUntil: 'domcontentloaded' });
  await m.getByText('Intervention Planner').first().waitFor();
  await m.waitForTimeout(4000);
  await m.screenshot({ path: `${shots}/09-mobile.png` });
  const overflow = await m.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  console.log('mobile horizontal overflow', overflow);
  console.log('console errors', errs.slice(0, 8));
  await b.close();
})().catch(e => { console.error('E2E FAILED', e.message); process.exit(1); });
