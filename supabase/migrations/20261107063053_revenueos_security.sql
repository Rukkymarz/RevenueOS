-- Private, narrowly scoped SECURITY DEFINER helpers avoid recursive membership RLS.
-- No service_role key is needed by the web app. All data requests carry the user JWT.
create schema if not exists private;
revoke all on schema private from public, anon;
grant usage on schema private to authenticated;
alter default privileges in schema private revoke execute on functions from public;
create table private.configuration (singleton boolean primary key default true check(singleton), bootstrap_email text not null);
create table private.request_windows (subject text primary key, window_start timestamptz not null, requests integer not null);
create table private.revoked_sessions (session_id uuid primary key, user_id uuid not null, revoked_at timestamptz not null default now());
revoke all on all tables in schema private from public, anon, authenticated;

create function private.actor() returns text language plpgsql stable security definer set search_path = '' as $$
declare actor_id uuid := auth.uid();
begin
  if actor_id is null or coalesce(auth.jwt()->>'aal','aal1') <> 'aal2'
    or not exists(select 1 from auth.users u where u.id=actor_id and u.email_confirmed_at is not null)
    or exists(select 1 from private.revoked_sessions r where r.session_id::text=auth.jwt()->>'session_id')
    or not exists(select 1 from auth.sessions s where s.id::text=auth.jwt()->>'session_id' and s.user_id=actor_id
                  and (s.not_after is null or s.not_after > now())) then
    raise exception 'Verified sign-in and MFA required' using errcode='42501';
  end if;
  return actor_id::text;
end $$;
create function private.has_role(bid text, minimum text default 'viewer') returns boolean
language sql stable security definer set search_path = '' as $$
 select exists(select 1 from public.memberships m where m.business_id=bid and m.subject=private.actor()
   and array_position(array['viewer','operator','manager','admin'],m.role)
       >= array_position(array['viewer','operator','manager','admin'],minimum))
$$;
grant execute on function private.actor(), private.has_role(text,text) to authenticated;

create function private.revoke_sessions() returns void language plpgsql security definer set search_path='' as $$
declare actor_id text:=private.actor();
begin
 insert into private.revoked_sessions(session_id,user_id)
 select id,user_id from auth.sessions where user_id::text=actor_id
 on conflict(session_id) do nothing;
end $$;
create function public.revenueos_revoke_sessions() returns void language sql security invoker set search_path='' as $$select private.revoke_sessions()$$;
grant execute on function private.revoke_sessions() to authenticated;
revoke all on function public.revenueos_revoke_sessions() from public,anon;
grant execute on function public.revenueos_revoke_sessions() to authenticated;

-- Deny every table first, including future-facing tables not yet exposed by the UI.
do $$ declare t record; begin
 for t in select tablename from pg_tables where schemaname='public' loop
  execute format('alter table public.%I enable row level security', t.tablename);
  execute format('alter table public.%I force row level security', t.tablename);
  execute format('revoke all on public.%I from anon, authenticated', t.tablename);
 end loop;
end $$;

grant select on public.businesses, public.memberships to authenticated;
create policy business_read on public.businesses for select to authenticated using (private.has_role(id));
create policy membership_read on public.memberships for select to authenticated
 using(subject=private.actor() or private.has_role(business_id,'admin'));

do $$ declare t text; begin
 foreach t in array array['leads','clients','opportunities','tasks','campaigns','proposals','websites','media_jobs'] loop
  execute format('grant select, insert on public.%I to authenticated',t);
  execute format('create policy tenant_read on public.%I for select to authenticated using (private.has_role(business_id))',t);
  execute format('create policy tenant_insert on public.%I for insert to authenticated with check (private.has_role(business_id,''operator''))',t);
  execute format('create policy tenant_update on public.%I for update to authenticated using (private.has_role(business_id,''operator'')) with check (private.has_role(business_id,''operator''))',t);
 end loop;
 foreach t in array array['approvals','message_drafts','audit_events','ai_runs'] loop
  execute format('grant select on public.%I to authenticated',t);
  execute format('create policy tenant_read on public.%I for select to authenticated using (private.has_role(business_id,%L))',t,case when t='audit_events' then 'admin' else 'viewer' end);
 end loop;
end $$;
-- Immutable identity, tenant, timestamps, calculated scores and approval fields.
grant update(business_name,industry,website,email,phone,location,stage,metrics,opted_out,lawful_basis,lawful_basis_note) on public.leads to authenticated;
grant update(name,email,monthly_revenue,active) on public.clients to authenticated;
grant update(name,value,probability,stage) on public.opportunities to authenticated;
grant update(status) on public.tasks to authenticated;
grant update(name,channel,objective,content,status) on public.campaigns to authenticated;
grant update(title,content,amount,status) on public.proposals to authenticated;
revoke insert on public.media_jobs from authenticated; -- generated server-side only

create function private.rate_limit() returns void language plpgsql security definer set search_path='' as $$
declare actor_id text := private.actor(); hits integer;
begin
 insert into private.request_windows values(actor_id,date_trunc('minute',now()),1)
 on conflict(subject) do update set
 requests=case when private.request_windows.window_start=date_trunc('minute',now()) then private.request_windows.requests+1 else 1 end,
 window_start=date_trunc('minute',now()) returning requests into hits;
 if hits>120 then raise exception 'Too many requests. Try again shortly.' using errcode='54000'; end if;
end $$;
create function public.revenueos_rate_limit() returns void language sql security invoker set search_path='' as $$ select private.rate_limit() $$;
grant execute on function private.rate_limit() to authenticated;
revoke all on function public.revenueos_rate_limit() from public,anon;
grant execute on function public.revenueos_rate_limit() to authenticated;

create function private.write_guard() returns trigger language plpgsql security definer set search_path='' as $$
declare details jsonb := to_jsonb(new); weighted numeric := 0; weight integer := 0; k text; w integer; n numeric;
begin
 perform private.rate_limit();
 if details->>'lead_id' is not null and not exists(select 1 from public.leads l where l.id=details->>'lead_id' and l.business_id=new.business_id) then
   raise exception 'Lead not found in workspace' using errcode='23503';
 end if;
 if tg_table_name='leads' then
   if jsonb_typeof(new.metrics::jsonb)<>'object' then raise exception 'Invalid metrics' using errcode='23514'; end if;
   for k in select jsonb_object_keys(new.metrics::jsonb) loop
     w := case k when 'seo' then 25 when 'reviews' then 20 when 'website' then 25 when 'social' then 10 when 'market' then 20 end;
     if w is null then raise exception 'Unknown measured dimension' using errcode='23514'; end if;
     if new.metrics::jsonb->k <> 'null'::jsonb then
       if jsonb_typeof(new.metrics::jsonb->k)<>'number' then raise exception 'Invalid metric' using errcode='23514'; end if;
       n := (new.metrics::jsonb->>k)::numeric;
       if n<0 or n>100 or n<>trunc(n) then raise exception 'Invalid metric' using errcode='23514'; end if;
       weighted:=weighted+n*w; weight:=weight+w;
     end if;
   end loop;
   -- Match Python's original round-to-even rule at exact half points.
   new.score := case when weight=0 then null
     when weighted/weight-floor(weighted/weight)=0.5 and mod(floor(weighted/weight),2)=0 then floor(weighted/weight)::int
     else round(weighted/weight)::int end;
   new.score_confidence:=weight;
   new.grade:=case when weight=0 then 'Unscored' when new.score>=85 then 'Platinum' when new.score>=70 then 'Gold' when new.score>=50 then 'Silver' else 'Bronze' end;
 end if;
 return new;
end $$;
create function private.audit_write() returns trigger language plpgsql security definer set search_path='' as $$
begin
 insert into public.audit_events(id,business_id,created_at,subject,action,resource_type,resource_id,details)
 values(gen_random_uuid()::text,new.business_id,now(),private.actor(),tg_table_name||'.'||lower(tg_op),tg_table_name,new.id,'{}');
 return new;
end $$;
do $$ declare t text; begin
 foreach t in array array['leads','clients','opportunities','tasks','campaigns','proposals','websites'] loop
  execute format('create trigger write_guard before insert or update on public.%I for each row execute function private.write_guard()',t);
  execute format('create trigger audit_write after insert or update on public.%I for each row execute function private.audit_write()',t);
 end loop;
end $$;

-- Database validation also applies to direct Data API callers.
alter table public.leads add check(length(trim(business_name)) between 2 and 180), add check(stage in ('new','qualified','contacted','proposal_sent','meeting_booked','client','lost')),
 add check(lawful_basis is null or lawful_basis in ('consent','legitimate_interest','contract'));
alter table public.clients add check(length(trim(name))>=2), add check(monthly_revenue between 0 and 1000000000);
alter table public.opportunities add check(value between 0 and 1000000000), add check(probability between 0 and 100), add check(stage in ('open','won','lost'));
alter table public.tasks add check(length(trim(title))>=3), add check(status in ('open','in_progress','done','cancelled'));
alter table public.campaigns add check(channel in ('email','social','seo','ads','other')), add check(status in ('draft','archived'));
alter table public.proposals add check(length(content) between 10 and 30000), add check(amount is null or amount between 0 and 1000000000), add check(status in ('draft','accepted','declined'));

create function private.create_workspace(workspace_name text, workspace_industry text, initial boolean) returns jsonb
language plpgsql security definer set search_path='' as $$
declare actor_id text:=private.actor(); bid text:=gen_random_uuid()::text; actor_email text;
begin
 perform private.rate_limit();
 perform pg_advisory_xact_lock(7814569);
 select lower(email) into actor_email from auth.users where id::text=actor_id;
 if length(trim(workspace_name)) not between 2 and 160 or length(workspace_industry)>80 then raise exception 'Invalid workspace' using errcode='23514'; end if;
 if initial then
   if exists(select 1 from public.businesses) then raise exception 'Workspace already initialized' using errcode='23505'; end if;
   if not exists(select 1 from private.configuration where bootstrap_email=actor_email) then raise exception 'Only the verified bootstrap administrator may initialize RevenueOS' using errcode='42501'; end if;
 else
   if not exists(select 1 from public.memberships where subject=actor_id and role='admin') then raise exception 'Administrator required' using errcode='42501'; end if;
   if (select count(*) from public.memberships where subject=actor_id and role='admin')>=10 then raise exception 'Workspace limit reached' using errcode='54000'; end if;
 end if;
 insert into public.businesses values(bid,trim(workspace_name),workspace_industry,now());
 insert into public.memberships(id,business_id,subject,email,role) values(gen_random_uuid()::text,bid,actor_id,actor_email,'admin');
 return jsonb_build_object('id',bid,'name',trim(workspace_name));
end $$;
create function public.revenueos_create_workspace(workspace_name text, workspace_industry text, initial boolean) returns jsonb
language sql security invoker set search_path='' as $$ select private.create_workspace(workspace_name,workspace_industry,initial) $$;
grant execute on function private.create_workspace(text,text,boolean) to authenticated;
revoke all on function public.revenueos_create_workspace(text,text,boolean) from public,anon;
grant execute on function public.revenueos_create_workspace(text,text,boolean) to authenticated;

create function private.add_member(bid text, user_subject text, user_email text, member_role text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare result public.memberships;
begin
 if not private.has_role(bid,'admin') then raise exception 'Administrator required' using errcode='42501'; end if;
 perform private.rate_limit();
 if not exists(select 1 from auth.users where id::text=user_subject and lower(email)=lower(user_email) and email_confirmed_at is not null) then
  raise exception 'Verified identity and matching email required' using errcode='23514'; end if;
 insert into public.memberships(id,business_id,subject,email,role) values(gen_random_uuid()::text,bid,user_subject,lower(user_email),member_role) returning * into result;
 insert into public.audit_events(id,business_id,created_at,subject,action,resource_type,resource_id,details)
 values(gen_random_uuid()::text,bid,now(),private.actor(),'member.add','memberships',result.id,'{}');
 return to_jsonb(result);
end $$;
create function public.revenueos_add_member(bid text,user_subject text,user_email text,member_role text) returns jsonb
language sql security invoker set search_path='' as $$ select private.add_member(bid,user_subject,user_email,member_role) $$;
grant execute on function private.add_member(text,text,text,text) to authenticated;
revoke all on function public.revenueos_add_member(text,text,text,text) from public,anon;
grant execute on function public.revenueos_add_member(text,text,text,text) to authenticated;

create function private.draft_email(bid text,lead text,email_subject text,email_body text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare recipient public.leads; draft public.message_drafts; approval public.approvals;
begin
 if not private.has_role(bid,'operator') then raise exception 'Operator required' using errcode='42501'; end if;
 perform private.rate_limit();
 select * into recipient from public.leads where id=lead and business_id=bid;
 if not found or recipient.email is null then raise exception 'Lead with email required' using errcode='23514'; end if;
 if recipient.opted_out then raise exception 'Contact is suppressed' using errcode='42501'; end if;
 if length(email_subject) not between 3 and 200 or length(email_body) not between 10 and 15000 then raise exception 'Invalid draft' using errcode='23514'; end if;
 insert into public.message_drafts(id,business_id,created_at,lead_id,recipient_email,subject,body,status)
 values(gen_random_uuid()::text,bid,now(),lead,recipient.email,email_subject,email_body,'draft') returning * into draft;
 insert into public.approvals(id,business_id,created_at,action,resource_type,resource_id,requested_by,decision)
 values(gen_random_uuid()::text,bid,now(),'send_email','message_drafts',draft.id,private.actor(),'pending') returning * into approval;
 insert into public.audit_events(id,business_id,created_at,subject,action,resource_type,resource_id,details)
 values(gen_random_uuid()::text,bid,now(),private.actor(),'email.draft','message_drafts',draft.id,'{}');
 return jsonb_build_object('draft',to_jsonb(draft),'approval',to_jsonb(approval));
end $$;
create function public.revenueos_draft_email(bid text,lead text,email_subject text,email_body text) returns jsonb
language sql security invoker set search_path='' as $$ select private.draft_email(bid,lead,email_subject,email_body) $$;
grant execute on function private.draft_email(text,text,text,text) to authenticated;
revoke all on function public.revenueos_draft_email(text,text,text,text) from public,anon;
grant execute on function public.revenueos_draft_email(text,text,text,text) to authenticated;

create function private.review_email(bid text, approval_id text, outcome text default null, expected_hash text default null, decision_reason text default null) returns jsonb
language plpgsql security definer set search_path='' as $$
declare a public.approvals; d public.message_drafts; fingerprint text;
begin
 if not private.has_role(bid,'manager') then raise exception 'Manager required' using errcode='42501'; end if;
 select * into a from public.approvals where id=approval_id and business_id=bid for update;
 if not found then raise exception 'Approval not found' using errcode='P0002'; end if;
 select * into d from public.message_drafts where id=a.resource_id and business_id=bid for update;
 if not found then raise exception 'Draft not found' using errcode='P0002'; end if;
 fingerprint:=encode(sha256(convert_to(jsonb_build_object('id',a.id,'recipient_email',d.recipient_email,'subject',d.subject,'body',d.body)::text,'UTF8')),'hex');
 if outcome is not null then
   perform private.rate_limit();
   if a.decision<>'pending' then raise exception 'Approval already decided' using errcode='23505'; end if;
   if outcome not in ('approved','rejected') then raise exception 'Invalid decision' using errcode='23514'; end if;
   if outcome='approved' and expected_hash is distinct from fingerprint then raise exception 'Review content again before approving' using errcode='23505'; end if;
   update public.approvals set decision=outcome,decided_by=private.actor(),decided_at=now(),review_hash=case when outcome='approved' then fingerprint end,reason=left(decision_reason,240) where id=a.id returning * into a;
   insert into public.audit_events(id,business_id,created_at,subject,action,resource_type,resource_id,details)
   values(gen_random_uuid()::text,bid,now(),private.actor(),'approval.'||outcome,'approvals',a.id,'{}');
   return to_jsonb(a);
 end if;
 return jsonb_build_object('id',a.id,'action',a.action,'decision',a.decision,'recipient_email',d.recipient_email,'subject',d.subject,'body',d.body,'review_hash',fingerprint);
end $$;
create function public.revenueos_review_email(bid text,approval_id text,outcome text default null,expected_hash text default null,decision_reason text default null) returns jsonb
language sql security invoker set search_path='' as $$ select private.review_email(bid,approval_id,outcome,expected_hash,decision_reason) $$;
grant execute on function private.review_email(text,text,text,text,text) to authenticated;
revoke all on function public.revenueos_review_email(text,text,text,text,text) from public,anon;
grant execute on function public.revenueos_review_email(text,text,text,text,text) to authenticated;

-- No public/anonymous database access and no anonymous invocation of helpers.
revoke all on all functions in schema private from public,anon;

create function public.revenueos_report(bid text, include_dashboard boolean default false) returns jsonb
language plpgsql security invoker set search_path='' as $$
declare total bigint; stages jsonb; active_count bigint; revenue numeric; pipeline numeric; done_count bigint; result jsonb;
begin
 if not private.has_role(bid) then raise exception 'Workspace access denied' using errcode='42501'; end if;
 select count(*) into total from public.leads where business_id=bid;
 select coalesce(jsonb_object_agg(stage,n),'{}') into stages from (select stage,count(*) n from public.leads where business_id=bid group by stage) grouped;
 select count(*),coalesce(sum(monthly_revenue),0) into active_count,revenue from public.clients where business_id=bid and active;
 select coalesce(sum(value),0) into pipeline from public.opportunities where business_id=bid and stage='open';
 select count(*) into done_count from public.tasks where business_id=bid and status='done';
 result:=jsonb_build_object('lead_volume',total,'stages',stages,'conversion_rate',case when total=0 then null else round(100.0*coalesce((stages->>'client')::numeric,0)/total,2) end,
  'clients_active',active_count,'mrr',round(revenue,2),'pipeline_value',round(pipeline,2),'tasks_completed',done_count,
  'notes',jsonb_build_array('Revenue is user-entered, not bank verified','Pipeline excludes closed opportunities'));
 if include_dashboard then
   result:=result||jsonb_build_object('due_tasks',(select coalesce(jsonb_agg(to_jsonb(t)),'[]') from (select * from public.tasks where business_id=bid and status not in ('done','cancelled') and due_at<=now() order by due_at limit 10)t),
    'pending_approvals',(select coalesce(jsonb_agg(to_jsonb(a)),'[]') from (select * from public.approvals where business_id=bid and decision='pending' order by created_at desc limit 10)a));
 end if;
 return result;
end $$;
revoke all on function public.revenueos_report(text,boolean) from public,anon;
grant execute on function public.revenueos_report(text,boolean) to authenticated;

create function private.export_workspace(bid text) returns jsonb language plpgsql security definer set search_path='' as $$
declare t text; rows jsonb; records jsonb:='{}';
begin
 if not private.has_role(bid,'admin') then raise exception 'Administrator required' using errcode='42501'; end if;
 perform private.rate_limit();
 foreach t in array array['leads','clients','opportunities','tasks','campaigns','proposals','websites','media_jobs','approvals','message_drafts'] loop
   execute format('select coalesce(jsonb_agg(to_jsonb(r)),''[]'') from (select * from public.%I where business_id=$1 order by id limit 10001)r',t) into rows using bid;
   if jsonb_array_length(rows)>10000 then raise exception 'Workspace exceeds interactive export size' using errcode='54000'; end if;
   records:=records||jsonb_build_object(t,rows);
 end loop;
 insert into public.audit_events(id,business_id,created_at,subject,action,resource_type,resource_id,details)
 values(gen_random_uuid()::text,bid,now(),private.actor(),'workspace.export','businesses',bid,'{}');
 return jsonb_build_object('business_id',bid,'exported_at',now(),'schema_version',1,'records',records);
end $$;
create function public.revenueos_export(bid text) returns jsonb language sql security invoker set search_path='' as $$select private.export_workspace(bid)$$;
grant execute on function private.export_workspace(text) to authenticated;
revoke all on function public.revenueos_export(text) from public,anon;
grant execute on function public.revenueos_export(text) to authenticated;

create function public.revenueos_import_leads(bid text, records jsonb) returns jsonb
language plpgsql security invoker set search_path='' as $$
declare item jsonb; imported integer:=0; changed integer; skipped integer:=0;
begin
 if not private.has_role(bid,'operator') then raise exception 'Operator required' using errcode='42501'; end if;
 if jsonb_typeof(records)<>'array' or jsonb_array_length(records) not between 1 and 100 then raise exception 'Import requires 1..100 leads' using errcode='23514'; end if;
 for item in select value from jsonb_array_elements(records) loop
  insert into public.leads(business_id,business_name,industry,website,email,phone,location,source,external_id,metrics,opted_out,lawful_basis,lawful_basis_note,stage,score,grade,score_confidence)
  values(bid,item->>'business_name',coalesce(item->>'industry','other'),item->>'website',item->>'email',item->>'phone',item->>'location',coalesce(item->>'source','manual'),item->>'external_id',coalesce(item->'metrics','{}'),coalesce((item->>'opted_out')::boolean,false),item->>'lawful_basis',item->>'lawful_basis_note','new',null,'Unscored',0)
  on conflict(business_id,source,external_id) do nothing;
  get diagnostics changed=row_count;
  imported:=imported+changed;skipped:=skipped+1-changed;
 end loop;
 return jsonb_build_object('imported',imported,'skipped',skipped);
end $$;
revoke all on function public.revenueos_import_leads(text,jsonb) from public,anon;
grant execute on function public.revenueos_import_leads(text,jsonb) to authenticated;

create function private.can_initialize() returns boolean language plpgsql stable security definer set search_path='' as $$
declare actor_id text:=private.actor();
begin
 return not exists(select 1 from public.businesses) and exists(
  select 1 from private.configuration c join auth.users u on lower(u.email)=c.bootstrap_email where u.id::text=actor_id);
end $$;
create function public.revenueos_can_initialize() returns boolean language sql security invoker set search_path='' as $$select private.can_initialize()$$;
grant execute on function private.can_initialize() to authenticated;
revoke all on function public.revenueos_can_initialize() from public,anon;
grant execute on function public.revenueos_can_initialize() to authenticated;
