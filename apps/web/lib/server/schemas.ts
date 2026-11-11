import { z } from "zod";

const text = (min:number,max:number) => z.string().trim().min(min).max(max);
const email = z.email().max(254).nullable().optional();
const money = z.number().finite().min(0).max(1_000_000_000);
const id = z.uuid().nullable().optional();
const date = z.iso.datetime({offset:true}).nullable().optional();
const metrics = z.object({seo:z.int().min(0).max(100).nullable().optional(),reviews:z.int().min(0).max(100).nullable().optional(),website:z.int().min(0).max(100).nullable().optional(),social:z.int().min(0).max(100).nullable().optional(),market:z.int().min(0).max(100).nullable().optional()}).strict();
const lead = z.object({business_name:text(2,180),industry:text(1,100).default("other"),website:z.url().max(1024).refine(v=>/^https?:\/\//.test(v),"HTTP or HTTPS URL required").nullable().optional(),email,phone:text(0,48).nullable().optional(),location:text(0,200).nullable().optional(),source:text(0,80).default("manual"),external_id:text(0,180).nullable().optional(),metrics:metrics.default({}),opted_out:z.boolean().default(false),lawful_basis:z.enum(["consent","legitimate_interest","contract"]).nullable().optional(),lawful_basis_note:text(0,1000).nullable().optional()}).strict();
export const workspace = z.object({name:text(2,160),industry:text(0,80).default("services")}).strict();
export const member = z.object({subject:z.uuid(),email:z.email().max(254),role:z.enum(["viewer","operator","manager","admin"])}).strict();
export const draft = z.object({lead_id:z.uuid(),subject:text(3,200),body:text(10,15000)}).strict();
export const decision = z.object({decision:z.enum(["approved","rejected"]),review_hash:z.string().regex(/^[0-9a-f]{64}$/).optional(),reason:text(0,240).optional()}).strict();
export const chat = z.object({message:text(2,5000),role:z.enum(["revenue","sales","research","marketing","operations","engineering"]).default("revenue"),use_ai:z.boolean().default(false)}).strict();
export const media = z.object({kind:z.enum(["image","video"]),title:text(2,160),subtitle:text(0,240).default("")}).strict();
const client=z.object({name:text(2,180),email,lead_id:id,monthly_revenue:money.default(0),renewal_date:date}).strict();
const opportunity=z.object({name:text(2,180),lead_id:id,value:money,probability:z.int().min(0).max(100).default(0),expected_close:date}).strict();
const task=z.object({title:text(3,240),description:text(0,8000).default(""),due_at:date,lead_id:id,assigned_subject:text(0,180).nullable().optional()}).strict();
const campaign=z.object({name:text(2,180),channel:z.enum(["email","social","seo","ads","other"]),objective:text(3,3000),content:z.record(z.string(),z.unknown()).default({})}).strict();
const proposal=z.object({title:text(3,180),lead_id:id,content:text(10,30000),amount:money.nullable().optional()}).strict();
const website=z.object({company:text(2,180),industry:z.enum(["cleaning","hvac","roofing","plumbing","electrical","landscaping","medical","dental","law","real_estate","other"]),tagline:text(3,240),contact_email:z.email().max(254),city:text(2,120),services:z.array(text(2,90)).min(1).max(12)}).strict();
export const createSchemas:Record<string,z.ZodType>={leads:lead,clients:client,opportunities:opportunity,tasks:task,campaigns:campaign,proposals:proposal,websites:website};
// partial() on fields with defaults must not populate missing PATCH fields.
const patchLead=lead.omit({source:true,external_id:true}).partial();
export const patchSchemas:Record<string,z.ZodType>={
 leads:patchLead.extend({stage:z.enum(["new","qualified","contacted","proposal_sent","meeting_booked","client","lost"]).optional()}).strict(),
 clients:client.pick({name:true,email:true,monthly_revenue:true}).partial().extend({active:z.boolean().optional()}).strict(),
 opportunities:opportunity.pick({name:true,value:true,probability:true}).partial().extend({stage:z.enum(["open","won","lost"]).optional()}).strict(),
 tasks:z.object({status:z.enum(["open","in_progress","done","cancelled"])}).strict(),
 campaigns:campaign.partial().extend({status:z.enum(["draft","archived"]).optional()}).strict(),
 proposals:proposal.omit({lead_id:true}).partial().extend({status:z.enum(["draft","accepted","declined"]).optional()}).strict(),
};
export const leadImport=z.object({leads:z.array(lead).min(1).max(100)}).strict();
export function parsePatch(table:string,raw:Record<string,unknown>){
 const parsed=patchSchemas[table].parse(raw) as Record<string,unknown>;
 return Object.fromEntries(Object.entries(parsed).filter(([key])=>Object.hasOwn(raw,key)));
}
export function defaults(table:string){
 return table==="leads"?{stage:"new",score:null,grade:"Unscored",score_confidence:0}:table==="clients"?{active:true}:table==="opportunities"?{stage:"open"}:table==="tasks"?{status:"open"}:table==="campaigns"||table==="proposals"?{status:"draft"}:table==="websites"?{status:"generated"}:{};
}
