-- crm_demo.sales_meeting_note definition

-- Drop table

-- DROP TABLE crm_demo.sales_meeting_note;

CREATE TABLE crm_demo.sales_meeting_note (
	id bigserial NOT NULL, -- 主键ID
	meeting_title varchar(255) NOT NULL, -- 会议纪要标题
	meeting_content text NULL, -- 会议内容
	start_time timestamp NOT NULL, -- 发起时间
	related_bo_id varchar(50) NULL DEFAULT NULL::character varying, -- 关联商机ID
	related_customer_id varchar(128) NULL DEFAULT NULL::character varying, -- 关联客户ID
	participant_emp_nos jsonb NULL, -- 会议参与人员工号（多个）
	created_by varchar(100) NOT NULL, -- 会议创建人
	created_time timestamp NOT NULL DEFAULT pg_systimestamp(), -- 创建时间
	updated_by varchar(100) NULL DEFAULT NULL::character varying, -- 更新人
	updated_time timestamp NULL DEFAULT pg_systimestamp(), -- 更新时间
	is_deleted bool NOT NULL DEFAULT false, -- 逻辑删除标识(0:正常,1:删除)
	CONSTRAINT sales_meeting_note_pkey PRIMARY KEY (id)
)
WITH (
	orientation=row,
	compression=no
);
COMMENT ON TABLE crm_demo.sales_meeting_note IS '会议纪要表';

-- Column comments

COMMENT ON COLUMN crm_demo.sales_meeting_note.id IS '主键ID';
COMMENT ON COLUMN crm_demo.sales_meeting_note.meeting_title IS '会议纪要标题';
COMMENT ON COLUMN crm_demo.sales_meeting_note.meeting_content IS '会议内容';
COMMENT ON COLUMN crm_demo.sales_meeting_note.start_time IS '发起时间';
COMMENT ON COLUMN crm_demo.sales_meeting_note.related_bo_id IS '关联商机ID';
COMMENT ON COLUMN crm_demo.sales_meeting_note.related_customer_id IS '关联客户ID';
COMMENT ON COLUMN crm_demo.sales_meeting_note.participant_emp_nos IS '会议参与人员工号（多个）';
COMMENT ON COLUMN crm_demo.sales_meeting_note.created_by IS '会议创建人';
COMMENT ON COLUMN crm_demo.sales_meeting_note.created_time IS '创建时间';
COMMENT ON COLUMN crm_demo.sales_meeting_note.updated_by IS '更新人';
COMMENT ON COLUMN crm_demo.sales_meeting_note.updated_time IS '更新时间';
COMMENT ON COLUMN crm_demo.sales_meeting_note.is_deleted IS '逻辑删除标识(0:正常,1:删除)';
