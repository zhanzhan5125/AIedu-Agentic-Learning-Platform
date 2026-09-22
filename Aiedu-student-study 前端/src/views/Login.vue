<template>
  <div class="login-container">
    <div class="login-box" style="padding: 10px; padding-top: 50px;align-content: center">
      <img src="./img/logo.png"  style="width: 100%; max-width: 350px; margin-bottom: 20px;">
      <el-form :model="user" :rules="rules" ref="userForm" >
        <el-form-item prop="id">
          <el-input
              size="large"
              style="margin-top: 30px; height: 40px;"
              prefix-icon="el-icon-user"
              v-model="user.id"
              placeholder="请输入登录ID"
              required
          ></el-input>
        </el-form-item>
        <el-form-item prop="upassword" >
          <el-input
              size="large"
              style="margin: 10px 0"
              prefix-icon="el-icon-lock"
              show-password
              v-model="user.upassword"
              placeholder="请输入密码"
              required
          ></el-input>
        </el-form-item>
        <el-form-item prop="role" :rules="this.rules.roleRules" >
          <el-radio-group v-model="user.role" @change="handleRadioChange" required
          style="margin-top: 20px"
          >
            <el-radio label="teacher">教师</el-radio>
            <el-radio label="student">学生</el-radio>
            <el-radio label="admin">管理员</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item style="margin: 10px 0; text-align: right">
          <!-- 其他部分保持不变 -->
          <Vcode :show="isShow" @success="success" @close="close"/>
          <div style="text-align: center;padding-top:30px" >
            <el-button type="primary" size="large" autocomplete="off" @click="submit() " style="margin-right: 10px;">登录</el-button>
          </div>
        </el-form-item>
      </el-form>
    </div>
    <div class="bottom-info">
      <a href="https://beian.miit.gov.cn/#/Integrated/index" target="_blank">浙ICP备20024110号-2</a>
    </div>
  </div>
</template>

<script>
import Vcode from "vue-puzzle-vcode";
import apiV1 from '@/utils/apiV1'
export default {
  components: {
    Vcode
  },
  data() {
    return {
      isShow:false,
      radio: "",
      identity:'',
      selectedOption: 'option1', // 初始化选中项为'option1'
      options: [
        {name: '选项1', value: 'option1'},
        {name: '选项2', value: 'option2'},
        {name: '选项3', value: 'option3'}
      ],
      user: {
        id: '',
        upassword: '',
        role: ''
      },
      rules: {
        id: [
          {required: true, message: '请输入登录名', trigger: 'blur'}
        ],
        upassword: [
          {required: true, message: '请输入密码', trigger: 'blur'}
        ],
        roleRules: [
          { required: true, message: '请选择角色', trigger: 'change' },
        ],
      }
    }
  },
  methods: {
    submit() {
      this.isShow = true;
    },
    handleRadioChange(value) {
      this.identity = value
      console.log('选中的值:', value);
    },
    success() {
      this.isShow = false; // 通过验证后，需要手动隐藏模态框
      this.login()
    },
    // 用户点击遮罩层，应该关闭模态框
    close() {
      this.isShow = false;
    },
    clearPreviousSessionContext() {
      this.$store.commit('clearCourse')
      this.$store.commit('clearCurrentAssignment')
      this.$store.commit('clearStudent')
    },
    completeLogin(user, target) {
      this.clearPreviousSessionContext()
      this.$store.dispatch('setUser', user)
      this.$router.push(target)
      this.$message.success('登录成功')
    },
    login() {
      this.$refs['userForm'].validate((valid) => {
        if (!valid) return
        const role = this.user.role === 'admin' ? 'manager' : this.user.role
        apiV1.post('/auth/login', {
          role,
          account: this.user.id,
          password: this.user.upassword
        }).then(res => {
          const target = role === 'teacher' ? '/home' : role === 'student' ? '/student_home' : '/admin_home'
          this.completeLogin({ ...res.data, _backend: 'fastapi' }, target)
        }).catch(error => this.$message.error(
          (error.response && error.response.data && error.response.data.msg) || '登录失败'
        ))
      });
    },
  }
};
</script>

<style scoped>
.login-container {
  background-image: url('img/loginback.png'); /* 背景图片路径 */
  background-size: cover;
  background-position: center;
  display: flex;
  flex-direction: column;
  align-content: center;
  align-items: center;
  height: 100vh;
  position: relative;
}

.background-image {
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: -1; /* 将背景置于所有其他内容下方 */
}

.login-box {
  height: 500px;
  width: 380px;
  border-radius: 10px;
  background-color: #ffffff;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  position: absolute;
  left: 73%; /* 将login-box左边缘定位到容器的中心 */
  top: 50%; /* 将login-box上边缘定位到容器的中心 */
  transform: translate(-50%, -50%); /* 使用transform属性将login-box居中 */
  display: flex;
  flex-direction:column;
  align-items: center;
}

.title {
  font-size: 80px;
  font-weight: bold;
  line-height: normal;
  letter-spacing: 0em;
  margin-left: 100px;
  margin-top: 20%;
  color: #e6ebee;
  text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.5);
}

.title2 {
  font-size: 50px;
  font-weight: bold;
  line-height: normal;
  letter-spacing: 0em;
  margin-left: 475px;
  color: #a7ccf5;
  text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.5);
}

.bottom-info {
  position: absolute;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  text-align: center;
  color: #999;
  font-size: 12px;
}

.bottom-info a {
  color: #999;
  text-decoration: none;
}
</style>
