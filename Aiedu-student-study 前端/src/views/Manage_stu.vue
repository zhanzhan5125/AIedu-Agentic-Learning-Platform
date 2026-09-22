<template>
  <div class="layout-container">
    <!-- Header 部分 -->
    <!-- Header 部分 -->
    <div class="wrapper" style="width: 100%; height: auto; display: flex;padding-top:0;border-bottom: 1px solid #ccc;">
      <p style="font-size: larger; color: #2196f3;  padding-bottom: 17px;padding-top:17px;padding-left:70px">
        {{ course.title || course.tittle }}</p>
      <el-menu :default-active="$route.path" router background-color="white" text-color="black"
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
                <span class="title">学生名单</span>
              </div>
              <el-row class="search-button-container" style="margin-top: 20px;">
                <div class="demo-input-suffix">
                  <el-input placeholder="请输入姓名或学号" v-model="studentSearch" clearable class="search-input">
                    <el-button slot="append" icon="el-icon-search" @click="load"></el-button>
                  </el-input>
                </div>
                <div style=" width: 100%; text-align: right;padding-right:20px">
                  <el-popconfirm class="ml-5" confirm-button-text='确定' cancel-button-text='我再想想' icon="el-icon-info"
                    icon-color="red" title="你确定删除吗？" @confirm="delBatch">
                    <el-button type="danger" round slot="reference" style="margin-right: 20px"> 批量删除</el-button>
                  </el-popconfirm>
                  <el-button type="primary" round @click="handleClick('添加学生')" style="margin-right: 10px">添加学生</el-button>
                  <!--                                    <dialog-component v-if="Visiable" ref="dialog"></dialog-component>-->
                  <el-button type="primary" round style="margin-right: 20px" @click="exp">导出名单</el-button>
                </div>
              </el-row>
            </div>

            <div class="table-container">
              <el-table :data="tableData" border stripe :header-cell-class-name="headerBg"
                @selection-change="handleSelectionChange">
                <el-table-column type="selection">
                </el-table-column>
                <el-table-column label="序号" align="center" width="80">
                  <template slot-scope="scope">
                    <span>{{ startIndex + scope.$index }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="sname" label="姓名" align="center">
                </el-table-column>
                <el-table-column prop="sid" label="学号" align="center">
                </el-table-column>

                <el-table-column label="操作" align="center">
                  <template slot-scope="scope">
                    <el-popconfirm
                        class="ml-5"
                        confirm-button-text='确定'
                        cancel-button-text='我再想想'
                        icon="el-icon-info"
                        icon-color="red"
                        title="你确定删除吗？"
                        @confirm="handleDelete(scope.row)"
                    >
                    <el-button type="text" size="small" slot="reference">移除</el-button>
                    </el-popconfirm>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <div class="block" style="display: flex; justify-content: center;">
              <el-pagination @size-change="handleSizeChange" @current-change="handleCurrentChange" :current-page="pageNum"
                :page-sizes="[8, 12, 16, 20]" :page-size="pageSize" layout="total, sizes, prev, pager, next,jumper"
                :total="total">
              </el-pagination>
            </div>
            <el-dialog title="添加学生" :visible.sync="detailVisible" width="30%" center>
              <div class="el-dialog-div">
                <div class="btn_switch">
                  <button class="btn_anniu" @click="change(0)" :class="{ newStyle: 0 === number }">手动添加</button>
                  <button class="btn_anniu" @click="change(1)" :class="{ newStyle: 1 === number }">批量导入</button>
                </div>
                <div class="switch_content">
                  <div v-show="1 === number"
                    style="display: flex; flex-direction: column; justify-content: center; align-items: center;">
                    <p style="margin-top:15px;">请下载最新模板，按照模板格式填写学生信息</p>
                    <el-button plain @click="downloadExcel()"
                      style="margin-top:35px;margin-bottom: 15px; width: 20%;">下载模板</el-button>
                    <el-alert title="批量导入正在按 FastAPI 文件格式重做，请暂时使用手动添加" type="info" :closable="false" />

                  </div>
                  <div v-show="0 === number">
                    <p style="margin-top:15px; text-align: center;margin-bottom: 20px">输入学生姓名、学号即可添加学生</p>
                    <el-form :model="studentForm" :rules="rules" ref="studentForm"
                      style=" text-align: center;margin-right: 0">
                      <el-form-item label="学生姓名" prop="studentName">
                        <el-input v-model="studentForm.studentName" :maxlength="10" style="flex: 1;width: 60%"></el-input>
                      </el-form-item>
                      <el-form-item label="学生学号" prop="studentNumber">
                        <el-input v-model="studentForm.studentNumber" :maxlength="15"
                          style="flex: 1;width: 60%"></el-input>
                      </el-form-item>
                      <el-form-item>
                        <el-button type="success" @click="addStudent" style="width: 50%;">添加</el-button>
                      </el-form-item>
                    </el-form>
                  </div>
                </div>
              </div>
            </el-dialog>
          </el-main>
        </el-container>
      </el-container>
    </div>
  </div>
</template>


<script>
import dialogComponent from "../components/addStudentDialog.vue";
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
      currentCourse: null,
      tableData: [],
      multipleSelection: [],
      number: 0,
      total: 0,
      // pageNum: 1,
      // pageSize: 8,
      headerBg: 'headerBg',
      Visiable: false,
      studentSearch: null,
      detailVisible: false,
      fileUrl: '../views/fileTemplate/importUserTemplate.xls',
      studentForm: {
        studentName: '',
        studentNumber: ''
      },
      rules: {
        studentName: [{ required: true, message: '请输入学生姓名', trigger: 'blur' }],
        studentNumber: [{ required: true, message: '请输入学生学号', trigger: 'blur' }]
      }
    };
  },
  created() {
    this.user = this.$store.getters.getUser;
    this.course = this.$store.getters.getCourse;
    // this.$store.commit("init_user");
    // this.fetchData();
    this.load();
  },

  components: {
    dialogComponent
  },
  methods: {
    ...mapMutations(['setPageNum', 'setPageSize']),
    ...mapActions(['updatePageInfo']),
    load() {
      apiV1.get(`/teacher/offerings/${this.course.offeringId||this.course.id}/enrollments`).then(res => {
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
    handleSelectionChange(val) {
      this.multipleSelection = val;
    },
    handleDelete(row) {
      apiV1.delete(`/teacher/offerings/${this.course.offeringId||this.course.id}/enrollments/${row.id}`).then(() => {
        this.$message.success('删除成功')
        this.load()
      }).catch(error=>this.$message.error(error.response?.data?.msg||'删除失败'))
    },
    delBatch() {
      const ids=this.multipleSelection.map(v=>v.id)
      apiV1.post(`/teacher/offerings/${this.course.offeringId||this.course.id}/enrollments/batch-remove`,ids).then(() => {
        this.$message.success('批量删除成功')
        this.load()
      }).catch(error=>this.$message.error(error.response?.data?.msg||'批量删除失败'))
    },
    handleClick(data) {
      this.detailVisible = true;
      this.$nextTick(() => {
        //这里的dialog与上面dialog-component组件里面的ref属性值是一致的
        //init调用的是dialog-component组件里面的init方法
        //data是传递给弹窗页面的值
        // this.$refs.dialog.init(data);
      })
    },
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
    exp() {
      // 构建包含用户ID（tID）和课程代码（courseCode）的对象
      const expData = {
        tID: this.user.id,
        courseCode: this.course.courseCode
      };
      // 在这里您可以使用expData对象来执行其他操作，比如将其发送到后端处理
      // 在新窗口中打开下载链接，注意您可以将expData作为查询参数传递到下载链接中
      this.$message.info('学生名单导出将在 FastAPI 导出接口中提供')
    },
    change: function (index) {
      this.number = index; //重要处
    },
    addImportExcel(res) {
      console.log(res.msg);
      this.detailVisible = false;
      if (res.code === 0) {
        this.$message.error(res.msg);
      } else {
        this.$message.success("导入成功");
        this.load();
      }
    },
    
    downloadExcel: function () {
      this.detailVisible = false;
      this.$message.info('请暂时使用手动添加学生')
    },
    addStudent: function () {
      this.$refs['studentForm'].validate((valid) => {
        if (valid) {
          this.detailVisible = false;
          apiV1.post(`/teacher/offerings/${this.course.offeringId||this.course.id}/enrollments`,{student_account:this.studentForm.studentNumber}).then(() => {
            this.$message.success('添加成功')
            this.detailVisible = false
            this.load()
            this.studentForm.studentNumber = ''
            this.studentForm.studentName = ''
          }).catch(error=>this.$message.error(error.response?.data?.msg||'添加失败'))
        }
      })
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
  padding-left: 50px;
}

.search-button-container {
  display: flex;
  margin-bottom: 20px;
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

.el-dialog-div {
  display: flex;
  flex-direction: column;
  height: 20vh;
  align-items: center;
  margin-bottom: 10vh;
}

.btn_anniu {
  width: 50%;
  padding: 11px 0;
  font-size: 15px;
  font-weight: bold;
  border: 0 solid #fff;
  color: #000;
  outline: none;
  background: #fff;
}

.newStyle {
  border-bottom: 2px solid #0885ea;
  color: #0885ea;
  font-size: 15px;
  font-weight: bold;
}

.btn_switch {
  display: flex;
  justify-content: space-around;
  align-items: center;
  width: 100%;
  height: 20%;
  margin-bottom: 10px;
  /* Add margin-bottom to create space between btn_switch and switch_content */
}

.switch_content {
  width: 100%;
  height: 70%;
  margin-bottom: 15px;
}
</style>

