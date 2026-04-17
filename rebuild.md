# FastLog 重构需求技术文档

> 本文档旨在提供足够的信息，使开发者能够从零开始重构出一个功能完全等价的 FastLog 系统。

---

## 目录

1. [系统概述](#1-系统概述)
2. [技术栈与依赖](#2-技术栈与依赖)
3. [系统架构设计](#3-系统架构设计)
4. [数据结构设计](#4-数据结构设计)
5. [功能清单（完整）](#5-功能清单完整)
6. [页面布局设计](#6-页面布局设计)
7. [API 接口设计](#7-api-接口设计)
8. [前端状态管理](#8-前端状态管理)
9. [后台任务与调度](#9-后台任务与调度)
10. [部署方案](#10-部署方案)
11. [项目目录结构](#11-项目目录结构)
12. [核心业务逻辑](#12-核心业务逻辑)
13. [安全与约束](#13-安全与约束)

---

## 1. 系统概述

FastLog 是一个**远程日志采集、查看、搜索与分析系统**，用于从远程 Linux 服务器通过 SSH 拉取日志文件，将匹配指定关键字的日志片段存储到本地 SQLite 数据库，并通过 Web UI 提供全文检索、备注标注、多视图管理等功能。

同时集成了 **SqlEye** 子系统，支持连接远程 MySQL/PostgreSQL 数据库执行 SQL 查询、Shell 命令远程执行、字段搜索等运维辅助功能。

### 核心定位

- 面向运维/开发人员的日志查看与分析工具
- 支持多工作区（系统）隔离，不同系统对应不同的服务器/日志目录
- 无用户登录认证，通过工作区 ID 区分数据

---

## 2. 技术栈与依赖

### 前端

| 技术 | 版本 | 用途 |
|------|------|------|
| Vue 3 | ^3.3.4 | 前端框架，使用 Composition API + `<script setup>` |
| Vite | ^5.0.0 | 构建工具与开发服务器 |
| Element Plus | ^2.4.4 | UI 组件库 |
| Pinia | ^2.3.1 | 状态管理 |
| Axios | ^1.6.2 | HTTP 请求客户端 |
| @vitejs/plugin-vue | ^4.5.0 | Vite Vue 插件 |

**无 Vue Router**——整个前端为单页面应用，通过顶部 `el-tabs` 切换不同功能模块。

### 后端

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.11 | 运行环境 |
| Flask | >=2.0.0 | Web 框架 |
| Flask-CORS | >=3.0.0 | 跨域支持 |
| Paramiko | >=2.12.0 | SSH 客户端（连接远程服务器执行命令/读文件） |
| APScheduler | >=3.10.0 | 后台定时任务（SqlEye/Shell 查询轮询） |
| SQLAlchemy | >=2.0.0 | ORM（仅用于 SqlEye 子系统） |
| pymysql | >=1.1.0 | MySQL 驱动 |
| psycopg2-binary | >=2.9.9 | PostgreSQL 驱动 |
| cryptography | >=41.0.0 | 加密支持 |
| Werkzeug | >=2.0.0 | Flask 依赖 |

### 数据库

| 数据库 | 文件 | 用途 |
|--------|------|------|
| SQLite（主库） | `data/logs.db` | 日志数据、配置、文件状态、视图、Shell 查询等 |
| SQLite（SqlEye 库） | `backend/sqleye.db` | SQL 连接会话、查询任务、查询历史、字段搜索任务 |
| SQLite FTS5 | 虚拟表 `logs_fts` | 日志全文搜索 |
| MySQL / PostgreSQL | 远程 | SqlEye 子系统连接的目标数据库（用户配置） |

---

## 3. 系统架构设计

### 整体架构

```
┌──────────────────────────────────────────────────────┐
│                     浏览器 (Browser)                   │
│  ┌────────────────────────────────────────────────┐   │
│  │            Vue 3 SPA (Element Plus)             │   │
│  │  ┌──────┬──────┬──────┬──────┬──────┬────────┐  │   │
│  │  │日志  │配置  │追加  │多搜索│SQL   │Shell   │  │   │
│  │  │列表  │管理  │日志  │配置  │查询  │查询    │  │   │
│  │  ├──────┴──────┴──────┴──────┴──────┴────────┤  │   │
│  │  │           Pinia Store 层                    │  │   │
│  │  ├────────────────────────────────────────────┤  │   │
│  │  │           Axios API 层                      │  │   │
│  │  └────────────────────────────────────────────┘  │   │
│  └──────────────────────┬─────────────────────────┘   │
│                         │ HTTP /api/*                   │
│                         │ Header: X-FastLog-System-Id   │
└─────────────────────────┼──────────────────────────────┘
                          │
┌─────────────────────────┼──────────────────────────────┐
│                   Flask 后端 (:5000)                     │
│  ┌──────────────────────┴─────────────────────────┐    │
│  │              路由层 (app.py + blueprints)        │    │
│  │  ┌─────────────┐  ┌──────────────────────────┐  │    │
│  │  │ FastLog核心  │  │  SqlEye 子系统 (蓝图)     │  │    │
│  │  │ 日志/配置/   │  │  sessions / queries /     │  │    │
│  │  │ 视图/Shell   │  │  field-search             │  │    │
│  │  └──────┬──────┘  └────────┬─────────────────┘  │    │
│  │         │                  │                      │    │
│  │  ┌──────┴──────┐  ┌───────┴──────────────────┐  │    │
│  │  │ database.py │  │ sqleye_models.py          │  │    │
│  │  │ (sqlite3    │  │ sqleye_db.py              │  │    │
│  │  │  直接操作)  │  │ (SQLAlchemy ORM)          │  │    │
│  │  └──────┬──────┘  └───────┬──────────────────┘  │    │
│  │         │                  │                      │    │
│  │    data/logs.db      sqleye.db                    │    │
│  │                                                    │    │
│  │  ┌────────────────────────────────────────────┐   │    │
│  │  │ 后台服务层                                   │   │    │
│  │  │  ├─ SchedulerManager（日志增量更新 10s 循环）│   │    │
│  │  │  ├─ PollingManager（SQL/Shell 查询轮询）    │   │    │
│  │  │  ├─ LogProcessor（SSH 日志采集）            │   │    │
│  │  │  ├─ SSHClient（Paramiko 封装）              │   │    │
│  │  │  └─ ShellQueryService（Shell 命令执行+差异）│   │    │
│  │  └────────────────────────────────────────────┘   │    │
│  │         │                                          │    │
│  │    SSH (Paramiko)                                  │    │
│  └─────────┼──────────────────────────────────────────┘    │
│            │                                               │
└────────────┼───────────────────────────────────────────────┘
             │
    ┌────────┴─────────┐      ┌─────────────────────┐
    │  远程 Linux 服务器 │      │  远程 MySQL/PgSQL    │
    │  (日志文件 + Shell)│      │  (SqlEye 查询目标)    │
    └──────────────────┘      └─────────────────────┘
```

### 关键设计决策

1. **多工作区隔离**：每个 HTTP 请求通过 `X-FastLog-System-Id` 头部传递工作区 ID，后端 `before_request` 中间件解析并存入 `flask.g.system_id`，所有数据操作均按此 ID 过滤。
2. **双数据库**：主库 `data/logs.db` 用原生 `sqlite3` 操作；SqlEye 库 `sqleye.db` 用 SQLAlchemy ORM。
3. **前端无路由**：所有页面通过 `el-tabs` 组织，无 vue-router。
4. **开发模式**：Vite 开发服务器在 3000 端口运行，`/api` 代理到 Flask 5000 端口。
5. **生产模式**：Vite 构建产物放入 `backend/static/`，Flask 同时服务 API 和前端静态文件。

---

## 4. 数据结构设计

### 4.1 主库 `data/logs.db`（sqlite3 直接管理）

#### 表 `systems`（工作区/系统）

```sql
CREATE TABLE systems (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- 默认插入: (1, '默认系统')
```

#### 表 `logs`（日志记录）

```sql
CREATE TABLE logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id    INTEGER NOT NULL DEFAULT 1,
    log_content  TEXT NOT NULL,
    file_path    TEXT NOT NULL,
    line_number  INTEGER NOT NULL,
    search_text  TEXT NOT NULL,
    notes        TEXT,
    printed_at   TEXT,            -- 从日志正文解析的打印时间
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX idx_logs_system_file_line ON logs(system_id, file_path, line_number);
CREATE INDEX idx_logs_created_at ON logs(created_at DESC);
CREATE INDEX idx_logs_file_path ON logs(file_path);
CREATE INDEX idx_logs_printed_at ON logs(printed_at DESC);
CREATE INDEX idx_logs_system_printed_at ON logs(system_id, printed_at DESC);
```

#### 表 `logs_fts`（FTS5 全文搜索虚拟表）

```sql
CREATE VIRTUAL TABLE logs_fts USING fts5(
    log_content,
    file_path,
    content=''
);
-- rowid 与 logs.id 一一对应
```

#### 表 `file_states`（文件读取状态，用于增量更新）

```sql
CREATE TABLE file_states (
    system_id        INTEGER NOT NULL DEFAULT 1,
    file_path        TEXT NOT NULL,
    last_size        INTEGER NOT NULL DEFAULT 0,
    last_position    INTEGER NOT NULL DEFAULT 0,
    last_line_number INTEGER NOT NULL DEFAULT 0,
    last_updated     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (system_id, file_path)
);
```

#### 表 `config`（键值配置）

```sql
CREATE TABLE config (
    system_id  INTEGER NOT NULL,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    PRIMARY KEY (system_id, key)
);
```

默认配置键：

| key | 默认值 | 说明 |
|-----|--------|------|
| `server_host` | 配置文件中的默认IP | SSH 服务器地址 |
| `server_username` | root | SSH 用户名 |
| `server_password` | (密码) | SSH 密码 |
| `server_port` | 22 | SSH 端口 |
| `log_directory` | /data/.../logs/... | 远程日志目录 |
| `search_text` | collect swap... | 搜索关键字 |
| `init_time_range_minutes` | 120 | 初始化时间范围（分钟） |
| `context_lines_before` | 0 | 匹配行前 N 行上下文 |
| `context_lines_after` | 0 | 匹配行后 M 行上下文 |
| `append_search_text` | (空) | 追加日志搜索文本 |
| `append_context_before` | 20 | 追加日志前 N 行 |
| `append_context_after` | 0 | 追加日志后 M 行 |
| `append_time_range_minutes` | 0 | 追加日志时间范围 |
| `append_dedupe_same_content` | 1 | 追加日志时按内容去重 |

#### 表 `search_configs`（多搜索配置）

```sql
CREATE TABLE search_configs (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id                INTEGER NOT NULL DEFAULT 1,
    log_directory            TEXT NOT NULL,
    search_text              TEXT NOT NULL,
    init_time_range_minutes  INTEGER NOT NULL DEFAULT 120,
    context_lines_before     INTEGER NOT NULL DEFAULT 20,
    context_lines_after      INTEGER NOT NULL DEFAULT 0,
    enabled                  INTEGER NOT NULL DEFAULT 1,
    created_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 表 `log_views`（日志视图）

```sql
CREATE TABLE log_views (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id    INTEGER NOT NULL DEFAULT 1,
    name         TEXT NOT NULL,
    search_query TEXT NOT NULL DEFAULT '',
    description  TEXT DEFAULT '',
    sort_order   INTEGER NOT NULL DEFAULT 0,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 表 `log_view_timeline_notes`（时间轴备注）

```sql
CREATE TABLE log_view_timeline_notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    view_id    INTEGER NOT NULL,
    content    TEXT NOT NULL,
    title      TEXT DEFAULT '',
    tags       TEXT DEFAULT '',     -- JSON 字符串，如 ["tag1","tag2"]
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (view_id) REFERENCES log_views(id) ON DELETE CASCADE
);
```

#### 表 `shell_queries`（Shell 查询任务）

```sql
CREATE TABLE shell_queries (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    system_id        INTEGER NOT NULL DEFAULT 1,
    name             TEXT NOT NULL,
    command          TEXT NOT NULL,
    preset_key       TEXT DEFAULT '',
    is_active        INTEGER NOT NULL DEFAULT 0,
    polling_interval INTEGER NOT NULL DEFAULT 60,
    ignore_patterns  TEXT DEFAULT '',
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 表 `shell_query_history`（Shell 查询执行历史）

```sql
CREATE TABLE shell_query_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id        INTEGER NOT NULL,
    executed_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    full_output     TEXT NOT NULL,
    is_different    INTEGER NOT NULL DEFAULT 0,
    diff_lines_json TEXT,           -- JSON 字符串，记录变化行的差异
    FOREIGN KEY (query_id) REFERENCES shell_queries(id) ON DELETE CASCADE
);
```

### 4.2 SqlEye 库 `sqleye.db`（SQLAlchemy ORM）

#### 表 `sessions`（数据库连接配置）

```python
class Session(Base):
    __tablename__ = 'sessions'
    id         = Column(Integer, primary_key=True)
    system_id  = Column(Integer, nullable=False, default=1, unique=True)  # 每个工作区一个会话
    name       = Column(String(100), nullable=False)
    db_type    = Column(String(20), nullable=False)   # 'mysql' 或 'pgsql'
    host       = Column(String(255), nullable=False)
    port       = Column(Integer, nullable=False)
    username   = Column(String(100), nullable=False)
    password   = Column(Text, nullable=False)          # 明文存储
    database   = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
```

#### 表 `query_tasks`（SQL 查询任务）

```python
class QueryTask(Base):
    __tablename__ = 'query_tasks'
    id               = Column(Integer, primary_key=True)
    session_id       = Column(Integer, ForeignKey('sessions.id'), nullable=False)
    name             = Column(String(100), nullable=False)
    sql              = Column(Text, nullable=False)
    polling_interval = Column(Integer, default=2)
    is_active        = Column(Boolean, default=True)
    created_at       = Column(DateTime, default=func.now())
```

#### 表 `query_histories`（SQL 查询历史）

```python
class QueryHistory(Base):
    __tablename__ = 'query_histories'
    id             = Column(Integer, primary_key=True)
    query_task_id  = Column(Integer, ForeignKey('query_tasks.id'), nullable=False)
    session_id     = Column(Integer, ForeignKey('sessions.id'), nullable=False)
    result_data    = Column(JSON, nullable=False)      # 查询结果行数据
    result_hash    = Column(String(64), nullable=False) # 用于差异检测
    executed_at    = Column(DateTime, default=func.now())
    is_different   = Column(Boolean, default=True)
    diff_markers   = Column(JSON)                       # 行/列差异标记
```

#### 表 `field_search_tasks`（字段搜索任务）

```python
class FieldSearchTask(Base):
    __tablename__ = 'field_search_tasks'
    id         = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey('sessions.id'), nullable=False)
    name       = Column(String(100), nullable=False)
    expression = Column(Text, nullable=False)          # 如 "f_id = 1000204"
    created_at = Column(DateTime, default=func.now())
```

---

## 5. 功能清单（完整）

### 5.1 多工作区管理

- [x] 创建新系统（工作区）
- [x] 重命名当前系统
- [x] 删除系统（至少保留一个，删除时级联清除所有关联数据）
- [x] 系统切换（下拉选择，切换后刷新整个页面）
- [x] 当前系统 ID 通过 `localStorage` 持久化，API 请求通过 `X-FastLog-System-Id` 头传递

### 5.2 日志管理

#### 日志视图

- [x] 创建日志视图（名称、搜索条件、备注说明）
- [x] 编辑视图设置（名称、备注说明）
- [x] 删除视图（可关闭 tab）
- [x] 视图 tab 切换时自动刷新日志
- [x] 首次进入无视图时自动创建"默认视图"
- [x] 记住上次激活的视图 ID（通过 `localStorage`）

#### 日志搜索

- [x] 关键字搜索（支持分号 `;` 分隔多个关键字，AND 逻辑）
- [x] FTS5 全文搜索（优先），失败时回退到 LIKE 搜索
- [x] 多关键字 FTS5 INTERSECT 优化
- [x] FTS5 短语匹配（含空格的关键字自动加双引号）
- [x] 搜索条件自动保存到视图配置
- [x] 搜索结果自动滚动到第一个匹配行

#### 日志展示

- [x] 分页展示（支持 10/20/50/100/200/500 条/页）
- [x] 按打印时间降序排列
- [x] 可选显示/隐藏文件路径列
- [x] 可选显示/隐藏打印时间列
- [x] 日志内容 HTML 高亮（搜索词黄色，自定义高亮多色）
- [x] 自定义高亮字符串（分号分隔，8 种颜色循环）
- [x] 高亮字符串持久化到 `localStorage`
- [x] 仅展示有备注数据的过滤选项
- [x] 日志总条数显示
- [x] 日志内容区域最大高度 200px 可滚动

#### 日志备注

- [x] 单条日志编辑备注（对话框）
- [x] 批量编辑备注（覆盖/追加两种模式）
- [x] 批量编辑时可选"仅编辑无备注的日志"
- [x] 日志表格中备注列可点击编辑
- [x] 单条日志删除

#### 时间轴备注

- [x] 每个日志视图拥有独立的时间轴备注列表
- [x] 新增时间轴备注（标题、内容、标签）
- [x] 编辑时间轴备注
- [x] 删除时间轴备注
- [x] 按创建时间倒序展示
- [x] 标签支持（JSON 数组存储）

### 5.3 配置管理

- [x] SSH 服务器配置（地址、账号、密码、端口）
- [x] 远程日志目录配置
- [x] 搜索目标文本配置
- [x] 初始化时间范围配置（分钟，0 表示处理所有文件）
- [x] 上下文行数配置（前 N 行、后 M 行）
- [x] 保存配置
- [x] 测试 SSH 连接
- [x] 重新初始化（异步，带进度条对话框）
- [x] 日志去重（按内容+备注规则）
- [x] 删除所有日志（危险操作，需确认）
- [x] 重新初始化进度展示（文件总数、已处理、匹配数、当前文件、百分比）

### 5.4 追加日志

- [x] 追加日志搜索文本配置
- [x] 追加日志前 N 行 / 后 M 行上下文配置
- [x] 追加日志时间范围配置
- [x] 追加日志内容去重开关
- [x] 保存追加日志配置
- [x] 执行追加日志（异步，带进度查询）

### 5.5 多搜索配置

- [x] 多条搜索配置的 CRUD（日志目录、搜索文本、时间范围、上下文行数、启用/禁用）
- [x] 搜索配置列表（表格展示，带开关）
- [x] 执行所有启用的搜索配置（异步，带进度对话框）
- [x] 创建搜索配置后自动触发一次搜索

### 5.6 SQL 连接配置（SqlEye）

- [x] 配置数据库连接（名称、类型 MySQL/PgSQL、主机、端口、用户名、密码、数据库名）
- [x] 保存连接配置
- [x] 测试连接
- [x] 每个工作区一个 SQL 连接会话

### 5.7 SQL 查询

- [x] 创建查询任务（自动命名，默认 SQL）
- [x] 编辑查询任务（名称、SQL）
- [x] 删除查询任务（确认对话框）
- [x] 手动执行一次查询
- [x] 保存任务配置
- [x] 自动轮询开关 + 轮询间隔（1~3600 秒）
- [x] 查询历史列表（左侧栏，显示执行时间、行数、是否有变化）
- [x] 点击历史记录切换查看不同时间点的结果
- [x] 结果表格展示（动态列）
- [x] 差异高亮（行级：新增行绿色底、修改行黄色底；列级：变化单元格橙色边框）
- [x] 每 10 秒自动刷新开启轮询的查询历史

### 5.8 Shell 查询

- [x] 创建 Shell 查询任务
- [x] 编辑任务（名称、命令、忽略模式）
- [x] 删除任务
- [x] 手动执行一次
- [x] 保存任务配置
- [x] 自动轮询开关 + 轮询间隔
- [x] 历史记录列表（含删除按钮）
- [x] 差异视图 - 变化行视图（三列表格：行号/上一次/本次）
- [x] 差异视图 - 左右对比视图（两栏并列）
- [x] 完整输出文本展示
- [x] 忽略模式（指定关键字的行不参与差异对比）
- [x] 默认预置 Shell 任务（查看进程数、磁盘使用情况、系统错误日志）

### 5.9 字段搜索

- [x] 创建字段搜索任务
- [x] 编辑任务（名称、表达式）
- [x] 删除任务
- [x] Tab 左移/右移排序
- [x] 表达式搜索（如 `f_id = 1000204`）
- [x] 精确匹配结果（在含指定字段名的表中匹配）
- [x] 全库值匹配开关（在所有表的所有字段中匹配值）
- [x] 异步后台值匹配（大库时自动后台执行，前端轮询状态）
- [x] 结果按精确匹配 / 值匹配分组展示
- [x] 折叠面板展示每张表的结果
- [x] 单元格双击 → 创建临时字段搜索视图并自动执行
- [x] 无结果时展示已扫描的表列表
- [x] 保存任务 / 临时任务（仅会话级别）

### 5.10 后台任务监控

- [x] 日志增量更新任务状态（是否运行中、轮询间隔）
- [x] SQL 查询轮询任务列表（ID、名称、间隔、最后执行时间、状态）
- [x] Shell 查询轮询任务列表
- [x] 手动刷新按钮
- [x] 每 10 秒自动刷新

### 5.11 其他小功能

- [x] 健康检查接口 `/api/health`
- [x] 启动时检测后端连通性，失败提示
- [x] Shell 预置命令模板 `/api/shell/presets`
- [x] 日志打印时间自动解析（支持 glog、ISO、紧凑格式）
- [x] 日志 WAL 模式 + busy_timeout 30s（减轻并发锁）
- [x] FTS5 全文索引自动创建和同步
- [x] 日志轮转（按小时，最多 10 个文件，最多保留 3 小时，单文件 50MB）
- [x] 启动时自动清理旧日志文件
- [x] 首次启动自动初始化日志扫描
- [x] PWA 支持（`site.webmanifest` + 多尺寸图标）

---

## 6. 页面布局设计

### 6.1 整体布局

```
┌─────────────────────────────────────────────────────────────────┐
│ [LOGO] 日志查看系统                    [系统选择▾] [⚙设置▾]     │
│                                         ├─新增系统              │
│                                         ├─重命名当前系统         │
│                                         └─删除当前系统           │
├─────────────────────────────────────────────────────────────────┤
│ [日志列表] [配置管理] [追加日志] [多搜索配置] [SQL连接配置]       │
│ [SQL查询] [Shell查询] [字段搜索] [后台任务]                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│                     当前 Tab 内容区域                              │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 日志列表页

```
┌─────────────────────────────────────────────────────────────────┐
│ 日志列表                                         [+ 新建视图]    │
├─────────────────────────────────────────────────────────────────┤
│ [视图A ×] [视图B ×] [视图C ×]                    ← card tabs     │
├─────────────────────────────────────────────────────────────────┤
│ 暂无备注说明（或视图描述）         [时间轴备注] [视图设置]        │
├─────────────────────────────────────────────────────────────────┤
│ ┌─SearchBox────────────────────────────────────────────────┐    │
│ │ [搜索关键词输入框（;分隔）                ] [搜索] [清空]  │    │
│ └──────────────────────────────────────────────────────────┘    │
├─────────────────────────────────────────────────────────────────┤
│ [刷新] [批量编辑备注] [高亮输入框________] [高亮]                │
│ ☑仅展示有备注 ☑展示文件路径 ☑展示打印时间          共 N 条日志  │
├─────────────────────────────────────────────────────────────────┤
│ ☑│ ID │ 文件路径     │ 行号 │ 打印时间   │ 日志内容   │备注│操作│
│──┼────┼──────────────┼──────┼───────────┼───────────┼────┼────│
│ ☐│ 1  │ /data/a.log  │ 42   │ 2026-...  │ xxx...    │ -  │编辑│
│  │    │              │      │           │ (高亮+     │    │删除│
│  │    │              │      │           │  pre滚动)  │    │    │
│──┼────┼──────────────┼──────┼───────────┼───────────┼────┼────│
│ ☐│ 2  │ /data/b.log  │ 100  │ 2026-...  │ yyy...    │备注│编辑│
│  │    │              │      │           │           │内容│删除│
├─────────────────────────────────────────────────────────────────┤
│                    共100条 [10▾] [< 1 2 3 ... >] [跳转__页]     │
└─────────────────────────────────────────────────────────────────┘
```

### 6.3 配置管理页

```
┌─────────────────────────────── max-width: 800px ─┐
│ ┌─ el-card ─────────────────────────────────────┐ │
│ │ 配置管理                                       │ │
│ ├───────────────────────────────────────────────┤ │
│ │ 服务器地址    [________________________]       │ │
│ │ 服务器账号    [________________________]       │ │
│ │ 服务器密码    [________________________]       │ │
│ │ 日志目录      [________________________]       │ │
│ │ 搜索目标文本  [________________________]       │ │
│ │               tip: 配置后增量更新使用新文本     │ │
│ │ 初始化时间范围 [___120___] 分钟                 │ │
│ │               tip: 0=处理所有文件               │ │
│ │ 目标行前N行   [___0_____]                      │ │
│ │ 目标行后M行   [___0_____]                      │ │
│ │                                                │ │
│ │ [保存配置] [测试连接] [重新初始化] [去重]       │ │
│ │ [🔴 删除所有日志]                               │ │
│ ├───────────────────────────────────────────────┤ │
│ │ ⓘ 重新初始化说明:                               │ │
│ │   · 清空所有文件状态记录                        │ │
│ │   · 重新扫描所有日志文件                        │ │
│ │   · 使用当前配置的搜索文本                      │ │
│ │   · 已存储的日志记录不会被删除                  │ │
│ └───────────────────────────────────────────────┘ │
│                                                    │
│ ┌─ Progress Dialog ───── (重新初始化时显示) ─────┐ │
│ │ ████████████████░░░░░ 65%                      │ │
│ │ 处理进度: 13/20 个文件                          │ │
│ │ 当前文件: /data/trade.log                       │ │
│ │ 已找到匹配日志: 156 条                          │ │
│ └────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────┘
```

### 6.4 SQL 查询页

```
┌─────────────────────────────────────────────────────────────────┐
│ ┌─ el-card ───────────────────────────────────────────────────┐ │
│ │ SQL 查询                                   [+ 新建查询任务] │ │
│ ├─────────────────────────────────────────────────────────────┤ │
│ │ [任务A ×] [任务B ×]                          ← card tabs    │ │
│ ├──────────────┬──────────────────────────────────────────────┤ │
│ │ 历史记录      │ 名称    [查询任务 1_________]               │ │
│ │ ┌───────────┐│ SQL     ┌─────────────────────┐             │ │
│ │ │2026-03-26 ││         │ SELECT * FROM users  │             │ │
│ │ │11:00:00   ││         │ WHERE id > 100       │             │ │
│ │ │5行 有变化  ││         └─────────────────────┘             │ │
│ │ ├───────────┤│ [执行一次] [保存任务]                        │ │
│ │ │2026-03-26 ││ ☑自动轮询  时间: [__2__] 秒                 │ │
│ │ │10:58:00   ││                                              │ │
│ │ │5行 无变化  ││ 结果行数：5        执行时间：2026-...        │ │
│ │ └───────────┘│ ┌──────┬───────┬───────┬────────┐          │ │
│ │  260px固定宽度 │ │ id   │ name  │ email │ status │          │ │
│ │              │ ├──────┼───────┼───────┼────────┤          │ │
│ │              │ │ 101  │ Alice │ a@..  │ active │ ← 绿底   │ │
│ │              │ │ 102  │ Bob   │ b@..  │[修改]  │ ← 黄底   │ │
│ │              │ └──────┴───────┴───────┴────────┘          │ │
│ └──────────────┴──────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 6.5 Shell 查询页

```
┌─────────────────────────────────────────────────────────────────┐
│ ┌─ el-card ───────────────────────────────────────────────────┐ │
│ │ Shell 查询                                 [+ 新建查询任务] │ │
│ ├─────────────────────────────────────────────────────────────┤ │
│ │ [任务A ×] [任务B ×]                                         │ │
│ ├──────────────┬──────────────────────────────────────────────┤ │
│ │ 历史记录      │ 名称    [磁盘使用情况______]                │ │
│ │ ┌───────────┐│ 命令    ┌─────────────────────┐             │ │
│ │ │2026-03-26 ││         │ df -h                │             │ │
│ │ │变化行:3   ││         └─────────────────────┘             │ │
│ │ │有变化 [🗑] ││ [执行一次] [保存任务]                        │ │
│ │ ├───────────┤│ ☑自动轮询  时间: [__60__] 秒                │ │
│ │ │10:55:00   ││                                              │ │
│ │ │变化行:0   ││ 含有目标文本的行不参与对比: [________]        │ │
│ │ │无变化 [🗑] ││                                              │ │
│ │ └───────────┘│ 差异视图: ◉变化行视图  ○左右对比视图         │ │
│ │              │ ┌──────┬──────────────┬──────────────┐      │ │
│ │              │ │ 行号 │ 上一次        │ 本次          │      │ │
│ │              │ │ 3    │ /dev 50%     │ /dev 55%      │      │ │
│ │              │ └──────┴──────────────┴──────────────┘      │ │
│ │              │                                              │ │
│ │              │ 完整执行文本                                 │ │
│ │              │ ┌────────────────────────────────────────┐  │ │
│ │              │ │ Filesystem  Size  Used  Avail  Use%    │  │ │
│ │              │ │ /dev/sda1   50G   25G   25G    50%     │  │ │
│ │              │ └────────────────────────────────────────┘  │ │
│ └──────────────┴──────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 6.6 字段搜索页

```
┌─────────────────────────────────────────────────────────────────┐
│ ┌─ el-card ───────────────────────────────────────────────────┐ │
│ │ 字段搜索                           [+ 新建字段搜索任务]     │ │
│ ├─────────────────────────────────────────────────────────────┤ │
│ │ [搜索1 ×] [搜索2 ×]                                        │ │
│ │                                     [左移] [右移] [删除任务]│ │
│ ├─────────────────────────────────────────────────────────────┤ │
│ │ 名称      [字段搜索 1______________]                        │ │
│ │ 表达式    ┌──────────────────────────┐                      │ │
│ │           │ f_id = 1000204           │                      │ │
│ │           └──────────────────────────┘                      │ │
│ │ 全库值匹配  [开关]  关闭后仅在含该字段名的表上做精确匹配    │ │
│ │ [执行搜索] [保存任务]                                       │ │
│ ├─────────────────────────────────────────────────────────────┤ │
│ │ ⓘ 正在后台扫描全库值匹配，完成后将自动刷新结果…             │ │
│ ├─────────────────────────────────────────────────────────────┤ │
│ │ [精确匹配] 字段 f_id 等于 1000204 的记录                    │ │
│ │ ▸ orders (3行)                                              │ │
│ │   ┌──────┬────────┬─────────┐                               │ │
│ │   │ f_id │ name   │ amount  │                               │ │
│ │   │ 1000 │ order1 │ 500.00  │  ← 双击可创建临时搜索        │ │
│ │   └──────┴────────┴─────────┘                               │ │
│ │ ──────────────────────────────                              │ │
│ │ [值匹配] 其他表中任意字段值等于 1000204 的记录              │ │
│ │ ▸ accounts [匹配字段: ref_id] (2行)                         │ │
│ │   ┌────────┬─────────┬────────────┐                         │ │
│ │   │ ref_id │ user_id │ balance    │                         │ │
│ │   └────────┴─────────┴────────────┘                         │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 6.7 后台任务监控页

```
┌─────────────────────────────────────────────────────────────────┐
│ ┌─ el-card ───────────────────────────────────────────────────┐ │
│ │ 后台任务监控                                     [🔄 刷新]  │ │
│ ├─────────────────────────────────────────────────────────────┤ │
│ │ 日志增量更新                                                │ │
│ │ ┌──────────────┬──────────┬──────────────┬──────┐          │ │
│ │ │ 任务类型      │ 状态     │ 轮询间隔(秒) │ 操作 │          │ │
│ │ │ 日志增量更新  │ 🟢运行中 │ 10           │ 系统 │          │ │
│ │ └──────────────┴──────────┴──────────────┴──────┘          │ │
│ │                                                             │ │
│ │ SQL查询轮询任务 (2个任务)                                   │ │
│ │ ┌────┬──────────┬──────────┬──────────────┬──────┐         │ │
│ │ │ ID │ 任务名称  │ 间隔(秒) │ 最后执行时间  │ 状态 │         │ │
│ │ │ 1  │ 查询任务1 │ 2        │ 2026-03-26   │ 🟢  │         │ │
│ │ └────┴──────────┴──────────┴──────────────┴──────┘         │ │
│ │                                                             │ │
│ │ Shell查询轮询任务 (1个任务)                                 │ │
│ │ ┌────┬──────────┬──────────┬──────────────┬──────┐         │ │
│ │ │ ID │ 任务名称  │ 间隔(秒) │ 最后执行时间  │ 状态 │         │ │
│ │ │ 3  │ 磁盘使用  │ 300      │ 2026-03-26   │ 🟢  │         │ │
│ │ └────┴──────────┴──────────┴──────────────┴──────┘         │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. API 接口设计

### 7.1 通用约定

- Base URL: `/api`
- 请求头 `X-FastLog-System-Id`: 当前工作区 ID（必须，默认 1）
- 响应格式: `{ success: boolean, data?: any, message?: string, error?: string }`
- 异步任务返回 `task_id`，通过单独的 progress 接口轮询

### 7.2 日志接口

| 方法 | 路径 | 说明 | 参数 |
|------|------|------|------|
| GET | `/api/logs` | 获取日志列表 | `page`, `page_size`, `search`, `notes_only` |
| DELETE | `/api/logs/<id>` | 删除单条日志 | - |
| DELETE | `/api/logs` | 删除所有日志 | - |
| PUT | `/api/logs/<id>/notes` | 更新单条备注 | `{ notes }` |
| PUT | `/api/logs/notes` | 批量更新备注 | `{ log_ids[], notes }` |
| POST | `/api/logs/append` | 追加日志（异步） | `{ search_text, context_before, context_after, time_range_minutes, dedupe_same_content }` |
| GET | `/api/logs/append/progress/<task_id>` | 追加日志进度 | - |
| POST | `/api/logs/dedupe-by-content` | 按内容去重 | - |

### 7.3 配置接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/config` | 获取所有配置 |
| POST | `/api/config` | 更新配置（部分字段） |
| POST | `/api/reinitialize` | 重新初始化（异步） |
| GET | `/api/reinitialize/progress/<task_id>` | 初始化进度 |
| POST | `/api/test-connection` | 测试 SSH 连接 |

### 7.4 工作区接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/systems` | 列出所有工作区 |
| POST | `/api/systems` | 新建工作区 |
| PUT | `/api/systems/<id>` | 重命名 |
| DELETE | `/api/systems/<id>` | 删除（至少保留一个） |

### 7.5 搜索配置接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/search-configs` | 获取所有搜索配置 |
| GET | `/api/search-configs/<id>` | 获取单个 |
| POST | `/api/search-configs` | 创建 |
| PUT | `/api/search-configs/<id>` | 更新 |
| DELETE | `/api/search-configs/<id>` | 删除 |
| POST | `/api/search-configs/execute` | 执行所有启用配置 |
| GET | `/api/search-configs/execute/progress/<task_id>` | 执行进度 |

### 7.6 日志视图接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/log-views` | 获取所有视图 |
| GET | `/api/log-views/<id>` | 获取单个视图 |
| POST | `/api/log-views` | 创建视图 |
| PUT | `/api/log-views/<id>` | 更新视图 |
| DELETE | `/api/log-views/<id>` | 删除视图 |

### 7.7 时间轴备注接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/log-views/<view_id>/timeline-notes` | 获取视图备注 |
| POST | `/api/log-views/<view_id>/timeline-notes` | 创建备注 |
| PUT | `/api/log-views/timeline-notes/<note_id>` | 更新备注 |
| DELETE | `/api/log-views/timeline-notes/<note_id>` | 删除备注 |

### 7.8 Shell 查询接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/shell/queries` | 获取所有 Shell 任务 |
| POST | `/api/shell/queries` | 创建任务 |
| PUT | `/api/shell/queries/<id>` | 更新任务 |
| DELETE | `/api/shell/queries/<id>` | 删除任务 |
| GET | `/api/shell/queries/<id>/history` | 获取历史 |
| DELETE | `/api/shell/queries/<id>/history/<hid>` | 删除历史 |
| POST | `/api/shell/queries/<id>/execute` | 执行一次 |
| GET | `/api/shell/presets` | 获取预置命令 |

### 7.9 SQL 会话接口（SqlEye）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sql/sessions` | 获取当前工作区会话 |
| POST | `/api/sql/sessions` | 创建/更新会话 |
| POST | `/api/sql/sessions/test` | 测试连接 |

### 7.10 SQL 查询接口（SqlEye）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sql/queries` | 获取所有查询任务 |
| POST | `/api/sql/queries` | 创建查询任务 |
| PUT | `/api/sql/queries/<id>` | 更新 |
| DELETE | `/api/sql/queries/<id>` | 删除 |
| GET | `/api/sql/queries/<id>/history` | 获取历史（最多100条） |
| POST | `/api/sql/queries/<id>/execute` | 执行一次 |

### 7.11 字段搜索接口（SqlEye）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sql/field-search/tasks` | 获取所有任务 |
| POST | `/api/sql/field-search/tasks` | 创建任务 |
| GET | `/api/sql/field-search/tasks/<id>` | 获取单个任务 |
| PUT | `/api/sql/field-search/tasks/<id>` | 更新 |
| DELETE | `/api/sql/field-search/tasks/<id>` | 删除 |
| POST | `/api/sql/field-search/<session_id>` | 执行搜索 |
| GET | `/api/sql/field-search/background/<job_id>` | 后台任务状态 |

### 7.12 其他接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/background-tasks` | 后台任务列表 |

---

## 8. 前端状态管理

### 8.1 Pinia Stores

#### `sessionStore.js` — SQL 连接会话

- `currentSession`: 当前工作区的数据库连接配置
- 操作: `loadSession()`, `saveSession(data)`, `testConnection()`

#### `queryStore.js` — SQL 查询

- `currentQueries`: 当前工作区的查询任务列表
- `queryResults`: 每个任务的 `{ history[], currentHistoryId, data }` 状态
- 操作: `loadQueries()`, `addQuery()`, `editQuery()`, `removeQuery()`, `executeQueryOnce()`, `loadQueryHistory()`, `setCurrentHistory()`

#### `shellQueryStore.js` — Shell 查询

- `currentQueries`: Shell 查询任务列表
- `shellResults`: 每个任务的 `{ history[], currentHistoryId, fullOutput }` 状态
- 操作: `loadQueries()`, `addQuery()`, `editQuery()`, `removeQuery()`, `executeQueryOnce()`, `loadQueryHistory()`, `setCurrentHistory()`, `deleteHistory()`

#### `fieldSearchStore.js` — 字段搜索

- `currentTabs`: 内存级 tab 列表（含持久化任务和临时任务）
- 每个 tab 包含: `id`, `taskId`, `name`, `expression`, `tables`, `debugInfo`, `includeValueMatch`, `valueMatchBackgroundLoading`
- 操作: `openTab()`, `closeTab()`, `updateTabData()`, `updateTabField()`, `moveTabLeft()`, `moveTabRight()`

### 8.2 localStorage 使用

| key | 用途 |
|-----|------|
| `fastlog_current_system_id` | 当前工作区 ID |
| `fastlog_last_active_view_id_${systemId}` | 各工作区最后激活的日志视图 ID |
| `fastlog_highlight_input` | 日志高亮字符串 |

### 8.3 API 层设计

- `api/api.js`: Axios 实例，base URL `/api`，timeout 30s（日志查询放宽到 120s）
  - 请求拦截器: 自动注入 `X-FastLog-System-Id` 头
  - 响应拦截器: 自动提取 `response.data`
- `api/sqlSessions.js`: SQL 会话相关请求
- `api/sqlQueries.js`: SQL 查询相关请求
- `api/shellQueries.js`: Shell 查询相关请求
- `api/sqlFieldSearch.js`: 字段搜索相关请求

---

## 9. 后台任务与调度

### 9.1 SchedulerManager（日志增量更新）

- 独立守护线程，每 10 秒执行一次
- 遍历所有工作区，执行 `LogProcessor.incremental_update()` 和 `incremental_update_with_configs()`
- 使用锁避免重叠执行

### 9.2 PollingManager（SQL/Shell 查询轮询）

- 基于 APScheduler `BackgroundScheduler`
- 为每个激活的 SQL 查询任务和 Shell 查询任务注册定时 interval job
- 任务状态变更（启用/禁用/间隔修改）时动态调整 job
- 应用启动时从数据库恢复所有激活任务

### 9.3 异步任务（线程）

以下操作在后台 `threading.Thread(daemon=True)` 中执行：

- 重新初始化日志 → 通过 `InitProgressManager` 汇报进度
- 追加日志 → 同上
- 多搜索配置执行 → 同上
- 字段搜索异步值匹配 → 内存 job store + 前端轮询

### 9.4 InitProgressManager

- 单例，内存字典存储各 `task_id` 的进度
- 状态: `running` / `completed` / `error`
- 字段: `total_files`, `processed_files`, `total_matches`, `current_file`, `percentage`, `error`

---

## 10. 部署方案

### 10.1 开发环境

```bash
# 后端
cd backend
pip install -r requirements.txt
python app.py
# → 监听 0.0.0.0:5000

# 前端
cd frontend
npm install
npm run dev
# → 监听 localhost:3000，/api 代理到 localhost:5000
```

### 10.2 Vite 开发代理配置

```javascript
// frontend/vite.config.js
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:5000',
        changeOrigin: true,
        timeout: 120000,
        proxyTimeout: 120000
      }
    }
  }
})
```

### 10.3 Docker 部署

#### Dockerfile（多阶段构建）

```dockerfile
# 阶段1: 构建前端
FROM node:18-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# 阶段2: Python 运行环境
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=frontend-builder /app/frontend/dist ./static
RUN mkdir -p /app/data
EXPOSE 5000
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=app.py
CMD ["python", "app.py"]
```

#### docker-compose.yml

```yaml
version: '3.8'
services:
  fastlog:
    build:
      context: .
      dockerfile: docker/Dockerfile
    container_name: fastlog
    ports:
      - "5000:5000"
    volumes:
      - ./data:/app/data        # 持久化数据库
    environment:
      - PYTHONUNBUFFERED=1
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/health').read()"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### 10.4 端口与路径

| 组件 | 端口 | 说明 |
|------|------|------|
| Flask 后端 | 5000 | API + 静态文件（生产） |
| Vite 开发服务器 | 3000 | 仅开发模式 |

### 10.5 数据持久化

- `data/logs.db` — 主数据库，通过 Docker volume 挂载
- `backend/sqleye.db` — SqlEye 数据库，随容器内 backend 目录
- `backend/logs/` — 应用日志（按小时轮转）

### 10.6 环境变量（可选）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SQLEYE_DATA_DIR` | backend 目录 | SqlEye 数据库存放目录 |
| `ENCRYPTION_KEY` | 开发默认值 | Fernet 加密密钥 |
| `FIELD_SEARCH_MAX_WORKERS` | (默认) | 字段搜索并发数 |
| `FIELD_SEARCH_COLUMN_BATCH` | (默认) | 字段搜索列批次 |
| `FIELD_SEARCH_VALUE_MATCH_MAX_TABLES` | (默认) | 值匹配最大表数 |
| `FIELD_SEARCH_VALUE_MATCH_MAX_COLUMNS` | (默认) | 值匹配最大列数 |
| `FIELD_SEARCH_BG_JOB_TTL` | (默认) | 后台任务 TTL |

---

## 11. 项目目录结构

```
FastLog/
├── backend/
│   ├── app.py                          # Flask 主应用，路由 + 启动
│   ├── config.py                       # 全局配置常量
│   ├── database.py                     # 主库 CRUD（sqlite3）
│   ├── log_processor.py                # SSH 日志采集、初始化、增量更新
│   ├── scheduler.py                    # 日志增量更新定时器
│   ├── ssh_client.py                   # Paramiko SSH 封装
│   ├── shell_query_service.py          # Shell 命令执行 + diff
│   ├── init_progress.py                # 异步任务进度管理器
│   ├── sqleye_config.py                # SqlEye 配置
│   ├── sqleye_db.py                    # SqlEye SQLAlchemy 会话工厂
│   ├── sqleye_models.py                # SqlEye ORM 模型
│   ├── sqleye_workspace.py             # SqlEye 工作区绑定
│   ├── sqleye_routes_sessions.py       # SqlEye 会话蓝图
│   ├── sqleye_routes_queries.py        # SqlEye 查询蓝图
│   ├── sqleye_routes_field_search.py   # SqlEye 字段搜索蓝图
│   ├── sqleye_services/
│   │   ├── db_connector.py             # MySQL/PgSQL 连接池
│   │   ├── query_executor.py           # SQL 执行器
│   │   ├── diff_detector.py            # 查询结果差异检测
│   │   └── polling_manager.py          # APScheduler 轮询管理
│   ├── migrate_fts.py                  # FTS5 迁移脚本
│   ├── rebuild_fts5.py                 # FTS5 重建脚本
│   ├── requirements.txt
│   └── connection_logs/
│       └── connection_info.json
├── frontend/
│   ├── public/                         # 静态资源（图标、manifest）
│   ├── src/
│   │   ├── App.vue                     # 根组件（头部 + tabs）
│   │   ├── main.js                     # 入口（Vue + Pinia + ElementPlus）
│   │   ├── api/
│   │   │   ├── api.js                  # Axios 实例 + 核心 API
│   │   │   ├── sqlSessions.js
│   │   │   ├── sqlQueries.js
│   │   │   ├── shellQueries.js
│   │   │   └── sqlFieldSearch.js
│   │   ├── components/
│   │   │   ├── LogViewPane.vue         # 搜索+日志列表容器
│   │   │   ├── LogList.vue             # 日志表格+分页+高亮+备注
│   │   │   ├── SearchBox.vue           # 搜索输入框
│   │   │   ├── ConfigPanel.vue         # 配置管理面板
│   │   │   ├── AppendLogPanel.vue      # 追加日志面板
│   │   │   ├── SearchConfigPanel.vue   # 多搜索配置面板
│   │   │   ├── SqlConnectionConfigPanel.vue
│   │   │   ├── SqlQueryPanel.vue       # SQL 查询面板
│   │   │   ├── ShellQueryPanel.vue     # Shell 查询面板
│   │   │   ├── SqlFieldSearchPanel.vue # 字段搜索面板
│   │   │   ├── BackgroundTasksPanel.vue
│   │   │   └── TimelineNotesDialog.vue # 时间轴备注对话框
│   │   └── stores/
│   │       ├── sessionStore.js
│   │       ├── queryStore.js
│   │       ├── shellQueryStore.js
│   │       └── fieldSearchStore.js
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── docker-compose.dist.yml
├── data/                               # 运行时创建，存放 logs.db
├── test/                               # 测试（unit/integration/e2e）
├── fuzz_test/                          # API 模糊测试
├── tools/                              # 打包、图标生成等工具
├── start.bat                           # Windows 快速启动
├── stop.bat
├── restart.bat
├── install.bat
└── README.md
```

---

## 12. 核心业务逻辑

### 12.1 日志采集流程

1. 通过 SSH 连接远程服务器
2. 列出指定目录下的日志文件，按修改时间过滤（时间范围内的文件）
3. 对每个文件，从 `file_states` 表获取上次读取位置
4. 从上次位置开始读取新内容
5. 使用 `grep` 或逐行匹配搜索关键字
6. 匹配行及其上下文（前 N 行、后 M 行）合并为一条日志记录
7. 插入 `logs` 表（基于 `system_id + file_path + line_number` 去重）
8. 同步插入 `logs_fts` FTS5 索引
9. 更新 `file_states` 记录读取位置
10. 从日志内容解析 `printed_at`（支持 glog、ISO、紧凑时间格式）

### 12.2 日志搜索逻辑

1. 将搜索查询按 `;` 分割为多个关键字段
2. 每个段如果含空格，包裹为 FTS5 短语（双引号）
3. 多段使用 INTERSECT 优化（各段分别 MATCH 取 rowid 交集）
4. FTS5 失败时回退到 LIKE `%keyword%` AND 查询
5. 搜索计数上限 100,000 条（避免大数据量 COUNT 过慢）
6. 按 `printed_at DESC` 排序

### 12.3 日志去重规则

按 `log_content` 分组：
1. 相同内容、相同备注 → 只保留一条
2. 相同内容、不同备注 → 全部保留
3. 如果内容组有备注记录，删除该组所有无备注记录
4. 如果内容组全无备注，只保留一条

### 12.4 Shell 查询差异检测

1. 通过 SSH 执行 Shell 命令，获取完整输出
2. 与上一次执行结果逐行对比
3. 根据 `ignore_patterns`（分号分隔），忽略含指定文本的行
4. 生成 `diff_lines_json`：每个差异行记录 `{ line_no, prev, curr }`
5. 标记 `is_different`

### 12.5 SQL 查询差异检测

1. 通过 `db_connector` 连接远程 MySQL/PostgreSQL
2. 执行 SQL，获取结果行
3. 对结果计算 hash（`result_hash`）
4. 与上次 hash 比较，相同则 `is_different = false`
5. 不同时生成 `diff_markers`：标记 `added_rows`、`different_rows`（含 `different_columns`）

### 12.6 字段搜索逻辑

1. 解析表达式（如 `f_id = 1000204`）得到字段名和值
2. 查询 `information_schema`，找到包含该字段名的所有表
3. 在这些表上执行 `SELECT * FROM table WHERE field = value`
4. 如开启全库值匹配，还需在所有表的所有字段上搜索该值
5. 大库时值匹配可异步执行（后台线程 + 轮询状态）

---

## 13. 安全与约束

### 当前设计

- **无用户认证**：任何可访问 5000 端口的人可操作任意工作区
- **密码明文存储**：SSH 密码和数据库密码存储在 SQLite 中
- **CORS 全开放**：`CORS(app)` 无限制
- **无 HTTPS**：默认 HTTP
- **SQLite 并发**：WAL 模式 + 30s busy_timeout 缓解，但高并发写入仍有限制

### 重构建议

- 添加用户认证（JWT/Session）
- 密码加密存储（已有 Fernet 基础设施但未全面使用）
- 限制 CORS 来源
- 生产环境使用 Gunicorn + Nginx 替代 Flask dev server
- 考虑 PostgreSQL 替代 SQLite 应对更大规模数据

---

## 附录 A: 日志打印时间解析规则

支持以下格式（按优先级）：

1. **glog 风格**: `W20260306 11:00:01.249769` 或 `[W20260306 11:00:01.249769`
2. **紧凑日期**: `20260306 11:00:01.249769` 或 `[20260306 11:00:01.249769`
3. **ISO 格式**: `2026-03-06 11:00:01.249769` 或 `2026-03-06T11:00:01.249769`

解析失败时回退到 `created_at`（插入时间）。

## 附录 B: 前端高亮颜色方案

| 索引 | 背景色 | 用途 |
|------|--------|------|
| 0 | #FFEB3B（黄色） | 第1个高亮词 |
| 1 | #81D4FA（浅蓝） | 第2个 |
| 2 | #A5D6A7（浅绿） | 第3个 |
| 3 | #F8BBD0（浅粉） | 第4个 |
| 4 | #FFCC80（浅橙） | 第5个 |
| 5 | #CE93D8（浅紫） | 第6个 |
| 6 | #90CAF9（蓝色） | 第7个 |
| 7 | #C5E1A5（绿色） | 第8个（之后循环） |

搜索词高亮始终使用黄色底黑字。

## 附录 C: 默认 Shell 预置任务

| 名称 | 命令 | 轮询间隔 |
|------|------|----------|
| 查看进程数 | `ps aux \| wc -l` | 60s |
| 磁盘使用情况 | `df -h` | 300s |
| 最近系统错误日志 | `tail -n 100 /var/log/syslog \| grep -i error \|\| echo 'no syslog or errors found'` | 120s |

## 附录 D: Windows 启动脚本说明

| 脚本 | 用途 |
|------|------|
| `install.bat` | 安装 Python 依赖 + npm 依赖 |
| `start.bat` | 启动后端 + 前端开发服务器 |
| `stop.bat` | 停止服务 |
| `restart.bat` | 重启 |
| `prepare_env.bat` | 准备运行环境 |
| `build_docker.bat` | 构建 Docker 镜像并导出 tar |
