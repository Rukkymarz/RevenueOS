import { createClient } from "@supabase/supabase-js";
import type { SupabaseClient } from "@supabase/supabase-js";

export class ApiError extends Error { constructor(public status:number,message:string){super(message);} }
export function checked<T>(result:{data:T;error:{code?:string;message:string}|null}):T {
 if(result.error){
  const code=result.error.code;
  throw new ApiError(code==="42501"?403:code==="23505"?409:code==="P0002"||code==="PGRST116"?404:code==="54000"?429:code?.startsWith("22")||code?.startsWith("23")?422:503,
   code==="42501"?"Access denied. Complete MFA and check your workspace role.":code==="23505"?"Record already exists or changed. Refresh and try again.":code==="P0002"||code==="PGRST116"?"Record not found":code==="54000"?"Request limit reached. Try again shortly.":code?.startsWith("22")||code?.startsWith("23")?"Invalid record or linked workspace record":"Data service temporarily unavailable");
 }
 return result.data;
}
export async function authenticate(request:Request){
 const url=process.env.NEXT_PUBLIC_SUPABASE_URL;
 const key=process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
 if(!url||!key)throw new ApiError(503,"Secure data service is awaiting configuration");
 const token=request.headers.get("authorization")?.match(/^Bearer ([^\s]+)$/)?.[1];
 if(!token||token.length>12000)throw new ApiError(401,"Sign in required");
 // New client per request. Caller JWT is used for every operation: never service_role.
 const db=createClient(url,key,{global:{headers:{Authorization:`Bearer ${token}`}},auth:{persistSession:false,autoRefreshToken:false,detectSessionInUrl:false}});
 const {data,error}=await db.auth.getUser(token);
 if(error||!data.user?.email_confirmed_at)throw new ApiError(401,"Verified sign-in required");
 // getClaims verifies the signature. The DB independently enforces MFA/session existence.
 const claims=await db.auth.getClaims(token);
 if(claims.error||claims.data?.claims.aal!=="aal2")throw new ApiError(403,"Complete authenticator verification");
 checked(await db.rpc("revenueos_rate_limit"));
 return {db,user:data.user};
}
export async function context(db:SupabaseClient,businessId:string|null,userId:string){
 if(!businessId||!/^[0-9a-f-]{36}$/i.test(businessId))throw new ApiError(400,"Select a workspace");
 const result=checked(await db.from("memberships").select("role").eq("business_id",businessId).eq("subject",userId).maybeSingle());
 if(!result)throw new ApiError(403,"Workspace access denied");
 return result.role as string;
}
export function requireRole(role:string,minimum:string){
 const roles=["viewer","operator","manager","admin"];
 if(roles.indexOf(role)<roles.indexOf(minimum))throw new ApiError(403,"Insufficient permissions");
}
export async function readBody(request:Request){
 if(!request.headers.get("content-type")?.startsWith("application/json"))throw new ApiError(415,"JSON body required");
 if(Number(request.headers.get("content-length"))>262144)throw new ApiError(413,"Request too large");
 const reader=request.body?.getReader();if(!reader)throw new ApiError(400,"Request body required");
 let size=0;const chunks:Uint8Array[]=[];
 try{for(;;){const {value,done}=await reader.read();if(done)break;size+=value.length;if(size>262144){await reader.cancel();throw new ApiError(413,"Request too large");}chunks.push(value);}}finally{reader.releaseLock();}
 const data=new Uint8Array(size);let offset=0;for(const chunk of chunks){data.set(chunk,offset);offset+=chunk.length;}
 try{const value=JSON.parse(new TextDecoder().decode(data));if(!value||typeof value!=="object"||Array.isArray(value))throw new Error();return value as Record<string,unknown>;}catch{throw new ApiError(400,"Invalid JSON object");}
}
