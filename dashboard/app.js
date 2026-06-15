// Smart LMS Dashboard front-end. Polls the Flask API and renders Chart.js views.
const API = "/api";
const C = {hi:"#ef4444", med:"#f59e0b", lo:"#22c55e", ac:"#38bdf8", line:"#334155", mut:"#94a3b8"};
Chart.defaults.color = C.mut;
Chart.defaults.borderColor = C.line;
let charts = {};

async function get(p){ const r = await fetch(API+p); return r.json(); }

function doughnut(id, labels, data, colors){
  if(charts[id]){ charts[id].data.labels=labels; charts[id].data.datasets[0].data=data; charts[id].update(); return; }
  charts[id]=new Chart(document.getElementById(id),{type:"doughnut",
    data:{labels,datasets:[{data,backgroundColor:colors,borderWidth:0}]},
    options:{plugins:{legend:{position:"bottom"}},cutout:"60%"}});
}
function bar(id, labels, data, color, horizontal){
  const cfg={type:"bar",data:{labels,datasets:[{data,backgroundColor:color,borderRadius:5}]},
    options:{indexAxis:horizontal?"y":"x",plugins:{legend:{display:false}},
      scales:{x:{grid:{display:!horizontal}},y:{grid:{display:horizontal}}}}};
  if(charts[id]){ charts[id].data.labels=labels; charts[id].data.datasets[0].data=data; charts[id].update(); }
  else charts[id]=new Chart(document.getElementById(id),cfg);
}
function line(id, labels, data){
  if(charts[id]){ charts[id].data.labels=labels; charts[id].data.datasets[0].data=data; charts[id].update(); return; }
  charts[id]=new Chart(document.getElementById(id),{type:"line",
    data:{labels,datasets:[{data,borderColor:C.ac,backgroundColor:"rgba(56,189,248,.15)",
      fill:true,tension:.3,pointRadius:2}]},
    options:{plugins:{legend:{display:false}}}});
}

async function refreshLive(){
  const o = await get("/overview");
  document.getElementById("k-total").textContent = o.total_students;
  document.getElementById("k-high").textContent = o.risk_bands.High||0;
  document.getElementById("k-eng").textContent = o.avg_engagement;
  document.getElementById("k-auc").textContent = (o.model.auc!=null?o.model.auc:"–");
  const u = o.last_updated ? new Date(o.last_updated*1000).toLocaleTimeString() : "—";
  document.getElementById("updated").textContent = "live · scored "+u;
  doughnut("c-risk", ["High","Medium","Low"],
    [o.risk_bands.High||0,o.risk_bands.Medium||0,o.risk_bands.Low||0], [C.hi,C.med,C.lo]);

  const st = await get("/students");
  const tb = document.getElementById("rows"); tb.innerHTML="";
  st.forEach(s=>{
    const tr=document.createElement("tr");
    const eng=(s.engagement||0).toFixed(1);
    tr.innerHTML=`<td>${s.name||("Student "+s.sid)}</td><td>${s.gender}</td>
      <td><div class="bar"><div style="width:${Math.min(100,s.engagement||0)}%"></div></div>${eng}</td>
      <td>${s.total_events}</td><td>${s.active_weeks}</td>
      <td>${(s.risk_prob*100).toFixed(0)}%</td>
      <td><span class="badge ${s.risk_band}">${s.risk_band}</span></td>`;
    tb.appendChild(tr);
  });

  const tl = await get("/timeline");
  line("c-timeline", tl.map(d=>d.day.slice(5)), tl.map(d=>d.events));

  const fe = await get("/recent");
  const feed=document.getElementById("feed");
  feed.innerHTML = fe.length? fe.map(e=>`<div><b>${e.student}</b> — ${e.action} ${e.target}
    <span style="float:right">${e.time.slice(5,16)}</span></div>`).join("")
    : "<div>No live activity yet — log in to Moodle and click around.</div>";
}

async function refreshStatic(){
  const ew = await get("/early_warning");
  bar("c-early", Object.keys(ew).map(k=>k.replace("week_","Wk ")), Object.values(ew), C.med, false);

  const imp = await get("/feature_importances");
  const items = Object.entries(imp).slice(0,8);
  bar("c-imp", items.map(i=>i[0]), items.map(i=>Math.abs(i[1])), C.ac, true);

  const eo = await get("/engagement_outcome");
  const col = b=> b==="High"?C.hi : b==="Medium"?C.med : C.lo;
  if(charts["c-scatter"]) charts["c-scatter"].destroy();
  charts["c-scatter"]=new Chart(document.getElementById("c-scatter"),{type:"scatter",
    data:{datasets:[{data:eo.map(p=>({x:p.engagement,y:p.mark})),
      backgroundColor:eo.map(p=>col(p.risk_band)),pointRadius:4}]},
    options:{plugins:{legend:{display:false}},
      scales:{x:{title:{display:true,text:"Engagement /100"}},
              y:{title:{display:true,text:"Final mark /100"}}}}});
}

refreshLive(); refreshStatic();
setInterval(refreshLive, 20000);
setInterval(refreshStatic, 120000);
