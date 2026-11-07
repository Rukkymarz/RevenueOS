import ffmpeg from "ffmpeg-static";
import { execFile } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { promisify } from "node:util";
import { svgArtwork } from "./exports";

const execute=promisify(execFile);
const filterPath=(path:string)=>path.replaceAll("\\","/").replaceAll(":","\\:").replaceAll("'","\\'");
export async function renderMedia(kind:"image"|"video",title:string,subtitle:string){
 if(kind==="image")return {bytes:svgArtwork(title,subtitle),mime:"image/svg+xml",extension:"svg"};
 if(!ffmpeg)throw new Error("Video renderer unavailable");
 const directory=await mkdtemp(join(tmpdir(),"revenueos-video-"));
 try{
  await writeFile(join(directory,"title.txt"),title,{mode:0o600});await writeFile(join(directory,"subtitle.txt"),subtitle,{mode:0o600});
  const font=filterPath(join(process.cwd(),"assets/fonts/NotoSans.ttf"));
  const titlePath=filterPath(join(directory,"title.txt"));const subtitlePath=filterPath(join(directory,"subtitle.txt"));
  const filters=`drawbox=x=50:y=75:w=80:h=6:color=0x00e5ff:t=fill,drawtext=fontfile='${font}':textfile='${titlePath}':expansion=none:fontsize=32:fontcolor=white:x=50:y=200,drawtext=fontfile='${font}':textfile='${subtitlePath}':expansion=none:fontsize=20:fontcolor=0xb7c8df:x=50:y=280,fade=t=in:st=0:d=0.4,fade=t=out:st=3.6:d=0.4`;
  await execute(ffmpeg,["-nostdin","-hide_banner","-loglevel","error","-f","lavfi","-i","color=c=0x080b12:s=960x540:r=24:d=4","-vf",filters,"-c:v","libx264","-threads","1","-preset","ultrafast","-pix_fmt","yuv420p","-movflags","+faststart","-y",join(directory,"video.mp4")],{timeout:30000,maxBuffer:262144,windowsHide:true});
  return {bytes:new Uint8Array(await readFile(join(directory,"video.mp4"))),mime:"video/mp4",extension:"mp4"};
 }finally{await rm(directory,{recursive:true,force:true});}
}
