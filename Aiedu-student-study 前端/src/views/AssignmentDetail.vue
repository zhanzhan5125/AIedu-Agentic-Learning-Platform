<template>
  <div class="detail-page">
    <main class="detail-main" v-loading="loading">
      <div class="page-title">
        <div>
          <h2>{{ currentAssignment.a_name }} · 作业详情统计</h2>
          <p>分数统计仅包含教师已确认的成绩；AI 负责总结答题情况，不参与数值计算。</p>
        </div>
        <div>
          <el-button
            v-if="insight.graded_count" size="small" icon="el-icon-refresh"
            :loading="analysisLoading" @click="loadAiAnalysis(true)"
          >重新生成 AI 分析</el-button>
          <el-button type="text" @click="$router.push({ name: '查看作业' })">返回提交列表</el-button>
        </div>
      </div>

      <el-alert
        v-if="!insight.graded_count && !loading"
        title="暂无可统计成绩"
        description="至少确认一份学生成绩后，才会计算平均分并生成逐题答题分析。"
        type="info" :closable="false" show-icon
      />

      <section class="overview-grid">
        <div class="metric-card primary">
          <span>作业平均分</span>
          <strong>{{ scoreText(insight.average_score) }}</strong>
          <small>/ {{ scoreText(insight.total_score) }} 分 · 得分率 {{ rateText(insight.average_rate) }}</small>
        </div>
        <div class="metric-card success">
          <span>最高分</span>
          <strong>{{ scoreText(insight.highest_score) }}</strong>
          <small>/ {{ scoreText(insight.total_score) }} 分</small>
        </div>
        <div class="metric-card warning">
          <span>最低分</span>
          <strong>{{ scoreText(insight.lowest_score) }}</strong>
          <small>/ {{ scoreText(insight.total_score) }} 分</small>
        </div>
        <div class="metric-card neutral">
          <span>已确认成绩</span>
          <strong>{{ insight.graded_count || 0 }}</strong>
          <small>已提交 {{ insight.submitted_count || 0 }} / 应交 {{ insight.assigned_count || 0 }}</small>
        </div>
      </section>

      <section class="submission-progress">
        <div>
          <strong>作业提交率</strong>
          <span>{{ insight.submitted_count || 0 }} / {{ insight.assigned_count || 0 }} 人</span>
        </div>
        <el-progress :percentage="Number(insight.submission_rate || 0)" :stroke-width="10" />
      </section>

      <section class="overall-analysis">
        <div class="section-heading">
          <div>
            <h3>出题/批阅智能体 · 整体分析</h3>
            <p>基于教师已确认成绩和匿名化作答样本生成。</p>
          </div>
          <el-tag v-if="analysis" :type="analysis.confidence >= 70 ? 'success' : 'warning'" size="small">
            置信度 {{ analysis.confidence || 0 }}%
          </el-tag>
        </div>
        <div v-if="analysisLoading" class="analysis-placeholder">
          <i class="el-icon-loading" /> 正在汇总每道题的答题情况……
        </div>
        <p v-else-if="analysis" class="overall-text">{{ analysis.overall_summary }}</p>
        <div v-else-if="analysisError" class="analysis-error">
          {{ analysisError }}
          <el-button type="text" @click="loadAiAnalysis(true)">重试</el-button>
        </div>
        <p v-else class="analysis-placeholder">确认成绩后将自动生成分析。</p>
      </section>

      <section class="question-section">
        <div class="section-heading">
          <div>
            <h3>逐题答题情况</h3>
            <p>共 {{ insight.questions ? insight.questions.length : 0 }} 道题，分数均为原始分值。</p>
          </div>
        </div>

        <el-empty v-if="!loading && (!insight.questions || !insight.questions.length)" description="暂无题目统计" />
        <article v-for="question in insight.questions" :key="question.question_id" class="question-card">
          <div class="question-header">
            <div class="question-title">
              <span>第 {{ question.position }} 题</span>
              <p>{{ question.prompt }}</p>
            </div>
            <el-tag size="small" effect="plain">满分 {{ scoreText(question.max_score) }} 分</el-tag>
          </div>

          <div class="question-metrics">
            <div><span>平均分</span><strong>{{ scoreText(question.average_score) }}</strong></div>
            <div><span>最高分</span><strong>{{ scoreText(question.highest_score) }}</strong></div>
            <div><span>最低分</span><strong>{{ scoreText(question.lowest_score) }}</strong></div>
            <div><span>已统计</span><strong>{{ question.submission_count || 0 }} 份</strong></div>
          </div>

          <div class="rate-row">
            <span>本题得分率</span>
            <el-progress :percentage="Number(question.score_rate || 0)" :stroke-width="9" />
          </div>

          <div v-if="question.knowledge_points && question.knowledge_points.length" class="knowledge-row">
            <span>关联知识点</span>
            <el-tag v-for="point in question.knowledge_points" :key="point.id" size="mini" type="info">
              {{ point.name }}
            </el-tag>
          </div>

          <div class="question-analysis">
            <template v-if="analysisByQuestion[question.question_id]">
              <p class="summary-text">{{ analysisByQuestion[question.question_id].summary }}</p>
              <div class="analysis-columns">
                <div>
                  <strong>主要得分点</strong>
                  <ul v-if="analysisByQuestion[question.question_id].strengths.length">
                    <li v-for="item in analysisByQuestion[question.question_id].strengths" :key="item">{{ item }}</li>
                  </ul>
                  <p v-else>当前样本中暂无稳定的共同得分点。</p>
                </div>
                <div>
                  <strong>共性问题</strong>
                  <ul v-if="analysisByQuestion[question.question_id].common_issues.length">
                    <li v-for="item in analysisByQuestion[question.question_id].common_issues" :key="item">{{ item }}</li>
                  </ul>
                  <p v-else>当前未发现明显共性问题。</p>
                </div>
                <div>
                  <strong>教学建议</strong>
                  <p>{{ analysisByQuestion[question.question_id].teaching_suggestion }}</p>
                </div>
              </div>
            </template>
            <div v-else class="analysis-placeholder">
              <i v-if="analysisLoading" class="el-icon-loading" />
              {{ analysisLoading ? '智能体正在分析本题……' : '暂无本题 AI 分析' }}
            </div>
          </div>
        </article>
      </section>
    </main>
  </div>
</template>

<script>
import apiV1 from '@/utils/apiV1'

export default {
  name: 'AssignmentDetail',
  data() {
    return {
      currentAssignment: {},
      insight: { questions: [] },
      analysis: null,
      analysisLoading: false,
      analysisError: '',
      loading: false
    }
  },
  computed: {
    analysisByQuestion() {
      return (this.analysis?.question_summaries || []).reduce((result, item) => {
        result[item.question_id] = item
        return result
      }, {})
    }
  },
  async created() {
    this.currentAssignment = this.$store.getters.getCurrentAssignment || {}
    await this.loadStats()
    if (this.insight.graded_count) await this.loadAiAnalysis(false)
  },
  methods: {
    async loadStats() {
      if (!this.currentAssignment.a_id) return
      this.loading = true
      try {
        const response = await apiV1.get(`/teacher/assignments/${this.currentAssignment.a_id}/insights`)
        this.insight = response.data || { questions: [] }
      } catch (error) {
        this.$message.error(error.response?.data?.msg || '作业统计加载失败')
      } finally {
        this.loading = false
      }
    },
    async loadAiAnalysis(force) {
      if (!this.insight.graded_count || this.analysisLoading) return
      this.analysisLoading = true
      this.analysisError = ''
      try {
        const suffix = force
          ? `manual-${Date.now()}`
          : `snapshot-${this.insight.snapshot_version || 0}-graded-${this.insight.graded_count}`
        const created = await apiV1.post('/ai/summary-jobs', {
          resource_id: this.currentAssignment.a_id,
          idempotency_key: `assignment-analysis-v6-${this.currentAssignment.a_id}-${suffix}`,
          prompt: null
        })
        let completed = false
        for (let attempt = 0; attempt < 100; attempt += 1) {
          const job = await apiV1.get(`/jobs/${created.data.job_id}`)
          if (job.data.status === 'succeeded') {
            this.analysis = job.data.result
            completed = true
            break
          }
          if (['failed', 'cancelled'].includes(job.data.status)) {
            throw new Error(job.data.error || 'AI 作业分析失败')
          }
          await new Promise(resolve => window.setTimeout(resolve, 1500))
        }
        if (!completed) throw new Error('AI 作业分析等待超时，请稍后重试')
      } catch (error) {
        this.analysisError = error.response?.data?.msg || error.message || 'AI 作业分析失败'
      } finally {
        this.analysisLoading = false
      }
    },
    scoreText(value) {
      return value === null || value === undefined ? '-' : Number(value).toFixed(Number(value) % 1 ? 1 : 0)
    },
    rateText(value) {
      return value === null || value === undefined ? '-' : `${this.scoreText(value)}%`
    }
  }
}
</script>

<style scoped>
.detail-page { height: 100vh; background: #f5f7fa; overflow: hidden; }
.detail-main { height: 100vh; overflow-y: auto; box-sizing: border-box; padding: 24px 6% 48px; }
.page-title { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 18px; }
.page-title h2, .section-heading h3 { margin: 0 0 7px; color: #1f2d3d; }
.page-title p, .section-heading p { margin: 0; color: #8492a6; font-size: 13px; }
.overview-grid { display: grid; grid-template-columns: repeat(4, minmax(170px, 1fr)); gap: 14px; margin: 18px 0 14px; }
.metric-card { display: flex; flex-direction: column; gap: 7px; padding: 18px 20px; border-radius: 8px; background: #fff; border-top: 4px solid #909399; box-shadow: 0 2px 10px rgba(31, 45, 61, 0.07); }
.metric-card.primary { border-color: #409eff; }
.metric-card.success { border-color: #67c23a; }
.metric-card.warning { border-color: #e6a23c; }
.metric-card span, .metric-card small { color: #8492a6; }
.metric-card strong { font-size: 30px; color: #303133; }
.submission-progress, .overall-analysis, .question-section { margin-top: 14px; padding: 18px 20px; border-radius: 8px; background: #fff; box-shadow: 0 2px 10px rgba(31, 45, 61, 0.07); }
.submission-progress > div { display: flex; justify-content: space-between; margin-bottom: 10px; color: #606266; }
.section-heading { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.overall-text { margin: 0; line-height: 1.8; color: #303133; white-space: pre-wrap; }
.analysis-placeholder { color: #909399; padding: 12px 0; }
.analysis-error { color: #f56c6c; }
.question-card { margin-top: 14px; padding: 18px; border: 1px solid #e4e7ed; border-radius: 8px; }
.question-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
.question-title { display: flex; align-items: flex-start; gap: 12px; min-width: 0; }
.question-title > span { flex: 0 0 auto; padding: 4px 9px; border-radius: 4px; color: #409eff; background: #ecf5ff; font-weight: 600; }
.question-title p { margin: 3px 0 0; line-height: 1.65; color: #303133; white-space: pre-wrap; }
.question-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 16px 0; }
.question-metrics > div { display: flex; flex-direction: column; gap: 5px; padding: 10px 14px; border-radius: 6px; background: #f7f9fc; }
.question-metrics span { color: #909399; font-size: 12px; }
.question-metrics strong { color: #303133; font-size: 18px; }
.rate-row { display: grid; grid-template-columns: 90px 1fr; align-items: center; color: #606266; }
.knowledge-row { display: flex; align-items: center; gap: 8px; margin-top: 12px; color: #606266; }
.question-analysis { margin-top: 16px; padding: 15px 16px; border-left: 3px solid #409eff; background: #f4faff; }
.summary-text { margin: 0 0 12px; line-height: 1.75; color: #303133; }
.analysis-columns { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.analysis-columns > div { padding: 12px; background: #fff; border-radius: 6px; }
.analysis-columns strong { color: #606266; }
.analysis-columns ul { margin: 8px 0 0; padding-left: 18px; color: #606266; line-height: 1.65; }
.analysis-columns p { margin: 8px 0 0; color: #606266; line-height: 1.65; }
@media (max-width: 1050px) {
  .overview-grid { grid-template-columns: repeat(2, 1fr); }
  .analysis-columns { grid-template-columns: 1fr; }
}
</style>
