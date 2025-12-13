// frontend/index.js
// assume api.js already loaded (api, setAuth, logout)

async function doLogin(){
  const loginMsg = document.getElementById("loginMsg");
  const loginEmail = document.getElementById("loginEmail");
  const loginPw = document.getElementById("loginPw");

  loginMsg.textContent = "Logging in...";
  try{
    const res = await api("/login", "POST", { email: loginEmail.value, password: loginPw.value });
    setAuth(res.token, res.user?.role);
    localStorage.setItem("user", JSON.stringify(res.user || {}));
    loginMsg.textContent = "✅ Login success! Redirecting to menu...";
    setTimeout(()=>window.location="menu.html", 500);
  }catch(e){
    loginMsg.textContent = "❌ " + e.message;
  }
}

async function doRegister(){
  const regMsg = document.getElementById("regMsg");
  const regName = document.getElementById("regName");
  const regEmail = document.getElementById("regEmail");
  const regPw = document.getElementById("regPw");
  const regRole = document.getElementById("regRole");

  regMsg.textContent = "Creating account...";
  try{
    const res = await api("/register", "POST", {
      name: regName.value,
      email: regEmail.value,
      password: regPw.value,
      role: regRole.value
    });
    setAuth(res.token, res.user?.role);
    localStorage.setItem("user", JSON.stringify(res.user || {}));
    regMsg.textContent = "✅ Register success! Redirecting to menu...";
    setTimeout(()=>window.location="menu.html", 500);
  }catch(e){
    regMsg.textContent = "❌ " + e.message;
  }
}

// expose to inline onclick
window.doLogin = doLogin;
window.doRegister = doRegister;