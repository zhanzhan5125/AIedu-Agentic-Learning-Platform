<!--作业库页面-->
<template>
    <div class="layout-container">
        <!-- Header 部分 -->
      <div class="wrapper" style="width: 100%; height: auto; display: flex;padding-top:0;border-bottom: 1px solid #ccc;">
        <p style="font-size: larger; color: #2196f3;  padding-bottom: 17px;padding-top:17px;padding-left:70px">{{ course.title || course.tittle }}</p>
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
        <div>
                    <el-main>
                        <div>
                            <div class="title-container">
                                <span class="title">{{this.currentAssignment.a_name}}</span>
                              <router-link class="router" to="/assignment">返回</router-link>
                            </div>
                            <el-row class="search-button-container" style="margin-top: 20px;">
                                <div class="demo-input-suffix">
                                    <el-input placeholder="请输入姓名，学号" v-model="searchStudent" clearable class="search-input">
                                        <el-button slot="append" icon="el-icon-search" @click="load"></el-button>
                                    </el-input>
                                </div>
                                <div style=" width: 100%; text-align: right;padding-right:20px">
                                    <el-button type="primary" round @click="llmCheckAssignment">
                                      AI 辅助批阅<span v-if="leftNumPendingReview">（{{ leftNumPendingReview }}）</span>
                                    </el-button>
                                    <el-button type="primary" round @click="detail">详情统计</el-button>
                                  <el-button type="info" round @click="exportScore">一键导出</el-button>
                                </div>
                            </el-row>
                        </div>
                      <div style="display: flex; align-items: center;">
                        <p style="color: #979797; margin-left: 5px; margin-right: 10px;">开始时间:{{this.currentAssignment.a_start_time}}</p>
                        <p style="color: #979797; margin-left: 5px; margin-right: 10px;">发送给:{{this.currentAssignment.total_num}}</p>
                        <p style="color: #979797; margin-left: 5px; margin-right: 10px;">已交:{{this.currentAssignment.submit_num}}</p>
                        <p style="color: #979797; margin-left: 5px; margin-right: 10px;">待批阅:{{this.leftNumPendingReview }}</p>
                        <p style="color: #979797; margin-left: 5px; margin-right: 10px;">AI处理中:{{this.AIProcessing }}</p>
                        <p style="color: #979797; margin-left: 5px; margin-right: 10px;">AI结果待教师确认:{{this.AICheck }}</p>
                        <p style="color: #979797; margin-left: 5px; margin-right: 10px;">已完成:{{this.TeaCheck }}</p>
                        <router-link class="router2" to="/no_submitted">查看未提交学生</router-link>
                        <div style="margin-left: auto;display: flex;flex-direction: row;align-items: center">
                        <div v-if="loading" style="margin-right: 10px">
                          <i class="el-icon-loading" style="color: #409dfd"></i> <i style="color: #409dfd">正在批阅中</i>
                        </div>
                        <div class="custom-loading" v-if="loading">
                          <el-progress :percentage="progressPercent" :stroke-width="10" show-text></el-progress>
                        </div>
                      </div>
                      </div>

                      <div class="table-container">

                        <el-table :data="tableData"
                                  @sort-change="handleSortChange"
                                  border stripe :header-cell-class-name="headerBg">
                          <el-table-column label="序号" align="center" width="80">
                            <template slot-scope="scope">
                              <span>{{ startIndex + scope.$index }}</span>
                            </template>
                          </el-table-column>
                            <el-table-column prop="sname" label="姓名"   align="center">
                            </el-table-column>
                            <el-table-column prop="sid" label="学号"  align="center">
                            </el-table-column>
                          <el-table-column prop="isChecked" label="作业状态" sortable="custom" align="center">
                            <template slot-scope="scope">
                              <span>{{ statusLabel(scope.row.isChecked) }}</span>
                            </template>
                          </el-table-column>
                            <el-table-column prop="submitTime" label="提交时间" sortable="custom" align="center">
                            </el-table-column>
                          <el-table-column prop="checkTime" label="批阅时间" sortable="custom" align="center">
                            <template slot-scope="scope">
                              <span>{{ scope.row.checkTime || (scope.row.isChecked === '已完成' ? '历史记录未保存' : '-') }}</span>
                            </template>
                          </el-table-column>
                            <el-table-column prop="totalScore" label="成绩" sortable="custom" align="center">
                            </el-table-column>
                            <el-table-column label="教师批阅" align="center">
                                <template slot-scope="scope">
                                    <el-button @click="handleMark(scope.row)" type="text" size="small">批阅</el-button>
                                </template>
                            </el-table-column>
                        </el-table>
        </div>
                        <div class="block" style="display: flex; justify-content: center;">
                            <el-pagination
                                @size-change="handleSizeChange"
                                @current-change="handleCurrentChange"
                                :current-page="pageNum"
                                :page-sizes="[8, 12, 16, 20]"
                                :page-size="pageSize"
                                layout="total, sizes, prev, pager, next,jumper"
                                :total="total">
                            </el-pagination>
                        </div>
                    </el-main>
        </div>
    </div>
</template>


<script>
import { mapState, mapMutations, mapActions } from 'vuex';
import apiV1 from '@/utils/apiV1'
export default {
  computed:{
    startIndex() {
      return (this.pageNum - 1) * this.pageSize + 1;
    },
    // 其他组件配置...
    beforeRouteEnter(to, from, next) {
      next(vm => {
        // 进入路由后调用组件实例的load方法
        vm.load();
      });
    },
    ...mapState(['pagination']),
    ...mapState(['sortParams']),
    pageNum: {
      get() {
        return this.$store.state.pagination.pageNum;
      },
      set(newNum) {
        this.$store.commit('setPageNum', newNum);
      },
    },
    pageSize: {
      get() {
        return this.$store.state.pagination.pageSize;
      },
      set(newSize) {
        this.$store.commit('setPageSize', newSize);
      },
    },
    sortField: {
      get() {
        return this.$store.state.sortParams.sortField;
      },
      set(newField) {
        this.$store.commit('setSortField', newField);
      },
    },
    sortOrder: {
      get() {
        return this.$store.state.sortParams.sortOrder;
      },
      set(newOrder) {
        this.$store.commit('setSortOrder', newOrder);
      },
    },
  },
    data() {
        return {
          searchStudent:null,
          course:null,
          user:null,
          currentAssignment:'',
            tableData: [],
            total: 0,
            // pageNum: 1,
            // pageSize: 8,
            headerBg: 'headerBg',
          loading:false,
          progressPercent: 50,
            // sortField: 'submitTime',
            // sortOrder: 'descending',
          stuList:null,
          leftNumPendingReview:0,
          AIProcessing:0,
          AICheck:0,
          TeaCheck:0
                };
    },
    created() {
      this.user = this.$store.getters.getUser;
      this.course = this.$store.getters.getCourse;
      this.currentAssignment = this.$store.getters.getCurrentAssignment;
      this.load();
    },
  methods:{
    ...mapMutations(['setPageNum', 'setPageSize','setSortField','setSortOrder']),
    ...mapActions(['updatePageInfo','updateSortParams']),
    statusLabel(status) {
      const labels = {
        '待批阅': '待批阅',
        'AI处理中': 'AI 处理中',
        '智能批阅': 'AI 结果待教师确认',
        '已完成': '已批阅'
      }
      return labels[status] || status
    },
    async load() {
      try {
        const response = await apiV1.get(`/teacher/assignments/${this.currentAssignment.a_id}/submissions`)
        const data = response.data || {}
        const keyword = (this.searchStudent || '').trim().toLowerCase()
        this.stuList = (data.records || []).map(item => ({
          submissionId: item.id,
          sid: item.student_account,
          studentId: item.student_id,
          sname: item.student_name,
          isChecked: ({
            submitted: '待批阅',
            ai_grading: 'AI处理中',
            needs_review: '智能批阅',
            graded: '已完成',
            returned: '已完成'
          })[item.status] || item.status,
          submitTime: item.submitted_at,
          checkTime: item.graded_at || item.ai_graded_at,
          totalScore: item.total_score
        })).filter(item => !keyword || item.sname.toLowerCase().includes(keyword) ||
          item.sid.toLowerCase().includes(keyword))
        this.total = this.stuList.length
        const start = (this.pageNum - 1) * this.pageSize
        this.tableData = this.stuList.slice(start, start + this.pageSize)
        this.leftNumPendingReview = this.stuList.filter(student => student.isChecked === '待批阅').length;
        this.AIProcessing = this.stuList.filter(student => student.isChecked === 'AI处理中').length;
        this.AICheck = this.stuList.filter(student => student.isChecked === '智能批阅').length;
        this.TeaCheck = this.stuList.filter(student => student.isChecked === '已完成').length;

        // 更新当前作业信息
        const assignment = {
          a_id: this.currentAssignment.a_id,
          a_name: this.currentAssignment.a_name,
          a_start_time: this.currentAssignment.a_start_time,
          a_end_time: this.currentAssignment.a_end_time,
          submit_num: data.submitted_count,
          total_num: data.assigned_count,
          left_num: data.not_submitted_count,
          AICheck: this.AICheck,
          TeaCheck: this.TeaCheck
        };
        await this.$store.dispatch('setCurrentAssignment', assignment);
        this.currentAssignment = this.$store.getters.getCurrentAssignment;
      } catch (error) {
        this.tableData = []
        this.stuList = []
        this.$message.error(error.response?.data?.msg || '提交记录加载失败，请稍后重试')
      }
    },
    llmCheckAssignment(){
      this.$router.push(
          {name: '智能批阅'}
      )
    },
    async exportScore(){
      try {
        const blob = await apiV1.get(`/teacher/assignments/${this.currentAssignment.a_id}/grades.csv`, {
          responseType: 'blob'
        })
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = `${this.currentAssignment.a_name}-成绩.csv`
        link.click()
        URL.revokeObjectURL(url)
      } catch (error) {
        this.$message.error(error.response?.data?.msg || '成绩导出失败')
      }
    },
    handleMark(row){
      if(row.isChecked === 'AI处理中'){
        this.$message.warning('智能批阅中，请稍后再试')
        return
      }
      this.setSortOrder(this.sortOrder)
      this.setSortField(this.sortField)
      console.log(this.stuList)
      const student = {
        s_name:row.sname,
        s_id:row.sid,
        student_id: row.studentId,
        submission_id: row.submissionId,
      }
      console.log(row)
      this.$store.dispatch('setStuList',this.stuList)
      this.$store.dispatch("setStudent",student)
        this.$router.push({
        name:'教师批阅'
      })
    },
    handleSizeChange(pageSize){
      console.log(pageSize)//控制台输出相关数据
      this.setPageSize(pageSize)
      this.load()
    },
    handleCurrentChange(pageNum){
      console.log(pageNum)
      this.setPageNum(pageNum);
      this.load()
    },
    handleSortChange({ prop, order }) {
      // prop: 当前排序列的字段名
      // order: 当前排序的顺序（'ascending' 升序，'descending' 降序）
      this.sortField = prop
      this.sortOrder = order
      console.log(this.sortParams)
      this.load()
    },

    detail(){
      console.log(this.currentAssignment)
      if(this.TeaCheck === 0){
        this.$message.warning('无批阅信息，请批阅后重试')
      }
      else{
        this.$router.push({
          name:'作业详情统计'
        })
      }
    }
  }
}
</script>
<style>
.title {
    display: block;
    font-size: 18px;
    color: black;
    font-weight: bold;
  margin-left: 50px;
}

.search-button-container {
    display: flex;
    margin-bottom: 20px;
}
.search-input {
    width: 250px;
    /* 设置输入框宽度 */
}
.router{
  text-decoration: none; /* 去掉下划线 */
  color: #0177FBFF; /* 保持默认文字颜色 */
  cursor: pointer; /* 添加手型光标 */
  font-size: 13px;
  margin-right: 70px;
}
.router2{
  //text-decoration: none; /* 去掉下划线 */
  color: #0177FBFF; /* 保持默认文字颜色 */
  cursor: pointer; /* 添加手型光标 */
  font-size: 15px;
}
.title-container {
  border-bottom: 1px solid #ccc;
  padding-bottom: 10px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  margin-bottom: 10px;
}
.table-container {
  display: flex;
  margin-right: 0;
  margin-top: 20px;
  padding-left: 50px;
  padding-right: 50px;
  margin-bottom: 20px;
  }
.custom-loading {
  width: 300px;
}
</style>
