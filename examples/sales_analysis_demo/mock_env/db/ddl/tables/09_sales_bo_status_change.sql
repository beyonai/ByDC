-- crm_demo.sales_bo_status_change definition

-- Drop table

-- DROP TABLE crm_demo.sales_bo_status_change;

CREATE TABLE crm_demo.sales_bo_status_change (
	id bigserial NOT NULL, -- 主键ID
	bo_id int8 NOT NULL, -- 商机主键ID，关联 sales_business_opportunity.id
	opportunity_id varchar(50) NULL DEFAULT NULL::character varying, -- 商机业务唯一标识，关联 sales_business_opportunity.id
	status_before varchar(64) NULL DEFAULT NULL::character varying, -- 变更前状态
	status_after varchar(64) NOT NULL, -- 变更后状态
	change_remark varchar(512) NULL DEFAULT NULL::character varying, -- 变更说明
	changed_by varchar(100) NOT NULL, -- 变更人
	changed_time timestamp NOT NULL DEFAULT pg_systimestamp(), -- 变更时间
	created_by varchar(100) NOT NULL, -- 创建人
	created_time timestamp NOT NULL DEFAULT pg_systimestamp(), -- 创建时间
	updated_by varchar(100) NULL DEFAULT NULL::character varying, -- 更新人
	updated_time timestamp NULL DEFAULT pg_systimestamp(), -- 更新时间
	is_deleted bool NOT NULL DEFAULT false, -- 逻辑删除标识(0:正常,1:删除)
	CONSTRAINT sales_bo_status_change_pkey PRIMARY KEY (id)
)
WITH (
	orientation=row,
	compression=no
);
COMMENT ON TABLE crm_demo.sales_bo_status_change IS '商机状态变更表';

-- Column comments

COMMENT ON COLUMN crm_demo.sales_bo_status_change.id IS '主键ID';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.bo_id IS '商机主键ID，关联 sales_business_opportunity.id';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.opportunity_id IS '商机业务唯一标识，关联 sales_business_opportunity.id';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.status_before IS '变更前状态';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.status_after IS '变更后状态';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.change_remark IS '变更说明';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.changed_by IS '变更人';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.changed_time IS '变更时间';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.created_by IS '创建人';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.created_time IS '创建时间';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.updated_by IS '更新人';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.updated_time IS '更新时间';
COMMENT ON COLUMN crm_demo.sales_bo_status_change.is_deleted IS '逻辑删除标识(0:正常,1:删除)';
