import { test } from "node:test";
import assert from "node:assert/strict";
import { PDFDocument } from "pdf-lib";
import { unzipSync, strFromU8 } from "fflate";
import { parsePatch, createSchemas, leadImport } from "../lib/server/schemas";
import { ApiError, readBody } from "../lib/server/database";
import { handleApi } from "../lib/server/api";
import { proposalExport, svgArtwork, websiteExport } from "../lib/server/exports";
import { renderMedia } from "../lib/server/media";

test("PATCH does not reset omitted fields to creation defaults",()=>{
 assert.deepEqual(parsePatch("leads",{stage:"qualified"}),{stage:"qualified"});
 assert.deepEqual(parsePatch("opportunities",{stage:"won"}),{stage:"won"});
 assert.throws(()=>parsePatch("leads",{metrics:null}));
 assert.throws(()=>parsePatch("clients",{monthly_revenue:null}));
 assert.throws(()=>parsePatch("leads",{business_id:"different-tenant"}));
});
test("measured dimensions reject invented scores and coercion",()=>{
 for(const metrics of [{seo:true},{seo:101},{seo:1.5},{unknown:10}])assert.throws(()=>createSchemas.leads.parse({business_name:"Lead",metrics}));
 const result=createSchemas.leads.parse({business_name:"Lead",metrics:{seo:35,website:null}}) as Record<string,unknown>;
 assert.deepEqual(result.metrics,{seo:35,website:null});
 assert.throws(()=>leadImport.parse({leads:Array.from({length:101},()=>({business_name:"Lead"}))}));
});
test("streamed JSON cannot bypass the body cap by omitting content-length",async()=>{
 const body=new ReadableStream({start(controller){controller.enqueue(new Uint8Array(262145));controller.close();}});
 const request=new Request("https://local.test/api",{method:"POST",headers:{"content-type":"application/json"},body,duplex:"half"} as RequestInit);
 await assert.rejects(readBody(request),(error:unknown)=>error instanceof ApiError&&error.status===413);
});
test("invalid content types and scalar JSON are rejected",async()=>{
 await assert.rejects(readBody(new Request("https://local.test",{method:"POST",body:"{}"})),(error:unknown)=>error instanceof ApiError&&error.status===415);
 await assert.rejects(readBody(new Request("https://local.test",{method:"POST",headers:{"content-type":"application/json"},body:"[]"})),(error:unknown)=>error instanceof ApiError&&error.status===400);
});
test("API fails closed without a user token and never caches private responses",async()=>{
 const previous={provider:process.env.NEXT_PUBLIC_AUTH_PROVIDER,url:process.env.NEXT_PUBLIC_SUPABASE_URL,key:process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY};
 try{
  process.env.NEXT_PUBLIC_AUTH_PROVIDER="supabase";process.env.NEXT_PUBLIC_SUPABASE_URL="https://isolated-test.supabase.co";process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY="sb_publishable_test";
  const response=await handleApi(new Request("https://local.test/api/v1/leads"));
  assert.equal(response.status,401);assert.equal(response.headers.get("cache-control"),"no-store");
 }finally{for(const [key,value] of Object.entries({NEXT_PUBLIC_AUTH_PROVIDER:previous.provider,NEXT_PUBLIC_SUPABASE_URL:previous.url,NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY:previous.key})){if(value===undefined)delete process.env[key];else process.env[key]=value;}}
});
test("PDF and DOCX are real readable documents, including Unicode input",async()=>{
 const row={title:"Proposal – Café",content:"A real scope with an explicit price.\n".repeat(100),amount:123.45};
 const pdf=await proposalExport(row,"pdf");const parsed=await PDFDocument.load(pdf.bytes);assert.ok(parsed.getPageCount()>1);
 const docx=await proposalExport(row,"docx");const files=unzipSync(docx.bytes);assert.match(strFromU8(files["word/document.xml"]),/Café/);
});
test("website export keeps supplied text as data, with no HTML injection",()=>{
 const marker='</script><img src=x onerror="alert(1)">';
 const zip=unzipSync(websiteExport({company:marker,tagline:"Example scope",city:"Example city",contact_email:"test@example.org",services:["Service"]}));
 const source=strFromU8(zip["app/page.tsx"]);assert.ok(source.includes("{profile.company}"));assert.ok(!source.includes("dangerouslySetInnerHTML"));assert.ok(zip["package.json"]);
});
test("SVG artwork escapes markup and FFmpeg creates an actual MP4",async()=>{
 assert.ok(strFromU8(svgArtwork("<script>","&")).includes("&lt;script&gt;"));
 const video=await renderMedia("video","Template % title","A real four-second clip");
 assert.equal(video.mime,"video/mp4");assert.equal(Buffer.from(video.bytes.subarray(4,8)).toString(),"ftyp");assert.ok(video.bytes.length>1000);
});
