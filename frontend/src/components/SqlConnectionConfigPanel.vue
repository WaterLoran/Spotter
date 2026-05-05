<template>
  <el-card
    :shadow="embedded ? 'never' : 'always'"
    :class="{ 'sql-connection-panel--embedded': embedded }"
  >
    <template v-if="!embedded" #header>SQL连接配置</template>
    <div class="sql-connection-panel-toolbar">
      <el-button type="primary" plain size="small" @click="startNewConnection">新建连接</el-button>
      <el-button size="small" :loading="loading" @click="reload">刷新列表</el-button>
    </div>
    <el-tabs v-model="activeTab" type="card" class="sql-connection-tabs" @tab-change="onTabChange">
      <el-tab-pane
        v-for="s in displayTabs"
        :key="s.tabKey"
        :name="s.tabKey"
        :label="s.label"
      />
    </el-tabs>
    <div v-if="loading" v-loading="true" class="sql-connection-loading" element-loading-text="加载中…" />
    <template v-else>
      <el-empty
        v-if="!displayTabs.length && !creating"
        description="暂无连接，请点击「新建连接」"
        :image-size="72"
      />
      <template v-else-if="form">
      <el-form label-width="100px" class="sql-connection-form">
        <el-form-item label="名称"><el-input v-model="form.name" placeholder="连接显示名称" /></el-form-item>
        <el-form-item label="Host"><el-input v-model="form.host" /></el-form-item>
        <el-form-item label="端口"><el-input-number v-model="form.port" :min="1" /></el-form-item>
        <el-form-item label="用户名"><el-input v-model="form.username" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password /></el-form-item>
        <el-form-item label="数据库">
          <el-input v-model="form.database" />
          <div v-if="lockedDbType === 'oracle'" class="sql-connection-hint">
            Oracle 请填写 Service Name（DSN: host:port/service_name）
          </div>
        </el-form-item>
      </el-form>
      <div class="sql-connection-panel-actions">
        <el-button type="primary" :loading="saving" @click="save">保存连接</el-button>
        <el-button :loading="testing" @click="test">测试连接</el-button>
        <el-button type="danger" plain :disabled="!form?.id" @click="remove">删除连接</el-button>
      </div>
      </template>
    </template>
  </el-card>
</template>

<script setup>
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onMounted, reactive, ref, watch } from "vue";
import {
  createSqlSession,
  deleteSqlSession,
  listSqlSessions,
  normalizeSqlSessionsData,
  testSqlSession,
  updateSqlSession
} from "../api/sqlSessions";

const props = defineProps({
  embedded: { type: Boolean, default: false },
  /** 齿轮菜单打开时锁定：mysql | pgsql | oracle */
  dbType: { type: String, default: "mysql" }
});

const loading = ref(true);
const saving = ref(false);
const testing = ref(false);
const sessions = ref([]);
const activeTab = ref("");
const creating = ref(false);

const lockedDbType = computed(() => {
  if (props.dbType === "pgsql") return "pgsql";
  if (props.dbType === "oracle") return "oracle";
  return "mysql";
});

function defaultPort() {
  if (lockedDbType.value === "pgsql") return 5432;
  if (lockedDbType.value === "oracle") return 1521;
  return 3306;
}

function defaultUsername() {
  if (lockedDbType.value === "pgsql") return "postgres";
  if (lockedDbType.value === "oracle") return "system";
  return "root";
}

function blankForm(overrides = {}) {
  return reactive({
    id: null,
    name:
      lockedDbType.value === "pgsql"
        ? "新 Pgsql 连接"
        : lockedDbType.value === "oracle"
          ? "新 Oracle 连接"
          : "新 Mysql 连接",
    db_type: lockedDbType.value,
    host: "127.0.0.1",
    port: defaultPort(),
    username: defaultUsername(),
    password: "",
    database: "",
    ...overrides
  });
}

const form = ref(null);

const displayTabs = computed(() => {
  const list = sessions.value.map((s) => ({
    tabKey: `id:${s.id}`,
    label: s.name || `连接 #${s.id}`,
    session: s
  }));
  if (creating.value) {
    list.push({ tabKey: "new", label: "未保存·新建", session: null });
  }
  return list;
});

function syncFormFromSession(s) {
  if (!s) {
    form.value = blankForm();
    return;
  }
  form.value = reactive({
    id: s.id,
    name: s.name,
    db_type: s.db_type,
    host: s.host,
    port: s.port,
    username: s.username,
    password: s.password,
    database: s.database
  });
}

async function reload() {
  loading.value = true;
  try {
    const res = await listSqlSessions(lockedDbType.value);
    const normalized = normalizeSqlSessionsData(res?.data);
    if (res && res.success === false) {
      ElMessage.error(res.error || res.message || "加载连接列表失败");
      return;
    }
    sessions.value = normalized;
    if (!sessions.value.length) {
      creating.value = true;
      activeTab.value = "new";
      syncFormFromSession(null);
      return;
    }
    // 正在「未保存·新建」页刷新列表时：只同步服务端列表，不要清空用户已填的草稿
    if (creating.value && activeTab.value === "new") {
      return;
    }
    const keys = new Set(sessions.value.map((s) => `id:${s.id}`));
    if (!keys.has(activeTab.value)) {
      activeTab.value = `id:${sessions.value[0].id}`;
    }
    const sid = Number(String(activeTab.value).replace(/^id:/, ""));
    const s = sessions.value.find((x) => x.id === sid);
    if (s) syncFormFromSession(s);
  } finally {
    loading.value = false;
  }
}

function onTabChange(name) {
  if (name === "new") {
    syncFormFromSession(null);
    return;
  }
  const sid = Number(String(name).replace(/^id:/, ""));
  const s = sessions.value.find((x) => x.id === sid);
  if (s) syncFormFromSession(s);
}

function startNewConnection() {
  creating.value = true;
  activeTab.value = "new";
  syncFormFromSession(null);
}

watch(
  () => props.dbType,
  () => {
    creating.value = false;
    activeTab.value = "";
    reload();
  }
);

onMounted(() => {
  reload();
});

async function save() {
  if (!form.value) return;
  const f = form.value;
  const name = String(f.name || "").trim();
  if (!name) {
    ElMessage.warning("请输入连接名称");
    return;
  }
  const database = String(f.database || "").trim();
  if (!database) {
    ElMessage.warning("请输入数据库名");
    return;
  }
  saving.value = true;
  try {
    const payload = {
      name,
      db_type: lockedDbType.value,
      host: String(f.host || "").trim() || "127.0.0.1",
      port: f.port,
      username: String(f.username || "").trim(),
      password: f.password ?? "",
      database
    };
    if (f.id) {
      const res = await updateSqlSession(f.id, payload);
      if (res && res.success === false) {
        ElMessage.error(res.error || res.message || "保存失败");
        return;
      }
      const row = res?.data;
      if (row && typeof row === "object") {
        Object.assign(f, row);
      }
      ElMessage.success("已保存");
    } else {
      const res = await createSqlSession(payload);
      if (res && res.success === false) {
        ElMessage.error(res.error || res.message || "保存失败");
        return;
      }
      const row = res?.data;
      if (!row?.id) {
        ElMessage.error("保存失败：服务端未返回连接信息");
        return;
      }
      // 先挂上列表与 Tab，再结束「新建」态，避免一瞬间 displayTabs 为空把表单挤掉
      sessions.value = [...sessions.value, row].sort((a, b) => (a.id ?? 0) - (b.id ?? 0));
      Object.assign(f, row);
      activeTab.value = `id:${row.id}`;
      creating.value = false;
      ElMessage.success("已创建连接");
    }
    await reload();
    if (f.id) {
      activeTab.value = `id:${f.id}`;
      const s = sessions.value.find((x) => x.id === f.id);
      if (s) syncFormFromSession(s);
    }
  } catch (e) {
    ElMessage.error(e?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function test() {
  if (!form.value) return;
  const f = form.value;
  testing.value = true;
  try {
    const res = await testSqlSession({
      db_type: lockedDbType.value,
      host: String(f.host || "").trim() || "127.0.0.1",
      port: f.port,
      username: String(f.username || "").trim(),
      password: f.password ?? "",
      database: String(f.database || "").trim()
    });
    if (res.success) ElMessage.success("连接成功");
    else ElMessage.error(res.error || "连接失败");
  } catch (e) {
    ElMessage.error(e?.message || "请求失败");
  } finally {
    testing.value = false;
  }
}

async function remove() {
  if (!form.value?.id) return;
  try {
    await ElMessageBox.confirm("确定删除该连接？若仍有任务引用将无法删除。", "删除连接", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消"
    });
  } catch {
    return;
  }
  try {
    await deleteSqlSession(form.value.id);
    ElMessage.success("已删除");
    creating.value = false;
    await reload();
  } catch (e) {
    ElMessage.error(e?.message || "删除失败");
  }
}
</script>

<style scoped>
.sql-connection-panel-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.sql-connection-tabs {
  margin-bottom: 12px;
}
.sql-connection-form {
  max-width: 520px;
}
.sql-connection-panel-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.sql-connection-panel--embedded {
  border: none;
  box-shadow: none;
}
.sql-connection-panel--embedded :deep(.el-card__body) {
  padding: 0;
}
.sql-connection-loading {
  min-height: 160px;
}
.sql-connection-hint {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.4;
}
</style>
