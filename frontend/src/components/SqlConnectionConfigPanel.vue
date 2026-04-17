<template>
  <el-card
    :shadow="embedded ? 'never' : 'always'"
    :class="{ 'sql-connection-panel--embedded': embedded }"
  >
    <template v-if="!embedded" #header>SQL连接配置</template>
    <el-form label-width="100px">
      <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="类型">
        <el-select v-model="form.db_type"><el-option label="MySQL" value="mysql" /><el-option label="PostgreSQL" value="pgsql" /></el-select>
      </el-form-item>
      <el-form-item label="Host"><el-input v-model="form.host" /></el-form-item>
      <el-form-item label="端口"><el-input-number v-model="form.port" :min="1" /></el-form-item>
      <el-form-item label="用户名"><el-input v-model="form.username" /></el-form-item>
      <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password /></el-form-item>
      <el-form-item label="数据库"><el-input v-model="form.database" /></el-form-item>
    </el-form>
    <div class="sql-connection-panel-actions">
      <el-button type="primary" @click="save">保存连接</el-button>
      <el-button @click="test">测试连接</el-button>
    </div>
  </el-card>
</template>

<script setup>
import { ElMessage } from "element-plus";
import { onMounted, reactive } from "vue";
import { loadSqlSession, saveSqlSession, testSqlSession } from "../api/sqlSessions";

defineProps({
  embedded: { type: Boolean, default: false },
});

const form = reactive({
  name: "默认连接",
  db_type: "mysql",
  host: "127.0.0.1",
  port: 33060,
  username: "root",
  password: "",
  database: "ruoyi"
});
onMounted(async () => {
  const res = await loadSqlSession();
  if (res.data) Object.assign(form, res.data);
});
async function save() {
  await saveSqlSession(form);
}
async function test() {
  try {
    const res = await testSqlSession(form);
    if (res.success) ElMessage.success("连接成功");
    else ElMessage.error(res.error || "连接失败");
  } catch (e) {
    ElMessage.error(e?.message || "请求失败");
  }
}
</script>

<style scoped>
.sql-connection-panel-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.sql-connection-panel--embedded {
  border: none;
  box-shadow: none;
}
.sql-connection-panel--embedded :deep(.el-card__body) {
  padding: 0;
}
</style>
