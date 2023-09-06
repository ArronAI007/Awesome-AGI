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
- [LLM Lists](#LLM-Lists)
  - [baichuan以及扩展](#baichuan以及扩展)
  - [ChatGLM以及扩展](#ChatGLM以及扩展)
  - [LLaMA以及扩展](#LLaMA以及扩展)
- [Universal LLMs](#Universal-LLMs)
  - [Universal LLMs for Text](#Universal-LLMs-for-Text)
  - [Universal LLMs for Code](#Universal-LLMs-for-Code)
  - [Universal LLMs for Picture/Video](#Universal-LLMs-for-Picture/Video)
  - [Universal LLMs for Audio](#Universal-LLMs-for-Audio)
  - [Universal LLMs for Multimodal](#Universal-LLMs-for-Multimodal)
- [Domain LLMs](#Domain-LLMs)
  - [Domain LLMs for Law](#Domain-LLMs-for-Law)
  - [Domain LLMs for Medical](#Domain-LLMs-for-Medical)
  - [Domain LLMs for Finance](#Domain-LLMs-for-Finance)
  - [Domain LLMs for Environment](#Domain-LLMs-for-Environment)
  - [Domain LLMs for Network Security](#Domain-LLMs-for-Network-Security)
  - [Domain LLMs for Education](#Domain-LLMs-for-Education)
  - [Domain LLMs for Traffic](#Domain-LLMs-for-Traffic)
  - [Domain LLMs for Other](#Domain-LLMs-for-Other)
- [LLM训练 微调 优化 评估以及部署](#LLM训练-微调-优化-评估以及部署)
  - [LLM训练](#LLM训练)
  - [LLM微调](#LLM微调)
  - [LLM优化](#LLM优化)
  - [LLM评估](#LLM评估)
  - [LLM部署](#LLM部署)
- [LLM关键技术与应用](#LLM关键技术与应用)
  - [Prompt Engineering](#Prompt-Engineering)
  - [LLM DataSets](#LLM-DataSets)
  - [LLM RLHF](#LLM-RLHF)
  - [LLM 可控性与安全](#LLM-可控性与安全)
  - [LLM 长文本解决方案](#LLM-长文本解决方案)
  - [LLM 问答](#LLM-问答)
  - [LLM Agent](#LLM-Agent)
  - [LLM 文本检测](#LLM-文本检测)
- [AGI Paper Lists](#AGI-Paper-Lists)


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

## LLM Lists

**Here are the LLMs sorted alphabetically，except for baichuan, ChatGLM, and LLaMA**

从GPT3到ChatGPT模型的发展路线图

![ChatGPT_family](https://i.postimg.cc/GtZmmjG2/chatgpt-3.jpg)

| Model| Paper | Code |Blog |
| --- | --- | --- | --- | 
| Anima |  | [code](https://github.com/lyogavin/Anima) | [blog](https://zhuanlan.zhihu.com/p/638058537?utm_source=wechat_session&utm_medium=social&s_r=0)，[model](https://huggingface.co/lyogavin/Anima33B) | 
| Bard |  |  | [报名地址](http://bard.google.com/)，[x blog](https://twitter.com/sundarpichai/status/1638180697352593408)，[theverge blog](https://www.theverge.com/23649897/google-Bard-chatbot-search-engine) | 
| Baize | [Baize: An Open-Source Chat Model with Parameter-Efficient Tuning on Self-Chat Data](https://arxiv.org/abs/2304.01196) | [code](https://github.com/project-baize/baize/blob/main/README.md) | [blog](https://mp.weixin.qq.com/s/zxElGfclNbBwTuDG4Qrxnw) ，[demo](https://huggingface.co/spaces/project-baize/baize-lora-7B)| 
| baichuan-7b |  | [code](https://github.com/baichuan-inc/baichuan-7B)，[Model Scope](https://modelscope.cn/models/baichuan-inc/baichuan-7B/summary) | [blog](https://mp.weixin.qq.com/s/qA_E_3dUe1sSOUM87ZgHdQ)，[Hugging Face](https://huggingface.co/baichuan-inc/baichuan-7B)，[C-EVAL](https://cevalbenchmark.com/static/leaderboard_zh.html) | 
| BLOOM | [BLOOM: A 176B-Parameter Open-Access Multilingual Language Model](https://arxiv.org/abs/2211.05100) | [code](https://github.com/huggingface/transformers-bloom-inference/tree/main) | [blog](https://mp.weixin.qq.com/s/_Vj-KNxS5SfuF_h7bfMb5Q)，[huggingface](https://huggingface.co/bigscience/bloom) | 
| BiomedGPT | [BiomedGPT: A Unified and Generalist Biomedical Generative Pre-trained Transformer for Vision, Language, and Multimodal Tasks](https://arxiv.org/abs/2305.17100) |  |  | 
| Claude |  |  | [产品地址](https://www.anthropic.com/product)，[申请地址](https://www.anthropic.com/earlyaccess)，[API说明 ](https://console.anthropic.com/docs/api)，[blog](https://mp.weixin.qq.com/s/Wx5q-rEwG4sROvnewGxWrw)]，[[Claude支持100k上下文](https://mp.weixin.qq.com/s/Yu551-z14lpiFGSOfXE2Tw)，[Claude2发布](https://hub.baai.ac.cn/view/27790) | 
| Claude 2 |  | [Claude2 API](https://mp.weixin.qq.com/s/yBOJfaUw9ei0WY-64rbCJg) | [blog](https://mp.weixin.qq.com/s/_uIPPJHmiYaBFxtKXdwFbA) | 
| ChatGLM |  | [code](https://github.com/THUDM/ChatGLM-6B.git) | [blog](https://chatglm.cn/blog) | 
| ChatYuan |  |  | [blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485655&idx=1&sn=ad80d8a17d4aaab90b17a79b638c712d&chksm=ced54b33f9a2c225ce292b4e3d5725a668d0bfc9fe0be610c847b31b61714ecf75c06dac1cb5&token=447941009&lang=zh_CN#rd) | 
| Copilot X |  |  | [blog](https://github.blog/2023-03-22-github-copilot-x-the-ai-powered-developer-experience/) | 
| ColossalAI |  |  | [blog](https://mp.weixin.qq.com/s/NS4yySeYd7QUYb7CB9V0lA) | 
| CPM-Bee |  | [code](https://github.com/OpenBMB/CPM-Bee) ，[HuggingFace](https://huggingface.co/openbmb/cpm-bee-10b)| [blog](https://mp.weixin.qq.com/s/BO4cDB9KRSODZw3TvZpUAA) | 
| ChatDB | [ChatDB: Augmenting LLMs with Databases as Their Symbolic Memory](https://arxiv.org/abs/2306.03901) | [code](https://github.com/huchenxucs/ChatDB) | [blog](https://mp.weixin.qq.com/s/o3j1vNLHlJ6qTea219A4Qw)，[主页](https://chatdatabase.github.io) | 
| Dolly |  |  | [blog](https://www.databricks.com/blog/2023/03/24/hello-dolly-democratizing-magic-chatgpt-open-models.html)，[Databricks Inc地址](https://www.databricks.com) | 
| Dolly2.0 |  |  | [英文blog](https://www.databricks.com/blog/2023/04/12/dolly-first-open-commercially-viable-instruction-tuned-llm)，[中文blog](https://hub.baai.ac.cn/view/25434) | 
| DeepSpeed-Chat |  | [code](https://github.com/microsoft/DeepSpeedExamples/tree/master/applications/DeepSpeed-Chat) | [blog](https://hub.baai.ac.cn/view/25414) | 
| FrugalGPT | [FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance](https://arxiv.org/pdf/2305.05176.pdf) |  | [blog](https://www.reddit.com/r/singularity/comments/13dnfd7/frugalgpt_can_match_the_performance_of_the_best/) | 
| GPT3.5 |  |  | [OpenAI playground](https://platform.openai.com/playground) | 
| GPT4 |  |  | [OpenAI GPT4](https://openai.com/research/gpt-4)，[GPT4_System_Card中文翻译](https://github.com/ArronAI007/ChatGPT-Summary/blob/main/GPT4/Official/GPT-4_System_Card_zh.md)，[GPT4_Technical_Report中文翻译](https://github.com/ArronAI007/ChatGPT-Summary/blob/main/GPT4/Official/GPT4_Technical_Report_zh.md)，[The Ultimate GPT-4 Guide](https://doc.clickup.com/37456139/d/h/13q28b-324/e2a22b0c164b1f9) | 
| JittorLLMs |  | [code](https://github.com/Jittor/JittorLLMs) |  | 
| LLM as Controller |  |  | [blog](https://mp.weixin.qq.com/s/jeb7ugGC6zxsOsfE-w-I0A) | 
| MetaGPT |  | [code](https://github.com/geekan/MetaGPT) |  | 
| MiniGPT-4 | [paper](https://github.com/Vision-CAIR/MiniGPT-4/blob/main/MiniGPT_4.pdf) | [code](https://github.com/Vision-CAIR/MiniGPT-4) | [主页](https://minigpt-4.github.io/)，[video](https://youtu.be/__tftoxpBAw)，[dataset](https://drive.google.com/file/d/1nJXhoEcy3KTExr17I7BXqY5Y9Lx_-n-9/view)，[Demo](https://6b89c70eb5e14dca33.gradio.live/)，[Demo1](https://b2517615b965687635.gradio.live/)，[Demo2](https://c8de8ff74b6a6c6a9b.gradio.live/)，[Demo3](https://0a111504e072685259.gradio.live/)，[Demo4](https://90bc0bac96e6457e8f.gradio.live/) | 
| MOSS |  | [code](https://openlmlab.github.io/MOSS-RLHF/) | [blog](https://mp.weixin.qq.com/s/BjXtnEEVCQiPOy-_qCNM4g)，[测试链接](https://huggingface.co/spaces/togethercomputer/OpenChatKit)，[模型权重](https://huggingface.co/togethercomputer/GPT-NeoXT-Chat-Base-20B)，[数据集](https://laion.ai/blog/oig-dataset/) | 
| OpenChatKit |  | [code](https://github.com/togethercomputer/OpenChatKit) | [blog](https://mp.weixin.qq.com/s/9Av3nhJLrcYAsBW9vVGjTw)，[技术报告](https://openlmlab.github.io/MOSS-RLHF/paper/SecretsOfRLHFPart1.pdf) | 
| OpenAssistant | [OpenAssistant Conversations - Democratizing Large Language Model Alignment](https://drive.google.com/file/d/10iR5hKwFqAKhL3umx8muOWSRm7hs5FqX/view) | [code](https://github.com/LAION-AI/Open-Assistant) | [官网](https://open-assistant.io/chat)，[dataset](https://huggingface.co/datasets/OpenAssistant/oasst1)，[youtube](https://youtu.be/ddG2fM9i4Kk) | 
| Platypus | [Platypus: Quick, Cheap, and Powerful Refinement of LLMs](https://arxiv.org/abs/2308.07317) |  | [blog](https://mp.weixin.qq.com/s/yzfgITUWaCf3Wcdc6lGCQA) | 
| WebCPM | [WebCPM: Interactive Web Search for Chinese Long-form Question Answering](https://arxiv.org/abs/2305.06849) | [code](https://github.com/thunlp/WebCPM) |  [blog](https://mp.weixin.qq.com/s/m4zsF2HDFHSKc23Oq0O98w)| 

### baichuan以及扩展

| Model| Paper | Code |Blog |
| --- | --- | --- | --- | 
| baichuan-13b |  |  | [blog](https://mp.weixin.qq.com/s/Px4h2r3VIAFI5vfjXxROxg)，[百川大模型【Baichuan-13B】 多卡训练微调记录](https://mp.weixin.qq.com/s/EUZA6Lt-OcI170md9lXH1g) | 
| firefly-baichuan-7b-qlora-sft |  | [code](https://github.com/baichuan-inc/baichuan-7B) | [blog](https://mp.weixin.qq.com/s/_eTkDGG5DmxyWeiQ6DIxBw)，[Hugging Face model](https://huggingface.co/YeungNLP/firefly-baichuan-7b-qlora-sft)，[Model Scope](https://modelscope.cn/models/baichuan-inc/baichuan-7B/summary)，[C-EVAL](https://cevalbenchmark.com/static/leaderboard_zh.html) | 
| baichuan-13b-Chat |  | [code](https://github.com/percent4/document_qa_with_llm) | [blog](https://mp.weixin.qq.com/s/wStOyHPd8c7V0ug1Qebryw) | 

### ChatGLM以及扩展

| Model/Description| Paper | Code |Blog |
| --- | --- | --- | --- | 
| ChatGLM-6B源码阅读 |  |  | [blog](https://mp.weixin.qq.com/s/r7KEJmrpJZmY7KBP4veS6A) | 
| ChatGLM模型底座细节分析 |  |  | [blog](https://mp.weixin.qq.com/s/oOdD3MYtE6-sNeAmPthqLg) | 
| chatglm+langchain+互联网 |  | [code](https://github.com/LemonQu-GIT/ChatGLM-6B-Engineering/) | [blog](https://mp.weixin.qq.com/s/lO6SrEuv4-vNbL8B3G-f8g) | 
| ChatGLM_multi_gpu_zero_Tuning |  | [code](https://github.com/CSHaitao/ChatGLM_mutli_gpu_tuning) |  | 
| ChatGLM+Fastapi |  |  | [blog](https://mp.weixin.qq.com/s/5J4UA4ePVZGXJGZsBXeN8Q) | 
| ChatGLM2-6B-32K |  |  | [blog](https://mp.weixin.qq.com/s/Fkm_D26z1jrqA44B82v7Ww) | 
| ChatGLM-6b+langchain |  | [code](https://github.com/yanqiangmiffy/Chinese-LangChain) | [blog](https://mp.weixin.qq.com/s/xAsZZ_LOkr9Nj-JafSbXnA) | 
| one-shot微调chatglm-6b实践信息抽取 |  |  | [blog](https://mp.weixin.qq.com/s/l7lCbdJ9XGzLPTb3zKDAzQ) | 
| Falcon |  |  | [blog1](https://mp.weixin.qq.com/s/jbRRjG2ferhFPWsMtCaJyg)，[blog2](https://mp.weixin.qq.com/s/Vy_xWBuZU0AaaPMCIhKIyw) | 

### LLaMA以及扩展

| Model| Paper | Code |Blog |
| --- | --- | --- | --- | 
| LLaMA | [LLaMA: Open and Efficient Foundation Language Models](https://research.facebook.com/publications/llama-open-and-efficient-foundation-language-models/) | [code](https://github.com/facebookresearch/llama) | [blog1](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485822&idx=1&sn=b365d93a0a08769aef77f34069da1422&chksm=ced54a9af9a2c38cd5779284b5e9ae573846153e7dc00961dc163664a657d6a3fa5c8c14c7d2&token=447941009&lang=zh_CN#rd)，[blog2](https://mp.weixin.qq.com/s/fGNuTcYE8QI9_JKS9LcQ7w)，[详聊LLaMA大模型的技术细节](https://mp.weixin.qq.com/s/B9Ue0ihUGAFjT_X__R2u8Q) | 
| LLaMA 2 |  | [[在 Hugging Face 上玩转LLaMA 2](https://mp.weixin.qq.com/s/UnzhBJjZfPXsaSu8gNnosw)] ，[[在Colab笔记本中微调自己的Llama 2模型](https://mp.weixin.qq.com/s/pnDJaOUh_xdNdqSBl53Arw)]，[[三步上手 LLaMA2](https://mp.weixin.qq.com/s/lkRg8-rw57wDNr7FrjOSOQ)]，[[使用 Transformers 量化 Meta AI LLaMA2 中文版大模型](https://mp.weixin.qq.com/s/DEgFNAB4gwWDlQOj7-2CEg)] | [[blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247486800&idx=1&sn=9b629ca41b9f6b4feedad94363a17253&chksm=ced54eb4f9a2c7a2a5b20c182981b4323b18509f2ca8f482c2a8cdbb29bf570488bdcd280eb6&token=882149695&lang=zh_CN#rd)]，[[伯克利AI博士详解Llama 2的技术细节](https://mp.weixin.qq.com/s/Mee7sMq_bxLpIOOr91li9A)]，[[NLP社区对LLaMA2论文上半部分的讨论](https://mp.weixin.qq.com/s/SJNqjSCBX-k80_r3nmTiuA)]，[[NLP中文社区顶尖研究员们对LLaMA2论文下半部分的讨论](https://mp.weixin.qq.com/s/6k5ML3HtmvBTTCgHBZGycQ)]，[[3个最值得了解llama2开发库，助你快速搭建LLM应用](https://mp.weixin.qq.com/s/_3H6Y_NolUuxYxOo8Pl7fg)]，[[使用 Docker 快速上手中文版 LLaMA2 开源大模型](https://mp.weixin.qq.com/s/9cTNa_oya2Zj9YdDYodCvw)]，[[ Llama 2资料汇总](https://mp.weixin.qq.com/s/-01Dg9ZVfPYM4mZ4iKt8Cw) | 
| Chinese-LlaMA2 |  | [code](https://github.com/michael-wzhu/Chinese-LlaMA2) |  | 
| llama2.c |  | [code](https://github.com/karpathy/llama2.c) | [blog](https://mp.weixin.qq.com/s/VVR6N1duJM5vAU5cY9FrDQ) | 
| LLaMA-2 & Alpaca-2 |  | [code](https://github.com/ymcui/Chinese-LLaMA-Alpaca-2) | [blog](https://mp.weixin.qq.com/s/sJ_imBdHCD4NibVy58EO2w) | 
| LLaMA评测 |  |  | [blog](https://mp.weixin.qq.com/s/kImwfWWtXMmEDVOhJZ4dJg) | 
| Alpaca |  | [code](https://github.com/tatsu-lab/stanford_alpaca) | [blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485890&idx=1&sn=2d1414fc3751353c31b946b3e954a465&chksm=ced54a26f9a2c330082e8c0014c96a6d9bef62e3581875031f203268a11fad09645a75b482b0&token=447941009&lang=zh_CN#rd)，[官网](https://crfm.stanford.edu/2023/03/13/alpaca.html)，[model](https://crfm.stanford.edu/alpaca) | 
| AlpaGasus | [AlpaGasus: Training A Better Alpaca with Fewer Data](https://arxiv.org/abs/2307.08701) | [code](https://lichang-chen.github.io/AlpaGasus/) | [blog](https://mp.weixin.qq.com/s/UroGj4rIa2nOw6DookpvCQ) | 
| Alpaca-CoT |  | [code](https://github.com/PhoebusSi/Alpaca-CoT) | [官网](https://sota.jiqizhixin.com/project/alpaca-cot) | 
| BiLLa |  | [code](https://github.com/Neutralzz/BiLLa) | [blog](https://mp.weixin.qq.com/s/8KDpDC6Fkb_61gFfkcT8TQ) | 
| CaMA |  | [code](https://github.com/zjunlp/CaMA) |  | 
| ChatLLaMA |  | [code](https://github.com/nebuly-ai/nebullvm/tree/main/apps/accelerate/chatllama) |  | 
| ColossalAI |  | [code](https://github.com/hpcaitech/ColossalAI) |  | 
| ColossalChat |  | [code](https://github.com/hpcaitech/ColossalAI) | [blog](https://syncedreview.com/2023/03/29/colossalchat-an-open-source-solution-for-cloning-chatgpt-with-a-complete-rlhf-pipeline/) | 
| CAMEL |  | [code](https://github.com/starmpcc/CAMEL) | [blog](https://starmpcc.github.io/CAMEL/) | 
| 草本（原华驼） | [HuaTuo (华驼): Tuning LLaMA Model with Chinese Medical Knowledge](https://arxiv.org/pdf/2304.06975v1.pdf) | [code](https://github.com/SCIR-HI/Huatuo-Llama-Med-Chinese) | [blog1](https://mp.weixin.qq.com/s/TYpc_63qDlR6MwscxCKKhA)，[blog2](https://mp.weixin.qq.com/s/iuQANmwCS7AXQRik7HwQPg) | 
| DB-GPT |  | [code](https://github.com/csunny/DB-GPT) |  | 
| DeepSpeed-Chat |  | [code](https://github.com/microsoft/DeepSpeedExamples/tree/master/applications/DeepSpeed-Chat) | [blog](https://mp.weixin.qq.com/s/kVEBUF20u4SUsHelF39o8Q) | 
| ExpertLLaMA |  | [code](https://github.com/OFA-Sys/ExpertLLaMA) |  | 
| FreedomGPT |  |  | [官网地址](https://freedomgpt.com/) | 
| FLAN |  |  | [blog](https://mp.weixin.qq.com/s/5jEJH6UBHrk_ILbrLsd6TQ) | 
| GoGPT/GoGPT2 |  | [GoGPT code](https://github.com/yanqiangmiffy/GoGPT)，[GoGPT2 code](https://huggingface.co/golaxy/gogpt2-7b) |  | 
| Koala |  |  | [中文blog](https://hub.baai.ac.cn/view/25284)，[英文blog](https://bair.berkeley.edu/blog/2023/04/03/koala/) | 
| LLaMA-Adapter | [LLaMA-Adapter: Efficient Fine-tuning of Language Models with Zero-init Attention](https://arxiv.org/pdf/2303.16199.pdf) | [code](https://github.com/ZrrSkywalker/LLaMA-Adapter) |  | 
| LaVIN | [Cheap and Quick: Efficient Vision-Language Instruction Tuning for Large Language Models](https://arxiv.org/pdf/2305.15023.pdf) | [code](https://github.com/luogen1996/LaVIN) | [blog](https://mp.weixin.qq.com/s/MRLYk1b7VJ_b6OmJ9mzkdw) | 
| lit-llama |  | [code](https://github.com/Lightning-AI/lit-llama) |  | 
| LlamaIndex |  |  | [blog](https://mp.weixin.qq.com/s/1zvXlcGfVdxU8_Pj5f2E1g) | 
| llama.cpp |  |  | [blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485875&idx=1&sn=a4e09d31802c087f1f47bd292e380c19&chksm=ced54a57f9a2c341935b81aa27824dfa740beb7ce33289e0cb5190b5910040c0904371b7e8a0&token=447941009&lang=zh_CN#rd) | 
| llama.cpp优化版 |  |  | [blog](https://hub.baai.ac.cn/view/25307) | 
| LIMA |  |  | [blog](https://mp.weixin.qq.com/s?search_click_id=7213828026277652651-1688375605291-1083947599&__biz=MjM5ODExNDA2MA==&mid=2449961473&idx=2&sn=f080fa7b1b5657db9872724caee56519&chksm=b13c7462864bfd741f0f061b87187f2cde36b68020cfe3402717a6858563311cb642eb340989&rd2werd=1&key=ea1d916ce49bb536ce48f3aba8e329d1e1aa6fdcda4f73580b0a5adbd624721e6a974570fd6ef2823ecfa6c95e2dc09179b51e440e9179f79d0ba01f62cf795d6c697f95bf05a28904f4172b11e1ce873a2d7a0e85c74d509e916176aacb43657fd11a6de7611d65bd4ae82315835aa138a423887a219f2971c6a525679fd805&ascene=65&uin=MTkwNzA5OTA4Mw%3D%3D&devicetype=iMac+MacBookPro13%2C2+OSX+OSX+12.6.7+build(21G651)&version=13080109&nettype=WIFI&lang=zh_CN&countrycode=CN&fontScale=100&exportkey=n_ChQIAhIQ0Z339%2BFUk%2Bp0YpfMQjB%2BhxKDAgIE97dBBAEAAAAAANJyNCKr%2F3UAAAAOpnltbLcz9gKNyK89dVj0q5AacL9r2sPbvlDuJo6SwYSJ2wbfYGvc3EDxuk%2BMQS0vl8RLluMN%2Fuh9u2LxBZTHTiuQct62Bjib68qd1EvB8CgGKMV34B5%2BKHCutInPzdE9Uac6dxp0VYtd%2BJnEwljL8jf7mWZdwTkPdEZl1P0OEb3HFzczXelqDR3h7D2xEVmQuFHGIeVi7iPOHMT0AWhhGLdbrVhCKbPT3%2BX9FPOLjJSql2UD95dTmSzZKqdvOIMGpD5t%2F98jDuMUojr9HUMdvljQ1XkiJVnd%2FbqSsLS3S5t7E%2Ftjmjb9g7IxWkY%3D&acctmode=0&pass_ticket=mJ3t3nBN%2BXhKCYp9bzJSkTl%2B9PwobzvYen%2F5Kv4kpcj1Lig98d0DXbcAyqBW0vaB&wx_header=0) | 
| LongLLaMA | [Focused Transformer: Contrastive Training for Context Scaling](https://arxiv.org/pdf/2307.03170.pdf) | [code](https://github.com/CStanKonrad/long_llama)，[Hugging Face](https://huggingface.co/syzymon/long_llama_3b) | [blog](https://mp.weixin.qq.com/s/K8ExTUUXDruZGwr-PA4oFQ) | 
| OpenBuddy-LLaMA1-30B |  |  | [blog](https://mp.weixin.qq.com/s/k-ZWg0Vuud3Atn3aaXBaCQ) | 
| PaLM |  |  | [blog](https://mp.weixin.qq.com/s/MT1xCsJp98BM-lkuOKJF-A) | 
| StackLLaMA |  |  | [中文blog](https://hub.baai.ac.cn/view/25341)，[英文blog](https://huggingface.co/blog/stackllama) | 
| Vicuna |  |  | [Vicuna官网地址](https://vicuna.lmsys.org/)，[blog](https://hub.baai.ac.cn/view/25328) | 

## Universal LLMs

### Universal LLMs for Text

Some examples of **Universal LLMs for Text** as follows：

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length | Licence | Code                                                                                                                |
| --- | --- | --- | --- | --- | --- | --- |-----------------------------------------------------------------------------------------------------------------------|
| Bloom | 2022/11 | [Bloom](https://huggingface.co/bigscience/bloom) | [BLOOM: A 176B-Parameter Open-Access Multilingual Language Model](https://arxiv.org/abs/2211.05100) | 176 | [2048](https://huggingface.co/bigscience/bloom) |  [OpenRAIL-M v1](https://huggingface.co/spaces/bigcode/bigcode-model-license-agreement) |                                                                                                                      |
| Cerebras-GPT | 2023/03 | [Cerebras-GPT](https://huggingface.co/cerebras)                                           | [Cerebras-GPT: A Family of Open, Compute-efficient, Large Language Models](https://www.cerebras.net/blog/cerebras-gpt-a-family-of-open-compute-efficient-large-language-models/) ([Paper](https://arxiv.org/abs/2304.03208)) | 0.111 - 13      | [2048](https://huggingface.co/cerebras/Cerebras-GPT-13B#model-details) | Apache 2.0         | [Cerebras-GPT-1.3B](https://github.com/slai-labs/get-beam/tree/main/examples/cerebras-gpt)                            |
| Dolly        | 2023/04 | [dolly-v2-12b](https://huggingface.co/databricks/dolly-v2-12b)                            | [Free Dolly: Introducing the World's First Truly Open Instruction-Tuned LLM](https://www.databricks.com/blog/2023/04/12/dolly-first-open-commercially-viable-instruction-tuned-llm)             | 3, 7, 12     | [2048](https://github.com/databrickslabs/dolly#dolly) | MIT                |                                                                                                                       |
| DLite | 2023/05 | [dlite-v2-1_5b](https://huggingface.co/aisquared/dlite-v2-1_5b) | [Announcing DLite V2: Lightweight, Open LLMs That Can Run Anywhere](https://medium.com/ai-squared/announcing-dlite-v2-lightweight-open-llms-that-can-run-anywhere-a852e5978c6e) | 0.124 - 1.5 | [1024](https://huggingface.co/aisquared/dlite-v2-1_5b/blob/main/config.json) | Apache 2.0         | [DLite-v2-1.5B](https://github.com/slai-labs/get-beam/tree/main/examples/dlite-v2)                                    |
| FastChat-T5 | 2023/04 | [fastchat-t5-3b-v1.0](https://huggingface.co/lmsys/fastchat-t5-3b-v1.0) | [We are excited to release FastChat-T5: our compact and commercial-friendly chatbot!](https://twitter.com/lmsysorg/status/1652037026705985537?s=20) | 3 | [512](https://huggingface.co/lmsys/fastchat-t5-3b-v1.0/blob/main/config.json) | Apache 2.0 |                                                                                                                       |

**Complete Content**: please refer to [Model Survey](https://github.com/ArronAI007/Awesome-AGI/tree/main/Model-Survey/README.md)

---

### Universal LLMs for Code  

Some examples of **Universal LLMs for Code** as follows：

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length                                                                         | Licence | Code                                                                                    |
| --- | --- | --- | --- | --- |----------------------------------------------------------------------------------------| --- |-------------------------------------------------------------------------------------------|
| Baldur |  |  | [Baldur: Whole-Proof Generation and Repair with Large Language Models](https://arxiv.org/abs/2303.04910) |  |  |  |  |
| CodeGeeX |  |  | [CodeGeeX: A Pre-Trained Model for Code Generation with Multilingual Evaluations on HumanEval-X](https://arxiv.org/pdf/2303.17568.pdf) |  |  |  | [CodeGeeX Code](https://github.com/THUDM/CodeGeeX) |
| CodeGeeX2-6B |  |  | [CodeGeeX2-6B Blog](https://mp.weixin.qq.com/s/roQSCo-7s361P3TmJjjZjA) |  |  |  | [CodeGeeX2-6B Code](https://github.com/THUDM/CodeGeeX2) |
| CodeGen2 | 2023/04 | [codegen2 1B-16B](https://github.com/salesforce/CodeGen2) | [CodeGen2: Lessons for Training LLMs on Programming and Natural Languages](https://arxiv.org/abs/2305.02309) | 1 - 16 | [2048](https://arxiv.org/abs/2305.02309) | [Apache 2.0](https://github.com/salesforce/CodeGen2/blob/main/LICENSE)|                                                                                           |
| CodeGen2.5 | 2023/07 | [CodeGen2.5-7B-multi](https://huggingface.co/Salesforce/codegen25-7b-multi) | [CodeGen2.5: Small, but mighty](https://blog.salesforceairesearch.com/codegen25/) | 7 | [2048](https://huggingface.co/Salesforce/codegen25-7b-multi/blob/main/config.json) | [Apache 2.0](https://huggingface.co/Salesforce/codegen25-7b-multi/blob/main/README.md) | 
| Code Llama  | 2023 | [Inference Code for CodeLlama models]([https://ai.meta.com/resources/models-and-libraries/llama-downloads/](https://github.com/facebookresearch/codellama)) | [Code Llama: Open Foundation Models for Code](https://ai.meta.com/research/publications/code-llama-open-foundation-models-for-code/)     | 7 - 34       | [4096](https://scontent-zrh1-1.xx.fbcdn.net/v/t39.2365-6/369856151_1754812304950972_1159666448927483931_n.pdf?_nc_cat=107&ccb=1-7&_nc_sid=3c67a6&_nc_ohc=wURKmnWKaloAX-ib5XW&_nc_ht=scontent-zrh1-1.xx&oh=00_AfAN1GB2K_XwIz54PqXTr-dhilI3CfCwdQoaLMyaYEEECg&oe=64F0A68F)  | [Custom](https://github.com/facebookresearch/llama/blob/main/LICENSE) Free if you have under 700M users and you cannot use LLaMA outputs to train other LLMs besides LLaMA and its derivatives   | [HuggingChat](https://huggingface.co/blog/codellama) | 

**Complete Content**: please refer to [Model Survey](https://github.com/ArronAI007/Awesome-AGI/tree/main/Model-Survey/README.md)

---

### Universal LLMs for Picture/Video 

Some examples of **Universal LLMs for Picture/Video** as follows：

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length                                                                         | Licence | Code                                                                                    |
| --- | --- | --- | --- | --- |----------------------------------------------------------------------------------------| --- |-------------------------------------------------------------------------------------------|
| Bing Image Creator |  |  | [Bing Image Creator Blog](https://techcrunch.com/2023/03/21/microsoft-brings-openais-dall-e-image-creator-to-the-new-bing/) |  |  |  |  |
| BlenderGPT |  |  |  |  |  |  | [BlenderGPT Code](https://github.com/gd3kr/BlenderGPT)  |
| CHAMPAGNE |  |  | [CHAMPAGNE: Learning Real-world Conversation from Large-Scale Web Videos](https://arxiv.org/pdf/2303.09713.pdf)  |  |  |  | [CHAMPAGNE Code](https://seungjuhan.me/champagne) |
| CodeGen2 | 2023/04 | [codegen2 1B-16B](https://github.com/salesforce/CodeGen2) | [CodeGen2: Lessons for Training LLMs on Programming and Natural Languages](https://arxiv.org/abs/2305.02309) | 1 - 16 | [2048](https://arxiv.org/abs/2305.02309) | [Apache 2.0](https://github.com/salesforce/CodeGen2/blob/main/LICENSE)| 
| Consistency Models |  |  | [Consistency Models](https://arxiv.org/abs/2303.01469)，[Consistency Models Blog](https://hub.baai.ac.cn/view/25445) |  |  |  | [Consistency Models Code](https://github.com/openai/consistency_models) |
| ControlNet |  |  | [Adding Conditional Control to Text-to-Image Diffusion Models](https://arxiv.org/pdf/2302.05543.pdf)，[ControlNet Blog](https://mp.weixin.qq.com/s/k8rE9GrF97E-0TKJhih9kw)  |  |  |  | [ControlNet Code](https://github.com/lllyasviel/ControlNet) |

**Complete Content**: please refer to [Model Survey](https://github.com/ArronAI007/Awesome-AGI/tree/main/Model-Survey/README.md)

---  

### Universal LLMs for Audio

Some examples of **Universal LLMs for Audio** as follows：

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length                                                                         | Licence | Code                                                                                    |
| --- | --- | --- | --- | --- |----------------------------------------------------------------------------------------| --- |-------------------------------------------------------------------------------------------|
| AudioCraft |  |  | [AudioCraft Blog](https://mp.weixin.qq.com/s/OLLCiMqKHQJxGGR1sPA3qw) |  |  |  | [code](https://github.com/facebookresearch/audiocraft) |
| CodeGen2 | 2023/04 | [codegen2 1B-16B](https://github.com/salesforce/CodeGen2) | [CodeGen2: Lessons for Training LLMs on Programming and Natural Languages](https://arxiv.org/abs/2305.02309) | 1 - 16 | [2048](https://arxiv.org/abs/2305.02309) | [Apache 2.0](https://github.com/salesforce/CodeGen2/blob/main/LICENSE)| 
| Generative Disco |  |  | [Generative Disco: Text-to-Video Generation for Music Visualization](https://arxiv.org/pdf/2304.08551.pdf)，[Generative Disco Blog](https://hub.baai.ac.cn/view/25517) |  |  |  | | 
| MUSICGEN |  |  | [Simple and Controllable Music Generation](https://arxiv.org/pdf/2306.05284.pdf)，[MUSICGEN Blog](https://the-decoder.com/metas-open-source-ai-musicgen-turns-text-and-melody-into-new-songs/) |  |  |  | [demo](https://huggingface.co/spaces/facebook/MusicGen) |
| Make-An-Audio |  |  | [Make-An-Audio: Text-To-Audio Generation with Prompt-Enhanced Diffusion Models](https://arxiv.org/abs/2301.12661) |  |  |  | [Make-An-Audio Code](https://text-to-audio.github.io) |
| Voicebox |  |  | [Voicebox: Text-Guided Multilingual Universal Speech Generation at Scale](https://research.facebook.com/file/649409006862002/paper_fixed.pdf)，[Voicebox Blog](https://hub.baai.ac.cn/view/27492) | |  |  |  | |

**Complete Content**: please refer to [Model Survey](https://github.com/ArronAI007/Awesome-AGI/tree/main/Model-Survey/README.md)

---

### Universal LLMs for Multimodal 

Some examples of **Universal LLMs for Multimodal** as follows：
 
| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length                                                                         | Licence | Code                                                                                    |
| --- | --- | --- | --- | --- |----------------------------------------------------------------------------------------| --- |-------------------------------------------------------------------------------------------|
| BLIP-2 |  |  | [paper](https://arxiv.org/abs/2301.12597)，[demo](https://huggingface.co/spaces/Salesforce/BLIP2)，[doc](https://huggingface.co/docs/transformers/main/en/model_doc/blip-2) |  |  | | [code](https://github.com/salesforce/LAVIS/tree/main/projects/blip2)，[fine-tuing](https://github.com/salesforce/LAVIS)，[hugging face spaces](https://hf.co/spaces/Salesforce/BLIP2) |
| CodeGen2 | 2023/04 | [codegen2 1B-16B](https://github.com/salesforce/CodeGen2) | [CodeGen2: Lessons for Training LLMs on Programming and Natural Languages](https://arxiv.org/abs/2305.02309) | 1 - 16 | [2048](https://arxiv.org/abs/2305.02309) | [Apache 2.0](https://github.com/salesforce/CodeGen2/blob/main/LICENSE)| 
| LLaVA |  |  | [Visual Instruction Tuning](https://arxiv.org/pdf/2304.08485.pdf)，[introduce](https://llava-vl.github.io/) |  |  |  | |
| UniDiffuser |  |  | [One Transformer Fits All Distributions in Multi-Modal Diffusion at Scale](https://ml.cs.tsinghua.edu.cn/diffusion/unidiffuser.pdf) |  |  |  | [UniDiffuser Code](https://github.com/thu-ml/unidiffuser) |
| Video-LLaMA |  |  | [Video-LLaMA: An Instruction-tuned Audio-Visual Language Model for Video Understanding](https://arxiv.org/abs/2306.02858) |  |  |  | |
| VisCPM |  |  | [VisCPM Blog](https://mp.weixin.qq.com/s/Fgfbs1vV7RF6kpyk4bfIYw) |  |  |  | [VisCPM Code](https://github.com/OpenBMB/VisCPM) |
| X-LLM |  |  | [X-LLM: Bootstrapping Advanced Large Language Models by Treating Multi-Modalities as Foreign Languages](https://arxiv.org/abs/2305.04160)，[项目主页](https://x-llm.github.io/) |  |  |  | |

**Complete Content**: please refer to [Model Survey](https://github.com/ArronAI007/Awesome-AGI/tree/main/Model-Survey/README.md)

---

## Domain LLMs

### Domain LLMs for Law

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length | Licence | Code                                                                                                                |
| --- | --- | --- | --- | --- | --- | --- |-----------------------------------------------------------------------------------------------------------------------|
| CaMA |  |  | [CaMA Blog](https://mp.weixin.qq.com/s/FYWmMH2ndN5XfWvwI9dcUA) |  |  |   |  |    
| ChatLaw |  |  | [ChatLaw: Open-Source Legal Large Language Model with Integrated External Knowledge Bases](https://arxiv.org/pdf/2306.16092.pdf)，[official website](https://www.chatlaw.cloud/) |  |  |   | [ChatLaw Code](https://github.com/PKU-YuanGroup/ChatLaw) |   
| ExpertLLaMA |  |  | [ExpertLLaMA Blog](https://mp.weixin.qq.com/s/FYWmMH2ndN5XfWvwI9dcUA) |  |  |   |  |   
| LaWGPT |  |  | [LaWGPT Blog](https://mp.weixin.qq.com/s/dI839IF0hdBTAfOBUg7Pfw) |  |  |   | [LaWGPT Code](https://github.com/pengxiao-song/LaWGPT) |   
| LAW-GPT |  |  |  |  |  |   | [LAW-GPT Code](https://github.com/LiuHC0428/LAW-GPT) |   
| LexiLaw |  |  |  |  |  |   | [LexiLaw Code](https://github.com/CSHaitao/LexiLaw) |   
| lawyer-llama |  |  |  |  |  |   | [lawyer-llama Code](https://github.com/AndrewZhe/lawyer-llama) |   

---
                                                                                                           
### Domain LLMs for Medical

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length | Licence | Code                                                                                                                |
| --- | --- | --- | --- | --- | --- | --- |-----------------------------------------------------------------------------------------------------------------------|
| AD-AutoGPT |  |  | [AD-AutoGPT: An Autonomous GPT for Alzheimer's Disease Infodemiology](https://arxiv.org/abs/2306.10095) |  |  |  |  |     
| BianQue |  |  |  |  |  |  | [BianQue Code](https://github.com/scutcyr/BianQue) |   
| ChatMed |  |  |  |  |  |  | [ChatMed Code](https://github.com/michael-wzhu/ChatMed) |   
| DoctorGLM |  |  |  |  |  |  | [DoctorGLM Code](https://github.com/xionghonglin/DoctorGLM) |   
| Huatuo-Llama-Med-Chinese |  |  |  |  |  |  | [Huatuo-Llama-Med-Chinese Code](https://github.com/SCIR-HI/Huatuo-Llama-Med-Chinese) |   
| Med-PaLM |  |  | [Large language models encode clinical knowledge](https://www.nature.com/articles/s41586-023-06291-2)，[Med-PaLM Blog](https://mp.weixin.qq.com/s/Qf4Ts7UKJNzkW1Tfy-b0Zg) |  |  |  |  |   
| MedQA-ChatGLM |  |  | [主页](https://www.wangrs.co/MedQA-ChatGLM/) |  |  |  | [MedQA-ChatGLM Code](http://github.com/WangRongsheng/MedQA-ChatGLM) |   
| MedicalGPT-zh |  |  |  |  |  |  | [MedicalGPT-zh Code](https://github.com/MediaBrain-SJTU/MedicalGPT-zh) |   
| Med-ChatGLM |  |  |  |  |  |  | [Med-ChatGLM Code](https://github.com/SCIR-HI/Med-ChatGLM) |   
| PULSE |  | [PULSE](https://huggingface.co/OpenMEDLab/PULSE-7bv5) |  |  |  |  |  |   
| ShenNong-TCM-LLM |  |  |  |  |  |  | [ShenNong-TCM-LLM Code](https://github.com/michael-wzhu/ShenNong-TCM-LLM) |  
| SoulChat |  |  |  |  |  |  | [SoulChat Code](https://github.com/scutcyr/SoulChat) |    

---                                                                                                              

### Domain LLMs for Finance

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length | Licence | Code                                                                                                                |
| --- | --- | --- | --- | --- | --- | --- |-----------------------------------------------------------------------------------------------------------------------|
| FinGPT |  |  | [FinGPT: Open-Source Financial Large Language Models](https://arxiv.org/pdf/2306.06031v1.pdf)，[FinGPT Blog](https://mp.weixin.qq.com/s/A9euFin675nxGGciiX6rJQ) |  |  |  | [FinGPT Code](https://github.com/ai4finance-foundation/fingpt) |     
| FinTuo |  |  |  |  |  |  | [FinTuo Code](https://github.com/qiyuan-chen/FinTuo-Chinese-Finance-LLM) |    

--- 

### Domain LLMs for Environment

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length | Licence | Code                                                                                                                |
| --- | --- | --- | --- | --- | --- | --- |-----------------------------------------------------------------------------------------------------------------------|
| NowcastNet |  |  | [Skilful nowcasting of extreme precipitation with NowcastNet](https://www.nature.com/articles/s41586-023-06184-4)，[NowcastNet Blog](https://mp.weixin.qq.com/s/Aygm03CdA0zFNf9F3_JU5A) |  |  |  |  |   

---   

### Domain LLMs for Network Security

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length | Licence | Code                                                                                                                |
| --- | --- | --- | --- | --- | --- | --- |-----------------------------------------------------------------------------------------------------------------------|
| FraudGPT |  |  | [FraudGPT Blog](https://mp.weixin.qq.com/s/OtLNybsbxDlbVb-cs4Zk8g) |  |  |  |  |      

---

### Domain LLMs for Education

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length | Licence | Code                                                                                                                |
| --- | --- | --- | --- | --- | --- | --- |-----------------------------------------------------------------------------------------------------------------------|
| EduChat |  |  |  |  |  |  | [EduChat Code](https://github.com/icalk-nlp/EduChat) |  

---     

### Domain LLMs for Traffic

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length | Licence | Code                                                                                                                |
| --- | --- | --- | --- | --- | --- | --- |-----------------------------------------------------------------------------------------------------------------------|
| TransGPT |  |  | [TransGPT Blog](https://mp.weixin.qq.com/s/WvzyjHqI0lOGIyPlCIFNQg) |  |  |  | [TransGPT Code](https://github.com/DUOMO/TransGPT) |   

---    

### Domain LLMs for Other

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length | Licence | Code                                                                                                                |
| --- | --- | --- | --- | --- | --- | --- |-----------------------------------------------------------------------------------------------------------------------|
| Panda LLM |  |  | [Panda LLM: Training Data and Evaluation for Open-Sourced Chinese Instruction-Following Large Language Models](https://arxiv.org/pdf/2305.03025v1.pdf)，[Panda LLM Blog](https://mp.weixin.qq.com/s/IsWSPAvwgT263wjO7TYTZQ) |  |  |  | [Panda LLM Code](https://github.com/dandelionsllm/pandallm) |     
  
---

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

## LLM关键技术与应用

### Prompt Engineering

Some examples of **Prompt Engineering** as follows：

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| OpenAI 应用人工智能研究负责人Lilian Weng新博文：关于提示工程的介绍 | |  | [blog](https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/) | 
| Prompt Engineering全面自动化 | | | [blog](https://mp.weixin.qq.com/s/aj8Ls463jpF92ssn6Acwzg) | 
| ChatGPT提示示例集合 | [huggingface](https://huggingface.co/datasets/fka/awesome-chatgpt-prompts) | [ChatGPT提示示例集合](https://github.com/f/awesome-chatgpt-prompts/) | [主页](https://prompts.chat) | 
| ChatGPT Prompt工程：设计、实践与思考 | | | [blog](https://mp.weixin.qq.com/s/a8hjzZ_Rzl6pOU1PRAARJQ) | 
| 指令学习综述｜ChatGPT背后的指令学习是什么 | [Is Prompt All You Need? No. A Comprehensive and Broader View of Instruction Learning](https://arxiv.org/pdf/2303.10475v2.pdf) | | [blog](https://mp.weixin.qq.com/s/BK30JkIlshwkdHRjaRCD2g) | 

**Complete Content**: please refer to [Prompt Engineering](https://github.com/ArronAI007/Awesome-AGI/tree/main/Prompt/README.md)

### LLM DataSets

Some examples of **DataSets** as follows：

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| 一篇关于LLM指令微调的综述 | [paper](https://arxiv.org/pdf/2308.10792.pdf) |  | [blog](https://mp.weixin.qq.com/s/7pqBvgF1BWDFxP5hajmBNw) |  
| 智源研究院发布国内首个大规模、可商用中文开源指令数据集COIG：最大规模中文多任务指令集，上新千个中文数据集 | [paper](https://arxiv.org/pdf/2304.07987.pdf) |  | [blog](https://mp.weixin.qq.com/s/PvJa8dPHk6aGEv1G1B3PUw)，[COIG-PC数据下载地址](https://huggingface.co/datasets/BAAI/COIG-PC)，[COIG数据下载地址](https://huggingface.co/datasets/BAAI/COIG) |  
| 总结当前开源可用的Instruct/Prompt Tuning数据 |  |  | [blog](https://mp.weixin.qq.com/s/vDbTJo3F7sy3-NY8xxg8jw) |  
| GPT-4平替版：MiniGPT-4，支持图像理解和对话，现已开源 |  |  | [dataset](https://drive.google.com/file/d/1nJXhoEcy3KTExr17I7BXqY5Y9Lx_-n-9/view) |  
| 多模态C4：一个开放的、10亿规模的、与文本交错的图像语料库 | [paper](https://arxiv.org/abs/2304.06939) | [code](https://github.com/allenai/mmc4) |  |  
| Mind2Web: 首个全面衡量大模型上网能力的数据集 |  |  | [blog](https://mp.weixin.qq.com/s/vge4CJbBfLXFIYYyNC12Hw) |  
| 该数据集是一个由人工生成、人工注释的助理式对话语料库，覆盖了广泛的主题和写作风格，由 161443 条消息组成，分布在 66497 个会话树中，使用 35 种不同的语言。该语料库是全球众包工作的产物，涉及超过 13500 名志愿者。为了证明 OpenAssistant Conversations 数据集的有效性，该研究还提出了一个基于聊天的助手 OpenAssistant，其可以理解任务、与第三方系统交互、动态检索信息。 | [paper](https://drive.google.com/file/d/10iR5hKwFqAKhL3umx8muOWSRm7hs5FqX/view ) | [code](https://github.com/LAION-AI/Open-Assistant) | [dataset](https://huggingface.co/datasets/OpenAssistant/oasst1) |  
| 为了让Panda LLM在中文数据集上获得强大的性能，作者使用了强大的指令微调instruction-tuning技术，将LLaMA基础模型在五个开源的中文数据集进行混合训练，其中包括来自各种语言领域的1530万个样本，例如维基百科语料，新闻语料，百科问答语料，社区问答语料，和翻译语料。 |  |  | [blog](https://mp.weixin.qq.com/s/IsWSPAvwgT263wjO7TYTZQ) |  
| RedPajama开源项目｜复制超过1.2万亿个令牌的LLaMA训练数据集 |  | [code](https://github.com/togethercomputer/RedPajama-Data) | [原始blog](https://www.together.xyz/blog/redpajama)，[中文blog](https://hub.baai.ac.cn/view/25485)，[dataset](https://huggingface.co/datasets/togethercomputer/RedPajama-Data-1T) |  

**Complete Content**: please refer to [DataSets](https://github.com/ArronAI007/Awesome-AGI/tree/main/DataSets/README.md)

### LLM RLHF

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| 复现RLHF：通过开源项目 trl 搭建一个通过强化学习算法（PPO）来更新语言模型（GPT-2） |  | [code](https://github.com/HarderThenHarder/transformers_tasks/tree/main/RLHF) | [blog](https://mp.weixin.qq.com/s/1v4Uuc1YAZ9MRr1UWMH9xw) |  
| 详解大模型RLHF过程（配代码解读） |  |  | [blog](https://mp.weixin.qq.com/s/2M3igy7Ctk2LAdNQLSO5tg) |  
| 想训练ChatGPT？得先弄明白Reward Model怎么训（附源码） |  |  | [blog](https://mp.weixin.qq.com/s/1v4Uuc1YAZ9MRr1UWMH9xw) |  

### LLM 可控性与安全

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| 微软提出Control-GPT：用GPT-4实现可控文本到图像生成！ | [paper](https://arxiv.org/abs/2305.18583) |  |  [blog](https://mp.weixin.qq.com/s/U3eWeGOEt9nhW-Xwbuah9w)|  
| AIGC如何安全可控?中山大学等最新《AIGC中对隐私和安全的挑战及其补救措施：探索隐私计算、区块链潜在应用》全面阐述 | [paper](https://www.zhuanzhi.ai/paper/0dd95e1d5aae9eb2e60aabf36a107482) |  | [blog](https://mp.weixin.qq.com/s/V8QjMQSO2tX6PFx_LfLIEA) |  
| ControlVideo: 可控的Training-free的文本生成视频 | [paper](https://arxiv.org/pdf/2305.13077.pdf) | [code](https://github.com/YBYBZhang/ControlVideo) | [blog](https://mp.weixin.qq.com/s/CAH6u-MT3cFM359d5_Xpxg) |  
| 大模型切脑后变身PoisonGPT，虚假信息案例 |  | [code](https://colab.research.google.com/drive/16RPph6SobDLhisNzA5azcP-0uMGGq10R?usp=sharing&ref=blog.mithrilsecurity.io) | [blog](https://hub.baai.ac.cn/view/27736) |  
| ChatGPT羊驼家族全沦陷！CMU博士击破LLM护栏，人类毁灭计划脱口而出 | [paper](https://arxiv.org/abs/2307.15043) | [code](https://github.com/llm-attacks/llm-attacks) | [blog](https://mp.weixin.qq.com/s/298nwP98UdRNybV2Fuo6Wg) |  

### LLM 长文本解决方案

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| Transformer升级之路：一种全局长度外推的新思路 |  |  | [blog](https://mp.weixin.qq.com/s/YJ647EUfzWaJsGoMdgsguA) |  
| ChatGPT能写长篇小说了，ETH提出RecurrentGPT实现交互式超长文本生成 | [paper](https://arxiv.org/abs/2305.13304) | [code](https://github.com/aiwaves-cn/RecurrentGPT) | [blog](https://mp.weixin.qq.com/s/5UVTwSWgoz7uhozMeps3EQ)，[demo1](https://www.aiwaves.org/recurrentgpt (长篇小说写作))，[demo2](https://www.aiwaves.org/interactivefiction (交互式小说)) |  
| 语言大模型100K上下文窗口的秘诀 |  |  | [blog](https://mp.weixin.qq.com/s/_i0eQgYNSLJydv3qOTqr-Q) |  
| RoPE可能是LLM时代的Resnet |  |  | [blog](https://mp.weixin.qq.com/s/BVm1XC7r1yzOiWIrEbWg3A) |  

### LLM 问答

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| 基于大语言模型的智能问答系统应该包含哪些环节？ |  | [OpenAI 的审核函数接口 Moderation API](https://platform.openai.com/docs/guides/moderation)  | [blog](https://mp.weixin.qq.com/s/pXEyFHEv1pcqwMNhveneew) |  
| 搭建本地的chatpdf（原理，文档处理，语义搜索等） |  |  | [blog](https://mp.weixin.qq.com/s/aW7r4i54coW26RMsTdAQ5g) |  
| 如何避免大语言模型绕过知识库乱答的情况？LlamaIndex 原理与应用简介 |  |  | [官方blog](https://betterprogramming.pub/llamaindex-how-to-use-index-correctly-6f928b8944c6)，[中文blog](https://mp.weixin.qq.com/s/D6_pUv7hHZHRrKSXqo0u2w) |  
| 使用 Langchain 和 Azure OpenAI 构建一个聊天机器人来查询您的文档 |  |  | [blog](https://mp.weixin.qq.com/s/LeUuq6O5uIJPmrrYYtTaqA) |  
| 一文搞懂LangChain是什么 |  |  | [blog](https://mp.weixin.qq.com/s/vLlS17AYe4lM95KrG5sFyQ) |  

### LLM Agent

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| AutoGPT |  |  |  |  
| BabyAGI |  |  |  |  
| ChatRPA |  |  |  |  
| GPT-Engineer |  |  |  |  

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

## AGI Paper Lists

Some examples of **Paper Lists** as follows：

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| 中文大语言模型汇总：医疗、法律、金融、教育、数学微调， 目前已1.1K星 |  | [code](https://github.com/HqWu-HITCS/Awesome-Chinese-LLM) |  | 
| 大型语言模型综述全新出炉：从T5到GPT-4最全盘点，国内20余位研究者联合撰写 | [A Survey of Large Language Models](https://arxiv.org/abs/2303.18223) |  |  | 
| 大语言模型综述全新出炉：51页论文带你盘点LLM领域专业化技术 | [Domain Specialization as the Key to Make Large Language Models Disruptive: A Comprehensive Survey](https://arxiv.org/abs/2305.18703) |  | [blog](https://mp.weixin.qq.com/s/0DrowrTIgXsBhj3sYu6Aog) | 
| AIGC综述: 从GAN到ChatGPT的生成式人工智能简史 | [A Comprehensive Survey of AI-Generated Content (AIGC): A History of Generative AI from GAN to ChatGPT](https://arxiv.org/abs/2303.04226v1) |  |  | 
| 大模型综述来了！一文带你理清全球AI巨头的大模型进化史 | [Harnessing the Power of LLMs in Practice: A Survey on ChatGPT and Beyond](https://arxiv.org/pdf/2304.13712.pdf) | [code](https://github.com/Mooler0410/LLMsPracticalGuide) |  | 

**Complete Content**: please refer to [Paper Lists](https://github.com/ArronAI007/Awesome-AGI/tree/main/Paper-List/README.md)

## 欢迎共创

【👬🏻】欢迎Star ⭐️⭐️⭐️⭐️⭐️ && 提交 Pull requests 👏🏻👏🏻👏🏻

## 关于我

**个人主页**：wshzd.github.io

**微信公众号**：

![公众号二维码](https://i.postimg.cc/g092W4dB/ArronAI.jpg)

## 声明

以上部分资料来自网络整理，供大家学习参考，如有侵权，麻烦联系我删除！ 

WeChat：h18821656387
