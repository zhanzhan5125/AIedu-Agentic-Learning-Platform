<template>
  <div class="grading-page">
    <div class="course-header">
      <p>{{ course.title || course.tittle }}</p>
      <el-menu
        :default-active="'/assignment'" router mode="horizontal"
        background-color="white" text-color="black" active-text-color="#2196f3"
        class="course-menu"
      >
        <el-menu-item index="/course">首页</el-menu-item>
        <el-menu-item index="/assignment">作业</el-menu-item>
        <el-menu-item index="/course_insights">学情洞察</el-menu-item>
        <el-menu-item index="/agent_studio">智能体工作台</el-menu-item>
        <el-menu-item index="/chatpage" :disabled="true">考试</el-menu-item>
        <el-menu-item index="/course_resources">资料</el-menu-item>
        <el-menu-item index="/course_messages"><MessageUnreadBadge :offering-id="course.offeringId || course.id || course.courseCode" /></el-menu-item>
        <el-menu-item index="/manage_stu">管理</el-menu-item>
      </el-menu>
    </div>

    <main class="grading-main">
      <div class="page-title">
        <div>
          <h2>{{ currentAssignment.a_name }} · AI 辅助批阅</h2>
          <p>AI 只生成逐题评分建议；教师确认后，成绩和学习画像才会更新。</p>
        </div>
        <el-button type="text" @click="$router.push({ name: '查看作业' })">返回提交列表</el-button>
      </div>

      <div class="summary-grid">
        <div class="summary-card"><strong>{{ counts.pending }}</strong><span>待批阅</span></div>
        <div class="summary-card processing"><strong>{{ counts.processing }}</strong><span>AI 处理中</span></div>
        <div class="summary-card review"><strong>{{ counts.review }}</strong><span>待教师确认</span></div>
        <div class="summary-card done"><strong>{{ counts.completed }}</strong><span>已完成</span></div>
      </div>

      <el-alert
        title="受控批阅模式"
        description="智能体会先形成评分标准，再逐题评分并检查分数边界与答案证据；发现问题时只允许重新批阅一次。低置信结果会标记为重点人工复核。"
        type="info" :closable="false" show-icon
      />

      <div class="workspace">
        <section class="rules-panel">
          <div class="panel-title">
            <div>
              <h3>本次批阅规则</h3>
              <p>系统的分值边界和证据校验不可关闭，下面只补充课程要求。</p>
            </div>
          </div>

          <div v-if="providerStatus" class="provider-status">
            <el-tag :type="providerReady ? 'success' : 'warning'" size="small">
              {{ providerReady ? `${providerStatus.chat_model} 已配置` : '模型服务未启用' }}
            </el-tag>
            <span v-if="!providerReady">当前只能产生确定性降级结果，请先配置模型服务。</span>
          </div>

          <el-select
            v-if="promptTemplates.length"
            v-model="selectedPromptId" size="small" class="prompt-select"
            placeholder="选择已保存规则" @change="selectPrompt"
          >
            <el-option
              v-for="item in promptTemplates" :key="item.id"
              :label="`${item.name}（第 ${item.version} 版）`" :value="item.id"
            />
          </el-select>

          <el-input
            v-model="gradingRules" type="textarea" :rows="12" maxlength="20000"
            show-word-limit placeholder="例如：术语表述准确即可，不要求与参考答案逐字一致；程序题重点检查算法和边界。"
          />

          <div class="rule-actions">
            <el-button size="small" :loading="savingRules" @click="saveRules">保存规则版本</el-button>
            <el-button
              type="primary" size="small" :loading="startingBatch"
              :disabled="counts.pending === 0 || (providerStatus && !providerReady)" @click="startBatch"
            >开始批阅 {{ counts.pending }} 份</el-button>
          </div>

          <div v-if="batchTotal" class="batch-progress">
            <div><span>本批任务进度</span><span>{{ batchFinished }}/{{ batchTotal }}</span></div>
            <el-progress :percentage="batchProgress" :status="batchFailed ? 'exception' : undefined" />
            <p v-if="batchFailed">{{ batchFailed }} 份任务失败，可在右侧查看原因后重试。</p>
          </div>
        </section>

        <section class="submission-panel">
          <div class="panel-title submission-title">
            <div>
              <h3>学生提交</h3>
              <p>完成后进入逐题确认页，AI 建议不会自动发布成绩。</p>
            </div>
            <el-button icon="el-icon-refresh" size="mini" @click="loadSubmissions">刷新</el-button>
          </div>

          <div v-loading="loading" class="submission-list">
            <el-empty v-if="!loading && submissions.length === 0" description="暂无已提交作业" />
            <div v-for="item in submissions" :key="item.id" class="submission-row">
              <div class="student-info">
                <strong>{{ item.student_name }}</strong>
                <span>{{ item.student_account }}</span>
                <small>{{ formatTime(item.submitted_at) }}</small>
              </div>
              <div class="row-result">
                <el-tag :type="statusMeta(item).type" size="small">{{ statusMeta(item).label }}</el-tag>
                <span v-if="item.ai_confidence !== null && item.ai_confidence !== undefined">
                  建议置信度 {{ item.ai_confidence }}%
                </span>
                <span v-if="jobFor(item).error" class="job-error">{{ jobFor(item).error }}</span>
                <span v-else-if="item.review_reason" class="review-reason">{{ item.review_reason }}</span>
              </div>
              <div class="row-action">
                <el-button
                  v-if="item.status === 'submitted'" type="primary" plain size="small"
                  :loading="jobFor(item).submitting" @click="startOne(item)"
                >AI 批阅</el-button>
                <el-button v-else-if="item.status === 'ai_grading'" size="small" disabled>
                  <i class="el-icon-loading" /> 正在批阅
                </el-button>
                <template v-else-if="isAiFailed(item)">
                  <el-button type="danger" plain size="small" :loading="jobFor(item).submitting" @click="startOne(item)">重试</el-button>
                  <el-button type="text" size="small" @click="openReview(item)">人工批阅</el-button>
                </template>
                <el-button v-else type="primary" size="small" @click="openReview(item)">
                  {{ item.status === 'needs_review' ? '确认建议' : '查看批阅' }}
                </el-button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  </div>
</template>

<script>
import apiV1 from '@/utils/apiV1'

const DEFAULT_RULES = `1. 以题目、参考答案、题目分值和学生实际作答为依据。
2. 答案含义正确即可，不要求与参考答案逐字一致。
3. 评语同时说明得分点和待改进点，不使用空泛表述。
4. 无法可靠判断时降低置信度并标记教师重点复核。`

export default {
  name: 'LlmPromptTeacher',
  data() {
    return {
      course: {},
      currentAssignment: {},
      submissions: [],
      promptTemplates: [],
      selectedPromptId: null,
      gradingRules: DEFAULT_RULES,
      providerStatus: null,
      jobs: {},
      batchSubmissionIds: [],
      loading: false,
      savingRules: false,
      startingBatch: false,
      pollTimer: null
    }
  },
  computed: {
    counts() {
      return this.submissions.reduce((result, item) => {
        if (item.status === 'submitted') result.pending += 1
        else if (item.status === 'ai_grading') result.processing += 1
        else if (item.status === 'needs_review') result.review += 1
        else if (['graded', 'returned'].includes(item.status)) result.completed += 1
        return result
      }, { pending: 0, processing: 0, review: 0, completed: 0 })
    },
    batchTotal() {
      return this.batchSubmissionIds.length
    },
    batchFinished() {
      return this.batchSubmissionIds.filter(id => ['succeeded', 'failed', 'cancelled'].includes(this.jobForId(id).status)).length
    },
    batchFailed() {
      return this.batchSubmissionIds.filter(id => ['failed', 'cancelled'].includes(this.jobForId(id).status)).length
    },
    batchProgress() {
      return this.batchTotal ? Math.round(this.batchFinished / this.batchTotal * 100) : 0
    },
    providerReady() {
      return Boolean(this.providerStatus?.configured && this.providerStatus?.enabled)
    }
  },
  async created() {
    this.course = this.$store.getters.getCourse || {}
    this.currentAssignment = this.$store.getters.getCurrentAssignment || {}
    await Promise.all([this.loadPrompts(), this.loadSubmissions(), this.loadProviderStatus()])
    this.ensurePolling()
  },
  beforeDestroy() {
    this.stopPolling()
  },
  methods: {
    async loadProviderStatus() {
      try {
        const response = await apiV1.get('/ai/provider/status')
        this.providerStatus = response.data || null
      } catch (error) {
        this.providerStatus = null
      }
    },
    async loadPrompts() {
      try {
        const response = await apiV1.get('/prompts')
        this.promptTemplates = (response.data || []).filter(item => item.purpose === 'grading')
        if (this.promptTemplates.length) {
          const selected = this.promptTemplates.find(item => item.active) || this.promptTemplates[0]
          this.selectedPromptId = selected.id
          this.gradingRules = (selected.content || DEFAULT_RULES).replace(/\$/g, '\n\n')
        }
      } catch (error) {
        this.promptTemplates = []
      }
    },
    selectPrompt(id) {
      const selected = this.promptTemplates.find(item => item.id === id)
      if (selected) this.gradingRules = (selected.content || DEFAULT_RULES).replace(/\$/g, '\n\n')
    },
    async saveRules() {
      if (!this.gradingRules.trim()) {
        this.$message.warning('请先填写批阅规则')
        return
      }
      this.savingRules = true
      try {
        const selected = this.promptTemplates.find(item => item.id === this.selectedPromptId)
        if (selected) {
          await apiV1.post(`/prompts/${selected.id}/versions`, {
            name: selected.name,
            purpose: 'grading',
            content: this.gradingRules.trim(),
            activate: selected.active
          })
        } else {
          await apiV1.post('/prompts', {
            name: `AI辅助批阅规则-${Date.now()}`,
            purpose: 'grading',
            content: this.gradingRules.trim(),
            activate: false
          })
        }
        await this.loadPrompts()
        this.$message.success('批阅规则已保存')
      } catch (error) {
        this.$message.error(error.response?.data?.msg || '批阅规则保存失败')
      } finally {
        this.savingRules = false
      }
    },
    async loadSubmissions() {
      if (!this.currentAssignment.a_id) return
      this.loading = this.submissions.length === 0
      try {
        const response = await apiV1.get(`/teacher/assignments/${this.currentAssignment.a_id}/submissions`)
        this.submissions = response.data?.records || []
      } catch (error) {
        this.$message.error(error.response?.data?.msg || '提交记录加载失败')
      } finally {
        this.loading = false
      }
    },
    async startBatch() {
      if (this.providerStatus && !this.providerReady) {
        this.$message.error('模型服务尚未配置或启用，无法开始 AI 批阅')
        return
      }
      const pending = this.submissions.filter(item => item.status === 'submitted')
      if (!pending.length) return
      this.batchSubmissionIds = pending.map(item => item.id)
      this.startingBatch = true
      await Promise.all(pending.map(item => this.startOne(item, false)))
      this.startingBatch = false
      this.ensurePolling()
    },
    async startOne(item, notify = true) {
      if (this.providerStatus && !this.providerReady) {
        this.$message.error('模型服务尚未配置或启用，无法开始 AI 批阅')
        return
      }
      this.$set(this.jobs, item.id, { ...this.jobFor(item), submitting: true, error: null })
      try {
        const response = await apiV1.post('/ai/grading-jobs', {
          resource_id: item.id,
          idempotency_key: `grading-${item.id}-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
          prompt: this.gradingRules.trim() || null
        })
        this.$set(this.jobs, item.id, {
          jobId: response.data.job_id,
          agentRunId: response.data.agent_run_id,
          status: response.data.status,
          submitting: false,
          error: null
        })
        item.status = 'ai_grading'
        if (!this.batchSubmissionIds.includes(item.id)) this.batchSubmissionIds = [item.id]
        if (notify) this.$message.success('已提交 AI 批阅任务')
        this.ensurePolling()
      } catch (error) {
        const message = error.response?.data?.msg || 'AI 批阅任务创建失败'
        this.$set(this.jobs, item.id, { status: 'failed', submitting: false, error: message })
        if (notify) this.$message.error(message)
      }
    },
    async pollJobs() {
      const active = Object.entries(this.jobs).filter(([, job]) => job.jobId && ['queued', 'running'].includes(job.status))
      await Promise.all(active.map(async ([submissionId, job]) => {
        try {
          const response = await apiV1.get(`/jobs/${job.jobId}`)
          this.$set(this.jobs, Number(submissionId), {
            ...job,
            status: response.data.status,
            error: response.data.error || null
          })
        } catch (error) {
          this.$set(this.jobs, Number(submissionId), {
            ...job,
            error: error.response?.data?.msg || '任务状态读取失败'
          })
        }
      }))
      await this.loadSubmissions()
      const hasActiveJobs = Object.values(this.jobs).some(job => ['queued', 'running'].includes(job.status))
      if (!hasActiveJobs && this.counts.processing === 0) this.stopPolling()
    },
    ensurePolling() {
      const hasActiveJobs = Object.values(this.jobs).some(job => ['queued', 'running'].includes(job.status))
      if (this.pollTimer || (this.counts.processing === 0 && !hasActiveJobs)) return
      this.pollTimer = window.setInterval(this.pollJobs, 2500)
    },
    stopPolling() {
      if (this.pollTimer) window.clearInterval(this.pollTimer)
      this.pollTimer = null
    },
    jobFor(item) {
      return this.jobs[item.id] || {}
    },
    jobForId(id) {
      return this.jobs[id] || {}
    },
    statusMeta(item) {
      const job = this.jobFor(item)
      if (this.isAiFailed(item)) return { label: 'AI 失败，需人工处理', type: 'danger' }
      return ({
        submitted: { label: '待批阅', type: 'info' },
        ai_grading: { label: 'AI 处理中', type: 'warning' },
        needs_review: { label: '待教师确认', type: 'warning' },
        graded: { label: '已完成', type: 'success' },
        returned: { label: '已完成', type: 'success' }
      })[item.status] || { label: item.status, type: 'info' }
    },
    isAiFailed(item) {
      const job = this.jobFor(item)
      return ['failed', 'cancelled'].includes(job.status) || (item.review_reason || '').includes('失败')
    },
    openReview(item) {
      const student = {
        s_name: item.student_name,
        s_id: item.student_account,
        student_id: item.student_id,
        submission_id: item.id
      }
      const stuList = this.submissions.map(row => ({
        sname: row.student_name,
        sid: row.student_account,
        studentId: row.student_id,
        submissionId: row.id
      }))
      this.$store.dispatch('setStuList', stuList)
      this.$store.dispatch('setStudent', student)
      this.$router.push({ name: '教师批阅' })
    },
    formatTime(value) {
      if (!value) return '-'
      return new Date(value).toLocaleString('zh-CN', { hour12: false })
    }
  }
}
</script>

<style scoped>
.grading-page { height: 100vh; background: #f5f7fa; overflow: hidden; }
.course-header { height: 61px; display: flex; align-items: center; border-bottom: 1px solid #ddd; background: #fff; }
.course-header > p { margin: 0; padding-left: 70px; font-size: 18px; color: #2196f3; }
.course-menu { flex: 1; display: flex; justify-content: flex-end; padding-right: 50px; border-bottom: none; }
.grading-main { height: calc(100vh - 61px); box-sizing: border-box; padding: 22px 5%; display: flex; flex-direction: column; gap: 14px; overflow: hidden; }
.page-title { display: flex; justify-content: space-between; align-items: flex-start; }
.page-title h2, .panel-title h3 { margin: 0 0 6px; color: #1f2d3d; }
.page-title p, .panel-title p { margin: 0; color: #8492a6; font-size: 13px; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 12px; }
.summary-card { display: flex; align-items: baseline; gap: 10px; padding: 12px 18px; background: #fff; border-left: 4px solid #909399; border-radius: 6px; }
.summary-card strong { font-size: 24px; }
.summary-card span { color: #606266; }
.summary-card.processing { border-color: #e6a23c; }
.summary-card.review { border-color: #409eff; }
.summary-card.done { border-color: #67c23a; }
.workspace { min-height: 0; flex: 1; display: grid; grid-template-columns: minmax(330px, 0.8fr) minmax(520px, 1.5fr); gap: 16px; }
.rules-panel, .submission-panel { min-height: 0; background: #fff; border-radius: 8px; box-shadow: 0 2px 10px rgba(31, 45, 61, 0.08); padding: 18px; box-sizing: border-box; }
.rules-panel { overflow-y: auto; }
.submission-panel { display: flex; flex-direction: column; overflow: hidden; }
.panel-title { margin-bottom: 14px; }
.submission-title { display: flex; justify-content: space-between; align-items: center; }
.prompt-select { width: 100%; margin-bottom: 12px; }
.provider-status { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; color: #e6a23c; font-size: 12px; }
.rule-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
.batch-progress { margin-top: 18px; padding-top: 16px; border-top: 1px solid #ebeef5; }
.batch-progress > div { display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 13px; }
.batch-progress p { color: #f56c6c; font-size: 12px; }
.submission-list { min-height: 160px; flex: 1; overflow-y: auto; padding-right: 4px; }
.submission-row { display: grid; grid-template-columns: 160px minmax(220px, 1fr) 180px; gap: 16px; align-items: center; padding: 14px 4px; border-bottom: 1px solid #ebeef5; }
.student-info, .row-result { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.student-info span, .student-info small, .row-result span { color: #8492a6; font-size: 12px; }
.review-reason, .job-error { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.job-error { color: #f56c6c !important; }
.row-action { text-align: right; }
@media (max-width: 1050px) {
  .workspace { grid-template-columns: 1fr; overflow-y: auto; }
  .rules-panel, .submission-panel { min-height: 430px; }
}
</style>
