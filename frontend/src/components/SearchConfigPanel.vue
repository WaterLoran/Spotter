<template>
  <el-card :shadow="embedded ? 'never' : 'hover'" :class="{ 'search-config-card--embedded': embedded }">
    <template v-if="!embedded" #header>多搜索配置</template>
    <div style="margin-bottom: 8px">
      <el-button type="primary" @click="createCfg">新增配置</el-button>
      <el-button @click="executeAll">执行启用配置</el-button>
    </div>
    <el-table :data="items">
      <el-table-column prop="id" label="ID" width="72" />
      <el-table-column prop="log_directory" label="日志目录" min-width="160" show-overflow-tooltip />
      <el-table-column prop="search_text" label="搜索文本" min-width="120" show-overflow-tooltip />
      <el-table-column label="前 N 行" width="88">
        <template #default="{ row }">{{ Number(row.context_lines_before ?? 0) }}</template>
      </el-table-column>
      <el-table-column label="后 M 行" width="88">
        <template #default="{ row }">{{ Number(row.context_lines_after ?? 0) }}</template>
      </el-table-column>
      <el-table-column label="启用" width="90">
        <template #default="{ row }">
          <el-switch :model-value="!!row.enabled" @change="(v) => toggle(row, v)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog
      v-model="editVisible"
      title="编辑搜索配置"
      width="520px"
      align-center
      destroy-on-close
      @closed="resetEditForm"
    >
      <el-form ref="editFormRef" :model="editForm" label-width="120px">
        <el-form-item label="日志目录" prop="log_directory" :rules="[{ required: true, message: '请填写日志目录' }]">
          <el-input v-model="editForm.log_directory" placeholder="远程服务器上的日志目录" />
        </el-form-item>
        <el-form-item label="搜索文本" prop="search_text" :rules="[{ required: true, message: '请填写搜索文本' }]">
          <el-input v-model="editForm.search_text" type="textarea" :rows="3" placeholder="支持分号分隔多个关键字（需同时匹配）" />
        </el-form-item>
        <el-form-item label="前 N 行">
          <el-input-number v-model="editForm.context_lines_before" :min="0" />
        </el-form-item>
        <el-form-item label="后 M 行">
          <el-input-number v-model="editForm.context_lines_after" :min="0" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { ElMessage, ElMessageBox } from "element-plus";
import { onMounted, reactive, ref } from "vue";
import { createSearchConfig, deleteSearchConfig, executeSearchConfigs, listSearchConfigs, updateSearchConfig } from "../api/api";

defineProps({
  /** 嵌入日志列表页子标签内时不显示卡片标题，避免与 tab 重复 */
  embedded: { type: Boolean, default: false },
});

const items = ref([]);
const editVisible = ref(false);
const editSaving = ref(false);
const editFormRef = ref(null);
const editForm = reactive({
  id: null,
  log_directory: "",
  search_text: "",
  context_lines_before: 0,
  context_lines_after: 0,
});

async function load() {
  const res = await listSearchConfigs();
  items.value = res.data || [];
}

function openEdit(row) {
  editForm.id = row.id;
  editForm.log_directory = row.log_directory ?? "";
  editForm.search_text = row.search_text ?? "";
  editForm.context_lines_before = Number(row.context_lines_before ?? 0);
  editForm.context_lines_after = Number(row.context_lines_after ?? 0);
  editVisible.value = true;
}

function resetEditForm() {
  editForm.id = null;
  editForm.log_directory = "";
  editForm.search_text = "";
  editForm.context_lines_before = 0;
  editForm.context_lines_after = 0;
}

async function submitEdit() {
  const form = editFormRef.value;
  if (!form) return;
  try {
    await form.validate();
  } catch {
    return;
  }
  if (!editForm.id) return;
  editSaving.value = true;
  try {
    await updateSearchConfig(editForm.id, {
      log_directory: editForm.log_directory.trim(),
      search_text: editForm.search_text.trim(),
      context_lines_before: Number(editForm.context_lines_before) || 0,
      context_lines_after: Number(editForm.context_lines_after) || 0,
    });
    ElMessage.success("配置已保存");
    editVisible.value = false;
    await load();
  } catch (e) {
    ElMessage.error(e?.message || "保存失败");
  } finally {
    editSaving.value = false;
  }
}

async function createCfg() {
  const list = items.value || [];
  const last = list.length ? list[list.length - 1] : null;
  const payload = last
    ? {
        log_directory: last.log_directory ?? "/var/log",
        search_text: last.search_text ?? "",
        init_time_range_minutes: Number(last.init_time_range_minutes ?? 120),
        context_lines_before: 0,
        context_lines_after: 0,
        enabled: 0,
      }
    : {
        log_directory: "/var/log",
        search_text: "error",
        init_time_range_minutes: 120,
        context_lines_before: 0,
        context_lines_after: 0,
        enabled: 0,
      };
  await createSearchConfig(payload);
  await load();
}

async function toggle(row, v) {
  await updateSearchConfig(row.id, { enabled: v ? 1 : 0 });
  await load();
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除搜索配置 ID ${row.id} 吗？删除后不可恢复。`,
      "删除搜索配置",
      {
        type: "warning",
        confirmButtonText: "确定删除",
        cancelButtonText: "取消",
      }
    );
  } catch {
    return;
  }
  try {
    await deleteSearchConfig(row.id);
    ElMessage.success("已删除该配置");
    await load();
  } catch (e) {
    ElMessage.error(e?.message || "删除失败");
  }
}

async function executeAll() {
  await executeSearchConfigs();
}

onMounted(load);
</script>

<style scoped>
.search-config-card--embedded {
  border: none;
}
.search-config-card--embedded :deep(.el-card__body) {
  padding: 0;
}
</style>
