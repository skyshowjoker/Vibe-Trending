const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 const page=await browser.newPage({viewport:{width:1440,height:960}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 let id;
 try{
  const plan={title:'Tushare MCP 验证',start_year:2024,end_year:2024,series:[{name:'半导体ETF 512480',indicator:'ETF每日收盘价',country:'CHN',unit:'元',frequency:'daily',source:'tushare',source_options:{api_name:'fund_daily',ts_code:'512480.SH',value_field:'close'}}]};
  await page.route('**/api/plan',r=>r.fulfill({json:{agent:'test-plan',plan}}));
  const created=await page.request.post('http://127.0.0.1:8088/api/projects',{data:{plan}});
  if(!created.ok())throw Error(await created.text());
  id=(await created.json()).id;
  await page.goto('http://127.0.0.1:8088');
  await page.evaluate(id=>localStorage.setItem('vibe-last-project',id),id);
  await page.reload();
  await page.waitForFunction(()=>!document.querySelector('#refresh').disabled);
  await page.locator('#refresh').click();
  await page.waitForFunction(()=>!document.querySelector('#refresh').disabled,{},{timeout:150000});
  const result=await (await page.request.get('http://127.0.0.1:8088/api/projects/'+id)).json();
  if(result.tasks[0].status!=='completed')throw Error(result.tasks[0].error);
  const s=result.series[0];
  if(s.source!=='tushare'||s.collector!=='jiuwenswarm'||s.points.length<200)throw Error('Missing live Tushare agent data');
  if(s.raw.evidence[0].mcp_server!=='tushareMcp')throw Error('Missing raw MCP evidence');
  if(JSON.stringify(s).includes('token='))throw Error('Credential URL leaked');
  await page.screenshot({path:'.data/tushare-data.png',fullPage:true});
  await page.locator('#new').click();
  await page.locator('#prompt-form button').click();
  await page.locator('#strategy').waitFor({state:'visible'});
  if(await page.locator('#plan-series select').first().inputValue()!=='fund_daily')throw Error('Wrong API control');
  await page.screenshot({path:'.data/tushare-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:'.data/tushare-mobile.png',fullPage:true});
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Mobile overflow');
  if(errors.length)throw Error(errors.join('\n'));
  console.log(JSON.stringify({points:s.points.length,collector:s.collector,source:s.source,tools:s.raw.agent_tools.map(t=>t.tool),pageErrors:errors}));
 }finally{
  if(id)await page.request.delete('http://127.0.0.1:8088/api/projects/'+id);
  await browser.close();
 }
})().catch(e=>{console.error(e);process.exit(1)});
