PAGE = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Пиксель — приватный питомец</title>
<style>
  :root { --navy:#34568b; --navy-d:#28406b; --bg:#0f1420; --card:#182031; --line:#2a3550; --text:#e8ecf4; --muted:#8b97b3; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:system-ui,Segoe UI,Roboto,sans-serif; background:var(--bg); color:var(--text); }
  .wrap { max-width:720px; margin:0 auto; padding:20px 16px 40px; }
  h1 { font-size:20px; margin:0 0 2px; }
  .sub { color:var(--muted); font-size:13px; margin-bottom:16px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:14px; padding:18px; margin-bottom:16px; }
  .face { font-size:34px; text-align:center; letter-spacing:2px; padding:10px 0 4px; }
  .mood { text-align:center; color:var(--navy); font-weight:600; text-transform:uppercase; letter-spacing:1px; font-size:12px; margin-bottom:14px; }
  .stat { margin:10px 0; }
  .stat .row { display:flex; justify-content:space-between; font-size:12px; color:var(--muted); margin-bottom:4px; }
  .bar { height:9px; background:#0d1626; border-radius:6px; overflow:hidden; }
  .bar > i { display:block; height:100%; background:var(--navy); transition:width .4s; }
  .meta { display:flex; gap:16px; justify-content:center; color:var(--muted); font-size:12px; margin-top:10px; }
  #log { height:300px; overflow-y:auto; display:flex; flex-direction:column; gap:8px; padding-right:4px; }
  .msg { max-width:82%; padding:9px 12px; border-radius:12px; font-size:14px; line-height:1.4; white-space:pre-wrap; }
  .me { align-self:flex-end; background:var(--navy-d); }
  .pet { align-self:flex-start; background:#101a2c; border:1px solid var(--line); }
  .sys { align-self:center; color:var(--muted); font-size:12px; }
  form { display:flex; gap:8px; margin-top:12px; }
  input { flex:1; background:#0d1626; border:1px solid var(--line); color:var(--text); border-radius:10px; padding:11px 12px; font-size:14px; }
  input:focus { outline:none; border-color:var(--navy); }
  button { background:var(--navy); color:#fff; border:0; border-radius:10px; padding:0 18px; font-size:14px; cursor:pointer; }
  button:disabled { opacity:.5; cursor:default; }
  .foot { color:var(--muted); font-size:11px; text-align:center; margin-top:6px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Пиксель</h1>
  <div class="sub">Приватный питомец на локальной LLM. Живёт на маленьком сервере, кормится вопросами.</div>

  <div class="card">
    <div class="face" id="face">( &middot; &omega; &middot; )</div>
    <div class="mood" id="mood">...</div>
    <div class="stat"><div class="row"><span>Сытость</span><span id="fv">0</span></div><div class="bar"><i id="fb" style="width:0%"></i></div></div>
    <div class="stat"><div class="row"><span>Энергия</span><span id="ev">0</span></div><div class="bar"><i id="eb" style="width:0%"></i></div></div>
    <div class="meta"><span>кормлений: <b id="feeds">0</b></span><span>возраст: <b id="age">0</b> ч</span></div>
  </div>

  <div class="card">
    <div id="log"><div class="sys">Скажи Пикселю что-нибудь.</div></div>
    <form id="f">
      <input id="in" placeholder="Спроси или поболтай..." autocomplete="off" maxlength="500">
      <button id="b" type="submit">Дать</button>
    </form>
    <div class="foot">1 сообщение = 1 лакомство. Слишком часто — питомец объедается.</div>
  </div>
</div>
<script>
const FACES = {
  "довольный":"( ^ ‿ ^ )", "спокойный":"( · ω · )",
  "голодный":"( ; ω ; )", "сонный":"( ˘ ω ˘ )", "объелся":"( >､< )"
};
const log=document.getElementById('log'), input=document.getElementById('in'), btn=document.getElementById('b');
function paint(p){
  document.getElementById('face').textContent = FACES[p.mood] || FACES["спокойный"];
  document.getElementById('mood').textContent = p.mood;
  document.getElementById('fv').textContent = p.fullness;
  document.getElementById('ev').textContent = p.energy;
  document.getElementById('fb').style.width = p.fullness+'%';
  document.getElementById('eb').style.width = p.energy+'%';
  document.getElementById('feeds').textContent = p.feeds;
  document.getElementById('age').textContent = p.age_hours;
}
function add(cls,text){ const d=document.createElement('div'); d.className='msg '+cls; d.textContent=text; log.appendChild(d); log.scrollTop=log.scrollHeight; }
async function refresh(){ try{ const r=await fetch('/pet'); paint(await r.json()); }catch(e){} }
document.getElementById('f').addEventListener('submit', async (e)=>{
  e.preventDefault();
  const msg=input.value.trim(); if(!msg) return;
  add('me',msg); input.value=''; btn.disabled=true;
  try{
    const r=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:msg})});
    const d=await r.json();
    if(d.clipped) add('sys','(сообщение обрезано до 500 символов)');
    add('pet',d.reply||'...');
    if(d.pet) paint(d.pet);
  }catch(e){ add('sys','сервер не ответил, попробуй ещё раз'); }
  btn.disabled=false; input.focus();
});
refresh(); setInterval(refresh, 7000);
</script>
</body>
</html>
"""
