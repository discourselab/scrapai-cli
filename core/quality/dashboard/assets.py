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
.sharectl{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--mut)}
.sharectl .pdf-share{accent-color:var(--acc);cursor:pointer;width:140px}
.sharectl .pdf-share-val{color:var(--fg);min-width:34px}
.pdf-shown{font-size:12px;color:var(--mut)}
.stor{display:inline-block;background:#0e2f42;color:#66ccff;border:1px solid #2f7ea3;border-radius:10px;
 padding:0 7px;font-size:11px;font-weight:600;cursor:help;margin-right:5px;white-space:nowrap}
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
.fx-row.hid,.fx-detail.hid,.fx-group.hid{display:none}
tr.fx-group{cursor:pointer;background:#111c28}
tr.fx-group:hover td{background:#1b2836}
tr.fx-group td{font-size:13px}
tr.fx-group .caret{display:inline-block;transition:transform .1s}
tr.fx-group.open .caret{transform:rotate(90deg)}
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
.pdfurls{margin:2px 0 8px}
.pdfurl{padding:1px 0;word-break:break-all}
.pdfurl.xtra{display:none}
.pdfurl a{color:var(--acc)}
.excctl{margin-left:4px}
.exc-note{color:var(--amber);margin-left:4px}
.fx-row.pdf-exc td{opacity:.62}
.fx-row.pdf-exc:hover td{opacity:.85}
.excb{color:var(--amber);font-size:11px;margin-left:6px;white-space:nowrap}
.excb:empty{display:none}
.pdf-info{margin:14px 0 2px;border:1px solid var(--line);border-radius:8px;background:#0d1620}
.pdf-expanel>summary{cursor:pointer;padding:8px 12px;color:var(--fg);font-size:13px;list-style:none}
.pdf-expanel>summary::-webkit-details-marker{display:none}
.pdf-expanel>summary::before{content:"▸";color:var(--mut);margin-right:8px;font-size:11px;display:inline-block}
.pdf-expanel[open]>summary::before{transform:rotate(90deg)}
.pdf-ex-count{color:var(--acc);font-weight:600}
.pdf-exbody{padding:4px 14px 14px;border-top:1px solid var(--line)}
.pdf-exbody>p{max-width:920px}
.pdf-exsec{margin:10px 0;font-size:12px}
.pdf-exsec>b{color:var(--fg)}
.chips{display:flex;flex-wrap:wrap;gap:5px;margin-top:5px}
.chips:empty::after{content:"none";color:var(--mut);font-size:11px}
.exchip{display:inline-flex;align-items:center;gap:5px;background:#0b131c;border:1px solid var(--line);
 border-radius:12px;padding:1px 9px;font-size:11px;font-family:ui-monospace,Menlo,monospace}
.exchip.added{border-color:var(--acc)}
.exchip .x{cursor:pointer;color:var(--mut);font-weight:700}
.exchip .x:hover{color:var(--red)}
.pdf-addrow{display:flex;align-items:center;gap:6px;margin:12px 0 4px}
.pdf-add{background:#0b131c;color:var(--fg);border:1px solid var(--line);border-radius:6px;
 padding:5px 9px;font-size:12px;min-width:280px}
.pdf-add-btn{background:var(--acc);color:#04121f;border:none;border-radius:6px;padding:5px 12px;
 cursor:pointer;font-size:12px;font-weight:600}
.pdf-add-msg{margin-left:2px}
.pdf-savebox{margin-top:10px;border-top:1px dashed var(--line);padding-top:10px}
.pdf-savejson{display:block;white-space:pre;max-height:220px;overflow:auto;margin:6px 0;
 background:#0b131c;border:1px solid var(--line);border-radius:6px;padding:8px;font-size:12px}
button.copyurls{background:var(--card);color:var(--acc);border:1px solid var(--line);
 border-radius:4px;padding:1px 8px;cursor:pointer;font-size:12px}
.selbar .dl,.selbar .savepage{background:var(--card);color:var(--acc);border:1px solid var(--line);
 border-radius:4px;padding:1px 8px;cursor:pointer;font-size:12px;margin-left:6px}
.selbar .cmd.json{display:block;white-space:pre-wrap;max-height:120px;overflow:auto;margin-top:6px;
 background:#0b131c;border:1px solid var(--line);border-radius:4px;padding:6px}
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
function downloadText(name,text,type){
 var b=new Blob([text],{type:type||'text/plain'});var u=URL.createObjectURL(b);
 var a=document.createElement('a');a.href=u;a.download=name;document.body.appendChild(a);
 a.click();setTimeout(function(){document.body.removeChild(a);URL.revokeObjectURL(u);},100);}
// PDF URL lists live in one JSON island, parsed once, and are turned into links ONLY when a host
// is expanded — keeping ~22k link nodes out of the initial DOM so the PDFs tab stays fast.
var _PDFU=null;
function pdfUrls(){if(_PDFU===null){var el=document.getElementById('pdf-urls');
 try{_PDFU=el?JSON.parse(el.textContent):{};}catch(e){_PDFU={};}}return _PDFU;}
function buildPdfDetail(d){
 if(!d)return; var box=d.querySelector('.pdfurls'); if(!box||box.getAttribute('data-built'))return;
 var urls=pdfUrls()[d.getAttribute('data-id')]; if(!urls)return;
 var CAP=25, frag=document.createDocumentFragment();
 urls.forEach(function(u,i){
  var div=document.createElement('div'); div.className='pdfurl'+(i>=CAP?' xtra':'');
  var a=document.createElement('a'); a.target='_blank'; a.rel='noopener'; a.textContent=u;
  if(/^https?:\/\//i.test(u))a.href=u;                 // linkify http(s) only (untrusted URLs)
  div.appendChild(a); frag.appendChild(div);});
 if(urls.length>CAP){var m=document.createElement('div'); m.className='sub';
  m.textContent='… +'+(urls.length-CAP)+' more (hidden; included in copy-all)'; frag.appendChild(m);}
 box.appendChild(frag); box.setAttribute('data-built','1');}
document.addEventListener('click',function(e){
 var b=e.target.closest('button.copy');if(b){copy(b.getAttribute('data-cmd'),b);e.stopPropagation();return;}
 var cu=e.target.closest('button.copyurls');
 if(cu){var dr=cu.closest('tr.fx-detail'); var urls=(dr&&pdfUrls()[dr.getAttribute('data-id')])||[];
  copy(urls.join('\n'),cu);e.stopPropagation();}});

// --- PDF host exclusions -----------------------------------------------------
// The exclusion config (from data/<project>/_audit/pdf_exclude.json) is embedded once as a JSON
// island. The matcher below decides, per host row, whether it's out of scope (a govt TLD, an
// excluded org, or a sibling org covered by its own spider). Live-added patterns extend the same
// state, so a host typed into the infobox hides immediately. Seeded here, applied in setupTable.
var _PDFX=null;
function pdfExc(){
 if(_PDFX)return _PDFX;
 var el=document.getElementById('pdf-exclude'),c={};
 try{c=el?JSON.parse(el.textContent):{};}catch(e){c={};}
 _PDFX={domains:(c.domains||[]).slice(),tlds:(c.block_tlds||[]).slice(),
        siblings:c.siblings||{},sibOn:!!c.exclude_sibling_org_domains,raw:c.raw||{},
        added:{domains:[],tlds:[]}};
 return _PDFX;}
function _sfx(host,d){return host===d||host.endsWith('.'+d);}   // dot-boundary suffix match
// returns an exclusion reason for a row's host, or '' if in scope
function pdfExcReason(host,spider){
 if(!host)return ''; var x=pdfExc();
 var lab=host.split('.'); var tld=lab[lab.length-1];
 if(x.tlds.indexOf(tld)>=0||x.added.tlds.indexOf(tld)>=0)return 'tld:'+tld;
 var doms=x.domains.concat(x.added.domains);
 for(var i=0;i<doms.length;i++)if(_sfx(host,doms[i]))return 'org:'+doms[i];
 for(var d in x.siblings){if(x.siblings[d]!==spider&&_sfx(host,d))return 'sib:'+x.siblings[d];}
 return '';}
var _EXCLABEL={tld:'govt TLD',org:'excluded org',sib:'sibling org'};

function tab(id,btn){
 document.querySelectorAll('section').forEach(s=>s.classList.remove('active'));
 document.querySelectorAll('nav button').forEach(x=>x.classList.remove('active'));
 document.getElementById(id).classList.add('active');btn.classList.add('active');}

function setupTable(table){
 var tab=table.getAttribute('data-tab');
 var tbody=table.querySelector('tbody');
 var facetsEl=document.querySelector('.fx-facets[data-for="'+tab+'"]');
 var active=new Set(); var att=false; var q=''; var thr=0;   // thr = pdf share threshold (%)
 var groups=tbody.querySelectorAll('tr.fx-group'); var grouped=groups.length>0; var openG=new Set();
 var isPdf=tab==='pdfs'; var showExc=false;   // showExc: reveal exclusion-hidden host rows
 var shareReadout=function(){};               // set below when the pdf share slider exists
 // helpers
 function detail(id){return tbody.querySelectorAll('tr.fx-detail[data-id="'+id+'"]')[0];}
 // mark a pdf row excluded/in-scope (returns true if excluded); paints the row's reason tag
 function mark(r){
  if(!isPdf)return false;
  var reason=pdfExcReason((r.getAttribute('data-host')||'').toLowerCase(),r.getAttribute('data-spider'));
  r.classList.toggle('pdf-exc',!!reason);
  var b=r.querySelector('.excb');
  if(b)b.textContent=reason?('· excluded: '+(_EXCLABEL[reason.split(':')[0]]||reason)):'';
  return !!reason;}
 function apply(){
  tbody.querySelectorAll('tr.fx-row').forEach(function(r){
   var okF=active.size===0||active.has(r.getAttribute('data-facet'));
   var okA=!att||r.getAttribute('data-attention')==='1';
   var okQ=q===''||(r.getAttribute('data-name')||'').toLowerCase().indexOf(q)>=0;
   var show=okF&&okA&&okQ;
   if(grouped){var g=r.getAttribute('data-group');show=show&&(q!==''||openG.has(g)); // search forces expand
    // excluded rows: gated by the toggle, ignore the slider; in-scope: share slider
    if(mark(r)) show=show&&showExc;
    else show=show&&(parseFloat(r.getAttribute('data-share')||'999')>=thr);}
   r.classList.toggle('hid',!show);
   var d=detail(r.getAttribute('data-id'));
   if(d){d.classList.toggle('hid',!show);}   // detail's expand state stays on its `hidden` attr
  });
  if(grouped){groups.forEach(function(gr){
   var gid=gr.getAttribute('data-group'); gr.classList.toggle('open',openG.has(gid)||q!=='');
   var any=false; tbody.querySelectorAll('tr.fx-row[data-group="'+gid+'"]:not(.hid)').forEach(function(){any=true;});
   gr.classList.toggle('hid',q!==''&&!any);   // when searching, hide empty org sections
   if(isPdf){var nx=tbody.querySelectorAll('tr.fx-row.pdf-exc[data-group="'+gid+'"]').length;
    var note=gr.querySelector('.exc-note'); if(note)note.textContent=nx?(' · '+nx+' hidden'):'';}
  });}}
 // expand
 tbody.addEventListener('click',function(e){
  if(e.target.closest('a,button,input'))return;
  var r=e.target.closest('tr.fx-row');if(!r)return;
  var d=detail(r.getAttribute('data-id'));if(!d)return;
  var open=d.hasAttribute('hidden');
  if(open){d.removeAttribute('hidden');r.classList.add('open');buildPdfDetail(d);}
  else{d.setAttribute('hidden','');r.classList.remove('open');}
  r.setAttribute('aria-expanded',open?'true':'false');});
 // org group headers (pdf tab): click toggles that org's host rows
 if(grouped){tbody.addEventListener('click',function(e){
  var g=e.target.closest('tr.fx-group');if(!g)return;
  var gid=g.getAttribute('data-group');
  if(openG.has(gid))openG.delete(gid);else openG.add(gid);
  apply();});}
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
  // pdf share slider: hide hosts below `thr`% of the org's PDFs; live 'showing X of Y' readout
  var sh=facetsEl.querySelector('.pdf-share');
  if(sh){thr=parseFloat(sh.value)||0;
   var shv=facetsEl.querySelector('.pdf-share-val'), shn=facetsEl.querySelector('.pdf-shown');
   shareReadout=function(){var rs=tbody.querySelectorAll('tr.fx-row[data-share]'),k=0,tot=0;
    rs.forEach(function(r){if(r.classList.contains('pdf-exc'))return;   // count in-scope hosts only
     tot++;if(parseFloat(r.getAttribute('data-share')||'0')>=thr)k++;});
    if(shn)shn.textContent=' showing '+k+' of '+tot+' hosts ';};
   sh.addEventListener('input',function(){thr=parseFloat(sh.value)||0;
    if(shv)shv.textContent=thr.toFixed(1)+'%';apply();shareReadout();});
   shareReadout();}
  // pdf 'show excluded hosts' toggle: reveal the rows hidden by pdf_exclude.json
  var se=facetsEl.querySelector('.pdf-showexc');
  if(se)se.addEventListener('change',function(){showExc=se.checked;apply();shareReadout();});
  var a=facetsEl.querySelector('.fx-att');
  if(a)a.addEventListener('change',function(){att=a.checked;apply();});
  var c=facetsEl.querySelector('.clear');
  if(c)c.addEventListener('click',function(){active.clear();att=false;q='';
   facetsEl.querySelectorAll('.facet').forEach(x=>x.classList.remove('on'));
   if(s)s.value='';if(a)a.checked=false;apply();});}
 if(isPdf)setupPdfInfobox(table,tbody,apply,function(){shareReadout();});
 // select bar — coverage: a bulk dedupe command · pdfs: an include-list JSON you export
 var selbar=document.getElementById('selbar-'+tab);
 if(selbar){
  var project=selbar.getAttribute('data-project');
  var mode=selbar.getAttribute('data-mode')||'dedupe';
  var cmd=selbar.querySelector('.cmd');
  // pdf include-list: {spider:{keep:[host,...]}} from EVERY ticked row (filter-independent)
  function pdfJSON(){
   var o={};
   tbody.querySelectorAll('tr.fx-row .fx-check:checked').forEach(function(c){
    var r=c.closest('tr.fx-row');var sp=r.getAttribute('data-spider');var h=r.getAttribute('data-host');
    if(!o[sp])o[sp]={keep:[]};
    if(o[sp].keep.indexOf(h)<0)o[sp].keep.push(h);});
   return o;}
  var LSKEY='pdf_hosts:'+project;
  function saveLS(){try{localStorage.setItem(LSKEY,JSON.stringify(pdfJSON()));}catch(e){}}
  function refresh(){
   var checked=[].slice.call(tbody.querySelectorAll('tr.fx-row .fx-check:checked'));
   if(mode==='pdf-json'){
    if(checked.length){selbar.classList.add('show');cmd.textContent=JSON.stringify(pdfJSON(),null,2);}
    else{selbar.classList.remove('show');cmd.textContent='';}
    selbar.querySelector('.n').textContent=checked.length;
   }else{
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
    else selbar.classList.remove('show');}}
  tbody.addEventListener('change',function(e){
   if(!e.target.classList.contains('fx-check'))return;
   // persist the tick in the DOM attribute so "save page with choices" serialises it
   if(e.target.checked)e.target.setAttribute('checked','');else e.target.removeAttribute('checked');
   if(mode==='pdf-json')saveLS();
   refresh();});
  var all=table.querySelector('.fx-all');
  if(all)all.addEventListener('change',function(){
   tbody.querySelectorAll('tr.fx-row:not(.hid) .fx-check').forEach(function(c){
    c.checked=all.checked;if(all.checked)c.setAttribute('checked','');else c.removeAttribute('checked');});
   refresh();});
  var cb=selbar.querySelector('button.copy');
  if(cb)cb.addEventListener('click',function(){copy(cmd.textContent,cb);});
  var dl=selbar.querySelector('button.dl');
  if(dl)dl.addEventListener('click',function(){downloadText('pdf_hosts.json',cmd.textContent,'application/json');});
  var sv=selbar.querySelector('button.savepage');
  if(sv)sv.addEventListener('click',function(){
   downloadText('dashboard_'+project+'.html','<!doctype html>\n'+document.documentElement.outerHTML,'text/html');});
  if(mode==='pdf-json'){
   // restore ticks: DOM `checked` attrs (a saved page) win; localStorage tops up (same-browser reload)
   var restore={};try{restore=JSON.parse(localStorage.getItem(LSKEY)||'{}');}catch(e){}
   tbody.querySelectorAll('tr.fx-row').forEach(function(r){
    var sp=r.getAttribute('data-spider'),h=r.getAttribute('data-host'),chk=r.querySelector('.fx-check');
    if(!chk)return;
    if(chk.hasAttribute('checked'))chk.checked=true;
    else if(restore[sp]&&restore[sp].keep&&restore[sp].keep.indexOf(h)>=0){
      chk.checked=true;chk.setAttribute('checked','');}});
   refresh();}}
 if(grouped){
  // start collapsed, but open any org that already has a ticked host so selections are visible
  tbody.querySelectorAll('tr.fx-row .fx-check:checked').forEach(function(c){
   openG.add(c.closest('tr.fx-row').getAttribute('data-group'));});
  apply(); shareReadout();   // readout after apply() so excluded rows are marked (in-scope count)
 }
}
// The PDFs-tab infobox: lists the active exclusions as chips, lets you add a domain/TLD live
// (extends the same matcher, so matching hosts hide at once), and builds a copy/downloadable
// pdf_exclude.json so the additions can be persisted. Static HTML can't write the file — this is
// the same "export a config, paste it back" pattern as the include-list select bar.
function setupPdfInfobox(table,tbody,apply,readout){
 var info=document.querySelector('.pdf-info'); if(!info)return;
 var x=pdfExc();
 function esc(t){return (''+t).replace(/[&<>"]/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
 function chip(text,kind,val){
  var s='<span class="exchip'+(kind?' added':'')+'">'+esc(text);
  if(kind)s+=' <span class="x" data-k="'+kind+'" data-v="'+esc(val)+'" title="remove">✕</span>';
  return s+'</span>';}
 var elT=info.querySelector('.pdf-ex-tlds'), elD=info.querySelector('.pdf-ex-domains'),
     elS=info.querySelector('.pdf-ex-siblings'), elC=info.querySelector('.pdf-ex-count'),
     save=info.querySelector('.pdf-savebox'), pre=info.querySelector('.pdf-savejson'),
     inp=info.querySelector('.pdf-add'), btn=info.querySelector('.pdf-add-btn'),
     msg=info.querySelector('.pdf-add-msg');
 function renderChips(){
  var tld=x.tlds.map(function(t){return chip(t,'',t);})
    .concat(x.added.tlds.map(function(t){return chip(t,'tld',t);}));
  var dom=x.domains.map(function(d){return chip(d,'',d);})
    .concat(x.added.domains.map(function(d){return chip(d,'dom',d);}));
  var sib=Object.keys(x.siblings).sort().map(function(d){return chip(d+' → '+x.siblings[d],'',d);});
  if(elT)elT.innerHTML=tld.join(''); if(elD)elD.innerHTML=dom.join(''); if(elS)elS.innerHTML=sib.join('');
  if(elC)elC.textContent=(x.tlds.length+x.added.tlds.length
    +x.domains.length+x.added.domains.length+sib.length);}
 function buildSave(){
  if(!(x.added.tlds.length||x.added.domains.length)){if(save)save.hidden=true;return;}
  var out={}; for(var k in x.raw)out[k]=x.raw[k];
  out.domains=(x.raw.domains||x.domains).concat(x.added.domains);
  out.block_tlds=(x.raw.block_tlds||x.tlds).concat(x.added.tlds);
  if(out.exclude_sibling_org_domains===undefined)out.exclude_sibling_org_domains=x.sibOn;
  if(pre)pre.textContent=JSON.stringify(out,null,2);
  if(save)save.hidden=false;}
 function norm(v){return v.trim().toLowerCase().replace(/^https?:\/\//,'')
   .replace(/\/.*$/,'').replace(/^\.+/,'').replace(/^www\./,'');}
 function add(){
  var raw=(inp&&inp.value||'').trim(); if(!raw)return;
  var kind='domains', v=raw;
  if(/^tld:/i.test(raw)){kind='tlds'; v=raw.slice(4);}
  v=norm(v);
  if(!v||!/^[a-z0-9.-]+$/.test(v)){if(msg)msg.textContent='enter a domain (worldbank.org) or tld:gov';return;}
  var arr=x.added[kind], base=(kind==='tlds')?x.tlds:x.domains;
  if(base.indexOf(v)>=0||arr.indexOf(v)>=0){if(msg)msg.textContent=v+' is already excluded';return;}
  arr.push(v); if(msg)msg.textContent='added '+(kind==='tlds'?'TLD ':'')+v; if(inp)inp.value='';
  renderChips(); apply(); readout(); buildSave();}
 if(btn)btn.addEventListener('click',add);
 if(inp)inp.addEventListener('keydown',function(e){if(e.key==='Enter'){e.preventDefault();add();}});
 info.addEventListener('click',function(e){
  var xb=e.target.closest('.exchip .x');
  if(xb){var k=xb.getAttribute('data-k'), v=xb.getAttribute('data-v');
   var arr=(k==='tld')?x.added.tlds:x.added.domains, i=arr.indexOf(v); if(i>=0)arr.splice(i,1);
   if(msg)msg.textContent='removed '+v; renderChips(); apply(); readout(); buildSave(); return;}
  var cp=e.target.closest('.pdf-copy-json'); if(cp){copy(pre.textContent,cp); return;}
  var dl=e.target.closest('.pdf-dl-json');
  if(dl){downloadText('pdf_exclude.json',pre.textContent,'application/json');}});
 renderChips();
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
