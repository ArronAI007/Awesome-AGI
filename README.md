# Awesome-AGI

[![Anurag's GitHub stats](https://github-readme-stats.vercel.app/api?username=ArronAI007)](https://github.com/anuraghazra/github-readme-stats)

## 技术交流

欢迎加入AIGC技术交流群，与AI领域专家和各行各业的AIGC爱好者一起交流技术理论与行业信息！不管你是学术界还是工业界实践者或爱好者，都欢迎加入群体！

| 交流群二维码                    | 拉你入群(备注AIGC-github)  |
| ------------------------------- | :------------------------: |
| ![Arron](https://i.postimg.cc/PqFvY1kW/AIGC-group.jpg) | ![Arron](https://i.postimg.cc/QMqj1DGc/Arron.jpg) |

## Table of Context
- [LLM 体验效果](#LLM-体验效果)
- [LLM Lists](#LLM-Lists)
  - [baichuan and extensions](#baichuan-and-extensions)
  - [ChatGLM and extensions](#ChatGLM-and-extensions)
  - [LLaMA and extensions](#LLaMA-and-extensions)
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
- [LLM Deployment](#LLM-Deployment)
- [LLM Agent](#LLM-Agent)
- [AGI Paper Lists](#AGI-Paper-Lists)

## LLM 体验效果

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

从GPT3到ChatGPT模型的发展路线图

![ChatGPT_family](https://i.postimg.cc/GtZmmjG2/chatgpt-3.jpg)

### baichuan and extensions

| Model| Paper | Code |Blog |
| --- | --- | --- | --- | 
| baichuan-7b |  | [code](https://github.com/baichuan-inc/baichuan-7B)，[Model Scope](https://modelscope.cn/models/baichuan-inc/baichuan-7B/summary) | [blog](https://mp.weixin.qq.com/s/qA_E_3dUe1sSOUM87ZgHdQ)，[Hugging Face](https://huggingface.co/baichuan-inc/baichuan-7B)，[C-EVAL](https://cevalbenchmark.com/static/leaderboard_zh.html) | 
| baichuan-13b |  |  | [blog](https://mp.weixin.qq.com/s/Px4h2r3VIAFI5vfjXxROxg)，[百川大模型【Baichuan-13B】 多卡训练微调记录](https://mp.weixin.qq.com/s/EUZA6Lt-OcI170md9lXH1g) | 
| firefly-baichuan-7b-qlora-sft |  | [code](https://github.com/baichuan-inc/baichuan-7B) | [blog](https://mp.weixin.qq.com/s/_eTkDGG5DmxyWeiQ6DIxBw)，[Hugging Face model](https://huggingface.co/YeungNLP/firefly-baichuan-7b-qlora-sft)，[Model Scope](https://modelscope.cn/models/baichuan-inc/baichuan-7B/summary)，[C-EVAL](https://cevalbenchmark.com/static/leaderboard_zh.html) | 
| baichuan-13b-Chat |  | [code](https://github.com/percent4/document_qa_with_llm) | [blog](https://mp.weixin.qq.com/s/wStOyHPd8c7V0ug1Qebryw) | 

### ChatGLM and extensions

| Model/Description| Paper | Code |Blog |
| --- | --- | --- | --- | 
| ChatGLM |  | [code](https://github.com/THUDM/ChatGLM-6B.git) | [blog](https://chatglm.cn/blog) | 
| ChatGLM-6B源码阅读 |  |  | [blog](https://mp.weixin.qq.com/s/r7KEJmrpJZmY7KBP4veS6A) | 
| ChatGLM模型底座细节分析 |  |  | [blog](https://mp.weixin.qq.com/s/oOdD3MYtE6-sNeAmPthqLg) | 
| chatglm+langchain+互联网 |  | [code](https://github.com/LemonQu-GIT/ChatGLM-6B-Engineering/) | [blog](https://mp.weixin.qq.com/s/lO6SrEuv4-vNbL8B3G-f8g) | 
| ChatGLM_multi_gpu_zero_Tuning |  | [code](https://github.com/CSHaitao/ChatGLM_mutli_gpu_tuning) |  | 
| ChatGLM+Fastapi |  |  | [blog](https://mp.weixin.qq.com/s/5J4UA4ePVZGXJGZsBXeN8Q) | 
| ChatGLM2-6B-32K |  |  | [blog](https://mp.weixin.qq.com/s/Fkm_D26z1jrqA44B82v7Ww) | 
| ChatGLM-6b+langchain |  | [code](https://github.com/yanqiangmiffy/Chinese-LangChain) | [blog](https://mp.weixin.qq.com/s/xAsZZ_LOkr9Nj-JafSbXnA) | 
| one-shot微调chatglm-6b实践信息抽取 |  |  | [blog](https://mp.weixin.qq.com/s/l7lCbdJ9XGzLPTb3zKDAzQ) | 
| Falcon |  |  | [blog1](https://mp.weixin.qq.com/s/jbRRjG2ferhFPWsMtCaJyg)，[blog2](https://mp.weixin.qq.com/s/Vy_xWBuZU0AaaPMCIhKIyw) | 

### LLaMA and extensions

| Target Model | Source Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length | Code                                                                                                                |
| --- | --- | --- | --- |--- | --- | --- |--- | 
| LLaMA | |  |  | [LLaMA: Open and Efficient Foundation Language Models](https://research.facebook.com/publications/llama-open-and-efficient-foundation-language-models/)，[blog1](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485822&idx=1&sn=b365d93a0a08769aef77f34069da1422&chksm=ced54a9af9a2c38cd5779284b5e9ae573846153e7dc00961dc163664a657d6a3fa5c8c14c7d2&token=447941009&lang=zh_CN#rd)，[blog2](https://mp.weixin.qq.com/s/fGNuTcYE8QI9_JKS9LcQ7w)，[详聊LLaMA大模型的技术细节](https://mp.weixin.qq.com/s/B9Ue0ihUGAFjT_X__R2u8Q) | 7，13，33，65 |  | [LLaMA Code](https://github.com/facebookresearch/llama) |
| LLaMA 2 |  | | [[在 Hugging Face 上玩转LLaMA 2](https://mp.weixin.qq.com/s/UnzhBJjZfPXsaSu8gNnosw)] ，[[在Colab笔记本中微调自己的Llama 2模型](https://mp.weixin.qq.com/s/pnDJaOUh_xdNdqSBl53Arw)]，[[三步上手 LLaMA2](https://mp.weixin.qq.com/s/lkRg8-rw57wDNr7FrjOSOQ)]，[[使用 Transformers 量化 Meta AI LLaMA2 中文版大模型](https://mp.weixin.qq.com/s/DEgFNAB4gwWDlQOj7-2CEg)] | [[blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247486800&idx=1&sn=9b629ca41b9f6b4feedad94363a17253&chksm=ced54eb4f9a2c7a2a5b20c182981b4323b18509f2ca8f482c2a8cdbb29bf570488bdcd280eb6&token=882149695&lang=zh_CN#rd)]，[[伯克利AI博士详解Llama 2的技术细节](https://mp.weixin.qq.com/s/Mee7sMq_bxLpIOOr91li9A)]，[[NLP社区对LLaMA2论文上半部分的讨论](https://mp.weixin.qq.com/s/SJNqjSCBX-k80_r3nmTiuA)]，[[NLP中文社区顶尖研究员们对LLaMA2论文下半部分的讨论](https://mp.weixin.qq.com/s/6k5ML3HtmvBTTCgHBZGycQ)]，[[3个最值得了解llama2开发库，助你快速搭建LLM应用](https://mp.weixin.qq.com/s/_3H6Y_NolUuxYxOo8Pl7fg)]，[[使用 Docker 快速上手中文版 LLaMA2 开源大模型](https://mp.weixin.qq.com/s/9cTNa_oya2Zj9YdDYodCvw)]，[[ Llama 2资料汇总](https://mp.weixin.qq.com/s/-01Dg9ZVfPYM4mZ4iKt8Cw) |  |  |  |
| Alpaca |  |  |  | [blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485890&idx=1&sn=2d1414fc3751353c31b946b3e954a465&chksm=ced54a26f9a2c330082e8c0014c96a6d9bef62e3581875031f203268a11fad09645a75b482b0&token=447941009&lang=zh_CN#rd)，[官网](https://crfm.stanford.edu/2023/03/13/alpaca.html)，[model](https://crfm.stanford.edu/alpaca) |  |  | [Alpaca Code](https://github.com/tatsu-lab/stanford_alpaca) |
| AlpaGasus |  | [AlpaGasus: Training A Better Alpaca with Fewer Data](https://arxiv.org/abs/2307.08701) | [code](https://lichang-chen.github.io/AlpaGasus/) | [blog](https://mp.weixin.qq.com/s/UroGj4rIa2nOw6DookpvCQ) |  |  |  |
| Alpaca-CoT |  |  | [code](https://github.com/PhoebusSi/Alpaca-CoT) | [官网](https://sota.jiqizhixin.com/project/alpaca-cot) |  |  |  |
| Anima | guanaco-33B |  | [Anima Code](https://github.com/lyogavin/Anima)，[HuggingFace model](https://huggingface.co/lyogavin/Anima33B) | [Anima Blog](https://zhuanlan.zhihu.com/p/638058537?utm_source=wechat_session&utm_medium=social&s_r=0) |  |  |  |
| Baize |   | [Baize: An Open-Source Chat Model with Parameter-Efficient Tuning on Self-Chat Data](https://arxiv.org/abs/2304.01196) | [code](https://github.com/project-baize/baize/blob/main/README.md) | [blog](https://mp.weixin.qq.com/s/zxElGfclNbBwTuDG4Qrxnw) ，[demo](https://huggingface.co/spaces/project-baize/baize-lora-7B)|  |  |  |
| BiLLa |  |  | [code](https://github.com/Neutralzz/BiLLa) | [blog](https://mp.weixin.qq.com/s/8KDpDC6Fkb_61gFfkcT8TQ) |  |  |  |
| CaMA |  |  | [code](https://github.com/zjunlp/CaMA) |  |  |  |  |
| ChatLLaMA |  |  | [code](https://github.com/nebuly-ai/nebullvm/tree/main/apps/accelerate/chatllama) |  |  |  |  |
| Chinese-LlaMA2 |  |  | [code](https://github.com/michael-wzhu/Chinese-LlaMA2) |  |  |  |  |
| ColossalAI |  |  | [code](https://github.com/hpcaitech/ColossalAI) |  |  |  |  |
| ColossalChat |  |  | [code](https://github.com/hpcaitech/ColossalAI) | [blog](https://syncedreview.com/2023/03/29/colossalchat-an-open-source-solution-for-cloning-chatgpt-with-a-complete-rlhf-pipeline/) |  |  |  |
| CAMEL |  |  | [code](https://github.com/starmpcc/CAMEL) | [blog](https://starmpcc.github.io/CAMEL/) |  |  |  |
| 草本（原华驼） |   | [HuaTuo (华驼): Tuning LLaMA Model with Chinese Medical Knowledge](https://arxiv.org/pdf/2304.06975v1.pdf) | [code](https://github.com/SCIR-HI/Huatuo-Llama-Med-Chinese) | [blog1](https://mp.weixin.qq.com/s/TYpc_63qDlR6MwscxCKKhA)，[blog2](https://mp.weixin.qq.com/s/iuQANmwCS7AXQRik7HwQPg) |  |  |  |
| DB-GPT |  |  | [code](https://github.com/csunny/DB-GPT) |  |  |  |  |
| DeepSpeed-Chat |  |  | [code](https://github.com/microsoft/DeepSpeedExamples/tree/master/applications/DeepSpeed-Chat) | [blog](https://mp.weixin.qq.com/s/kVEBUF20u4SUsHelF39o8Q) |  |  |  |
| ExpertLLaMA |  |  | [code](https://github.com/OFA-Sys/ExpertLLaMA) |  |  |  |  |
| FreedomGPT |  |  |  | [官网地址](https://freedomgpt.com/) |  |  |  |
| FLAN |  |  |  | [blog](https://mp.weixin.qq.com/s/5jEJH6UBHrk_ILbrLsd6TQ) |  |  |  |
| GoGPT/GoGPT2 |  |  | [GoGPT code](https://github.com/yanqiangmiffy/GoGPT)，[GoGPT2 code](https://huggingface.co/golaxy/gogpt2-7b) |  |  |  |  |
| guanaco | LLaMA |  |  |  |  |  |  |
| Koala |  |  |  | [中文blog](https://hub.baai.ac.cn/view/25284)，[英文blog](https://bair.berkeley.edu/blog/2023/04/03/koala/) |  |  |  |
| LLaMA-Adapter |  | [LLaMA-Adapter: Efficient Fine-tuning of Language Models with Zero-init Attention](https://arxiv.org/pdf/2303.16199.pdf) | [code](https://github.com/ZrrSkywalker/LLaMA-Adapter) |  |  |  |  |
| LaVIN |  | [Cheap and Quick: Efficient Vision-Language Instruction Tuning for Large Language Models](https://arxiv.org/pdf/2305.15023.pdf) | [code](https://github.com/luogen1996/LaVIN) | [blog](https://mp.weixin.qq.com/s/MRLYk1b7VJ_b6OmJ9mzkdw) |  |  |  |
| lit-llama |  |  | [code](https://github.com/Lightning-AI/lit-llama) |  |  |  |  |
| LlamaIndex |  |  |  | [blog](https://mp.weixin.qq.com/s/1zvXlcGfVdxU8_Pj5f2E1g) |  |  |  |
| llama.cpp |  |  |  | [blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485875&idx=1&sn=a4e09d31802c087f1f47bd292e380c19&chksm=ced54a57f9a2c341935b81aa27824dfa740beb7ce33289e0cb5190b5910040c0904371b7e8a0&token=447941009&lang=zh_CN#rd) |  |  |  |
| llama.cpp优化版 |  |  |  | [blog](https://hub.baai.ac.cn/view/25307) |  |  |  |
| llama2.c |  |  | [code](https://github.com/karpathy/llama2.c) | [blog](https://mp.weixin.qq.com/s/VVR6N1duJM5vAU5cY9FrDQ) |  |  |  |
| LLaMA-2 & Alpaca-2 |  |  | [code](https://github.com/ymcui/Chinese-LLaMA-Alpaca-2) | [blog](https://mp.weixin.qq.com/s/sJ_imBdHCD4NibVy58EO2w) |  |  |  |
| LIMA |  |  |  | [blog](https://mp.weixin.qq.com/s?search_click_id=7213828026277652651-1688375605291-1083947599&__biz=MjM5ODExNDA2MA==&mid=2449961473&idx=2&sn=f080fa7b1b5657db9872724caee56519&chksm=b13c7462864bfd741f0f061b87187f2cde36b68020cfe3402717a6858563311cb642eb340989&rd2werd=1&key=ea1d916ce49bb536ce48f3aba8e329d1e1aa6fdcda4f73580b0a5adbd624721e6a974570fd6ef2823ecfa6c95e2dc09179b51e440e9179f79d0ba01f62cf795d6c697f95bf05a28904f4172b11e1ce873a2d7a0e85c74d509e916176aacb43657fd11a6de7611d65bd4ae82315835aa138a423887a219f2971c6a525679fd805&ascene=65&uin=MTkwNzA5OTA4Mw%3D%3D&devicetype=iMac+MacBookPro13%2C2+OSX+OSX+12.6.7+build(21G651)&version=13080109&nettype=WIFI&lang=zh_CN&countrycode=CN&fontScale=100&exportkey=n_ChQIAhIQ0Z339%2BFUk%2Bp0YpfMQjB%2BhxKDAgIE97dBBAEAAAAAANJyNCKr%2F3UAAAAOpnltbLcz9gKNyK89dVj0q5AacL9r2sPbvlDuJo6SwYSJ2wbfYGvc3EDxuk%2BMQS0vl8RLluMN%2Fuh9u2LxBZTHTiuQct62Bjib68qd1EvB8CgGKMV34B5%2BKHCutInPzdE9Uac6dxp0VYtd%2BJnEwljL8jf7mWZdwTkPdEZl1P0OEb3HFzczXelqDR3h7D2xEVmQuFHGIeVi7iPOHMT0AWhhGLdbrVhCKbPT3%2BX9FPOLjJSql2UD95dTmSzZKqdvOIMGpD5t%2F98jDuMUojr9HUMdvljQ1XkiJVnd%2FbqSsLS3S5t7E%2Ftjmjb9g7IxWkY%3D&acctmode=0&pass_ticket=mJ3t3nBN%2BXhKCYp9bzJSkTl%2B9PwobzvYen%2F5Kv4kpcj1Lig98d0DXbcAyqBW0vaB&wx_header=0) |  |  |  |
| LongLLaMA | | [Focused Transformer: Contrastive Training for Context Scaling](https://arxiv.org/pdf/2307.03170.pdf) | [code](https://github.com/CStanKonrad/long_llama)，[Hugging Face](https://huggingface.co/syzymon/long_llama_3b) | [blog](https://mp.weixin.qq.com/s/K8ExTUUXDruZGwr-PA4oFQ) |  |  |  |
| OpenBuddy-LLaMA1-30B |  |  |  | [blog](https://mp.weixin.qq.com/s/k-ZWg0Vuud3Atn3aaXBaCQ) |  |  |  |
| PaLM |  |  |  | [blog](https://mp.weixin.qq.com/s/MT1xCsJp98BM-lkuOKJF-A) |  |  |  |
| Platypus | LLaMA2 | [Platypus: Quick, Cheap, and Powerful Refinement of LLMs](https://arxiv.org/abs/2308.07317) |  | [blog](https://mp.weixin.qq.com/s/yzfgITUWaCf3Wcdc6lGCQA) |  |  |  |
| StackLLaMA |  |  |  | [中文blog](https://hub.baai.ac.cn/view/25341)，[英文blog](https://huggingface.co/blog/stackllama) |  |  |  |
| Vicuna |  |  |  | [Vicuna官网地址](https://vicuna.lmsys.org/)，[blog](https://hub.baai.ac.cn/view/25328) |  |  |  |

## Universal LLMs

### Universal LLMs for Text

Some examples of **Universal LLMs for Text** as follows：

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length | Licence | Code                                                                                                                |
| --- | --- | --- | --- | --- | --- | --- |-----------------------------------------------------------------------------------------------------------------------|
| Bard | 2023/03 |  | [Bard homepage](http://bard.google.com/)，[theverge blog](https://www.theverge.com/23649897/google-Bard-chatbot-search-engine) | | | | |
| Bloom | 2022/11 | [Bloom](https://huggingface.co/bigscience/bloom) | [BLOOM: A 176B-Parameter Open-Access Multilingual Language Model](https://arxiv.org/abs/2211.05100) | 176 | [2048](https://huggingface.co/bigscience/bloom) |  [OpenRAIL-M v1](https://huggingface.co/spaces/bigcode/bigcode-model-license-agreement) | [Bloom Code](https://github.com/huggingface/transformers-bloom-inference/tree/main)                                                                                                                     |
| Cerebras-GPT | 2023/03 | [Cerebras-GPT](https://huggingface.co/cerebras)                                           | [Cerebras-GPT: A Family of Open, Compute-efficient, Large Language Models](https://www.cerebras.net/blog/cerebras-gpt-a-family-of-open-compute-efficient-large-language-models/) ([Paper](https://arxiv.org/abs/2304.03208)) | 0.111 - 13      | [2048](https://huggingface.co/cerebras/Cerebras-GPT-13B#model-details) | Apache 2.0         | [Cerebras-GPT-1.3B](https://github.com/slai-labs/get-beam/tree/main/examples/cerebras-gpt)                            |
| ChatYuan |  | [ChatYuan-large-v1](https://huggingface.co/ClueAI/ChatYuan-large-v1)  | [ChatYuan Blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485655&idx=1&sn=ad80d8a17d4aaab90b17a79b638c712d&chksm=ced54b33f9a2c225ce292b4e3d5725a668d0bfc9fe0be610c847b31b61714ecf75c06dac1cb5&token=447941009&lang=zh_CN#rd) | |  |  | [ChatYuan Code](https://github.com/clue-ai/ChatYuan) |
| ChatDB |  |  | [ChatDB: Augmenting LLMs with Databases as Their Symbolic Memory](https://arxiv.org/abs/2306.03901)，[blog](https://mp.weixin.qq.com/s/o3j1vNLHlJ6qTea219A4Qw)，[主页](https://chatdatabase.github.io) |  |  |   | [ChatDB Code](https://github.com/huchenxucs/ChatDB) |
| Claude |  |  | [产品地址](https://www.anthropic.com/product)，[申请地址](https://www.anthropic.com/earlyaccess)，[blog](https://mp.weixin.qq.com/s/Wx5q-rEwG4sROvnewGxWrw)，[Claude支持100k上下文](https://mp.weixin.qq.com/s/Yu551-z14lpiFGSOfXE2Tw) | 
| Claude 2 |  |  | [Model Card and Evaluations for Claude Models](https://www-files.anthropic.com/production/images/Model-Card-Claude-2.pdf) |
| ColossalAI |  |  | [ColossalAI SFT Blog](https://mp.weixin.qq.com/s/NS4yySeYd7QUYb7CB9V0lA) |  |  |  | [ColossalAI Code](https://github.com/hpcaitech/ColossalAI/tree/main/applications/Chat) | 
| CPM-Bee |  |  [CPM-Bee-10B](https://huggingface.co/openbmb/cpm-bee-10b)| [CPM-Bee Blog](https://mp.weixin.qq.com/s/BO4cDB9KRSODZw3TvZpUAA) |  |  |  | [CPM-Bee Code](https://github.com/OpenBMB/CPM-Bee) |
| Dolly        | 2023/04 | [dolly-v2-12b](https://huggingface.co/databricks/dolly-v2-12b)                            |  [Hello Dolly: Democratizing the magic of ChatGPT with open models](https://www.databricks.com/blog/2023/03/24/hello-dolly-democratizing-magic-chatgpt-open-models.html)，[Databricks Inc主页](https://www.databricks.com)            | 3, 7, 12     | [2048](https://github.com/databrickslabs/dolly#dolly) | MIT                |                                                                                                                       |
| Dolly2.0 |  |  | [Free Dolly: Introducing the World's First Truly Open Instruction-Tuned LLM](https://www.databricks.com/blog/2023/04/12/dolly-first-open-commercially-viable-instruction-tuned-llm)，[中文blog](https://hub.baai.ac.cn/view/25434) | 
| DeepSpeed-Chat |  | [code](https://github.com/microsoft/DeepSpeedExamples/tree/master/applications/DeepSpeed-Chat) | [blog](https://hub.baai.ac.cn/view/25414) | 
| DLite | 2023/05 | [dlite-v2-1_5b](https://huggingface.co/aisquared/dlite-v2-1_5b) | [Announcing DLite V2: Lightweight, Open LLMs That Can Run Anywhere](https://medium.com/ai-squared/announcing-dlite-v2-lightweight-open-llms-that-can-run-anywhere-a852e5978c6e) | 0.124 - 1.5 | [1024](https://huggingface.co/aisquared/dlite-v2-1_5b/blob/main/config.json) | Apache 2.0         | [DLite-v2-1.5B](https://github.com/slai-labs/get-beam/tree/main/examples/dlite-v2)                                    |
| FastChat-T5 | 2023/04 | [fastchat-t5-3b-v1.0](https://huggingface.co/lmsys/fastchat-t5-3b-v1.0) | [We are excited to release FastChat-T5: our compact and commercial-friendly chatbot!](https://twitter.com/lmsysorg/status/1652037026705985537?s=20) | 3 | [512](https://huggingface.co/lmsys/fastchat-t5-3b-v1.0/blob/main/config.json) | Apache 2.0 |                                                                                                                       |
| GPT3.5 |  |  | [OpenAI playground](https://platform.openai.com/playground) | 
| MiniGPT-4 |  |  | [MiniGPT-4 Paper](https://github.com/Vision-CAIR/MiniGPT-4/blob/main/MiniGPT_4.pdf)，[主页](https://minigpt-4.github.io/)，[video](https://youtu.be/__tftoxpBAw)，[dataset](https://drive.google.com/file/d/1nJXhoEcy3KTExr17I7BXqY5Y9Lx_-n-9/view)，[Demo](https://6b89c70eb5e14dca33.gradio.live/)，[Demo1](https://b2517615b965687635.gradio.live/)，[Demo2](https://c8de8ff74b6a6c6a9b.gradio.live/)，[Demo3](https://0a111504e072685259.gradio.live/)，[Demo4](https://90bc0bac96e6457e8f.gradio.live/) |  |  |  | [MiniGPT-4 Code](https://github.com/Vision-CAIR/MiniGPT-4) |
| MOSS |  |  | [Secrets of RLHF in Large Language Models Part I: PPO](https://arxiv.org/abs/2307.04964)，[MOSS Blog](https://mp.weixin.qq.com/s/BjXtnEEVCQiPOy-_qCNM4g)，[数据集](https://laion.ai/blog/oig-dataset/) |  |  |  | [MOSS Code](https://openlmlab.github.io/MOSS-RLHF/) |
| OpenAssistant |  |  | [OpenAssistant Conversations - Democratizing Large Language Model Alignment](https://drive.google.com/file/d/10iR5hKwFqAKhL3umx8muOWSRm7hs5FqX/view)，[官网](https://open-assistant.io/chat)，[dataset](https://huggingface.co/datasets/OpenAssistant/oasst1)，[youtube](https://youtu.be/ddG2fM9i4Kk) |  |  |  | [OpenAssistant Code](https://github.com/LAION-AI/Open-Assistant) |
| OpenChatKit |  | | [OpenChatKit Blog](https://mp.weixin.qq.com/s/9Av3nhJLrcYAsBW9vVGjTw)，[OpenChatKit Chat](https://huggingface.co/spaces/togethercomputer/OpenChatKit)  |  |  |  | [OpenChatKit Code](https://github.com/togethercomputer/OpenChatKit) |
| WebCPM |  |  | [WebCPM: Interactive Web Search for Chinese Long-form Question Answering](https://arxiv.org/abs/2305.06849)，[WebCPM Blog](https://mp.weixin.qq.com/s/m4zsF2HDFHSKc23Oq0O98w) |  |  |  | [WebCPM Code](https://github.com/thunlp/WebCPM) |

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
| Copilot X |  |  | [Copilot X Blog](https://github.blog/2023-03-22-github-copilot-x-the-ai-powered-developer-experience/) |  |  |  | [Copilot X Code](https://github.com/features/copilot/) |

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
| GPT4 |  |  | [OpenAI GPT4](https://openai.com/research/gpt-4)，[GPT4_System_Card中文翻译](https://github.com/ArronAI007/ChatGPT-Summary/blob/main/GPT4/Official/GPT-4_System_Card_zh.md)，[GPT4_Technical_Report中文翻译](https://github.com/ArronAI007/ChatGPT-Summary/blob/main/GPT4/Official/GPT4_Technical_Report_zh.md)，[The Ultimate GPT-4 Guide](https://doc.clickup.com/37456139/d/h/13q28b-324/e2a22b0c164b1f9) | 
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
| BiomedGPT |  |  | [BiomedGPT: A Unified and Generalist Biomedical Generative Pre-trained Transformer for Vision, Language, and Multimodal Tasks](https://arxiv.org/abs/2305.17100) |  |  |  |  |
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

## LLM Deployment

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| BentoML |  | [BentoML Code](https://github.com/bentoml/BentoML) |  |  
| CLIP-API-service |  |  |  |  
| CTranslate2 |  |  |  |  
| DeepSpeed-MII |  |  |  |  
| LightLLM |  |  |  |  
| LMDeploy |  |  |  |  
| MLC LLM |  |  |  |  
| OneDiffusion |  |  |  |  
| OpenLLM |  |  |  |  
| Ray Serve |  |  |  |  

## LLM Agent

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| AgentGPT |  | [AgentGPT Code](https://github.com/reworkd/AgentGPT) | [AgentGPT Chat](https://agentgpt.reworkd.ai/zh)，[AgentGPT docs](https://docs.reworkd.ai/introduction) |  
| AI Legion |  | [AI Legion Chat](https://github.com/eumemic/ai-legion) |  |  
| AutoGPT |  | [AutoGPT Code](https://github.com/Significant-Gravitas/Auto-GPT) | [AutoGPT docs](https://docs.agpt.co/setup/) ，[AutoGPT blog](https://generativeai.pub/complete-guide-to-setup-autogpt-revolutionize-your-task-automation-with-gpt-4-39eda5a85821?gi=ea5c40bac6fd) |  
| BabyAGI |  | [BabyAGI Code](https://github.com/yoheinakajima/babyagi) | [BabyAGI docs](https://babyagi.org/) |  
| CAMEL |  | [CAMEL Code](https://github.com/camel-ai/camel) | [CAMEL Chat](http://agents.camel-ai.org/)，[CAMEL docs](https://www.camel-ai.org/) |  
| Do Anything Machine |  |  | [Do Anything Machine Chat](https://www.doanythingmachine.com/) |  
| Generative Agents | [Generative Agents: Interactive Simulacra of Human Behavior](https://arxiv.org/abs/2304.03442) | [GPTRPG Code](https://github.com/dzoba/gptrpg) |  | 
| Godmode |  |  | [Godmode Chat](https://godmode.space/) |  
| GPT-Engineer |  | [GPT-Engineer Code](https://github.com/AntonOsika/gpt-engineer) |  |   
| HuggingGPT |  | [HuggingGPT Code](https://github.com/microsoft/JARVIS) | [HuggingGPT Chat](https://huggingface.co/spaces/microsoft/HuggingGPT) |  
| MetaGPT |  | [MetaGPT Code](https://github.com/geekan/MetaGPT) |  | 
| NexusGPT |  |  | [NexusGPT Chat](https://nexus.snikpic.io/) |  
| Toolformer | [Toolformer: Language Models Can Teach Themselves to Use Tools](https://arxiv.org/pdf/2302.04761.pdf) |  | [Toolformer blog](https://www.sensorexpert.com.cn/article/194585.html) |  

## AGI Paper Lists

Some examples of **Paper Lists** as follows：

| Description| Paper | Code | Blog |
| --- | --- | --- | --- |  
| 中文大语言模型汇总：医疗、法律、金融、教育、数学微调， 目前已1.1K星 |  | [code](https://github.com/HqWu-HITCS/Awesome-Chinese-LLM) |  | 
| 大型语言模型综述全新出炉：从T5到GPT-4最全盘点，国内20余位研究者联合撰写 | [A Survey of Large Language Models](https://arxiv.org/abs/2303.18223) |  |  | 
| 大语言模型综述全新出炉：51页论文带你盘点LLM领域专业化技术 | [Domain Specialization as the Key to Make Large Language Models Disruptive: A Comprehensive Survey](https://arxiv.org/abs/2305.18703) |  | [blog](https://mp.weixin.qq.com/s/0DrowrTIgXsBhj3sYu6Aog) | 
| AIGC综述: 从GAN到ChatGPT的生成式人工智能简史 | [A Comprehensive Survey of AI-Generated Content (AIGC): A History of Generative AI from GAN to ChatGPT](https://arxiv.org/abs/2303.04226v1) |  |  | 
| 大模型综述来了！一文带你理清全球AI巨头的大模型进化史 | [Harnessing the Power of LLMs in Practice: A Survey on ChatGPT and Beyond](https://arxiv.org/pdf/2304.13712.pdf) | [code](https://github.com/Mooler0410/LLMsPracticalGuide) |  | 

**Complete Content**: please refer to [Paper Lists](https://github.com/ArronAI007/Awesome-AGI/tree/main/Paper-Lists/README.md)

## 欢迎共创

【👬🏻】欢迎Star ⭐️⭐️⭐️⭐️⭐️ && 提交 Pull requests 👏🏻👏🏻👏🏻

## 关于我

**个人主页**：wshzd.github.io

**微信公众号**：

![公众号二维码](https://i.postimg.cc/g092W4dB/ArronAI.jpg)

## 声明

以上部分资料来自网络整理，供大家学习参考，如有侵权，麻烦联系我删除！ 

WeChat：h18821656387
