<template>
  <el-card class="sql-query-card">
    <template #header>
      <div class="sql-query-card-header">
        <span class="sql-query-title">SQL 查询</span>
        <el-dropdown trigger="click" @command="onMenuCommand">
          <el-button type="primary" plain size="small" circle title="操作">
            <el-icon :size="18"><MenuIcon /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="add">新建查询任务</el-dropdown-item>
              <el-dropdown-item command="refresh" divided>刷新任务列表</el-dropdown-item>
              <el-dropdown-item command="edit" :disabled="!current">编辑任务</el-dropdown-item>
              <el-dropdown-item command="save" :disabled="!current">保存当前任务</el-dropdown-item>
              <el-dropdown-item command="delete" :disabled="!current">删除当前任务</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </template>
    <el-tabs v-model="activeId" type="card" @tab-change="onTabChange">
      <el-tab-pane v-for="q in store.currentQueries" :key="q.id" :name="String(q.id)" :label="q.name" />
    </el-tabs>
    <el-empty v-if="!store.currentQueries.length" description="暂无查询任务，请点击右上角菜单图标新建" />
    <template v-else-if="current">
      <el-container class="sql-query-layout" direction="horizontal">
        <el-aside width="268px" class="sql-history-aside">
          <div class="sql-history-title">执行历史</div>
          <el-scrollbar class="sql-history-scroll">
            <el-tree
              v-if="historyTreeData.length"
              :key="historyTreeRenderKey"
              ref="historyTreeRef"
              class="sql-history-tree"
              :data="historyTreeData"
              node-key="id"
              highlight-current
              :props="{ label: 'label' }"
              @node-click="onHistoryNodeClick"
            >
              <template #default="{ data }">
                <div class="history-tree-node">
                  <div class="history-tree-meta">
                    <span class="history-num">#{{ data.indexLabel }}</span>
                    <span class="history-time">{{ data.executedAt }}</span>
                    <el-tag v-if="data.isDifferent" type="warning" size="small" effect="plain">变化</el-tag>
                  </div>
                  <el-button type="danger" link size="small" @click.stop="removeHistoryItem(data.id)">删除</el-button>
                </div>
              </template>
            </el-tree>
            <el-empty v-else description="暂无执行记录" :image-size="56" />
          </el-scrollbar>
        </el-aside>
        <el-main class="sql-query-main">
          <el-input v-model="current.sql" type="textarea" :rows="5" placeholder="SQL 语句" />
          <div class="sql-query-actions">
            <el-button type="primary" @click="run">执行一次</el-button>
            <el-checkbox
              :model-value="Boolean(current.is_active)"
              class="sql-poll-checkbox"
              @change="onPollEnabledChange"
            >
              定时执行
            </el-checkbox>
            <span class="sql-poll-interval">
              <el-input-number
                v-model="current.polling_interval"
                :min="1"
                :max="3600"
                :disabled="!Boolean(current.is_active)"
                controls-position="right"
                class="sql-poll-interval-input"
                @change="onPollIntervalChange"
              />
              <span class="sql-poll-interval-unit">秒</span>
            </span>
            <el-button @click="save">保存任务</el-button>
            <span class="sql-task-session">
              <span class="sql-task-session-label">数据库配置</span>
              <el-select
                v-model="current.session_id"
                class="sql-task-session-select"
                placeholder="选择连接"
                filterable
                @change="onSessionChange"
              >
                <el-option
                  v-for="s in sessionOptions"
                  :key="s.id"
                  :value="s.id"
                  :label="sessionOptionLabel(s)"
                />
              </el-select>
            </span>
            <el-button type="danger" @click="remove">删除任务</el-button>
          </div>
          <el-table :key="tableRenderKey" style="margin-top:12px;" :data="resultRows" border stripe>
            <el-table-column v-for="c in columns" :key="c" :prop="c" :label="c" min-width="100" show-overflow-tooltip />
          </el-table>
        </el-main>
      </el-container>
    </template>

    <el-dialog v-model="editDialogVisible" title="编辑任务" width="420px" destroy-on-close @opened="syncEditName">
      <el-form label-width="88px">
        <el-form-item label="任务名称">
          <el-input v-model="editTaskName" maxlength="100" show-word-limit placeholder="请输入任务名称" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmEditTask">确定</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { Menu as MenuIcon } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { listSqlSessions, normalizeSqlSessionsData } from "../api/sqlSessions";
import { useQueryStore } from "../stores/queryStore";

const store = useQueryStore();
const sessionsForSelect = ref([]);
const activeId = ref("");
const tableRenderKey = ref(0);
const historyTreeRef = ref(null);
const editDialogVisible = ref(false);
const editTaskName = ref("");
const current = computed(() => store.currentQueries.find((q) => String(q.id) === activeId.value));

const sessionOptions = computed(() => {
  const list = sessionsForSelect.value || [];
  const q = current.value;
  if (!q?.session_id) return list;
  if (!list.some((s) => s.id === q.session_id)) {
    return [
      ...list,
      {
        id: q.session_id,
        name: `已绑定 #${q.session_id}`,
        db_type: "mysql",
        _orphan: true
      }
    ];
  }
  return list;
});

function sessionOptionLabel(s) {
  const dt = (s.db_type || "").toLowerCase();
  const t = dt === "pgsql" || dt === "postgres" ? "Pgsql" : dt === "mysql" ? "Mysql" : dt === "oracle" ? "Oracle" : dt === "sqlite" ? "Sqlite" : dt || "DB";
  return `${s.name}（${t}）`;
}

async function loadSessionsForSelect() {
  try {
    const res = await listSqlSessions();
    sessionsForSelect.value = normalizeSqlSessionsData(res?.data);
  } catch {
    sessionsForSelect.value = [];
  }
}

async function onSessionChange() {
  if (!current.value) return;
  try {
    const res = await store.editQuery(current.value.id, { session_id: current.value.session_id });
    if (res?.success === false) {
      ElMessage.error(res.error || "保存失败");
      return;
    }
    const key = String(current.value.id);
    store.queryResults[key] = { history: [], currentHistoryId: null, data: [] };
    await store.loadQueryHistory(key);
    tableRenderKey.value += 1;
  } catch (e) {
    ElMessage.error(e?.message || "保存失败");
  }
}
const resultRows = computed(() => (activeId.value ? store.queryResults[activeId.value]?.data || [] : []));
const columns = computed(() => (resultRows.value[0] ? Object.keys(resultRows.value[0]) : []));

let pollTimer = null;

function clearPollTimer() {
  if (pollTimer != null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function clampPollingInterval(raw) {
  let n = Number(raw);
  if (!Number.isFinite(n)) n = 60;
  return Math.min(3600, Math.max(1, Math.round(n)));
}

async function persistPollingFromUi() {
  if (!current.value) return;
  const interval = clampPollingInterval(current.value.polling_interval);
  current.value.polling_interval = interval;
  const res = await store.patchQueryPolling(current.value.id, {
    is_active: Boolean(current.value.is_active),
    polling_interval: interval
  });
  if (res?.success === false) ElMessage.error(res.error || "定时设置保存失败");
}

function schedulePoll() {
  clearPollTimer();
  if (!activeId.value || !current.value) return;
  if (!Boolean(current.value.is_active)) return;
  const sec = clampPollingInterval(current.value.polling_interval);
  const id = current.value.id;
  pollTimer = setInterval(() => {
    const key = String(id);
    const b = store.queryResults[key];
    const viewingOld =
      Boolean(b?.history?.length) &&
      b.currentHistoryId != null &&
      b.history[0]?.id !== b.currentHistoryId;
    store.executeQueryOnce(id).then((res) => {
      if (res?.success === false) return;
      if (!viewingOld) tableRenderKey.value += 1;
    });
  }, sec * 1000);
}

async function onPollEnabledChange(val) {
  if (!current.value) return;
  current.value.is_active = Boolean(val);
  current.value.polling_interval = clampPollingInterval(current.value.polling_interval);
  await persistPollingFromUi();
}

async function onPollIntervalChange() {
  if (!current.value || !Boolean(current.value.is_active)) return;
  current.value.polling_interval = clampPollingInterval(current.value.polling_interval);
  await persistPollingFromUi();
}

watch(
  () => [
    activeId.value,
    current.value?.id,
    current.value ? Boolean(current.value.is_active) : false,
    Number(current.value?.polling_interval)
  ],
  () => {
    schedulePoll();
  }
);

onUnmounted(() => {
  clearPollTimer();
});

function formatExecutedAt(raw) {
  if (!raw) return "";
  const s = String(raw).replace("T", " ");
  return s.length > 19 ? s.slice(0, 19) : s;
}

const historyTreeData = computed(() => {
  if (!activeId.value) return [];
  const list = store.queryResults[activeId.value]?.history || [];
  const n = list.length;
  return list.map((h, i) => {
    const indexLabel = n - i;
    return {
      id: h.id,
      label: `#${indexLabel} ${formatExecutedAt(h.executed_at)}`,
      indexLabel,
      executedAt: formatExecutedAt(h.executed_at),
      isDifferent: Boolean(h.is_different)
    };
  });
});

/** el-tree 对 data 变更有时不刷新，用 id 序列作 key 强制随列表重建 */
const historyTreeRenderKey = computed(() => {
  const list = store.queryResults[activeId.value]?.history || [];
  return list.map((h) => h.id).join(",");
});

watch(
  () => {
    const bucket = activeId.value ? store.queryResults[activeId.value] : null;
    return [activeId.value, bucket?.currentHistoryId, historyTreeRenderKey.value];
  },
  () => {
    const id = activeId.value ? store.queryResults[activeId.value]?.currentHistoryId : null;
    nextTick(() => {
      if (id != null) historyTreeRef.value?.setCurrentKey(id);
    });
  }
);

function onHistoryNodeClick(data) {
  if (!activeId.value || !data?.id) return;
  store.setCurrentHistory(activeId.value, data.id);
}

async function removeHistoryItem(historyId) {
  if (!current.value) return;
  try {
    await ElMessageBox.confirm("确定删除该条执行历史？", "删除历史", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消"
    });
  } catch {
    return;
  }
  try {
    await store.deleteHistory(current.value.id, historyId);
    ElMessage.success("已删除");
  } catch (e) {
    ElMessage.error(e?.message || "删除失败");
  }
}

onMounted(async () => {
  await loadSessionsForSelect();
  await refreshList({ silent: true });
});

async function refreshList({ silent } = {}) {
  await store.loadQueries();
  if (!store.currentQueries.length) {
    activeId.value = "";
    return;
  }
  const ids = new Set(store.currentQueries.map((q) => String(q.id)));
  if (!activeId.value || !ids.has(activeId.value)) {
    activeId.value = String(store.currentQueries[0].id);
  }
  await store.loadQueryHistory(activeId.value);
  if (!silent) ElMessage.success("列表已刷新");
}

async function onTabChange(name) {
  await store.loadQueryHistory(String(name));
}

function onMenuCommand(cmd) {
  if (cmd === "add") add();
  else if (cmd === "refresh") refreshList({ silent: false });
  else if (cmd === "edit") openEditDialog();
  else if (cmd === "save") save();
  else if (cmd === "delete") remove();
}

function openEditDialog() {
  if (!current.value) return;
  editTaskName.value = current.value.name || "";
  editDialogVisible.value = true;
}

function syncEditName() {
  if (current.value) editTaskName.value = current.value.name || "";
}

async function confirmEditTask() {
  if (!current.value) return;
  const name = editTaskName.value.trim();
  if (!name) {
    ElMessage.warning("请输入任务名称");
    return;
  }
  current.value.name = name;
  try {
    const res = await store.editQuery(current.value.id, current.value);
    if (res?.success === false) {
      ElMessage.error(res.error || "保存失败");
      return;
    }
    editDialogVisible.value = false;
    ElMessage.success("任务名称已更新");
  } catch (e) {
    ElMessage.error(e?.message || "保存失败");
  }
}

async function add() {
  await loadSessionsForSelect();
  const firstSid = sessionsForSelect.value[0]?.id;
  if (firstSid == null) {
    ElMessage.warning("请先在右上角齿轮中配置至少一份数据库连接（Mysql 或 Pgsql）");
    return;
  }
  try {
    await store.addQuery({
      name: `查询任务 ${store.currentQueries.length + 1}`,
      sql: "SELECT 1",
      session_id: firstSid,
      is_active: false,
      polling_interval: 60
    });
    activeId.value = String(store.currentQueries[store.currentQueries.length - 1].id);
    await store.loadQueryHistory(activeId.value);
    ElMessage.success("已新建查询任务");
  } catch (e) {
    ElMessage.error(e?.message || "新建失败");
  }
}
async function save() {
  if (!current.value) return;
  try {
    const res = await store.editQuery(current.value.id, current.value);
    if (res?.success === false) ElMessage.error(res.error || "保存失败");
    else ElMessage.success("已保存");
  } catch (e) {
    ElMessage.error(e?.message || "保存失败");
  }
}
async function run() {
  if (!current.value) return;
  try {
    const saveRes = await store.editQuery(current.value.id, current.value);
    if (saveRes?.success === false) {
      ElMessage.error(saveRes.error || "保存失败");
      return;
    }
    const res = await store.executeQueryOnce(current.value.id, { respectHistorySelection: false });
    if (res?.success === false) {
      ElMessage.error(res.error || "执行失败");
      return;
    }
    tableRenderKey.value += 1;
    if (res?.data?.history_appended === false) {
      ElMessage.success("已执行；结果与上次一致，未新增历史记录");
    } else {
      ElMessage.success("已保存并执行，已记录历史");
    }
  } catch (e) {
    ElMessage.error(e?.message || "操作失败");
  }
}
async function remove() {
  if (!current.value) return;
  try {
    await ElMessageBox.confirm("确定删除当前查询任务？此操作不可恢复。", "删除任务", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消"
    });
  } catch {
    return;
  }
  try {
    await store.removeQuery(current.value.id);
    ElMessage.success("已删除");
    activeId.value = store.currentQueries[0] ? String(store.currentQueries[0].id) : "";
    if (activeId.value) await store.loadQueryHistory(activeId.value);
  } catch (e) {
    ElMessage.error(e?.message || "删除失败");
  }
}
</script>

<style scoped>
.sql-query-card :deep(.el-card__header) {
  padding: 12px 16px;
}
.sql-query-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.sql-query-title {
  font-weight: 600;
  font-size: 15px;
}
.sql-query-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 12px;
  margin-top: 8px;
}
.sql-poll-checkbox {
  margin-left: 4px;
  white-space: nowrap;
}
.sql-poll-interval {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.sql-poll-interval-input {
  width: 120px;
}
.sql-poll-interval-unit {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
.sql-task-session {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-left: 4px;
}
.sql-task-session-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}
.sql-task-session-select {
  width: 220px;
}
.sql-query-layout {
  margin-top: 8px;
  align-items: stretch;
  min-height: 280px;
}
.sql-history-aside {
  border-right: 1px solid var(--el-border-color-lighter);
  padding-right: 12px;
  margin-right: 12px;
  flex-shrink: 0;
}
.sql-history-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}
.sql-history-scroll {
  max-height: 480px;
}
.sql-history-tree {
  background: transparent;
}
.sql-history-tree :deep(.el-tree-node__content) {
  height: auto;
  min-height: 32px;
  align-items: flex-start;
  padding: 4px 0;
}
.sql-query-main {
  padding: 0;
  flex: 1;
  min-width: 0;
}
.history-tree-node {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding-right: 4px;
  box-sizing: border-box;
}
.history-tree-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex: 1;
}
.history-num {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
.history-time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  word-break: break-all;
}
</style>
