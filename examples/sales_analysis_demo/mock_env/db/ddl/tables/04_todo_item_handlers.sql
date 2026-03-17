-- "crm_demo".todo_item_handlers definition

-- Drop table

-- DROP TABLE "crm_demo".todo_item_handlers;

CREATE TABLE "crm_demo".todo_item_handlers (
	id int8 NOT NULL, -- 关联ID（自增）
	todo_item_id int8 NOT NULL, -- 待办ID
	org_id int8 NOT NULL, -- 组织ID
	handler_id varchar(64) NOT NULL, -- 处理人ID
	assigned_at timestamptz(6) NULL DEFAULT pg_systimestamp(), -- 分配时间
	handled_at timestamptz(6) NULL, -- 处理时间
	handle_comment text NULL, -- 处理意见/备注
	progress_percentage int4 NULL DEFAULT 0 -- 该处理人的处理进度0-100，100时可变为待审核
)
WITH (
	orientation=row,
	compression=no
);
CREATE INDEX idx_todo_handlers_composite ON crm_demo.todo_item_handlers USING btree (handler_id, todo_item_id) TABLESPACE pg_default;
CREATE INDEX idx_todo_handlers_handled_at ON crm_demo.todo_item_handlers USING btree (handled_at DESC) TABLESPACE pg_default WHERE (handled_at IS NOT NULL);
CREATE INDEX idx_todo_handlers_handler_id ON crm_demo.todo_item_handlers USING btree (handler_id) TABLESPACE pg_default;
CREATE INDEX idx_todo_handlers_org_id ON crm_demo.todo_item_handlers USING btree (org_id) TABLESPACE pg_default;
CREATE INDEX idx_todo_handlers_todo_item_id ON crm_demo.todo_item_handlers USING btree (todo_item_id) TABLESPACE pg_default;
COMMENT ON TABLE "crm_demo".todo_item_handlers IS '待办处理人关联表';

-- Column comments

COMMENT ON COLUMN "crm_demo".todo_item_handlers.id IS '关联ID（自增）';
COMMENT ON COLUMN "crm_demo".todo_item_handlers.todo_item_id IS '待办ID';
COMMENT ON COLUMN "crm_demo".todo_item_handlers.org_id IS '组织ID';
COMMENT ON COLUMN "crm_demo".todo_item_handlers.handler_id IS '处理人ID';
COMMENT ON COLUMN "crm_demo".todo_item_handlers.assigned_at IS '分配时间';
COMMENT ON COLUMN "crm_demo".todo_item_handlers.handled_at IS '处理时间';
COMMENT ON COLUMN "crm_demo".todo_item_handlers.handle_comment IS '处理意见/备注';
COMMENT ON COLUMN "crm_demo".todo_item_handlers.progress_percentage IS '该处理人的处理进度0-100，100时可变为待审核';
