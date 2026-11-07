import ffmpeg from "ffmpeg-static";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import { svgArtwork } from "./exports";
import fontkit from "@pdf-lib/fontkit";
import sharp from "sharp";

const execute=promisify(execFile);
export async function renderMedia(kind:"image"|"video",title:string,subtitle:string){
 if(kind==="image")return {bytes:svgArtwork(title,subtitle),mime:"image/svg+xml",extension:"svg"};
 if(!ffmpeg)throw new Error("Video renderer unavailable");
 const directory=await mkdtemp(join(tmpdir(),"revenueos-video-"));
 try{
  const font=fontkit.create(await readFile(join(process.cwd(),"assets/fonts/NotoSans.ttf")));
  // Outline glyphs ourselves: no dependency on host fonts or FFmpeg's drawtext filter.
  const outline=(text:string,y:number,size:number,color:string)=>{
   const run=font.layout(text);const width=run.positions.reduce((sum,p)=>sum+p.xAdvance,0);
   const scale=Math.min(size/font.unitsPerEm,860/Math.max(1,width));let x=0;
   return `<g transform="translate(50 ${y}) scale(${scale} ${-scale})" fill="${color}">${run.glyphs.map((glyph,i)=>{const p=run.positions[i];const path=`<path transform="translate(${x+p.xOffset} ${p.yOffset})" d="${glyph.path.toSVG()}"/>`;x+=p.xAdvance;return path;}).join("")}</g>`;
  };
  const artwork=`<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540"><rect width="960" height="540" fill="#080b12"/><circle cx="900" cy="50" r="230" fill="#7c3aed" opacity=".3"/><rect x="50" y="75" width="80" height="6" fill="#00e5ff"/>${outline(title,235,32,"white")}${outline(subtitle,295,20,"#b7c8df")}${outline("REVENUEOS · TEMPLATE VIDEO",470,14,"#10b981")}</svg>`;
  await writeFile(join(directory,"cover.png"),await sharp(Buffer.from(artwork)).png().toBuffer(),{mode:0o600});
  await execute(ffmpeg,["-nostdin","-hide_banner","-loglevel","error","-loop","1","-i",join(directory,"cover.png"),"-t","4","-r","24","-vf","fade=t=in:st=0:d=0.4,fade=t=out:st=3.6:d=0.4","-c:v","libx264","-threads","1","-preset","ultrafast","-pix_fmt","yuv420p","-movflags","+faststart","-y",join(directory,"video.mp4")],{timeout:30000,maxBuffer:262144,windowsHide:true});
  return {bytes:new Uint8Array(await readFile(join(directory,"video.mp4"))),mime:"video/mp4",extension:"mp4"};
 }finally{await rm(directory,{recursive:true,force:true});}
}
