/*
 demo 鏁版嵁搴?
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
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (202, '202', '椴告櫤绉戞妧', '0', -1, 1, 0, '2026-04-28 07:46:39.645', NULL, '-1.202', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (242, '242', '鍗庝腑-鍖荤枟缁?, '0', 215, 4, 3, '2026-04-28 07:46:39.912', NULL, '-1.202.210.215.242', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (241, '241', '鍗庝腑-鏀垮簻缁?, '0', 215, 4, 2, '2026-04-28 07:46:39.912', NULL, '-1.202.210.215.241', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (240, '240', '鍗庝腑-閲戣瀺缁?, '0', 215, 4, 1, '2026-04-28 07:46:39.912', NULL, '-1.202.210.215.240', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (239, '239', '鍗庤タ-鍒堕€犵粍', '0', 214, 4, 2, '2026-04-28 07:46:39.912', NULL, '-1.202.210.214.239', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (238, '238', '鍗庤タ-鏀垮簻缁?, '0', 214, 4, 1, '2026-04-28 07:46:39.912', NULL, '-1.202.210.214.238', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (237, '237', '鍗庡崡-鏀垮簻缁?, '0', 213, 4, 2, '2026-04-28 07:46:39.912', NULL, '-1.202.210.213.237', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (236, '236', '鍗庡崡-閲戣瀺缁?, '0', 213, 4, 1, '2026-04-28 07:46:39.912', NULL, '-1.202.210.213.236', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (235, '235', '鍗庝笢-鍒堕€犵粍', '0', 212, 4, 3, '2026-04-28 07:46:39.912', NULL, '-1.202.210.212.235', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (234, '234', '鍗庝笢-鏀垮簻缁?, '0', 212, 4, 2, '2026-04-28 07:46:39.912', NULL, '-1.202.210.212.234', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (233, '233', '鍗庝笢-閲戣瀺缁?, '0', 212, 4, 1, '2026-04-28 07:46:39.912', NULL, '-1.202.210.212.233', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (232, '232', '鍗庡寳-鏀垮簻缁?, '0', 211, 4, 2, '2026-04-28 07:46:39.912', NULL, '-1.202.210.211.232', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (231, '231', '鍗庡寳-閲戣瀺缁?, '0', 211, 4, 1, '2026-04-28 07:46:39.912', NULL, '-1.202.210.211.231', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (224, '224', '浜や粯閮?, '0', 220, 3, 4, '2026-04-28 07:46:39.848', NULL, '-1.202.220.224', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (223, '223', 'CRM浜у搧閮?, '0', 220, 3, 3, '2026-04-28 07:46:39.848', NULL, '-1.202.220.223', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (222, '222', 'BI浜у搧閮?, '0', 220, 3, 2, '2026-04-28 07:46:39.848', NULL, '-1.202.220.222', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (221, '221', '鏁版嵁浜у搧閮?, '0', 220, 3, 1, '2026-04-28 07:46:39.848', NULL, '-1.202.220.221', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (220, '220', '鐮斿彂涓庝氦浠樹腑蹇?, '0', 202, 2, 2, '2026-04-28 07:46:39.717', NULL, '-1.202.220', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (215, '215', '鍗庝腑澶у尯', '0', 210, 3, 5, '2026-04-28 07:46:39.783', NULL, '-1.202.210.215', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (214, '214', '鍗庤タ澶у尯', '0', 210, 3, 4, '2026-04-28 07:46:39.783', NULL, '-1.202.210.214', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (213, '213', '鍗庡崡澶у尯', '0', 210, 3, 3, '2026-04-28 07:46:39.783', NULL, '-1.202.210.213', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (212, '212', '鍗庝笢澶у尯', '0', 210, 3, 2, '2026-04-28 07:46:39.783', NULL, '-1.202.210.212', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (211, '211', '鍗庡寳澶у尯', '0', 210, 3, 1, '2026-04-28 07:46:39.783', NULL, '-1.202.210.211', NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_organization" VALUES (210, '210', '閿€鍞腑蹇?, '0', 202, 2, 1, '2026-04-28 07:46:39.717', NULL, '-1.202.210', NULL);

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
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."user_id" IS '鐢ㄦ埛鍞竴鏍囪瘑';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."user_name" IS '鐢ㄦ埛鍚嶇О';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."email" IS '鐢ㄦ埛閭';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."phone" IS '鐢ㄦ埛鐢佃瘽';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."user_code" IS '鐢ㄦ埛鐧诲綍鏍囪瘑';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."pwd" IS '鐢ㄦ埛瀵嗙爜(md5鍔犲瘑)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."address" IS '鐢ㄦ埛鍦板潃';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."remark" IS '鐢ㄦ埛澶囨敞';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."user_eff_date" IS '棰勭暀';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."user_exp_date" IS '鐢ㄦ埛杩囨湡鏃ユ湡';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."create_date" IS '璁板綍鍒涘缓鏃ユ湡';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."update_date" IS '璁板綍鏇存柊鏃ユ湡';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."state" IS '鐢ㄦ埛鐘舵€侊細A-姝ｅ父;X-绂佺敤';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."is_locked" IS '鏄惁閿佸畾锛?'Y''-閿佸畾锛?'N''-娌℃湁閿佸畾锛宯ull琛ㄧず''N''';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."last_login_date" IS '鐢ㄦ埛鏈€鍚庝竴娆＄櫥褰曟椂闂?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."security_question_id" IS '鐢ㄦ埛蹇樿瀵嗙爜鎵惧洖瀵嗙爜闂';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."security_answer" IS '鐢ㄦ埛蹇樿瀵嗙爜瀹夊叏鎻愮ず闂';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."thumbnail_uri" IS '鐢ㄦ埛澶村儚URL鍦板潃';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."ext_attr" IS '鐢ㄦ埛鎵╁睍淇℃伅';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."assistant_id" IS '涓€涓憳宸ュ搴斾竴涓秴绾у姪鎵?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."user_number" IS '宸ュ彿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."station_id" IS '鎵€灞為┗鍦?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."register_type" IS '娉ㄥ唽绫诲瀷 1-鎵嬫満鍙锋敞鍐?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."po_users"."apple_user_id" IS '鑻规灉鐢ㄦ埛ID锛岀敤浜庤嫻鏋滅櫥褰曞叧鑱?;
COMMENT ON TABLE "{{DATACLOUD_DB_SCHEMA}}"."po_users" IS '鐢ㄦ埛琛?;

-- ----------------------------
-- Records of po_users
-- ----------------------------
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (101, '钀у嘲', NULL, NULL, 'xiaofeng', '11f3e866026b21d3cc6bf419083ae7fd', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (102, '閮潠', NULL, NULL, 'guojing', 'abe81f55c23f66d509d6ff911b54a716', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (103, '浠ょ嫄鍐?, NULL, NULL, 'linghuchong', '94e6e036752607a1d9c32ea1d473069c', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (104, '闊﹀皬瀹?, NULL, NULL, 'weixiaobao', '5b8cd4e991d3f75fd4c0fca3cbc9479e', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (105, '鑳℃枑', NULL, NULL, 'hufei', '6f65618d791121fc462a9bdb15ed1d64', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (106, '闄堝娲?, NULL, NULL, 'chenjialuo', 'cca58b33a6656fb57b2175f933360a26', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (107, '鐙勪簯', NULL, NULL, 'diyun', 'de0f42cf627be6707d0e1229ae399340', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (108, '鏉ㄨ繃', NULL, NULL, 'yangguo', '914bd8bbb758aa4c1fae2c4b1123daee', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (109, '寮犳棤蹇?, NULL, NULL, 'zhangwuji', '9b5524374d801b1eeb0fa30aa07f3d99', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (110, '榛勮搲', NULL, NULL, 'huangrong', 'e72be06c7a4003a523e45ddc4154f9e1', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (111, '璧垫晱', NULL, NULL, 'zhaomin', '165dfbd637f2d12bb5fff64fa34263d9', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (100, '寮犱笁涓?, NULL, NULL, 'zhangsanfeng', '9be6b5fe662ec7eda75e388da9f1d0b3', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, '221312', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (112, '浠荤泩鐩?, NULL, NULL, 'renyingying', '3738a9006cea101dabe09efca74a71c8', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000077, '榛庢槑', NULL, NULL, '0027011322', 'baf140a7045f3981eed6047d9ec40a87', NULL, NULL, '2026-04-28 11:11:15.24', NULL, '2026-04-28 11:11:15.24', NULL, 'A', '2026-04-28 11:11:15.24', 'N', NULL, NULL, NULL, NULL, NULL, 10000077, '0027011322', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (113, '灏忛緳濂?, NULL, NULL, 'xiaolongnv', '95d79dc9e3dc06f1f27fe94d71f70f85', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (114, '鐜嬭瀚?, NULL, NULL, 'wangyuyan', '2efae2ad0680bffb50b933069bc6f5f9', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (115, '闇嶉潚妗?, NULL, NULL, 'huoqingtong', 'dfc82eb5717618adccd1627424f982bc', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (116, '鑻楄嫢鍏?, NULL, NULL, 'miaoruolan', '2853a36fa8c963127210dcb5cc5cff72', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (117, '娲竷鍏?, NULL, NULL, 'hongqigong', 'e02a7a3444ec27094808f82bec92eb0f', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (119, '娆ч槼閿?, NULL, NULL, 'ouyangfeng', '6ea7dfba7a5d9c6baa485d5313562494', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (120, '娈佃獕', NULL, NULL, 'duanyu', '7e7d5cb2b1078b72606b3aba5ccdef03', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (121, '铏氱', NULL, NULL, 'xuzhu', '9081fc184a922271b966101ff9bac603', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (122, '鍛ㄤ集閫?, NULL, NULL, 'zhoubotong', '84c4ac2d9e98f6cd07af8829a5d2cb87', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (123, '鎱曞澶?, NULL, NULL, 'murongfu', '3a6efa410db4417c4df7737bf3f77a6b', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (124, '娓稿潶涔?, NULL, NULL, 'youtanzhi', '46418332b0d8ee3495179f2a938385e6', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (125, '宀充笉缇?, NULL, NULL, 'yuebuqun', '7dfb391e13233965056f10eb445d58ec', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (126, '椋庢竻鎵?, NULL, NULL, 'fengqingyang', '25ac15b9af5430a4bfafd4e6794a78ff', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (127, '鎵湴鍍?, NULL, NULL, 'saodiseng', 'aeae1ff3f89fcdece56d9a92a1d43168', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (128, '瀹嬭繙妗?, NULL, NULL, 'songyuanqiao', 'bc9c9e741643555d04d064e25b14d686', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (129, '淇炶幉鑸?, NULL, NULL, 'yulianzhou', 'ea944ea1baf3cc97da92db60bbc90484', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (130, '寮犵繝灞?, NULL, NULL, 'zhangcuishan', 'f0566ffafa9fcdbff1ee8432c648df36', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (131, '娈风礌绱?, NULL, NULL, 'yinsusu', '16eff566bf11c02ccea671cc8cf88489', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (132, '淇炲脖宀?, NULL, NULL, 'yudaiyan', 'bcb2fb54b87928260736ee378fb4de4f', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (133, '璋㈤€?, NULL, NULL, 'xiexun', '417db0a0fb7a29da1821870ff7b73a2c', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (134, '闊︿竴绗?, NULL, NULL, 'weiyixiao', '7964102c17ac4bbc77ea9fa7b985ff9d', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (135, '鏉ㄩ€?, NULL, NULL, 'yangxiao', '552f65db63bcc31b1d4f321339a1e9ac', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (136, '鑼冮仴', NULL, NULL, 'fanyao', 'b03a74a2984fd3d2a3df23fd5358ab63', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (137, '鎴愭槅', NULL, NULL, 'chengkun', '068c04db899bda204ac6acd6301b7ea1', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (138, '娈峰ぉ姝?, NULL, NULL, 'yintianzheng', '77251c404d05198b95552928eecf64b1', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000084, '鍚村溅绁?, NULL, NULL, '0027021534', '63d5b7b2fd1ff1889b4293943442ccc3', NULL, NULL, '2026-04-28 11:12:01.794', NULL, '2026-04-28 11:12:01.794', '2026-04-28 11:17:54.221', 'A', '2026-04-28 11:12:01.794', 'N', NULL, NULL, NULL, NULL, NULL, 10000084, '0027021534', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (137, '鎴愭槅', NULL, NULL, 'chengkun', '068c04db899bda204ac6acd6301b7ea1', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10, '椴嶆€?, NULL, NULL, '101155', '967a7b1604f8962380f351f17dd9f96d', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, '101155', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (11, '鏉ㄦ€?, NULL, NULL, '0027010369', '73bd3298f80dfd1b6cd53914e5c599de', NULL, NULL, '2026-04-28 11:17:10.014', NULL, '2026-04-28 11:17:10.014', NULL, 'A', '2026-04-28 11:17:10.014', 'N', NULL, NULL, NULL, NULL, NULL, NULL, '0027010369', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (12, '缃楁€?, NULL, NULL, '0027000618', 'd5825494e02fc4ca8977dd8a29e2cc4a', NULL, NULL, '2026-04-28 11:12:01.794', NULL, '2026-04-28 11:12:01.794', '2026-04-28 11:17:54.221', 'A', '2026-04-28 11:12:01.794', 'N', NULL, NULL, NULL, NULL, NULL, NULL, '0027000618', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (13, '闄堟€?, NULL, NULL, '0027002811', '3ee833b26a505b0b026978a24a71be09', NULL, NULL, '2026-04-28 11:05:58.807', NULL, '2026-04-28 11:05:58.807', NULL, 'A', '2026-04-28 11:05:58.807', 'N', NULL, NULL, NULL, NULL, NULL, NULL, '0027002811', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000091, '鏉滅敨', NULL, NULL, '0027012991', 'b3d2a271f363068b7823e750131f3f59', NULL, NULL, '2026-04-28 11:13:06.771', NULL, '2026-04-28 11:13:06.771', '2026-05-14 20:33:31.674', 'A', '2026-04-28 11:13:06.771', 'N', '2026-05-14 20:33:31.627', NULL, NULL, NULL, NULL, 10000091, '0027012991', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000118, '鍒樼殗鍙?, NULL, NULL, '0027030770', '3afa6137a8e832c849eabc81d1354df1', NULL, NULL, '2026-04-28 11:17:10.014', NULL, '2026-04-28 11:17:10.014', '2026-05-14 16:56:54.653', 'A', '2026-04-28 11:17:10.014', 'N', '2026-05-14 16:56:54.606', NULL, NULL, NULL, NULL, 10000118, '0027030770', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000009, '瑕冨皬杩?, NULL, NULL, '0027002543', 'e7eed98dd3caf055555b5923904e1348', NULL, NULL, '2026-04-28 11:04:11.689', NULL, '2026-04-28 11:04:11.689', '2026-05-12 18:01:22.85', 'A', '2026-04-28 11:04:11.689', 'N', '2026-05-12 18:01:22.811', NULL, NULL, NULL, NULL, 10000009, '0027002543', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10001767, '澶у笀鏂扮敤鎴?, NULL, NULL, 'dashixinyonghu', '512be623019f71e5b8428b5d2a846554', NULL, NULL, '2026-05-08 19:55:54.629', NULL, '2026-05-08 19:55:54.629', NULL, 'A', '2026-05-08 19:55:54.629', 'N', NULL, NULL, NULL, NULL, NULL, 10001767, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000022, '榛勮嵂甯?, NULL, NULL, '0027024630', 'f26f6cc039b08e623fe2cf4d4788c41b', NULL, NULL, '2026-04-28 11:05:00.066', NULL, '2026-04-28 11:05:00.066', '2026-05-14 21:29:34.607', 'A', '2026-04-28 11:05:00.066', 'N', '2026-05-14 21:29:34.606', NULL, NULL, NULL, NULL, 10000022, '0027024630', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (118, '榛勮嵂甯?', NULL, NULL, 'huangyaoshi', '556e4f3fce8b6fe464bc2bcc4e1172b5', NULL, NULL, NULL, NULL, '2026-04-28 07:46:39.977', NULL, 'A', NULL, 'N', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000036, '鏃犲悕', NULL, NULL, '0027000620', 'c8c78e740d2775c2dc2c2e8076f48483', NULL, NULL, '2026-04-28 11:06:49.14', NULL, '2026-04-28 11:06:49.14', '2026-05-14 22:27:54.973', 'A', '2026-04-28 11:06:49.14', 'N', '2026-05-14 22:27:54.932', NULL, NULL, NULL, NULL, 10000036, '0027000620', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000098, '缃楄疮涓?, NULL, NULL, '0027028723', '1610fd1c28e4c25f195426942c615717', NULL, NULL, '2026-04-28 11:14:57.12', NULL, '2026-04-28 11:14:57.12', '2026-05-14 20:39:04.569', 'A', '2026-04-28 11:14:57.12', 'N', '2026-05-14 20:39:04.568', NULL, NULL, NULL, NULL, 10000098, '0027028723', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000050, '璋㈤€婇', NULL, NULL, '0027023754', 'a32c976423ef1308b81018c5f802679d', NULL, NULL, '2026-04-28 11:08:07.481', NULL, '2026-04-28 11:08:07.481', '2026-05-14 20:04:34.846', 'A', '2026-04-28 11:08:07.481', 'N', '2026-05-14 20:04:34.846', NULL, NULL, NULL, NULL, 10000050, '0027023754', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10003595, '涔愪匠', NULL, NULL, 'lejia', '6fb97f9b12ee7b87504280c3417cb692', NULL, NULL, '2026-05-09 17:20:11.881', NULL, '2026-05-09 17:20:11.881', '2026-05-09 18:20:26.814', 'A', '2026-05-09 17:20:11.881', 'N', '2026-05-09 18:20:26.765', NULL, NULL, NULL, NULL, 10003595, NULL, NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000105, '钀у嘲', NULL, NULL, '0027016840', '1f9523c4f00a172ebe7aa1925513c465', NULL, NULL, '2026-04-28 11:15:48.839', NULL, '2026-04-28 11:15:48.839', '2026-05-13 14:41:14.736', 'A', '2026-04-28 11:15:48.839', 'N', '2026-05-13 14:41:14.736', NULL, NULL, NULL, NULL, 10000105, '0027016840', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000029, '姊佸皬', NULL, NULL, '0027003719', 'b7441994d49c674e4840e1d3b0df64b4', NULL, NULL, '2026-04-28 11:05:58.807', NULL, '2026-04-28 11:05:58.807', '2026-05-12 16:29:06.894', 'A', '2026-04-28 11:05:58.807', 'N', '2026-05-12 16:29:06.893', NULL, NULL, NULL, NULL, 10000029, '0027003719', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000057, '闄堣埖涓?, NULL, NULL, '0027024710', 'de622ef8f9d7445122fee69a0e8d6508', NULL, NULL, '2026-04-28 11:08:49.096', NULL, '2026-04-28 11:08:49.096', '2026-05-13 21:29:45.596', 'A', '2026-04-28 11:08:49.096', 'N', '2026-05-13 21:29:45.596', NULL, NULL, NULL, NULL, 10000057, '0027024710', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000070, '鐜嬮噸闃?, NULL, NULL, '0027019281', '8aa92ea8a5a509804f74d3739de46e3a', NULL, NULL, '2026-04-28 11:10:05.087', NULL, '2026-04-28 11:10:05.087', '2026-05-14 09:33:57.391', 'A', '2026-04-28 11:10:05.087', 'N', '2026-05-14 09:33:57.391', NULL, NULL, NULL, NULL, 10000070, '0027019281', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10001, '骞冲彴绠＄悊鍛榓dminvip', 'adminvip@byai.com', 'TvvjzLzE6+JUsjGVhw7yXw==', 'adminvip', 'dfef67ebc70b6746ad6305a6da2518e8', NULL, NULL, '2025-06-03 07:04:21.908', NULL, '2025-06-03 07:04:21.908', '2026-05-14 21:48:26.551', 'A', NULL, 'N', '2026-05-14 21:48:26.487', NULL, NULL, NULL, NULL, 10000004, '0000000002', 576, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."po_users" VALUES (10000043, '鍛ㄤ集閫?, NULL, NULL, '0027011326', 'b0309abdbf4d258f631d44965acc34ce', NULL, NULL, '2026-04-28 11:07:23.106', NULL, '2026-04-28 11:07:23.106', '2026-05-14 21:01:01.461', 'A', '2026-04-28 11:07:23.106', 'N', '2026-05-14 21:01:01.461', NULL, NULL, NULL, NULL, 10000043, '0027011326', NULL, NULL, NULL);



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
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."id" IS '涓婚敭';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."customer_code" IS '瀹㈡埛缂栫爜';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."customer_name" IS '瀹㈡埛鍚嶇О';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."industry" IS '鎵€灞炶涓?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."province" IS '鎵€灞炵渷浠?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."city" IS '鎵€灞炲煄甯?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."domain" IS '鎵€灞為鍩?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."sales_user_id" IS '鎵€灞為攢鍞敤鎴风紪鐮?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."sales_person" IS '鎵€灞為攢鍞鍚?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."dept_id" IS '鎵€灞炵粍缁囩紪鐮?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."dept_name" IS '鎵€灞炵粍缁囧悕绉?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."create_by" IS '鍒涘缓鑰?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."create_time" IS '鍒涘缓鏃堕棿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."update_by" IS '鏇存柊鑰?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."update_time" IS '鏇存柊鏃堕棿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_customer"."remark" IS '澶囨敞';
COMMENT ON TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_customer" IS '瀹㈡埛淇℃伅琛?;

-- ----------------------------
-- Records of by_customer
-- ----------------------------
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (1, 'CUST000001', '鍖椾含鍥芥姇涓€鸿祫浜х鐞嗘湁闄愬叕鍙?, '閲戣瀺', '11', '鍖椾含', '1', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2025-11-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (2, 'CUST000002', '涓浗宸ュ晢閾惰鑲′唤鏈夐檺鍏徃鍖椾含鍒嗚', '閲戣瀺', '11', '鍖椾含', '1', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2025-11-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (3, 'CUST000003', '鍖椾含甯傛捣娣€鍖轰汉姘戞斂搴?, '鏀垮簻', '11', '鍖椾含', '2', 'diyun', '鐙勪簯', '234', '鍗庝笢-鏀垮簻缁?, 'admin', '2025-11-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (4, 'CUST000004', '鎷涘晢閾惰鑲′唤鏈夐檺鍏徃涓婃捣鍒嗚', '閲戣瀺', '31', '涓婃捣', '1', 'hufei', '鑳℃枑', '233', '鍗庝笢-閲戣瀺缁?, 'admin', '2025-11-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (5, 'CUST000005', '涓婃捣娴︿笢鍙戝睍閾惰鑲′唤鏈夐檺鍏徃', '閲戣瀺', '31', '涓婃捣', '1', 'hufei', '鑳℃枑', '233', '鍗庝笢-閲戣瀺缁?, 'admin', '2025-11-19 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (6, 'CUST000006', '骞垮窞甯傚ぉ娌冲尯鍗敓鍋ュ悍灞€', '鏀垮簻', '44', '骞垮窞', '2', 'chenjialuo', '闄堝娲?, '236', '鍗庡崡-閲戣瀺缁?, 'admin', '2025-11-21 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (7, 'CUST000007', '骞夸笢鐪佷汉姘戝尰闄?, '鍖荤枟鍋ュ悍', '44', '骞垮窞', '3', 'chenjialuo', '闄堝娲?, '236', '鍗庡崡-閲戣瀺缁?, 'admin', '2025-11-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (8, 'CUST000008', '娣卞湷甯傚钩瀹夐摱琛岃偂浠芥湁闄愬叕鍙?, '閲戣瀺', '44', '娣卞湷', '1', 'chenjialuo', '闄堝娲?, '236', '鍗庡崡-閲戣瀺缁?, 'admin', '2025-11-26 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (9, 'CUST000009', '鎴愰兘楂樻柊鎶€鏈骇涓氬紑鍙戝尯绠″浼?, '鏀垮簻', '51', '鎴愰兘', '2', 'yangguo', '鏉ㄨ繃', '238', '鍗庤タ-鏀垮簻缁?, 'admin', '2025-12-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (10, 'CUST000010', '鍥涘窛鐪佹暀鑲插巺', '鏀垮簻', '51', '鎴愰兘', '4', 'yangguo', '鏉ㄨ繃', '238', '鍗庤タ-鏀垮簻缁?, 'admin', '2025-12-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (11, 'CUST000011', '姝︽眽甯傚晢涓氶摱琛岃偂浠芥湁闄愬叕鍙?, '閲戣瀺', '42', '姝︽眽', '1', 'zhangwuji', '寮犳棤蹇?, '240', '鍗庝腑-閲戣瀺缁?, 'admin', '2025-12-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (12, 'CUST000012', '婀栧寳鐪佸崼鐢熷仴搴峰鍛樹細', '鏀垮簻', '42', '姝︽眽', '3', 'zhangwuji', '寮犳棤蹇?, '240', '鍗庝腑-閲戣瀺缁?, 'admin', '2025-12-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (13, 'CUST000013', '鍗椾含閾惰鑲′唤鏈夐檺鍏徃', '閲戣瀺', '32', '鍗椾含', '1', 'hufei', '鑳℃枑', '233', '鍗庝笢-閲戣瀺缁?, 'admin', '2025-12-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (14, 'CUST000014', '姹熻嫃鐪佸ぇ鏁版嵁绠＄悊涓績', '鏀垮簻', '32', '鍗椾含', '2', 'diyun', '鐙勪簯', '234', '鍗庝笢-鏀垮簻缁?, 'admin', '2025-12-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (15, 'CUST000015', '娴欐睙澶у', '鏁欒偛', '33', '鏉窞', '4', 'diyun', '鐙勪簯', '234', '鍗庝笢-鏀垮簻缁?, 'admin', '2025-12-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (16, 'CUST000016', '闃块噷宸村反锛堜腑鍥斤級鏈夐檺鍏徃', '鍒堕€?, '33', '鏉窞', '5', 'diyun', '鐙勪簯', '234', '鍗庝笢-鏀垮簻缁?, 'admin', '2025-12-19 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (17, 'CUST000017', '瀹佹尝閾惰鑲′唤鏈夐檺鍏徃', '閲戣瀺', '33', '瀹佹尝', '1', 'hufei', '鑳℃枑', '233', '鍗庝笢-閲戣瀺缁?, 'admin', '2025-12-21 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (18, 'CUST000018', '娣卞湷甯傝吘璁绠楁満绯荤粺鏈夐檺鍏徃', '鍒堕€?, '44', '娣卞湷', '5', 'chenjialuo', '闄堝娲?, '236', '鍗庡崡-閲戣瀺缁?, 'admin', '2025-12-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (19, 'CUST000019', '骞垮窞甯傝秺绉€鍖烘暀鑲插眬', '鏀垮簻', '44', '骞垮窞', '4', 'chenjialuo', '闄堝娲?, '236', '鍗庡崡-閲戣瀺缁?, 'admin', '2025-12-25 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (20, 'CUST000020', '鍗庝负鎶€鏈湁闄愬叕鍙?, '鍒堕€?, '44', '娣卞湷', '5', 'chenjialuo', '闄堝娲?, '236', '鍗庡崡-閲戣瀺缁?, 'admin', '2025-12-27 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (21, 'CUST000021', '涓浗寤鸿閾惰鑲′唤鏈夐檺鍏徃澶╂触鍒嗚', '閲戣瀺', '12', '澶╂触', '1', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2025-12-29 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (22, 'CUST000022', '澶╂触甯傛花娴锋柊鍖轰汉姘戞斂搴?, '鏀垮簻', '12', '澶╂触', '2', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2026-01-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (23, 'CUST000023', '娌冲寳鐪佹暟瀛楀姙', '鏀垮簻', '13', '鐭冲搴?, '2', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2026-01-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (24, 'CUST000024', '涓浗鍐滀笟閾惰灞变笢鐪佸垎琛?, '閲戣瀺', '37', '娴庡崡', '1', 'zhangwuji', '寮犳棤蹇?, '240', '鍗庝腑-閲戣瀺缁?, 'admin', '2026-01-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (25, 'CUST000025', '灞变笢鐪佷汉姘戝尰闄?, '鍖荤枟鍋ュ悍', '37', '娴庡崡', '3', 'zhangwuji', '寮犳棤蹇?, '240', '鍗庝腑-閲戣瀺缁?, 'admin', '2026-01-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (26, 'CUST000026', '閮戝窞閾惰鑲′唤鏈夐檺鍏徃', '閲戣瀺', '41', '閮戝窞', '1', 'zhangwuji', '寮犳棤蹇?, '240', '鍗庝腑-閲戣瀺缁?, 'admin', '2026-01-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (27, 'CUST000027', '娌冲崡鐪佸崼鐢熷仴搴峰鍛樹細', '鏀垮簻', '41', '閮戝窞', '3', 'zhangwuji', '寮犳棤蹇?, '240', '鍗庝腑-閲戣瀺缁?, 'admin', '2026-01-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (28, 'CUST000028', '閲嶅簡鍐滄潙鍟嗕笟閾惰鑲′唤鏈夐檺鍏徃', '閲戣瀺', '50', '閲嶅簡', '1', 'yangguo', '鏉ㄨ繃', '238', '鍗庤タ-鏀垮簻缁?, 'admin', '2026-01-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (29, 'CUST000029', '璐靛窞鐪佸ぇ鏁版嵁鍙戝睍绠＄悊灞€', '鏀垮簻', '52', '璐甸槼', '2', 'yangguo', '鏉ㄨ繃', '238', '鍗庤タ-鏀垮簻缁?, 'admin', '2026-01-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (30, 'CUST000030', '浜戝崡鐪佹暟瀛楃粡娴庡眬', '鏀垮簻', '53', '鏄嗘槑', '2', 'yangguo', '鏉ㄨ繃', '238', '鍗庤タ-鏀垮簻缁?, 'admin', '2026-01-19 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (31, 'CUST000031', '鍘﹂棬鍥介檯閾惰鑲′唤鏈夐檺鍏徃', '閲戣瀺', '35', '鍘﹂棬', '1', 'hufei', '鑳℃枑', '233', '鍗庝笢-閲戣瀺缁?, 'admin', '2026-01-21 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (32, 'CUST000032', '绂忓缓鐪佸尰绉戝ぇ瀛﹂檮灞炵涓€鍖婚櫌', '鍖荤枟鍋ュ悍', '35', '绂忓窞', '3', 'hufei', '鑳℃枑', '233', '鍗庝笢-閲戣瀺缁?, 'admin', '2026-01-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (33, 'CUST000033', '鑻忓窞宸ヤ笟鍥尯绠″浼?, '鏀垮簻', '32', '鑻忓窞', '2', 'diyun', '鐙勪簯', '234', '鍗庝笢-鏀垮簻缁?, 'admin', '2026-01-25 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (34, 'CUST000034', '鏃犻敗甯傚ぇ鏁版嵁绠＄悊灞€', '鏀垮簻', '32', '鏃犻敗', '2', 'diyun', '鐙勪簯', '234', '鍗庝笢-鏀垮簻缁?, 'admin', '2026-02-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (35, 'CUST000035', '姹熻嫃鐪佷汉姘戝尰闄?, '鍖荤枟鍋ュ悍', '32', '鍗椾含', '3', 'hufei', '鑳℃枑', '233', '鍗庝笢-閲戣瀺缁?, 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (36, 'CUST000036', '涓婃捣浜ら€氬ぇ瀛?, '鏁欒偛', '31', '涓婃捣', '4', 'hufei', '鑳℃枑', '233', '鍗庝笢-閲戣瀺缁?, 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (37, 'CUST000037', '涓婃捣甯傚ぇ鏁版嵁涓績', '鏀垮簻', '31', '涓婃捣', '2', 'diyun', '鐙勪簯', '234', '鍗庝笢-鏀垮簻缁?, 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (38, 'CUST000038', '涓浗鐢典俊鑲′唤鏈夐檺鍏徃涓婃捣鍒嗗叕鍙?, '鍒堕€?, '31', '涓婃捣', '9', 'diyun', '鐙勪簯', '234', '鍗庝笢-鏀垮簻缁?, 'admin', '2026-02-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (39, 'CUST000039', '鍖椾含閾惰鑲′唤鏈夐檺鍏徃', '閲戣瀺', '11', '鍖椾含', '1', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2026-02-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (40, 'CUST000040', '鍖椾含甯傚ぇ鏁版嵁涓績', '鏀垮簻', '11', '鍖椾含', '2', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2026-02-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (41, 'CUST000041', '棣栭兘鍖荤澶у闄勫睘鍖椾含鍗忓拰鍖婚櫌', '鍖荤枟鍋ュ悍', '11', '鍖椾含', '3', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2026-02-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (42, 'CUST000042', '涓浗鐢靛姏寤鸿鑲′唤鏈夐檺鍏徃', '鍒堕€?, '11', '鍖椾含', '7', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2026-02-19 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (43, 'CUST000043', '涓浗绉诲姩閫氫俊闆嗗洟骞夸笢鏈夐檺鍏徃', '鍒堕€?, '44', '骞垮窞', '9', 'chenjialuo', '闄堝娲?, '236', '鍗庡崡-閲戣瀺缁?, 'admin', '2026-02-21 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (44, 'CUST000044', '骞垮窞鍐滃晢閾惰鑲′唤鏈夐檺鍏徃', '閲戣瀺', '44', '骞垮窞', '1', 'chenjialuo', '闄堝娲?, '236', '鍗庡崡-閲戣瀺缁?, 'admin', '2026-02-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (45, 'CUST000045', '娴峰崡鐪佸ぇ鏁版嵁绠＄悊灞€', '鏀垮簻', '46', '娴峰彛', '2', 'chenjialuo', '闄堝娲?, '236', '鍗庡崡-閲戣瀺缁?, 'admin', '2026-03-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (46, 'CUST000046', '瑗垮畨閾惰鑲′唤鏈夐檺鍏徃', '閲戣瀺', '61', '瑗垮畨', '1', 'yangguo', '鏉ㄨ繃', '238', '鍗庤タ-鏀垮簻缁?, 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (47, 'CUST000047', '闄曡タ鐪佹暟瀛楁斂搴滅鐞嗗眬', '鏀垮簻', '61', '瑗垮畨', '2', 'yangguo', '鏉ㄨ繃', '238', '鍗庤タ-鏀垮簻缁?, 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (48, 'CUST000048', '鍥涘窛鐪佷汉姘戝尰闄?, '鍖荤枟鍋ュ悍', '51', '鎴愰兘', '3', 'yangguo', '鏉ㄨ繃', '238', '鍗庤タ-鏀垮簻缁?, 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (49, 'CUST000049', '婀栧崡鐪佸ぇ鏁版嵁灞€', '鏀垮簻', '43', '闀挎矙', '2', 'zhangwuji', '寮犳棤蹇?, '240', '鍗庝腑-閲戣瀺缁?, 'admin', '2026-03-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (50, 'CUST000050', '闀挎矙閾惰鑲′唤鏈夐檺鍏徃', '閲戣瀺', '43', '闀挎矙', '1', 'zhangwuji', '寮犳棤蹇?, '240', '鍗庝腑-閲戣瀺缁?, 'admin', '2026-03-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (51, 'CUST000051', '闈掑矝閾惰鑲′唤鏈夐檺鍏徃', '閲戣瀺', '37', '闈掑矝', '1', 'zhangwuji', '寮犳棤蹇?, '240', '鍗庝腑-閲戣瀺缁?, 'admin', '2026-03-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (52, 'CUST000052', '娴庡崡甯傚ぇ鏁版嵁灞€', '鏀垮簻', '37', '娴庡崡', '2', 'zhangwuji', '寮犳棤蹇?, '240', '鍗庝腑-閲戣瀺缁?, 'admin', '2026-03-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (53, 'CUST000053', '鍚堣偉甯傛暟鎹祫婧愬眬', '鏀垮簻', '34', '鍚堣偉', '2', 'hufei', '鑳℃枑', '233', '鍗庝笢-閲戣瀺缁?, 'admin', '2026-03-19 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (54, 'CUST000054', '瀹夊窘鐪佺珛鍖婚櫌', '鍖荤枟鍋ュ悍', '34', '鍚堣偉', '3', 'hufei', '鑳℃枑', '233', '鍗庝笢-閲戣瀺缁?, 'admin', '2026-03-21 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (55, 'CUST000055', '寰藉晢閾惰鑲′唤鏈夐檺鍏徃', '閲戣瀺', '34', '鍚堣偉', '1', 'hufei', '鑳℃枑', '233', '鍗庝笢-閲戣瀺缁?, 'admin', '2026-03-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (56, 'CUST000056', '鍗楁槍甯傛斂鍔℃暟鎹眬', '鏀垮簻', '36', '鍗楁槍', '2', 'hufei', '鑳℃枑', '233', '鍗庝笢-閲戣瀺缁?, 'admin', '2026-04-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (57, 'CUST000057', '姹熻タ閾惰鑲′唤鏈夐檺鍏徃', '閲戣瀺', '36', '鍗楁槍', '1', 'diyun', '鐙勪簯', '234', '鍗庝笢-鏀垮簻缁?, 'admin', '2026-04-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (58, 'CUST000058', '鍗楀畞甯傚ぇ鏁版嵁鍙戝睍灞€', '鏀垮簻', '45', '鍗楀畞', '2', 'chenjialuo', '闄堝娲?, '236', '鍗庡崡-閲戣瀺缁?, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (59, 'CUST000059', '骞胯タ澹棌鑷不鍖轰汉姘戝尰闄?, '鍖荤枟鍋ュ悍', '45', '鍗楀畞', '3', 'chenjialuo', '闄堝娲?, '236', '鍗庡崡-閲戣瀺缁?, 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (60, 'CUST000060', '妗傛灄閾惰鑲′唤鏈夐檺鍏徃', '閲戣瀺', '45', '妗傛灄', '1', 'chenjialuo', '闄堝娲?, '236', '鍗庡崡-閲戣瀺缁?, 'admin', '2026-04-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (61, 'CUST000061', '鍏板窞閾惰鑲′唤鏈夐檺鍏徃', '閲戣瀺', '62', '鍏板窞', '1', 'yangguo', '鏉ㄨ繃', '238', '鍗庤タ-鏀垮簻缁?, 'admin', '2026-04-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (62, 'CUST000062', '鐢樿們鐪佹暟鎹眬', '鏀垮簻', '62', '鍏板窞', '2', 'yangguo', '鏉ㄨ繃', '238', '鍗庤タ-鏀垮簻缁?, 'admin', '2026-04-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (63, 'CUST000063', '瀹佸閾惰鑲′唤鏈夐檺鍏徃', '閲戣瀺', '64', '閾跺窛', '1', 'yangguo', '鏉ㄨ繃', '238', '鍗庤タ-鏀垮簻缁?, 'admin', '2026-04-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (64, 'CUST000064', '鍐呰挋鍙よ嚜娌诲尯澶ф暟鎹腑蹇?, '鏀垮簻', '15', '鍛煎拰娴╃壒', '2', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2026-04-19 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (65, 'CUST000065', '鍐呰挋鍙ら摱琛岃偂浠芥湁闄愬叕鍙?, '閲戣瀺', '15', '鍛煎拰娴╃壒', '1', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2026-04-21 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (66, 'CUST000066', '鍝堝皵婊ㄩ摱琛岃偂浠芥湁闄愬叕鍙?, '閲戣瀺', '23', '鍝堝皵婊?, '1', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2026-04-17 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (67, 'CUST000067', '榛戦緳姹熺渷鏀垮姟鏈嶅姟鍜屽ぇ鏁版嵁灞€', '鏀垮簻', '23', '鍝堝皵婊?, '2', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2026-04-19 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (68, 'CUST000068', '鍚夋灄閾惰鑲′唤鏈夐檺鍏徃', '閲戣瀺', '22', '闀挎槬', '1', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2026-04-21 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (69, 'CUST000069', '闀挎槬甯傛暟鎹眬', '鏀垮簻', '22', '闀挎槬', '2', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2026-04-23 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (70, 'CUST000070', '杈藉畞鐪佷汉姘戝尰闄?, '鍖荤枟鍋ュ悍', '21', '娌堥槼', '3', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2026-04-25 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (71, 'CUST000071', '鐩涗含閾惰鑲′唤鏈夐檺鍏徃', '閲戣瀺', '21', '娌堥槼', '1', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2026-04-26 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (72, 'CUST000072', '涓滃寳澶у', '鏁欒偛', '21', '娌堥槼', '4', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2026-04-27 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (73, 'CUST000073', '娴欐睙鐪佷汉姘戝尰闄?, '鍖荤枟鍋ュ悍', '33', '鏉窞', '3', 'diyun', '鐙勪簯', '235', '鍗庝笢-鍒堕€犵粍', 'admin', '2026-04-28 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (74, 'CUST000074', '缃戞槗锛堟澀宸烇級缃戠粶鏈夐檺鍏徃', '鍒堕€?, '33', '鏉窞', '5', 'diyun', '鐙勪簯', '235', '鍗庝笢-鍒堕€犵粍', 'admin', '2026-04-29 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (75, 'CUST000075', '灞辫タ鐪佸ぇ鏁版嵁搴旂敤灞€', '鏀垮簻', '14', '澶師', '2', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2026-04-30 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (76, 'CUST000076', '灞辫タ閾惰鑲′唤鏈夐檺鍏徃', '閲戣瀺', '14', '澶師', '1', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2026-05-01 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (77, 'CUST000077', '涓浗閾惰鑲′唤鏈夐檺鍏徃骞夸笢鐪佸垎琛?, '閲戣瀺', '44', '骞垮窞', '1', 'chenjialuo', '闄堝娲?, '236', '鍗庡崡-閲戣瀺缁?, 'admin', '2026-05-02 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (78, 'CUST000078', '骞垮窞甯傛暟鎹眬', '鏀垮簻', '44', '骞垮窞', '2', 'chenjialuo', '闄堝娲?, '237', '鍗庡崡-鏀垮簻缁?, 'admin', '2026-05-02 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (79, 'CUST000079', '娣卞湷甯傛暟瀛楁斂搴滅爺绌堕櫌', '鏀垮簻', '44', '娣卞湷', '2', 'chenjialuo', '闄堝娲?, '237', '鍗庡崡-鏀垮簻缁?, 'admin', '2026-05-03 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (80, 'CUST000080', '涓北澶у', '鏁欒偛', '44', '骞垮窞', '4', 'chenjialuo', '闄堝娲?, '236', '鍗庡崡-閲戣瀺缁?, 'admin', '2026-05-03 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (81, 'CUST000081', '绂忓窞閾惰鑲′唤鏈夐檺鍏徃', '閲戣瀺', '35', '绂忓窞', '1', 'hufei', '鑳℃枑', '233', '鍗庝笢-閲戣瀺缁?, 'admin', '2026-05-04 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (82, 'CUST000082', '绂忓缓鐪佹暟瀛楃寤哄缓璁剧鐞嗗姙鍏', '鏀垮簻', '35', '绂忓窞', '2', 'hufei', '鑳℃枑', '233', '鍗庝笢-閲戣瀺缁?, 'admin', '2026-05-04 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (83, 'CUST000083', '鍘﹂棬澶у', '鏁欒偛', '35', '鍘﹂棬', '4', 'hufei', '鑳℃枑', '233', '鍗庝笢-閲戣瀺缁?, 'admin', '2026-05-05 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (84, 'CUST000084', '璐甸槼閾惰鑲′唤鏈夐檺鍏徃', '閲戣瀺', '52', '璐甸槼', '1', 'yangguo', '鏉ㄨ繃', '238', '鍗庤タ-鏀垮簻缁?, 'admin', '2026-05-05 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (85, 'CUST000085', '浜戝崡鐪佷汉姘戝尰闄?, '鍖荤枟鍋ュ悍', '53', '鏄嗘槑', '3', 'yangguo', '鏉ㄨ繃', '238', '鍗庤タ-鏀垮簻缁?, 'admin', '2026-05-06 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (86, 'CUST000086', '鏄嗘槑甯傚ぇ鏁版嵁灞€', '鏀垮簻', '53', '鏄嗘槑', '2', 'yangguo', '鏉ㄨ繃', '238', '鍗庤タ-鏀垮簻缁?, 'admin', '2026-05-06 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (87, 'CUST000087', '涓浗澶钩娲嬩繚闄╋紙闆嗗洟锛夎偂浠芥湁闄愬叕鍙?, '閲戣瀺', '31', '涓婃捣', '1', 'hufei', '鑳℃枑', '233', '鍗庝笢-閲戣瀺缁?, 'admin', '2026-05-07 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (88, 'CUST000088', '鍥芥嘲鍚涘畨璇佸埜鑲′唤鏈夐檺鍏徃', '閲戣瀺', '31', '涓婃捣', '1', 'hufei', '鑳℃枑', '233', '鍗庝笢-閲戣瀺缁?, 'admin', '2026-05-07 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (89, 'CUST000089', '涓浗鍗庤兘闆嗗洟鏈夐檺鍏徃', '鍒堕€?, '11', '鍖椾含', '7', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2026-05-08 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (90, 'CUST000090', '鍥藉鐢电綉鏈夐檺鍏徃', '鍒堕€?, '11', '鍖椾含', '7', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2026-05-08 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (91, 'CUST000091', '娣卞湷璇佸埜浜ゆ槗鎵€', '閲戣瀺', '44', '娣卞湷', '1', 'chenjialuo', '闄堝娲?, '236', '鍗庡崡-閲戣瀺缁?, 'admin', '2026-05-09 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (92, 'CUST000092', '涓婃捣璇佸埜浜ゆ槗鎵€', '閲戣瀺', '31', '涓婃捣', '1', 'hufei', '鑳℃枑', '233', '鍗庝笢-閲戣瀺缁?, 'admin', '2026-05-09 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (93, 'CUST000093', '鍖椾含璇佸埜浜ゆ槗鎵€', '閲戣瀺', '11', '鍖椾含', '1', 'weixiaobao', '闊﹀皬瀹?, '231', '鍗庡寳-閲戣瀺缁?, 'admin', '2026-05-10 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (94, 'CUST000094', '姝︽眽澶у', '鏁欒偛', '42', '姝︽眽', '4', 'zhangwuji', '寮犳棤蹇?, '240', '鍗庝腑-閲戣瀺缁?, 'admin', '2026-05-10 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (95, 'CUST000095', '鍗庝腑绉戞妧澶у', '鏁欒偛', '42', '姝︽眽', '4', 'zhangwuji', '寮犳棤蹇?, '240', '鍗庝腑-閲戣瀺缁?, 'admin', '2026-05-10 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (96, 'CUST000096', '婀栧寳鐪佷汉姘戝尰闄?, '鍖荤枟鍋ュ悍', '42', '姝︽眽', '3', 'zhangwuji', '寮犳棤蹇?, '241', '鍗庝腑-鏀垮簻缁?, 'admin', '2026-05-11 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (97, 'CUST000097', '闀挎矙甯傚崼鐢熷仴搴峰鍛樹細', '鏀垮簻', '43', '闀挎矙', '3', 'zhangwuji', '寮犳棤蹇?, '241', '鍗庝腑-鏀垮簻缁?, 'admin', '2026-05-11 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (98, 'CUST000098', '涓崡澶у婀橀泤鍖婚櫌', '鍖荤枟鍋ュ悍', '43', '闀挎矙', '3', 'zhangwuji', '寮犳棤蹇?, '242', '鍗庝腑-鍖荤枟缁?, 'admin', '2026-05-12 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (99, 'CUST000099', '鎴愰兘甯傚ぇ鏁版嵁鍜岀數瀛愭斂鍔″眬', '鏀垮簻', '51', '鎴愰兘', '2', 'yangguo', '鏉ㄨ繃', '239', '鍗庤タ-鍒堕€犵粍', 'admin', '2026-05-12 07:20:07.970549', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_customer" VALUES (100, 'CUST000100', '閲嶅簡甯傚ぇ鏁版嵁鍙戝睍灞€', '鏀垮簻', '50', '閲嶅簡', '2', 'yangguo', '鏉ㄨ繃', '239', '鍗庤タ-鍒堕€犵粍', 'admin', '2026-05-12 07:20:07.970549', NULL, NULL, NULL);

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
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."id" IS '涓婚敭';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."customer_code" IS '瀹㈡埛缂栫爜';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."opp_code" IS '鍟嗘満缂栫爜';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."product_code" IS '浜у搧缂栫爜';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."task_type" IS '浠诲姟绫诲瀷(1绾跨储鑾峰彇 2鏂规浜ゆ祦 3鍟嗗姟鎶ヤ环 4鍟嗗姟搴旀爣 5鍟嗘満绛剧害 6搴旀爣澶嶇洏)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."initiator_user_id" IS '鍙戣捣浜虹敤鎴风紪鐮?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."handler_user_id" IS '澶勭悊浜虹敤鎴风紪鐮?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."task_status" IS '浠诲姟鐘舵€?1澶勭悊涓?2姝ｅ父缁撴潫 3寮傚父缁撴潫)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."task_name" IS '浠诲姟鍚嶇О';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."task_desc" IS '浠诲姟鎻忚堪';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."handle_desc" IS '澶勭悊鎻忚堪';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."initiate_time" IS '鍙戣捣鏃堕棿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."plan_finish_time" IS '璁″垝瀹屾垚鏃堕棿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."actual_finish_time" IS '瀹為檯瀹屾垚鏃堕棿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."create_by" IS '鍒涘缓鑰?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."create_time" IS '鍒涘缓鏃堕棿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."update_by" IS '鏇存柊鑰?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."update_time" IS '鏇存柊鏃堕棿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task"."remark" IS '澶囨敞';
COMMENT ON TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" IS '鍟嗘満浠诲姟琛?;

-- ----------------------------
-- Records of by_opp_task
-- ----------------------------
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (1, 'CUST000001', 'OPP00000001', 'WHALE_BI', '1', 'huangrong', 'weixiaobao', '2', '宸ヨ鍖椾含BI绾跨储鑾峰彇', NULL, NULL, '2025-11-06 00:00:00', '2025-11-21 00:00:00', '2025-11-21 00:00:00', 'admin', '2025-11-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (2, 'CUST000001', 'OPP00000001', 'WHALE_BI', '2', 'huangrong', 'weixiaobao', '2', '宸ヨ鍖椾含BI鏂规浜ゆ祦', NULL, NULL, '2025-11-23 00:00:00', '2025-12-16 00:00:00', '2025-12-16 00:00:00', 'admin', '2025-11-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (3, 'CUST000001', 'OPP00000001', 'WHALE_BI', '3', 'huangrong', 'weixiaobao', '2', '宸ヨ鍖椾含BI鍟嗗姟鎶ヤ环', NULL, NULL, '2025-12-17 00:00:00', '2025-12-26 00:00:00', '2025-12-25 00:00:00', 'admin', '2025-12-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (4, 'CUST000001', 'OPP00000001', 'WHALE_BI', '5', 'huangrong', 'weixiaobao', '2', '宸ヨ鍖椾含BI鍟嗘満绛剧害', NULL, NULL, '2025-12-26 00:00:00', '2026-01-06 00:00:00', '2026-01-06 00:00:00', 'admin', '2025-12-26 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (5, 'CUST000001', 'OPP00000002', 'WHALE_CRM', '1', 'zhaomin', 'weixiaobao', '2', '宸ヨ鍖椾含CRM绾跨储鑾峰彇', NULL, NULL, '2025-12-09 00:00:00', '2025-12-21 00:00:00', '2025-12-21 00:00:00', 'admin', '2025-12-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (6, 'CUST000001', 'OPP00000002', 'WHALE_CRM', '2', 'zhaomin', 'weixiaobao', '2', '宸ヨ鍖椾含CRM鏂规浜ゆ祦', NULL, NULL, '2025-12-22 00:00:00', '2026-01-16 00:00:00', '2026-01-16 00:00:00', 'admin', '2025-12-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (7, 'CUST000002', 'OPP00000003', 'WHALE_BI', '1', 'huangrong', 'weixiaobao', '2', '宸ヨ鍖椾含2-BI绾跨储鑾峰彇', NULL, NULL, '2025-11-04 00:00:00', '2025-11-19 00:00:00', '2025-11-19 00:00:00', 'admin', '2025-11-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (8, 'CUST000002', 'OPP00000003', 'WHALE_BI', '2', 'huangrong', 'weixiaobao', '2', '宸ヨ鍖椾含2-BI鏂规浜ゆ祦', NULL, NULL, '2025-11-20 00:00:00', '2025-12-11 00:00:00', '2025-12-11 00:00:00', 'admin', '2025-11-20 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (9, 'CUST000002', 'OPP00000003', 'WHALE_BI', '3', 'huangrong', 'weixiaobao', '2', '宸ヨ鍖椾含2-BI鍟嗗姟鎶ヤ环', NULL, NULL, '2025-12-12 00:00:00', '2026-01-21 00:00:00', '2026-01-21 00:00:00', 'admin', '2025-12-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (10, 'CUST000002', 'OPP00000003', 'WHALE_BI', '5', 'huangrong', 'weixiaobao', '2', '宸ヨ鍖椾含2-BI鍟嗘満绛剧害', NULL, NULL, '2026-01-22 00:00:00', '2026-01-29 00:00:00', '2026-01-29 00:00:00', 'admin', '2026-01-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (11, 'CUST000004', 'OPP00000004', 'WHALE_BI', '1', 'renyingying', 'hufei', '2', '鎷涘晢閾惰BI绾跨储', NULL, NULL, '2025-11-07 00:00:00', '2025-11-23 00:00:00', '2025-11-23 00:00:00', 'admin', '2025-11-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (12, 'CUST000004', 'OPP00000004', 'WHALE_BI', '2', 'renyingying', 'hufei', '2', '鎷涘晢閾惰BI鏂规浜ゆ祦', NULL, NULL, '2025-11-24 00:00:00', '2025-12-13 00:00:00', '2025-12-13 00:00:00', 'admin', '2025-11-24 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (13, 'CUST000004', 'OPP00000004', 'WHALE_BI', '5', 'renyingying', 'hufei', '2', '鎷涘晢閾惰BI绛剧害', NULL, NULL, '2025-12-14 00:00:00', '2025-12-21 00:00:00', '2025-12-21 00:00:00', 'admin', '2025-12-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (14, 'CUST000005', 'OPP00000005', 'WHALE_CRM', '1', 'xiaolongnv', 'diyun', '2', '娴﹀彂閾惰CRM绾跨储', NULL, NULL, '2025-12-05 00:00:00', '2025-12-21 00:00:00', '2025-12-21 00:00:00', 'admin', '2025-12-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (15, 'CUST000005', 'OPP00000005', 'WHALE_CRM', '3', 'xiaolongnv', 'diyun', '2', '娴﹀彂閾惰CRM鎶ヤ环', NULL, NULL, '2025-12-22 00:00:00', '2026-01-16 00:00:00', '2026-01-16 00:00:00', 'admin', '2025-12-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (16, 'CUST000006', 'OPP00000006', 'WHALE_CRM', '1', 'huangrong', 'chenjialuo', '2', '骞垮窞鍗仴CRM绾跨储', NULL, NULL, '2025-11-09 00:00:00', '2025-11-26 00:00:00', '2025-11-26 00:00:00', 'admin', '2025-11-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (17, 'CUST000007', 'OPP00000007', 'WHALE_BI', '1', 'zhaomin', 'chenjialuo', '2', '骞夸笢浜烘皯鍖婚櫌BI绾跨储', NULL, NULL, '2025-12-06 00:00:00', '2025-12-21 00:00:00', '2025-12-21 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (18, 'CUST000007', 'OPP00000007', 'WHALE_BI', '2', 'zhaomin', 'chenjialuo', '2', '骞夸笢浜烘皯鍖婚櫌BI鏂规', NULL, NULL, '2025-12-23 00:00:00', '2026-01-13 00:00:00', '2026-01-13 00:00:00', 'admin', '2025-12-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (19, 'CUST000008', 'OPP00000008', 'WHALE_BI', '1', 'wangyuyan', 'chenjialuo', '2', '骞冲畨閾惰BI绾跨储', NULL, NULL, '2025-11-13 00:00:00', '2025-11-29 00:00:00', '2025-11-29 00:00:00', 'admin', '2025-11-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (20, 'CUST000008', 'OPP00000008', 'WHALE_BI', '2', 'wangyuyan', 'chenjialuo', '2', '骞冲畨閾惰BI鏂规浜ゆ祦', NULL, NULL, '2025-12-02 00:00:00', '2026-01-11 00:00:00', '2026-01-11 00:00:00', 'admin', '2025-12-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (21, 'CUST000009', 'OPP00000011', 'WHALE_CRM', '1', 'huoqingtong', 'yangguo', '2', '鎴愰兘楂樻柊CRM绾跨储', NULL, NULL, '2025-12-04 00:00:00', '2025-12-19 00:00:00', '2025-12-19 00:00:00', 'admin', '2025-12-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (22, 'CUST000009', 'OPP00000011', 'WHALE_CRM', '2', 'huoqingtong', 'yangguo', '2', '鎴愰兘楂樻柊CRM鏂规', NULL, NULL, '2025-12-20 00:00:00', '2026-01-09 00:00:00', '2026-01-09 00:00:00', 'admin', '2025-12-20 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (23, 'CUST000010', 'OPP00000012', 'WHALE_BI', '1', 'miaoruolan', 'yangguo', '2', '宸濈渷鏁欒偛BI绾跨储', NULL, NULL, '2025-12-07 00:00:00', '2025-12-23 00:00:00', '2025-12-23 00:00:00', 'admin', '2025-12-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (24, 'CUST000011', 'OPP00000013', 'WHALE_BI', '1', 'huangrong', 'zhangwuji', '2', '姝︽眽鍟嗚BI绾跨储', NULL, NULL, '2025-12-10 00:00:00', '2025-12-26 00:00:00', '2025-12-26 00:00:00', 'admin', '2025-12-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (25, 'CUST000011', 'OPP00000013', 'WHALE_BI', '2', 'huangrong', 'zhangwuji', '2', '姝︽眽鍟嗚BI鏂规', NULL, NULL, '2025-12-27 00:00:00', '2026-01-15 00:00:00', '2026-01-15 00:00:00', 'admin', '2025-12-27 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (26, 'CUST000011', 'OPP00000013', 'WHALE_BI', '5', 'huangrong', 'zhangwuji', '2', '姝︽眽鍟嗚BI绛剧害', NULL, NULL, '2026-01-16 00:00:00', '2026-01-23 00:00:00', '2026-01-23 00:00:00', 'admin', '2026-01-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (27, 'CUST000012', 'OPP00000014', 'WHALE_CRM', '1', 'zhaomin', 'zhangwuji', '2', '閯傜渷鍗仴CRM绾跨储', NULL, NULL, '2025-12-05 00:00:00', '2025-12-21 00:00:00', '2025-12-21 00:00:00', 'admin', '2025-12-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (28, 'CUST000013', 'OPP00000015', 'WHALE_BI', '1', 'renyingying', 'hufei', '2', '鍗椾含閾惰BI绾跨储', NULL, NULL, '2025-11-02 00:00:00', '2025-11-16 00:00:00', '2025-11-16 00:00:00', 'admin', '2025-11-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (29, 'CUST000013', 'OPP00000015', 'WHALE_BI', '2', 'renyingying', 'hufei', '2', '鍗椾含閾惰BI鏂规', NULL, NULL, '2025-11-17 00:00:00', '2025-12-06 00:00:00', '2025-12-06 00:00:00', 'admin', '2025-11-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (30, 'CUST000014', 'OPP00000017', 'WHALE_CRM', '1', 'xiaolongnv', 'diyun', '2', '鑻忕渷鏁版嵁CRM绾跨储', NULL, NULL, '2025-12-08 00:00:00', '2025-12-23 00:00:00', '2025-12-23 00:00:00', 'admin', '2025-12-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (31, 'CUST000016', 'OPP00000021', 'WHALE_DF', '1', 'wangyuyan', 'diyun', '2', '闃块噷宸村反DF绾跨储', NULL, NULL, '2025-11-11 00:00:00', '2025-11-26 00:00:00', '2025-11-26 00:00:00', 'admin', '2025-11-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (32, 'CUST000016', 'OPP00000021', 'WHALE_DF', '2', 'wangyuyan', 'diyun', '2', '闃块噷宸村反DF鏂规', NULL, NULL, '2025-11-27 00:00:00', '2025-12-16 00:00:00', '2025-12-16 00:00:00', 'admin', '2025-11-27 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (33, 'CUST000016', 'OPP00000021', 'WHALE_DF', '3', 'wangyuyan', 'diyun', '2', '闃块噷宸村反DF鎶ヤ环', NULL, NULL, '2025-12-17 00:00:00', '2025-12-26 00:00:00', '2025-12-26 00:00:00', 'admin', '2025-12-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (34, 'CUST000016', 'OPP00000021', 'WHALE_DF', '5', 'wangyuyan', 'diyun', '2', '闃块噷宸村反DF绛剧害', NULL, NULL, '2025-12-27 00:00:00', '2026-01-09 00:00:00', '2026-01-09 00:00:00', 'admin', '2025-12-27 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (35, 'CUST000018', 'OPP00000023', 'WHALE_DF', '1', 'huoqingtong', 'chenjialuo', '2', '鑵捐DF绾跨储', NULL, NULL, '2025-11-06 00:00:00', '2025-11-21 00:00:00', '2025-11-21 00:00:00', 'admin', '2025-11-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (36, 'CUST000018', 'OPP00000023', 'WHALE_DF', '2', 'huoqingtong', 'chenjialuo', '2', '鑵捐DF鏂规', NULL, NULL, '2025-11-23 00:00:00', '2025-12-11 00:00:00', '2025-12-11 00:00:00', 'admin', '2025-11-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (37, 'CUST000020', 'OPP00000025', 'WHALE_DF', '1', 'miaoruolan', 'chenjialuo', '2', '鍗庝负DF绾跨储', NULL, NULL, '2025-11-09 00:00:00', '2025-11-23 00:00:00', '2025-11-23 00:00:00', 'admin', '2025-11-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (38, 'CUST000020', 'OPP00000025', 'WHALE_DF', '2', 'miaoruolan', 'chenjialuo', '2', '鍗庝负DF鏂规', NULL, NULL, '2025-11-24 00:00:00', '2025-12-13 00:00:00', '2025-12-13 00:00:00', 'admin', '2025-11-24 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (39, 'CUST000020', 'OPP00000025', 'WHALE_DF', '3', 'miaoruolan', 'chenjialuo', '2', '鍗庝负DF鎶ヤ环', NULL, NULL, '2025-12-14 00:00:00', '2026-01-21 00:00:00', '2026-01-21 00:00:00', 'admin', '2025-12-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (40, 'CUST000020', 'OPP00000025', 'WHALE_DF', '5', 'miaoruolan', 'chenjialuo', '2', '鍗庝负DF绛剧害', NULL, NULL, '2026-01-22 00:00:00', '2026-01-29 00:00:00', '2026-01-29 00:00:00', 'admin', '2026-01-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (41, 'CUST000021', 'OPP00000031', 'WHALE_BI', '1', 'huangrong', 'weixiaobao', '2', '寤鸿澶╂触BI绾跨储', NULL, NULL, '2025-12-11 00:00:00', '2025-12-26 00:00:00', '2025-12-26 00:00:00', 'admin', '2025-12-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (42, 'CUST000021', 'OPP00000031', 'WHALE_BI', '2', 'huangrong', 'weixiaobao', '2', '寤鸿澶╂触BI鏂规', NULL, NULL, '2025-12-27 00:00:00', '2026-01-16 00:00:00', '2026-01-16 00:00:00', 'admin', '2025-12-27 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (43, 'CUST000022', 'OPP00000032', 'WHALE_BI', '1', 'zhaomin', 'weixiaobao', '2', '澶╂触婊ㄦ捣BI绾跨储', NULL, NULL, '2026-01-06 00:00:00', '2026-01-21 00:00:00', '2026-01-21 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (44, 'CUST000024', 'OPP00000035', 'WHALE_BI', '1', 'renyingying', 'zhangwuji', '2', '鍐滆灞变笢BI绾跨储', NULL, NULL, '2025-12-04 00:00:00', '2025-12-19 00:00:00', '2025-12-19 00:00:00', 'admin', '2025-12-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (45, 'CUST000024', 'OPP00000035', 'WHALE_BI', '2', 'renyingying', 'zhangwuji', '2', '鍐滆灞变笢BI鏂规', NULL, NULL, '2025-12-20 00:00:00', '2026-01-09 00:00:00', '2026-01-09 00:00:00', 'admin', '2025-12-20 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (46, 'CUST000028', 'OPP00000041', 'WHALE_BI', '1', 'xiaolongnv', 'yangguo', '2', '閲嶅簡鍐滃晢BI绾跨储', NULL, NULL, '2026-01-09 00:00:00', '2026-01-23 00:00:00', '2026-01-23 00:00:00', 'admin', '2026-01-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (47, 'CUST000031', 'OPP00000046', 'WHALE_BI', '1', 'wangyuyan', 'hufei', '2', '鍘﹂棬鍥介檯BI绾跨储', NULL, NULL, '2026-01-03 00:00:00', '2026-01-16 00:00:00', '2026-01-16 00:00:00', 'admin', '2026-01-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (48, 'CUST000033', 'OPP00000049', 'WHALE_BI', '1', 'huoqingtong', 'diyun', '2', '鑻忓窞宸ヤ笟鍥瑽I绾跨储', NULL, NULL, '2026-01-06 00:00:00', '2026-01-21 00:00:00', '2026-01-21 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (49, 'CUST000033', 'OPP00000049', 'WHALE_BI', '2', 'huoqingtong', 'diyun', '2', '鑻忓窞宸ヤ笟鍥瑽I鏂规', NULL, NULL, '2026-01-22 00:00:00', '2026-02-11 00:00:00', '2026-02-11 00:00:00', 'admin', '2026-01-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (50, 'CUST000035', 'OPP00000052', 'WHALE_BI', '1', 'miaoruolan', 'hufei', '2', '鑻忕渷浜烘皯鍖婚櫌BI绾跨储', NULL, NULL, '2026-01-07 00:00:00', '2026-01-23 00:00:00', '2026-01-23 00:00:00', 'admin', '2026-01-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (51, 'CUST000039', 'OPP00000061', 'WHALE_BI', '1', 'huangrong', 'weixiaobao', '1', '鍖椾含閾惰BI绾跨储', NULL, NULL, '2026-02-06 00:00:00', '2026-02-21 00:00:00', NULL, 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (52, 'CUST000039', 'OPP00000061', 'WHALE_BI', '2', 'huangrong', 'weixiaobao', '1', '鍖椾含閾惰BI鏂规浜ゆ祦', NULL, NULL, '2026-02-23 00:00:00', '2026-03-11 00:00:00', NULL, 'admin', '2026-02-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (53, 'CUST000040', 'OPP00000063', 'WHALE_BI', '1', 'zhaomin', 'weixiaobao', '1', '鍖椾含澶ф暟鎹瓸I绾跨储', NULL, NULL, '2026-02-04 00:00:00', '2026-02-19 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (54, 'CUST000044', 'OPP00000067', 'WHALE_BI', '1', 'renyingying', 'chenjialuo', '2', '骞垮窞鍐滃晢BI绾跨储', NULL, NULL, '2025-12-07 00:00:00', '2025-12-21 00:00:00', '2025-12-21 00:00:00', 'admin', '2025-12-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (55, 'CUST000044', 'OPP00000067', 'WHALE_BI', '2', 'renyingying', 'chenjialuo', '2', '骞垮窞鍐滃晢BI鏂规', NULL, NULL, '2025-12-23 00:00:00', '2026-01-13 00:00:00', '2026-01-13 00:00:00', 'admin', '2025-12-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (56, 'CUST000044', 'OPP00000067', 'WHALE_BI', '5', 'renyingying', 'chenjialuo', '2', '骞垮窞鍐滃晢BI绛剧害', NULL, NULL, '2026-01-14 00:00:00', '2026-01-21 00:00:00', '2026-01-21 00:00:00', 'admin', '2026-01-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (57, 'CUST000050', 'OPP00000073', 'WHALE_BI', '1', 'xiaolongnv', 'zhangwuji', '1', '闀挎矙閾惰BI绾跨储', NULL, NULL, '2026-03-09 00:00:00', '2026-03-23 00:00:00', NULL, 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (58, 'CUST000051', 'OPP00000075', 'WHALE_BI', '1', 'wangyuyan', 'zhangwuji', '1', '闈掑矝閾惰BI绾跨储', NULL, NULL, '2026-03-06 00:00:00', '2026-03-21 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (59, 'CUST000051', 'OPP00000075', 'WHALE_BI', '2', 'wangyuyan', 'zhangwuji', '1', '闈掑矝閾惰BI鏂规', NULL, NULL, '2026-03-22 00:00:00', '2026-04-11 00:00:00', NULL, 'admin', '2026-03-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (60, 'CUST000055', 'OPP00000079', 'WHALE_BI', '1', 'huoqingtong', 'hufei', '1', '寰藉晢閾惰BI绾跨储', NULL, NULL, '2026-03-04 00:00:00', '2026-03-19 00:00:00', NULL, 'admin', '2026-03-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (61, 'CUST000057', 'OPP00000083', 'WHALE_CRM', '1', 'miaoruolan', 'diyun', '1', '姹熻タ閾惰CRM绾跨储', NULL, NULL, '2026-03-11 00:00:00', '2026-03-26 00:00:00', NULL, 'admin', '2026-03-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (62, 'CUST000060', 'OPP00000086', 'WHALE_BI', '1', 'huangrong', 'chenjialuo', '1', '妗傛灄閾惰BI绾跨储', NULL, NULL, '2026-03-08 00:00:00', '2026-03-23 00:00:00', NULL, 'admin', '2026-03-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (63, 'CUST000063', 'OPP00000089', 'WHALE_CRM', '1', 'zhaomin', 'yangguo', '1', '瀹佸閾惰CRM绾跨储', NULL, NULL, '2026-04-06 00:00:00', '2026-04-21 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (64, 'CUST000065', 'OPP00000092', 'WHALE_BI', '1', 'renyingying', 'weixiaobao', '1', '鍐呰挋鍙ら摱琛孊I绾跨储', NULL, NULL, '2026-04-09 00:00:00', '2026-04-23 00:00:00', NULL, 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (65, 'CUST000066', 'OPP00000094', 'WHALE_BI', '1', 'xiaolongnv', 'weixiaobao', '1', '鍝堝皵婊ㄩ摱琛孊I绾跨储', NULL, NULL, '2026-04-07 00:00:00', '2026-04-21 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (66, 'CUST000068', 'OPP00000096', 'WHALE_CRM', '1', 'wangyuyan', 'weixiaobao', '1', '鍚夋灄閾惰CRM绾跨储', NULL, NULL, '2026-04-05 00:00:00', '2026-04-19 00:00:00', NULL, 'admin', '2026-04-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (67, 'CUST000071', 'OPP00000099', 'WHALE_BI', '1', 'huoqingtong', 'weixiaobao', '1', '鐩涗含閾惰BI绾跨储', NULL, NULL, '2026-04-10 00:00:00', '2026-04-25 00:00:00', NULL, 'admin', '2026-04-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (68, 'CUST000071', 'OPP00000099', 'WHALE_BI', '2', 'huoqingtong', 'weixiaobao', '1', '鐩涗含閾惰BI鏂规', NULL, NULL, '2026-04-26 00:00:00', '2026-05-24 07:20:08.980334', NULL, 'admin', '2026-04-26 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (69, 'CUST000073', 'OPP00000101', 'WHALE_BI', '1', 'miaoruolan', 'diyun', '1', '娴欑渷浜烘皯鍖婚櫌BI绾跨储', NULL, NULL, '2026-04-04 00:00:00', '2026-04-19 00:00:00', NULL, 'admin', '2026-04-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (70, 'CUST000076', 'OPP00000104', 'WHALE_BI', '1', 'huangrong', 'weixiaobao', '1', '灞辫タ閾惰BI绾跨储', NULL, NULL, '2026-04-22 07:20:08.980334', '2026-05-22 07:20:08.980334', NULL, 'admin', '2026-04-22 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (71, 'CUST000081', 'OPP00000107', 'WHALE_BI', '1', 'zhaomin', 'hufei', '2', '绂忓窞閾惰BI绾跨储', NULL, NULL, '2025-12-03 00:00:00', '2025-12-16 00:00:00', '2025-12-16 00:00:00', 'admin', '2025-12-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (72, 'CUST000081', 'OPP00000107', 'WHALE_BI', '2', 'zhaomin', 'hufei', '2', '绂忓窞閾惰BI鏂规', NULL, NULL, '2025-12-17 00:00:00', '2026-01-06 00:00:00', '2026-01-06 00:00:00', 'admin', '2025-12-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (73, 'CUST000081', 'OPP00000107', 'WHALE_BI', '5', 'zhaomin', 'hufei', '2', '绂忓窞閾惰BI绛剧害', NULL, NULL, '2026-01-07 00:00:00', '2026-01-13 00:00:00', '2026-01-13 00:00:00', 'admin', '2026-01-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (74, 'CUST000084', 'OPP00000110', 'WHALE_BI', '1', 'renyingying', 'yangguo', '1', '璐甸槼閾惰BI绾跨储', NULL, NULL, '2026-04-17 07:20:08.980334', '2026-05-27 07:20:08.980334', NULL, 'admin', '2026-04-17 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (75, 'CUST000087', 'OPP00000113', 'WHALE_DF', '1', 'xiaolongnv', 'hufei', '1', '澶钩娲嬩繚闄〥F绾跨储', NULL, NULL, '2026-04-06 00:00:00', '2026-04-21 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (76, 'CUST000087', 'OPP00000113', 'WHALE_DF', '2', 'xiaolongnv', 'hufei', '1', '澶钩娲嬩繚闄〥F鏂规', NULL, NULL, '2026-04-22 00:00:00', '2026-05-22 07:20:08.980334', NULL, 'admin', '2026-04-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (77, 'CUST000088', 'OPP00000116', 'WHALE_BI', '1', 'wangyuyan', 'hufei', '1', '鍥芥嘲鍚涘畨BI绾跨储', NULL, NULL, '2026-04-04 00:00:00', '2026-04-19 00:00:00', NULL, 'admin', '2026-04-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (78, 'CUST000091', 'OPP00000119', 'WHALE_BI', '1', 'huoqingtong', 'chenjialuo', '1', '娣变氦鎵€BI绾跨储', NULL, NULL, '2026-04-20 07:20:08.980334', '2026-05-24 07:20:08.980334', NULL, 'admin', '2026-04-20 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (79, 'CUST000092', 'OPP00000122', 'WHALE_DF', '1', 'miaoruolan', 'hufei', '1', '涓婁氦鎵€DF绾跨储', NULL, NULL, '2026-04-24 07:20:08.980334', '2026-05-20 07:20:08.980334', NULL, 'admin', '2026-04-24 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (80, 'CUST000093', 'OPP00000125', 'WHALE_BI', '1', 'huangrong', 'weixiaobao', '1', '鍖椾氦鎵€BI缁绾跨储', NULL, NULL, '2026-04-27 07:20:08.980334', '2026-05-17 07:20:08.980334', NULL, 'admin', '2026-04-27 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (81, 'CUST000036', 'OPP00000128', 'WHALE_CRM', '1', 'zhaomin', 'hufei', '2', '涓婁氦澶RM绾跨储', NULL, NULL, '2025-12-05 00:00:00', '2025-12-19 00:00:00', '2025-12-19 00:00:00', 'admin', '2025-12-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (82, 'CUST000036', 'OPP00000128', 'WHALE_CRM', '2', 'zhaomin', 'hufei', '2', '涓婁氦澶RM鏂规', NULL, NULL, '2025-12-20 00:00:00', '2026-01-09 00:00:00', '2026-01-09 00:00:00', 'admin', '2025-12-20 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (83, 'CUST000036', 'OPP00000128', 'WHALE_CRM', '5', 'zhaomin', 'hufei', '2', '涓婁氦澶RM绛剧害', NULL, NULL, '2026-01-10 00:00:00', '2026-01-16 00:00:00', '2026-01-16 00:00:00', 'admin', '2026-01-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (84, 'CUST000043', 'OPP00000131', 'WHALE_MASS', '1', 'renyingying', 'chenjialuo', '2', '绉诲姩骞夸笢MASS绾跨储', NULL, NULL, '2025-11-04 00:00:00', '2025-11-19 00:00:00', '2025-11-19 00:00:00', 'admin', '2025-11-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (85, 'CUST000043', 'OPP00000131', 'WHALE_MASS', '2', 'renyingying', 'chenjialuo', '2', '绉诲姩骞夸笢MASS鏂规', NULL, NULL, '2025-11-21 00:00:00', '2025-12-09 00:00:00', '2025-12-09 00:00:00', 'admin', '2025-11-21 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (86, 'CUST000043', 'OPP00000131', 'WHALE_MASS', '5', 'renyingying', 'chenjialuo', '2', '绉诲姩骞夸笢MASS绛剧害', NULL, NULL, '2025-12-10 00:00:00', '2025-12-16 00:00:00', '2025-12-16 00:00:00', 'admin', '2025-12-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (87, 'CUST000072', 'OPP00000140', 'WHALE_BI', '1', 'xiaolongnv', 'weixiaobao', '2', '涓滃寳澶уBI绾跨储', NULL, NULL, '2026-01-07 00:00:00', '2026-01-21 00:00:00', '2026-01-21 00:00:00', 'admin', '2026-01-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (88, 'CUST000072', 'OPP00000140', 'WHALE_BI', '2', 'xiaolongnv', 'weixiaobao', '2', '涓滃寳澶уBI鏂规', NULL, NULL, '2026-01-22 00:00:00', '2026-02-11 00:00:00', '2026-02-11 00:00:00', 'admin', '2026-01-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (89, 'CUST000074', 'OPP00000143', 'WHALE_DF', '1', 'wangyuyan', 'diyun', '1', '缃戞槗DF绾跨储', NULL, NULL, '2026-03-06 00:00:00', '2026-03-21 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (90, 'CUST000074', 'OPP00000143', 'WHALE_DF', '2', 'wangyuyan', 'diyun', '1', '缃戞槗DF鏂规', NULL, NULL, '2026-03-22 00:00:00', '2026-04-11 00:00:00', NULL, 'admin', '2026-03-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (91, 'CUST000077', 'OPP00000147', 'WHALE_BI', '1', 'huoqingtong', 'chenjialuo', '1', '涓骞夸笢BI绾跨储', NULL, NULL, '2026-04-09 00:00:00', '2026-04-23 00:00:00', NULL, 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (92, 'CUST000078', 'OPP00000149', 'WHALE_DF', '1', 'miaoruolan', 'chenjialuo', '1', '骞垮窞鏁版嵁DF绾跨储', NULL, NULL, '2026-04-05 00:00:00', '2026-04-19 00:00:00', NULL, 'admin', '2026-04-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (93, 'CUST000079', 'OPP00000151', 'WHALE_BI', '1', 'huangrong', 'chenjialuo', '1', '娣卞湷鏁板瓧鏀垮簻BI绾跨储', NULL, NULL, '2026-04-14 07:20:08.980334', '2026-05-30 07:20:08.980334', NULL, 'admin', '2026-04-14 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (94, 'CUST000080', 'OPP00000153', 'WHALE_CRM', '1', 'zhaomin', 'chenjialuo', '1', '涓北澶уCRM绾跨储', NULL, NULL, '2026-04-18 07:20:08.980334', '2026-05-26 07:20:08.980334', NULL, 'admin', '2026-04-18 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (95, 'CUST000082', 'OPP00000155', 'WHALE_CRM', '1', 'renyingying', 'hufei', '1', '绂忓缓鏁板瓧鍔濩RM绾跨储', NULL, NULL, '2026-04-22 07:20:08.980334', '2026-05-22 07:20:08.980334', NULL, 'admin', '2026-04-22 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (96, 'CUST000083', 'OPP00000157', 'WHALE_BI', '1', 'xiaolongnv', 'hufei', '1', '鍘﹂棬澶уBI绾跨储', NULL, NULL, '2026-04-26 07:20:08.980334', '2026-05-18 07:20:08.980334', NULL, 'admin', '2026-04-26 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (97, 'CUST000086', 'OPP00000160', 'WHALE_BI', '1', 'wangyuyan', 'yangguo', '1', '鏄嗘槑澶ф暟鎹瓸I绾跨储', NULL, NULL, '2026-04-28 07:20:08.980334', '2026-05-16 07:20:08.980334', NULL, 'admin', '2026-04-28 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (98, 'CUST000089', 'OPP00000163', 'WHALE_DF', '1', 'huoqingtong', 'weixiaobao', '1', '鍗庤兘闆嗗洟DF绾跨储', NULL, NULL, '2026-04-07 00:00:00', '2026-04-21 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (99, 'CUST000090', 'OPP00000166', 'WHALE_DF', '1', 'miaoruolan', 'weixiaobao', '1', '鍥藉鐢电綉DF绾跨储', NULL, NULL, '2026-04-14 07:20:08.980334', '2026-05-30 07:20:08.980334', NULL, 'admin', '2026-04-14 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (100, 'CUST000094', 'OPP00000169', 'WHALE_CRM', '1', 'huangrong', 'zhangwuji', '1', '姝︽眽澶уCRM绾跨储', NULL, NULL, '2026-04-20 07:20:08.980334', '2026-05-24 07:20:08.980334', NULL, 'admin', '2026-04-20 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (101, 'CUST000095', 'OPP00000171', 'WHALE_BI', '1', 'zhaomin', 'zhangwuji', '1', '鍗庝腑绉戝ぇBI绾跨储', NULL, NULL, '2026-04-24 07:20:08.980334', '2026-05-20 07:20:08.980334', NULL, 'admin', '2026-04-24 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (102, 'CUST000096', 'OPP00000173', 'WHALE_BI', '1', 'renyingying', 'zhangwuji', '1', '閯傜渷浜烘皯鍖婚櫌BI绾跨储', NULL, NULL, '2026-04-28 07:20:08.980334', '2026-05-16 07:20:08.980334', NULL, 'admin', '2026-04-28 07:20:08.980334', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opp_task" VALUES (103, 'CUST000099', 'OPP00000175', 'WHALE_CRM', '1', 'xiaolongnv', 'yangguo', '1', '鎴愰兘澶ф暟鎹瓹RM绾跨储', NULL, NULL, '2026-05-02 07:20:08.980334', '2026-05-14 07:20:08.980334', NULL, 'admin', '2026-05-02 07:20:08.980334', NULL, NULL, NULL);

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
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."id" IS '涓婚敭';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."opp_code" IS '鍟嗘満缂栫爜';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."opp_name" IS '鍟嗘満鍚嶇О';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."industry" IS '鎵€灞炶涓?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."domain" IS '鎵€灞為鍩?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."customer_code" IS '鎵€灞炲鎴风紪鐮?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."sales_user_id" IS '鎵€灞為攢鍞敤鎴风紪鐮?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."dept_id" IS '鎵€灞炵粍缁囩紪鐮?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."product_code" IS '鎵€灞炰骇鍝佺紪鐮?dict_type: product)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."opp_status" IS '鍟嗘満鐘舵€?1绾跨储鑾峰彇 2鏂规浜ゆ祦 3鍟嗗姟鎶ヤ环 4绛剧害鎴愬姛 5绛剧害澶辫触)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."forecast_amount" IS '棰勬祴閲戦';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."contract_amount" IS '绛剧害閲戦';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."forecast_rate" IS '棰勬祴鎴愬姛鐜?%)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."fail_reason" IS '绛剧害澶辫触鍘熷洜鎻忚堪';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."success_summary" IS '绛剧害鎴愬姛鎬荤粨';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."plan_sign_date" IS '璁″垝绛剧害鏃ユ湡(YYYY-MM-DD)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."actual_sign_date" IS '瀹為檯绛剧害鏃ユ湡(YYYY-MM-DD)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."create_by" IS '鍒涘缓鑰?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."create_time" IS '鍒涘缓鏃堕棿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."update_by" IS '鏇存柊鑰?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."update_time" IS '鏇存柊鏃堕棿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity"."remark" IS '澶囨敞';
COMMENT ON TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" IS '鍟嗘満淇℃伅琛?;

-- ----------------------------
-- Records of by_opportunity
-- ----------------------------
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (1, 'OPP00000001', '鍥芥姇涓€?BI-椤圭洰', '閲戣瀺', '1', 'CUST000001', 'weixiaobao', '231', 'WHALE_BI', '4', 1200000.00, 1100000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2025-12-01 00:00:00', '2025-12-01 00:00:00', 'admin', '2025-11-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (2, 'OPP00000002', '鍥芥姇涓€?CRM-椤圭洰', '閲戣瀺', '1', 'CUST000001', 'weixiaobao', '231', 'WHALE_CRM', '2', 800000.00, NULL, 35.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-01-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (3, 'OPP00000003', '鍥芥姇涓€?鏁版嵁宸ュ巶-椤圭洰', '閲戣瀺', '1', 'CUST000001', 'weixiaobao', '231', 'WHALE_DF', '1', 500000.00, NULL, 15.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-03-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (4, 'OPP00000004', '宸ヨ鍖椾含-BI-椤圭洰', '閲戣瀺', '1', 'CUST000002', 'weixiaobao', '231', 'WHALE_BI', '4', 2500000.00, 2300000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-11-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (5, 'OPP00000005', '宸ヨ鍖椾含-鏁版嵁宸ュ巶-椤圭洰', '閲戣瀺', '1', 'CUST000002', 'weixiaobao', '231', 'WHALE_DF', '3', 1800000.00, NULL, 60.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (6, 'OPP00000006', '宸ヨ鍖椾含-MASS-椤圭洰', '閲戣瀺', '1', 'CUST000002', 'weixiaobao', '231', 'WHALE_MASS', '5', 600000.00, NULL, 0.00, '绔炲搧浠锋牸鏇翠綆', NULL, '2026-02-01 00:00:00', NULL, 'admin', '2025-12-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (7, 'OPP00000007', '娴锋穩鏀垮簻-CRM-椤圭洰', '鏀垮簻', '2', 'CUST000003', 'diyun', '234', 'WHALE_CRM', '4', 900000.00, 850000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-11-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (8, 'OPP00000008', '娴锋穩鏀垮簻-BI-椤圭洰', '鏀垮簻', '2', 'CUST000003', 'diyun', '234', 'WHALE_BI', '2', 1200000.00, NULL, 40.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (9, 'OPP00000009', '娴锋穩鏀垮簻-鏅鸿兘浣?椤圭洰', '鏀垮簻', '2', 'CUST000003', 'diyun', '234', 'WHALE_AGENT', '1', 300000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (10, 'OPP00000010', '鎷涜涓婃捣-BI-椤圭洰', '閲戣瀺', '1', 'CUST000004', 'hufei', '233', 'WHALE_BI', '4', 3000000.00, 2800000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2025-12-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-11-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (11, 'OPP00000011', '鎷涜涓婃捣-鏁版嵁宸ュ巶-椤圭洰', '閲戣瀺', '1', 'CUST000004', 'hufei', '233', 'WHALE_DF', '3', 2000000.00, NULL, 55.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-01-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (12, 'OPP00000012', '鎷涜涓婃捣-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000004', 'hufei', '233', 'WHALE_CRM', '5', 800000.00, NULL, 0.00, '瀹㈡埛棰勭畻缂╁噺', NULL, '2026-03-01 00:00:00', NULL, 'admin', '2026-01-19 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (13, 'OPP00000013', '娴﹀彂閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000005', 'hufei', '233', 'WHALE_BI', '4', 1500000.00, 1400000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-11-20 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (14, 'OPP00000014', '娴﹀彂閾惰-MASS-椤圭洰', '閲戣瀺', '1', 'CUST000005', 'hufei', '233', 'WHALE_MASS', '2', 700000.00, NULL, 30.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (15, 'OPP00000015', '娴﹀彂閾惰-鏅鸿兘浣?椤圭洰', '閲戣瀺', '1', 'CUST000005', 'hufei', '233', 'WHALE_AGENT', '1', 400000.00, NULL, 15.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (16, 'OPP00000016', '澶╂渤鍗仴-CRM-椤圭洰', '鏀垮簻', '3', 'CUST000006', 'chenjialuo', '236', 'WHALE_CRM', '4', 600000.00, 580000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2025-12-01 00:00:00', '2025-12-01 00:00:00', 'admin', '2025-11-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (17, 'OPP00000017', '澶╂渤鍗仴-BI-椤圭洰', '鏀垮簻', '3', 'CUST000006', 'chenjialuo', '236', 'WHALE_BI', '3', 900000.00, NULL, 65.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (18, 'OPP00000018', '澶╂渤鍗仴-鏁版嵁宸ュ巶-椤圭洰', '鏀垮簻', '3', 'CUST000006', 'chenjialuo', '236', 'WHALE_DF', '1', 500000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (19, 'OPP00000019', '绮ょ渷浜烘皯鍖婚櫌-BI-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000007', 'chenjialuo', '236', 'WHALE_BI', '4', 1100000.00, 1050000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-11-24 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (20, 'OPP00000020', '绮ょ渷浜烘皯鍖婚櫌-CRM-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000007', 'chenjialuo', '236', 'WHALE_CRM', '2', 700000.00, NULL, 35.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (21, 'OPP00000021', '绮ょ渷浜烘皯鍖婚櫌-鏅鸿兘浣?椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000007', 'chenjialuo', '236', 'WHALE_AGENT', '5', 300000.00, NULL, 0.00, '浜у搧鍔熻兘涓嶆弧瓒?, NULL, '2026-03-01 00:00:00', NULL, 'admin', '2026-02-21 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (22, 'OPP00000022', '骞冲畨閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000008', 'chenjialuo', '236', 'WHALE_BI', '4', 2000000.00, 1900000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (23, 'OPP00000023', '骞冲畨閾惰-鏁版嵁宸ュ巶-椤圭洰', '閲戣瀺', '1', 'CUST000008', 'chenjialuo', '236', 'WHALE_DF', '3', 1200000.00, NULL, 50.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (24, 'OPP00000024', '骞冲畨閾惰-MASS-椤圭洰', '閲戣瀺', '1', 'CUST000008', 'chenjialuo', '236', 'WHALE_MASS', '1', 600000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (25, 'OPP00000025', '鎴愰兘楂樻柊-CRM-椤圭洰', '鏀垮簻', '2', 'CUST000009', 'yangguo', '238', 'WHALE_CRM', '4', 750000.00, 720000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (26, 'OPP00000026', '鎴愰兘楂樻柊-BI-椤圭洰', '鏀垮簻', '2', 'CUST000009', 'yangguo', '238', 'WHALE_BI', '2', 900000.00, NULL, 30.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (27, 'OPP00000027', '鎴愰兘楂樻柊-鏁版嵁宸ュ巶-椤圭洰', '鏀垮簻', '2', 'CUST000009', 'yangguo', '238', 'WHALE_DF', '1', 400000.00, NULL, 15.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (28, 'OPP00000028', '宸濈渷鏁欒偛鍘?BI-椤圭洰', '鏀垮簻', '4', 'CUST000010', 'yangguo', '238', 'WHALE_BI', '4', 800000.00, 780000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2025-12-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (29, 'OPP00000029', '宸濈渷鏁欒偛鍘?鏅鸿兘浣?椤圭洰', '鏀垮簻', '4', 'CUST000010', 'yangguo', '238', 'WHALE_AGENT', '3', 350000.00, NULL, 55.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (30, 'OPP00000030', '宸濈渷鏁欒偛鍘?CRM-椤圭洰', '鏀垮簻', '4', 'CUST000010', 'yangguo', '238', 'WHALE_CRM', '5', 500000.00, NULL, 0.00, '瀹㈡埛鍐呴儴鍐崇瓥鏈€氳繃', NULL, '2026-03-01 00:00:00', NULL, 'admin', '2026-01-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (31, 'OPP00000031', '姝︽眽鍟嗚-BI-椤圭洰', '閲戣瀺', '1', 'CUST000011', 'zhangwuji', '240', 'WHALE_BI', '4', 1300000.00, 1250000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (32, 'OPP00000032', '姝︽眽鍟嗚-鏁版嵁宸ュ巶-椤圭洰', '閲戣瀺', '1', 'CUST000011', 'zhangwuji', '240', 'WHALE_DF', '2', 900000.00, NULL, 40.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (33, 'OPP00000033', '姝︽眽鍟嗚-MASS-椤圭洰', '閲戣瀺', '1', 'CUST000011', 'zhangwuji', '240', 'WHALE_MASS', '1', 400000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (34, 'OPP00000034', '閯傜渷鍗仴-CRM-椤圭洰', '鏀垮簻', '3', 'CUST000012', 'zhangwuji', '240', 'WHALE_CRM', '4', 700000.00, 680000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (35, 'OPP00000035', '閯傜渷鍗仴-BI-椤圭洰', '鏀垮簻', '3', 'CUST000012', 'zhangwuji', '240', 'WHALE_BI', '3', 1000000.00, NULL, 60.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (36, 'OPP00000036', '閯傜渷鍗仴-鏅鸿兘浣?椤圭洰', '鏀垮簻', '3', 'CUST000012', 'zhangwuji', '240', 'WHALE_AGENT', '5', 300000.00, NULL, 0.00, '闇€姹傚彉鏇存悂缃?, NULL, '2026-03-01 00:00:00', NULL, 'admin', '2026-01-21 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (37, 'OPP00000037', '鍗椾含閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000013', 'hufei', '233', 'WHALE_BI', '4', 1600000.00, 1520000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (38, 'OPP00000038', '鍗椾含閾惰-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000013', 'hufei', '233', 'WHALE_CRM', '2', 800000.00, NULL, 35.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (39, 'OPP00000039', '鍗椾含閾惰-鏁版嵁宸ュ巶-椤圭洰', '閲戣瀺', '1', 'CUST000013', 'hufei', '233', 'WHALE_DF', '1', 600000.00, NULL, 15.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (40, 'OPP00000040', '鑻忕渷鏁版嵁-CRM-椤圭洰', '鏀垮簻', '2', 'CUST000014', 'diyun', '234', 'WHALE_CRM', '4', 900000.00, 870000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2025-12-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (41, 'OPP00000041', '鑻忕渷鏁版嵁-BI-椤圭洰', '鏀垮簻', '2', 'CUST000014', 'diyun', '234', 'WHALE_BI', '3', 1100000.00, NULL, 55.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (42, 'OPP00000042', '鑻忕渷鏁版嵁-鏅鸿兘浣?椤圭洰', '鏀垮簻', '2', 'CUST000014', 'diyun', '234', 'WHALE_AGENT', '1', 350000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (43, 'OPP00000043', '娴欏ぇ-BI-椤圭洰', '鏁欒偛', '4', 'CUST000015', 'diyun', '234', 'WHALE_BI', '4', 700000.00, 680000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2025-12-18 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (44, 'OPP00000044', '娴欏ぇ-鏅鸿兘浣?椤圭洰', '鏁欒偛', '4', 'CUST000015', 'diyun', '234', 'WHALE_AGENT', '2', 400000.00, NULL, 40.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (45, 'OPP00000045', '娴欏ぇ-CRM-椤圭洰', '鏁欒偛', '4', 'CUST000015', 'diyun', '234', 'WHALE_CRM', '5', 300000.00, NULL, 0.00, '瀹㈡埛棰勭畻缂╁噺', NULL, '2026-03-01 00:00:00', NULL, 'admin', '2026-01-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (46, 'OPP00000046', '闃块噷宸村反-鏁版嵁宸ュ巶-椤圭洰', '鍒堕€?, '5', 'CUST000016', 'diyun', '234', 'WHALE_DF', '4', 4000000.00, 3800000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-20 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (47, 'OPP00000047', '闃块噷宸村反-BI-椤圭洰', '鍒堕€?, '5', 'CUST000016', 'diyun', '234', 'WHALE_BI', '3', 2000000.00, NULL, 65.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (48, 'OPP00000048', '闃块噷宸村反-MASS-椤圭洰', '鍒堕€?, '5', 'CUST000016', 'diyun', '234', 'WHALE_MASS', '1', 800000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (49, 'OPP00000049', '瀹佹尝閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000017', 'hufei', '233', 'WHALE_BI', '4', 1400000.00, 1350000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2025-12-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (50, 'OPP00000050', '瀹佹尝閾惰-鏁版嵁宸ュ巶-椤圭洰', '閲戣瀺', '1', 'CUST000017', 'hufei', '233', 'WHALE_DF', '2', 900000.00, NULL, 40.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (51, 'OPP00000051', '鑵捐-鏁版嵁宸ュ巶-椤圭洰', '鍒堕€?, '5', 'CUST000018', 'chenjialuo', '236', 'WHALE_DF', '4', 5000000.00, 4800000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-24 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (52, 'OPP00000052', '鑵捐-BI-椤圭洰', '鍒堕€?, '5', 'CUST000018', 'chenjialuo', '236', 'WHALE_BI', '3', 2500000.00, NULL, 60.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (53, 'OPP00000053', '鑵捐-鏅鸿兘浣?椤圭洰', '鍒堕€?, '5', 'CUST000018', 'chenjialuo', '236', 'WHALE_AGENT', '2', 800000.00, NULL, 45.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (54, 'OPP00000054', '瓒婄鏁欒偛-CRM-椤圭洰', '鏀垮簻', '4', 'CUST000019', 'chenjialuo', '236', 'WHALE_CRM', '4', 500000.00, 480000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2025-12-26 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (55, 'OPP00000055', '瓒婄鏁欒偛-BI-椤圭洰', '鏀垮簻', '4', 'CUST000019', 'chenjialuo', '236', 'WHALE_BI', '1', 700000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-03-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (56, 'OPP00000056', '瓒婄鏁欒偛-鏅鸿兘浣?椤圭洰', '鏀垮簻', '4', 'CUST000019', 'chenjialuo', '236', 'WHALE_AGENT', '5', 300000.00, NULL, 0.00, '绔炲搧浠锋牸鏇翠綆', NULL, '2026-03-01 00:00:00', NULL, 'admin', '2026-01-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (57, 'OPP00000057', '鍗庝负-鏁版嵁宸ュ巶-椤圭洰', '鍒堕€?, '5', 'CUST000020', 'chenjialuo', '236', 'WHALE_DF', '4', 8000000.00, 7500000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-28 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (58, 'OPP00000058', '鍗庝负-BI-椤圭洰', '鍒堕€?, '5', 'CUST000020', 'chenjialuo', '236', 'WHALE_BI', '3', 3000000.00, NULL, 65.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (59, 'OPP00000059', '鍗庝负-MASS-椤圭洰', '鍒堕€?, '5', 'CUST000020', 'chenjialuo', '236', 'WHALE_MASS', '1', 1000000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (60, 'OPP00000060', '寤鸿澶╂触-BI-椤圭洰', '閲戣瀺', '1', 'CUST000021', 'weixiaobao', '231', 'WHALE_BI', '4', 1800000.00, 1700000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-29 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (61, 'OPP00000061', '寤鸿澶╂触-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000021', 'weixiaobao', '231', 'WHALE_CRM', '2', 900000.00, NULL, 35.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (62, 'OPP00000062', '寤鸿澶╂触-鏁版嵁宸ュ巶-椤圭洰', '閲戣瀺', '1', 'CUST000021', 'weixiaobao', '231', 'WHALE_DF', '5', 700000.00, NULL, 0.00, '瀹㈡埛鍐呴儴鍐崇瓥鏈€氳繃', NULL, '2026-03-01 00:00:00', NULL, 'admin', '2026-01-19 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (63, 'OPP00000063', '澶╂触婊ㄦ捣-BI-椤圭洰', '鏀垮簻', '2', 'CUST000022', 'weixiaobao', '231', 'WHALE_BI', '4', 1000000.00, 950000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (64, 'OPP00000064', '澶╂触婊ㄦ捣-CRM-椤圭洰', '鏀垮簻', '2', 'CUST000022', 'weixiaobao', '231', 'WHALE_CRM', '3', 600000.00, NULL, 55.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (65, 'OPP00000065', '澶╂触婊ㄦ捣-鏅鸿兘浣?椤圭洰', '鏀垮簻', '2', 'CUST000022', 'weixiaobao', '231', 'WHALE_AGENT', '1', 250000.00, NULL, 15.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (66, 'OPP00000066', '鍐滆灞变笢-BI-椤圭洰', '閲戣瀺', '1', 'CUST000024', 'zhangwuji', '240', 'WHALE_BI', '4', 2200000.00, 2100000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (67, 'OPP00000067', '鍐滆灞变笢-鏁版嵁宸ュ巶-椤圭洰', '閲戣瀺', '1', 'CUST000024', 'zhangwuji', '240', 'WHALE_DF', '2', 1500000.00, NULL, 40.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (68, 'OPP00000068', '灞变笢鐪佷汉姘戝尰闄?CRM-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000025', 'zhangwuji', '240', 'WHALE_CRM', '4', 700000.00, 670000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (69, 'OPP00000069', '灞变笢鐪佷汉姘戝尰闄?BI-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000025', 'zhangwuji', '240', 'WHALE_BI', '1', 900000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (70, 'OPP00000070', '閮戝窞閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000026', 'zhangwuji', '240', 'WHALE_BI', '4', 1200000.00, 1150000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (71, 'OPP00000071', '閮戝窞閾惰-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000026', 'zhangwuji', '240', 'WHALE_CRM', '3', 700000.00, NULL, 60.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (72, 'OPP00000072', '璞渷鍗仴-CRM-椤圭洰', '鏀垮簻', '3', 'CUST000027', 'zhangwuji', '240', 'WHALE_CRM', '4', 650000.00, 620000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (73, 'OPP00000073', '璞渷鍗仴-鏁版嵁宸ュ巶-椤圭洰', '鏀垮簻', '3', 'CUST000027', 'zhangwuji', '240', 'WHALE_DF', '5', 500000.00, NULL, 0.00, '闇€姹傚彉鏇存悂缃?, NULL, '2026-03-01 00:00:00', NULL, 'admin', '2026-01-25 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (74, 'OPP00000074', '閲嶅簡鍐滃晢-BI-椤圭洰', '閲戣瀺', '1', 'CUST000028', 'yangguo', '238', 'WHALE_BI', '4', 1600000.00, 1520000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (75, 'OPP00000075', '閲嶅簡鍐滃晢-鏁版嵁宸ュ巶-椤圭洰', '閲戣瀺', '1', 'CUST000028', 'yangguo', '238', 'WHALE_DF', '2', 1000000.00, NULL, 40.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (76, 'OPP00000076', '璐靛窞澶ф暟鎹?CRM-椤圭洰', '鏀垮簻', '2', 'CUST000029', 'yangguo', '238', 'WHALE_CRM', '4', 800000.00, 760000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-18 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (77, 'OPP00000077', '璐靛窞澶ф暟鎹?BI-椤圭洰', '鏀垮簻', '2', 'CUST000029', 'yangguo', '238', 'WHALE_BI', '1', 1000000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (78, 'OPP00000078', '浜戝崡鏁板瓧-CRM-椤圭洰', '鏀垮簻', '2', 'CUST000030', 'yangguo', '238', 'WHALE_CRM', '4', 700000.00, 680000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-20 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (79, 'OPP00000079', '鍘﹂棬鍥介檯閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000031', 'hufei', '233', 'WHALE_BI', '4', 1200000.00, 1150000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-22 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (80, 'OPP00000080', '鍘﹂棬鍥介檯閾惰-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000031', 'hufei', '233', 'WHALE_CRM', '2', 700000.00, NULL, 35.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-02-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (81, 'OPP00000081', '闂藉尰绉戝ぇ-CRM-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000032', 'hufei', '233', 'WHALE_CRM', '4', 600000.00, 580000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-24 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (82, 'OPP00000082', '鑻忓窞宸ヤ笟鍥?BI-椤圭洰', '鏀垮簻', '2', 'CUST000033', 'diyun', '234', 'WHALE_BI', '4', 1300000.00, 1250000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-26 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (83, 'OPP00000083', '鏃犻敗澶ф暟鎹?CRM-椤圭洰', '鏀垮簻', '2', 'CUST000034', 'diyun', '234', 'WHALE_CRM', '4', 750000.00, 720000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (84, 'OPP00000084', '鏃犻敗澶ф暟鎹?BI-椤圭洰', '鏀垮簻', '2', 'CUST000034', 'diyun', '234', 'WHALE_BI', '3', 900000.00, NULL, 55.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (85, 'OPP00000085', '鑻忕渷浜烘皯鍖婚櫌-BI-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000035', 'hufei', '233', 'WHALE_BI', '4', 1100000.00, 1050000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (86, 'OPP00000086', '涓婃捣浜ゅぇ-鏅鸿兘浣?椤圭洰', '鏁欒偛', '4', 'CUST000036', 'hufei', '233', 'WHALE_AGENT', '4', 500000.00, 480000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (87, 'OPP00000087', '涓婃捣澶ф暟鎹?CRM-椤圭洰', '鏀垮簻', '2', 'CUST000037', 'diyun', '234', 'WHALE_CRM', '4', 1200000.00, 1150000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (88, 'OPP00000088', '涓浗鐢典俊涓婃捣-MASS-椤圭洰', '鍒堕€?, '9', 'CUST000038', 'diyun', '234', 'WHALE_MASS', '4', 2000000.00, 1900000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (89, 'OPP00000089', '鍖椾含閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000039', 'weixiaobao', '231', 'WHALE_BI', '4', 1500000.00, 1420000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (90, 'OPP00000090', '鍖椾含甯傚ぇ鏁版嵁-CRM-椤圭洰', '鏀垮簻', '2', 'CUST000040', 'weixiaobao', '231', 'WHALE_CRM', '4', 900000.00, 870000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (91, 'OPP00000091', '鍖椾含鍗忓拰-BI-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000041', 'weixiaobao', '231', 'WHALE_BI', '3', 1400000.00, NULL, 60.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-03-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (92, 'OPP00000092', '涓浗鐢靛缓-鏁版嵁宸ュ巶-椤圭洰', '鍒堕€?, '7', 'CUST000042', 'weixiaobao', '231', 'WHALE_DF', '4', 3000000.00, 2800000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-18 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (93, 'OPP00000093', '涓Щ鍔ㄥ箍涓?MASS-椤圭洰', '鍒堕€?, '9', 'CUST000043', 'chenjialuo', '236', 'WHALE_MASS', '4', 2500000.00, 2400000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-20 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (94, 'OPP00000094', '骞垮窞鍐滃晢-BI-椤圭洰', '閲戣瀺', '1', 'CUST000044', 'chenjialuo', '236', 'WHALE_BI', '4', 1700000.00, 1620000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (95, 'OPP00000095', '骞垮窞鍐滃晢-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000044', 'chenjialuo', '236', 'WHALE_CRM', '2', 900000.00, NULL, 35.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (96, 'OPP00000096', '娴峰崡澶ф暟鎹?CRM-椤圭洰', '鏀垮簻', '2', 'CUST000045', 'chenjialuo', '236', 'WHALE_CRM', '3', 700000.00, NULL, 55.00, NULL, NULL, '2026-04-01 00:00:00', NULL, 'admin', '2026-03-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (97, 'OPP00000097', '瑗垮畨閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000046', 'yangguo', '238', 'WHALE_BI', '4', 1100000.00, 1050000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (98, 'OPP00000098', '闄曡タ鏁板瓧-CRM-椤圭洰', '鏀垮簻', '2', 'CUST000047', 'yangguo', '238', 'WHALE_CRM', '2', 800000.00, NULL, 40.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (99, 'OPP00000099', '宸濈渷浜烘皯鍖婚櫌-BI-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000048', 'yangguo', '238', 'WHALE_BI', '1', 1000000.00, NULL, 20.00, NULL, NULL, '2026-05-01 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (100, 'OPP00000100', '婀栧崡澶ф暟鎹?CRM-椤圭洰', '鏀垮簻', '2', 'CUST000049', 'zhangwuji', '240', 'WHALE_CRM', '4', 850000.00, 820000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (101, 'OPP00000101', '闀挎矙閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000050', 'zhangwuji', '240', 'WHALE_BI', '4', 1300000.00, 1250000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (102, 'OPP00000102', '闈掑矝閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000051', 'zhangwuji', '240', 'WHALE_BI', '3', 1100000.00, NULL, 60.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (103, 'OPP00000103', '娴庡崡澶ф暟鎹?CRM-椤圭洰', '鏀垮簻', '2', 'CUST000052', 'zhangwuji', '240', 'WHALE_CRM', '2', 700000.00, NULL, 30.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (104, 'OPP00000104', '鍚堣偉鏁版嵁-CRM-椤圭洰', '鏀垮簻', '2', 'CUST000053', 'hufei', '233', 'WHALE_CRM', '4', 750000.00, 720000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (105, 'OPP00000105', '瀹夊窘鐪佺珛鍖婚櫌-BI-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000054', 'hufei', '233', 'WHALE_BI', '3', 900000.00, NULL, 50.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (106, 'OPP00000106', '寰藉晢閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000055', 'hufei', '233', 'WHALE_BI', '4', 1200000.00, 1150000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (107, 'OPP00000107', '鍗楁槍鏀垮姟-CRM-椤圭洰', '鏀垮簻', '2', 'CUST000056', 'hufei', '233', 'WHALE_CRM', '1', 600000.00, NULL, 20.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (108, 'OPP00000108', '姹熻タ閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000057', 'diyun', '234', 'WHALE_BI', '4', 1000000.00, 960000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (109, 'OPP00000109', '鍗楀畞澶ф暟鎹?CRM-椤圭洰', '鏀垮簻', '2', 'CUST000058', 'chenjialuo', '236', 'WHALE_CRM', '3', 700000.00, NULL, 55.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (110, 'OPP00000110', '骞胯タ浜烘皯鍖婚櫌-BI-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000059', 'chenjialuo', '236', 'WHALE_BI', '4', 800000.00, 760000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (111, 'OPP00000111', '妗傛灄閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000060', 'chenjialuo', '236', 'WHALE_BI', '2', 900000.00, NULL, 35.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (112, 'OPP00000112', '鍏板窞閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000061', 'yangguo', '238', 'WHALE_BI', '4', 1000000.00, 960000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (113, 'OPP00000113', '鐢樿們鏁版嵁-CRM-椤圭洰', '鏀垮簻', '2', 'CUST000062', 'yangguo', '238', 'WHALE_CRM', '1', 600000.00, NULL, 20.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (114, 'OPP00000114', '瀹佸閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000063', 'yangguo', '238', 'WHALE_BI', '3', 800000.00, NULL, 50.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (115, 'OPP00000115', '鍐呰挋鍙ゅぇ鏁版嵁-CRM-椤圭洰', '鏀垮簻', '2', 'CUST000064', 'weixiaobao', '231', 'WHALE_CRM', '4', 700000.00, 670000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (116, 'OPP00000116', '鍐呰挋鍙ら摱琛?BI-椤圭洰', '閲戣瀺', '1', 'CUST000065', 'weixiaobao', '231', 'WHALE_BI', '2', 900000.00, NULL, 35.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (117, 'OPP00000117', '鍝堝皵婊ㄩ摱琛?BI-椤圭洰', '閲戣瀺', '1', 'CUST000066', 'weixiaobao', '231', 'WHALE_BI', '4', 1100000.00, 1050000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-04-18 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (118, 'OPP00000118', '榛戦緳姹熸斂鍔?CRM-椤圭洰', '鏀垮簻', '2', 'CUST000067', 'weixiaobao', '231', 'WHALE_CRM', '3', 700000.00, NULL, 55.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-20 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (119, 'OPP00000119', '鍚夋灄閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000068', 'weixiaobao', '231', 'WHALE_BI', '4', 1000000.00, 950000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-04-22 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (120, 'OPP00000120', '闀挎槬澶ф暟鎹?CRM-椤圭洰', '鏀垮簻', '2', 'CUST000069', 'weixiaobao', '231', 'WHALE_CRM', '1', 600000.00, NULL, 20.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-24 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (121, 'OPP00000121', '杈藉畞浜烘皯鍖婚櫌-BI-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000070', 'weixiaobao', '231', 'WHALE_BI', '3', 900000.00, NULL, 50.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-26 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (122, 'OPP00000122', '鐩涗含閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000071', 'weixiaobao', '231', 'WHALE_BI', '4', 1200000.00, 1150000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-04-27 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (123, 'OPP00000123', '涓滃寳澶у-鏅鸿兘浣?椤圭洰', '鏁欒偛', '4', 'CUST000072', 'weixiaobao', '231', 'WHALE_AGENT', '2', 400000.00, NULL, 40.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-28 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (124, 'OPP00000124', '娴欐睙浜烘皯鍖婚櫌-CRM-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000073', 'diyun', '235', 'WHALE_CRM', '4', 700000.00, 670000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-04-29 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (125, 'OPP00000125', '缃戞槗-鏁版嵁宸ュ巶-椤圭洰', '鍒堕€?, '5', 'CUST000074', 'diyun', '235', 'WHALE_DF', '3', 3000000.00, NULL, 60.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-04-30 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (126, 'OPP00000126', '灞辫タ澶ф暟鎹?CRM-椤圭洰', '鏀垮簻', '2', 'CUST000075', 'weixiaobao', '231', 'WHALE_CRM', '1', 600000.00, NULL, 20.00, NULL, NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-05-01 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (127, 'OPP00000127', '灞辫タ閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000076', 'weixiaobao', '231', 'WHALE_BI', '2', 900000.00, NULL, 35.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-05-02 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (128, 'OPP00000128', '涓骞夸笢-BI-椤圭洰', '閲戣瀺', '1', 'CUST000077', 'chenjialuo', '236', 'WHALE_BI', '4', 2500000.00, 2400000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-03 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (129, 'OPP00000129', '骞垮窞甯傛暟鎹?CRM-椤圭洰', '鏀垮簻', '2', 'CUST000078', 'chenjialuo', '237', 'WHALE_CRM', '3', 800000.00, NULL, 55.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-05-03 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (130, 'OPP00000130', '娣卞湷鏁板瓧鐮旂┒闄?BI-椤圭洰', '鏀垮簻', '2', 'CUST000079', 'chenjialuo', '237', 'WHALE_BI', '1', 1000000.00, NULL, 20.00, NULL, NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-05-04 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (131, 'OPP00000131', '涓北澶у-鏅鸿兘浣?椤圭洰', '鏁欒偛', '4', 'CUST000080', 'chenjialuo', '236', 'WHALE_AGENT', '4', 500000.00, 480000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-04 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (132, 'OPP00000132', '绂忓窞閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000081', 'hufei', '233', 'WHALE_BI', '4', 1100000.00, 1050000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-05 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (133, 'OPP00000133', '绂忓缓鏁板瓧-CRM-椤圭洰', '鏀垮簻', '2', 'CUST000082', 'hufei', '233', 'WHALE_CRM', '2', 700000.00, NULL, 35.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-05-05 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (134, 'OPP00000134', '鍘﹂棬澶у-鏅鸿兘浣?椤圭洰', '鏁欒偛', '4', 'CUST000083', 'hufei', '233', 'WHALE_AGENT', '3', 400000.00, NULL, 50.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-05-06 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (135, 'OPP00000135', '璐甸槼閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000084', 'yangguo', '238', 'WHALE_BI', '4', 1000000.00, 960000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-06 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (136, 'OPP00000136', '浜戝崡浜烘皯鍖婚櫌-CRM-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000085', 'yangguo', '238', 'WHALE_CRM', '1', 600000.00, NULL, 20.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-05-07 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (137, 'OPP00000137', '鏄嗘槑澶ф暟鎹?BI-椤圭洰', '鏀垮簻', '2', 'CUST000086', 'yangguo', '238', 'WHALE_BI', '3', 800000.00, NULL, 55.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-05-07 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (138, 'OPP00000138', '澶钩娲嬩繚闄?鏁版嵁宸ュ巶-椤圭洰', '閲戣瀺', '1', 'CUST000087', 'hufei', '233', 'WHALE_DF', '4', 3500000.00, 3300000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-08 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (139, 'OPP00000139', '鍥芥嘲鍚涘畨-BI-椤圭洰', '閲戣瀺', '1', 'CUST000088', 'hufei', '233', 'WHALE_BI', '4', 2000000.00, 1900000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-08 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (140, 'OPP00000140', '鍗庤兘-鏁版嵁宸ュ巶-椤圭洰', '鍒堕€?, '7', 'CUST000089', 'weixiaobao', '231', 'WHALE_DF', '3', 4000000.00, NULL, 60.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-05-09 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (141, 'OPP00000141', '鍥藉鐢电綉-鏁版嵁宸ュ巶-椤圭洰', '鍒堕€?, '7', 'CUST000090', 'weixiaobao', '231', 'WHALE_DF', '2', 5000000.00, NULL, 40.00, NULL, NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-05-09 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (142, 'OPP00000142', '娣变氦鎵€-BI-椤圭洰', '閲戣瀺', '1', 'CUST000091', 'chenjialuo', '236', 'WHALE_BI', '4', 2500000.00, 2400000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-10 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (143, 'OPP00000143', '涓婁氦鎵€-BI-椤圭洰', '閲戣瀺', '1', 'CUST000092', 'hufei', '233', 'WHALE_BI', '4', 3000000.00, 2850000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-10 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (144, 'OPP00000144', '鍖椾氦鎵€-BI-椤圭洰', '閲戣瀺', '1', 'CUST000093', 'weixiaobao', '231', 'WHALE_BI', '1', 2000000.00, NULL, 20.00, NULL, NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-05-11 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (145, 'OPP00000145', '姝︽眽澶у-鏅鸿兘浣?椤圭洰', '鏁欒偛', '4', 'CUST000094', 'zhangwuji', '240', 'WHALE_AGENT', '3', 500000.00, NULL, 50.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-05-11 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (146, 'OPP00000146', '鍗庝腑绉戞妧-鏅鸿兘浣?椤圭洰', '鏁欒偛', '4', 'CUST000095', 'zhangwuji', '240', 'WHALE_AGENT', '1', 450000.00, NULL, 20.00, NULL, NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-05-11 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (147, 'OPP00000147', '婀栧寳浜烘皯鍖婚櫌-CRM-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000096', 'zhangwuji', '241', 'WHALE_CRM', '4', 700000.00, 670000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-12 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (148, 'OPP00000148', '闀挎矙鍗仴-BI-椤圭洰', '鏀垮簻', '3', 'CUST000097', 'zhangwuji', '241', 'WHALE_BI', '2', 900000.00, NULL, 35.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-05-12 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (149, 'OPP00000149', '婀橀泤鍖婚櫌-鏅鸿兘浣?椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000098', 'zhangwuji', '242', 'WHALE_AGENT', '1', 400000.00, NULL, 20.00, NULL, NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-05-12 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (150, 'OPP00000150', '鎴愰兘澶ф暟鎹?CRM-椤圭洰', '鏀垮簻', '2', 'CUST000099', 'yangguo', '239', 'WHALE_CRM', '3', 750000.00, NULL, 55.00, NULL, NULL, '2026-06-01 00:00:00', NULL, 'admin', '2026-05-12 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (151, 'OPP00000151', '鍥芥姇涓€?MASS-椤圭洰', '閲戣瀺', '1', 'CUST000001', 'weixiaobao', '231', 'WHALE_MASS', '4', 400000.00, 380000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2025-12-01 00:00:00', '2025-12-01 00:00:00', 'admin', '2025-11-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (152, 'OPP00000152', '宸ヨ鍖椾含-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000002', 'weixiaobao', '231', 'WHALE_CRM', '4', 800000.00, 770000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2025-12-01 00:00:00', '2025-12-01 00:00:00', 'admin', '2025-11-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (153, 'OPP00000153', '鎷涜涓婃捣-MASS-椤圭洰', '閲戣瀺', '1', 'CUST000004', 'hufei', '233', 'WHALE_MASS', '4', 600000.00, 580000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2025-12-01 00:00:00', '2025-12-01 00:00:00', 'admin', '2025-11-18 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (154, 'OPP00000154', '骞冲畨閾惰-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000008', 'chenjialuo', '236', 'WHALE_CRM', '4', 900000.00, 860000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2025-12-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (155, 'OPP00000155', '鍗庝负-CRM-椤圭洰', '鍒堕€?, '5', 'CUST000020', 'chenjialuo', '236', 'WHALE_CRM', '4', 1500000.00, 1440000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-27 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (156, 'OPP00000156', '闃块噷宸村反-CRM-椤圭洰', '鍒堕€?, '5', 'CUST000016', 'diyun', '234', 'WHALE_CRM', '4', 2000000.00, 1900000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-19 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (157, 'OPP00000157', '姝︽眽鍟嗚-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000011', 'zhangwuji', '240', 'WHALE_CRM', '4', 700000.00, 670000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (158, 'OPP00000158', '娴﹀彂閾惰-鏁版嵁宸ュ巶-椤圭洰', '閲戣瀺', '1', 'CUST000005', 'hufei', '233', 'WHALE_DF', '4', 1200000.00, 1150000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-01-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2025-12-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (159, 'OPP00000159', '瀹佹尝閾惰-MASS-椤圭洰', '閲戣瀺', '1', 'CUST000017', 'hufei', '233', 'WHALE_MASS', '4', 500000.00, 480000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (160, 'OPP00000160', '鑵捐-CRM-椤圭洰', '鍒堕€?, '5', 'CUST000018', 'chenjialuo', '236', 'WHALE_CRM', '4', 1800000.00, 1720000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (161, 'OPP00000161', '鍗椾含閾惰-MASS-椤圭洰', '閲戣瀺', '1', 'CUST000013', 'hufei', '233', 'WHALE_MASS', '4', 500000.00, 480000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (162, 'OPP00000162', '鑻忕渷鏁版嵁-鏁版嵁宸ュ巶-椤圭洰', '鏀垮簻', '2', 'CUST000014', 'diyun', '234', 'WHALE_DF', '4', 1500000.00, 1430000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-02-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-01-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (163, 'OPP00000163', '鎴愰兘楂樻柊-MASS-椤圭洰', '鏀垮簻', '2', 'CUST000009', 'yangguo', '238', 'WHALE_MASS', '4', 400000.00, 380000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (164, 'OPP00000164', '閲嶅簡鍐滃晢-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000028', 'yangguo', '238', 'WHALE_CRM', '4', 700000.00, 670000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (165, 'OPP00000165', '閮戝窞閾惰-鏁版嵁宸ュ巶-椤圭洰', '閲戣瀺', '1', 'CUST000026', 'zhangwuji', '240', 'WHALE_DF', '4', 1000000.00, 960000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (166, 'OPP00000166', '鍘﹂棬鍥介檯閾惰-鏁版嵁宸ュ巶-椤圭洰', '閲戣瀺', '1', 'CUST000031', 'hufei', '233', 'WHALE_DF', '4', 800000.00, 760000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (167, 'OPP00000167', '鑻忓窞宸ヤ笟鍥?CRM-椤圭洰', '鏀垮簻', '2', 'CUST000033', 'diyun', '234', 'WHALE_CRM', '4', 600000.00, 580000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (168, 'OPP00000168', '寤鸿澶╂触-MASS-椤圭洰', '閲戣瀺', '1', 'CUST000021', 'weixiaobao', '231', 'WHALE_MASS', '4', 400000.00, 380000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (169, 'OPP00000169', '璐靛窞澶ф暟鎹?鏁版嵁宸ュ巶-椤圭洰', '鏀垮簻', '2', 'CUST000029', 'yangguo', '238', 'WHALE_DF', '4', 1200000.00, 1150000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-03-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-02-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (170, 'OPP00000170', '鑻忕渷浜烘皯鍖婚櫌-CRM-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000035', 'hufei', '233', 'WHALE_CRM', '4', 600000.00, 580000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (171, 'OPP00000171', '寰藉晢閾惰-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000055', 'hufei', '233', 'WHALE_CRM', '4', 700000.00, 670000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (172, 'OPP00000172', '瑗垮畨閾惰-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000046', 'yangguo', '238', 'WHALE_CRM', '4', 600000.00, 580000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (173, 'OPP00000173', '涓婁氦鎵€-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000092', 'hufei', '233', 'WHALE_CRM', '4', 1500000.00, 1420000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-11 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (174, 'OPP00000174', '娣变氦鎵€-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000091', 'chenjialuo', '236', 'WHALE_CRM', '4', 1200000.00, 1150000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-11 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (175, 'OPP00000175', '澶钩娲嬩繚闄?BI-椤圭洰', '閲戣瀺', '1', 'CUST000087', 'hufei', '233', 'WHALE_BI', '4', 2000000.00, 1900000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-05-09 07:20:08.344498', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (176, 'OPP00000176', '闈掑矝閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000051', 'zhangwuji', '240', 'WHALE_BI', '4', 1470000.00, 1280000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (177, 'OPP00000177', '姹熻タ閾惰-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000057', 'diyun', '234', 'WHALE_CRM', '4', 780000.00, 680000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (178, 'OPP00000178', '妗傛灄閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000060', 'chenjialuo', '236', 'WHALE_BI', '4', 1060000.00, 920000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (179, 'OPP00000179', '瀹佸閾惰-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000063', 'yangguo', '238', 'WHALE_CRM', '4', 600000.00, 520000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (180, 'OPP00000180', '鍐呰挋鍙ら摱琛?BI-椤圭洰', '閲戣瀺', '1', 'CUST000065', 'weixiaobao', '231', 'WHALE_BI', '4', 900000.00, 780000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (181, 'OPP00000181', '鍚夋灄閾惰-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000068', 'weixiaobao', '231', 'WHALE_CRM', '4', 550000.00, 480000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (182, 'OPP00000182', '灞辫タ閾惰-BI-椤圭洰', '閲戣瀺', '1', 'CUST000076', 'weixiaobao', '231', 'WHALE_BI', '4', 970000.00, 840000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (183, 'OPP00000183', '涓婁氦鎵€-鏁版嵁宸ュ巶-椤圭洰', '閲戣瀺', '1', 'CUST000092', 'hufei', '233', 'WHALE_DF', '4', 5180000.00, 4500000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (184, 'OPP00000184', '鍖椾含澶ф暟鎹?BI-椤圭洰', '鏀垮簻', '2', 'CUST000040', 'weixiaobao', '231', 'WHALE_BI', '4', 1720000.00, 1500000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (185, 'OPP00000185', '娴峰崡澶ф暟鎹?CRM-椤圭洰', '鏀垮簻', '2', 'CUST000045', 'chenjialuo', '236', 'WHALE_CRM', '4', 670000.00, 580000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (186, 'OPP00000186', '闄曡タ鏁板瓧鏀垮簻-CRM-椤圭洰', '鏀垮簻', '2', 'CUST000047', 'yangguo', '238', 'WHALE_CRM', '4', 870000.00, 760000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (187, 'OPP00000187', '婀栧崡澶ф暟鎹?BI-椤圭洰', '鏀垮簻', '2', 'CUST000049', 'zhangwuji', '240', 'WHALE_BI', '4', 1060000.00, 920000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (188, 'OPP00000188', '娴庡崡澶ф暟鎹?CRM-椤圭洰', '鏀垮簻', '2', 'CUST000052', 'zhangwuji', '240', 'WHALE_CRM', '4', 740000.00, 640000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (189, 'OPP00000189', '鍚堣偉澶ф暟鎹?BI-椤圭洰', '鏀垮簻', '2', 'CUST000053', 'hufei', '233', 'WHALE_BI', '4', 1010000.00, 880000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (190, 'OPP00000190', '鍗楁槍鏀垮姟-CRM-椤圭洰', '鏀垮簻', '2', 'CUST000056', 'hufei', '233', 'WHALE_CRM', '4', 600000.00, 520000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (191, 'OPP00000191', '鍗楀畞澶ф暟鎹?BI-椤圭洰', '鏀垮簻', '2', 'CUST000058', 'chenjialuo', '236', 'WHALE_BI', '4', 870000.00, 760000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (192, 'OPP00000192', '鐢樿們鏁版嵁-CRM-椤圭洰', '鏀垮簻', '2', 'CUST000062', 'yangguo', '238', 'WHALE_CRM', '4', 520000.00, 450000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (193, 'OPP00000193', '鍐呰挋鍙ゅぇ鏁版嵁-BI-椤圭洰', '鏀垮簻', '2', 'CUST000064', 'weixiaobao', '231', 'WHALE_BI', '4', 790000.00, 690000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (194, 'OPP00000194', '榛戦緳姹熸斂鍔?CRM-椤圭洰', '鏀垮簻', '2', 'CUST000067', 'weixiaobao', '231', 'WHALE_CRM', '4', 550000.00, 480000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (195, 'OPP00000195', '闀挎槬鏁版嵁-BI-椤圭洰', '鏀垮簻', '2', 'CUST000069', 'weixiaobao', '231', 'WHALE_BI', '4', 640000.00, 560000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (196, 'OPP00000196', '灞辫タ澶ф暟鎹?CRM-椤圭洰', '鏀垮簻', '2', 'CUST000075', 'weixiaobao', '231', 'WHALE_CRM', '4', 750000.00, 650000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (197, 'OPP00000197', '骞垮窞鏁版嵁-鏁版嵁宸ュ巶-椤圭洰', '鏀垮簻', '2', 'CUST000078', 'chenjialuo', '237', 'WHALE_DF', '4', 3220000.00, 2800000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (198, 'OPP00000198', '娣卞湷鏁板瓧鏀垮簻-BI-椤圭洰', '鏀垮簻', '2', 'CUST000079', 'chenjialuo', '237', 'WHALE_BI', '4', 1260000.00, 1100000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (199, 'OPP00000199', '绂忓缓鏁板瓧鍔?CRM-椤圭洰', '鏀垮簻', '2', 'CUST000082', 'hufei', '233', 'WHALE_CRM', '4', 900000.00, 780000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (200, 'OPP00000200', '鏄嗘槑澶ф暟鎹?BI-椤圭洰', '鏀垮簻', '2', 'CUST000086', 'yangguo', '238', 'WHALE_BI', '4', 780000.00, 680000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (201, 'OPP00000201', '鎴愰兘澶ф暟鎹?CRM-椤圭洰', '鏀垮簻', '2', 'CUST000099', 'yangguo', '239', 'WHALE_CRM', '4', 620000.00, 540000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (202, 'OPP00000202', '娓濆競澶ф暟鎹?BI-椤圭洰', '鏀垮簻', '2', 'CUST000100', 'yangguo', '239', 'WHALE_BI', '4', 990000.00, 860000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (203, 'OPP00000203', '鍖椾含鍗忓拰-BI-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000041', 'weixiaobao', '231', 'WHALE_BI', '4', 1670000.00, 1450000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (204, 'OPP00000204', '宸濈渷浜烘皯鍖婚櫌-BI-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000048', 'yangguo', '238', 'WHALE_BI', '4', 1440000.00, 1250000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (205, 'OPP00000205', '瀹夊窘鐪佺珛-CRM-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000054', 'hufei', '233', 'WHALE_CRM', '4', 710000.00, 620000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (206, 'OPP00000206', '杈界渷浜烘皯鍖婚櫌-CRM-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000070', 'weixiaobao', '231', 'WHALE_CRM', '4', 550000.00, 480000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (207, 'OPP00000207', '娴欑渷浜烘皯鍖婚櫌-BI-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000073', 'diyun', '235', 'WHALE_BI', '4', 1550000.00, 1350000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (208, 'OPP00000208', '浜戝崡浜烘皯鍖婚櫌-CRM-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000085', 'yangguo', '238', 'WHALE_CRM', '4', 640000.00, 560000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (209, 'OPP00000209', '閯傜渷浜烘皯鍖婚櫌-BI-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000096', 'zhangwuji', '241', 'WHALE_BI', '4', 1930000.00, 1680000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (210, 'OPP00000210', '婀橀泤鍖婚櫌-CRM-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000098', 'zhangwuji', '242', 'WHALE_CRM', '4', 1020000.00, 890000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (211, 'OPP00000211', '涓婁氦澶?CRM-椤圭洰', '鏁欒偛', '4', 'CUST000036', 'hufei', '233', 'WHALE_CRM', '4', 1260000.00, 1100000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2025-11-01 00:00:00', '2025-11-01 00:00:00', 'admin', '2025-10-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (212, 'OPP00000212', '涓滃寳澶у-BI-椤圭洰', '鏁欒偛', '4', 'CUST000072', 'weixiaobao', '231', 'WHALE_BI', '4', 860000.00, 750000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (213, 'OPP00000213', '涓北澶у-CRM-椤圭洰', '鏁欒偛', '4', 'CUST000080', 'chenjialuo', '236', 'WHALE_CRM', '4', 780000.00, 680000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (214, 'OPP00000214', '鍘﹂棬澶у-BI-椤圭洰', '鏁欒偛', '4', 'CUST000083', 'hufei', '233', 'WHALE_BI', '4', 940000.00, 820000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (215, 'OPP00000215', '姝︽眽澶у-CRM-椤圭洰', '鏁欒偛', '4', 'CUST000094', 'zhangwuji', '240', 'WHALE_CRM', '4', 790000.00, 690000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (216, 'OPP00000216', '鍗庝腑绉戝ぇ-BI-椤圭洰', '鏁欒偛', '4', 'CUST000095', 'zhangwuji', '240', 'WHALE_BI', '4', 900000.00, 780000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (217, 'OPP00000217', '缃戞槗-鏁版嵁宸ュ巶-椤圭洰', '鍒堕€?, '5', 'CUST000074', 'diyun', '235', 'WHALE_DF', '4', 4370000.00, 3800000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (218, 'OPP00000218', '鍗庤兘闆嗗洟-鏁版嵁宸ュ巶-椤圭洰', '鍒堕€?, '5', 'CUST000089', 'weixiaobao', '231', 'WHALE_DF', '4', 5980000.00, 5200000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (219, 'OPP00000219', '鍥藉鐢电綉-鏁版嵁宸ュ巶-椤圭洰', '鍒堕€?, '5', 'CUST000090', 'weixiaobao', '231', 'WHALE_DF', '4', 7820000.00, 6800000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (220, 'OPP00000220', '宸ヨ鍖椾含-鏁版嵁宸ュ巶-椤圭洰', '閲戣瀺', '1', 'CUST000002', 'weixiaobao', '231', 'WHALE_DF', '4', 5180000.00, 4500000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (221, 'OPP00000221', '骞冲畨閾惰-MASS-椤圭洰', '閲戣瀺', '1', 'CUST000008', 'chenjialuo', '236', 'WHALE_MASS', '4', 1840000.00, 1600000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (222, 'OPP00000222', '姝︽眽鍟嗚-MASS-椤圭洰', '閲戣瀺', '1', 'CUST000011', 'zhangwuji', '240', 'WHALE_MASS', '4', 1030000.00, 900000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (223, 'OPP00000223', '鍗椾含閾惰-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000013', 'hufei', '233', 'WHALE_CRM', '4', 900000.00, 780000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (224, 'OPP00000224', '闃块噷宸村反-MASS-椤圭洰', '鍒堕€?, '5', 'CUST000016', 'diyun', '234', 'WHALE_MASS', '4', 2420000.00, 2100000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-01-01 00:00:00', '2026-01-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (225, 'OPP00000225', '鑵捐-MASS-椤圭洰', '鍒堕€?, '5', 'CUST000018', 'chenjialuo', '236', 'WHALE_MASS', '4', 2990000.00, 2600000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (226, 'OPP00000226', '鍗庝负-MASS-椤圭洰', '鍒堕€?, '5', 'CUST000020', 'chenjialuo', '236', 'WHALE_MASS', '4', 2070000.00, 1800000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (227, 'OPP00000227', '鍗庝负-DQC-椤圭洰', '鍒堕€?, '5', 'CUST000020', 'chenjialuo', '236', 'WHALE_DQC', '4', 1380000.00, 1200000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (228, 'OPP00000228', '鍐滆灞变笢-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000024', 'zhangwuji', '240', 'WHALE_CRM', '4', 780000.00, 680000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (229, 'OPP00000229', '鍘﹂棬鍥介檯-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000031', 'hufei', '233', 'WHALE_CRM', '4', 670000.00, 580000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (230, 'OPP00000230', '绂忓缓鍖诲ぇ闄?BI-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000032', 'hufei', '233', 'WHALE_BI', '4', 1130000.00, 980000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (231, 'OPP00000231', '鐢靛姏寤鸿-BI-椤圭洰', '鍒堕€?, '5', 'CUST000042', 'weixiaobao', '231', 'WHALE_BI', '4', 1260000.00, 1100000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-02-01 00:00:00', '2026-02-01 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (232, 'OPP00000232', '鍖椾氦鎵€-BI-缁椤圭洰', '閲戣瀺', '1', 'CUST000093', 'weixiaobao', '231', 'WHALE_BI', '4', 2130000.00, 1850000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (233, 'OPP00000233', '鍖椾含閾惰-MASS-椤圭洰', '閲戣瀺', '1', 'CUST000039', 'weixiaobao', '231', 'WHALE_MASS', '4', 920000.00, 800000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (234, 'OPP00000234', '闀挎矙閾惰-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000050', 'zhangwuji', '240', 'WHALE_CRM', '4', 480000.00, 420000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (235, 'OPP00000235', '妗傛灄閾惰-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000060', 'chenjialuo', '236', 'WHALE_CRM', '4', 410000.00, 360000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (236, 'OPP00000236', '鍐呰挋鍙ら摱琛?CRM-椤圭洰', '閲戣瀺', '1', 'CUST000065', 'weixiaobao', '231', 'WHALE_CRM', '4', 390000.00, 340000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (237, 'OPP00000237', '鍝堝皵婊ㄩ摱琛?CRM-椤圭洰', '閲戣瀺', '1', 'CUST000066', 'weixiaobao', '231', 'WHALE_CRM', '4', 520000.00, 450000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (238, 'OPP00000238', '鐩涗含閾惰-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000071', 'weixiaobao', '231', 'WHALE_CRM', '4', 600000.00, 520000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (239, 'OPP00000239', '灞辫タ閾惰-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000076', 'weixiaobao', '231', 'WHALE_CRM', '4', 440000.00, 380000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (240, 'OPP00000240', '绂忓窞閾惰-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000081', 'hufei', '233', 'WHALE_CRM', '4', 480000.00, 420000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (241, 'OPP00000241', '璐甸槼閾惰-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000084', 'yangguo', '238', 'WHALE_CRM', '4', 450000.00, 390000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (242, 'OPP00000242', '澶钩娲嬩繚闄?CRM-椤圭洰', '閲戣瀺', '1', 'CUST000087', 'hufei', '233', 'WHALE_CRM', '4', 980000.00, 850000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (243, 'OPP00000243', '鍥芥嘲鍚涘畨-CRM-椤圭洰', '閲戣瀺', '1', 'CUST000088', 'hufei', '233', 'WHALE_CRM', '4', 870000.00, 760000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (244, 'OPP00000244', '闀挎矙鍗仴濮?BI-椤圭洰', '鏀垮簻', '3', 'CUST000097', 'zhangwuji', '241', 'WHALE_BI', '4', 790000.00, 690000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (245, 'OPP00000245', '婀橀泤鍖婚櫌-BI-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000098', 'zhangwuji', '242', 'WHALE_BI', '4', 970000.00, 840000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (246, 'OPP00000246', '鎴愰兘澶ф暟鎹?BI-椤圭洰', '鏀垮簻', '2', 'CUST000099', 'yangguo', '239', 'WHALE_BI', '4', 830000.00, 720000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (247, 'OPP00000247', '娓濆競澶ф暟鎹?CRM-椤圭洰', '鏀垮簻', '2', 'CUST000100', 'yangguo', '239', 'WHALE_CRM', '4', 530000.00, 460000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (248, 'OPP00000248', '骞垮窞鍗仴-MASS-椤圭洰', '鏀垮簻', '3', 'CUST000006', 'chenjialuo', '236', 'WHALE_MASS', '4', 900000.00, 780000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (249, 'OPP00000249', '鍖椾含娴锋穩-BI-椤圭洰', '鏀垮簻', '2', 'CUST000003', 'diyun', '234', 'WHALE_BI', '4', 1380000.00, 1200000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (250, 'OPP00000250', '骞夸笢浜烘皯鍖婚櫌-CRM-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000007', 'chenjialuo', '236', 'WHALE_CRM', '4', 670000.00, 580000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (251, 'OPP00000251', '婀栧寳鍗仴-BI-椤圭洰', '鏀垮簻', '3', 'CUST000012', 'zhangwuji', '240', 'WHALE_BI', '4', 940000.00, 820000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (252, 'OPP00000252', '鑻忕渷澶ф暟鎹?BI-椤圭洰', '鏀垮簻', '2', 'CUST000014', 'diyun', '234', 'WHALE_BI', '4', 1550000.00, 1350000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (253, 'OPP00000253', '灞变笢浜烘皯鍖婚櫌-BI-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000025', 'zhangwuji', '240', 'WHALE_BI', '4', 1320000.00, 1150000.00, 100.00, NULL, '浠锋牸浼樺娍鏄庢樉', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (254, 'OPP00000254', '浜戝崡鏁板瓧缁忔祹-BI-椤圭洰', '鏀垮簻', '2', 'CUST000030', 'yangguo', '238', 'WHALE_BI', '4', 670000.00, 580000.00, 100.00, NULL, '鍞墠鍝嶅簲鍙婃椂', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (255, 'OPP00000255', '鏃犻敗澶ф暟鎹?BI-椤圭洰', '鏀垮簻', '2', 'CUST000034', 'diyun', '234', 'WHALE_BI', '4', 750000.00, 650000.00, 100.00, NULL, '瀹㈡埛鍏崇郴缁存姢鑹ソ', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_opportunity" VALUES (256, 'OPP00000256', '宸濈渷浜烘皯鍖婚櫌-CRM-椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000048', 'yangguo', '238', 'WHALE_CRM', '4', 620000.00, 540000.00, 100.00, NULL, '浜у搧鍔熻兘濂戝悎搴﹂珮', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);

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
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."id" IS '涓婚敭';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."project_code" IS '椤圭洰缂栫爜';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."project_name" IS '椤圭洰鍚嶇О';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."industry" IS '鎵€灞炶涓?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."domain" IS '鎵€灞為鍩?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."customer_code" IS '鎵€灞炲鎴风紪鐮?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."sales_user_id" IS '鎵€灞為攢鍞敤鎴风紪鐮?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."dept_id" IS '鎵€灞為儴闂ㄧ紪鐮?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."opp_id" IS '鍏宠仈鍟嗘満ID';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."product_code" IS '鎵€灞炰骇鍝佺紪鐮?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."project_status" IS '椤圭洰鐘舵€?1椤圭洰鍚姩 2瀹夎閮ㄧ讲 3椤圭洰浜や粯 4椤圭洰涓婄嚎 5鏀跺叆纭 6瀹屾垚鍥炴)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."contract_amount" IS '绛剧害閲戦';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."revenue_amount" IS '鏀跺叆閲戦';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."payment_amount" IS '鍥炴閲戦';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."arrear_amount" IS '娆犺垂閲戦';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."plan_online_date" IS '璁″垝涓婄嚎鏃ユ湡(YYYY-MM-DD)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."actual_online_date" IS '瀹為檯涓婄嚎鏃ユ湡(YYYY-MM-DD)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."plan_revenue_date" IS '璁″垝鏀跺叆瀹屾垚鏃ユ湡(YYYY-MM-DD)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."actual_revenue_date" IS '瀹為檯鏀跺叆瀹屾垚鏃ユ湡(YYYY-MM-DD)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."plan_payment_date" IS '璁″垝鍥炴瀹屾垚鏃ユ湡(YYYY-MM-DD)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."actual_payment_date" IS '瀹為檯鍥炴瀹屾垚鏃ユ湡(YYYY-MM-DD)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."create_by" IS '鍒涘缓鑰?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."create_time" IS '鍒涘缓鏃堕棿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."update_by" IS '鏇存柊鑰?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."update_time" IS '鏇存柊鏃堕棿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project"."remark" IS '澶囨敞';
COMMENT ON TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_project" IS '椤圭洰淇℃伅琛?;

-- ----------------------------
-- Records of by_project
-- ----------------------------
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (1, 'PROJ00000001', '鍥芥姇涓€?BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000001', 'weixiaobao', '231', 1, 'WHALE_BI', '6', 1100000.00, 1050000.00, 1050000.00, 0.00, '2026-01-01 00:00:00', '2026-01-01 00:00:00', '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2025-12-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (2, 'PROJ00000002', '宸ヨ鍖椾含-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000002', 'weixiaobao', '231', 4, 'WHALE_BI', '6', 2300000.00, 2200000.00, 2200000.00, 0.00, '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-01-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (3, 'PROJ00000003', '宸ヨ鍖椾含-CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000002', 'weixiaobao', '231', 152, 'WHALE_CRM', '5', 770000.00, 750000.00, 600000.00, 150000.00, '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', NULL, 'admin', '2025-12-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (4, 'PROJ00000004', '娴锋穩鏀垮簻-CRM-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000003', 'diyun', '234', 7, 'WHALE_CRM', '6', 850000.00, 820000.00, 820000.00, 0.00, '2026-03-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (5, 'PROJ00000005', '鎷涜涓婃捣-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000004', 'hufei', '233', 10, 'WHALE_BI', '6', 2800000.00, 2700000.00, 2700000.00, 0.00, '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-01-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (6, 'PROJ00000006', '鎷涜涓婃捣-MASS-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000004', 'hufei', '233', 153, 'WHALE_MASS', '5', 580000.00, 560000.00, 400000.00, 160000.00, '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', NULL, 'admin', '2025-12-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (7, 'PROJ00000007', '娴﹀彂閾惰-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000005', 'hufei', '233', 13, 'WHALE_BI', '6', 1400000.00, 1350000.00, 1350000.00, 0.00, '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2026-01-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (8, 'PROJ00000008', '娴﹀彂閾惰-鏁版嵁宸ュ巶-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000005', 'hufei', '233', 158, 'WHALE_DF', '4', 1150000.00, NULL, NULL, NULL, '2026-05-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (9, 'PROJ00000009', '澶╂渤鍗仴-CRM-瀹炴柦椤圭洰', '鏀垮簻', '3', 'CUST000006', 'chenjialuo', '236', 16, 'WHALE_CRM', '6', 580000.00, 560000.00, 560000.00, 0.00, '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', 'admin', '2025-12-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (10, 'PROJ00000010', '绮ょ渷浜烘皯鍖婚櫌-BI-瀹炴柦椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000007', 'chenjialuo', '236', 19, 'WHALE_BI', '5', 1050000.00, 1000000.00, 700000.00, 300000.00, '2026-03-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (11, 'PROJ00000011', '骞冲畨閾惰-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000008', 'chenjialuo', '236', 22, 'WHALE_BI', '6', 1900000.00, 1820000.00, 1820000.00, 0.00, '2026-03-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-01-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (12, 'PROJ00000012', '骞冲畨閾惰-CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000008', 'chenjialuo', '236', 154, 'WHALE_CRM', '4', 860000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2025-12-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (13, 'PROJ00000013', '鎴愰兘楂樻柊-CRM-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000009', 'yangguo', '238', 25, 'WHALE_CRM', '5', 720000.00, 700000.00, 500000.00, 200000.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (14, 'PROJ00000014', '宸濈渷鏁欒偛鍘?BI-瀹炴柦椤圭洰', '鏀垮簻', '4', 'CUST000010', 'yangguo', '238', 28, 'WHALE_BI', '4', 780000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', '2026-04-01 00:00:00', '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (15, 'PROJ00000015', '姝︽眽鍟嗚-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000011', 'zhangwuji', '240', 31, 'WHALE_BI', '6', 1250000.00, 1200000.00, 1200000.00, 0.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (16, 'PROJ00000016', '姝︽眽鍟嗚-CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000011', 'zhangwuji', '240', 157, 'WHALE_CRM', '3', 670000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (17, 'PROJ00000017', '閯傜渷鍗仴-CRM-瀹炴柦椤圭洰', '鏀垮簻', '3', 'CUST000012', 'zhangwuji', '240', 34, 'WHALE_CRM', '5', 680000.00, 660000.00, 400000.00, 260000.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (18, 'PROJ00000018', '鍗椾含閾惰-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000013', 'hufei', '233', 37, 'WHALE_BI', '6', 1520000.00, 1460000.00, 1460000.00, 0.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (19, 'PROJ00000019', '鍗椾含閾惰-MASS-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000013', 'hufei', '233', 161, 'WHALE_MASS', '4', 480000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (20, 'PROJ00000020', '鑻忕渷鏁版嵁-CRM-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000014', 'diyun', '234', 40, 'WHALE_CRM', '5', 870000.00, 850000.00, 600000.00, 250000.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (21, 'PROJ00000021', '鑻忕渷鏁版嵁-鏁版嵁宸ュ巶-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000014', 'diyun', '234', 162, 'WHALE_DF', '4', 1430000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (22, 'PROJ00000022', '娴欏ぇ-BI-瀹炴柦椤圭洰', '鏁欒偛', '4', 'CUST000015', 'diyun', '234', 43, 'WHALE_BI', '6', 680000.00, 660000.00, 660000.00, 0.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', '2026-06-01 00:00:00', 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (23, 'PROJ00000023', '闃块噷宸村反-鏁版嵁宸ュ巶-瀹炴柦椤圭洰', '鍒堕€?, '5', 'CUST000016', 'diyun', '234', 46, 'WHALE_DF', '5', 3800000.00, 3700000.00, 2500000.00, 1200000.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (24, 'PROJ00000024', '闃块噷宸村反-CRM-瀹炴柦椤圭洰', '鍒堕€?, '5', 'CUST000016', 'diyun', '234', 156, 'WHALE_CRM', '4', 1900000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', '2026-06-01 00:00:00', '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (25, 'PROJ00000025', '瀹佹尝閾惰-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000017', 'hufei', '233', 49, 'WHALE_BI', '6', 1350000.00, 1300000.00, 1300000.00, 0.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', '2026-06-01 00:00:00', 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (26, 'PROJ00000026', '鑵捐-鏁版嵁宸ュ巶-瀹炴柦椤圭洰', '鍒堕€?, '5', 'CUST000018', 'chenjialuo', '236', 51, 'WHALE_DF', '5', 4800000.00, 4600000.00, 3000000.00, 1600000.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (27, 'PROJ00000027', '鑵捐-CRM-瀹炴柦椤圭洰', '鍒堕€?, '5', 'CUST000018', 'chenjialuo', '236', 160, 'WHALE_CRM', '4', 1720000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (28, 'PROJ00000028', '瓒婄鏁欒偛-CRM-瀹炴柦椤圭洰', '鏀垮簻', '4', 'CUST000019', 'chenjialuo', '236', 54, 'WHALE_CRM', '5', 480000.00, 465000.00, 300000.00, 165000.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (29, 'PROJ00000029', '鍗庝负-鏁版嵁宸ュ巶-瀹炴柦椤圭洰', '鍒堕€?, '5', 'CUST000020', 'chenjialuo', '236', 57, 'WHALE_DF', '5', 7500000.00, 7200000.00, 5000000.00, 2200000.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (30, 'PROJ00000030', '鍗庝负-CRM-瀹炴柦椤圭洰', '鍒堕€?, '5', 'CUST000020', 'chenjialuo', '236', 155, 'WHALE_CRM', '4', 1440000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', '2026-06-01 00:00:00', '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (31, 'PROJ00000031', '寤鸿澶╂触-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000021', 'weixiaobao', '231', 60, 'WHALE_BI', '5', 1700000.00, 1640000.00, 1000000.00, 640000.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (32, 'PROJ00000032', '澶╂触婊ㄦ捣-BI-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000022', 'weixiaobao', '231', 63, 'WHALE_BI', '5', 950000.00, 920000.00, 600000.00, 320000.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (33, 'PROJ00000033', '鍐滆灞变笢-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000024', 'zhangwuji', '240', 66, 'WHALE_BI', '5', 2100000.00, 2000000.00, 1500000.00, 500000.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (34, 'PROJ00000034', '閮戝窞閾惰-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000026', 'zhangwuji', '240', 70, 'WHALE_BI', '4', 1150000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (35, 'PROJ00000035', '閲嶅簡鍐滃晢-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000028', 'yangguo', '238', 74, 'WHALE_BI', '5', 1520000.00, 1470000.00, 1000000.00, 470000.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (36, 'PROJ00000036', '璐靛窞澶ф暟鎹?CRM-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000029', 'yangguo', '238', 76, 'WHALE_CRM', '4', 760000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', '2026-06-01 00:00:00', '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (37, 'PROJ00000037', '浜戝崡鏁板瓧-CRM-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000030', 'yangguo', '238', 78, 'WHALE_CRM', '3', 680000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (38, 'PROJ00000038', '鍘﹂棬鍥介檯閾惰-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000031', 'hufei', '233', 79, 'WHALE_BI', '5', 1150000.00, 1100000.00, 800000.00, 300000.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (39, 'PROJ00000039', '鑻忓窞宸ヤ笟鍥?BI-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000033', 'diyun', '234', 82, 'WHALE_BI', '5', 1250000.00, 1200000.00, 900000.00, 300000.00, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, 'admin', '2026-03-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (40, 'PROJ00000040', '鏃犻敗澶ф暟鎹?CRM-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000034', 'diyun', '234', 83, 'WHALE_CRM', '4', 720000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', '2026-05-01 00:00:00', '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-04-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (41, 'PROJ00000041', '鍖椾含閾惰-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000039', 'weixiaobao', '231', 89, 'WHALE_BI', '5', 1600000.00, 1472000.00, 853760.00, 618240.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (42, 'PROJ00000042', '骞垮窞鍐滃晢閾惰-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000044', 'chenjialuo', '236', 94, 'WHALE_BI', '6', 1350000.00, 1282500.00, 1179900.00, 102600.00, '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2026-01-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (43, 'PROJ00000043', '闀挎矙閾惰-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000050', 'zhangwuji', '240', 101, 'WHALE_BI', '5', 1150000.00, 1058000.00, 613640.00, 444360.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (44, 'PROJ00000044', '闈掑矝閾惰-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000051', 'zhangwuji', '240', 176, 'WHALE_BI', '4', 1280000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (45, 'PROJ00000045', '寰藉晢閾惰-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000055', 'hufei', '233', 106, 'WHALE_BI', '5', 1420000.00, 1306400.00, 757712.00, 548688.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (46, 'PROJ00000046', '姹熻タ閾惰-CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000057', 'diyun', '234', 177, 'WHALE_CRM', '3', 680000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (47, 'PROJ00000047', '妗傛灄閾惰-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000060', 'chenjialuo', '236', 178, 'WHALE_BI', '4', 920000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (48, 'PROJ00000048', '鍏板窞閾惰-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000061', 'yangguo', '238', 112, 'WHALE_BI', '3', 860000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (49, 'PROJ00000049', '瀹佸閾惰-CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000063', 'yangguo', '238', 179, 'WHALE_CRM', '2', 520000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (50, 'PROJ00000050', '鍐呰挋鍙ら摱琛?BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000065', 'weixiaobao', '231', 180, 'WHALE_BI', '4', 780000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-02-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (51, 'PROJ00000051', '鍝堝皵婊ㄩ摱琛?BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000066', 'weixiaobao', '231', 117, 'WHALE_BI', '3', 1050000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (52, 'PROJ00000052', '鍚夋灄閾惰-CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000068', 'weixiaobao', '231', 181, 'WHALE_CRM', '2', 480000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (53, 'PROJ00000053', '鐩涗含閾惰-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000071', 'weixiaobao', '231', 122, 'WHALE_BI', '5', 1180000.00, 1085600.00, 629648.00, 455952.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (54, 'PROJ00000054', '灞辫タ閾惰-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000076', 'weixiaobao', '231', 182, 'WHALE_BI', '4', 840000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (55, 'PROJ00000055', '绂忓窞閾惰-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000081', 'hufei', '233', 132, 'WHALE_BI', '6', 1320000.00, 1254000.00, 1153680.00, 100320.00, '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (56, 'PROJ00000056', '璐甸槼閾惰-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000084', 'yangguo', '238', 135, 'WHALE_BI', '3', 960000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (57, 'PROJ00000057', '澶钩娲嬩繚闄?鏁版嵁宸ュ巶-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000087', 'hufei', '233', 138, 'WHALE_DF', '4', 3200000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-02-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (58, 'PROJ00000058', '鍥芥嘲鍚涘畨-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000088', 'hufei', '233', 139, 'WHALE_BI', '5', 1800000.00, 1656000.00, 960480.00, 695520.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (59, 'PROJ00000059', '娣变氦鎵€-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000091', 'chenjialuo', '236', 142, 'WHALE_BI', '4', 2100000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (60, 'PROJ00000060', '涓婁氦鎵€-鏁版嵁宸ュ巶-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000092', 'hufei', '233', 183, 'WHALE_DF', '3', 4500000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-02-02 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (61, 'PROJ00000061', '娌ぇ鏁版嵁-CRM-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000037', 'diyun', '234', 87, 'WHALE_CRM', '6', 1200000.00, 1140000.00, 1048800.00, 91200.00, '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2025-12-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (62, 'PROJ00000062', '鍖椾含澶ф暟鎹?BI-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000040', 'weixiaobao', '231', 184, 'WHALE_BI', '5', 1500000.00, 1380000.00, 800400.00, 579600.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (63, 'PROJ00000063', '娴峰崡澶ф暟鎹?CRM-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000045', 'chenjialuo', '236', 185, 'WHALE_CRM', '3', 580000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (64, 'PROJ00000064', '闄曡タ鏁板瓧鏀垮簻-CRM-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000047', 'yangguo', '238', 186, 'WHALE_CRM', '4', 760000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (65, 'PROJ00000065', '婀栧崡澶ф暟鎹?BI-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000049', 'zhangwuji', '240', 187, 'WHALE_BI', '3', 920000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (66, 'PROJ00000066', '娴庡崡澶ф暟鎹?CRM-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000052', 'zhangwuji', '240', 188, 'WHALE_CRM', '2', 640000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (67, 'PROJ00000067', '鍚堣偉澶ф暟鎹?BI-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000053', 'hufei', '233', 189, 'WHALE_BI', '4', 880000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (68, 'PROJ00000068', '鍗楁槍鏀垮姟-CRM-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000056', 'hufei', '233', 190, 'WHALE_CRM', '3', 520000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-04-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (69, 'PROJ00000069', '鍗楀畞澶ф暟鎹?BI-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000058', 'chenjialuo', '236', 191, 'WHALE_BI', '2', 760000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (70, 'PROJ00000070', '鐢樿們鏁版嵁-CRM-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000062', 'yangguo', '238', 192, 'WHALE_CRM', '1', 450000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (71, 'PROJ00000071', '鍐呰挋鍙ゅぇ鏁版嵁-BI-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000064', 'weixiaobao', '231', 193, 'WHALE_BI', '3', 690000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (72, 'PROJ00000072', '榛戦緳姹熸斂鍔?CRM-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000067', 'weixiaobao', '231', 194, 'WHALE_CRM', '2', 480000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (73, 'PROJ00000073', '闀挎槬鏁版嵁-BI-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000069', 'weixiaobao', '231', 195, 'WHALE_BI', '1', 560000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (74, 'PROJ00000074', '灞辫タ澶ф暟鎹?CRM-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000075', 'weixiaobao', '231', 196, 'WHALE_CRM', '3', 650000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (75, 'PROJ00000075', '骞垮窞鏁版嵁-鏁版嵁宸ュ巶-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000078', 'chenjialuo', '237', 197, 'WHALE_DF', '4', 2800000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (76, 'PROJ00000076', '娣卞湷鏁板瓧鏀垮簻-BI-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000079', 'chenjialuo', '237', 198, 'WHALE_BI', '3', 1100000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (77, 'PROJ00000077', '绂忓缓鏁板瓧鍔?CRM-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000082', 'hufei', '233', 199, 'WHALE_CRM', '5', 780000.00, 717600.00, 416208.00, 301392.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (78, 'PROJ00000078', '鏄嗘槑澶ф暟鎹?BI-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000086', 'yangguo', '238', 200, 'WHALE_BI', '2', 680000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (79, 'PROJ00000079', '鎴愰兘澶ф暟鎹?CRM-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000099', 'yangguo', '239', 201, 'WHALE_CRM', '1', 540000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (80, 'PROJ00000080', '娓濆競澶ф暟鎹?BI-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000100', 'yangguo', '239', 202, 'WHALE_BI', '1', 860000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (81, 'PROJ00000081', '鍖椾含鍗忓拰-BI-瀹炴柦椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000041', 'weixiaobao', '231', 203, 'WHALE_BI', '5', 1450000.00, 1334000.00, 773720.00, 560280.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (82, 'PROJ00000082', '宸濈渷浜烘皯鍖婚櫌-BI-瀹炴柦椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000048', 'yangguo', '238', 204, 'WHALE_BI', '4', 1250000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (83, 'PROJ00000083', '瀹夊窘鐪佺珛-CRM-瀹炴柦椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000054', 'hufei', '233', 205, 'WHALE_CRM', '3', 620000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (84, 'PROJ00000084', '骞胯タ浜烘皯鍖婚櫌-BI-瀹炴柦椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000059', 'chenjialuo', '236', 110, 'WHALE_BI', '2', 890000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (85, 'PROJ00000085', '杈界渷浜烘皯鍖婚櫌-CRM-瀹炴柦椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000070', 'weixiaobao', '231', 206, 'WHALE_CRM', '1', 480000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (86, 'PROJ00000086', '娴欑渷浜烘皯鍖婚櫌-BI-瀹炴柦椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000073', 'diyun', '235', 207, 'WHALE_BI', '4', 1350000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (87, 'PROJ00000087', '浜戝崡浜烘皯鍖婚櫌-CRM-瀹炴柦椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000085', 'yangguo', '238', 208, 'WHALE_CRM', '3', 560000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (88, 'PROJ00000088', '閯傜渷浜烘皯鍖婚櫌-BI-瀹炴柦椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000096', 'zhangwuji', '241', 209, 'WHALE_BI', '5', 1680000.00, 1545600.00, 896448.00, 649152.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (89, 'PROJ00000089', '婀橀泤鍖婚櫌-CRM-瀹炴柦椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000098', 'zhangwuji', '242', 210, 'WHALE_CRM', '4', 890000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (90, 'PROJ00000090', '涓婁氦澶?CRM-瀹炴柦椤圭洰', '鏁欒偛', '4', 'CUST000036', 'hufei', '233', 211, 'WHALE_CRM', '6', 1100000.00, 1045000.00, 961400.00, 83600.00, '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2025-12-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (91, 'PROJ00000091', '涓滃寳澶у-BI-瀹炴柦椤圭洰', '鏁欒偛', '4', 'CUST000072', 'weixiaobao', '231', 212, 'WHALE_BI', '5', 750000.00, 690000.00, 400200.00, 289800.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (92, 'PROJ00000092', '涓北澶у-CRM-瀹炴柦椤圭洰', '鏁欒偛', '4', 'CUST000080', 'chenjialuo', '236', 213, 'WHALE_CRM', '3', 680000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (93, 'PROJ00000093', '鍘﹂棬澶у-BI-瀹炴柦椤圭洰', '鏁欒偛', '4', 'CUST000083', 'hufei', '233', 214, 'WHALE_BI', '4', 820000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (94, 'PROJ00000094', '姝︽眽澶у-CRM-瀹炴柦椤圭洰', '鏁欒偛', '4', 'CUST000094', 'zhangwuji', '240', 215, 'WHALE_CRM', '2', 690000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (95, 'PROJ00000095', '鍗庝腑绉戝ぇ-BI-瀹炴柦椤圭洰', '鏁欒偛', '4', 'CUST000095', 'zhangwuji', '240', 216, 'WHALE_BI', '1', 780000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (96, 'PROJ00000096', '绉诲姩骞夸笢-MASS-瀹炴柦椤圭洰', '鍒堕€?, '5', 'CUST000043', 'chenjialuo', '236', 93, 'WHALE_MASS', '6', 2800000.00, 2660000.00, 2447200.00, 212800.00, '2026-02-01 00:00:00', '2026-02-01 00:00:00', '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', 'admin', '2025-12-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (97, 'PROJ00000097', '涓浗鐢典俊娌垎-MASS-瀹炴柦椤圭洰', '鍒堕€?, '5', 'CUST000038', 'diyun', '234', 88, 'WHALE_MASS', '5', 3200000.00, 2944000.00, 1707520.00, 1236480.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-01-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (98, 'PROJ00000098', '缃戞槗-鏁版嵁宸ュ巶-瀹炴柦椤圭洰', '鍒堕€?, '5', 'CUST000074', 'diyun', '235', 217, 'WHALE_DF', '4', 3800000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-02-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (99, 'PROJ00000099', '鍗庤兘闆嗗洟-鏁版嵁宸ュ巶-瀹炴柦椤圭洰', '鍒堕€?, '5', 'CUST000089', 'weixiaobao', '231', 218, 'WHALE_DF', '3', 5200000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (100, 'PROJ00000100', '鍥藉鐢电綉-鏁版嵁宸ュ巶-瀹炴柦椤圭洰', '鍒堕€?, '5', 'CUST000090', 'weixiaobao', '231', 219, 'WHALE_DF', '2', 6800000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (101, 'PROJ00000101', '宸ヨ鍖椾含-BI-缁椤圭洰', '閲戣瀺', '1', 'CUST000002', 'weixiaobao', '231', 4, 'WHALE_BI', '2', 2200000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (102, 'PROJ00000102', '宸ヨ鍖椾含-鏁版嵁宸ュ巶-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000002', 'weixiaobao', '231', 220, 'WHALE_DF', '1', 4500000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (103, 'PROJ00000103', '鎷涘晢閾惰娌?MASS-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000004', 'hufei', '233', 153, 'WHALE_MASS', '3', 1800000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (104, 'PROJ00000104', '骞冲畨閾惰-MASS-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000008', 'chenjialuo', '236', 221, 'WHALE_MASS', '4', 1600000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (105, 'PROJ00000105', '姝︽眽鍟嗚-MASS-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000011', 'zhangwuji', '240', 222, 'WHALE_MASS', '3', 900000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (106, 'PROJ00000106', '鍗椾含閾惰-CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000013', 'hufei', '233', 223, 'WHALE_CRM', '5', 780000.00, 717600.00, 416208.00, 301392.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (107, 'PROJ00000107', '闃块噷宸村反-MASS-瀹炴柦椤圭洰', '鍒堕€?, '5', 'CUST000016', 'diyun', '234', 224, 'WHALE_MASS', '4', 2100000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (108, 'PROJ00000108', '鑵捐-MASS-瀹炴柦椤圭洰', '鍒堕€?, '5', 'CUST000018', 'chenjialuo', '236', 225, 'WHALE_MASS', '2', 2600000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (109, 'PROJ00000109', '鍗庝负-MASS-瀹炴柦椤圭洰', '鍒堕€?, '5', 'CUST000020', 'chenjialuo', '236', 226, 'WHALE_MASS', '1', 1800000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (110, 'PROJ00000110', '鍗庝负-DQC-瀹炴柦椤圭洰', '鍒堕€?, '5', 'CUST000020', 'chenjialuo', '236', 227, 'WHALE_DQC', '1', 1200000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (111, 'PROJ00000111', '鍐滆灞变笢-CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000024', 'zhangwuji', '240', 228, 'WHALE_CRM', '3', 680000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (112, 'PROJ00000112', '閲嶅簡鍐滃晢-CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000028', 'yangguo', '238', 164, 'WHALE_CRM', '4', 540000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (113, 'PROJ00000113', '鍘﹂棬鍥介檯-CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000031', 'hufei', '233', 229, 'WHALE_CRM', '2', 580000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (114, 'PROJ00000114', '绂忓缓鍖诲ぇ闄?BI-瀹炴柦椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000032', 'hufei', '233', 230, 'WHALE_BI', '3', 980000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (115, 'PROJ00000115', '鑻忓窞宸ヤ笟鍥?CRM-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000033', 'diyun', '234', 167, 'WHALE_CRM', '1', 640000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (116, 'PROJ00000116', '鐢靛姏寤鸿-BI-瀹炴柦椤圭洰', '鍒堕€?, '5', 'CUST000042', 'weixiaobao', '231', 231, 'WHALE_BI', '3', 1100000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (117, 'PROJ00000117', '瑗垮畨閾惰-CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000046', 'yangguo', '238', 172, 'WHALE_CRM', '4', 620000.00, NULL, NULL, NULL, '2026-04-01 00:00:00', '2026-04-01 00:00:00', '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, 'admin', '2026-03-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (118, 'PROJ00000118', '寰藉晢閾惰-CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000055', 'hufei', '233', 171, 'WHALE_CRM', '5', 540000.00, 496800.00, 288144.00, 208656.00, '2026-03-01 00:00:00', '2026-04-01 00:00:00', '2026-05-01 00:00:00', '2026-05-01 00:00:00', '2026-06-01 00:00:00', NULL, 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (119, 'PROJ00000119', '涓骞夸笢-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000077', 'chenjialuo', '236', 128, 'WHALE_BI', '3', 2300000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-03-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (120, 'PROJ00000120', '鍖椾氦鎵€-BI-缁椤圭洰', '閲戣瀺', '1', 'CUST000093', 'weixiaobao', '231', 232, 'WHALE_BI', '2', 1850000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (121, 'PROJ00000121', '鍖椾含閾惰-MASS-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000039', 'weixiaobao', '231', 233, 'WHALE_MASS', '1', 800000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (122, 'PROJ00000122', '闀挎矙閾惰-CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000050', 'zhangwuji', '240', 234, 'WHALE_CRM', '2', 420000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (123, 'PROJ00000123', '妗傛灄閾惰-CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000060', 'chenjialuo', '236', 235, 'WHALE_CRM', '1', 360000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-24 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (124, 'PROJ00000124', '鍐呰挋鍙ゅぇ鏁版嵁-CRM-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000064', 'weixiaobao', '231', 115, 'WHALE_CRM', '2', 480000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (125, 'PROJ00000125', '鍐呰挋鍙ら摱琛?CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000065', 'weixiaobao', '231', 236, 'WHALE_CRM', '1', 340000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-27 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (126, 'PROJ00000126', '鍝堝皵婊ㄩ摱琛?CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000066', 'weixiaobao', '231', 237, 'WHALE_CRM', '2', 450000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (127, 'PROJ00000127', '鍚夋灄閾惰-BI-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000068', 'weixiaobao', '231', 119, 'WHALE_BI', '1', 680000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-20 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (128, 'PROJ00000128', '鐩涗含閾惰-CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000071', 'weixiaobao', '231', 238, 'WHALE_CRM', '3', 520000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-04-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (129, 'PROJ00000129', '灞辫タ閾惰-CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000076', 'weixiaobao', '231', 239, 'WHALE_CRM', '2', 380000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (130, 'PROJ00000130', '绂忓窞閾惰-CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000081', 'hufei', '233', 240, 'WHALE_CRM', '1', 420000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-22 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (131, 'PROJ00000131', '璐甸槼閾惰-CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000084', 'yangguo', '238', 241, 'WHALE_CRM', '1', 390000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-25 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (132, 'PROJ00000132', '澶钩娲嬩繚闄?CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000087', 'hufei', '233', 242, 'WHALE_CRM', '2', 850000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (133, 'PROJ00000133', '鍥芥嘲鍚涘畨-CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000088', 'hufei', '233', 243, 'WHALE_CRM', '1', 760000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-17 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (134, 'PROJ00000134', '娣变氦鎵€-CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000091', 'chenjialuo', '236', 174, 'WHALE_CRM', '2', 1100000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (135, 'PROJ00000135', '涓婁氦鎵€-CRM-瀹炴柦椤圭洰', '閲戣瀺', '1', 'CUST000092', 'hufei', '233', 173, 'WHALE_CRM', '1', 980000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-14 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (136, 'PROJ00000136', '闀挎矙鍗仴濮?BI-瀹炴柦椤圭洰', '鏀垮簻', '3', 'CUST000097', 'zhangwuji', '241', 244, 'WHALE_BI', '2', 690000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (137, 'PROJ00000137', '婀橀泤鍖婚櫌-BI-瀹炴柦椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000098', 'zhangwuji', '242', 245, 'WHALE_BI', '1', 840000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-19 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (138, 'PROJ00000138', '鎴愰兘澶ф暟鎹?BI-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000099', 'yangguo', '239', 246, 'WHALE_BI', '2', 720000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (139, 'PROJ00000139', '娓濆競澶ф暟鎹?CRM-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000100', 'yangguo', '239', 247, 'WHALE_CRM', '1', 460000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-21 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (140, 'PROJ00000140', '骞垮窞鍗仴-MASS-瀹炴柦椤圭洰', '鏀垮簻', '3', 'CUST000006', 'chenjialuo', '236', 248, 'WHALE_MASS', '3', 780000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-04-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (141, 'PROJ00000141', '鍖椾含娴锋穩-BI-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000003', 'diyun', '234', 249, 'WHALE_BI', '2', 1200000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (142, 'PROJ00000142', '骞夸笢浜烘皯鍖婚櫌-CRM-瀹炴柦椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000007', 'chenjialuo', '236', 250, 'WHALE_CRM', '1', 580000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-23 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (143, 'PROJ00000143', '婀栧寳鍗仴-BI-瀹炴柦椤圭洰', '鏀垮簻', '3', 'CUST000012', 'zhangwuji', '240', 251, 'WHALE_BI', '2', 820000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (144, 'PROJ00000144', '鑻忕渷澶ф暟鎹?BI-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000014', 'diyun', '234', 252, 'WHALE_BI', '3', 1350000.00, NULL, NULL, NULL, '2026-06-01 00:00:00', NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, 'admin', '2026-04-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (145, 'PROJ00000145', '灞变笢浜烘皯鍖婚櫌-BI-瀹炴柦椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000025', 'zhangwuji', '240', 253, 'WHALE_BI', '2', 1150000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (146, 'PROJ00000146', '娌冲崡鍗仴-CRM-瀹炴柦椤圭洰', '鏀垮簻', '3', 'CUST000027', 'zhangwuji', '240', 72, 'WHALE_CRM', '1', 480000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-18 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (147, 'PROJ00000147', '浜戝崡鏁板瓧缁忔祹-BI-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000030', 'yangguo', '238', 254, 'WHALE_BI', '1', 580000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-15 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (148, 'PROJ00000148', '鏃犻敗澶ф暟鎹?BI-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000034', 'diyun', '234', 255, 'WHALE_BI', '2', 650000.00, NULL, NULL, NULL, '2026-07-01 00:00:00', NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, 'admin', '2026-04-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (149, 'PROJ00000149', '宸濈渷浜烘皯鍖婚櫌-CRM-瀹炴柦椤圭洰', '鍖荤枟鍋ュ悍', '3', 'CUST000048', 'yangguo', '238', 256, 'WHALE_CRM', '1', 540000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-26 07:20:09.215481', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project" VALUES (150, 'PROJ00000150', '婀栧崡澶ф暟鎹?CRM-瀹炴柦椤圭洰', '鏀垮簻', '2', 'CUST000049', 'zhangwuji', '240', 100, 'WHALE_CRM', '1', 620000.00, NULL, NULL, NULL, '2026-08-01 00:00:00', NULL, '2026-09-01 00:00:00', NULL, '2026-10-01 00:00:00', NULL, 'admin', '2026-04-28 07:20:09.215481', NULL, NULL, NULL);

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
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."id" IS '涓婚敭';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."project_code" IS '椤圭洰缂栫爜';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."opp_code" IS '鍟嗘満缂栫爜';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."customer_code" IS '瀹㈡埛缂栫爜';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."product_code" IS '浜у搧缂栫爜';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."task_type" IS '浠诲姟绫诲瀷(鍚岄」鐩姸鎬? 1椤圭洰鍚姩 2瀹夎閮ㄧ讲 3椤圭洰浜や粯 4椤圭洰涓婄嚎 5鏀跺叆纭 6瀹屾垚鍥炴)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."initiator_user_id" IS '鍙戣捣浜虹敤鎴风紪鐮?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."handler_user_id" IS '澶勭悊浜虹敤鎴风紪鐮?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."task_status" IS '浠诲姟鐘舵€?1澶勭悊涓?2姝ｅ父缁撴潫 3寮傚父缁撴潫)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."task_name" IS '浠诲姟鍚嶇О';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."task_desc" IS '浠诲姟鎻忚堪';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."handle_desc" IS '澶勭悊鎻忚堪';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."initiate_time" IS '鍙戣捣鏃堕棿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."plan_finish_time" IS '璁″垝瀹屾垚鏃堕棿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."actual_finish_time" IS '瀹為檯瀹屾垚鏃堕棿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."create_by" IS '鍒涘缓鑰?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."create_time" IS '鍒涘缓鏃堕棿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."update_by" IS '鏇存柊鑰?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."update_time" IS '鏇存柊鏃堕棿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_project_task"."remark" IS '澶囨敞';
COMMENT ON TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" IS '椤圭洰浠诲姟琛?;

-- ----------------------------
-- Records of by_project_task
-- ----------------------------
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (1, 'PROJ00000001', NULL, 'CUST000001', 'WHALE_BI', '1', 'songyuanqiao', 'xiexun', '2', '宸ヨ鍖椾含BI椤圭洰鍚姩', NULL, NULL, '2025-12-03 00:00:00', '2025-12-06 00:00:00', '2025-12-06 00:00:00', 'admin', '2025-12-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (2, 'PROJ00000001', NULL, 'CUST000001', 'WHALE_BI', '4', 'songyuanqiao', 'xiexun', '2', '宸ヨ鍖椾含BI涓婄嚎楠屾敹', NULL, NULL, '2026-01-06 00:00:00', '2026-01-11 00:00:00', '2026-01-11 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (3, 'PROJ00000001', NULL, 'CUST000001', 'WHALE_BI', '6', 'zhangsanfeng', 'xiexun', '2', '宸ヨ鍖椾含BI鍥炴瀹屾垚', NULL, NULL, '2026-02-11 00:00:00', '2026-02-16 00:00:00', '2026-02-16 00:00:00', 'admin', '2026-02-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (4, 'PROJ00000002', NULL, 'CUST000001', 'WHALE_CRM', '1', 'songyuanqiao', 'weiyixiao', '2', '宸ヨ鍖椾含CRM椤圭洰鍚姩', NULL, NULL, '2026-01-09 00:00:00', '2026-01-13 00:00:00', '2026-01-13 00:00:00', 'admin', '2026-01-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (5, 'PROJ00000002', NULL, 'CUST000001', 'WHALE_CRM', '4', 'songyuanqiao', 'weiyixiao', '2', '宸ヨ鍖椾含CRM涓婄嚎', NULL, NULL, '2026-02-06 00:00:00', '2026-02-13 00:00:00', '2026-02-13 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (6, 'PROJ00000003', NULL, 'CUST000002', 'WHALE_BI', '1', 'yulianzhou', 'yangxiao', '2', '宸ヨ鍖椾含2-BI鍚姩', NULL, NULL, '2025-12-06 00:00:00', '2025-12-11 00:00:00', '2025-12-11 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (7, 'PROJ00000003', NULL, 'CUST000002', 'WHALE_BI', '6', 'zhangsanfeng', 'yangxiao', '2', '宸ヨ鍖椾含2-BI鍥炴', NULL, NULL, '2026-02-06 00:00:00', '2026-02-13 00:00:00', '2026-02-13 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (8, 'PROJ00000004', NULL, 'CUST000004', 'WHALE_BI', '1', 'songyuanqiao', 'fanyao', '2', '鎷涘晢閾惰BI鍚姩', NULL, NULL, '2025-11-04 00:00:00', '2025-11-09 00:00:00', '2025-11-09 00:00:00', 'admin', '2025-11-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (9, 'PROJ00000004', NULL, 'CUST000004', 'WHALE_BI', '5', 'zhangsanfeng', 'fanyao', '2', '鎷涘晢閾惰BI鏀跺叆纭', NULL, NULL, '2026-01-06 00:00:00', '2026-01-11 00:00:00', '2026-01-11 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (10, 'PROJ00000005', NULL, 'CUST000004', 'WHALE_CRM', '1', 'yulianzhou', 'chengkun', '2', '鎷涘晢閾惰CRM鍚姩', NULL, NULL, '2026-01-07 00:00:00', '2026-01-11 00:00:00', '2026-01-11 00:00:00', 'admin', '2026-01-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (11, 'PROJ00000006', NULL, 'CUST000005', 'WHALE_BI', '1', 'songyuanqiao', 'xiexun', '2', '娴﹀彂BI鍚姩', NULL, NULL, '2025-12-09 00:00:00', '2025-12-13 00:00:00', '2025-12-13 00:00:00', 'admin', '2025-12-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (12, 'PROJ00000006', NULL, 'CUST000005', 'WHALE_BI', '4', 'songyuanqiao', 'xiexun', '2', '娴﹀彂BI涓婄嚎', NULL, NULL, '2026-01-03 00:00:00', '2026-01-09 00:00:00', '2026-01-09 00:00:00', 'admin', '2026-01-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (13, 'PROJ00000007', NULL, 'CUST000006', 'WHALE_CRM', '1', 'yulianzhou', 'weiyixiao', '2', '骞垮窞鍗仴CRM鍚姩', NULL, NULL, '2025-12-05 00:00:00', '2025-12-10 00:00:00', '2025-12-10 00:00:00', 'admin', '2025-12-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (14, 'PROJ00000008', NULL, 'CUST000006', 'WHALE_BI', '1', 'songyuanqiao', 'yangxiao', '2', '骞垮窞鍗仴BI鍚姩', NULL, NULL, '2026-01-09 00:00:00', '2026-01-13 00:00:00', '2026-01-13 00:00:00', 'admin', '2026-01-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (15, 'PROJ00000009', NULL, 'CUST000007', 'WHALE_CRM', '1', 'yulianzhou', 'fanyao', '2', '骞夸笢浜烘皯鍖婚櫌CRM鍚姩', NULL, NULL, '2026-01-04 00:00:00', '2026-01-09 00:00:00', '2026-01-09 00:00:00', 'admin', '2026-01-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (16, 'PROJ00000010', NULL, 'CUST000007', 'WHALE_BI', '1', 'songyuanqiao', 'chengkun', '2', '骞夸笢浜烘皯鍖婚櫌BI鍚姩', NULL, NULL, '2026-02-07 00:00:00', '2026-02-13 00:00:00', '2026-02-13 00:00:00', 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (17, 'PROJ00000010', NULL, 'CUST000007', 'WHALE_BI', '4', 'songyuanqiao', 'chengkun', '2', '骞夸笢浜烘皯鍖婚櫌BI涓婄嚎', NULL, NULL, '2026-03-11 00:00:00', '2026-03-17 00:00:00', '2026-03-17 00:00:00', 'admin', '2026-03-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (18, 'PROJ00000011', NULL, 'CUST000008', 'WHALE_BI', '1', 'yulianzhou', 'yintianzheng', '2', '骞冲畨閾惰BI鍚姩', NULL, NULL, '2026-01-06 00:00:00', '2026-01-11 00:00:00', '2026-01-11 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (19, 'PROJ00000011', NULL, 'CUST000008', 'WHALE_BI', '6', 'zhangsanfeng', 'yintianzheng', '2', '骞冲畨閾惰BI鍥炴', NULL, NULL, '2026-02-03 00:00:00', '2026-02-09 00:00:00', '2026-02-09 00:00:00', 'admin', '2026-02-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (20, 'PROJ00000012', NULL, 'CUST000008', 'WHALE_CRM', '1', 'songyuanqiao', 'xiexun', '1', '骞冲畨閾惰CRM鍚姩', NULL, NULL, '2026-02-09 00:00:00', '2026-03-06 00:00:00', NULL, 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (21, 'PROJ00000013', NULL, 'CUST000009', 'WHALE_CRM', '1', 'yulianzhou', 'weiyixiao', '1', '鎴愰兘楂樻柊CRM鍚姩', NULL, NULL, '2026-02-05 00:00:00', '2026-03-03 00:00:00', NULL, 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (22, 'PROJ00000013', NULL, 'CUST000009', 'WHALE_CRM', '3', 'yulianzhou', 'weiyixiao', '1', '鎴愰兘楂樻柊CRM浜や粯', NULL, NULL, '2026-03-06 00:00:00', '2026-04-06 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (23, 'PROJ00000015', NULL, 'CUST000011', 'WHALE_BI', '1', 'songyuanqiao', 'yangxiao', '2', '姝︽眽鍟嗚BI鍚姩', NULL, NULL, '2026-02-07 00:00:00', '2026-02-13 00:00:00', '2026-02-13 00:00:00', 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (24, 'PROJ00000015', NULL, 'CUST000011', 'WHALE_BI', '6', 'zhangsanfeng', 'yangxiao', '2', '姝︽眽鍟嗚BI鍥炴', NULL, NULL, '2026-03-09 00:00:00', '2026-03-15 00:00:00', '2026-03-15 00:00:00', 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (25, 'PROJ00000018', NULL, 'CUST000013', 'WHALE_BI', '1', 'yulianzhou', 'fanyao', '2', '鍗椾含閾惰BI鍚姩', NULL, NULL, '2026-02-06 00:00:00', '2026-02-11 00:00:00', '2026-02-11 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (26, 'PROJ00000018', NULL, 'CUST000013', 'WHALE_BI', '6', 'zhangsanfeng', 'fanyao', '2', '鍗椾含閾惰BI鍥炴', NULL, NULL, '2026-03-06 00:00:00', '2026-03-11 00:00:00', '2026-03-11 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (27, 'PROJ00000020', NULL, 'CUST000014', 'WHALE_CRM', '1', 'songyuanqiao', 'chengkun', '1', '鑻忕渷鏁版嵁CRM鍚姩', NULL, NULL, '2026-03-09 00:00:00', '2026-04-09 00:00:00', NULL, 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (28, 'PROJ00000020', NULL, 'CUST000014', 'WHALE_CRM', '3', 'songyuanqiao', 'chengkun', '1', '鑻忕渷鏁版嵁CRM浜や粯', NULL, NULL, '2026-04-11 00:00:00', '2026-05-22 07:20:09.741738', NULL, 'admin', '2026-04-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (29, 'PROJ00000022', NULL, 'CUST000015', 'WHALE_BI', '1', 'yulianzhou', 'yintianzheng', '2', '娴欏ぇBI鍚姩', NULL, NULL, '2026-03-07 00:00:00', '2026-03-13 00:00:00', '2026-03-13 00:00:00', 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (30, 'PROJ00000022', NULL, 'CUST000015', 'WHALE_BI', '5', 'zhangsanfeng', 'yintianzheng', '2', '娴欏ぇBI鏀跺叆纭', NULL, NULL, '2026-04-09 00:00:00', '2026-04-15 00:00:00', '2026-04-15 00:00:00', 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (31, 'PROJ00000023', NULL, 'CUST000016', 'WHALE_DF', '1', 'songyuanqiao', 'xiexun', '1', '闃块噷宸村反DF鍚姩', NULL, NULL, '2026-02-05 00:00:00', '2026-03-05 00:00:00', NULL, 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (32, 'PROJ00000023', NULL, 'CUST000016', 'WHALE_DF', '3', 'songyuanqiao', 'xiexun', '1', '闃块噷宸村反DF浜や粯', NULL, NULL, '2026-03-07 00:00:00', '2026-04-07 00:00:00', NULL, 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (33, 'PROJ00000025', NULL, 'CUST000017', 'WHALE_BI', '1', 'yulianzhou', 'weiyixiao', '2', '瀹佹尝閾惰BI鍚姩', NULL, NULL, '2026-03-06 00:00:00', '2026-03-11 00:00:00', '2026-03-11 00:00:00', 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (34, 'PROJ00000025', NULL, 'CUST000017', 'WHALE_BI', '5', 'zhangsanfeng', 'weiyixiao', '2', '瀹佹尝閾惰BI鏀跺叆纭', NULL, NULL, '2026-04-07 00:00:00', '2026-04-13 00:00:00', '2026-04-13 00:00:00', 'admin', '2026-04-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (35, 'PROJ00000026', NULL, 'CUST000018', 'WHALE_DF', '1', 'songyuanqiao', 'yangxiao', '1', '鑵捐DF鍚姩', NULL, NULL, '2026-03-09 00:00:00', '2026-04-09 00:00:00', NULL, 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (36, 'PROJ00000031', NULL, 'CUST000021', 'WHALE_BI', '1', 'yulianzhou', 'fanyao', '1', '寤鸿澶╂触BI鍚姩', NULL, NULL, '2026-02-04 00:00:00', '2026-03-04 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (37, 'PROJ00000031', NULL, 'CUST000021', 'WHALE_BI', '3', 'yulianzhou', 'fanyao', '1', '寤鸿澶╂触BI浜や粯', NULL, NULL, '2026-03-05 00:00:00', '2026-04-05 00:00:00', NULL, 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (38, 'PROJ00000033', NULL, 'CUST000024', 'WHALE_BI', '1', 'songyuanqiao', 'chengkun', '1', '鍐滆灞变笢BI鍚姩', NULL, NULL, '2026-02-07 00:00:00', '2026-03-07 00:00:00', NULL, 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (39, 'PROJ00000035', NULL, 'CUST000028', 'WHALE_BI', '1', 'yulianzhou', 'yintianzheng', '1', '閲嶅簡鍐滃晢BI鍚姩', NULL, NULL, '2026-03-05 00:00:00', '2026-04-05 00:00:00', NULL, 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (40, 'PROJ00000038', NULL, 'CUST000031', 'WHALE_BI', '1', 'songyuanqiao', 'xiexun', '1', '鍘﹂棬鍥介檯BI鍚姩', NULL, NULL, '2026-03-08 00:00:00', '2026-04-08 00:00:00', NULL, 'admin', '2026-03-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (41, 'PROJ00000041', NULL, 'CUST000039', 'WHALE_BI', '1', 'yulianzhou', 'weiyixiao', '1', '鍖椾含閾惰BI鍚姩', NULL, NULL, '2026-02-06 00:00:00', '2026-03-06 00:00:00', NULL, 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (42, 'PROJ00000041', NULL, 'CUST000039', 'WHALE_BI', '3', 'yulianzhou', 'weiyixiao', '1', '鍖椾含閾惰BI浜や粯', NULL, NULL, '2026-03-07 00:00:00', '2026-04-07 00:00:00', NULL, 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (43, 'PROJ00000042', NULL, 'CUST000044', 'WHALE_BI', '1', 'songyuanqiao', 'yangxiao', '2', '骞垮窞鍐滃晢BI鍚姩', NULL, NULL, '2026-01-09 00:00:00', '2026-01-13 00:00:00', '2026-01-13 00:00:00', 'admin', '2026-01-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (44, 'PROJ00000042', NULL, 'CUST000044', 'WHALE_BI', '6', 'zhangsanfeng', 'yangxiao', '2', '骞垮窞鍐滃晢BI鍥炴', NULL, NULL, '2026-02-06 00:00:00', '2026-02-11 00:00:00', '2026-02-11 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (45, 'PROJ00000043', NULL, 'CUST000050', 'WHALE_BI', '1', 'yulianzhou', 'fanyao', '1', '闀挎矙閾惰BI鍚姩', NULL, NULL, '2026-02-04 00:00:00', '2026-03-04 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (46, 'PROJ00000043', NULL, 'CUST000050', 'WHALE_BI', '3', 'yulianzhou', 'fanyao', '1', '闀挎矙閾惰BI浜や粯', NULL, NULL, '2026-03-05 00:00:00', '2026-04-05 00:00:00', NULL, 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (47, 'PROJ00000045', NULL, 'CUST000055', 'WHALE_BI', '1', 'songyuanqiao', 'chengkun', '1', '寰藉晢閾惰BI鍚姩', NULL, NULL, '2026-02-07 00:00:00', '2026-03-07 00:00:00', NULL, 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (48, 'PROJ00000055', NULL, 'CUST000081', 'WHALE_BI', '1', 'yulianzhou', 'yintianzheng', '2', '绂忓窞閾惰BI鍚姩', NULL, NULL, '2025-12-04 00:00:00', '2025-12-09 00:00:00', '2025-12-09 00:00:00', 'admin', '2025-12-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (49, 'PROJ00000055', NULL, 'CUST000081', 'WHALE_BI', '6', 'zhangsanfeng', 'yintianzheng', '2', '绂忓窞閾惰BI鍥炴', NULL, NULL, '2026-01-03 00:00:00', '2026-01-09 00:00:00', '2026-01-09 00:00:00', 'admin', '2026-01-03 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (50, 'PROJ00000061', NULL, 'CUST000037', 'WHALE_CRM', '1', 'songyuanqiao', 'xiexun', '2', '娌ぇ鏁版嵁CRM鍚姩', NULL, NULL, '2025-12-06 00:00:00', '2025-12-11 00:00:00', '2025-12-11 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (51, 'PROJ00000061', NULL, 'CUST000037', 'WHALE_CRM', '5', 'zhangsanfeng', 'xiexun', '2', '娌ぇ鏁版嵁CRM鏀跺叆', NULL, NULL, '2026-01-04 00:00:00', '2026-01-09 00:00:00', '2026-01-09 00:00:00', 'admin', '2026-01-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (52, 'PROJ00000062', NULL, 'CUST000040', 'WHALE_BI', '1', 'yulianzhou', 'weiyixiao', '1', '鍖椾含澶ф暟鎹瓸I鍚姩', NULL, NULL, '2026-02-05 00:00:00', '2026-03-05 00:00:00', NULL, 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (53, 'PROJ00000081', NULL, 'CUST000041', 'WHALE_BI', '1', 'songyuanqiao', 'yangxiao', '1', '鍖椾含鍗忓拰BI鍚姩', NULL, NULL, '2026-02-08 00:00:00', '2026-03-08 00:00:00', NULL, 'admin', '2026-02-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (54, 'PROJ00000082', NULL, 'CUST000048', 'WHALE_BI', '1', 'yulianzhou', 'fanyao', '1', '宸濈渷浜烘皯鍖婚櫌BI鍚姩', NULL, NULL, '2026-03-06 00:00:00', '2026-04-06 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (55, 'PROJ00000088', NULL, 'CUST000096', 'WHALE_BI', '1', 'songyuanqiao', 'chengkun', '1', '閯傜渷浜烘皯鍖婚櫌BI鍚姩', NULL, NULL, '2026-02-04 00:00:00', '2026-03-04 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (56, 'PROJ00000090', NULL, 'CUST000036', 'WHALE_CRM', '1', 'yulianzhou', 'yintianzheng', '2', '涓婁氦澶RM鍚姩', NULL, NULL, '2025-12-05 00:00:00', '2025-12-09 00:00:00', '2025-12-09 00:00:00', 'admin', '2025-12-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (57, 'PROJ00000090', NULL, 'CUST000036', 'WHALE_CRM', '5', 'zhangsanfeng', 'yintianzheng', '2', '涓婁氦澶RM鏀跺叆', NULL, NULL, '2026-01-05 00:00:00', '2026-01-11 00:00:00', '2026-01-11 00:00:00', 'admin', '2026-01-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (58, 'PROJ00000096', NULL, 'CUST000043', 'WHALE_MASS', '1', 'songyuanqiao', 'xiexun', '2', '绉诲姩骞夸笢MASS鍚姩', NULL, NULL, '2025-12-07 00:00:00', '2025-12-11 00:00:00', '2025-12-11 00:00:00', 'admin', '2025-12-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (59, 'PROJ00000096', NULL, 'CUST000043', 'WHALE_MASS', '6', 'zhangsanfeng', 'xiexun', '2', '绉诲姩骞夸笢MASS鍥炴', NULL, NULL, '2026-01-05 00:00:00', '2026-01-11 00:00:00', '2026-01-11 00:00:00', 'admin', '2026-01-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (60, 'PROJ00000097', NULL, 'CUST000038', 'WHALE_MASS', '1', 'yulianzhou', 'weiyixiao', '1', '涓浗鐢典俊MASS鍚姩', NULL, NULL, '2026-01-06 00:00:00', '2026-02-06 00:00:00', NULL, 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (61, 'PROJ00000097', NULL, 'CUST000038', 'WHALE_MASS', '3', 'yulianzhou', 'weiyixiao', '1', '涓浗鐢典俊MASS浜や粯', NULL, NULL, '2026-02-07 00:00:00', '2026-03-07 00:00:00', NULL, 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (62, 'PROJ00000106', NULL, 'CUST000013', 'WHALE_CRM', '1', 'songyuanqiao', 'yangxiao', '1', '鍗椾含閾惰CRM鍚姩', NULL, NULL, '2026-02-09 00:00:00', '2026-03-09 00:00:00', NULL, 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_project_task" VALUES (63, 'PROJ00000107', NULL, 'CUST000016', 'WHALE_MASS', '1', 'yulianzhou', 'fanyao', '1', '闃块噷MASS鍚姩', NULL, NULL, '2026-02-04 00:00:00', '2026-03-04 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);

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
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."id" IS '涓婚敭';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."project_code" IS '椤圭洰缂栫爜';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."opp_code" IS '鍟嗘満缂栫爜';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."customer_code" IS '瀹㈡埛缂栫爜';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."product_code" IS '浜у搧缂栫爜';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."task_type" IS '浠诲姟绫诲瀷(1闇€姹傚垎鏋?2浜у搧璁捐 3鍔熻兘寮€鍙?4鐗规€ф祴璇?5鏁呴殰鍒嗘瀽 6鏁呴殰澶勭悊)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."initiator_user_id" IS '鍙戣捣浜虹敤鎴风紪鐮?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."handler_user_id" IS '澶勭悊浜虹敤鎴风紪鐮?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."task_status" IS '浠诲姟鐘舵€?1澶勭悊涓?2姝ｅ父缁撴潫 3寮傚父缁撴潫)';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."task_name" IS '浠诲姟鍚嶇О';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."task_desc" IS '浠诲姟鎻忚堪';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."handle_desc" IS '澶勭悊鎻忚堪';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."initiate_time" IS '鍙戣捣鏃堕棿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."plan_finish_time" IS '璁″垝瀹屾垚鏃堕棿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."actual_finish_time" IS '瀹為檯瀹屾垚鏃堕棿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."create_by" IS '鍒涘缓鑰?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."create_time" IS '鍒涘缓鏃堕棿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."update_by" IS '鏇存柊鑰?;
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."update_time" IS '鏇存柊鏃堕棿';
COMMENT ON COLUMN "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task"."remark" IS '澶囨敞';
COMMENT ON TABLE "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" IS '鐮斿彂浠诲姟琛?;

-- ----------------------------
-- Records of by_rd_task
-- ----------------------------
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (1, 'PROJ00000001', NULL, 'CUST000001', 'WHALE_BI', '1', 'songyuanqiao', 'hongqigong', '2', '宸ヨ鍖椾含BI闇€姹傚垎鏋?, NULL, NULL, '2025-12-04 00:00:00', '2025-12-11 00:00:00', '2025-12-11 00:00:00', 'admin', '2025-12-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (2, 'PROJ00000001', NULL, 'CUST000001', 'WHALE_BI', '2', 'songyuanqiao', 'huangyaoshi', '2', '宸ヨ鍖椾含BI浜у搧璁捐', NULL, NULL, '2025-12-12 00:00:00', '2026-01-21 00:00:00', '2026-01-21 00:00:00', 'admin', '2025-12-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (3, 'PROJ00000001', NULL, 'CUST000001', 'WHALE_BI', '3', 'songyuanqiao', 'ouyangfeng', '2', '宸ヨ鍖椾含BI鍔熻兘寮€鍙?, NULL, NULL, '2026-01-23 00:00:00', '2026-02-21 00:00:00', '2026-02-21 00:00:00', 'admin', '2026-01-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (4, 'PROJ00000001', NULL, 'CUST000001', 'WHALE_BI', '4', 'zhangcuishan', 'duanyu', '2', '宸ヨ鍖椾含BI鐗规€ф祴璇?, NULL, NULL, '2026-02-23 00:00:00', '2026-03-01 00:00:00', '2026-03-01 00:00:00', 'admin', '2026-02-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (5, 'PROJ00000003', NULL, 'CUST000002', 'WHALE_BI', '1', 'songyuanqiao', 'xuzhu', '2', '宸ヨ鍖椾含2-BI闇€姹?, NULL, NULL, '2025-12-06 00:00:00', '2025-12-13 00:00:00', '2025-12-13 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (6, 'PROJ00000003', NULL, 'CUST000002', 'WHALE_BI', '3', 'songyuanqiao', 'zhoubotong', '2', '宸ヨ鍖椾含2-BI寮€鍙?, NULL, NULL, '2026-01-16 00:00:00', '2026-02-16 00:00:00', '2026-02-16 00:00:00', 'admin', '2026-01-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (7, 'PROJ00000004', NULL, 'CUST000004', 'WHALE_BI', '1', 'yulianzhou', 'murongfu', '2', '鎷涘晢閾惰BI闇€姹?, NULL, NULL, '2025-11-05 00:00:00', '2025-11-13 00:00:00', '2025-11-13 00:00:00', 'admin', '2025-11-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (8, 'PROJ00000004', NULL, 'CUST000004', 'WHALE_BI', '2', 'yulianzhou', 'youtanzhi', '2', '鎷涘晢閾惰BI璁捐', NULL, NULL, '2025-11-15 00:00:00', '2025-12-21 00:00:00', '2025-12-21 00:00:00', 'admin', '2025-11-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (9, 'PROJ00000004', NULL, 'CUST000004', 'WHALE_BI', '3', 'yulianzhou', 'yuebuqun', '2', '鎷涘晢閾惰BI寮€鍙?, NULL, NULL, '2025-12-23 00:00:00', '2026-01-23 00:00:00', '2026-01-23 00:00:00', 'admin', '2025-12-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (10, 'PROJ00000004', NULL, 'CUST000004', 'WHALE_BI', '4', 'zhangcuishan', 'fengqingyang', '2', '鎷涘晢閾惰BI娴嬭瘯', NULL, NULL, '2026-01-25 00:00:00', '2026-01-29 00:00:00', '2026-01-29 00:00:00', 'admin', '2026-01-25 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (11, 'PROJ00000006', NULL, 'CUST000005', 'WHALE_BI', '1', 'songyuanqiao', 'saodiseng', '2', '娴﹀彂BI闇€姹?, NULL, NULL, '2025-12-09 00:00:00', '2025-12-15 00:00:00', '2025-12-15 00:00:00', 'admin', '2025-12-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (12, 'PROJ00000006', NULL, 'CUST000005', 'WHALE_BI', '3', 'songyuanqiao', 'hongqigong', '2', '娴﹀彂BI寮€鍙?, NULL, NULL, '2026-01-17 00:00:00', '2026-02-17 00:00:00', '2026-02-17 00:00:00', 'admin', '2026-01-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (13, 'PROJ00000008', NULL, 'CUST000006', 'WHALE_BI', '1', 'yulianzhou', 'huangyaoshi', '2', '骞垮窞鍗仴BI闇€姹?, NULL, NULL, '2026-01-09 00:00:00', '2026-01-15 00:00:00', '2026-01-15 00:00:00', 'admin', '2026-01-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (14, 'PROJ00000008', NULL, 'CUST000006', 'WHALE_BI', '3', 'yulianzhou', 'ouyangfeng', '2', '骞垮窞鍗仴BI寮€鍙?, NULL, NULL, '2026-02-16 00:00:00', '2026-03-16 00:00:00', '2026-03-16 00:00:00', 'admin', '2026-02-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (15, 'PROJ00000010', NULL, 'CUST000007', 'WHALE_BI', '1', 'songyuanqiao', 'duanyu', '2', '骞夸笢浜烘皯鍖婚櫌BI闇€姹?, NULL, NULL, '2026-02-07 00:00:00', '2026-02-13 00:00:00', '2026-02-13 00:00:00', 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (16, 'PROJ00000010', NULL, 'CUST000007', 'WHALE_BI', '3', 'songyuanqiao', 'xuzhu', '2', '骞夸笢浜烘皯鍖婚櫌BI寮€鍙?, NULL, NULL, '2026-03-15 00:00:00', '2026-04-15 00:00:00', '2026-04-15 00:00:00', 'admin', '2026-03-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (17, 'PROJ00000011', NULL, 'CUST000008', 'WHALE_BI', '1', 'yulianzhou', 'zhoubotong', '2', '骞冲畨閾惰BI闇€姹?, NULL, NULL, '2026-01-06 00:00:00', '2026-01-12 00:00:00', '2026-01-12 00:00:00', 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (18, 'PROJ00000011', NULL, 'CUST000008', 'WHALE_BI', '2', 'yulianzhou', 'murongfu', '2', '骞冲畨閾惰BI璁捐', NULL, NULL, '2026-01-13 00:00:00', '2026-02-21 00:00:00', '2026-02-21 00:00:00', 'admin', '2026-01-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (19, 'PROJ00000011', NULL, 'CUST000008', 'WHALE_BI', '3', 'songyuanqiao', 'youtanzhi', '2', '骞冲畨閾惰BI寮€鍙?, NULL, NULL, '2026-02-23 00:00:00', '2026-03-23 00:00:00', '2026-03-23 00:00:00', 'admin', '2026-02-23 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (20, 'PROJ00000011', NULL, 'CUST000008', 'WHALE_BI', '4', 'zhangcuishan', 'yuebuqun', '2', '骞冲畨閾惰BI娴嬭瘯', NULL, NULL, '2026-03-25 00:00:00', '2026-03-29 00:00:00', '2026-03-29 00:00:00', 'admin', '2026-03-25 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (21, 'PROJ00000012', NULL, 'CUST000008', 'WHALE_CRM', '1', 'songyuanqiao', 'fengqingyang', '2', '骞冲畨閾惰CRM闇€姹?, NULL, NULL, '2026-02-09 00:00:00', '2026-02-16 00:00:00', '2026-02-16 00:00:00', 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (22, 'PROJ00000012', NULL, 'CUST000008', 'WHALE_CRM', '2', 'songyuanqiao', 'saodiseng', '1', '骞冲畨閾惰CRM璁捐', NULL, NULL, '2026-03-17 00:00:00', '2026-04-17 00:00:00', NULL, 'admin', '2026-03-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (23, 'PROJ00000013', NULL, 'CUST000009', 'WHALE_CRM', '1', 'yulianzhou', 'hongqigong', '2', '鎴愰兘楂樻柊CRM闇€姹?, NULL, NULL, '2026-02-05 00:00:00', '2026-02-11 00:00:00', '2026-02-11 00:00:00', 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (24, 'PROJ00000013', NULL, 'CUST000009', 'WHALE_CRM', '3', 'yulianzhou', 'huangyaoshi', '1', '鎴愰兘楂樻柊CRM寮€鍙?, NULL, NULL, '2026-03-13 00:00:00', '2026-04-13 00:00:00', NULL, 'admin', '2026-03-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (25, 'PROJ00000015', NULL, 'CUST000011', 'WHALE_BI', '1', 'songyuanqiao', 'ouyangfeng', '2', '姝︽眽鍟嗚BI闇€姹?, NULL, NULL, '2026-02-07 00:00:00', '2026-02-13 00:00:00', '2026-02-13 00:00:00', 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (26, 'PROJ00000015', NULL, 'CUST000011', 'WHALE_BI', '3', 'songyuanqiao', 'duanyu', '2', '姝︽眽鍟嗚BI寮€鍙?, NULL, NULL, '2026-03-15 00:00:00', '2026-04-15 00:00:00', '2026-04-15 00:00:00', 'admin', '2026-03-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (27, 'PROJ00000016', NULL, 'CUST000011', 'WHALE_CRM', '1', 'yulianzhou', 'xuzhu', '1', '姝︽眽鍟嗚CRM闇€姹?, NULL, NULL, '2026-02-04 00:00:00', '2026-03-04 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (28, 'PROJ00000018', NULL, 'CUST000013', 'WHALE_BI', '1', 'songyuanqiao', 'zhoubotong', '2', '鍗椾含閾惰BI闇€姹?, NULL, NULL, '2026-02-06 00:00:00', '2026-02-12 00:00:00', '2026-02-12 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (29, 'PROJ00000018', NULL, 'CUST000013', 'WHALE_BI', '3', 'songyuanqiao', 'murongfu', '2', '鍗椾含閾惰BI寮€鍙?, NULL, NULL, '2026-03-14 00:00:00', '2026-04-14 00:00:00', '2026-04-14 00:00:00', 'admin', '2026-03-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (30, 'PROJ00000020', NULL, 'CUST000014', 'WHALE_CRM', '1', 'yulianzhou', 'youtanzhi', '1', '鑻忕渷鏁版嵁CRM闇€姹?, NULL, NULL, '2026-03-09 00:00:00', '2026-04-09 00:00:00', NULL, 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (31, 'PROJ00000020', NULL, 'CUST000014', 'WHALE_CRM', '3', 'yulianzhou', 'yuebuqun', '1', '鑻忕渷鏁版嵁CRM寮€鍙?, NULL, NULL, '2026-04-11 00:00:00', '2026-05-22 07:20:10.048148', NULL, 'admin', '2026-04-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (32, 'PROJ00000022', NULL, 'CUST000015', 'WHALE_BI', '1', 'songyuanqiao', 'fengqingyang', '2', '娴欏ぇBI闇€姹?, NULL, NULL, '2026-03-07 00:00:00', '2026-03-13 00:00:00', '2026-03-13 00:00:00', 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (33, 'PROJ00000023', NULL, 'CUST000016', 'WHALE_DF', '1', 'yulianzhou', 'saodiseng', '1', '闃块噷DF闇€姹?, NULL, NULL, '2026-02-05 00:00:00', '2026-03-05 00:00:00', NULL, 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (34, 'PROJ00000023', NULL, 'CUST000016', 'WHALE_DF', '2', 'yulianzhou', 'hongqigong', '1', '闃块噷DF璁捐', NULL, NULL, '2026-03-06 00:00:00', '2026-04-06 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (35, 'PROJ00000026', NULL, 'CUST000018', 'WHALE_DF', '1', 'songyuanqiao', 'huangyaoshi', '1', '鑵捐DF闇€姹?, NULL, NULL, '2026-03-09 00:00:00', '2026-04-09 00:00:00', NULL, 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (36, 'PROJ00000031', NULL, 'CUST000021', 'WHALE_BI', '1', 'yulianzhou', 'ouyangfeng', '1', '寤鸿澶╂触BI闇€姹?, NULL, NULL, '2026-02-04 00:00:00', '2026-03-04 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (37, 'PROJ00000033', NULL, 'CUST000024', 'WHALE_BI', '1', 'songyuanqiao', 'duanyu', '1', '鍐滆灞变笢BI闇€姹?, NULL, NULL, '2026-02-07 00:00:00', '2026-03-07 00:00:00', NULL, 'admin', '2026-02-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (38, 'PROJ00000033', NULL, 'CUST000024', 'WHALE_BI', '3', 'songyuanqiao', 'xuzhu', '1', '鍐滆灞变笢BI寮€鍙?, NULL, NULL, '2026-03-09 00:00:00', '2026-04-09 00:00:00', NULL, 'admin', '2026-03-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (39, 'PROJ00000035', NULL, 'CUST000028', 'WHALE_BI', '1', 'yulianzhou', 'zhoubotong', '1', '閲嶅簡鍐滃晢BI闇€姹?, NULL, NULL, '2026-03-05 00:00:00', '2026-04-05 00:00:00', NULL, 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (40, 'PROJ00000038', NULL, 'CUST000031', 'WHALE_BI', '1', 'songyuanqiao', 'murongfu', '1', '鍘﹂棬鍥介檯BI闇€姹?, NULL, NULL, '2026-03-08 00:00:00', '2026-04-08 00:00:00', NULL, 'admin', '2026-03-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (41, 'PROJ00000041', NULL, 'CUST000039', 'WHALE_BI', '1', 'yulianzhou', 'youtanzhi', '1', '鍖椾含閾惰BI闇€姹?, NULL, NULL, '2026-02-06 00:00:00', '2026-03-06 00:00:00', NULL, 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (42, 'PROJ00000041', NULL, 'CUST000039', 'WHALE_BI', '3', 'yulianzhou', 'yuebuqun', '1', '鍖椾含閾惰BI寮€鍙?, NULL, NULL, '2026-03-07 00:00:00', '2026-04-07 00:00:00', NULL, 'admin', '2026-03-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (43, 'PROJ00000042', NULL, 'CUST000044', 'WHALE_BI', '1', 'songyuanqiao', 'fengqingyang', '2', '骞垮窞鍐滃晢BI闇€姹?, NULL, NULL, '2026-01-09 00:00:00', '2026-01-15 00:00:00', '2026-01-15 00:00:00', 'admin', '2026-01-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (44, 'PROJ00000042', NULL, 'CUST000044', 'WHALE_BI', '3', 'songyuanqiao', 'saodiseng', '2', '骞垮窞鍐滃晢BI寮€鍙?, NULL, NULL, '2026-02-17 00:00:00', '2026-03-17 00:00:00', '2026-03-17 00:00:00', 'admin', '2026-02-17 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (45, 'PROJ00000042', NULL, 'CUST000044', 'WHALE_BI', '4', 'zhangcuishan', 'hongqigong', '2', '骞垮窞鍐滃晢BI娴嬭瘯', NULL, NULL, '2026-03-19 00:00:00', '2026-03-25 00:00:00', '2026-03-25 00:00:00', 'admin', '2026-03-19 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (46, 'PROJ00000043', NULL, 'CUST000050', 'WHALE_BI', '1', 'yulianzhou', 'huangyaoshi', '1', '闀挎矙閾惰BI闇€姹?, NULL, NULL, '2026-02-04 00:00:00', '2026-03-04 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (47, 'PROJ00000043', NULL, 'CUST000050', 'WHALE_BI', '3', 'yulianzhou', 'ouyangfeng', '1', '闀挎矙閾惰BI寮€鍙?, NULL, NULL, '2026-03-05 00:00:00', '2026-04-05 00:00:00', NULL, 'admin', '2026-03-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (48, 'PROJ00000055', NULL, 'CUST000081', 'WHALE_BI', '1', 'songyuanqiao', 'duanyu', '2', '绂忓窞閾惰BI闇€姹?, NULL, NULL, '2025-12-04 00:00:00', '2025-12-10 00:00:00', '2025-12-10 00:00:00', 'admin', '2025-12-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (49, 'PROJ00000055', NULL, 'CUST000081', 'WHALE_BI', '3', 'songyuanqiao', 'xuzhu', '2', '绂忓窞閾惰BI寮€鍙?, NULL, NULL, '2026-01-12 00:00:00', '2026-02-12 00:00:00', '2026-02-12 00:00:00', 'admin', '2026-01-12 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (50, 'PROJ00000055', NULL, 'CUST000081', 'WHALE_BI', '4', 'zhangcuishan', 'zhoubotong', '2', '绂忓窞閾惰BI娴嬭瘯', NULL, NULL, '2026-02-14 00:00:00', '2026-02-19 00:00:00', '2026-02-19 00:00:00', 'admin', '2026-02-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (51, 'PROJ00000061', NULL, 'CUST000037', 'WHALE_CRM', '1', 'yulianzhou', 'murongfu', '2', '娌ぇ鏁版嵁CRM闇€姹?, NULL, NULL, '2025-12-06 00:00:00', '2025-12-12 00:00:00', '2025-12-12 00:00:00', 'admin', '2025-12-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (52, 'PROJ00000061', NULL, 'CUST000037', 'WHALE_CRM', '3', 'yulianzhou', 'youtanzhi', '2', '娌ぇ鏁版嵁CRM寮€鍙?, NULL, NULL, '2026-01-14 00:00:00', '2026-02-14 00:00:00', '2026-02-14 00:00:00', 'admin', '2026-01-14 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (53, 'PROJ00000062', NULL, 'CUST000040', 'WHALE_BI', '1', 'songyuanqiao', 'yuebuqun', '1', '鍖椾含澶ф暟鎹瓸I闇€姹?, NULL, NULL, '2026-02-05 00:00:00', '2026-03-05 00:00:00', NULL, 'admin', '2026-02-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (54, 'PROJ00000081', NULL, 'CUST000041', 'WHALE_BI', '1', 'yulianzhou', 'fengqingyang', '1', '鍖椾含鍗忓拰BI闇€姹?, NULL, NULL, '2026-02-08 00:00:00', '2026-03-08 00:00:00', NULL, 'admin', '2026-02-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (55, 'PROJ00000082', NULL, 'CUST000048', 'WHALE_BI', '1', 'songyuanqiao', 'saodiseng', '1', '宸濈渷浜烘皯鍖婚櫌BI闇€姹?, NULL, NULL, '2026-03-06 00:00:00', '2026-04-06 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (56, 'PROJ00000086', NULL, 'CUST000073', 'WHALE_BI', '1', 'yulianzhou', 'hongqigong', '1', '娴欑渷浜烘皯鍖婚櫌BI闇€姹?, NULL, NULL, '2026-03-13 00:00:00', '2026-04-13 00:00:00', NULL, 'admin', '2026-03-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (57, 'PROJ00000088', NULL, 'CUST000096', 'WHALE_BI', '1', 'songyuanqiao', 'huangyaoshi', '1', '閯傜渷浜烘皯鍖婚櫌BI闇€姹?, NULL, NULL, '2026-02-04 00:00:00', '2026-03-04 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (58, 'PROJ00000090', NULL, 'CUST000036', 'WHALE_CRM', '1', 'yulianzhou', 'ouyangfeng', '2', '涓婁氦澶RM闇€姹?, NULL, NULL, '2025-12-05 00:00:00', '2025-12-11 00:00:00', '2025-12-11 00:00:00', 'admin', '2025-12-05 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (59, 'PROJ00000090', NULL, 'CUST000036', 'WHALE_CRM', '3', 'yulianzhou', 'duanyu', '2', '涓婁氦澶RM寮€鍙?, NULL, NULL, '2026-01-13 00:00:00', '2026-02-13 00:00:00', '2026-02-13 00:00:00', 'admin', '2026-01-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (60, 'PROJ00000096', NULL, 'CUST000043', 'WHALE_MASS', '1', 'songyuanqiao', 'xuzhu', '2', '绉诲姩骞夸笢MASS闇€姹?, NULL, NULL, '2025-12-07 00:00:00', '2025-12-13 00:00:00', '2025-12-13 00:00:00', 'admin', '2025-12-07 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (61, 'PROJ00000096', NULL, 'CUST000043', 'WHALE_MASS', '3', 'songyuanqiao', 'zhoubotong', '2', '绉诲姩骞夸笢MASS寮€鍙?, NULL, NULL, '2026-01-15 00:00:00', '2026-02-15 00:00:00', '2026-02-15 00:00:00', 'admin', '2026-01-15 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (62, 'PROJ00000097', NULL, 'CUST000038', 'WHALE_MASS', '1', 'yulianzhou', 'murongfu', '1', '涓浗鐢典俊MASS闇€姹?, NULL, NULL, '2026-01-06 00:00:00', '2026-02-06 00:00:00', NULL, 'admin', '2026-01-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (63, 'PROJ00000097', NULL, 'CUST000038', 'WHALE_MASS', '3', 'yulianzhou', 'youtanzhi', '1', '涓浗鐢典俊MASS寮€鍙?, NULL, NULL, '2026-02-08 00:00:00', '2026-03-08 00:00:00', NULL, 'admin', '2026-02-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (64, 'PROJ00000098', NULL, 'CUST000074', 'WHALE_DF', '1', 'songyuanqiao', 'yuebuqun', '1', '缃戞槗DF闇€姹?, NULL, NULL, '2026-03-06 00:00:00', '2026-04-06 00:00:00', NULL, 'admin', '2026-03-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (65, 'PROJ00000099', NULL, 'CUST000089', 'WHALE_DF', '1', 'yulianzhou', 'fengqingyang', '1', '鍗庤兘闆嗗洟DF闇€姹?, NULL, NULL, '2026-03-08 00:00:00', '2026-04-08 00:00:00', NULL, 'admin', '2026-03-08 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (66, 'PROJ00000106', NULL, 'CUST000013', 'WHALE_CRM', '1', 'songyuanqiao', 'saodiseng', '1', '鍗椾含閾惰CRM闇€姹?, NULL, NULL, '2026-02-09 00:00:00', '2026-03-09 00:00:00', NULL, 'admin', '2026-02-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (67, 'PROJ00000107', NULL, 'CUST000016', 'WHALE_MASS', '1', 'yulianzhou', 'hongqigong', '1', '闃块噷MASS闇€姹?, NULL, NULL, '2026-02-04 00:00:00', '2026-03-04 00:00:00', NULL, 'admin', '2026-02-04 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (68, 'PROJ00000119', NULL, 'CUST000077', 'WHALE_BI', '1', 'songyuanqiao', 'huangyaoshi', '1', '涓骞夸笢BI闇€姹?, NULL, NULL, '2026-03-10 00:00:00', '2026-04-10 00:00:00', NULL, 'admin', '2026-03-10 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (69, 'PROJ00000001', NULL, 'CUST000001', 'WHALE_BI', '5', 'songyuanqiao', 'ouyangfeng', '2', '宸ヨ鍖椾含BI鏁呴殰鍒嗘瀽', NULL, NULL, '2026-01-16 00:00:00', '2026-01-18 00:00:00', '2026-01-18 00:00:00', 'admin', '2026-01-16 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (70, 'PROJ00000001', NULL, 'CUST000001', 'WHALE_BI', '6', 'songyuanqiao', 'ouyangfeng', '2', '宸ヨ鍖椾含BI鏁呴殰澶勭悊', NULL, NULL, '2026-01-18 00:00:00', '2026-01-20 00:00:00', '2026-01-20 00:00:00', 'admin', '2026-01-18 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (71, 'PROJ00000011', NULL, 'CUST000008', 'WHALE_BI', '5', 'yulianzhou', 'duanyu', '2', '骞冲畨閾惰BI鏁呴殰鍒嗘瀽', NULL, NULL, '2026-02-06 00:00:00', '2026-02-08 00:00:00', '2026-02-08 00:00:00', 'admin', '2026-02-06 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (72, 'PROJ00000022', NULL, 'CUST000015', 'WHALE_BI', '5', 'songyuanqiao', 'xuzhu', '2', '娴欏ぇBI鏁呴殰鍒嗘瀽', NULL, NULL, '2026-04-11 00:00:00', '2026-04-13 00:00:00', '2026-04-13 00:00:00', 'admin', '2026-04-11 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (73, 'PROJ00000022', NULL, 'CUST000015', 'WHALE_BI', '6', 'songyuanqiao', 'xuzhu', '2', '娴欏ぇBI鏁呴殰澶勭悊', NULL, NULL, '2026-04-13 00:00:00', '2026-04-15 00:00:00', '2026-04-15 00:00:00', 'admin', '2026-04-13 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (74, 'PROJ00000015', NULL, 'CUST000011', 'WHALE_BI', '5', 'yulianzhou', 'zhoubotong', '2', '姝︽眽鍟嗚BI鏁呴殰鍒嗘瀽', NULL, NULL, '2026-04-09 00:00:00', '2026-04-11 00:00:00', '2026-04-11 00:00:00', 'admin', '2026-04-09 00:00:00', NULL, NULL, NULL);
INSERT INTO "{{DATACLOUD_DB_SCHEMA}}"."by_rd_task" VALUES (75, 'PROJ00000055', NULL, 'CUST000081', 'WHALE_BI', '5', 'songyuanqiao', 'murongfu', '1', '绂忓窞閾惰BI鏁呴殰鍒嗘瀽', NULL, NULL, '2026-04-27 07:20:10.048148', '2026-05-17 07:20:10.048148', NULL, 'admin', '2026-04-27 07:20:10.048148', NULL, NULL, NULL);

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

