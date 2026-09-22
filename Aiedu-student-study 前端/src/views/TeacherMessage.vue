<template>
  <div class="message-page">
    <div class="heading">
      <h2>消息中心</h2>
      <el-button icon="el-icon-refresh" @click="load">刷新</el-button>
    </div>
    <el-alert v-if="unavailable" :title="unavailableMessage" type="warning" show-icon />
    <el-table v-loading="loading" :data="records" empty-text="暂无消息">
      <el-table-column prop="title" label="标题" min-width="180" />
      <el-table-column prop="body" label="内容" min-width="320" />
      <el-table-column prop="created_at" label="时间" width="180" />
      <el-table-column label="状态" width="100">
        <template slot-scope="scope">
          <el-button v-if="!scope.row.is_read" type="text" @click="markRead(scope.row)">标为已读</el-button>
          <el-tag v-else type="info">已读</el-tag>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script>
import apiV1 from '@/utils/apiV1'
export default {
  data: () => ({
    loading: false,
    unavailable: false,
    unavailableMessage: '',
    records: []
  }),
  created() { this.load() },
  methods: {
    async load() {
      const user = JSON.parse(localStorage.getItem('user') || 'null')
      if (!user || user._backend !== 'fastapi') {
        this.records = []
        this.unavailable = true
        this.unavailableMessage = '消息中心正在迁移中，当前页面不会影响 Spring Boot 登录状态。'
        return
      }
      this.loading = true
      this.unavailable = false
      try {
        const res = await apiV1.get('/notifications')
        this.records = (res.data && res.data.records) || []
      } catch (_) {
        this.unavailable = true
        this.unavailableMessage = '消息服务暂时不可用，请稍后重试。'
      } finally {
        this.loading = false
      }
    },
    async markRead(row) {
      const user = JSON.parse(localStorage.getItem('user') || 'null')
      if (!user || user._backend !== 'fastapi') return
      await apiV1.put(`/notifications/${row.id}/read`)
      row.is_read = true
    }
  }
}
</script>

<style scoped>
.message-page { padding: 24px; }
.heading { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
</style>
