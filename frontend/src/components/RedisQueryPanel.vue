<template>
  <el-card class="redis-query-card">
    <template #header>
      <div class="redis-query-card-header">
        <span class="redis-query-title">Redis 查询</span>
        <el-dropdown trigger="click" @command="onMenuCommand">
          <el-button :icon="Setting" circle title="操作" />
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="add">新建查询任务</el-dropdown-item>
              <el-dropdown-item command="refresh" divided>刷新任务列表</el-dropdown-item>
              <el-dropdown-item command="col-sort" divided>排序</el-dropdown-item>
              <el-dropdown-item command="col-vis">显隐</el-dropdown-item>
              <el-dropdown-item command="help" divided>功能说明</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </template>

    <el-table
      :data="store.tasks"
      border
      stripe
      class="redis-task-table"
      :row-style="rowStyle"
      empty-text="暂无查询任务，请点击右上角齿轮菜单新建"
    >
      <el-table-column
        v-for="col in visibleColumnsOrdered"
        :key="col.key"
        :prop="col.key"
        :label="col.label"
        :min-width="col.minW"
        :width="col.width"
        :align="col.align"
      >
        <template #default="{ row, $index }">
          <template v-if="col.key === 'idx'">{{ $index + 1 }}</template>
          <template v-else-if="col.key === 'name'">{{ row.name }}</template>
          <template v-else-if="col.key === 'redis_key'"><code class="redis-key-cell">{{ row.redis_key }}</code></template>
          <template v-else-if="col.key === 'value'">
            <span
              class="redis-value-cell"
              :class="{ 'is-clickable': hasValue(row) }"
              :title="row.latest_value || ''"
              @click="onValueClick(row)"
            >
              {{ truncate(row.latest_value, 200) }}
            </span>
          </template>
          <template v-else-if="col.key === 'last_changed'">{{ formatTime(row.last_changed_at) }}</template>
          <template v-else-if="col.key === 'detail'">
            <el-button type="primary" link @click="openDetail(row)">详情</el-button>
          </template>
          <template v-else-if="col.key === 'actions'">
            <el-button type="primary" link @click="openEdit(row)">编辑</el-button>
            <el-button type="danger" link @click="removeTask(row)">删除</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="editDialogVisible"
      :title="editMode === 'create' ? '新建查询任务' : '编辑查询任务'"
      width="480px"
      destroy-on-close
      align-center
    >
      <el-form label-width="120px">
        <el-form-item label="任务名称">
          <el-input v-model="editForm.name" maxlength="100" show-word-limit />
        </el-form-item>
        <el-form-item label="Redis 连接">
          <el-select v-model="editForm.redis_session_id" style="width: 100%" filterable>
            <el-option
              v-for="s in store.sessions"
              :key="s.id"
              :label="s.name || `连接 #${s.id}`"
              :value="s.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Key">
          <el-input v-model="editForm.redis_key" placeholder="要监视的 Redis key" />
        </el-form-item>
        <el-form-item label="颜色递增百分比">
          <div class="color-step-row">
            <el-input-number v-model="editForm.color_step_percent" :min="1" :max="100" controls-position="right" />
            <el-popover placement="right" :width="320" trigger="click">
              <template #reference>
                <el-button circle class="color-step-help" title="说明">?</el-button>
              </template>
              <div class="color-step-help-body">
                <p>
                  每检测到<strong>值相对上次发生变化</strong>一次，行背景会从绿色向红色加深一档；该百分比表示向红色靠近的幅度（默认
                  10% 表示约 10 次变化后变为红色并保持）。
                </p>
                <p>点击表格中「key 对应的值」表示你已注意到当前值，背景会重置为亮绿色。</p>
              </div>
            </el-popover>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="confirmEdit">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="detailDialogVisible"
      :title="detailTitle"
      width="820px"
      destroy-on-close
      align-center
      @opened="onDetailOpened"
    >
      <div class="detail-toolbar">
        <el-button size="small" :loading="detailLoading" @click="reloadDetail">刷新</el-button>
        <el-button size="small" type="danger" plain @click="clearDetailHistory">清空历史</el-button>
      </div>
      <el-table :data="detailTableRows" border stripe max-height="420">
        <el-table-column label="序号" width="72" align="center">
          <template #default="{ $index }">{{ detailSeq($index) }}</template>
        </el-table-column>
        <el-table-column label="时间" width="180" prop="recorded_at" />
        <el-table-column label="数值" min-width="280">
          <template #default="{ row }">
            <div class="history-value-cell">
              <el-button size="small" link type="primary" class="history-copy" @click="copyText(row.displayValue)">
                复制
              </el-button>
              <el-tooltip :content="row.displayValue" placement="top" :disabled="row.displayValue.length < 80">
                <span class="history-value-text">{{ truncate(row.displayValue, 200) }}</span>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <el-dialog
      v-model="colSortDialogVisible"
      title="列排序"
      width="400px"
      destroy-on-close
      @closed="destroyColSortable"
    >
      <p class="dialog-hint">拖动左侧手柄调整列顺序。</p>
      <div ref="colSortRef" class="col-sort-list">
        <div v-for="row in colSortDraft" :key="row.key" class="col-sort-row">
          <span class="col-sort-handle" title="拖动排序">
            <el-icon><Rank /></el-icon>
          </span>
          <span class="col-sort-label">{{ row.label }}</span>
        </div>
      </div>
      <template #footer>
        <el-button @click="colSortDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="applyColSort">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="colVisDialogVisible" title="列显隐" width="400px" destroy-on-close>
      <el-checkbox-group v-model="colVisDraft" class="col-vis-group">
        <div v-for="c in allColumnDefs" :key="c.key" class="col-vis-row">
          <el-checkbox :label="c.key" :disabled="c.key === 'idx' || c.key === 'actions'">
            {{ c.label }}
          </el-checkbox>
        </div>
      </el-checkbox-group>
      <template #footer>
        <el-button @click="colVisDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="applyColVis">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="helpDialogVisible" title="Redis 查询功能说明" width="640px" destroy-on-close>
      <div class="help-body">
        <h4>一、Redis 服务端配置</h4>
        <p>
          本功能依赖 Redis
          <strong>键空间通知（Keyspace Notifications）</strong>。请在 Redis 中启用，例如临时生效：
        </p>
        <pre class="help-pre">CONFIG SET notify-keyspace-events KEA</pre>
        <p>生产环境建议在 <code>redis.conf</code> 中设置并重启：</p>
        <pre class="help-pre">notify-keyspace-events "KEA"</pre>
        <p>
          若实例禁止 <code>CONFIG</code>，需由运维在配置文件中开启。Spotter 会在「测试连接」时尝试读取该配置；无权限时请以实际配置为准。
        </p>
        <h4>二、工作原理</h4>
        <p>
          对每个已配置且存在查询任务的连接，后端会 <code>PSUBSCRIBE __keyspace@&lt;DB&gt;__:*</code>；当订阅频道显示你关心的
          key 发生变化时，会立即对该 key 执行只读命令拉取当前值，写入本地库并通过浏览器 SSE 推送到本页。
        </p>
        <h4>三、表格与颜色</h4>
        <p>
          行背景从绿到红表示<strong>在你标记「已读」之后</strong>，该 key
          的值相对上次记录又发生了多少次变化；达到满档后保持红色，直到你点击「key 对应的值」重置为已关注。
        </p>
        <h4>四、详情与历史</h4>
        <p>「详情」中按时间倒序列出每次值变化的历史；可刷新或清空。键被删除等场景下值可能为 <code>(nil)</code>。</p>
      </div>
      <template #footer>
        <el-button type="primary" @click="helpDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { Rank, Setting } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import Sortable from "sortablejs";
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { createRedisTask, deleteRedisTask, orderRedisTasks, updateRedisTask } from "../api/redisQuery";
import { useRedisQueryStore } from "../stores/redisQueryStore";

const COLUMN_STORAGE_KEY = "spotter_redis_query_columns_v1";

const ALL_COLUMNS = [
  { key: "idx", label: "序号", minW: 64, width: 64, align: "center" },
  { key: "name", label: "任务名称", minW: 120 },
  { key: "redis_key", label: "key", minW: 120 },
  { key: "value", label: "key对应的值", minW: 160 },
  { key: "last_changed", label: "最新变更时间", minW: 168, width: 180 },
  { key: "detail", label: "详情", width: 88, align: "center" },
  { key: "actions", label: "操作", width: 120, align: "center" }
];

function loadColumnPrefs() {
  try {
    const raw = localStorage.getItem(COLUMN_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function defaultPrefs() {
  return {
    order: ALL_COLUMNS.map((c) => c.key),
    visible: ALL_COLUMNS.reduce((acc, c) => {
      acc[c.key] = true;
      return acc;
    }, {})
  };
}

const prefs = loadColumnPrefs();
const basePrefs = defaultPrefs();
const savedColOrder = ref(
  Array.isArray(prefs?.order) ? prefs.order.filter((k) => ALL_COLUMNS.some((c) => c.key === k)) : basePrefs.order
);
const missingOrder = ALL_COLUMNS.map((c) => c.key).filter((k) => !savedColOrder.value.includes(k));
savedColOrder.value = [...savedColOrder.value, ...missingOrder];

const savedColVisible = ref({ ...basePrefs.visible, ...(prefs?.visible && typeof prefs.visible === "object" ? prefs.visible : {}) });
for (const c of ALL_COLUMNS) {
  if (!(c.key in savedColVisible.value)) savedColVisible.value[c.key] = true;
}
savedColVisible.value.idx = true;
savedColVisible.value.actions = true;

function persistColumnPrefs() {
  localStorage.setItem(
    COLUMN_STORAGE_KEY,
    JSON.stringify({
      order: savedColOrder.value,
      visible: { ...savedColVisible.value }
    })
  );
}

const allColumnDefs = ALL_COLUMNS;

const visibleColumnsOrdered = computed(() => {
  const vis = savedColVisible.value;
  const order = savedColOrder.value;
  const map = new Map(ALL_COLUMNS.map((c) => [c.key, c]));
  return order.map((k) => map.get(k)).filter((c) => c && vis[c.key] !== false);
});

const store = useRedisQueryStore();

const editDialogVisible = ref(false);
const editMode = ref("create");
const editSaving = ref(false);
const editForm = reactive({
  id: null,
  name: "",
  redis_session_id: null,
  redis_key: "",
  color_step_percent: 10
});

const detailDialogVisible = ref(false);
const detailTaskId = ref(null);
const detailTitle = computed(() => {
  const t = store.tasks.find((x) => Number(x.id) === Number(detailTaskId.value));
  return t ? `历史：${t.name}` : "历史记录";
});
const detailLoading = ref(false);

const detailTableRows = computed(() => {
  const id = detailTaskId.value;
  if (id == null) return [];
  const list = store.taskHistory[String(id)] || [];
  return list.map((r) => ({
    ...r,
    displayValue: prettyValue(r.value)
  }));
});

const colSortDialogVisible = ref(false);
const colSortDraft = ref([]);
const colSortRef = ref(null);
let colSortable = null;

const colVisDialogVisible = ref(false);
const colVisDraft = ref([]);

const helpDialogVisible = ref(false);

function destroyColSortable() {
  if (colSortable) {
    colSortable.destroy();
    colSortable = null;
  }
}

function hexToRgb(hex) {
  const h = hex.replace("#", "");
  const n = parseInt(h, 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

function lerpHex(a, b, t) {
  const u = Math.max(0, Math.min(1, t));
  const A = hexToRgb(a);
  const B = hexToRgb(b);
  const r = Math.round(A.r + (B.r - A.r) * u);
  const g = Math.round(A.g + (B.g - A.g) * u);
  const bl = Math.round(A.b + (B.b - A.b) * u);
  return `rgb(${r},${g},${bl})`;
}

function rowStyle({ row }) {
  const pct = Number(row.color_step_percent) || 10;
  const maxSteps = Math.max(1, Math.floor(100 / pct));
  const level = Math.min(maxSteps, Number(row.change_count_since_seen) || 0);
  const t = maxSteps > 0 ? level / maxSteps : 0;
  return { backgroundColor: lerpHex("#52c41a", "#ff4d4f", t) };
}

function truncate(s, n) {
  if (s == null || s === "") return "";
  const t = String(s);
  return t.length > n ? `${t.slice(0, n)}…` : t;
}

function formatTime(raw) {
  if (!raw) return "";
  const s = String(raw).replace("T", " ");
  return s.length > 19 ? s.slice(0, 19) : s;
}

function hasValue(row) {
  return row.latest_value != null && String(row.latest_value).length > 0;
}

function prettyValue(raw) {
  if (raw == null) return "";
  const s = String(raw);
  try {
    const j = JSON.parse(s);
    return JSON.stringify(j, null, 2);
  } catch {
    return s;
  }
}

async function onValueClick(row) {
  if (!hasValue(row)) return;
  try {
    await store.markSeen(row.id);
    ElMessage.success("已标记为已关注");
  } catch (e) {
    ElMessage.error(e?.message || "操作失败");
  }
}

function openEdit(row) {
  editMode.value = "edit";
  editForm.id = row.id;
  editForm.name = row.name || "";
  editForm.redis_session_id = row.redis_session_id;
  editForm.redis_key = row.redis_key || "";
  editForm.color_step_percent = Number(row.color_step_percent) || 10;
  editDialogVisible.value = true;
}

async function openCreate() {
  try {
    await store.loadSessions();
  } catch {
    /* ignore */
  }
  if (!store.sessions.length) {
    ElMessage.warning("请先在顶部齿轮菜单中配置 Redis 连接");
    return;
  }
  editMode.value = "create";
  editForm.id = null;
  editForm.name = `Redis 任务 ${store.tasks.length + 1}`;
  editForm.redis_session_id = store.sessions[0]?.id ?? null;
  editForm.redis_key = "";
  editForm.color_step_percent = 10;
  editDialogVisible.value = true;
}

async function confirmEdit() {
  const name = String(editForm.name || "").trim();
  if (!name) {
    ElMessage.warning("请输入任务名称");
    return;
  }
  const key = String(editForm.redis_key || "").trim();
  if (!key) {
    ElMessage.warning("请输入 key");
    return;
  }
  if (editForm.redis_session_id == null) {
    ElMessage.warning("请选择 Redis 连接");
    return;
  }
  editSaving.value = true;
  try {
    if (editMode.value === "create") {
      const res = await createRedisTask({
        name,
        redis_session_id: editForm.redis_session_id,
        redis_key: key,
        color_step_percent: editForm.color_step_percent
      });
      if (res?.success === false) {
        ElMessage.error(res.error || "创建失败");
        return;
      }
      ElMessage.success("已创建");
    } else {
      const res = await updateRedisTask(editForm.id, {
        name,
        redis_session_id: editForm.redis_session_id,
        redis_key: key,
        color_step_percent: editForm.color_step_percent
      });
      if (res?.success === false) {
        ElMessage.error(res.error || "保存失败");
        return;
      }
      ElMessage.success("已保存");
    }
    editDialogVisible.value = false;
    await store.loadTasks();
    await persistTaskOrderFromTable();
  } catch (e) {
    ElMessage.error(e?.message || "保存失败");
  } finally {
    editSaving.value = false;
  }
}

async function persistTaskOrderFromTable() {
  const ids = store.tasks.map((t) => t.id);
  if (!ids.length) return;
  try {
    await orderRedisTasks(ids);
  } catch {
    /* ignore */
  }
}

async function removeTask(row) {
  try {
    await ElMessageBox.confirm("确定删除该查询任务？", "删除任务", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消"
    });
  } catch {
    return;
  }
  try {
    await deleteRedisTask(row.id);
    ElMessage.success("已删除");
    delete store.taskHistory[String(row.id)];
    await store.loadTasks();
  } catch (e) {
    ElMessage.error(e?.message || "删除失败");
  }
}

function openDetail(row) {
  detailTaskId.value = row.id;
  detailDialogVisible.value = true;
}

async function onDetailOpened() {
  if (detailTaskId.value == null) return;
  detailLoading.value = true;
  try {
    await store.loadTaskHistory(detailTaskId.value);
  } catch (e) {
    ElMessage.error(e?.message || "加载历史失败");
  } finally {
    detailLoading.value = false;
  }
}

async function reloadDetail() {
  await onDetailOpened();
  ElMessage.success("已刷新");
}

async function clearDetailHistory() {
  if (detailTaskId.value == null) return;
  try {
    await ElMessageBox.confirm("确定清空该任务的全部历史？", "清空历史", {
      type: "warning",
      confirmButtonText: "清空",
      cancelButtonText: "取消"
    });
  } catch {
    return;
  }
  try {
    await store.clearTaskHistory(detailTaskId.value);
    ElMessage.success("已清空");
  } catch (e) {
    ElMessage.error(e?.message || "清空失败");
  }
}

function detailSeq(index) {
  const n = detailTableRows.value.length;
  return n - index;
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text || "");
    ElMessage.success("已复制");
  } catch {
    ElMessage.error("复制失败");
  }
}

function onMenuCommand(cmd) {
  if (cmd === "add") {
    void openCreate();
  }
  else if (cmd === "refresh") refreshTasks();
  else if (cmd === "col-sort") openColSort();
  else if (cmd === "col-vis") openColVis();
  else if (cmd === "help") helpDialogVisible.value = true;
}

async function refreshTasks() {
  try {
    await store.loadTasks();
    await store.loadSessions();
    ElMessage.success("列表已刷新");
  } catch (e) {
    ElMessage.error(e?.message || "刷新失败");
  }
}

function openColSort() {
  const map = new Map(ALL_COLUMNS.map((c) => [c.key, c]));
  colSortDraft.value = savedColOrder.value.map((k) => map.get(k)).filter(Boolean).map((c) => ({ key: c.key, label: c.label }));
  colSortDialogVisible.value = true;
}

watch(colSortDialogVisible, async (open) => {
  if (!open) {
    destroyColSortable();
    return;
  }
  await nextTick();
  destroyColSortable();
  const el = colSortRef.value;
  if (!el) return;
  colSortable = Sortable.create(el, {
    animation: 150,
    handle: ".col-sort-handle",
    ghostClass: "tab-visibility-ghost",
    onEnd(evt) {
      const arr = colSortDraft.value;
      const moved = arr.splice(evt.oldIndex, 1)[0];
      arr.splice(evt.newIndex, 0, moved);
    }
  });
});

function applyColSort() {
  savedColOrder.value = colSortDraft.value.map((r) => r.key);
  persistColumnPrefs();
  colSortDialogVisible.value = false;
}

function openColVis() {
  colVisDraft.value = ALL_COLUMNS.filter((c) => savedColVisible.value[c.key] !== false).map((c) => c.key);
  colVisDialogVisible.value = true;
}

function applyColVis() {
  const set = new Set(colVisDraft.value);
  for (const c of ALL_COLUMNS) {
    savedColVisible.value[c.key] = set.has(c.key);
  }
  savedColVisible.value.idx = true;
  savedColVisible.value.actions = true;
  persistColumnPrefs();
  colVisDialogVisible.value = false;
}

onMounted(async () => {
  try {
    await store.loadSessions();
    await store.loadTasks();
  } catch {
    /* ignore */
  }
  store.connectEventSource();
});

onUnmounted(() => {
  store.disconnectEventSource();
});
</script>

<style scoped>
.redis-query-card :deep(.el-card__header) {
  padding: 12px 16px;
}
.redis-query-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.redis-query-title {
  font-weight: 600;
  font-size: 15px;
}
.redis-task-table {
  width: 100%;
}
.redis-key-cell {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
}
.redis-value-cell {
  cursor: default;
  word-break: break-all;
}
.redis-value-cell.is-clickable {
  cursor: pointer;
  color: var(--el-color-primary);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.color-step-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.color-step-help {
  font-weight: 700;
  color: var(--el-text-color-secondary);
}
.color-step-help-body p {
  margin: 0 0 8px;
  font-size: 13px;
  line-height: 1.55;
}
.color-step-help-body p:last-child {
  margin-bottom: 0;
}
.detail-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.history-value-cell {
  position: relative;
  padding-right: 40px;
}
.history-copy {
  position: absolute;
  right: 0;
  top: 0;
}
.history-value-text {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
}
.dialog-hint {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.col-sort-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.col-sort-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
}
.col-sort-handle {
  cursor: grab;
  color: var(--el-text-color-secondary);
  touch-action: none;
}
.col-sort-label {
  font-size: 14px;
}
.col-vis-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.help-body h4 {
  margin: 16px 0 8px;
  font-size: 14px;
}
.help-body h4:first-child {
  margin-top: 0;
}
.help-body p {
  margin: 0 0 8px;
  font-size: 13px;
  line-height: 1.55;
}
.help-pre {
  margin: 0 0 10px;
  padding: 10px 12px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  font-size: 12px;
  overflow-x: auto;
}
</style>
