"use client";
import { useAuth } from "react-oidc-context";
import useSWR, { SWRConfig } from "swr";
import useSWRInfinite from "swr/infinite";
import { CommandCenter } from "../components/command-center";
import { WorkspaceSettings } from "../components/workspace-settings";
import { AiCoreDock } from "../components/ai-core-dock";
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { LayoutDashboard, UsersRound, BriefcaseBusiness, Target, Megaphone, FileText, Globe2,
  Image as ImageIcon, Video, CheckSquare, ClipboardCheck, BarChart3, Settings2, Bot,
  Menu, LogOut, Plus, Download, Send, Check, X, RefreshCcw, Search,
  ShieldCheck, ChevronRight, AlertTriangle, LoaderCircle, Layers3 } from "lucide-react";
type Item = Record<string, unknown>;
type Business = {id:string;name:string;role:string};
type Me = {email:string;subject:string;businesses:Business[]};
type Section = "Dashboard"|"Leads"|"Clients"|"Opportunities"|"Campaigns"|"Content"|"Websites"|"Media Studio"|"Tasks"|"Approvals"|"Reports"|"Settings"|"AI Assistant"|"Proposals"|"Research";
type Field = {key:string;label:string;type?:"text"|"email"|"number"|"date"|"textarea"|"select";required?:boolean;options?:string[];placeholder?:string};
const pages: {label:Section;icon:typeof LayoutDashboard;route?:string}[] = [
  {label:"Dashboard",icon:LayoutDashboard,route:"/dashboard"}, {label:"Leads",icon:Target,route:"/leads"},
  {label:"Clients",icon:UsersRound,route:"/clients"}, {label:"Opportunities",icon:BriefcaseBusiness,route:"/opportunities"},
  {label:"Campaigns",icon:Megaphone,route:"/campaigns"}, {label:"Content",icon:FileText,route:"/outreach/drafts"},
  {label:"Proposals",icon:FileText,route:"/proposals"}, {label:"Websites",icon:Globe2,route:"/websites"},
  {label:"Media Studio",icon:ImageIcon,route:"/media"}, {label:"Tasks",icon:CheckSquare,route:"/tasks"},
  {label:"Approvals",icon:ClipboardCheck,route:"/approvals"}, {label:"Reports",icon:BarChart3,route:"/reports/pipeline"},
  {label:"AI Assistant",icon:Bot}, {label:"Research",icon:Search}, {label:"Settings",icon:Settings2,route:"/plugins"}
];
const fields:Partial<Record<Section,Field[]>> = {
  Leads:[{key:"business_name",label:"Business / lead name",required:true},{key:"industry",label:"Industry",placeholder:"cleaning"},{key:"email",label:"Email",type:"email"},{key:"phone",label:"Phone"},{key:"website",label:"Website URL",placeholder:"https://example.com"},{key:"location",label:"City / location"},{key:"lawful_basis",label:"Contact basis",type:"select",options:["","consent","legitimate_interest","contract"]},{key:"lawful_basis_note",label:"Contact basis evidence",type:"textarea"}],
  Clients:[{key:"name",label:"Client name",required:true},{key:"email",label:"Email",type:"email"},{key:"monthly_revenue",label:"Monthly recurring revenue ($)",type:"number"}],
  Opportunities:[{key:"name",label:"Opportunity",required:true},{key:"value",label:"Potential deal value ($)",type:"number",required:true},{key:"probability",label:"Win probability (%)",type:"number"}],
  Campaigns:[{key:"name",label:"Campaign name",required:true},{key:"channel",label:"Channel",type:"select",options:["email","social","seo","ads","other"]},{key:"objective",label:"Objective",type:"textarea",required:true}],
  Proposals:[{key:"title",label:"Proposal title",required:true},{key:"content",label:"Scope and deliverables",type:"textarea",required:true},{key:"amount",label:"Proposed amount ($)",type:"number"}],
  Websites:[{key:"company",label:"Business name",required:true},{key:"industry",label:"Industry",type:"select",options:["cleaning","hvac","roofing","plumbing","electrical","landscaping","medical","dental","law","real_estate","other"]}, {key:"tagline",label:"Headline",required:true},{key:"contact_email",label:"Public contact email",type:"email",required:true},{key:"city",label:"Service area / city",required:true},{key:"services",label:"Services (comma separated)",required:true}],
  "Media Studio":[{key:"kind",label:"Media format",type:"select",options:["image","video"]},{key:"title",label:"Headline",required:true},{key:"subtitle",label:"Supporting message"}],
  Tasks:[{key:"title",label:"Task title",required:true},{key:"description",label:"Description",type:"textarea"},{key:"due_at",label:"Due date",type:"date"}]
};
const routes:Partial<Record<Section,string>> = { Leads:"/leads",Clients:"/clients",Opportunities:"/opportunities",Campaigns:"/campaigns",Proposals:"/proposals",Websites:"/websites","Media Studio":"/media",Tasks:"/tasks"};
function str(v:unknown):string {return v==null?"":String(v);}
function dateLabel(v:unknown):string {if(!v)return "Not scheduled";const d=new Date(str(v));return Number.isNaN(d.valueOf())?"—":d.toLocaleDateString();}
function count(v:unknown):string {return typeof v==="number"?v.toLocaleString():"0";}
function usd(v:unknown):string {return new Intl.NumberFormat("en-US",{style:"currency",currency:"USD",maximumFractionDigits:0}).format(Number(v)||0);}
const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "";
const subscribeTheme=(notify:()=>void)=>{
  window.addEventListener("storage",notify);window.addEventListener("revenueos-theme",notify);
  return()=>{window.removeEventListener("storage",notify);window.removeEventListener("revenueos-theme",notify);};
};
function themeSnapshot():"system"|"dark"|"light" {
  try{const value=window.localStorage.getItem("revenueos-theme");return value==="dark"||value==="light"?value:"system";}catch{return "system";}
}
const subscribeSystemTheme=(notify:()=>void)=>{
  const media=window.matchMedia("(prefers-color-scheme: light)");media.addEventListener("change",notify);
  return()=>media.removeEventListener("change",notify);
};
const subscribeWorkspace=(notify:()=>void)=>{
  window.addEventListener("popstate",notify);window.addEventListener("revenueos-navigation",notify);
  return()=>{window.removeEventListener("popstate",notify);window.removeEventListener("revenueos-navigation",notify);};
};
function workspaceSnapshot():Section {
  const slug=new URLSearchParams(window.location.search).get("workspace");
  return pages.find(p=>p.label.toLowerCase().replaceAll(" ","-")===slug)?.label||"Dashboard";
}
const subscribeMobile=(notify:()=>void)=>{
  const media=window.matchMedia("(max-width: 800px)");media.addEventListener("change",notify);
  return()=>media.removeEventListener("change",notify);
};
export default function Home(){
  const auth=useAuth();
  return <SWRConfig key={auth.user?.profile.sub||"anonymous"} value={{provider:()=>new Map(),shouldRetryOnError:false}}><IdentityWorkspace/></SWRConfig>;
}
function IdentityWorkspace(){
  const auth=useAuth();const token=auth.user?.access_token;
  const [selectedBusiness,setSelectedBusiness]=useState("");
  const [setupName,setSetupName]=useState("");const [setupError,setSetupError]=useState("");const [saving,setSaving]=useState(false);
  const identity=useSWR<Me>(token?["identity",token]:null,async()=>{
    const response=await fetch(`${apiBase}/api/v1/me`,{headers:{Authorization:`Bearer ${token}`},cache:"no-store",signal:AbortSignal.timeout(30000)});
    if(!response.ok)throw new Error(`Could not load workspace access (${response.status}). Retry or sign in again.`);
    return response.json();
  });
  if(auth.isLoading)return <div className="auth-screen"><LoaderCircle className="spin"/><h2>Connecting securely…</h2></div>;
  if(auth.error)return <div className="auth-screen" role="alert"><AlertTriangle/><h2>Authentication failed</h2><p>{auth.error.message}</p><button onClick={()=>void auth.signinRedirect()} className="primary">Try again</button></div>;
  if(!auth.isAuthenticated||!token)return <div className="auth-screen"><div className="brand-mark"><Layers3/></div><p className="overline">REVENUE OPERATING SYSTEM</p><h1>Run your business.<br/><span>Not your software.</span></h1><p>One workspace for leads, clients, approvals, campaigns, websites, and revenue.</p><button className="primary large" onClick={()=>void auth.signinRedirect()}>Sign in securely <ChevronRight size={18}/></button></div>;
  if(identity.error)return <div className="auth-screen" role="alert"><h1>Workspace unavailable</h1><p>{identity.error.message}</p><button className="primary" onClick={()=>void identity.mutate()}>Retry</button><button className="outline" onClick={()=>void auth.signoutRedirect()}>Sign out</button></div>;
  const me=identity.data;
  if(!me||me.subject!==auth.user?.profile.sub)return <div className="auth-screen"><LoaderCircle className="spin"/><h2>Loading your workspace…</h2></div>;
  if(!me.businesses.length)return <div className="auth-screen"><div className="brand-mark"><ShieldCheck/></div><h1>Initialize your workspace</h1><p>Only the verified bootstrap administrator can create the first workspace.</p><form onSubmit={async event=>{
    event.preventDefault();setSaving(true);setSetupError("");
    try{const response=await fetch(`${apiBase}/api/v1/setup`,{method:"POST",headers:{Authorization:`Bearer ${token}`,"Content-Type":"application/json"},body:JSON.stringify({name:setupName,industry:"services"}),signal:AbortSignal.timeout(30000)});
      if(!response.ok){const body=await response.json();throw new Error(typeof body.detail==="string"?body.detail:"Workspace setup failed");}
      await identity.mutate();
    }catch(error){setSetupError((error as Error).message);}finally{setSaving(false);}
  }}><label htmlFor="setup-name">Business name</label><input id="setup-name" value={setupName} onChange={e=>setSetupName(e.target.value)} minLength={2} maxLength={160} required/><button className="primary" disabled={saving}>Create workspace</button></form>{setupError&&<p role="alert" className="error">{setupError}</p>}<button className="outline" onClick={()=>void auth.signoutRedirect()}>Sign out</button></div>;
  const businessId=me.businesses.some(b=>b.id===selectedBusiness)?selectedBusiness:me.businesses[0].id;
  return <Workspace key={businessId} me={me} businessId={businessId} setBusinessId={setSelectedBusiness} loadMe={async()=>{await identity.mutate();}}/>;
}
function Workspace({me,businessId,setBusinessId,loadMe}:{me:Me;businessId:string;setBusinessId:(id:string)=>void;loadMe:()=>Promise<void>}) {
  const auth=useAuth();
  const page=useSyncExternalStore<Section>(subscribeWorkspace,workspaceSnapshot,()=>"Dashboard");
  const mobile=useSyncExternalStore(subscribeMobile,()=>window.matchMedia("(max-width: 800px)").matches,()=>false);

  const [moreOpen,setMoreOpen] = useState(false);

  const [saving,setSaving] = useState(false);
  const [message,setMessage] = useState("");
  const [operationError,setError] = useState("");
  const [sidebar,setSidebar] = useState(false);
  useEffect(()=>{
    if(!sidebar||!mobile)return;
    const panel=document.getElementById("revenue-navigation");
    const controls=()=>Array.from(panel?.querySelectorAll<HTMLElement>("button:not(:disabled),select:not(:disabled)")||[]);
    controls()[0]?.focus();
    const handler=(event:KeyboardEvent)=>{
      if(event.key==="Escape"){setSidebar(false);return;}
      if(event.key!=="Tab")return;
      const items=controls();const first=items[0],last=items[items.length-1];
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
    };
    document.addEventListener("keydown",handler);
    return()=>{document.removeEventListener("keydown",handler);document.querySelector<HTMLButtonElement>('button[aria-label="Open navigation"]')?.focus();};
  },[sidebar,mobile]);
  const theme=useSyncExternalStore(subscribeTheme,themeSnapshot,()=>"system");
  const systemLight=useSyncExternalStore(subscribeSystemTheme,()=>window.matchMedia("(prefers-color-scheme: light)").matches,()=>false);
  const light=theme==="light"||(theme==="system"&&systemLight);
  const changeTheme=(next:"system"|"dark"|"light")=>{
    try{window.localStorage.setItem("revenueos-theme",next);window.dispatchEvent(new Event("revenueos-theme"));}catch{}
  };
  const [editingId,setEditingId] = useState("");

  const [newForm,setNewForm] = useState(false);
  const [values,setValues] = useState<Record<string,string>>({});
  const [query,setQuery] = useState("");
  const [chat,setChat] = useState("");
  const [answer,setAnswer] = useState("");
  const [chatRole,setChatRole] = useState("revenue");
  const [researchFilter,setResearchFilter] = useState({country:"US",state:"",city:"",radius:"25",industry:""});
  const [useAI,setUseAI] = useState(false);

    const [review,setReview] = useState<{id:string;action:string;decision:string;recipient_email:string;subject:string;body:string;review_hash:string}|null>(null);
  useEffect(()=>{
    if(!review)return;
    const handler=(event:KeyboardEvent)=>{
      if(event.key==="Escape"){event.preventDefault();setReview(null);return;}
      if(event.key!=="Tab")return;
      const dialog=document.querySelector<HTMLElement>(".review-dialog");
      if(!dialog)return;
      const focusable=Array.from(dialog.querySelectorAll<HTMLElement>("button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled)"));
      if(!focusable.length)return;
      const first=focusable[0],last=focusable[focusable.length-1];
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
    };
    document.addEventListener("keydown",handler);
    return ()=>document.removeEventListener("keydown",handler);
  },[review]);

  const token = auth.user?.access_token;
  const call = useCallback(async (path:string, method="GET", body?:unknown, requireBusiness=true, signal?:AbortSignal):Promise<unknown> => {
    if(!token)throw new Error("Authentication required");
    const response=await fetch(`${apiBase}/api/v1${path}`,{
      method,
      headers:{"Authorization":`Bearer ${token}`,...(requireBusiness&&businessId?{"X-Business-Id":businessId}:{}),...(body?{"Content-Type":"application/json"}:{})},
      body:body?JSON.stringify(body):undefined,cache:"no-store",
      signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(120000)]) : AbortSignal.timeout(120000)
    });
    if(!response.ok){let detail=`Request failed (${response.status})`;try{const json=await response.json();detail=typeof json.detail==="string"?json.detail:JSON.stringify(json.detail);}catch{}throw new Error(detail);}
    return response.status===204?{}:response.json();
  },[businessId,token]);
  const selected=pages.find(p=>p.label===page);
  const summary=useSWR<Item>((page==="Dashboard"||page==="Reports")?[selected?.route,businessId,token]:null,([path]:[string])=>call(path) as Promise<Item>);
  const isList=Boolean(selected?.route)&&!["Dashboard","Reports","Settings"].includes(page);
  const list=useSWRInfinite<Item[]>((index,previous:Item[]|null)=>{
    if(!isList||(previous&&previous.length<50))return null;
    return [`${selected?.route}?limit=50&offset=${index*50}`,businessId,token];
  },([path]:[string])=>call(path) as Promise<Item[]>,{revalidateFirstPage:true});
  const priorities=useSWR<Item[]>(page==="Dashboard"?["/leads",businessId,token]:null,([path]:[string])=>call(path) as Promise<Item[]>);
  const recipients=useSWR<Item[]>(page==="Content"?["/leads?limit=100",businessId,token]:null,([path]:[string])=>call(path) as Promise<Item[]>);
  const rows=(list.data||[]).flat();const report=summary.data||{};
  const dashboardLeads=priorities.data||[];const dashboardLeadsError=priorities.error?.message||"";
  const leadOptions=recipients.data||[];
  const loading=isList?list.isLoading||list.isValidating:summary.isLoading||summary.isValidating;
  const hasMore=isList&&Boolean(list.data?.length)&&list.data![list.data!.length-1].length===50;
  const error=operationError||summary.error?.message||list.error?.message||recipients.error?.message||"";
  const reload=async(append=false):Promise<void>=>{
    setError("");if(append){await list.setSize(list.size+1);return;}
    await Promise.all([summary.mutate(),list.mutate(),priorities.mutate(),recipients.mutate()]);
  };
  const save=async(e:React.FormEvent)=>{
    e.preventDefault();const path=routes[page];if(!path)return;setSaving(true);setError("");setMessage("");
    try{
      const payload:Record<string,unknown>={};
      for(const [k,v] of Object.entries(values)){if(v.trim()===""||k.startsWith("metric_"))continue;payload[k]=["value","amount","probability","monthly_revenue"].includes(k)?Number(v):v;}
      if(page==="Leads"){
        if(editingId&&!values.lawful_basis)payload.lawful_basis=null;
        const metrics:Record<string,number>={};
        for(const key of ["seo","reviews","website","social","market"])if(values[`metric_${key}`]?.trim())metrics[key]=Number(values[`metric_${key}`]);
        if(Object.keys(metrics).length||editingId)payload.metrics=metrics;
      }
      if(page==="Websites")payload.services=(values.services||"").split(",").map(x=>x.trim()).filter(Boolean);
      if(page==="Media Studio")payload.kind=values.kind||"image";
      if(page==="Campaigns")payload.channel=values.channel||"email";
      if(page==="Websites")payload.industry=values.industry||"cleaning";
      if(page==="Tasks"&&values.due_at)payload.due_at=new Date(values.due_at+"T17:00:00").toISOString();
      const result=await call(editingId?`${path}/${editingId}`:path,editingId?"PATCH":"POST",payload) as Item;
      setMessage(page==="Websites"?"Website source generated. Download it below.":page==="Media Studio"?`Media status: ${str(result.status)}. Download when ready.`:"Saved successfully.");
      setValues({});setNewForm(false);setEditingId("");await reload();
    }catch(e){setError((e as Error).message);}finally{setSaving(false);}
  };
  const edit=async(path:string,body:unknown)=>{setSaving(true);setError("");try{await call(path,"PATCH",body);setMessage("Updated.");await reload();}catch(e){setError((e as Error).message);}finally{setSaving(false);}};
  const decide=async(id:string,decision:string)=>{setSaving(true);setError("");try{await call(`/approvals/${id}/decision`,"POST",{decision,review_hash:decision==="approved"?review?.review_hash:undefined});setMessage(`Approval ${decision}.`);setReview(null);await reload();}catch(e){setError((e as Error).message);}finally{setSaving(false);}};
  const reviewApproval=async(id:string)=>{
    setSaving(true);setError("");
    try{setReview(await call(`/approvals/${id}/preview`) as NonNullable<typeof review>);}catch(e){setError((e as Error).message);}finally{setSaving(false);}
  };
  const download=async(path:string,filename:string)=>{
    setSaving(true);setError("");try{
      const res=await fetch(`${apiBase}/api/v1${path}`,{headers:{Authorization:`Bearer ${token}`,"X-Business-Id":businessId},cache:"no-store"});
      if(!res.ok)throw new Error(`Download failed (${res.status})`);
      const blob=await res.blob();const url=URL.createObjectURL(blob);const anchor=document.createElement("a");anchor.href=url;anchor.download=filename;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),60000);
    }catch(e){setError((e as Error).message);}finally{setSaving(false);}
  };
  const submitChat=async(e:React.FormEvent)=>{e.preventDefault();setSaving(true);setError("");try{const res=await call("/assistant/chat","POST",{message:chat,role:chatRole,use_ai:useAI}) as Item;setAnswer(str(res.message));if(res.notice)setMessage(str(res.notice));}catch(e){setError((e as Error).message);}finally{setSaving(false);}};
  const navigate=(target:Section,create=false)=>{
    setEditingId("");
    const url=new URL(window.location.href);url.searchParams.set("workspace",target.toLowerCase().replaceAll(" ","-"));
    window.history.pushState(null,"",url);window.dispatchEvent(new Event("revenueos-navigation"));
    setQuery("");setValues({});setMessage("");setError("");setNewForm(create);setSidebar(false);
  };
  const beginEdit=(item:Item)=>{
    const editable:Record<string,string>={};
    for(const field of fields[page]||[])editable[field.key]=str(item[field.key]);
    for(const [metric,value] of Object.entries((item.metrics||{}) as Item))editable[`metric_${metric}`]=str(value);
    setValues(editable);setEditingId(str(item.id));setNewForm(true);
    window.scrollTo({top:0,behavior:"instant"});
  };
  const filtered=useMemo(()=>rows.filter(r=>JSON.stringify(r).toLowerCase().includes(query.toLowerCase())),[rows,query]);
  const currentBusiness=me.businesses.find(b=>b.id===businessId);
  return <div className={`shell ${light ? "light" : ""}`}>
    {sidebar&&<button aria-label="Close navigation" className="nav-backdrop" onClick={()=>setSidebar(false)}/>}
    <aside id="revenue-navigation" inert={mobile&&!sidebar} aria-label="Workspace navigation" role={mobile?"dialog":undefined} aria-modal={mobile&&sidebar?true:undefined} className={`sidebar ${sidebar?"open":""}`}>
      {mobile&&<button className="icon-btn" aria-label="Close navigation" onClick={()=>setSidebar(false)}><X size={20}/></button>}
      <div className="sidebar-brand"><div className="brand-mark small"><Layers3/></div><div><strong>RevenueOS</strong><span>BUSINESS COMMAND</span></div></div>
      <div className="workspace-picker"><span>WORKSPACE</span><select aria-label="Select business" value={businessId} disabled={saving} onChange={e=>setBusinessId(e.target.value)}>{me.businesses.map(b=><option value={b.id} key={b.id}>{b.name}</option>)}</select><small>{currentBusiness?.role||"member"} access</small></div>
      <div className="nav-label">WORKSPACE</div><nav aria-label="Primary navigation">{pages.filter(p=>["Dashboard","Leads","Clients","Campaigns","Approvals"].includes(p.label)).map(({label,icon:Icon})=><button key={label} className={`nav-link ${page===label?"selected":""}`} onClick={()=>navigate(label)}><Icon size={19}/><span>{label==="Dashboard"?"Home":label}</span>{page===label&&<span className="active-dot"/>}</button>)}<button className="nav-link nav-more" aria-expanded={moreOpen} aria-controls="other-workspaces" onClick={()=>setMoreOpen(v=>!v)}><Layers3 size={19}/><span>All tools</span><ChevronRight className={moreOpen?"rotate":""} size={15}/></button>{(moreOpen||["Opportunities","Content","Proposals","Websites","Media Studio","Tasks","Reports","Research","AI Assistant","Settings"].includes(page))&&<div id="other-workspaces" className="nav-subgroup">{pages.filter(p=>["Opportunities","Content","Proposals","Websites","Media Studio","Tasks","Reports","Research","AI Assistant","Settings"].includes(p.label)).map(({label,icon:Icon})=><button key={label} className={`nav-link ${page===label?"selected":""}`} onClick={()=>navigate(label)}><Icon size={17}/><span>{label}</span></button>)}</div>}</nav>
      <div className="sidebar-bottom"><div className="avatar">{me.email.charAt(0).toUpperCase()}</div><div className="account-meta"><strong>{me.email.split("@")[0]}</strong><span>{me.email}</span></div><button aria-label="Sign out" className="icon-btn" onClick={()=>void auth.signoutRedirect()}><LogOut size={18}/></button></div>
    </aside>
    <a className="skip-link" inert={mobile&&sidebar} href="#workspace-content">Skip to workspace</a>
    <main className="main" id="workspace-content" tabIndex={-1} inert={mobile&&sidebar}>
      <header className="topbar"><div className="topbar-left"><button className="icon-btn mobile-menu" aria-label="Open navigation" aria-controls="revenue-navigation" aria-expanded={sidebar} onClick={()=>setSidebar(true)}><Menu/></button><span className="breadcrumbs">RevenueOS <ChevronRight size={15}/> <strong>{page==="Dashboard"?"Command Center":page}</strong></span></div><div className="topbar-actions"><span className="connection"><span className="status-dot"/> Workspace secured</span><label className="neo-sr-only" htmlFor="theme-select">Color theme</label><select id="theme-select" className="theme-select" value={theme} onChange={e=>changeTheme(e.target.value as "system"|"dark"|"light")} aria-label="Theme"><option value="system">System</option><option value="dark">Dark</option><option value="light">Light</option></select><button aria-label="Refresh" className="icon-btn" onClick={()=>void reload()}><RefreshCcw size={18}/></button><div className="avatar compact">{me.email.charAt(0).toUpperCase()}</div></div></header>
      <div className="content"><div className="page-head"><div><span className="overline">{page==="Dashboard"?"EXECUTIVE OVERVIEW":"REVENUEOS / WORKSPACE"}</span><h1>{page==="Dashboard"?"Revenue, in command.":page}</h1><p>{page==="Dashboard"?"One command center for your AI, pipeline and next actions.":page==="AI Assistant"?"One assistant, six role profiles, with human approvals for external actions.":"Manage work and review results for your selected business."}</p></div>{routes[page]&&<button className="primary" onClick={()=>{setEditingId("");setValues({});setNewForm(v=>!v);}}><Plus size={17}/>{newForm?"Cancel":"Create new"}</button>}</div>
      {error&&<div className="error" role="alert"><AlertTriangle size={18}/><span>{error}</span><button onClick={()=>setError("")} aria-label="Dismiss error"><X size={15}/></button></div>}
      {message&&<div className="success" role="status"><Check size={18}/><span>{message}</span><button onClick={()=>setMessage("")} aria-label="Dismiss message"><X size={15}/></button></div>}
      {page==="Dashboard"&&!error&&<CommandCenter report={report} leads={dashboardLeads} loading={loading||!Object.keys(report).length} leadError={dashboardLeadsError} command={chat} setCommand={setChat} answer={answer} sending={saving} useAI={useAI} setUseAI={setUseAI} onSubmit={submitChat} navigate={navigate}/>}
      {newForm&&fields[page]&&<form className="panel form-panel" onSubmit={save}><div className="panel-head"><h2>{editingId?"Edit":"Create"} {page==="Media Studio"?"media":page.toLowerCase().slice(0,-1)}</h2><span className="muted">Saved to your business workspace</span></div><div className="fields">{fields[page]?.map(f=><label key={f.key} className={f.type==="textarea"?"wide":""}><span>{f.label}{f.required?" *":""}</span>{f.type==="textarea"?<textarea value={values[f.key]||""} required={f.required} onChange={e=>setValues({...values,[f.key]:e.target.value})} rows={4}/>:f.type==="select"?<select value={values[f.key]||f.options?.[0]} onChange={e=>setValues({...values,[f.key]:e.target.value})}>{f.options?.map(x=><option value={x} key={x}>{x.replaceAll("_"," ")}</option>)}</select>:<input type={f.type||"text"} required={f.required} placeholder={f.placeholder} min={f.type==="number"?"0":undefined} step={f.type==="number"?"any":undefined} value={values[f.key]||""} onChange={e=>setValues({...values,[f.key]:e.target.value})}/>}</label>)}</div>{page==="Leads"&&<fieldset className="metrics-fields"><legend>Observed digital health (0–100)</legend><p>Leave unknown values blank. Scores describe measured digital health, not buying intent.</p><div className="fields">{["seo","reviews","website","social","market"].map(metric=><label key={metric}><span>{metric}</span><input type="number" min={0} max={100} step={1} value={values[`metric_${metric}`]||""} onChange={e=>setValues({...values,[`metric_${metric}`]:e.target.value})}/></label>)}</div></fieldset>}<div className="form-footer"><button type="submit" className="primary" disabled={saving}>{saving?<LoaderCircle className="spin" size={17}/>:<Check size={17}/>} Save {page==="Websites"?"website source":page==="Media Studio"?"and render":"record"}</button></div></form>}
      {page==="Research"&&<section className="panel form-panel neo-research"><div className="panel-head"><div><h2>Research a market</h2><p>Set a target region and industry. Generate a research request for the AI Core.</p></div><Search size={20}/></div><form onSubmit={e=>{e.preventDefault();setChat(`Prepare a compliant, evidence-based research plan for ${researchFilter.industry} businesses in ${researchFilter.city}, ${researchFilter.state}, ${researchFilter.country} within approximately ${researchFilter.radius} miles. Identify useful public data sources, scoring criteria and next steps. Do not invent prospect listings; ask for a connected lead provider if none is configured.`);navigate("AI Assistant");}}><div className="fields"><label><span>Country *</span><input required value={researchFilter.country} onChange={e=>setResearchFilter({...researchFilter,country:e.target.value})} maxLength={64}/></label><label><span>State / province *</span><input required value={researchFilter.state} onChange={e=>setResearchFilter({...researchFilter,state:e.target.value})} maxLength={80}/></label><label><span>City *</span><input required value={researchFilter.city} onChange={e=>setResearchFilter({...researchFilter,city:e.target.value})} maxLength={80}/></label><label><span>Radius (miles)</span><input type="number" min={1} max={500} value={researchFilter.radius} onChange={e=>setResearchFilter({...researchFilter,radius:e.target.value})}/></label><label className="wide"><span>Industry *</span><input required value={researchFilter.industry} onChange={e=>setResearchFilter({...researchFilter,industry:e.target.value})} placeholder="e.g. roofing, dental, property management" maxLength={100}/></label></div><p className="muted">Research requests are drafts. Live lead discovery requires a connected and authorized data source.</p><button type="submit" className="primary"><Search size={16}/> Prepare AI research</button></form></section>}
      {page==="AI Assistant"&&<section className="panel chat-panel"><div className="chat-intro"><div className="item-icon teal"><Bot/></div><div><h2>RevenueOS Assistant</h2><p>Guided planning by default. Configured AI providers are optional.</p></div></div><div className="chat-output" role="status" aria-live="polite">{answer||"I can help you qualify leads, prepare proposals, draft campaigns, and plan your next actions. External actions always need your approval."}</div><div className="assistant-quick-actions" aria-label="Quick workspace actions"><button type="button" onClick={()=>navigate("Leads")}><Target size={16}/> Review leads</button><button type="button" onClick={()=>navigate("Proposals")}><FileText size={16}/> Proposals</button><button type="button" onClick={()=>navigate("Approvals")}><ShieldCheck size={16}/> Approvals</button></div><form onSubmit={submitChat}><label htmlFor="chat-prompt">Your instruction</label><textarea id="chat-prompt" value={chat} onChange={e=>setChat(e.target.value)} rows={4} placeholder="Create a 90-day marketing plan for my cleaning business" minLength={2} required/><div className="chat-footer"><select aria-label="Agent role" value={chatRole} onChange={e=>setChatRole(e.target.value)}>{["revenue","sales","research","marketing","operations","engineering"].map(r=><option key={r}>{r}</option>)}</select><label className="check"><input type="checkbox" checked={useAI} onChange={e=>setUseAI(e.target.checked)}/> Use configured AI provider</label><button className="primary" disabled={saving}>{saving?<LoaderCircle className="spin" size={17}/>:<Send size={17}/>} Ask</button></div></form></section>}
      {page==="Reports"&&!error&&Object.keys(report).length>0&&<><div className="stat-grid">{[{label:"Leads",value:count(report.lead_volume)},{label:"Conversion",value:report.conversion_rate==null?"Insufficient data":str(report.conversion_rate)+"%"},{label:"MRR",value:usd(report.mrr)},{label:"Pipeline",value:usd(report.pipeline_value)}].map(x=><div className="stat-card" key={x.label}><div className="stat-top">{x.label}</div><strong>{x.value}</strong></div>)}</div><section className="panel"><h2>Pipeline stages</h2><div className="pipeline-stages">{Object.entries((report.stages||{}) as Record<string,number>).map(([k,v])=><div key={k}><span>{k.replaceAll("_"," ")}</span><strong>{v}</strong><div className="progress"><div style={{width:`${Math.min(100,v/Math.max(1,Number(report.lead_volume))*100)}%`}}/></div></div>)}{!Object.keys((report.stages||{}) as object).length&&<Empty text="Pipeline metrics appear as you add leads."/>}</div><p className="muted">MRR and pipeline value are entered amounts, not payment-processor reconciliations.</p></section></>}
      {page==="Content"&&<><div className="panel-head page-subhead"><h2>Human-approved email drafts</h2><button className="primary" onClick={()=>{setValues({});setNewForm(v=>!v);}}><Plus size={17}/> Compose</button></div>{newForm&&<form className="panel form-panel" onSubmit={async e=>{e.preventDefault();setSaving(true);try{await call("/outreach/drafts","POST",{lead_id:values.lead_id,subject:values.subject,body:values.body});setMessage("Draft saved and approval requested.");setValues({});setNewForm(false);setEditingId("");await reload();}catch(e){setError((e as Error).message);}finally{setSaving(false);}}}><div className="fields">{[{key:"lead_id",label:"Recipient lead"},{key:"subject",label:"Subject"},{key:"body",label:"Email body"}].map(f=><label key={f.key}><span>{f.label}</span>{f.key==="lead_id"?<select required value={values.lead_id||""} onChange={e=>setValues({...values,lead_id:e.target.value})}><option value="">Choose a lead with an email</option>{leadOptions.filter(lead=>lead.email).map(lead=><option key={str(lead.id)} value={str(lead.id)}>{str(lead.business_name)} — {str(lead.email)}</option>)}</select>:<textarea rows={f.key==="body"?5:1} value={values[f.key]||""} required onChange={e=>setValues({...values,[f.key]:e.target.value})}/>}</label>)}</div><button className="primary" disabled={saving}>Save for approval</button></form>}{renderRows(filtered,page,download,edit,saving,call,reload,setMessage,setError,reviewApproval,beginEdit)}</>}
      {page==="Settings"&&<WorkspaceSettings key={businessId} call={call} role={currentBusiness?.role||"viewer"} onChanged={loadMe}/>}
      {!(["Dashboard","Reports","AI Assistant","Settings","Content","Research"] as Section[]).includes(page)&&<section className="panel list-panel"><div className="panel-head"><h2>{page==="Media Studio"?"Your creative assets":"Records"}</h2><div className="search-box"><Search size={17}/><input aria-label="Search records" placeholder="Search loaded records" value={query} onChange={e=>setQuery(e.target.value)}/></div></div>{loading?<div className="loading"><LoaderCircle className="spin"/> Loading records…</div>:renderRows(filtered,page,download,edit,saving,call,reload,setMessage,setError,reviewApproval,beginEdit)}</section>}
      {hasMore&&!(["Dashboard","Reports","Settings","Research","AI Assistant"] as Section[]).includes(page)&&<button className="outline" disabled={loading} onClick={()=>void reload(true)}>{loading?"Loading…":"Load more records"}</button>}
      </div>
    </main>
    {review&&<div className="review-backdrop" role="presentation"><section className="review-dialog" role="dialog" aria-modal="true" aria-labelledby="review-title"><div className="panel-head"><div><span className="overline">REVIEW BEFORE DECIDING</span><h2 id="review-title">Outgoing email approval</h2></div><button className="icon-btn" aria-label="Close review" autoFocus onClick={()=>setReview(null)}><X size={20}/></button></div><p className="review-notice">Approval authorizes this specific email for later manual sending. It does not send it now.</p><div className="review-field"><span>Recipient</span><strong>{review.recipient_email}</strong></div><div className="review-field"><span>Subject</span><strong>{review.subject}</strong></div><div className="review-field"><span>Message body</span><div className="review-body">{review.body}</div></div><div className="review-actions"><button className="outline" onClick={()=>setReview(null)}>Cancel</button><button className="outline" disabled={saving} onClick={()=>void decide(review.id,"rejected")}><X size={16}/> Reject</button><button className="primary" disabled={saving||review.decision!=="pending"} onClick={()=>void decide(review.id,"approved")}><ShieldCheck size={16}/> Approve this email</button></div></section></div>}
    {page!=="Dashboard"&&!(mobile&&sidebar)&&<AiCoreDock command={chat} setCommand={setChat} onSubmit={submitChat} answer={answer} sending={saving} useAI={useAI} setUseAI={setUseAI}/>}
    <nav className="bottom-nav" inert={mobile&&sidebar} aria-label="Mobile navigation">{(["Dashboard","Leads","AI Assistant","Approvals","Tasks"] as Section[]).map(label=>{const entry=pages.find(x=>x.label===label)!;const Icon=entry.icon;return <button key={label} className={page===label?"active":""} aria-current={page===label?"page":undefined} onClick={()=>navigate(label)}><Icon size={21}/><span>{label==="AI Assistant"?"Command":label==="Dashboard"?"Home":label}</span></button>})}</nav>
  </div>;
}
function Empty({text}:{text:string}){return <div className="empty"><span className="empty-symbol"><Layers3 size={25}/></span><p>{text}</p></div>;}
function renderRows(rows:Item[],page:Section,download:(p:string,n:string)=>Promise<void>,edit:(p:string,b:unknown)=>Promise<void>,saving:boolean,call:(p:string,m?:string,b?:unknown)=>Promise<unknown>,reload:()=>Promise<void>,setMessage:(s:string)=>void,setError:(s:string)=>void,onReview:(id:string)=>Promise<void>,onEdit:(item:Item)=>void){
  if(!rows.length)return <Empty text={page==="Leads"?"No leads yet. Create your first lead or import verified records.":"Nothing here yet. Use Create new to add your first record."}/>;
  return <div className="record-list">{rows.map(x=>{
    const id=str(x.id);const title=str(x.business_name||x.name||x.title||x.company||x.action||x.subject||"Untitled");
    return <article className="record" key={id}><div className="record-main"><span className="record-icon">{page==="Media Studio"?(x.kind==="video"?<Video size={20}/>:<ImageIcon size={20}/>):<BriefcaseBusiness size={20}/>}</span><div className="record-info"><h3>{title}</h3><p>{str(x.email||x.location||x.channel||x.description||x.subtitle||x.resource_type||x.industry||x.objective||"")}</p><div className="record-meta">{x.opted_out===true&&<span>Outreach suppressed · </span>}<span>{dateLabel(x.created_at)}</span><span className="dot-sep">·</span><span>{str(x.grade||x.stage||x.status||x.decision||x.kind||"").replaceAll("_"," ")}</span>{x.score!=null&&<><span className="dot-sep">·</span><span>Score {str(x.score)}/100 ({str(x.score_confidence)}% measured)</span></>}</div></div></div><div className="record-actions">
      {["Leads","Clients","Opportunities","Campaigns","Proposals"].includes(page)&&<button className="outline" disabled={saving} onClick={()=>onEdit(x)}>Edit</button>}
      {page==="Leads"&&<button className="outline" disabled={saving} onClick={()=>void edit(`/leads/${id}`,{opted_out:!x.opted_out})}>{x.opted_out?"Remove suppression":"Suppress outreach"}</button>}
      {page==="Leads"&&<select aria-label={`Stage for ${title}`} value={str(x.stage)} onChange={e=>void edit(`/leads/${id}`,{stage:e.target.value})} disabled={saving}>{["new","qualified","contacted","proposal_sent","meeting_booked","client","lost"].map(s=><option key={s}>{s}</option>)}</select>}
      {page==="Clients"&&<button className="outline" disabled={saving} onClick={()=>void edit(`/clients/${id}`,{active:!x.active})}>{x.active?"Mark inactive":"Reactivate"}</button>}
      {page==="Opportunities"&&<select aria-label={`Status for ${title}`} value={str(x.stage)} disabled={saving} onChange={e=>void edit(`/opportunities/${id}`,{stage:e.target.value})}>{["open","won","lost"].map(stage=><option key={stage}>{stage}</option>)}</select>}
      {page==="Tasks"&&x.status!=="done"&&<button className="outline" onClick={()=>void edit(`/tasks/${id}`,{status:"done"})} disabled={saving}><Check size={16}/> Complete</button>}
      {page==="Approvals"&&x.decision==="pending"&&<button className="outline approve" onClick={()=>void onReview(id)} disabled={saving}><ShieldCheck size={16}/> Review & decide</button>}
      {page==="Proposals"&&<><button className="outline" onClick={()=>void download(`/proposals/${id}/export?format=pdf`,`proposal-${id}.pdf`)}><Download size={16}/> PDF</button><button className="outline" onClick={()=>void download(`/proposals/${id}/export?format=docx`,`proposal-${id}.docx`)}><Download size={16}/> DOCX</button></>}
      {page==="Websites"&&<button className="outline" onClick={()=>void download(`/websites/${id}/download`,`website-${id}.zip`)}><Download size={16}/> Source</button>}
      {page==="Media Studio"&&x.status==="done"&&<button className="outline" onClick={()=>void download(`/media/${id}/download`,`media-${id}.${x.kind==="video"?"mp4":"svg"}`)}><Download size={16}/> Export</button>}
      {page==="Content"&&x.status==="draft"&&x.approval_decision!=="approved"&&<span className="status-pill">{x.approval_decision==="rejected"?"Rejected":"Awaiting approval"}</span>}
      {page==="Content"&&x.status==="draft"&&x.approval_decision==="approved"&&<button className="outline" onClick={async()=>{try{await call(`/outreach/${id}/send`,"POST");setMessage("Email sent.");await reload();}catch(e){setError((e as Error).message);}}}><Send size={16}/> Send approved</button>}
    </div></article>;
  })}</div>;
}
