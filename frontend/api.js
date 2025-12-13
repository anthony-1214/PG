const API_BASE = "https://pg-1-3sfs.onrender.com";

function getToken(){ return localStorage.getItem("token"); }
function setAuth(token, role){
  localStorage.setItem("token", token);
  if (role) localStorage.setItem("role", role);
}
function logout(){
  localStorage.removeItem("token");
  localStorage.removeItem("role");
  localStorage.removeItem("user");
  window.location = "index.html";
}

async function api(path, method="GET", body=null){
  const headers = { "Content-Type": "application/json" };
  const t = getToken();
  if (t) headers["Authorization"] = "Bearer " + t;

  const res = await fetch(API_BASE + path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : null
  });

  const data = await res.json().catch(()=>({}));
  if (!res.ok) throw new Error(data.error || ("HTTP " + res.status));
  return data;
}

function fmtMoney(n){ return "$" + Number(n||0).toLocaleString(); }
function statusTag(status){
  const s = (status||"").toUpperCase();
  if (s==="READY") return `<span class="tag ready">● READY</span>`;
  if (s==="PREPARING") return `<span class="tag prep">● PREPARING</span>`;
  if (s==="COMPLETED") return `<span class="tag done">● COMPLETED</span>`;
  if (s==="CANCELLED") return `<span class="tag cancel">● CANCELLED</span>`;
  return `<span class="tag">● ${s}</span>`;
}