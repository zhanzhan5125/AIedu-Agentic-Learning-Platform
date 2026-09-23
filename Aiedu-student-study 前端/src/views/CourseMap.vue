<template>
  <div class="page-shell" v-loading="loading">
    <div class="page-heading"><h2>{{ courseMap ? courseMap.title : '课程知识路线' }}</h2></div>
    <el-empty v-if="!courseMap" description="暂无课程知识路线" />
    <el-card v-else class="route-card">
      <div class="map-layout">
        <div class="map-list">
          <div v-for="(chapter,index) in chapterNodes" :key="chapter.node_key" class="chapter-group">
            <div class="map-node chapter-node" :class="{active:selected&&selected.node_key===chapter.node_key}" @click="selectNode(chapter)">
              <span>{{ index + 1 }}</span><b>{{ chapter.name }}</b>
            </div>
            <div v-for="point in chapter.children" :key="point.node_key" class="knowledge-point" :class="{active:selected&&selected.node_key===point.node_key}" @click="selectNode(point)">
              <i></i><span>{{ point.name }}</span>
            </div>
          </div>
        </div>
        <div>
          <div ref="chart" class="map-chart"></div>
          <el-card v-if="selected" shadow="never" class="evidence-card">
            <div slot="header" class="node-heading"><b>{{ selected.name }}</b><el-tag size="mini">{{ selected.node_type==='chapter'?'章节':'知识点' }}</el-tag></div>
            <p>{{ selected.description || '暂无概要' }}</p>
            <div v-if="selected.node_type==='chapter'&&childrenOf(selected).length" class="point-summary">
              <b>本章知识点</b><el-tag v-for="point in childrenOf(selected)" :key="point.node_key" size="small" @click="selectNode(point)">{{ point.name }}</el-tag>
            </div>
            <el-collapse v-if="selected.evidence&&selected.evidence.length" class="source-collapse">
              <el-collapse-item :title="`查看资料依据（${selected.evidence.length}）`">
                <div v-for="item in selected.evidence" :key="item.chunk_id" class="evidence-item">
                  <el-tag size="mini" type="info">{{ sourceType(item.resource_type) }}</el-tag>
                  《{{ item.title }}》 {{ locator(item) }}
                  <small>{{ item.excerpt }}</small>
                </div>
              </el-collapse-item>
            </el-collapse>
          </el-card>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script>
import apiV1 from '@/utils/apiV1'
import * as echarts from 'echarts'

export default {
  data(){return{loading:false,courseMap:null,selected:null,chart:null}},
  computed:{
    course(){return this.$store.getters.getCourse||{}},
    offeringId(){return Number(this.course.id||this.course.offeringId||this.course.courseCode)||null},
    chapterNodes(){return this.hierarchicalNodes(this.courseMap)}
  },
  created(){this.load()},
  mounted(){window.addEventListener('resize',this.resizeChart)},
  beforeDestroy(){window.removeEventListener('resize',this.resizeChart);if(this.chart)this.chart.dispose()},
  methods:{
    async load(){
      if(!this.offeringId)return
      this.loading=true
      try{
        this.courseMap=(await apiV1.get(`/offerings/${this.offeringId}/course-map?status=published`)).data
        this.selected=this.courseMap&&this.courseMap.nodes[0]
        this.$nextTick(this.render)
      }catch(_){this.courseMap=null}
      finally{this.loading=false}
    },
    hierarchicalNodes(courseMap){
      if(!courseMap)return[]
      const edges=(courseMap.edges||[]).filter(edge=>edge.relation_type==='contains')
      const childrenByKey={}
      const childKeys=new Set()
      edges.forEach(edge=>{(childrenByKey[edge.source_key]||(childrenByKey[edge.source_key]=[])).push(edge.target_key);childKeys.add(edge.target_key)})
      const byKey=Object.fromEntries(courseMap.nodes.map(node=>[node.node_key,node]))
      return courseMap.nodes.filter(node=>!childKeys.has(node.node_key)).map(node=>({...node,children:(childrenByKey[node.node_key]||[]).map(key=>byKey[key]).filter(Boolean)}))
    },
    childrenOf(node){const chapter=this.chapterNodes.find(item=>item.node_key===node.node_key);return chapter?chapter.children:[]},
    selectNode(node){this.selected=node},
    locator(item){if(item.page_number)return `第 ${item.page_number} 页`;if(item.slide_number)return `第 ${item.slide_number} 张幻灯片`;return item.heading_path||''},
    sourceType(value){return({outline:'大纲',textbook:'教材',courseware:'课件'})[value]||'资料'},
    resizeChart(){if(this.chart)this.chart.resize()},
    render(){
      const container=this.$refs.chart
      if(!this.courseMap||!container||container.clientWidth===0)return
      if(!this.chart||this.chart.isDisposed())this.chart=echarts.init(container)
      this.chart.setOption({tooltip:{},series:[{type:'graph',layout:'force',roam:true,label:{show:true},force:{repulsion:220,edgeLength:100},data:this.courseMap.nodes.map(node=>({id:node.node_key,name:node.name,value:node.confidence,symbolSize:44})),links:this.courseMap.edges.map(edge=>({source:edge.source_key,target:edge.target_key,label:{show:true,formatter:edge.relation_type}}))}]},true)
      this.chart.resize()
      this.chart.off('click')
      this.chart.on('click',params=>{const node=this.courseMap.nodes.find(item=>item.node_key===params.data.id);if(node)this.selected=node})
    }
  }
}
</script>

<style scoped>
.page-shell{padding:32px 48px;min-height:80vh;background:#f6f8fb}.page-heading{margin-bottom:20px}h2{margin:0}.route-card{min-height:540px}.map-layout{display:grid;grid-template-columns:360px minmax(480px,1fr);gap:20px;align-items:start}.map-list{max-height:calc(100vh - 220px);min-height:420px;overflow-y:auto;padding-right:8px;scrollbar-gutter:stable}.chapter-group{margin-bottom:10px}.map-node{display:flex;align-items:center;gap:10px;padding:12px;border:1px solid #dfe5ec;border-radius:8px;margin-bottom:5px;cursor:pointer;background:#fff}.map-node.active,.knowledge-point.active{border-color:#409eff;background:#ecf5ff}.map-node>span{display:flex;width:24px;height:24px;border-radius:50%;background:#409eff;color:#fff;align-items:center;justify-content:center}.map-node b{flex:1}.knowledge-point{display:flex;align-items:center;gap:9px;margin:3px 0 3px 22px;padding:7px 10px;border:1px solid transparent;border-radius:6px;color:#56616d;cursor:pointer}.knowledge-point i{width:7px;height:7px;border-radius:50%;background:#8abcf0}.map-chart{height:420px;background:#fbfcfe;border-radius:8px}.evidence-card{margin-top:14px}.node-heading{display:flex;align-items:center;gap:8px}.evidence-card p{color:#66717d;line-height:1.7}.point-summary{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:14px 0}.point-summary .el-tag{cursor:pointer}.source-collapse{margin-top:16px}.evidence-item{padding:10px 0;border-top:1px solid #edf0f3}.evidence-item small{display:block;color:#7b8794;margin-top:5px;line-height:1.5}@media(max-width:1200px){.page-shell{padding:24px}.map-layout{grid-template-columns:1fr}.map-list{max-height:560px;min-height:0}}
</style>
