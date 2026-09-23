<template>
  <div>
    <div class="wrapper" style="width: 100%;display: flex;padding-top:0;border-bottom: 1px solid #ccc;">
      <div style="font-size: larger; color: #2196f3;  padding-bottom: 17px;padding-top:17px;padding-left:70px">{{ course.title || course.tittle }}</div>
      <el-menu
          :default-active="$route.path" router
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
    <div id="content" class="content" v-loading="loading">
    <div class="center-wrapper">
      <div class="content-container">
        <el-empty v-if="!loading && tableData.length === 0"
                  description="当前没有作业发布，请先前往智能体工作台生成并审核作业草稿" />
        <el-row v-else :gutter="60">
          <el-col :xs="24" :sm="12" :md="8" :lg="8" :xl="6" v-for="(item) in tableData" :key="item.a_id">
            <div class="grid-content bg-purples">
              <div style="width: 100%;">
                <div class="assign-tittle">
                  <button class="text-button" @click="goToItem(item)">{{ item.a_name }}</button>
                  <div class="a_info">
                    开始时间:
                    <div class="detail">{{ item.a_start_time }}</div>
                  </div>
                  <div class="a_info">
                    截止时间:
                    <div class="detail">{{ item.a_end_time }}</div>
                  </div>
                  <div class="a_info">
                    提交数:<div class="detail">{{ item.submit_num }}</div> / <div class="detail" style="margin-left: 0">{{item.total_num}}</div>
                  </div>
                </div>
              </div>

              <div class="card-bottom"
                   style="width: 100%; height: 35%; background-color: #E4EDF8;display: flex; justify-content: space-between;border: 1px solid #ccc">
                <div class="box1" style="display: flex; align-items: center;">
                  <div style="margin-left: 10px; margin-right: 4px;display: flex;flex-direction: row">
                    <p style="font-size: 30px; color: #DB1F35; margin: 0;">{{item.leftNumPendingReview}}</p>
                  </div>
                  <p style="margin: 0;">份待完成批阅</p>
                </div>
                <div class="box2" style="display: flex; align-items: center;margin-right:10px">
                  <el-button type="success" @click="handleCheck(item)">查看</el-button>
                </div>
              </div>
            </div>
          </el-col>
        </el-row>
      </div>
    </div>
  </div>
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
      timeForm:{
        dateTime:null,
      },
      dialogVisible:false,
      loading:false,
      tableData:[],
      total: 0,
      pageNum: 1,
      pageSize: 8,
      headerBg: 'headerBg',
      rules: {
        dateTime: [{ required: true, message: '请选择截止时间', trigger: 'change' }]
      },

    }
  },
  created() {
    this.course = this.$store.getters.getCourse;
    this.user = this.$store.getters.getUser;
    this.load()
  },
  methods: {
    async load() {
      const offeringId = this.course.id || this.course.offeringId || this.course.courseCode
      if (!offeringId) {
        this.$message.warning('未选择课程，请返回课程列表后重试')
        this.$router.push({ name: '主页' })
        return
      }
      this.loading = true
      try {
        const res = await apiV1.get('/teacher/assignments', { params: { offering_id: offeringId, include_drafts: false } })
        const records = (res.data && res.data.records) || []
        this.total = res.data?.total || records.length
        this.tableData = records.map(item => ({
          ...item,
          a_id: item.id,
          a_name: item.title,
          a_start_time: item.start_at,
          a_end_time: item.end_at,
          submit_num: item.submitted_count,
          total_num: item.assigned_count,
          left_num: item.not_submitted_count,
          leftNumPendingReview: item.pending_grading_count + item.ai_processing_count +
            item.pending_teacher_review_count
        }))
      } catch (error) {
        this.tableData = []
        this.$message.error(error.response?.data?.msg || '作业列表加载失败，请稍后重试')
      } finally { this.loading = false }
    },
    goToItem(item) {
      const assignment = {
        a_id:item.a_id,
        a_name: item.a_name,
        a_start_time:item.a_start_time,
        a_end_time:item.a_end_time,
        submit_num: item.submit_num,
        total_num: item.total_num,
        left_num:item.left_num,
      }
      this.$store.dispatch('setCurrentAssignment',assignment)
      // this.$store.dispatch('setSummary',0)
      this.$router.push({
        name:'作业题目' })
    },
    handleCheck(item){
      const assignment = {
        a_id:item.a_id,
        a_name: item.a_name,
        a_start_time:item.a_start_time,
        a_end_time:item.a_end_time,
        submit_num: item.submit_num,
        total_num: item.total_num,
        left_num:item.left_num,
      }
      this.$store.dispatch('setCurrentAssignment',assignment)
      // this.$store.dispatch('setSummary',0)
      const params = {id:item.a_id,name:item.a_name}
      this.$router.push({
        name:'查看作业',
        params:params })
    },
    gotoManageAss(){
      this.$router.push({
        path:'/manage_ass'})
    },
  }
}


</script>

<style scoped>

.bg-purples {
  background: #3162ae;
}
.content-container{
  width: 100%;
  max-width: 1600px;
  margin: 0 auto;
}

.center-wrapper {
  display: flex;
  justify-content: center;
  align-items: flex-start;
  width: 100%;
  padding: 0 clamp(16px, 5vw, 80px);
  box-sizing: border-box;
}

.grid-content {
  height: 200px;
  width: 100%;
  max-width: 350px;
  background: #ffffff;
  margin: 30px auto;
  border: 1px solid #ccc;
  box-shadow: 0 2px 4px rgba(0, 0, 0, .12), 0 0 6px rgba(0, 0, 0, .04)
}
.assign-tittle{
  align-content: center;
  height:20%
}
.detail{
  color:#3D3D3D;
  margin-left:5px
}
.a_info{
  display: flex;
  height:30px;
  line-height: 30px;
  margin-left:10px
}

.content {
  display: flex;
  flex-direction: column;
  justify-content: center;
  width: 100%;
  max-width: 1920px;
  margin: 0 auto;
  box-sizing: border-box;
}
.text-button {
  height:40px;
  line-height: 40px;
  margin-left:10px;
  font-size:20px;
  font-weight:bold;
  border: none;
  background-color: transparent;
  cursor: pointer;
}

@media (max-width: 767px) {
  .center-wrapper {
    padding: 0 12px;
  }

  .grid-content {
    max-width: 100%;
  }

  .wrapper .el-menu {
    padding-right: 12px !important;
  }
}

</style>
