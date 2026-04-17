<template>
  <el-card>
    <template #header>
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span>Shell 查询</span>
        <el-dropdown trigger="click" @command="onMenuCommand">
          <el-button :icon="Setting" />
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="add">新建查询任务</el-dropdown-item>
              <el-dropdown-item command="edit" :disabled="!current">编辑查询任务</el-dropdown-item>
              <el-dropdown-item command="delete" :disabled="!current || store.currentQueries.length <= 1" divided>
                删除查询任务
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </template>
    <div style="margin-bottom:8px;">
    </div>
    <el-tabs
      v-model="activeId"
      type="card"
      :closable="store.currentQueries.length > 1"
      @tab-remove="removeByTabName"
    >
      <el-tab-pane v-for="q in store.currentQueries" :key="q.id" :name="String(q.id)" :label="q.name" />
    </el-tabs>
    <template v-if="current">
      <el-input v-model="current.command" type="textarea" :rows="6" style="margin-top:8px;" placeholder="远程执行的 Shell 命令" />
      <div style="margin-top:8px;">
        <el-button @click="run">执行一次</el-button>
      </div>
      <h4 style="margin-top:12px;">完整输出</h4>
      <pre style="background:#111;color:#eaeaea;padding:8px;white-space:pre-wrap;">{{ output }}</pre>
    </template>
    <el-dialog v-model="editDialogVisible" title="编辑查询任务" width="560px" align-center>
      <el-form label-width="100px">
        <el-form-item label="任务名称">
          <el-input v-model="editName" placeholder="请输入任务名称" />
        </el-form-item>
        <el-form-item label="命令">
          <el-input v-model="editCommand" type="textarea" :rows="6" placeholder="远程执行的 Shell 命令" />
        </el-form-item>
        <el-form-item label="忽略模式">
          <el-input v-model="editIgnorePatterns" placeholder="差异对比时忽略的行（; 分隔）" />
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
import { useShellQueryStore } from "../stores/shellQueryStore";

const store = useShellQueryStore();
const activeId = ref("");
const current = computed(() => store.currentQueries.find((q) => String(q.id) === activeId.value));
const output = computed(() => (activeId.value ? store.shellResults[activeId.value]?.fullOutput || "" : ""));
const editDialogVisible = ref(false);
const editName = ref("");
const editCommand = ref("");
const editIgnorePatterns = ref("");

onMounted(async () => {
  await store.loadQueries();
  if (store.currentQueries.length) {
    activeId.value = String(store.currentQueries[0].id);
    await store.loadQueryHistory(activeId.value);
  }
});
async function add() {
  await store.addQuery({ name: `Shell任务 ${store.currentQueries.length + 1}`, command: "echo hello", ignore_patterns: "", is_active: 0, polling_interval: 60 });
  activeId.value = String(store.currentQueries[store.currentQueries.length - 1].id);
}
async function run() {
  if (!current.value) return;
  const id = current.value.id;
  await store.editQuery(id, { ...current.value, command: current.value.command || "" });
  activeId.value = String(id);
  await store.executeQueryOnce(id);
}
async function remove() {
  if (!current.value) return;
  if (store.currentQueries.length <= 1) {
    ElMessage.warning("至少保留一个 Shell 查询任务");
    return;
  }
  try {
    await store.removeQuery(current.value.id);
    activeId.value = store.currentQueries[0] ? String(store.currentQueries[0].id) : "";
  } catch (e) {
    ElMessage.error(e?.message || "删除失败");
  }
}
async function removeByTabName(name) {
  if (store.currentQueries.length <= 1) {
    ElMessage.warning("至少保留一个 Shell 查询任务");
    return;
  }
  try {
    await store.removeQuery(Number(name));
    if (String(activeId.value) === String(name)) {
      activeId.value = store.currentQueries[0] ? String(store.currentQueries[0].id) : "";
    }
  } catch (e) {
    ElMessage.error(e?.message || "删除失败");
  }
}
async function onMenuCommand(command) {
  if (command === "add") {
    await add();
    return;
  }
  if (command === "edit") {
    if (!current.value) return;
    editName.value = current.value.name || "";
    editCommand.value = current.value.command || "";
    editIgnorePatterns.value = current.value.ignore_patterns || "";
    editDialogVisible.value = true;
    return;
  }
  if (command === "delete") {
    if (!current.value || store.currentQueries.length <= 1) {
      if (store.currentQueries.length <= 1) ElMessage.warning("至少保留一个 Shell 查询任务");
      return;
    }
    await ElMessageBox.confirm("确认删除当前查询任务？", "提示", { type: "warning" });
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
  const command = String(editCommand.value || "").trim();
  if (!command) {
    ElMessage.warning("命令不能为空");
    return;
  }
  await store.editQuery(current.value.id, {
    ...current.value,
    name,
    command,
    ignore_patterns: editIgnorePatterns.value || ""
  });
  editDialogVisible.value = false;
}
</script>

