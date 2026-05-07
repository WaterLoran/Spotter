<template>
  <el-card
    :shadow="embedded ? 'never' : 'always'"
    :class="{ 'redis-connection-panel--embedded': embedded }"
  >
    <template v-if="!embedded" #header>Redis 连接配置</template>
    <div class="redis-connection-panel-toolbar">
      <el-button type="primary" plain size="small" @click="startNewConnection">新建连接</el-button>
      <el-button size="small" :loading="loading" @click="reload">刷新列表</el-button>
    </div>
    <el-tabs v-model="activeTab" type="card" class="redis-connection-tabs" @tab-change="onTabChange">
      <el-tab-pane v-for="s in displayTabs" :key="s.tabKey" :name="s.tabKey" :label="s.label" />
    </el-tabs>
    <div v-if="loading" v-loading="true" class="redis-connection-loading" element-loading-text="加载中…" />
    <template v-else>
      <el-empty
        v-if="!displayTabs.length && !creating"
        description="暂无连接，请点击「新建连接」"
        :image-size="72"
      />
      <template v-else-if="form">
        <el-form label-width="108px" class="redis-connection-form">
          <el-form-item label="名称"><el-input v-model="form.name" placeholder="连接显示名称" /></el-form-item>
          <el-form-item label="Host"><el-input v-model="form.host" /></el-form-item>
          <el-form-item label="端口"><el-input-number v-model="form.port" :min="1" :max="65535" /></el-form-item>
          <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password /></el-form-item>
          <el-form-item label="DB 序号"><el-input-number v-model="form.db_index" :min="0" :max="255" /></el-form-item>
          <el-form-item label="SSL">
            <el-checkbox v-model="form.use_ssl">使用 TLS 连接</el-checkbox>
          </el-form-item>
        </el-form>
        <div class="redis-connection-panel-actions">
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
import { computed, onMounted, reactive, ref } from "vue";
import {
  createRedisSession,
  deleteRedisSession,
  listRedisSessions,
  testRedisSession,
  updateRedisSession
} from "../api/redisQuery";

const props = defineProps({
  embedded: { type: Boolean, default: false }
});

const loading = ref(true);
const saving = ref(false);
const testing = ref(false);
const sessions = ref([]);
const activeTab = ref("");
const creating = ref(false);

function blankForm(overrides = {}) {
  return reactive({
    id: null,
    name: "新 Redis 连接",
    host: "127.0.0.1",
    port: 6379,
    password: "",
    db_index: 0,
    use_ssl: false,
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
    host: s.host,
    port: s.port,
    password: s.password ?? "",
    db_index: s.db_index ?? 0,
    use_ssl: Boolean(s.use_ssl)
  });
}

async function reload() {
  loading.value = true;
  try {
    const res = await listRedisSessions();
    if (res && res.success === false) {
      ElMessage.error(res.error || res.message || "加载连接列表失败");
      return;
    }
    sessions.value = res?.data || [];
    if (!sessions.value.length) {
      creating.value = true;
      activeTab.value = "new";
      syncFormFromSession(null);
      return;
    }
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
  saving.value = true;
  try {
    const payload = {
      name,
      host: String(f.host || "").trim() || "127.0.0.1",
      port: f.port,
      password: f.password ?? "",
      db_index: f.db_index ?? 0,
      use_ssl: Boolean(f.use_ssl)
    };
    if (f.id) {
      const res = await updateRedisSession(f.id, payload);
      if (res && res.success === false) {
        ElMessage.error(res.error || res.message || "保存失败");
        return;
      }
      ElMessage.success("已保存");
    } else {
      const res = await createRedisSession(payload);
      if (res && res.success === false) {
        ElMessage.error(res.error || res.message || "保存失败");
        return;
      }
      const row = res?.data;
      if (!row?.id) {
        ElMessage.error("保存失败：服务端未返回连接信息");
        return;
      }
      sessions.value = [...sessions.value, { id: row.id, ...payload }].sort((a, b) => (a.id ?? 0) - (b.id ?? 0));
      Object.assign(f, { id: row.id });
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
    const res = await testRedisSession({
      host: String(f.host || "").trim() || "127.0.0.1",
      port: f.port,
      password: f.password ?? "",
      db_index: f.db_index ?? 0,
      use_ssl: Boolean(f.use_ssl)
    });
    if (res.success) {
      const d = res.data || {};
      if (d.notify_keyspace_events_ok) {
        ElMessage.success("连接成功，键空间通知已启用");
      } else {
        ElMessage.warning(
          `连接成功，但 ${d.notify_keyspace_events_detail || "notify-keyspace-events 未正确配置"}；请在 Redis 执行 CONFIG SET notify-keyspace-events KEA`
        );
      }
    } else {
      ElMessage.error(res.error || "连接失败");
    }
  } catch (e) {
    ElMessage.error(e?.message || "请求失败");
  } finally {
    testing.value = false;
  }
}

async function remove() {
  if (!form.value?.id) return;
  try {
    await ElMessageBox.confirm("确定删除该连接？关联的查询任务将一并删除。", "删除连接", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消"
    });
  } catch {
    return;
  }
  try {
    await deleteRedisSession(form.value.id);
    ElMessage.success("已删除");
    creating.value = false;
    await reload();
  } catch (e) {
    ElMessage.error(e?.message || "删除失败");
  }
}
</script>

<style scoped>
.redis-connection-panel-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.redis-connection-tabs {
  margin-bottom: 12px;
}
.redis-connection-form {
  max-width: 520px;
}
.redis-connection-panel-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.redis-connection-panel--embedded {
  border: none;
  box-shadow: none;
}
.redis-connection-panel--embedded :deep(.el-card__body) {
  padding: 0;
}
.redis-connection-loading {
  min-height: 160px;
}
</style>
