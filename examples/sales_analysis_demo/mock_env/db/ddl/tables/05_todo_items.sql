-- "crm_demo".todo_items definition

-- Drop table

-- DROP TABLE "crm_demo".todo_items;

CREATE TABLE "crm_demo".todo_items (
	id int8 NOT NULL, -- 待办ID（自增）
	title varchar(512) NOT NULL, -- 待办标题
	todo_content text NULL, -- 待办内容
	deadline_at timestamptz(6) NULL, -- 截止时间
	todo_priority varchar(64) NULL DEFAULT 'Normal'::character varying, -- 优先级：Low(低)、Normal(普通)、High(高)、Urgent(紧急)
	todo_status varchar(64) NULL DEFAULT 'Pending'::character varying, -- 状态：Pending(待处理)、Approving(待审批)、Rejected(已审批拒绝)、Completed(已完成)、Cancelled(已取消)
	created_by varchar(64) NOT NULL, -- 创建人ID
	promoter varchar(64) NOT NULL, -- 发起人ID
	org_id int8 NOT NULL, -- 组织ID
	handler_id varchar(64) NULL, -- 处理人ID（主处理人）
	created_at timestamptz(6) NULL DEFAULT pg_systimestamp(), -- 创建时间
	updated_at timestamptz(6) NULL DEFAULT pg_systimestamp(), -- 更新时间
	completed_at timestamptz(6) NULL, -- 完成时间
	cancelled_at timestamptz(6) NULL, -- 取消时间
	cancelled_reason text NULL, -- 取消原因
	approved_at timestamptz(6) NULL, -- 审批通过时间
	rejected_at timestamptz(6) NULL, -- 审批拒绝时间
	approval_comment text NULL, -- 审批意见
	urgency_level varchar(64) NULL,
	remark varchar(2048) NULL, -- 备注
	meeting_note_id int8 NULL, -- 关联的会议纪要id
	return_reason varchar(5000) NULL, -- 退回理由
	returned_at timestamptz(6) NULL -- 退回时间
)
WITH (
	orientation=row,
	compression=no
);
COMMENT ON TABLE "crm_demo".todo_items IS '待办事项主表';

-- Column comments

COMMENT ON COLUMN "crm_demo".todo_items.id IS '待办ID（自增）';
COMMENT ON COLUMN "crm_demo".todo_items.title IS '待办标题';
COMMENT ON COLUMN "crm_demo".todo_items.todo_content IS '待办内容';
COMMENT ON COLUMN "crm_demo".todo_items.deadline_at IS '截止时间';
COMMENT ON COLUMN "crm_demo".todo_items.todo_priority IS '优先级：Low(低)、Normal(普通)、High(高)、Urgent(紧急)';
COMMENT ON COLUMN "crm_demo".todo_items.todo_status IS '状态：Pending(待处理)、Approving(待审批)、Rejected(已审批拒绝)、Completed(已完成)、Cancelled(已取消)';
COMMENT ON COLUMN "crm_demo".todo_items.created_by IS '创建人ID';
COMMENT ON COLUMN "crm_demo".todo_items.promoter IS '发起人ID';
COMMENT ON COLUMN "crm_demo".todo_items.org_id IS '组织ID';
COMMENT ON COLUMN "crm_demo".todo_items.handler_id IS '处理人ID（主处理人）';
COMMENT ON COLUMN "crm_demo".todo_items.created_at IS '创建时间';
COMMENT ON COLUMN "crm_demo".todo_items.updated_at IS '更新时间';
COMMENT ON COLUMN "crm_demo".todo_items.completed_at IS '完成时间';
COMMENT ON COLUMN "crm_demo".todo_items.cancelled_at IS '取消时间';
COMMENT ON COLUMN "crm_demo".todo_items.cancelled_reason IS '取消原因';
COMMENT ON COLUMN "crm_demo".todo_items.approved_at IS '审批通过时间';
COMMENT ON COLUMN "crm_demo".todo_items.rejected_at IS '审批拒绝时间';
COMMENT ON COLUMN "crm_demo".todo_items.approval_comment IS '审批意见';
COMMENT ON COLUMN "crm_demo".todo_items.remark IS '备注';
COMMENT ON COLUMN "crm_demo".todo_items.meeting_note_id IS '关联的会议纪要id';
COMMENT ON COLUMN "crm_demo".todo_items.return_reason IS '退回理由';
COMMENT ON COLUMN "crm_demo".todo_items.returned_at IS '退回时间';
