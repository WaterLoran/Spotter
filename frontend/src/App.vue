<template>
  <div class="app">
    <div class="header header-bar">
      <AppLogo>Spotter</AppLogo>
      <div class="header-actions">
        <el-select v-model="currentSystemId" style="width: 180px" @change="onSystemChanged">
          <el-option v-for="s in systems" :key="s.id" :label="s.name" :value="String(s.id)" />
        </el-select>
        <el-dropdown trigger="click" placement="bottom-end" popper-class="system-menu-dropdown">
          <el-button :icon="MenuIcon" circle />
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="renameSystemAction">
                <span class="system-menu-row">
                  <el-icon><EditPen /></el-icon>
                  编辑系统名称
                </span>
              </el-dropdown-item>
              <el-dropdown-item @click="createSystemAction">
                <span class="system-menu-row">
                  <el-icon><Plus /></el-icon>
                  新增系统
                </span>
              </el-dropdown-item>
              <el-dropdown-item divided @click="deleteSystemAction">
                <span class="system-menu-row">
                  <el-icon><Delete /></el-icon>
                  删除当前系统
                </span>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-dropdown trigger="click" placement="bottom-end" popper-class="settings-menu-dropdown">
          <el-button :icon="Setting" circle />
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="openLogConfigTab">日志配置</el-dropdown-item>
              <el-dropdown-item divided @click="openSqlSessionConfigDialog('mysql')">Mysql配置</el-dropdown-item>
              <el-dropdown-item @click="openSqlSessionConfigDialog('pgsql')">Pgsql配置</el-dropdown-item>
              <el-dropdown-item @click="openSqlSessionConfigDialog('oracle')">Oracle配置</el-dropdown-item>
              <el-dropdown-item divided @click="openRedisConfigDialog">Redis 配置</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button :icon="View" circle @click="openTabVisibilityDialog" />
      </div>
    </div>

    <el-alert v-if="healthError" type="error" :closable="false" title="后端连接失败，请检查后端服务" />

    <el-tabs v-model="activeTab">
      <el-tab-pane
        v-for="name in displayTabNames"
        :key="name"
        :label="TAB_LABELS[name]"
        :name="name"
        :lazy="true"
      >
        <component :is="TAB_COMPONENTS[name]" />
      </el-tab-pane>
    </el-tabs>

    <el-dialog
      v-model="tabVisibilityDialogVisible"
      title="标签页显示与排序"
      width="420px"
      destroy-on-close
      @closed="destroyTabSortable"
    >
      <p class="tab-visibility-hint">拖动左侧手柄排序；勾选控制在主界面是否显示（仅下列六项）。</p>
      <div ref="sortableContainerRef" class="tab-visibility-sort-list">
        <div v-for="row in draftOrderRows" :key="row.key" class="tab-visibility-row">
          <span class="tab-visibility-drag-handle" title="拖动排序">
            <el-icon><Rank /></el-icon>
          </span>
          <el-checkbox v-model="row.visible" class="tab-visibility-check">
            {{ row.label }}
          </el-checkbox>
        </div>
      </div>
      <template #footer>
        <el-button @click="tabVisibilityDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="applyTabVisibilitySettings">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="sqlSessionConfigDialogVisible"
      :title="sqlSessionConfigDialogTitle"
      width="640px"
      destroy-on-close
      align-center
    >
      <SqlConnectionConfigPanel v-if="sqlSessionConfigDialogVisible" embedded :db-type="sqlSessionConfigInitialDb" />
    </el-dialog>

    <el-dialog v-model="redisConfigDialogVisible" title="Redis 连接配置" width="640px" destroy-on-close align-center>
      <RedisConnectionConfigPanel v-if="redisConfigDialogVisible" embedded />
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, provide, ref, watch } from "vue";
import { Delete, EditPen, Menu as MenuIcon, Plus, Rank, Setting, View } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import Sortable from "sortablejs";
import { createSystem, deleteSystem, health, listSystems, renameSystem } from "./api/api";
import AppLogo from "./components/AppLogo.vue";
import BackgroundTasksPanel from "./components/BackgroundTasksPanel.vue";
import LogViewPane from "./components/LogViewPane.vue";
import ShellQueryPanel from "./components/ShellQueryPanel.vue";
import SqlConnectionConfigPanel from "./components/SqlConnectionConfigPanel.vue";
import ApiQueryPanel from "./components/ApiQueryPanel.vue";
import RedisConnectionConfigPanel from "./components/RedisConnectionConfigPanel.vue";
import RedisQueryPanel from "./components/RedisQueryPanel.vue";
import SqlFieldSearchPanel from "./components/SqlFieldSearchPanel.vue";
import SqlQueryPanel from "./components/SqlQueryPanel.vue";

const TAB_STORAGE_KEY = "spotter_tab_bar_prefs_v1";

/** 仅这六项可在弹窗中配置显示与顺序；其余标签顺序固定见 DEFAULT_FULL_TAB_ORDER */
const CONFIGURABLE_TAB_KEYS = ["logs", "sql-query", "shell-query", "api-query", "redis-query", "field-search"];
/** 与 {@link DEFAULT_FULL_TAB_ORDER} 中前六项可配置标签对应下标；最后一项为固定的「后台任务」 */
const CONFIGURABLE_TAB_SLOTS = [0, 1, 2, 3, 4, 5];

const CONFIGURABLE_LABELS = {
  logs: "日志列表",
  "sql-query": "SQL查询",
  "shell-query": "Shell查询",
  "api-query": "API查询",
  "redis-query": "Redis 查询",
  "field-search": "字段搜索",
};

const TAB_LABELS = {
  logs: "日志列表",
  "sql-query": "SQL查询",
  "shell-query": "Shell查询",
  "api-query": "API查询",
  "redis-query": "Redis 查询",
  "field-search": "字段搜索",
  tasks: "后台任务",
};

const TAB_COMPONENTS = {
  logs: LogViewPane,
  "sql-query": SqlQueryPanel,
  "shell-query": ShellQueryPanel,
  "api-query": ApiQueryPanel,
  "redis-query": RedisQueryPanel,
  "field-search": SqlFieldSearchPanel,
  tasks: BackgroundTasksPanel,
};

const DEFAULT_FULL_TAB_ORDER = [
  "logs",
  "sql-query",
  "shell-query",
  "api-query",
  "redis-query",
  "field-search",
  "tasks",
];

const DEFAULT_ORDER_CONFIGURABLE = [
  "logs",
  "sql-query",
  "shell-query",
  "api-query",
  "redis-query",
  "field-search",
];

function loadTabBarPrefs() {
  try {
    const raw = localStorage.getItem(TAB_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function normalizeOrderConfigurable(raw) {
  const allowed = new Set(CONFIGURABLE_TAB_KEYS);
  const list = Array.isArray(raw) ? raw.filter((k) => allowed.has(k)) : [];
  const missing = DEFAULT_ORDER_CONFIGURABLE.filter((k) => !list.includes(k));
  return [...list, ...missing].slice(0, CONFIGURABLE_TAB_KEYS.length);
}

function normalizeVisible(raw) {
  const v = {
    logs: true,
    "sql-query": true,
    "shell-query": true,
    "api-query": true,
    "redis-query": true,
    "field-search": true,
  };
  if (raw && typeof raw === "object") {
    for (const k of CONFIGURABLE_TAB_KEYS) {
      if (k in raw) v[k] = !!raw[k];
    }
  }
  return v;
}

const prefs = loadTabBarPrefs();
const savedOrderConfigurable = ref(
  normalizeOrderConfigurable(prefs?.orderConfigurable ?? prefs?.orderFour),
);
const savedVisible = ref(normalizeVisible(prefs?.visible));

function mergeFullTabOrder(orderConfigurable) {
  const full = [...DEFAULT_FULL_TAB_ORDER];
  for (let i = 0; i < CONFIGURABLE_TAB_KEYS.length; i++) {
    full[CONFIGURABLE_TAB_SLOTS[i]] = orderConfigurable[i];
  }
  return full;
}

function isConfigurableTab(name) {
  return CONFIGURABLE_TAB_KEYS.includes(name);
}

const displayTabNames = computed(() => {
  const full = mergeFullTabOrder(savedOrderConfigurable.value);
  const vis = savedVisible.value;
  return full.filter((name) => !isConfigurableTab(name) || vis[name] !== false);
});

const activeTab = ref("logs");
const systems = ref([]);
const healthError = ref(false);
const currentSystemId = ref(localStorage.getItem("fastlog_current_system_id") || "1");

const tabVisibilityDialogVisible = ref(false);
/** 与 LogViewPane 内「日志配置」子标签联动 */
const pendingLogConfigTab = ref(false);
provide("pendingLogConfigTab", pendingLogConfigTab);
/** 主界面当前标签（日志列表 / SQL 等），供 LogViewPane 在离开「日志」页时暂停轮询、返回时恢复 */
provide("spotterActiveTab", activeTab);

const sqlSessionConfigDialogVisible = ref(false);
/** 打开 SQL 连接弹窗时锁定的库类型：mysql | pgsql | oracle */
const sqlSessionConfigInitialDb = ref("mysql");
const sqlSessionConfigDialogTitle = computed(() =>
  sqlSessionConfigInitialDb.value === "pgsql"
    ? "Pgsql 连接配置"
    : sqlSessionConfigInitialDb.value === "oracle"
      ? "Oracle 连接配置"
      : "Mysql 连接配置"
);
const redisConfigDialogVisible = ref(false);
const sortableContainerRef = ref(null);
const draftOrderRows = ref([]);
let sortableInstance = null;

function destroyTabSortable() {
  if (sortableInstance) {
    sortableInstance.destroy();
    sortableInstance = null;
  }
}

function ensureValidActiveTab() {
  const names = displayTabNames.value;
  if (!names.length) return;
  if (!names.includes(activeTab.value)) {
    activeTab.value = names[0];
  }
}

function persistTabBarPrefs() {
  localStorage.setItem(
    TAB_STORAGE_KEY,
    JSON.stringify({
      orderConfigurable: savedOrderConfigurable.value,
      visible: { ...savedVisible.value },
    }),
  );
}

function openTabVisibilityDialog() {
  draftOrderRows.value = savedOrderConfigurable.value.map((key) => ({
    key,
    label: CONFIGURABLE_LABELS[key],
    visible: savedVisible.value[key] !== false,
  }));
  tabVisibilityDialogVisible.value = true;
}

function applyTabVisibilitySettings() {
  savedOrderConfigurable.value = draftOrderRows.value.map((r) => r.key);
  const nextVis = { ...savedVisible.value };
  for (const row of draftOrderRows.value) {
    nextVis[row.key] = row.visible;
  }
  savedVisible.value = nextVis;
  persistTabBarPrefs();
  tabVisibilityDialogVisible.value = false;
  ensureValidActiveTab();
}

watch(tabVisibilityDialogVisible, async (open) => {
  if (!open) {
    destroyTabSortable();
    return;
  }
  await nextTick();
  destroyTabSortable();
  const el = sortableContainerRef.value;
  if (!el) return;
  sortableInstance = Sortable.create(el, {
    animation: 150,
    handle: ".tab-visibility-drag-handle",
    ghostClass: "tab-visibility-ghost",
    onEnd(evt) {
      const arr = draftOrderRows.value;
      const moved = arr.splice(evt.oldIndex, 1)[0];
      arr.splice(evt.newIndex, 0, moved);
    },
  });
});

async function loadSystems() {
  const res = await listSystems();
  systems.value = res.data || [];
  if (!systems.value.find((s) => String(s.id) === currentSystemId.value) && systems.value.length) {
    currentSystemId.value = String(systems.value[0].id);
    localStorage.setItem("fastlog_current_system_id", currentSystemId.value);
  }
}

function onSystemChanged() {
  localStorage.setItem("fastlog_current_system_id", currentSystemId.value);
  location.reload();
}

async function renameSystemAction() {
  const curr = systems.value.find((s) => String(s.id) === currentSystemId.value);
  if (!curr) return;
  const { value } = await ElMessageBox.prompt("请输入系统名称", "重命名系统", { inputValue: curr.name });
  await renameSystem(curr.id, value);
  await loadSystems();
}

async function createSystemAction() {
  const { value } = await ElMessageBox.prompt("请输入系统名称", "新增系统", { inputValue: "新系统" });
  await createSystem(value);
  await loadSystems();
}

function openLogConfigTab() {
  activeTab.value = "logs";
  pendingLogConfigTab.value = true;
}

function openSqlSessionConfigDialog(kind = "mysql") {
  sqlSessionConfigInitialDb.value = kind === "pgsql" ? "pgsql" : kind === "oracle" ? "oracle" : "mysql";
  sqlSessionConfigDialogVisible.value = true;
}

function openRedisConfigDialog() {
  redisConfigDialogVisible.value = true;
}

async function deleteSystemAction() {
  const curr = systems.value.find((s) => String(s.id) === currentSystemId.value);
  if (!curr) return;
  await ElMessageBox.confirm(`确认删除系统 ${curr.name} ?`, "警告", { type: "warning" });
  await deleteSystem(curr.id);
  ElMessage.success("删除成功");
  await loadSystems();
}

onMounted(async () => {
  ensureValidActiveTab();
  try {
    await health();
    healthError.value = false;
  } catch {
    healthError.value = true;
  }
  await loadSystems();
});
</script>

<style scoped>
.app {
  padding: 16px;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
/* BOSS直聘 APP 主导航栏相近青绿主题色 */
.header-bar {
  background-color: #12ada9;
  color: #fff;
  margin: -16px -16px 12px;
  padding: 12px 16px;
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.06);
}
.header-bar :deep(.app-logo-text) {
  color: #fff;
}
.header-bar :deep(.el-select .el-select__wrapper) {
  background-color: rgba(255, 255, 255, 0.18);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.42) inset;
}
.header-bar :deep(.el-select .el-select__wrapper.is-focused) {
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.75) inset;
}
.header-bar :deep(.el-select .el-select__wrapper.is-hovering:not(.is-focused)) {
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.55) inset;
}
.header-bar :deep(.el-select .el-select__placeholder) {
  color: rgba(255, 255, 255, 0.65);
}
.header-bar :deep(.el-select .el-select__placeholder.is-transparent) {
  color: rgba(255, 255, 255, 0.55);
}
.header-bar :deep(.el-select .el-select__tags-text),
.header-bar :deep(.el-select .el-select__selected-item) {
  color: #fff;
}
.header-bar :deep(.el-select .el-select__caret) {
  color: rgba(255, 255, 255, 0.92);
}
.header-bar :deep(.el-button) {
  --el-button-bg-color: rgba(255, 255, 255, 0.16);
  --el-button-border-color: rgba(255, 255, 255, 0.48);
  --el-button-text-color: #fff;
  --el-button-hover-bg-color: rgba(255, 255, 255, 0.28);
  --el-button-hover-border-color: rgba(255, 255, 255, 0.75);
  --el-button-hover-text-color: #fff;
  --el-button-active-bg-color: rgba(255, 255, 255, 0.22);
  --el-button-active-border-color: #fff;
}
.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.tab-visibility-hint {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
}
.tab-visibility-sort-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.tab-visibility-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
}
.tab-visibility-drag-handle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: grab;
  color: var(--el-text-color-secondary);
  padding: 2px;
  touch-action: none;
}
.tab-visibility-drag-handle:active {
  cursor: grabbing;
}
.tab-visibility-check {
  flex: 1;
}
</style>

<style>
.system-menu-dropdown .system-menu-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.settings-menu-dropdown .el-dropdown-menu__item {
  min-width: 168px;
}
.tab-visibility-ghost {
  opacity: 0.55;
  background: var(--el-color-primary-light-9);
}
</style>
