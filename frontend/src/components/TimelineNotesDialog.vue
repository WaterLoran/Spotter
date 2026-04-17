<template>
  <el-dialog v-model="visibleModel" title="时间轴备注" width="700px">
    <div style="display:flex;gap:8px;margin-bottom:8px;">
      <el-input v-model="form.title" placeholder="标题" />
      <el-input v-model="form.tags" placeholder="标签，逗号分隔" />
      <el-button type="primary" @click="save">新增</el-button>
    </div>
    <el-input v-model="form.content" type="textarea" :rows="3" placeholder="备注内容" />
    <el-divider />
    <el-table :data="notes">
      <el-table-column prop="title" label="标题" width="180" />
      <el-table-column prop="content" label="内容" />
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button size="small" @click="edit(row)">编辑</el-button>
          <el-button size="small" type="danger" @click="remove(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import { createTimelineNote, deleteTimelineNote, listTimelineNotes, updateTimelineNote } from "../api/api";

const props = defineProps({ visible: Boolean, viewId: Number });
const emit = defineEmits(["update:visible"]);
const visibleModel = computed({
  get: () => props.visible,
  set: (v) => emit("update:visible", v)
});
const notes = ref([]);
const form = reactive({ id: null, title: "", content: "", tags: "" });

async function load() {
  if (!props.viewId) return;
  const res = await listTimelineNotes(props.viewId);
  notes.value = res.data || [];
}
watch(() => props.visible, (v) => v && load());

async function save() {
  const payload = { title: form.title, content: form.content, tags: form.tags.split(",").map((i) => i.trim()).filter(Boolean) };
  if (form.id) {
    await updateTimelineNote(form.id, payload);
  } else {
    await createTimelineNote(props.viewId, payload);
  }
  form.id = null;
  form.title = "";
  form.content = "";
  form.tags = "";
  await load();
}
function edit(row) {
  form.id = row.id;
  form.title = row.title || "";
  form.content = row.content || "";
  form.tags = Array.isArray(row.tags) ? row.tags.join(",") : "";
}
async function remove(id) {
  await deleteTimelineNote(id);
  await load();
}
</script>

