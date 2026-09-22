<template>
  <div class="layout-container">
    <!-- Header 部分 -->
    <!-- Header 部分 -->
    <div class="wrapper" style="width: 100%; height: auto; display: flex;padding-top:0;border-bottom: 1px solid #ccc;">
      <p style="font-size: larger; color: #2196f3;  padding-bottom: 17px;padding-top:17px;padding-left:70px">
        {{ course.title || course.tittle }}</p>
      <el-menu  :default-active="'/assignment'" router background-color="white" text-color="black"
               active-text-color="#2196f3" class="el-menu-demo" mode="horizontal" :ellipsis="true"
               style="flex-grow: 1; display: flex; justify-content: flex-end;border-bottom: none;padding-right:50px">
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
      <el-container>
        <el-container>
          <el-main>
            <div>
              <div class="title-container">
                <span class="title">{{this.assignment.a_name}}&nbsp;未提交学生名单</span>
                <router-link class="router" to="/checkassignment">返回</router-link>
              </div>
              <el-row class="search-button-container" style="margin-top: 20px;">
                <div class="demo-input-suffix">
                  <el-input placeholder="请输入姓名或学号" v-model="studentSearch" clearable class="search-input">
                    <el-button slot="append" icon="el-icon-search" @click="load"></el-button>
                  </el-input>
                </div>
              </el-row>
            </div>

            <div class="table-container">
              <el-table :data="tableData" border stripe :header-cell-class-name="headerBg">
                <el-table-column label="序号" align="center" width="80">
                  <template slot-scope="scope">
                    <span>{{ startIndex + scope.$index }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="sname" label="姓名" align="center">
                </el-table-column>
                <el-table-column prop="sid" label="学号" align="center">
                </el-table-column>
              </el-table>
            </div>

            <div class="block" style="display: flex; justify-content: center;">
              <el-pagination @size-change="handleSizeChange" @current-change="handleCurrentChange" :current-page="pageNum"
                             :page-sizes="[8, 12, 16, 20]" :page-size="pageSize" layout="total, sizes, prev, pager, next,jumper"
                             :total="total">
              </el-pagination>
            </div>
          </el-main>
        </el-container>
      </el-container>
    </div>
  </div>
</template>


<script>
import {mapActions, mapMutations, mapState} from "vuex";
import apiV1 from '@/utils/apiV1'
export default {
  computed:{
    startIndex() {
      return (this.pageNum - 1) * this.pageSize + 1;
    },
    ...mapState(['pagination']),
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
  },
  data() {
    return {
      user: null,
      course: null,
      assignment:null,
      currentCourse: null,
      tableData: [],
      multipleSelection: [],
      number: 0,
      total: 0,
      // pageNum: 1,
      // pageSize: 8,
      headerBg: 'headerBg',
      studentSearch: null,
    };
  },
  created() {
    this.user = this.$store.getters.getUser;
    this.course = this.$store.getters.getCourse;
    this.assignment = this.$store.getters.getCurrentAssignment;
    // this.$store.commit("init_user");
    // this.fetchData();
    this.load();
  },

  methods: {
    ...mapMutations(['setPageNum', 'setPageSize']),
    ...mapActions(['updatePageInfo']),
    load() {
      apiV1.get(`/teacher/assignments/${this.assignment.a_id}/unsubmitted`).then(res=>{
        const keyword=(this.studentSearch||'').trim().toLowerCase()
        const records=res.data.records.filter(item=>!keyword||item.name.toLowerCase().includes(keyword)||item.account.toLowerCase().includes(keyword))
        this.total=records.length
        this.tableData=records.slice((this.pageNum-1)*this.pageSize,this.pageNum*this.pageSize).map(item=>({...item,sid:item.account,sname:item.name}))
      })
    },
    // toggleSelection(rows) {
    //     if (rows) {
    //         rows.forEach(row => {
    //             this.$refs.multipleTable.toggleRowSelection(row);
    //         });
    //     } else {
    //         this.$refs.multipleTable.clearSelection();
    //     }
    // },
    handleSizeChange(pageSize) {
      console.log(pageSize)//控制台输出相关数据
      this.pageSize = pageSize
      this.load()
    },
    handleCurrentChange(pageNum) {
      console.log(pageNum)
      this.pageNum = pageNum
      this.load()
    },
    change: function (index) {
      this.number = index; //重要处
    },
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

.button-container {
  display: flex;
}

.search-input {
  width: 250px;
  /* 设置输入框宽度 */
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
  padding-left: 100px;
  padding-right: 100px;
  margin-bottom: 20px;
}

.demo-input-suffix {
  display: flex;
  flex-direction: row;
}


.router{
  text-decoration: none; /* 去掉下划线 */
  color: #0177FBFF; /* 保持默认文字颜色 */
  cursor: pointer; /* 添加手型光标 */
  font-size: 13px;
}

</style>

