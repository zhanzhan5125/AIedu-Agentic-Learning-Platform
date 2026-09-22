<template>
  <div class="page-shell" v-loading="loading">
    <div class="page-heading"><h2>课程知识路线</h2><p>由教师审核发布的学习顺序与资料依据。</p></div>
    <el-empty v-if="!courseMap" description="教师尚未发布课程知识路线" />
    <div v-else class="map-layout">
      <el-card><div slot="header">{{ courseMap.title }}</div><p>{{ courseMap.summary }}</p>
        <div v-for="(node,index) in courseMap.nodes" :key="node.node_key" class="node" :class="{active:selected&&selected.id===node.id}" @click="selectNode(node)"><span>{{ index+1 }}</span><b>{{ node.name }}</b></div>
      </el-card>
      <div><el-card><div ref="chart" class="chart"></div></el-card>
        <el-card v-if="selected" class="evidence"><div slot="header">{{ selected.name }} · 资料依据</div><p>{{ selected.description }}</p><div v-for="item in selected.evidence" :key="item.chunk_id" class="source"><b>《{{ item.title }}》{{ locator(item) }}</b><p>{{ item.excerpt }}</p></div></el-card>
      </div>
    </div>
  </div>
</template>
<script>
import apiV1 from '@/utils/apiV1'
import * as echarts from 'echarts'
export default{
  data(){return{loading:false,courseMap:null,selected:null,chart:null}},
  computed:{course(){return this.$store.getters.getCourse||{}},offeringId(){return Number(this.course.id||this.course.offeringId||this.course.courseCode)||null}},
  created(){this.load()},beforeDestroy(){if(this.chart)this.chart.dispose()},
  methods:{async load(){if(!this.offeringId)return;this.loading=true;try{this.courseMap=(await apiV1.get(`/offerings/${this.offeringId}/course-map`)).data;this.selected=this.courseMap&&this.courseMap.nodes[0];this.$nextTick(this.render)}catch(_){this.courseMap=null}finally{this.loading=false}},selectNode(node){this.selected=node},locator(item){if(item.page_number)return ` · 第 ${item.page_number} 页`;if(item.slide_number)return ` · 第 ${item.slide_number} 张幻灯片`;return item.heading_path?` · ${item.heading_path}`:''},render(){if(!this.courseMap||!this.$refs.chart)return;this.chart=echarts.init(this.$refs.chart);this.chart.setOption({series:[{type:'graph',layout:'force',roam:true,label:{show:true},force:{repulsion:240,edgeLength:110},data:this.courseMap.nodes.map(n=>({id:n.node_key,name:n.name,symbolSize:46})),links:this.courseMap.edges.map(e=>({source:e.source_key,target:e.target_key,label:{show:true,formatter:e.relation_type}}))}]});this.chart.on('click',p=>{const n=this.courseMap.nodes.find(i=>i.node_key===p.data.id);if(n)this.selected=n})}}
}
</script>
<style scoped>.page-shell{padding:32px 48px;min-height:80vh;background:#f6f8fb}.page-heading{margin-bottom:22px}h2{margin:0 0 8px}.page-heading p{color:#7b8794}.map-layout{display:grid;grid-template-columns:340px 1fr;gap:20px}.node{display:flex;gap:10px;align-items:center;padding:12px;border-radius:8px;cursor:pointer}.node.active{background:#ecf5ff;color:#2379d8}.node span{display:flex;width:24px;height:24px;align-items:center;justify-content:center;border-radius:50%;background:#2379d8;color:white}.chart{height:440px}.evidence{margin-top:18px}.source{padding:12px 0;border-top:1px solid #edf0f3}.source p{color:#66717d;line-height:1.6}</style>
