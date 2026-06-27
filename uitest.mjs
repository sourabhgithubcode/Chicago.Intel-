import { chromium } from 'playwright';

const BASE = process.argv[2] || 'http://localhost:5173/';
const ADDR = process.argv[3] || '850 W Eastwood Ave, Chicago, IL';
const OUT = '/private/tmp/claude-501/-Users-HP-Downloads-Chicago-intel/2026acef-349e-453e-9f2e-31e4ce9e63fc/scratchpad';
const findings = [];
const note = (sev, msg) => { findings.push({ sev, msg }); console.log(`[${sev}] ${msg}`); };

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();

const consoleErrors = [], pageErrors = [], apiResp = [];
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
page.on('pageerror', (e) => pageErrors.push(String(e)));
page.on('response', (r) => {
  const u = r.url();
  if (/geocode|\/rest\/v1\//.test(u)) apiResp.push(`${r.status()} ${u.split('?')[0].split('/').slice(-2).join('/')}${u.includes('rpc')?' '+u.split('/rpc/')[1]?.split('?')[0]:''}`);
});

console.log(`\n===== UI TEST: ${BASE} (addr: ${ADDR}) =====`);
try {
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 45000 });
  await page.locator('h1').first().waitFor({ timeout: 20000 });
} catch (e) { note('FAIL', `goto/load: ${e.message}`); }

const h1 = await page.locator('h1').first().textContent().catch(() => null);
note(h1?.includes('Chicago.Intel') ? 'PASS' : 'FAIL', `h1 = ${JSON.stringify(h1)}`);
note(await page.locator('input#addr').count() ? 'PASS' : 'FAIL', `search input present`);
await page.screenshot({ path: `${OUT}/shot_1_initial.png`, fullPage: true });

// Search
try {
  await page.fill('input#addr', ADDR);
  await page.click('button:has-text("Search")');
  // wait for building card to populate (pin) OR explicit empty state
  await page.waitForFunction(() => {
    const t = document.body.innerText;
    return /\b1\d{2}-?\d|pin\b/i.test(t) || /No Cook County parcel/i.test(t);
  }, { timeout: 25000 }).catch(() => note('WARN', 'building card did not populate within 25s'));
  await page.waitForTimeout(2000);
  const t = await page.locator('body').innerText();
  note(/\bpin\b/i.test(t) && !/No Cook County parcel/i.test(t) ? 'PASS' : 'FAIL', `building PIN shown`);
  note(/landlord record/i.test(t) ? 'PASS' : 'WARN', `landlord record row`);
  note(/year built/i.test(t) ? 'PASS' : 'WARN', `building facts (year built)`);
  note(/cta|stop/i.test(t) ? 'PASS' : 'WARN', `nearest CTA section`);
  note(/displacement/i.test(t) ? 'PASS' : 'WARN', `displacement section`);
  const bSec = (await page.locator('section').filter({ hasText: 'Building' }).first().innerText().catch(()=>''))?.slice(0,400);
  console.log('  --- building section text ---\n  ' + bSec.replace(/\n/g,'\n  '));
  await page.screenshot({ path: `${OUT}/shot_2_building.png`, fullPage: true });
} catch (e) { note('FAIL', `search flow: ${e.message}`); }

// Breadcrumb buttons + zoom to CCA
try {
  const btns = await page.locator('nav button').allInnerTexts();
  note('INFO', `breadcrumb: ${JSON.stringify(btns)}`);
  const ccaLabel = btns.find((b) => !/chicago/i.test(b));
  if (ccaLabel) {
    await page.locator(`nav button:has-text(${JSON.stringify(ccaLabel)})`).first().click();
    await page.waitForTimeout(3500);
  }
  const c = await page.locator('body').innerText();
  note(/safety score/i.test(c) ? 'PASS' : 'FAIL', `CCA Safety score`);
  note(/walk score/i.test(c) ? 'PASS' : 'WARN', `CCA Walk score`);
  note(/displacement score/i.test(c) ? 'PASS' : 'WARN', `CCA Displacement score`);
  note(/median rent/i.test(c) ? 'PASS' : 'WARN', `CCA Median rent`);
  note(/what this does not tell you/i.test(c) ? 'PASS' : 'WARN', `'What this does not tell you'`);
  note(/\/\s?10/.test(c) ? 'PASS' : 'WARN', `confidence /10 badges`);
  note(!/No data for this neighborhood/i.test(c) ? 'PASS' : 'FAIL', `CCA not empty ('No data...')`);
  const ccaSec = (await page.locator('section').filter({ hasText: /Neighborhood|score/i }).first().innerText().catch(()=>''))?.slice(0,500);
  console.log('  --- CCA section text ---\n  ' + ccaSec.replace(/\n/g,'\n  '));
  await page.screenshot({ path: `${OUT}/shot_3_cca.png`, fullPage: true });
} catch (e) { note('FAIL', `cca flow: ${e.message}`); }

note(await page.locator('canvas').count() ? 'PASS' : 'WARN', `map canvas present`);

console.log('\n--- API responses (geocode/rest) ---'); [...new Set(apiResp)].slice(0,25).forEach(x=>console.log('  '+x));
console.log('--- console errors ---'); [...new Set(consoleErrors)].slice(0,12).forEach(e=>console.log('  • '+e.slice(0,160)));
console.log('--- page errors ---'); [...new Set(pageErrors)].slice(0,12).forEach(e=>console.log('  • '+e.slice(0,160)));
console.log(`\nSUMMARY  PASS=${findings.filter(f=>f.sev==='PASS').length} WARN=${findings.filter(f=>f.sev==='WARN').length} FAIL=${findings.filter(f=>f.sev==='FAIL').length}`);
await browser.close();
