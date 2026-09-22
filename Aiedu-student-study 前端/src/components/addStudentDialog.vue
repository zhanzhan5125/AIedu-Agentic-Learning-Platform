<template>
<!--1.首先，弹窗页面中要有el-dialog组件即弹窗组件，我们把弹窗中的内容放在el-dialog组件中-->
<!--2.设置:visible.sync属性，动态绑定一个布尔值，通过这个属性来控制弹窗是否弹出-->
<el-dialog title="添加学生" :visible.sync="detailVisible" width="35%" center>
    <div class="el-dialog-div">
        <div class="btn_switch">
            <button class="btn_anniu" @click="change(0)" :class="{ newStyle:0===number}">手动添加</button>
            <button class="btn_anniu" @click="change(1)" :class="{ newStyle:1===number}">批量导入</button>
        </div>
        <div class="switch_content">
            <div v-show="1===number" style="display: flex; flex-direction: column; justify-content: center; align-items: center;">
                <p style="margin-top:15px;">请下载最新模板，按照模板格式填写学生信息</p>
                <el-button plain @click="downloadExcel()" style="margin-top:15px;margin-bottom: 15px; width: 50%;">下载最新模板</el-button>
              <el-alert title="批量导入正在按 FastAPI 文件格式重做，请暂时使用手动添加" type="info" :closable="false" />
            </div>
            <div v-show="0===number" style="display: flex; flex-direction: column; justify-content: center; align-items: center">
                <p style="margin-top:15px;">输入学生姓名、学号即可添加学生</p>
                <div style="margin-top:15px;display: flex; align-items: center;">
                    <el-label style="margin-right: 10px;">学生姓名：</el-label>
                    <el-input v-model="studentName" :maxlength="10" style="flex: 1;"></el-input>
                </div>
                <div style="margin-top:15px;margin-bottom:15px;display: flex; align-items: center;">
                    <el-label style="margin-right: 10px;">学生学号：</el-label>
                    <el-input v-model="studentNumber" :maxlength="15" style="flex: 1;"></el-input>
                </div>
                <el-button type="success" @click="addStudent(studentName,studentNumber)" style="width: 50%;">添加</el-button>
            </div>
        </div>
    </div>
  </el-dialog>
</template>

<script>
import apiV1 from '@/utils/apiV1'
    export default {
        name: "addStudentDialog",
        data(){
          return{
            user:null,
            course:null,
            detailVisible:false,
            number:0,
            fileUrl: '../views/fileTemplate/importUserTemplate.xls',
            studentName:'',
            studentNumber:''
          }
        },
      created() {
          this.user = this.$store.getters.getUser;
          this.course = this.$store.getters.getCourse;
      },
      methods:{
      //3.定义一个init函数，通过设置detailVisible值为true来让弹窗弹出，这个函数会在父组件的方法中被调用
        init(data){
          this.detailVisible=true;
          //data是父组件弹窗传递过来的值，我们可以打印看看
          console.log(data);
        },
        change: function (index) {
            this.number = index; //重要处
        },
        addImportExcel: function () {
            this.detailVisible=false;
          this.$message.success("导入成功")
          this.load()
        },
        downloadExcel: function () {
            this.detailVisible=false;
            this.$message.info('请暂时使用手动添加学生')
        },
        addStudent: function (studentName,studentNumber) {
            this.detailVisible=false;
          apiV1.post(`/teacher/offerings/${this.course.offeringId||this.course.id}/enrollments`,{student_account:studentNumber}).then(()=>{
            this.$message.success('添加成功')
            this.detailVisible=true
          }).catch(error=>this.$message.error(error.response?.data?.msg||'添加失败'))
        }
      }
    }
</script>

<style>
    .el-dialog-div{
      display: flex;
      flex-direction: column;
        height:20vh;
        align-items: center;
        margin-bottom:10vh;
    }
    .btn_anniu{
    width: 50%;
    padding: 11px 0;
    font-size: 15px;
    font-weight: bold;
    border: 0 solid #fff;
    color: #000;
    outline: none;
    background: #fff;
    }
    .newStyle{
        border-bottom: 2px solid #0885ea;
        color: #0885ea;
        font-size:15px;
        font-weight: bold;
    }
    .btn_switch {
        display: flex;
        justify-content: space-around;
        align-items: center;
        width: 100%;
        height: 20%;
        margin-bottom: 10px; /* Add margin-bottom to create space between btn_switch and switch_content */
    }

    .switch_content {
        width: 100%;
        height: 70%;
        margin-bottom:15px;
    }
</style>
