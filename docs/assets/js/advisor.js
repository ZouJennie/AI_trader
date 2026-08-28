const STORAGE_KEY = "ai-trader.actual-ledger.v1";
const $ = (id) => document.getElementById(id);
const money = (value) => new Intl.NumberFormat("en-US", {style:"currency", currency:"USD"}).format(Number(value) || 0);
const number = (value, digits=6) => (Number(value) || 0).toLocaleString("en-US", {maximumFractionDigits:digits});
const uid = () => globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;

let advice = {initial_cash:200, history:[], prices:{}};
let ledger = loadLedger();
let cloud = {client:null, user:null, saveTimer:null, reconciling:false};

function loadLedger(){
  try{
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if(saved && Array.isArray(saved.trades) && saved.priceOverrides) return {...saved, initialCash:Number(saved.initialCash)||200};
  }catch(error){ console.warn("无法读取本地交易记录", error); }
  return {version:1, initialCash:200, trades:[], priceOverrides:{}};
}

function normalizeLedger(value){
  return {
    version:1,
    initialCash:Number(value?.initialCash)||200,
    trades:Array.isArray(value?.trades)?value.trades:[],
    priceOverrides:value?.priceOverrides && typeof value.priceOverrides==="object"?value.priceOverrides:{},
    updatedAt:value?.updatedAt||""
  };
}

function saveLedger(sync=true){
  if(sync) ledger.updatedAt = new Date().toISOString();
  localStorage.setItem(STORAGE_KEY, JSON.stringify(ledger));
  if(sync) queueCloudSave();
}
function setText(id, value){ $(id).textContent = value; }
function signedMoney(value){ return `${value >= 0 ? "+" : "-"}${money(Math.abs(value))}`; }
function setGainClass(element, value){ element.classList.remove("positive","negative"); element.classList.add(value >= 0 ? "positive" : "negative"); }

const ADVICE_LABELS={DECISION:"投资结论",SYMBOL:"股票代码",TARGET_AMOUNT_USD:"建议投入金额（美元）",HORIZON_MONTHS:"预计持有期（月）",CONFIDENCE:"置信度",ENTRY_GATE:"综合买入门槛",FUNDAMENTAL_GATE:"基本面门槛",SEC_RISK_GATE:"SEC 风险门槛",TREND_GATE:"趋势门槛",PRICE_VS_SMA20_PCT:"价格相对 SMA20（%）",FAIR_VALUE_RANGE_USD:"合理价值区间（美元）",MARGIN_OF_SAFETY_PCT:"安全边际（%）",EXPECTED_GROSS_UPSIDE_PCT:"预期毛上涨空间（%）",ROUND_TRIP_COST_PCT:"往返交易成本（%）",EXPECTED_NET_UPSIDE_PCT:"扣费后预期上涨空间（%）",THESIS:"投资逻辑",RISKS:"主要风险",INVALIDATION:"逻辑失效条件",OFFICIAL_EVIDENCE:"官方证据",TREND_CONFIRMATION:"趋势确认",DATA_AS_OF:"数据截至"};
const ADVICE_VALUES={BUY:"买入",HOLD:"观望/持有",REDUCE:"减仓",PASS:"通过",FAIL:"未通过",NONE:"无",DATA_UNAVAILABLE:"数据不可用"};
function formatAdvice(item){
  const raw=String(item?.content||"").replaceAll("<FINISH_SIGNAL>","").trim();
  const translated=raw.split("\n").map(line=>{
    const match=line.match(/^([A-Z][A-Z0-9_]*):\s*(.*)$/);if(!match)return line;
    const label=ADVICE_LABELS[match[1]]||match[1];const value=ADVICE_VALUES[match[2]]||match[2];return `${label}：${value}`;
  }).join("\n");
  const execution=item?.execution_mode==="advisory"?"执行状态：仅提供投资建议，系统尚未自动下单；请按实际成交结果录入交易。":"执行状态：模拟交易模式";
  return `${execution}\n\n${translated}`.trim();
}

function syncConfigured(){
  const config=window.AI_TRADER_SYNC_CONFIG||{};
  return /^https:\/\/.+\.supabase\.co$/.test(config.url||"") && /^(sb_publishable_|eyJ)/.test(config.publishableKey||"");
}

function setCloudStatus(message,type=""){
  const status=$("cloudStatus");status.textContent=message;status.classList.remove("sync-ok","sync-error");if(type)status.classList.add(type);
}

function updateCloudControls(){
  const configured=syncConfigured();
  const signedIn=Boolean(cloud.user);$("syncEmail").hidden=signedIn;$("syncPassword").hidden=signedIn;$("signInPassword").hidden=signedIn;$("sendMagicLink").hidden=signedIn;$("newSyncPassword").hidden=!signedIn;$("setPassword").hidden=!signedIn;$("syncNow").hidden=!signedIn;$("signOut").hidden=!signedIn;
  $("syncEmail").disabled=!configured;$("syncPassword").disabled=!configured;$("signInPassword").disabled=!configured;$("sendMagicLink").disabled=!configured;$("newSyncPassword").disabled=!configured||!signedIn;$("setPassword").disabled=!configured||!signedIn;
  if(signedIn)setCloudStatus(`已登录 ${cloud.user.email||"Supabase"}，实际交易会自动同步。`,"sync-ok");
}

async function initializeCloudSync(){
  if(!syncConfigured()){updateCloudControls();setCloudStatus("当前为本机模式；请先填写 supabase-config.js。","");return;}
  if(!window.supabase?.createClient){setCloudStatus("Supabase 客户端加载失败，仍使用本机记录。","sync-error");return;}
  const config=window.AI_TRADER_SYNC_CONFIG;
  cloud.client=window.supabase.createClient(config.url,config.publishableKey,{auth:{persistSession:true,autoRefreshToken:true,detectSessionInUrl:true}});
  const {data,error}=await cloud.client.auth.getSession();
  if(error){setCloudStatus(`登录状态读取失败：${error.message}`,"sync-error");return;}
  cloud.user=data.session?.user||null;updateCloudControls();
  if(cloud.user)await reconcileCloud();
  cloud.client.auth.onAuthStateChange((_event,session)=>{
    const previous=cloud.user?.id;cloud.user=session?.user||null;updateCloudControls();
    if(cloud.user && cloud.user.id!==previous)setTimeout(()=>reconcileCloud(),0);
  });
}

async function sendMagicLink(){
  if(!cloud.client){setCloudStatus("Supabase 尚未配置，当前仅保存在本机。","sync-error");return;}
  const email=$("syncEmail").value.trim();if(!email){setCloudStatus("请先填写邮箱。","sync-error");return;}
  setCloudStatus("正在发送登录链接…");
  const redirectTo=`${window.location.origin}${window.location.pathname}`;
  const {error}=await cloud.client.auth.signInWithOtp({email,options:{emailRedirectTo:redirectTo}});
  setCloudStatus(error?`发送失败：${error.message}`:"登录链接已发送，请在同一设备打开邮件完成登录。",error?"sync-error":"sync-ok");
}

async function signInWithPassword(){
  if(!cloud.client){setCloudStatus("Supabase 尚未配置，当前仅保存在本机。","sync-error");return;}
  const email=$("syncEmail").value.trim();const password=$("syncPassword").value;
  if(!email||!password){setCloudStatus("请输入邮箱和密码。","sync-error");return;}
  setCloudStatus("正在登录…");
  const {error}=await cloud.client.auth.signInWithPassword({email,password});
  if(error)setCloudStatus(`登录失败：${error.message}`,"sync-error");
  else $("syncPassword").value="";
}

async function setAccountPassword(){
  if(!cloud.client||!cloud.user){setCloudStatus("请先通过邮件链接登录一次。","sync-error");return;}
  const password=$("newSyncPassword").value;
  if(password.length<8){setCloudStatus("新密码至少需要 8 位。","sync-error");return;}
  setCloudStatus("正在设置密码…");
  const {error}=await cloud.client.auth.updateUser({password});
  if(error)setCloudStatus(`密码设置失败：${error.message}`,"sync-error");
  else{$("newSyncPassword").value="";setCloudStatus("密码设置成功；主屏幕 App 现在可以直接登录。","sync-ok");}
}

function queueCloudSave(){
  if(!cloud.client||!cloud.user||cloud.reconciling)return;
  clearTimeout(cloud.saveTimer);cloud.saveTimer=setTimeout(()=>pushCloudLedger(),600);
}

async function pushCloudLedger(){
  if(!cloud.client||!cloud.user)return;
  const updatedAt=ledger.updatedAt||new Date().toISOString();
  const {error}=await cloud.client.from("user_ledgers").upsert({user_id:cloud.user.id,ledger,updated_at:updatedAt},{onConflict:"user_id"});
  setCloudStatus(error?`云端保存失败：${error.message}`:`已同步 ${new Date().toLocaleTimeString("zh-CN",{hour12:false})}`,error?"sync-error":"sync-ok");
}

async function reconcileCloud(){
  if(!cloud.client||!cloud.user||cloud.reconciling)return;
  cloud.reconciling=true;setCloudStatus("正在核对云端台账…");
  try{
    const {data,error}=await cloud.client.from("user_ledgers").select("ledger,updated_at").eq("user_id",cloud.user.id).maybeSingle();
    if(error)throw error;
    const localTime=Date.parse(ledger.updatedAt||0)||0;const remoteTime=Date.parse(data?.updated_at||data?.ledger?.updatedAt||0)||0;
    if(data?.ledger && remoteTime>localTime){ledger=normalizeLedger(data.ledger);saveLedger(false);renderAll();setCloudStatus("已载入更新的云端台账。","sync-ok");}
    else await pushCloudLedger();
  }catch(error){setCloudStatus(`同步失败：${error.message}`,"sync-error");}
  finally{cloud.reconciling=false;}
}

async function signOutCloud(){
  if(!cloud.client)return;const {error}=await cloud.client.auth.signOut();if(error)setCloudStatus(`退出失败：${error.message}`,"sync-error");
}

async function loadAdvice(){
  try{
    const response = await fetch(`data/advice.json?v=${Date.now()}`, {cache:"no-store"});
    if(!response.ok) throw new Error(`HTTP ${response.status}`);
    advice = await response.json();
    ledger.initialCash = Number(advice.initial_cash) || ledger.initialCash || 200;
  }catch(error){ console.warn("建议数据暂不可用", error); }
  renderAdvice();
  renderAll();
}

function renderAdvice(){
  if(advice.generated_at){
    const stamp = new Date(advice.generated_at);
    setText("generatedAt", Number.isNaN(stamp.getTime()) ? advice.generated_at : stamp.toLocaleString("zh-CN", {hour12:false}));
  }
  const latest = advice.latest;
  if(latest){
    setText("adviceDate", latest.date || "最新");
    const content = $("adviceContent");
    content.textContent = formatAdvice(latest) || "本次没有输出建议。";
    content.classList.remove("empty");
  }
  const history = $("adviceHistory");
  history.replaceChildren();
  (advice.history || []).slice().reverse().forEach(item => {
    const box = document.createElement("article"); box.className = "history-item";
    const date = document.createElement("strong"); date.textContent = item.date || "未知日期";
    const body = document.createElement("pre"); body.textContent = formatAdvice(item);
    box.append(date, body); history.append(box);
  });
  if(!history.children.length) history.textContent = "暂无历史建议。";
}

function orderedTrades(){
  return ledger.trades.slice().sort((a,b) => `${a.date}-${a.createdAt||a.id}`.localeCompare(`${b.date}-${b.createdAt||b.id}`));
}

function calculatePortfolio(){
  const positions = {};
  let cash = Number(ledger.initialCash) || 200;
  let fees = 0;
  for(const trade of orderedTrades()){
    const symbol = trade.symbol;
    const notional = Number(trade.notional);
    const price = Number(trade.price);
    const fee = Number(trade.fee) || 0;
    const qty = notional / price;
    if(!positions[symbol]) positions[symbol] = {qty:0, avgCost:0, realized:0};
    const position = positions[symbol];
    fees += fee;
    if(trade.side === "buy"){
      const oldBasis = position.qty * position.avgCost;
      position.qty += qty;
      position.avgCost = position.qty > 0 ? (oldBasis + notional + fee) / position.qty : 0;
      cash -= notional + fee;
    }else{
      const soldQty = Math.min(qty, position.qty);
      const calculated = notional - fee - soldQty * position.avgCost;
      position.realized += Number.isFinite(Number(trade.pnlOverride)) && trade.pnlOverride !== "" ? Number(trade.pnlOverride) : calculated;
      position.qty = Math.max(0, position.qty - soldQty);
      cash += notional - fee;
      if(position.qty < 1e-9){ position.qty = 0; position.avgCost = 0; }
    }
  }
  let marketValue = 0;
  for(const [symbol, position] of Object.entries(positions)){
    const mark = getMark(symbol, position.avgCost);
    position.mark = mark.price;
    position.markSource = mark.source;
    position.marketValue = position.qty * position.mark;
    position.unrealized = position.marketValue - position.qty * position.avgCost;
    marketValue += position.marketValue;
  }
  return {positions, cash, fees, marketValue, equity:cash+marketValue};
}

function getMark(symbol, fallback){
  const override = Number(ledger.priceOverrides[symbol]);
  if(override > 0) return {price:override, source:"手动"};
  const automatic = Number(advice.prices?.[symbol]?.price);
  if(automatic > 0) return {price:automatic, source:`自动 ${advice.prices[symbol].timestamp || ""}`.trim()};
  return {price:Number(fallback)||0, source:"成本价（无行情）"};
}

function renderAll(){
  const portfolio = calculatePortfolio();
  const total = portfolio.equity - ledger.initialCash;
  const rate = ledger.initialCash ? total / ledger.initialCash * 100 : 0;
  setText("equity", money(portfolio.equity)); setText("equityHint", `本金 ${money(ledger.initialCash)}`);
  setText("totalReturn", signedMoney(total)); setText("returnRate", `${rate >= 0 ? "+" : ""}${rate.toFixed(2)}%`);
  setGainClass($("totalReturn"), total); setGainClass($("returnRate"), total);
  setText("cash", money(portfolio.cash)); setText("invested", `持仓市值 ${money(portfolio.marketValue)}`);
  setText("fees", money(portfolio.fees)); setText("tradeCount", `${ledger.trades.length} 笔实际交易`);
  renderPositions(portfolio.positions); renderTrades(); renderPriceEditor(portfolio.positions);
}

function emptyRow(body, columns, text){
  body.replaceChildren(); const row = body.insertRow(); const cell = row.insertCell(); cell.colSpan=columns; cell.textContent=text; cell.className="empty";
}

function renderPositions(positions){
  const body = $("positionsBody"); body.replaceChildren();
  const active = Object.entries(positions).filter(([,p]) => p.qty > 1e-9 || Math.abs(p.realized) > .005);
  if(!active.length){ emptyRow(body,7,"尚无实际持仓"); return; }
  active.forEach(([symbol,p]) => {
    const row = body.insertRow();
    [symbol,number(p.qty),money(p.avgCost),`${money(p.mark)} · ${p.markSource}`,money(p.marketValue),signedMoney(p.unrealized),signedMoney(p.realized)].forEach((value,index) => {
      const cell=row.insertCell(); cell.textContent=value; if(index===0) cell.className="symbol"; if(index===5||index===6) setGainClass(cell,index===5?p.unrealized:p.realized);
    });
  });
}

function renderTrades(){
  const body = $("tradesBody"); body.replaceChildren();
  const trades = ledger.trades.slice().sort((a,b) => `${b.date}-${b.createdAt||b.id}`.localeCompare(`${a.date}-${a.createdAt||a.id}`));
  if(!trades.length){ emptyRow(body,8,"尚未录入实际交易"); return; }
  trades.forEach(trade => {
    const row = body.insertRow(); const qty = Number(trade.notional)/Number(trade.price);
    const values=[trade.date,trade.side==="buy"?"买入":"卖出",trade.symbol,money(trade.notional),money(trade.price),number(qty),money(trade.fee)];
    values.forEach((value,index)=>{const cell=row.insertCell();cell.textContent=value;if(index===1)cell.className=trade.side;});
    const actions=row.insertCell(); actions.className="action-cell";
    const edit=document.createElement("button"); edit.type="button";edit.className="ghost";edit.textContent="修改";edit.addEventListener("click",()=>startEdit(trade.id));
    const remove=document.createElement("button");remove.type="button";remove.className="ghost";remove.textContent="删除";remove.addEventListener("click",()=>deleteTrade(trade.id));
    actions.append(edit,remove);
  });
}

function renderPriceEditor(positions){
  const editor=$("priceEditor");editor.replaceChildren();
  const active=Object.entries(positions).filter(([,p])=>p.qty>1e-9);
  if(!active.length){editor.textContent="录入买入交易后即可修正持仓价格。";editor.className="price-editor empty";return;}
  editor.className="price-editor";
  active.forEach(([symbol,p])=>{
    const row=document.createElement("div");row.className="price-row";
    const label=document.createElement("div");const strong=document.createElement("strong");strong.textContent=symbol;const small=document.createElement("small");small.textContent=getMark(symbol,p.avgCost).source;label.append(strong,small);
    const input=document.createElement("input");input.type="number";input.min="0.0001";input.step="0.0001";input.placeholder=String(advice.prices?.[symbol]?.price || p.avgCost || "");input.value=ledger.priceOverrides[symbol]??"";input.setAttribute("aria-label",`${symbol} 当前价格修正`);
    input.addEventListener("change",()=>{const value=Number(input.value);if(value>0)ledger.priceOverrides[symbol]=value;else delete ledger.priceOverrides[symbol];saveLedger();renderAll();});
    row.append(label,input);editor.append(row);
  });
}

function validateTrade(candidate, editingId){
  if(!/^([A-Z][A-Z0-9.-]{0,9})$/.test(candidate.symbol)) return "请输入有效的美股代码。";
  if(!(candidate.notional>0) || !(candidate.price>0) || candidate.fee<0) return "成交金额和成交价必须大于 0，手续费不能为负数。";
  const trial=ledger.trades.filter(t=>t.id!==editingId).concat(candidate)
    .sort((a,b)=>`${a.date}-${a.createdAt||a.id}`.localeCompare(`${b.date}-${b.createdAt||b.id}`));
  const holdings={};
  for(const trade of trial){
    const quantity=Number(trade.notional)/Number(trade.price);
    holdings[trade.symbol]=holdings[trade.symbol]||0;
    if(trade.side==="buy") holdings[trade.symbol]+=quantity;
    else if(quantity>holdings[trade.symbol]+1e-7) return `${trade.date} 的 ${trade.symbol} 卖出份额超过当时持仓（最多 ${number(holdings[trade.symbol])} 股）。`;
    else holdings[trade.symbol]-=quantity;
  }
  return "";
}

function resetForm(){
  $("tradeForm").reset();$("tradeDate").value=new Date().toISOString().slice(0,10);$("tradeFee").value="1.00";$("tradeId").value="";$("cancelEdit").hidden=true;setText("formTitle","录入实际交易");setText("formError","");
}

function startEdit(id){
  const trade=ledger.trades.find(t=>t.id===id);if(!trade)return;
  $("tradeId").value=trade.id;$("tradeDate").value=trade.date;$("tradeSide").value=trade.side;$("symbol").value=trade.symbol;$("notional").value=trade.notional;$("executionPrice").value=trade.price;$("tradeFee").value=trade.fee;$("pnlOverride").value=trade.pnlOverride??"";$("tradeNote").value=trade.note||"";$("cancelEdit").hidden=false;setText("formTitle","修改实际交易");$("tradeForm").scrollIntoView({behavior:"smooth",block:"center"});
}

function deleteTrade(id){
  if(!confirm("确定删除这笔实际交易吗？"))return;
  ledger.trades=ledger.trades.filter(t=>t.id!==id);saveLedger();renderAll();
}

function submitTrade(event){
  event.preventDefault();const editingId=$("tradeId").value;
  const candidate={id:editingId||uid(),createdAt:ledger.trades.find(t=>t.id===editingId)?.createdAt||new Date().toISOString(),date:$("tradeDate").value,side:$("tradeSide").value,symbol:$("symbol").value.trim().toUpperCase(),notional:Number($("notional").value),price:Number($("executionPrice").value),fee:Number($("tradeFee").value),pnlOverride:$("pnlOverride").value===""?"":Number($("pnlOverride").value),note:$("tradeNote").value.trim()};
  const error=validateTrade(candidate,editingId);setText("formError",error);if(error)return;
  const index=ledger.trades.findIndex(t=>t.id===editingId);if(index>=0)ledger.trades[index]=candidate;else ledger.trades.push(candidate);
  saveLedger();resetForm();renderAll();
}

function exportLedger(){
  const blob=new Blob([JSON.stringify({...ledger,exportedAt:new Date().toISOString()},null,2)],{type:"application/json"});const url=URL.createObjectURL(blob);const link=document.createElement("a");link.href=url;link.download=`ai-trader-ledger-${new Date().toISOString().slice(0,10)}.json`;link.click();URL.revokeObjectURL(url);
}

async function importLedger(event){
  const file=event.target.files?.[0];if(!file)return;
  try{const incoming=JSON.parse(await file.text());if(!Array.isArray(incoming.trades)||typeof incoming.priceOverrides!=="object")throw new Error("格式不正确");if(!confirm(`导入将覆盖当前 ${ledger.trades.length} 笔记录，是否继续？`))return;ledger={version:1,initialCash:Number(incoming.initialCash)||200,trades:incoming.trades,priceOverrides:incoming.priceOverrides||{}};saveLedger();resetForm();renderAll();}
  catch(error){alert(`导入失败：${error.message}`);}finally{event.target.value="";}
}

$("tradeForm").addEventListener("submit",submitTrade);$("cancelEdit").addEventListener("click",resetForm);$("exportData").addEventListener("click",exportLedger);$("importData").addEventListener("change",importLedger);$("sendMagicLink").addEventListener("click",sendMagicLink);$("signInPassword").addEventListener("click",signInWithPassword);$("syncPassword").addEventListener("keydown",event=>{if(event.key==="Enter")signInWithPassword();});$("setPassword").addEventListener("click",setAccountPassword);$("newSyncPassword").addEventListener("keydown",event=>{if(event.key==="Enter")setAccountPassword();});$("syncNow").addEventListener("click",reconcileCloud);$("signOut").addEventListener("click",signOutCloud);
resetForm();loadAdvice();initializeCloudSync();
