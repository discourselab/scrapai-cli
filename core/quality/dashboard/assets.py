"""The dashboard's CSS/JS — one generic interactive-table engine (sort · facet · search ·
select · expand · tooltip) written once in vanilla JS/CSS, instantiated by every tab and
reused by the sibling overview dashboard. The two strings are moved VERBATIM from the
original single-file module (byte-sacred: the golden gate diffs the rendered output); the
package facade re-exports them under the legacy `_CSS` / `_JS` names."""

# --------------------------------------------------------------------------- CSS / JS
CSS = """
:root{--bg:#0f1720;--card:#16212e;--line:#26364a;--fg:#e6edf3;--mut:#93a4b8;--acc:#4da3ff;
 --green:#2ea043;--amber:#d29922;--red:#e5534b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
header{padding:16px 24px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--bg);z-index:5}
h1{margin:0;font-size:18px}
.meta{color:var(--mut);font-size:12px;margin-top:4px}
nav{display:flex;gap:4px;padding:12px 24px 0}
nav button{background:var(--card);color:var(--fg);border:1px solid var(--line);border-bottom:none;
 padding:8px 16px;cursor:pointer;border-radius:6px 6px 0 0;font-size:13px}
nav button.active{background:var(--acc);color:#04121f;font-weight:600}
main{padding:0 24px 60px}
section{display:none;border:1px solid var(--line);border-radius:0 8px 8px 8px;background:var(--card);padding:14px}
section.active{display:block}
.fx-facets{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:4px 0 12px}
.facet{background:#0b131c;color:var(--fg);border:1px solid var(--line);border-radius:14px;
 padding:3px 11px;cursor:pointer;font-size:12px}
.facet b{color:var(--mut);font-weight:600}
.facet.on{outline:2px solid var(--acc);color:#fff}
.att{color:var(--mut);font-size:12px;display:flex;align-items:center;gap:4px;cursor:pointer}
.fx-search{background:#0b131c;color:var(--fg);border:1px solid var(--line);border-radius:6px;
 padding:4px 8px;font-size:12px;min-width:170px;margin-left:auto}
.clear{background:var(--card);color:var(--mut);border:1px solid var(--line);border-radius:6px;padding:4px 8px;
cursor:pointer;font-size:12px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border-bottom:1px solid var(--line);padding:6px 10px;text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:600;cursor:pointer;white-space:nowrap;position:sticky;top:57px;background:var(--card)}
th[data-key]:hover{color:var(--fg)}
th.sel,td.sel{width:24px;cursor:default}
.r{text-align:right}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.sample{color:var(--mut);word-break:break-all;max-width:520px}
.flags{color:var(--mut);font-size:12px}
.tok{background:#0b131c;border:1px solid var(--line);border-radius:4px;padding:0 5px;margin:0 2px 2px 0;
display:inline-block}
.tok[title]{cursor:help;border-bottom:1px dotted var(--mut)}
.fx-row{cursor:pointer}
.fx-row:hover td{background:#1b2836}
.fx-row.hid,.fx-detail.hid{display:none}
.caret{color:var(--mut);font-size:11px;transition:transform .1s}
.fx-row.open .caret{transform:rotate(90deg);display:inline-block}
.fx-detail td{background:#0d1620;color:var(--fg);font-size:13px}
.fx-detail .kv,.fx-detail .why,.fx-detail .fix,.fx-detail .dupe{margin:4px 0}
.fx-detail .why{color:#cdd8e4}
.fx-detail .fix{color:#9be6b0}
.fx-detail .flagline{margin:2px 0;color:#cdd8e4}
.fx-detail .flagline b{color:#e6edf3;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-weight:600}
details.fullguide{margin:6px 0 2px}
details.fullguide summary{cursor:pointer;color:var(--acc);font-size:12px}
.fx-detail blockquote{margin:4px 0 8px;padding:6px 10px;border-left:3px solid var(--line);color:var(--mut);
background:#0b131c}
.meter{display:inline-flex;align-items:center;gap:6px;min-width:110px}
.meter .bar{height:8px;border-radius:4px;display:inline-block;min-width:2px}
.bar.green{background:var(--green)}.bar.amber{background:var(--amber)}.bar.red{background:var(--red)}
.meter{position:relative;background:linear-gradient(#0b131c,#0b131c);border:1px solid var(--line);border-radius:5px;
padding:0;height:14px;width:120px;overflow:hidden}
.meter .bar{position:absolute;left:0;top:0;bottom:0;height:auto;border-radius:0}
.mlabel{position:relative;z-index:1;font-size:11px;padding-left:6px;color:#fff;mix-blend-mode:difference}
.na{color:var(--mut)}
.badge{background:#3a2a1d;color:#ffd28a;border-radius:10px;padding:0 7px;font-size:12px}
.sub{color:var(--mut);font-size:11px}
.warn{color:var(--amber)}
.hint{color:var(--mut);font-size:12px;margin:4px 0}
.fx-tip{display:none;position:absolute;z-index:60;max-width:340px;background:#0b131c;color:var(--fg);
 border:1px solid var(--acc);border-radius:6px;padding:7px 10px;box-shadow:0 6px 20px rgba(0,0,0,.55);
 font:12px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;pointer-events:none;white-space:normal}
[data-tip]{cursor:help}
th[data-tip]::after{content:"ⓘ";font-size:9px;opacity:.4;margin-left:3px;vertical-align:super}
.tok[data-tip]{border-bottom:1px dotted var(--mut)}
.tabintro{color:#cdd8e4;font-size:13px;line-height:1.5;margin:2px 0 12px;max-width:920px}
.tabintro .axes{color:var(--mut)}
#coverage h3 .lead{color:#9be6b0;font-weight:400;font-size:13px}
details.howto{margin:2px 0 8px}
details.howto>summary{cursor:pointer;color:var(--acc);font-size:12px}
details.howto .fixhint{margin:6px 0 4px;color:#cdd8e4}
details.howto ul{margin:4px 0;padding-left:20px}
details.howto li{margin:4px 0;color:#cdd8e4;font-size:12px;line-height:1.5}
details.howto pre{background:#0b131c;border:1px solid var(--line);border-radius:4px;padding:8px 10px;margin:6px 0;
overflow-x:auto;font-size:12px}
details.howto pre code{background:none;border:none;padding:0}
header details.howto{margin-top:8px;max-width:920px}
.selbar code.cmd{white-space:pre-wrap;display:inline-block;vertical-align:top;max-width:100%}
.empty{color:var(--mut);padding:20px 0}
.banner{background:#3a1d1d;border:1px solid #5a2a2a;color:#ffb3b3;border-radius:6px;padding:8px 12px;margin:0 0 12px;
font-size:13px}
.warnbanner{background:#3a2f1d;border:1px solid #5a4a2a;color:#ffd9a8}
code{background:#0b131c;border:1px solid var(--line);border-radius:4px;padding:1px 5px;font-size:12px}
a{color:var(--acc)}
button.copy{background:var(--card);color:var(--acc);border:1px solid var(--line);border-radius:4px;padding:1px 8px;
cursor:pointer;font-size:12px;margin-left:4px}
.chip{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;white-space:nowrap;cursor:help}
.s-broken{background:#4a1d1d;color:#ffb3b3}.s-few{background:#4a3a1d;color:#ffd28a}
.s-incomplete{background:#4a3a1d;color:#ffd28a}.s-review{background:#3a3a1d;color:#e6e08a}
.s-ok{background:#1d4a2a;color:#9be6b0}.s-discarded{background:#2a2f38;color:#93a4b8}.s-other{background:#2a2f38;color:#cdd8e4}
.selbar{position:sticky;bottom:0;background:#0b131c;border-top:1px solid var(--line);padding:8px 4px;
 margin-top:8px;font-size:13px;display:none}
.selbar.show{display:block}
details.drawer{margin-top:14px;color:var(--mut);font-size:12px}
details.drawer summary{cursor:pointer;color:var(--fg)}
details.drawer ul.defs{margin:4px 0 8px;padding-left:18px}
details.drawer ul.defs li{margin:3px 0}
details.drawer ul.defs b{color:var(--fg);font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
#coverage h3{font-size:14px;margin:22px 0 6px;padding-top:6px;border-top:1px solid var(--line)}
#coverage .covsec:first-of-type h3{border-top:none}
.summary{margin-bottom:8px}
.summary td.def{color:var(--mut);font-size:12px;white-space:normal;max-width:640px}
.summary td .chip{cursor:default}
.summary a{font-weight:600}
.fixhint{color:#9be6b0;font-size:12px;margin:4px 0 8px;max-width:900px}
.healthstrip{display:flex;align-items:center;gap:10px;margin:8px 0 14px}
.hsbar{display:flex;flex:1;height:24px;border-radius:6px;overflow:hidden;border:1px solid var(--line)}
.hsbar .seg{display:flex;align-items:center;justify-content:center;font-weight:600;font-size:12px;
 text-decoration:none;min-width:22px;border-radius:0}
.hslabel{color:var(--mut);font-size:12px;white-space:nowrap}
details.allgrid{margin:18px 0 6px}
details.allgrid>summary{cursor:pointer;color:var(--fg);font-size:14px;padding:6px 0;
 border-top:1px solid var(--line)}
.covsearch{display:flex;gap:6px;align-items:center;margin:4px 0 6px}
.cov-q{background:#0b131c;color:var(--fg);border:1px solid var(--line);border-radius:6px;
 padding:5px 9px;font-size:12px;min-width:280px}
.cov-clear{background:var(--card);color:var(--mut);border:1px solid var(--line);border-radius:6px;
 padding:5px 9px;cursor:pointer;font-size:12px}
"""
JS = r"""
function copy(t,b){(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject())
 .then(()=>{var o=b.textContent;b.textContent='copied';setTimeout(()=>b.textContent=o,1200);})
 .catch(()=>{b.textContent='copy failed';});}
document.addEventListener('click',function(e){
 var b=e.target.closest('button.copy');if(b){copy(b.getAttribute('data-cmd'),b);e.stopPropagation();}});

function tab(id,btn){
 document.querySelectorAll('section').forEach(s=>s.classList.remove('active'));
 document.querySelectorAll('nav button').forEach(x=>x.classList.remove('active'));
 document.getElementById(id).classList.add('active');btn.classList.add('active');}

function setupTable(table){
 var tab=table.getAttribute('data-tab');
 var tbody=table.querySelector('tbody');
 var facetsEl=document.querySelector('.fx-facets[data-for="'+tab+'"]');
 var active=new Set(); var att=false; var q='';
 // helpers
 function detail(id){return tbody.querySelectorAll('tr.fx-detail[data-id="'+id+'"]')[0];}
 function apply(){
  tbody.querySelectorAll('tr.fx-row').forEach(function(r){
   var okF=active.size===0||active.has(r.getAttribute('data-facet'));
   var okA=!att||r.getAttribute('data-attention')==='1';
   var okQ=q===''||(r.getAttribute('data-name')||'').toLowerCase().indexOf(q)>=0;
   var show=okF&&okA&&okQ;
   r.classList.toggle('hid',!show);
   var d=detail(r.getAttribute('data-id'));
   if(d){d.classList.toggle('hid',!show);}   // detail's expand state stays on its `hidden` attr
  });}
 // expand
 tbody.addEventListener('click',function(e){
  if(e.target.closest('a,button,input'))return;
  var r=e.target.closest('tr.fx-row');if(!r)return;
  var d=detail(r.getAttribute('data-id'));if(!d)return;
  var open=d.hasAttribute('hidden');
  if(open){d.removeAttribute('hidden');r.classList.add('open');}
  else{d.setAttribute('hidden','');r.classList.remove('open');}
  r.setAttribute('aria-expanded',open?'true':'false');});
 // sort
 table.querySelectorAll('th[data-key]').forEach(function(th){
  var idx=th.cellIndex;   // real column position (accounts for a leading no-key `sel` column)
  th.addEventListener('click',function(){
   var type=th.getAttribute('data-type')||'str';var dir=th.__d=-(th.__d||-1);
   table.querySelectorAll('th').forEach(function(o){if(o!==th)o.__d=0;});
   var rows=[].slice.call(tbody.querySelectorAll('tr.fx-row'));
   rows.sort(function(a,b){
    var ka=a.children[idx]?a.children[idx].getAttribute('data-key'):'';
    var kb=b.children[idx]?b.children[idx].getAttribute('data-key'):'';
    if(type==='num'){ka=parseFloat(ka);kb=parseFloat(kb);if(isNaN(ka))ka=-1e15;if(isNaN(kb))kb=-1e15;
     return (ka-kb)*dir;}
    return (''+ka).localeCompare(''+kb)*dir;});
   rows.forEach(function(r){tbody.appendChild(r);var d=detail(r.getAttribute('data-id'));if(d)tbody.appendChild(d);});
  });});
 // facets / search / attention
 if(facetsEl){
  facetsEl.querySelectorAll('.facet').forEach(function(f){
   f.addEventListener('click',function(){
    var v=f.getAttribute('data-facet');
    if(active.has(v)){active.delete(v);f.classList.remove('on');}
    else{active.add(v);f.classList.add('on');}apply();});});
  var s=facetsEl.querySelector('.fx-search');
  if(s)s.addEventListener('input',function(){q=s.value.toLowerCase();apply();});
  var a=facetsEl.querySelector('.fx-att');
  if(a)a.addEventListener('change',function(){att=a.checked;apply();});
  var c=facetsEl.querySelector('.clear');
  if(c)c.addEventListener('click',function(){active.clear();att=false;q='';
   facetsEl.querySelectorAll('.facet').forEach(x=>x.classList.remove('on'));
   if(s)s.value='';if(a)a.checked=false;apply();});}
 // select bar — the ticked rows become a copy-paste command (dedupe / review / crawl)
 var selbar=document.getElementById('selbar-'+tab);
 if(selbar){
  var project=selbar.getAttribute('data-project');
  var mode=selbar.getAttribute('data-mode')||'dedupe';
  var cmd=selbar.querySelector('.cmd');
  function refresh(){
   var names=[].slice.call(tbody.querySelectorAll('tr.fx-row:not(.hid) .fx-check:checked'))
     .map(function(c){return c.closest('tr.fx-row').getAttribute('data-name');});
   if(names.length){selbar.classList.add('show');
    var c;
    if(mode==='repair') c='/spider-review '+project+' '+names.join(' ');
    else if(mode==='review') c='/spider-review '+project+' '+names.join(' ');
    else if(mode==='crawl') c=names.map(function(n){return './scrapai crawl '+n+' --project '+project;}).join('\n');
    else c='./scrapai dedupe --project '+project+' --only '+names.join(' ');
    cmd.textContent=c;
    selbar.querySelector('.n').textContent=names.length;}
   else selbar.classList.remove('show');}
  tbody.addEventListener('change',function(e){
   if(!e.target.classList.contains('fx-check'))return;
   if(e.target.checked)e.target.setAttribute('checked','');else e.target.removeAttribute('checked');
   refresh();});
  var all=table.querySelector('.fx-all');
  if(all)all.addEventListener('change',function(){
   tbody.querySelectorAll('tr.fx-row:not(.hid) .fx-check').forEach(function(c){
    c.checked=all.checked;if(all.checked)c.setAttribute('checked','');else c.removeAttribute('checked');});
   refresh();});
  var cb=selbar.querySelector('button.copy');
  if(cb)cb.addEventListener('click',function(){copy(cmd.textContent,cb);});}
}
// styled hover/focus tooltip — replaces native title= everywhere; instant, readable, discoverable.
(function(){
 var tip=document.createElement('div'); tip.className='fx-tip'; tip.setAttribute('role','tooltip');
 document.body.appendChild(tip); var cur=null;
 function show(el){
  var t=el.getAttribute('data-tip'); if(!t){hide();return;}
  if(el.hasAttribute('title')){el.setAttribute('data-title',el.getAttribute('title'));el.removeAttribute('title');}
  tip.textContent=t; tip.style.display='block'; cur=el;               // textContent = XSS-safe
  var r=el.getBoundingClientRect();
  tip.style.top=(r.bottom+6+window.scrollY)+'px';
  tip.style.left=(r.left+window.scrollX)+'px';
  var tr=tip.getBoundingClientRect();                                 // keep on-screen
  if(tr.right>window.innerWidth-8) tip.style.left=(window.innerWidth-tr.width-8+window.scrollX)+'px';
 }
 function hide(){
  tip.style.display='none';
  if(cur&&cur.hasAttribute('data-title')){cur.setAttribute('title',cur.getAttribute('data-title'));cur.removeAttribute('data-title');}
  cur=null;
 }
 document.addEventListener('mouseover',function(e){var el=e.target.closest('[data-tip]');
  if(el){if(el!==cur)show(el);} else if(cur){hide();}});
 document.addEventListener('focusin',function(e){var el=e.target.closest('[data-tip]'); if(el)show(el);});
 document.addEventListener('focusout',hide);
 document.addEventListener('scroll',hide,true);
})();
document.querySelectorAll('.fx-table').forEach(setupTable);
// coverage-wide search: filter spiders across every table on the Coverage tab; hide a section
// whose rows all vanish (headings/summary/notes stay).
(function(){
 var q=document.querySelector('.cov-q'); if(!q)return;
 function run(){
  var v=q.value.toLowerCase();
  document.querySelectorAll('#coverage tr.fx-row').forEach(function(r){
   var m=v===''||(r.getAttribute('data-name')||'').toLowerCase().indexOf(v)>=0;
   r.classList.toggle('hid',!m);
   var id=r.getAttribute('data-id');
   if(id){var d=r.parentNode.querySelector('tr.fx-detail[data-id="'+id+'"]');if(d)d.classList.toggle('hid',!m);}
  });
  document.querySelectorAll('#coverage .covsec').forEach(function(sec){
   var hasRows=sec.querySelector('tr.fx-row');
   sec.style.display=(!hasRows||sec.querySelector('tr.fx-row:not(.hid)'))?'':'none';
  });
 }
 q.addEventListener('input',run);
 var c=document.querySelector('.cov-clear'); if(c)c.addEventListener('click',function(){q.value='';run();});
})();
"""
