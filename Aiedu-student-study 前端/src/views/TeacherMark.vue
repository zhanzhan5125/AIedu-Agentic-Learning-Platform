<template>
  <div id="content" class="content" >
  <div class="answer-container" style="display: flex; flex-direction: column;">
    <div class="answer-header"
         style="height: 60px; width: 100%; border-bottom: 3px solid #ccc; display: flex; justify-content: space-between;">
      <div class="left-side" style="height: 100%;margin-left:40px">
        <div class="left-upper" style="font-size:18px;margin-top:3px">
          <p>{{ this.assignment.a_name }}</p>
        </div>
        <div class="left-bottom" style="color:#BFBFBF;margin-top:3px;font-size:14px;display:flex;">
          <p>姓名：{{this.student.s_name}}&nbsp&nbsp&nbsp学号：{{this.student.s_id}}</p>
        </div>
      </div>

      <div class="right-side" style="height: 100%; line-height: 57px;margin-left: auto;margin-right:10px">
        <el-button type="primary" style="width:150px;margin-right: 10px" round @click="saveToDatabase(1)">确认成绩并保存</el-button>
        <el-button type="success" style="width:120px;margin-right: 10px" round @click="saveToDatabase(2)">保存并进入下一份</el-button>
        <el-button type="info" style="width:120px;margin-right: 20px" round @click="saveToDatabase(3)">仅进入下一份</el-button>
        <router-link type="primary" class="router" to="/checkassignment" style="margin-right: 50px">返回</router-link>
      </div>
    </div>

    <div v-if="aiGrading" class="ai-summary">
      <div>
        <strong>AI 批阅建议：{{ aiGrading.total_score }} 分</strong>
        <el-tag size="mini" :type="aiGrading.confidence >= 70 ? 'success' : 'warning'">
          置信度 {{ aiGrading.confidence || 0 }}%
        </el-tag>
      </div>
      <p>{{ aiGrading.overall_comment }}</p>
      <p v-if="aiGrading.review_reason" class="review-warning">
        <i class="el-icon-warning-outline" /> {{ aiGrading.review_reason }}
      </p>
    </div>

    <div class="answer-bottom" style="height: 100%; width: 95%; display: grid; grid-template-columns: 300px 1fr;">
      <div class="answer-aside" style="background-color: #EAF4FD; border-right: 1px solid #ccc;">
        <div class="block" style="width:100%;height:20px;background-color: #EAF4FD"></div>
        <div class="answer-problems"
             style="background-color: white;margin-left: 20px;margin-right:20px;border-radius: 20px;padding:15px">
          <div class="answer-title" style="display:flex;height:30px;width:100%">
            <p style="font-size:18px">题目列表</p>
            <div style="font-size:16px;display: flex;margin-top:2px">
              <p style="margin-left: 6px">(</p>
              <p>{{ total_score }}</p>
              <p>分)</p>
            </div>
          </div>
          <div class="answer-body" style="height:100px;width:100%;margin-top:10px">
            <el-row :gutter="20">
              <el-col :span="6" v-for="item in tableData" :key="item.porder" :offset="0">
                <el-button
                    :class="{ activeButton: item.porder === p_now }"
                    style="height: 40px; width: 40px; margin-bottom: 20px; border: 2px solid #409EFF; border-radius: 6px; display: flex; justify-content: center; align-items: center;"
                    @click="changeProblem(item.porder)"
                >
                  <p :style="{ color: item.porder === p_now ? 'white' : '#409EFF', fontSize: '20px' }">{{ item.porder }}</p>
                </el-button>
              </el-col>
            </el-row>
          </div>
        </div>
      </div>
      <div class="answer-sheet" style="padding: 30px;overflow-x:hidden">
        <div class="sheet-inside" style="border:2px solid #E4EDF8;padding:20px">
          <div class="problem-title" style="word-break: break-all;">
            <p>第{{this.p_now}}题({{this.score}}分)</p>
            <p>&nbsp;</p>
            <p style="margin: 0;line-height: 20px;text-align: left;display: inline;color: black;word-break: break-all; white-space: pre-wrap;">
            {{this.p_main}}
            </p>
          </div>
          <div style="margin-top:20px">
            <div style="margin-bottom: 10px;color: #888888;margin-left: 5px">正确答案:</div>
            <div style="border:2px solid #E4EDF8;padding:20px;word-break: break-all; white-space: pre-wrap;">{{this.rightAnsContent}}</div>
          </div>
          <div style="margin-top:20px">
            <div style="margin-bottom: 10px;color: #888888;margin-left: 5px;">学生答案:</div>
            <div style="border:2px solid #E4EDF8;padding:20px;word-break: break-all; white-space: pre-wrap;">
              <div style="max-width: 100%;overflow: auto;white-space: pre-wrap;">{{ stuAnsContent }}</div>
            </div>
          </div>
          <div style="margin-top:20px">
            <div style="margin-bottom: 10px;color: #888888;margin-left: 5px">智能批阅:</div>
            <div v-loading="llmLoading" element-loading-text="批阅中" class="ai-detail">
              <template v-if="chatCheckContent">
                <div class="ai-score-line">
                  <strong>建议得分：{{ aiSuggestedScore === null ? '-' : aiSuggestedScore }} / {{ score }}</strong>
                  <el-tag v-if="aiConfidence !== null" size="mini" :type="aiConfidence >= 70 ? 'success' : 'warning'">
                    {{ aiConfidence }}% 置信度
                  </el-tag>
                  <el-tag v-if="aiErrorType" size="mini" type="danger">{{ aiErrorType }}</el-tag>
                </div>
                <p>{{ chatCheckContent }}</p>
                <div v-if="aiRubric.length" class="rubric-box">
                  <strong>评分要点</strong>
                  <ul><li v-for="(item, index) in aiRubric" :key="index">{{ item }}</li></ul>
                </div>
                <div v-if="aiEvidenceExcerpt" class="evidence-box">
                  <strong>学生答案依据</strong>
                  <p>“{{ aiEvidenceExcerpt }}”</p>
                </div>
              </template>
              <span v-else class="empty-ai">尚无 AI 建议，可直接人工批阅。</span>
            </div>
          </div>
          <div style="margin-top:20px">
            <div style="margin-bottom: 10px;color: #888888;margin-left: 5px">教师批阅:</div>
            <el-input type="textarea" :rows="4" v-model="teacherCheckContent" placeholder="确认或修改 AI 评语" />
          </div>
          <div style="margin-top:20px">
            <div style="margin-bottom: 10px;color: #888888;margin-left: 5px">该题得分:</div>
            <el-input-number v-model="stuScoreContent" placeholder="请输入分数" size="medium"  :min="0" :max="this.score"></el-input-number>
          </div>
          <div style="margin-top:20px">
            <div style="margin-bottom: 10px;color: #888888;margin-left: 5px">总体评语:</div>
            <el-input type="textarea" :rows="3" v-model="overallComment" placeholder="可确认或修改 AI 总体评语" />
          </div>
        </div>
        <div style="text-align: center">
          <el-button :disabled="isFirstItem" type="primary" round style="width:140px;margin-top:20px;text-align: center" @click="lastItem()">上一题</el-button>
          <el-button :disabled="isLastItem" type="primary" round style="width:140px;margin-top:20px;text-align: center" @click="saveItem()">下一题</el-button>
        </div>
      </div>
    </div>
  </div>
  </div>
</template>


<script>
import apiV1 from '@/utils/apiV1'

export default {
  name: "Answer",
  data() {
    return {
      user:null,
      student:null,
      assignment:null,
      isFirstItem:true,
      isLastItem:false,
      totalItem:3,
      p_now:1,
      hs_num: 7,
      total_score: 0,
      tableData: [],
      teacherCheckContent:'',
      stuScoreContent:0,
      stuAnsContent:'',
      rightAnsContent:'',
      chatCheckContent:'',
      aiSuggestedScore:null,
      aiConfidence:null,
      aiErrorType:null,
      aiEvidenceExcerpt:'',
      aiRubric:[],
      aiGrading:null,
      overallComment:'',
      p_main:"",
      score:0,
      stuList:null,
      llmLoading:false
    }
  },
  created() {
    // 在教师批阅组件中
    this.stuList = this.$store.getters.getStuList
    this.user = this.$store.getters.getUser
    this.student = this.$store.getters.getStudent
    this.assignment = this.$store.getters.getCurrentAssignment
    this.course = this.$store.getters.getCourse
    this.load()
  },
  methods:{
    changeProblem(item){
      this.tableData[this.p_now-1].stuScore = this.stuScoreContent;
      this.tableData[this.p_now - 1].teacherCheck = this.teacherCheckContent;
      this.p_now=item;
      this.check()
      this.putTo()
    },
    async saveToDatabase(index){
      if(index === 3){
        this.goToNextStudent()
      }
      else {
        this.tableData[this.p_now - 1].stuScore = this.stuScoreContent;
        this.tableData[this.p_now - 1].teacherCheck = this.teacherCheckContent;
        try {
          await apiV1.post(`/teacher/submissions/${this.student.submission_id}/grade`, {
            items: this.tableData.filter(item => item.aid).map(item => ({
              answer_id: item.aid,
              score: item.stuScore || 0,
              comment: item.teacherCheck || null
            })),
            overall_comment: this.overallComment || null
          })
          this.$message.success('批阅成功')
          if (index === 1) this.$router.push({ name: '查看作业' })
          else this.goToNextStudent()
        } catch (error) {
          this.$message.error(error.response?.data?.msg || '批阅保存失败')
        }
      }
    },
    goToNextStudent() {
      const targetIndex = this.stuList.findIndex(item => item.submissionId === this.student.submission_id)
      if (targetIndex < 0 || targetIndex >= this.stuList.length - 1) {
        this.$message.info('当前已为最后一份')
        this.$router.push({ name: '查看作业' })
        return
      }
      const next = this.stuList[targetIndex + 1]
      const currentStudent = {
        s_name: next.sname,
        s_id: next.sid,
        student_id: next.studentId,
        submission_id: next.submissionId
      }
      this.$store.dispatch('setStudent', currentStudent)
      this.student = currentStudent
      this.load()
    },
    async load(){
      this.p_now = 1
      if (!this.student || !this.student.submission_id) {
        this.$message.warning('未选择学生提交记录')
        this.$router.push({ name: '查看作业' })
        return
      }
      try {
        const res = await apiV1.get(`/teacher/submissions/${this.student.submission_id}`)
        const detail = res.data || {}
        const hasFinalGrade = ['graded', 'returned'].includes(detail.status)
        this.aiGrading = detail.ai_grading || null
        this.overallComment = detail.overall_comment || (!hasFinalGrade && this.aiGrading?.overall_comment) || ''
        this.tableData = (detail.questions || []).map(item => ({
          aid: item.answer_id,
          porder: item.position,
          main: item.prompt,
          score: item.score,
          stuAns: item.answer || '未作答',
          rightAns: item.reference_answer || '暂无参考答案',
          chatCheck: item.ai_comment || '',
          aiSuggestedScore: item.ai_suggested_score,
          aiConfidence: item.ai_confidence,
          aiErrorType: item.ai_error_type,
          aiEvidenceExcerpt: item.ai_evidence_excerpt || '',
          aiRubric: item.ai_rubric || [],
          stuScore: hasFinalGrade ? (item.earned_score || 0) : (item.ai_suggested_score ?? item.earned_score ?? 0),
          teacherCheck: item.teacher_comment || (!hasFinalGrade ? item.ai_comment : '') || ''
        }))
        this.totalItem = this.tableData.length
        this.total_score = this.tableData.reduce((sum, item) => sum + item.score, 0)
        if (this.totalItem > 0) {
          this.check()
          this.putTo()
        }
      } catch (error) {
        this.tableData = []
        this.$message.error(error.response?.data?.msg || '提交详情加载失败')
      }
    },
    check() {
      if (this.p_now !== 1) {
        this.isFirstItem = false
      } else if (this.p_now === 1) {
        this.isFirstItem = true
      }
      if (this.p_now === this.totalItem) {
        this.isLastItem = true
      } else if (this.p_now !== this.totalItem) {
        this.isLastItem = false
      }
    },
    saveItem() {
      this.tableData[this.p_now - 1].stuScore = this.stuScoreContent;
      this.tableData[this.p_now - 1].teacherCheck = this.teacherCheckContent;
      this.p_now = this.p_now + 1;
      this.check()
      this.putTo()
    },
    lastItem() {
      this.tableData[this.p_now - 1].stuScore = this.stuScoreContent;
      this.tableData[this.p_now - 1].teacherCheck = this.teacherCheckContent;
      this.p_now = this.p_now - 1;
      this.check()
      this.putTo()
    },
    putTo() {
      this.p_main = this.tableData[this.p_now - 1].main;
      this.score = this.tableData[this.p_now-1].score;
      this.stuAnsContent = this.tableData[this.p_now - 1].stuAns;
      this.rightAnsContent = this.tableData[this.p_now - 1].rightAns;
      this.chatCheckContent = this.tableData[this.p_now - 1].chatCheck;
      this.aiSuggestedScore = this.tableData[this.p_now - 1].aiSuggestedScore;
      this.aiConfidence = this.tableData[this.p_now - 1].aiConfidence;
      this.aiErrorType = this.tableData[this.p_now - 1].aiErrorType;
      this.aiEvidenceExcerpt = this.tableData[this.p_now - 1].aiEvidenceExcerpt;
      this.aiRubric = this.tableData[this.p_now - 1].aiRubric || [];
      this.stuScoreContent = this.tableData[this.p_now - 1].stuScore;
      this.teacherCheckContent = this.tableData[this.p_now - 1].teacherCheck;
    }
  }
}
</script>

<style scoped>
.activeButton {
  background-color: #409EFF; /* 设置当前激活按钮的背景色为蓝色 */
}

.answer-sheet {
  padding: 30px;
  overflow-x: hidden;
}

.sheet-inside {
  border: 2px solid #E4EDF8;
  overflow-y: auto;
  height: 72vh; /* 设置容器高度为自适应 */
  padding: 20px;
}

.problem-title p {
  overflow-wrap: break-word;
  /* 或者使用 word-wrap: break-word; */
}
.content {
  padding-left: 10px;
  padding-right: 10px;
}
.ai-summary {
  margin: 12px 5% 0;
  padding: 14px 18px;
  border: 1px solid #d9ecff;
  border-radius: 8px;
  background: #f4faff;
}
.ai-summary > div { display: flex; align-items: center; gap: 10px; }
.ai-summary p { margin: 8px 0 0; color: #606266; }
.ai-summary .review-warning { color: #e6a23c; }
.ai-detail {
  min-height: 90px;
  border: 2px solid #E4EDF8;
  padding: 20px;
  word-break: break-word;
  white-space: pre-wrap;
}
.ai-score-line { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.rubric-box, .evidence-box { margin-top: 12px; padding: 10px 12px; border-radius: 6px; background: #f7f9fc; }
.rubric-box ul { margin: 8px 0 0; padding-left: 20px; }
.evidence-box p { margin: 8px 0 0; color: #606266; }
.empty-ai { color: #909399; }
.router{
  text-decoration: none; /* 去掉下划线 */
  color: #0177FBFF; /* 保持默认文字颜色 */
  cursor: pointer; /* 添加手型光标 */
  font-size: 13px;
}
::v-deep img{
  width:100%;
}
</style>
