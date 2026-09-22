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
                <span class="title">课程管理</span>
              </div>
              <el-row class="search-button-container" style="margin-top: 20px;">
                <div class="demo-input-suffix">
                  <el-input placeholder="请输入课程名或编号" v-model="searchCourse" clearable class="search-input">
                    <el-button slot="append" icon="el-icon-search" @click="load"></el-button>
                  </el-input>
                </div>
                <div style=" width: 100%; text-align: right;padding-right:20px">
                  <el-button type="primary" icon="el-icon-plus" @click="openCreateCourseDialog" class="create-course-btn">创建课程</el-button>
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
                <el-table-column prop="cno" label="课程编号"   align="center">
                </el-table-column>
                <el-table-column prop="cname" label="课程名称"  align="center">
                </el-table-column>
                <el-table-column label="开设情况" align="center" width="150">
                  <template slot-scope="scope">
                    <el-button @click="goToCheck(scope.row)" type="text" size="small">查看</el-button>
                  </template>
                </el-table-column>
                <el-table-column label="操作" align="center" width="150">
                  <template slot-scope="scope">
                    <el-popconfirm
                        confirm-button-text='确定'
                        cancel-button-text='我再想想'
                        icon="el-icon-info"
                        icon-color="red"
                        title="你确定删除吗？"
                        @confirm="handleDelete(scope.row.cno)"
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
            <el-dialog :visible.sync="dialogVisible" title="创建课程"  width="25%" >
              <!-- 表单内容 -->
              <el-form :model="courseForm" label-width="80px" ref="courseForm" :rules="rules">
                <el-form-item label="课程编号" prop="cNo">
                  <el-input v-model="courseForm.cno" :maxlength="10" style="flex: 1;"></el-input>
                </el-form-item>
                <el-form-item label="课程名称" prop="cName">
                  <el-input v-model="courseForm.cname" :maxlength="10" style="flex: 1;"></el-input>
                </el-form-item>
                <el-form-item>
                  <div style="float: right">
                    <el-button type="primary" @click="createCourse()">创建</el-button>
                    <el-button @click="closeCreateCourseDialog()">取消</el-button></div>
                </el-form-item>
              </el-form>
            </el-dialog>
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
      searchCourse:null,
      user:null,
      tableData: [],
      courseForm:{
        cno:null,
        cname:null
      },
      rules: {
        cno: [
          {required: true, message: '请输入课程编号', trigger: 'blur'}
        ],
        cname: [
          {required: true, message: '请输入课程名称', trigger: 'blur'}
        ]
      },
      total: 0,
      // pageNum: 1,
      // pageSize: 8,
      headerBg: 'headerBg'
    };
  },
  created() {
    this.user = this.$store.getters.getUser;
    // this.course = this.$store.getters.getCourse;
    // this.currentAssignment = this.$store.getters.getCurrentAssignment;
    // this.$store.commit("init_user");
    // this.fetchData();
    this.load();
  },
  methods:{
    ...mapMutations(['setPageNum', 'setPageSize']),
    ...mapActions(['updatePageInfo']),
    load(){
      apiV1.get('/admin/courses',{params:{search:this.searchCourse||'',page:this.pageNum,page_size:this.pageSize}}).then(res =>{
        this.tableData=res.data.records.map(item=>({...item,cno:item.number,cname:item.name}))
        this.total=res.data.total
      })
    },
    goToCheck(row){
      const course = {
        id: row.id,
        cNo : row.cno,
        cName : row.cname
      }
      console.log(row)
      this.$store.dispatch("setCourse",course)
      this.$router.push({
        name:'排课情况'
      })
    },
    createCourse(){
      this.$refs['courseForm'].validate((valid) => {
        if(valid) {
          console.log(this.courseForm)
          apiV1.post('/admin/courses', {number:this.courseForm.cno,name:this.courseForm.cname}).then(() => {
            this.$message.success('保存成功')
            this.load()
          }).catch(error=>this.$message.error(error.response?.data?.msg||'保存失败'))
          // 处理创建课程逻辑
          console.log('Creating course:', this.courseForm);
          // 关闭模态框
        }
      })
    },
    handleDelete(cNo){
      const row=this.tableData.find(item=>item.cno===cNo)
      if(!row)return
      apiV1.delete(`/admin/courses/${row.id}`).then(()=>{
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
    },
    openCreateCourseDialog() {
      this.dialogVisible = true;
    },
    closeCreateCourseDialog() {
      this.dialogVisible = false;
      this.courseForm.cno = null;
      this.courseForm.cname = null;
    },
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

