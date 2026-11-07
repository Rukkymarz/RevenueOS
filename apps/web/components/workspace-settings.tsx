"use client";

import { useEffect, useState } from "react";
import { Download, RefreshCcw, ShieldCheck, Upload } from "lucide-react";

type Item = Record<string, unknown>;
type Call = (path:string, method?:string, body?:unknown, requireBusiness?:boolean, signal?:AbortSignal)=>Promise<unknown>;

export function WorkspaceSettings({call,role,subject,onChanged}:{call:Call;role:string;subject:string;onChanged:()=>Promise<void>}) {
  const [plugins,setPlugins]=useState<Item[]>([]);
  const [members,setMembers]=useState<Item[]>([]);
  const [events,setEvents]=useState<Item[]>([]);
  const [usage,setUsage]=useState<Item>({});
  const [error,setError]=useState("");
  const [notice,setNotice]=useState("");
  const [busy,setBusy]=useState(false);
  const [revision,setRevision]=useState(0);
  const [member,setMember]=useState({subject:"",email:"",role:"viewer"});
  const [workspace,setWorkspace]=useState("");
  const operator=["admin","manager","operator"].includes(role);

  useEffect(()=>{
    const controller=new AbortController();
    async function load(){
      setError("");
      const get=(path:string)=>call(path,"GET",undefined,true,controller.signal);
      try {
        if(operator){
          const [inventory,quota]=await Promise.all([get("/plugins"),get("/ai/usage")]);
          if(!controller.signal.aborted){setPlugins(inventory as Item[]);setUsage(quota as Item);}
        }
        if(role==="admin"){
          const [people,audit]=await Promise.all([get("/members"),get("/audit-events")]);
          if(!controller.signal.aborted){setMembers(people as Item[]);setEvents(audit as Item[]);}
        }
      }catch(e){if(!controller.signal.aborted)setError((e as Error).message);}
    }
    void load();return()=>controller.abort();
  },[call,role,operator,revision]);

  async function action(work:()=>Promise<string>){
    setBusy(true);setError("");setNotice("");
    try{setNotice(await work());setRevision(v=>v+1);}catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }

  return <div className="settings-grid">
    {error&&<p role="alert" className="error">{error}</p>}
    {notice&&<p role="status" className="success">{notice}</p>}
    <section className="panel"><div className="panel-head"><h2>Workspace access</h2><button className="icon-btn" aria-label="Refresh settings" onClick={()=>setRevision(v=>v+1)}><RefreshCcw size={18}/></button></div>
      <p>Your role: <strong>{role}</strong>. Administrators manage access; managers review and send approved work.</p>
      <p>Your sign-in ID: <code>{subject}</code></p>
      <p className="settings-note"><ShieldCheck size={18}/> Provider credentials stay on the server. External publishing and sending require separate approval.</p>
    </section>
    {operator&&<section className="panel"><h2>Connections and AI usage</h2>
      <p>{usage.enabled?"AI gateway enabled":"AI gateway not connected"} · {String(usage.runs_today??"—")} / {String(usage.daily_limit??"—")} runs today. Quota resets at 00:00 UTC for each workspace and user.</p>
      {plugins.map(plugin=><div className="item-row" key={String(plugin.id)}><div><strong>{String(plugin.id)}</strong><p>{(plugin.capabilities as string[]||[]).join(" · ")}</p></div><span className="status-pill">{plugin.enabled?"Available":"Not configured"}</span></div>)}
      <p className="muted">Availability reflects configuration. Live provider verification is required before use. Lead discovery, social publishing and generated AI imagery/video are not connected.</p>
    </section>}
    {operator&&<section className="panel"><h2>Import verified leads</h2><p>Select a JSON file with a <code>leads</code> array (maximum 100 records and 256 KB). Each record needs a business_name. Optional fields: email, website, phone, industry, location, source, external_id, metrics, lawful_basis and lawful_basis_note.</p>
      <p>Keep the same source and external_id to skip previously imported records. Importing never sends outreach.</p>
      <label className="import-control"><Upload size={18}/> Lead JSON file<input type="file" accept=".json,application/json" disabled={busy} onChange={e=>{
        const file=e.target.files?.[0];e.target.value="";if(!file)return;
        void action(async()=>{if(file.size>262144)throw new Error("Choose a file smaller than 256 KB");
          const data=JSON.parse(await file.text());const payload=Array.isArray(data)?{leads:data}:data;
          const result=await call("/leads/import","POST",payload) as Item;
          return `Imported ${result.imported} leads; skipped ${result.skipped} duplicates.`;
        });
      }}/></label>
    </section>}
    {role==="admin"&&<>
      <section className="panel"><h2>Team members</h2><p>Add an existing RevenueOS identity by its subject ID and verified email. Create and verify the identity in the sign-in service first.</p>
        {members.map(person=><div className="item-row" key={String(person.id)}><strong>{String(person.email)}</strong><span className="status-pill">{String(person.role)}</span></div>)}
        <form className="settings-form" onSubmit={e=>{e.preventDefault();void action(async()=>{await call("/members","POST",member);setMember({subject:"",email:"",role:"viewer"});return "Member added.";});}}>
          <label>Identity subject<input required minLength={8} maxLength={180} value={member.subject} onChange={e=>setMember({...member,subject:e.target.value})}/></label>
          <label>Email<input required type="email" value={member.email} onChange={e=>setMember({...member,email:e.target.value})}/></label>
          <label>Role<select value={member.role} onChange={e=>setMember({...member,role:e.target.value})}>{["viewer","operator","manager","admin"].map(value=><option key={value}>{value}</option>)}</select></label>
          <button className="primary" disabled={busy}>Add member</button>
        </form>
      </section>
      <section className="panel"><h2>Additional workspace</h2><form className="settings-form" onSubmit={e=>{e.preventDefault();void action(async()=>{await call("/businesses","POST",{name:workspace,industry:"services"});setWorkspace("");await onChanged();return "Workspace created. Select it in the workspace menu.";});}}><label>Workspace name<input required minLength={2} maxLength={160} value={workspace} onChange={e=>setWorkspace(e.target.value)}/></label><button className="primary" disabled={busy}>Create workspace</button></form></section>
      <section className="panel"><h2>Audit history</h2><p>Most recent 50 recorded actions in this workspace.</p>{events.length?events.map(event=><div className="item-row" key={String(event.id)}><div><strong>{String(event.action)}</strong><p>{String(event.resource_type)} · {new Date(String(event.created_at)).toLocaleString()}</p></div></div>):<p>No audit events to display.</p>}
        <button className="outline" disabled={busy} onClick={()=>void action(async()=>{const data=await call("/workspace/export");const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:"application/json"}));const anchor=document.createElement("a");anchor.href=url;anchor.download="revenueos-workspace.json";anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);return "Workspace export downloaded. Store it securely.";})}><Download size={16}/> Export workspace data</button>
      </section>
    </>}
  </div>;
}
