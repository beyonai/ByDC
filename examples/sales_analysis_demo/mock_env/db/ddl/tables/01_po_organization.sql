-- crm_demo.po_organization definition

-- Drop table

-- DROP TABLE crm_demo.po_organization;

CREATE TABLE crm_demo.po_organization (
	org_id int8 NOT NULL, -- 组织ID
	org_code varchar(250) NOT NULL, -- 组织编码
	org_name varchar(100) NOT NULL, -- 组织名称
	org_type varchar(4) NOT NULL DEFAULT '0'::character varying, -- 组织类型(0：内部组织；1：外部组织)
	parent_org_id int8 NOT NULL, -- 父标识，-1代表顶层
	org_level int4 NULL, -- 组织层级(0: 顶级； 1-9往后递增)
	org_index int4 NULL, -- 同层级内排序字段
	create_date timestamp NULL, -- 创建时间
	update_date timestamp NULL, -- 更新时间
	path_code varchar(500) NULL, -- 组织路径
	org_desc varchar(1000) NULL, -- 组织描述
	CONSTRAINT po_organization_pkey PRIMARY KEY (org_id)
)
WITH (
	orientation=row,
	compression=no
);
COMMENT ON TABLE crm_demo.po_organization IS '组织信息表';

-- Column comments

COMMENT ON COLUMN crm_demo.po_organization.org_id IS '组织ID';
COMMENT ON COLUMN crm_demo.po_organization.org_code IS '组织编码';
COMMENT ON COLUMN crm_demo.po_organization.org_name IS '组织名称';
COMMENT ON COLUMN crm_demo.po_organization.org_type IS '组织类型(0：内部组织；1：外部组织)';
COMMENT ON COLUMN crm_demo.po_organization.parent_org_id IS '父标识，-1代表顶层';
COMMENT ON COLUMN crm_demo.po_organization.org_level IS '组织层级(0: 顶级； 1-9往后递增)';
COMMENT ON COLUMN crm_demo.po_organization.org_index IS '同层级内排序字段';
COMMENT ON COLUMN crm_demo.po_organization.create_date IS '创建时间';
COMMENT ON COLUMN crm_demo.po_organization.update_date IS '更新时间';
COMMENT ON COLUMN crm_demo.po_organization.path_code IS '组织路径';
COMMENT ON COLUMN crm_demo.po_organization.org_desc IS '组织描述';
