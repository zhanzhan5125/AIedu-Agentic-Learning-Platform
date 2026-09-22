const { defineConfig } = require('@vue/cli-service')
module.exports = defineConfig({
  assetsDir:'static',
  transpileDependencies: true,
  devServer: {
    port: 8080,
    proxy: {
      '/api/v1': {
        target: process.env.AIEDU_FASTAPI_TARGET || 'http://127.0.0.1:9091',
        changeOrigin: true,
        ws: true
      }
    }
  }
})
