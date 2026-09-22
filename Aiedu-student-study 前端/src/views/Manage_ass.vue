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
            <el-container>
                <el-container>
                    <el-main>
                        <div>
                            <div class="title-container">
                                <span class="title">作业库</span>
                              <router-link type="primary"  class="router" to="/assignment">返回</router-link>
                            </div>
                            <el-row class="search-button-container" style="margin-top: 20px;">
                                <div class="demo-input-suffix">
                                    <el-input placeholder="请输入作业名称" v-model="assignmentSearch" clearable class="search-input">
                                        <el-button slot="append" icon="el-icon-search" @click="load"></el-button>
                                    </el-input>
                                </div>

                            </el-row>
                        </div>
                        <div class="table-container">
                            <el-table :data="tableData" border stripe :header-cell-class-name="headerBg"
                                      @selection-change="handleSelectionChange">
                                <el-table-column type="selection"  align="center">
                                </el-table-column>
                              <el-table-column label="序号" align="center" width="80">
                                <template slot-scope="scope">
                                  <span>{{ startIndex + scope.$index }}</span>
                                </template>
                              </el-table-column>
                                <el-table-column  prop="asId" label="作业编号"  align="center">
                                </el-table-column>
                                <el-table-column prop="asName" label="作业标题" align="center">
                                </el-table-column>
                                <el-table-column prop="asCreate" label="创建者" align="center">
                                </el-table-column>
                                <el-table-column prop="asStartTime" label="开始时间" align="center">
                                </el-table-column>
                              <el-table-column prop="asEndTime" label="截至时间"  align="center">
                              </el-table-column>
                                <el-table-column label="操作"  align="center">
                                    <template slot-scope="scope">                                       
                                        <el-button @click="goToAssign(scope.row)" type="text" :style="{ fontSize: '20px' }" icon="el-icon-position"></el-button>
                                        <el-button @click="handleEdit(scope.row)" type="text" :style="{ fontSize: '20px' }" icon="el-icon-edit-outline"></el-button>
                                        <el-popconfirm
                                            class="ml-5"
                                            confirm-button-text='确定'
                                            cancel-button-text='我再想想'
                                            icon="el-icon-info"
                                            icon-color="red"
                                            title="你确定删除吗？"
                                            @confirm="handleDelete(scope.row)"
                                        >
                                        <el-button slot="reference" type="text" :style="{ fontSize: '20px' }" icon="el-icon-delete"></el-button>
                                        </el-popconfirm>
                                    </template>
                                </el-table-column>
                            </el-table>
                          <el-dialog :visible.sync="dialogVisible" title="发布课程" width="25%">
                            <!-- 表单内容 -->
                            <el-form :model="submitForm" label-width="80px" ref="submitForm" :rules="rules">
                              <el-form-item label="开始时间">
                                <!-- 使用 el-date-picker 显示和选择开始时间 -->
                                <el-date-picker v-model="submitForm.startTime" type="datetime" placeholder="选择开始时间" format="yyyy-MM-dd HH:mm"></el-date-picker>
                              </el-form-item>
                              <el-form-item label="截止时间" prop="endTime" >
                                <!-- 使用 el-date-picker 显示和选择截止时间 -->
                                <el-date-picker v-model="submitForm.endTime" type="datetime" placeholder="选择截止时间" required format="yyyy-MM-dd HH:mm"></el-date-picker>
                              </el-form-item>
                              <el-form-item>
                                <div style="float: right">
                                  <el-button type="primary" @click="handleAssign">创建</el-button>
                                </div>
                              </el-form-item>
                            </el-form>
                          </el-dialog>
                        </div>
                        <div class="block" style="display: flex; justify-content: center;">
                            <el-pagination @size-change="handleSizeChange" @current-change="handleCurrentChange"
                                :current-page="pageNum" :page-sizes="[8, 12, 16, 20]" :page-size="pageSize"
                                layout="total, sizes, prev, pager, next,jumper" :total="total">
                            </el-pagination>
                        </div>
                    </el-main>
                </el-container>
            </el-container>
        </div>
    </div>
</template>


<script>
import assignment from "@/views/Assignment.vue";
import {mapActions, mapMutations, mapState} from "vuex";
import apiV1 from '@/utils/apiV1'

export default {
  computed: {
    startIndex() {
      return (this.pageNum - 1) * this.pageSize + 1;
    },
    assignment() {
      return assignment
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
          user:null,
          course:null,
            tableData: [],
            multipleSelection: [],
            total: 0,
            // pageNum: 1,
            // pageSize: 8,
            headerBg: 'headerBg',
           assignmentSearch:'',
          dialogVisible:false,
          submitForm:{
            startTime: new Date(), // 默认为当前时间
            endTime: null, // 初始截止时间为空
          },
          currentRow:null,
          rules: {
            endTime: [
              { type:'date', required: true, message: '请选择截止时间', trigger: 'blur' }
            ]
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

    methods: {
      ...mapMutations(['setPageNum', 'setPageSize']),
      ...mapActions(['updatePageInfo']),
      load(){
        apiV1.get('/teacher/assignments',{params:{offering_id:this.course.offeringId||this.course.id}}).then(res=>{
          const keyword=(this.assignmentSearch||'').trim().toLowerCase()
          const records=res.data.records.filter(item=>!keyword||item.title.toLowerCase().includes(keyword))
          this.total=records.length
          this.tableData=records.slice((this.pageNum-1)*this.pageSize,this.pageNum*this.pageSize).map(item=>({...item,asId:item.id,asName:item.title,asStartTime:item.start_at,asEndTime:item.end_at}))
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
      goToAssign(row){
        if(row.asStartTime && row.asEndTime){
          this.$message.error("作业已发布");
        }
        else{
          this.dialogVisible = true
          this.currentRow = row
        }
      },
      handleAssign() {
        // 先进行表单验证
        this.$refs['submitForm'].validate((valid) => {
          if (valid) {
            // 表单验证通过
            const startTime = new Date(this.submitForm.startTime);
            const endTime = new Date(this.submitForm.endTime);

            // 判断截止时间是否早于发布时间
            if (endTime && endTime <= startTime) {
              // 截止时间早于发布时间，给出提示信息
              this.$message.error("截止时间不能在发布时间之前");
            } else {
              // 截止时间符合要求，继续执行你的逻辑
              const formatstartTime = `${startTime.getFullYear()}-${(startTime.getMonth() + 1).toString().padStart(2, '0')}-${startTime.getDate().toString().padStart(2, '0')}` + ' ' + `${startTime.getHours().toString().padStart(2, '0')}:${startTime.getMinutes().toString().padStart(2, '0')}:${startTime.getSeconds().toString().padStart(2, '0')}`;

              const formatendTime = `${endTime.getFullYear()}-${(endTime.getMonth() + 1).toString().padStart(2, '0')}-${endTime.getDate().toString().padStart(2, '0')}` + ' ' + `${endTime.getHours().toString().padStart(2, '0')}:${endTime.getMinutes().toString().padStart(2, '0')}:${endTime.getSeconds().toString().padStart(2, '0')}`;

              apiV1.post(`/assignments/${this.currentRow.asId}/publish`,{start_at:formatstartTime,end_at:formatendTime,idempotency_key:`publish-${this.currentRow.asId}-${Date.now()}`}).then(() => {
                this.$message.success('发布成功')
                this.dialogVisible = false
                this.submitForm.endTime = null
                this.load()
              }).catch(error=>this.$message.error(error.response?.data?.msg||'发布失败'))
            }
          }
        });
      },
      handleEdit(row){
          const assignment = {
            a_id:row.asId,
            a_name: row.asName,
            a_start_time: row.asStartTime,
            a_end_time:row.asEndTime
          }
          this.$store.dispatch('setCurrentAssignment',assignment)
          this.$router.push({
            name:'创建作业'
          })
        },
        handleDelete(row){
          apiV1.delete(`/teacher/assignments/${row.asId}`).then(()=>{
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
    }
}



</script>
<style>
.title {
    display: block;
    font-size: 20px;
    color: black;
    font-weight: bold;
  margin-left: 70px;
}

.line {
    flex: 1;
    /* 让横线占据剩余的空间 */
    border-top: 2px solid #d8d8d8;
    /* 设置横线样式 */
    margin-top: 5px;
    /* 调整横线与标题之间的间距 */
    height: 1px;
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
