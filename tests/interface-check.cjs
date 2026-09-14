// No browser automation: execute UI render paths and controls in a DOM stub.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const root=path.resolve(__dirname,'..');
const html=fs.readFileSync(path.join(root,'dist/index.html'),'utf8');
const data=html.match(/<script id="economic-data" type="application\/json">([\s\S]*?)<\/script>/)[1];
const elements=new Map();
function element(id){if(!elements.has(id))elements.set(id,{textContent:'',innerHTML:'',hidden:false,style:{},value:'',classList:{toggle(){}},setAttribute(){},getBoundingClientRect(){return {x:0,y:0}},click(){}});return elements.get(id);}
element('economic-data').textContent=data;
const tools=[];
const sandbox={console,Date,Intl,Number,String,Map,Set,Math,Object,JSON,Promise,Error,URL,Blob,NaN,
document:{getElementById:element,querySelectorAll(){return []},createElement(){return element('download')},modelContext:{registerTool(t){tools.push(t)}}},
window:{innerWidth:1440,innerHeight:900,history:{replaceState(){}},scrollTo(){},addEventListener(){},print(){}},
location:{hash:''},setTimeout(){},navigator:{}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(path.join(root,'templates/app.js'),'utf8'),sandbox);
const evaluate=expr=>vm.runInContext(expr,sandbox);
for(const view of ['overview','industries','costs','trade','scenarios','outlook','sources']){
 evaluate(`switchView('${view}')`);assert.ok(element('content').innerHTML.length>1000,view);
 assert.ok(!element('content').innerHTML.includes('>NaN<'),view+' has invalid number');
 const ids=[...element('content').innerHTML.matchAll(/\bid="([^"]+)"/g)].map(x=>x[1]);
 assert.equal(ids.length,new Set(ids).size,view+' duplicate ids');
 console.log('Rendered markup:',view);
}
evaluate("state.geo='BC';state.industry='industry_manufacturing';switchView('industries')");
assert.ok(element('content').innerHTML.includes('British Columbia · permits'));
evaluate("state.geo='CA';switchView('industries')");assert.ok(element('content').innerHTML.includes('Canada · permits'));
evaluate("state.partner='Mexico';switchView('trade')");assert.ok(element('content').innerHTML.includes('Mexico exports'));
const all=evaluate("state.history='all';rows('cpi_CA').length");
const two=evaluate("state.history='24';rows('cpi_CA').length");assert.ok(all>two);
assert.equal(evaluate("csvText(['cpi_CA'],true).split('\\r\\n').length"),two+1);
assert.ok(Math.abs(evaluate('calculateScenario(defaults).incremental_cost')-660400)<.001);
assert.throws(()=>evaluate('calculateScenario({...defaults,material_share:80,labour_share:50})'));
evaluate("state.quarter=DATA.quarters[0].id;switchView('outlook')");assert.ok(element('content').innerHTML.includes('Interim quarter'));
sandbox.window.innerWidth=390;evaluate("switchView('costs')");assert.ok(element('content').innerHTML.includes('mobilebars'));
assert.equal(tools.length,2);assert.ok(tools.every(t=>t.annotations&&t.inputSchema));
const read=tools.find(t=>t.name==='get_economic_monitor_context');
const navigate=tools.find(t=>t.name==='navigate_economic_monitor');
(async()=>{assert.equal((await read.execute({})).view.view,'costs');assert.equal((await navigate.execute({view:'trade'})).view,'trade');await assert.rejects(navigate.execute({view:'invalid'}));console.log('PASS: view filters, CSV scope, scenarios, quarter coverage and mock WebMCP state. No visual browser QA.');})().catch(e=>{console.error(e);process.exitCode=1});
