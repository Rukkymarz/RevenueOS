import type { SupabaseClient } from "@supabase/supabase-js";
import { z } from "zod";
import { ApiError, authenticate, checked, context, readBody, requireRole } from "./database";
import { chat, createSchemas, decision, defaults, draft, leadImport, media, member, parsePatch, patchSchemas, workspace } from "./schemas";

const tables:Record<string,string>={leads:"leads",clients:"clients",opportunities:"opportunities",tasks:"tasks",campaigns:"campaigns",proposals:"proposals",websites:"websites",media:"media_jobs",approvals:"approvals","outreach/drafts":"message_drafts","audit-events":"audit_events"};
const headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY","Referrer-Policy":"strict-origin-when-cross-origin"};
const json=(value:unknown,status=200)=>Response.json(value,{status,headers});
function binary(bytes:Uint8Array,type:string,name:string){return new Response(Buffer.from(bytes),{headers:{...headers,"Content-Type":type,"Content-Disposition":`attachment; filename="${name}"`}});}
async function rpc(db:SupabaseClient,name:string,parameters:Record<string,unknown>){return checked(await db.rpc(name,parameters));}
async function record(db:SupabaseClient,table:string,bid:string,id:string){const row=checked(await db.from(table).select("*").eq("business_id",bid).eq("id",id).maybeSingle());if(!row)throw new ApiError(404,"Record not found");return row;}

export async function handleApi(request:Request){
 try{
  if(process.env.NEXT_PUBLIC_AUTH_PROVIDER!=="supabase")throw new ApiError(404,"Endpoint unavailable");
  const url=new URL(request.url);const path=url.pathname.replace(/^\/api\/v1\//,"").replace(/\/$/,"");
  const parts=path.split("/");const method=request.method;
  const {db,user}=await authenticate(request);
  if(path==="me"&&method==="GET"){
   const memberships=checked(await db.from("memberships").select("business_id,role,businesses(name)").eq("subject",user.id));
   return json({subject:user.id,email:user.email,can_initialize:await rpc(db,"revenueos_can_initialize",{}),businesses:(memberships||[]).map(m=>({id:m.business_id,role:m.role,name:(m.businesses as unknown as {name:string})?.name}))});
  }
  if(path==="setup"&&method==="POST"){
   const data=workspace.parse(await readBody(request));return json(await rpc(db,"revenueos_create_workspace",{workspace_name:data.name,workspace_industry:data.industry,initial:true}),201);
  }
  const bid=request.headers.get("x-business-id")||"";const role=await context(db,bid,user.id);
  if(method!=="GET")requireRole(role,"operator");
  if(path==="businesses"&&method==="POST"){
   requireRole(role,"admin");const data=workspace.parse(await readBody(request));return json(await rpc(db,"revenueos_create_workspace",{workspace_name:data.name,workspace_industry:data.industry,initial:false}),201);
  }
  if(path==="members"){
   requireRole(role,"admin");
   if(method==="GET")return json(checked(await db.from("memberships").select("id,email,role,subject").eq("business_id",bid)));
   if(method==="POST"){const data=member.parse(await readBody(request));return json(await rpc(db,"revenueos_add_member",{bid,user_subject:data.subject,user_email:data.email,member_role:data.role}),201);}
  }
  if((path==="dashboard"||path==="reports/pipeline")&&method==="GET")return json(await rpc(db,"revenueos_report",{bid,include_dashboard:path==="dashboard"}));
  if(path==="workspace/export"&&method==="GET"){requireRole(role,"admin");return json(await rpc(db,"revenueos_export",{bid}));}
  if(path==="ai/usage"&&method==="GET"){requireRole(role,"operator");const today=new Date();today.setUTCHours(0,0,0,0);const result=await db.from("ai_runs").select("id",{head:true,count:"exact"}).eq("business_id",bid).eq("subject",user.id).gte("created_at",today.toISOString());checked(result);return json({enabled:false,runs_today:result.count||0,daily_limit:0,remaining:0,scope:"workspace and user",resets:"00:00 UTC"});}
  if(path==="plugins"&&method==="GET"){
   requireRole(role,"operator");return json([{id:"documents",capabilities:["PDF","DOCX","website source ZIP"],enabled:true},{id:"ai",capabilities:["AI provider not configured"],enabled:false},{id:"email",capabilities:["Drafts and exact-content approvals","Sending not configured"],enabled:false},{id:"media",capabilities:["SVG artwork","4-second template MP4","20 jobs/day; 5 videos/day; 100 stored jobs/workspace"],enabled:true}]);
  }
  if(path==="assistant/chat"&&method==="POST"){
   const data=chat.parse(await readBody(request));if(data.use_ai)throw new ApiError(503,"AI provider is not connected. No paid calls were made.");
   const prompts:[string,RegExp,string][]=[
    ["lead_research",/find leads|prospects|find companies|lead discovery/i,"Open Leads to import verified prospects. Automated discovery needs an authorized data provider."],
    ["proposal",/proposal|quote|pricing/i,"Open Proposals to draft a scope and export PDF or DOCX using your own pricing."],
    ["website",/website|landing page/i,"Open Websites to generate editable Next.js source. Review it before deploying."],
    ["marketing",/ads|campaign|marketing plan|social post/i,"Open Campaigns to prepare a plan. External publishing is not connected."],
    ["followups",/follow.up|today.s tasks/i,"Open Tasks and Approvals for follow-ups and messages awaiting review. Nothing is sent automatically."],
    ["analytics",/revenue|conversion|pipeline|report/i,"Open Reports for recorded pipeline and user-entered revenue. These are not bank-verified figures."],
   ];const selected=prompts.find(p=>p[1].test(data.message));return json({intent:selected?.[0]||"general",role:data.role,message:selected?.[2]||"I can guide you through leads, proposals, websites, tasks, campaigns, approvals and reporting. AI generation is not connected.",requires_approval:true});
  }
  if(path==="ai/drafts"&&method==="POST")throw new ApiError(503,"AI provider is not connected. No paid calls were made.");
  if(path==="outreach/drafts"&&method==="POST"){const data=draft.parse(await readBody(request));return json(await rpc(db,"revenueos_draft_email",{bid,lead:data.lead_id,email_subject:data.subject,email_body:data.body}),201);}
  if(parts[0]==="approvals"&&parts.length===3){
   requireRole(role,"manager");z.uuid().parse(parts[1]);
   if(parts[2]==="preview"&&method==="GET")return json(await rpc(db,"revenueos_review_email",{bid,approval_id:parts[1]}));
   if(parts[2]==="decision"&&method==="POST"){const data=decision.parse(await readBody(request));return json(await rpc(db,"revenueos_review_email",{bid,approval_id:parts[1],outcome:data.decision,expected_hash:data.review_hash||null,decision_reason:data.reason||null}));}
  }
  if(parts[0]==="outreach"&&parts[2]==="send"&&method==="POST"){requireRole(role,"manager");throw new ApiError(503,"Email delivery is not configured. No message was sent.");}
  if(path==="leads/import"&&method==="POST"){const data=leadImport.parse(await readBody(request));return json(await rpc(db,"revenueos_import_leads",{bid,records:data.leads}),201);}
  if(parts[0]==="proposals"&&parts[2]==="export"&&method==="GET"){
   const {proposalExport}=await import("./exports");
   z.uuid().parse(parts[1]);const format=url.searchParams.get("format")||"pdf";if(!["pdf","docx"].includes(format))throw new ApiError(422,"Choose PDF or DOCX");
   const row=await record(db,"proposals",bid,parts[1]);const output=await proposalExport(row,format);return binary(output.bytes,output.type,`proposal-${parts[1]}.${output.extension}`);
  }
  if(parts[0]==="websites"&&parts[2]==="download"&&method==="GET"){const {websiteExport}=await import("./exports");z.uuid().parse(parts[1]);return binary(websiteExport(await record(db,"websites",bid,parts[1])),"application/zip",`website-${parts[1]}.zip`);}
  if(path==="media"&&method==="POST"){
   const {renderMedia}=await import("./media");
   const data=media.parse(await readBody(request));const job=await rpc(db,"revenueos_reserve_media",{bid,media_kind:data.kind,media_title:data.title,media_subtitle:data.subtitle});
   try{
    const output=await renderMedia(data.kind,data.title,data.subtitle);
    if(output.bytes.length>5*1024*1024)throw new Error("Artifact exceeds free size limit");
    const name=`${bid}/${user.id}/${job.id}.${output.extension}`;
    checked(await db.storage.from("revenueos-artifacts").upload(name,output.bytes,{contentType:output.mime,upsert:false}));
    return json(await rpc(db,"revenueos_finish_media",{bid,job_id:job.id,succeeded:true}),201);
   }catch{await db.rpc("revenueos_finish_media",{bid,job_id:job.id,succeeded:false});throw new ApiError(503,"Rendering failed. The job is recorded; no completed asset was reported.");}
  }
  if(parts[0]==="media"&&parts[2]==="download"&&method==="GET"){
   z.uuid().parse(parts[1]);const job=await record(db,"media_jobs",bid,parts[1]);if(job.status!=="done"||!job.output_file)throw new ApiError(409,"Artifact is not ready");
   const blob=checked(await db.storage.from("revenueos-artifacts").download(job.output_file));if(!blob)throw new ApiError(404,"Artifact unavailable");
   return binary(new Uint8Array(await blob.arrayBuffer()),job.kind==="video"?"video/mp4":"image/svg+xml",`media-${parts[1]}.${job.kind==="video"?"mp4":"svg"}`);
  }
  if(parts.length===2&&parts[0] in tables&&method==="GET") {z.uuid().parse(parts[1]);return json(await record(db,tables[parts[0]],bid,parts[1]));}
  if(path in tables&&method==="GET"){
   if(path==="audit-events")requireRole(role,"admin");
   const limit=z.coerce.number().int().min(1).max(100).parse(url.searchParams.get("limit")||50);
   const offset=z.coerce.number().int().min(0).max(100000).parse(url.searchParams.get("offset")||0);
   let query=db.from(tables[path]).select("*").eq("business_id",bid).order("created_at",{ascending:false}).order("id").range(offset,offset+limit-1);
   if(path==="leads"){
    const stage=url.searchParams.get("stage");if(stage)query=query.eq("stage",stage);
    const search=z.string().max(180).parse(url.searchParams.get("q")||"");if(search)query=query.ilike("business_name",`%${search.replace(/[\\%_]/g,"\\$&")}%`);
   }
   return json(checked(await query));
  }
  if(path in createSchemas&&method==="POST"){
   const data=createSchemas[path].parse(await readBody(request)) as Record<string,unknown>;
   return json(checked(await db.from(tables[path]).insert({...defaults(path),...data,business_id:bid}).select().single()),201);
  }
  if(parts.length===2&&parts[0] in patchSchemas&&method==="PATCH"){
   z.uuid().parse(parts[1]);const data=parsePatch(parts[0],await readBody(request));if(!Object.keys(data).length)throw new ApiError(422,"No changes supplied");
   return json(checked(await db.from(tables[parts[0]]).update(data).eq("business_id",bid).eq("id",parts[1]).select().single()));
  }
  throw new ApiError(404,"Endpoint unavailable");
 }catch(error){
  if(error instanceof z.ZodError)return json({detail:"Invalid request fields",fields:error.issues.map(i=>({path:i.path.join("."),message:i.message}))},422);
  if(error instanceof ApiError)return json({detail:error.message},error.status);
  // Never echo database diagnostics, JWTs or provider credentials to clients/logs.
  return json({detail:"Request could not be completed. Try again shortly."},503);
 }
}
