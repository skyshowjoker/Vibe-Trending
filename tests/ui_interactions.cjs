const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:960}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://localhost:8088');
  await page.locator('#projects button').first().waitFor();
  const response=await page.request.get('http://localhost:8088/api/projects');
  const projects=await response.json(),large=projects.find(p=>p.series.some(s=>s.points.length>100));
  if(!large)throw Error('Need a real project with at least 100 points');
  await page.locator('#project-search').fill(large.plan.title);
  await page.locator('#projects button').first().click();
  await page.locator('#workspace').waitFor({state:'visible'});
  await page.locator('[data-tab="data"]').click();
  if(await page.locator('#rows tr').count()!==50)throw Error('Pagination not bounded');
  const latest=await page.locator('#rows tr td').first().textContent();
  await page.locator('#next-page').click();
  if((await page.locator('#rows tr td').first().textContent())===latest)throw Error('Page did not change');
  await page.locator('#sort').selectOption('asc');
  if((await page.locator('#page-number').textContent()).trim().split('/')[0].trim()!=='1')throw Error('Sort did not reset page');
  await page.locator('#filter').fill('no-such-date');
  await page.locator('#rows .empty').waitFor();
  await page.locator('#filter').fill('');
  await page.locator('#rows button').first().click();
  await page.locator('#edit-dialog').waitFor({state:'visible'});
  await page.keyboard.press('Escape');
  await page.locator('#remove').click();
  await page.locator('#confirm-dialog').waitFor({state:'visible'});
  await page.locator('#confirm-dialog button[value="cancel"]').click();
  if(await page.locator('#workspace').isHidden())throw Error('Cancel deleted project');
  await page.locator('[data-tab="history"]').click();
  await page.locator('#versions button').first().click();
  await page.locator('#confirm-dialog').waitFor({state:'visible'});
  await page.keyboard.press('Escape');
  await page.locator('[data-tab="chart"]').click();
  for(const checkbox of await page.locator('#legend input').all())await checkbox.check();
  await page.locator('#chart-type').selectOption('area');
  await page.waitForTimeout(400);
  await page.locator('#chart').scrollIntoViewIfNeeded();
  const box=await page.locator('#chart').boundingBox();
  await page.locator('#chart').hover({position:{x:box.width/2,y:100}});
  await page.locator('#chart-tooltip').waitFor({state:'visible'});
  await page.screenshot({path:'.data/ui-desktop.png',fullPage:true});
  for(const width of [390,760,1024]){
   await page.setViewportSize({width,height:844});
   await page.waitForTimeout(100);
   for(const tab of ['chart','data','history']){
    await page.locator('[data-tab="'+tab+'"]').click();
    if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Overflow '+width+' '+tab);
   }
  }
  await page.setViewportSize({width:390,height:844});
  await page.locator('[data-tab="chart"]').click();
  await page.screenshot({path:'.data/ui-mobile.png',fullPage:true});
  await page.reload();
  await page.locator('#workspace').waitFor({state:'visible'});
  if(!(await page.locator('#title').textContent()).includes(large.plan.title))throw Error('Last project not restored');
  if(errors.length)throw Error(errors.join('\n'));
  console.log(JSON.stringify({pagination:true,sort:true,emptyState:true,dialogs:true,tooltip:true,restoreProject:true,responsiveWidths:[390,760,1024],pageErrors:errors}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
