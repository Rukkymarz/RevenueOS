import { PDFDocument, rgb } from "pdf-lib";
import fontkit from "@pdf-lib/fontkit";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { Document, Packer, Paragraph, HeadingLevel } from "docx";
import { strToU8, zipSync } from "fflate";

type Row=Record<string,unknown>;
export async function proposalExport(row:Row,format:string){
 if(format==="docx"){
  const doc=new Document({sections:[{children:[new Paragraph({text:String(row.title),heading:HeadingLevel.TITLE}),...String(row.content).split(/\r?\n/).map(text=>new Paragraph({text})),new Paragraph({text:row.amount==null?"Amount: not specified":`Amount: $${Number(row.amount).toFixed(2)}`})]}]});
  return {bytes:new Uint8Array(await Packer.toBuffer(doc)),type:"application/vnd.openxmlformats-officedocument.wordprocessingml.document",extension:"docx"};
 }
 if(format!=="pdf")throw new Error("Choose PDF or DOCX");
 const pdf=await PDFDocument.create();pdf.registerFontkit(fontkit);
 const font=await pdf.embedFont(await readFile(join(process.cwd(),"assets/fonts/NotoSans.ttf")),{subset:true});
 let page=pdf.addPage();let y=page.getHeight()-55;
 const line=(text:string,size=11)=>{if(y<55){page=pdf.addPage();y=page.getHeight()-55;}page.drawText(text,{x:50,y,size,font,color:rgb(.08,.1,.16)});y-=size+7;};
 // Standard PDF font only supports WinAnsi; replace unsupported glyphs explicitly.
 const safe=(text:string)=>Array.from(text).map(c=>{try{font.encodeText(c);return c;}catch{return "?";}}).join("");
 for(const raw of [String(row.title),"",...String(row.content).split(/\r?\n/),"",row.amount==null?"Amount: not specified":`Amount: $${Number(row.amount).toFixed(2)}`]){
  let current="";
  for(const word of safe(raw).split(/\s+/)){
   for(let rest=word;rest.length;){const chunk=rest.slice(0,65);rest=rest.slice(65);if(font.widthOfTextAtSize(current+" "+chunk,11)>page.getWidth()-100){line(current);current=chunk;}else current+=(current?" ":"")+chunk;}
  }
  line(current);
 }
 return {bytes:await pdf.save(),type:"application/pdf",extension:"pdf"};
}
export function websiteExport(row:Row){
 const profile={company:row.company,tagline:row.tagline,city:row.city,email:row.contact_email,services:row.services};
 const source=`const profile = ${JSON.stringify(profile,null,2)};\nexport default function Home(){return <main><header><h1>{profile.company}</h1><p>{profile.tagline}</p><p>Serving {profile.city}</p></header><section><h2>Our services</h2><ul>{profile.services.map((service:string)=><li key={service}>{service}</li>)}</ul></section><section><h2>Contact us</h2><a href={"mailto:"+profile.email}>{profile.email}</a></section></main>;}\n`;
 const files={
  "package.json":JSON.stringify({name:"revenueos-website",version:"1.0.0",private:true,scripts:{dev:"next dev",build:"next build",start:"next start"},dependencies:{next:"16.4.5",react:"19.2.0","react-dom":"19.2.0"},devDependencies:{typescript:"5.9.3","@types/react":"19.2.0","@types/node":"22.19.0"}},null,2),
  "app/page.tsx":source,
  "app/layout.tsx":'import "./globals.css"; import type {ReactNode} from "react"; export default function Layout({children}:{children:ReactNode}){return <html lang="en"><body>{children}</body></html>;}',
  "app/globals.css":"body{margin:0;background:#080b12;color:#eef4ff;font:18px/1.6 system-ui}main{max-width:1000px;margin:auto;padding:48px 24px}header,section{padding:32px 0}h1{font-size:clamp(2.2rem,7vw,4rem);line-height:1.1}a{color:#00e5ff}li{margin:16px 0}",
  "README.md":"# Editable website source\nReview content, install dependencies with npm install, then npm run build. Deployment requires a separate hosting account. No site was automatically published.\n",
  ".gitignore":"node_modules/\n.next/\n.env*\n",
 };
 return zipSync(Object.fromEntries(Object.entries(files).map(([name,data])=>[name,strToU8(data)])));
}
const escapeXml=(value:unknown)=>String(value).replace(/[<>&"']/g,c=>({"<":"&lt;",">":"&gt;","&":"&amp;",'"':"&quot;","'":"&apos;"}[c]!));
export function svgArtwork(title:unknown,subtitle:unknown){
 return strToU8(`<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="628" viewBox="0 0 1200 628"><rect width="1200" height="628" fill="#080b12"/><circle cx="1020" cy="110" r="290" fill="#7c3aed" opacity=".35"/><rect x="70" y="100" width="90" height="8" fill="#00e5ff"/><text x="70" y="280" font-family="sans-serif" font-size="48" fill="white">${escapeXml(title)}</text><text x="70" y="370" font-family="sans-serif" font-size="28" fill="#b7c8df">${escapeXml(subtitle)}</text><text x="70" y="540" font-family="sans-serif" font-size="20" fill="#10b981">REVENUEOS · TEMPLATE ARTWORK</text></svg>`);
}
