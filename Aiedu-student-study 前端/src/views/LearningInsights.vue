<template>
  <div class="page-shell" :class="{ 'student-page': !isTeacher }" v-loading="loading">
    <div class="page-heading">
      <div>
        <h2>{{ isTeacher ? '班级学情洞察' : '我的学习画像' }}</h2>
        <p>{{ isTeacher ? '展示已发布课程路线的全部知识点；每次确认批阅后，平均掌握度会根据得分自动更新。' : '掌握度按已评分作业 70% 与个人练习 30% 加权计算。' }}</p>
      </div>
      <div v-if="!isTeacher" class="heading-actions">
        <el-button @click="openPracticeHistory">练习历史</el-button>
        <el-button type="primary" :loading="generating" @click="generatePractice">{{ practiceButtonText }}</el-button>
      </div>
    </div>
    <template v-if="isTeacher">
      <div class="metrics"><el-card><b>{{ data.student_count || 0 }}</b><span>班级学生</span></el-card><el-card><b>{{ coveredPointCount }}</b><span>已产生成绩的知识点</span></el-card><el-card><b>{{ classWeakCount }}</b><span>班级薄弱知识点</span></el-card></div>
      <el-table :data="data.knowledge_points || []" empty-text="请先发布课程知识路线">
        <el-table-column prop="code" label="编号" width="90"/><el-table-column prop="name" label="知识点" min-width="200"/>
        <el-table-column label="所属章节" min-width="220"><template slot-scope="s"><span>{{ s.row.chapter_name || '未归属章节' }}</span></template></el-table-column>
        <el-table-column label="平均掌握度" width="190"><template slot-scope="s"><el-progress v-if="s.row.average_mastery !== null" :percentage="s.row.average_mastery"/><span v-else class="no-score">尚无已确认成绩</span></template></el-table-column>
        <el-table-column prop="evidence_student_count" label="已计入学生" width="110"/><el-table-column prop="weak_student_count" label="薄弱人数" width="100"/>
        <el-table-column label="判断" width="120"><template slot-scope="s"><el-tag :type="classStatus(s.row).type">{{ classStatus(s.row).text }}</el-tag></template></el-table-column>
      </el-table>
    </template>
    <template v-else>
      <div class="metrics"><el-card><b>{{ (data.activity || {}).score || 0 }}</b><span>近30天活跃度</span></el-card><el-card><b>{{ weakCount }}</b><span>个人薄弱知识点</span></el-card><el-card><b>{{ masteredCount }}</b><span>已掌握知识点</span></el-card></div>
      <el-table :data="data.knowledge_points || []" empty-text="完成已评分作业或个人练习后将生成学习画像">
        <el-table-column prop="name" label="知识点"/><el-table-column label="所属章节"><template slot-scope="s"><span>{{ s.row.chapter_name || '未归属章节' }}</span></template></el-table-column>
        <el-table-column label="掌握度" width="240"><template slot-scope="s"><el-progress v-if="s.row.state !== 'unobserved'" :percentage="s.row.mastery_score"/><span v-else class="no-score">暂无学习记录</span></template></el-table-column>
        <el-table-column label="证据" width="110"><template slot-scope="s"><el-button type="text" @click="showEvidence(s.row)">查看证据</el-button></template></el-table-column>
      </el-table>
    </template>

    <el-dialog title="个性化练习" :visible.sync="practiceVisible" width="760px" custom-class="practice-dialog">
      <div v-loading="practiceLoading" class="practice-dialog-body">
        <template v-if="practice.id">
          <div class="practice-heading">
            <el-alert :title="practice.rationale || '根据个人学习画像生成'" type="info" :closable="false"/>
            <div class="practice-state"><el-tag :type="practiceStatus(practice.status).type">{{ practiceStatus(practice.status).text }}</el-tag><b v-if="practice.status === 'completed'">{{ practice.score }} / {{ practice.total_score }} 分</b></div>
          </div>
          <div v-for="q in practice.questions || []" :key="q.question_index" class="practice-question">
            <b>{{ q.question_index + 1 }}. {{ q.prompt }}</b>
            <el-input v-model="practiceAnswers[q.question_index]" type="textarea" :rows="3" :disabled="!practiceEditable" placeholder="请输入你的答案"/>
            <div v-if="q.feedback" class="practice-feedback">
              <div><el-tag size="mini" :type="q.feedback.is_correct ? 'success' : (q.feedback.score > 0 ? 'warning' : 'danger')">{{ q.feedback.is_correct ? '回答正确' : (q.feedback.score > 0 ? '部分正确' : '需要订正') }}</el-tag><strong>{{ q.feedback.score }} / {{ q.feedback.max_score }} 分</strong></div>
              <p>{{ q.feedback.feedback }}</p><small v-if="q.reference_answer"><b>参考答案：</b>{{ q.reference_answer }}</small>
            </div>
          </div>
          <el-alert v-if="practice.summary" :title="practice.summary" type="success" :closable="false" show-icon/>
        </template>
        <el-empty v-else description="暂无练习"/>
      </div>
      <span slot="footer" class="dialog-footer"><span v-if="practice.status === 'feedback_pending'" class="pending-text"><i class="el-icon-loading"/> 学生学习助手正在逐题反馈</span><el-button @click="practiceVisible=false">关闭</el-button><el-button v-if="practiceEditable" type="primary" :loading="submittingPractice" @click="submitPractice">提交并查看反馈</el-button></span>
    </el-dialog>

    <el-drawer title="练习历史" :visible.sync="historyVisible" size="460px">
      <div class="history-list" v-loading="historyLoading">
        <div v-for="item in practiceHistory" :key="item.id" class="history-item" @click="openPracticeSession(item.id)">
          <div><b>{{ item.assignment_title || '个性化练习' }}</b><el-tag size="mini" :type="practiceStatus(item.status).type">{{ practiceStatus(item.status).text }}</el-tag></div>
          <p>{{ formatTime(item.created_at) }} · {{ item.question_count }} 题</p><strong v-if="item.status === 'completed'">{{ item.score }} / {{ item.total_score }} 分</strong><i class="el-icon-arrow-right"/>
        </div><el-empty v-if="!practiceHistory.length && !historyLoading" description="还没有历史练习"/>
      </div>
    </el-drawer>

    <el-drawer :title="`${evidencePoint.name || ''} · 学习证据`" :visible.sync="evidenceVisible" size="440px">
      <div class="evidence-drawer"><el-timeline v-if="(evidencePoint.evidence || []).length">
        <el-timeline-item v-for="item in evidencePoint.evidence" :key="item.id" :timestamp="formatTime(item.observed_at)">
          <b>{{ sourceText(item.source_type) }}</b><div>得分比 {{ item.score }}%</div>
          <template v-if="item.source_type === 'assignment' && item.assignment_id"><p class="evidence-title">{{ item.assignment_title }} · 第 {{ item.question_position }} 题</p><small>{{ item.question_prompt }}</small><el-button type="text" @click="openAssignmentEvidence(item)">查看这道作业题</el-button></template>
          <template v-else-if="item.source_type === 'practice' && item.practice_session_id"><p class="evidence-title">{{ item.practice_title }}</p><el-button type="text" @click="openPracticeEvidence(item)">查看这次练习</el-button></template>
        </el-timeline-item>
      </el-timeline><el-empty v-else description="尚无学习证据"/></div>
    </el-drawer>
  </div>
</template>

<script>
import apiV1 from '@/utils/apiV1'
export default {
  data() { return { loading:false, data:{}, generating:false, practiceVisible:false, practiceLoading:false, submittingPractice:false, practice:{}, practiceAnswers:{}, practiceRunId:null, practiceHistory:[], historyVisible:false, historyLoading:false, evidenceVisible:false, evidencePoint:{} } },
  computed: {
    user(){return this.$store.getters.getUser||{}}, course(){return this.$store.getters.getCourse||{}}, offeringId(){return Number(this.course.id||this.course.offeringId||this.course.courseCode)||null}, isTeacher(){return (this.user.role||this.user.identity)==='teacher'},
    classWeakCount(){return (this.data.knowledge_points||[]).filter(i=>i.is_class_weak).length}, coveredPointCount(){return (this.data.knowledge_points||[]).filter(i=>i.average_mastery!==null).length}, weakCount(){return (this.data.knowledge_points||[]).filter(i=>i.state==='weak').length}, masteredCount(){return (this.data.knowledge_points||[]).filter(i=>i.state==='mastered').length}, observedCount(){return (this.data.knowledge_points||[]).filter(i=>i.state!=='unobserved').length},
    practiceEditable(){return ['ready','feedback_failed'].includes(this.practice.status)}, practiceButtonText(){if(this.weakCount)return '针对薄弱点复习';if(this.observedCount)return '生成综合巩固练习';return '生成课程基础练习'}
  },
  created(){this.load()},
  methods: {
    async load(){if(!this.offeringId)return;this.loading=true;try{const path=this.isTeacher?`/teacher/offerings/${this.offeringId}/insights`:`/student/offerings/${this.offeringId}/learning-profile`;this.data=(await apiV1.get(path)).data||{};if(!this.isTeacher)await this.loadPracticeHistory()}catch(_){this.$message.error('学情数据加载失败')}finally{this.loading=false}},
    async loadPracticeHistory(){this.historyLoading=true;try{const data=(await apiV1.get(`/student/offerings/${this.offeringId}/practice-sessions?page=1&page_size=50`)).data||{};this.practiceHistory=(data.items||[]).filter(item=>item.question_count>0)}finally{this.historyLoading=false}},
    async openPracticeHistory(){this.historyVisible=true;await this.loadPracticeHistory()},
    async openPracticeSession(sessionId){this.practiceVisible=true;this.practiceLoading=true;try{this.practice=(await apiV1.get(`/student/practice-sessions/${sessionId}`)).data||{};const values={};(this.practice.questions||[]).forEach(q=>{values[q.question_index]=q.student_answer||''});this.practiceAnswers=values;this.historyVisible=false}catch(error){this.$message.error(this.errorMessage(error)||'练习加载失败')}finally{this.practiceLoading=false}},
    showEvidence(row){this.evidencePoint=row;this.evidenceVisible=true}, sourceText(value){return ({assignment:'已评分作业',practice:'个人练习'})[value]||value},
    classStatus(row){if(row.sample_status==='none')return{type:'info',text:'暂无成绩'};if(row.sample_status==='limited')return{type:'warning',text:'样本积累中'};return row.is_class_weak?{type:'danger',text:'班级薄弱点'}:{type:'success',text:'正常'}},
    practiceStatus(value){return ({ready:{type:'info',text:'待作答'},feedback_pending:{type:'warning',text:'反馈生成中'},completed:{type:'success',text:'已完成'},feedback_failed:{type:'danger',text:'反馈失败，可重试'}})[value]||{type:'info',text:value||'未知'}},
    formatTime(value){return value?new Date(value).toLocaleString():''}, errorMessage(error){if(error&&error.response&&error.response.data)return error.response.data.msg||error.response.data.detail;return error&&error.message},
    openAssignmentEvidence(item){this.$store.dispatch('setCurrentAssignment',{id:item.assignment_id,a_id:item.assignment_id,a_name:item.assignment_title});this.$router.push({name:'学生成绩',query:{question:item.question_position}})},
    async openPracticeEvidence(item){this.evidenceVisible=false;await this.openPracticeSession(item.practice_session_id)},
    async waitForRun(runId){for(let index=0;index<240;index++){const run=(await apiV1.get(`/agent-runs/${runId}`)).data;if(run.status==='succeeded')return run;if(run.status==='failed'||run.status==='cancelled')throw new Error(run.error||run.last_error||'智能体任务失败');await new Promise(resolve=>setTimeout(resolve,1000))}throw new Error('处理时间较长，任务仍可能在后台继续；稍后可从练习历史查看结果')},
    async generatePractice(){this.generating=true;try{const created=await apiV1.post(`/student/offerings/${this.offeringId}/practice-jobs`,{idempotency_key:`practice-${this.offeringId}-${Date.now()}`,knowledge_point_ids:[],question_count:5});this.practiceRunId=created.data.agent_run_id;const run=await this.waitForRun(this.practiceRunId);await this.loadPracticeHistory();const sessionId=run.result&&run.result.practice_session_id;if(sessionId)await this.openPracticeSession(sessionId)}catch(error){this.$message.error(this.errorMessage(error)||'个性化练习生成失败')}finally{this.generating=false}},
    async submitPractice(){const answers=(this.practice.questions||[]).map(q=>({question_index:q.question_index,content:(this.practiceAnswers[q.question_index]||'').trim()}));if(answers.some(item=>!item.content)){this.$message.warning('请完成全部练习题后再提交');return}this.submittingPractice=true;try{const created=await apiV1.post(`/student/practice-sessions/${this.practice.id}/submit`,{answers,idempotency_key:`practice-feedback-${this.practice.id}-${Date.now()}`});this.practice.status='feedback_pending';const run=await this.waitForRun(created.data.agent_run_id);await this.openPracticeSession((run.result&&run.result.practice_session_id)||this.practice.id);await this.loadPracticeHistory();this.data=(await apiV1.get(`/student/offerings/${this.offeringId}/learning-profile`)).data||{};this.$message.success('学习助手已完成逐题反馈')}catch(error){await this.openPracticeSession(this.practice.id);this.$message.error(this.errorMessage(error)||'练习反馈失败，请稍后重试')}finally{this.submittingPractice=false}}
  }
}
</script>

<style scoped>
.page-shell{padding:32px 48px;min-height:80vh;background:#f6f8fb}.page-heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px}.heading-actions{display:flex;gap:10px}h2{margin:0 0 8px}p{margin:0;color:#7b8794}.metrics{display:grid;grid-template-columns:repeat(3,minmax(160px,1fr));gap:16px;margin-bottom:20px}.metrics b{display:block;font-size:30px;color:#2379d8}.metrics span{color:#7b8794}.student-page{padding-top:32px}.no-score{color:#909399;font-size:13px}.practice-dialog-body{max-height:62vh;overflow-y:auto;padding-right:8px}.practice-heading{position:sticky;top:0;z-index:2;background:#fff;padding-bottom:8px}.practice-state{display:flex;align-items:center;gap:12px;margin-top:12px}.practice-question{padding:18px 0;border-bottom:1px solid #edf0f3;line-height:1.7}.practice-question .el-textarea{margin-top:10px}.practice-feedback{margin-top:12px;padding:12px 14px;border-radius:7px;background:#f6f8fb}.practice-feedback>div{display:flex;align-items:center;gap:10px}.practice-feedback p{margin:8px 0;color:#4e5965}.practice-feedback small{display:block;color:#6f7a86;line-height:1.6}.pending-text{margin-right:14px;color:#e6a23c}.history-list,.evidence-drawer{padding:0 24px}.history-item{position:relative;padding:15px 34px 15px 0;border-bottom:1px solid #edf0f3;cursor:pointer}.history-item:hover b{color:#409eff}.history-item>div{display:flex;align-items:center;gap:8px}.history-item p{margin:6px 0;font-size:13px}.history-item>strong{color:#409eff}.history-item>i{position:absolute;right:4px;top:34px;color:#a0a8b1}.evidence-title{margin:8px 0 4px;color:#4e5965}.evidence-drawer small{display:block;color:#7b8794;line-height:1.5;max-height:66px;overflow:hidden}.evidence-drawer .el-button{padding-top:8px}@media(max-width:900px){.page-shell{padding:24px}.page-heading{align-items:flex-start;gap:16px}.heading-actions{flex-wrap:wrap}.metrics{grid-template-columns:1fr}}
</style>
