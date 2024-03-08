# Awesome-AGI

[![Anurag's GitHub stats](https://github-readme-stats.vercel.app/api?username=ArronAI007)](https://github.com/anuraghazra/github-readme-stats)

## 技术交流

欢迎加入AIGC技术交流群，与AI领域专家和各行各业的AIGC爱好者一起交流技术理论与行业信息！不管你是学术界还是工业界实践者或爱好者，都欢迎加入！

| 交流群二维码                    | 拉你入群(备注AIGC-github) |
| ------------------------------- | :------------------------: |
| ![Arron](https://i.postimg.cc/q78pyj8t/Wechat-IMG259.jpg) | ![Arron](https://i.postimg.cc/QMqj1DGc/Arron.jpg) |

## Table of Context
- [LLM 体验效果](#LLM-体验效果)
- [Model List](#Model-List)
- [LLM Pipeline](#LLM-Pipeline)
  - [LLM 预训练](#LLM-预训练)
  - [LLM 微调](#LLM-微调)
  - [LLM 部署](#LLM-部署)
  - [LLM 分布式并行框架](#LLM-分布式并行框架)
- [LLM 应用](#LLM-应用)
  - [RAG](#RAG)
    - [向量数据库](#向量数据库)
    - [RAG开源项目](#RAG开源项目)
  - [Agent](#Agent)
  - [LLM 应用框架](#LLM-应用框架)
    - [LangChain](#LangChain)
    - [LlamaIndex](#LlamaIndex)
    - [TaskingAI](#TaskingAI)
- [LLM Concepts](#LLM-Concepts)
  - [Prompt Engineering](#Prompt-Engineering)
  - [RLHF](#RLHF)
  - [LLM 扩词表](#LLM-扩词表)
  - [LLM 长文本](#LLM-长文本)
  - [LLM 幻觉](#LLM-幻觉)
  - [LLM 可控性与安全](#LLM-可控性与安全)
  - [LLM 文本检测](#LLM-文本检测)

## LLM 体验效果

| Model_A| Model_B | Blog |
| --- | --- | --- |                                                                                                                     
| 360智脑 | 讯飞星火 | [对比效果](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247486609&idx=2&sn=7fedb8ab37588d43968fdec2d7e5fcdd&chksm=ced54f75f9a2c663b9a2671f2548e2940730735605356cc0ffe72bc737470136a40032c80bfe&token=1282379489&lang=zh_CN#rd)|
| 阿里通义千问 | 讯飞星火 | [对比效果](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247486534&idx=1&sn=6f36d41b618790cba62e63eb25bb033b&chksm=ced54fa2f9a2c6b4a901528f87a7e74628dfd79d835f4cdea1ee4dea442f339adfd2736b2305&token=1282379489&lang=zh_CN#rd)|
| Bard | Bing_VS_ChatGPT | [对比效果](https://www.theverge.com/2023/3/24/23653377/ai-chatbots-comparison-bard-bing-chatgpt-gpt-4)|
| baichuan-53B | ChatGLM-6B | [对比效果](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247487325&idx=1&sn=561cb8b09c37ccfe0ed1f73de04b1db6&chksm=ced54cb9f9a2c5af30ac3d134086c955ac240f452cad0ab2b3708bc3cc09ef5b662b831c7d62&token=293446899&lang=zh_CN#rd)|
| 文心一言 | Bard | [对比效果](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247486260&idx=1&sn=a41224fee7ed4cb4a48eb40a420d7479&chksm=ced548d0f9a2c1c6f4930f30447468f9f01bb2af6031368e302b13a6354fc4bca6636e3b297e&token=666852558&lang=zh_CN#rd)|
| 文心一言 | Baize-7B | [对比效果](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247486317&idx=1&sn=ea3cc745d2991b8c657325392ce68f71&chksm=ced54889f9a2c19f3c2f85d8d7af7fff366027f79d1f4a5b2c650fea1b5dee9efde0b7c992ca&token=1173964254&lang=zh_CN#rd)|
| 文心一言 | OpenAssistant | [对比效果](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247486413&idx=2&sn=3816e5a4bccceee5e2af868166b18897&chksm=ced54829f9a2c13fb787b7a7e3c2aa0799eb7ff6d124f6847349346146900e05684ceb8cc7f7&token=1282379489&lang=zh_CN#rd)|
| 文心一言 | ChatGLM-6B | [对比效果](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247486081&idx=2&sn=fd87305419158d66dd4b05b57bee1324&chksm=ced54965f9a2c073ba1badfedbc6610036455cd769a3c8ee3445f7fbff9364b5624091be9914&token=666852558&lang=zh_CN#rd)|
| 文心一言 | GPT-4 | [对比效果](https://mp.weixin.qq.com/s/l1pTPlohMmiYEMc4x6QKhw)|
| 文心一言 | GPT-4实测 | [对比效果](https://mp.weixin.qq.com/s/uO8N3RpcrYU8rV1RkwBxzQ)|
| 文心一言 | 讯飞星火 | [对比效果](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247486490&idx=1&sn=c8d756f7f26a4e35f8b67ae485efabce&chksm=ced54ffef9a2c6e8d66f8b744d6af524e320d5aec384d142621cee53fd2150f2c7db1fa7596a&token=1282379489&lang=zh_CN#rd)|
| GPT4 | ChatGPT | [对比效果](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485952&idx=2&sn=e54a62e358bf7aee3c007d59600fd452&chksm=ced549e4f9a2c0f2868eb8877c14fbe287a469e63b09774cefcb9edc4c0601016f6d36561973&token=666852558&lang=zh_CN#rd)|
| GPT4 | Claude2 | [对比效果1](https://mp.weixin.qq.com/s/dj2_WlWVpGwYsa8kO-GRFQ)，[对比效果2](https://mp.weixin.qq.com/s/Xo3XXQ5zYPmDxBYivhBYqA)|

---

## Model List

这里整理了主流大模型baichuan、ChatGLM和LLaMA及其扩展模型的一些细节，并且会对目前主流的LLM按照功能和应用领域进行分类整理，更多请参考【[Model List](https://github.com/ArronAI007/Awesome-AGI/blob/main/Model%20List/README.md)】。

dair-ai同样也整理了很多关于LLM和经典论文，感兴趣的读者可以参考：【[ML Papers Explained](https://github.com/dair-ai/ML-Papers-Explained)】

---

## LLM Pipeline

### LLM 预训练

这里整理了LLM预训练、微调使用的部分数据集，更多请参考【[DataSet](https://github.com/ArronAI007/Awesome-AGI/blob/main/DataSet/README.md)】

---

### LLM 微调

这里整理关于LLM微调的脚本以及开源工具或者平台的使用案例，更多请参考【[Fine Tune](https://github.com/ArronAI007/Awesome-AGI/tree/main/Fine-Tune/README.md)】

---

### LLM 部署

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| BentoML |  | [BentoML Code](https://github.com/bentoml/BentoML) |  |  
| CLIP-API-service |  |  |  |  
| CTranslate2 |  |  |  |  
| DeepSpeed-MII |  |  |  | 
| FastLLM |  |  |  |   
| Huggingface |  |  |  |   
| JittorLLM |  |  |  |   
| LightLLM |  |  |  |  
| LMDeploy |  |  |  |  
| MLC LLM |  |  |  |  
| OneDiffusion |  |  |  |  
| OpenLLM |  |  |  |  
| Ray Serve |  |  |  |  

【LLM大语言模型之Generate/Inference（生成/推理）中参数与解码策略原理及其代码实现】【[blog](https://mp.weixin.qq.com/s/BbWjr8mr3Iu_JLCK0x2rcA)】

---

### LLM 分布式并行框架

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| ColossalAI |  | [ColossalAI Code](https://github.com/hpcaitech/ColossalAI) |  |  
| DeepSpeed |  |  |  |  
| Megatron-LM |  |  |  |  

---

## LLM 应用

### RAG

#### 向量数据库

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| Chroma |  |  |  |  
| LanceDB |  |  |  |  
| Milvus |  |  |  |  
| Pinecone |  |  |  |  
| QDrant |  |  |  |  
| Weaviate |  |  |  |  
| Zilliz |  |  |  |  

---

#### RAG开源项目

| Description| Code | Blog |
| --- | --- | --- |  
| AnythingLLM | [AnythingLLM Code](https://github.com/Mintplex-Labs/anything-llm) | [AnythingLLM官网](https://useanything.com/) |  
| QAnything | [QAnything Code](https://github.com/netease-youdao/QAnything) |  |  

---

### Agent

| Model| Paper | Code | Blog |
| --- | --- | --- | --- |  
| Agents | [Agents: An Open-source Framework for Autonomous Language Agents](https://arxiv.org/pdf/2309.07870.pdf) | [Agent Code](https://github.com/aiwaves-cn/agents) | [Agent 官网](http://www.aiwaves-agents.com/)，[blog](https://mp.weixin.qq.com/s/OEud_eW7kAMYW2PagdoIcg) |  
| AgentGPT |  | [AgentGPT Code](https://github.com/reworkd/AgentGPT) | [AgentGPT Chat](https://agentgpt.reworkd.ai/zh)，[AgentGPT docs](https://docs.reworkd.ai/introduction) | 
| AgentVerse |  |  |  |   
| AI Legion |  | [AI Legion Chat](https://github.com/eumemic/ai-legion) |  |  
| AutoGen |  |  | [AutoGen blog](https://mp.weixin.qq.com/s/M7xHAA4HSH-cJG3kbvgvNg) |  
| AutoGPT |  | [AutoGPT Code](https://github.com/Significant-Gravitas/Auto-GPT) | [AutoGPT docs](https://docs.agpt.co/setup/) ，[AutoGPT blog](https://generativeai.pub/complete-guide-to-setup-autogpt-revolutionize-your-task-automation-with-gpt-4-39eda5a85821?gi=ea5c40bac6fd) |  
| BabyAGI |  | [BabyAGI Code](https://github.com/yoheinakajima/babyagi) | [BabyAGI docs](https://babyagi.org/) |  
| Camel |  | [CAMEL Code](https://github.com/camel-ai/camel) | [CAMEL Chat](http://agents.camel-ai.org/)，[CAMEL docs](https://www.camel-ai.org/) |  
| crewAI |  | [crewAI Code](https://github.com/joaomdmoura/crewAI) | [crewAI Blog](https://mp.weixin.qq.com/s/FBhrVwBlSMtfK1KTwo1yXg) |  
| CogAgent | --- | --- | --- |  
| Do Anything Machine |  |  | [Do Anything Machine Chat](https://www.doanythingmachine.com/) |  
| Generative Agents | [Generative Agents: Interactive Simulacra of Human Behavior](https://arxiv.org/abs/2304.03442) | [GPTRPG Code](https://github.com/dzoba/gptrpg) |  | 
| Gentopia |  |  |  |  
| Godmode |  |  | [Godmode Chat](https://godmode.space/) |  
| GPT-Engineer |  | [GPT-Engineer Code](https://github.com/AntonOsika/gpt-engineer) |  |   
| HuggingGPT |  | [HuggingGPT Code](https://github.com/microsoft/JARVIS) | [HuggingGPT Chat](https://huggingface.co/spaces/microsoft/HuggingGPT) |  
| MetaGPT |  | [MetaGPT Code](https://github.com/geekan/MetaGPT) |  | 
| NexusGPT |  |  | [NexusGPT Chat](https://nexus.snikpic.io/) |  
| RecurrentGPT |  |  |  |  
| RestGPT | [RestGPT: Connecting Large Language Models with Real-World RESTful APIs](https://arxiv.org/abs/2306.06624) | [RestGPT Code](https://github.com/Yifan-Song793/RestGPT) | [RestGPT blog](https://mp.weixin.qq.com/s/cdkezgE31ozGPiLZBU9Cxw) | 
| RoboGen | [RoboGen: Towards Unleashing Infinite Data for Automated Robot Learning via Generative Simulation](https://arxiv.org/abs/2311.01455) | [RoboGen Code](https://github.com/Genesis-Embodied-AI) | [项目主页](https://robogen-ai.github.io/)，[blog](https://mp.weixin.qq.com/s/2bQTuwE-k6ukp--XHXIzMg) |   
| Toolformer | [Toolformer: Language Models Can Teach Themselves to Use Tools](https://arxiv.org/pdf/2302.04761.pdf) |  | [Toolformer blog](https://www.sensorexpert.com.cn/article/194585.html) |  
| XAgent |  | [XAgent Code](https://github.com/OpenBMB/XAgent) | [XAgent官网](https://x-agent.net/)，[XAgent Blog](https://blog.x-agent.net) |  
| Xlang |  |  |  |  

---

### LLM 应用框架

#### LangChain

整理关于LangChain的相关笔记和课程，更多请参考【[LangChain](https://github.com/ArronAI007/Awesome-AGI/tree/main/LangChain/README.md)】

---

#### LlamaIndex

整理关于LlamaIndex的相关笔记和课程，更多请参考【[LlamaIndex](https://github.com/ArronAI007/Awesome-AGI/blob/main/LlamaIndex/README.md)】

#### TaskingAI

整理关于LlamaIndex的相关笔记和课程，更多请参考【[LlamaIndex](https://github.com/ArronAI007/Awesome-AGI/blob/main/TaskingAI/README.md)】

---

## LLM Concepts

### Prompt Engineering

| FrameWork | Paper | Code | Blog |
| --- | --- | --- | --- |  
| AoT | [Algorithm of Thoughts: Enhancing Exploration of Ideas in Large Language Models](https://arxiv.org/abs/2308.10379) |  |  |  
| CoT | [Chain-of-Thought Prompting Elicits Reasoning in Large Language Models](https://arxiv.org/abs/2201.11903) |  |  |  
| CoTSC | [Self-Consistency Improves Chain of Thought Reasoning in Language Models](https://arxiv.org/abs/2203.11171) |  |  |  
| Cue-CoT | [Cue-CoT: Chain-of-thought Prompting for Responding to In-depth Dialogue Questions with LLMs](https://arxiv.org/abs/2305.11792) | [Cue-CoT Code](https://github.com/ruleGreen/Cue-CoT) | [Cue-CoT blog](https://mp.weixin.qq.com/s/zJHZTuNPNc0jyj5OvvL3-g) |  
| GoT | [Graph of Thoughts: Solving Elaborate Problems with Large Language Models](https://arxiv.org/abs/2308.09687) |  |  |  
| PoT | [Program of Thoughts Prompting: Disentangling Computation from Reasoning for Numerical Reasoning Tasks](https://arxiv.org/abs/2211.12588) |  |  |  
| SoT | [Skeleton-of-Thought: Large Language Models Can Do Parallel Decoding](https://arxiv.org/abs/2307.15337) |  |  |  
| ToT | [Tree of Thoughts: Deliberate Problem Solving with Large Language Models](https://arxiv.org/abs/2305.10601) |  |  |  

Some examples of **Prompt Engineering** as follows：

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| 提示词管理工具agenta |  |  | [agenta主页](https://agenta.ai/) |  
| OpenAI 应用人工智能研究负责人Lilian Weng新博文：关于提示工程的介绍 | |  | [blog](https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/) | 
| Prompt Engineering全面自动化 | | | [blog](https://mp.weixin.qq.com/s/aj8Ls463jpF92ssn6Acwzg) | 
| ChatGPT提示示例集合 | [huggingface](https://huggingface.co/datasets/fka/awesome-chatgpt-prompts) | [ChatGPT提示示例集合](https://github.com/f/awesome-chatgpt-prompts/) | [主页](https://prompts.chat) | 
| ChatGPT Prompt工程：设计、实践与思考 | | | [blog](https://mp.weixin.qq.com/s/a8hjzZ_Rzl6pOU1PRAARJQ) | 
| 指令学习综述｜ChatGPT背后的指令学习是什么 | [Is Prompt All You Need? No. A Comprehensive and Broader View of Instruction Learning](https://arxiv.org/pdf/2303.10475v2.pdf) | | [blog](https://mp.weixin.qq.com/s/BK30JkIlshwkdHRjaRCD2g) | 

更多请参考【[Prompt Engineering](https://github.com/ArronAI007/Awesome-AGI/tree/main/Prompt-Engineering/README.md)】

---

### RLHF

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| 复现RLHF：通过开源项目 trl 搭建一个通过强化学习算法（PPO）来更新语言模型（GPT-2） |  | [code](https://github.com/HarderThenHarder/transformers_tasks/tree/main/RLHF) | [blog](https://mp.weixin.qq.com/s/1v4Uuc1YAZ9MRr1UWMH9xw) |  
| 详解大模型RLHF过程（配代码解读） |  |  | [blog](https://mp.weixin.qq.com/s/2M3igy7Ctk2LAdNQLSO5tg) |  
| 想训练ChatGPT？得先弄明白Reward Model怎么训（附源码） |  |  | [blog](https://mp.weixin.qq.com/s/1v4Uuc1YAZ9MRr1UWMH9xw) |  

---

### LLM 扩词表

【LLM大模型之基于SentencePiece扩充LLaMa中文词表实践】【[blog](https://mp.weixin.qq.com/s/N1mJ0gfDgNzztO55D-QNVg)】

---

### LLM 长文本

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| Transformer升级之路：一种全局长度外推的新思路 |  |  | [blog](https://mp.weixin.qq.com/s/YJ647EUfzWaJsGoMdgsguA) |  
| ChatGPT能写长篇小说了，ETH提出RecurrentGPT实现交互式超长文本生成 | [paper](https://arxiv.org/abs/2305.13304) | [code](https://github.com/aiwaves-cn/RecurrentGPT) | [blog](https://mp.weixin.qq.com/s/5UVTwSWgoz7uhozMeps3EQ)，[demo1](https://www.aiwaves.org/recurrentgpt (长篇小说写作))，[demo2](https://www.aiwaves.org/interactivefiction (交互式小说)) |  
| 语言大模型100K上下文窗口的秘诀 |  |  | [blog](https://mp.weixin.qq.com/s/_i0eQgYNSLJydv3qOTqr-Q) |  
| RoPE可能是LLM时代的Resnet |  |  | [blog](https://mp.weixin.qq.com/s/BVm1XC7r1yzOiWIrEbWg3A) |  
| 图解RoPE旋转位置编码及其特性 |  |  | [blog](https://mp.weixin.qq.com/s/-1xVXjoM0imXMC7DKqo-Gw) |  
| 详解基于调整RoPE旋转角度的大模型长度外推方法 |  |  | [blog](https://mp.weixin.qq.com/s/RtI95hu-ZLxGkdGuNIkERQ) | 
| 无需微调的自扩展大模型上下文窗口 | [LLM Maybe LongLM: Self-Extend LLM Context Window Without Tuning](https://simg.baai.ac.cn/paperfile/a34ae7f4-f0ce-4f8f-b8f2-e8e4d84bbee5.pdf) | --- | --- |   
| 大模型长文本评估方案CLongEval | [CLongEval: A Chinese Benchmark for Evaluating Long-Context Large Language Models](https://arxiv.org/pdf/2403.03514) | [CLongEval Code](https://github.com/zexuanqiu/CLongEval) | [CLongEval Blog](https://mp.weixin.qq.com/s/LuyanfotOGJhdUQ5fnUkqg) |  

---

### LLM 幻觉

解决幻觉常用的两种方法：1）不断增加模型的数据规模、提升数据质量；2）通过调用搜索等外部工具让模型能够获取实时信息。

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| 腾讯AILab等《大型语言模型中的幻觉》，全面阐述检测、解释和减轻幻觉 | [Siren's Song in the AI Ocean: A Survey on Hallucination in Large Language Models](https://www.zhuanzhi.ai/paper/61ebe9c5007cf1373b900452ad52f0ae) | [code](https://github.com/HillZhang1999/llm-hallucination-survey) | [blog](https://mp.weixin.qq.com/s/GrN0FO_HrEk4GMYdJWJCMQ) |  
| LLM幻觉的解决方案及其应用 | [Cognitive Mirage: A Review of Hallucinations in Large Language Models](https://arxiv.org/abs/2309.06794v1) | [code](Cognitive Mirage: A Review of Hallucinations in Large Language Models) | [blog](https://mp.weixin.qq.com/s/9yQeGk1mRgc9ityn5imxxw) |  

---

### LLM 可控性与安全

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| 微软提出Control-GPT：用GPT-4实现可控文本到图像生成！ | [paper](https://arxiv.org/abs/2305.18583) |  |  [blog](https://mp.weixin.qq.com/s/U3eWeGOEt9nhW-Xwbuah9w)|  
| AIGC如何安全可控?中山大学等最新《AIGC中对隐私和安全的挑战及其补救措施：探索隐私计算、区块链潜在应用》全面阐述 | [paper](https://www.zhuanzhi.ai/paper/0dd95e1d5aae9eb2e60aabf36a107482) |  | [blog](https://mp.weixin.qq.com/s/V8QjMQSO2tX6PFx_LfLIEA) |  
| ControlVideo: 可控的Training-free的文本生成视频 | [paper](https://arxiv.org/pdf/2305.13077.pdf) | [code](https://github.com/YBYBZhang/ControlVideo) | [blog](https://mp.weixin.qq.com/s/CAH6u-MT3cFM359d5_Xpxg) |  
| 大模型切脑后变身PoisonGPT，虚假信息案例 |  | [code](https://colab.research.google.com/drive/16RPph6SobDLhisNzA5azcP-0uMGGq10R?usp=sharing&ref=blog.mithrilsecurity.io) | [blog](https://hub.baai.ac.cn/view/27736) |  
| ChatGPT羊驼家族全沦陷！CMU博士击破LLM护栏，人类毁灭计划脱口而出 | [paper](https://arxiv.org/abs/2307.15043) | [code](https://github.com/llm-attacks/llm-attacks) | [blog](https://mp.weixin.qq.com/s/298nwP98UdRNybV2Fuo6Wg) |  

---

### LLM 文本检测

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| 美国麻省大学&谷歌研究院：改写文本可以避开AI生成文本的检测器，但检索则是一种有效的防御 | [paper](https://papers.labml.ai/api/v1/redirect/pdf?paper_key=2cfe8cecc9f211edb95839eec3084ddd) | [code](https://github.com/martiansideofthemoon/ai-detection-paraphrases) |  |  
| 人工智能生成的文本能被可靠地检测出来吗？ | [paper](https://arxiv.org/pdf/2303.11156.pdf) |  | [blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247486128&idx=3&sn=e5ea32b7d7cb4c8c41f29a9ea15ac3ac&chksm=ced54954f9a2c0425a65761f1766550f6b90857da0106f6fd55f3c6773fbdbd1fc45bbb9369a&token=447941009&lang=zh_CN#rd) |  
| DetectGPT（斯坦福大学）：利用概率曲率检测文本是否大模型生成 | [paper](https://arxiv.org/abs/2301.11305) | [code&data](https://ericmitchell.ai/detectgpt/) | [blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485713&idx=2&sn=805caf25603cf15dbf71949f85b9d041&chksm=ced54af5f9a2c3e3e0dffd728592fd7ab8f738869e94240daba4fad9f6ac90a2f76a6b458e3f&token=447941009&lang=zh_CN#rd) |  
| Detecting LLM-Generated-Text综述 | [paper](https://github.com/datamllab/The-Science-of-LLM-generated-Text-Detection) |  | [blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485747&idx=1&sn=5e5029a70c54c08f6f8c40631962b1e1&chksm=ced54ad7f9a2c3c184ccb123199510bb09470e054fb5cb887e70bac204927b65e296f8921db1&token=447941009&lang=zh_CN#rd) |  
| 一个专为**教育**者打造的全新 AI 检测模型 |  |  | [blog](https://gptzero.substack.com/p/gptzerox) |  
| OpenAI重磅发布官方「ChatGPT检测器」 |  |  | [blog](https://mp.weixin.qq.com/s/EcZE7TgHspf22rPRWhAybw) |  
| 斯坦福最新研究：不要过度依赖GPT生成内容，其检测器可能存在不利于非母语英语写作者的偏见 | [paper](https://arxiv.org/abs/2304.02819) |  |  |  
| TUM发布最新《检测ChatGPT生成文本现状》综述 | [paper](https://arxiv.org/abs/2309.07689) |  |  |  

---

## 欢迎共创

【👬🏻】欢迎Star ⭐️⭐️⭐️⭐️⭐️ && 提交 Pull requests 👏🏻👏🏻👏🏻

## 关于我

**个人主页**：wshzd.github.io

**微信公众号**：

![公众号二维码](https://i.postimg.cc/g092W4dB/ArronAI.jpg)

## 声明

以上部分资料来自网络整理，供大家学习参考，如有侵权，麻烦联系我删除！ 

WeChat：h18821656387
