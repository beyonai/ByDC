/*
 demo 数据库
*/



-- ----------------------------
-- Table structure for po_organization
-- ----------------------------
DROP TABLE IF EXISTS "{{DATACLOUD_DB_SCHEMA}}"."po_organization";
CREATE TABLE "{{DATACLOUD_DB_SCHEMA}}"."po_organization" (
  "org_id" int8,
  "org_code" varchar(250) COLLATE "pg_catalog"."default",
  "org_name" varchar(100) COLLATE "pg_catalog"."default",
  "org_type" varchar(4) COLLATE "pg_catalog"."default",
  "parent_org_id" int8,
  "org_level" int4,
  "org_index" int4,
  "create_date" timestamp(6),
  "update_date" timestamp(6),
  "path_code" varchar(500) COLLATE "pg_catalog"."default",
  "org_desc" varchar(1000) COLLATE "pg_catalog"."default"
)
;

-- ----------------------------
-- Records of po_organization
-- ----------------------------
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (202, '202', '鲸智科技', '0', -1, 1, 0, '2026-04-28 07:46:39.645', NULL, '-1.202', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (242, '242', '华中-医疗组', '0', 215, 4, 3, '2026-04-28 07:46:39.912', NULL, '-1.202.210.215.242', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (241, '241', '华中-政府组', '0', 215, 4, 2, '2026-04-28 07:46:39.912', NULL, '-1.202.210.215.241', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (240, '240', '华中-金融组', '0', 215, 4, 1, '2026-04-28 07:46:39.912', NULL, '-1.202.210.215.240', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (239, '239', '华西-制造组', '0', 214, 4, 2, '2026-04-28 07:46:39.912', NULL, '-1.202.210.214.239', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (238, '238', '华西-政府组', '0', 214, 4, 1, '2026-04-28 07:46:39.912', NULL, '-1.202.210.214.238', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (237, '237', '华南-政府组', '0', 213, 4, 2, '2026-04-28 07:46:39.912', NULL, '-1.202.210.213.237', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (236, '236', '华南-金融组', '0', 213, 4, 1, '2026-04-28 07:46:39.912', NULL, '-1.202.210.213.236', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (235, '235', '华东-制造组', '0', 212, 4, 3, '2026-04-28 07:46:39.912', NULL, '-1.202.210.212.235', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (234, '234', '华东-政府组', '0', 212, 4, 2, '2026-04-28 07:46:39.912', NULL, '-1.202.210.212.234', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (233, '233', '华东-金融组', '0', 212, 4, 1, '2026-04-28 07:46:39.912', NULL, '-1.202.210.212.233', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (232, '232', '华北-政府组', '0', 211, 4, 2, '2026-04-28 07:46:39.912', NULL, '-1.202.210.211.232', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (231, '231', '华北-金融组', '0', 211, 4, 1, '2026-04-28 07:46:39.912', NULL, '-1.202.210.211.231', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (224, '224', '交付部', '0', 220, 3, 4, '2026-04-28 07:46:39.848', NULL, '-1.202.220.224', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (223, '223', 'CRM产品部', '0', 220, 3, 3, '2026-04-28 07:46:39.848', NULL, '-1.202.220.223', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (222, '222', 'BI产品部', '0', 220, 3, 2, '2026-04-28 07:46:39.848', NULL, '-1.202.220.222', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (221, '221', '数据产品部', '0', 220, 3, 1, '2026-04-28 07:46:39.848', NULL, '-1.202.220.221', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (220, '220', '研发与交付中心', '0', 202, 2, 2, '2026-04-28 07:46:39.717', NULL, '-1.202.220', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (215, '215', '华中大区', '0', 210, 3, 5, '2026-04-28 07:46:39.783', NULL, '-1.202.210.215', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (214, '214', '华西大区', '0', 210, 3, 4, '2026-04-28 07:46:39.783', NULL, '-1.202.210.214', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (213, '213', '华南大区', '0', 210, 3, 3, '2026-04-28 07:46:39.783', NULL, '-1.202.210.213', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (212, '212', '华东大区', '0', 210, 3, 2, '2026-04-28 07:46:39.783', NULL, '-1.202.210.212', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (211, '211', '华北大区', '0', 210, 3, 1, '2026-04-28 07:46:39.783', NULL, '-1.202.210.211', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (210, '210', '销售中心', '0', 202, 2, 1, '2026-04-28 07:46:39.717', NULL, '-1.202.210', NULL);

-- ----------------------------
-- Table structure for po_users
-- ----------------------------
DROP TABLE IF EXISTS "{{DATACLOUD_DB_SCHEMA}}"."po_users";
CREATE TABLE "{{DATACLOUD_DB_SCHEMA}}"."po_users" (
  "user_id" int8,
  "user_name" varchar(255) COLLATE "pg_catalog"."default",
  "email" varchar(255) COLLATE "pg_catalog"."default",
  "phone" varchar(255) COLLATE "pg_catalog"."default",
  "user_code" varchar(255) COLLATE "pg_catalog"."default",
  "pwd" varchar(255) COLLATE "pg_catalog"."default",
  "address" text COLLATE "pg_catalog"."default",
  "remark" varchar(255) COLLATE "pg_catalog"."default",
  "user_eff_date" timestamp(6),
  "user_exp_date" timestamp(6),
  "create_date" timestamp(6),
  "update_date" timestamp(6),
  "state" char(1) COLLATE "pg_catalog"."default",
  "state_time" timestamp(6),
  "is_locked" char(1) COLLATE "pg_catalog"."default",
  "last_login_date" timestamp(6),
  "security_question_id" numeric(3,0),
  "security_answer" varchar(120) COLLATE "pg_catalog"."default",
  "thumbnail_uri" varchar(400) COLLATE "pg_catalog"."default",
  "ext_attr" varchar(1000) COLLATE "pg_catalog"."default",
  "assistant_id" int8,
  "user_number" varchar(300) COLLATE "pg_catalog"."default",
  "station_id" int8,
  "register_type" int2,
  "apple_user_id" varchar(255) COLLATE "pg_catalog"."default"
)
;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."user_id" IS '用户唯一标识';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."user_name" IS '用户名称';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."email" IS '用户邮箱';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."phone" IS '用户电话';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."user_code" IS '用户登录标识';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."pwd" IS '用户密码(md5加密)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."address" IS '用户地址';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."remark" IS '用户备注';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."user_eff_date" IS '预留';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."user_exp_date" IS '用户过期日期';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."create_date" IS '记录创建日期';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."update_date" IS '记录更新日期';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."state" IS '用户状态：A-正常;X-禁用';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."is_locked" IS '是否锁定，''Y''-锁定，''N''-没有锁定，null表示''N''';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."last_login_date" IS '用户最后一次登录时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."security_question_id" IS '用户忘记密码找回密码问题';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."security_answer" IS '用户忘记密码安全提示问题';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."thumbnail_uri" IS '用户头像URL地址';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."ext_attr" IS '用户扩展信息';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."assistant_id" IS '一个员工对应一个超级助手';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."user_number" IS '工号';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."station_id" IS '所属驻地';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."register_type" IS '注册类型 1-手机号注册';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."apple_user_id" IS '苹果用户ID，用于苹果登录关联';
COMMENT ON TABLE "{{DATACLOUD_DB_SCHEMA}}"."po_users" IS '用户表';

-- ----------------------------
-- Records of po_users
-- ----------------------------
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (101, '萧峰', NULL, NULL, 'xiaofeng', '11f3e866026b21d3cc6bf419083ae7fd', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (102, '郭靖', NULL, NULL, 'guojing', 'abe81f55c23f66d509d6ff911b54a716', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (103, '令狐冲', NULL, NULL, 'linghuchong', '94e6e036752607a1d9c32ea1d473069c', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (104, '韦小宝', NULL, NULL, 'weixiaobao', '5b8cd4e991d3f75fd4c0fca3cbc9479e', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (105, '胡斐', NULL, NULL, 'hufei', '6f65618d791121fc462a9bdb15ed1d64', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (106, '陈家洛', NULL, NULL, 'chenjialuo', 'cca58b33a6656fb57b2175f933360a26', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (107, '狄云', NULL, NULL, 'diyun', 'de0f42cf627be6707d0e1229ae399340', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (108, '杨过', NULL, NULL, 'yangguo', '914bd8bbb758aa4c1fae2c4b1123daee', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (109, '张无忌', NULL, NULL, 'zhangwuji', '9b5524374d801b1eeb0fa30aa07f3d99', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (110, '黄蓉', NULL, NULL, 'huangrong', 'e72be06c7a4003a523e45ddc4154f9e1', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (111, '赵敏', NULL, NULL, 'zhaomin', '165dfbd637f2d12bb5fff64fa34263d9', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (100, '张三丰', NULL, NULL, 'zhangsanfeng', '9be6b5fe662ec7eda75e388da9f1d0b3', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, '221312', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (112, '任盈盈', NULL, NULL, 'renyingying', '3738a9006cea101dabe09efca74a71c8', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000077, '黎明', NULL, NULL, '0027011322', 'baf140a7045f3981eed6047d9ec40a87', NULL, NULL, '2026-04-28 11:11:15.24', NULL, '2026-04-28 11:11:15.24', NULL, 'A', '2026-04-28 11:11:15.24', 'N', NULL, NULL, NULL, NULL, NULL, 10000077, '0027011322', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (113, '小龙女', NULL, NULL, 'xiaolongnv', '95d79dc9e3dc06f1f27fe94d71f70f85', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (114, '王语嫣', NULL, NULL, 'wangyuyan', '2efae2ad0680bffb50b933069bc6f5f9', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (115, '霍青桐', NULL, NULL, 'huoqingtong', 'dfc82eb5717618adccd1627424f982bc', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (116, '苗若兰', NULL, NULL, 'miaoruolan', '2853a36fa8c963127210dcb5cc5cff72', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (117, '洪七公', NULL, NULL, 'hongqigong', 'e02a7a3444ec27094808f82bec92eb0f', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (119, '欧阳锋', NULL, NULL, 'ouyangfeng', '6ea7dfba7a5d9c6baa485d5313562494', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (120, '段誉', NULL, NULL, 'duanyu', '7e7d5cb2b1078b72606b3aba5ccdef03', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (121, '虚竹', NULL, NULL, 'xuzhu', '9081fc184a922271b966101ff9bac603', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (122, '周伯通', NULL, NULL, 'zhoubotong', '84c4ac2d9e98f6cd07af8829a5d2cb87', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (123, '慕容复', NULL, NULL, 'murongfu', '3a6efa410db4417c4df7737bf3f77a6b', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (124, '游坦之', NULL, NULL, 'youtanzhi', '46418332b0d8ee3495179f2a938385e6', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (125, '岳不群', NULL, NULL, 'yuebuqun', '7dfb391e13233965056f10eb445d58ec', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (126, '风清扬', NULL, NULL, 'fengqingyang', '25ac15b9af5430a4bfafd4e6794a78ff', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (127, '扫地僧', NULL, NULL, 'saodiseng', 'aeae1ff3f89fcdece56d9a92a1d43168', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (128, '宋远桥', NULL, NULL, 'songyuanqiao', 'bc9c9e741643555d04d064e25b14d686', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (129, '俞莲舟', NULL, NULL, 'yulianzhou', 'ea944ea1baf3cc97da92db60bbc90484', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (130, '张翠山', NULL, NULL, 'zhangcuishan', 'f0566ffafa9fcdbff1ee8432c648df36', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (131, '殷素素', NULL, NULL, 'yinsusu', '16eff566bf11c02ccea671cc8cf88489', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (132, '俞岱岩', NULL, NULL, 'yudaiyan', 'bcb2fb54b87928260736ee378fb4de4f', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (133, '谢逊', NULL, NULL, 'xiexun', '417db0a0fb7a29da1821870ff7b73a2c', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (134, '韦一笑', NULL, NULL, 'weiyixiao', '7964102c17ac4bbc77ea9fa7b985ff9d', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (135, '杨逍', NULL, NULL, 'yangxiao', '552f65db63bcc31b1d4f321339a1e9ac', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (136, '范遥', NULL, NULL, 'fanyao', 'b03a74a2984fd3d2a3df23fd5358ab63', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (137, '成昆', NULL, NULL, 'chengkun', '068c04db899bda204ac6acd6301b7ea1', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (138, '殷天正', NULL, NULL, 'yintianzheng', '77251c404d05198b95552928eecf64b1', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000084, '吴彦祖', NULL, NULL, '0027021534', '63d5b7b2fd1ff1889b4293943442ccc3', NULL, NULL, '2026-04-28 11:12:01.794', NULL, '2026-04-28 11:12:01.794', '2026-04-28 11:17:54.221', 'A', '2026-04-28 11:12:01.794', 'N', NULL, NULL, NULL, NULL, NULL, 10000084, '0027021534', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (137, '成昆', NULL, NULL, 'chengkun', '068c04db899bda204ac6acd6301b7ea1', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10, '鲍总', NULL, NULL, '101155', '967a7b1604f8962380f351f17dd9f96d', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, '101155', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (11, '杨总', NULL, NULL, '0027010369', '73bd3298f80dfd1b6cd53914e5c599de', NULL, NULL, '2026-04-28 11:17:10.014', NULL, '2026-04-28 11:17:10.014', NULL, 'A', '2026-04-28 11:17:10.014', 'N', NULL, NULL, NULL, NULL, NULL, NULL, '0027010369', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (12, '罗总', NULL, NULL, '0027000618', 'd5825494e02fc4ca8977dd8a29e2cc4a', NULL, NULL, '2026-04-28 11:12:01.794', NULL, '2026-04-28 11:12:01.794', '2026-04-28 11:17:54.221', 'A', '2026-04-28 11:12:01.794', 'N', NULL, NULL, NULL, NULL, NULL, NULL, '0027000618', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (13, '陈总', NULL, NULL, '0027002811', '3ee833b26a505b0b026978a24a71be09', NULL, NULL, '2026-04-28 11:05:58.807', NULL, '2026-04-28 11:05:58.807', NULL, 'A', '2026-04-28 11:05:58.807', 'N', NULL, NULL, NULL, NULL, NULL, NULL, '0027002811', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000091, '杜甫', NULL, NULL, '0027012991', 'b3d2a271f363068b7823e750131f3f59', NULL, NULL, '2026-04-28 11:13:06.771', NULL, '2026-04-28 11:13:06.771', '2026-05-14 20:33:31.674', 'A', '2026-04-28 11:13:06.771', 'N', '2026-05-14 20:33:31.627', NULL, NULL, NULL, NULL, 10000091, '0027012991', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000118, '刘皇叔', NULL, NULL, '0027030770', '3afa6137a8e832c849eabc81d1354df1', NULL, NULL, '2026-04-28 11:17:10.014', NULL, '2026-04-28 11:17:10.014', '2026-05-14 16:56:54.653', 'A', '2026-04-28 11:17:10.014', 'N', '2026-05-14 16:56:54.606', NULL, NULL, NULL, NULL, 10000118, '0027030770', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000009, '覃小迪', NULL, NULL, '0027002543', 'e7eed98dd3caf055555b5923904e1348', NULL, NULL, '2026-04-28 11:04:11.689', NULL, '2026-04-28 11:04:11.689', '2026-05-12 18:01:22.85', 'A', '2026-04-28 11:04:11.689', 'N', '2026-05-12 18:01:22.811', NULL, NULL, NULL, NULL, 10000009, '0027002543', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10001767, '大师新用户', NULL, NULL, 'dashixinyonghu', '512be623019f71e5b8428b5d2a846554', NULL, NULL, '2026-05-08 19:55:54.629', NULL, '2026-05-08 19:55:54.629', NULL, 'A', '2026-05-08 19:55:54.629', 'N', NULL, NULL, NULL, NULL, NULL, 10001767, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000022, '黄药师', NULL, NULL, '0027024630', 'f26f6cc039b08e623fe2cf4d4788c41b', NULL, NULL, '2026-04-28 11:05:00.066', NULL, '2026-04-28 11:05:00.066', '2026-05-14 21:29:34.607', 'A', '2026-04-28 11:05:00.066', 'N', '2026-05-14 21:29:34.606', NULL, NULL, NULL, NULL, 10000022, '0027024630', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (118, '黄药师2', NULL, NULL, 'huangyaoshi', '556e4f3fce8b6fe464bc2bcc4e1172b5', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000036, '无名', NULL, NULL, '0027000620', 'c8c78e740d2775c2dc2c2e8076f48483', NULL, NULL, '2026-04-28 11:06:49.14', NULL, '2026-04-28 11:06:49.14', '2026-05-14 22:27:54.973', 'A', '2026-04-28 11:06:49.14', 'N', '2026-05-14 22:27:54.932', NULL, NULL, NULL, NULL, 10000036, '0027000620', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000098, '罗贯中', NULL, NULL, '0027028723', '1610fd1c28e4c25f195426942c615717', NULL, NULL, '2026-04-28 11:14:57.12', NULL, '2026-04-28 11:14:57.12', '2026-05-14 20:39:04.569', 'A', '2026-04-28 11:14:57.12', 'N', '2026-05-14 20:39:04.568', NULL, NULL, NULL, NULL, 10000098, '0027028723', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000050, '谢逊飞', NULL, NULL, '0027023754', 'a32c976423ef1308b81018c5f802679d', NULL, NULL, '2026-04-28 11:08:07.481', NULL, '2026-04-28 11:08:07.481', '2026-05-14 20:04:34.846', 'A', '2026-04-28 11:08:07.481', 'N', '2026-05-14 20:04:34.846', NULL, NULL, NULL, NULL, 10000050, '0027023754', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10003595, '乐佳', NULL, NULL, 'lejia', '6fb97f9b12ee7b87504280c3417cb692', NULL, NULL, '2026-05-09 17:20:11.881', NULL, '2026-05-09 17:20:11.881', '2026-05-09 18:20:26.814', 'A', '2026-05-09 17:20:11.881', 'N', '2026-05-09 18:20:26.765', NULL, NULL, NULL, NULL, 10003595, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000105, '萧峰', NULL, NULL, '0027016840', '1f9523c4f00a172ebe7aa1925513c465', NULL, NULL, '2026-04-28 11:15:48.839', NULL, '2026-04-28 11:15:48.839', '2026-05-13 14:41:14.736', 'A', '2026-04-28 11:15:48.839', 'N', '2026-05-13 14:41:14.736', NULL, NULL, NULL, NULL, 10000105, '0027016840', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000029, '梁小', NULL, NULL, '0027003719', 'b7441994d49c674e4840e1d3b0df64b4', NULL, NULL, '2026-04-28 11:05:58.807', NULL, '2026-04-28 11:05:58.807', '2026-05-12 16:29:06.894', 'A', '2026-04-28 11:05:58.807', 'N', '2026-05-12 16:29:06.893', NULL, NULL, NULL, NULL, 10000029, '0027003719', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000057, '陈舵主', NULL, NULL, '0027024710', 'de622ef8f9d7445122fee69a0e8d6508', NULL, NULL, '2026-04-28 11:08:49.096', NULL, '2026-04-28 11:08:49.096', '2026-05-13 21:29:45.596', 'A', '2026-04-28 11:08:49.096', 'N', '2026-05-13 21:29:45.596', NULL, NULL, NULL, NULL, 10000057, '0027024710', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000070, '王重阳', NULL, NULL, '0027019281', '8aa92ea8a5a509804f74d3739de46e3a', NULL, NULL, '2026-04-28 11:10:05.087', NULL, '2026-04-28 11:10:05.087', '2026-05-14 09:33:57.391', 'A', '2026-04-28 11:10:05.087', 'N', '2026-05-14 09:33:57.391', NULL, NULL, NULL, NULL, 10000070, '0027019281', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10001, '平台管理员adminvip', 'adminvip@byai.com', 'TvvjzLzE6+JUsjGVhw7yXw==', 'adminvip', 'dfef67ebc70b6746ad6305a6da2518e8', NULL, NULL, '2025-06-03 07:04:21.908', NULL, '2025-06-03 07:04:21.908', '2026-05-14 21:48:26.551', 'A', NULL, 'N', '2026-05-14 21:48:26.487', NULL, NULL, NULL, NULL, 10000004, '0000000002', 576, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000043, '周伯通', NULL, NULL, '0027011326', 'b0309abdbf4d258f631d44965acc34ce', NULL, NULL, '2026-04-28 11:07:23.106', NULL, '2026-04-28 11:07:23.106', '2026-05-14 21:01:01.461', 'A', '2026-04-28 11:07:23.106', 'N', '2026-05-14 21:01:01.461', NULL, NULL, NULL, NULL, 10000043, '0027011326', NULL, NULL, NULL);



-- ----------------------------
-- Table structure for by_customer
-- ----------------------------
DROP TABLE IF EXISTS "{{DATACLOUD_DB_SCHEMA}}"."by_customer";
CREATE TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_customer" (
  "id" int8 NOT NULL DEFAULT nextval('"{{DATACLOUD_DB_SCHEMA}}".by_customer_id_seq'::regclass),
  "customer_code" varchar(50) COLLATE "pg_catalog"."default" NOT NULL,
  "customer_name" varchar(200) COLLATE "pg_catalog"."default" NOT NULL,
  "industry" varchar(100) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "province" varchar(50) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "city" varchar(50) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "domain" varchar(100) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "sales_user_id" varchar(100) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "sales_person" varchar(100) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "dept_id" varchar(50) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "dept_name" varchar(200) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "create_by" varchar(64) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "create_time" timestamp(6),
  "update_by" varchar(64) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "update_time" timestamp(6),
  "remark" varchar(500) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying
)
;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."id" IS '主键';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."customer_code" IS '客户编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."customer_name" IS '客户名称';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."industry" IS '所属行业';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."province" IS '所属省份';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."city" IS '所属城市';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."domain" IS '所属领域';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."sales_user_id" IS '所属销售用户编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."sales_person" IS '所属销售姓名';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."dept_id" IS '所属组织编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."dept_name" IS '所属组织名称';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."create_by" IS '创建者';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."create_time" IS '创建时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."update_by" IS '更新者';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."update_time" IS '更新时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."remark" IS '备注';
COMMENT ON TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_customer" IS '客户信息表';

-- ----------------------------
-- Records of by_customer
-- ----------------------------
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (1, 'CUST000001', '北京国投中债资产管理有限公司', '金融', '11', '北京', '1', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2025-11-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (2, 'CUST000002', '中国工商银行股份有限公司北京分行', '金融', '11', '北京', '1', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2025-11-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (3, 'CUST000003', '北京市海淀区人民政府', '政府', '11', '北京', '2', 'diyun', '狄云', '234', '华东-政府组', 'admin', '2025-11-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (4, 'CUST000004', '招商银行股份有限公司上海分行', '金融', '31', '上海', '1', 'hufei', '胡斐', '233', '华东-金融组', 'admin', '2025-11-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (5, 'CUST000005', '上海浦东发展银行股份有限公司', '金融', '31', '上海', '1', 'hufei', '胡斐', '233', '华东-金融组', 'admin', '2025-11-19 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (6, 'CUST000006', '广州市天河区卫生健康局', '政府', '44', '广州', '2', 'chenjialuo', '陈家洛', '236', '华南-金融组', 'admin', '2025-11-21 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (7, 'CUST000007', '广东省人民医院', '医疗健康', '44', '广州', '3', 'chenjialuo', '陈家洛', '236', '华南-金融组', 'admin', '2025-11-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (8, 'CUST000008', '深圳市平安银行股份有限公司', '金融', '44', '深圳', '1', 'chenjialuo', '陈家洛', '236', '华南-金融组', 'admin', '2025-11-26 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (9, 'CUST000009', '成都高新技术产业开发区管委会', '政府', '51', '成都', '2', 'yangguo', '杨过', '238', '华西-政府组', 'admin', '2025-12-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (10, 'CUST000010', '四川省教育厅', '政府', '51', '成都', '4', 'yangguo', '杨过', '238', '华西-政府组', 'admin', '2025-12-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (11, 'CUST000011', '武汉市商业银行股份有限公司', '金融', '42', '武汉', '1', 'zhangwuji', '张无忌', '240', '华中-金融组', 'admin', '2025-12-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (12, 'CUST000012', '湖北省卫生健康委员会', '政府', '42', '武汉', '3', 'zhangwuji', '张无忌', '240', '华中-金融组', 'admin', '2025-12-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (13, 'CUST000013', '南京银行股份有限公司', '金融', '32', '南京', '1', 'hufei', '胡斐', '233', '华东-金融组', 'admin', '2025-12-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (14, 'CUST000014', '江苏省大数据管理中心', '政府', '32', '南京', '2', 'diyun', '狄云', '234', '华东-政府组', 'admin', '2025-12-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (15, 'CUST000015', '浙江大学', '教育', '33', '杭州', '4', 'diyun', '狄云', '234', '华东-政府组', 'admin', '2025-12-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (16, 'CUST000016', '阿里巴巴（中国）有限公司', '制造', '33', '杭州', '5', 'diyun', '狄云', '234', '华东-政府组', 'admin', '2025-12-19 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (17, 'CUST000017', '宁波银行股份有限公司', '金融', '33', '宁波', '1', 'hufei', '胡斐', '233', '华东-金融组', 'admin', '2025-12-21 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (18, 'CUST000018', '深圳市腾讯计算机系统有限公司', '制造', '44', '深圳', '5', 'chenjialuo', '陈家洛', '236', '华南-金融组', 'admin', '2025-12-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (19, 'CUST000019', '广州市越秀区教育局', '政府', '44', '广州', '4', 'chenjialuo', '陈家洛', '236', '华南-金融组', 'admin', '2025-12-25 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (20, 'CUST000020', '华为技术有限公司', '制造', '44', '深圳', '5', 'chenjialuo', '陈家洛', '236', '华南-金融组', 'admin', '2025-12-27 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (21, 'CUST000021', '中国建设银行股份有限公司天津分行', '金融', '12', '天津', '1', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2025-12-29 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (22, 'CUST000022', '天津市滨海新区人民政府', '政府', '12', '天津', '2', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2026-01-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (23, 'CUST000023', '河北省数字办', '政府', '13', '石家庄', '2', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2026-01-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (24, 'CUST000024', '中国农业银行山东省分行', '金融', '37', '济南', '1', 'zhangwuji', '张无忌', '240', '华中-金融组', 'admin', '2026-01-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (25, 'CUST000025', '山东省人民医院', '医疗健康', '37', '济南', '3', 'zhangwuji', '张无忌', '240', '华中-金融组', 'admin', '2026-01-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (26, 'CUST000026', '郑州银行股份有限公司', '金融', '41', '郑州', '1', 'zhangwuji', '张无忌', '240', '华中-金融组', 'admin', '2026-01-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (27, 'CUST000027', '河南省卫生健康委员会', '政府', '41', '郑州', '3', 'zhangwuji', '张无忌', '240', '华中-金融组', 'admin', '2026-01-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (28, 'CUST000028', '重庆农村商业银行股份有限公司', '金融', '50', '重庆', '1', 'yangguo', '杨过', '238', '华西-政府组', 'admin', '2026-01-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (29, 'CUST000029', '贵州省大数据发展管理局', '政府', '52', '贵阳', '2', 'yangguo', '杨过', '238', '华西-政府组', 'admin', '2026-01-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (30, 'CUST000030', '云南省数字经济局', '政府', '53', '昆明', '2', 'yangguo', '杨过', '238', '华西-政府组', 'admin', '2026-01-19 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (31, 'CUST000031', '厦门国际银行股份有限公司', '金融', '35', '厦门', '1', 'hufei', '胡斐', '233', '华东-金融组', 'admin', '2026-01-21 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (32, 'CUST000032', '福建省医科大学附属第一医院', '医疗健康', '35', '福州', '3', 'hufei', '胡斐', '233', '华东-金融组', 'admin', '2026-01-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (33, 'CUST000033', '苏州工业园区管委会', '政府', '32', '苏州', '2', 'diyun', '狄云', '234', '华东-政府组', 'admin', '2026-01-25 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (34, 'CUST000034', '无锡市大数据管理局', '政府', '32', '无锡', '2', 'diyun', '狄云', '234', '华东-政府组', 'admin', '2026-02-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (35, 'CUST000035', '江苏省人民医院', '医疗健康', '32', '南京', '3', 'hufei', '胡斐', '233', '华东-金融组', 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (36, 'CUST000036', '上海交通大学', '教育', '31', '上海', '4', 'hufei', '胡斐', '233', '华东-金融组', 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (37, 'CUST000037', '上海市大数据中心', '政府', '31', '上海', '2', 'diyun', '狄云', '234', '华东-政府组', 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (38, 'CUST000038', '中国电信股份有限公司上海分公司', '制造', '31', '上海', '9', 'diyun', '狄云', '234', '华东-政府组', 'admin', '2026-02-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (39, 'CUST000039', '北京银行股份有限公司', '金融', '11', '北京', '1', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2026-02-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (40, 'CUST000040', '北京市大数据中心', '政府', '11', '北京', '2', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2026-02-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (41, 'CUST000041', '首都医科大学附属北京协和医院', '医疗健康', '11', '北京', '3', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2026-02-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (42, 'CUST000042', '中国电力建设股份有限公司', '制造', '11', '北京', '7', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2026-02-19 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (43, 'CUST000043', '中国移动通信集团广东有限公司', '制造', '44', '广州', '9', 'chenjialuo', '陈家洛', '236', '华南-金融组', 'admin', '2026-02-21 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (44, 'CUST000044', '广州农商银行股份有限公司', '金融', '44', '广州', '1', 'chenjialuo', '陈家洛', '236', '华南-金融组', 'admin', '2026-02-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (45, 'CUST000045', '海南省大数据管理局', '政府', '46', '海口', '2', 'chenjialuo', '陈家洛', '236', '华南-金融组', 'admin', '2026-03-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (46, 'CUST000046', '西安银行股份有限公司', '金融', '61', '西安', '1', 'yangguo', '杨过', '238', '华西-政府组', 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (47, 'CUST000047', '陕西省数字政府管理局', '政府', '61', '西安', '2', 'yangguo', '杨过', '238', '华西-政府组', 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (48, 'CUST000048', '四川省人民医院', '医疗健康', '51', '成都', '3', 'yangguo', '杨过', '238', '华西-政府组', 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (49, 'CUST000049', '湖南省大数据局', '政府', '43', '长沙', '2', 'zhangwuji', '张无忌', '240', '华中-金融组', 'admin', '2026-03-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (50, 'CUST000050', '长沙银行股份有限公司', '金融', '43', '长沙', '1', 'zhangwuji', '张无忌', '240', '华中-金融组', 'admin', '2026-03-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (51, 'CUST000051', '青岛银行股份有限公司', '金融', '37', '青岛', '1', 'zhangwuji', '张无忌', '240', '华中-金融组', 'admin', '2026-03-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (52, 'CUST000052', '济南市大数据局', '政府', '37', '济南', '2', 'zhangwuji', '张无忌', '240', '华中-金融组', 'admin', '2026-03-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (53, 'CUST000053', '合肥市数据资源局', '政府', '34', '合肥', '2', 'hufei', '胡斐', '233', '华东-金融组', 'admin', '2026-03-19 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (54, 'CUST000054', '安徽省立医院', '医疗健康', '34', '合肥', '3', 'hufei', '胡斐', '233', '华东-金融组', 'admin', '2026-03-21 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (55, 'CUST000055', '徽商银行股份有限公司', '金融', '34', '合肥', '1', 'hufei', '胡斐', '233', '华东-金融组', 'admin', '2026-03-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (56, 'CUST000056', '南昌市政务数据局', '政府', '36', '南昌', '2', 'hufei', '胡斐', '233', '华东-金融组', 'admin', '2026-04-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (57, 'CUST000057', '江西银行股份有限公司', '金融', '36', '南昌', '1', 'diyun', '狄云', '234', '华东-政府组', 'admin', '2026-04-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (58, 'CUST000058', '南宁市大数据发展局', '政府', '45', '南宁', '2', 'chenjialuo', '陈家洛', '236', '华南-金融组', 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (59, 'CUST000059', '广西壮族自治区人民医院', '医疗健康', '45', '南宁', '3', 'chenjialuo', '陈家洛', '236', '华南-金融组', 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (60, 'CUST000060', '桂林银行股份有限公司', '金融', '45', '桂林', '1', 'chenjialuo', '陈家洛', '236', '华南-金融组', 'admin', '2026-04-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (61, 'CUST000061', '兰州银行股份有限公司', '金融', '62', '兰州', '1', 'yangguo', '杨过', '238', '华西-政府组', 'admin', '2026-04-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (62, 'CUST000062', '甘肃省数据局', '政府', '62', '兰州', '2', 'yangguo', '杨过', '238', '华西-政府组', 'admin', '2026-04-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (63, 'CUST000063', '宁夏银行股份有限公司', '金融', '64', '银川', '1', 'yangguo', '杨过', '238', '华西-政府组', 'admin', '2026-04-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (64, 'CUST000064', '内蒙古自治区大数据中心', '政府', '15', '呼和浩特', '2', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2026-04-19 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (65, 'CUST000065', '内蒙古银行股份有限公司', '金融', '15', '呼和浩特', '1', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2026-04-21 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (66, 'CUST000066', '哈尔滨银行股份有限公司', '金融', '23', '哈尔滨', '1', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2026-04-17 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (67, 'CUST000067', '黑龙江省政务服务和大数据局', '政府', '23', '哈尔滨', '2', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2026-04-19 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (68, 'CUST000068', '吉林银行股份有限公司', '金融', '22', '长春', '1', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2026-04-21 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (69, 'CUST000069', '长春市数据局', '政府', '22', '长春', '2', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2026-04-23 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (70, 'CUST000070', '辽宁省人民医院', '医疗健康', '21', '沈阳', '3', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2026-04-25 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (71, 'CUST000071', '盛京银行股份有限公司', '金融', '21', '沈阳', '1', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2026-04-26 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (72, 'CUST000072', '东北大学', '教育', '21', '沈阳', '4', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2026-04-27 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (73, 'CUST000073', '浙江省人民医院', '医疗健康', '33', '杭州', '3', 'diyun', '狄云', '235', '华东-制造组', 'admin', '2026-04-28 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (74, 'CUST000074', '网易（杭州）网络有限公司', '制造', '33', '杭州', '5', 'diyun', '狄云', '235', '华东-制造组', 'admin', '2026-04-29 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (75, 'CUST000075', '山西省大数据应用局', '政府', '14', '太原', '2', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2026-04-30 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (76, 'CUST000076', '山西银行股份有限公司', '金融', '14', '太原', '1', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2026-05-01 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (77, 'CUST000077', '中国银行股份有限公司广东省分行', '金融', '44', '广州', '1', 'chenjialuo', '陈家洛', '236', '华南-金融组', 'admin', '2026-05-02 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (78, 'CUST000078', '广州市数据局', '政府', '44', '广州', '2', 'chenjialuo', '陈家洛', '237', '华南-政府组', 'admin', '2026-05-02 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (79, 'CUST000079', '深圳市数字政府研究院', '政府', '44', '深圳', '2', 'chenjialuo', '陈家洛', '237', '华南-政府组', 'admin', '2026-05-03 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (80, 'CUST000080', '中山大学', '教育', '44', '广州', '4', 'chenjialuo', '陈家洛', '236', '华南-金融组', 'admin', '2026-05-03 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (81, 'CUST000081', '福州银行股份有限公司', '金融', '35', '福州', '1', 'hufei', '胡斐', '233', '华东-金融组', 'admin', '2026-05-04 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (82, 'CUST000082', '福建省数字福建建设管理办公室', '政府', '35', '福州', '2', 'hufei', '胡斐', '233', '华东-金融组', 'admin', '2026-05-04 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (83, 'CUST000083', '厦门大学', '教育', '35', '厦门', '4', 'hufei', '胡斐', '233', '华东-金融组', 'admin', '2026-05-05 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (84, 'CUST000084', '贵阳银行股份有限公司', '金融', '52', '贵阳', '1', 'yangguo', '杨过', '238', '华西-政府组', 'admin', '2026-05-05 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (85, 'CUST000085', '云南省人民医院', '医疗健康', '53', '昆明', '3', 'yangguo', '杨过', '238', '华西-政府组', 'admin', '2026-05-06 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (86, 'CUST000086', '昆明市大数据局', '政府', '53', '昆明', '2', 'yangguo', '杨过', '238', '华西-政府组', 'admin', '2026-05-06 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (87, 'CUST000087', '中国太平洋保险（集团）股份有限公司', '金融', '31', '上海', '1', 'hufei', '胡斐', '233', '华东-金融组', 'admin', '2026-05-07 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (88, 'CUST000088', '国泰君安证券股份有限公司', '金融', '31', '上海', '1', 'hufei', '胡斐', '233', '华东-金融组', 'admin', '2026-05-07 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (89, 'CUST000089', '中国华能集团有限公司', '制造', '11', '北京', '7', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2026-05-08 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (90, 'CUST000090', '国家电网有限公司', '制造', '11', '北京', '7', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2026-05-08 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (91, 'CUST000091', '深圳证券交易所', '金融', '44', '深圳', '1', 'chenjialuo', '陈家洛', '236', '华南-金融组', 'admin', '2026-05-09 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (92, 'CUST000092', '上海证券交易所', '金融', '31', '上海', '1', 'hufei', '胡斐', '233', '华东-金融组', 'admin', '2026-05-09 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (93, 'CUST000093', '北京证券交易所', '金融', '11', '北京', '1', 'weixiaobao', '韦小宝', '231', '华北-金融组', 'admin', '2026-05-10 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (94, 'CUST000094', '武汉大学', '教育', '42', '武汉', '4', 'zhangwuji', '张无忌', '240', '华中-金融组', 'admin', '2026-05-10 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (95, 'CUST000095', '华中科技大学', '教育', '42', '武汉', '4', 'zhangwuji', '张无忌', '240', '华中-金融组', 'admin', '2026-05-10 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (96, 'CUST000096', '湖北省人民医院', '医疗健康', '42', '武汉', '3', 'zhangwuji', '张无忌', '241', '华中-政府组', 'admin', '2026-05-11 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (97, 'CUST000097', '长沙市卫生健康委员会', '政府', '43', '长沙', '3', 'zhangwuji', '张无忌', '241', '华中-政府组', 'admin', '2026-05-11 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (98, 'CUST000098', '中南大学湘雅医院', '医疗健康', '43', '长沙', '3', 'zhangwuji', '张无忌', '242', '华中-医疗组', 'admin', '2026-05-12 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (99, 'CUST000099', '成都市大数据和电子政务局', '政府', '51', '成都', '2', 'yangguo', '杨过', '239', '华西-制造组', 'admin', '2026-05-12 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (100, 'CUST000100', '重庆市大数据发展局', '政府', '50', '重庆', '2', 'yangguo', '杨过', '239', '华西-制造组', 'admin', '2026-05-12 07:20:07.970549', NULL, NULL, NULL);

-- ----------------------------
-- Table structure for by_opp_task
-- ----------------------------
DROP TABLE IF EXISTS "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task";
CREATE TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" (
  "id" int8 NOT NULL DEFAULT nextval('"{{DATACLOUD_DB_SCHEMA}}".by_opp_task_id_seq'::regclass),
  "customer_code" varchar(50) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "opp_code" varchar(50) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "product_code" varchar(50) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "task_type" char(1) COLLATE "pg_catalog"."default" NOT NULL DEFAULT '1'::bpchar,
  "initiator_user_id" varchar(100) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "handler_user_id" varchar(100) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "task_status" char(1) COLLATE "pg_catalog"."default" NOT NULL DEFAULT '1'::bpchar,
  "task_name" varchar(200) COLLATE "pg_catalog"."default" NOT NULL,
  "task_desc" text COLLATE "pg_catalog"."default",
  "handle_desc" text COLLATE "pg_catalog"."default",
  "initiate_time" timestamp(6),
  "plan_finish_time" timestamp(6),
  "actual_finish_time" timestamp(6),
  "create_by" varchar(64) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "create_time" timestamp(6),
  "update_by" varchar(64) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "update_time" timestamp(6),
  "remark" varchar(500) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying
)
;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."id" IS '主键';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."customer_code" IS '客户编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."opp_code" IS '商机编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."product_code" IS '产品编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."task_type" IS '任务类型(1线索获取 2方案交流 3商务报价 4商务应标 5商机签约 6应标复盘)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."initiator_user_id" IS '发起人用户编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."handler_user_id" IS '处理人用户编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."task_status" IS '任务状态(1处理中 2正常结束 3异常结束)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."task_name" IS '任务名称';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."task_desc" IS '任务描述';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."handle_desc" IS '处理描述';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."initiate_time" IS '发起时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."plan_finish_time" IS '计划完成时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."actual_finish_time" IS '实际完成时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."create_by" IS '创建者';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."create_time" IS '创建时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."update_by" IS '更新者';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."update_time" IS '更新时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."remark" IS '备注';
COMMENT ON TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" IS '商机任务表';

-- ----------------------------
-- Records of by_opp_task
-- ----------------------------
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (1, 'CUST000001', 'OPP00000001', 'WHALE_BI', '1', 'huangrong', 'weixiaobao', '2', '工行北京BI线索获取', NULL, NULL, '2025-11-06 00:00:00', '2025-11-21 00:00:00', '2025-11-21 00:00:00', 'admin', '2025-11-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (2, 'CUST000001', 'OPP00000001', 'WHALE_BI', '2', 'huangrong', 'weixiaobao', '2', '工行北京BI方案交流', NULL, NULL, '2025-11-23 00:00:00', '2025-12-16 00:00:00', '2025-12-16 00:00:00', 'admin', '2025-11-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (3, 'CUST000001', 'OPP00000001', 'WHALE_BI', '3', 'huangrong', 'weixiaobao', '2', '工行北京BI商务报价', NULL, NULL, '2025-12-17 00:00:00', '2025-12-26 00:00:00', '2025-12-25 00:00:00', 'admin', '2025-12-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (4, 'CUST000001', 'OPP00000001', 'WHALE_BI', '5', 'huangrong', 'weixiaobao', '2', '工行北京BI商机签约', NULL, NULL, '2025-12-26 00:00:00', '2026-01-06 00:00:00', '2026-01-06 00:00:00', 'admin', '2025-12-26 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (5, 'CUST000001', 'OPP00000002', 'WHALE_CRM', '1', 'zhaomin', 'weixiaobao', '2', '工行北京CRM线索获取', NULL, NULL, '2025-12-09 00:00:00', '2025-12-21 00:00:00', '2025-12-21 00:00:00', 'admin', '2025-12-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (6, 'CUST000001', 'OPP00000002', 'WHALE_CRM', '2', 'zhaomin', 'weixiaobao', '2', '工行北京CRM方案交流', NULL, NULL, '2025-12-22 00:00:00', '2026-01-16 00:00:00', '2026-01-16 00:00:00', 'admin', '2025-12-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (7, 'CUST000002', 'OPP00000003', 'WHALE_BI', '1', 'huangrong', 'weixiaobao', '2', '工行北京2-BI线索获取', NULL, NULL, '2025-11-04 00:00:00', '2025-11-19 00:00:00', '2025-11-19 00:00:00', 'admin', '2025-11-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (8, 'CUST000002', 'OPP00000003', 'WHALE_BI', '2', 'huangrong', 'weixiaobao', '2', '工行北京2-BI方案交流', NULL, NULL, '2025-11-20 00:00:00', '2025-12-11 00:00:00', '2025-12-11 00:00:00', 'admin', '2025-11-20 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (9, 'CUST000002', 'OPP00000003', 'WHALE_BI', '3', 'huangrong', 'weixiaobao', '2', '工行北京2-BI商务报价', NULL, NULL, '2025-12-12 00:00:00', '2026-01-21 00:00:00', '2026-01-21 00:00:00', 'admin', '2025-12-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (10, 'CUST000002', 'OPP00000003', 'WHALE_BI', '5', 'huangrong', 'weixiaobao', '2', '工行北京2-BI商机签约', NULL, NULL, '2026-01-22 00:00:00', '2026-01-29 00:00:00', '2026-01-29 00:00:00', 'admin', '2026-01-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (11, 'CUST000004', 'OPP00000004', 'WHALE_BI', '1', 'renyingying', 'hufei', '2', '招商银行BI线索', NULL, NULL, '2025-11-07 00:00:00', '2025-11-23 00:00:00', '2025-11-23 00:00:00', 'admin', '2025-11-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (12, 'CUST000004', 'OPP00000004', 'WHALE_BI', '2', 'renyingying', 'hufei', '2', '招商银行BI方案交流', NULL, NULL, '2025-11-24 00:00:00', '2025-12-13 00:00:00', '2025-12-13 00:00:00', 'admin', '2025-11-24 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (13, 'CUST000004', 'OPP00000004', 'WHALE_BI', '5', 'renyingying', 'hufei', '2', '招商银行BI签约', NULL, NULL, '2025-12-14 00:00:00', '2025-12-21 00:00:00', '2025-12-21 00:00:00', 'admin', '2025-12-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (14, 'CUST000005', 'OPP00000005', 'WHALE_CRM', '1', 'xiaolongnv', 'diyun', '2', '浦发银行CRM线索', NULL, NULL, '2025-12-05 00:00:00', '2025-12-21 00:00:00', '2025-12-21 00:00:00', 'admin', '2025-12-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (15, 'CUST000005', 'OPP00000005', 'WHALE_CRM', '3', 'xiaolongnv', 'diyun', '2', '浦发银行CRM报价', NULL, NULL, '2025-12-22 00:00:00', '2026-01-16 00:00:00', '2026-01-16 00:00:00', 'admin', '2025-12-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (16, 'CUST000006', 'OPP00000006', 'WHALE_CRM', '1', 'huangrong', 'chenjialuo', '2', '广州卫健CRM线索', NULL, NULL, '2025-11-09 00:00:00', '2025-11-26 00:00:00', '2025-11-26 00:00:00', 'admin', '2025-11-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (17, 'CUST000007', 'OPP00000007', 'WHALE_BI', '1', 'zhaomin', 'chenjialuo', '2', '广东人民医院BI线索', NULL, NULL, '2025-12-06 00:00:00', '2025-12-21 00:00:00', '2025-12-21 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (18, 'CUST000007', 'OPP00000007', 'WHALE_BI', '2', 'zhaomin', 'chenjialuo', '2', '广东人民医院BI方案', NULL, NULL, '2025-12-23 00:00:00', '2026-01-13 00:00:00', '2026-01-13 00:00:00', 'admin', '2025-12-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (19, 'CUST000008', 'OPP00000008', 'WHALE_BI', '1', 'wangyuyan', 'chenjialuo', '2', '平安银行BI线索', NULL, NULL, '2025-11-13 00:00:00', '2025-11-29 00:00:00', '2025-11-29 00:00:00', 'admin', '2025-11-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (20, 'CUST000008', 'OPP00000008', 'WHALE_BI', '2', 'wangyuyan', 'chenjialuo', '2', '平安银行BI方案交流', NULL, NULL, '2025-12-02 00:00:00', '2026-01-11 00:00:00', '2026-01-11 00:00:00', 'admin', '2025-12-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (21, 'CUST000009', 'OPP00000011', 'WHALE_CRM', '1', 'huoqingtong', 'yangguo', '2', '成都高新CRM线索', NULL, NULL, '2025-12-04 00:00:00', '2025-12-19 00:00:00', '2025-12-19 00:00:00', 'admin', '2025-12-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (22, 'CUST000009', 'OPP00000011', 'WHALE_CRM', '2', 'huoqingtong', 'yangguo', '2', '成都高新CRM方案', NULL, NULL, '2025-12-20 00:00:00', '2026-01-09 00:00:00', '2026-01-09 00:00:00', 'admin', '2025-12-20 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (23, 'CUST000010', 'OPP00000012', 'WHALE_BI', '1', 'miaoruolan', 'yangguo', '2', '川省教育BI线索', NULL, NULL, '2025-12-07 00:00:00', '2025-12-23 00:00:00', '2025-12-23 00:00:00', 'admin', '2025-12-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (24, 'CUST000011', 'OPP00000013', 'WHALE_BI', '1', 'huangrong', 'zhangwuji', '2', '武汉商行BI线索', NULL, NULL, '2025-12-10 00:00:00', '2025-12-26 00:00:00', '2025-12-26 00:00:00', 'admin', '2025-12-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (25, 'CUST000011', 'OPP00000013', 'WHALE_BI', '2', 'huangrong', 'zhangwuji', '2', '武汉商行BI方案', NULL, NULL, '2025-12-27 00:00:00', '2026-01-15 00:00:00', '2026-01-15 00:00:00', 'admin', '2025-12-27 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (26, 'CUST000011', 'OPP00000013', 'WHALE_BI', '5', 'huangrong', 'zhangwuji', '2', '武汉商行BI签约', NULL, NULL, '2026-01-16 00:00:00', '2026-01-23 00:00:00', '2026-01-23 00:00:00', 'admin', '2026-01-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (27, 'CUST000012', 'OPP00000014', 'WHALE_CRM', '1', 'zhaomin', 'zhangwuji', '2', '鄂省卫健CRM线索', NULL, NULL, '2025-12-05 00:00:00', '2025-12-21 00:00:00', '2025-12-21 00:00:00', 'admin', '2025-12-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (28, 'CUST000013', 'OPP00000015', 'WHALE_BI', '1', 'renyingying', 'hufei', '2', '南京银行BI线索', NULL, NULL, '2025-11-02 00:00:00', '2025-11-16 00:00:00', '2025-11-16 00:00:00', 'admin', '2025-11-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (29, 'CUST000013', 'OPP00000015', 'WHALE_BI', '2', 'renyingying', 'hufei', '2', '南京银行BI方案', NULL, NULL, '2025-11-17 00:00:00', '2025-12-06 00:00:00', '2025-12-06 00:00:00', 'admin', '2025-11-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (30, 'CUST000014', 'OPP00000017', 'WHALE_CRM', '1', 'xiaolongnv', 'diyun', '2', '苏省数据CRM线索', NULL, NULL, '2025-12-08 00:00:00', '2025-12-23 00:00:00', '2025-12-23 00:00:00', 'admin', '2025-12-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (31, 'CUST000016', 'OPP00000021', 'WHALE_DF', '1', 'wangyuyan', 'diyun', '2', '阿里巴巴DF线索', NULL, NULL, '2025-11-11 00:00:00', '2025-11-26 00:00:00', '2025-11-26 00:00:00', 'admin', '2025-11-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (32, 'CUST000016', 'OPP00000021', 'WHALE_DF', '2', 'wangyuyan', 'diyun', '2', '阿里巴巴DF方案', NULL, NULL, '2025-11-27 00:00:00', '2025-12-16 00:00:00', '2025-12-16 00:00:00', 'admin', '2025-11-27 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (33, 'CUST000016', 'OPP00000021', 'WHALE_DF', '3', 'wangyuyan', 'diyun', '2', '阿里巴巴DF报价', NULL, NULL, '2025-12-17 00:00:00', '2025-12-26 00:00:00', '2025-12-26 00:00:00', 'admin', '2025-12-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (34, 'CUST000016', 'OPP00000021', 'WHALE_DF', '5', 'wangyuyan', 'diyun', '2', '阿里巴巴DF签约', NULL, NULL, '2025-12-27 00:00:00', '2026-01-09 00:00:00', '2026-01-09 00:00:00', 'admin', '2025-12-27 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (35, 'CUST000018', 'OPP00000023', 'WHALE_DF', '1', 'huoqingtong', 'chenjialuo', '2', '腾讯DF线索', NULL, NULL, '2025-11-06 00:00:00', '2025-11-21 00:00:00', '2025-11-21 00:00:00', 'admin', '2025-11-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (36, 'CUST000018', 'OPP00000023', 'WHALE_DF', '2', 'huoqingtong', 'chenjialuo', '2', '腾讯DF方案', NULL, NULL, '2025-11-23 00:00:00', '2025-12-11 00:00:00', '2025-12-11 00:00:00', 'admin', '2025-11-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (37, 'CUST000020', 'OPP00000025', 'WHALE_DF', '1', 'miaoruolan', 'chenjialuo', '2', '华为DF线索', NULL, NULL, '2025-11-09 00:00:00', '2025-11-23 00:00:00', '2025-11-23 00:00:00', 'admin', '2025-11-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (38, 'CUST000020', 'OPP00000025', 'WHALE_DF', '2', 'miaoruolan', 'chenjialuo', '2', '华为DF方案', NULL, NULL, '2025-11-24 00:00:00', '2025-12-13 00:00:00', '2025-12-13 00:00:00', 'admin', '2025-11-24 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (39, 'CUST000020', 'OPP00000025', 'WHALE_DF', '3', 'miaoruolan', 'chenjialuo', '2', '华为DF报价', NULL, NULL, '2025-12-14 00:00:00', '2026-01-21 00:00:00', '2026-01-21 00:00:00', 'admin', '2025-12-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (40, 'CUST000020', 'OPP00000025', 'WHALE_DF', '5', 'miaoruolan', 'chenjialuo', '2', '华为DF签约', NULL, NULL, '2026-01-22 00:00:00', '2026-01-29 00:00:00', '2026-01-29 00:00:00', 'admin', '2026-01-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (41, 'CUST000021', 'OPP00000031', 'WHALE_BI', '1', 'huangrong', 'weixiaobao', '2', '建行天津BI线索', NULL, NULL, '2025-12-11 00:00:00', '2025-12-26 00:00:00', '2025-12-26 00:00:00', 'admin', '2025-12-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (42, 'CUST000021', 'OPP00000031', 'WHALE_BI', '2', 'huangrong', 'weixiaobao', '2', '建行天津BI方案', NULL, NULL, '2025-12-27 00:00:00', '2026-01-16 00:00:00', '2026-01-16 00:00:00', 'admin', '2025-12-27 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (43, 'CUST000022', 'OPP00000032', 'WHALE_BI', '1', 'zhaomin', 'weixiaobao', '2', '天津滨海BI线索', NULL, NULL, '2026-01-06 00:00:00', '2026-01-21 00:00:00', '2026-01-21 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (44, 'CUST000024', 'OPP00000035', 'WHALE_BI', '1', 'renyingying', 'zhangwuji', '2', '农行山东BI线索', NULL, NULL, '2025-12-04 00:00:00', '2025-12-19 00:00:00', '2025-12-19 00:00:00', 'admin', '2025-12-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (45, 'CUST000024', 'OPP00000035', 'WHALE_BI', '2', 'renyingying', 'zhangwuji', '2', '农行山东BI方案', NULL, NULL, '2025-12-20 00:00:00', '2026-01-09 00:00:00', '2026-01-09 00:00:00', 'admin', '2025-12-20 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (46, 'CUST000028', 'OPP00000041', 'WHALE_BI', '1', 'xiaolongnv', 'yangguo', '2', '重庆农商BI线索', NULL, NULL, '2026-01-09 00:00:00', '2026-01-23 00:00:00', '2026-01-23 00:00:00', 'admin', '2026-01-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (47, 'CUST000031', 'OPP00000046', 'WHALE_BI', '1', 'wangyuyan', 'hufei', '2', '厦门国际BI线索', NULL, NULL, '2026-01-03 00:00:00', '2026-01-16 00:00:00', '2026-01-16 00:00:00', 'admin', '2026-01-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (48, 'CUST000033', 'OPP00000049', 'WHALE_BI', '1', 'huoqingtong', 'diyun', '2', '苏州工业园BI线索', NULL, NULL, '2026-01-06 00:00:00', '2026-01-21 00:00:00', '2026-01-21 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (49, 'CUST000033', 'OPP00000049', 'WHALE_BI', '2', 'huoqingtong', 'diyun', '2', '苏州工业园BI方案', NULL, NULL, '2026-01-22 00:00:00', '2026-02-11 00:00:00', '2026-02-11 00:00:00', 'admin', '2026-01-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (50, 'CUST000035', 'OPP00000052', 'WHALE_BI', '1', 'miaoruolan', 'hufei', '2', '苏省人民医院BI线索', NULL, NULL, '2026-01-07 00:00:00', '2026-01-23 00:00:00', '2026-01-23 00:00:00', 'admin', '2026-01-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (51, 'CUST000039', 'OPP00000061', 'WHALE_BI', '1', 'huangrong', 'weixiaobao', '1', '北京银行BI线索', NULL, NULL, '2026-02-06 00:00:00', '2026-02-21 00:00:00', NULL, 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (52, 'CUST000039', 'OPP00000061', 'WHALE_BI', '2', 'huangrong', 'weixiaobao', '1', '北京银行BI方案交流', NULL, NULL, '2026-02-23 00:00:00', '2026-03-11 00:00:00', NULL, 'admin', '2026-02-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (53, 'CUST000040', 'OPP00000063', 'WHALE_BI', '1', 'zhaomin', 'weixiaobao', '1', '北京大数据BI线索', NULL, NULL, '2026-02-04 00:00:00', '2026-02-19 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (54, 'CUST000044', 'OPP00000067', 'WHALE_BI', '1', 'renyingying', 'chenjialuo', '2', '广州农商BI线索', NULL, NULL, '2025-12-07 00:00:00', '2025-12-21 00:00:00', '2025-12-21 00:00:00', 'admin', '2025-12-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (55, 'CUST000044', 'OPP00000067', 'WHALE_BI', '2', 'renyingying', 'chenjialuo', '2', '广州农商BI方案', NULL, NULL, '2025-12-23 00:00:00', '2026-01-13 00:00:00', '2026-01-13 00:00:00', 'admin', '2025-12-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (56, 'CUST000044', 'OPP00000067', 'WHALE_BI', '5', 'renyingying', 'chenjialuo', '2', '广州农商BI签约', NULL, NULL, '2026-01-14 00:00:00', '2026-01-21 00:00:00', '2026-01-21 00:00:00', 'admin', '2026-01-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (57, 'CUST000050', 'OPP00000073', 'WHALE_BI', '1', 'xiaolongnv', 'zhangwuji', '1', '长沙银行BI线索', NULL, NULL, '2026-03-09 00:00:00', '2026-03-23 00:00:00', NULL, 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (58, 'CUST000051', 'OPP00000075', 'WHALE_BI', '1', 'wangyuyan', 'zhangwuji', '1', '青岛银行BI线索', NULL, NULL, '2026-03-06 00:00:00', '2026-03-21 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (59, 'CUST000051', 'OPP00000075', 'WHALE_BI', '2', 'wangyuyan', 'zhangwuji', '1', '青岛银行BI方案', NULL, NULL, '2026-03-22 00:00:00', '2026-04-11 00:00:00', NULL, 'admin', '2026-03-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (60, 'CUST000055', 'OPP00000079', 'WHALE_BI', '1', 'huoqingtong', 'hufei', '1', '徽商银行BI线索', NULL, NULL, '2026-03-04 00:00:00', '2026-03-19 00:00:00', NULL, 'admin', '2026-03-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (61, 'CUST000057', 'OPP00000083', 'WHALE_CRM', '1', 'miaoruolan', 'diyun', '1', '江西银行CRM线索', NULL, NULL, '2026-03-11 00:00:00', '2026-03-26 00:00:00', NULL, 'admin', '2026-03-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (62, 'CUST000060', 'OPP00000086', 'WHALE_BI', '1', 'huangrong', 'chenjialuo', '1', '桂林银行BI线索', NULL, NULL, '2026-03-08 00:00:00', '2026-03-23 00:00:00', NULL, 'admin', '2026-03-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (63, 'CUST000063', 'OPP00000089', 'WHALE_CRM', '1', 'zhaomin', 'yangguo', '1', '宁夏银行CRM线索', NULL, NULL, '2026-04-06 00:00:00', '2026-04-21 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (64, 'CUST000065', 'OPP00000092', 'WHALE_BI', '1', 'renyingying', 'weixiaobao', '1', '内蒙古银行BI线索', NULL, NULL, '2026-04-09 00:00:00', '2026-04-23 00:00:00', NULL, 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (65, 'CUST000066', 'OPP00000094', 'WHALE_BI', '1', 'xiaolongnv', 'weixiaobao', '1', '哈尔滨银行BI线索', NULL, NULL, '2026-04-07 00:00:00', '2026-04-21 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (66, 'CUST000068', 'OPP00000096', 'WHALE_CRM', '1', 'wangyuyan', 'weixiaobao', '1', '吉林银行CRM线索', NULL, NULL, '2026-04-05 00:00:00', '2026-04-19 00:00:00', NULL, 'admin', '2026-04-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (67, 'CUST000071', 'OPP00000099', 'WHALE_BI', '1', 'huoqingtong', 'weixiaobao', '1', '盛京银行BI线索', NULL, NULL, '2026-04-10 00:00:00', '2026-04-25 00:00:00', NULL, 'admin', '2026-04-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (68, 'CUST000071', 'OPP00000099', 'WHALE_BI', '2', 'huoqingtong', 'weixiaobao', '1', '盛京银行BI方案', NULL, NULL, '2026-04-26 00:00:00', '2026-05-24 07:20:08.980334', NULL, 'admin', '2026-04-26 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (69, 'CUST000073', 'OPP00000101', 'WHALE_BI', '1', 'miaoruolan', 'diyun', '1', '浙省人民医院BI线索', NULL, NULL, '2026-04-04 00:00:00', '2026-04-19 00:00:00', NULL, 'admin', '2026-04-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (70, 'CUST000076', 'OPP00000104', 'WHALE_BI', '1', 'huangrong', 'weixiaobao', '1', '山西银行BI线索', NULL, NULL, '2026-04-22 07:20:08.980334', '2026-05-22 07:20:08.980334', NULL, 'admin', '2026-04-22 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (71, 'CUST000081', 'OPP00000107', 'WHALE_BI', '1', 'zhaomin', 'hufei', '2', '福州银行BI线索', NULL, NULL, '2025-12-03 00:00:00', '2025-12-16 00:00:00', '2025-12-16 00:00:00', 'admin', '2025-12-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (72, 'CUST000081', 'OPP00000107', 'WHALE_BI', '2', 'zhaomin', 'hufei', '2', '福州银行BI方案', NULL, NULL, '2025-12-17 00:00:00', '2026-01-06 00:00:00', '2026-01-06 00:00:00', 'admin', '2025-12-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (73, 'CUST000081', 'OPP00000107', 'WHALE_BI', '5', 'zhaomin', 'hufei', '2', '福州银行BI签约', NULL, NULL, '2026-01-07 00:00:00', '2026-01-13 00:00:00', '2026-01-13 00:00:00', 'admin', '2026-01-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (74, 'CUST000084', 'OPP00000110', 'WHALE_BI', '1', 'renyingying', 'yangguo', '1', '贵阳银行BI线索', NULL, NULL, '2026-04-17 07:20:08.980334', '2026-05-27 07:20:08.980334', NULL, 'admin', '2026-04-17 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (75, 'CUST000087', 'OPP00000113', 'WHALE_DF', '1', 'xiaolongnv', 'hufei', '1', '太平洋保险DF线索', NULL, NULL, '2026-04-06 00:00:00', '2026-04-21 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (76, 'CUST000087', 'OPP00000113', 'WHALE_DF', '2', 'xiaolongnv', 'hufei', '1', '太平洋保险DF方案', NULL, NULL, '2026-04-22 00:00:00', '2026-05-22 07:20:08.980334', NULL, 'admin', '2026-04-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (77, 'CUST000088', 'OPP00000116', 'WHALE_BI', '1', 'wangyuyan', 'hufei', '1', '国泰君安BI线索', NULL, NULL, '2026-04-04 00:00:00', '2026-04-19 00:00:00', NULL, 'admin', '2026-04-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (78, 'CUST000091', 'OPP00000119', 'WHALE_BI', '1', 'huoqingtong', 'chenjialuo', '1', '深交所BI线索', NULL, NULL, '2026-04-20 07:20:08.980334', '2026-05-24 07:20:08.980334', NULL, 'admin', '2026-04-20 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (79, 'CUST000092', 'OPP00000122', 'WHALE_DF', '1', 'miaoruolan', 'hufei', '1', '上交所DF线索', NULL, NULL, '2026-04-24 07:20:08.980334', '2026-05-20 07:20:08.980334', NULL, 'admin', '2026-04-24 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (80, 'CUST000093', 'OPP00000125', 'WHALE_BI', '1', 'huangrong', 'weixiaobao', '1', '北交所BI续签线索', NULL, NULL, '2026-04-27 07:20:08.980334', '2026-05-17 07:20:08.980334', NULL, 'admin', '2026-04-27 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (81, 'CUST000036', 'OPP00000128', 'WHALE_CRM', '1', 'zhaomin', 'hufei', '2', '上交大CRM线索', NULL, NULL, '2025-12-05 00:00:00', '2025-12-19 00:00:00', '2025-12-19 00:00:00', 'admin', '2025-12-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (82, 'CUST000036', 'OPP00000128', 'WHALE_CRM', '2', 'zhaomin', 'hufei', '2', '上交大CRM方案', NULL, NULL, '2025-12-20 00:00:00', '2026-01-09 00:00:00', '2026-01-09 00:00:00', 'admin', '2025-12-20 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (83, 'CUST000036', 'OPP00000128', 'WHALE_CRM', '5', 'zhaomin', 'hufei', '2', '上交大CRM签约', NULL, NULL, '2026-01-10 00:00:00', '2026-01-16 00:00:00', '2026-01-16 00:00:00', 'admin', '2026-01-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (84, 'CUST000043', 'OPP00000131', 'WHALE_MASS', '1', 'renyingying', 'chenjialuo', '2', '移动广东MASS线索', NULL, NULL, '2025-11-04 00:00:00', '2025-11-19 00:00:00', '2025-11-19 00:00:00', 'admin', '2025-11-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (85, 'CUST000043', 'OPP00000131', 'WHALE_MASS', '2', 'renyingying', 'chenjialuo', '2', '移动广东MASS方案', NULL, NULL, '2025-11-21 00:00:00', '2025-12-09 00:00:00', '2025-12-09 00:00:00', 'admin', '2025-11-21 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (86, 'CUST000043', 'OPP00000131', 'WHALE_MASS', '5', 'renyingying', 'chenjialuo', '2', '移动广东MASS签约', NULL, NULL, '2025-12-10 00:00:00', '2025-12-16 00:00:00', '2025-12-16 00:00:00', 'admin', '2025-12-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (87, 'CUST000072', 'OPP00000140', 'WHALE_BI', '1', 'xiaolongnv', 'weixiaobao', '2', '东北大学BI线索', NULL, NULL, '2026-01-07 00:00:00', '2026-01-21 00:00:00', '2026-01-21 00:00:00', 'admin', '2026-01-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (88, 'CUST000072', 'OPP00000140', 'WHALE_BI', '2', 'xiaolongnv', 'weixiaobao', '2', '东北大学BI方案', NULL, NULL, '2026-01-22 00:00:00', '2026-02-11 00:00:00', '2026-02-11 00:00:00', 'admin', '2026-01-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (89, 'CUST000074', 'OPP00000143', 'WHALE_DF', '1', 'wangyuyan', 'diyun', '1', '网易DF线索', NULL, NULL, '2026-03-06 00:00:00', '2026-03-21 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (90, 'CUST000074', 'OPP00000143', 'WHALE_DF', '2', 'wangyuyan', 'diyun', '1', '网易DF方案', NULL, NULL, '2026-03-22 00:00:00', '2026-04-11 00:00:00', NULL, 'admin', '2026-03-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (91, 'CUST000077', 'OPP00000147', 'WHALE_BI', '1', 'huoqingtong', 'chenjialuo', '1', '中行广东BI线索', NULL, NULL, '2026-04-09 00:00:00', '2026-04-23 00:00:00', NULL, 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (92, 'CUST000078', 'OPP00000149', 'WHALE_DF', '1', 'miaoruolan', 'chenjialuo', '1', '广州数据DF线索', NULL, NULL, '2026-04-05 00:00:00', '2026-04-19 00:00:00', NULL, 'admin', '2026-04-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (93, 'CUST000079', 'OPP00000151', 'WHALE_BI', '1', 'huangrong', 'chenjialuo', '1', '深圳数字政府BI线索', NULL, NULL, '2026-04-14 07:20:08.980334', '2026-05-30 07:20:08.980334', NULL, 'admin', '2026-04-14 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (94, 'CUST000080', 'OPP00000153', 'WHALE_CRM', '1', 'zhaomin', 'chenjialuo', '1', '中山大学CRM线索', NULL, NULL, '2026-04-18 07:20:08.980334', '2026-05-26 07:20:08.980334', NULL, 'admin', '2026-04-18 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (95, 'CUST000082', 'OPP00000155', 'WHALE_CRM', '1', 'renyingying', 'hufei', '1', '福建数字办CRM线索', NULL, NULL, '2026-04-22 07:20:08.980334', '2026-05-22 07:20:08.980334', NULL, 'admin', '2026-04-22 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (96, 'CUST000083', 'OPP00000157', 'WHALE_BI', '1', 'xiaolongnv', 'hufei', '1', '厦门大学BI线索', NULL, NULL, '2026-04-26 07:20:08.980334', '2026-05-18 07:20:08.980334', NULL, 'admin', '2026-04-26 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (97, 'CUST000086', 'OPP00000160', 'WHALE_BI', '1', 'wangyuyan', 'yangguo', '1', '昆明大数据BI线索', NULL, NULL, '2026-04-28 07:20:08.980334', '2026-05-16 07:20:08.980334', NULL, 'admin', '2026-04-28 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (98, 'CUST000089', 'OPP00000163', 'WHALE_DF', '1', 'huoqingtong', 'weixiaobao', '1', '华能集团DF线索', NULL, NULL, '2026-04-07 00:00:00', '2026-04-21 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (99, 'CUST000090', 'OPP00000166', 'WHALE_DF', '1', 'miaoruolan', 'weixiaobao', '1', '国家电网DF线索', NULL, NULL, '2026-04-14 07:20:08.980334', '2026-05-30 07:20:08.980334', NULL, 'admin', '2026-04-14 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (100, 'CUST000094', 'OPP00000169', 'WHALE_CRM', '1', 'huangrong', 'zhangwuji', '1', '武汉大学CRM线索', NULL, NULL, '2026-04-20 07:20:08.980334', '2026-05-24 07:20:08.980334', NULL, 'admin', '2026-04-20 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (101, 'CUST000095', 'OPP00000171', 'WHALE_BI', '1', 'zhaomin', 'zhangwuji', '1', '华中科大BI线索', NULL, NULL, '2026-04-24 07:20:08.980334', '2026-05-20 07:20:08.980334', NULL, 'admin', '2026-04-24 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (102, 'CUST000096', 'OPP00000173', 'WHALE_BI', '1', 'renyingying', 'zhangwuji', '1', '鄂省人民医院BI线索', NULL, NULL, '2026-04-28 07:20:08.980334', '2026-05-16 07:20:08.980334', NULL, 'admin', '2026-04-28 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (103, 'CUST000099', 'OPP00000175', 'WHALE_CRM', '1', 'xiaolongnv', 'yangguo', '1', '成都大数据CRM线索', NULL, NULL, '2026-05-02 07:20:08.980334', '2026-05-14 07:20:08.980334', NULL, 'admin', '2026-05-02 07:20:08.980334', NULL, NULL, NULL);

-- ----------------------------
-- Table structure for by_opportunity
-- ----------------------------
DROP TABLE IF EXISTS "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity";
CREATE TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" (
  "id" int8 NOT NULL DEFAULT nextval('"{{DATACLOUD_DB_SCHEMA}}".by_opportunity_id_seq'::regclass),
  "opp_code" varchar(50) COLLATE "pg_catalog"."default" NOT NULL,
  "opp_name" varchar(200) COLLATE "pg_catalog"."default" NOT NULL,
  "industry" varchar(100) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "domain" varchar(100) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "customer_code" varchar(50) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "sales_user_id" varchar(100) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "dept_id" varchar(50) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "product_code" varchar(50) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "opp_status" char(1) COLLATE "pg_catalog"."default" NOT NULL DEFAULT '1'::bpchar,
  "forecast_amount" numeric(18,2) DEFAULT NULL::numeric,
  "contract_amount" numeric(18,2) DEFAULT NULL::numeric,
  "forecast_rate" numeric(5,2) DEFAULT NULL::numeric,
  "fail_reason" varchar(500) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "success_summary" varchar(500) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "plan_sign_date" timestamp(0) DEFAULT NULL::timestamp without time zone,
  "actual_sign_date" timestamp(0) DEFAULT NULL::timestamp without time zone,
  "create_by" varchar(64) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "create_time" timestamp(6),
  "update_by" varchar(64) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "update_time" timestamp(6),
  "remark" varchar(500) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying
)
;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."id" IS '主键';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."opp_code" IS '商机编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."opp_name" IS '商机名称';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."industry" IS '所属行业';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."domain" IS '所属领域';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."customer_code" IS '所属客户编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."sales_user_id" IS '所属销售用户编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."dept_id" IS '所属组织编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."product_code" IS '所属产品编码(dict_type: product)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."opp_status" IS '商机状态(1线索获取 2方案交流 3商务报价 4签约成功 5签约失败)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."forecast_amount" IS '预测金额';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."contract_amount" IS '签约金额';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."forecast_rate" IS '预测成功率(%)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."fail_reason" IS '签约失败原因描述';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."success_summary" IS '签约成功总结';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."plan_sign_date" IS '计划签约日期(YYYY-MM-DD)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."actual_sign_date" IS '实际签约日期(YYYY-MM-DD)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."create_by" IS '创建者';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."create_time" IS '创建时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."update_by" IS '更新者';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."update_time" IS '更新时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."remark" IS '备注';
COMMENT ON TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" IS '商机信息表';

-- ----------------------------
-- Records of by_opportunity
-- ----------------------------
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (1, 'OPP00000001', '国投中债-BI-项目', '金融', '1', 'CUST000001', 'weixiaobao', '231', 'WHALE_BI', '4', 1200000.00, 1100000.00, 100.00, NULL, '产品功能契合度高', '2025-12-01 00:00:00', '2025-12-01 00:00:00', 'admin', '2025-11-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (2, 'OPP00000002', '国投中债-CRM-项目', '金融', '1', 'CUST000001', 'weixiaobao', '231', 'WHALE_CRM', '2', 800000.00, NULL, 35.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-01-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (3, 'OPP00000003', '国投中债-数据工厂-项目', '金融', '1', 'CUST000001', 'weixiaobao', '231', 'WHALE_DF', '1', 500000.00, NULL, 15.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-03-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (4, 'OPP00000004', '工行北京-BI-项目', '金融', '1', 'CUST000002', 'weixiaobao', '231', 'WHALE_BI', '4', 2500000.00, 2300000.00, 100.00, NULL, '价格优势明显', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-11-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (5, 'OPP00000005', '工行北京-数据工厂-项目', '金融', '1', 'CUST000002', 'weixiaobao', '231', 'WHALE_DF', '3', 1800000.00, NULL, 60.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (6, 'OPP00000006', '工行北京-MASS-项目', '金融', '1', 'CUST000002', 'weixiaobao', '231', 'WHALE_MASS', '5', 600000.00, NULL, 0.00, '竞品价格更低', NULL, '2026-02-01 00:00:00', NULL, 'admin', '2025-12-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (7, 'OPP00000007', '海淀政府-CRM-项目', '政府', '2', 'CUST000003', 'diyun', '234', 'WHALE_CRM', '4', 900000.00, 850000.00, 100.00, NULL, '售前响应及时', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-11-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (8, 'OPP00000008', '海淀政府-BI-项目', '政府', '2', 'CUST000003', 'diyun', '234', 'WHALE_BI', '2', 1200000.00, NULL, 40.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (9, 'OPP00000009', '海淀政府-智能体-项目', '政府', '2', 'CUST000003', 'diyun', '234', 'WHALE_AGENT', '1', 300000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (10, 'OPP00000010', '招行上海-BI-项目', '金融', '1', 'CUST000004', 'hufei', '233', 'WHALE_BI', '4', 3000000.00, 2800000.00, 100.00, NULL, '客户关系维护良好', '2025-12-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-11-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (11, 'OPP00000011', '招行上海-数据工厂-项目', '金融', '1', 'CUST000004', 'hufei', '233', 'WHALE_DF', '3', 2000000.00, NULL, 55.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-01-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (12, 'OPP00000012', '招行上海-CRM-项目', '金融', '1', 'CUST000004', 'hufei', '233', 'WHALE_CRM', '5', 800000.00, NULL, 0.00, '客户预算缩减', NULL, '2026-03-01 00:00:00', NULL, 'admin', '2026-01-19 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (13, 'OPP00000013', '浦发银行-BI-项目', '金融', '1', 'CUST000005', 'hufei', '233', 'WHALE_BI', '4', 1500000.00, 1400000.00, 100.00, NULL, '产品功能契合度高', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-11-20 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (14, 'OPP00000014', '浦发银行-MASS-项目', '金融', '1', 'CUST000005', 'hufei', '233', 'WHALE_MASS', '2', 700000.00, NULL, 30.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (15, 'OPP00000015', '浦发银行-智能体-项目', '金融', '1', 'CUST000005', 'hufei', '233', 'WHALE_AGENT', '1', 400000.00, NULL, 15.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (16, 'OPP00000016', '天河卫健-CRM-项目', '政府', '3', 'CUST000006', 'chenjialuo', '236', 'WHALE_CRM', '4', 600000.00, 580000.00, 100.00, NULL, '售前响应及时', '2025-12-01 00:00:00', '2025-12-01 00:00:00', 'admin', '2025-11-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (17, 'OPP00000017', '天河卫健-BI-项目', '政府', '3', 'CUST000006', 'chenjialuo', '236', 'WHALE_BI', '3', 900000.00, NULL, 65.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (18, 'OPP00000018', '天河卫健-数据工厂-项目', '政府', '3', 'CUST000006', 'chenjialuo', '236', 'WHALE_DF', '1', 500000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (19, 'OPP00000019', '粤省人民医院-BI-项目', '医疗健康', '3', 'CUST000007', 'chenjialuo', '236', 'WHALE_BI', '4', 1100000.00, 1050000.00, 100.00, NULL, '价格优势明显', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-11-24 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (20, 'OPP00000020', '粤省人民医院-CRM-项目', '医疗健康', '3', 'CUST000007', 'chenjialuo', '236', 'WHALE_CRM', '2', 700000.00, NULL, 35.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (21, 'OPP00000021', '粤省人民医院-智能体-项目', '医疗健康', '3', 'CUST000007', 'chenjialuo', '236', 'WHALE_AGENT', '5', 300000.00, NULL, 0.00, '产品功能不满足', NULL, '2026-03-01 00:00:00', NULL, 'admin', '2026-02-21 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (22, 'OPP00000022', '平安银行-BI-项目', '金融', '1', 'CUST000008', 'chenjialuo', '236', 'WHALE_BI', '4', 2000000.00, 1900000.00, 100.00, NULL, '客户关系维护良好', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (23, 'OPP00000023', '平安银行-数据工厂-项目', '金融', '1', 'CUST000008', 'chenjialuo', '236', 'WHALE_DF', '3', 1200000.00, NULL, 50.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (24, 'OPP00000024', '平安银行-MASS-项目', '金融', '1', 'CUST000008', 'chenjialuo', '236', 'WHALE_MASS', '1', 600000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (25, 'OPP00000025', '成都高新-CRM-项目', '政府', '2', 'CUST000009', 'yangguo', '238', 'WHALE_CRM', '4', 750000.00, 720000.00, 100.00, NULL, '产品功能契合度高', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (26, 'OPP00000026', '成都高新-BI-项目', '政府', '2', 'CUST000009', 'yangguo', '238', 'WHALE_BI', '2', 900000.00, NULL, 30.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (27, 'OPP00000027', '成都高新-数据工厂-项目', '政府', '2', 'CUST000009', 'yangguo', '238', 'WHALE_DF', '1', 400000.00, NULL, 15.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (28, 'OPP00000028', '川省教育厅-BI-项目', '政府', '4', 'CUST000010', 'yangguo', '238', 'WHALE_BI', '4', 800000.00, 780000.00, 100.00, NULL, '售前响应及时', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2025-12-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (29, 'OPP00000029', '川省教育厅-智能体-项目', '政府', '4', 'CUST000010', 'yangguo', '238', 'WHALE_AGENT', '3', 350000.00, NULL, 55.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (30, 'OPP00000030', '川省教育厅-CRM-项目', '政府', '4', 'CUST000010', 'yangguo', '238', 'WHALE_CRM', '5', 500000.00, NULL, 0.00, '客户内部决策未通过', NULL, '2026-03-01 00:00:00', NULL, 'admin', '2026-01-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (31, 'OPP00000031', '武汉商行-BI-项目', '金融', '1', 'CUST000011', 'zhangwuji', '240', 'WHALE_BI', '4', 1300000.00, 1250000.00, 100.00, NULL, '价格优势明显', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (32, 'OPP00000032', '武汉商行-数据工厂-项目', '金融', '1', 'CUST000011', 'zhangwuji', '240', 'WHALE_DF', '2', 900000.00, NULL, 40.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (33, 'OPP00000033', '武汉商行-MASS-项目', '金融', '1', 'CUST000011', 'zhangwuji', '240', 'WHALE_MASS', '1', 400000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (34, 'OPP00000034', '鄂省卫健-CRM-项目', '政府', '3', 'CUST000012', 'zhangwuji', '240', 'WHALE_CRM', '4', 700000.00, 680000.00, 100.00, NULL, '客户关系维护良好', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (35, 'OPP00000035', '鄂省卫健-BI-项目', '政府', '3', 'CUST000012', 'zhangwuji', '240', 'WHALE_BI', '3', 1000000.00, NULL, 60.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (36, 'OPP00000036', '鄂省卫健-智能体-项目', '政府', '3', 'CUST000012', 'zhangwuji', '240', 'WHALE_AGENT', '5', 300000.00, NULL, 0.00, '需求变更搁置', NULL, '2026-03-01 00:00:00', NULL, 'admin', '2026-01-21 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (37, 'OPP00000037', '南京银行-BI-项目', '金融', '1', 'CUST000013', 'hufei', '233', 'WHALE_BI', '4', 1600000.00, 1520000.00, 100.00, NULL, '产品功能契合度高', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (38, 'OPP00000038', '南京银行-CRM-项目', '金融', '1', 'CUST000013', 'hufei', '233', 'WHALE_CRM', '2', 800000.00, NULL, 35.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (39, 'OPP00000039', '南京银行-数据工厂-项目', '金融', '1', 'CUST000013', 'hufei', '233', 'WHALE_DF', '1', 600000.00, NULL, 15.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (40, 'OPP00000040', '苏省数据-CRM-项目', '政府', '2', 'CUST000014', 'diyun', '234', 'WHALE_CRM', '4', 900000.00, 870000.00, 100.00, NULL, '售前响应及时', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2025-12-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (41, 'OPP00000041', '苏省数据-BI-项目', '政府', '2', 'CUST000014', 'diyun', '234', 'WHALE_BI', '3', 1100000.00, NULL, 55.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (42, 'OPP00000042', '苏省数据-智能体-项目', '政府', '2', 'CUST000014', 'diyun', '234', 'WHALE_AGENT', '1', 350000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (43, 'OPP00000043', '浙大-BI-项目', '教育', '4', 'CUST000015', 'diyun', '234', 'WHALE_BI', '4', 700000.00, 680000.00, 100.00, NULL, '价格优势明显', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2025-12-18 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (44, 'OPP00000044', '浙大-智能体-项目', '教育', '4', 'CUST000015', 'diyun', '234', 'WHALE_AGENT', '2', 400000.00, NULL, 40.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (45, 'OPP00000045', '浙大-CRM-项目', '教育', '4', 'CUST000015', 'diyun', '234', 'WHALE_CRM', '5', 300000.00, NULL, 0.00, '客户预算缩减', NULL, '2026-03-01 00:00:00', NULL, 'admin', '2026-01-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (46, 'OPP00000046', '阿里巴巴-数据工厂-项目', '制造', '5', 'CUST000016', 'diyun', '234', 'WHALE_DF', '4', 4000000.00, 3800000.00, 100.00, NULL, '客户关系维护良好', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-20 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (47, 'OPP00000047', '阿里巴巴-BI-项目', '制造', '5', 'CUST000016', 'diyun', '234', 'WHALE_BI', '3', 2000000.00, NULL, 65.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (48, 'OPP00000048', '阿里巴巴-MASS-项目', '制造', '5', 'CUST000016', 'diyun', '234', 'WHALE_MASS', '1', 800000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (49, 'OPP00000049', '宁波银行-BI-项目', '金融', '1', 'CUST000017', 'hufei', '233', 'WHALE_BI', '4', 1400000.00, 1350000.00, 100.00, NULL, '产品功能契合度高', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2025-12-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (50, 'OPP00000050', '宁波银行-数据工厂-项目', '金融', '1', 'CUST000017', 'hufei', '233', 'WHALE_DF', '2', 900000.00, NULL, 40.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (51, 'OPP00000051', '腾讯-数据工厂-项目', '制造', '5', 'CUST000018', 'chenjialuo', '236', 'WHALE_DF', '4', 5000000.00, 4800000.00, 100.00, NULL, '客户关系维护良好', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-24 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (52, 'OPP00000052', '腾讯-BI-项目', '制造', '5', 'CUST000018', 'chenjialuo', '236', 'WHALE_BI', '3', 2500000.00, NULL, 60.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (53, 'OPP00000053', '腾讯-智能体-项目', '制造', '5', 'CUST000018', 'chenjialuo', '236', 'WHALE_AGENT', '2', 800000.00, NULL, 45.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (54, 'OPP00000054', '越秀教育-CRM-项目', '政府', '4', 'CUST000019', 'chenjialuo', '236', 'WHALE_CRM', '4', 500000.00, 480000.00, 100.00, NULL, '售前响应及时', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2025-12-26 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (55, 'OPP00000055', '越秀教育-BI-项目', '政府', '4', 'CUST000019', 'chenjialuo', '236', 'WHALE_BI', '1', 700000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-03-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (56, 'OPP00000056', '越秀教育-智能体-项目', '政府', '4', 'CUST000019', 'chenjialuo', '236', 'WHALE_AGENT', '5', 300000.00, NULL, 0.00, '竞品价格更低', NULL, '2026-03-01 00:00:00', NULL, 'admin', '2026-01-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (57, 'OPP00000057', '华为-数据工厂-项目', '制造', '5', 'CUST000020', 'chenjialuo', '236', 'WHALE_DF', '4', 8000000.00, 7500000.00, 100.00, NULL, '产品功能契合度高', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-28 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (58, 'OPP00000058', '华为-BI-项目', '制造', '5', 'CUST000020', 'chenjialuo', '236', 'WHALE_BI', '3', 3000000.00, NULL, 65.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (59, 'OPP00000059', '华为-MASS-项目', '制造', '5', 'CUST000020', 'chenjialuo', '236', 'WHALE_MASS', '1', 1000000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (60, 'OPP00000060', '建行天津-BI-项目', '金融', '1', 'CUST000021', 'weixiaobao', '231', 'WHALE_BI', '4', 1800000.00, 1700000.00, 100.00, NULL, '价格优势明显', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-29 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (61, 'OPP00000061', '建行天津-CRM-项目', '金融', '1', 'CUST000021', 'weixiaobao', '231', 'WHALE_CRM', '2', 900000.00, NULL, 35.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (62, 'OPP00000062', '建行天津-数据工厂-项目', '金融', '1', 'CUST000021', 'weixiaobao', '231', 'WHALE_DF', '5', 700000.00, NULL, 0.00, '客户内部决策未通过', NULL, '2026-03-01 00:00:00', NULL, 'admin', '2026-01-19 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (63, 'OPP00000063', '天津滨海-BI-项目', '政府', '2', 'CUST000022', 'weixiaobao', '231', 'WHALE_BI', '4', 1000000.00, 950000.00, 100.00, NULL, '客户关系维护良好', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (64, 'OPP00000064', '天津滨海-CRM-项目', '政府', '2', 'CUST000022', 'weixiaobao', '231', 'WHALE_CRM', '3', 600000.00, NULL, 55.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (65, 'OPP00000065', '天津滨海-智能体-项目', '政府', '2', 'CUST000022', 'weixiaobao', '231', 'WHALE_AGENT', '1', 250000.00, NULL, 15.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (66, 'OPP00000066', '农行山东-BI-项目', '金融', '1', 'CUST000024', 'zhangwuji', '240', 'WHALE_BI', '4', 2200000.00, 2100000.00, 100.00, NULL, '产品功能契合度高', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (67, 'OPP00000067', '农行山东-数据工厂-项目', '金融', '1', 'CUST000024', 'zhangwuji', '240', 'WHALE_DF', '2', 1500000.00, NULL, 40.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (68, 'OPP00000068', '山东省人民医院-CRM-项目', '医疗健康', '3', 'CUST000025', 'zhangwuji', '240', 'WHALE_CRM', '4', 700000.00, 670000.00, 100.00, NULL, '售前响应及时', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (69, 'OPP00000069', '山东省人民医院-BI-项目', '医疗健康', '3', 'CUST000025', 'zhangwuji', '240', 'WHALE_BI', '1', 900000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (70, 'OPP00000070', '郑州银行-BI-项目', '金融', '1', 'CUST000026', 'zhangwuji', '240', 'WHALE_BI', '4', 1200000.00, 1150000.00, 100.00, NULL, '价格优势明显', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (71, 'OPP00000071', '郑州银行-CRM-项目', '金融', '1', 'CUST000026', 'zhangwuji', '240', 'WHALE_CRM', '3', 700000.00, NULL, 60.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (72, 'OPP00000072', '豫省卫健-CRM-项目', '政府', '3', 'CUST000027', 'zhangwuji', '240', 'WHALE_CRM', '4', 650000.00, 620000.00, 100.00, NULL, '客户关系维护良好', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (73, 'OPP00000073', '豫省卫健-数据工厂-项目', '政府', '3', 'CUST000027', 'zhangwuji', '240', 'WHALE_DF', '5', 500000.00, NULL, 0.00, '需求变更搁置', NULL, '2026-03-01 00:00:00', NULL, 'admin', '2026-01-25 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (74, 'OPP00000074', '重庆农商-BI-项目', '金融', '1', 'CUST000028', 'yangguo', '238', 'WHALE_BI', '4', 1600000.00, 1520000.00, 100.00, NULL, '产品功能契合度高', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (75, 'OPP00000075', '重庆农商-数据工厂-项目', '金融', '1', 'CUST000028', 'yangguo', '238', 'WHALE_DF', '2', 1000000.00, NULL, 40.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (76, 'OPP00000076', '贵州大数据-CRM-项目', '政府', '2', 'CUST000029', 'yangguo', '238', 'WHALE_CRM', '4', 800000.00, 760000.00, 100.00, NULL, '售前响应及时', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-18 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (77, 'OPP00000077', '贵州大数据-BI-项目', '政府', '2', 'CUST000029', 'yangguo', '238', 'WHALE_BI', '1', 1000000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (78, 'OPP00000078', '云南数字-CRM-项目', '政府', '2', 'CUST000030', 'yangguo', '238', 'WHALE_CRM', '4', 700000.00, 680000.00, 100.00, NULL, '价格优势明显', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-20 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (79, 'OPP00000079', '厦门国际银行-BI-项目', '金融', '1', 'CUST000031', 'hufei', '233', 'WHALE_BI', '4', 1200000.00, 1150000.00, 100.00, NULL, '客户关系维护良好', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (80, 'OPP00000080', '厦门国际银行-CRM-项目', '金融', '1', 'CUST000031', 'hufei', '233', 'WHALE_CRM', '2', 700000.00, NULL, 35.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (81, 'OPP00000081', '闽医科大-CRM-项目', '医疗健康', '3', 'CUST000032', 'hufei', '233', 'WHALE_CRM', '4', 600000.00, 580000.00, 100.00, NULL, '产品功能契合度高', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-24 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (82, 'OPP00000082', '苏州工业园-BI-项目', '政府', '2', 'CUST000033', 'diyun', '234', 'WHALE_BI', '4', 1300000.00, 1250000.00, 100.00, NULL, '售前响应及时', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-26 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (83, 'OPP00000083', '无锡大数据-CRM-项目', '政府', '2', 'CUST000034', 'diyun', '234', 'WHALE_CRM', '4', 750000.00, 720000.00, 100.00, NULL, '价格优势明显', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (84, 'OPP00000084', '无锡大数据-BI-项目', '政府', '2', 'CUST000034', 'diyun', '234', 'WHALE_BI', '3', 900000.00, NULL, 55.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (85, 'OPP00000085', '苏省人民医院-BI-项目', '医疗健康', '3', 'CUST000035', 'hufei', '233', 'WHALE_BI', '4', 1100000.00, 1050000.00, 100.00, NULL, '客户关系维护良好', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (86, 'OPP00000086', '上海交大-智能体-项目', '教育', '4', 'CUST000036', 'hufei', '233', 'WHALE_AGENT', '4', 500000.00, 480000.00, 100.00, NULL, '产品功能契合度高', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (87, 'OPP00000087', '上海大数据-CRM-项目', '政府', '2', 'CUST000037', 'diyun', '234', 'WHALE_CRM', '4', 1200000.00, 1150000.00, 100.00, NULL, '价格优势明显', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (88, 'OPP00000088', '中国电信上海-MASS-项目', '制造', '9', 'CUST000038', 'diyun', '234', 'WHALE_MASS', '4', 2000000.00, 1900000.00, 100.00, NULL, '售前响应及时', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (89, 'OPP00000089', '北京银行-BI-项目', '金融', '1', 'CUST000039', 'weixiaobao', '231', 'WHALE_BI', '4', 1500000.00, 1420000.00, 100.00, NULL, '客户关系维护良好', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (90, 'OPP00000090', '北京市大数据-CRM-项目', '政府', '2', 'CUST000040', 'weixiaobao', '231', 'WHALE_CRM', '4', 900000.00, 870000.00, 100.00, NULL, '产品功能契合度高', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (91, 'OPP00000091', '北京协和-BI-项目', '医疗健康', '3', 'CUST000041', 'weixiaobao', '231', 'WHALE_BI', '3', 1400000.00, NULL, 60.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-03-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (92, 'OPP00000092', '中国电建-数据工厂-项目', '制造', '7', 'CUST000042', 'weixiaobao', '231', 'WHALE_DF', '4', 3000000.00, 2800000.00, 100.00, NULL, '价格优势明显', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-18 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (93, 'OPP00000093', '中移动广东-MASS-项目', '制造', '9', 'CUST000043', 'chenjialuo', '236', 'WHALE_MASS', '4', 2500000.00, 2400000.00, 100.00, NULL, '售前响应及时', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-20 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (94, 'OPP00000094', '广州农商-BI-项目', '金融', '1', 'CUST000044', 'chenjialuo', '236', 'WHALE_BI', '4', 1700000.00, 1620000.00, 100.00, NULL, '客户关系维护良好', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (95, 'OPP00000095', '广州农商-CRM-项目', '金融', '1', 'CUST000044', 'chenjialuo', '236', 'WHALE_CRM', '2', 900000.00, NULL, 35.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (96, 'OPP00000096', '海南大数据-CRM-项目', '政府', '2', 'CUST000045', 'chenjialuo', '236', 'WHALE_CRM', '3', 700000.00, NULL, 55.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-03-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (97, 'OPP00000097', '西安银行-BI-项目', '金融', '1', 'CUST000046', 'yangguo', '238', 'WHALE_BI', '4', 1100000.00, 1050000.00, 100.00, NULL, '产品功能契合度高', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (98, 'OPP00000098', '陕西数字-CRM-项目', '政府', '2', 'CUST000047', 'yangguo', '238', 'WHALE_CRM', '2', 800000.00, NULL, 40.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (99, 'OPP00000099', '川省人民医院-BI-项目', '医疗健康', '3', 'CUST000048', 'yangguo', '238', 'WHALE_BI', '1', 1000000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (100, 'OPP00000100', '湖南大数据-CRM-项目', '政府', '2', 'CUST000049', 'zhangwuji', '240', 'WHALE_CRM', '4', 850000.00, 820000.00, 100.00, NULL, '价格优势明显', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (101, 'OPP00000101', '长沙银行-BI-项目', '金融', '1', 'CUST000050', 'zhangwuji', '240', 'WHALE_BI', '4', 1300000.00, 1250000.00, 100.00, NULL, '售前响应及时', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (102, 'OPP00000102', '青岛银行-BI-项目', '金融', '1', 'CUST000051', 'zhangwuji', '240', 'WHALE_BI', '3', 1100000.00, NULL, 60.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (103, 'OPP00000103', '济南大数据-CRM-项目', '政府', '2', 'CUST000052', 'zhangwuji', '240', 'WHALE_CRM', '2', 700000.00, NULL, 30.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (104, 'OPP00000104', '合肥数据-CRM-项目', '政府', '2', 'CUST000053', 'hufei', '233', 'WHALE_CRM', '4', 750000.00, 720000.00, 100.00, NULL, '客户关系维护良好', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (105, 'OPP00000105', '安徽省立医院-BI-项目', '医疗健康', '3', 'CUST000054', 'hufei', '233', 'WHALE_BI', '3', 900000.00, NULL, 50.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (106, 'OPP00000106', '徽商银行-BI-项目', '金融', '1', 'CUST000055', 'hufei', '233', 'WHALE_BI', '4', 1200000.00, 1150000.00, 100.00, NULL, '产品功能契合度高', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (107, 'OPP00000107', '南昌政务-CRM-项目', '政府', '2', 'CUST000056', 'hufei', '233', 'WHALE_CRM', '1', 600000.00, NULL, 20.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (108, 'OPP00000108', '江西银行-BI-项目', '金融', '1', 'CUST000057', 'diyun', '234', 'WHALE_BI', '4', 1000000.00, 960000.00, 100.00, NULL, '价格优势明显', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (109, 'OPP00000109', '南宁大数据-CRM-项目', '政府', '2', 'CUST000058', 'chenjialuo', '236', 'WHALE_CRM', '3', 700000.00, NULL, 55.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (110, 'OPP00000110', '广西人民医院-BI-项目', '医疗健康', '3', 'CUST000059', 'chenjialuo', '236', 'WHALE_BI', '4', 800000.00, 760000.00, 100.00, NULL, '客户关系维护良好', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (111, 'OPP00000111', '桂林银行-BI-项目', '金融', '1', 'CUST000060', 'chenjialuo', '236', 'WHALE_BI', '2', 900000.00, NULL, 35.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (112, 'OPP00000112', '兰州银行-BI-项目', '金融', '1', 'CUST000061', 'yangguo', '238', 'WHALE_BI', '4', 1000000.00, 960000.00, 100.00, NULL, '产品功能契合度高', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (113, 'OPP00000113', '甘肃数据-CRM-项目', '政府', '2', 'CUST000062', 'yangguo', '238', 'WHALE_CRM', '1', 600000.00, NULL, 20.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (114, 'OPP00000114', '宁夏银行-BI-项目', '金融', '1', 'CUST000063', 'yangguo', '238', 'WHALE_BI', '3', 800000.00, NULL, 50.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (115, 'OPP00000115', '内蒙古大数据-CRM-项目', '政府', '2', 'CUST000064', 'weixiaobao', '231', 'WHALE_CRM', '4', 700000.00, 670000.00, 100.00, NULL, '售前响应及时', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (116, 'OPP00000116', '内蒙古银行-BI-项目', '金融', '1', 'CUST000065', 'weixiaobao', '231', 'WHALE_BI', '2', 900000.00, NULL, 35.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (117, 'OPP00000117', '哈尔滨银行-BI-项目', '金融', '1', 'CUST000066', 'weixiaobao', '231', 'WHALE_BI', '4', 1100000.00, 1050000.00, 100.00, NULL, '价格优势明显', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-04-18 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (118, 'OPP00000118', '黑龙江政务-CRM-项目', '政府', '2', 'CUST000067', 'weixiaobao', '231', 'WHALE_CRM', '3', 700000.00, NULL, 55.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-20 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (119, 'OPP00000119', '吉林银行-BI-项目', '金融', '1', 'CUST000068', 'weixiaobao', '231', 'WHALE_BI', '4', 1000000.00, 950000.00, 100.00, NULL, '客户关系维护良好', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-04-22 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (120, 'OPP00000120', '长春大数据-CRM-项目', '政府', '2', 'CUST000069', 'weixiaobao', '231', 'WHALE_CRM', '1', 600000.00, NULL, 20.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-24 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (121, 'OPP00000121', '辽宁人民医院-BI-项目', '医疗健康', '3', 'CUST000070', 'weixiaobao', '231', 'WHALE_BI', '3', 900000.00, NULL, 50.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-26 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (122, 'OPP00000122', '盛京银行-BI-项目', '金融', '1', 'CUST000071', 'weixiaobao', '231', 'WHALE_BI', '4', 1200000.00, 1150000.00, 100.00, NULL, '产品功能契合度高', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-04-27 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (123, 'OPP00000123', '东北大学-智能体-项目', '教育', '4', 'CUST000072', 'weixiaobao', '231', 'WHALE_AGENT', '2', 400000.00, NULL, 40.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-28 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (124, 'OPP00000124', '浙江人民医院-CRM-项目', '医疗健康', '3', 'CUST000073', 'diyun', '235', 'WHALE_CRM', '4', 700000.00, 670000.00, 100.00, NULL, '售前响应及时', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-04-29 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (125, 'OPP00000125', '网易-数据工厂-项目', '制造', '5', 'CUST000074', 'diyun', '235', 'WHALE_DF', '3', 3000000.00, NULL, 60.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-30 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (126, 'OPP00000126', '山西大数据-CRM-项目', '政府', '2', 'CUST000075', 'weixiaobao', '231', 'WHALE_CRM', '1', 600000.00, NULL, 20.00, NULL, NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-05-01 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (127, 'OPP00000127', '山西银行-BI-项目', '金融', '1', 'CUST000076', 'weixiaobao', '231', 'WHALE_BI', '2', 900000.00, NULL, 35.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-05-02 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (128, 'OPP00000128', '中行广东-BI-项目', '金融', '1', 'CUST000077', 'chenjialuo', '236', 'WHALE_BI', '4', 2500000.00, 2400000.00, 100.00, NULL, '价格优势明显', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-03 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (129, 'OPP00000129', '广州市数据-CRM-项目', '政府', '2', 'CUST000078', 'chenjialuo', '237', 'WHALE_CRM', '3', 800000.00, NULL, 55.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-05-03 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (130, 'OPP00000130', '深圳数字研究院-BI-项目', '政府', '2', 'CUST000079', 'chenjialuo', '237', 'WHALE_BI', '1', 1000000.00, NULL, 20.00, NULL, NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-05-04 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (131, 'OPP00000131', '中山大学-智能体-项目', '教育', '4', 'CUST000080', 'chenjialuo', '236', 'WHALE_AGENT', '4', 500000.00, 480000.00, 100.00, NULL, '客户关系维护良好', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-04 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (132, 'OPP00000132', '福州银行-BI-项目', '金融', '1', 'CUST000081', 'hufei', '233', 'WHALE_BI', '4', 1100000.00, 1050000.00, 100.00, NULL, '产品功能契合度高', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-05 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (133, 'OPP00000133', '福建数字-CRM-项目', '政府', '2', 'CUST000082', 'hufei', '233', 'WHALE_CRM', '2', 700000.00, NULL, 35.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-05-05 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (134, 'OPP00000134', '厦门大学-智能体-项目', '教育', '4', 'CUST000083', 'hufei', '233', 'WHALE_AGENT', '3', 400000.00, NULL, 50.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-05-06 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (135, 'OPP00000135', '贵阳银行-BI-项目', '金融', '1', 'CUST000084', 'yangguo', '238', 'WHALE_BI', '4', 1000000.00, 960000.00, 100.00, NULL, '售前响应及时', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-06 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (136, 'OPP00000136', '云南人民医院-CRM-项目', '医疗健康', '3', 'CUST000085', 'yangguo', '238', 'WHALE_CRM', '1', 600000.00, NULL, 20.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-05-07 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (137, 'OPP00000137', '昆明大数据-BI-项目', '政府', '2', 'CUST000086', 'yangguo', '238', 'WHALE_BI', '3', 800000.00, NULL, 55.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-05-07 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (138, 'OPP00000138', '太平洋保险-数据工厂-项目', '金融', '1', 'CUST000087', 'hufei', '233', 'WHALE_DF', '4', 3500000.00, 3300000.00, 100.00, NULL, '价格优势明显', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-08 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (139, 'OPP00000139', '国泰君安-BI-项目', '金融', '1', 'CUST000088', 'hufei', '233', 'WHALE_BI', '4', 2000000.00, 1900000.00, 100.00, NULL, '客户关系维护良好', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-08 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (140, 'OPP00000140', '华能-数据工厂-项目', '制造', '7', 'CUST000089', 'weixiaobao', '231', 'WHALE_DF', '3', 4000000.00, NULL, 60.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-05-09 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (141, 'OPP00000141', '国家电网-数据工厂-项目', '制造', '7', 'CUST000090', 'weixiaobao', '231', 'WHALE_DF', '2', 5000000.00, NULL, 40.00, NULL, NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-05-09 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (142, 'OPP00000142', '深交所-BI-项目', '金融', '1', 'CUST000091', 'chenjialuo', '236', 'WHALE_BI', '4', 2500000.00, 2400000.00, 100.00, NULL, '产品功能契合度高', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-10 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (143, 'OPP00000143', '上交所-BI-项目', '金融', '1', 'CUST000092', 'hufei', '233', 'WHALE_BI', '4', 3000000.00, 2850000.00, 100.00, NULL, '售前响应及时', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-10 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (144, 'OPP00000144', '北交所-BI-项目', '金融', '1', 'CUST000093', 'weixiaobao', '231', 'WHALE_BI', '1', 2000000.00, NULL, 20.00, NULL, NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-05-11 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (145, 'OPP00000145', '武汉大学-智能体-项目', '教育', '4', 'CUST000094', 'zhangwuji', '240', 'WHALE_AGENT', '3', 500000.00, NULL, 50.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-05-11 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (146, 'OPP00000146', '华中科技-智能体-项目', '教育', '4', 'CUST000095', 'zhangwuji', '240', 'WHALE_AGENT', '1', 450000.00, NULL, 20.00, NULL, NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-05-11 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (147, 'OPP00000147', '湖北人民医院-CRM-项目', '医疗健康', '3', 'CUST000096', 'zhangwuji', '241', 'WHALE_CRM', '4', 700000.00, 670000.00, 100.00, NULL, '价格优势明显', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-12 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (148, 'OPP00000148', '长沙卫健-BI-项目', '政府', '3', 'CUST000097', 'zhangwuji', '241', 'WHALE_BI', '2', 900000.00, NULL, 35.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-05-12 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (149, 'OPP00000149', '湘雅医院-智能体-项目', '医疗健康', '3', 'CUST000098', 'zhangwuji', '242', 'WHALE_AGENT', '1', 400000.00, NULL, 20.00, NULL, NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-05-12 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (150, 'OPP00000150', '成都大数据-CRM-项目', '政府', '2', 'CUST000099', 'yangguo', '239', 'WHALE_CRM', '3', 750000.00, NULL, 55.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-05-12 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (151, 'OPP00000151', '国投中债-MASS-项目', '金融', '1', 'CUST000001', 'weixiaobao', '231', 'WHALE_MASS', '4', 400000.00, 380000.00, 100.00, NULL, '产品功能契合度高', '2025-12-01 00:00:00', '2025-12-01 00:00:00', 'admin', '2025-11-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (152, 'OPP00000152', '工行北京-CRM-项目', '金融', '1', 'CUST000002', 'weixiaobao', '231', 'WHALE_CRM', '4', 800000.00, 770000.00, 100.00, NULL, '价格优势明显', '2025-12-01 00:00:00', '2025-12-01 00:00:00', 'admin', '2025-11-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (153, 'OPP00000153', '招行上海-MASS-项目', '金融', '1', 'CUST000004', 'hufei', '233', 'WHALE_MASS', '4', 600000.00, 580000.00, 100.00, NULL, '售前响应及时', '2025-12-01 00:00:00', '2025-12-01 00:00:00', 'admin', '2025-11-18 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (154, 'OPP00000154', '平安银行-CRM-项目', '金融', '1', 'CUST000008', 'chenjialuo', '236', 'WHALE_CRM', '4', 900000.00, 860000.00, 100.00, NULL, '客户关系维护良好', '2025-12-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (155, 'OPP00000155', '华为-CRM-项目', '制造', '5', 'CUST000020', 'chenjialuo', '236', 'WHALE_CRM', '4', 1500000.00, 1440000.00, 100.00, NULL, '产品功能契合度高', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-27 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (156, 'OPP00000156', '阿里巴巴-CRM-项目', '制造', '5', 'CUST000016', 'diyun', '234', 'WHALE_CRM', '4', 2000000.00, 1900000.00, 100.00, NULL, '价格优势明显', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-19 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (157, 'OPP00000157', '武汉商行-CRM-项目', '金融', '1', 'CUST000011', 'zhangwuji', '240', 'WHALE_CRM', '4', 700000.00, 670000.00, 100.00, NULL, '售前响应及时', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (158, 'OPP00000158', '浦发银行-数据工厂-项目', '金融', '1', 'CUST000005', 'hufei', '233', 'WHALE_DF', '4', 1200000.00, 1150000.00, 100.00, NULL, '客户关系维护良好', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (159, 'OPP00000159', '宁波银行-MASS-项目', '金融', '1', 'CUST000017', 'hufei', '233', 'WHALE_MASS', '4', 500000.00, 480000.00, 100.00, NULL, '产品功能契合度高', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (160, 'OPP00000160', '腾讯-CRM-项目', '制造', '5', 'CUST000018', 'chenjialuo', '236', 'WHALE_CRM', '4', 1800000.00, 1720000.00, 100.00, NULL, '价格优势明显', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (161, 'OPP00000161', '南京银行-MASS-项目', '金融', '1', 'CUST000013', 'hufei', '233', 'WHALE_MASS', '4', 500000.00, 480000.00, 100.00, NULL, '售前响应及时', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (162, 'OPP00000162', '苏省数据-数据工厂-项目', '政府', '2', 'CUST000014', 'diyun', '234', 'WHALE_DF', '4', 1500000.00, 1430000.00, 100.00, NULL, '客户关系维护良好', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (163, 'OPP00000163', '成都高新-MASS-项目', '政府', '2', 'CUST000009', 'yangguo', '238', 'WHALE_MASS', '4', 400000.00, 380000.00, 100.00, NULL, '产品功能契合度高', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (164, 'OPP00000164', '重庆农商-CRM-项目', '金融', '1', 'CUST000028', 'yangguo', '238', 'WHALE_CRM', '4', 700000.00, 670000.00, 100.00, NULL, '价格优势明显', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (165, 'OPP00000165', '郑州银行-数据工厂-项目', '金融', '1', 'CUST000026', 'zhangwuji', '240', 'WHALE_DF', '4', 1000000.00, 960000.00, 100.00, NULL, '售前响应及时', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (166, 'OPP00000166', '厦门国际银行-数据工厂-项目', '金融', '1', 'CUST000031', 'hufei', '233', 'WHALE_DF', '4', 800000.00, 760000.00, 100.00, NULL, '客户关系维护良好', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (167, 'OPP00000167', '苏州工业园-CRM-项目', '政府', '2', 'CUST000033', 'diyun', '234', 'WHALE_CRM', '4', 600000.00, 580000.00, 100.00, NULL, '产品功能契合度高', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (168, 'OPP00000168', '建行天津-MASS-项目', '金融', '1', 'CUST000021', 'weixiaobao', '231', 'WHALE_MASS', '4', 400000.00, 380000.00, 100.00, NULL, '价格优势明显', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (169, 'OPP00000169', '贵州大数据-数据工厂-项目', '政府', '2', 'CUST000029', 'yangguo', '238', 'WHALE_DF', '4', 1200000.00, 1150000.00, 100.00, NULL, '客户关系维护良好', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (170, 'OPP00000170', '苏省人民医院-CRM-项目', '医疗健康', '3', 'CUST000035', 'hufei', '233', 'WHALE_CRM', '4', 600000.00, 580000.00, 100.00, NULL, '产品功能契合度高', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (171, 'OPP00000171', '徽商银行-CRM-项目', '金融', '1', 'CUST000055', 'hufei', '233', 'WHALE_CRM', '4', 700000.00, 670000.00, 100.00, NULL, '价格优势明显', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (172, 'OPP00000172', '西安银行-CRM-项目', '金融', '1', 'CUST000046', 'yangguo', '238', 'WHALE_CRM', '4', 600000.00, 580000.00, 100.00, NULL, '售前响应及时', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (173, 'OPP00000173', '上交所-CRM-项目', '金融', '1', 'CUST000092', 'hufei', '233', 'WHALE_CRM', '4', 1500000.00, 1420000.00, 100.00, NULL, '客户关系维护良好', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-11 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (174, 'OPP00000174', '深交所-CRM-项目', '金融', '1', 'CUST000091', 'chenjialuo', '236', 'WHALE_CRM', '4', 1200000.00, 1150000.00, 100.00, NULL, '产品功能契合度高', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-11 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (175, 'OPP00000175', '太平洋保险-BI-项目', '金融', '1', 'CUST000087', 'hufei', '233', 'WHALE_BI', '4', 2000000.00, 1900000.00, 100.00, NULL, '价格优势明显', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-09 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (176, 'OPP00000176', '青岛银行-BI-项目', '金融', '1', 'CUST000051', 'zhangwuji', '240', 'WHALE_BI', '4', 1470000.00, 1280000.00, 100.00, NULL, '产品功能契合度高', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (177, 'OPP00000177', '江西银行-CRM-项目', '金融', '1', 'CUST000057', 'diyun', '234', 'WHALE_CRM', '4', 780000.00, 680000.00, 100.00, NULL, '价格优势明显', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (178, 'OPP00000178', '桂林银行-BI-项目', '金融', '1', 'CUST000060', 'chenjialuo', '236', 'WHALE_BI', '4', 1060000.00, 920000.00, 100.00, NULL, '售前响应及时', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (179, 'OPP00000179', '宁夏银行-CRM-项目', '金融', '1', 'CUST000063', 'yangguo', '238', 'WHALE_CRM', '4', 600000.00, 520000.00, 100.00, NULL, '客户关系维护良好', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (180, 'OPP00000180', '内蒙古银行-BI-项目', '金融', '1', 'CUST000065', 'weixiaobao', '231', 'WHALE_BI', '4', 900000.00, 780000.00, 100.00, NULL, '产品功能契合度高', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (181, 'OPP00000181', '吉林银行-CRM-项目', '金融', '1', 'CUST000068', 'weixiaobao', '231', 'WHALE_CRM', '4', 550000.00, 480000.00, 100.00, NULL, '价格优势明显', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (182, 'OPP00000182', '山西银行-BI-项目', '金融', '1', 'CUST000076', 'weixiaobao', '231', 'WHALE_BI', '4', 970000.00, 840000.00, 100.00, NULL, '售前响应及时', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (183, 'OPP00000183', '上交所-数据工厂-项目', '金融', '1', 'CUST000092', 'hufei', '233', 'WHALE_DF', '4', 5180000.00, 4500000.00, 100.00, NULL, '客户关系维护良好', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (184, 'OPP00000184', '北京大数据-BI-项目', '政府', '2', 'CUST000040', 'weixiaobao', '231', 'WHALE_BI', '4', 1720000.00, 1500000.00, 100.00, NULL, '产品功能契合度高', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (185, 'OPP00000185', '海南大数据-CRM-项目', '政府', '2', 'CUST000045', 'chenjialuo', '236', 'WHALE_CRM', '4', 670000.00, 580000.00, 100.00, NULL, '价格优势明显', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (186, 'OPP00000186', '陕西数字政府-CRM-项目', '政府', '2', 'CUST000047', 'yangguo', '238', 'WHALE_CRM', '4', 870000.00, 760000.00, 100.00, NULL, '售前响应及时', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (187, 'OPP00000187', '湖南大数据-BI-项目', '政府', '2', 'CUST000049', 'zhangwuji', '240', 'WHALE_BI', '4', 1060000.00, 920000.00, 100.00, NULL, '客户关系维护良好', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (188, 'OPP00000188', '济南大数据-CRM-项目', '政府', '2', 'CUST000052', 'zhangwuji', '240', 'WHALE_CRM', '4', 740000.00, 640000.00, 100.00, NULL, '产品功能契合度高', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (189, 'OPP00000189', '合肥大数据-BI-项目', '政府', '2', 'CUST000053', 'hufei', '233', 'WHALE_BI', '4', 1010000.00, 880000.00, 100.00, NULL, '价格优势明显', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (190, 'OPP00000190', '南昌政务-CRM-项目', '政府', '2', 'CUST000056', 'hufei', '233', 'WHALE_CRM', '4', 600000.00, 520000.00, 100.00, NULL, '售前响应及时', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (191, 'OPP00000191', '南宁大数据-BI-项目', '政府', '2', 'CUST000058', 'chenjialuo', '236', 'WHALE_BI', '4', 870000.00, 760000.00, 100.00, NULL, '客户关系维护良好', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (192, 'OPP00000192', '甘肃数据-CRM-项目', '政府', '2', 'CUST000062', 'yangguo', '238', 'WHALE_CRM', '4', 520000.00, 450000.00, 100.00, NULL, '产品功能契合度高', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (193, 'OPP00000193', '内蒙古大数据-BI-项目', '政府', '2', 'CUST000064', 'weixiaobao', '231', 'WHALE_BI', '4', 790000.00, 690000.00, 100.00, NULL, '价格优势明显', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (194, 'OPP00000194', '黑龙江政务-CRM-项目', '政府', '2', 'CUST000067', 'weixiaobao', '231', 'WHALE_CRM', '4', 550000.00, 480000.00, 100.00, NULL, '售前响应及时', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (195, 'OPP00000195', '长春数据-BI-项目', '政府', '2', 'CUST000069', 'weixiaobao', '231', 'WHALE_BI', '4', 640000.00, 560000.00, 100.00, NULL, '客户关系维护良好', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (196, 'OPP00000196', '山西大数据-CRM-项目', '政府', '2', 'CUST000075', 'weixiaobao', '231', 'WHALE_CRM', '4', 750000.00, 650000.00, 100.00, NULL, '产品功能契合度高', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (197, 'OPP00000197', '广州数据-数据工厂-项目', '政府', '2', 'CUST000078', 'chenjialuo', '237', 'WHALE_DF', '4', 3220000.00, 2800000.00, 100.00, NULL, '价格优势明显', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (198, 'OPP00000198', '深圳数字政府-BI-项目', '政府', '2', 'CUST000079', 'chenjialuo', '237', 'WHALE_BI', '4', 1260000.00, 1100000.00, 100.00, NULL, '售前响应及时', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (199, 'OPP00000199', '福建数字办-CRM-项目', '政府', '2', 'CUST000082', 'hufei', '233', 'WHALE_CRM', '4', 900000.00, 780000.00, 100.00, NULL, '客户关系维护良好', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (200, 'OPP00000200', '昆明大数据-BI-项目', '政府', '2', 'CUST000086', 'yangguo', '238', 'WHALE_BI', '4', 780000.00, 680000.00, 100.00, NULL, '产品功能契合度高', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (201, 'OPP00000201', '成都大数据-CRM-项目', '政府', '2', 'CUST000099', 'yangguo', '239', 'WHALE_CRM', '4', 620000.00, 540000.00, 100.00, NULL, '价格优势明显', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (202, 'OPP00000202', '渝市大数据-BI-项目', '政府', '2', 'CUST000100', 'yangguo', '239', 'WHALE_BI', '4', 990000.00, 860000.00, 100.00, NULL, '售前响应及时', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (203, 'OPP00000203', '北京协和-BI-项目', '医疗健康', '3', 'CUST000041', 'weixiaobao', '231', 'WHALE_BI', '4', 1670000.00, 1450000.00, 100.00, NULL, '客户关系维护良好', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (204, 'OPP00000204', '川省人民医院-BI-项目', '医疗健康', '3', 'CUST000048', 'yangguo', '238', 'WHALE_BI', '4', 1440000.00, 1250000.00, 100.00, NULL, '产品功能契合度高', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (205, 'OPP00000205', '安徽省立-CRM-项目', '医疗健康', '3', 'CUST000054', 'hufei', '233', 'WHALE_CRM', '4', 710000.00, 620000.00, 100.00, NULL, '价格优势明显', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (206, 'OPP00000206', '辽省人民医院-CRM-项目', '医疗健康', '3', 'CUST000070', 'weixiaobao', '231', 'WHALE_CRM', '4', 550000.00, 480000.00, 100.00, NULL, '售前响应及时', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (207, 'OPP00000207', '浙省人民医院-BI-项目', '医疗健康', '3', 'CUST000073', 'diyun', '235', 'WHALE_BI', '4', 1550000.00, 1350000.00, 100.00, NULL, '客户关系维护良好', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (208, 'OPP00000208', '云南人民医院-CRM-项目', '医疗健康', '3', 'CUST000085', 'yangguo', '238', 'WHALE_CRM', '4', 640000.00, 560000.00, 100.00, NULL, '产品功能契合度高', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (209, 'OPP00000209', '鄂省人民医院-BI-项目', '医疗健康', '3', 'CUST000096', 'zhangwuji', '241', 'WHALE_BI', '4', 1930000.00, 1680000.00, 100.00, NULL, '价格优势明显', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (210, 'OPP00000210', '湘雅医院-CRM-项目', '医疗健康', '3', 'CUST000098', 'zhangwuji', '242', 'WHALE_CRM', '4', 1020000.00, 890000.00, 100.00, NULL, '售前响应及时', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (211, 'OPP00000211', '上交大-CRM-项目', '教育', '4', 'CUST000036', 'hufei', '233', 'WHALE_CRM', '4', 1260000.00, 1100000.00, 100.00, NULL, '客户关系维护良好', '2025-11-01 00:00:00', '2025-11-01 00:00:00', 'admin', '2025-10-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (212, 'OPP00000212', '东北大学-BI-项目', '教育', '4', 'CUST000072', 'weixiaobao', '231', 'WHALE_BI', '4', 860000.00, 750000.00, 100.00, NULL, '产品功能契合度高', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (213, 'OPP00000213', '中山大学-CRM-项目', '教育', '4', 'CUST000080', 'chenjialuo', '236', 'WHALE_CRM', '4', 780000.00, 680000.00, 100.00, NULL, '价格优势明显', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (214, 'OPP00000214', '厦门大学-BI-项目', '教育', '4', 'CUST000083', 'hufei', '233', 'WHALE_BI', '4', 940000.00, 820000.00, 100.00, NULL, '售前响应及时', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (215, 'OPP00000215', '武汉大学-CRM-项目', '教育', '4', 'CUST000094', 'zhangwuji', '240', 'WHALE_CRM', '4', 790000.00, 690000.00, 100.00, NULL, '客户关系维护良好', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (216, 'OPP00000216', '华中科大-BI-项目', '教育', '4', 'CUST000095', 'zhangwuji', '240', 'WHALE_BI', '4', 900000.00, 780000.00, 100.00, NULL, '产品功能契合度高', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (217, 'OPP00000217', '网易-数据工厂-项目', '制造', '5', 'CUST000074', 'diyun', '235', 'WHALE_DF', '4', 4370000.00, 3800000.00, 100.00, NULL, '价格优势明显', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (218, 'OPP00000218', '华能集团-数据工厂-项目', '制造', '5', 'CUST000089', 'weixiaobao', '231', 'WHALE_DF', '4', 5980000.00, 5200000.00, 100.00, NULL, '售前响应及时', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (219, 'OPP00000219', '国家电网-数据工厂-项目', '制造', '5', 'CUST000090', 'weixiaobao', '231', 'WHALE_DF', '4', 7820000.00, 6800000.00, 100.00, NULL, '客户关系维护良好', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (220, 'OPP00000220', '工行北京-数据工厂-项目', '金融', '1', 'CUST000002', 'weixiaobao', '231', 'WHALE_DF', '4', 5180000.00, 4500000.00, 100.00, NULL, '产品功能契合度高', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (221, 'OPP00000221', '平安银行-MASS-项目', '金融', '1', 'CUST000008', 'chenjialuo', '236', 'WHALE_MASS', '4', 1840000.00, 1600000.00, 100.00, NULL, '价格优势明显', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (222, 'OPP00000222', '武汉商行-MASS-项目', '金融', '1', 'CUST000011', 'zhangwuji', '240', 'WHALE_MASS', '4', 1030000.00, 900000.00, 100.00, NULL, '售前响应及时', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (223, 'OPP00000223', '南京银行-CRM-项目', '金融', '1', 'CUST000013', 'hufei', '233', 'WHALE_CRM', '4', 900000.00, 780000.00, 100.00, NULL, '客户关系维护良好', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (224, 'OPP00000224', '阿里巴巴-MASS-项目', '制造', '5', 'CUST000016', 'diyun', '234', 'WHALE_MASS', '4', 2420000.00, 2100000.00, 100.00, NULL, '产品功能契合度高', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (225, 'OPP00000225', '腾讯-MASS-项目', '制造', '5', 'CUST000018', 'chenjialuo', '236', 'WHALE_MASS', '4', 2990000.00, 2600000.00, 100.00, NULL, '价格优势明显', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (226, 'OPP00000226', '华为-MASS-项目', '制造', '5', 'CUST000020', 'chenjialuo', '236', 'WHALE_MASS', '4', 2070000.00, 1800000.00, 100.00, NULL, '售前响应及时', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (227, 'OPP00000227', '华为-DQC-项目', '制造', '5', 'CUST000020', 'chenjialuo', '236', 'WHALE_DQC', '4', 1380000.00, 1200000.00, 100.00, NULL, '客户关系维护良好', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (228, 'OPP00000228', '农行山东-CRM-项目', '金融', '1', 'CUST000024', 'zhangwuji', '240', 'WHALE_CRM', '4', 780000.00, 680000.00, 100.00, NULL, '产品功能契合度高', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (229, 'OPP00000229', '厦门国际-CRM-项目', '金融', '1', 'CUST000031', 'hufei', '233', 'WHALE_CRM', '4', 670000.00, 580000.00, 100.00, NULL, '价格优势明显', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (230, 'OPP00000230', '福建医大附-BI-项目', '医疗健康', '3', 'CUST000032', 'hufei', '233', 'WHALE_BI', '4', 1130000.00, 980000.00, 100.00, NULL, '售前响应及时', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (231, 'OPP00000231', '电力建设-BI-项目', '制造', '5', 'CUST000042', 'weixiaobao', '231', 'WHALE_BI', '4', 1260000.00, 1100000.00, 100.00, NULL, '客户关系维护良好', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (232, 'OPP00000232', '北交所-BI-续签项目', '金融', '1', 'CUST000093', 'weixiaobao', '231', 'WHALE_BI', '4', 2130000.00, 1850000.00, 100.00, NULL, '产品功能契合度高', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (233, 'OPP00000233', '北京银行-MASS-项目', '金融', '1', 'CUST000039', 'weixiaobao', '231', 'WHALE_MASS', '4', 920000.00, 800000.00, 100.00, NULL, '价格优势明显', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (234, 'OPP00000234', '长沙银行-CRM-项目', '金融', '1', 'CUST000050', 'zhangwuji', '240', 'WHALE_CRM', '4', 480000.00, 420000.00, 100.00, NULL, '售前响应及时', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (235, 'OPP00000235', '桂林银行-CRM-项目', '金融', '1', 'CUST000060', 'chenjialuo', '236', 'WHALE_CRM', '4', 410000.00, 360000.00, 100.00, NULL, '客户关系维护良好', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (236, 'OPP00000236', '内蒙古银行-CRM-项目', '金融', '1', 'CUST000065', 'weixiaobao', '231', 'WHALE_CRM', '4', 390000.00, 340000.00, 100.00, NULL, '产品功能契合度高', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (237, 'OPP00000237', '哈尔滨银行-CRM-项目', '金融', '1', 'CUST000066', 'weixiaobao', '231', 'WHALE_CRM', '4', 520000.00, 450000.00, 100.00, NULL, '价格优势明显', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (238, 'OPP00000238', '盛京银行-CRM-项目', '金融', '1', 'CUST000071', 'weixiaobao', '231', 'WHALE_CRM', '4', 600000.00, 520000.00, 100.00, NULL, '售前响应及时', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (239, 'OPP00000239', '山西银行-CRM-项目', '金融', '1', 'CUST000076', 'weixiaobao', '231', 'WHALE_CRM', '4', 440000.00, 380000.00, 100.00, NULL, '客户关系维护良好', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (240, 'OPP00000240', '福州银行-CRM-项目', '金融', '1', 'CUST000081', 'hufei', '233', 'WHALE_CRM', '4', 480000.00, 420000.00, 100.00, NULL, '产品功能契合度高', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (241, 'OPP00000241', '贵阳银行-CRM-项目', '金融', '1', 'CUST000084', 'yangguo', '238', 'WHALE_CRM', '4', 450000.00, 390000.00, 100.00, NULL, '价格优势明显', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (242, 'OPP00000242', '太平洋保险-CRM-项目', '金融', '1', 'CUST000087', 'hufei', '233', 'WHALE_CRM', '4', 980000.00, 850000.00, 100.00, NULL, '售前响应及时', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (243, 'OPP00000243', '国泰君安-CRM-项目', '金融', '1', 'CUST000088', 'hufei', '233', 'WHALE_CRM', '4', 870000.00, 760000.00, 100.00, NULL, '客户关系维护良好', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (244, 'OPP00000244', '长沙卫健委-BI-项目', '政府', '3', 'CUST000097', 'zhangwuji', '241', 'WHALE_BI', '4', 790000.00, 690000.00, 100.00, NULL, '产品功能契合度高', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (245, 'OPP00000245', '湘雅医院-BI-项目', '医疗健康', '3', 'CUST000098', 'zhangwuji', '242', 'WHALE_BI', '4', 970000.00, 840000.00, 100.00, NULL, '价格优势明显', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (246, 'OPP00000246', '成都大数据-BI-项目', '政府', '2', 'CUST000099', 'yangguo', '239', 'WHALE_BI', '4', 830000.00, 720000.00, 100.00, NULL, '售前响应及时', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (247, 'OPP00000247', '渝市大数据-CRM-项目', '政府', '2', 'CUST000100', 'yangguo', '239', 'WHALE_CRM', '4', 530000.00, 460000.00, 100.00, NULL, '客户关系维护良好', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (248, 'OPP00000248', '广州卫健-MASS-项目', '政府', '3', 'CUST000006', 'chenjialuo', '236', 'WHALE_MASS', '4', 900000.00, 780000.00, 100.00, NULL, '产品功能契合度高', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (249, 'OPP00000249', '北京海淀-BI-项目', '政府', '2', 'CUST000003', 'diyun', '234', 'WHALE_BI', '4', 1380000.00, 1200000.00, 100.00, NULL, '价格优势明显', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (250, 'OPP00000250', '广东人民医院-CRM-项目', '医疗健康', '3', 'CUST000007', 'chenjialuo', '236', 'WHALE_CRM', '4', 670000.00, 580000.00, 100.00, NULL, '售前响应及时', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (251, 'OPP00000251', '湖北卫健-BI-项目', '政府', '3', 'CUST000012', 'zhangwuji', '240', 'WHALE_BI', '4', 940000.00, 820000.00, 100.00, NULL, '客户关系维护良好', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (252, 'OPP00000252', '苏省大数据-BI-项目', '政府', '2', 'CUST000014', 'diyun', '234', 'WHALE_BI', '4', 1550000.00, 1350000.00, 100.00, NULL, '产品功能契合度高', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (253, 'OPP00000253', '山东人民医院-BI-项目', '医疗健康', '3', 'CUST000025', 'zhangwuji', '240', 'WHALE_BI', '4', 1320000.00, 1150000.00, 100.00, NULL, '价格优势明显', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (254, 'OPP00000254', '云南数字经济-BI-项目', '政府', '2', 'CUST000030', 'yangguo', '238', 'WHALE_BI', '4', 670000.00, 580000.00, 100.00, NULL, '售前响应及时', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (255, 'OPP00000255', '无锡大数据-BI-项目', '政府', '2', 'CUST000034', 'diyun', '234', 'WHALE_BI', '4', 750000.00, 650000.00, 100.00, NULL, '客户关系维护良好', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (256, 'OPP00000256', '川省人民医院-CRM-项目', '医疗健康', '3', 'CUST000048', 'yangguo', '238', 'WHALE_CRM', '4', 620000.00, 540000.00, 100.00, NULL, '产品功能契合度高', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);

-- ----------------------------
-- Table structure for by_project
-- ----------------------------
DROP TABLE IF EXISTS "{{DATACLOUD_DB_SCHEMA}}"."by_project";
CREATE TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_project" (
  "id" int8 NOT NULL DEFAULT nextval('"{{DATACLOUD_DB_SCHEMA}}".by_project_id_seq'::regclass),
  "project_code" varchar(50) COLLATE "pg_catalog"."default" NOT NULL,
  "project_name" varchar(200) COLLATE "pg_catalog"."default" NOT NULL,
  "industry" varchar(100) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "domain" varchar(100) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "customer_code" varchar(50) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "sales_user_id" varchar(100) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "dept_id" varchar(50) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "opp_id" int8,
  "product_code" varchar(50) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "project_status" char(1) COLLATE "pg_catalog"."default" NOT NULL DEFAULT '1'::bpchar,
  "contract_amount" numeric(18,2) DEFAULT NULL::numeric,
  "revenue_amount" numeric(18,2) DEFAULT NULL::numeric,
  "payment_amount" numeric(18,2) DEFAULT NULL::numeric,
  "arrear_amount" numeric(18,2) DEFAULT NULL::numeric,
  "plan_online_date" timestamp(0) DEFAULT NULL::timestamp without time zone,
  "actual_online_date" timestamp(0) DEFAULT NULL::timestamp without time zone,
  "plan_revenue_date" timestamp(0) DEFAULT NULL::timestamp without time zone,
  "actual_revenue_date" timestamp(0) DEFAULT NULL::timestamp without time zone,
  "plan_payment_date" timestamp(0) DEFAULT NULL::timestamp without time zone,
  "actual_payment_date" timestamp(0) DEFAULT NULL::timestamp without time zone,
  "create_by" varchar(64) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "create_time" timestamp(6),
  "update_by" varchar(64) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "update_time" timestamp(6),
  "remark" varchar(500) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying
)
;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."id" IS '主键';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."project_code" IS '项目编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."project_name" IS '项目名称';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."industry" IS '所属行业';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."domain" IS '所属领域';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."customer_code" IS '所属客户编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."sales_user_id" IS '所属销售用户编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."dept_id" IS '所属部门编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."opp_id" IS '关联商机ID';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."product_code" IS '所属产品编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."project_status" IS '项目状态(1项目启动 2安装部署 3项目交付 4项目上线 5收入确认 6完成回款)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."contract_amount" IS '签约金额';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."revenue_amount" IS '收入金额';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."payment_amount" IS '回款金额';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."arrear_amount" IS '欠费金额';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."plan_online_date" IS '计划上线日期(YYYY-MM-DD)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."actual_online_date" IS '实际上线日期(YYYY-MM-DD)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."plan_revenue_date" IS '计划收入完成日期(YYYY-MM-DD)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."actual_revenue_date" IS '实际收入完成日期(YYYY-MM-DD)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."plan_payment_date" IS '计划回款完成日期(YYYY-MM-DD)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."actual_payment_date" IS '实际回款完成日期(YYYY-MM-DD)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."create_by" IS '创建者';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."create_time" IS '创建时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."update_by" IS '更新者';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."update_time" IS '更新时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."remark" IS '备注';
COMMENT ON TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_project" IS '项目信息表';

-- ----------------------------
-- Records of by_project
-- ----------------------------
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (1, 'PROJ00000001', '国投中债-BI-实施项目', '金融', '1', 'CUST000001', 'weixiaobao', '231', 1, 'WHALE_BI', '6', 1100000.00, 1050000.00, 1050000.00, 0.00, '2026-01-01 00:00:00', '2026-01-01 00:00:00', '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2025-12-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (2, 'PROJ00000002', '工行北京-BI-实施项目', '金融', '1', 'CUST000002', 'weixiaobao', '231', 4, 'WHALE_BI', '6', 2300000.00, 2200000.00, 2200000.00, 0.00, '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-01-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (3, 'PROJ00000003', '工行北京-CRM-实施项目', '金融', '1', 'CUST000002', 'weixiaobao', '231', 152, 'WHALE_CRM', '5', 770000.00, 750000.00, 600000.00, 150000.00, '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', NULL, 'admin', '2025-12-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (4, 'PROJ00000004', '海淀政府-CRM-实施项目', '政府', '2', 'CUST000003', 'diyun', '234', 7, 'WHALE_CRM', '6', 850000.00, 820000.00, 820000.00, 0.00, '2026-03-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (5, 'PROJ00000005', '招行上海-BI-实施项目', '金融', '1', 'CUST000004', 'hufei', '233', 10, 'WHALE_BI', '6', 2800000.00, 2700000.00, 2700000.00, 0.00, '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-01-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (6, 'PROJ00000006', '招行上海-MASS-实施项目', '金融', '1', 'CUST000004', 'hufei', '233', 153, 'WHALE_MASS', '5', 580000.00, 560000.00, 400000.00, 160000.00, '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', NULL, 'admin', '2025-12-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (7, 'PROJ00000007', '浦发银行-BI-实施项目', '金融', '1', 'CUST000005', 'hufei', '233', 13, 'WHALE_BI', '6', 1400000.00, 1350000.00, 1350000.00, 0.00, '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-01-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (8, 'PROJ00000008', '浦发银行-数据工厂-实施项目', '金融', '1', 'CUST000005', 'hufei', '233', 158, 'WHALE_DF', '4', 1150000.00, NULL, NULL, NULL, '2026-05-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (9, 'PROJ00000009', '天河卫健-CRM-实施项目', '政府', '3', 'CUST000006', 'chenjialuo', '236', 16, 'WHALE_CRM', '6', 580000.00, 560000.00, 560000.00, 0.00, '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2025-12-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (10, 'PROJ00000010', '粤省人民医院-BI-实施项目', '医疗健康', '3', 'CUST000007', 'chenjialuo', '236', 19, 'WHALE_BI', '5', 1050000.00, 1000000.00, 700000.00, 300000.00, '2026-03-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (11, 'PROJ00000011', '平安银行-BI-实施项目', '金融', '1', 'CUST000008', 'chenjialuo', '236', 22, 'WHALE_BI', '6', 1900000.00, 1820000.00, 1820000.00, 0.00, '2026-03-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-01-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (12, 'PROJ00000012', '平安银行-CRM-实施项目', '金融', '1', 'CUST000008', 'chenjialuo', '236', 154, 'WHALE_CRM', '4', 860000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2025-12-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (13, 'PROJ00000013', '成都高新-CRM-实施项目', '政府', '2', 'CUST000009', 'yangguo', '238', 25, 'WHALE_CRM', '5', 720000.00, 700000.00, 500000.00, 200000.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (14, 'PROJ00000014', '川省教育厅-BI-实施项目', '政府', '4', 'CUST000010', 'yangguo', '238', 28, 'WHALE_BI', '4', 780000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', '2026-04-01 00:00:00', '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (15, 'PROJ00000015', '武汉商行-BI-实施项目', '金融', '1', 'CUST000011', 'zhangwuji', '240', 31, 'WHALE_BI', '6', 1250000.00, 1200000.00, 1200000.00, 0.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (16, 'PROJ00000016', '武汉商行-CRM-实施项目', '金融', '1', 'CUST000011', 'zhangwuji', '240', 157, 'WHALE_CRM', '3', 670000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (17, 'PROJ00000017', '鄂省卫健-CRM-实施项目', '政府', '3', 'CUST000012', 'zhangwuji', '240', 34, 'WHALE_CRM', '5', 680000.00, 660000.00, 400000.00, 260000.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (18, 'PROJ00000018', '南京银行-BI-实施项目', '金融', '1', 'CUST000013', 'hufei', '233', 37, 'WHALE_BI', '6', 1520000.00, 1460000.00, 1460000.00, 0.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (19, 'PROJ00000019', '南京银行-MASS-实施项目', '金融', '1', 'CUST000013', 'hufei', '233', 161, 'WHALE_MASS', '4', 480000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (20, 'PROJ00000020', '苏省数据-CRM-实施项目', '政府', '2', 'CUST000014', 'diyun', '234', 40, 'WHALE_CRM', '5', 870000.00, 850000.00, 600000.00, 250000.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (21, 'PROJ00000021', '苏省数据-数据工厂-实施项目', '政府', '2', 'CUST000014', 'diyun', '234', 162, 'WHALE_DF', '4', 1430000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (22, 'PROJ00000022', '浙大-BI-实施项目', '教育', '4', 'CUST000015', 'diyun', '234', 43, 'WHALE_BI', '6', 680000.00, 660000.00, 660000.00, 0.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', '2026-06-01 00:00:00', 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (23, 'PROJ00000023', '阿里巴巴-数据工厂-实施项目', '制造', '5', 'CUST000016', 'diyun', '234', 46, 'WHALE_DF', '5', 3800000.00, 3700000.00, 2500000.00, 1200000.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (24, 'PROJ00000024', '阿里巴巴-CRM-实施项目', '制造', '5', 'CUST000016', 'diyun', '234', 156, 'WHALE_CRM', '4', 1900000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', '2026-06-01 00:00:00', '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (25, 'PROJ00000025', '宁波银行-BI-实施项目', '金融', '1', 'CUST000017', 'hufei', '233', 49, 'WHALE_BI', '6', 1350000.00, 1300000.00, 1300000.00, 0.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', '2026-06-01 00:00:00', 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (26, 'PROJ00000026', '腾讯-数据工厂-实施项目', '制造', '5', 'CUST000018', 'chenjialuo', '236', 51, 'WHALE_DF', '5', 4800000.00, 4600000.00, 3000000.00, 1600000.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (27, 'PROJ00000027', '腾讯-CRM-实施项目', '制造', '5', 'CUST000018', 'chenjialuo', '236', 160, 'WHALE_CRM', '4', 1720000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (28, 'PROJ00000028', '越秀教育-CRM-实施项目', '政府', '4', 'CUST000019', 'chenjialuo', '236', 54, 'WHALE_CRM', '5', 480000.00, 465000.00, 300000.00, 165000.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (29, 'PROJ00000029', '华为-数据工厂-实施项目', '制造', '5', 'CUST000020', 'chenjialuo', '236', 57, 'WHALE_DF', '5', 7500000.00, 7200000.00, 5000000.00, 2200000.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (30, 'PROJ00000030', '华为-CRM-实施项目', '制造', '5', 'CUST000020', 'chenjialuo', '236', 155, 'WHALE_CRM', '4', 1440000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', '2026-06-01 00:00:00', '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (31, 'PROJ00000031', '建行天津-BI-实施项目', '金融', '1', 'CUST000021', 'weixiaobao', '231', 60, 'WHALE_BI', '5', 1700000.00, 1640000.00, 1000000.00, 640000.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (32, 'PROJ00000032', '天津滨海-BI-实施项目', '政府', '2', 'CUST000022', 'weixiaobao', '231', 63, 'WHALE_BI', '5', 950000.00, 920000.00, 600000.00, 320000.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (33, 'PROJ00000033', '农行山东-BI-实施项目', '金融', '1', 'CUST000024', 'zhangwuji', '240', 66, 'WHALE_BI', '5', 2100000.00, 2000000.00, 1500000.00, 500000.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (34, 'PROJ00000034', '郑州银行-BI-实施项目', '金融', '1', 'CUST000026', 'zhangwuji', '240', 70, 'WHALE_BI', '4', 1150000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (35, 'PROJ00000035', '重庆农商-BI-实施项目', '金融', '1', 'CUST000028', 'yangguo', '238', 74, 'WHALE_BI', '5', 1520000.00, 1470000.00, 1000000.00, 470000.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (36, 'PROJ00000036', '贵州大数据-CRM-实施项目', '政府', '2', 'CUST000029', 'yangguo', '238', 76, 'WHALE_CRM', '4', 760000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', '2026-06-01 00:00:00', '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (37, 'PROJ00000037', '云南数字-CRM-实施项目', '政府', '2', 'CUST000030', 'yangguo', '238', 78, 'WHALE_CRM', '3', 680000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (38, 'PROJ00000038', '厦门国际银行-BI-实施项目', '金融', '1', 'CUST000031', 'hufei', '233', 79, 'WHALE_BI', '5', 1150000.00, 1100000.00, 800000.00, 300000.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (39, 'PROJ00000039', '苏州工业园-BI-实施项目', '政府', '2', 'CUST000033', 'diyun', '234', 82, 'WHALE_BI', '5', 1250000.00, 1200000.00, 900000.00, 300000.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (40, 'PROJ00000040', '无锡大数据-CRM-实施项目', '政府', '2', 'CUST000034', 'diyun', '234', 83, 'WHALE_CRM', '4', 720000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-04-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (41, 'PROJ00000041', '北京银行-BI-实施项目', '金融', '1', 'CUST000039', 'weixiaobao', '231', 89, 'WHALE_BI', '5', 1600000.00, 1472000.00, 853760.00, 618240.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (42, 'PROJ00000042', '广州农商银行-BI-实施项目', '金融', '1', 'CUST000044', 'chenjialuo', '236', 94, 'WHALE_BI', '6', 1350000.00, 1282500.00, 1179900.00, 102600.00, '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-01-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (43, 'PROJ00000043', '长沙银行-BI-实施项目', '金融', '1', 'CUST000050', 'zhangwuji', '240', 101, 'WHALE_BI', '5', 1150000.00, 1058000.00, 613640.00, 444360.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (44, 'PROJ00000044', '青岛银行-BI-实施项目', '金融', '1', 'CUST000051', 'zhangwuji', '240', 176, 'WHALE_BI', '4', 1280000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (45, 'PROJ00000045', '徽商银行-BI-实施项目', '金融', '1', 'CUST000055', 'hufei', '233', 106, 'WHALE_BI', '5', 1420000.00, 1306400.00, 757712.00, 548688.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (46, 'PROJ00000046', '江西银行-CRM-实施项目', '金融', '1', 'CUST000057', 'diyun', '234', 177, 'WHALE_CRM', '3', 680000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (47, 'PROJ00000047', '桂林银行-BI-实施项目', '金融', '1', 'CUST000060', 'chenjialuo', '236', 178, 'WHALE_BI', '4', 920000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (48, 'PROJ00000048', '兰州银行-BI-实施项目', '金融', '1', 'CUST000061', 'yangguo', '238', 112, 'WHALE_BI', '3', 860000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (49, 'PROJ00000049', '宁夏银行-CRM-实施项目', '金融', '1', 'CUST000063', 'yangguo', '238', 179, 'WHALE_CRM', '2', 520000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (50, 'PROJ00000050', '内蒙古银行-BI-实施项目', '金融', '1', 'CUST000065', 'weixiaobao', '231', 180, 'WHALE_BI', '4', 780000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-02-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (51, 'PROJ00000051', '哈尔滨银行-BI-实施项目', '金融', '1', 'CUST000066', 'weixiaobao', '231', 117, 'WHALE_BI', '3', 1050000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (52, 'PROJ00000052', '吉林银行-CRM-实施项目', '金融', '1', 'CUST000068', 'weixiaobao', '231', 181, 'WHALE_CRM', '2', 480000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (53, 'PROJ00000053', '盛京银行-BI-实施项目', '金融', '1', 'CUST000071', 'weixiaobao', '231', 122, 'WHALE_BI', '5', 1180000.00, 1085600.00, 629648.00, 455952.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (54, 'PROJ00000054', '山西银行-BI-实施项目', '金融', '1', 'CUST000076', 'weixiaobao', '231', 182, 'WHALE_BI', '4', 840000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (55, 'PROJ00000055', '福州银行-BI-实施项目', '金融', '1', 'CUST000081', 'hufei', '233', 132, 'WHALE_BI', '6', 1320000.00, 1254000.00, 1153680.00, 100320.00, '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (56, 'PROJ00000056', '贵阳银行-BI-实施项目', '金融', '1', 'CUST000084', 'yangguo', '238', 135, 'WHALE_BI', '3', 960000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (57, 'PROJ00000057', '太平洋保险-数据工厂-实施项目', '金融', '1', 'CUST000087', 'hufei', '233', 138, 'WHALE_DF', '4', 3200000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-02-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (58, 'PROJ00000058', '国泰君安-BI-实施项目', '金融', '1', 'CUST000088', 'hufei', '233', 139, 'WHALE_BI', '5', 1800000.00, 1656000.00, 960480.00, 695520.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (59, 'PROJ00000059', '深交所-BI-实施项目', '金融', '1', 'CUST000091', 'chenjialuo', '236', 142, 'WHALE_BI', '4', 2100000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (60, 'PROJ00000060', '上交所-数据工厂-实施项目', '金融', '1', 'CUST000092', 'hufei', '233', 183, 'WHALE_DF', '3', 4500000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (61, 'PROJ00000061', '沪大数据-CRM-实施项目', '政府', '2', 'CUST000037', 'diyun', '234', 87, 'WHALE_CRM', '6', 1200000.00, 1140000.00, 1048800.00, 91200.00, '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2025-12-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (62, 'PROJ00000062', '北京大数据-BI-实施项目', '政府', '2', 'CUST000040', 'weixiaobao', '231', 184, 'WHALE_BI', '5', 1500000.00, 1380000.00, 800400.00, 579600.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (63, 'PROJ00000063', '海南大数据-CRM-实施项目', '政府', '2', 'CUST000045', 'chenjialuo', '236', 185, 'WHALE_CRM', '3', 580000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (64, 'PROJ00000064', '陕西数字政府-CRM-实施项目', '政府', '2', 'CUST000047', 'yangguo', '238', 186, 'WHALE_CRM', '4', 760000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (65, 'PROJ00000065', '湖南大数据-BI-实施项目', '政府', '2', 'CUST000049', 'zhangwuji', '240', 187, 'WHALE_BI', '3', 920000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (66, 'PROJ00000066', '济南大数据-CRM-实施项目', '政府', '2', 'CUST000052', 'zhangwuji', '240', 188, 'WHALE_CRM', '2', 640000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (67, 'PROJ00000067', '合肥大数据-BI-实施项目', '政府', '2', 'CUST000053', 'hufei', '233', 189, 'WHALE_BI', '4', 880000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (68, 'PROJ00000068', '南昌政务-CRM-实施项目', '政府', '2', 'CUST000056', 'hufei', '233', 190, 'WHALE_CRM', '3', 520000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-04-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (69, 'PROJ00000069', '南宁大数据-BI-实施项目', '政府', '2', 'CUST000058', 'chenjialuo', '236', 191, 'WHALE_BI', '2', 760000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (70, 'PROJ00000070', '甘肃数据-CRM-实施项目', '政府', '2', 'CUST000062', 'yangguo', '238', 192, 'WHALE_CRM', '1', 450000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (71, 'PROJ00000071', '内蒙古大数据-BI-实施项目', '政府', '2', 'CUST000064', 'weixiaobao', '231', 193, 'WHALE_BI', '3', 690000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (72, 'PROJ00000072', '黑龙江政务-CRM-实施项目', '政府', '2', 'CUST000067', 'weixiaobao', '231', 194, 'WHALE_CRM', '2', 480000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (73, 'PROJ00000073', '长春数据-BI-实施项目', '政府', '2', 'CUST000069', 'weixiaobao', '231', 195, 'WHALE_BI', '1', 560000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (74, 'PROJ00000074', '山西大数据-CRM-实施项目', '政府', '2', 'CUST000075', 'weixiaobao', '231', 196, 'WHALE_CRM', '3', 650000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (75, 'PROJ00000075', '广州数据-数据工厂-实施项目', '政府', '2', 'CUST000078', 'chenjialuo', '237', 197, 'WHALE_DF', '4', 2800000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (76, 'PROJ00000076', '深圳数字政府-BI-实施项目', '政府', '2', 'CUST000079', 'chenjialuo', '237', 198, 'WHALE_BI', '3', 1100000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (77, 'PROJ00000077', '福建数字办-CRM-实施项目', '政府', '2', 'CUST000082', 'hufei', '233', 199, 'WHALE_CRM', '5', 780000.00, 717600.00, 416208.00, 301392.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (78, 'PROJ00000078', '昆明大数据-BI-实施项目', '政府', '2', 'CUST000086', 'yangguo', '238', 200, 'WHALE_BI', '2', 680000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (79, 'PROJ00000079', '成都大数据-CRM-实施项目', '政府', '2', 'CUST000099', 'yangguo', '239', 201, 'WHALE_CRM', '1', 540000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (80, 'PROJ00000080', '渝市大数据-BI-实施项目', '政府', '2', 'CUST000100', 'yangguo', '239', 202, 'WHALE_BI', '1', 860000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (81, 'PROJ00000081', '北京协和-BI-实施项目', '医疗健康', '3', 'CUST000041', 'weixiaobao', '231', 203, 'WHALE_BI', '5', 1450000.00, 1334000.00, 773720.00, 560280.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (82, 'PROJ00000082', '川省人民医院-BI-实施项目', '医疗健康', '3', 'CUST000048', 'yangguo', '238', 204, 'WHALE_BI', '4', 1250000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (83, 'PROJ00000083', '安徽省立-CRM-实施项目', '医疗健康', '3', 'CUST000054', 'hufei', '233', 205, 'WHALE_CRM', '3', 620000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (84, 'PROJ00000084', '广西人民医院-BI-实施项目', '医疗健康', '3', 'CUST000059', 'chenjialuo', '236', 110, 'WHALE_BI', '2', 890000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (85, 'PROJ00000085', '辽省人民医院-CRM-实施项目', '医疗健康', '3', 'CUST000070', 'weixiaobao', '231', 206, 'WHALE_CRM', '1', 480000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (86, 'PROJ00000086', '浙省人民医院-BI-实施项目', '医疗健康', '3', 'CUST000073', 'diyun', '235', 207, 'WHALE_BI', '4', 1350000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (87, 'PROJ00000087', '云南人民医院-CRM-实施项目', '医疗健康', '3', 'CUST000085', 'yangguo', '238', 208, 'WHALE_CRM', '3', 560000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (88, 'PROJ00000088', '鄂省人民医院-BI-实施项目', '医疗健康', '3', 'CUST000096', 'zhangwuji', '241', 209, 'WHALE_BI', '5', 1680000.00, 1545600.00, 896448.00, 649152.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (89, 'PROJ00000089', '湘雅医院-CRM-实施项目', '医疗健康', '3', 'CUST000098', 'zhangwuji', '242', 210, 'WHALE_CRM', '4', 890000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (90, 'PROJ00000090', '上交大-CRM-实施项目', '教育', '4', 'CUST000036', 'hufei', '233', 211, 'WHALE_CRM', '6', 1100000.00, 1045000.00, 961400.00, 83600.00, '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2025-12-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (91, 'PROJ00000091', '东北大学-BI-实施项目', '教育', '4', 'CUST000072', 'weixiaobao', '231', 212, 'WHALE_BI', '5', 750000.00, 690000.00, 400200.00, 289800.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (92, 'PROJ00000092', '中山大学-CRM-实施项目', '教育', '4', 'CUST000080', 'chenjialuo', '236', 213, 'WHALE_CRM', '3', 680000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (93, 'PROJ00000093', '厦门大学-BI-实施项目', '教育', '4', 'CUST000083', 'hufei', '233', 214, 'WHALE_BI', '4', 820000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (94, 'PROJ00000094', '武汉大学-CRM-实施项目', '教育', '4', 'CUST000094', 'zhangwuji', '240', 215, 'WHALE_CRM', '2', 690000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (95, 'PROJ00000095', '华中科大-BI-实施项目', '教育', '4', 'CUST000095', 'zhangwuji', '240', 216, 'WHALE_BI', '1', 780000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (96, 'PROJ00000096', '移动广东-MASS-实施项目', '制造', '5', 'CUST000043', 'chenjialuo', '236', 93, 'WHALE_MASS', '6', 2800000.00, 2660000.00, 2447200.00, 212800.00, '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2025-12-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (97, 'PROJ00000097', '中国电信沪分-MASS-实施项目', '制造', '5', 'CUST000038', 'diyun', '234', 88, 'WHALE_MASS', '5', 3200000.00, 2944000.00, 1707520.00, 1236480.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-01-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (98, 'PROJ00000098', '网易-数据工厂-实施项目', '制造', '5', 'CUST000074', 'diyun', '235', 217, 'WHALE_DF', '4', 3800000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-02-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (99, 'PROJ00000099', '华能集团-数据工厂-实施项目', '制造', '5', 'CUST000089', 'weixiaobao', '231', 218, 'WHALE_DF', '3', 5200000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (100, 'PROJ00000100', '国家电网-数据工厂-实施项目', '制造', '5', 'CUST000090', 'weixiaobao', '231', 219, 'WHALE_DF', '2', 6800000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (101, 'PROJ00000101', '工行北京-BI-续签项目', '金融', '1', 'CUST000002', 'weixiaobao', '231', 4, 'WHALE_BI', '2', 2200000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (102, 'PROJ00000102', '工行北京-数据工厂-实施项目', '金融', '1', 'CUST000002', 'weixiaobao', '231', 220, 'WHALE_DF', '1', 4500000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (103, 'PROJ00000103', '招商银行沪-MASS-实施项目', '金融', '1', 'CUST000004', 'hufei', '233', 153, 'WHALE_MASS', '3', 1800000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (104, 'PROJ00000104', '平安银行-MASS-实施项目', '金融', '1', 'CUST000008', 'chenjialuo', '236', 221, 'WHALE_MASS', '4', 1600000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (105, 'PROJ00000105', '武汉商行-MASS-实施项目', '金融', '1', 'CUST000011', 'zhangwuji', '240', 222, 'WHALE_MASS', '3', 900000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (106, 'PROJ00000106', '南京银行-CRM-实施项目', '金融', '1', 'CUST000013', 'hufei', '233', 223, 'WHALE_CRM', '5', 780000.00, 717600.00, 416208.00, 301392.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (107, 'PROJ00000107', '阿里巴巴-MASS-实施项目', '制造', '5', 'CUST000016', 'diyun', '234', 224, 'WHALE_MASS', '4', 2100000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (108, 'PROJ00000108', '腾讯-MASS-实施项目', '制造', '5', 'CUST000018', 'chenjialuo', '236', 225, 'WHALE_MASS', '2', 2600000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (109, 'PROJ00000109', '华为-MASS-实施项目', '制造', '5', 'CUST000020', 'chenjialuo', '236', 226, 'WHALE_MASS', '1', 1800000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (110, 'PROJ00000110', '华为-DQC-实施项目', '制造', '5', 'CUST000020', 'chenjialuo', '236', 227, 'WHALE_DQC', '1', 1200000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (111, 'PROJ00000111', '农行山东-CRM-实施项目', '金融', '1', 'CUST000024', 'zhangwuji', '240', 228, 'WHALE_CRM', '3', 680000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (112, 'PROJ00000112', '重庆农商-CRM-实施项目', '金融', '1', 'CUST000028', 'yangguo', '238', 164, 'WHALE_CRM', '4', 540000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (113, 'PROJ00000113', '厦门国际-CRM-实施项目', '金融', '1', 'CUST000031', 'hufei', '233', 229, 'WHALE_CRM', '2', 580000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (114, 'PROJ00000114', '福建医大附-BI-实施项目', '医疗健康', '3', 'CUST000032', 'hufei', '233', 230, 'WHALE_BI', '3', 980000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (115, 'PROJ00000115', '苏州工业园-CRM-实施项目', '政府', '2', 'CUST000033', 'diyun', '234', 167, 'WHALE_CRM', '1', 640000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (116, 'PROJ00000116', '电力建设-BI-实施项目', '制造', '5', 'CUST000042', 'weixiaobao', '231', 231, 'WHALE_BI', '3', 1100000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (117, 'PROJ00000117', '西安银行-CRM-实施项目', '金融', '1', 'CUST000046', 'yangguo', '238', 172, 'WHALE_CRM', '4', 620000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (118, 'PROJ00000118', '徽商银行-CRM-实施项目', '金融', '1', 'CUST000055', 'hufei', '233', 171, 'WHALE_CRM', '5', 540000.00, 496800.00, 288144.00, 208656.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (119, 'PROJ00000119', '中行广东-BI-实施项目', '金融', '1', 'CUST000077', 'chenjialuo', '236', 128, 'WHALE_BI', '3', 2300000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (120, 'PROJ00000120', '北交所-BI-续签项目', '金融', '1', 'CUST000093', 'weixiaobao', '231', 232, 'WHALE_BI', '2', 1850000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (121, 'PROJ00000121', '北京银行-MASS-实施项目', '金融', '1', 'CUST000039', 'weixiaobao', '231', 233, 'WHALE_MASS', '1', 800000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (122, 'PROJ00000122', '长沙银行-CRM-实施项目', '金融', '1', 'CUST000050', 'zhangwuji', '240', 234, 'WHALE_CRM', '2', 420000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (123, 'PROJ00000123', '桂林银行-CRM-实施项目', '金融', '1', 'CUST000060', 'chenjialuo', '236', 235, 'WHALE_CRM', '1', 360000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-24 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (124, 'PROJ00000124', '内蒙古大数据-CRM-实施项目', '政府', '2', 'CUST000064', 'weixiaobao', '231', 115, 'WHALE_CRM', '2', 480000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (125, 'PROJ00000125', '内蒙古银行-CRM-实施项目', '金融', '1', 'CUST000065', 'weixiaobao', '231', 236, 'WHALE_CRM', '1', 340000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-27 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (126, 'PROJ00000126', '哈尔滨银行-CRM-实施项目', '金融', '1', 'CUST000066', 'weixiaobao', '231', 237, 'WHALE_CRM', '2', 450000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (127, 'PROJ00000127', '吉林银行-BI-实施项目', '金融', '1', 'CUST000068', 'weixiaobao', '231', 119, 'WHALE_BI', '1', 680000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-20 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (128, 'PROJ00000128', '盛京银行-CRM-实施项目', '金融', '1', 'CUST000071', 'weixiaobao', '231', 238, 'WHALE_CRM', '3', 520000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-04-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (129, 'PROJ00000129', '山西银行-CRM-实施项目', '金融', '1', 'CUST000076', 'weixiaobao', '231', 239, 'WHALE_CRM', '2', 380000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (130, 'PROJ00000130', '福州银行-CRM-实施项目', '金融', '1', 'CUST000081', 'hufei', '233', 240, 'WHALE_CRM', '1', 420000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-22 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (131, 'PROJ00000131', '贵阳银行-CRM-实施项目', '金融', '1', 'CUST000084', 'yangguo', '238', 241, 'WHALE_CRM', '1', 390000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-25 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (132, 'PROJ00000132', '太平洋保险-CRM-实施项目', '金融', '1', 'CUST000087', 'hufei', '233', 242, 'WHALE_CRM', '2', 850000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (133, 'PROJ00000133', '国泰君安-CRM-实施项目', '金融', '1', 'CUST000088', 'hufei', '233', 243, 'WHALE_CRM', '1', 760000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-17 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (134, 'PROJ00000134', '深交所-CRM-实施项目', '金融', '1', 'CUST000091', 'chenjialuo', '236', 174, 'WHALE_CRM', '2', 1100000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (135, 'PROJ00000135', '上交所-CRM-实施项目', '金融', '1', 'CUST000092', 'hufei', '233', 173, 'WHALE_CRM', '1', 980000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-14 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (136, 'PROJ00000136', '长沙卫健委-BI-实施项目', '政府', '3', 'CUST000097', 'zhangwuji', '241', 244, 'WHALE_BI', '2', 690000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (137, 'PROJ00000137', '湘雅医院-BI-实施项目', '医疗健康', '3', 'CUST000098', 'zhangwuji', '242', 245, 'WHALE_BI', '1', 840000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-19 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (138, 'PROJ00000138', '成都大数据-BI-实施项目', '政府', '2', 'CUST000099', 'yangguo', '239', 246, 'WHALE_BI', '2', 720000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (139, 'PROJ00000139', '渝市大数据-CRM-实施项目', '政府', '2', 'CUST000100', 'yangguo', '239', 247, 'WHALE_CRM', '1', 460000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-21 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (140, 'PROJ00000140', '广州卫健-MASS-实施项目', '政府', '3', 'CUST000006', 'chenjialuo', '236', 248, 'WHALE_MASS', '3', 780000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-04-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (141, 'PROJ00000141', '北京海淀-BI-实施项目', '政府', '2', 'CUST000003', 'diyun', '234', 249, 'WHALE_BI', '2', 1200000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (142, 'PROJ00000142', '广东人民医院-CRM-实施项目', '医疗健康', '3', 'CUST000007', 'chenjialuo', '236', 250, 'WHALE_CRM', '1', 580000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-23 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (143, 'PROJ00000143', '湖北卫健-BI-实施项目', '政府', '3', 'CUST000012', 'zhangwuji', '240', 251, 'WHALE_BI', '2', 820000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (144, 'PROJ00000144', '苏省大数据-BI-实施项目', '政府', '2', 'CUST000014', 'diyun', '234', 252, 'WHALE_BI', '3', 1350000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-04-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (145, 'PROJ00000145', '山东人民医院-BI-实施项目', '医疗健康', '3', 'CUST000025', 'zhangwuji', '240', 253, 'WHALE_BI', '2', 1150000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (146, 'PROJ00000146', '河南卫健-CRM-实施项目', '政府', '3', 'CUST000027', 'zhangwuji', '240', 72, 'WHALE_CRM', '1', 480000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-18 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (147, 'PROJ00000147', '云南数字经济-BI-实施项目', '政府', '2', 'CUST000030', 'yangguo', '238', 254, 'WHALE_BI', '1', 580000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-15 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (148, 'PROJ00000148', '无锡大数据-BI-实施项目', '政府', '2', 'CUST000034', 'diyun', '234', 255, 'WHALE_BI', '2', 650000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (149, 'PROJ00000149', '川省人民医院-CRM-实施项目', '医疗健康', '3', 'CUST000048', 'yangguo', '238', 256, 'WHALE_CRM', '1', 540000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-26 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (150, 'PROJ00000150', '湖南大数据-CRM-实施项目', '政府', '2', 'CUST000049', 'zhangwuji', '240', 100, 'WHALE_CRM', '1', 620000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-28 07:20:09.215481', NULL, NULL, NULL);

-- ----------------------------
-- Table structure for by_project_task
-- ----------------------------
DROP TABLE IF EXISTS "{{DATACLOUD_DB_SCHEMA}}"."by_project_task";
CREATE TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" (
  "id" int8 NOT NULL DEFAULT nextval('"{{DATACLOUD_DB_SCHEMA}}".by_project_task_id_seq'::regclass),
  "project_code" varchar(50) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "opp_code" varchar(50) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "customer_code" varchar(50) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "product_code" varchar(50) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "task_type" char(1) COLLATE "pg_catalog"."default" NOT NULL DEFAULT '1'::bpchar,
  "initiator_user_id" varchar(100) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "handler_user_id" varchar(100) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "task_status" char(1) COLLATE "pg_catalog"."default" NOT NULL DEFAULT '1'::bpchar,
  "task_name" varchar(200) COLLATE "pg_catalog"."default" NOT NULL,
  "task_desc" text COLLATE "pg_catalog"."default",
  "handle_desc" text COLLATE "pg_catalog"."default",
  "initiate_time" timestamp(6),
  "plan_finish_time" timestamp(6),
  "actual_finish_time" timestamp(6),
  "create_by" varchar(64) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "create_time" timestamp(6),
  "update_by" varchar(64) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "update_time" timestamp(6),
  "remark" varchar(500) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying
)
;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."id" IS '主键';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."project_code" IS '项目编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."opp_code" IS '商机编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."customer_code" IS '客户编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."product_code" IS '产品编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."task_type" IS '任务类型(同项目状态: 1项目启动 2安装部署 3项目交付 4项目上线 5收入确认 6完成回款)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."initiator_user_id" IS '发起人用户编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."handler_user_id" IS '处理人用户编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."task_status" IS '任务状态(1处理中 2正常结束 3异常结束)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."task_name" IS '任务名称';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."task_desc" IS '任务描述';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."handle_desc" IS '处理描述';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."initiate_time" IS '发起时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."plan_finish_time" IS '计划完成时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."actual_finish_time" IS '实际完成时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."create_by" IS '创建者';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."create_time" IS '创建时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."update_by" IS '更新者';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."update_time" IS '更新时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."remark" IS '备注';
COMMENT ON TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" IS '项目任务表';

-- ----------------------------
-- Records of by_project_task
-- ----------------------------
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (1, 'PROJ00000001', NULL, 'CUST000001', 'WHALE_BI', '1', 'songyuanqiao', 'xiexun', '2', '工行北京BI项目启动', NULL, NULL, '2025-12-03 00:00:00', '2025-12-06 00:00:00', '2025-12-06 00:00:00', 'admin', '2025-12-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (2, 'PROJ00000001', NULL, 'CUST000001', 'WHALE_BI', '4', 'songyuanqiao', 'xiexun', '2', '工行北京BI上线验收', NULL, NULL, '2026-01-06 00:00:00', '2026-01-11 00:00:00', '2026-01-11 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (3, 'PROJ00000001', NULL, 'CUST000001', 'WHALE_BI', '6', 'zhangsanfeng', 'xiexun', '2', '工行北京BI回款完成', NULL, NULL, '2026-02-11 00:00:00', '2026-02-16 00:00:00', '2026-02-16 00:00:00', 'admin', '2026-02-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (4, 'PROJ00000002', NULL, 'CUST000001', 'WHALE_CRM', '1', 'songyuanqiao', 'weiyixiao', '2', '工行北京CRM项目启动', NULL, NULL, '2026-01-09 00:00:00', '2026-01-13 00:00:00', '2026-01-13 00:00:00', 'admin', '2026-01-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (5, 'PROJ00000002', NULL, 'CUST000001', 'WHALE_CRM', '4', 'songyuanqiao', 'weiyixiao', '2', '工行北京CRM上线', NULL, NULL, '2026-02-06 00:00:00', '2026-02-13 00:00:00', '2026-02-13 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (6, 'PROJ00000003', NULL, 'CUST000002', 'WHALE_BI', '1', 'yulianzhou', 'yangxiao', '2', '工行北京2-BI启动', NULL, NULL, '2025-12-06 00:00:00', '2025-12-11 00:00:00', '2025-12-11 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (7, 'PROJ00000003', NULL, 'CUST000002', 'WHALE_BI', '6', 'zhangsanfeng', 'yangxiao', '2', '工行北京2-BI回款', NULL, NULL, '2026-02-06 00:00:00', '2026-02-13 00:00:00', '2026-02-13 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (8, 'PROJ00000004', NULL, 'CUST000004', 'WHALE_BI', '1', 'songyuanqiao', 'fanyao', '2', '招商银行BI启动', NULL, NULL, '2025-11-04 00:00:00', '2025-11-09 00:00:00', '2025-11-09 00:00:00', 'admin', '2025-11-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (9, 'PROJ00000004', NULL, 'CUST000004', 'WHALE_BI', '5', 'zhangsanfeng', 'fanyao', '2', '招商银行BI收入确认', NULL, NULL, '2026-01-06 00:00:00', '2026-01-11 00:00:00', '2026-01-11 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (10, 'PROJ00000005', NULL, 'CUST000004', 'WHALE_CRM', '1', 'yulianzhou', 'chengkun', '2', '招商银行CRM启动', NULL, NULL, '2026-01-07 00:00:00', '2026-01-11 00:00:00', '2026-01-11 00:00:00', 'admin', '2026-01-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (11, 'PROJ00000006', NULL, 'CUST000005', 'WHALE_BI', '1', 'songyuanqiao', 'xiexun', '2', '浦发BI启动', NULL, NULL, '2025-12-09 00:00:00', '2025-12-13 00:00:00', '2025-12-13 00:00:00', 'admin', '2025-12-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (12, 'PROJ00000006', NULL, 'CUST000005', 'WHALE_BI', '4', 'songyuanqiao', 'xiexun', '2', '浦发BI上线', NULL, NULL, '2026-01-03 00:00:00', '2026-01-09 00:00:00', '2026-01-09 00:00:00', 'admin', '2026-01-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (13, 'PROJ00000007', NULL, 'CUST000006', 'WHALE_CRM', '1', 'yulianzhou', 'weiyixiao', '2', '广州卫健CRM启动', NULL, NULL, '2025-12-05 00:00:00', '2025-12-10 00:00:00', '2025-12-10 00:00:00', 'admin', '2025-12-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (14, 'PROJ00000008', NULL, 'CUST000006', 'WHALE_BI', '1', 'songyuanqiao', 'yangxiao', '2', '广州卫健BI启动', NULL, NULL, '2026-01-09 00:00:00', '2026-01-13 00:00:00', '2026-01-13 00:00:00', 'admin', '2026-01-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (15, 'PROJ00000009', NULL, 'CUST000007', 'WHALE_CRM', '1', 'yulianzhou', 'fanyao', '2', '广东人民医院CRM启动', NULL, NULL, '2026-01-04 00:00:00', '2026-01-09 00:00:00', '2026-01-09 00:00:00', 'admin', '2026-01-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (16, 'PROJ00000010', NULL, 'CUST000007', 'WHALE_BI', '1', 'songyuanqiao', 'chengkun', '2', '广东人民医院BI启动', NULL, NULL, '2026-02-07 00:00:00', '2026-02-13 00:00:00', '2026-02-13 00:00:00', 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (17, 'PROJ00000010', NULL, 'CUST000007', 'WHALE_BI', '4', 'songyuanqiao', 'chengkun', '2', '广东人民医院BI上线', NULL, NULL, '2026-03-11 00:00:00', '2026-03-17 00:00:00', '2026-03-17 00:00:00', 'admin', '2026-03-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (18, 'PROJ00000011', NULL, 'CUST000008', 'WHALE_BI', '1', 'yulianzhou', 'yintianzheng', '2', '平安银行BI启动', NULL, NULL, '2026-01-06 00:00:00', '2026-01-11 00:00:00', '2026-01-11 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (19, 'PROJ00000011', NULL, 'CUST000008', 'WHALE_BI', '6', 'zhangsanfeng', 'yintianzheng', '2', '平安银行BI回款', NULL, NULL, '2026-02-03 00:00:00', '2026-02-09 00:00:00', '2026-02-09 00:00:00', 'admin', '2026-02-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (20, 'PROJ00000012', NULL, 'CUST000008', 'WHALE_CRM', '1', 'songyuanqiao', 'xiexun', '1', '平安银行CRM启动', NULL, NULL, '2026-02-09 00:00:00', '2026-03-06 00:00:00', NULL, 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (21, 'PROJ00000013', NULL, 'CUST000009', 'WHALE_CRM', '1', 'yulianzhou', 'weiyixiao', '1', '成都高新CRM启动', NULL, NULL, '2026-02-05 00:00:00', '2026-03-03 00:00:00', NULL, 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (22, 'PROJ00000013', NULL, 'CUST000009', 'WHALE_CRM', '3', 'yulianzhou', 'weiyixiao', '1', '成都高新CRM交付', NULL, NULL, '2026-03-06 00:00:00', '2026-04-06 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (23, 'PROJ00000015', NULL, 'CUST000011', 'WHALE_BI', '1', 'songyuanqiao', 'yangxiao', '2', '武汉商行BI启动', NULL, NULL, '2026-02-07 00:00:00', '2026-02-13 00:00:00', '2026-02-13 00:00:00', 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (24, 'PROJ00000015', NULL, 'CUST000011', 'WHALE_BI', '6', 'zhangsanfeng', 'yangxiao', '2', '武汉商行BI回款', NULL, NULL, '2026-03-09 00:00:00', '2026-03-15 00:00:00', '2026-03-15 00:00:00', 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (25, 'PROJ00000018', NULL, 'CUST000013', 'WHALE_BI', '1', 'yulianzhou', 'fanyao', '2', '南京银行BI启动', NULL, NULL, '2026-02-06 00:00:00', '2026-02-11 00:00:00', '2026-02-11 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (26, 'PROJ00000018', NULL, 'CUST000013', 'WHALE_BI', '6', 'zhangsanfeng', 'fanyao', '2', '南京银行BI回款', NULL, NULL, '2026-03-06 00:00:00', '2026-03-11 00:00:00', '2026-03-11 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (27, 'PROJ00000020', NULL, 'CUST000014', 'WHALE_CRM', '1', 'songyuanqiao', 'chengkun', '1', '苏省数据CRM启动', NULL, NULL, '2026-03-09 00:00:00', '2026-04-09 00:00:00', NULL, 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (28, 'PROJ00000020', NULL, 'CUST000014', 'WHALE_CRM', '3', 'songyuanqiao', 'chengkun', '1', '苏省数据CRM交付', NULL, NULL, '2026-04-11 00:00:00', '2026-05-22 07:20:09.741738', NULL, 'admin', '2026-04-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (29, 'PROJ00000022', NULL, 'CUST000015', 'WHALE_BI', '1', 'yulianzhou', 'yintianzheng', '2', '浙大BI启动', NULL, NULL, '2026-03-07 00:00:00', '2026-03-13 00:00:00', '2026-03-13 00:00:00', 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (30, 'PROJ00000022', NULL, 'CUST000015', 'WHALE_BI', '5', 'zhangsanfeng', 'yintianzheng', '2', '浙大BI收入确认', NULL, NULL, '2026-04-09 00:00:00', '2026-04-15 00:00:00', '2026-04-15 00:00:00', 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (31, 'PROJ00000023', NULL, 'CUST000016', 'WHALE_DF', '1', 'songyuanqiao', 'xiexun', '1', '阿里巴巴DF启动', NULL, NULL, '2026-02-05 00:00:00', '2026-03-05 00:00:00', NULL, 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (32, 'PROJ00000023', NULL, 'CUST000016', 'WHALE_DF', '3', 'songyuanqiao', 'xiexun', '1', '阿里巴巴DF交付', NULL, NULL, '2026-03-07 00:00:00', '2026-04-07 00:00:00', NULL, 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (33, 'PROJ00000025', NULL, 'CUST000017', 'WHALE_BI', '1', 'yulianzhou', 'weiyixiao', '2', '宁波银行BI启动', NULL, NULL, '2026-03-06 00:00:00', '2026-03-11 00:00:00', '2026-03-11 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (34, 'PROJ00000025', NULL, 'CUST000017', 'WHALE_BI', '5', 'zhangsanfeng', 'weiyixiao', '2', '宁波银行BI收入确认', NULL, NULL, '2026-04-07 00:00:00', '2026-04-13 00:00:00', '2026-04-13 00:00:00', 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (35, 'PROJ00000026', NULL, 'CUST000018', 'WHALE_DF', '1', 'songyuanqiao', 'yangxiao', '1', '腾讯DF启动', NULL, NULL, '2026-03-09 00:00:00', '2026-04-09 00:00:00', NULL, 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (36, 'PROJ00000031', NULL, 'CUST000021', 'WHALE_BI', '1', 'yulianzhou', 'fanyao', '1', '建行天津BI启动', NULL, NULL, '2026-02-04 00:00:00', '2026-03-04 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (37, 'PROJ00000031', NULL, 'CUST000021', 'WHALE_BI', '3', 'yulianzhou', 'fanyao', '1', '建行天津BI交付', NULL, NULL, '2026-03-05 00:00:00', '2026-04-05 00:00:00', NULL, 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (38, 'PROJ00000033', NULL, 'CUST000024', 'WHALE_BI', '1', 'songyuanqiao', 'chengkun', '1', '农行山东BI启动', NULL, NULL, '2026-02-07 00:00:00', '2026-03-07 00:00:00', NULL, 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (39, 'PROJ00000035', NULL, 'CUST000028', 'WHALE_BI', '1', 'yulianzhou', 'yintianzheng', '1', '重庆农商BI启动', NULL, NULL, '2026-03-05 00:00:00', '2026-04-05 00:00:00', NULL, 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (40, 'PROJ00000038', NULL, 'CUST000031', 'WHALE_BI', '1', 'songyuanqiao', 'xiexun', '1', '厦门国际BI启动', NULL, NULL, '2026-03-08 00:00:00', '2026-04-08 00:00:00', NULL, 'admin', '2026-03-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (41, 'PROJ00000041', NULL, 'CUST000039', 'WHALE_BI', '1', 'yulianzhou', 'weiyixiao', '1', '北京银行BI启动', NULL, NULL, '2026-02-06 00:00:00', '2026-03-06 00:00:00', NULL, 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (42, 'PROJ00000041', NULL, 'CUST000039', 'WHALE_BI', '3', 'yulianzhou', 'weiyixiao', '1', '北京银行BI交付', NULL, NULL, '2026-03-07 00:00:00', '2026-04-07 00:00:00', NULL, 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (43, 'PROJ00000042', NULL, 'CUST000044', 'WHALE_BI', '1', 'songyuanqiao', 'yangxiao', '2', '广州农商BI启动', NULL, NULL, '2026-01-09 00:00:00', '2026-01-13 00:00:00', '2026-01-13 00:00:00', 'admin', '2026-01-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (44, 'PROJ00000042', NULL, 'CUST000044', 'WHALE_BI', '6', 'zhangsanfeng', 'yangxiao', '2', '广州农商BI回款', NULL, NULL, '2026-02-06 00:00:00', '2026-02-11 00:00:00', '2026-02-11 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (45, 'PROJ00000043', NULL, 'CUST000050', 'WHALE_BI', '1', 'yulianzhou', 'fanyao', '1', '长沙银行BI启动', NULL, NULL, '2026-02-04 00:00:00', '2026-03-04 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (46, 'PROJ00000043', NULL, 'CUST000050', 'WHALE_BI', '3', 'yulianzhou', 'fanyao', '1', '长沙银行BI交付', NULL, NULL, '2026-03-05 00:00:00', '2026-04-05 00:00:00', NULL, 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (47, 'PROJ00000045', NULL, 'CUST000055', 'WHALE_BI', '1', 'songyuanqiao', 'chengkun', '1', '徽商银行BI启动', NULL, NULL, '2026-02-07 00:00:00', '2026-03-07 00:00:00', NULL, 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (48, 'PROJ00000055', NULL, 'CUST000081', 'WHALE_BI', '1', 'yulianzhou', 'yintianzheng', '2', '福州银行BI启动', NULL, NULL, '2025-12-04 00:00:00', '2025-12-09 00:00:00', '2025-12-09 00:00:00', 'admin', '2025-12-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (49, 'PROJ00000055', NULL, 'CUST000081', 'WHALE_BI', '6', 'zhangsanfeng', 'yintianzheng', '2', '福州银行BI回款', NULL, NULL, '2026-01-03 00:00:00', '2026-01-09 00:00:00', '2026-01-09 00:00:00', 'admin', '2026-01-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (50, 'PROJ00000061', NULL, 'CUST000037', 'WHALE_CRM', '1', 'songyuanqiao', 'xiexun', '2', '沪大数据CRM启动', NULL, NULL, '2025-12-06 00:00:00', '2025-12-11 00:00:00', '2025-12-11 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (51, 'PROJ00000061', NULL, 'CUST000037', 'WHALE_CRM', '5', 'zhangsanfeng', 'xiexun', '2', '沪大数据CRM收入', NULL, NULL, '2026-01-04 00:00:00', '2026-01-09 00:00:00', '2026-01-09 00:00:00', 'admin', '2026-01-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (52, 'PROJ00000062', NULL, 'CUST000040', 'WHALE_BI', '1', 'yulianzhou', 'weiyixiao', '1', '北京大数据BI启动', NULL, NULL, '2026-02-05 00:00:00', '2026-03-05 00:00:00', NULL, 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (53, 'PROJ00000081', NULL, 'CUST000041', 'WHALE_BI', '1', 'songyuanqiao', 'yangxiao', '1', '北京协和BI启动', NULL, NULL, '2026-02-08 00:00:00', '2026-03-08 00:00:00', NULL, 'admin', '2026-02-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (54, 'PROJ00000082', NULL, 'CUST000048', 'WHALE_BI', '1', 'yulianzhou', 'fanyao', '1', '川省人民医院BI启动', NULL, NULL, '2026-03-06 00:00:00', '2026-04-06 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (55, 'PROJ00000088', NULL, 'CUST000096', 'WHALE_BI', '1', 'songyuanqiao', 'chengkun', '1', '鄂省人民医院BI启动', NULL, NULL, '2026-02-04 00:00:00', '2026-03-04 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (56, 'PROJ00000090', NULL, 'CUST000036', 'WHALE_CRM', '1', 'yulianzhou', 'yintianzheng', '2', '上交大CRM启动', NULL, NULL, '2025-12-05 00:00:00', '2025-12-09 00:00:00', '2025-12-09 00:00:00', 'admin', '2025-12-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (57, 'PROJ00000090', NULL, 'CUST000036', 'WHALE_CRM', '5', 'zhangsanfeng', 'yintianzheng', '2', '上交大CRM收入', NULL, NULL, '2026-01-05 00:00:00', '2026-01-11 00:00:00', '2026-01-11 00:00:00', 'admin', '2026-01-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (58, 'PROJ00000096', NULL, 'CUST000043', 'WHALE_MASS', '1', 'songyuanqiao', 'xiexun', '2', '移动广东MASS启动', NULL, NULL, '2025-12-07 00:00:00', '2025-12-11 00:00:00', '2025-12-11 00:00:00', 'admin', '2025-12-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (59, 'PROJ00000096', NULL, 'CUST000043', 'WHALE_MASS', '6', 'zhangsanfeng', 'xiexun', '2', '移动广东MASS回款', NULL, NULL, '2026-01-05 00:00:00', '2026-01-11 00:00:00', '2026-01-11 00:00:00', 'admin', '2026-01-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (60, 'PROJ00000097', NULL, 'CUST000038', 'WHALE_MASS', '1', 'yulianzhou', 'weiyixiao', '1', '中国电信MASS启动', NULL, NULL, '2026-01-06 00:00:00', '2026-02-06 00:00:00', NULL, 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (61, 'PROJ00000097', NULL, 'CUST000038', 'WHALE_MASS', '3', 'yulianzhou', 'weiyixiao', '1', '中国电信MASS交付', NULL, NULL, '2026-02-07 00:00:00', '2026-03-07 00:00:00', NULL, 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (62, 'PROJ00000106', NULL, 'CUST000013', 'WHALE_CRM', '1', 'songyuanqiao', 'yangxiao', '1', '南京银行CRM启动', NULL, NULL, '2026-02-09 00:00:00', '2026-03-09 00:00:00', NULL, 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (63, 'PROJ00000107', NULL, 'CUST000016', 'WHALE_MASS', '1', 'yulianzhou', 'fanyao', '1', '阿里MASS启动', NULL, NULL, '2026-02-04 00:00:00', '2026-03-04 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);

-- ----------------------------
-- Table structure for by_rd_task
-- ----------------------------
DROP TABLE IF EXISTS "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task";
CREATE TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" (
  "id" int8 NOT NULL DEFAULT nextval('"{{DATACLOUD_DB_SCHEMA}}".by_rd_task_id_seq'::regclass),
  "project_code" varchar(50) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "opp_code" varchar(50) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "customer_code" varchar(50) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "product_code" varchar(50) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "task_type" char(1) COLLATE "pg_catalog"."default" NOT NULL DEFAULT '1'::bpchar,
  "initiator_user_id" varchar(100) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "handler_user_id" varchar(100) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "task_status" char(1) COLLATE "pg_catalog"."default" NOT NULL DEFAULT '1'::bpchar,
  "task_name" varchar(200) COLLATE "pg_catalog"."default" NOT NULL,
  "task_desc" text COLLATE "pg_catalog"."default",
  "handle_desc" text COLLATE "pg_catalog"."default",
  "initiate_time" timestamp(6),
  "plan_finish_time" timestamp(6),
  "actual_finish_time" timestamp(6),
  "create_by" varchar(64) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "create_time" timestamp(6),
  "update_by" varchar(64) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying,
  "update_time" timestamp(6),
  "remark" varchar(500) COLLATE "pg_catalog"."default" DEFAULT NULL::character varying
)
;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."id" IS '主键';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."project_code" IS '项目编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."opp_code" IS '商机编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."customer_code" IS '客户编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."product_code" IS '产品编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."task_type" IS '任务类型(1需求分析 2产品设计 3功能开发 4特性测试 5故障分析 6故障处理)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."initiator_user_id" IS '发起人用户编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."handler_user_id" IS '处理人用户编码';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."task_status" IS '任务状态(1处理中 2正常结束 3异常结束)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."task_name" IS '任务名称';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."task_desc" IS '任务描述';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."handle_desc" IS '处理描述';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."initiate_time" IS '发起时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."plan_finish_time" IS '计划完成时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."actual_finish_time" IS '实际完成时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."create_by" IS '创建者';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."create_time" IS '创建时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."update_by" IS '更新者';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."update_time" IS '更新时间';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."remark" IS '备注';
COMMENT ON TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" IS '研发任务表';

-- ----------------------------
-- Records of by_rd_task
-- ----------------------------
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (1, 'PROJ00000001', NULL, 'CUST000001', 'WHALE_BI', '1', 'songyuanqiao', 'hongqigong', '2', '工行北京BI需求分析', NULL, NULL, '2025-12-04 00:00:00', '2025-12-11 00:00:00', '2025-12-11 00:00:00', 'admin', '2025-12-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (2, 'PROJ00000001', NULL, 'CUST000001', 'WHALE_BI', '2', 'songyuanqiao', 'huangyaoshi', '2', '工行北京BI产品设计', NULL, NULL, '2025-12-12 00:00:00', '2026-01-21 00:00:00', '2026-01-21 00:00:00', 'admin', '2025-12-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (3, 'PROJ00000001', NULL, 'CUST000001', 'WHALE_BI', '3', 'songyuanqiao', 'ouyangfeng', '2', '工行北京BI功能开发', NULL, NULL, '2026-01-23 00:00:00', '2026-02-21 00:00:00', '2026-02-21 00:00:00', 'admin', '2026-01-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (4, 'PROJ00000001', NULL, 'CUST000001', 'WHALE_BI', '4', 'zhangcuishan', 'duanyu', '2', '工行北京BI特性测试', NULL, NULL, '2026-02-23 00:00:00', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (5, 'PROJ00000003', NULL, 'CUST000002', 'WHALE_BI', '1', 'songyuanqiao', 'xuzhu', '2', '工行北京2-BI需求', NULL, NULL, '2025-12-06 00:00:00', '2025-12-13 00:00:00', '2025-12-13 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (6, 'PROJ00000003', NULL, 'CUST000002', 'WHALE_BI', '3', 'songyuanqiao', 'zhoubotong', '2', '工行北京2-BI开发', NULL, NULL, '2026-01-16 00:00:00', '2026-02-16 00:00:00', '2026-02-16 00:00:00', 'admin', '2026-01-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (7, 'PROJ00000004', NULL, 'CUST000004', 'WHALE_BI', '1', 'yulianzhou', 'murongfu', '2', '招商银行BI需求', NULL, NULL, '2025-11-05 00:00:00', '2025-11-13 00:00:00', '2025-11-13 00:00:00', 'admin', '2025-11-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (8, 'PROJ00000004', NULL, 'CUST000004', 'WHALE_BI', '2', 'yulianzhou', 'youtanzhi', '2', '招商银行BI设计', NULL, NULL, '2025-11-15 00:00:00', '2025-12-21 00:00:00', '2025-12-21 00:00:00', 'admin', '2025-11-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (9, 'PROJ00000004', NULL, 'CUST000004', 'WHALE_BI', '3', 'yulianzhou', 'yuebuqun', '2', '招商银行BI开发', NULL, NULL, '2025-12-23 00:00:00', '2026-01-23 00:00:00', '2026-01-23 00:00:00', 'admin', '2025-12-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (10, 'PROJ00000004', NULL, 'CUST000004', 'WHALE_BI', '4', 'zhangcuishan', 'fengqingyang', '2', '招商银行BI测试', NULL, NULL, '2026-01-25 00:00:00', '2026-01-29 00:00:00', '2026-01-29 00:00:00', 'admin', '2026-01-25 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (11, 'PROJ00000006', NULL, 'CUST000005', 'WHALE_BI', '1', 'songyuanqiao', 'saodiseng', '2', '浦发BI需求', NULL, NULL, '2025-12-09 00:00:00', '2025-12-15 00:00:00', '2025-12-15 00:00:00', 'admin', '2025-12-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (12, 'PROJ00000006', NULL, 'CUST000005', 'WHALE_BI', '3', 'songyuanqiao', 'hongqigong', '2', '浦发BI开发', NULL, NULL, '2026-01-17 00:00:00', '2026-02-17 00:00:00', '2026-02-17 00:00:00', 'admin', '2026-01-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (13, 'PROJ00000008', NULL, 'CUST000006', 'WHALE_BI', '1', 'yulianzhou', 'huangyaoshi', '2', '广州卫健BI需求', NULL, NULL, '2026-01-09 00:00:00', '2026-01-15 00:00:00', '2026-01-15 00:00:00', 'admin', '2026-01-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (14, 'PROJ00000008', NULL, 'CUST000006', 'WHALE_BI', '3', 'yulianzhou', 'ouyangfeng', '2', '广州卫健BI开发', NULL, NULL, '2026-02-16 00:00:00', '2026-03-16 00:00:00', '2026-03-16 00:00:00', 'admin', '2026-02-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (15, 'PROJ00000010', NULL, 'CUST000007', 'WHALE_BI', '1', 'songyuanqiao', 'duanyu', '2', '广东人民医院BI需求', NULL, NULL, '2026-02-07 00:00:00', '2026-02-13 00:00:00', '2026-02-13 00:00:00', 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (16, 'PROJ00000010', NULL, 'CUST000007', 'WHALE_BI', '3', 'songyuanqiao', 'xuzhu', '2', '广东人民医院BI开发', NULL, NULL, '2026-03-15 00:00:00', '2026-04-15 00:00:00', '2026-04-15 00:00:00', 'admin', '2026-03-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (17, 'PROJ00000011', NULL, 'CUST000008', 'WHALE_BI', '1', 'yulianzhou', 'zhoubotong', '2', '平安银行BI需求', NULL, NULL, '2026-01-06 00:00:00', '2026-01-12 00:00:00', '2026-01-12 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (18, 'PROJ00000011', NULL, 'CUST000008', 'WHALE_BI', '2', 'yulianzhou', 'murongfu', '2', '平安银行BI设计', NULL, NULL, '2026-01-13 00:00:00', '2026-02-21 00:00:00', '2026-02-21 00:00:00', 'admin', '2026-01-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (19, 'PROJ00000011', NULL, 'CUST000008', 'WHALE_BI', '3', 'songyuanqiao', 'youtanzhi', '2', '平安银行BI开发', NULL, NULL, '2026-02-23 00:00:00', '2026-03-23 00:00:00', '2026-03-23 00:00:00', 'admin', '2026-02-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (20, 'PROJ00000011', NULL, 'CUST000008', 'WHALE_BI', '4', 'zhangcuishan', 'yuebuqun', '2', '平安银行BI测试', NULL, NULL, '2026-03-25 00:00:00', '2026-03-29 00:00:00', '2026-03-29 00:00:00', 'admin', '2026-03-25 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (21, 'PROJ00000012', NULL, 'CUST000008', 'WHALE_CRM', '1', 'songyuanqiao', 'fengqingyang', '2', '平安银行CRM需求', NULL, NULL, '2026-02-09 00:00:00', '2026-02-16 00:00:00', '2026-02-16 00:00:00', 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (22, 'PROJ00000012', NULL, 'CUST000008', 'WHALE_CRM', '2', 'songyuanqiao', 'saodiseng', '1', '平安银行CRM设计', NULL, NULL, '2026-03-17 00:00:00', '2026-04-17 00:00:00', NULL, 'admin', '2026-03-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (23, 'PROJ00000013', NULL, 'CUST000009', 'WHALE_CRM', '1', 'yulianzhou', 'hongqigong', '2', '成都高新CRM需求', NULL, NULL, '2026-02-05 00:00:00', '2026-02-11 00:00:00', '2026-02-11 00:00:00', 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (24, 'PROJ00000013', NULL, 'CUST000009', 'WHALE_CRM', '3', 'yulianzhou', 'huangyaoshi', '1', '成都高新CRM开发', NULL, NULL, '2026-03-13 00:00:00', '2026-04-13 00:00:00', NULL, 'admin', '2026-03-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (25, 'PROJ00000015', NULL, 'CUST000011', 'WHALE_BI', '1', 'songyuanqiao', 'ouyangfeng', '2', '武汉商行BI需求', NULL, NULL, '2026-02-07 00:00:00', '2026-02-13 00:00:00', '2026-02-13 00:00:00', 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (26, 'PROJ00000015', NULL, 'CUST000011', 'WHALE_BI', '3', 'songyuanqiao', 'duanyu', '2', '武汉商行BI开发', NULL, NULL, '2026-03-15 00:00:00', '2026-04-15 00:00:00', '2026-04-15 00:00:00', 'admin', '2026-03-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (27, 'PROJ00000016', NULL, 'CUST000011', 'WHALE_CRM', '1', 'yulianzhou', 'xuzhu', '1', '武汉商行CRM需求', NULL, NULL, '2026-02-04 00:00:00', '2026-03-04 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (28, 'PROJ00000018', NULL, 'CUST000013', 'WHALE_BI', '1', 'songyuanqiao', 'zhoubotong', '2', '南京银行BI需求', NULL, NULL, '2026-02-06 00:00:00', '2026-02-12 00:00:00', '2026-02-12 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (29, 'PROJ00000018', NULL, 'CUST000013', 'WHALE_BI', '3', 'songyuanqiao', 'murongfu', '2', '南京银行BI开发', NULL, NULL, '2026-03-14 00:00:00', '2026-04-14 00:00:00', '2026-04-14 00:00:00', 'admin', '2026-03-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (30, 'PROJ00000020', NULL, 'CUST000014', 'WHALE_CRM', '1', 'yulianzhou', 'youtanzhi', '1', '苏省数据CRM需求', NULL, NULL, '2026-03-09 00:00:00', '2026-04-09 00:00:00', NULL, 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (31, 'PROJ00000020', NULL, 'CUST000014', 'WHALE_CRM', '3', 'yulianzhou', 'yuebuqun', '1', '苏省数据CRM开发', NULL, NULL, '2026-04-11 00:00:00', '2026-05-22 07:20:10.048148', NULL, 'admin', '2026-04-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (32, 'PROJ00000022', NULL, 'CUST000015', 'WHALE_BI', '1', 'songyuanqiao', 'fengqingyang', '2', '浙大BI需求', NULL, NULL, '2026-03-07 00:00:00', '2026-03-13 00:00:00', '2026-03-13 00:00:00', 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (33, 'PROJ00000023', NULL, 'CUST000016', 'WHALE_DF', '1', 'yulianzhou', 'saodiseng', '1', '阿里DF需求', NULL, NULL, '2026-02-05 00:00:00', '2026-03-05 00:00:00', NULL, 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (34, 'PROJ00000023', NULL, 'CUST000016', 'WHALE_DF', '2', 'yulianzhou', 'hongqigong', '1', '阿里DF设计', NULL, NULL, '2026-03-06 00:00:00', '2026-04-06 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (35, 'PROJ00000026', NULL, 'CUST000018', 'WHALE_DF', '1', 'songyuanqiao', 'huangyaoshi', '1', '腾讯DF需求', NULL, NULL, '2026-03-09 00:00:00', '2026-04-09 00:00:00', NULL, 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (36, 'PROJ00000031', NULL, 'CUST000021', 'WHALE_BI', '1', 'yulianzhou', 'ouyangfeng', '1', '建行天津BI需求', NULL, NULL, '2026-02-04 00:00:00', '2026-03-04 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (37, 'PROJ00000033', NULL, 'CUST000024', 'WHALE_BI', '1', 'songyuanqiao', 'duanyu', '1', '农行山东BI需求', NULL, NULL, '2026-02-07 00:00:00', '2026-03-07 00:00:00', NULL, 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (38, 'PROJ00000033', NULL, 'CUST000024', 'WHALE_BI', '3', 'songyuanqiao', 'xuzhu', '1', '农行山东BI开发', NULL, NULL, '2026-03-09 00:00:00', '2026-04-09 00:00:00', NULL, 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (39, 'PROJ00000035', NULL, 'CUST000028', 'WHALE_BI', '1', 'yulianzhou', 'zhoubotong', '1', '重庆农商BI需求', NULL, NULL, '2026-03-05 00:00:00', '2026-04-05 00:00:00', NULL, 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (40, 'PROJ00000038', NULL, 'CUST000031', 'WHALE_BI', '1', 'songyuanqiao', 'murongfu', '1', '厦门国际BI需求', NULL, NULL, '2026-03-08 00:00:00', '2026-04-08 00:00:00', NULL, 'admin', '2026-03-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (41, 'PROJ00000041', NULL, 'CUST000039', 'WHALE_BI', '1', 'yulianzhou', 'youtanzhi', '1', '北京银行BI需求', NULL, NULL, '2026-02-06 00:00:00', '2026-03-06 00:00:00', NULL, 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (42, 'PROJ00000041', NULL, 'CUST000039', 'WHALE_BI', '3', 'yulianzhou', 'yuebuqun', '1', '北京银行BI开发', NULL, NULL, '2026-03-07 00:00:00', '2026-04-07 00:00:00', NULL, 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (43, 'PROJ00000042', NULL, 'CUST000044', 'WHALE_BI', '1', 'songyuanqiao', 'fengqingyang', '2', '广州农商BI需求', NULL, NULL, '2026-01-09 00:00:00', '2026-01-15 00:00:00', '2026-01-15 00:00:00', 'admin', '2026-01-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (44, 'PROJ00000042', NULL, 'CUST000044', 'WHALE_BI', '3', 'songyuanqiao', 'saodiseng', '2', '广州农商BI开发', NULL, NULL, '2026-02-17 00:00:00', '2026-03-17 00:00:00', '2026-03-17 00:00:00', 'admin', '2026-02-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (45, 'PROJ00000042', NULL, 'CUST000044', 'WHALE_BI', '4', 'zhangcuishan', 'hongqigong', '2', '广州农商BI测试', NULL, NULL, '2026-03-19 00:00:00', '2026-03-25 00:00:00', '2026-03-25 00:00:00', 'admin', '2026-03-19 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (46, 'PROJ00000043', NULL, 'CUST000050', 'WHALE_BI', '1', 'yulianzhou', 'huangyaoshi', '1', '长沙银行BI需求', NULL, NULL, '2026-02-04 00:00:00', '2026-03-04 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (47, 'PROJ00000043', NULL, 'CUST000050', 'WHALE_BI', '3', 'yulianzhou', 'ouyangfeng', '1', '长沙银行BI开发', NULL, NULL, '2026-03-05 00:00:00', '2026-04-05 00:00:00', NULL, 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (48, 'PROJ00000055', NULL, 'CUST000081', 'WHALE_BI', '1', 'songyuanqiao', 'duanyu', '2', '福州银行BI需求', NULL, NULL, '2025-12-04 00:00:00', '2025-12-10 00:00:00', '2025-12-10 00:00:00', 'admin', '2025-12-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (49, 'PROJ00000055', NULL, 'CUST000081', 'WHALE_BI', '3', 'songyuanqiao', 'xuzhu', '2', '福州银行BI开发', NULL, NULL, '2026-01-12 00:00:00', '2026-02-12 00:00:00', '2026-02-12 00:00:00', 'admin', '2026-01-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (50, 'PROJ00000055', NULL, 'CUST000081', 'WHALE_BI', '4', 'zhangcuishan', 'zhoubotong', '2', '福州银行BI测试', NULL, NULL, '2026-02-14 00:00:00', '2026-02-19 00:00:00', '2026-02-19 00:00:00', 'admin', '2026-02-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (51, 'PROJ00000061', NULL, 'CUST000037', 'WHALE_CRM', '1', 'yulianzhou', 'murongfu', '2', '沪大数据CRM需求', NULL, NULL, '2025-12-06 00:00:00', '2025-12-12 00:00:00', '2025-12-12 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (52, 'PROJ00000061', NULL, 'CUST000037', 'WHALE_CRM', '3', 'yulianzhou', 'youtanzhi', '2', '沪大数据CRM开发', NULL, NULL, '2026-01-14 00:00:00', '2026-02-14 00:00:00', '2026-02-14 00:00:00', 'admin', '2026-01-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (53, 'PROJ00000062', NULL, 'CUST000040', 'WHALE_BI', '1', 'songyuanqiao', 'yuebuqun', '1', '北京大数据BI需求', NULL, NULL, '2026-02-05 00:00:00', '2026-03-05 00:00:00', NULL, 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (54, 'PROJ00000081', NULL, 'CUST000041', 'WHALE_BI', '1', 'yulianzhou', 'fengqingyang', '1', '北京协和BI需求', NULL, NULL, '2026-02-08 00:00:00', '2026-03-08 00:00:00', NULL, 'admin', '2026-02-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (55, 'PROJ00000082', NULL, 'CUST000048', 'WHALE_BI', '1', 'songyuanqiao', 'saodiseng', '1', '川省人民医院BI需求', NULL, NULL, '2026-03-06 00:00:00', '2026-04-06 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (56, 'PROJ00000086', NULL, 'CUST000073', 'WHALE_BI', '1', 'yulianzhou', 'hongqigong', '1', '浙省人民医院BI需求', NULL, NULL, '2026-03-13 00:00:00', '2026-04-13 00:00:00', NULL, 'admin', '2026-03-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (57, 'PROJ00000088', NULL, 'CUST000096', 'WHALE_BI', '1', 'songyuanqiao', 'huangyaoshi', '1', '鄂省人民医院BI需求', NULL, NULL, '2026-02-04 00:00:00', '2026-03-04 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (58, 'PROJ00000090', NULL, 'CUST000036', 'WHALE_CRM', '1', 'yulianzhou', 'ouyangfeng', '2', '上交大CRM需求', NULL, NULL, '2025-12-05 00:00:00', '2025-12-11 00:00:00', '2025-12-11 00:00:00', 'admin', '2025-12-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (59, 'PROJ00000090', NULL, 'CUST000036', 'WHALE_CRM', '3', 'yulianzhou', 'duanyu', '2', '上交大CRM开发', NULL, NULL, '2026-01-13 00:00:00', '2026-02-13 00:00:00', '2026-02-13 00:00:00', 'admin', '2026-01-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (60, 'PROJ00000096', NULL, 'CUST000043', 'WHALE_MASS', '1', 'songyuanqiao', 'xuzhu', '2', '移动广东MASS需求', NULL, NULL, '2025-12-07 00:00:00', '2025-12-13 00:00:00', '2025-12-13 00:00:00', 'admin', '2025-12-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (61, 'PROJ00000096', NULL, 'CUST000043', 'WHALE_MASS', '3', 'songyuanqiao', 'zhoubotong', '2', '移动广东MASS开发', NULL, NULL, '2026-01-15 00:00:00', '2026-02-15 00:00:00', '2026-02-15 00:00:00', 'admin', '2026-01-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (62, 'PROJ00000097', NULL, 'CUST000038', 'WHALE_MASS', '1', 'yulianzhou', 'murongfu', '1', '中国电信MASS需求', NULL, NULL, '2026-01-06 00:00:00', '2026-02-06 00:00:00', NULL, 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (63, 'PROJ00000097', NULL, 'CUST000038', 'WHALE_MASS', '3', 'yulianzhou', 'youtanzhi', '1', '中国电信MASS开发', NULL, NULL, '2026-02-08 00:00:00', '2026-03-08 00:00:00', NULL, 'admin', '2026-02-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (64, 'PROJ00000098', NULL, 'CUST000074', 'WHALE_DF', '1', 'songyuanqiao', 'yuebuqun', '1', '网易DF需求', NULL, NULL, '2026-03-06 00:00:00', '2026-04-06 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (65, 'PROJ00000099', NULL, 'CUST000089', 'WHALE_DF', '1', 'yulianzhou', 'fengqingyang', '1', '华能集团DF需求', NULL, NULL, '2026-03-08 00:00:00', '2026-04-08 00:00:00', NULL, 'admin', '2026-03-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (66, 'PROJ00000106', NULL, 'CUST000013', 'WHALE_CRM', '1', 'songyuanqiao', 'saodiseng', '1', '南京银行CRM需求', NULL, NULL, '2026-02-09 00:00:00', '2026-03-09 00:00:00', NULL, 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (67, 'PROJ00000107', NULL, 'CUST000016', 'WHALE_MASS', '1', 'yulianzhou', 'hongqigong', '1', '阿里MASS需求', NULL, NULL, '2026-02-04 00:00:00', '2026-03-04 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (68, 'PROJ00000119', NULL, 'CUST000077', 'WHALE_BI', '1', 'songyuanqiao', 'huangyaoshi', '1', '中行广东BI需求', NULL, NULL, '2026-03-10 00:00:00', '2026-04-10 00:00:00', NULL, 'admin', '2026-03-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (69, 'PROJ00000001', NULL, 'CUST000001', 'WHALE_BI', '5', 'songyuanqiao', 'ouyangfeng', '2', '工行北京BI故障分析', NULL, NULL, '2026-01-16 00:00:00', '2026-01-18 00:00:00', '2026-01-18 00:00:00', 'admin', '2026-01-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (70, 'PROJ00000001', NULL, 'CUST000001', 'WHALE_BI', '6', 'songyuanqiao', 'ouyangfeng', '2', '工行北京BI故障处理', NULL, NULL, '2026-01-18 00:00:00', '2026-01-20 00:00:00', '2026-01-20 00:00:00', 'admin', '2026-01-18 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (71, 'PROJ00000011', NULL, 'CUST000008', 'WHALE_BI', '5', 'yulianzhou', 'duanyu', '2', '平安银行BI故障分析', NULL, NULL, '2026-02-06 00:00:00', '2026-02-08 00:00:00', '2026-02-08 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (72, 'PROJ00000022', NULL, 'CUST000015', 'WHALE_BI', '5', 'songyuanqiao', 'xuzhu', '2', '浙大BI故障分析', NULL, NULL, '2026-04-11 00:00:00', '2026-04-13 00:00:00', '2026-04-13 00:00:00', 'admin', '2026-04-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (73, 'PROJ00000022', NULL, 'CUST000015', 'WHALE_BI', '6', 'songyuanqiao', 'xuzhu', '2', '浙大BI故障处理', NULL, NULL, '2026-04-13 00:00:00', '2026-04-15 00:00:00', '2026-04-15 00:00:00', 'admin', '2026-04-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (74, 'PROJ00000015', NULL, 'CUST000011', 'WHALE_BI', '5', 'yulianzhou', 'zhoubotong', '2', '武汉商行BI故障分析', NULL, NULL, '2026-04-09 00:00:00', '2026-04-11 00:00:00', '2026-04-11 00:00:00', 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (75, 'PROJ00000055', NULL, 'CUST000081', 'WHALE_BI', '5', 'songyuanqiao', 'murongfu', '1', '福州银行BI故障分析', NULL, NULL, '2026-04-27 07:20:10.048148', '2026-05-17 07:20:10.048148', NULL, 'admin', '2026-04-27 07:20:10.048148', NULL, NULL, NULL);

-- ----------------------------
-- Indexes structure for table by_customer
-- ----------------------------
CREATE INDEX "idx_dept_id" ON "{{DATACLOUD_DB_SCHEMA}}"."by_customer" USING btree (
  "dept_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "idx_sales_user_id" ON "{{DATACLOUD_DB_SCHEMA}}"."by_customer" USING btree (
  "sales_user_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE UNIQUE INDEX "uk_customer_code" ON "{{DATACLOUD_DB_SCHEMA}}"."by_customer" USING btree (
  "customer_code" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Triggers structure for table by_customer
-- ----------------------------
CREATE TRIGGER "trg_by_customer_after_insert" AFTER INSERT ON "{{DATACLOUD_DB_SCHEMA}}"."by_customer"
FOR EACH ROW
EXECUTE PROCEDURE "{{DATACLOUD_DB_SCHEMA}}"."trg_fn_by_customer_sync_term"();

-- ----------------------------
-- Primary Key structure for table by_customer
-- ----------------------------
ALTER TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_customer" ADD CONSTRAINT "by_customer_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table by_opp_task
-- ----------------------------
CREATE INDEX "idx_customer_code3" ON "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" USING btree (
  "customer_code" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "idx_handler_user_id3" ON "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" USING btree (
  "handler_user_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "idx_initiator_user_id3" ON "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" USING btree (
  "initiator_user_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "idx_opp_code3" ON "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" USING btree (
  "opp_code" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key structure for table by_opp_task
-- ----------------------------
ALTER TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" ADD CONSTRAINT "by_opp_task_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table by_opportunity
-- ----------------------------
CREATE INDEX "idx_customer_code" ON "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" USING btree (
  "customer_code" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "idx_dept_id12" ON "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" USING btree (
  "dept_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "idx_sales_user_id12" ON "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" USING btree (
  "sales_user_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE UNIQUE INDEX "uk_opp_code" ON "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" USING btree (
  "opp_code" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Triggers structure for table by_opportunity
-- ----------------------------
CREATE TRIGGER "trg_by_opportunity_after_insert" AFTER INSERT ON "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"
FOR EACH ROW
EXECUTE PROCEDURE "{{DATACLOUD_DB_SCHEMA}}"."trg_fn_by_opportunity_sync_term"();

-- ----------------------------
-- Primary Key structure for table by_opportunity
-- ----------------------------
ALTER TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" ADD CONSTRAINT "by_opportunity_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table by_project
-- ----------------------------
CREATE INDEX "idx_customer_code10" ON "{{DATACLOUD_DB_SCHEMA}}"."by_project" USING btree (
  "customer_code" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "idx_dept_id10" ON "{{DATACLOUD_DB_SCHEMA}}"."by_project" USING btree (
  "dept_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "idx_opp_id10" ON "{{DATACLOUD_DB_SCHEMA}}"."by_project" USING btree (
  "opp_id" "pg_catalog"."int8_ops" ASC NULLS LAST
);
CREATE INDEX "idx_sales_user_id10" ON "{{DATACLOUD_DB_SCHEMA}}"."by_project" USING btree (
  "sales_user_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE UNIQUE INDEX "uk_project_code10" ON "{{DATACLOUD_DB_SCHEMA}}"."by_project" USING btree (
  "project_code" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Triggers structure for table by_project
-- ----------------------------
CREATE TRIGGER "trg_by_project_after_insert" AFTER INSERT ON "{{DATACLOUD_DB_SCHEMA}}"."by_project"
FOR EACH ROW
EXECUTE PROCEDURE "{{DATACLOUD_DB_SCHEMA}}"."trg_fn_by_project_sync_term"();

-- ----------------------------
-- Primary Key structure for table by_project
-- ----------------------------
ALTER TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_project" ADD CONSTRAINT "by_project_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table by_project_task
-- ----------------------------
CREATE INDEX "idx_customer_code2" ON "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" USING btree (
  "customer_code" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "idx_handler_user_id2" ON "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" USING btree (
  "handler_user_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "idx_initiator_user_id2" ON "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" USING btree (
  "initiator_user_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "idx_opp_code2" ON "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" USING btree (
  "opp_code" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "idx_project_code2" ON "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" USING btree (
  "project_code" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key structure for table by_project_task
-- ----------------------------
ALTER TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" ADD CONSTRAINT "by_project_task_pkey" PRIMARY KEY ("id");

-- ----------------------------
-- Indexes structure for table by_rd_task
-- ----------------------------
CREATE INDEX "by_rd_task_idx_customer_code" ON "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" USING btree (
  "customer_code" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "by_rd_task_idx_handler_user_id" ON "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" USING btree (
  "handler_user_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "by_rd_task_idx_initiator_user_id" ON "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" USING btree (
  "initiator_user_id" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "by_rd_task_idx_opp_code" ON "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" USING btree (
  "opp_code" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);
CREATE INDEX "by_rd_task_idx_project_code" ON "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" USING btree (
  "project_code" COLLATE "pg_catalog"."default" "pg_catalog"."text_ops" ASC NULLS LAST
);

-- ----------------------------
-- Primary Key structure for table by_rd_task
-- ----------------------------
ALTER TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" ADD CONSTRAINT "by_rd_task_pkey" PRIMARY KEY ("id");
