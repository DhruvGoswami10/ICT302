// Smart LMS Dashboard front-end. Polls the Flask API and renders Chart.js views.
const API = "/api";
const C = {hi:"#FF6B5B", med:"#FFC24B", lo:"#3DDC97", ac:"#35D0C0", line:"#26292D", mut:"#9AA3AF"};
Chart.defaults.color = C.mut;
Chart.defaults.borderColor = C.line;
Chart.defaults.font.family = "ui-monospace, 'SF Mono', Consolas, monospace";
let charts = {};
let currentFilter = "all";
let lastStudents = [];

async function get(p){ const r = await fetch(API+p); return r.json(); }

const centerTextPlugin = {
  id: 'centerText',
  afterDraw(chart){
    if(chart.config.type!=='doughnut') return;
    const {ctx, chartArea:{width, height, left, top}} = chart;
    const total = chart.data.datasets[0].data.reduce((a,b)=>a+b, 0);
    ctx.save();
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = "700 26px ui-monospace, 'SF Mono', Consolas, monospace";
    ctx.fillStyle = "#E8EAED";
    ctx.fillText(total, left + width/2, top + height/2 - 8);
    ctx.font = "600 10px ui-monospace, 'SF Mono', Consolas, monospace";
    ctx.fillStyle = "#9AA3AF";
    ctx.fillText("STUDENTS", left + width/2, top + height/2 + 14);
    ctx.restore();
  }
};
function doughnut(id, labels, data, colors){
  if(charts[id]){ charts[id].data.labels=labels; charts[id].data.datasets[0].data=data; charts[id].update(); return; }
  charts[id]=new Chart(document.getElementById(id),{type:"doughnut",
    data:{labels,datasets:[{data,backgroundColor:colors,borderWidth:0}]},
    plugins:[centerTextPlugin],
    options:{maintainAspectRatio:false,cutout:"62%",
      plugins:{legend:{position:"bottom"},
        tooltip:{callbacks:{label:ctx=>{
          const total = ctx.dataset.data.reduce((a,b)=>a+b,0);
          const pct = total ? ((ctx.parsed/total)*100).toFixed(0) : 0;
          return `${ctx.label}: ${ctx.parsed} students (${pct}%)`;
        }}}}}});
}

function bar(id, labels, data, color, horizontal){
  const cfg={type:"bar",data:{labels,datasets:[{data,backgroundColor:color,borderRadius:3}]},
    options:{maintainAspectRatio:false,indexAxis:horizontal?"y":"x",plugins:{legend:{display:false}},
      interaction:{mode:'nearest',intersect:true},
      scales:{x:{grid:{display:!horizontal}},y:{grid:{display:horizontal},ticks:{autoSkip:false}}}}};
  if(charts[id]){ charts[id].data.labels=labels; charts[id].data.datasets[0].data=data; charts[id].update(); }
  else charts[id]=new Chart(document.getElementById(id),cfg);
}

function line(id, labels, data){
  if(charts[id]){ charts[id].data.labels=labels; charts[id].data.datasets[0].data=data; charts[id].update(); return; }
  charts[id]=new Chart(document.getElementById(id),{type:"line",
    data:{labels,datasets:[{data,borderColor:C.ac,backgroundColor:"rgba(53,208,192,.15)",
      fill:true,tension:.3,pointRadius:0,pointHoverRadius:6,pointHoverBackgroundColor:C.ac,
      pointHoverBorderColor:"#fff",pointHoverBorderWidth:2}]},
    options:{maintainAspectRatio:false,plugins:{legend:{display:false},
        tooltip:{callbacks:{label:ctx=>`${ctx.parsed.y} events`}}},
      interaction:{mode:'index',intersect:false},
      scales:{x:{title:{display:true,text:"Date"},ticks:{maxRotation:0,minRotation:0,autoSkip:true,maxTicksLimit:7}},
              y:{title:{display:true,text:"Events per day"}}}}});
}

function renderRows(){
  const tb = document.getElementById("rows"); tb.innerHTML="";
  let filtered = lastStudents;
  if(currentFilter==="High"||currentFilter==="Medium"||currentFilter==="Low"){
    filtered = lastStudents.filter(s=>s.risk_band===currentFilter);
  } else if(currentFilter==="noassign"){
    filtered = lastStudents.filter(s=>(s.assign_events||0)===0);
  } else if(currentFilter==="inactive"){
    filtered = lastStudents.filter(s=>(s.active_weeks||0)===0);
  }
  filtered.forEach(s=>{
    const tr=document.createElement("tr");
    const eng=(s.engagement||0).toFixed(1);
    tr.innerHTML=`<td><a href="student.html?sid=${s.sid}&name=${encodeURIComponent(s.name||'Student '+s.sid)}" style="color:${C.ac};text-decoration:none;">${s.name||('Student '+s.sid)}</a></td>      
      <td>${s.gender||'—'}</td>
      <td><div class="bar"><div style="width:${Math.min(100,s.engagement||0)}%"></div></div>${eng}</td>
      <td>${s.total_events}</td><td>${s.active_weeks}</td>
      <td>${(s.risk_prob*100).toFixed(0)}%</td>
      <td><span class="badge ${s.risk_band}">${s.risk_band}</span></td>`;
    tb.appendChild(tr);
  });
}

document.getElementById("risk-filter").addEventListener("click", e=>{
  if(!e.target.matches(".filter-btn")) return;
  document.querySelectorAll(".filter-btn").forEach(b=>b.classList.remove("active"));
  e.target.classList.add("active");
  currentFilter = e.target.dataset.band;
  renderRows();
});

function showModal(filterValue, title){
  let list = lastStudents;
  if(filterValue==="High") list = lastStudents.filter(s=>s.risk_band==="High");
  else if(filterValue==="noassign") list = lastStudents.filter(s=>(s.assign_events||0)===0);
  else if(filterValue==="inactive") list = lastStudents.filter(s=>(s.active_weeks||0)===0);

  document.getElementById("modal-title").textContent = title;
  const listEl = document.getElementById("modal-list");
  listEl.innerHTML = list.length ? list.map(s=>
    `<div><a href="student.html?sid=${s.sid}&name=${encodeURIComponent(s.name||'Student '+s.sid)}">${s.name||('Student '+s.sid)}</a><span>${s.risk_band||''}</span></div>`
  ).join("") : `<div class="modal-empty">No students match.</div>`;
  document.getElementById("modal-overlay").style.display = "flex";
}
document.getElementById("modal-close").addEventListener("click", ()=>{
  document.getElementById("modal-overlay").style.display = "none";
});
document.getElementById("modal-overlay").addEventListener("click", e=>{
  if(e.target.id==="modal-overlay") document.getElementById("modal-overlay").style.display = "none";
});
document.getElementById("k-high").closest(".kpi").addEventListener("click", ()=>showModal("High","High-risk students"));
document.getElementById("k-nosub").closest(".kpi").addEventListener("click", ()=>showModal("noassign","No assignment interaction"));
document.getElementById("k-notlogin").closest(".kpi").addEventListener("click", ()=>showModal("inactive","Inactive since term start"));

async function refreshLive(){
  const o = await get("/overview");
  document.getElementById("k-total").textContent = o.total_students;
  document.getElementById("k-high").textContent = o.risk_bands.High||0;
  document.getElementById("k-eng").textContent = o.avg_engagement;
  const u = o.last_updated ? new Date(o.last_updated*1000).toLocaleTimeString() : "—";
  document.getElementById("updated").textContent = "live · scored "+u;
  const notice = document.getElementById("limited-notice");
  if (!o.last_updated || (o.risk_bands.High === 0 && o.risk_bands.Medium === 0 && o.risk_bands.Low === 0)) {
    notice.style.display = "block";
  } else {
    notice.style.display = "none";
  }
  doughnut("c-risk", ["High","Medium","Low"],
    [o.risk_bands.High||0,o.risk_bands.Medium||0,o.risk_bands.Low||0], [C.hi,C.med,C.lo]);
  const st = await get("/students");
  lastStudents = st;
  renderRows();
  const noSub = st.filter(s => (s.assign_events || 0) === 0).length;
  document.getElementById("k-nosub").textContent = noSub;
  const notLogin = st.filter(s => (s.active_weeks || 0) === 0).length;
  document.getElementById("k-notlogin").textContent = notLogin;
  const males = st.filter(s => s.gender === "M").length;
  const females = st.filter(s => s.gender === "F").length;
  document.getElementById("k-gender").textContent = `${males}/${females}`;
  const tl = await get("/timeline");
  line("c-timeline", tl.map(d=>d.day.slice(5).replace("-","/")), tl.map(d=>d.events));
  const fe = await get("/recent");
  const feed=document.getElementById("feed");
  feed.innerHTML = fe.length? fe.map(e=>`<div style="display:flex;justify-content:space-between;gap:10px"><span><b>${e.student}</b> — ${e.action} ${e.target}</span>
    <span style="flex-shrink:0;padding-right:6px">${e.time.slice(5,16)}</span></div>`).join("")
    : "<div>No live activity yet — log in to Moodle and click around.</div>";
}

const passLinePlugin = {
  id: 'passLine',
  afterDatasetsDraw(chart){
    if(chart.config.type!=='scatter') return;
    const y = chart.scales.y.getPixelForValue(50);
    const {left, right} = chart.chartArea, ctx = chart.ctx;
    ctx.save();
    ctx.strokeStyle = "rgba(154,163,175,.4)"; ctx.setLineDash([5,4]);
    ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke();
    ctx.fillStyle = C.mut; ctx.font = "600 9px ui-monospace, 'SF Mono', Consolas, monospace";
    ctx.fillText("PASS MARK 50", left+6, y-5);
    ctx.restore();
  }
};

async function refreshStatic(){

  const eo = await get("/engagement_outcome");
  const dot = b=>({label:`${b} risk`,
    data:eo.filter(p=>p.risk_band===b).map(p=>({x:p.engagement,y:p.mark,band:p.risk_band})),
    backgroundColor:b==="High"?C.hi:b==="Medium"?C.med:C.lo,pointRadius:4,
    pointHoverRadius:7,pointHoverBorderColor:"#fff",pointHoverBorderWidth:2});
  if(charts["c-scatter"]) charts["c-scatter"].destroy();
  charts["c-scatter"]=new Chart(document.getElementById("c-scatter"),{type:"scatter",
    data:{datasets:[dot("High"),dot("Medium"),dot("Low")]},
    plugins:[passLinePlugin],
    options:{maintainAspectRatio:false,plugins:{legend:{display:true,position:"bottom",
        labels:{usePointStyle:true,pointStyle:"circle",boxWidth:6,boxHeight:6}},
        tooltip:{callbacks:{label:ctx=>{
          const p = ctx.raw;
          return [`Engagement: ${p.x}`, `Final mark: ${p.y}`, `Risk: ${p.band}`];
        }}}},
      interaction:{mode:'nearest',intersect:true},
      scales:{x:{title:{display:true,text:"Engagement /100"}},
              y:{title:{display:true,text:"Final mark /100"}}}}});
}

refreshLive(); refreshStatic();
setInterval(refreshLive, 20000);
setInterval(refreshStatic, 120000);
