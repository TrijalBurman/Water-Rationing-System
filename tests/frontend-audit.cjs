/* Read-only visual and keyboard audit; see docs/verification.md. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require('../.runtime/browser/node_modules/playwright');

(async () => {
  const root = path.resolve(__dirname, '..');
  const base = process.env.TEST_BASE_URL || 'http://127.0.0.1:8010';
  await fs.mkdir(path.join(root, '.runtime/dark-review'), {recursive:true});
  const browser = await chromium.launch({headless:true,args:['--no-sandbox']});
  const context = await browser.newContext({viewport:{width:1440,height:1100},reducedMotion:'reduce'});
  const page = await context.newPage();
  const errors=[]; const external=[]; const results=[];
  page.on('pageerror', error=>errors.push(error.message));
  page.on('request', request=>{if(new URL(request.url()).origin !== new URL(base).origin)external.push(request.url());});
  const pass=label=>{results.push(label);console.log('PASS '+label);};
  try {
    await page.goto(base + '/frontend/');
    await page.waitForFunction(()=>document.getElementById('level-value').textContent!=='—');
    await page.evaluate(()=>document.fonts.ready);
    assert.equal(await page.evaluate(()=>document.fonts.check('14px Manrope') && document.fonts.check('40px "Space Grotesk"')),true);
    pass('Local display and interface fonts loaded');
    const color=await page.evaluate(()=>getComputedStyle(document.documentElement).backgroundColor);
    console.log('CANVAS '+color);
    await page.locator('#flow-chart svg').waitFor();
    await page.locator('#flow-chart').focus();
    await page.keyboard.press('ArrowLeft');
    await page.locator('#chart-tooltip').waitFor({state:'visible'});
    assert.ok((await page.locator('#chart-announcement').textContent()).includes('liters per minute'));
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#chart-tooltip').isVisible(),false);
    pass('Keyboard chart inspection and dismissal');
    await page.locator('#page-title').click();
    await page.addScriptTag({path:path.join(root,'.runtime/browser/node_modules/axe-core/axe.min.js')});
    const accessibility=[];
    for (const view of ['overview','activity','health','controls']) {
      await page.locator(`[data-view="${view}"]`).click();
      await page.screenshot({path:path.join(root,`.runtime/dark-review/${view}-desktop.png`),fullPage:true});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
      const report=await page.evaluate(async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return r.violations.map(v=>({id:v.id,impact:v.impact,help:v.help,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}));});
      accessibility.push({view,violations:report});
      pass('Desktop '+view+' view fits viewport');
    }
    await page.locator('[data-view="health"]').click();
    await page.locator('.skip-link').focus();
    await page.keyboard.press('Enter');
    assert.equal(await page.evaluate(()=>location.hash),'#health');
    assert.equal(await page.evaluate(()=>document.activeElement.id),'page-title');
    pass('Skip link focuses heading without changing the current view');
    await page.locator('[data-view="activity"]').click();
    await page.locator('.table-scroll').focus();
    await page.keyboard.press('End');
    assert.equal(await page.locator('.table-scroll').evaluate(el=>el.clientHeight<=570),true);
    assert.equal(await page.locator('th').first().evaluate(el=>getComputedStyle(el).position),'sticky');
    pass('History has a bounded keyboard-accessible scroll area and sticky headers');
    await page.locator('[data-view="overview"]').click();
    await page.locator('#tips-button').click();
    await page.locator('#tips-dialog').waitFor({state:'visible'});
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#tips-dialog').isVisible(),false);
    assert.equal(await page.evaluate(()=>document.activeElement.id),'tips-button');
    pass('Tips dialog closes and restores focus');
    for (const width of [768,390,320]) {
      await page.setViewportSize({width,height:900});
      for(const view of ['overview','health','controls','activity']) {
        if(width<=700) await page.locator('#menu-button').click();
        await page.locator(`[data-view="${view}"]`).click();
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`${view} at ${width}px overflows`);
        if(width===390) {
          await page.screenshot({path:path.join(root,`.runtime/dark-review/${view}-mobile.png`),fullPage:true});
          const report=await page.evaluate(async()=>{const r=await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return r.violations.map(v=>({id:v.id,impact:v.impact,help:v.help,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}));});
          accessibility.push({view:view+'-mobile',violations:report});
        }
      }
      pass(`All views fit ${width}px`);
    }
    await page.setViewportSize({width:390,height:844});
    await page.locator('#menu-button').click();
    assert.equal(await page.evaluate(()=>document.querySelector('main').inert),true);
    assert.equal(await page.evaluate(()=>document.getElementById('sidebar').contains(document.activeElement)),true);
    for(let index=0;index<14;index++) {
      await page.keyboard.press('Tab');
      assert.equal(await page.evaluate(()=>document.getElementById('sidebar').contains(document.activeElement)),true);
    }
    await page.keyboard.press('Escape');
    assert.equal(await page.evaluate(()=>document.activeElement.id),'menu-button');
    assert.equal(await page.evaluate(()=>document.querySelector('main').inert),false);
    pass('Mobile keyboard focus remains in menu and returns on Escape');
    assert.deepEqual(errors,[]); assert.deepEqual(external,[]);
    pass('No uncaught errors or external asset requests');
    await fs.writeFile(path.join(root,'.runtime/dark-review/accessibility.json'),JSON.stringify(accessibility,null,2));
    await fs.writeFile(path.join(root,'.runtime/dark-review/results.json'),JSON.stringify({checks:results,pageErrors:errors,externalRequests:external},null,2));
    console.log('ACCESSIBILITY '+JSON.stringify(accessibility));
    assert.equal(accessibility.reduce((count,item)=>count+item.violations.length,0),0,'Accessibility violations remain');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
