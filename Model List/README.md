# Model List

Model List mainly includes Universal LLMs and Domain LLMs, In terms of Universal LLMs， including text generation model, image and video generation model, code generation model, music generation model, multimodal model；In terms of Domain LLMs， including law, medical, finance, environment, network security, education, Traffic and so on.

从GPT3到ChatGPT模型的发展路线图

![ChatGPT_family](https://i.postimg.cc/GtZmmjG2/chatgpt-3.jpg)

## baichuan Alternatives

| Target Model | Release Date | Source Model | Optimization | Checkpoints | Paper/Blog | Params (B) | Context Length | Code | Tokens | Tokenizer | Vocab size | Position Embedding | Layer Normalization | Activation Function | Attention |
| --- | --- | --- | --- |--- | --- | --- |--- | --- | --- | --- | --- | --- | --- | --- | --- | 
| baichuan-7b | 2023/6/15 |  |  | [Model Scope](https://modelscope.cn/models/baichuan-inc/baichuan-7B/summary)，[hugging face](https://huggingface.co/baichuan-inc/baichuan-7B) | [blog](https://mp.weixin.qq.com/s/qA_E_3dUe1sSOUM87ZgHdQ) | [7](https://github.com/ArronAI007/Awesome-AGI/tree/main/Model-List/model-params.md) | 4096 | [baichuan-7b Code](https://github.com/baichuan-inc/baichuan-7B)，[baichuan-7b Demo](https://huggingface.co/baichuan-inc/baichuan-7B) |1.2T | BPE | 64000 | RoPE | Pre RMS Norm |  SwiGLU | Flash-attention |
| baichuan-13b | 2023/7/11 |  |  | [hugging face Base](https://huggingface.co/baichuan-inc/Baichuan-13B-Base)，[hugging face Chat](https://huggingface.co/baichuan-inc/Baichuan-13B-Chat)，[modelscope Base](https://modelscope.cn/models/baichuan-inc/Baichuan-13B-Base)，[modelscope Chat](https://modelscope.cn/models/baichuan-inc/Baichuan-13B-Chat) | [baichuan-13b blog](https://mp.weixin.qq.com/s/Px4h2r3VIAFI5vfjXxROxg)，[百川大模型【Baichuan-13B】 多卡训练微调记录](https://mp.weixin.qq.com/s/EUZA6Lt-OcI170md9lXH1g) | [13](https://github.com/ArronAI007/Awesome-AGI/tree/main/Model-List/model-params.md) | 4096 | [baichuan-13b Code](https://github.com/baichuan-inc/Baichuan-13B) | 1.4T |  | 64000 | ALiBi | RMSNorm |  | Flash-attention |
| baichuan-53b | 2023/8/8 |  | --- | --- |--- | 53（用于搜索） | --- | [baichuan Demo](https://chat.baichuan-ai.com/home) | --- | --- | --- | --- | --- | --- | --- | 
| fireballoon/baichuan-vicuna-chinese-7b |  | baichuan-7b |  |  | | |  | |  |  |  |  |  |  |  | 
| fireballoon/baichuan-vicuna-7b |  | baichuan-7b |  |  | | |  | |  |  |  |  |  |  |  | 
| firefly-baichuan-7b-qlora-sft |  | baichuan-7b |  |  | [blog](https://mp.weixin.qq.com/s/_eTkDGG5DmxyWeiQ6DIxBw)，[Hugging Face model](https://huggingface.co/YeungNLP/firefly-baichuan-7b-qlora-sft)，[Model Scope](https://modelscope.cn/models/baichuan-inc/baichuan-7B/summary)，[C-EVAL](https://cevalbenchmark.com/static/leaderboard_zh.html) |  |  | [code](https://github.com/baichuan-inc/baichuan-7B) |
| baichuan-13b-Chat |  |  |  |  | [blog](https://mp.weixin.qq.com/s/wStOyHPd8c7V0ug1Qebryw) |  |  | [code](https://github.com/percent4/document_qa_with_llm) |
| Baichuan2 |  |  |  | [Baichuan2](https://huggingface.co/baichuan-inc/Baichuan2-7B-Intermediate-Checkpoints) | [Baichuan2技术报告](https://cdn.baichuan-ai.com/paper/Baichuan2-technical-report.pdf)，[SuperCLUE评测效果](https://mp.weixin.qq.com/s/SV7COWNu9uGnpOBzVYCyog) | 7，13 |  | [Baichuan2 Code](https://github.com/baichuan-inc/Baichuan2) | 2.6T |  |  |  |  |  |  | 
| firefly-baichuan-13b | --- | baichuan-13b-base | QLoRA |--- | --- | --- |--- | --- | --- | --- | --- | --- | --- | --- | --- | 

## ChatGLM Alternatives

| Model/Description| Paper | Code | Blog | Tokens |  Tokenizer | Vocab size | Position Embedding | Layer Normalization | Activation Function | Attention |
| --- | --- | --- | --- |--- | --- | --- |--- | --- | --- | --- | 
| ChatGLM-6B |  | [code](https://github.com/THUDM/ChatGLM-6B.git) | [blog](https://chatglm.cn/blog)，[ChatGLM-6B源码阅读](https://mp.weixin.qq.com/s/r7KEJmrpJZmY7KBP4veS6A)，[ChatGLM模型底座细节分析](https://mp.weixin.qq.com/s/oOdD3MYtE6-sNeAmPthqLg) | 1T | SentencePiece | 130528 | | Post Deep Norm | GeLU |
| chatglm+langchain+互联网 |  | [code](https://github.com/LemonQu-GIT/ChatGLM-6B-Engineering/) | [blog](https://mp.weixin.qq.com/s/lO6SrEuv4-vNbL8B3G-f8g) | 
| ChatGLM_multi_gpu_zero_Tuning |  | [code](https://github.com/CSHaitao/ChatGLM_mutli_gpu_tuning) |  | 
| ChatGLM+Fastapi |  |  | [blog](https://mp.weixin.qq.com/s/5J4UA4ePVZGXJGZsBXeN8Q) | 
| ChatGLM2-6B-32K |  |  | [blog](https://mp.weixin.qq.com/s/Fkm_D26z1jrqA44B82v7Ww) | 1.4T |  | 65024 | | Post RMS Norm | SwiGLU | GQA |
| ChatGLM-6b+langchain |  | [code](https://github.com/yanqiangmiffy/Chinese-LangChain) | [blog](https://mp.weixin.qq.com/s/xAsZZ_LOkr9Nj-JafSbXnA) | 
| one-shot微调chatglm-6b实践信息抽取 |  |  | [blog](https://mp.weixin.qq.com/s/l7lCbdJ9XGzLPTb3zKDAzQ) | 
| Falcon |  |  | [blog1](https://mp.weixin.qq.com/s/jbRRjG2ferhFPWsMtCaJyg)，[blog2](https://mp.weixin.qq.com/s/Vy_xWBuZU0AaaPMCIhKIyw) | 1.5T |  | 65024 | | Pre LN | GeLU | MQA |

## LLaMA Alternatives

| Target Model | Source Model | Optimization | Checkpoints | Paper/Blog | Params (B) | Context Length | Code | Tokens | Tokenizer | Vocab size | Position Embedding | Layer Normalization | Activation Function | Attention |
| --- | --- | --- | --- |--- | --- | --- |--- | --- | --- | --- | --- | --- | --- | --- | 
| LLaMA |  |  |  | [LLaMA: Open and Efficient Foundation Language Models](https://research.facebook.com/publications/llama-open-and-efficient-foundation-language-models/)，[blog1](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485822&idx=1&sn=b365d93a0a08769aef77f34069da1422&chksm=ced54a9af9a2c38cd5779284b5e9ae573846153e7dc00961dc163664a657d6a3fa5c8c14c7d2&token=447941009&lang=zh_CN#rd)，[blog2](https://mp.weixin.qq.com/s/fGNuTcYE8QI9_JKS9LcQ7w)，[详聊LLaMA大模型的技术细节](https://mp.weixin.qq.com/s/B9Ue0ihUGAFjT_X__R2u8Q) | 7，13，33，65 | 2048 | [LLaMA Code](https://github.com/facebookresearch/llama) | 1T/1.4T | BPE | 32000 | RoPE | Pre RMS Norm | SwiGLU |
| LLaMA 2 |  |  | [[在 Hugging Face 上玩转LLaMA 2](https://mp.weixin.qq.com/s/UnzhBJjZfPXsaSu8gNnosw)] ，[[在Colab笔记本中微调自己的Llama 2模型](https://mp.weixin.qq.com/s/pnDJaOUh_xdNdqSBl53Arw)]，[[三步上手 LLaMA2](https://mp.weixin.qq.com/s/lkRg8-rw57wDNr7FrjOSOQ)]，[[使用 Transformers 量化 Meta AI LLaMA2 中文版大模型](https://mp.weixin.qq.com/s/DEgFNAB4gwWDlQOj7-2CEg)] | [[blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247486800&idx=1&sn=9b629ca41b9f6b4feedad94363a17253&chksm=ced54eb4f9a2c7a2a5b20c182981b4323b18509f2ca8f482c2a8cdbb29bf570488bdcd280eb6&token=882149695&lang=zh_CN#rd)]，[[伯克利AI博士详解Llama 2的技术细节](https://mp.weixin.qq.com/s/Mee7sMq_bxLpIOOr91li9A)]，[[NLP社区对LLaMA2论文上半部分的讨论](https://mp.weixin.qq.com/s/SJNqjSCBX-k80_r3nmTiuA)]，[[NLP中文社区顶尖研究员们对LLaMA2论文下半部分的讨论](https://mp.weixin.qq.com/s/6k5ML3HtmvBTTCgHBZGycQ)]，[[3个最值得了解llama2开发库，助你快速搭建LLM应用](https://mp.weixin.qq.com/s/_3H6Y_NolUuxYxOo8Pl7fg)]，[[使用 Docker 快速上手中文版 LLaMA2 开源大模型](https://mp.weixin.qq.com/s/9cTNa_oya2Zj9YdDYodCvw)]，[[ Llama 2资料汇总](https://mp.weixin.qq.com/s/-01Dg9ZVfPYM4mZ4iKt8Cw) | 7，13，34，70 | 4096 | [LLaMA2 Code](https://github.com/facebookresearch/llama-recipes) | 2T |  |  |  |  | SwiGLU | GQA |
| Airoboros | LLaMA |  |  |  | 13B |  |  |  |  |  |  |  |  |  | 
| Alpaca | LLaMA 7B |  |  | [Alpaca blog](https://crfm.stanford.edu/2023/03/13/alpaca.html)，[Alpaca homepage](https://crfm.stanford.edu/alpaca) | 7，13 | 2048 | [Alpaca Code](https://github.com/tatsu-lab/stanford_alpaca) |
| Alpaca-Lora | LLaMA 7B |  |  |  | 7 |  | [Alpaca-Lora Code](https://github.com/tloen/alpaca-lora) |
| AlpaGasus | Alpaca |  |  | [AlpaGasus: Training A Better Alpaca with Fewer Data](https://arxiv.org/abs/2307.08701)，[blog](https://mp.weixin.qq.com/s/UroGj4rIa2nOw6DookpvCQ) |  |  | [AlpaGasus Code](https://lichang-chen.github.io/AlpaGasus/) |
| Alpaca-CoT | Alpaca |  |  | [官网](https://sota.jiqizhixin.com/project/alpaca-cot) |  |  |  [Alpaca-CoT Code](https://github.com/PhoebusSi/Alpaca-CoT)|
| Anima | guanaco-33B |  | [Anima-33B](https://huggingface.co/lyogavin/Anima33B) | [Anima Blog](https://zhuanlan.zhihu.com/p/638058537?utm_source=wechat_session&utm_medium=social&s_r=0) |  |  | [Anima Code](https://github.com/lyogavin/Anima) |
| Baize | LLaMA |  | [baize-lora-7B](https://huggingface.co/spaces/project-baize/baize-lora-7B) | [Baize: An Open-Source Chat Model with Parameter-Efficient Tuning on Self-Chat Data](https://arxiv.org/abs/2304.01196)，[blog](https://mp.weixin.qq.com/s/zxElGfclNbBwTuDG4Qrxnw) | 7B | 512 | [Baize Code](https://github.com/project-baize/baize-chatbot) |
| BELLE | Alpaca |  |  |  | 7B |  | [BELLE Code](https://github.com/LianjiaTech/BELLE) |
| BiLLa | LLaMA |  |  | [BiLLa: A Bilingual LLaMA with Enhanced Reasoning Ability](https://mp.weixin.qq.com/s/8KDpDC6Fkb_61gFfkcT8TQ) | 7B |  | [BiLLa Code](https://github.com/Neutralzz/BiLLa) |
| CaMA | LLaMA |  |  |  |  |  | [CaMA Code](https://github.com/zjunlp/CaMA) |
| ChatLLaMA | LLaMA | RLHF |  |  |  |  | [ChatLLaMA Code](https://github.com/nebuly-ai/nebuly/tree/main/optimization/chatllama) |
| Chinese-LlaMA2 | Llama-2 | SFT |  |  |  |  | [Chinese-LlaMA2 Code](https://github.com/michael-wzhu/Chinese-LlaMA2) |
| Chinese-Llama-2 | Llama-2 | LoRA/FPFT |  |  |  |  | [Chinese-Llama-2 Code](https://github.com/longyuewangdcu/Chinese-Llama-2) |
| Chinese-Vicuna | LLaMA | LoRA |  |  |  |  | [Chinese-Vicuna Code](https://github.com/Facico/Chinese-Vicuna) |
| Chinese-LLaMA-Alpaca | LLaMA | 扩词表 |  | [EFFICIENT AND EFFECTIVE TEXT ENCODING FOR CHINESE LL AMA AND ALPACA](https://arxiv.org/pdf/2304.08177v1.pdf) |  |  | [Chinese-LLaMA-Alpaca Code](https://github.com/ymcui/Chinese-LLaMA-Alpaca) |  |  |  |  |  |  |  | 
| ColossalChat | LLaMA | RLHF |  | [blog](https://syncedreview.com/2023/03/29/colossalchat-an-open-source-solution-for-cloning-chatgpt-with-a-complete-rlhf-pipeline/) |  |  | [ColossalChat Code](https://github.com/hpcaitech/ColossalAI/tree/main/applications/Chat) |
| CAMEL | LLaMA |  |  | [blog](https://starmpcc.github.io/CAMEL/) |  |  | [CAMEL Code](https://github.com/starmpcc/CAMEL) |
| 草本（原华驼） |  LLaMA | SFT |  | [HuaTuo (华驼): Tuning LLaMA Model with Chinese Medical Knowledge](https://arxiv.org/pdf/2304.06975v1.pdf)，[blog1](https://mp.weixin.qq.com/s/TYpc_63qDlR6MwscxCKKhA)，[blog2](https://mp.weixin.qq.com/s/iuQANmwCS7AXQRik7HwQPg) |  |  | [草本（原华驼） Code](https://github.com/SCIR-HI/Huatuo-Llama-Med-Chinese) |
| ExpertLLaMA | LLaMA |  |  | [ExpertPrompting: Instructing Large Language Models to be Distinguished Experts](https://arxiv.org/abs/2305.14688)，[ExpertLLaMA demo](https://huggingface.co/spaces/OFA-Sys/expertllama) | 7B |  | [ExpertLLaMA Code](https://github.com/OFA-Sys/ExpertLLaMA) |
| FreedomGPT | LLaMA |  |  | [FreedomGPT homepage](https://freedomgpt.com/) |  |  | [FreedomGPT Code](https://github.com/ohmplatform/FreedomGPT) |
| GoGPT/GoGPT2 |  |  | [GoGPT2-7B](https://huggingface.co/golaxy/gogpt2-7b) |  |  |  | [GoGPT code](https://github.com/yanqiangmiffy/GoGPT) |
| GPT-4-LLM | LLaMA |  |  |  | 7B |  |  |
| Guanaco | LLaMA |  |  |  |  |  |  |
| Koala | LLaMA-13B |  | [Koala model](https://drive.google.com/drive/folders/10f7wrlAFoPIy-TECHsx9DKIvbQYunCfl) | [中文blog](https://hub.baai.ac.cn/view/25284)，[英文blog](https://bair.berkeley.edu/blog/2023/04/03/koala/) | 13B | 512 | [Koala Chat](https://chat.lmsys.org/?model=koala-13b)，[EasyLM Koala](https://github.com/young-geng/EasyLM)，[training data preprocessing](https://github.com/young-geng/koala_data_pipeline) | ChatGPT Distillation Data:[ShareGPT](https://sharegpt.com/)，[HC3](https://arxiv.org/abs/2301.07597)； Open Source Data:[OIG](https://laion.ai/blog/oig-dataset/)，[Stanford Alpaca](https://crfm.stanford.edu/2023/03/13/alpaca.html)，[Anthropic HH](https://huggingface.co/datasets/Anthropic/hh-rlhf)，[OpenAI WebGPT](https://huggingface.co/datasets/openai/webgpt_comparisons)，[OpenAI Summarization](https://huggingface.co/datasets/openai/summarize_from_feedback)；[koala-test-set](https://github.com/arnav-gudibande/koala-test-set) |
| LLaMA-2 & Alpaca-2 | Llama-2，LLaMA&Alpaca | （1）扩充中文词表，（2）FlashAttention-2，（3）基于NTK的自适应上下文扩展技术，（4）简化的中英双语系统提示语 |  | [blog](https://mp.weixin.qq.com/s/sJ_imBdHCD4NibVy58EO2w) |  |  | [LLaMA-2 & Alpaca-2 Code](https://github.com/ymcui/Chinese-LLaMA-Alpaca-2) |
| LIMA | LLaMA-65B |  |  | [blog](https://mp.weixin.qq.com/s?search_click_id=7213828026277652651-1688375605291-1083947599&__biz=MjM5ODExNDA2MA==&mid=2449961473&idx=2&sn=f080fa7b1b5657db9872724caee56519&chksm=b13c7462864bfd741f0f061b87187f2cde36b68020cfe3402717a6858563311cb642eb340989&rd2werd=1&key=ea1d916ce49bb536ce48f3aba8e329d1e1aa6fdcda4f73580b0a5adbd624721e6a974570fd6ef2823ecfa6c95e2dc09179b51e440e9179f79d0ba01f62cf795d6c697f95bf05a28904f4172b11e1ce873a2d7a0e85c74d509e916176aacb43657fd11a6de7611d65bd4ae82315835aa138a423887a219f2971c6a525679fd805&ascene=65&uin=MTkwNzA5OTA4Mw%3D%3D&devicetype=iMac+MacBookPro13%2C2+OSX+OSX+12.6.7+build(21G651)&version=13080109&nettype=WIFI&lang=zh_CN&countrycode=CN&fontScale=100&exportkey=n_ChQIAhIQ0Z339%2BFUk%2Bp0YpfMQjB%2BhxKDAgIE97dBBAEAAAAAANJyNCKr%2F3UAAAAOpnltbLcz9gKNyK89dVj0q5AacL9r2sPbvlDuJo6SwYSJ2wbfYGvc3EDxuk%2BMQS0vl8RLluMN%2Fuh9u2LxBZTHTiuQct62Bjib68qd1EvB8CgGKMV34B5%2BKHCutInPzdE9Uac6dxp0VYtd%2BJnEwljL8jf7mWZdwTkPdEZl1P0OEb3HFzczXelqDR3h7D2xEVmQuFHGIeVi7iPOHMT0AWhhGLdbrVhCKbPT3%2BX9FPOLjJSql2UD95dTmSzZKqdvOIMGpD5t%2F98jDuMUojr9HUMdvljQ1XkiJVnd%2FbqSsLS3S5t7E%2Ftjmjb9g7IxWkY%3D&acctmode=0&pass_ticket=mJ3t3nBN%2BXhKCYp9bzJSkTl%2B9PwobzvYen%2F5Kv4kpcj1Lig98d0DXbcAyqBW0vaB&wx_header=0) |  |  |  |
| LongLLaMA |  |  | [LongLLaMA-3B](https://huggingface.co/syzymon/long_llama_3b) | [Focused Transformer: Contrastive Training for Context Scaling](https://arxiv.org/pdf/2307.03170.pdf)，[blog](https://mp.weixin.qq.com/s/K8ExTUUXDruZGwr-PA4oFQ) |  |  | [LongLLaMA Code](https://github.com/CStanKonrad/long_llama) |
| MetaMath | LLaMA2 | SFT | [MetaMath](https://huggingface.co/meta-math) | [MetaMath: Bootstrap Your Own Mathematical Questions for Large Language Models](https://arxiv.org/abs/2309.12284)，[MetaMath主页](https://meta-math.github.io/) | --- | --- | [MetaMath Code](https://github.com/meta-math/MetaMath) | --- | --- | --- | --- | --- | --- | --- | 
| YuLan-Chat | LLaMA-13B |  |  |  |  |  |  |  |  |  |  |  |  |  |
| OpenBuddy-LLaMA1-30B | LLaMA |  | [ModelScope demo](https://modelscope.cn/models/OpenBuddy/openbuddy-llama-65b-v8-bf16/summary) | [blog](https://mp.weixin.qq.com/s/k-ZWg0Vuud3Atn3aaXBaCQ) | 13，33，65 |  |  |
| Platypus | LLaMA2 |  |  | [Platypus: Quick, Cheap, and Powerful Refinement of LLMs](https://arxiv.org/abs/2308.07317)，[blog](https://mp.weixin.qq.com/s/yzfgITUWaCf3Wcdc6lGCQA) |  |  |  |
| StackLLaMA | LLaMA | SFT/RM/RLHF |  | [中文blog](https://hub.baai.ac.cn/view/25341)，[英文blog](https://huggingface.co/blog/stackllama) |  |  |  |
| UltraLM | LLaMA |  |  |  | 13B |  |  |  |  |  |  |  |  |  | 
| Vicuna | Alpaca |  |  | [Vicuna官网地址](https://vicuna.lmsys.org/)，[blog](https://hub.baai.ac.cn/view/25328) | 7，13 | 2k | [Vicuna Code](https://github.com/lm-sys/FastChat) |
| Vicuna v1.5 | Llama 2 |  |  | [Vicuna官网地址](https://vicuna.lmsys.org/)，[blog](https://hub.baai.ac.cn/view/25328) | 7，13 | 4k，16k | [Vicuna v1.5 Code](https://github.com/lm-sys/FastChat) |
| WizardLM | LLaMA |  |  | |  |  | |  |  |  |  |  |  |  | 

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
| Dolly（GPT-J）        | 2023/04 | [dolly-v2-12b](https://huggingface.co/databricks/dolly-v2-12b)                            |  [Hello Dolly: Democratizing the magic of ChatGPT with open models](https://www.databricks.com/blog/2023/03/24/hello-dolly-democratizing-magic-chatgpt-open-models.html)，[Databricks Inc主页](https://www.databricks.com)            | 3, 7, 12     | [2048](https://github.com/databrickslabs/dolly#dolly) | MIT                |                                                                                                                       |
| Dolly2.0（Pythia） |  |  | [Free Dolly: Introducing the World's First Truly Open Instruction-Tuned LLM](https://www.databricks.com/blog/2023/04/12/dolly-first-open-commercially-viable-instruction-tuned-llm)，[中文blog](https://hub.baai.ac.cn/view/25434) | 
| DeepSpeed-Chat |  | [code](https://github.com/microsoft/DeepSpeedExamples/tree/master/applications/DeepSpeed-Chat) | [blog](https://hub.baai.ac.cn/view/25414) | 
| DLite | 2023/05 | [dlite-v2-1_5b](https://huggingface.co/aisquared/dlite-v2-1_5b) | [Announcing DLite V2: Lightweight, Open LLMs That Can Run Anywhere](https://medium.com/ai-squared/announcing-dlite-v2-lightweight-open-llms-that-can-run-anywhere-a852e5978c6e) | 0.124 - 1.5 | [1024](https://huggingface.co/aisquared/dlite-v2-1_5b/blob/main/config.json) | Apache 2.0         | [DLite-v2-1.5B](https://github.com/slai-labs/get-beam/tree/main/examples/dlite-v2)                                    |
| FastChat-T5 | 2023/04 | [fastchat-t5-3b-v1.0](https://huggingface.co/lmsys/fastchat-t5-3b-v1.0) | [We are excited to release FastChat-T5: our compact and commercial-friendly chatbot!](https://twitter.com/lmsysorg/status/1652037026705985537?s=20) | 3 | [512](https://huggingface.co/lmsys/fastchat-t5-3b-v1.0/blob/main/config.json) | Apache 2.0 |                                                                                                                       |
| GPT3.5 |  |  | [OpenAI playground](https://platform.openai.com/playground) | 
| MiniGPT-4 |  |  | [MiniGPT-4 Paper](https://github.com/Vision-CAIR/MiniGPT-4/blob/main/MiniGPT_4.pdf)，[主页](https://minigpt-4.github.io/)，[video](https://youtu.be/__tftoxpBAw)，[dataset](https://drive.google.com/file/d/1nJXhoEcy3KTExr17I7BXqY5Y9Lx_-n-9/view)，[Demo](https://6b89c70eb5e14dca33.gradio.live/)，[Demo1](https://b2517615b965687635.gradio.live/)，[Demo2](https://c8de8ff74b6a6c6a9b.gradio.live/)，[Demo3](https://0a111504e072685259.gradio.live/)，[Demo4](https://90bc0bac96e6457e8f.gradio.live/) |  |  |  | [MiniGPT-4 Code](https://github.com/Vision-CAIR/MiniGPT-4) |
| MOSS |  |  | [Secrets of RLHF in Large Language Models Part I: PPO](https://arxiv.org/abs/2307.04964)，[MOSS Blog](https://mp.weixin.qq.com/s/BjXtnEEVCQiPOy-_qCNM4g)，[数据集](https://laion.ai/blog/oig-dataset/) |  |  |  | [MOSS Code](https://openlmlab.github.io/MOSS-RLHF/) |
| OpenAssistant |  |  | [OpenAssistant Conversations - Democratizing Large Language Model Alignment](https://drive.google.com/file/d/10iR5hKwFqAKhL3umx8muOWSRm7hs5FqX/view)，[官网](https://open-assistant.io/chat)，[dataset](https://huggingface.co/datasets/OpenAssistant/oasst1)，[youtube](https://youtu.be/ddG2fM9i4Kk) |  |  |  | [OpenAssistant Code](https://github.com/LAION-AI/Open-Assistant) |
| OpenChatKit |  | | [OpenChatKit Blog](https://mp.weixin.qq.com/s/9Av3nhJLrcYAsBW9vVGjTw)，[OpenChatKit Chat](https://huggingface.co/spaces/togethercomputer/OpenChatKit)  |  |  |  | [OpenChatKit Code](https://github.com/togethercomputer/OpenChatKit) |
| WebCPM |  |  | [WebCPM: Interactive Web Search for Chinese Long-form Question Answering](https://arxiv.org/abs/2305.06849)，[WebCPM Blog](https://mp.weixin.qq.com/s/m4zsF2HDFHSKc23Oq0O98w) |  |  |  | [WebCPM Code](https://github.com/thunlp/WebCPM) |

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

---

### Universal LLMs for Picture/Video 

Some examples of **Universal LLMs for Picture/Video** as follows：

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length                                                                         | Licence | Code |
| --- | --- | --- | --- | --- | ---| --- | ---|
| Animate Anyone |  |  | [Animate Anyone: Consistent and Controllable Image-to-Video Synthesis for Character Animation](https://arxiv.org/pdf/2311.17117.pdf)，[Animate Anyone主页](https://humanaigc.github.io/animate-anyone/) |  |  |  | [Animate Anyone Code](https://github.com/HumanAIGC/AnimateAnyone) |
| Bing Image Creator |  |  | [Bing Image Creator Blog](https://techcrunch.com/2023/03/21/microsoft-brings-openais-dall-e-image-creator-to-the-new-bing/) |  |  |  |  |
| BlenderGPT |  |  |  |  |  |  | [BlenderGPT Code](https://github.com/gd3kr/BlenderGPT)  |
| CHAMPAGNE |  |  | [CHAMPAGNE: Learning Real-world Conversation from Large-Scale Web Videos](https://arxiv.org/pdf/2303.09713.pdf)  |  |  |  | [CHAMPAGNE Code](https://seungjuhan.me/champagne) |
| CodeGen2 | 2023/04 | [codegen2 1B-16B](https://github.com/salesforce/CodeGen2) | [CodeGen2: Lessons for Training LLMs on Programming and Natural Languages](https://arxiv.org/abs/2305.02309) | 1 - 16 | [2048](https://arxiv.org/abs/2305.02309) | [Apache 2.0](https://github.com/salesforce/CodeGen2/blob/main/LICENSE)| 
| Consistency Models |  |  | [Consistency Models](https://arxiv.org/abs/2303.01469)，[Consistency Models Blog](https://hub.baai.ac.cn/view/25445) |  |  |  | [Consistency Models Code](https://github.com/openai/consistency_models) |
| ControlNet |  |  | [Adding Conditional Control to Text-to-Image Diffusion Models](https://arxiv.org/pdf/2302.05543.pdf)，[ControlNet Blog](https://mp.weixin.qq.com/s/k8rE9GrF97E-0TKJhih9kw)  |  |  |  | [ControlNet Code](https://github.com/lllyasviel/ControlNet) |

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

---

### Universal LLMs for Multimodal 

Some examples of **Universal LLMs for Multimodal** as follows：
 
| Multimodal Model | Language Model | Vision Model |  Checkpoints | Paper/Blog | Params (B) | Context Length | Licence | Code |
| --- | --- | --- | --- | --- |---|---| --- | --- |
| BLIP-2 |  |  |  | [BLIP-2: Bootstrapping Language-Image Pre-training with Frozen Image Encoders and Large Language Models](https://arxiv.org/abs/2301.12597)，[demo](https://huggingface.co/spaces/Salesforce/BLIP2)，[doc](https://huggingface.co/docs/transformers/main/en/model_doc/blip-2) |  |  | | [code](https://github.com/salesforce/LAVIS/tree/main/projects/blip2)，[fine-tuing](https://github.com/salesforce/LAVIS)，[hugging face spaces](https://hf.co/spaces/Salesforce/BLIP2) |
| CodeGen2 | | | [codegen2 1B-16B](https://github.com/salesforce/CodeGen2) | [CodeGen2: Lessons for Training LLMs on Programming and Natural Languages](https://arxiv.org/abs/2305.02309) | 1 - 16 | [2048](https://arxiv.org/abs/2305.02309) | [Apache 2.0](https://github.com/salesforce/CodeGen2/blob/main/LICENSE)| 
| CogVLM | Vicuna-7B-v1.5，GLM，Llama2 | EVA2-CLIP-E | [modelscope](https://www.modelscope.cn/models/ZhipuAI/CogVLM)，[Huggingface](https://huggingface.co/THUDM/CogVLM) | [CogVLM: Visual Expert for Pretrained Language Models](https://arxiv.org/abs/2311.03079) | 17 |---| --- | [CogVLM Code](https://github.com/THUDM/CogVLM) |
| Emu2 |  |  | [Emu2](https://huggingface.co/BAAI/Emu2) | [Generative Multimodal Models are In-Context Learners](https://arxiv.org/abs/2312.13286)，[PageHome](https://baaivision.github.io/emu2/)，[Demo](https://huggingface.co/spaces/BAAI/Emu2) | 37 |---| --- | [Emu2 Code](https://github.com/baaivision/Emu/tree/main/Emu2) |
| GPT4 |  |  |  | [OpenAI GPT4](https://openai.com/research/gpt-4)，[GPT4_System_Card中文翻译](https://github.com/ArronAI007/ChatGPT-Summary/blob/main/GPT4/Official/GPT-4_System_Card_zh.md)，[GPT4_Technical_Report中文翻译](https://github.com/ArronAI007/ChatGPT-Summary/blob/main/GPT4/Official/GPT4_Technical_Report_zh.md)，[The Ultimate GPT-4 Guide](https://doc.clickup.com/37456139/d/h/13q28b-324/e2a22b0c164b1f9) | 
| GPT4Video |  |  |  | [GPT4Video: A Unified Multimodal Large Language Model for lnstruction-Followed Understanding and Safety-Aware Generation](https://arxiv.org/abs/2311.16511)，[HomePage](https://gpt4video.github.io) |  |  |  |  |
| LaVIN | LLaMA | ViT-L |  | [Cheap and Quick: Efficient Vision-Language Instruction Tuning for Large Language Models](https://arxiv.org/pdf/2305.15023.pdf)，[blog](https://mp.weixin.qq.com/s/MRLYk1b7VJ_b6OmJ9mzkdw) | 7，13 |  | [LaVIN Code](https://github.com/luogen1996/LaVIN) |
| LLaVA |  |  |  | [Visual Instruction Tuning](https://arxiv.org/pdf/2304.08485.pdf)，[introduce](https://llava-vl.github.io/) |  |  |  | |
| UniDiffuser |  |  |  | [One Transformer Fits All Distributions in Multi-Modal Diffusion at Scale](https://ml.cs.tsinghua.edu.cn/diffusion/unidiffuser.pdf) |  |  |  | [UniDiffuser Code](https://github.com/thu-ml/unidiffuser) |
| Video-LLaMA |  |  |  | [Video-LLaMA: An Instruction-tuned Audio-Visual Language Model for Video Understanding](https://arxiv.org/abs/2306.02858) |  |  |  | |
| VisCPM |  |  |  | [VisCPM Blog](https://mp.weixin.qq.com/s/Fgfbs1vV7RF6kpyk4bfIYw) |  |  |  | [VisCPM Code](https://github.com/OpenBMB/VisCPM) |
| X-LLM |  |  |  | [X-LLM: Bootstrapping Advanced Large Language Models by Treating Multi-Modalities as Foreign Languages](https://arxiv.org/abs/2305.04160)，[项目主页](https://x-llm.github.io/) |  |  |  | |
| Pika | --- | --- | --- | --- | ---| --- | ---|
| Sora | --- | --- | --- | [Sora](https://openai.com/sora) | ---| --- | ---|
| SoraWebui | --- | --- | --- | [SoraWebui](https://sorawebui.com/) | ---| --- | [SoraWebui Code](https://github.com/SoraWebui/SoraWebui) |

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
