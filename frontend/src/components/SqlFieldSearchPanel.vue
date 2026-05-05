<template>
  <el-card>
    <template #header>
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span>字段搜索</span>
        <el-dropdown trigger="click" @command="onMenuCommand">
          <el-button :icon="Setting" />
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="add">新建字段搜索任务</el-dropdown-item>
              <el-dropdown-item command="edit" :disabled="!current">编辑字段搜索任务</el-dropdown-item>
              <el-dropdown-item command="delete" :disabled="!current || tasks.length <= 1" divided>
                删除字段搜索任务
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </template>
    <el-tabs v-model="activeId" type="card" :closable="tasks.length > 1" @tab-remove="removeByTabName">
      <el-tab-pane v-for="t in tasks" :key="t.id" :name="String(t.id)" :label="t.name" />
    </el-tabs>
    <template v-if="current">
      <el-input v-model="current.expression" placeholder="表达式，例如 f_id = 1000204" style="margin-top:8px;" />
      <div class="field-search-actions">
        <div class="field-search-value-match">
          <el-switch v-model="includeValueMatch" />
          <span class="field-search-value-match-label">开启全库值匹配</span>
        </div>
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
        <el-button :loading="searching" @click="run">执行搜索</el-button>
      </div>
      <div v-if="orderedTableResults.length" class="search-result-wrap">
        <div class="search-result-summary">
          <span>共扫描 {{ orderedTableResults.length }} 张表</span>
          <span>命中 {{ hitTableCount }} 张表</span>
        </div>
        <el-collapse v-model="expandedTables">
          <el-collapse-item
            v-for="item in orderedTableResults"
            :key="item.table"
            :name="item.table"
          >
            <template #title>
              <div class="table-title-row">
                <span class="table-name">{{ item.table }}</span>
                <el-tag :type="item.hasHit ? 'success' : 'info'" size="small">
                  {{ item.hasHit ? `命中 ${item.hitCount} 条` : "无命中" }}
                </el-tag>
              </div>
            </template>
            <div v-if="item.hasHit">
              <el-table
                :data="item.rows"
                border
                stripe
                size="small"
                style="width: 100%"
                :cell-style="(p) => tableCellStyle(p, item)"
                :header-cell-style="(p) => tableHeaderCellStyle(p, item)"
              >
                <el-table-column
                  v-for="col in item.columns"
                  :key="`${item.table}-${col}`"
                  :prop="col"
                  :label="col"
                  min-width="120"
                  show-overflow-tooltip
                />
              </el-table>
            </div>
            <el-empty v-else description="该表未匹配到结果" :image-size="60" />
          </el-collapse-item>
        </el-collapse>
      </div>
      <el-empty v-else description="暂无搜索结果，请先执行搜索" :image-size="80" />
    </template>
    <el-dialog v-model="editDialogVisible" title="编辑字段搜索任务" width="560px" align-center>
      <el-form label-width="100px">
        <el-form-item label="任务名称">
          <el-input v-model="editName" placeholder="请输入任务名称" />
        </el-form-item>
        <el-form-item label="表达式">
          <el-input v-model="editExpression" placeholder="例如 id = 1" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmEdit">保存</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { Setting } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  createFieldSearchTask,
  deleteFieldSearchTask,
  executeFieldSearch,
  fieldSearchBackground,
  listFieldSearchTasks,
  updateFieldSearchTask
} from "../api/sqlFieldSearch";
import { listSqlSessions, normalizeSqlSessionsData } from "../api/sqlSessions";

const tasks = ref([]);
const sessionsForSelect = ref([]);
const activeId = ref("");
const includeValueMatch = ref(false);
const resultIncludeValueMatch = ref(false);
const searchResult = ref(null);
const expandedTables = ref([]);
const searching = ref(false);
const current = computed(() => tasks.value.find((t) => String(t.id) === activeId.value));
const sessionOptions = computed(() => {
  const list = sessionsForSelect.value || [];
  const t = current.value;
  if (!t?.session_id) return list;
  if (!list.some((s) => s.id === t.session_id)) {
    return [
      ...list,
      { id: t.session_id, name: `已绑定 #${t.session_id}`, db_type: "mysql", _orphan: true }
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
    await updateFieldSearchTask(current.value.id, {
      ...current.value,
      session_id: current.value.session_id,
      expression: current.value.expression || ""
    });
    ElMessage.success("已切换数据库配置");
  } catch (e) {
    ElMessage.error(e?.message || "保存失败");
  }
}
const editDialogVisible = ref(false);
const editName = ref("");
const editExpression = ref("");
const orderedTableResults = computed(() => {
  const result = searchResult.value || {};
  const scanned = Array.isArray(result.scanned_tables) ? result.scanned_tables : [];
  const exact = Array.isArray(result.exact_matches) ? result.exact_matches : [];
  const valueMatches = Array.isArray(result.value_matches) ? result.value_matches : [];
  const byTable = new Map();
  for (const table of scanned) {
    byTable.set(String(table), { table: String(table), rows: [] });
  }
  for (const m of [...exact, ...valueMatches]) {
    const table = String(m?.table || "");
    if (!table) continue;
    if (!byTable.has(table)) byTable.set(table, { table, rows: [] });
    const target = byTable.get(table);
    const rows = Array.isArray(m.rows) ? m.rows : Array.isArray(m.sample_rows) ? m.sample_rows : [];
    target.rows.push(...rows);
  }
  const merged = [...byTable.values()].map((item) => {
    const dedupRows = [];
    const seen = new Set();
    for (const row of item.rows) {
      const key = JSON.stringify(row);
      if (seen.has(key)) continue;
      seen.add(key);
      dedupRows.push(row);
    }
    const colSet = new Set();
    for (const row of dedupRows) {
      Object.keys(row || {}).forEach((k) => colSet.add(k));
    }
    const targetColumns = new Set();
    for (const m of exact) {
      if (String(m?.table || "") === item.table && m?.column) {
        targetColumns.add(String(m.column));
      }
    }
    return {
      table: item.table,
      rows: dedupRows,
      columns: [...colSet],
      targetColumns,
      hasHit: dedupRows.length > 0,
      hitCount: dedupRows.length,
    };
  });
  return merged.sort((a, b) => {
    if (a.hasHit !== b.hasHit) return a.hasHit ? -1 : 1;
    return a.table.localeCompare(b.table);
  });
});
const hitTableCount = computed(() => orderedTableResults.value.filter((i) => i.hasHit).length);

async function load() {
  await loadSessionsForSelect();
  const res = await listFieldSearchTasks();
  tasks.value = res.data || [];
  if (tasks.value.length && !activeId.value) activeId.value = String(tasks.value[0].id);
}
async function createTaskAction() {
  await loadSessionsForSelect();
  const firstSid = sessionsForSelect.value[0]?.id;
  if (firstSid == null) {
    ElMessage.warning("请先在右上角齿轮中配置至少一份数据库连接（Mysql 或 Pgsql）");
    return;
  }
  await createFieldSearchTask({
    name: `字段搜索 ${tasks.value.length + 1}`,
    expression: "id = 1",
    session_id: firstSid
  });
  await load();
}
async function remove() {
  if (!current.value) return;
  if (tasks.value.length <= 1) {
    ElMessage.warning("至少保留一个字段搜索任务");
    return;
  }
  await deleteFieldSearchTask(current.value.id);
  await load();
}
async function removeByTabName(name) {
  if (tasks.value.length <= 1) {
    ElMessage.warning("至少保留一个字段搜索任务");
    return;
  }
  await deleteFieldSearchTask(Number(name));
  await load();
}
async function run() {
  if (!current.value || current.value.session_id == null) return;
  await updateFieldSearchTask(current.value.id, { ...current.value, expression: current.value.expression || "" });
  searching.value = true;
  resultIncludeValueMatch.value = includeValueMatch.value;
  try {
    const res = await executeFieldSearch(current.value.session_id, {
      expression: current.value.expression,
      include_value_match: includeValueMatch.value
    });
    const data = res?.data || {};
    if (data.background && data.job_id) {
      searchResult.value = null;
      const maxRounds = 120;
      for (let i = 0; i < maxRounds; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        const p = await fieldSearchBackground(data.job_id);
        const status = p?.data?.status;
        if (status === "completed") {
          searchResult.value = p?.data?.result || null;
          expandedTables.value = orderedTableResults.value.filter((it) => it.hasHit).map((it) => it.table);
          ElMessage.success("全库值匹配完成");
          return;
        }
        if (status === "error") {
          ElMessage.error(p?.data?.error || "全库值匹配失败");
          return;
        }
      }
      ElMessage.warning("全库值匹配超时，请稍后重试");
      return;
    }
    searchResult.value = data.result || null;
    expandedTables.value = orderedTableResults.value.filter((i) => i.hasHit).map((i) => i.table);
  } finally {
    searching.value = false;
  }
}

function parseExpressionTarget(expression) {
  const raw = String(expression || "");
  const idx = raw.indexOf("=");
  if (idx < 0) return { field: "", value: "" };
  const field = raw.slice(0, idx).trim();
  let value = raw.slice(idx + 1).trim();
  if ((value.startsWith("'") && value.endsWith("'")) || (value.startsWith("\"") && value.endsWith("\""))) {
    value = value.slice(1, -1);
  }
  return { field, value };
}

function valueEqualsTarget(cellValue, target) {
  if (target === "") return false;
  if (cellValue === null || cellValue === undefined) return false;
  const text = String(cellValue);
  if (text === target) return true;
  const n = Number(target);
  if (!Number.isNaN(n) && typeof cellValue === "number") return cellValue === n;
  return false;
}

function tableCellStyle({ row, column }, item) {
  if (!item) return {};
  if (!resultIncludeValueMatch.value) {
    if (item.targetColumns?.has(column.property)) {
      return { backgroundColor: "#fff7e6" };
    }
    return {};
  }
  const targetValue = parseExpressionTarget(searchResult.value?.expression || current.value?.expression).value;
  if (valueEqualsTarget(row?.[column.property], targetValue)) {
    return { backgroundColor: "#e6f7ff" };
  }
  return {};
}

function tableHeaderCellStyle({ column }, item) {
  if (resultIncludeValueMatch.value) return {};
  if (item?.targetColumns?.has(column.property)) {
    return { backgroundColor: "#ffe7ba" };
  }
  return {};
}
async function onMenuCommand(command) {
  if (command === "add") {
    await createTaskAction();
    return;
  }
  if (command === "edit") {
    if (!current.value) return;
    editName.value = current.value.name || "";
    editExpression.value = current.value.expression || "";
    editDialogVisible.value = true;
    return;
  }
  if (command === "delete") {
    if (!current.value || tasks.value.length <= 1) {
      if (tasks.value.length <= 1) ElMessage.warning("至少保留一个字段搜索任务");
      return;
    }
    await ElMessageBox.confirm("确认删除当前字段搜索任务？", "提示", { type: "warning" });
    await remove();
  }
}
async function confirmEdit() {
  if (!current.value) return;
  const name = String(editName.value || "").trim();
  if (!name) {
    ElMessage.warning("任务名称不能为空");
    return;
  }
  const expression = String(editExpression.value || "").trim();
  if (!expression) {
    ElMessage.warning("表达式不能为空");
    return;
  }
  await updateFieldSearchTask(current.value.id, { ...current.value, name, expression });
  editDialogVisible.value = false;
  await load();
}
onMounted(load);
</script>

<style scoped>
.search-result-wrap {
  margin-top: 12px;
}
.search-result-summary {
  margin-bottom: 8px;
  display: flex;
  gap: 12px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.table-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.table-name {
  font-weight: 500;
}
.field-search-actions {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px;
  row-gap: 8px;
}
.field-search-value-match {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.field-search-value-match-label {
  font-size: 13px;
  color: var(--el-text-color-regular);
  white-space: nowrap;
}
.sql-task-session {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.sql-task-session-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}
.sql-task-session-select {
  width: 220px;
}
</style>

