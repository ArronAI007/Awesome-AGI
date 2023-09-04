# Awesome-AGI

[![Anurag's GitHub stats](https://github-readme-stats.vercel.app/api?username=ArronAI007)](https://github.com/anuraghazra/github-readme-stats)

## 技术交流

欢迎加入AIGC技术交流群，与AI领域专家和各行各业的AIGC爱好者一起交流技术理论与行业信息！不管你是学术界还是工业界实践者或爱好者，都欢迎加入群体！

| 交流群二维码                    | 拉你入群(备注AIGC-github)  |
| ------------------------------- | :------------------------: |
| ![Arron](https://i.postimg.cc/PqFvY1kW/AIGC-group.jpg) | ![Arron](https://i.postimg.cc/QMqj1DGc/Arron.jpg) |

## Table of Context
- [AIGC视频会议 访谈](#AIGC视频会议-访谈)
  - [论文分享](#论文分享)
  - [访谈 视频](#访谈-视频)
- [LLM体验效果](#LLM体验效果)
- [LLM领域大模型](#LLM领域大模型)
  - [法律](#法律)
  - [医疗](#医疗)
  - [金融](#金融)
  - [环境](#环境)
  - [网络安全](#网络安全)
  - [交通](#交通)
  - [其他](#其他)
- [LLM关键技术与应用](#LLM关键技术与应用)
  - [Prompt Engineering](#Prompt-Engineering)
  - [LLM 数据集](#LLM-数据集)
  - [LLM RLHF](#LLM-RLHF)
  - [LLM 可控性与安全](#LLM-可控性与安全)
  - [LLM 长文本解决方案](#LLM-长文本解决方案)
  - [LLM 问答](#LLM-问答)
  - [LLM Agent](#LLM-Agent)
  - [LLM 文本检测](#LLM-文本检测)
- [LLM训练 微调 优化 评估以及部署](#LLM训练-微调-优化-评估以及部署)
  - [LLM训练](#LLM训练)
  - [LLM微调](#LLM微调)
  - [LLM优化](#LLM优化)
  - [LLM评估](#LLM评估)
  - [LLM部署](#LLM部署)
- [AGI Paper List](#AGI-Paper-List)
- [文本生成](#文本生成)
  - [ChatGPT](#ChatGPT)
    - [ChatGPT 应用篇](#ChatGPT-应用篇)
    - [ChatGPT 工具篇](#ChatGPT-工具篇)
    - [ChatGPT 技术篇](#ChatGPT-技术篇)
  - [GPT4](#GPT4)
    - [GPT4 官方文档](#GPT4-官方文档)
    - [GPT4 博客篇](#GPT4-博客篇)
    - [GPT4 论文篇](#GPT4-论文篇)
  - [Anima](#Anima)
  - [Bard](#Bard)
  - [Baize](#Baize)
  - [baichuan以及扩展](#baichuan以及扩展)
  - [BLOOM](#BLOOM)
  - [BiomedGPT](#BiomedGPT)
  - [Claude](#Claude)
  - [Claude 2](#Claude-2)
  - [ChatGLM以及扩展](#ChatGLM以及扩展)
  - [ChatYuan](#ChatYuan)
  - [Copilot X](#Copilot-X)
  - [ColossalAI](#ColossalAI)
  - [CPM-Bee](#CPM-Bee)
  - [ChatDB](#ChatDB)
  - [Dolly](#Dolly)
  - [Dolly2.0](#Dolly2.0)
  - [DeepSpeed-Chat](#DeepSpeed-Chat)
  - [FrugalGPT](#FrugalGPT)
  - [GPT3.5](#GPT3.5)
  - [JittorLLMs](#JittorLLMs)
  - [LLM as Controller](#LLM-as-Controller)
  - [MetaGPT](#MetaGPT)
  - [MiniGPT-4](#MiniGPT-4)
  - [MOSS](#MOSS)
  - [OpenChatKit](#OpenChatKit)
  - [OpenAssistant](#OpenAssistant)
  - [Platypus](#Platypus)
  - [WebCPM](#WebCPM)
  - [LLaMA以及扩展](#LLaMA以及扩展)
- [图像 视频生成](#图像-视频生成)
- [代码生成](#代码生成)
- [语音生成](#语音生成)
- [多模态生成](#多模态生成)

## AIGC视频会议 访谈

### 论文分享

| Description| Paper | Code | Blog |Video |
| --- | --- | --- | --- | --- |  
| AugGPT：利用ChatGPT进行文本数据增强 |[AugGPT: Leveraging ChatGPT for Text Data Augmentation](https://arxiv.org/abs/2302.13007) | | [blog](https://hub.baai.ac.cn/view/24771) | [link](https://event.baai.ac.cn/activities/664) |
| ChatGPT的鲁棒性探究——对抗性和分布外泛化的视角 | [On the Robustness of ChatGPT: An Adversarial and Out-of-distribution Perspective ](https://arxiv.org/pdf/2302.12095.pdf) | [code](https://github.com/microsoft/robustlearn) | [blog](https://hub.baai.ac.cn/view/24771) |[link](https://event.baai.ac.cn/activities/657) |
| 传统检索模型和大语言模型（GPT-3）在信息搜索中的应用和对比 | [Generate rather than Retrieve: Large Language Models are Strong Context Generators](https://arxiv.org/abs/2209.10063) |[code](https://github.com/wyu97/GenRead) | [blog](https://hub.baai.ac.cn/view/24380) | [link](https://event.baai.ac.cn/activities/656) | 

### 访谈 视频

| Description| Blog |
| --- | --- |  
| OpenAI 的核心研发人员 Jack Rae 在参加 Stanford MLSys Seminar 的访谈时进行了一个名为 Compression for AGI的主题分享 | [访谈记录](https://mp.weixin.qq.com/s/hQmvltuMlClBonM6UJmtLg) | 
| 万字长文：想训大模型？这里有一份避坑指南 | [访谈记录](https://mp.weixin.qq.com/s/yX5B1ZzV7vewQs1-ezHIQg) | 
| 微软Bing版ChatGPT表明想做人类，并且对纽约时报专栏作家表达爱意 | [访谈记录](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485854&idx=1&sn=011e0ef0f2c69cd48d042495b2a47eb3&chksm=ced54a7af9a2c36c29fec6301236685d443bde94681ec3f669408d953ae92bb54b686aeab9f8&token=447941009&lang=zh_CN#rd) | 
| Midjourney创始人David Holz关于生成式AI的访谈 | [访谈记录](https://mp.weixin.qq.com/s/jMyuSYu8ACk2peu_OfZK0w) | 
| OpenAI创始人：GPT-4的研究起源和构建心法 | [访谈记录](https://mp.weixin.qq.com/s/hO1ZdqgOjpA328luobQ9eg) | 
| ABC News 专访OpenAI首席执行官萨姆·奥尔特曼：AI风险和重塑社会的问题 | [访谈记录](https://abcnews.go.com/Technology/openai-ceo-sam-altman-ai-reshape-society-acknowledges/story?id=97897122) | 
| OpenAI联合创始人Ilya Sutskever等专访：开源人工智能是不明智的 | [访谈记录](https://www.theverge.com/2023/3/15/23640180/openai-gpt-4-launch-closed-research-ilya-sutskever-interview) | 
| OpenAI董事长、CTO Greg Brockman专访 ：GPT-4 并不完美，不过人无完人 | [访谈记录](https://techcrunch.com/2023/03/15/interview-with-openais-greg-brockman-gpt-4-isnt-perfect-but-neither-are-you/) | 
| 图灵奖获得者 Yoshua Bengio 认为 ChatGPT 是一个“警钟” | [访谈记录](https://mp.weixin.qq.com/s/2-QoJHKWxiS63vEjX9OOGQ) | 
| 《麻省理工科技评论》对 ChatGPT 幕后团队，进行了一次深入的独家专访 | [访谈记录](https://www.technologyreview.com/2023/03/03/1069311/inside-story-oral-history-how-chatgpt-built-openai) | 
| 口述历史，探析ChatGPT的创造历程，ChatGPT内部故事 | [访谈记录](https://mp.weixin.qq.com/s/RAdIxzdgs3elUiozB8cH8g) | 
| 对话ChatGPT之父！AI会改变什么？不会改变什么？ | [访谈记录](https://mp.weixin.qq.com/s/zNuOmVeVKP335iJ4RNJqNw) | 
| 对话OpenAI研究科学家：他们是如何让GPT4更像人的？ | [访谈记录](https://mp.weixin.qq.com/s/iJImioHXxelCxUsETSxuXw) | 
| 邱锡鹏教授介绍以ChatGPT为核心的大规模语言模型的相关知识及未来的发展方向 | [视频](https://www.bilibili.com/video/BV1Xb411X7c3/) | 

## LLM体验效果

| Model_A| Model_B | Blog |
| --- | --- | --- |                                                                                                                     
| 360智脑 | 讯飞星火 | [对比效果](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247486609&idx=2&sn=7fedb8ab37588d43968fdec2d7e5fcdd&chksm=ced54f75f9a2c663b9a2671f2548e2940730735605356cc0ffe72bc737470136a40032c80bfe&token=1282379489&lang=zh_CN#rd)|
| 阿里通义千问 | 讯飞星火 | [对比效果](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247486534&idx=1&sn=6f36d41b618790cba62e63eb25bb033b&chksm=ced54fa2f9a2c6b4a901528f87a7e74628dfd79d835f4cdea1ee4dea442f339adfd2736b2305&token=1282379489&lang=zh_CN#rd)|
| Bard | Bing_VS_ChatGPT | [对比效果](https://www.theverge.com/2023/3/24/23653377/ai-chatbots-comparison-bard-bing-chatgpt-gpt-4)|
| 文心一言 | Bard | [对比效果](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247486260&idx=1&sn=a41224fee7ed4cb4a48eb40a420d7479&chksm=ced548d0f9a2c1c6f4930f30447468f9f01bb2af6031368e302b13a6354fc4bca6636e3b297e&token=666852558&lang=zh_CN#rd)|
| 文心一言 | Baize-7B | [对比效果](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247486317&idx=1&sn=ea3cc745d2991b8c657325392ce68f71&chksm=ced54889f9a2c19f3c2f85d8d7af7fff366027f79d1f4a5b2c650fea1b5dee9efde0b7c992ca&token=1173964254&lang=zh_CN#rd)|
| 文心一言 | OpenAssistant | [对比效果](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247486413&idx=2&sn=3816e5a4bccceee5e2af868166b18897&chksm=ced54829f9a2c13fb787b7a7e3c2aa0799eb7ff6d124f6847349346146900e05684ceb8cc7f7&token=1282379489&lang=zh_CN#rd)|
| 文心一言 | ChatGLM-6B | [对比效果](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247486081&idx=2&sn=fd87305419158d66dd4b05b57bee1324&chksm=ced54965f9a2c073ba1badfedbc6610036455cd769a3c8ee3445f7fbff9364b5624091be9914&token=666852558&lang=zh_CN#rd)|
| 文心一言 | GPT-4 | [对比效果](https://mp.weixin.qq.com/s/l1pTPlohMmiYEMc4x6QKhw)|
| 文心一言 | GPT-4实测 | [对比效果](https://mp.weixin.qq.com/s/uO8N3RpcrYU8rV1RkwBxzQ)|
| 文心一言 | 讯飞星火 | [对比效果](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247486490&idx=1&sn=c8d756f7f26a4e35f8b67ae485efabce&chksm=ced54ffef9a2c6e8d66f8b744d6af524e320d5aec384d142621cee53fd2150f2c7db1fa7596a&token=1282379489&lang=zh_CN#rd)|
| GPT4 | ChatGPT | [对比效果](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485952&idx=2&sn=e54a62e358bf7aee3c007d59600fd452&chksm=ced549e4f9a2c0f2868eb8877c14fbe287a469e63b09774cefcb9edc4c0601016f6d36561973&token=666852558&lang=zh_CN#rd)|
| GPT4 | Claude2 | [对比效果1](https://mp.weixin.qq.com/s/dj2_WlWVpGwYsa8kO-GRFQ)，[对比效果2](https://mp.weixin.qq.com/s/Xo3XXQ5zYPmDxBYivhBYqA)|

## LLM领域大模型

【论文】[[垂直领域大模型的一些思考及开源模型汇总](https://mp.weixin.qq.com/s/HiGkSwbGeo4sPZvQeKCJfQ)]，[[大模型时代-行业落地的再思考](https://mp.weixin.qq.com/s/wSQSjO_0OmIg2kBZUuXA4Q)]

### 法律

| Model| Paper | Code | Blog |
| --- | --- | --- | --- |  
| CaMA |  |  | [blog](https://mp.weixin.qq.com/s/FYWmMH2ndN5XfWvwI9dcUA) |  
| ChatLaw | [ChatLaw: Open-Source Legal Large Language Model with Integrated External Knowledge Bases](https://arxiv.org/pdf/2306.16092.pdf) | [ChatLaw Code](https://github.com/PKU-YuanGroup/ChatLaw)|[official website](https://www.chatlaw.cloud/) |
| ExpertLLaMA |  |  | [blog](https://mp.weixin.qq.com/s/FYWmMH2ndN5XfWvwI9dcUA) |  
| LaWGPT |  | [LaWGPT Code](https://github.com/pengxiao-song/LaWGPT) | [LaWGPT Blog](https://mp.weixin.qq.com/s/dI839IF0hdBTAfOBUg7Pfw) |  
| LAW-GPT |  | [LAW-GPT Code](https://github.com/LiuHC0428/LAW-GPT) |  |  
| LexiLaw |  | [LexiLaw Code](https://github.com/CSHaitao/LexiLaw) |  |  
| lawyer-llama |  | [lawyer-llama Code](https://github.com/AndrewZhe/lawyer-llama) |  |  

### 医疗

| Model| Paper | Code | Blog |
| --- | --- | --- | --- |  
| AD-AutoGPT | [AD-AutoGPT: An Autonomous GPT for Alzheimer's Disease Infodemiology](https://arxiv.org/abs/2306.10095) |  |  | 
| BianQue |  | [BianQue](https://github.com/scutcyr/BianQue) |  | 
| ChatMed | | [ChatMed](https://github.com/michael-wzhu/ChatMed) |  | 
| DoctorGLM | | [DoctorGLM](https://github.com/xionghonglin/DoctorGLM) |  | 
| Huatuo-Llama-Med-Chinese |  | [Huatuo-Llama-Med-Chinese](https://github.com/SCIR-HI/Huatuo-Llama-Med-Chinese) |  | 
| Med-PaLM |  | [Large language models encode clinical knowledge](https://www.nature.com/articles/s41586-023-06291-2) | [blog](https://mp.weixin.qq.com/s/Qf4Ts7UKJNzkW1Tfy-b0Zg) | 
| MedQA-ChatGLM |  | [MedQA-ChatGLM](http://github.com/WangRongsheng/MedQA-ChatGLM) | [主页](https://www.wangrs.co/MedQA-ChatGLM/) | 
| MedicalGPT-zh |  | [MedicalGPT-zh](https://github.com/MediaBrain-SJTU/MedicalGPT-zh) |  | 
| Med-ChatGLM |  | [Med-ChatGLM](https://github.com/SCIR-HI/Med-ChatGLM) |  | 
| PULSE |  | [PULSE](https://huggingface.co/OpenMEDLab/PULSE-7bv5) |  | 
| ShenNong-TCM-LLM |  | [ShenNong-TCM-LLM](https://github.com/michael-wzhu/ShenNong-TCM-LLM) |  | 
| SoulChat |  | [SoulChat](https://github.com/scutcyr/SoulChat) |  | 

【医疗领域大模型的幻觉问题分析】[[blog](https://mp.weixin.qq.com/s/1o4u0Em0fFk9YndTaF2I7A)]

【基于中文金融知识的 LLaMA 系微调模型的智能问答系统：LLaMA大模型训练微调推理等详细教学】[[blog](https://mp.weixin.qq.com/s/lrKPUcS9GkSS20-Jda-8bA)]

【中文多模态医学大模型智能分析X光片，实现影像诊断，完成医生问诊多轮对话】[[blog](https://mp.weixin.qq.com/s/Spb_dbsHRyP9EvUaMYgHxw)]

### 金融

| Model| Paper | Code | Blog |
| --- | --- | --- | --- |  
| FinGPT | [FinGPT: Open-Source Financial Large Language Models](https://arxiv.org/pdf/2306.06031v1.pdf) | [FinGPT](https://github.com/ai4finance-foundation/fingpt) | [blog](https://mp.weixin.qq.com/s/A9euFin675nxGGciiX6rJQ) | 
| FinTuo |  | [FinTuo](https://github.com/qiyuan-chen/FinTuo-Chinese-Finance-LLM) |  | 

### 环境

| Model| Paper | Code | Blog |
| --- | --- | --- | --- |  
| NowcastNet | [Skilful nowcasting of extreme precipitation with NowcastNet](https://www.nature.com/articles/s41586-023-06184-4) |  | [blog](https://mp.weixin.qq.com/s/Aygm03CdA0zFNf9F3_JU5A) | 

### 网络安全

| Model| Paper | Code | Blog |
| --- | --- | --- | --- |  
| FraudGPT |  |  | [blog](https://mp.weixin.qq.com/s/OtLNybsbxDlbVb-cs4Zk8g) | 

### 教育

| Model| Paper | Code | Blog |
| --- | --- | --- | --- |  
| EduChat |  | [EduChat](https://github.com/icalk-nlp/EduChat) |  | 

### 交通

| Model| Paper | Code | Blog |
| --- | --- | --- | --- |  
| TransGPT |  | [TransGPT](https://github.com/DUOMO/TransGPT) | [blog](https://mp.weixin.qq.com/s/WvzyjHqI0lOGIyPlCIFNQg) | 

### 其他

| Model| Paper | Code | Blog |
| --- | --- | --- | --- |  
| Panda LLM | [Panda LLM: Training Data and Evaluation for Open-Sourced Chinese Instruction-Following Large Language Models](https://arxiv.org/pdf/2305.03025v1.pdf) | [Panda LLM](https://github.com/dandelionsllm/pandallm) | [blog](https://mp.weixin.qq.com/s/IsWSPAvwgT263wjO7TYTZQ) | 

## LLM关键技术与应用

### Prompt Engineering

Some examples of AGI Paper List as follows：

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| OpenAI 应用人工智能研究负责人Lilian Weng新博文：关于提示工程的介绍 | |  | [blog](https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/) | 
| Prompt Engineering全面自动化 | | | [blog](https://mp.weixin.qq.com/s/aj8Ls463jpF92ssn6Acwzg) | 
| ChatGPT提示示例集合 | [huggingface](https://huggingface.co/datasets/fka/awesome-chatgpt-prompts) | [ChatGPT提示示例集合](https://github.com/f/awesome-chatgpt-prompts/) | [主页](https://prompts.chat) | 
| ChatGPT Prompt工程：设计、实践与思考 | | | [blog](https://mp.weixin.qq.com/s/a8hjzZ_Rzl6pOU1PRAARJQ) | 
| 指令学习综述｜ChatGPT背后的指令学习是什么 | [Is Prompt All You Need? No. A Comprehensive and Broader View of Instruction Learning](https://arxiv.org/pdf/2303.10475v2.pdf) | | [blog](https://mp.weixin.qq.com/s/BK30JkIlshwkdHRjaRCD2g) | 

**Complete Content**: please refer to [Prompt Engineering](https://github.com/ArronAI007/Awesome-AGI/tree/main/Prompt/README.md)

### LLM 数据集

【**Instruct Tuning**】【一篇关于LLM指令微调的综述】[[blog](https://mp.weixin.qq.com/s/7pqBvgF1BWDFxP5hajmBNw)]，[[paper](https://arxiv.org/pdf/2308.10792.pdf)]

【**COIG-PC**】【智源研究院发布国内首个大规模、可商用中文开源指令数据集COIG：最大规模中文多任务指令集，上新千个中文数据集】[[blog](https://mp.weixin.qq.com/s/PvJa8dPHk6aGEv1G1B3PUw)]，[[paper](https://arxiv.org/pdf/2304.07987.pdf)]，[[COIG-PC数据下载地址](https://huggingface.co/datasets/BAAI/COIG-PC)]，[[COIG数据下载地址](https://huggingface.co/datasets/BAAI/COIG)]

【**Instruct/Prompt Tuning可用数据**】【总结当前开源可用的Instruct/Prompt Tuning数据】[[blog](https://mp.weixin.qq.com/s/vDbTJo3F7sy3-NY8xxg8jw)]

【**MiniGPT-4**】【GPT-4平替版：MiniGPT-4，支持图像理解和对话，现已开源】[[dataset](https://drive.google.com/file/d/1nJXhoEcy3KTExr17I7BXqY5Y9Lx_-n-9/view)]

【**Multimodal C4**】【多模态C4：一个开放的、10亿规模的、与文本交错的图像语料库】[[paper](https://arxiv.org/abs/2304.06939)]，[[code](https://github.com/allenai/mmc4)]

【**Mind2Web**】【Mind2Web: 首个全面衡量大模型上网能力的数据集】[[blog](https://mp.weixin.qq.com/s/vge4CJbBfLXFIYYyNC12Hw)]

<details><summary>展开更多</summary>
<p>

【**OpenAssistant Conversations**】【该数据集是一个由人工生成、人工注释的助理式对话语料库，覆盖了广泛的主题和写作风格，由 161443 条消息组成，分布在 66497 个会话树中，使用 35 种不同的语言。该语料库是全球众包工作的产物，涉及超过 13500 名志愿者。为了证明 OpenAssistant Conversations 数据集的有效性，该研究还提出了一个基于聊天的助手 OpenAssistant，其可以理解任务、与第三方系统交互、动态检索信息。】[[dataset](https://huggingface.co/datasets/OpenAssistant/oasst1 )]，[[paper](https://drive.google.com/file/d/10iR5hKwFqAKhL3umx8muOWSRm7hs5FqX/view )]，[[code](https://github.com/LAION-AI/Open-Assistant )]

【**Panda LLM**】【为了让Panda LLM在中文数据集上获得强大的性能，作者使用了强大的指令微调instruction-tuning技术，将LLaMA基础模型在五个开源的中文数据集进行混合训练，其中包括来自各种语言领域的1530万个样本，例如维基百科语料，新闻语料，百科问答语料，社区问答语料，和翻译语料。】[[blog](https://mp.weixin.qq.com/s/IsWSPAvwgT263wjO7TYTZQ)]

【**RedPajama**】【RedPajama开源项目｜复制超过1.2万亿个令牌的LLaMA训练数据集】[[原始blog](https://www.together.xyz/blog/redpajama)]，[[中文blog](https://hub.baai.ac.cn/view/25485)]，[[dataset](https://huggingface.co/datasets/togethercomputer/RedPajama-Data-1T)]，[[code](https://github.com/togethercomputer/RedPajama-Data)]
</p>
</details>

### LLM RLHF

**【LLM RLHF】**【复现RLHF：通过开源项目 trl 搭建一个通过强化学习算法（PPO）来更新语言模型（GPT-2）】[[blog](https://mp.weixin.qq.com/s/1v4Uuc1YAZ9MRr1UWMH9xw)]，[[code](https://github.com/HarderThenHarder/transformers_tasks/tree/main/RLHF)]

**【LLM RLHF】**【详解大模型RLHF过程（配代码解读）】[[blog](https://mp.weixin.qq.com/s/2M3igy7Ctk2LAdNQLSO5tg)]

**【LLM RM】**【想训练ChatGPT？得先弄明白Reward Model怎么训（附源码）】[[blog](https://mp.weixin.qq.com/s/1v4Uuc1YAZ9MRr1UWMH9xw)]

### LLM 可控性与安全

**【可控性】**【微软提出Control-GPT：用GPT-4实现可控文本到图像生成！】[[paper](https://arxiv.org/abs/2305.18583)]，[[blog](https://mp.weixin.qq.com/s/U3eWeGOEt9nhW-Xwbuah9w)]

**【可控性】**【AIGC如何安全可控?中山大学等最新《AIGC中对隐私和安全的挑战及其补救措施：探索隐私计算、区块链潜在应用》全面阐述】[[paper](https://www.zhuanzhi.ai/paper/0dd95e1d5aae9eb2e60aabf36a107482)]，[[blog](https://mp.weixin.qq.com/s/V8QjMQSO2tX6PFx_LfLIEA)]

**【可控性】**【ControlVideo: 可控的Training-free的文本生成视频】[[blog](https://mp.weixin.qq.com/s/CAH6u-MT3cFM359d5_Xpxg)]，[[paper](https://arxiv.org/pdf/2305.13077.pdf)]，[[code](https://github.com/YBYBZhang/ControlVideo)]

**【安全】**【大模型切脑后变身PoisonGPT，虚假信息案例】[[blog](https://hub.baai.ac.cn/view/27736)]，[[code](https://colab.research.google.com/drive/16RPph6SobDLhisNzA5azcP-0uMGGq10R?usp=sharing&ref=blog.mithrilsecurity.io)]

**【安全】**【ChatGPT羊驼家族全沦陷！CMU博士击破LLM护栏，人类毁灭计划脱口而出】[[blog](https://mp.weixin.qq.com/s/298nwP98UdRNybV2Fuo6Wg)]，[[paper](https://arxiv.org/abs/2307.15043)]，[[code](https://github.com/llm-attacks/llm-attacks)]

### LLM 长文本解决方案

**【苏剑林】**【Transformer升级之路：一种全局长度外推的新思路】[[blog](https://mp.weixin.qq.com/s/YJ647EUfzWaJsGoMdgsguA)]

**【博客】**【ChatGPT能写长篇小说了，ETH提出RecurrentGPT实现交互式超长文本生成】[[paper](https://arxiv.org/abs/2305.13304)]，[[code](https://github.com/aiwaves-cn/RecurrentGPT)]，[[blog](https://mp.weixin.qq.com/s/5UVTwSWgoz7uhozMeps3EQ)]，[[demo1](https://www.aiwaves.org/recurrentgpt (长篇小说写作))]，[[demo2](https://www.aiwaves.org/interactivefiction (交互式小说))]

**【博客】**【语言大模型100K上下文窗口的秘诀】[[blog](https://mp.weixin.qq.com/s/_i0eQgYNSLJydv3qOTqr-Q)]

**【博客】**【RoPE可能是LLM时代的Resnet】[[blog](https://mp.weixin.qq.com/s/BVm1XC7r1yzOiWIrEbWg3A)]

### LLM 问答

**【LLM 问答流程】**【基于大语言模型的智能问答系统应该包含哪些环节？】[[blog](https://mp.weixin.qq.com/s/pXEyFHEv1pcqwMNhveneew)]，[[OpenAI 的审核函数接口 Moderation API](https://platform.openai.com/docs/guides/moderation)]

**【ChatPDF】**【搭建本地的chatpdf（原理，文档处理，语义搜索等）】[[blog](https://mp.weixin.qq.com/s/aW7r4i54coW26RMsTdAQ5g)]

**【LlamaIndex】**【如何避免大语言模型绕过知识库乱答的情况？LlamaIndex 原理与应用简介】[[官方blog](https://betterprogramming.pub/llamaindex-how-to-use-index-correctly-6f928b8944c6)]，[[中文blog](https://mp.weixin.qq.com/s/D6_pUv7hHZHRrKSXqo0u2w)]

**【Langchain】**【使用 Langchain 和 Azure OpenAI 构建一个聊天机器人来查询您的文档】[[blog](https://mp.weixin.qq.com/s/LeUuq6O5uIJPmrrYYtTaqA)]

**【Langchain】**【一文搞懂LangChain是什么】[[blog](https://mp.weixin.qq.com/s/vLlS17AYe4lM95KrG5sFyQ)]

### LLM Agent

**【AutoGPT】**【】

**【BabyAGI】**【】

**【ChatRPA】**【在TARS大模型的加持下，它不仅能够理解人类的意图，还能操作所有桌面软件，包括各种复杂的CS架构软件，甚至对不开放接口的软件也能操作】

**【GPT-Engineer】**【】

### LLM 文本检测

**【论文&代码】**【美国麻省大学&谷歌研究院：改写文本可以避开AI生成文本的检测器，但检索则是一种有效的防御】[[paper](https://papers.labml.ai/api/v1/redirect/pdf?paper_key=2cfe8cecc9f211edb95839eec3084ddd)]，[[code](https://github.com/martiansideofthemoon/ai-detection-paraphrases)]

**【论文】**【人工智能生成的文本能被可靠地检测出来吗？】[[paper](https://arxiv.org/pdf/2303.11156.pdf )]，[[blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247486128&idx=3&sn=e5ea32b7d7cb4c8c41f29a9ea15ac3ac&chksm=ced54954f9a2c0425a65761f1766550f6b90857da0106f6fd55f3c6773fbdbd1fc45bbb9369a&token=447941009&lang=zh_CN#rd)]

**【论文】**【DetectGPT（斯坦福大学）：利用概率曲率检测文本是否大模型生成】[[paper](https://arxiv.org/abs/2301.11305)]，[[blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485713&idx=2&sn=805caf25603cf15dbf71949f85b9d041&chksm=ced54af5f9a2c3e3e0dffd728592fd7ab8f738869e94240daba4fad9f6ac90a2f76a6b458e3f&token=447941009&lang=zh_CN#rd)]，[[code&data](https://ericmitchell.ai/detectgpt/)]

**【论文】**【Detecting LLM-Generated-Text综述】[[paper](https://github.com/datamllab/The-Science-of-LLM-generated-Text-Detection)]，[[blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485747&idx=1&sn=5e5029a70c54c08f6f8c40631962b1e1&chksm=ced54ad7f9a2c3c184ccb123199510bb09470e054fb5cb887e70bac204927b65e296f8921db1&token=447941009&lang=zh_CN#rd)]

**【论文】**【一个专为**教育**者打造的全新 AI 检测模型】[[blog](https://gptzero.substack.com/p/gptzerox)]

<details><summary>展开更多</summary>
<p>

**【论文】**【OpenAI重磅发布官方「ChatGPT检测器」】[[blog](https://mp.weixin.qq.com/s/EcZE7TgHspf22rPRWhAybw)]

**【论文】**【斯坦福最新研究：不要过度依赖GPT生成内容，其检测器可能存在不利于非母语英语写作者的偏见】[[paper](https://arxiv.org/abs/2304.02819)]
</p>
</details>

## LLM训练 微调 优化 评估以及部署

**【LLM 学习网站】**【训练、微调、优化和部署大模型最新技术LLM Learning Lab】[[官网](https://lightning.ai/pages/llm-learning-lab/)]

**【LLM 算力评估】**【PEFT | Transformer参数量、计算量、显存占用分析】[[官网](https://mp.weixin.qq.com/s/5zxfwlO-skxZchJ0qtzqAw)]

**【LLM Tokenizer】**【Tokenizer的系统梳理，并手推每个方法的具体实现】[[blog](https://mp.weixin.qq.com/s/W8QaPQFeGO7S6mTZt8iKcg)]

### LLM训练

| Description| Blog |
| --- | --- | 
| 从头预训练大模型实践经验 | [blog](https://mp.weixin.qq.com/s/q8XNFzsm_sm_EocCIks-1w) | 
| DeepSpeed的Tutorials | [主页](https://www.deepspeed.ai)，[DeepSpeed Getting Starte](https://mp.weixin.qq.com/s/xpNQtl7hPs3fy9S7VRbIkg) | 
| 打造LLM界的Web UI：24GB显卡训练百亿大模型 | [blog](https://mp.weixin.qq.com/s/x9oED0Uxc5Wt-eR0Amde7g) | 
| 大模型训练感知量化开山之作：LLM-QAT | [blog](https://mp.weixin.qq.com/s/zKndNym9Q7QJWlmn60HmyQ) | 
| 混合精度训练技术梳理总结 | [blog](https://mp.weixin.qq.com/s/j-f47VPHKAkCwpwEheEgJQ) | 
| LLM大模型训练Trick系列之拒绝采样 | [blog](https://zhuanlan.zhihu.com/p/649731916) | 
| Muti Query Attention 和 Attention with Linear Bias（附源码） | [blog](https://mp.weixin.qq.com/s/GXMwnbWLce9Aq4alEHCHJA)，[paper](https://arxiv.org/pdf/1911.02150.pdf) | 
| 如何使用 Megatron-LM 训练语言模型 | [blog](https://mp.weixin.qq.com/s/QPg6gOWGbQDezTl8OFZU3g) | 

### LLM微调

| Description| Blog |
| --- | --- | 
| PEFT: 在低资源硬件上对十亿规模模型进行参数高效微调 | [blog](https://mp.weixin.qq.com/s/x2mQBE0pfTv8w3Czp8JkDg) | 
| 大语言模型（LLM）微调技术笔记 | [code](https://github.com/ninehills/ninehills.github.io/issues/92) | 
| 大模型LLM-微调经验分享&总结 | [code](https://github.com/liucongg/ChatGLM-Finetuning)，[blog](https://mp.weixin.qq.com/s/pkBvL0k7sZWaW6jMlSSIZA) | 
| LoRA：卷完图像生成领域，卷文本生成领域的东西，到时是个啥？ | [blog](https://mp.weixin.qq.com/s/emLpTAOhr8khO1hTgQhU9w)，[code](https://github.com/microsoft/LoRA) | 
| QLoRA：在单个48GB GPU上对65B参数的大模型进行微调，只需微调12个小时就可以达到97%的ChatGPT水平。同时只用int4就可以保持fp16精度的效果。 | [paper](https://arxiv.org/pdf/2305.14314.pdf) | 
| 华盛顿大学提出全新量化和微调方法，在DB-GPT上享受33B参数的LLM | [blog](https://mp.weixin.qq.com/s/A3flqm2FeOn0WQr5mrD1-Q) | 
| MeZO：高效零阶优化器，单卡A100可训练300亿参数模型 | [paper](https://arxiv.org/abs/2305.17333)，[code](https://github.com/princeton-nlp/MeZO)，[blog](https://mp.weixin.qq.com/s/JteUpY4fEbENQFvReRLPJg) | 
| 人工智能大语言模型微调技术：SFT 监督微调、LoRA 微调方法、P-tuning v2 微调方法、Freeze 监督微调方法 | [blog](https://mp.weixin.qq.com/s/N0Z1Kq0mrVrK-RED_gvJmw) | 
| LLM微调经验分享 | [中文blog](https://mp.weixin.qq.com/s/83sqfeaoSKtMSo_5Sf_doA)，[英文blog](https://twitter.com/xinqiu_bot/status/1679786303716749312) | 
| Firefly项目 | [介绍Firefly项目如何充分高效训练多轮对话大模型](https://mp.weixin.qq.com/s/WG_YCk6DM8nWvLfpw1OmoA)，[源码解析ChatGLM2多轮对话训练方法的不足，以及改进方法](https://mp.weixin.qq.com/s/r-JOLsoIAgZynGIeryU1-Q) | 

### LLM优化

| Description| Blog |
| --- | --- | 
| 伯克利开源LLM推理与服务库：GPU减半、吞吐数十倍猛增 | [中文blog](https://hub.baai.ac.cn/view/27505)，[英文blog](https://vllm.ai/?continueFlag=24b2e01413fd53e24a2779b4a664ca16) | 
| CAME：大模型训练成本降低近一半 | [blog](https://mp.weixin.qq.com/s/iUXu_Pfsop0bq7ktoXTY4A) | 
| 大模型推理性能优化之KV Cache解读 | [blog](https://mp.weixin.qq.com/s/ydjcUOF9iUM581hUTSXPdw) | 
| LLM，压缩即泛化，泛化即智能 | [blog](https://mp.weixin.qq.com/s/tSj9npIPg8IlYr2jbtg-Og) | 
| LLM-Pruner: 剪枝+少量数据+少量训练 = 高效的LLM压缩 | [blog](https://mp.weixin.qq.com/s/feqFfy4n31eztoZfodMieQ) | 
| LLM Accelerator：使用参考文本无损加速大语言模型推理 | [blog](https://mp.weixin.qq.com/s/H1JaQZ9-m2gkZaIwzJTTtg)，[paper](https://arxiv.org/pdf/2304.04487.pdf)，[code](https://github.com/microsoft/LMOps) | 
| LLM 的推理优化技术纵览 | [blog](https://mp.weixin.qq.com/s/Os4Uy8K6z2fVMSa7ihR1dg) | 
| LLM量化之后，能力退化了多少 | [blog](https://mp.weixin.qq.com/s/ri4SS_NCKn4boGZfJtUWUQ) | 
| 邱锡鹏团队提出新优化器LOMO｜650亿参数，8块GPU全参数微调 | [blog](https://mp.weixin.qq.com/s/339iXf2bimusfq6zQmFpWw)，[paper](https://arxiv.org/abs/2306.09782) | 
| 继思维链、思维树后又一思维骨架：让大模型能做并行解码 | [blog](https://mp.weixin.qq.com/s/cyyKEtGe6QBmP8aAU9fmhQ) | 

### LLM评估

| Description| Blog |
| --- | --- | 
| 工程实践！以LLAMA为例的大模型部署方案 | [blog](https://mp.weixin.qq.com/s/zGkkekFqKsnM66uQwfUPcw) | 
| 一文看遍各行业对ChatGPT的专业评估 | [blog](https://mp.weixin.qq.com/s/2JryWW33j9udOpi3dK5X9g) | 
| ChatGPT关于推理、幻觉和交互的多任务、多语言、多通道评估 | [paper](https://arxiv.org/abs/2302.04023) | 
| 如何评价 OpenAI 的超级对话模型 ChatGPT ？ | [paper](https://www.zhihu.com/question/570189639) | 
| 用ChatGPT参加计算机科学考试 | [paper](https://arxiv.org/abs/2303.09461) | 
| C-Eval：构造中文大模型的知识评估基准 | [主页](https://cevalbenchmark.com/)，[paper](https://mp.weixin.qq.com/s/4560jl7ctWmHz3xGVIKkRw)，[code](https://github.com/SJTU-LIT/ceval)，[blog](https://mp.weixin.qq.com/s/4560jl7ctWmHz3xGVIKkRw) | 
| 多模态大模型的幻觉问题与评估 | [blog](https://mp.weixin.qq.com/s/s0z-mAyjAaqvNcaTg2VFEA)，[paper](https://arxiv.org/abs/2305.10355)，[code](https://github.com/RUCAIBox/POPE) | 
| 谷歌提出TrueTeacher：基于大型语言模型的学习事实一致性评价 | [blog](https://mp.weixin.qq.com/s/tcqHXIHxrkiYrYBX8JzIZA)，[paper](https://arxiv.org/pdf/2305.10601.pdf) | 
| 粗看大模型ChatGLM、MOSS、Bloomz在中文垂域评测中的性能表现：医学、法律、心理学、教育等四大类试题下的测试报告介绍 | [paper](https://arxiv.org/pdf/2304.12986.pdf)，[code](https://github.com/Felixgithub2017/MMCU)，[blog](https://mp.weixin.qq.com/s/Hq6bn_4vD559TMQxx806tg) | 
| 评测国内各种对标 ChatGPT 的大语言模型 | [blog](https://mp.weixin.qq.com/s/Oe1Rc0kXjMOD2G_Sqambow)，[code](https://github.com/dongrixinyu/JioNLP/wiki/LLM%E8%AF%84%E6%B5%8B%E6%95%B0%E6%8D%AE%E9%9B%86) | 
| OpenLLM大模型排行榜 | [主页](https://huggingface.co/spaces/HuggingFaceH4/open_llm_leaderboard)，[blog](https://mp.weixin.qq.com/s/t1Th8iFOGoyuqqysUiIcXQ)，[最新进展blog](https://zhuanlan.zhihu.com/p/642996275) | 
| 斯坦福发布LLM排行榜AlpacaEval，微软WizardLM登顶开源模型第一 | [blog](https://mp.weixin.qq.com/s/7X8pRaexWJ4c0kVswawU1A)，[主页](https://tatsu-lab.github.io/alpaca_eval)，[code](https://github.com/tatsu-lab/alpaca_eval) | 

### LLM部署

| Description| Blog |
| --- | --- | 
| 工程实践！以LLAMA为例的大模型部署方案 | [blog](https://mp.weixin.qq.com/s/zGkkekFqKsnM66uQwfUPcw) | 
| 大模型部署框架FastLLM解析，支持X86/Arm/CUDA 3种架构的硬件！ | [blog](https://mp.weixin.qq.com/s/j19QdlFvblcABXzB7Vi5wg)，[code](https://github.com/ztxz16/fastllm) | 
| 用 Hugging Face 推理端点部署 LLM | [blog](https://mp.weixin.qq.com/s/ms1ThLcN6uTOFgKm5FqBig) | 
| 【完全指南】如何在本地运行LLM模型：提高模型性能与运行速度 | [blog](https://mp.weixin.qq.com/s/Ijf6MrUdqG0JxiRmF6Wh5w) | 
| LLM 低成本 GPU 部署方案 lmdeploy 开源！ | [blog](https://mp.weixin.qq.com/s/cndjXFr3vJPdN-7aTNqCnQ)，[code](https://github.com/InternLM/lmdeploy) | 
| 使用 BentoML 部署 🤗 Hugging Face 上的模型：DeepFloyd IF 实战 | [中文blog](https://mp.weixin.qq.com/s/GySP9vpzf3cj6vtQAsRRvw)，[英文blog](https://hf.co/blog/deploy-deepfloydif-using-bentoml)，[code](https://github.com/bentoml) | 

## AGI Paper List

Some examples of AGI Paper List as follows：

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| 中文大语言模型汇总：医疗、法律、金融、教育、数学微调， 目前已1.1K星 |  | [code](https://github.com/HqWu-HITCS/Awesome-Chinese-LLM) |  | 
| 大型语言模型综述全新出炉：从T5到GPT-4最全盘点，国内20余位研究者联合撰写 | [A Survey of Large Language Models](https://arxiv.org/abs/2303.18223) |  |  | 
| 大语言模型综述全新出炉：51页论文带你盘点LLM领域专业化技术 | [Domain Specialization as the Key to Make Large Language Models Disruptive: A Comprehensive Survey](https://arxiv.org/abs/2305.18703) |  | [blog](https://mp.weixin.qq.com/s/0DrowrTIgXsBhj3sYu6Aog) | 
| AIGC综述: 从GAN到ChatGPT的生成式人工智能简史 | [A Comprehensive Survey of AI-Generated Content (AIGC): A History of Generative AI from GAN to ChatGPT](https://arxiv.org/abs/2303.04226v1) |  |  | 
| 大模型综述来了！一文带你理清全球AI巨头的大模型进化史 | [Harnessing the Power of LLMs in Practice: A Survey on ChatGPT and Beyond](https://arxiv.org/pdf/2304.13712.pdf) | [code](https://github.com/Mooler0410/LLMsPracticalGuide) |  | 

**Complete Content**: please refer to [AGI Paper List](https://github.com/ArronAI007/Awesome-AGI/tree/main/AGI-Paper-List/README.md)

## 文本生成

### ChatGPT

从GPT3到ChatGPT模型的发展路线图

![ChatGPT_family](https://i.postimg.cc/GtZmmjG2/chatgpt-3.jpg)

#### ChatGPT 应用篇

| Description| Paper | Code |Blog |
| --- | --- | --- | --- | 
| 从 GPT 到 ChatGPT 的演进与应用思考 |  | | [blog](https://mp.weixin.qq.com/s/3Pr82xKpZ7mAWQcxPPB1xA) | 
| 语言模型可以预测公众舆论 | [Language models trained on media diets can predict public opinion](https://arxiv.org/pdf/2303.16779.pdf) |  |  | 
| ChatGPT助力芯片，传统 EDA如何演变成智能EDA |  |  | [blog](https://mp.weixin.qq.com/s/JyveUDEYKLrFolfCFLqhhw) | 
| ChatGPT机器人:设计原则和模型能力 | [ChatGPT for Robotics: Design Principles and Model Abilities](https://www.microsoft.com/en-us/research/group/autonomous-systems-group-robotics/articles/chatgpt-for-robotics/) |  |  | 
| 各种环境下的ChatGPT赋能长步机器人控制： 一个案例的应用 | [ChatGPT Empowered Long-Step Robot Control in Various Environments: A Case Application](https://arxiv.org/pdf/2304.03893.pdf) | [code](https://github.com/microsoft/ChatGPT-Robot-Manipulation-Prompts) |  | 
| ChatGPT获得了「Wolfram」超能力 |  |  | [blog](https://writings.stephenwolfram.com/2023/03/chatgpt-gets-its-wolfram-superpowers/) | 
| OpenAI开发Plugin将 ChatGPT 连接到互联网 |  |  | [blog](https://techcrunch.com/2023/03/23/openai-connects-chatgpt-to-the-internet/) | 
| ChatAug：利用ChatGPT进行文本数据增强 | [ChatAug: Leveraging ChatGPT for Text Data Augmentation](https://arxiv.org/pdf/2302.13007v1.pdf) |  |  | 
| ChatGPT 是数据隐私的另一个障碍吗 |  |  | [blog](https://www.bizcommunity.com/Article/196/639/236418.html) | 
| 基于ChatGPT的数据增强方法：ChatAug和AugGPT |  |  | [blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247486140&idx=1&sn=bba4342966c99559938824f2d747d231&chksm=ced54958f9a2c04ec121b8c198d69a5a17c8b3e0a96a0cfcd8d1271bd6097a2cbf66895dd8a9&token=447941009&lang=zh_CN#rd) | 
| Character.AI 在ChatGPT基础上加入个性化、UGC两大武器，有比 ChatGPT 更丰富的使用场景 |  |  | [blog](https://mp.weixin.qq.com/s/U4R8loz1G9PYM_l6IvNF_A) | 
| 让ChatGPT可以**语音交互** |  |  | [blog](https://mp.weixin.qq.com/s/H4XLCQ-kR7T28yywHJL4uA) | 
| “ChatGPT们”的淘金时代 |  |  | [blog](https://mp.weixin.qq.com/s/otdenJh5FJsCgi5ONy9JIQ) | 
| 70 款 ChatGPT 插件评测（含样例分析） |  |  | [blog](https://mp.weixin.qq.com/s/vHwAk63ukRteF1u1myrTlA) | 
| 人大提出WebBrain：NLP新任务，通过网络数据的挖掘生成真实文章 | [WebBrain: Learning to Generate Factually Correct Articles for Queries by Grounding on Large Web Corpus](https://arxiv.org/abs/2304.04358) | [code](https://github.com/qhjqhj00/WebBrain) |  | 
| ChatGPT爆火带来思考：医学界或将迎来与AI融合的奇点？ |  |  | [blog](https://mp.weixin.qq.com/s/x8ppg6GVCAeLNpv5uJ7B7g) | 
| 论ChatGPT大语言模型在教育中的机遇与挑战 |  |  | [blog](https://url39.ctfile.com/f/2501739-809898048-6394c7?p=2096) | 
| ChatGPT在投资研究领域的应用初探及原理分析 |  |  | [blog](https://mp.weixin.qq.com/s/LFPeSLeEOTb1-2YJBXclbQ) | 
| OpenAI总裁Greg Brockman转发｜一种编译语言的调试器，利用ChatGPT旨在增强您使用GDB进行调试体验 |  | [code](https://github.com/pgosar/ChatGDB) |  | 
| 不必排队等 OpenAI Plugins，OpenBMB 开源大模型工具学习引擎 |  |  | [blog](https://hub.baai.ac.cn/view/25189) | 
| 分析了ChatGPT技术以及落地应用场景 |  |  | [blog](https://url39.ctfile.com/f/2501739-805099789-098b62?p=2096) | 

#### ChatGPT 工具篇

| Description| Paper | Code |Blog |
| --- | --- | --- | --- | 
| ChatGPT 应用汇总及操作手册 |  |  | [blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485794&idx=1&sn=6aa0500e3139b67246dd5f96007d1487&chksm=ced54a86f9a2c390d86856181f1fcd09091cf84d67e81535b6d592617f49fe24349779cfa1e5&token=447941009&lang=zh_CN#rd) | 
| ChatGPT提示和技巧速查手册 |  |  | [blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485766&idx=1&sn=43ad627e4e183d7a108c3c57ab0e02dc&chksm=ced54aa2f9a2c3b4a2d529e4ed7c2acc7fa32e7465837045d3ec607701e0da2a55c0c557cad2&token=447941009&lang=zh_CN#rd) | 
| 非常全面的ChatGPT、LLM相关资源整理分享 |  | [code](https://github.com/cedrickchee/chatgpt-universe) |  | 
| ChatGPT超全面课程 |  |  | [blog](https://tested-salto-cab.notion.site/The-Ultimate-Chat-GPT-Course-69ed24a317a942d288e740419b1ad6f6) | 
| BloombergGPT: A Large Language Model for Finance | [BloombergGPT: A Large Language Model for Finance](https://papers.labml.ai/api/v1/redirect/pdf?paper_key=b0e4b03ecf5c11edb95839eec3084ddd) |  |  | 
| ChatPDF：一键上传PDF文件即可解读 |  |  | [blog](https://mp.weixin.qq.com/s/S1DUJrNK5_H5krvHotOwHQ)，[试用地址](https://www.chatpdf.com/) | 
| ChatWeb：可爬取网页正文，并根据正文回答问题 |  | [code](https://github.com/SkywalkerDarren/chatWeb) |  | 
| chatgpt_academic：中科院基于 ChatGPT 专属定制的学术研究及日常开发工具 | --- | [code](https://github.com/binary-husky/chatgpt_academic) | [blog](https://hub.baai.ac.cn/view/25298)，[demo](https://huggingface.co/spaces/qingxu98/gpt-academic) | 
| Einstein GPT：SaaS 行业巨头 Salesforce 宣布与 OpenAI 合作，推出 Einstein GPT，这是全球首个用于客户关系管理（CRM）的生成式 AI 产品 |  |  | [Einstein GPT地址](https://www.salesforce.com/products/einstein/overview/?d=cta-body-promo-8)，[试用地址](https://openai.com/waitlist/slack) | 
| HuggingGPT: Solving AI Tasks with ChatGPT and its Friends in HuggingFace | [HuggingGPT: Solving AI Tasks with ChatGPT and its Friends in HuggingFace](https://arxiv.org/pdf/2303.17580.pdf) |  |  | 
| ImpressionGPT： 利用ChatGPT对放射科报告进行总结的迭代优化框架 | [ImpressionGPT: An Iterative Optimizing Framework for Radiology Report Summarization with ChatGPT](https://arxiv.org/abs/2304.08448) |  |  | 
| OpenGpt：创建ChatGPT小应用的AI平台 |  | [code](https://github.com/futantan/OpenGpt) | [官网](https://open-gpt.app/) | 
| TagGPT：腾讯提出零样本多模态标签的大语言模型TagGPT | [TagGPT: Large Language Models are Zero-shot Multimodal Taggers](https://arxiv.org/abs/2304.03022) | [code](https://github.com/TencentARC/TagGPT) |  | 
| Visual ChatGPT: 在视觉模型加持下的ChatGPT，聊天生图全拿捏了。 | [Visual ChatGPT: Talking, Drawing and Editing with Visual Foundation Models](https://arxiv.org/pdf/2303.04671.pdf) |  |  | 
| NetGPT：用于网络流量的生成预训练Transformer模型 | [NetGPT: Generative Pretrained Transformer for Network Traffic](https://arxiv.org/pdf/2304.09513.pdf) |  |  | 

#### ChatGPT 技术篇

| Description| Paper | Code |Blog |
| --- | --- | --- | --- | 
| ChatGPT_Inference_Cost | --- | --- | [blog](https://github.com/ArronAI007/ChatGPT-Summary/blob/main/ChatGPT/Blog/ChatGPT_Technology/ChatGPT_Inference_Cost.md) | 
| ChatGPT_Official_API_Learning |  |  | [blog](https://github.com/ArronAI007/ChatGPT-Summary/blob/main/ChatGPT/Blog/ChatGPT_Technology/ChatGPT_Official_API_Learning.md) | 
| ChatGPT_Parameter_is_not_175B |  |  | [blog](https://github.com/ArronAI007/ChatGPT-Summary/blob/main/ChatGPT/Blog/ChatGPT_Technology/ChatGPT_Parameter_is_not_175B.md) | 
| ChatGPT_Road_Map_from_yao.fu |  |  | [blog](https://github.com/ArronAI007/ChatGPT-Summary/blob/main/ChatGPT/Blog/ChatGPT_Technology/ChatGPT_Road_Map_from_yao.fu.md) | 
| Lessons_Learned_from_ChatGPT_Recurrence |  |  | [blog](https://github.com/ArronAI007/ChatGPT-Summary/blob/main/ChatGPT/Blog/ChatGPT_Technology/Lessons_Learned_from_ChatGPT_Recurrence.md) | 
| LLM_Pre-training_Guide（Bloom-175B） |  |  | [blog](https://github.com/ArronAI007/ChatGPT-Summary/blob/main/ChatGPT/Blog/ChatGPT_Technology/LLM_Pre-training_Guide（Bloom-175B）.md) | 
| The_guide_of_training_LLM |  |  | [blog](https://github.com/ArronAI007/ChatGPT-Summary/blob/main/ChatGPT/Blog/ChatGPT_Technology/The_guide_of_training_LLM.md) | 
| 深度拆解GPT-3.5能力起源 |  |  | [原文blog](https://yaofu.notion.site/GPT-3-5-360081d91ec245f29029d37b54573756)，[译文blog](https://mp.weixin.qq.com/s/ckd6KxeTfdQas_UCsJ7HgQ) | 
| ChatGPT发展历程、原理、技术架构详解和产业未来 |  |  | [blog](https://zhuanlan.zhihu.com/p/590655677) | 
| 让天下没有难训练的大模型，微软亚洲研究院开源TorchScale |  | [code](https://github.com/microsoft/torchscale) |  | 
| 82页PPT ！最新ChatGPT: 提示学习, 指导微调和RLHF |  |  | [blog](https://pan.baidu.com/s/15Bs1u7z1RhCdfiR3oJ_gJQ), [提取码:chat]| 
| 他们提出了包含视觉特征的 Multimodal-CoT，该架构在参数量小于 10 亿的情况下，在 ScienceQA 基准测试中，比 GPT-3.5 高出 16 个百分点 | [Multimodal Chain-of-Thought Reasoning in Language Models](https://arxiv.org/abs/2302.00923) | [code](https://github.com/amazon-science/mm-cot) |  | 
| Nature ：生成式 AI 的前景与风险 |  |  | [blog](https://mp.weixin.qq.com/s/d6t2xpdvSDCHzO2gG1N6eQ) | 
| 万字长文解读：从Transformer到ChatGPT，通用人工智能曙光初现 |  |  | [blog](https://mp.weixin.qq.com/s/iZyKmWgXUkPv3Phyaw4Ppg) | 
| AI芯片制造商Cerebras发布7个基于GPT的大语言模型，现已开源 |  |  | [官网地址](https://www.cerebras.net/blog/cerebras-gpt-a-family-of-open-compute-efficient-large-language-models/)，[GPT地址](https://www.cerebras.net/cerebras-gpt)，[Hugging Face地址](https://huggingface.co/cerebras) | 
| 大模型论文周报丨GPT-4发布，谷歌开放PaLM API，斯坦福7B开源模型Alpaca媲美GPT-3.5 |  |  | [blog](https://mp.weixin.qq.com/s/C6g_H6xfFn59IxnLpbjA1g) | 
| LLaMA模型Meta版泄露，GitHub获8K星 |  |  | [blog](https://mp.weixin.qq.com/s/2M19WSq2YICo-3t5ibQcig) | 
| ChatGPT or Grammarly? Evaluating ChatGPT on Grammatical Error Correction Benchmark | [ChatGPT or Grammarly? Evaluating ChatGPT on Grammatical Error Correction Benchmark](https://arxiv.org/abs/2303.13648) |  |  | 
| 打造中国版ChatGPT，国内哪家实力最强 |  |  | [blog](https://mp.weixin.qq.com/s/B-n_qz110HmhSP66NKRCiQ) | 
| 复旦大学邱锡鹏教授解读ChatGPT |  |  | [blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485810&idx=1&sn=47eb672c688517d6bade2c62c7eae94f&chksm=ced54a96f9a2c380ccacfbb223df52de64f2c410a91e726023a074fc98fb87fcd9f60f5a4957&token=447941009&lang=zh_CN#rd) | 
| 万字长文:可能是全网最晚的ChatGPT技术总结 |  |  | [blog](https://mp.weixin.qq.com/s/LJoxupaKflL793TCwnpyPg) | 
| ChatGPT作为知识库问答系统的问答能力评测 |  |  | [blog](https://mp.weixin.qq.com/s/xul2-SENnqxV8VehozDKHg) | 
| ChatGPT作者John Shulman：我们成功的秘密武器 |  |  | [blog](https://www.talkrl.com/episodes/john-schulman)，[blog译文](https://mp.weixin.qq.com/s/sDeBYMvAwbJr5_tj7Q20-w) | 
| ChatGPT 是数据隐私的另一个障碍吗 |  |  | [blog](https://www.bizcommunity.com/Article/196/639/236418.html) | 
| Hugging Face 每周速递: ChatGPT API 怎么用？我们帮你搭好页面了 |  |  | [blog](https://mp.weixin.qq.com/s/oeXgd78vFV8os2uTGZkFQQ) | 
| 复旦大学教授肖仰华：ChatGPT 浪潮下，面向大模型如何做数据治理？ |  |  | [blog](https://mp.weixin.qq.com/s/od24PYvFLUJe4NQxjvsbMw) | 
| 腾讯在ChatGPT的布局 |  |  | [blog](https://mp.weixin.qq.com/s/rdpGZII3pu3MHr-lFm3GyQ) | 
| 浅析ChatGPT：历史沿革、应用现状及前景展望 |  |  | [blog](https://mp.weixin.qq.com/s/fQ8DmL_M3QMiFX23Tf0z7w) | 
| ChatGPT 背后的“功臣”——人类反馈强化学习RLHF 技术详解 |  |  | [blog](https://mp.weixin.qq.com/s/mZdZS9QNda26Ae0OIhRjFA) | 
| 万字长文解析！复现和使用GPT-3/ChatGPT，你所应该知道的 |  |  | [blog](https://mp.weixin.qq.com/s/ILpbRRNP10Ef1z3lb2CqmA) | 
| 想训练ChatGPT？得先弄明白Reward Model怎么训（附源码） |  |  | [blog](https://mp.weixin.qq.com/s/1v4Uuc1YAZ9MRr1UWMH9xw) | 
| ChatGPT核心技术：强化学习PPO算法 |  |  | [blog](https://mp.weixin.qq.com/s/z4oc9xQmduKMolWxztdHjA) | 
| 解读 ChatGPT 背后的技术重点：RLHF、IFT、CoT、红蓝对抗 |  |  | [blog](https://mp.weixin.qq.com/s/y4ywidZ55BQLgQzJa_Wjbg) | 
| OpenAI ChatGPT Code Interpreter入门 |  |  | [blog](https://www.oneusefulthing.org/p/what-ai-can-do-with-a-toolbox-getting) | 
| 加拿大魁北克大学教授详述：我们该拿ChatGPT怎么办？ |  |  | [blog](https://lemire.me/blog/2023/04/03/what-are-we-going-to-do-about-chatgpt/) | 
| AIGC时代的ChatGPT全面综述 | [One Small Step for Generative AI, One Giant Leap for AGI: A Complete Survey on ChatGPT in AIGC Era](https://arxiv.org/abs/2304.06488) |  |  | 
| ChatGPT is a Knowledgeable but Inexperienced Solver: An Investigation of Commonsense Problem in Large Language Models |  [ChatGPT is a Knowledgeable but Inexperienced Solver: An Investigation of Commonsense Problem in Large Language Models](https://arxiv.org/pdf/2303.16421.pdf) |  |  | 
| GPT-3 和 GPT-3.5 系列模型的全面分析 | [A Comprehensive Capability Analysis of GPT-3 and GPT-3.5 Series Models](https://arxiv.org/abs/2303.10420v1) |  |  | 
| ChatGPT Outperforms Crowd-Workers for Text-Annotation Tasks | [CHATGPT OUTPERFORMS CROWD-WORKERS FOR TEXT-ANNOTATION TASKS](https://arxiv.org/pdf/2303.15056.pdf) |  |  | 
| AdaLoRA：自适应预算分配以实现参数有效的微调 | [ADAPTIVE BUDGET ALLOCATION FOR PARAMETEREFFICIENT FINE-TUNING](https://arxiv.org/pdf/2303.10512.pdf) | [code](https://github.com/QingruZhang/AdaLoRA) |  | 
| 大型语言模型的语境忠实提示法 | [Context-faithful Prompting for Large Language Models](https://arxiv.org/pdf/2303.11315.pdf) |  |  | 
| ChatGPT问，BLIP-2回答模型：面向丰富的视觉描述的自动提问 | [ChatGPT Asks, BLIP-2 Answers: Automatic Questioning Towards Enriched Visual Descriptions](https://arxiv.org/pdf/2303.06594.pdf) | [code](https://github.com/Vision-CAIR/ChatCaptioner) |  | 
| ChatGPT真的可以取代知识图谱问答吗？ | [Can ChatGPT Replace Traditional KBQA Models? An In-depth Analysis of GPT family LLMs' Question Answering Performance](https://arxiv.org/abs/2303.07992)，[paper翻译](https://mp.weixin.qq.com/s/cvBVgxCrreic6U6CU-YB-A) |  |  | 
| Meta & 斯坦福大学推出FlexGen：用单个GPU进行大型语言模型的高吞吐量生成性推理 | [FlexGen: High-Throughput Generative Inference of Large Language Models with a Single GPU](https://arxiv.org/pdf/2303.06865.pdf) | [code](https://github.com/FMInference/FlexGen) |  | 
| ChatGPT破圈的「秘密武器」：详解RLHF如何影响人类社会！ | [Perspectives on the Social Impacts of Reinforcement Learning with Human Feedback](https://arxiv.org/abs/2303.02891) |  | [blog](https://mp.weixin.qq.com/s/DCFhefWGQS5naYwT3o6neg) | 
| 探讨ChatGPT在对抗攻击和分布外泛化下的鲁棒性 | [On the Robustness of ChatGPT: An Adversarial and Out-of-distribution Perspective](https://arxiv.org/pdf/2302.12095.pdf) | [code](https://github.com/microsoft/robustlearn) |  | 
| 复旦清华联合顶刊发文｜ChatGPT：潜力、前景和局限 | [ChatGPT: potential, prospects, and limitations](https://link.springer.com/article/10.1631/FITEE.2300089) |  | [blog](https://mp.weixin.qq.com/s/1D62QuxXFDXWwwRXrB-Ivw) | 
| 引导ChatGPT不要输出有害信息 | [The Capacity for Moral Self-Correction in Large Language Models](https://arxiv.org/pdf/2302.07459.pdf) |  |  | 
| Junnan Li大佬发表最新多模态的杰作BLIP2 | [BLIP-2: Bootstrapping Language-Image Pre-training with Frozen Image Encoders and Large Language Models](https://arxiv.org/abs/2301.12597) | [code](https://github.com/salesforce/LAVIS/tree/main/projects/blip2) | [blog](https://mp.weixin.qq.com/s/xmSy4m7NheY8iComv7grxQ) | 
| Instruction Tuning：无/少样本学习新范式 | [Finetuned Language Models Are Zero-Shot Learners](https://arxiv.org/abs/2109.01652) | [code](https://github.com/google-research/flan) |  | 
| GPTScore：一种新的评估语言模型方法 | [GPTScore: Evaluate as You Desire](https://arxiv.org/abs/2302.04166) | [code](https://github.com/jinlanfu/GPTScore) |  | 
| ChatGPT内核：InstructGPT，基于反馈指令的PPO强化学习 |  |  | [blog](https://zhuanlan.zhihu.com/p/589747432)，[video](https://www.bilibili.com/video/BV1hd4y187CR) | 
| Fine-tune-CoT：小模型也能做推理，完美逆袭大模型 | [Large Language Models Are Reasoning Teachers](https://arxiv.org/pdf/2212.10071.pdf) | [code](https://github.com/itsnamgyu/reasoning-teacher) |  | 
| ChatGPT的潜力解锁：自然语言处理中应用、优势、限制和未来方向的全面探索 | [UNLOCKING THE POTENTIAL OF CHATGPT: A COMPREHENSIVE EXPLORATION OF ITS APPLICATIONS, ADVANTAGES, LIMITATIONS, AND FUTURE DIRECTIONS IN NATURAL LANGUAGE PROCESSING](https://arxiv.org/pdf/2304.02017.pdf) |  |  | 
| 阿里巴巴&清华大学|大型语言模型在算术任务中的表现如何？ | [How well do Large Language Models perform in Arithmetic tasks?](https://arxiv.org/pdf/2304.02015.pdf) | [code](https://github.com/GanjinZero/math401-llm) |  | 
| 本科生60行代码教你手搓GPT大模型 |  | [code](https://github.com/jaymody/picoGPT/tree/29e78cc52b58ed2c1c483ffea2eb46ff6bdec785) |  | 

### GPT4

#### GPT4 官方文档
**【博客】**【GPT4_System_Card中文翻译】[[blog](https://github.com/ArronAI007/ChatGPT-Summary/blob/main/GPT4/Official/GPT-4_System_Card_zh.md)]

**【博客】**【GPT4_Technical_Report中文翻译】[[blog](https://github.com/ArronAI007/ChatGPT-Summary/blob/main/GPT4/Official/GPT4_Technical_Report_zh.md)]

#### GPT4 博客篇

**【博客】**【【万字长文】GPT-4秘密泄露！所有的信息都在这里！从GPT-4 架构、基础设施、训练数据集、成本、视觉到MoE！】[[blog](https://mp.weixin.qq.com/s/vgUKe31pykC12sUV5xyLNQ)]，[[原blog](https://www.semianalysis.com/p/gpt-4-architecture-infrastructure)]

**【纽约时报】**【GPT-4 令人印象深刻但仍在 10 个方面具有缺陷】[[blog](https://www.nytimes.com/2023/03/14/technology/openai-new-gpt4.html)]

**【Open AI】**【多模态大模型GPT-4的新突破】[[blog](https://hub.baai.ac.cn/view/24852)]

**【OpenAI】**【重磅发布GPT-4】[[blog](https://openai.com/research/gpt-4)]

**【OpenAI】**【GPT-4 创造者 Ilya Sutskever 谈 AI 幻觉和 AI 民主】[[blog](https://www.forbes.com/sites/craigsmith/2023/03/15/gpt-4-creator-ilya-sutskever-on-ai-hallucinations-and-ai-democracy/?sh=7743f01e1218)]

<details><summary>展开更多</summary>
<p>

**【OpenAI】**【GPT-4创造者：第二次改变AI浪潮的方向】[[blog](https://mp.weixin.qq.com/s/rZBEDlxFVsVXoL5YUVU3XQ)]

**【OpenAI】**【当GPT-4进入北京市2022高考考场能有什么表现？】[[blog](https://mp.weixin.qq.com/s/N_j01KSuEKuVwCCD69G92g)]

**【博客】**【GPT4技术细节】[[blog](https://github.com/ArronAI007/ChatGPT-Summary/blob/main/GPT4/Blog/GPT4_Technical_Detail.md)]

**【博客】**【GPT4技术关键点总结】[[blog](https://github.com/ArronAI007/ChatGPT-Summary/blob/main/GPT4/Blog/GPT4_Technical_Summary.md)]

**【博客】**【GPT4和ChatGPT的效果对比】[[blog](https://github.com/ArronAI007/ChatGPT-Summary/blob/main/ChatGPT_VS_GPT4/GPT4_VS_ChatGPT（from_nytimes）.md)]

**【博客】**【The Ultimate GPT-4 Guide】[[blog](https://doc.clickup.com/37456139/d/h/13q28b-324/e2a22b0c164b1f9)]

**【博客】**【GPT-4里套娃LLaMA 2！OpenAI创始成员周末爆改「羊驼宝宝」，GitHub一日千星】[[blog](https://mp.weixin.qq.com/s/Tp4q8VflEZ7o8FgpZfrNgQ)]

**【博客】**【Claude 2 解读 ChatGPT 4 的技术秘密：细节：参数数量、架构、基础设施、训练数据集、成本】[[blog](https://mp.weixin.qq.com/s/E2KpvldbYrH0NFvxgfsMlw)]
</p>
</details>

#### GPT4 论文篇

**【微软】**【用GPT-4进行指令调优】[[paper](https://arxiv.org/pdf/2304.03277.pdf)]，[[code](https://instruction-tuning-with-gpt-4.github.io/)]

**【论文】**【点燃通用人工智能的火花：GPT-4的早期实验】[[原始paper](https://arxiv.org/pdf/2303.12712.pdf)]，[[中文版paper](https://event-cdn.baai.ac.cn/file/file-browser/waTXJn85fm3FPyDXpsZ4faGk47trjjYb.pdf)]，[[blog](https://mp.weixin.qq.com/s/H1RVdH0fmwM0GjfV3uvd4g)]

**【论文】**【GPT4All：用GPT-3.5-Turbo的大规模数据提炼训练一个助理式聊天机器人】[[paper](https://s3.amazonaws.com/static.nomic.ai/gpt4all/2023_GPT4All_Technical_Report.pdf)]，[[code](https://github.com/nomic-ai/gpt4all)]

**【论文】**【美国东北大学：可以通过要求GPT4反思“你为什么错了？”来提高30%的性能】[[paper](https://arxiv.org/abs/2303.11366)]，[[code](https://github.com/noahshinn024/reflexion)]

**【论文】**【对ChatGPT/GPT-4研究的总结以及对大型语言模型未来的展望】[[paper](https://arxiv.org/pdf/2304.01852.pdf)]

<details><summary>展开更多</summary>
<p>

**【论文】**【评估日本医疗执照考试的GPT-4和ChatGPT】[[paper](https://arxiv.org/pdf/2303.18027.pdf)]

**【论文】**【Amazon | 深入研究LLMs与AutoGPT的结合：揭示出GPT-4惊人的人类决策能力！】[[blog](https://mp.weixin.qq.com/s/Gbz7ZVVdeTq64mj1-__aQA)]，[[paper](https://arxiv.org/pdf/2306.02224.pdf)]，[[code](https://github.com/younghuman/LLMAgent)]
</p>
</details>

### Anima

【33B QLoRA大语言模型Anima的性能超越了对比的所有的中文开源模型。】[[blog](https://zhuanlan.zhihu.com/p/638058537?utm_source=wechat_session&utm_medium=social&s_r=0)]，[[code](https://github.com/lyogavin/Anima)]，[[model](https://huggingface.co/lyogavin/Anima33B)]

### Bard

【谷歌再次开放Bard访问权，向着ChatGPT发起再一次攻击】[[报名地址 ]([http://Bard.google.com](http://bard.google.com/) )]，[[blog](https://twitter.com/sundarpichai/status/1638180697352593408)]，[[theverge](https://www.theverge.com/23649897/google-Bard-chatbot-search-engine)]

### Baize

【用ChatGPT训练羊驼：「Baize」开源，轻松构建专属模型】[[blog](https://mp.weixin.qq.com/s/zxElGfclNbBwTuDG4Qrxnw)]，[[paper](https://arxiv.org/abs/2304.01196)]，[[code](https://github.com/project-baize/baize/blob/main/README.md)]，[[demo](https://huggingface.co/spaces/project-baize/baize-lora-7B)]

### baichuan以及扩展

**【baichuan-7b】**【王小川大模型首亮相！70亿参数霸榜，清北抢先用｜独家专访】[[blog](https://mp.weixin.qq.com/s/qA_E_3dUe1sSOUM87ZgHdQ)]，[[Hugging Face](https://huggingface.co/baichuan-inc/baichuan-7B)]，[[code](https://github.com/baichuan-inc/baichuan-7B)]，[[Model Scope](https://modelscope.cn/models/baichuan-inc/baichuan-7B/summary)]，[[C-EVAL](https://cevalbenchmark.com/static/leaderboard_zh.html)]

**【firefly-baichuan-7b-qlora-sft】**[使用Firefly项目中的QLoRA训练流程，在moss-003-sft-data百万多轮指令数据上进行了指令微调baichuan-7b模型]，[[blog](https://mp.weixin.qq.com/s/_eTkDGG5DmxyWeiQ6DIxBw)]，[[Hugging Face model](https://huggingface.co/YeungNLP/firefly-baichuan-7b-qlora-sft)]，[[code](https://github.com/baichuan-inc/baichuan-7B)]，[[Model Scope](https://modelscope.cn/models/baichuan-inc/baichuan-7B/summary)]，[[C-EVAL](https://cevalbenchmark.com/static/leaderboard_zh.html)]

**【baichuan-13b-Chat】**【使用Baichuan-13B-Chat模型构建智能文档】[[blog](https://mp.weixin.qq.com/s/wStOyHPd8c7V0ug1Qebryw)]，[[code](https://github.com/percent4/document_qa_with_llm)]

**【baichuan-13b】**【微调BaiChuan13B来做命名实体识别】[[blog](https://mp.weixin.qq.com/s/Px4h2r3VIAFI5vfjXxROxg)]，[[百川大模型【Baichuan-13B】 多卡训练微调记录](https://mp.weixin.qq.com/s/EUZA6Lt-OcI170md9lXH1g)]

### BLOOM

【【LLM系列之BLOOM】BLOOM: 多语言大模型】[[blog](https://mp.weixin.qq.com/s/_Vj-KNxS5SfuF_h7bfMb5Q)]，[[paper](https://arxiv.org/abs/2211.05100)]，[[code](https://github.com/huggingface/transformers-bloom-inference/tree/main)]，[[huggingface](https://huggingface.co/bigscience/bloom)]

### BiomedGPT

【BiomedGPT: 统一通用的生物医学生成式预训练Transformer】[[paper](https://arxiv.org/abs/2305.17100)]

### Claude 

【ChatGPT最强竞品Claude今日开放API】[[产品地址 ](https://www.anthropic.com/product)]，[[申请地址](https://www.anthropic.com/earlyaccess)]，[[API说明 ](https://console.anthropic.com/docs/api)]，[[blog](https://mp.weixin.qq.com/s/Wx5q-rEwG4sROvnewGxWrw)]，[[Claude支持100k上下文](https://mp.weixin.qq.com/s/Yu551-z14lpiFGSOfXE2Tw)]，[[Claude2发布](https://hub.baai.ac.cn/view/27790)]

### Claude 2

【ChatGPT最强竞品Claude2来了】[[blog](https://mp.weixin.qq.com/s/_uIPPJHmiYaBFxtKXdwFbA)]，[[Claude2 API](https://mp.weixin.qq.com/s/yBOJfaUw9ei0WY-64rbCJg)]

### ChatGLM以及扩展

【ChatGLM：千亿基座的对话模型开启内测 ⸺对应单卡版本开源】[[blog](https://chatglm.cn/blog)]，[[code](https://github.com/THUDM/ChatGLM-6B.git)]

【ChatGLM-6B模型结构组件源码阅读】[[blog](https://mp.weixin.qq.com/s/r7KEJmrpJZmY7KBP4veS6A)]

【ChatGLM模型底座模型细节分析】[[blog](https://mp.weixin.qq.com/s/oOdD3MYtE6-sNeAmPthqLg)]

【chatglm+langchain+互联网，你可以将大模型接入网络了】[[blog](https://mp.weixin.qq.com/s/lO6SrEuv4-vNbL8B3G-f8g)]，[[code](https://github.com/LemonQu-GIT/ChatGLM-6B-Engineering/)]

【ChatGLM_multi_gpu_zero_Tuning：简单高效实现多卡微调大模型】[[code](https://github.com/CSHaitao/ChatGLM_mutli_gpu_tuning)]

<details><summary>展开更多</summary>
<p>

【ChatGLM模型通过api方式调用响应时间慢怎么破，Fastapi流式接口来解惑，能快速提升响应速度】[[blog](https://mp.weixin.qq.com/s/5J4UA4ePVZGXJGZsBXeN8Q)]

【ChatGLM 更新：LongBench—评测长文本理解能力的数据集，支持 32k 上下文的 ChatGLM2-6B-32K】[[blog](https://mp.weixin.qq.com/s/Fkm_D26z1jrqA44B82v7Ww)]

**【Chinese-LangChain】**【基于ChatGLM-6b+langchain实现本地化知识库检索与智能答案生成】[[code](https://github.com/yanqiangmiffy/Chinese-LangChain)]，[[blog](https://mp.weixin.qq.com/s/xAsZZ_LOkr9Nj-JafSbXnA)]

【浅尝prompt咒语设计：one-shot微调chatglm-6b实践信息抽取】[[blog](https://mp.weixin.qq.com/s/l7lCbdJ9XGzLPTb3zKDAzQ)]

【基于1万亿token开源大模型Falcon，超越650亿的LLaMA，可商用】[[blog1](https://mp.weixin.qq.com/s/jbRRjG2ferhFPWsMtCaJyg)]，[[blog2](https://mp.weixin.qq.com/s/Vy_xWBuZU0AaaPMCIhKIyw)]
</p>
</details>

### ChatYuan

【ChatYuan：基于PromptCLUE-large的中文对话开源大模型】[[blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485655&idx=1&sn=ad80d8a17d4aaab90b17a79b638c712d&chksm=ced54b33f9a2c225ce292b4e3d5725a668d0bfc9fe0be610c847b31b61714ecf75c06dac1cb5&token=447941009&lang=zh_CN#rd)]

### Copilot X

【GitHub Copilot X编辑器发布，大大提升编码速度】[[blog](https://github.blog/2023-03-22-github-copilot-x-the-ai-powered-developer-experience/)]

### ColossalAI

【穷孩子如何体验ColossalAI SFT（Colab篇）】[[blog](https://mp.weixin.qq.com/s/NS4yySeYd7QUYb7CB9V0lA)]

### CPM-Bee

【中文基座模型CPM-Bee开源了】[[blog](https://mp.weixin.qq.com/s/BO4cDB9KRSODZw3TvZpUAA)]，[[code](https://github.com/OpenBMB/CPM-Bee)]，[[HuggingFace](https://huggingface.co/openbmb/cpm-bee-10b)]

### ChatDB

【清华大学和北京智源人工智能研究院的研究者们提出了ChatDB：用数据库作为符号性记忆模块来增强大语言模型】[[blog](https://mp.weixin.qq.com/s/o3j1vNLHlJ6qTea219A4Qw)]，[[paper](https://arxiv.org/abs/2306.03901)]，[[主页](https://chatdatabase.github.io)]，[[code](https://github.com/huchenxucs/ChatDB)]

### Dolly

【声称它 "**像ChatGPT一样神奇**"，但只需要**使用一台机器**在**不到三个小时的时间里**训练的数据少得多。】[[blog](https://www.databricks.com/blog/2023/03/24/hello-dolly-democratizing-magic-chatgpt-open-models.html )]，[[Databricks Inc地址](https://www.databricks.com )]

### Dolly2.0

【Databricks的dolly-v2-12b，是一个在Databricks机器学习平台上训练的指令跟随型大型语言模型】[[blog_en](https://www.databricks.com/blog/2023/04/12/dolly-first-open-commercially-viable-instruction-tuned-llm)]，[[blog_zh](https://hub.baai.ac.cn/view/25434)]

### DeepSpeed-Chat

【DeepSpeed对话：易于使用、快速而实惠的RLHF训练，在各种规模下训练ChatGPT模型】[[code](https://github.com/microsoft/DeepSpeedExamples/tree/master/applications/DeepSpeed-Chat)]，[[blog](https://hub.baai.ac.cn/view/25414)]

### FrugalGPT

【斯坦福提出FrugalGPT｜性能媲美GPT4，成本降低98%】[[paper](https://arxiv.org/pdf/2305.05176.pdf)]，[[blog](https://www.reddit.com/r/singularity/comments/13dnfd7/frugalgpt_can_match_the_performance_of_the_best/ )]

### GPT3.5

【GPT3.5试用地址 】[[试用地址](https://platform.openai.com/playground )]

### JittorLLMs

【笔记本没有显卡也能跑大模型，具有高性能、配置要求低、中文支持好、可移植等特点】[[code](https://github.com/Jittor/JittorLLMs)]

### LLM as Controller

【LLM as Controller—无限拓展LLM的能力边界】[[blog](https://mp.weixin.qq.com/s/jeb7ugGC6zxsOsfE-w-I0A)]

### MetaGPT

【MetaGPT：多角色元编程框架】[[code](https://github.com/geekan/MetaGPT)]

### MiniGPT-4

【类似GPT-4图像理解与对话能力的AI大模型，已开源】[[主页](https://minigpt-4.github.io/ )]，[[paper](https://github.com/Vision-CAIR/MiniGPT-4/blob/main/MiniGPT_4.pdf )]，[[code](https://github.com/Vision-CAIR/MiniGPT-4 )]，[[video](https://youtu.be/__tftoxpBAw )]，[[dataset](https://drive.google.com/file/d/1nJXhoEcy3KTExr17I7BXqY5Y9Lx_-n-9/view )]，[[Demo](https://6b89c70eb5e14dca33.gradio.live/)]，[[Demo1](https://b2517615b965687635.gradio.live/ )]，[[Demo2](https://c8de8ff74b6a6c6a9b.gradio.live/ )]，[[Demo3](https://0a111504e072685259.gradio.live/)]，[[Demo4](https://90bc0bac96e6457e8f.gradio.live/)]

### MOSS

【FudanNLP团队最新成果，借助RLHF实现人类对齐的MOSS-RLHF来了】[[blog](https://mp.weixin.qq.com/s/BjXtnEEVCQiPOy-_qCNM4g)]，[[code](https://openlmlab.github.io/MOSS-RLHF/)]，[[测试链接](https://huggingface.co/spaces/togethercomputer/OpenChatKit)]，[[模型权重](https://huggingface.co/togethercomputer/GPT-NeoXT-Chat-Base-20B)]，[[数据集](https://laion.ai/blog/oig-dataset/)]

### OpenChatKit 

【ChatGPT开源平替OpenChatKit：参数量200亿，在4300万条指令上微调而成】[[blog](https://mp.weixin.qq.com/s/9Av3nhJLrcYAsBW9vVGjTw)]，[[code](https://github.com/togethercomputer/OpenChatKit)]，[[技术报告](https://openlmlab.github.io/MOSS-RLHF/paper/SecretsOfRLHFPart1.pdf)]

### OpenAssistant

【ChatGPT全球最大开源平替OpenAssistant，基于Pythia和LLaMA微调而来，主要用于训练人类标注的数据，支持35种语言，免费可用RLHF数据】[[官网](https://open-assistant.io/chat)]，[[paper](https://drive.google.com/file/d/10iR5hKwFqAKhL3umx8muOWSRm7hs5FqX/view)]，[[code](https://github.com/LAION-AI/Open-Assistant)]，[[dataset](https://huggingface.co/datasets/OpenAssistant/oasst1)]，[[youtube](https://youtu.be/ddG2fM9i4Kk)]

### Platypus

【Open LLM榜单再次刷新，比Llama 2更强的Platypus来了】[[paper](https://arxiv.org/abs/2308.07317)]，[[blog](https://mp.weixin.qq.com/s/yzfgITUWaCf3Wcdc6lGCQA)]

### WebCPM

【首个联网支持中文问答开源模型WebCPM】[[paper](https://arxiv.org/abs/2305.06849)]，[[code](https://github.com/thunlp/WebCPM)]，[[blog](https://mp.weixin.qq.com/s/m4zsF2HDFHSKc23Oq0O98w)]

### LLaMA以及扩展

**【LLaMA】**【Meta开放小模型LLaMA，性能超过GPT-3】[[paper](https://research.facebook.com/publications/llama-open-and-efficient-foundation-language-models/)]，[[code](https://github.com/facebookresearch/llama)]，[[blog1](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485822&idx=1&sn=b365d93a0a08769aef77f34069da1422&chksm=ced54a9af9a2c38cd5779284b5e9ae573846153e7dc00961dc163664a657d6a3fa5c8c14c7d2&token=447941009&lang=zh_CN#rd)]，[[blog2](https://mp.weixin.qq.com/s/fGNuTcYE8QI9_JKS9LcQ7w)]，[[详聊LLaMA大模型的技术细节](https://mp.weixin.qq.com/s/B9Ue0ihUGAFjT_X__R2u8Q)]

**【LLaMA 2】【LLaMA 2技术细节详细介绍！】**[[blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247486800&idx=1&sn=9b629ca41b9f6b4feedad94363a17253&chksm=ced54eb4f9a2c7a2a5b20c182981b4323b18509f2ca8f482c2a8cdbb29bf570488bdcd280eb6&token=882149695&lang=zh_CN#rd)]，[[在 Hugging Face 上玩转LLaMA 2](https://mp.weixin.qq.com/s/UnzhBJjZfPXsaSu8gNnosw)]，[[伯克利AI博士详解Llama 2的技术细节](https://mp.weixin.qq.com/s/Mee7sMq_bxLpIOOr91li9A)]，[[Chinese-LlaMA2](https://github.com/michael-wzhu/Chinese-LlaMA2)]，[[NLP社区对LLaMA2论文上半部分的讨论](https://mp.weixin.qq.com/s/SJNqjSCBX-k80_r3nmTiuA)]，[[NLP中文社区顶尖研究员们对LLaMA2论文下半部分的讨论](https://mp.weixin.qq.com/s/6k5ML3HtmvBTTCgHBZGycQ)]，[[在Colab笔记本中微调自己的Llama 2模型](https://mp.weixin.qq.com/s/pnDJaOUh_xdNdqSBl53Arw)]，[[三步上手 LLaMA2](https://mp.weixin.qq.com/s/lkRg8-rw57wDNr7FrjOSOQ)]，[[使用 Transformers 量化 Meta AI LLaMA2 中文版大模型](https://mp.weixin.qq.com/s/DEgFNAB4gwWDlQOj7-2CEg)]，[[3个最值得了解llama2开发库，助你快速搭建LLM应用](https://mp.weixin.qq.com/s/_3H6Y_NolUuxYxOo8Pl7fg)]，[[使用 Docker 快速上手中文版 LLaMA2 开源大模型](https://mp.weixin.qq.com/s/9cTNa_oya2Zj9YdDYodCvw)]，[[ Llama 2资料汇总](https://mp.weixin.qq.com/s/-01Dg9ZVfPYM4mZ4iKt8Cw)]

**【llama2.c】**【OpenAI联创Karpathy爱上羊驼：纯C代码实现婴儿Llama2，MacBook可运行，已揽1.6k星】[[blog](https://mp.weixin.qq.com/s/VVR6N1duJM5vAU5cY9FrDQ)]，[[code](https://github.com/karpathy/llama2.c)]

**【LLaMA-2 & Alpaca-2】**【哈工大科大讯飞联合推出中文LLaMA-2 & Alpaca-2大语言模型】[[blog](https://mp.weixin.qq.com/s/sJ_imBdHCD4NibVy58EO2w)]，[[code](https://github.com/ymcui/Chinese-LLaMA-Alpaca-2)]

**【LLaMA评测】**[[blog](https://mp.weixin.qq.com/s/kImwfWWtXMmEDVOhJZ4dJg)]

<details><summary>展开更多</summary>
<p>

**【Alpaca】**【斯坦福发布了一个由LLaMA 7B微调的模型Alpaca（羊驼），训练3小时，性能比肩GPT-3.5】[[blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485890&idx=1&sn=2d1414fc3751353c31b946b3e954a465&chksm=ced54a26f9a2c330082e8c0014c96a6d9bef62e3581875031f203268a11fad09645a75b482b0&token=447941009&lang=zh_CN#rd)]，[[官网](https://crfm.stanford.edu/2023/03/13/alpaca.html)]，[[model](https://crfm.stanford.edu/alpaca)]，[[code](https://github.com/tatsu-lab/stanford_alpaca)]

**【AlpaGasus】**【研究者提出的模型AlpaGasus，使用从52k Alpaca数据中过滤出来的9k高质量数据进行微调，在多个测试集上显著优于原始的Alpaca】[[blog](https://mp.weixin.qq.com/s/UroGj4rIa2nOw6DookpvCQ)]，[[paper](https://arxiv.org/abs/2307.08701)]，[[code](https://lichang-chen.github.io/AlpaGasus/)]

**【Alpaca-CoT】**【Alpaca-CoT：多接口统一的轻量级LLM指令微调平台】[[code](https://github.com/PhoebusSi/Alpaca-CoT)]，[[官网](https://sota.jiqizhixin.com/project/alpaca-cot)]

**【BiLLa】**【BiLLa 是开源的推理能力增强的中英双语 LLaMA 模型】[[blog](https://mp.weixin.qq.com/s/8KDpDC6Fkb_61gFfkcT8TQ)]，[[code](https://github.com/Neutralzz/BiLLa)]

**【CaMA】**【一种支持中英语言的LLaMA模型】[[code](https://github.com/zjunlp/CaMA)]

**【ChatLLaMA】**【初创公司 Nebuly AI在LLaMA基础上加入RLHF 开源 ChatLLaMA 训练方法】[[code](https://github.com/nebuly-ai/nebullvm/tree/main/apps/accelerate/chatllama)]

**【ColossalAI】**【完整复现ChatGPT全流程】[[code](https://github.com/hpcaitech/ColossalAI)]

**【ColossalChat】**【用于克隆 ChatGPT 和完整 RLHF 管道的开源解决方案】[[code](https://github.com/hpcaitech/ColossalAI)]，[[blog](https://syncedreview.com/2023/03/29/colossalchat-an-open-source-solution-for-cloning-chatgpt-with-a-complete-rlhf-pipeline/)]

**【CAMEL】**【从LLaMA衍生并适应临床的模型】[[code](https://github.com/starmpcc/CAMEL)]，[[blog](https://starmpcc.github.io/CAMEL/)]

**【草本（原华驼）】**【让LLaMA模型成为中医专家】[[paper](https://arxiv.org/pdf/2304.06975v1.pdf)]，[[code](https://github.com/SCIR-HI/Huatuo-Llama-Med-Chinese)]，[[blog1](https://mp.weixin.qq.com/s/TYpc_63qDlR6MwscxCKKhA)]，[[blog2](https://mp.weixin.qq.com/s/iuQANmwCS7AXQRik7HwQPg)]

**【DB-GPT】**【基于vicuna-13b和FastChat的开源实验项目】[[code](https://github.com/csunny/DB-GPT)]

**【DeepSpeed-Chat】**【最强ChatGPT训练框架，一键完成RLHF训练！
】[[code](https://github.com/microsoft/DeepSpeedExamples/tree/master/applications/DeepSpeed-Chat)]，[[blog](https://mp.weixin.qq.com/s/kVEBUF20u4SUsHelF39o8Q)]

**【ExpertLLaMA】**【一个使用ExpertPrompting构建的开源聊天机器人，其能力达到ChatGPT的96%。】[[code](https://github.com/OFA-Sys/ExpertLLaMA)]

**【FreedomGPT】**【FreedomGPT使用Electron 和 React构建，它是一个桌面应用程序，允许用户在他们的本地机器上运行LLaMA。】[[官网地址](https://freedomgpt.com/)]

**【FLAN】**【【LLM系列之FLAN】Scaling Instruction-Finetuned Language Models】[[blog](https://mp.weixin.qq.com/s/5jEJH6UBHrk_ILbrLsd6TQ)]

**【GoGPT/GoGPT2】**【基于Llama/Llama 2训练的底座大模型,再扩充词表+继续预训练】[[GoGPT code](https://github.com/yanqiangmiffy/GoGPT)]，[[GoGPT2 code](https://huggingface.co/golaxy/gogpt2-7b)]

**【Koala】**【加州大学BAIR团队提出Koala：学术研究的对话模型】[[blog_zh](https://hub.baai.ac.cn/view/25284)]，[[blog_en](https://bair.berkeley.edu/blog/2023/04/03/koala/)]

**【LLaMA-Adapter】**【**LLaMA-Adapter**，一种用于微调指令遵循[LLaMA](https://github.com/facebookresearch/llama)模型的轻量级自适应方法，使用[Stanford Alpaca](https://github.com/tatsu-lab/stanford_alpaca)提供的 52K 数据。】[[paper](https://arxiv.org/pdf/2303.16199.pdf )]，[[code](https://github.com/ZrrSkywalker/LLaMA-Adapter)]

**【LaVIN】**【MMA方案让羊驼模型实现多模态：训练时间减少71.4%，成本节省99.9%】[[paper](https://arxiv.org/pdf/2305.15023.pdf)]，[[code](https://github.com/luogen1996/LaVIN)]，[[blog](https://mp.weixin.qq.com/s/MRLYk1b7VJ_b6OmJ9mzkdw)]

**【lit-llama】**【基于nanoGPT的LLaMA语言模型，支持量化、LoRA微调和预训练】[[code](https://github.com/Lightning-AI/lit-llama)]

**【LlamaIndex】**【面向QA 系统的全新文档摘要索引】[[blog](https://mp.weixin.qq.com/s/1zvXlcGfVdxU8_Pj5f2E1g)]

**【llama.cpp】**【量化130亿参数LLaMA模型的llama.cpp，推理仅需4GB内存】[[blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485875&idx=1&sn=a4e09d31802c087f1f47bd292e380c19&chksm=ced54a57f9a2c341935b81aa27824dfa740beb7ce33289e0cb5190b5910040c0904371b7e8a0&token=447941009&lang=zh_CN#rd)]

**【llama.cpp优化版】**【Edge AI 变得更快|在 C/C++ 中移植 Facebook 的 LLaMA 模型】[[blog](https://hub.baai.ac.cn/view/25307)]

**【LIMA】**【使用 LoRA 技术对 LLaMA 65B 大模型进行微调及推理】[[blog](https://mp.weixin.qq.com/s?search_click_id=7213828026277652651-1688375605291-1083947599&__biz=MjM5ODExNDA2MA==&mid=2449961473&idx=2&sn=f080fa7b1b5657db9872724caee56519&chksm=b13c7462864bfd741f0f061b87187f2cde36b68020cfe3402717a6858563311cb642eb340989&rd2werd=1&key=ea1d916ce49bb536ce48f3aba8e329d1e1aa6fdcda4f73580b0a5adbd624721e6a974570fd6ef2823ecfa6c95e2dc09179b51e440e9179f79d0ba01f62cf795d6c697f95bf05a28904f4172b11e1ce873a2d7a0e85c74d509e916176aacb43657fd11a6de7611d65bd4ae82315835aa138a423887a219f2971c6a525679fd805&ascene=65&uin=MTkwNzA5OTA4Mw%3D%3D&devicetype=iMac+MacBookPro13%2C2+OSX+OSX+12.6.7+build(21G651)&version=13080109&nettype=WIFI&lang=zh_CN&countrycode=CN&fontScale=100&exportkey=n_ChQIAhIQ0Z339%2BFUk%2Bp0YpfMQjB%2BhxKDAgIE97dBBAEAAAAAANJyNCKr%2F3UAAAAOpnltbLcz9gKNyK89dVj0q5AacL9r2sPbvlDuJo6SwYSJ2wbfYGvc3EDxuk%2BMQS0vl8RLluMN%2Fuh9u2LxBZTHTiuQct62Bjib68qd1EvB8CgGKMV34B5%2BKHCutInPzdE9Uac6dxp0VYtd%2BJnEwljL8jf7mWZdwTkPdEZl1P0OEb3HFzczXelqDR3h7D2xEVmQuFHGIeVi7iPOHMT0AWhhGLdbrVhCKbPT3%2BX9FPOLjJSql2UD95dTmSzZKqdvOIMGpD5t%2F98jDuMUojr9HUMdvljQ1XkiJVnd%2FbqSsLS3S5t7E%2Ftjmjb9g7IxWkY%3D&acctmode=0&pass_ticket=mJ3t3nBN%2BXhKCYp9bzJSkTl%2B9PwobzvYen%2F5Kv4kpcj1Lig98d0DXbcAyqBW0vaB&wx_header=0)]

**【LongLLaMA】**【LLaMA Plus版来了，谷歌推出LongLLaMA，不仅让你的大模型更集中注意力，还能处理超长上线文】[[blog](https://mp.weixin.qq.com/s/K8ExTUUXDruZGwr-PA4oFQ)]，[[paper](https://arxiv.org/pdf/2307.03170.pdf)]，[[code](https://github.com/CStanKonrad/long_llama)]，[[Hugging Face](https://huggingface.co/syzymon/long_llama_3b)]

**【OpenBuddy-LLaMA1-30B】**【3090单卡可部署！OpenBuddy发布基于LLaMA1-30B的跨语言对话模型】[[blog](https://mp.weixin.qq.com/s/k-ZWg0Vuud3Atn3aaXBaCQ)]

**【PaLM】**【【LLM系列之PaLM】PaLM: Scaling Language Modeling with Pathways】[[blog](https://mp.weixin.qq.com/s/MT1xCsJp98BM-lkuOKJF-A)]

**【StackLLaMA】**【使用 RLHF 训练 LLaMA 的实践指南】[[blog_zh](https://hub.baai.ac.cn/view/25341)]，[[blog_en](https://huggingface.co/blog/stackllama)]

**【Vicuna】**【通过对从ShareGPT收集的用户共享对话进行微调的LLaMA训练，Vicuna-13B达到了OpenAI ChatGPT和Google Bard 90%*以上的质量 】[[Vicuna官网地址](https://vicuna.lmsys.org/)]，[[blog](https://hub.baai.ac.cn/view/25328)]
</p>
</details>

## 图像 视频生成

**【博客】**【Genmo Chat】【这是一款创造性的copilot，使用GPT-4和一大套生成人工智能工具创建并编辑您需要的任何视频或图像。 】[[blog](https://www.genmo.ai/)]

**【博客】**【BlenderGPT】【**一款基于GPT-4的扩展程序BlenderGPT开源，这是一个由GPT3/4驱动的全能AI编辑助手，为Blender提供支持** 】[[code](https://github.com/gd3kr/BlenderGPT)]

**【博客】**【Firefly】【Adobe制造了一个人工智能图像生成器--并表示它没有窃取艺术家的作品来做这件事 】[[blog](https://www.theverge.com/2023/3/21/23648315/adobe-firefly-ai-image-generator-announced)]

**【博客】**【Bing Image Creator】【微软推出Bing Image Creator，用户可根据文本提示创建图片】[[blog](https://techcrunch.com/2023/03/21/microsoft-brings-openais-dall-e-image-creator-to-the-new-bing/)]

**【博客】**【Hugging Face 现已支持使用达摩院text-to-video模型从文本生成视频】[[模型地址 ](https://modelscope.cn/models/damo/text-to-video-synthesis/summary)]

<details><summary>展开更多</summary>
<p>

**【论文】**【最新女娲大模型，中科院提出NUWA-XL：扩散模型中的扩散，生成超长视频】[[paper](https://arxiv.org/pdf/2303.12346.pdf)]，[[blog](https://msra-nuwa.azurewebsites.net/#/)]

**【论文】**【艾伦AI研究院 & 华盛顿大学 | CHAMPAGNE：从大规模的网络视频中学习真实世界的对话】[[paper](https://arxiv.org/pdf/2303.09713.pdf)]，[[code](https://seungjuhan.me/champagne)]

**【论文】**【用AI直接复现你在想什么，Stable Diffusion逼真复现图像】[[paper](https://sites.google.com/view/stablediffusion-with-brain/)]，[[blog](https://mp.weixin.qq.com/s/gIwj2eqNph8jHWOhYYEXIg)]

**【论文】**【Stable Diffusion公司新作Gen-1：基于扩散模型的视频合成新模型，加特效杠杠的！】[[paper](https://arxiv.org/pdf/2302.03011)]，[[site](https://research.runwayml.com/gen1)]

**【论文】**【使用Diffusers 实现 ControlNet 高速推理】[[blog](https://mp.weixin.qq.com/s/k8rE9GrF97E-0TKJhih9kw)]

**【论文】**【文生图引入ControlNet，深度、边缘信息全能复用 】[[paper](https://arxiv.org/pdf/2302.05543.pdf)]，[[code](https://github.com/lllyasviel/ControlNet)]

**【论文】**【ChatGPT｜可用于AI绘画，效果飞升47% 】[[paper](https://arxiv.org/abs/2302.12192)]

**【论文】**【智源研究院提出SegGPT： 一个用于分割上下文中所有事物的通用模型】[[paper](https://arxiv.org/pdf/2304.03284.pdf)]

**【论文】**【OpenAI开源新模型代码库Consistency Models，无需对抗训练即可快速获得高质量样本】[[paper](https://arxiv.org/abs/2303.01469)]，[[code](https://github.com/openai/consistency_models)]，[[blog](https://hub.baai.ac.cn/view/25445)]

**【可控图文大模型】**【伯克利&微软｜用GPT-4进行可控的文本-图像生成】[[paper](https://arxiv.org/abs/2305.18583)]
</p>
</details>

## 代码生成

**【综述】**【代码大模型综述：中科院和MSRA调研27个LLMs，并给出5个有趣挑战】[[blog](https://mp.weixin.qq.com/s/t2SMftox6546E7kvRgQMnA)]，[[paper](https://arxiv.org/abs/2212.09420)]，[[项目主页](https://nl2code.github.io)]

**【博客】**【GPT-Engineer｜提需求即可生成整个代码库，已20K星】[[blog](https://mp.weixin.qq.com/s/rtsVsQbh7NnTh5vjgNMJHQ)]，[[code](https://github.com/AntonOsika/gpt-engineer)]

**【博客】**【StarCoder: 最先进的代码大模型】[[blog](https://mp.weixin.qq.com/s/f-WwzLcEO-ZJczI-_bZh3Q)]

**【博客】**【StableCode: Stability Al发布的代码大模型：上下文窗口1.6万token、30亿参数】[[中文blog](https://mp.weixin.qq.com/s/aAGMwSyT7Kgj3FLbzebJaQ)]，[[英文blog](https://stability.ai/blog/stablecode-llm-generative-ai-coding)]，[[4k代码补全模型](https://huggingface.co/stabilityai/stablecode-completion-alpha-3b-4k)]，[[指令模型](https://huggingface.co/stabilityai/stablecode-instruct-alpha-3b)]，[[16k代码补全模型](https://huggingface.co/stabilityai/stablecode-completion-alpha-3b)]

**【论文】**【北京大学：具有大语言模型的自我规划代码生成】[[paper](https://arxiv.org/pdf/2303.06689.pdf)]

<details><summary>展开更多</summary>
<p>

**【论文】**【谷歌提出Self-Debugging:教导大型语言模型进行自我调试】[[paper](https://arxiv.org/pdf/2304.05128.pdf)]

**【论文】**【通过自我改进实现更好的代码语言模型，显著提高模型生成任务的性能】[[paper](https://arxiv.org/pdf/2304.01228.pdf)]

**【论文】**【Baldur: 基于大型语言模型的完全证明生成与修复】[[paper](https://arxiv.org/abs/2303.04910)]

**【论文】**【CodeGeeX: A Pre-Trained Model for Code Generation with Multilingual Evaluations on HumanEval-X 】[[paper](https://arxiv.org/pdf/2303.17568.pdf)]，[[code](https://github.com/THUDM/CodeGeeX)]

**【论文】**【代码模型 CodeGeeX2-6B 开源，最低6GB显存，性能优于StarCoder】[[blog](https://mp.weixin.qq.com/s/roQSCo-7s361P3TmJjjZjA)]，[[code](https://github.com/THUDM/CodeGeeX2)]

**【论文】**【CodeT5+：非常灵活的、面向代码理解和生成的开放大型代码语言模型】[[paper](https://arxiv.org/abs/2305.07922)]

【**工具**】【Cursor：一个集成了 GPT-4 的国内直接可以访问的，优秀而强大的免费代码生成器，可以帮助你快速编写、编辑和讨论代码。】[[官网地址](https://www.cursor.so/)]

**【论文】**【MIT最新研究：利用大预言模型生成Code】[[paper](https://arxiv.org/abs/2303.05510)]，[[code](https://github.com/shunzh/Code-AI-Tree-Search)]，[[项目网址](https://codeaimcts.github.io/)]

**【论文】**【MathPrompter: 基于大型语言模型的数学推理】[[paper](https://arxiv.org/abs/2303.05398)]

**【论文】**【MIT最新研究：利用大语言模型生成Code】[[paper](https://arxiv.org/abs/2303.05510)]，[[code](https://github.com/shunzh/Code-AI-Tree-Search)]，[[官网地址](https://codeaimcts.github.io/)]
</p>
</details>

## 语音生成

**【论文】**【Meta AI研究者推出MUSICGEN】[[paper](https://arxiv.org/pdf/2306.05284.pdf)]，[[blog](https://the-decoder.com/metas-open-source-ai-musicgen-turns-text-and-melody-into-new-songs/)]，[[demo](https://huggingface.co/spaces/facebook/MusicGen)]

【**论文**】【MetaAI发布第一个生成的人工智能语音模型Voicebox】[[blog](https://hub.baai.ac.cn/view/27492)]，[[paper](https://research.facebook.com/file/649409006862002/paper_fixed.pdf)]

【**论文**】【MetaAI开源AudioCraft：一个支持AudioGen、MusicGen等模型的音频生成开发框架】[[blog](https://mp.weixin.qq.com/s/OLLCiMqKHQJxGGR1sPA3qw)]，[[code](https://github.com/facebookresearch/audiocraft)]

**【论文】**【文字、图片一键生成逼真音效，音频界AIGC来了】[[paper](https://arxiv.org/abs/2301.12661)]，[[code](https://text-to-audio.github.io)]

【**论文**】【音乐可视化｜利用大型语言模型和文本到图像模型帮助生成「音乐迪斯科」】[[paper](https://arxiv.org/pdf/2304.08551.pdf)]，[[blog](https://hub.baai.ac.cn/view/25517)]

## 多模态生成

**【BLIP-2】**【高效训练多模态大模型（BLIP-2）】[[paper](https://arxiv.org/abs/2301.12597)]，[[code](https://github.com/salesforce/LAVIS/tree/main/projects/blip2)]，[[demo](https://huggingface.co/spaces/Salesforce/BLIP2)]，[[doc](https://huggingface.co/docs/transformers/main/en/model_doc/blip-2)]，[[fine-tuing](https://github.com/salesforce/LAVIS)]，[[hugging face spaces](https://hf.co/spaces/Salesforce/BLIP2)]

**【VisCPM】**【SOTA 开源中文多模态大模型】[[blog](https://mp.weixin.qq.com/s/Fgfbs1vV7RF6kpyk4bfIYw)]，[[code](https://github.com/OpenBMB/VisCPM)]

**【HuggingFace Transformers Agents】**【一键控制10万多个AI模型，HuggingFace给类ChatGPT模型们做了个「APP Store」】[[demo](https://huggingface.co/docs/transformers/transformers_agents)]，[[blog](https://mp.weixin.qq.com/s/8gyTqT1B4C2Da_6dmtaNiw)]

**【LLaVA】**【熔岩羊驼LLaVA来了：像GPT-4一样可以看图聊天，无需邀请码，在线可玩】[[paper](https://arxiv.org/pdf/2304.08485.pdf)]，[[introduce](https://llava-vl.github.io/)]

**【UniDiffuser】**【清华朱军团队开源UniDiffuser：首个基于Transformer的多模态扩散大模型！文图互生、改写全拿下！】[[paper](https://ml.cs.tsinghua.edu.cn/diffusion/unidiffuser.pdf)]，[[code](https://github.com/thu-ml/unidiffuser)]

<details><summary>展开更多</summary>
<p>

**【Video-LLaMA】**【人机视频对话｜Video-LLaMA多模态框架，使大型语言模型具备了理解视频内容的能力】[[paper](https://arxiv.org/abs/2306.02858)]

**【X-LLM】**【多模态语言训练大模型】[[项目地址](https://x-llm.github.io/)]，[[paper](https://arxiv.org/abs/2305.04160)]
</p>
</details>

## 欢迎共创

【👬🏻】欢迎Star ⭐️⭐️⭐️⭐️⭐️ && 提交 Pull requests 👏🏻👏🏻👏🏻

## 关于我

**个人主页**：wshzd.github.io

**微信公众号**：

![公众号二维码](https://i.postimg.cc/g092W4dB/ArronAI.jpg)

## 声明

以上部分资料来自网络整理，供大家学习参考，如有侵权，麻烦联系我删除！ 

WeChat：h18821656387
