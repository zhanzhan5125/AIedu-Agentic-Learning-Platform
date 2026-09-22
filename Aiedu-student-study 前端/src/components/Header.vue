
<template>
  <div style="background-color: #E5F1FE">
    <header class="app-header">
      <!-- 左边的文字 -->
      <div class="left-text">
        CourseAIMate
        <p style="font-size: small;margin-top: 5px;margin-left: 5px">和山杏台</p>
      </div>
      <!-- 右边的图标 -->
      <div class="right-icons">
        <el-tooltip content="退出平台">
          <button style="border: none; background-color: transparent; padding: 0;" @click="logout"><el-icon name="d-arrow-left" class="icon"></el-icon></button>
        </el-tooltip>
        <el-tooltip content="回到首页">
          <router-link :to="this.homepath"><el-icon name="house" class="icon"></el-icon></router-link>
        </el-tooltip>
        <el-icon name="bell" class="icon"></el-icon>
        <el-icon name="message" class="icon"></el-icon>
        <el-dropdown @command='handleClick'>
          <div class="user-avatar">
            <!-- 用户头像放在这里，可以使用 img 标签或其他组件 -->
            <img src="../views/img/头像.png" alt="User Avatar">
          </div>
          <el-dropdown-menu slot="dropdown">
            <el-dropdown-item>修改密码</el-dropdown-item>
          </el-dropdown-menu>
        </el-dropdown>
      </div>
    </header>
    <el-dialog :visible.sync="dialogVisible" title="修改密码" width="25%">
      <el-form :model="passForm" :rules="rules" ref="passForm" style="text-align: center; margin-right: 0">
        <el-form-item label="旧密码" prop="oldPass" style="margin-bottom: 15px;">
          <el-input v-model="passForm.oldPass" :maxlength="20" style="width: 60%;" show-password></el-input>
        </el-form-item>
        <el-form-item label="新密码" prop="newPass" style="margin-bottom: 15px;">
          <el-input v-model="passForm.newPass" :maxlength="20" style="width: 60%;" show-password></el-input>
        </el-form-item>
        <el-form-item label="确认密码" prop="confirmPass">
          <el-input v-model="passForm.confirmPass" :maxlength="20" style="width: 60%;" show-password></el-input>
        </el-form-item>
        <el-form-item>
          <el-button type="success" @click="changePass" style="width: 50%;">确认修改</el-button>
        </el-form-item>
      </el-form>
    </el-dialog>

  </div>

</template>

<script>
import apiV1 from '@/utils/apiV1'
export default {
  name: "Header",
  props: {
    collapseBtnClass: String,
    collapse: Function
  },
  data() {
    return {
      homepath: '',
      paths: [],
      form: {},
      id: "",
      avatarUrl: '',
      user: null,
      dialogVisible:false,
      passForm: {
        oldPass: '',
        newPass: '',
        confirmPass: ''
      },
      rules: {
        oldPass: [{ required: true, message: '请输入旧密码', trigger: 'blur' }],
        newPass: [
          { required: true, message: '请输入新密码', trigger: 'blur' },
          {
            validator: (rule, value, callback) => {
              if (!/^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$/.test(value)) {
                callback(new Error('密码需要包含大小写英文字母和数字，且长度不少于8个字符'));
              } else {
                callback();
              }
            },
            trigger: 'blur'
          }
        ],
        confirmPass: [
          { required: true, message: '请再次输入新密码', trigger: 'blur' },
          {
            validator: (rule, value, callback) => {
              if (value !== this.passForm.newPass) {
                callback(new Error('两次输入的密码不一致'));
              } else {
                callback();
              }
            },
            trigger: 'blur'
          }
        ]
      }

    }
  },
  created() {
    this.user = this.$store.getters.getUser;
    this.avatarUrl = this.user.image;
    this.load()
  },
  methods: {
    load() {
      if (this.user.role === 'teacher') {
        this.homepath = '/home'
      } else if (this.user.role === 'student') {
        this.homepath = '/student_home'
      } else {
        this.homepath = '/admin_home'
      }
    },
    clearStore() {
      this.$store.commit('clearUser')
      this.$store.commit('clearCourse')
      this.$store.commit('clearCurrentAssignment')
      this.$store.commit('clearStudent')
    },
    handleClick(){
      this.dialogVisible = true
    },
    changePass(){
      this.$refs['passForm'].validate((valid) => {
        if (valid) {
          apiV1.put('/auth/password', {
            old_password: this.passForm.oldPass,
            new_password: this.passForm.newPass
          }).then(() => {
            this.$message.success('修改成功，请重新登录')
            this.dialogVisible = false
            this.clearStore()
            this.$router.push('/login')
          }).catch(error => this.$message.error(error.response?.data?.msg || '修改失败'))
        }
      })
    },
    logout() {
      apiV1.post('/auth/logout').catch(() => {}).finally(() => {
        this.$message.success('退出成功')
        this.clearStore()
        this.$router.push('/login')
      })
    }
    //   changeUsername(name) {//动态修改昵称
    //     this.$set(this.user, 'name',name);
    //      },
    // },
    //  mounted() {
    //  MiddleUtil.$on("click",(name)=>{
    //    this.changeUsername(name);
    //  });
    // },
    //   watch: {
    //   currentPathName(newVal, oldVal) {
    //     console.log(newVal)
    //   }
  }


}
</script>

<style scoped>
.app-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  background-color: #E5F1FE;
  color: black;
  height: 50px;
}

.user-avatar {
  width: 35px; /* 调整用户头像大小 */
  height: 35px;
  overflow: hidden;
  border-radius: 50%; /* 圆形头像 */
  margin-left: 15px; /* 为头像添加右边距 */
}

.user-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.left-text {
  font-size: 18px;
  font-weight: bold;
  margin-right: 20px;
  color: #626c91;
  display: flex;
  flex-direction: row;/* 可根据需要调整右边距 */
}

.right-icons {
  display: flex;
  align-items: center;
}

.icon {
  font-size: 24px;
  margin-left: 15px; /* 可根据需要调整左边距 */
  cursor: pointer;
  color: #A5B4CB; /* 图标颜色，根据需要调整颜色 */
}

.avatar {
  margin-left: 15px; /* 可根据需要调整左边距 */
}
</style>
