const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 let pid,page;
 try{
  page=await browser.newPage({viewport:{width:1440,height:960}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const plan={title:'Vibe 编辑交互测试',start_year:2020,end_year:2024,series:[{name:'中国 GDP',indicator:'NY.GDP.MKTP.CD',country:'CHN',unit:'美元',source:'worldbank',frequency:'annual'}]};
  const response=await page.request.post('http://localhost:8088/api/projects',{data:{plan}});const project=await response.json();pid=project.id;
  const candidate={...plan,title:'Vibe 编辑交互测试（更新）',series:[...plan.series,{...plan.series[0],name:'美国 GDP',country:'USA'}]};
  await page.route('**/vibe-edit',route=>route.fulfill({json:{plan:candidate,base_revision:project.updated_at,changes:{added:[candidate.series[1]],removed:[],retained:[candidate.series[0]]}}}));
  await page.goto('http://localhost:8088');
  await page.locator('#project-search').fill(plan.title);
  await page.locator('#projects button').first().click();
  await page.locator('#workspace').waitFor({state:'visible'});
  await page.locator('#vibe-edit').click();
  await page.locator('#vibe-prompt').fill('保留中国，新增美国GDP');
  await page.locator('#generate-edit').click();
  await page.locator('#vibe-preview').waitFor({state:'visible'});
  if(!(await page.locator('#vibe-diff').textContent()).includes('新增 1'))throw Error('Diff missing');
  await page.screenshot({path:'.data/vibe-edit.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  if(await page.locator('#vibe-dialog').evaluate(d=>d.scrollWidth>d.clientWidth))throw Error('Modal overflow');
  await page.locator('#cancel-vibe').click();
  const unchanged=await (await page.request.get('http://localhost:8088/api/projects/'+pid)).json();
  if(unchanged.plan.series.length!==1)throw Error('Preview mutated project');
  await page.locator('#vibe-edit').click();
  await page.locator('#vibe-prompt').fill('保留中国，新增美国GDP');
  await page.locator('#generate-edit').click();
  await page.locator('#vibe-preview').waitFor({state:'visible'});
  await page.locator('#vibe-collect').uncheck();
  await page.locator('#apply-vibe').click();
  await page.locator('#vibe-dialog').waitFor({state:'hidden'});
  const saved=await (await page.request.get('http://localhost:8088/api/projects/'+pid)).json();
  if(saved.plan.series.length!==2||saved.audit[0].kind!=='plan_edit')throw Error('Apply failed');
  if(errors.length)throw Error(errors.join('\n'));
  console.log(JSON.stringify({preview:true,cancelWithoutMutation:true,apply:true,mobileModal:true,pageErrors:errors}));
 }finally{if(pid&&page)await page.request.delete('http://localhost:8088/api/projects/'+pid);await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
