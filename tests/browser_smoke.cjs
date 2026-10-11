const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'chrome'});
  const page=await browser.newPage({viewport:{width:1440,height:960}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  // Isolate UI regression from nondeterministic external model planning.
  await page.route('**/api/plan',route=>route.fulfill({json:{agent:'test-plan',plan:{title:'中美人均 GDP 对比',start_year:2015,end_year:2024,series:[{name:'中国人均 GDP',country:'CHN',indicator:'NY.GDP.PCAP.CD',unit:'美元/人',source:'worldbank',frequency:'annual'},{name:'美国人均 GDP',country:'USA',indicator:'NY.GDP.PCAP.CD',unit:'美元/人',source:'worldbank',frequency:'annual'}]}}}));
  await page.goto('http://127.0.0.1:8088');
  await page.locator('#prompt-form button').click();
  await page.locator('#strategy').waitFor({state:'visible',timeout:120000});
  await page.locator('#confirm').click();
  await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('采集完成'),{},{timeout:120000});
  await page.waitForFunction(()=>!document.querySelector('#refresh').disabled);
  await page.screenshot({path:'.data/desktop.png',fullPage:true});
  const canvas=await page.locator('canvas').evaluate(c=>{
    const pixels=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
    return Array.from(pixels).filter((v,i)=>i%4!==3 && v<220).length;
  });
  if(canvas<100)throw Error('Blank chart');
  await page.locator('[data-tab="data"]').click();
  if(await page.locator('#rows tr').count()<5)throw Error('Missing real data');
  await page.locator('[data-tab="chart"]').click();
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:'.data/mobile.png',fullPage:true});
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
  if(overflow)throw Error('Mobile overflow');
  if(errors.length)throw Error(errors.join('\n'));
  console.log(JSON.stringify({realDataRows:await page.locator('#rows tr').count(),canvasPixels:canvas,pageErrors:errors,mobileOverflow:overflow}));
  await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
