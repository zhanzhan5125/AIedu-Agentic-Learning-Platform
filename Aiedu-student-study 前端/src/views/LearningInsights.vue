<template>
  <div class="page-shell" :class="{ 'student-page': !isTeacher }" v-loading="loading">
    <div class="page-heading"><div><h2>{{ isTeacher ? '班级学情洞察' : '我的学习画像' }}</h2><p>活跃度与知识掌握度分开计算，所有结论均可追溯到学习证据。</p></div><el-button v-if="!isTeacher" type="primary" :loading="generating" @click="generatePractice">{{ practiceButtonText }}</el-button></div>
    <template v-if="isTeacher">
      <div class="metrics"><el-card><b>{{ data.student_count || 0 }}</b><span>班级学生</span></el-card><el-card><b>{{ classWeakCount }}</b><span>班级薄弱知识点</span></el-card></div>
      <el-table :data="data.knowledge_points || []" empty-text="尚无足够学习证据">
        <el-table-column prop="code" label="编号" width="120"/><el-table-column prop="name" label="知识点"/>
        <el-table-column label="平均掌握度" width="180"><template slot-scope="s"><el-progress :percentage="s.row.average_mastery || 0" /></template></el-table-column>
        <el-table-column prop="evidence_student_count" label="有效样本" width="100"/>
        <el-table-column prop="weak_student_count" label="薄弱人数" width="100"/>
        <el-table-column label="判断" width="120"><template slot-scope="s"><el-tag :type="s.row.is_class_weak ? 'danger' : 'success'">{{ s.row.is_class_weak ? '班级薄弱点' : '正常' }}</el-tag></template></el-table-column>
      </el-table>
    </template>
    <template v-else>
      <div class="metrics"><el-card><b>{{ (data.activity || {}).score || 0 }}</b><span>近30天活跃度</span></el-card><el-card><b>{{ weakCount }}</b><span>个人薄弱知识点</span></el-card><el-card><b>{{ coverageText }}</b><span>{{ insufficientCount ? '画像覆盖率' : '画像证据充分' }}</span></el-card></div>
      <el-table :data="data.knowledge_points || []" empty-text="完成作业或参与问答后将生成学习画像">
        <el-table-column prop="name" label="知识点"/><el-table-column label="掌握度" width="220"><template slot-scope="s"><el-progress :percentage="s.row.mastery_score" :status="s.row.state === 'weak' ? 'exception' : null" /></template></el-table-column>
        <el-table-column label="证据" width="180"><template slot-scope="s"><el-button type="text" @click="showEvidence(s.row)">{{ s.row.observation_count }} 条<span v-if="s.row.evidence_needed">，还差 {{ s.row.evidence_needed }} 条</span></el-button></template></el-table-column><el-table-column prop="trend" label="趋势" width="90"/>
        <el-table-column label="状态" width="130"><template slot-scope="s"><el-tag :type="s.row.state === 'weak' ? 'danger' : s.row.state === 'mastered' ? 'success' : 'info'">{{ stateText(s.row.state) }}</el-tag></template></el-table-column>
      </el-table>
    </template>
    <el-dialog title="个性化复习题" :visible.sync="practiceVisible" width="680px"><el-alert :title="practice.reason || '根据个人学习画像生成'" type="info" :closable="false"/><div v-for="(q,index) in practice.questions || []" :key="index" class="practice-question"><b>{{ index + 1 }}. {{ q.prompt }}</b><el-input type="textarea" :rows="2" placeholder="在这里整理你的思路" /></div></el-dialog>
    <el-drawer :title="`${evidencePoint.name || ''} · 学习证据`" :visible.sync="evidenceVisible" size="420px">
      <div class="evidence-drawer">
        <el-alert v-if="evidencePoint.evidence_needed" :title="`还需要 ${evidencePoint.evidence_needed} 条有效证据才能形成可信判断`" type="warning" :closable="false" />
        <el-timeline v-if="(evidencePoint.evidence || []).length">
          <el-timeline-item v-for="item in evidencePoint.evidence" :key="item.id" :timestamp="formatTime(item.observed_at)">
            <b>{{ sourceText(item.source_type) }}</b><div>得分 {{ item.score }} · 置信度 {{ Math.round(item.confidence * 100) }}%</div>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="尚无学习证据" />
      </div>
    </el-drawer>
  </div>
</template>

<script>
import apiV1 from '@/utils/apiV1'
export default {
  data() { return { loading: false, data: {}, generating: false, practiceVisible: false, practice: {}, evidenceVisible: false, evidencePoint: {} } },
  computed: {
    user() { return this.$store.getters.getUser || {} }, course() { return this.$store.getters.getCourse || {} },
    offeringId() { return Number(this.course.id || this.course.offeringId || this.course.courseCode) || null },
    isTeacher() { return (this.user.role || this.user.identity) === 'teacher' },
    classWeakCount() { return (this.data.knowledge_points || []).filter(i => i.is_class_weak).length },
    weakCount() { return (this.data.knowledge_points || []).filter(i => i.state === 'weak').length },
    insufficientCount() { return (this.data.knowledge_points || []).filter(i => i.state === 'insufficient_data').length },
    coverageText() { const coverage=this.data.profile_coverage||{}; return `${coverage.sufficient||0}/${coverage.total||0}` },
    practiceButtonText() { if(this.weakCount) return '针对薄弱点复习'; if(this.insufficientCount) return '生成诊断练习'; return '生成综合巩固练习' }
  },
  created() { this.load() },
  methods: {
    async load() { if (!this.offeringId) return; this.loading = true; try { const path = this.isTeacher ? `/teacher/offerings/${this.offeringId}/insights` : `/student/offerings/${this.offeringId}/learning-profile`; this.data = (await apiV1.get(path)).data || {} } catch (_) { this.$message.error('学情数据加载失败') } finally { this.loading = false } },
    stateText(value) { return ({ weak: '需要巩固', mastered: '掌握良好', insufficient_data: '证据不足' })[value] || value },
    showEvidence(row) { this.evidencePoint=row; this.evidenceVisible=true },
    sourceText(value) { return ({ assignment:'作业', practice:'个性化练习', chat:'课程问答' })[value] || value },
    formatTime(value) { return value ? new Date(value).toLocaleString() : '' },
    errorMessage(error) { if(error && error.response && error.response.data) return error.response.data.msg || error.response.data.detail; return error && error.message },
    async generatePractice(){this.generating=true;try{const key=`practice-${this.offeringId}-${Date.now()}`;const created=await apiV1.post(`/student/offerings/${this.offeringId}/practice-jobs`,{idempotency_key:key,knowledge_point_ids:[],question_count:5});for(let i=0;i<60;i++){const run=(await apiV1.get(`/agent-runs/${created.data.agent_run_id}`)).data;if(run.status==='succeeded'){this.practice=run.result||{};this.practiceVisible=true;return}if(run.status==='failed')throw new Error(run.error||'Agent 任务失败');await new Promise(resolve=>setTimeout(resolve,1000))}throw new Error('任务超时，请确认 Worker 是否已启动')}catch(error){this.$message.error(this.errorMessage(error)||'个性化练习生成失败，请检查模型和 Worker 配置')}finally{this.generating=false}}
  }
}
</script>
<style scoped>
.page-shell { padding: 32px 48px; min-height: 80vh; background: #f6f8fb; }.page-heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px}h2{margin:0 0 8px}p{margin:0;color:#7b8794}.metrics{display:grid;grid-template-columns:repeat(3,minmax(160px,1fr));gap:16px;margin-bottom:20px}.metrics b{display:block;font-size:30px;color:#2379d8}.metrics span{color:#7b8794}.practice-question{padding:16px 0;border-bottom:1px solid #edf0f3}.practice-question .el-textarea{margin-top:10px}
.student-page{padding-top:32px}
.evidence-drawer{padding:0 24px}.evidence-drawer .el-alert{margin-bottom:20px}
</style>
