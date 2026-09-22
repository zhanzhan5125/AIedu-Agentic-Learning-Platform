<!--作业库页面-->
<template>
  <div class="layout-container">
    <!-- Header 部分 -->
    <div>
      <el-container>
        <el-container>
          <el-main>
            <div>
              <div class="title-container">
                <span class="title">{{this.course.cNo}}&nbsp;{{ this.course.cName }}</span>
                <router-link class="router" to="/admin_home">返回</router-link>
              </div>
              <el-row class="search-button-container" style="margin-top: 20px;">
                <div class="demo-input-suffix">
                  <el-input placeholder="请输入教师姓名或编号" v-model="searchTeacher" clearable class="search-input">
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
                <el-table-column prop="ssSectionCode" label="教学班号" align="center">
                </el-table-column>
                <el-table-column prop="ssSectionName" label="教学班名称" align="center">
                </el-table-column>
                <el-table-column prop="tname" label="任课教师"  align="center">
                </el-table-column>
                <el-table-column prop="ssYear" label="开设学年"  align="center">
                </el-table-column>
                <el-table-column prop="ssTerm" label="开设学期"  align="center">
                </el-table-column>
                <el-table-column prop="ssStatus" label="课程状态"  align="center">
                </el-table-column>
                <el-table-column label="操作" align="center" width="150">
                  <template slot-scope="scope">
                    <el-popconfirm
                        confirm-button-text='确定'
                        cancel-button-text='我再想想'
                        icon="el-icon-info"
                        icon-color="red"
                        title="你确定删除吗？"
                        @confirm="handleDelete(scope.row.ssId)"
                        class="ml-5"
                    >
                    <el-button slot="reference" type="text" size="small" :style="{ color: 'red' }">删除</el-button>
                    </el-popconfirm>
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
      dialogVisible:false,
      searchTeacher:null,
      user:null,
      course:null,
      tableData: [],
      courseForm:[],
      total: 0,
      // pageNum: 1,
      // pageSize: 8,
      headerBg: 'headerBg'
    };
  },
  created() {
    this.user = this.$store.getters.getUser;
    this.course = this.$store.getters.getCourse;
    console.log(this.course.cNo)
    // this.currentAssignment = this.$store.getters.getCurrentAssignment;
    // this.$store.commit("init_user");
    // this.fetchData();
    this.load();
  },
  methods:{
    ...mapMutations(['setPageNum', 'setPageSize']),
    ...mapActions(['updatePageInfo']),
    load(){
      apiV1.get('/admin/offerings',{params:{course_id:this.course.id,search:this.searchTeacher||'',page:this.pageNum,page_size:this.pageSize}}).then(res=>{
        this.tableData=res.data.records.map(item=>({...item,ssId:item.id,ssSectionCode:item.section_code,ssSectionName:item.section_name,tname:item.teacher_name,ssYear:item.year,ssTerm:item.term,ssStatus:item.status}))
        this.total=res.data.total
      })
    },
    handleDelete(ssId){
      console.log(ssId)
      apiV1.delete(`/admin/offerings/${ssId}`).then(()=>{
        this.$message.success('删除成功')
        this.load()
      }).catch(error=>this.$message.error(error.response?.data?.msg||'删除失败'))
    },
    handleSizeChange(pageSize){
      console.log(pageSize)//控制台输出相关数据
      this.pageSize=pageSize
      this.load()
    },
    handleCurrentChange(pageNum){
      console.log(pageNum)
      this.pageNum=pageNum
      this.load()
    }
  }
}
</script>
<style>
.title {
  display: block;
  font-size: 20px;
  color: black;
  font-weight: bold;
}

.line {
  flex: 1;
  /* 让横线占据剩余的空间 */
  border-top: 2px solid #d8d8d8;
  /* 设置横线样式 */
  margin-top: 15px;
  /* 调整横线与标题之间的间距 */
  height: 0.3px;
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
.router{
  text-decoration: none; /* 去掉下划线 */
  color: #0177FBFF; /* 保持默认文字颜色 */
  cursor: pointer; /* 添加手型光标 */
  font-size: 13px;
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
</style>

