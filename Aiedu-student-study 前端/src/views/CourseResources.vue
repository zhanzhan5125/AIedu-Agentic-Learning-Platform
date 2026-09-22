<template>
  <div class="page-shell" :class="{ 'student-page': !isTeacher }">
    <div class="page-heading">
      <div><h2>课程资料</h2><p>资料完成解析后可供问答杏台检索引用。</p></div>
      <div v-if="isTeacher" class="upload-controls"><el-select v-model="resourceType" size="small" aria-label="资料类型"><el-option label="课件" value="courseware"/><el-option label="教学大纲" value="syllabus"/><el-option label="教材" value="textbook"/></el-select><el-upload :show-file-list="false" :http-request="upload"
                 :before-upload="beforeUpload" accept=".pdf,.docx,.pptx" :disabled="uploading || !offeringId">
        <el-button type="primary" icon="el-icon-upload" :loading="uploading" :disabled="!offeringId">
          {{ uploading ? `上传中 ${uploadPercent}%` : '上传资料' }}
        </el-button>
      </el-upload></div>
    </div>
    <el-alert v-if="!offeringId" title="请先选择一门课程" type="warning" :closable="false" />
    <el-table v-else v-loading="loading" :data="resources" empty-text="暂无课程资料">
      <el-table-column prop="title" label="资料名称" min-width="220" />
      <el-table-column label="类型" width="110"><template slot-scope="scope">{{ typeText(scope.row.resource_type) }}</template></el-table-column>
      <el-table-column prop="size" label="大小" width="120">
        <template slot-scope="scope">{{ formatSize(scope.row.size) }}</template>
      </el-table-column>
      <el-table-column label="处理状态" width="130">
        <template slot-scope="scope">
          <el-tooltip :disabled="!scope.row.error_message" :content="scope.row.error_message" placement="top">
            <el-tag :type="statusType(scope.row.status)">{{ statusText(scope.row.status) }}</el-tag>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="上传时间" min-width="180">
        <template slot-scope="scope">
          <el-tooltip content="资料成功写入向量数据库的时间" placement="top">
            <span>{{ formatTime(scope.row.indexed_at) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="230">
        <template slot-scope="scope">
          <el-button type="text" @click="open(scope.row, false)">打开</el-button>
          <el-button type="text" @click="open(scope.row, true)">下载</el-button>
          <el-button v-if="isTeacher && scope.row.status === 'failed'" type="text" @click="reindex(scope.row)">重新索引</el-button>
          <el-button v-if="isTeacher" type="text" class="danger" @click="remove(scope.row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script>
import apiV1 from '@/utils/apiV1'

export default {
  data() { return { loading: false, uploading: false, uploadPercent: 0, resourceType: 'courseware', resources: [], pollTimer: null } },
  computed: {
    user() { return this.$store.getters.getUser || {} },
    course() { return this.$store.getters.getCourse || {} },
    offeringId() { return Number(this.course.id || this.course.offeringId || this.course.courseCode) || null },
    isTeacher() { return (this.user.role || this.user.identity) === 'teacher' }
  },
  created() { this.load() },
  beforeDestroy() { this.stopPolling() },
  methods: {
    async load(silent = false) {
      if (!this.offeringId) return
      if (!silent) this.loading = true
      try {
        this.resources = (await apiV1.get(`/offerings/${this.offeringId}/resources`)).data || []
        if (this.isTeacher && this.resources.some(item => ['uploaded', 'scanning', 'parsing', 'indexing'].includes(item.status))) this.startPolling()
        else this.stopPolling()
      } catch (error) {
        if (!silent) this.$message.error(this.errorText(error, '课程资料加载失败'))
      } finally { if (!silent) this.loading = false }
    },
    beforeUpload(file) {
      const suffix = (file.name.split('.').pop() || '').toLowerCase()
      if (!['pdf', 'docx', 'pptx'].includes(suffix)) {
        this.$message.error('仅支持 PDF、DOCX 和 PPTX 资料')
        return false
      }
      if (file.size > 10 * 1024 * 1024) {
        this.$message.error('单个文件不能超过 10 MB')
        return false
      }
      return true
    },
    async upload(option) {
      const data = new FormData(); data.append('file', option.file); data.append('title', option.file.name.replace(/\.[^.]+$/, '')); data.append('resource_type', this.resourceType)
      this.uploading = true; this.uploadPercent = 0
      try {
        const result = await apiV1.post(`/teacher/offerings/${this.offeringId}/resources`, data, {
          onUploadProgress: event => { if (event.total) this.uploadPercent = Math.round(event.loaded * 100 / event.total) }
        })
        option.onSuccess(result)
        this.$message.success('资料已保存，RocketMQ 正在异步处理')
        await this.load()
      } catch (error) {
        option.onError(error)
        this.$message.error(this.errorText(error, '资料上传失败，请确认格式和大小'))
      } finally { this.uploading = false; this.uploadPercent = 0 }
    },
    async open(row, download) {
      try {
        const response = await apiV1.get(`/resources/${row.id}/${download ? 'download' : 'preview'}`, { responseType: 'blob' })
        const url = URL.createObjectURL(response)
        if (download) { const a = document.createElement('a'); a.href = url; a.download = row.name; a.click() }
        else window.open(url, '_blank')
        setTimeout(() => URL.revokeObjectURL(url), 30000)
      } catch (error) { this.$message.error(this.errorText(error, download ? '资料下载失败' : '资料暂时无法打开')) }
    },
    async reindex(row) {
      try { await apiV1.post(`/resources/${row.id}/reindex`); this.$message.success('已重新提交异步索引'); this.load() }
      catch (error) { this.$message.error(this.errorText(error, '重新索引失败')) }
    },
    async remove(row) {
      try {
        await this.$confirm(`确认删除“${row.title}”？`, '删除资料')
        await apiV1.delete(`/resources/${row.id}`); this.load()
      } catch (error) { if (error !== 'cancel' && error !== 'close') this.$message.error(this.errorText(error, '删除资料失败')) }
    },
    startPolling() {
      if (this.pollTimer) return
      this.pollTimer = setInterval(() => this.load(true), 3000)
    },
    stopPolling() { if (this.pollTimer) { clearInterval(this.pollTimer); this.pollTimer = null } },
    errorText(error, fallback) {
      const body = error && error.response && error.response.data
      return (body && (body.msg || body.message || body.detail)) || fallback
    },
    formatSize(value) { return value > 1024 * 1024 ? `${(value / 1024 / 1024).toFixed(1)} MB` : `${Math.ceil(value / 1024)} KB` },
    formatTime(value) {
      if (!value) return '等待入库'
      return new Date(value).toLocaleString('zh-CN', { hour12: false })
    },
    statusText(value) { return ({ uploaded: '等待处理', scanning: '安全检查', parsing: '解析中', indexing: '索引中', ready: '可用', failed: '处理失败' })[value] || value },
    statusType(value) { return value === 'ready' ? 'success' : value === 'failed' ? 'danger' : 'warning' },
    typeText(value) { return ({ syllabus: '教学大纲', courseware: '课件', textbook: '教材' })[value] || '课件' }
  }
}
</script>

<style scoped>
.page-shell { padding: 0 48px 32px; min-height: 80vh; background: #f6f8fb; }
.student-page { padding-top: 32px; }
.page-heading { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
h2 { margin: 0 0 8px; } p { margin: 0; color: #7b8794; } .danger { color: #f56c6c; }
.upload-controls{display:flex;align-items:center;gap:10px}.upload-controls .el-select{width:120px}
</style>
