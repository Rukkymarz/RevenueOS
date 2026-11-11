-- Preserves the existing RevenueOS models; apply only to its isolated project.

CREATE TABLE businesses (
	id VARCHAR(36) NOT NULL, 
	name VARCHAR(160) NOT NULL, 
	industry VARCHAR(80) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)

;
ALTER TABLE public.businesses ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;
ALTER TABLE public.businesses ALTER COLUMN created_at SET DEFAULT now();

CREATE TABLE agent_memory (
	role VARCHAR(40) NOT NULL, 
	key VARCHAR(150) NOT NULL, 
	value TEXT NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	business_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (business_id, role, key), 
	FOREIGN KEY(business_id) REFERENCES businesses (id)
)

;
CREATE INDEX ix_agent_memory_business_id ON agent_memory (business_id);
ALTER TABLE public.agent_memory ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;
ALTER TABLE public.agent_memory ALTER COLUMN created_at SET DEFAULT now();

CREATE TABLE ai_runs (
	subject VARCHAR(180) NOT NULL, 
	role VARCHAR(40) NOT NULL, 
	provider VARCHAR(40) NOT NULL, 
	model VARCHAR(100) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	input_tokens INTEGER, 
	output_tokens INTEGER, 
	error VARCHAR(200), 
	id VARCHAR(36) NOT NULL, 
	business_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(business_id) REFERENCES businesses (id)
)

;
CREATE INDEX ix_ai_runs_business_id ON ai_runs (business_id);
ALTER TABLE public.ai_runs ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;
ALTER TABLE public.ai_runs ALTER COLUMN created_at SET DEFAULT now();

CREATE TABLE approvals (
	action VARCHAR(80) NOT NULL, 
	resource_type VARCHAR(70) NOT NULL, 
	resource_id VARCHAR(36) NOT NULL, 
	requested_by VARCHAR(180) NOT NULL, 
	decided_by VARCHAR(180), 
	decision VARCHAR(24) NOT NULL, 
	decided_at TIMESTAMP WITH TIME ZONE, 
	reason VARCHAR(240), 
	review_hash VARCHAR(64), 
	id VARCHAR(36) NOT NULL, 
	business_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (business_id, action, resource_type, resource_id), 
	FOREIGN KEY(business_id) REFERENCES businesses (id)
)

;
CREATE INDEX ix_approvals_business_id ON approvals (business_id);
ALTER TABLE public.approvals ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;
ALTER TABLE public.approvals ALTER COLUMN created_at SET DEFAULT now();

CREATE TABLE audit_events (
	subject VARCHAR(180) NOT NULL, 
	action VARCHAR(100) NOT NULL, 
	resource_type VARCHAR(80) NOT NULL, 
	resource_id VARCHAR(36) NOT NULL, 
	details JSON NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	business_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(business_id) REFERENCES businesses (id)
)

;
CREATE INDEX ix_audit_events_business_id ON audit_events (business_id);
ALTER TABLE public.audit_events ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;
ALTER TABLE public.audit_events ALTER COLUMN created_at SET DEFAULT now();

CREATE TABLE campaigns (
	name VARCHAR(180) NOT NULL, 
	channel VARCHAR(50) NOT NULL, 
	objective TEXT NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	content JSON NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	business_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(business_id) REFERENCES businesses (id)
)

;
CREATE INDEX ix_campaigns_business_id ON campaigns (business_id);
ALTER TABLE public.campaigns ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;
ALTER TABLE public.campaigns ALTER COLUMN created_at SET DEFAULT now();

CREATE TABLE integration_events (
	source VARCHAR(50) NOT NULL, 
	external_id VARCHAR(160) NOT NULL, 
	resource_id VARCHAR(36), 
	id VARCHAR(36) NOT NULL, 
	business_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (business_id, source, external_id), 
	FOREIGN KEY(business_id) REFERENCES businesses (id)
)

;
CREATE INDEX ix_integration_events_business_id ON integration_events (business_id);
ALTER TABLE public.integration_events ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;
ALTER TABLE public.integration_events ALTER COLUMN created_at SET DEFAULT now();

CREATE TABLE knowledge (
	title VARCHAR(200) NOT NULL, 
	content TEXT NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	business_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(business_id) REFERENCES businesses (id)
)

;
CREATE INDEX ix_knowledge_business_id ON knowledge (business_id);
ALTER TABLE public.knowledge ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;
ALTER TABLE public.knowledge ALTER COLUMN created_at SET DEFAULT now();

CREATE TABLE leads (
	business_name VARCHAR(180) NOT NULL, 
	industry VARCHAR(100) NOT NULL, 
	website VARCHAR(1024), 
	email VARCHAR(254), 
	phone VARCHAR(48), 
	location VARCHAR(200), 
	stage VARCHAR(32) NOT NULL, 
	source VARCHAR(80) NOT NULL, 
	external_id VARCHAR(180), 
	metrics JSON NOT NULL, 
	score INTEGER, 
	grade VARCHAR(12) NOT NULL, 
	score_confidence INTEGER NOT NULL, 
	last_contact TIMESTAMP WITH TIME ZONE, 
	opted_out BOOLEAN NOT NULL, 
	lawful_basis VARCHAR(50), 
	lawful_basis_note TEXT, 
	id VARCHAR(36) NOT NULL, 
	business_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_lead_external UNIQUE (business_id, source, external_id), 
	FOREIGN KEY(business_id) REFERENCES businesses (id)
)

;
CREATE INDEX ix_leads_business_id ON leads (business_id);
CREATE INDEX ix_lead_business_stage ON leads (business_id, stage);
ALTER TABLE public.leads ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;
ALTER TABLE public.leads ALTER COLUMN created_at SET DEFAULT now();

CREATE TABLE media_jobs (
	kind VARCHAR(24) NOT NULL, 
	title VARCHAR(180) NOT NULL, 
	subtitle VARCHAR(240) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	output_file VARCHAR(200), 
	error VARCHAR(255), 
	id VARCHAR(36) NOT NULL, 
	business_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(business_id) REFERENCES businesses (id)
)

;
CREATE INDEX ix_media_jobs_business_id ON media_jobs (business_id);
ALTER TABLE public.media_jobs ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;
ALTER TABLE public.media_jobs ALTER COLUMN created_at SET DEFAULT now();

CREATE TABLE memberships (
	id VARCHAR(36) NOT NULL, 
	business_id VARCHAR(36) NOT NULL, 
	subject VARCHAR(180) NOT NULL, 
	email VARCHAR(254) NOT NULL, 
	role VARCHAR(24) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (business_id, subject), 
	CHECK (role IN ('admin','manager','operator','viewer')), 
	FOREIGN KEY(business_id) REFERENCES businesses (id)
)

;
CREATE INDEX ix_memberships_subject ON memberships (subject);
CREATE INDEX ix_memberships_business_id ON memberships (business_id);
ALTER TABLE public.memberships ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;

CREATE TABLE websites (
	company VARCHAR(180) NOT NULL, 
	industry VARCHAR(100) NOT NULL, 
	tagline VARCHAR(240) NOT NULL, 
	contact_email VARCHAR(254) NOT NULL, 
	city VARCHAR(120) NOT NULL, 
	services JSON NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	business_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(business_id) REFERENCES businesses (id)
)

;
CREATE INDEX ix_websites_business_id ON websites (business_id);
ALTER TABLE public.websites ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;
ALTER TABLE public.websites ALTER COLUMN created_at SET DEFAULT now();

CREATE TABLE workflows (
	name VARCHAR(150) NOT NULL, 
	spec JSON NOT NULL, 
	active BOOLEAN NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	business_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(business_id) REFERENCES businesses (id)
)

;
CREATE INDEX ix_workflows_business_id ON workflows (business_id);
ALTER TABLE public.workflows ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;
ALTER TABLE public.workflows ALTER COLUMN created_at SET DEFAULT now();

CREATE TABLE clients (
	name VARCHAR(180) NOT NULL, 
	lead_id VARCHAR(36), 
	email VARCHAR(254), 
	active BOOLEAN NOT NULL, 
	monthly_revenue NUMERIC(12, 2) NOT NULL, 
	renewal_date TIMESTAMP WITH TIME ZONE, 
	id VARCHAR(36) NOT NULL, 
	business_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(lead_id) REFERENCES leads (id), 
	FOREIGN KEY(business_id) REFERENCES businesses (id)
)

;
CREATE INDEX ix_clients_business_id ON clients (business_id);
ALTER TABLE public.clients ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;
ALTER TABLE public.clients ALTER COLUMN created_at SET DEFAULT now();

CREATE TABLE contacts (
	lead_id VARCHAR(36), 
	name VARCHAR(160) NOT NULL, 
	email VARCHAR(254), 
	phone VARCHAR(48), 
	opted_out BOOLEAN NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	business_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(lead_id) REFERENCES leads (id), 
	FOREIGN KEY(business_id) REFERENCES businesses (id)
)

;
CREATE INDEX ix_contacts_business_id ON contacts (business_id);
ALTER TABLE public.contacts ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;
ALTER TABLE public.contacts ALTER COLUMN created_at SET DEFAULT now();

CREATE TABLE message_drafts (
	lead_id VARCHAR(36) NOT NULL, 
	recipient_email VARCHAR(254) NOT NULL, 
	subject VARCHAR(200) NOT NULL, 
	body TEXT NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	provider_id VARCHAR(160), 
	sent_at TIMESTAMP WITH TIME ZONE, 
	id VARCHAR(36) NOT NULL, 
	business_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(lead_id) REFERENCES leads (id), 
	FOREIGN KEY(business_id) REFERENCES businesses (id)
)

;
CREATE INDEX ix_message_drafts_business_id ON message_drafts (business_id);
ALTER TABLE public.message_drafts ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;
ALTER TABLE public.message_drafts ALTER COLUMN created_at SET DEFAULT now();

CREATE TABLE opportunities (
	name VARCHAR(180) NOT NULL, 
	lead_id VARCHAR(36), 
	value NUMERIC(12, 2) NOT NULL, 
	probability INTEGER NOT NULL, 
	stage VARCHAR(32) NOT NULL, 
	expected_close TIMESTAMP WITH TIME ZONE, 
	id VARCHAR(36) NOT NULL, 
	business_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(lead_id) REFERENCES leads (id), 
	FOREIGN KEY(business_id) REFERENCES businesses (id)
)

;
CREATE INDEX ix_opportunities_business_id ON opportunities (business_id);
ALTER TABLE public.opportunities ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;
ALTER TABLE public.opportunities ALTER COLUMN created_at SET DEFAULT now();

CREATE TABLE proposals (
	title VARCHAR(180) NOT NULL, 
	lead_id VARCHAR(36), 
	content TEXT NOT NULL, 
	amount NUMERIC(12, 2), 
	status VARCHAR(24) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	business_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(lead_id) REFERENCES leads (id), 
	FOREIGN KEY(business_id) REFERENCES businesses (id)
)

;
CREATE INDEX ix_proposals_business_id ON proposals (business_id);
ALTER TABLE public.proposals ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;
ALTER TABLE public.proposals ALTER COLUMN created_at SET DEFAULT now();

CREATE TABLE tasks (
	title VARCHAR(240) NOT NULL, 
	description TEXT NOT NULL, 
	due_at TIMESTAMP WITH TIME ZONE, 
	status VARCHAR(24) NOT NULL, 
	lead_id VARCHAR(36), 
	assigned_subject VARCHAR(180), 
	id VARCHAR(36) NOT NULL, 
	business_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(lead_id) REFERENCES leads (id), 
	FOREIGN KEY(business_id) REFERENCES businesses (id)
)

;
CREATE INDEX ix_tasks_business_id ON tasks (business_id);
ALTER TABLE public.tasks ALTER COLUMN id SET DEFAULT gen_random_uuid()::text;
ALTER TABLE public.tasks ALTER COLUMN created_at SET DEFAULT now();