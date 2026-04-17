<template>
  <div>
    <div class="toolbar">
      <el-button @click="$emit('refresh')">刷新</el-button>
      <el-button @click="batchEdit">批量备注</el-button>
      <el-input v-model="highlightInput" placeholder="高亮词，分号分隔" />
      <el-checkbox v-model="notesOnly" @change="onFilterChanged">仅展示有备注</el-checkbox>
      <el-checkbox v-model="showFilePath">展示文件路径</el-checkbox>
      <el-checkbox v-model="showPrintedAt">展示打印时间</el-checkbox>
    </div>
    <el-table :data="items" @selection-change="onSelectionChange">
      <el-table-column type="selection" width="50" />
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column v-if="showFilePath" prop="file_path" label="文件路径" width="220" />
      <el-table-column prop="line_number" label="行号" width="80" />
      <el-table-column v-if="showPrintedAt" prop="printed_at" label="打印时间" width="180" />
      <el-table-column label="日志内容">
        <template #default="{ row }">
          <pre class="log-pre" v-html="highlight(row.log_content)"></pre>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="160" width="200">
        <template #default="{ row }">
          <el-input
            class="notes-display"
            :model-value="normalizeNote(row.notes)"
            type="textarea"
            readonly
            :autosize="{ minRows: 2, maxRows: 8 }"
            placeholder="无"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" align="center" fixed="right">
        <template #default="{ row }">
          <div class="op-cell">
            <el-tooltip :content="row.notes ? '已有备注，点击编辑' : '编辑备注'" placement="left">
              <el-button
                class="note-edit-icon"
                text
                circle
                size="small"
                :type="row.notes && String(row.notes).trim() ? 'primary' : 'default'"
                @click="openNoteDialog(row)"
              >
                <el-icon :size="14"><EditPen /></el-icon>
              </el-button>
            </el-tooltip>
            <el-button class="op-delete" type="danger" size="small" link @click="() => remove(row)">
              删除
            </el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="noteDialogVisible"
      title="编辑备注"
      width="520px"
      destroy-on-close
      align-center
      @closed="onNoteDialogClosed"
    >
      <template v-if="noteDialogRow">
        <p class="note-dialog-meta">日志 ID：{{ noteDialogRow.id }}</p>
        <el-input
          v-model="noteDialogNotes"
          type="textarea"
          :autosize="{ minRows: 8, maxRows: 20 }"
          placeholder="在此填写或修改备注…"
        />
      </template>
      <template #footer>
        <el-button @click="noteDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="noteDialogSaving" @click="saveNoteDialog">保存</el-button>
      </template>
    </el-dialog>

    <el-pagination
      style="margin-top: 8px"
      :current-page="page"
      :page-size="pageSize"
      :total="total"
      :page-sizes="[10, 20, 50, 100, 200, 500]"
      layout="total, sizes, prev, pager, next"
      @size-change="(v) => $emit('update:pageSize', v)"
      @current-change="(v) => $emit('update:page', v)"
    />
  </div>
</template>

<script setup>
import { EditPen } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { ref, watch } from "vue";
import { bulkUpdateLogNotes, deleteLog, updateLogNotes } from "../api/api";

const props = defineProps({
  items: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  page: { type: Number, default: 1 },
  pageSize: { type: Number, default: 20 },
});
const emit = defineEmits(["refresh", "update:page", "update:pageSize", "update:notesOnly"]);

const selected = ref([]);
const notesOnly = ref(false);
const showFilePath = ref(true);
const showPrintedAt = ref(true);
const highlightInput = ref(localStorage.getItem("fastlog_highlight_input") || "");

const noteDialogVisible = ref(false);
const noteDialogRow = ref(null);
const noteDialogNotes = ref("");
const noteDialogSaving = ref(false);

watch(highlightInput, (v) => localStorage.setItem("fastlog_highlight_input", v));

function onSelectionChange(v) {
  selected.value = v;
}
function onFilterChanged() {
  emit("update:notesOnly", notesOnly.value);
}

function normalizeNote(v) {
  return v == null ? "" : String(v);
}

function openNoteDialog(row) {
  noteDialogRow.value = row;
  noteDialogNotes.value = normalizeNote(row.notes);
  noteDialogVisible.value = true;
}

function onNoteDialogClosed() {
  noteDialogRow.value = null;
  noteDialogNotes.value = "";
}

async function saveNoteDialog() {
  const row = noteDialogRow.value;
  if (!row) return;
  const draft = normalizeNote(noteDialogNotes.value);
  const prev = normalizeNote(row.notes);
  if (draft === prev) {
    ElMessage.info("备注无变更");
    noteDialogVisible.value = false;
    return;
  }
  noteDialogSaving.value = true;
  try {
    await updateLogNotes(row.id, draft);
    ElMessage.success("备注已保存");
    noteDialogVisible.value = false;
    emit("refresh");
  } catch (e) {
    ElMessage.error(e?.message || "保存备注失败");
  } finally {
    noteDialogSaving.value = false;
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm("确定删除该条日志？此操作不可恢复。", "删除确认", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }
  try {
    await deleteLog(row.id);
    ElMessage.success("已删除");
    emit("refresh");
  } catch (e) {
    ElMessage.error(e?.message || "删除失败");
  }
}

async function batchEdit() {
  if (!selected.value.length) return;
  try {
    await bulkUpdateLogNotes({
      log_ids: selected.value.map((i) => i.id),
      notes: "批量备注",
      append: true,
      only_empty: false,
    });
    ElMessage.success("批量备注已更新");
    emit("refresh");
  } catch (e) {
    ElMessage.error(e?.message || "批量备注失败");
  }
}

function highlight(txt = "") {
  let out = txt.replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const words = highlightInput.value
    .split(";")
    .map((i) => i.trim())
    .filter(Boolean);
  words.forEach((w) => {
    out = out.replaceAll(w, `<mark>${w}</mark>`);
  });
  return out;
}
</script>

<style scoped>
.toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.log-pre {
  white-space: pre-wrap;
  max-height: 200px;
  overflow: auto;
  margin: 0;
}
.note-edit-icon {
  padding: 0;
  min-height: auto;
  height: auto;
}
.notes-display :deep(.el-textarea__inner) {
  cursor: default;
  resize: none;
  background-color: var(--el-fill-color-light);
}
.op-cell {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  flex-wrap: nowrap;
  gap: 2px;
}
.op-delete {
  font-size: 12px;
  padding: 0 2px;
}
.note-dialog-meta {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
