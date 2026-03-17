-- crm_demo.po_users_organization definition

-- Drop table

-- DROP TABLE crm_demo.po_users_organization;

CREATE TABLE crm_demo.po_users_organization (
	id int8 NOT NULL, -- 主键
	user_id int8 NOT NULL,
	org_id int8 NOT NULL, -- 组织ID
	position_id int8 NULL, -- 岗位ID
	user_type varchar(50) NULL, -- 用户类型
	CONSTRAINT po_users_organization_pkey PRIMARY KEY (id)
)
WITH (
	orientation=row,
	compression=no
);
CREATE INDEX idx_po_users_organization_org_id ON crm_demo.po_users_organization (org_id);
CREATE INDEX idx_po_users_organization_user_id ON crm_demo.po_users_organization (user_id);
COMMENT ON TABLE crm_demo.po_users_organization IS '用户组织关联表';

-- Column comments

COMMENT ON COLUMN crm_demo.po_users_organization.id IS '主键';
COMMENT ON COLUMN crm_demo.po_users_organization.org_id IS '组织ID';
COMMENT ON COLUMN crm_demo.po_users_organization.position_id IS '岗位ID';
COMMENT ON COLUMN crm_demo.po_users_organization.user_type IS '用户类型';
