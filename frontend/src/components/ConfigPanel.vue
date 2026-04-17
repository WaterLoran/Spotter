<template>
  <el-card
    :shadow="embedded ? 'never' : 'always'"
    :class="{ 'config-panel--embedded': embedded }"
  >
    <template v-if="!embedded" #header>配置管理</template>
    <el-form label-width="140px">
      <el-form-item label="日志搜集">
        <el-checkbox v-model="mainLogCollectionEnabled">
          启用日志搜集（主配置：定时增量采集当前日志目录）
        </el-checkbox>
        <div class="config-panel-hint">
          仅控制上方主配置路径的定时任务；与「多搜索配置」里各条规则的启用开关相互独立。
        </div>
      </el-form-item>
      <el-form-item label="服务器地址"><el-input v-model="form.server_host" /></el-form-item>
      <el-form-item label="服务器账号"><el-input v-model="form.server_username" /></el-form-item>
      <el-form-item label="服务器密码"><el-input v-model="form.server_password" type="password" show-password /></el-form-item>
      <el-form-item label="服务器端口"><el-input v-model="form.server_port" /></el-form-item>
      <el-form-item label="日志目录"><el-input v-model="form.log_directory" /></el-form-item>
      <el-form-item label="搜索目标文本"><el-input v-model="form.search_text" /></el-form-item>
      <el-form-item label="初始化范围分钟">
        <el-input v-model="form.init_time_range_minutes" />
        <div class="config-panel-hint">
          仅作用于本页主配置：大于 0 时，初始化 / 重新初始化按命中行时间在 [文件 mtime − N 分钟, 文件 mtime] 内过滤；定时增量不按此项过滤。「多搜索配置」各条规则自带初始化范围，与这里无关。
        </div>
      </el-form-item>
      <el-form-item label="前N行"><el-input v-model="form.context_lines_before" /></el-form-item>
      <el-form-item label="后M行"><el-input v-model="form.context_lines_after" /></el-form-item>
    </el-form>
    <div class="config-panel-actions">
      <el-button type="primary" @click="save">保存配置</el-button>
      <el-button type="success" :loading="applyLoading" @click="saveAndApply">保存并启动采集</el-button>
      <el-button @click="check">测试连接</el-button>
      <el-button :loading="reinitLoading" @click="reinit">重新初始化</el-button>
      <el-button :loading="dedupeLoading" @click="dedupe">去重</el-button>
      <el-button type="danger" @click="clearAll">删除所有日志</el-button>
    </div>
    <div v-if="daemonRunning" class="config-panel-daemon-status">
      <el-tag type="success" effect="light" size="small">日志采集运行中</el-tag>
      <span class="config-panel-hint">后台正以当前配置持续采集目标日志，每隔数秒自动执行一次。</span>
    </div>
    <el-dialog
      v-model="reinitDialogVisible"
      title="重新初始化进度"
      width="600px"
      align-center
      :close-on-click-modal="false"
    >
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="将根据当前配置进行初始化（服务器、目录、搜索关键字、上下文范围等）。"
        style="margin-bottom: 10px"
      />
      <div class="reinit-progress">
        <div class="reinit-progress-head">
          <span>初始化进度</span>
          <span>{{ reinitTask.processed_files }}/{{ reinitTask.total_files }} 个文件</span>
        </div>
        <el-progress
          :percentage="Number(reinitTask.percentage || 0)"
          :status="reinitTask.status === 'error' ? 'exception' : undefined"
        />
        <div class="reinit-progress-meta">
          <span v-if="reinitTask.total_files > 0">当前第 {{ reinitTask.processed_files }} / {{ reinitTask.total_files }} 个</span>
          <span v-if="reinitTask.current_file">{{ reinitTask.current_file }}</span>
        </div>
        <div class="reinit-progress-foot">
          <span>已搜集日志：{{ Number(reinitTask.total_matches || 0) }} 条</span>
          <span v-if="reinitTask.status === 'cancelled'">状态：已停止</span>
          <span v-else-if="reinitTask.status === 'completed'">状态：已完成</span>
          <span v-else-if="reinitTask.status === 'error'">状态：失败</span>
          <span v-else>状态：进行中</span>
        </div>
      </div>
      <template #footer>
        <el-button
          type="danger"
          plain
          :disabled="!reinitLoading || !reinitTask.id || reinitTask.status !== 'running'"
          @click="stopReinit"
        >
          停止
        </el-button>
        <el-button :disabled="reinitLoading" @click="reinitDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { ElMessage, ElMessageBox } from "element-plus";
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import {
  applyConfig,
  deleteAllLogs,
  dedupeLogsByContent,
  getConfig,
  listBackgroundTasks,
  cancelReinitialize,
  reinitialize,
  reinitializeProgress,
  testConnection,
  updateConfig,
} from "../api/api";

defineProps({
  embedded: { type: Boolean, default: false },
});

const emit = defineEmits(["reinitialized", "logs-cleared"]);

const form = reactive({});

/** 与 form.main_log_collection_enabled（"1"/"0"）同步，默认未写入库时视为开启 */
const mainLogCollectionEnabled = computed({
  get() {
    const v = form.main_log_collection_enabled;
    if (v === undefined || v === null || v === "") return true;
    return String(v) !== "0";
  },
  set(on) {
    form.main_log_collection_enabled = on ? "1" : "0";
  },
});

const reinitLoading = ref(false);
const dedupeLoading = ref(false);
const reinitDialogVisible = ref(false);
const reinitTask = reactive({
  id: "",
  status: "",
  total_files: 0,
  processed_files: 0,
  percentage: 0,
  current_file: "",
  total_matches: 0,
});
let reinitTimer = null;

onMounted(async () => {
  const [cfgRes, taskRes] = await Promise.all([getConfig(), listBackgroundTasks()]);
  Object.assign(form, cfgRes.data || {});
  daemonRunning.value = taskRes?.data?.scheduler_running ?? false;
});

onBeforeUnmount(() => {
  if (reinitTimer) {
    clearInterval(reinitTimer);
    reinitTimer = null;
  }
});

const applyLoading = ref(false);
const daemonRunning = ref(false);

async function save() {
  await updateConfig(form);
  ElMessage.success("配置已保存");
}

async function saveAndApply() {
  applyLoading.value = true;
  try {
    const res = await applyConfig(form);
    daemonRunning.value = res?.data?.scheduler_running ?? false;
    ElMessage.success(res?.message || "配置已保存，日志采集已启动");
  } catch (e) {
    ElMessage.error(e?.message || "保存并启动采集失败");
  } finally {
    applyLoading.value = false;
  }
}
async function check() {
  const res = await testConnection(form);
  if (res?.success && res?.data?.ok) {
    ElMessage.success("SSH 连接成功");
    return;
  }
  const detail = res?.data?.error || res?.error || "";
  ElMessage.error(detail ? `SSH 连接失败：${detail}` : "SSH 连接失败");
}
async function reinit() {
  try {
    await ElMessageBox.confirm(
      "重新初始化会清除本地的所有日志数据，确认继续吗？",
      "危险操作确认",
      {
        type: "warning",
        confirmButtonText: "确定并初始化",
        cancelButtonText: "取消",
      }
    );
  } catch {
    return;
  }

  reinitLoading.value = true;
  try {
    const res = await reinitialize();
    const taskId = res?.data?.task_id || "";
    reinitDialogVisible.value = true;
    reinitTask.id = taskId;
    reinitTask.status = "running";
    reinitTask.total_files = 0;
    reinitTask.processed_files = 0;
    reinitTask.percentage = 0;
    reinitTask.current_file = "";
    reinitTask.total_matches = 0;
    if (reinitTimer) clearInterval(reinitTimer);
    reinitTimer = setInterval(async () => {
      if (!reinitTask.id) return;
      try {
        const p = await reinitializeProgress(reinitTask.id);
        const data = p?.data || {};
        reinitTask.status = data.status || "";
        reinitTask.total_files = Number(data.total_files || 0);
        reinitTask.processed_files = Number(data.processed_files || 0);
        reinitTask.percentage = Number(data.percentage || 0);
        reinitTask.current_file = data.current_file || "";
        reinitTask.total_matches = Number(data.total_matches || 0);
        if (data.status === "completed") {
          clearInterval(reinitTimer);
          reinitTimer = null;
          reinitLoading.value = false;
          ElMessage.success(`重新初始化完成，共搜集到 ${reinitTask.total_matches} 条日志`);
          emit("reinitialized");
        } else if (data.status === "cancelled") {
          clearInterval(reinitTimer);
          reinitTimer = null;
          reinitLoading.value = false;
          ElMessage.warning(`初始化任务已停止，当前已搜集 ${reinitTask.total_matches} 条日志`);
        } else if (data.status === "error") {
          clearInterval(reinitTimer);
          reinitTimer = null;
          reinitLoading.value = false;
          ElMessage.error(data.error || "重新初始化失败");
        }
      } catch (e) {
        clearInterval(reinitTimer);
        reinitTimer = null;
        reinitLoading.value = false;
        ElMessage.error(e?.message || "读取初始化进度失败");
      }
    }, 1000);
  } catch (e) {
    reinitLoading.value = false;
    ElMessage.error(e?.message || "初始化请求失败");
  }
}
async function stopReinit() {
  if (!reinitTask.id || reinitTask.status !== "running") return;
  try {
    await cancelReinitialize(reinitTask.id);
    ElMessage.info("已发送停止请求");
  } catch (e) {
    ElMessage.error(e?.message || "停止任务失败");
  }
}
const DEDUPE_EXPLAIN =
  "作用范围：仅「当前系统」下本地数据库中已搜集的日志，不会改动远程服务器上的文件。\n\n" +
  "分组规则：按「日志正文」完全一致分为一组（与文件路径、行号无关）。\n\n" +
  "删除规则：\n" +
  "· 若某一组内至少有一条填写过备注：保留该组中所有带备注的记录，删除同组内其余无备注的重复记录。\n" +
  "· 若某一组内全部没有备注：只保留 id 最小（最先入库）的一条，删除同组内其余重复记录。\n\n" +
  "全文检索索引会随删除自动更新。确定执行去重吗？";

async function dedupe() {
  try {
    await ElMessageBox.confirm(DEDUPE_EXPLAIN, "按正文去重说明", {
      type: "warning",
      confirmButtonText: "开始去重",
      cancelButtonText: "取消",
      distinguishCancelAndClose: true,
    });
  } catch {
    return;
  }
  dedupeLoading.value = true;
  try {
    const res = await dedupeLogsByContent();
    const n = res?.data?.deleted;
    if (typeof n === "number") {
      ElMessage.success(n === 0 ? "没有可去重的重复日志" : `去重完成，已删除 ${n} 条重复记录`);
    } else {
      ElMessage.success(res?.message || "去重完成");
    }
  } catch (e) {
    ElMessage.error(e?.message || "去重失败");
  } finally {
    dedupeLoading.value = false;
  }
}
async function clearAll() {
  try {
    await ElMessageBox.confirm(
      "将删除当前系统下本地数据库中已搜集的全部日志记录（不会删除远程服务器上的原始日志文件）。本地读取进度会重置，定时任务将重新从文件开头扫描并再次匹配关键字。此操作不可恢复，是否继续？",
      "删除所有日志",
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
    const res = await deleteAllLogs();
    const n = res?.data?.deleted;
    if (typeof n === "number") {
      ElMessage.success(`已删除本地 ${n} 条日志`);
    } else {
      ElMessage.success(res?.message || "已删除本地全部日志");
    }
    emit("logs-cleared");
  } catch (e) {
    ElMessage.error(e?.message || "删除失败");
  }
}
</script>

<style scoped>
.config-panel-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.45;
  max-width: 520px;
}
.config-panel-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.reinit-progress {
  margin-top: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;
}
.reinit-progress-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
}
.reinit-progress-meta {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.reinit-progress-foot {
  margin-top: 10px;
  display: flex;
  justify-content: space-between;
  font-size: 13px;
}
.config-panel-daemon-status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}
.config-panel--embedded {
  border: none;
  box-shadow: none;
}
.config-panel--embedded :deep(.el-card__body) {
  padding: 0;
}
</style>
