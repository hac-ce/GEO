import {session} from './session.ts';

export type CurrentUser = {id:number; email:string; is_active:boolean; is_superuser:boolean; is_verified:boolean};
export class ApiError extends Error {
  status:number;
  constructor(message:string,status:number) { super(message); this.status=status; }
}

export type Brand = {id:number; name:string; aliases:string[]; domain:string};
export type Prompt = {id:number; brand_id:number; question:string};
export type CollectionMethod = 'api'|'browser_doubao';
export type JobStatus = 'queued'|'running'|'succeeded'|'failed'|'interrupted'|'cancelled';
export type Job = {id:number; prompt_id:number; status:JobStatus; error:string|null; observation_id:number|null; created_at:string|null; started_at:string|null; finished_at:string|null; request_id:string|null; collection_method:CollectionMethod};
export type Observation = {id:number; prompt_id:number; question:string; answer:string; mentioned:boolean|null; prompted:boolean|null; created_at:string|null; provider:string|null; model:string|null};
export type Summary = {total_samples:number; eligible_samples:number; mentioned_samples:number; mention_rate:number|null};
export const statusNames:Record<JobStatus,string> = {queued:'排队中',running:'执行中',succeeded:'已完成',failed:'执行失败',interrupted:'已中断',cancelled:'已取消'};

// 页面统一通过同源 /api 请求学习版 FastAPI，不自动重试提交操作。
export function createApi(fetcher:typeof fetch = fetch, tokens:Pick<typeof session,'getToken'|'clearIfMatches'> = session) {
  let collectionScope = tokens.getToken();
  const pending = new Map<string,{key:string; inFlight?:Promise<Job>}>();
  async function request<T>(path:string, options:RequestInit = {}, authenticated=true):Promise<T> {
    const token = authenticated ? tokens.getToken() : null;
    const headers = new Headers(options.headers);
    if (!headers.has('Content-Type') && options.body !== undefined) headers.set('Content-Type','application/json');
    if (token) headers.set('Authorization','Bearer '+token);
    let response:Response;
    try {
      response = await fetcher('/api'+path, {...options,
        headers,
        signal:options.signal ?? AbortSignal.timeout(15000)});
    } catch(error) {
      if(options.signal?.aborted) throw error;
      throw new Error('连接失败或等待超时；提交采集后请先查看任务列表，确认是否已创建任务。');
    }
    if(response.status===401 && authenticated) tokens.clearIfMatches(token);
    if(response.status===204 && response.ok) return undefined as T;
    let data:unknown;
    try { data = await response.json(); }
    catch { throw new Error('服务返回了无法解析的响应（'+response.status+'）'); }
    if(!response.ok) {
      const detail = (data as {detail?:unknown})?.detail;
      const translations:Record<string,string> = {LOGIN_BAD_CREDENTIALS:'邮箱或密码不正确，或账号已停用',REGISTER_USER_ALREADY_EXISTS:'该邮箱已经注册，请直接登录',Unauthorized:'登录已失效，请重新登录'};
      const message = typeof detail === 'string' ? translations[detail]||detail : Array.isArray(detail)
        ? detail.map((item:{loc?:unknown[];msg?:string}) => (item.loc||[]).slice(1).join('.')+': '+item.msg).join('；')
        : '请求失败（'+response.status+'）';
      throw new ApiError(message,response.status);
    }
    return data as T;
  }
  const send = <T>(path:string, method:string, body?:unknown) => request<T>(path,{method,...(body===undefined?{}:{body:JSON.stringify(body)})});

  // 同一待确认操作保留编号供手动重试；不自动重试，不跨账号复用。
  function collect(prompt:number,method:CollectionMethod='api'):Promise<Job> {
    const scope = tokens.getToken();
    if (scope !== collectionScope) { pending.clear(); collectionScope = scope; }
    const pendingKey=prompt+':'+method;
    let entry = pending.get(pendingKey);
    if (entry?.inFlight) return entry.inFlight;
    if (!entry) {
      if (pending.size >= 100) return Promise.reject(new Error('待确认任务过多，请先查看任务列表。'));
      entry = {key:crypto.randomUUID()};
      pending.set(pendingKey,entry);
    }
    const operation = entry;
    operation.inFlight = request<Job>('/prompts/'+prompt+'/jobs'+(method==='api'?'':'?collection_method='+method),{
      method:'POST', headers:{'Idempotency-Key':operation.key},
    }).then(job=>{
      if (pending.get(pendingKey) === operation) pending.delete(pendingKey);
      return job;
    }).catch(error=>{
      // 结果未知和 429 保留编号；明确的输入、权限错误结束这次本地操作。
      if (error instanceof ApiError && [400,401,403,404,409,422].includes(error.status)
          && pending.get(pendingKey) === operation) pending.delete(pendingKey);
      throw error;
    }).finally(()=>{operation.inFlight=undefined;});
    return operation.inFlight;
  }
  return {
    login:(email:string,password:string)=>request<{access_token:string;token_type:string}>('/auth/session/login',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({username:email,password}).toString()},false),
    register:(email:string,password:string)=>request<CurrentUser>('/auth/register',{method:'POST',body:JSON.stringify({email,password})},false),
    me:()=>request<CurrentUser>('/auth/me'),
    logout:()=>request<void>('/auth/session/logout',{method:'POST'}),
    health:()=>request<{status:string;project:string;mode?:'demo'|'live';browser_enabled?:boolean}>('/health',{},false),
    brands:(offset=0,limit=21,q='')=>request<Brand[]>('/brands?'+new URLSearchParams({offset:String(offset),limit:String(limit),q})),
    brand:(id:number)=>request<Brand>('/brands/'+id),
    saveBrand:(data:Omit<Brand,'id'>,id?:number)=>send<Brand>(id?'/brands/'+id:'/brands',id?'PUT':'POST',data),
    prompts:(brand:number,offset=0,limit=21,q='')=>request<Prompt[]>('/brands/'+brand+'/prompts?'+new URLSearchParams({offset:String(offset),limit:String(limit),q})),
    savePrompt:(brand:number,question:string,id?:number)=>send<Prompt>(id?'/prompts/'+id:'/brands/'+brand+'/prompts',id?'PUT':'POST',{question}),
    summary:(brand:number)=>request<Summary>('/brands/'+brand+'/summary'),
    observations:(prompt:number,offset=0,limit=21)=>request<Observation[]>('/prompts/'+prompt+'/observations?'+new URLSearchParams({offset:String(offset),limit:String(limit)})),
    brandObservations:(brand:number,offset=0,limit=21)=>request<Observation[]>('/brands/'+brand+'/observations?'+new URLSearchParams({offset:String(offset),limit:String(limit)})),
    observation:(id:number)=>request<Observation>('/observations/'+id),
    jobs:(status:JobStatus|''='',offset=0,limit=20)=>request<Job[]>('/jobs?'+new URLSearchParams({...(status?{status}:{}),offset:String(offset),limit:String(limit)})),
    job:(id:number)=>request<Job>('/jobs/'+id),
    collect,
    cancel:(id:number)=>send<Job>('/jobs/'+id+'/cancel','POST'),
  };
}
export const api = createApi();
