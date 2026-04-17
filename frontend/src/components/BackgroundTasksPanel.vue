<template>
  <el-card>
    <template #header>后台任务监控</template>
    <div style="margin-bottom:8px;">
      <el-button @click="load">刷新</el-button>
    </div>
    <el-descriptions :column="1" border>
      <el-descriptions-item label="日志增量更新运行中">{{ data.scheduler_running ? "是" : "否" }}</el-descriptions-item>
      <el-descriptions-item label="主配置轮询间隔(秒)">{{ data.scheduler_interval }}</el-descriptions-item>
      <el-descriptions-item label="多搜索全量扫描间隔(秒)">{{ data.scheduler_search_config_interval ?? "—" }}</el-descriptions-item>
      <el-descriptions-item label="上次调度完成时间">{{ data.last_scheduler_tick_at ?? "—" }}</el-descriptions-item>
      <el-descriptions-item label="上轮主配置新入库行数">{{ data.last_main_inserted_total ?? 0 }}</el-descriptions-item>
      <el-descriptions-item label="上轮是否执行多搜索扫描">{{ data.last_tick_ran_search_configs ? "是" : "否" }}</el-descriptions-item>
      <el-descriptions-item label="最近调度错误">{{ data.last_scheduler_error ?? "—" }}</el-descriptions-item>
      <el-descriptions-item label="错误关联系统 ID">{{ data.last_scheduler_error_system_id ?? "—" }}</el-descriptions-item>
      <el-descriptions-item label="错误发生时间">{{ data.last_scheduler_error_at ?? "—" }}</el-descriptions-item>
    </el-descriptions>
    <h4>Shell轮询任务</h4>
    <el-table :data="data.shell_polling_tasks || []">
      <el-table-column prop="id" label="ID" />
      <el-table-column prop="name" label="名称" />
      <el-table-column prop="seconds" label="间隔" />
      <el-table-column prop="status" label="状态" />
      <el-table-column prop="last_executed_at" label="最后执行时间" />
    </el-table>
  </el-card>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from "vue";
import { listBackgroundTasks } from "../api/api";

const data = ref({ scheduler_running: false, scheduler_interval: 0, shell_polling_tasks: [] });
let timer = null;
async function load() {
  const res = await listBackgroundTasks();
  data.value = res.data || data.value;
}
onMounted(async () => {
  await load();
  timer = setInterval(load, 10000);
});
onUnmounted(() => {
  if (timer) clearInterval(timer);
});
</script>

