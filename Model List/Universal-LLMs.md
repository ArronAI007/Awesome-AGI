# Universal LLMs

## Universal LLMs for Text

Some examples of **Universal LLMs for Text** as follows：

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length | Licence | Code |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Bard | 2023/03 |  | [Bard homepage](http://bard.google.com/)，[theverge blog](https://www.theverge.com/23649897/google-Bard-chatbot-search-engine) | | | | |
| Bloom | 2022/11 | [Bloom](https://huggingface.co/bigscience/bloom) | [BLOOM: A 176B-Parameter Open-Access Multilingual Language Model](https://arxiv.org/abs/2211.05100) | 176 | [2048](https://huggingface.co/bigscience/bloom) |  [OpenRAIL-M v1](https://huggingface.co/spaces/bigcode/bigcode-model-license-agreement) | [Bloom Code](https://github.com/huggingface/transformers-bloom-inference/tree/main)                                                                                                                     |
| Cerebras-GPT | 2023/03 | [Cerebras-GPT](https://huggingface.co/cerebras)                                           | [Cerebras-GPT: A Family of Open, Compute-efficient, Large Language Models](https://www.cerebras.net/blog/cerebras-gpt-a-family-of-open-compute-efficient-large-language-models/) ([Paper](https://arxiv.org/abs/2304.03208)) | 0.111 - 13      | [2048](https://huggingface.co/cerebras/Cerebras-GPT-13B#model-details) | Apache 2.0         | [Cerebras-GPT-1.3B](https://github.com/slai-labs/get-beam/tree/main/examples/cerebras-gpt)                            |
| ChatYuan |  | [ChatYuan-large-v1](https://huggingface.co/ClueAI/ChatYuan-large-v1)  | [ChatYuan Blog](https://mp.weixin.qq.com/s?__biz=Mzg3NDIyMzI0Mw==&mid=2247485655&idx=1&sn=ad80d8a17d4aaab90b17a79b638c712d&chksm=ced54b33f9a2c225ce292b4e3d5725a668d0bfc9fe0be610c847b31b61714ecf75c06dac1cb5&token=447941009&lang=zh_CN#rd) | |  |  | [ChatYuan Code](https://github.com/clue-ai/ChatYuan) |
| ChatDB |  |  | [ChatDB: Augmenting LLMs with Databases as Their Symbolic Memory](https://arxiv.org/abs/2306.03901)，[blog](https://mp.weixin.qq.com/s/o3j1vNLHlJ6qTea219A4Qw)，[主页](https://chatdatabase.github.io) |  |  |   | [ChatDB Code](https://github.com/huchenxucs/ChatDB) |
| Claude |  |  | [产品地址](https://www.anthropic.com/product)，[申请地址](https://www.anthropic.com/earlyaccess)，[blog](https://mp.weixin.qq.com/s/Wx5q-rEwG4sROvnewGxWrw)，[Claude支持100k上下文](https://mp.weixin.qq.com/s/Yu551-z14lpiFGSOfXE2Tw) | 
| Claude 2 |  |  | [Model Card and Evaluations for Claude Models](https://www-files.anthropic.com/production/images/Model-Card-Claude-2.pdf) |
| Claude 3 | 2024/3 | [Claude 3](https://www.anthropic.com/claude-3-model-card) | [Claude 3技术报告](https://www.anthropic.com/claude-3-model-card) |  |  |  |  |
| ColossalAI |  |  | [ColossalAI SFT Blog](https://mp.weixin.qq.com/s/NS4yySeYd7QUYb7CB9V0lA) |  |  |  | [ColossalAI Code](https://github.com/hpcaitech/ColossalAI/tree/main/applications/Chat) | 
| CPM-Bee |  |  [CPM-Bee-10B](https://huggingface.co/openbmb/cpm-bee-10b)| [CPM-Bee Blog](https://mp.weixin.qq.com/s/BO4cDB9KRSODZw3TvZpUAA) |  |  |  | [CPM-Bee Code](https://github.com/OpenBMB/CPM-Bee) |
| DBRX | 2024/03 | [DBRX-base](https://huggingface.co/databricks/dbrx-base)，[DBRX微调模型](https://huggingface.co/databricks/dbrx-instruct) |  | 132 |  |  | [DBRX Code](https://github.com/databricks/dbrx) |
| Dolly（GPT-J）        | 2023/04 | [dolly-v2-12b](https://huggingface.co/databricks/dolly-v2-12b)                            |  [Hello Dolly: Democratizing the magic of ChatGPT with open models](https://www.databricks.com/blog/2023/03/24/hello-dolly-democratizing-magic-chatgpt-open-models.html)，[Databricks Inc主页](https://www.databricks.com)            | 3, 7, 12     | [2048](https://github.com/databrickslabs/dolly#dolly) | MIT                |                                                                                                                       |
| Dolly2.0（Pythia） |  |  | [Free Dolly: Introducing the World's First Truly Open Instruction-Tuned LLM](https://www.databricks.com/blog/2023/04/12/dolly-first-open-commercially-viable-instruction-tuned-llm)，[中文blog](https://hub.baai.ac.cn/view/25434) | 
| DeepSpeed-Chat |  | [code](https://github.com/microsoft/DeepSpeedExamples/tree/master/applications/DeepSpeed-Chat) | [blog](https://hub.baai.ac.cn/view/25414) | 
| DLite | 2023/05 | [dlite-v2-1_5b](https://huggingface.co/aisquared/dlite-v2-1_5b) | [Announcing DLite V2: Lightweight, Open LLMs That Can Run Anywhere](https://medium.com/ai-squared/announcing-dlite-v2-lightweight-open-llms-that-can-run-anywhere-a852e5978c6e) | 0.124 - 1.5 | [1024](https://huggingface.co/aisquared/dlite-v2-1_5b/blob/main/config.json) | Apache 2.0         | [DLite-v2-1.5B](https://github.com/slai-labs/get-beam/tree/main/examples/dlite-v2)                                    |
| FastChat-T5 | 2023/04 | [fastchat-t5-3b-v1.0](https://huggingface.co/lmsys/fastchat-t5-3b-v1.0) | [We are excited to release FastChat-T5: our compact and commercial-friendly chatbot!](https://twitter.com/lmsysorg/status/1652037026705985537?s=20) | 3 | [512](https://huggingface.co/lmsys/fastchat-t5-3b-v1.0/blob/main/config.json) | Apache 2.0 |  |                                                
| GPT3.5 |  |  | [OpenAI playground](https://platform.openai.com/playground) | 
| Grok-1 | 2024/3 | [Grok-1](https://github.com/xai-org/grok-1#downloading-the-weights) | [Grok-1 Blog](https://mp.weixin.qq.com/s/hvt5zwoazDx26KOaKuTs_w) | 314 | 8192 | Apache 2.0 | [Grok-1 Code](https://github.com/xai-org/grok-1) |
| MiniGPT-4 |  |  | [MiniGPT-4 Paper](https://github.com/Vision-CAIR/MiniGPT-4/blob/main/MiniGPT_4.pdf)，[主页](https://minigpt-4.github.io/)，[video](https://youtu.be/__tftoxpBAw)，[dataset](https://drive.google.com/file/d/1nJXhoEcy3KTExr17I7BXqY5Y9Lx_-n-9/view)，[Demo](https://6b89c70eb5e14dca33.gradio.live/)，[Demo1](https://b2517615b965687635.gradio.live/)，[Demo2](https://c8de8ff74b6a6c6a9b.gradio.live/)，[Demo3](https://0a111504e072685259.gradio.live/)，[Demo4](https://90bc0bac96e6457e8f.gradio.live/) |  |  |  | [MiniGPT-4 Code](https://github.com/Vision-CAIR/MiniGPT-4) |
| MOSS |  |  | [Secrets of RLHF in Large Language Models Part I: PPO](https://arxiv.org/abs/2307.04964)，[MOSS Blog](https://mp.weixin.qq.com/s/BjXtnEEVCQiPOy-_qCNM4g)，[数据集](https://laion.ai/blog/oig-dataset/) |  |  |  | [MOSS Code](https://openlmlab.github.io/MOSS-RLHF/) |
| OpenAssistant |  |  | [OpenAssistant Conversations - Democratizing Large Language Model Alignment](https://drive.google.com/file/d/10iR5hKwFqAKhL3umx8muOWSRm7hs5FqX/view)，[官网](https://open-assistant.io/chat)，[dataset](https://huggingface.co/datasets/OpenAssistant/oasst1)，[youtube](https://youtu.be/ddG2fM9i4Kk) |  |  |  | [OpenAssistant Code](https://github.com/LAION-AI/Open-Assistant) |
| OpenChatKit |  | | [OpenChatKit Blog](https://mp.weixin.qq.com/s/9Av3nhJLrcYAsBW9vVGjTw)，[OpenChatKit Chat](https://huggingface.co/spaces/togethercomputer/OpenChatKit)  |  |  |  | [OpenChatKit Code](https://github.com/togethercomputer/OpenChatKit) |
| WebCPM |  |  | [WebCPM: Interactive Web Search for Chinese Long-form Question Answering](https://arxiv.org/abs/2305.06849)，[WebCPM Blog](https://mp.weixin.qq.com/s/m4zsF2HDFHSKc23Oq0O98w) |  |  |  | [WebCPM Code](https://github.com/thunlp/WebCPM) |
| Yi-1.5 |  | [Yi-1.5](https://huggingface.co/collections/01-ai/yi-15-2024-05-663f3ecab5f815a3eaca7ca8) |  | 6、9、34 | 4k | Apache 2.0 | [Yi-1.5 Code](https://github.com/01-ai/Yi-1.5) |

---

## Universal LLMs for Code  

Some examples of **Universal LLMs for Code** as follows：

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length                                                                         | Licence | Code                                                                                    |
| --- | --- | --- | --- | --- |----| --- |---|
| AutoCoder | 2024/05 | [AutoCoder 6.7-33](https://huggingface.co/Bin12345/AutoCoder) | [AutoCoder: Enhancing Code Large Language Model with AIEV-INSTRUCT](https://arxiv.org/pdf/2405.14906) | 6.7,33 | 5120 |  | [AutoCoder Code](https://github.com/bin123apple/AutoCoder) |
| Baldur |  |  | [Baldur: Whole-Proof Generation and Repair with Large Language Models](https://arxiv.org/abs/2303.04910) |  |  |  |  |
| CodeGeeX |  |  | [CodeGeeX: A Pre-Trained Model for Code Generation with Multilingual Evaluations on HumanEval-X](https://arxiv.org/pdf/2303.17568.pdf) |  |  |  | [CodeGeeX Code](https://github.com/THUDM/CodeGeeX) |
| CodeGeeX2-6B |  |  | [CodeGeeX2-6B Blog](https://mp.weixin.qq.com/s/roQSCo-7s361P3TmJjjZjA) |  |  |  | [CodeGeeX2-6B Code](https://github.com/THUDM/CodeGeeX2) |
| CodeGen2 | 2023/04 | [codegen2 1B-16B](https://github.com/salesforce/CodeGen2) | [CodeGen2: Lessons for Training LLMs on Programming and Natural Languages](https://arxiv.org/abs/2305.02309) | 1 - 16 | [2048](https://arxiv.org/abs/2305.02309) | [Apache 2.0](https://github.com/salesforce/CodeGen2/blob/main/LICENSE)|                                                                                           |
| CodeGen2.5 | 2023/07 | [CodeGen2.5-7B-multi](https://huggingface.co/Salesforce/codegen25-7b-multi) | [CodeGen2.5: Small, but mighty](https://blog.salesforceairesearch.com/codegen25/) | 7 | [2048](https://huggingface.co/Salesforce/codegen25-7b-multi/blob/main/config.json) | [Apache 2.0](https://huggingface.co/Salesforce/codegen25-7b-multi/blob/main/README.md) | 
| Code Llama  | 2023 | [Inference Code for CodeLlama models]([https://ai.meta.com/resources/models-and-libraries/llama-downloads/](https://github.com/facebookresearch/codellama)) | [Code Llama: Open Foundation Models for Code](https://ai.meta.com/research/publications/code-llama-open-foundation-models-for-code/)     | 7 - 34       | [4096](https://scontent-zrh1-1.xx.fbcdn.net/v/t39.2365-6/369856151_1754812304950972_1159666448927483931_n.pdf?_nc_cat=107&ccb=1-7&_nc_sid=3c67a6&_nc_ohc=wURKmnWKaloAX-ib5XW&_nc_ht=scontent-zrh1-1.xx&oh=00_AfAN1GB2K_XwIz54PqXTr-dhilI3CfCwdQoaLMyaYEEECg&oe=64F0A68F)  | [Custom](https://github.com/facebookresearch/llama/blob/main/LICENSE) Free if you have under 700M users and you cannot use LLaMA outputs to train other LLMs besides LLaMA and its derivatives   | [HuggingChat](https://huggingface.co/blog/codellama) | 
| Copilot X |  |  | [Copilot X Blog](https://github.blog/2023-03-22-github-copilot-x-the-ai-powered-developer-experience/) |  |  |  | [Copilot X Code](https://github.com/features/copilot/) |
| Deepseek-Coder |  |  |  |  |  |  |  |

---

## Universal LLMs for Picture/Video 

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

## Universal LLMs for Audio

Some examples of **Universal LLMs for Audio** as follows：

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length                                                                         | Licence | Code                                                                                    |
| --- | --- | --- | --- | --- |----| --- |---|
| AudioCraft |  |  | [AudioCraft Blog](https://mp.weixin.qq.com/s/OLLCiMqKHQJxGGR1sPA3qw) |  |  |  | [code](https://github.com/facebookresearch/audiocraft) |
| CodeGen2 | 2023/04 | [codegen2 1B-16B](https://github.com/salesforce/CodeGen2) | [CodeGen2: Lessons for Training LLMs on Programming and Natural Languages](https://arxiv.org/abs/2305.02309) | 1 - 16 | [2048](https://arxiv.org/abs/2305.02309) | [Apache 2.0](https://github.com/salesforce/CodeGen2/blob/main/LICENSE)| 
| Generative Disco |  |  | [Generative Disco: Text-to-Video Generation for Music Visualization](https://arxiv.org/pdf/2304.08551.pdf)，[Generative Disco Blog](https://hub.baai.ac.cn/view/25517) |  |  |  | | 
| MUSICGEN |  |  | [Simple and Controllable Music Generation](https://arxiv.org/pdf/2306.05284.pdf)，[MUSICGEN Blog](https://the-decoder.com/metas-open-source-ai-musicgen-turns-text-and-melody-into-new-songs/) |  |  |  | [demo](https://huggingface.co/spaces/facebook/MusicGen) |
| Make-An-Audio |  |  | [Make-An-Audio: Text-To-Audio Generation with Prompt-Enhanced Diffusion Models](https://arxiv.org/abs/2301.12661) |  |  |  | [Make-An-Audio Code](https://text-to-audio.github.io) |
| Voicebox |  |  | [Voicebox: Text-Guided Multilingual Universal Speech Generation at Scale](https://research.facebook.com/file/649409006862002/paper_fixed.pdf)，[Voicebox Blog](https://hub.baai.ac.cn/view/27492) | |  |  |  | |

---

## Universal LLMs for Multimodal 

Some examples of **Universal LLMs for Multimodal** as follows：
 
| Multimodal Model | Language Model | Vision Model |  Checkpoints | Paper/Blog | Params (B) | Context Length | Licence | Code |
| --- | --- | --- | --- | --- |---|---| --- | --- |
| BLIP-2 |  |  |  | [BLIP-2: Bootstrapping Language-Image Pre-training with Frozen Image Encoders and Large Language Models](https://arxiv.org/abs/2301.12597)，[demo](https://huggingface.co/spaces/Salesforce/BLIP2)，[doc](https://huggingface.co/docs/transformers/main/en/model_doc/blip-2) |  |  | | [code](https://github.com/salesforce/LAVIS/tree/main/projects/blip2)，[fine-tuing](https://github.com/salesforce/LAVIS)，[hugging face spaces](https://hf.co/spaces/Salesforce/BLIP2) |
| CodeGen2 | | | [codegen2 1B-16B](https://github.com/salesforce/CodeGen2) | [CodeGen2: Lessons for Training LLMs on Programming and Natural Languages](https://arxiv.org/abs/2305.02309) | 1 - 16 | [2048](https://arxiv.org/abs/2305.02309) | [Apache 2.0](https://github.com/salesforce/CodeGen2/blob/main/LICENSE)| 
| CogVLM | Vicuna-7B-v1.5，GLM，Llama2 | EVA2-CLIP-E | [modelscope](https://www.modelscope.cn/models/ZhipuAI/CogVLM)，[Huggingface](https://huggingface.co/THUDM/CogVLM) | [CogVLM: Visual Expert for Pretrained Language Models](https://arxiv.org/abs/2311.03079) | 17 |---| --- | [CogVLM Code](https://github.com/THUDM/CogVLM) |
| EMO |  |  |  |  |  |  |  |
| Emu2 |  |  | [Emu2](https://huggingface.co/BAAI/Emu2) | [Generative Multimodal Models are In-Context Learners](https://arxiv.org/abs/2312.13286)，[PageHome](https://baaivision.github.io/emu2/)，[Demo](https://huggingface.co/spaces/BAAI/Emu2) | 37 |---| --- | [Emu2 Code](https://github.com/baaivision/Emu/tree/main/Emu2) |
| GPT4 |  |  |  | [OpenAI GPT4](https://openai.com/research/gpt-4)，[GPT4_System_Card中文翻译](https://github.com/ArronAI007/ChatGPT-Summary/blob/main/GPT4/Official/GPT-4_System_Card_zh.md)，[GPT4_Technical_Report中文翻译](https://github.com/ArronAI007/ChatGPT-Summary/blob/main/GPT4/Official/GPT4_Technical_Report_zh.md)，[The Ultimate GPT-4 Guide](https://doc.clickup.com/37456139/d/h/13q28b-324/e2a22b0c164b1f9) | 
| GPT4Video |  |  |  | [GPT4Video: A Unified Multimodal Large Language Model for lnstruction-Followed Understanding and Safety-Aware Generation](https://arxiv.org/abs/2311.16511)，[HomePage](https://gpt4video.github.io) |  |  |  |  |
| LaVIN | LLaMA | ViT-L |  | [Cheap and Quick: Efficient Vision-Language Instruction Tuning for Large Language Models](https://arxiv.org/pdf/2305.15023.pdf)，[blog](https://mp.weixin.qq.com/s/MRLYk1b7VJ_b6OmJ9mzkdw) | 7，13 |  | [LaVIN Code](https://github.com/luogen1996/LaVIN) |
| LLaVA |  |  |  | [Visual Instruction Tuning](https://arxiv.org/pdf/2304.08485.pdf)，[introduce](https://llava-vl.github.io/) |  |  |  | |
| LTX Studio |  |  |  | [LTX Studio](https://ltx.studio/) |  |  |  |
| UniDiffuser |  |  |  | [One Transformer Fits All Distributions in Multi-Modal Diffusion at Scale](https://ml.cs.tsinghua.edu.cn/diffusion/unidiffuser.pdf) |  |  |  | [UniDiffuser Code](https://github.com/thu-ml/unidiffuser) |
| Video-LLaMA |  |  |  | [Video-LLaMA: An Instruction-tuned Audio-Visual Language Model for Video Understanding](https://arxiv.org/abs/2306.02858) |  |  |  | |
| VisCPM |  |  |  | [VisCPM Blog](https://mp.weixin.qq.com/s/Fgfbs1vV7RF6kpyk4bfIYw) |  |  |  | [VisCPM Code](https://github.com/OpenBMB/VisCPM) |
| X-LLM |  |  |  | [X-LLM: Bootstrapping Advanced Large Language Models by Treating Multi-Modalities as Foreign Languages](https://arxiv.org/abs/2305.04160)，[项目主页](https://x-llm.github.io/) |  |  |  | |
| Pika |  |  |  |  |  |  |  |
| Sora |  |  |  | [Sora](https://openai.com/sora) |  |  |  |
| SoraWebui |  |  |  | [SoraWebui](https://sorawebui.com/) |  |  | [SoraWebui Code](https://github.com/SoraWebui/SoraWebui) |

---


