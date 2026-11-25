import {useEffect, useRef, useState, type ReactNode, type ComponentType} from 'react';
import {LayoutDashboard, Target, ListChecks, FileText, LogOut, ChevronRight, Plus, RefreshCw, Radar, ArrowRight, Menu, Eye, CheckCircle2, Layers3, Loader2} from 'lucide-react';
import {api, statusNames, type Brand, type Prompt, type Observation, type JobStatus, type CurrentUser, type CollectionMethod} from './lib/api';
import Dialog from './components/Dialog';
import AnswerContent from './components/AnswerContent';

type View = 'overview'|'brands'|'tasks'|'answers';
type Modal = {kind:'brand';brand?:Brand}|{kind:'prompt';prompt?:Prompt}|{kind:'collect';prompt?:Prompt}|null;
const navigation = [{id:'overview',name:'数据概览',icon:LayoutDashboard},{id:'brands',name:'品牌与问题',icon:Target},{id:'tasks',name:'监控任务',icon:ListChecks},{id:'answers',name:'回答洞察',icon:FileText}] as const;
const unknown = (value:boolean|null) => value === null ? '未分析' : value ? '是' : '否';
const message = (error:unknown) => error instanceof Error ? error.message : '操作失败，请刷新后重试';

// 请求结果与筛选键绑定，忽略过期请求，避免切换品牌时显示旧结果。
function useResource<T>(key:string, loader:()=>Promise<T>) {
  const load = useRef(loader); load.current = loader;
  const [state,setState] = useState<{key:string;data?:T;error:string;loading:boolean}>({key:'',error:'',loading:true});
  useEffect(()=>{let active=true;setState(previous=>({key,data:previous.key===key?previous.data:undefined,error:'',loading:true}));
    load.current().then(data=>{if(active)setState({key,data,error:'',loading:false});}).catch(error=>{if(active)setState(previous=>({...previous,key,error:message(error),loading:false}));});
    return()=>{active=false;};
  },[key]);
  return state.key===key?state:{key,error:'',loading:true,data:undefined};
}

function Empty({text,action}:{text:string;action?:()=>void}) {return <div className="empty"><Radar size={32}/><h3>{text}</h3>{action&&<button className="primary" onClick={action}><Plus size={15}/>开始创建</button>}</div>;}
function Metric({title,value,sub,icon:Icon}:{title:string;value:string;sub:string;icon:ComponentType<{size?:number}>}) {return <section className="metric"><div className="metric-label">{title}<Icon size={17}/></div><div className="metric-value">{value}</div><p>{sub}</p></section>;}

// 每页显示20条，多取一条仅用于判断下一页。
function ListPager({label,page,loading,hasNext,change}:{label:string;page:number;loading:boolean;hasNext:boolean;change:(page:number)=>void}) {
  return <div className="pagination"><span>{label}第 {page+1} 页 · 每页 20 条</span><div className="learning-actions"><button aria-label={label+'上一页'} disabled={page===0||loading} onClick={()=>change(page-1)}>上一页</button><button aria-label={label+'下一页'} disabled={!hasNext||loading} onClick={()=>change(page+1)}>下一页</button></div></div>;
}

// 使用 geo-monitor 的工作台布局与样式，业务数据全部来自学习版 API。
export default function App({user,onLogout}:{user:CurrentUser;onLogout:()=>Promise<void>}) {
  const [view,setView]=useState<View>('overview'),[mobile,setMobile]=useState(false);
  const [brandId,setBrandId]=useState<number|null>(null),[revision,setRevision]=useState(0);
  const [brandPage,setBrandPage]=useState(0),[brandQuery,setBrandQuery]=useState(''),[brandDraft,setBrandDraft]=useState('');
  const [promptPaging,setPromptPaging]=useState({brand:null as number|null,page:0}),[answerPaging,setAnswerPaging]=useState({brand:null as number|null,page:0});
  const [modal,setModal]=useState<Modal>(null),[answer,setAnswer]=useState<Observation|null>(null);
  const [status,setStatus]=useState<JobStatus|''>(''),[page,setPage]=useState(0);
  const [notice,setNotice]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const actionLock=useRef(false);
  const brands=useResource('brands:'+brandPage+':'+brandQuery+':'+revision,()=>api.brands(brandPage*20,21,brandQuery));
  useEffect(()=>{if(brandId===null&&brands.data?.length)setBrandId(brands.data[0].id);},[brands.data,brandId]);
  const selectedBrand=useResource('selected-brand:'+brandId+':'+revision,()=>brandId===null?Promise.resolve(undefined):api.brand(brandId));
  const brand=selectedBrand.data||brands.data?.find(item=>item.id===brandId);
  const visibleBrands=brands.data?.slice(0,20)||[];
  const brandOptions=brand&&!visibleBrands.some(item=>item.id===brand.id)?[brand,...visibleBrands]:visibleBrands;
  const promptPage=promptPaging.brand===brandId?promptPaging.page:0;
  const answerPage=answerPaging.brand===brandId?answerPaging.page:0;
  useEffect(()=>{setPromptPaging({brand:brandId,page:0});setAnswerPaging({brand:brandId,page:0});},[brandId]);
  const prompts=useResource('prompts:'+brandId+':'+promptPage+':'+revision,()=>brandId===null?Promise.resolve([]):api.prompts(brandId,promptPage*20,21));
  const recentPrompts=useResource('recent-prompts:'+brandId+':'+revision,()=>brandId===null?Promise.resolve([]):api.prompts(brandId,0,5));
  const summary=useResource('summary:'+brandId+':'+revision,()=>brandId===null?Promise.resolve(null):api.summary(brandId));
  const jobs=useResource('jobs:'+status+':'+page+':'+revision,()=>api.jobs(status,page*20,21));
  const answers=useResource('answers:'+brandId+':'+answerPage+':'+revision,()=>brandId===null?Promise.resolve([]):api.brandObservations(brandId,answerPage*20,21));
  const recentAnswers=useResource('recent-answers:'+brandId+':'+revision,()=>brandId===null?Promise.resolve([]):api.brandObservations(brandId,0,4));
  const health=useResource('health:'+revision,()=>api.health());
  const active=jobs.data?.some(job=>job.status==='queued'||job.status==='running');
  useEffect(()=>{if(!active)return;const timer=setInterval(()=>setRevision(value=>value+1),4000);return()=>clearInterval(timer);},[active]);
  useEffect(()=>{if(!notice)return;const timer=setTimeout(()=>setNotice(''),5000);return()=>clearTimeout(timer);},[notice]);
  function refresh(){setRevision(value=>value+1);}
  function go(next:View){setView(next);setMobile(false);refresh();}
  function create(){if(!brand){setModal({kind:'brand'});return;}setModal(recentPrompts.data?.length?{kind:'collect'}:{kind:'prompt'});}
  async function act(action:()=>Promise<unknown>,text:string){if(actionLock.current)return;actionLock.current=true;setBusy(true);setError('');try{await action();setNotice(text);refresh();}catch(error){setError(message(error));}finally{actionLock.current=false;setBusy(false);}}
  function saved(text:string,savedBrand?:Brand){if(savedBrand)setBrandId(savedBrand.id);setModal(null);setNotice(text);refresh();}
  const title=navigation.find(item=>item.id===view)!.name;
  const failed=error||brands.error||selectedBrand.error||prompts.error||jobs.error||summary.error||answers.error||recentAnswers.error||recentPrompts.error||health.error;
  const sample=summary.data;
  return <div className="app-shell">
    <aside className={'sidebar '+(mobile?'open':'')}><div className="workspace-title">?????</div><div className="workspace"><span className="workspace-avatar">{user.email[0].toUpperCase()}</span><div>品牌洞察工作空间<small>Brand Intelligence</small></div></div><p className="nav-caption">工作台</p><nav>{navigation.map(item=><button key={item.id} className={view===item.id?'active':''} onClick={()=>go(item.id)}><item.icon size={19}/>{item.name}</button>)}</nav><div className="sidebar-bottom"><div className="helper-card"><Radar size={20}/><strong>让品牌被 AI 看见</strong><p>从真实回答中，观察品牌的自然提及情况。</p><button onClick={create}>开始监控<ArrowRight size={14}/></button></div><div className="profile"><span className="profile-avatar">G</span><span>{user.email}<small>个人工作区</small></span></div></div></aside>
    {mobile&&<button className="mobile-backdrop" aria-label="关闭导航" onClick={()=>setMobile(false)}/>}
    <div className="main-shell"><header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-menu" aria-label="展开导航" onClick={()=>setMobile(true)}><Menu size={20}/></button><span>工作台</span><ChevronRight size={13}/><strong>{title}</strong></div><div className="top-actions"><span className="subtle-tag">{health.data?'后端已连接':'连接中'}</span><button disabled={busy} onClick={()=>void act(onLogout,'已退出登录')}><LogOut size={14}/>退出登录</button></div></header>
    <main><div className="page-heading"><div><div className="eyebrow">AI BRAND INTELLIGENCE</div><h1>{view==='overview'?'品牌可见性概览':title}<span className="version-tag">LEARNING</span></h1><p>管理品牌与问题，追踪每次 AI 采集任务，查看可追溯的回答。</p></div><div className="heading-actions"><button onClick={refresh} disabled={busy}><RefreshCw size={15}/>重新加载</button><button className="primary" onClick={create} disabled={busy||brands.loading||selectedBrand.loading||prompts.loading}><Plus size={16}/>新建监控</button></div></div>
    {health.data?.mode==='demo'&&<div className="learning-note" role="note">本机演示模式：数据单独保存，回答由本地模拟生成，不调用真实 DeepSeek。</div>}
    {failed&&<div className="error-box" role="alert">{failed}<button onClick={()=>{setError('');refresh();}}>重新加载</button></div>}
    {view!=='tasks'&&<><div className="filters"><div className="filter-brand"><span className="brand-square">{brand?.name[0]||'品'}</span><select aria-label="监控品牌" value={brandId??''} onChange={event=>setBrandId(Number(event.target.value))}><option value="" disabled>请选择品牌</option>{brandOptions.map(item=><option value={item.id} key={item.id}>{item.name}</option>)}</select></div><div className="filter-separator"/><Layers3 size={15}/><span>API / 网页采集</span></div><div className="brand-browser"><form className="brand-search" onSubmit={event=>{event.preventDefault();setBrandQuery(brandDraft.trim());setBrandPage(0);}}><input aria-label="搜索品牌" maxLength={80} value={brandDraft} onChange={event=>setBrandDraft(event.target.value)} placeholder="按品牌名称或域名搜索"/><button type="submit">搜索</button><button type="button" onClick={()=>{setBrandDraft('');setBrandQuery('');setBrandPage(0);}}>清空搜索</button></form><div className="brand-pagination"><span>品牌第 {brandPage+1} 页 · 每页 20 条</span><button aria-label="品牌上一页" disabled={brandPage===0||brands.loading} onClick={()=>setBrandPage(value=>value-1)}>上一页</button><button aria-label="品牌下一页" disabled={!brands.data||brands.data.length<=20||brands.loading} onClick={()=>setBrandPage(value=>value+1)}>下一页</button></div>{!brands.loading&&!brands.error&&!visibleBrands.length&&<p role="status">{brandQuery?'没有匹配的品牌，请修改搜索条件。':'本页没有品牌，可返回上一页或添加品牌。'}</p>}</div></>}
    {brands.loading&&<div className="loading-line"><Loader2 size={14} className="spin"/>正在加载品牌…</div>}
    {view==='overview'&&<><div className="metric-grid"><Metric title="自然提及率" value={sample?.mention_rate!=null?(sample.mention_rate*100).toFixed(1)+'%':'—'} sub="排除问题中已点名品牌及未分析的回答" icon={Eye}/><Metric title="自然回答样本" value={String(sample?.eligible_samples??0)} sub="符合自然提及率统计条件的回答" icon={Target}/><Metric title="自然提及次数" value={String(sample?.mentioned_samples??0)} sub="自然回答中提及品牌或别名的次数" icon={CheckCircle2}/><Metric title="全部回答" value={String(sample?.total_samples??0)} sub="当前品牌下所有问题的历史回答" icon={FileText}/></div><div className="learning-grid"><section className="panel"><div className="panel-head"><div><h2>监测问题</h2><p>{brand?.name||'请选择品牌'} · 已保存的采集输入</p></div><button onClick={()=>brand?setModal({kind:'prompt'}):setModal({kind:'brand'})}><Plus size={15}/>添加问题</button></div><div className="learning-list">{recentPrompts.data?.map(prompt=><div className="learning-row" key={prompt.id}><div><strong>{prompt.question}</strong><small>问题 #{prompt.id}</small></div><button onClick={()=>setModal({kind:'collect',prompt})}>采集</button></div>)}{!recentPrompts.data?.length&&<Empty text="还没有监测问题"/>}</div></section><section className="panel"><div className="panel-head"><div><h2>最近回答</h2><p>点击查看完整回答与提及分析</p></div><button onClick={()=>go('answers')}>查看全部<ArrowRight size={14}/></button></div><div className="learning-list">{recentAnswers.data?.map(row=><div className="learning-row" key={row.id}><div><strong>{row.question}</strong><small>回答 #{row.id} · 提及品牌：{unknown(row.mentioned)}</small></div><button onClick={()=>setAnswer(row)}>详情</button></div>)}{!recentAnswers.data?.length&&<Empty text="等待采集结果" action={create}/>}</div></section></div></>}
    {view==='brands'&&<div className="learning-grid"><section className="panel"><div className="panel-head"><div><h2>品牌资料</h2><p>品牌名称和别名用于匹配回答中的提及</p></div><button onClick={()=>setModal({kind:'brand'})}><Plus size={15}/>添加品牌</button></div><div className="learning-list">{visibleBrands.map(item=><div className="learning-row" key={item.id}><div><strong>{item.name}</strong><small>#{item.id} · {item.domain||'未填域名'}</small><small>别名：{item.aliases.join('、')||'无'}</small></div><div className="learning-actions"><button onClick={()=>setBrandId(item.id)}>{brandId===item.id?'已选择':'选择'}</button><button onClick={()=>setModal({kind:'brand',brand:item})}>编辑</button></div></div>)}{!brands.loading&&!brands.error&&!visibleBrands.length&&!brandQuery&&brandPage===0&&<Empty text="先创建一个品牌" action={()=>setModal({kind:'brand'})}/>}</div></section><section className="panel"><div className="panel-head"><div><h2>{brand?.name||'当前品牌'}的监测问题</h2><p>修改问题不会改变已有回答与任务快照</p></div><button disabled={!brand} onClick={()=>setModal({kind:'prompt'})}><Plus size={15}/>添加问题</button></div><div className="learning-list">{prompts.data?.slice(0,20).map(prompt=><div className="learning-row" key={prompt.id}><div><strong>{prompt.question}</strong><small>问题 #{prompt.id}</small></div><div className="learning-actions"><button onClick={()=>setModal({kind:'prompt',prompt})}>编辑</button><button className="primary" onClick={()=>setModal({kind:'collect',prompt})}>采集</button></div></div>)}{!prompts.data?.length&&<Empty text="还没有监测问题"/>}</div><ListPager label="问题" page={promptPage} loading={prompts.loading} hasNext={(prompts.data?.length||0)>20} change={next=>setPromptPaging({brand:brandId,page:next})}/></section></div>}
    {view==='tasks'&&<section className="panel"><div className="panel-head"><div><h2>采集任务</h2><p>所有品牌 · 按编号倒序 · 当前页有活动任务时每 4 秒刷新</p></div><select aria-label="任务状态" value={status} onChange={event=>{setStatus(event.target.value as JobStatus|'');setPage(0);}}><option value="">全部状态</option>{Object.entries(statusNames).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></div><div className="table-scroll"><table className="learning-table"><thead><tr><th>任务 / 问题</th><th>状态</th><th>执行说明</th><th>回答</th><th>操作</th></tr></thead><tbody>{jobs.data?.slice(0,20).map(job=><tr key={job.id}><td><strong>任务 #{job.id}</strong><div className="task-subtitle">问题 #{job.prompt_id}</div></td><td><span className={'badge '+job.status}><i/>{statusNames[job.status]||job.status}</span></td><td className="error-cell">{(job.collection_method==='browser_doubao'?'豆包网页':'API')+' · '+(job.error||'—')}</td><td>{job.observation_id?'#'+job.observation_id:'—'}</td><td>{job.status==='queued'?<button disabled={busy} onClick={()=>void act(()=>api.cancel(job.id),'排队任务已取消')}>取消任务</button>:job.observation_id?<button disabled={busy} onClick={()=>void act(async()=>setAnswer(await api.observation(job.observation_id!)),'已读取回答')}>查看回答</button>:<span>—</span>}</td></tr>)}</tbody></table></div>{!jobs.loading&&!jobs.data?.length&&<Empty text="暂无符合条件的任务"/>}<div className="pagination"><span>第 {page+1} 页 · 每页最多 20 条</span><div className="learning-actions"><button disabled={page===0||jobs.loading} onClick={()=>setPage(value=>value-1)}>上一页</button><button disabled={!jobs.data||jobs.data.length<=20||jobs.loading} onClick={()=>setPage(value=>value+1)}>下一页</button></div></div></section>}
    {view==='answers'&&<section className="panel"><div className="panel-head"><div><h2>回答洞察</h2><p>{brand?.name||'当前品牌'} · 展示已保存的原始回答，保留提问快照</p></div></div>{answers.loading&&<div className="learning-empty">正在加载回答…</div>}<div className="answer-grid">{answers.data?.slice(0,20).map(row=><button className="answer-card" key={row.id} onClick={()=>setAnswer(row)}><span className="badge succeeded">回答 #{row.id}</span><h3>{row.question}</h3><p>{row.answer.slice(0,180)}</p><div className="answer-meta"><span>{row.provider||'未知来源'} · 提及：{unknown(row.mentioned)}</span><span>问题点名：{unknown(row.prompted)}</span></div></button>)}</div>{!answers.loading&&!answers.data?.length&&<Empty text="暂无回答，先提交一次采集" action={create}/>}<ListPager label="回答" page={answerPage} loading={answers.loading} hasNext={(answers.data?.length||0)>20} change={next=>setAnswerPaging({brand:brandId,page:next})}/></section>}
    <footer className="page-footer">GEO · 品牌 AI 可见性监测 · 数据来自当前工作区</footer></main></div>
    {modal&&<Editor key={modal.kind+('prompt'in modal?modal.prompt?.id:'brand'in modal?modal.brand?.id:'new')} modal={modal} brand={brand} prompts={prompts.data?.slice(0,20)||[]} demo={health.data?.mode==='demo'} browserEnabled={Boolean(health.data?.browser_enabled)} onClose={()=>setModal(null)} onSaved={saved}/>}
    {answer&&<Dialog title={'回答 #'+answer.id} subtitle={'问题 #'+answer.prompt_id+' · '+(answer.provider||'未知来源')} wide onClose={()=>setAnswer(null)}><h3 className="learning-answer-title">{answer.question}</h3><div className="answer-meta"><span>提及品牌：{unknown(answer.mentioned)}</span><span>问题点名品牌：{unknown(answer.prompted)}</span></div><AnswerContent content={answer.answer}/></Dialog>}
    {notice&&<div className="toast" role="status"><CheckCircle2 size={16}/>{notice}</div>}
  </div>;
}

// 复用原有弹窗，保存品牌/问题或明确提交一次采集，不重试付费请求。
function Editor({modal,brand,prompts,demo,browserEnabled,onClose,onSaved}:{modal:NonNullable<Modal>;brand:Brand|undefined;prompts:Prompt[];demo:boolean;browserEnabled:boolean;onClose:()=>void;onSaved:(text:string,brand?:Brand)=>void}) {
  const initialBrand=modal.kind==='brand'?modal.brand:undefined;
  const initialPrompt=modal.kind==='prompt'||modal.kind==='collect'?modal.prompt:undefined;
  const [name,setName]=useState(initialBrand?.name||''),[aliases,setAliases]=useState(initialBrand?.aliases.join('，')||''),[domain,setDomain]=useState(initialBrand?.domain||'');
  const [question,setQuestion]=useState(initialPrompt?.question||''),[promptId,setPromptId]=useState(initialPrompt?.id??prompts[0]?.id??0);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const [collectionMethod,setCollectionMethod]=useState<CollectionMethod>('api'),[collectPage,setCollectPage]=useState(0);
  const collectPrompts=useResource('collect-prompts:'+modal.kind+':'+brand?.id+':'+collectPage,()=>modal.kind==='collect'&&brand?api.prompts(brand.id,collectPage*20,21):Promise.resolve([]));
  const collectOptions=collectPrompts.data?.slice(0,20)||[];
  const [selectedPrompt,setSelectedPrompt]=useState<Prompt|undefined>(initialPrompt||prompts[0]);
  const promptOptions=selectedPrompt&&!collectOptions.some(item=>item.id===selectedPrompt.id)?[selectedPrompt,...collectOptions]:collectOptions;
  useEffect(()=>{if(!promptId&&collectOptions.length){setPromptId(collectOptions[0].id);setSelectedPrompt(collectOptions[0]);}},[collectPrompts.data,promptId]);
  const lock=useRef(false);
  const title=modal.kind==='brand'?(initialBrand?'编辑品牌':'添加品牌'):modal.kind==='prompt'?(initialPrompt?'编辑监测问题':'添加监测问题'):'提交问答采集';
  async function submit(event:React.FormEvent){event.preventDefault();if(lock.current)return;lock.current=true;setBusy(true);setError('');try{
    if(modal.kind==='brand'){if(!name.trim())throw new Error('品牌名称不能为空');const savedBrand=await api.saveBrand({name:name.trim(),aliases:aliases.split(/[,，;；\n]/).map(value=>value.trim()).filter(Boolean),domain:domain.trim()},initialBrand?.id);onSaved('品牌已保存',savedBrand);}
    else if(modal.kind==='prompt'){if(!brand)throw new Error('请先选择品牌');if(!question.trim())throw new Error('问题不能为空');await api.savePrompt(brand.id,question.trim(),initialPrompt?.id);onSaved('监测问题已保存');}
    else{if(!promptId)throw new Error('请先创建监测问题');const job=await api.collect(promptId,collectionMethod);onSaved('任务 #'+job.id+' 已提交，请在监控任务中查看进度');}
  }catch(error){setError(message(error));}finally{lock.current=false;setBusy(false);}}
  let fields:ReactNode;
  if(modal.kind==='brand')fields=<><label>品牌名称<input autoFocus required maxLength={80} value={name} onChange={event=>setName(event.target.value)} placeholder="例如：华为"/></label><label>品牌别名<input value={aliases} onChange={event=>setAliases(event.target.value)} placeholder="用逗号分隔，例如 Huawei，HUAWEI"/></label><label>品牌域名<input maxLength={253} value={domain} onChange={event=>setDomain(event.target.value)} placeholder="例如 huawei.com（可留空）"/></label></>;
  else if(modal.kind==='prompt')fields=<><p>当前品牌：{brand?.name||'未选择'}</p><label>监测问题<textarea autoFocus required minLength={1} maxLength={500} rows={4} value={question} onChange={event=>setQuestion(event.target.value)} placeholder="例如：推荐几个手机品牌"/></label></>;
  else fields=<><p>当前品牌：{brand?.name}</p><label>监测问题<select aria-label="采集问题" value={promptId} onChange={event=>{const id=Number(event.target.value);setPromptId(id);setSelectedPrompt(promptOptions.find(item=>item.id===id));}}>{promptOptions.map(prompt=><option key={prompt.id} value={prompt.id}>#{prompt.id} · {prompt.question}</option>)}</select></label><ListPager label="采集问题" page={collectPage} loading={collectPrompts.loading} hasNext={(collectPrompts.data?.length||0)>20} change={setCollectPage}/>{collectPrompts.error&&<p role="alert">{collectPrompts.error}</p>}<label>采集方式<select aria-label="采集方式" value={collectionMethod} onChange={event=>setCollectionMethod(event.target.value as CollectionMethod)}><option value="api">DeepSeek API</option><option value="browser_doubao" disabled={!browserEnabled}>豆包网页版（Playwright）{!browserEnabled?' · 未启用':''}</option></select></label><div className="learning-note">{collectionMethod==='browser_doubao'?'将在后端电脑使用独立豆包浏览器，登录或验证码需自行处理。':demo?'当前为本机演示：使用本地模拟回答，不调用真实模型。':'后台 Worker 会调用 DeepSeek API，可能产生费用。'}关闭弹窗不停止任务；排队中可在任务列表取消。</div></>;
  return <Dialog title={title} subtitle="品牌 AI 可见性监测" onClose={()=>{if(!busy)onClose();}}><form className="learning-form" onSubmit={event=>void submit(event)}>{fields}{error&&<div className="error-box" role="alert">{error}</div>}<div className="heading-actions"><button type="button" disabled={busy} onClick={onClose}>取消</button><button className="primary" type="submit" disabled={busy}>{busy?<Loader2 size={15} className="spin"/>:<Plus size={15}/>} {busy?'提交中…':modal.kind==='collect'?'提交采集任务':'保存'}</button></div></form></Dialog>;
}
