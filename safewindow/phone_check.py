"""A self-contained page that tests the things an emulator cannot: a real phone's GPS, SMS app, fingers, fonts and
file handling. Open it on the phone, tap through, and send back the summary at the bottom."""
from __future__ import annotations

import html

SAMPLES = [("English", "SafeWindow: your village card"), ("Bangla", "সেফউইন্ডো: আপনার গ্রামের কার্ড"),
           ("Nepali", "सेफविन्डो: तपाईंको गाउँको कार्ड"), ("Hindi", "सेफविंडो: आपके गाँव का कार्ड"),
           ("Urdu (right to left)", "سیف ونڈو: آپ کے گاؤں کا کارڈ")]

_PAGE = """<!doctype html><html lang='en'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'><title>SafeWindow phone check</title>
<style>
body{font-family:'Noto Sans Bengali','Nirmala UI','Segoe UI',Roboto,Arial,sans-serif;margin:0;padding:12px;background:#eef1ec;color:#1b1f1a;font-size:1.0625rem;line-height:1.45}
.t{background:#fff;border:1px solid #c9d3c4;border-radius:10px;padding:14px;margin:12px 0} h1{font-size:1.4em;margin:.2em 0} h2{font-size:1.1em;margin:0 0 .4em}
button,a.b{min-height:44px;padding:8px 14px;font-size:1em;border-radius:8px;border:1px solid #6b7c72;background:#f4f4f0;color:#111;display:inline-block;margin:4px 4px 4px 0;text-decoration:none;cursor:pointer}
.ok{color:#0b7a35;font-weight:700} .bad{color:#c0192e;font-weight:700} .note{font-size:.85em;color:#555} pre{white-space:pre-wrap;word-break:break-word;background:#f4f4f0;padding:8px;border-radius:6px}
.row{display:flex;flex-wrap:wrap;gap:6px}
</style></head><body>
<h1>SafeWindow phone check</h1><p class='note'>Three minutes. Tap each button and answer honestly. Nothing leaves your phone; the summary at the bottom is for you to send back.</p>
<div class='t'><h2>1. Your phone</h2><pre id='info'></pre></div>
<div class='t'><h2>2. GPS (the village finder and the help SMS need it)</h2><button id='gps'>Test my location</button><div id='gpsr' class='note'></div></div>
<div class='t'><h2>3. SMS app</h2><a class='b' id='smsl' href='sms:?&body=SafeWindow%20test%20message'>Open a test SMS</a>
 <div>Did your messages app open with the text filled in?</div><button data-q='sms' data-v='yes'>Yes</button><button data-q='sms' data-v='no'>No</button></div>
<div class='t'><h2>4. Fingers</h2><div>Tap each of the six buttons once.</div><div class='row' id='taps'></div><div id='tapr' class='note'></div></div>
<div class='t'><h2>5. Text and fonts</h2><div id='fontline'>This line is 1rem.</div><div class='note' id='fontr'></div>__SAMPLES__
 <div>Do ALL the lines above show real letters (no empty boxes), and does the Urdu line read right to left?</div><button data-q='fonts' data-v='yes'>Yes</button><button data-q='fonts' data-v='no'>No</button></div>
<div class='t'><h2>6. Saving a file</h2><button id='dl'>Save a test file</button><div>Did a file called safewindow-test.txt save to your phone?</div><button data-q='download' data-v='yes'>Yes</button><button data-q='download' data-v='no'>No</button></div>
<div class='t'><h2>7. No internet</h2><div>Save THIS page to your phone, switch on airplane mode, open the saved copy. Does it open?</div><button data-q='offline' data-v='yes'>Yes</button><button data-q='offline' data-v='no'>No</button><button data-q='offline' data-v='skipped'>Skip</button></div>
<div class='t'><h2>Summary: send this back</h2><pre id='sum'>(answer the questions above)</pre><button id='copy'>Copy summary</button></div>
<script>
var R={};function $(i){return document.getElementById(i)}
function show(){var keys=['gps','sms','taps','fonts','download','offline'];$('sum').textContent=JSON.stringify({page:'safewindow-phone-check',info:INFO,results:R},null,1)}
var INFO={ua:navigator.userAgent,viewport:innerWidth+'x'+innerHeight,dpr:devicePixelRatio,orientation:(screen.orientation||{}).type||'n/a',touchPoints:navigator.maxTouchPoints,
 dark:matchMedia('(prefers-color-scheme: dark)').matches,reducedMotion:matchMedia('(prefers-reduced-motion: reduce)').matches,lang:navigator.language,secureContext:isSecureContext,
 protocol:location.protocol,online:navigator.onLine};
$('info').textContent=Object.keys(INFO).map(function(k){return k+': '+INFO[k]}).join('\\n');
$('gps').onclick=function(){$('gpsr').textContent='Asking...';if(!navigator.geolocation){R.gps='no geolocation in this browser';$('gpsr').innerHTML='<span class=bad>Not available</span>';show();return}
 navigator.geolocation.getCurrentPosition(function(p){R.gps='ok accuracy '+Math.round(p.coords.accuracy)+' m';$('gpsr').innerHTML='<span class=ok>Works</span> '+p.coords.latitude.toFixed(4)+', '+p.coords.longitude.toFixed(4)+' (about '+Math.round(p.coords.accuracy)+' m)';show()},
 function(e){R.gps='failed code '+e.code+' '+e.message;$('gpsr').innerHTML='<span class=bad>Failed</span> '+e.message+(isSecureContext?'':' (this page is not a secure context: GPS needs https or a saved file)');show()},{enableHighAccuracy:true,timeout:20000})};
var tapped={};for(var i=1;i<=6;i++){(function(n){var b=document.createElement('button');b.textContent=n;b.style.minWidth='56px';b.onclick=function(){tapped[n]=1;b.style.background='#cfe9d6';var c=Object.keys(tapped).length;
 $('tapr').textContent=c+' of 6 tapped';R.taps=c+' of 6 tapped, button size '+Math.round(b.getBoundingClientRect().width)+'x'+Math.round(b.getBoundingClientRect().height)+' css px';show()};$('taps').appendChild(b)})(i)}
var fs=parseFloat(getComputedStyle($('fontline')).fontSize);$('fontr').textContent='1rem is '+fs+' px. At the default text size this is 16 px. If you set a larger text size in your phone, this number grows.';R.textSizePx=fs;
$('dl').onclick=function(){var a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['SafeWindow phone check']));a.download='safewindow-test.txt';document.body.appendChild(a);a.click();a.remove()};
document.querySelectorAll('button[data-q]').forEach(function(b){b.onclick=function(){R[b.dataset.q]=b.dataset.v;b.style.background=b.dataset.v==='yes'?'#cfe9d6':'#f6cfd3';show()}});
$('copy').onclick=function(){var t=$('sum').textContent;if(navigator.clipboard){navigator.clipboard.writeText(t).then(function(){$('copy').textContent='Copied'},function(){})}};
show();
</script></body></html>"""


def build() -> str:
    lines = "".join(f"<div class='note'>{html.escape(name)}</div><div style='font-size:1.15em' lang='x'"
                    f"{' dir=\"rtl\"' if 'Urdu' in name else ''}>{html.escape(text)}</div>" for name, text in SAMPLES)
    return _PAGE.replace("__SAMPLES__", lines)
