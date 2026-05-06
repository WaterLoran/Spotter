<template>
  <el-card class="api-query-card">
    <template #header>
      <div class="api-query-card-header">
        <span class="api-query-title">API 查询</span>
        <el-dropdown trigger="click" @command="onMenuCommand">
          <el-button :icon="Setting" circle title="操作" />
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="add">新建查询任务</el-dropdown-item>
              <el-dropdown-item command="refresh" divided>刷新任务列表</el-dropdown-item>
              <el-dropdown-item command="edit" :disabled="!current">编辑任务</el-dropdown-item>
              <el-dropdown-item command="save" :disabled="!current">保存当前任务</el-dropdown-item>
              <el-dropdown-item command="delete" :disabled="!current">删除当前任务</el-dropdown-item>
              <el-dropdown-item command="headers" divided>获取 Header 的代码</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </template>

    <el-tabs v-model="activeId" type="card" @tab-change="onTabChange">
      <el-tab-pane v-for="q in store.currentTasks" :key="q.id" :name="String(q.id)" :label="q.name" />
    </el-tabs>
    <el-empty v-if="!store.currentTasks.length" description="暂无查询任务，请点击右上角齿轮菜单新建" />
    <template v-else-if="current">
      <el-container class="api-query-layout" direction="horizontal">
        <el-aside width="268px" class="api-history-aside">
          <div class="api-history-title">执行历史</div>
          <el-scrollbar class="api-history-scroll">
            <el-tree
              v-if="historyTreeData.length"
              :key="historyTreeRenderKey"
              ref="historyTreeRef"
              class="api-history-tree"
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
                    <el-tag v-if="data.statusCode != null" size="small" type="info" effect="plain">
                      {{ data.statusCode }}
                    </el-tag>
                    <el-tag v-if="data.isDifferent" type="warning" size="small" effect="plain">变化</el-tag>
                  </div>
                  <el-button type="danger" link size="small" @click.stop="removeHistoryItem(data.id)">删除</el-button>
                </div>
              </template>
            </el-tree>
            <el-empty v-else description="暂无执行记录" :image-size="56" />
          </el-scrollbar>
        </el-aside>
        <el-main class="api-query-main">
          <el-collapse v-model="apiInfoCollapseActive" class="api-info-collapse">
            <el-collapse-item name="api-info">
              <template #title>
                <span class="api-info-collapse-title">API信息</span>
              </template>
          <el-form label-width="96px" class="api-task-form">
            <el-form-item label="方法">
              <el-select v-model="current.method" style="width: 140px">
                <el-option label="GET" value="GET" />
                <el-option label="POST" value="POST" />
                <el-option label="PUT" value="PUT" />
                <el-option label="PATCH" value="PATCH" />
                <el-option label="DELETE" value="DELETE" />
              </el-select>
            </el-form-item>
            <el-form-item label="URL">
              <el-input v-model="current.url" placeholder="https://..." />
            </el-form-item>
            <el-form-item label="Query 参数">
              <el-table :data="queryParamsTable" border size="small" class="api-params-table">
                <el-table-column label="启用" width="64" align="center">
                  <template #default="{ row }">
                    <el-checkbox v-model="row.enabled" />
                  </template>
                </el-table-column>
                <el-table-column label="键">
                  <template #default="{ row }">
                    <el-input v-model="row.key" placeholder="key" />
                  </template>
                </el-table-column>
                <el-table-column label="值">
                  <template #default="{ row }">
                    <el-input v-model="row.value" placeholder="value" />
                  </template>
                </el-table-column>
                <el-table-column label="" width="100" align="center">
                  <template #default="{ $index }">
                    <el-button type="danger" link size="small" @click="removeQueryParamRow($index)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
              <el-button class="api-add-param" size="small" @click="addQueryParamRow">添加参数</el-button>
            </el-form-item>
            <el-form-item label="Body 类型">
              <div class="body-type-row">
                <el-select v-model="current.body_type" style="width: 200px">
                  <el-option label="无" value="none" />
                  <el-option label="JSON" value="json" />
                  <el-option label="Form (x-www-form-urlencoded)" value="form" />
                  <el-option label="Form Data (multipart)" value="form-data" />
                  <el-option label="原始文本" value="raw" />
                </el-select>
                <el-popover
                  placement="right-start"
                  :width="380"
                  trigger="click"
                >
                  <template #reference>
                    <el-button circle size="small" class="body-type-help-btn" title="Body 类型说明">?</el-button>
                  </template>
                  <div class="body-type-help">
                    <div class="body-type-help-title">Body 类型说明</div>
                    <div class="body-type-help-item">
                      <span class="body-type-help-label">无 (none)</span>
                      <p>不发送请求体，适用于 GET、DELETE 等不需要携带数据的请求。</p>
                    </div>
                    <div class="body-type-help-item">
                      <span class="body-type-help-label">JSON</span>
                      <p>以 <code>application/json</code> 格式发送请求体。在请求体中填写合法的 JSON 对象或数组，例如：</p>
                      <pre class="body-type-help-pre">{"key": "value", "page": 1}</pre>
                    </div>
                    <div class="body-type-help-item">
                      <span class="body-type-help-label">Form (x-www-form-urlencoded)</span>
                      <p>以表单键值对格式发送，Content-Type 为 <code>application/x-www-form-urlencoded</code>。在请求体中填写 <code>key=value</code> 格式，多个参数用 <code>&amp;</code> 分隔，例如：</p>
                      <pre class="body-type-help-pre">username=admin&password=123456</pre>
                    </div>
                    <div class="body-type-help-item">
                      <span class="body-type-help-label">Form Data (multipart/form-data)</span>
                      <p>以多部分表单格式发送，Content-Type 为 <code>multipart/form-data</code>，浏览器上传文件时常用此格式。通过下方表格直接添加键值对字段，勾选"启用"控制是否发送该字段。</p>
                    </div>
                    <div class="body-type-help-item">
                      <span class="body-type-help-label">原始文本 (raw)</span>
                      <p>以纯文本形式发送请求体，Content-Type 为 <code>text/plain</code>。适用于 XML、自定义格式或任意文本内容，例如：</p>
                      <pre class="body-type-help-pre">&lt;xml&gt;&lt;id&gt;1&lt;/id&gt;&lt;/xml&gt;</pre>
                    </div>
                  </div>
                </el-popover>
              </div>
            </el-form-item>
            <el-form-item v-if="current.body_type === 'form-data'" label="请求体">
              <div style="width: 100%">
                <el-table :data="formDataTable" border size="small" class="api-params-table">
                  <el-table-column label="启用" width="64" align="center">
                    <template #default="{ row }">
                      <el-checkbox v-model="row.enabled" @change="syncFormDataToBody" />
                    </template>
                  </el-table-column>
                  <el-table-column label="键">
                    <template #default="{ row }">
                      <el-input v-model="row.key" placeholder="key" @input="syncFormDataToBody" />
                    </template>
                  </el-table-column>
                  <el-table-column label="值">
                    <template #default="{ row }">
                      <el-input v-model="row.value" placeholder="value" @input="syncFormDataToBody" />
                    </template>
                  </el-table-column>
                  <el-table-column label="" width="100" align="center">
                    <template #default="{ $index }">
                      <el-button type="danger" link size="small" @click="removeFormDataRow($index)">删除</el-button>
                    </template>
                  </el-table-column>
                </el-table>
                <el-button class="api-add-param" size="small" @click="addFormDataRow">添加字段</el-button>
              </div>
            </el-form-item>
            <el-form-item v-else-if="current.body_type !== 'none'" label="请求体">
              <el-input v-model="current.body" type="textarea" :rows="4" placeholder="JSON 对象或原始内容" />
            </el-form-item>
            <el-form-item label="Header 代码">
              <el-select
                v-model="headerSnippetModel"
                clearable
                placeholder="不附加"
                style="width: 100%; max-width: 420px"
              >
                <el-option
                  v-for="h in store.headerSnippets"
                  :key="h.id"
                  :label="h.name"
                  :value="String(h.id)"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="超时 (秒)">
              <el-input-number v-model="current.timeout" :min="1" :max="300" controls-position="right" />
            </el-form-item>
          </el-form>
            </el-collapse-item>
          </el-collapse>

          <div class="api-query-actions">
            <el-button type="primary" @click="run">执行一次</el-button>
            <el-checkbox
              :model-value="Boolean(current.is_active)"
              class="api-poll-checkbox"
              @change="onPollEnabledChange"
            >
              定时执行
            </el-checkbox>
            <span class="api-poll-interval">
              <el-input-number
                v-model="current.polling_interval"
                :min="1"
                :max="3600"
                :disabled="!Boolean(current.is_active)"
                controls-position="right"
                class="api-poll-interval-input"
                @change="onPollIntervalChange"
              />
              <span class="api-poll-interval-unit">秒</span>
            </span>
            <el-button @click="save">保存任务</el-button>
            <el-button type="danger" @click="remove">删除任务</el-button>
          </div>

          <div v-if="selectedHistory" class="api-result-toolbar">
            <el-radio-group v-model="resultViewMode" size="small">
              <el-radio-button value="table" :disabled="!canTableView">表格</el-radio-button>
              <el-radio-button value="json">JSON</el-radio-button>
              <el-radio-button value="raw">原始</el-radio-button>
            </el-radio-group>
            <el-tag v-if="selectedHistory.error" type="danger" size="small" effect="plain">
              {{ selectedHistory.error }}
            </el-tag>
          </div>

          <div v-if="selectedHistory" class="api-result-body">
            <el-table
              v-if="resultViewMode === 'table'"
              :key="tableRenderKey"
              :data="tableRowsForView"
              border
              stripe
              style="margin-top: 8px"
            >
              <el-table-column
                v-for="c in tableColumns"
                :key="c"
                :prop="c"
                :label="c"
                min-width="100"
                show-overflow-tooltip
              />
            </el-table>
            <div v-else-if="resultViewMode === 'json'" class="api-json-viewer">
              <div class="api-json-lines">
                <div v-for="(line, idx) in jsonViewerLines" :key="idx" class="api-json-line">{{ line }}</div>
              </div>
            </div>
            <pre v-else class="api-response-pre">{{ rawViewText }}</pre>
          </div>
          <el-empty v-else description="执行后将在此展示响应" :image-size="56" />
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

    <el-dialog
      v-model="headerDialogVisible"
      title="获取 Header 的代码"
      width="920px"
      destroy-on-close
      align-center
      @opened="onHeaderDialogOpened"
    >
      <el-container class="header-dialog-layout">
        <el-aside width="220px" class="header-snippet-aside">
          <div class="header-snippet-aside-title">代码列表</div>
          <el-scrollbar class="header-snippet-scroll">
            <div
              v-for="h in store.headerSnippets"
              :key="h.id"
              class="header-snippet-row"
              :class="{ active: selectedHeaderId === h.id }"
              @click="selectHeader(h.id)"
            >
              {{ h.name }}
            </div>
            <el-empty v-if="!store.headerSnippets.length" description="暂无条目" :image-size="48" />
          </el-scrollbar>
          <div class="header-snippet-aside-actions">
            <el-button size="small" type="primary" @click="createHeaderSnippet">新建</el-button>
            <el-button size="small" type="danger" plain :disabled="!selectedHeaderId" @click="deleteHeaderSnippet">
              删除
            </el-button>
          </div>
        </el-aside>
        <el-main class="header-snippet-main">
          <template v-if="selectedHeaderId">
            <el-form label-width="100px">
              <el-form-item label="名称">
                <el-input v-model="headerDraft.name" maxlength="100" show-word-limit />
              </el-form-item>
              <el-form-item label="TTL (秒)">
                <el-input-number v-model="headerDraft.ttl_seconds" :min="1" :max="86400" controls-position="right" />
              </el-form-item>
              <el-form-item label="Python 代码">
                <el-input
                  v-model="headerDraft.code"
                  type="textarea"
                  :rows="16"
                  class="header-code-input"
                  placeholder="新建时会填入默认示例；可改为 headers={...} 或 def get_headers(): return {...}"
                />
              </el-form-item>
            </el-form>
            <div class="header-snippet-actions">
              <el-button type="primary" @click="saveHeaderSnippet">保存</el-button>
              <el-button @click="testHeaderSnippet">测试</el-button>
            </div>
            <div v-if="headerPreviewError" class="header-preview-error">{{ headerPreviewError }}</div>
            <div v-if="headerPreviewOk" class="header-preview-label">计算得到的 headers：</div>
            <pre v-if="headerPreviewOk" class="header-preview-pre">{{ headerPreviewOk }}</pre>
          </template>
          <el-empty v-else description="请新建或选择一条 Header 代码" />
        </el-main>
      </el-container>
      <template #footer>
        <el-button @click="headerDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { Setting } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { extractTableRows, useApiQueryStore } from "../stores/apiQueryStore";

/** 新建「获取 Header 的代码」时的默认名称与示例代码 */
const DEFAULT_HEADER_SNIPPET_NAME = "get_headers_demo";
const DEFAULT_HEADER_SNIPPET_CODE = 'headers={"token":"Spotter is the best testTool"}\n';

const store = useApiQueryStore();

/** 与已有条目名称去重；冲突时在名称后追加时间戳 */
function uniqueNewHeaderSnippetName(baseName) {
  const names = new Set((store.headerSnippets || []).map((h) => String(h.name ?? "").trim()));
  const trimmed = String(baseName ?? "").trim() || DEFAULT_HEADER_SNIPPET_NAME;
  if (!names.has(trimmed)) return trimmed;
  let candidate = `${trimmed}_${Date.now()}`;
  while (names.has(candidate)) {
    candidate = `${trimmed}_${Date.now()}`;
  }
  return candidate;
}
const API_INFO_COLLAPSE_KEY = "spotter_api_query_api_info_expanded";

function loadApiInfoCollapseActive() {
  try {
    if (localStorage.getItem(API_INFO_COLLAPSE_KEY) === "0") return [];
  } catch {
    /* ignore */
  }
  return ["api-info"];
}

const activeId = ref("");
/** 折叠面板已展开的名称列表；含 api-info 表示「API信息」展开 */
const apiInfoCollapseActive = ref(loadApiInfoCollapseActive());
const tableRenderKey = ref(0);
const historyTreeRef = ref(null);
const editDialogVisible = ref(false);
const editTaskName = ref("");
const headerDialogVisible = ref(false);
const selectedHeaderId = ref(null);
const headerDraft = reactive({ name: "", ttl_seconds: 300, code: "" });
const headerPreviewOk = ref("");
const headerPreviewError = ref("");
const resultViewMode = ref("table");

const current = computed(() => store.currentTasks.find((q) => String(q.id) === activeId.value));

const headerSnippetModel = computed({
  get() {
    const id = current.value?.header_snippet_id;
    return id == null ? "" : String(id);
  },
  set(v) {
    if (!current.value) return;
    current.value.header_snippet_id = v === "" || v == null ? null : Number(v);
  }
});

const queryParamsTable = computed(() => {
  const q = current.value;
  if (!q) return [];
  return Array.isArray(q.query_params) ? q.query_params : [];
});

function parseFormDataBody(raw) {
  if (!raw || !raw.trim()) return [];
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed;
  } catch {
    // ignore
  }
  return [];
}

const formDataTable = computed(() => {
  const q = current.value;
  if (!q) return [];
  return parseFormDataBody(q.body);
});

function syncFormDataToBody() {
  if (!current.value) return;
  current.value.body = JSON.stringify(formDataTable.value);
}

function addFormDataRow() {
  if (!current.value) return;
  const rows = parseFormDataBody(current.value.body);
  rows.push({ key: "", value: "", enabled: true });
  current.value.body = JSON.stringify(rows);
}

function removeFormDataRow(index) {
  if (!current.value) return;
  const rows = parseFormDataBody(current.value.body);
  rows.splice(index, 1);
  current.value.body = JSON.stringify(rows);
}

const bucket = computed(() => (activeId.value ? store.taskResults[activeId.value] : null));

const selectedHistory = computed(() => {
  const b = bucket.value;
  if (!b?.history?.length) return null;
  const hid = b.currentHistoryId;
  const hit = (b.history || []).find((h) => h.id === hid);
  return hit || b.history[0];
});

const tableRowsForView = computed(() => extractTableRows(selectedHistory.value?.response_data));

const tableColumns = computed(() => {
  const rows = tableRowsForView.value;
  return rows[0] ? Object.keys(rows[0]) : [];
});

const canTableView = computed(() => tableRowsForView.value.length > 0);

/** 前端格式化 JSON：从对象或 response_text 解析后 stringify，再按行渲染（每行 nowrap，避免整段 pre 在布局里被错误断行） */
const jsonViewerLines = computed(() => {
  const h = selectedHistory.value;
  if (!h) return [];
  const stringifyLines = (val) => {
    try {
      return JSON.stringify(val, null, 2).split("\n");
    } catch {
      return [String(val)];
    }
  };
  if (h.response_data !== undefined && h.response_data !== null) {
    return stringifyLines(h.response_data);
  }
  const text = (h.response_text || "").trim();
  if (!text) return [];
  try {
    return stringifyLines(JSON.parse(text));
  } catch {
    return text.split("\n");
  }
});

const rawViewText = computed(() => selectedHistory.value?.response_text || "");

watch([canTableView, selectedHistory], () => {
  if (resultViewMode.value === "table" && !canTableView.value) {
    resultViewMode.value = "json";
  }
});

watch(
  apiInfoCollapseActive,
  (arr) => {
    try {
      localStorage.setItem(API_INFO_COLLAPSE_KEY, Array.isArray(arr) && arr.includes("api-info") ? "1" : "0");
    } catch {
      /* ignore */
    }
  },
  { deep: true }
);

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
  const res = await store.patchTaskPolling(current.value.id, {
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
    const b = store.taskResults[key];
    const viewingOld =
      Boolean(b?.history?.length) &&
      b.currentHistoryId != null &&
      b.history[0]?.id !== b.currentHistoryId;
    store.executeTaskOnce(id).then((res) => {
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
  const list = store.taskResults[activeId.value]?.history || [];
  const n = list.length;
  return list.map((h, i) => {
    const indexLabel = n - i;
    return {
      id: h.id,
      label: `#${indexLabel} ${formatExecutedAt(h.executed_at)}`,
      indexLabel,
      executedAt: formatExecutedAt(h.executed_at),
      isDifferent: Boolean(h.is_different),
      statusCode: h.status_code
    };
  });
});

const historyTreeRenderKey = computed(() => {
  const list = store.taskResults[activeId.value]?.history || [];
  return list.map((h) => h.id).join(",");
});

watch(
  () => {
    const b = activeId.value ? store.taskResults[activeId.value] : null;
    return [activeId.value, b?.currentHistoryId, historyTreeRenderKey.value];
  },
  () => {
    const id = activeId.value ? store.taskResults[activeId.value]?.currentHistoryId : null;
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
  await store.loadHeaderSnippets();
  await refreshList({ silent: true });
});

async function refreshList({ silent } = {}) {
  await store.loadTasks();
  if (!store.currentTasks.length) {
    activeId.value = "";
    return;
  }
  const ids = new Set(store.currentTasks.map((q) => String(q.id)));
  if (!activeId.value || !ids.has(activeId.value)) {
    activeId.value = String(store.currentTasks[0].id);
  }
  const t = store.currentTasks.find((q) => String(q.id) === activeId.value);
  if (t && !Array.isArray(t.query_params)) t.query_params = [];
  await store.loadTaskHistory(activeId.value);
  if (!silent) ElMessage.success("列表已刷新");
}

async function onTabChange(name) {
  const t = store.currentTasks.find((q) => String(q.id) === String(name));
  if (t && !Array.isArray(t.query_params)) t.query_params = [];
  await store.loadTaskHistory(String(name));
}

function onMenuCommand(cmd) {
  if (cmd === "add") add();
  else if (cmd === "refresh") refreshList({ silent: false });
  else if (cmd === "edit") openEditDialog();
  else if (cmd === "save") save();
  else if (cmd === "delete") remove();
  else if (cmd === "headers") openHeaderDialog();
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
    const res = await store.editTask(current.value.id, { name });
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

function openHeaderDialog() {
  headerPreviewOk.value = "";
  headerPreviewError.value = "";
  headerDialogVisible.value = true;
}

async function onHeaderDialogOpened() {
  await store.loadHeaderSnippets();
  if (store.headerSnippets.length) {
    selectedHeaderId.value = store.headerSnippets[0].id;
    syncHeaderDraftFromStore();
  } else {
    selectedHeaderId.value = null;
  }
}

function syncHeaderDraftFromStore() {
  const h = store.headerSnippets.find((x) => x.id === selectedHeaderId.value);
  if (!h) return;
  headerDraft.name = h.name || "";
  headerDraft.ttl_seconds = Number(h.ttl_seconds) || 300;
  headerDraft.code = h.code || "";
}

function selectHeader(id) {
  selectedHeaderId.value = id;
  headerPreviewOk.value = "";
  headerPreviewError.value = "";
  syncHeaderDraftFromStore();
}

watch(selectedHeaderId, () => {
  if (headerDialogVisible.value && selectedHeaderId.value) syncHeaderDraftFromStore();
});

async function createHeaderSnippet() {
  try {
    const res = await store.addHeaderSnippet({
      name: uniqueNewHeaderSnippetName(DEFAULT_HEADER_SNIPPET_NAME),
      code: DEFAULT_HEADER_SNIPPET_CODE,
      ttl_seconds: 300
    });
    if (res?.success === false) {
      ElMessage.error(res.error || "新建失败");
      return;
    }
    const newId = res?.data?.id;
    await store.loadHeaderSnippets();
    if (newId) selectedHeaderId.value = newId;
    else if (store.headerSnippets.length)
      selectedHeaderId.value = store.headerSnippets[store.headerSnippets.length - 1].id;
    syncHeaderDraftFromStore();
    ElMessage.success("已新建");
  } catch (e) {
    ElMessage.error(e?.message || "新建失败");
  }
}

async function deleteHeaderSnippet() {
  if (!selectedHeaderId.value) return;
  try {
    await ElMessageBox.confirm("确定删除该条 Header 代码？", "删除", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消"
    });
  } catch {
    return;
  }
  try {
    await store.removeHeaderSnippet(selectedHeaderId.value);
    headerPreviewOk.value = "";
    headerPreviewError.value = "";
    selectedHeaderId.value = store.headerSnippets[0]?.id ?? null;
    if (selectedHeaderId.value) syncHeaderDraftFromStore();
    ElMessage.success("已删除");
  } catch (e) {
    ElMessage.error(e?.message || "删除失败");
  }
}

async function saveHeaderSnippet() {
  if (!selectedHeaderId.value) return;
  try {
    const res = await store.saveHeaderSnippet(selectedHeaderId.value, {
      name: headerDraft.name,
      ttl_seconds: headerDraft.ttl_seconds,
      code: headerDraft.code
    });
    if (res?.success === false) {
      ElMessage.error(res.error || "保存失败");
      return;
    }
    await store.loadHeaderSnippets();
    ElMessage.success("已保存");
  } catch (e) {
    ElMessage.error(e?.message || "保存失败");
  }
}

async function testHeaderSnippet() {
  if (!selectedHeaderId.value) return;
  headerPreviewOk.value = "";
  headerPreviewError.value = "";
  try {
    const res = await store.previewHeader(selectedHeaderId.value);
    if (!res?.success) {
      headerPreviewError.value = res?.error || "执行失败";
      return;
    }
    headerPreviewOk.value = JSON.stringify(res.data?.headers || {}, null, 2);
  } catch (e) {
    headerPreviewError.value = e?.message || "执行失败";
  }
}

function addQueryParamRow() {
  if (!current.value) return;
  if (!Array.isArray(current.value.query_params)) current.value.query_params = [];
  current.value.query_params.push({ key: "", value: "", enabled: true });
}

function removeQueryParamRow(index) {
  if (!current.value || !Array.isArray(current.value.query_params)) return;
  current.value.query_params.splice(index, 1);
}

async function add() {
  try {
    await store.addTask({
      name: `API 任务 ${store.currentTasks.length + 1}`,
      method: "GET",
      url: "",
      query_params: [],
      body_type: "none",
      body: "",
      header_snippet_id: null,
      timeout: 30,
      polling_interval: 60,
      is_active: false
    });
    activeId.value = String(store.currentTasks[store.currentTasks.length - 1].id);
    await store.loadTaskHistory(activeId.value);
    ElMessage.success("已新建查询任务");
  } catch (e) {
    ElMessage.error(e?.message || "新建失败");
  }
}

function buildTaskPayload() {
  const c = current.value;
  if (!c) return {};
  const qp = Array.isArray(c.query_params) ? c.query_params : [];
  return {
    name: c.name,
    method: c.method,
    url: c.url,
    query_params: qp,
    body_type: c.body_type,
    body: c.body,
    header_snippet_id: c.header_snippet_id,
    timeout: c.timeout,
    polling_interval: c.polling_interval,
    is_active: c.is_active
  };
}

async function save() {
  if (!current.value) return;
  try {
    const res = await store.editTask(current.value.id, buildTaskPayload());
    if (res?.success === false) ElMessage.error(res.error || "保存失败");
    else ElMessage.success("已保存");
  } catch (e) {
    ElMessage.error(e?.message || "保存失败");
  }
}

async function run() {
  if (!current.value) return;
  try {
    const saveRes = await store.editTask(current.value.id, buildTaskPayload());
    if (saveRes?.success === false) {
      ElMessage.error(saveRes.error || "保存失败");
      return;
    }
    const res = await store.executeTaskOnce(current.value.id, { respectHistorySelection: false });
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
    await store.removeTask(current.value.id);
    ElMessage.success("已删除");
    activeId.value = store.currentTasks[0] ? String(store.currentTasks[0].id) : "";
    if (activeId.value) await store.loadTaskHistory(activeId.value);
  } catch (e) {
    ElMessage.error(e?.message || "删除失败");
  }
}
</script>

<style scoped>
.api-query-card :deep(.el-card__header) {
  padding: 12px 16px;
}
.api-query-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.api-query-title {
  font-weight: 600;
  font-size: 15px;
}
.api-query-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 12px;
  margin-top: 8px;
}
.api-poll-checkbox {
  margin-left: 4px;
  white-space: nowrap;
}
.api-poll-interval {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.api-poll-interval-input {
  width: 120px;
}
.api-poll-interval-unit {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
.api-query-layout {
  margin-top: 8px;
  align-items: stretch;
  min-height: 280px;
}
.api-history-aside {
  border-right: 1px solid var(--el-border-color-lighter);
  padding-right: 12px;
  margin-right: 12px;
  flex-shrink: 0;
}
.api-history-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}
.api-history-scroll {
  max-height: 480px;
}
.api-history-tree {
  background: transparent;
}
.api-history-tree :deep(.el-tree-node__content) {
  height: auto;
  min-height: 32px;
  align-items: flex-start;
  padding: 4px 0;
}
.api-query-main {
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
.api-info-collapse {
  border: none;
  --el-collapse-border-color: var(--el-border-color-lighter);
}
.api-info-collapse :deep(.el-collapse-item__header) {
  padding-left: 0;
  padding-right: 8px;
  height: 40px;
  line-height: 40px;
  font-size: 14px;
  background: transparent;
}
.api-info-collapse :deep(.el-collapse-item__arrow) {
  margin: 0 6px 0 0;
}
.api-info-collapse-title {
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.api-info-collapse :deep(.el-collapse-item__wrap) {
  border: none;
  background: transparent;
}
.api-info-collapse :deep(.el-collapse-item__content) {
  padding: 8px 0 4px;
}
.api-task-form {
  margin-top: 0;
}
.body-type-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.body-type-help-btn {
  flex-shrink: 0;
  font-weight: 700;
  color: var(--el-text-color-secondary);
}
.api-params-table {
  width: 100%;
}
.api-add-param {
  margin-top: 8px;
}
.api-result-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  flex-wrap: wrap;
}
.api-result-body {
  margin-top: 4px;
  min-width: 0;
}
.api-json-viewer {
  margin: 8px 0 0;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  max-height: 420px;
  overflow: auto;
  min-width: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
  line-height: 1.5;
}
.api-json-lines {
  display: block;
  width: max-content;
  min-width: 100%;
  box-sizing: border-box;
}
.api-json-line {
  white-space: pre;
  word-break: keep-all;
  overflow-wrap: normal;
}
.api-response-pre {
  margin: 8px 0 0;
  padding: 12px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.45;
  overflow: auto;
  max-height: 420px;
  white-space: pre;
  word-break: normal;
  overflow-wrap: normal;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  tab-size: 2;
}
.header-dialog-layout {
  min-height: 420px;
}
.header-snippet-aside {
  border-right: 1px solid var(--el-border-color-lighter);
  padding-right: 12px;
  margin-right: 12px;
  display: flex;
  flex-direction: column;
}
.header-snippet-aside-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}
.header-snippet-scroll {
  flex: 1;
  max-height: 360px;
}
.header-snippet-row {
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  margin-bottom: 4px;
}
.header-snippet-row:hover {
  background: var(--el-fill-color-light);
}
.header-snippet-row.active {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 600;
}
.header-snippet-aside-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}
.header-snippet-main {
  padding: 0 0 0 8px;
}
.header-code-input :deep(textarea) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 12px;
}
.header-snippet-actions {
  margin-bottom: 12px;
}
.header-preview-error {
  color: var(--el-color-danger);
  font-size: 13px;
  margin: 8px 0;
}
.header-preview-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 8px;
}
.header-preview-pre {
  margin: 4px 0 0;
  padding: 10px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  font-size: 12px;
  max-height: 200px;
  overflow: auto;
}
</style>

<style>
.body-type-help {
  font-size: 13px;
  line-height: 1.6;
}
.body-type-help-title {
  font-weight: 700;
  font-size: 14px;
  margin-bottom: 10px;
  color: var(--el-text-color-primary);
}
.body-type-help-item {
  margin-bottom: 12px;
}
.body-type-help-item:last-child {
  margin-bottom: 0;
}
.body-type-help-label {
  display: inline-block;
  font-weight: 600;
  color: var(--el-color-primary);
  margin-bottom: 2px;
}
.body-type-help-item p {
  margin: 2px 0 4px;
  color: var(--el-text-color-regular);
}
.body-type-help-item code {
  background: var(--el-fill-color);
  border-radius: 3px;
  padding: 1px 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  color: var(--el-color-danger);
}
.body-type-help-pre {
  margin: 0;
  padding: 7px 10px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12px;
  overflow-x: auto;
  white-space: pre;
  color: var(--el-text-color-primary);
}
</style>
