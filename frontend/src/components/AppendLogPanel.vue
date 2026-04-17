<template>
  <el-card :shadow="embedded ? 'never' : 'hover'" :class="{ 'append-log-card--embedded': embedded }">
    <template v-if="!embedded" #header>追加日志</template>
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="日志目录、前 N 行、后 M 行使用「配置管理」里已保存的值；搜索目标文本与追加时间范围可在本页单独填写（用于多抓一些额外关键字）。修改目录或上下文后请先保存配置。"
      class="append-hint"
    />
    <div class="append-toolbar">
      <el-button size="small" @click="loadSavedConfig">刷新预览</el-button>
    </div>
    <el-descriptions v-if="savedLogConfig" :column="1" border size="small" class="append-desc">
      <el-descriptions-item label="日志目录（来自配置）">{{ savedLogConfig.log_directory || "—" }}</el-descriptions-item>
      <el-descriptions-item label="前 N 行（来自配置）">{{ Number(savedLogConfig.context_lines_before ?? 0) }}</el-descriptions-item>
      <el-descriptions-item label="后 M 行（来自配置）">{{ Number(savedLogConfig.context_lines_after ?? 0) }}</el-descriptions-item>
      <el-descriptions-item label="追加后按内容去重">
        {{ Number(savedLogConfig.append_dedupe_same_content ?? 1) === 1 ? "是" : "否" }}
      </el-descriptions-item>
    </el-descriptions>
    <el-form label-width="160px" class="append-form">
      <el-form-item label="搜索目标文本">
        <el-input v-model="form.search_text" type="textarea" :rows="2" placeholder="可填写与配置不同的关键字；留空则使用配置中的搜索目标文本" />
      </el-form-item>
      <el-form-item label="追加的时间范围 (分钟)">
        <el-input-number v-model="form.append_time_range_minutes" :min="0" />
        <span class="append-form-tip">为 0 表示不按时间过滤；大于 0 时仅保留能从正文中解析出时间且在最近 N 分钟内的匹配</span>
      </el-form-item>
    </el-form>
    <el-button type="primary" :loading="appendLoading" class="append-run" @click="run">执行追加日志</el-button>

    <el-dialog
      v-model="appendDialogVisible"
      title="追加日志进度"
      width="600px"
      align-center
      :close-on-click-modal="false"
    >
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="目录与前 N/后 M 行来自已保存的配置；搜索关键字与追加时间范围以本页填写为准。"
        style="margin-bottom: 10px"
      />
      <div class="append-progress">
        <div class="append-progress-head">
          <span>扫描进度</span>
          <span>{{ appendTask.processed_files }}/{{ appendTask.total_files }} 个文件</span>
        </div>
        <el-progress
          :percentage="Number(appendTask.percentage || 0)"
          :status="appendTask.status === 'error' ? 'exception' : undefined"
        />
        <div class="append-progress-meta">
          <span v-if="appendTask.total_files > 0">当前第 {{ appendTask.processed_files }} / {{ appendTask.total_files }} 个</span>
          <span v-if="appendTask.current_file">{{ appendTask.current_file }}</span>
        </div>
        <div class="append-progress-foot">
          <span>已搜集日志：{{ Number(appendTask.total_matches || 0) }} 条</span>
          <span v-if="appendTask.status === 'cancelled'">状态：已停止</span>
          <span v-else-if="appendTask.status === 'completed'">状态：已完成</span>
          <span v-else-if="appendTask.status === 'error'">状态：失败</span>
          <span v-else>状态：进行中</span>
        </div>
      </div>
      <template #footer>
        <el-button
          type="danger"
          plain
          :disabled="!appendLoading || !appendTask.id || appendTask.status !== 'running'"
          @click="stopAppend"
        >
          停止
        </el-button>
        <el-button :disabled="appendLoading" @click="appendDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { ElMessage } from "element-plus";
import { onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { appendLogs, appendLogsProgress, cancelAppendLogs, getConfig } from "../api/api";

defineProps({
  /** 嵌入日志列表页标签内时不显示卡片标题「追加日志」，避免与 tab 重复 */
  embedded: { type: Boolean, default: false },
});

const savedLogConfig = ref(null);
const form = reactive({
  search_text: "",
  append_time_range_minutes: 0,
});
const appendLoading = ref(false);
const appendDialogVisible = ref(false);
const appendTask = reactive({
  id: "",
  status: "",
  total_files: 0,
  processed_files: 0,
  percentage: 0,
  current_file: "",
  total_matches: 0,
});
let appendTimer = null;

function syncEditableFromConfig() {
  const c = savedLogConfig.value;
  if (!c) return;
  form.search_text = String(c.search_text ?? "");
  form.append_time_range_minutes = Number(c.append_time_range_minutes ?? c.init_time_range_minutes ?? 0);
}

async function loadSavedConfig() {
  try {
    const res = await getConfig();
    savedLogConfig.value = res?.data || {};
  } catch (e) {
    ElMessage.error(e?.message || "读取配置失败");
  }
}

onMounted(async () => {
  await loadSavedConfig();
  syncEditableFromConfig();
});

onBeforeUnmount(() => {
  if (appendTimer) {
    clearInterval(appendTimer);
    appendTimer = null;
  }
});

async function run() {
  await loadSavedConfig();
  appendLoading.value = true;
  try {
    const res = await appendLogs({
      search_text: form.search_text,
      time_range_minutes: form.append_time_range_minutes,
    });
    const taskId = res?.data?.task_id || "";
    appendDialogVisible.value = true;
    appendTask.id = taskId;
    appendTask.status = "running";
    appendTask.total_files = 0;
    appendTask.processed_files = 0;
    appendTask.percentage = 0;
    appendTask.current_file = "";
    appendTask.total_matches = 0;
    if (appendTimer) clearInterval(appendTimer);
    appendTimer = setInterval(async () => {
      if (!appendTask.id) return;
      try {
        const p = await appendLogsProgress(appendTask.id);
        const data = p?.data || {};
        appendTask.status = data.status || "";
        appendTask.total_files = Number(data.total_files || 0);
        appendTask.processed_files = Number(data.processed_files || 0);
        appendTask.percentage = Number(data.percentage || 0);
        appendTask.current_file = data.current_file || "";
        appendTask.total_matches = Number(data.total_matches || 0);
        if (data.status === "completed") {
          clearInterval(appendTimer);
          appendTimer = null;
          appendLoading.value = false;
          ElMessage.success(`追加日志完成，共搜集到 ${appendTask.total_matches} 条日志`);
        } else if (data.status === "cancelled") {
          clearInterval(appendTimer);
          appendTimer = null;
          appendLoading.value = false;
          ElMessage.warning(`追加任务已停止，当前已搜集 ${appendTask.total_matches} 条日志`);
        } else if (data.status === "error") {
          clearInterval(appendTimer);
          appendTimer = null;
          appendLoading.value = false;
          ElMessage.error(data.error || "追加日志失败");
        }
      } catch (e) {
        clearInterval(appendTimer);
        appendTimer = null;
        appendLoading.value = false;
        ElMessage.error(e?.message || "读取追加进度失败");
      }
    }, 1000);
  } catch (e) {
    appendLoading.value = false;
    ElMessage.error(e?.message || "追加日志请求失败");
  }
}

async function stopAppend() {
  if (!appendTask.id || appendTask.status !== "running") return;
  try {
    await cancelAppendLogs(appendTask.id);
    ElMessage.info("已发送停止请求");
  } catch (e) {
    ElMessage.error(e?.message || "停止任务失败");
  }
}
</script>

<style scoped>
.append-log-card--embedded {
  border: none;
}
.append-log-card--embedded :deep(.el-card__body) {
  padding: 0;
}
.append-hint {
  margin-bottom: 12px;
}
.append-toolbar {
  margin-bottom: 10px;
}
.append-desc {
  margin-bottom: 16px;
}
.append-form {
  max-width: 640px;
}
.append-form-tip {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}
.append-run {
  margin-top: 4px;
}
.append-progress {
  margin-top: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;
}
.append-progress-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
}
.append-progress-meta {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.append-progress-foot {
  margin-top: 10px;
  display: flex;
  justify-content: space-between;
  font-size: 13px;
}
</style>
