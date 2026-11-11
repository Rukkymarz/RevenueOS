alter table public.media_jobs add column requested_by text not null;
insert into storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
values('revenueos-artifacts','revenueos-artifacts',false,5242880,array['image/svg+xml','video/mp4']);

create policy revenueos_artifact_read on storage.objects for select to authenticated
using(bucket_id='revenueos-artifacts' and private.has_role(split_part(name,'/',1)));
create policy revenueos_artifact_insert on storage.objects for insert to authenticated
with check(bucket_id='revenueos-artifacts' and private.has_role(split_part(name,'/',1),'operator')
 and split_part(name,'/',2)=private.actor()
 and exists(select 1 from public.media_jobs j where j.business_id=split_part(name,'/',1)
   and j.requested_by=private.actor() and j.status='pending'
   and name=j.business_id||'/'||j.requested_by||'/'||j.id||case when j.kind='video' then '.mp4' else '.svg' end));
-- No overwriting or deletion through the app. Recovery/retention is an owner operation.

create function private.reserve_media(bid text, media_kind text, media_title text, media_subtitle text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare result public.media_jobs; actor_id text:=private.actor();
begin
 if not private.has_role(bid,'operator') then raise exception 'Operator required' using errcode='42501'; end if;
 perform private.rate_limit();
 perform pg_advisory_xact_lock(hashtextextended(bid,0));
 if media_kind not in ('image','video') or length(trim(media_title)) not between 2 and 160 or length(media_subtitle)>240 then raise exception 'Invalid media request' using errcode='23514'; end if;
 if (select count(*) from public.media_jobs where business_id=bid)>=100
  or (select count(*) from public.media_jobs where business_id=bid and created_at>=(date_trunc('day',now() at time zone 'UTC') at time zone 'UTC'))>=20
  or (media_kind='video' and (select count(*) from public.media_jobs where business_id=bid and kind='video' and created_at>=(date_trunc('day',now() at time zone 'UTC') at time zone 'UTC'))>=5) then
  raise exception 'Free media quota reached' using errcode='54000'; end if;
 insert into public.media_jobs(id,business_id,created_at,kind,title,subtitle,status,requested_by)
 values(gen_random_uuid()::text,bid,now(),media_kind,media_title,media_subtitle,'pending',actor_id) returning * into result;
 return to_jsonb(result);
end $$;
create function public.revenueos_reserve_media(bid text,media_kind text,media_title text,media_subtitle text) returns jsonb
language sql security invoker set search_path='' as $$select private.reserve_media(bid,media_kind,media_title,media_subtitle)$$;
grant execute on function private.reserve_media(text,text,text,text) to authenticated;
revoke all on function public.revenueos_reserve_media(text,text,text,text) from public,anon;
grant execute on function public.revenueos_reserve_media(text,text,text,text) to authenticated;

create function private.finish_media(bid text,job_id text,succeeded boolean) returns jsonb
language plpgsql security definer set search_path='' as $$
declare result public.media_jobs; object_name text;
begin
 if not private.has_role(bid,'operator') then raise exception 'Operator required' using errcode='42501'; end if;
 select * into result from public.media_jobs where id=job_id and business_id=bid and requested_by=private.actor() for update;
 if not found then raise exception 'Job not found' using errcode='P0002'; end if;
 if result.status<>'pending' then raise exception 'Job already finalized' using errcode='23505'; end if;
 object_name:=bid||'/'||private.actor()||'/'||job_id||case when result.kind='video' then '.mp4' else '.svg' end;
 if succeeded and not exists(select 1 from storage.objects where bucket_id='revenueos-artifacts' and name=object_name) then raise exception 'Artifact not found' using errcode='23514'; end if;
 update public.media_jobs set status=case when succeeded then 'done' else 'failed' end,
  output_file=case when succeeded then object_name else null end,error=case when succeeded then null else 'Rendering failed; retry with a new job' end
 where id=job_id returning * into result;
 insert into public.audit_events(id,business_id,created_at,subject,action,resource_type,resource_id,details)
 values(gen_random_uuid()::text,bid,now(),private.actor(),'media.'||result.status,'media_jobs',job_id,'{}');
 return to_jsonb(result);
end $$;
create function public.revenueos_finish_media(bid text,job_id text,succeeded boolean) returns jsonb
language sql security invoker set search_path='' as $$select private.finish_media(bid,job_id,succeeded)$$;
grant execute on function private.finish_media(text,text,boolean) to authenticated;
revoke all on function public.revenueos_finish_media(text,text,boolean) from public,anon;
grant execute on function public.revenueos_finish_media(text,text,boolean) to authenticated;
