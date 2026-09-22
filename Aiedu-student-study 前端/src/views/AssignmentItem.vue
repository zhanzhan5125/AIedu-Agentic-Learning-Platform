<template>
  <div>
    <div class="wrapper" style="width: 100%;display: flex;padding-top:0;border-bottom: 1px solid #ccc;">
      <div style="font-size: larger; color: #2196f3;  padding-bottom: 17px;padding-top:17px;padding-left:70px">{{ course.title || course.tittle }}</div>
      <el-menu
          :default-active="'/assignment'" router
          background-color="white"
          text-color="black"
          active-text-color="#2196f3"
          class="el-menu-demo"
          mode="horizontal"
          :ellipsis="true"
          style="flex-grow: 1; display: flex; justify-content: flex-end;border-bottom: none;padding-right:50px"
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
      <el-main>
      <div class="title-container">
        <span class="title">{{this.currentAssignment.a_name}}</span>
        <router-link class="router" to="/assignment">返回</router-link>
      </div>
        <div style="height: 75vh">
        <div v-for="(item, index) in itemtable" :key="index" style="margin-bottom: 20px; padding-left: 20px; padding-right: 20px">
          <div style="display: flex; flex-direction: row; align-items: center">
            <div style="font-size: medium;margin-left: 70px">第{{index+1}}题</div>
            <div style="margin-left:10px;display:inline;background-color: #e3effc;color: #409dfd;border-radius: 3px;padding: 3px">&nbsp;{{item.item_type}}&nbsp;({{item.item_score}}分)</div>
          </div>
          <div style="padding:20px;border-bottom: 1px solid #ccc; margin-top: 10px; margin-left:50px;word-break: break-all; white-space: pre-wrap; color: black">{{ item.item_main }}</div>
          <div style="margin-top: 10px;border-bottom: 1px solid #ccc;">
            <div style="display:inline;background-color: #e3effc;color: #409dfd;border-radius: 3px;padding: 3px;margin-left: 70px">&nbsp;答案&nbsp;</div>
            <div  style="padding:20px;word-break: break-all; white-space: pre-wrap;color: black;margin-left: 70px">{{ item.item_answer }}</div>
          </div>
        </div>
    </div>
      </el-main>
    </div>
</template>

<script>
import apiV1 from '@/utils/apiV1'

export default {
  name: "language",
  data() {
    return {
      user:null,
      course:null,
      currentItem:null,
      currentAssignment:null,
      timeForm:{
        dateTime:null,
      },
      dialogVisible:false,
      itemtable:[],
      itemNum: 0,
      totalScore:0,
      headerBg: 'headerBg',
      rules: {
        dateTime: [{ required: true, message: '请选择截止时间', trigger: 'change' }]
      },

    }
  },
  created() {
    this.course = this.$store.getters.getCourse;
    this.user = this.$store.getters.getUser;
    this.currentAssignment = this.$store.getters.getCurrentAssignment;
    this.load()
  },
  methods: {
    async load() {
      try {
        const res = await apiV1.get(`/teacher/assignments/${this.currentAssignment.a_id}`)
        const detail = res.data || {}
        this.itemtable = (detail.questions || []).map(item => ({
          item_type: ({ short_answer: '简答题', single_choice: '单选题',
            multiple_choice: '多选题', programming: '编程题' })[item.kind] || item.kind,
          item_score: item.score,
          item_main: item.prompt,
          item_answer: item.reference_answer || '暂无参考答案'
        }))
        this.itemNum = this.itemtable.length
        this.totalScore = detail.total_score || this.itemtable.reduce((sum, item) => sum + item.item_score, 0)
      } catch (error) {
        this.itemtable = []
        this.$message.error(error.response?.data?.msg || '作业题目加载失败，请稍后重试')
      }
    }
  }
}


</script>

<style>

.content {
  display: flex;
  flex-direction: column;
  justify-content: center;
  width: 96rem;
}
.title-container {
  border-bottom: 1px solid #ccc;
  padding-bottom: 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.title {
  display: block;
  font-size: 18px;
  color: black;
  font-weight: bold;
  margin-left: 50px;
}

.router{
  text-decoration: none; /* 去掉下划线 */
  color: #0177FBFF; /* 保持默认文字颜色 */
  cursor: pointer; /* 添加手型光标 */
  font-size: 13px;
  margin-right: 70px;
}
</style>
