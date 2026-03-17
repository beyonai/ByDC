-- crm_demo.sales_expense_report definition

CREATE TABLE crm_demo.sales_expense_report (
  id BIGSERIAL PRIMARY KEY,
  applicant_emp_no VARCHAR(32) NOT NULL,
  applicant_name VARCHAR(64) NOT NULL,
  applicant_org_id VARCHAR(32) NOT NULL,
  expense_amount NUMERIC(10,2) NOT NULL,
  expense_desc VARCHAR(512) DEFAULT NULL,
  related_bo_id VARCHAR(50) DEFAULT NULL,
  related_customer_id VARCHAR(128) DEFAULT NULL,
  apply_time TIMESTAMP NOT NULL DEFAULT NULL,
  created_by VARCHAR(100) NOT NULL,
  created_time TIMESTAMP NOT NULL DEFAULT NULL,
  updated_by VARCHAR(100) DEFAULT NULL,
  updated_time TIMESTAMP DEFAULT NULL,
  is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
  -- 新增审核相关字段（行内仅定义字段，注释单独写）
  approval_status VARCHAR(20) DEFAULT 'PENDING',
  approval_comment VARCHAR(1024) DEFAULT NULL,
  approved_at TIMESTAMP DEFAULT NULL
);

-- 表注释
COMMENT ON TABLE crm_demo.sales_expense_report IS '费用报备表';

-- 字段注释（逐个声明）
COMMENT ON COLUMN crm_demo.sales_expense_report.id IS '主键ID';
COMMENT ON COLUMN crm_demo.sales_expense_report.applicant_emp_no IS '申请人工号';
COMMENT ON COLUMN crm_demo.sales_expense_report.applicant_name IS '申请人姓名';
COMMENT ON COLUMN crm_demo.sales_expense_report.applicant_org_id IS '申请组织ID';
COMMENT ON COLUMN crm_demo.sales_expense_report.expense_amount IS '申请金额（元）';
COMMENT ON COLUMN crm_demo.sales_expense_report.expense_desc IS '申请说明';
COMMENT ON COLUMN crm_demo.sales_expense_report.related_bo_id IS '关联商机ID';
COMMENT ON COLUMN crm_demo.sales_expense_report.related_customer_id IS '关联客户ID';
COMMENT ON COLUMN crm_demo.sales_expense_report.apply_time IS '申请时间';
COMMENT ON COLUMN crm_demo.sales_expense_report.created_by IS '创建人';
COMMENT ON COLUMN crm_demo.sales_expense_report.created_time IS '创建时间';
COMMENT ON COLUMN crm_demo.sales_expense_report.updated_by IS '更新人';
COMMENT ON COLUMN crm_demo.sales_expense_report.updated_time IS '更新时间';
COMMENT ON COLUMN crm_demo.sales_expense_report.is_deleted IS '逻辑删除标识(0:正常,1:删除)';
-- 新增字段的注释
COMMENT ON COLUMN crm_demo.sales_expense_report.approval_status IS '审核状态（PENDING:待审核,APPROVED:已通过,REJECTED:已驳回）';
COMMENT ON COLUMN crm_demo.sales_expense_report.approval_comment IS '审核意见';
COMMENT ON COLUMN crm_demo.sales_expense_report.approved_at IS '审批时间';
