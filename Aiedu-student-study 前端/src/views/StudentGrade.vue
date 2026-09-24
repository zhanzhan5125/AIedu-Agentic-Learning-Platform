<template>
  <div id="content" class="content" >
  <div class="answer-container" style="display: flex;flex-direction: column;">
    <div class="answer-header"
         style="height: 60px; width: 100%; border-bottom: 3px solid #ccc; display: flex; justify-content: space-between;">
      <div class="left-side" style="height: 100%;width: 100%;margin-left:40px">
        <div class="left-upper" style="font-size:18px;margin-top:3px;width: 100%">
          <p>{{this.assignment.a_name}}</p>
        </div>
        <div class="left-bottom" style="color:#BFBFBF;margin-top:3px;font-size:14px;width:100%;display:flex;flex-direction: row;justify-content: space-between">
          <p>姓名：{{this.user.name}}&nbsp&nbsp&nbsp学号：{{this.user.id}}</p>
          <router-link type="primary" class="router" to="/student_course" style="margin-right: 30px">返回</router-link>
        </div>

      </div>
    </div>

    <div class="answer-bottom" style="height: 100%; width: 100%; display: grid; grid-template-columns: 300px 1fr;">
      <div class="answer-aside" style="background-color: #EAF4FD; border-right: 1px solid #ccc;">
        <div class="block" style="width:100%;height:20px;background-color: #EAF4FD"></div>
        <div  style="background-color: white;margin-left: 20px;margin-right:20px;margin-bottom:20px;border-radius: 20px;padding:15px">
          <div class="answer-title" style="display:flex;height:30px;width:100%">
            <p style="font-size:18px">总分：</p><p style="font-size:18px;color: #1d8dd8">{{this.total_score}}</p>
            <p style="font-size:18px;margin-left: 20px">成绩：</p><p style="font-size:18px;color: #DB1F35">{{ this.total_stuScore }}</p>
          </div>
        </div>
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
          <div class="problem-title" style="word-break: break-all; white-space: pre-wrap;">
            <p>第{{this.p_now}}题({{this.score}}分)</p>
            <p>&nbsp;</p>
            <p style="margin: 0;line-height: 20px;text-align: left;display: inline;color: black;">
              {{this.p_main}}
            </p>
          </div>
          <div style="margin-top:20px">
            <div style="margin-bottom: 10px;color: #888888;margin-left: 5px;">学生答案:</div>
            <div style="border:2px solid #E4EDF8;padding:20px;word-break: break-all; white-space: pre-wrap;">
              <div v-html="convertNewlinesToBreaks(this.stuAnsContent)" style="max-width: 100%;overflow: auto;"></div>
            </div>
          </div>
          <div style="margin-top:20px">
            <div style="margin-bottom: 10px;color: #888888;margin-left: 5px">正确答案:</div>
            <div style="border:2px solid #E4EDF8;padding:20px;word-break: break-all; white-space: pre-wrap;">{{this.rightAnsContent}}</div>
          </div>
          <div style="margin-top:20px">
            <div style="margin-bottom: 10px;color: #888888;margin-left: 5px">智能批阅:</div>
            <div style="border:2px solid #E4EDF8;padding:20px;word-break: break-all; white-space: pre-wrap;">{{this.chatCheckContent}}</div>
          </div>
          <div style="margin-top:20px">
            <div style="margin-bottom: 10px;color: #888888;margin-left: 5px">教师批阅:</div>
            <div style="border:2px solid #E4EDF8;padding:20px;width: 100%;word-break: break-all; white-space: pre-wrap;">
              {{ this.teacherCheckContent }}</div>
          </div>
          <div style="margin-top:20px">
            <div style="margin-bottom: 10px;color: #888888;margin-left: 5px">视频讲解:</div>
            <div style="border:2px solid #E4EDF8;padding:20px;width: 100%;">
              <Video :src="videoSrc"></Video>
            </div>
          </div>
          <div style="margin-top:20px">
            <div style="margin-bottom: 10px;color: #888888;margin-left: 5px;">该题得分:</div>
            <div style="border:2px solid #E4EDF8;padding:20px;width: 20%">{{ this.stuScoreContent }}</div>
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
import Video from "@/components/Video.vue";
import apiV1 from '@/utils/apiV1'

export default {
  name: "Answer",
  components: {Video},
  data() {
    return {
      user:null,
      course:null,
      assignment:null,
      isFirstItem:true,
      isLastItem:false,
      totalItem:3,
      p_now:1,
      hs_num: 7,
      total_score: 0,
      total_stuScore:0,
      tableData: [],
      teacherCheckContent:'',
      stuScoreContent:0,
      stuAnsContent:'',
      rightAnsContent:'',
      chatCheckContent:'',
      p_main:"",
      score:0,
      // videoSrc: require('@/views/img/AIVideo.mp4'),
      // poster:require('@/views/img/loginback.png')
      videoSrc:'http://www.courseaimate.cn/pic/aivideo.mp4',
      poster:'http://www.courseaimate.cn/pic/null_1710936834077.png'
    }
  },

  created() {
    this.user = this.$store.getters.getUser
    console.log(this.user)
    this.course = this.$store.getters.getCourse
    this.assignment = this.$store.getters.getCurrentAssignment
    this.load()
  },
  methods:{
    convertNewlinesToBreaks(text) {
      if (text) {
        // 检查是否存在 <p> 标签，如果存在则直接返回原始文本
        if (text.includes('<p>')) {
          return text;
        }
        // 替换除了 <img> 以外的所有标签中的 "<" 为 "&lt;"，并将换行符替换为 "<br>"
        text = text.replace(/<(?!img)/g, '&lt;');
        return text.replace(/\n/g, '<br>');
      }
    },
    changeProblem(item){
      this.p_now=item;
      this.check()
      this.p_main=this.tableData[this.p_now-1].main;
      this.score = this.tableData[this.p_now-1].score;
      this.stuAnsContent = this.tableData[this.p_now-1].stuAns;
      this.rightAnsContent = this.tableData[this.p_now-1].rightAns;
      this.chatCheckContent = this.tableData[this.p_now-1].chatCheck;
      this.stuScoreContent= this.tableData[this.p_now-1].stuScore ;
      this.teacherCheckContent =this.tableData[this.p_now-1].teacherCheck ;
    },
    async load(){
      const assignmentId = this.assignment && (this.assignment.id || this.assignment.a_id)
      if (!assignmentId) {
        this.$message.warning('未选择作业，请返回课程作业列表后重试')
        this.$router.push({ name: '学生课程' })
        return
      }
      try {
        const res = await apiV1.get(`/student/assignments/${assignmentId}`)
        const detail = res.data || {}
        if (!detail.result_visible) {
          this.$message.info('成绩尚未由教师确认')
          this.$router.push({ name: '学生课程' })
          return
        }
        this.assignment.a_name = detail.title
        this.tableData = (detail.questions || []).map(item => ({
          porder: item.position,
          main: item.prompt,
          score: item.score,
          stuAns: item.answer || '未作答',
          rightAns: item.reference_answer || '暂无参考答案',
          chatCheck: item.ai_comment || '暂无智能批阅意见',
          stuScore: item.earned_score || 0,
          teacherCheck: item.teacher_comment || '暂无教师评语'
        }))
        this.totalItem = this.tableData.length
        this.total_score = detail.total_score || this.tableData.reduce((sum, item) => sum + item.score, 0)
        this.total_stuScore = detail.submission?.total_score || 0
        if (this.totalItem > 0) {
          const requestedPosition = Number(this.$route.query.question)
          const target = this.tableData.find(item => item.porder === requestedPosition) || this.tableData[0]
          this.changeProblem(target.porder)
        }
      } catch (error) {
        this.$message.error(error.response?.data?.msg || '批阅结果加载失败，请稍后重试')
      }
    },
    check(){
      if(this.p_now !== 1){
        this.isFirstItem = false
      }
      else if(this.p_now === 1){
        this.isFirstItem = true
      }
      if(this.p_now === this.totalItem){
        this.isLastItem = true
      }
      else if(this.p_now !== this.totalItem){
        this.isLastItem = false
      }
    },
    saveItem(){
      this.p_now=this.p_now+1;
      this.check()
      this.p_main=this.tableData[this.p_now-1].main;
      this.score = this.tableData[this.p_now-1].score;
      this.stuAnsContent = this.tableData[this.p_now-1].stuAns;
      this.rightAnsContent = this.tableData[this.p_now-1].rightAns;
      this.chatCheckContent = this.tableData[this.p_now-1].chatCheck;
      this.stuScoreContent= this.tableData[this.p_now-1].stuScore ;
      this.teacherCheckContent =this.tableData[this.p_now-1].teacherCheck ;
    },
    lastItem(){
      this.p_now=this.p_now-1;
      this.check()
      this.p_main=this.tableData[this.p_now-1].main;
      this.score = this.tableData[this.p_now-1].score;
      this.stuAnsContent = this.tableData[this.p_now-1].stuAns;
      this.rightAnsContent = this.tableData[this.p_now-1].rightAns;
      this.chatCheckContent = this.tableData[this.p_now-1].chatCheck;
      this.stuScoreContent= this.tableData[this.p_now-1].stuScore ;
      this.teacherCheckContent =this.tableData[this.p_now-1].teacherCheck ;
    },
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
  height: 73vh; /* 设置容器高度为自适应 */
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
.router{
  text-decoration: none; /* 去掉下划线 */
  color: #0177FBFF; /* 保持默认文字颜色 */
  cursor: pointer; /* 添加手型光标 */
  font-size: 13px;
}

</style>
