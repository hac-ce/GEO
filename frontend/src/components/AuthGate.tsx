import {useEffect, useRef, useState, type ReactNode} from 'react';
import {Eye, EyeOff, Loader2, LogIn, UserPlus} from 'lucide-react';
import {api, ApiError, type CurrentUser} from '../lib/api';
import {session} from '../lib/session';
import '../login.css';

// 验证令牌后才挂载工作台，切换账号时销毁原用户的界面数据。
export default function AuthGate({children}:{children:(user:CurrentUser,onLogout:()=>Promise<void>)=>ReactNode}) {
  const [user,setUser]=useState<CurrentUser|null>(null);
  const [checking,setChecking]=useState(Boolean(session.getToken()));
  const [checkError,setCheckError]=useState('');
  const [retry,setRetry]=useState(0);
  useEffect(()=>session.subscribe(()=>{if(!session.getToken()){setUser(null);setCheckError('');setChecking(false);}}),[]);
  useEffect(()=>{
    const token=session.getToken();
    if(!token){setChecking(false);return;}
    let active=true;setChecking(true);setCheckError('');
    api.me().then(value=>{if(active&&session.getToken()===token)setUser(value);})
      .catch(error=>{if(active&&!(error instanceof ApiError&&error.status===401))setCheckError(error instanceof Error?error.message:'无法验证登录状态');})
      .finally(()=>{if(active)setChecking(false);});
    return()=>{active=false;};
  },[retry]);
  async function login(email:string,password:string){
    const result=await api.login(email,password);
    session.setToken(result.access_token);
    try {const value=await api.me();if(session.getToken()===result.access_token)setUser(value);}
    catch(error){session.clearIfMatches(result.access_token);throw error;}
  }
  async function logout(){
    try {await api.logout();}
    catch(error){
      if(!(error instanceof ApiError&&error.status===401))
        throw new Error('退出尚未确认，请保持当前页面并重试。');
    }
    session.setToken(null);setUser(null);
  }
  if(checking)return <div className="login-page"><div className="login-card auth-loading"><Loader2 className="spin" size={22}/>正在验证登录状态…</div></div>;
  if(checkError)return <div className="login-page"><div className="login-card"><h1>连接暂时不可用</h1><p role="alert">{checkError}</p><button onClick={()=>setRetry(value=>value+1)}>重试连接</button><button onClick={()=>session.setToken(null)}>返回登录</button></div></div>;
  if(user)return children(user,logout);
  return <LoginForm onLogin={login}/>;
}

// 复用 geo-monitor 登录页外观，只呈现已经接通的邮箱认证流程。
function LoginForm({onLogin}:{onLogin:(email:string,password:string)=>Promise<void>}){
  const [register,setRegister]=useState(false),[email,setEmail]=useState(''),[password,setPassword]=useState('');
  const [confirm,setConfirm]=useState(''),[visible,setVisible]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const lock=useRef(false);
  const [registered,setRegistered]=useState(false);
  async function submit(event:React.FormEvent){
    event.preventDefault();if(lock.current)return;
    if(register&&password!==confirm){setError('两次输入的密码不一致');return;}
    lock.current=true;setBusy(true);setError('');
    try {
      if(register){await api.register(email.trim(),password);setRegistered(true);setRegister(false);setConfirm('');}
      await onLogin(email.trim(),password);
    }catch(error){setError(error instanceof Error?error.message:'请求失败，请重试');}
    finally{lock.current=false;setBusy(false);}
  }
  return <div className="login-page"><div className="login-wrap"><div className="login-brand">GEO 品牌洞察</div><section className="login-card" aria-label={register?'注册账号':'账号登录'}>
    <header><h1>{register?'注册账号':'账号登录'}</h1><p>{register?'使用邮箱创建您的独立账号':'登录后管理您的品牌与采集任务'}</p></header>
    <form onSubmit={event=>void submit(event)}>
      <label className="login-field">邮箱<input type="email" autoComplete="username" value={email} onChange={event=>setEmail(event.target.value)} placeholder="请输入邮箱" maxLength={320} required disabled={busy}/></label>
      <label className="login-field">密码<span className="login-password"><input type={visible?'text':'password'} autoComplete={register?'new-password':'current-password'} value={password} onChange={event=>setPassword(event.target.value)} placeholder="请输入密码" maxLength={128} required disabled={busy}/><button type="button" aria-label={visible?'隐藏密码':'显示密码'} onClick={()=>setVisible(!visible)}>{visible?<EyeOff size={17}/>:<Eye size={17}/>}</button></span></label>
      {register&&<label className="login-field">确认密码<input type={visible?'text':'password'} autoComplete="new-password" value={confirm} onChange={event=>setConfirm(event.target.value)} required disabled={busy}/></label>}
      {registered&&<p className="login-message" role="status">账号已创建；如自动登录未成功，请使用刚才的邮箱和密码登录。</p>}
      {error&&<p className="login-message" role="alert">{error}</p>}
      <button className="login-submit" type="submit" disabled={busy||!email.trim()||!password||register&&!confirm}>{busy?<><Loader2 size={17} className="spin"/>处理中…</>:register?<><UserPlus size={17}/>注册并登录</>:<><LogIn size={17}/>登录</>}</button>
    </form>
    <div className="login-switch"><span>{register?'已有账号？':'还没有账号？'}</span><button type="button" disabled={busy} onClick={()=>{setRegister(!register);setError('');setRegistered(false);setConfirm('');}}>{register?'返回登录':'邮箱注册'}</button></div>
  </section></div></div>;
}
