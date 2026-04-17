<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <h3>日志列表</h3>
      <div>
        <el-button @click="showTimeline = true">时间轴备注</el-button>
        <el-dropdown trigger="click" @command="onViewMenuCommand">
          <el-button :icon="Setting" />
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="create">新建视图</el-dropdown-item>
              <el-dropdown-item command="edit" :disabled="!activeViewId">编辑视图</el-dropdown-item>
              <el-dropdown-item command="delete" :disabled="!activeViewId" divided>删除视图</el-dropdown-item>
              <el-dropdown-item command="appendLog">追加日志</el-dropdown-item>
              <el-dropdown-item command="searchConfigMulti">多搜索配置</el-dropdown-item>
              <el-dropdown-item command="config" divided>日志配置</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <el-tabs v-model="activePane" type="card" closable @tab-remove="onTabRemove">
      <el-tab-pane v-for="v in views" :key="v.id" :name="String(v.id)" :label="v.name" />
      <el-tab-pane v-if="showAppendLogTab" :name="APPEND_LOG_TAB" label="追加日志" />
      <el-tab-pane v-if="showSearchConfigTab" :name="SEARCH_CONFIG_TAB" label="多搜索配置" />
      <el-tab-pane v-if="showLogConfigTab" :name="LOG_CONFIG_TAB" label="日志配置" />
    </el-tabs>

    <template
      v-if="
        activePane !== APPEND_LOG_TAB &&
        activePane !== SEARCH_CONFIG_TAB &&
        activePane !== LOG_CONFIG_TAB
      "
    >
    <SearchBox :value="search" @update:value="(v) => (search = v)" @search="loadLogs" />
    <LogList
      :items="logs"
      :total="total"
      :page="page"
      :page-size="pageSize"
      @refresh="loadLogs"
      @update:page="(v) => { page = v; loadLogs(); }"
      @update:pageSize="(v) => { pageSize = v; loadLogs(); }"
      @update:notesOnly="(v) => { notesOnly = v; loadLogs(); }"
    />
    </template>
    <AppendLogPanel v-else-if="activePane === APPEND_LOG_TAB" embedded class="log-pane-sub" />
    <SearchConfigPanel v-else-if="activePane === SEARCH_CONFIG_TAB" embedded class="log-pane-sub" />
    <ConfigPanel
      v-else-if="activePane === LOG_CONFIG_TAB"
      embedded
      class="log-pane-sub"
      @reinitialized="onLogsDatasetChanged"
      @logs-cleared="onLogsDatasetChanged"
    />

    <TimelineNotesDialog v-model:visible="showTimeline" :view-id="timelineViewId" />
    <el-dialog v-model="editDialogVisible" title="编辑视图" width="420px" align-center>
      <el-form label-width="90px">
        <el-form-item label="视图名称">
          <el-input v-model="editViewName" placeholder="请输入视图名称" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmEditView">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, inject, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { Setting } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { createLogView, deleteLogView, getLogs, listLogViews, updateLogView } from "../api/api";
import AppendLogPanel from "./AppendLogPanel.vue";
import ConfigPanel from "./ConfigPanel.vue";
import SearchConfigPanel from "./SearchConfigPanel.vue";
import LogList from "./LogList.vue";
import SearchBox from "./SearchBox.vue";
import TimelineNotesDialog from "./TimelineNotesDialog.vue";

/** 与真实视图 ID 不冲突的占位名，仅用于 UI 标签，不参与视图 CRUD */
const APPEND_LOG_TAB = "__append_log__";
const SEARCH_CONFIG_TAB = "__search_config__";
const LOG_CONFIG_TAB = "__log_config__";

const views = ref([]);
/** 当前选中的标签：视图 ID 字符串，或子功能占位名 */
const activePane = ref("");
const showAppendLogTab = ref(false);
const showSearchConfigTab = ref(false);
const showLogConfigTab = ref(false);

/** 顶栏「日志配置」与日志子标签联动（App.vue provide） */
const pendingLogConfigTab = inject("pendingLogConfigTab", null);
/** 主界面顶栏当前标签；离开「日志列表」主标签时暂停列表轮询，避免无效请求并在返回时立即刷新 */
const spotterActiveTab = inject("spotterActiveTab", ref("logs"));

const activeViewId = computed(() => {
  if (
    activePane.value === APPEND_LOG_TAB ||
    activePane.value === SEARCH_CONFIG_TAB ||
    activePane.value === LOG_CONFIG_TAB
  ) {
    return "";
  }
  return activePane.value;
});

const timelineViewId = computed(() => {
  const id = Number(activePane.value);
  if (!Number.isNaN(id) && id > 0) return id;
  const first = views.value[0]?.id;
  return first != null ? Number(first) : 0;
});
const showTimeline = ref(false);
const logs = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);
const search = ref("");
const notesOnly = ref(false);
const editDialogVisible = ref(false);
const editViewName = ref("");

/** 进入配置等子标签前最后选中的视图，用于在「日志配置」下仍轮询该视图的列表数据 */
const lastActiveLogViewId = ref("");

const POLL_INTERVAL_MS = 10000;
let pollTimer = null;

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function resolvePollViewId() {
  if (activeViewId.value) return activeViewId.value;
  return lastActiveLogViewId.value || "";
}

function startPolling() {
  stopPolling();
  pollTimer = setInterval(() => {
    if (resolvePollViewId() && spotterActiveTab.value === "logs") {
      loadLogs();
    }
  }, POLL_INTERVAL_MS);
}

function syncLogPollingAfterNav() {
  if (spotterActiveTab.value !== "logs") {
    stopPolling();
    return;
  }
  if (resolvePollViewId()) {
    startPolling();
  } else {
    stopPolling();
  }
}

async function onLogsDatasetChanged() {
  await loadLogs();
  syncLogPollingAfterNav();
}

function lastViewStorageKey() {
  return `fastlog_last_active_view_id_${localStorage.getItem("fastlog_current_system_id") || "1"}`;
}

function resolveStoredViewId() {
  const key = lastViewStorageKey();
  let next = localStorage.getItem(key) || String(views.value[0]?.id ?? "");
  if (!views.value.find((v) => String(v.id) === next)) {
    next = String(views.value[0]?.id ?? "");
  }
  return next;
}

async function loadViews() {
  const res = await listLogViews();
  views.value = res.data || [];
  if (!views.value.length) {
    const createRes = await createLogView({ name: "默认视图", search_query: "", description: "", sort_order: 0 });
    activePane.value = String(createRes.data.id);
    lastActiveLogViewId.value = activePane.value;
    await loadViews();
    return;
  }
  const wasSpecialSubTab =
    (activePane.value === APPEND_LOG_TAB && showAppendLogTab.value) ||
    (activePane.value === SEARCH_CONFIG_TAB && showSearchConfigTab.value) ||
    (activePane.value === LOG_CONFIG_TAB && showLogConfigTab.value);
  if (wasSpecialSubTab) {
    const stored = resolveStoredViewId();
    if (stored && views.value.some((v) => String(v.id) === stored)) {
      lastActiveLogViewId.value = stored;
    }
    return;
  }
  activePane.value = resolveStoredViewId();
  const curr = views.value.find((v) => String(v.id) === activePane.value);
  search.value = curr?.search_query || "";
  if (activePane.value && views.value.some((v) => String(v.id) === String(activePane.value))) {
    lastActiveLogViewId.value = activePane.value;
  }
}

watch(activePane, async (pane) => {
  if (pane === APPEND_LOG_TAB || pane === SEARCH_CONFIG_TAB) {
    stopPolling();
    return;
  }
  if (pane === LOG_CONFIG_TAB) {
    if (spotterActiveTab.value === "logs" && lastActiveLogViewId.value) {
      syncLogPollingAfterNav();
    } else {
      stopPolling();
    }
    return;
  }
  const key = lastViewStorageKey();
  localStorage.setItem(key, pane || "");
  if (views.value.some((v) => String(v.id) === String(pane))) {
    lastActiveLogViewId.value = pane;
  }
  const curr = views.value.find((i) => String(i.id) === String(pane));
  search.value = curr?.search_query || "";
  await loadLogs();
  syncLogPollingAfterNav();
});

watch(spotterActiveTab, (t) => {
  if (t !== "logs") {
    stopPolling();
    return;
  }
  if (resolvePollViewId()) {
    loadLogs();
    startPolling();
  }
});

async function loadLogs() {
  const vid = resolvePollViewId();
  if (!vid) return;
  await updateLogView(Number(vid), { search_query: search.value });
  const res = await getLogs({
    page: page.value,
    page_size: pageSize.value,
    search: search.value,
    notes_only: notesOnly.value
  });
  logs.value = res.data.items || [];
  total.value = res.data.total || 0;
}

async function createView() {
  await createLogView({ name: `视图${views.value.length + 1}`, search_query: "", description: "", sort_order: views.value.length });
  await loadViews();
}
async function editView() {
  if (!activeViewId.value) return;
  const curr = views.value.find((v) => String(v.id) === String(activeViewId.value));
  if (!curr) return;
  editViewName.value = curr.name || "";
  editDialogVisible.value = true;
}
async function confirmEditView() {
  const curr = views.value.find((v) => String(v.id) === String(activeViewId.value));
  if (!curr) return;
  const name = String(editViewName.value || "").trim();
  if (!name) {
    ElMessage.warning("视图名称不能为空");
    return;
  }
  await updateLogView(Number(curr.id), { name });
  editDialogVisible.value = false;
  await loadViews();
}
async function onTabRemove(name) {
  if (name === APPEND_LOG_TAB) {
    showAppendLogTab.value = false;
    activePane.value = resolveStoredViewId();
    return;
  }
  if (name === SEARCH_CONFIG_TAB) {
    showSearchConfigTab.value = false;
    activePane.value = resolveStoredViewId();
    return;
  }
  if (name === LOG_CONFIG_TAB) {
    showLogConfigTab.value = false;
    activePane.value = resolveStoredViewId();
    return;
  }
  await deleteLogView(Number(name));
  await loadViews();
  await loadLogs();
}

async function onViewMenuCommand(command) {
  if (command === "create") {
    await createView();
    return;
  }
  if (command === "edit") {
    await editView();
    return;
  }
  if (command === "delete") {
    if (!activeViewId.value) return;
    await ElMessageBox.confirm("确认删除当前视图？", "提示", { type: "warning" });
    await deleteLogView(Number(activeViewId.value));
    await loadViews();
    await loadLogs();
    return;
  }
  if (command === "appendLog") {
    showAppendLogTab.value = true;
    activePane.value = APPEND_LOG_TAB;
    return;
  }
  if (command === "searchConfigMulti") {
    showSearchConfigTab.value = true;
    activePane.value = SEARCH_CONFIG_TAB;
    return;
  }
  if (command === "config") {
    showLogConfigTab.value = true;
    activePane.value = LOG_CONFIG_TAB;
  }
}

watch(
  () => pendingLogConfigTab?.value,
  (v) => {
    if (!pendingLogConfigTab || !v) return;
    showLogConfigTab.value = true;
    activePane.value = LOG_CONFIG_TAB;
    pendingLogConfigTab.value = false;
  },
  { immediate: true },
);

onMounted(async () => {
  await loadViews();
  if (
    activePane.value !== APPEND_LOG_TAB &&
    activePane.value !== SEARCH_CONFIG_TAB &&
    activePane.value !== LOG_CONFIG_TAB
  ) {
    await loadLogs();
    syncLogPollingAfterNav();
  } else if (activePane.value === LOG_CONFIG_TAB && spotterActiveTab.value === "logs") {
    await loadLogs();
    syncLogPollingAfterNav();
  }
});

onBeforeUnmount(() => {
  stopPolling();
});
</script>

