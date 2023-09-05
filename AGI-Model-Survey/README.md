# AGI-Model-Survey

AGI Survey mainly includes LLM and AIGC, specifically including text generation model, image and video generation model, code generation model, music generation model, and multimodal model.

## Universal LLMs

### Universal LLMs for Text

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length | Licence | Code                                                                                                                |
| --- | --- | --- | --- | --- | --- | --- |-----------------------------------------------------------------------------------------------------------------------|
| Bloom | 2022/11 | [Bloom](https://huggingface.co/bigscience/bloom) | [BLOOM: A 176B-Parameter Open-Access Multilingual Language Model](https://arxiv.org/abs/2211.05100) | 176 | [2048](https://huggingface.co/bigscience/bloom) |  [OpenRAIL-M v1](https://huggingface.co/spaces/bigcode/bigcode-model-license-agreement) |                                                                                                                      |
| Cerebras-GPT | 2023/03 | [Cerebras-GPT](https://huggingface.co/cerebras)                                           | [Cerebras-GPT: A Family of Open, Compute-efficient, Large Language Models](https://www.cerebras.net/blog/cerebras-gpt-a-family-of-open-compute-efficient-large-language-models/) ([Paper](https://arxiv.org/abs/2304.03208)) | 0.111 - 13      | [2048](https://huggingface.co/cerebras/Cerebras-GPT-13B#model-details) | Apache 2.0         | [Cerebras-GPT-1.3B](https://github.com/slai-labs/get-beam/tree/main/examples/cerebras-gpt)                            |
| Dolly        | 2023/04 | [dolly-v2-12b](https://huggingface.co/databricks/dolly-v2-12b)                            | [Free Dolly: Introducing the World's First Truly Open Instruction-Tuned LLM](https://www.databricks.com/blog/2023/04/12/dolly-first-open-commercially-viable-instruction-tuned-llm)             | 3, 7, 12     | [2048](https://github.com/databrickslabs/dolly#dolly) | MIT                |                                                                                                                       |
| DLite | 2023/05 | [dlite-v2-1_5b](https://huggingface.co/aisquared/dlite-v2-1_5b) | [Announcing DLite V2: Lightweight, Open LLMs That Can Run Anywhere](https://medium.com/ai-squared/announcing-dlite-v2-lightweight-open-llms-that-can-run-anywhere-a852e5978c6e) | 0.124 - 1.5 | [1024](https://huggingface.co/aisquared/dlite-v2-1_5b/blob/main/config.json) | Apache 2.0         | [DLite-v2-1.5B](https://github.com/slai-labs/get-beam/tree/main/examples/dlite-v2)                                    |
| FastChat-T5 | 2023/04 | [fastchat-t5-3b-v1.0](https://huggingface.co/lmsys/fastchat-t5-3b-v1.0) | [We are excited to release FastChat-T5: our compact and commercial-friendly chatbot!](https://twitter.com/lmsysorg/status/1652037026705985537?s=20) | 3 | [512](https://huggingface.co/lmsys/fastchat-t5-3b-v1.0/blob/main/config.json) | Apache 2.0 |                                                                                                                       |
| Falcon | 2023/05 | [Falcon-40B](https://huggingface.co/tiiuae/falcon-40b), [Falcon-7B](https://huggingface.co/tiiuae/falcon-7b) | [The RefinedWeb Dataset for Falcon LLM: Outperforming Curated Corpora with Web Data, and Web Data Only](https://arxiv.org/abs/2306.01116) | 7, 40 | [2048](https://huggingface.co/tiiuae/falcon-7b/blob/main/config.json) | Apache 2.0 | 
| GPT-J-6B | 2023/06 | [GPT-J-6B](https://github.com/kingoflolz/mesh-transformer-jax/#gpt-j-6b), [GPT4All-J](https://github.com/nomic-ai/gpt4all#raw-model) | [GPT-J-6B: 6B JAX-Based Transformer](https://arankomatsuzaki.wordpress.com/2021/06/04/gpt-j/) | 6 | [2048](https://github.com/kingoflolz/mesh-transformer-jax/#gpt-j-6b) | Apache 2.0 |                                                                                                                       |
| GPT-NeoX-20B | 2022/04 | [GPT-NEOX-20B](https://huggingface.co/EleutherAI/gpt-neox-20b) | [GPT-NeoX-20B: An Open-Source Autoregressive Language Model](https://arxiv.org/abs/2204.06745) | 20 | [2048](https://huggingface.co/EleutherAI/gpt-neox-20b) | Apache 2.0 |                                                                                                                       |
| h2oGPT | 2023/05 | [h2oGPT](https://github.com/h2oai/h2ogpt) | [Building the World’s Best Open-Source Large Language Model: H2O.ai’s Journey](https://h2o.ai/blog/building-the-worlds-best-open-source-large-language-model-h2o-ais-journey/) | 12 - 20 | [256 - 2048](https://huggingface.co/h2oai) | Apache 2.0 |                                                                                                                       |
| LLaMA 2  | 2023 | [LLaMA 2 Weights](https://ai.meta.com/resources/models-and-libraries/llama-downloads/) | [Llama 2: Open Foundation and Fine-Tuned Chat Models](https://scontent-ham3-1.xx.fbcdn.net/v/t39.2365-6/10000000_662098952474184_2584067087619170692_n.pdf?_nc_cat=105&ccb=1-7&_nc_sid=3c67a6&_nc_ohc=qhK-ahCbkBMAX94XV2X&_nc_ht=scontent-ham3-1.xx&oh=00_AfDB7dN8momft9nkv8X0gqrZdEnKltVjPOxhKBm0XLRinA&oe=64BE66FF)      | 7 - 70       | [4096](https://scontent-ham3-1.xx.fbcdn.net/v/t39.2365-6/10000000_662098952474184_2584067087619170692_n.pdf?_nc_cat=105&ccb=1-7&_nc_sid=3c67a6&_nc_ohc=qhK-ahCbkBMAX94XV2X&_nc_ht=scontent-ham3-1.xx&oh=00_AfDB7dN8momft9nkv8X0gqrZdEnKltVjPOxhKBm0XLRinA&oe=64BE66FF)  | [Custom](https://github.com/facebookresearch/llama/blob/main/LICENSE) Free if you have under 700M users and you cannot use LLaMA outputs to train other LLMs besides LLaMA and its derivatives   | [HuggingChat](https://huggingface.co/blog/llama2#demo)     |  
| MPT-7B | 2023/05 | [MPT-7B](https://huggingface.co/mosaicml/mpt-7b), [MPT-7B-Instruct](https://huggingface.co/mosaicml/mpt-7b-instruct) | [Introducing MPT-7B: A New Standard for Open-Source, Commercially Usable LLMs](https://www.mosaicml.com/blog/mpt-7b) | 7 | [84k (ALiBi)](https://huggingface.co/mosaicml/mpt-7b#how-is-this-model-different) | Apache 2.0, CC BY-SA-3.0 |                                                                                                                       |
| MPT-30B | 2023/06 | [MPT-30B](https://huggingface.co/mosaicml/mpt-30b), [MPT-30B-instruct](https://huggingface.co/mosaicml/mpt-30b-instruct) | [MPT-30B: Raising the bar for open-source foundation models](https://www.mosaicml.com/blog/mpt-30b) | 30 | [8192](https://huggingface.co/mosaicml/mpt-30b/blob/main/config.json) | Apache 2.0, CC BY-SA-3.0 | [MPT 30B inference code using CPU](https://github.com/abacaj/mpt-30B-inference) |
| Open Assistant (Pythia family) | 2023/03 | [OA-Pythia-12B-SFT-8](https://huggingface.co/OpenAssistant/pythia-12b-sft-v8-7k-steps), [OA-Pythia-12B-SFT-4](https://huggingface.co/OpenAssistant/oasst-sft-4-pythia-12b-epoch-3.5), [OA-Pythia-12B-SFT-1](https://huggingface.co/OpenAssistant/oasst-sft-1-pythia-12b) | [Democratizing Large Language Model Alignment](https://arxiv.org/abs/2304.07327) | 12     | [2048](https://huggingface.co/OpenAssistant/pythia-12b-sft-v8-7k-steps/blob/main/config.json)  | Apache 2.0                | [Pythia-2.8B](https://github.com/slai-labs/get-beam/tree/main/examples/pythia)                                        |
| OpenLLaMA | 2023/05 | [open_llama_3b](https://huggingface.co/openlm-research/open_llama_3b), [open_llama_7b](https://huggingface.co/openlm-research/open_llama_7b), [open_llama_13b](https://huggingface.co/openlm-research/open_llama_13b) | [OpenLLaMA: An Open Reproduction of LLaMA](https://github.com/openlm-research/open_llama) | 3, 7 | [2048](https://huggingface.co/h2oai) | Apache 2.0 | [OpenLLaMA-7B-Preview_200bt](https://github.com/slai-labs/get-beam/tree/main/examples/openllama)                      |
| Pythia       | 2023/04 | [pythia 70M - 12B](https://github.com/EleutherAI/pythia)                                   | [Pythia: A Suite for Analyzing Large Language Models Across Training and Scaling](https://arxiv.org/abs/2304.01373)                                                                    | 0.07 - 12       | [2048](https://arxiv.org/pdf/2304.01373.pdf) | Apache 2.0         |                                                                                                                       |
| RedPajama-INCITE | 2023/05 | [RedPajama-INCITE](https://huggingface.co/togethercomputer) | [Releasing 3B and 7B RedPajama-INCITE family of models including base, instruction-tuned & chat models](https://www.together.xyz/blog/redpajama-models-v1) | 3 - 7 | [2048](https://huggingface.co/togethercomputer/RedPajama-INCITE-Instruct-7B-v0.1/blob/157bf3174feebb67f37e131ea68f84dee007c687/config.json#L13) | Apache 2.0 | [RedPajama-INCITE-Instruct-3B-v1](https://github.com/slai-labs/get-beam/tree/main/examples/redpajama-incite-instruct) |
| RWKV         | 2021/08| [RWKV, ChatRWKV](https://github.com/BlinkDL/RWKV-LM#rwkv-parallelizable-rnn-with-transformer-level-llm-performance-pronounced-as-rwakuv-from-4-major-params-r-w-k-v) | [The RWKV Language Model (and my LM tricks)](https://github.com/BlinkDL/RWKV-LM)                                           | 0.1 - 14      | [infinity (RNN)](https://github.com/BlinkDL/RWKV-LM#rwkv-parallelizable-rnn-with-transformer-level-llm-performance-pronounced-as-rwakuv-from-4-major-params-r-w-k-v) | Apache 2.0         |                                                                                                                       |
| StableLM-Alpha | 2023/04 | [StableLM-Alpha](https://github.com/Stability-AI/StableLM#stablelm-alpha) | [Stability AI Launches the First of its StableLM Suite of Language Models](https://stability.ai/blog/stability-ai-launches-the-first-of-its-stablelm-suite-of-language-models) | 3 - 65 | [4096](https://github.com/Stability-AI/StableLM#stablelm-alpha) | CC BY-SA-4.0 |                                                                                                                       |
| T5           | 2019/10 |[T5 & Flan-T5](https://github.com/google-research/t5x/blob/main/docs/models.md#flan-t5-checkpoints), [Flan-T5-xxl (HF)](https://huggingface.co/google/flan-t5-xxl)      | [Exploring the Limits of Transfer Learning with a Unified Text-to-Text Transformer](https://github.com/google-research/text-to-text-transfer-transformer#released-model-checkpoints) | 0.06 - 11       | [512](https://discuss.huggingface.co/t/does-t5-truncate-input-longer-than-512-internally/3602) | Apache 2.0         | [T5-Large](https://github.com/slai-labs/get-beam/tree/main/examples/t5)                                               |
| UL2          | 2022/10 | [UL2 & Flan-UL2](https://github.com/google-research/google-research/tree/master/ul2#checkpoints), [Flan-UL2 (HF)](https://huggingface.co/google/flan-ul2)          | [UL2 20B: An Open Source Unified Language Learner](https://ai.googleblog.com/2022/10/ul2-20b-open-source-unified-language.html)                                                       | 20             | [512, 2048](https://huggingface.co/google/flan-ul2#tldr) | Apache 2.0         |                                                                                                                       |

---

### Universal LLMs for Code  

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length                                                                         | Licence | Code                                                                                    |
| --- | --- | --- | --- | --- |----------------------------------------------------------------------------------------| --- |-------------------------------------------------------------------------------------------|
| Baldur |  |  | [Baldur: Whole-Proof Generation and Repair with Large Language Models](https://arxiv.org/abs/2303.04910) |  |  |  |  |
| CodeGeeX |  |  | [CodeGeeX: A Pre-Trained Model for Code Generation with Multilingual Evaluations on HumanEval-X](https://arxiv.org/pdf/2303.17568.pdf) |  |  |  | [CodeGeeX Code](https://github.com/THUDM/CodeGeeX) |
| CodeGeeX2-6B |  |  | [CodeGeeX2-6B Blog](https://mp.weixin.qq.com/s/roQSCo-7s361P3TmJjjZjA) |  |  |  | [CodeGeeX2-6B Code](https://github.com/THUDM/CodeGeeX2) |
| CodeGen2 | 2023/04 | [codegen2 1B-16B](https://github.com/salesforce/CodeGen2) | [CodeGen2: Lessons for Training LLMs on Programming and Natural Languages](https://arxiv.org/abs/2305.02309) | 1 - 16 | [2048](https://arxiv.org/abs/2305.02309) | [Apache 2.0](https://github.com/salesforce/CodeGen2/blob/main/LICENSE)|                                                                                           |
| CodeGen2.5 | 2023/07 | [CodeGen2.5-7B-multi](https://huggingface.co/Salesforce/codegen25-7b-multi) | [CodeGen2.5: Small, but mighty](https://blog.salesforceairesearch.com/codegen25/) | 7 | [2048](https://huggingface.co/Salesforce/codegen25-7b-multi/blob/main/config.json) | [Apache 2.0](https://huggingface.co/Salesforce/codegen25-7b-multi/blob/main/README.md) | 
| Code Llama  | 2023 | [Inference Code for CodeLlama models]([https://ai.meta.com/resources/models-and-libraries/llama-downloads/](https://github.com/facebookresearch/codellama)) | [Code Llama: Open Foundation Models for Code](https://ai.meta.com/research/publications/code-llama-open-foundation-models-for-code/)     | 7 - 34       | [4096](https://scontent-zrh1-1.xx.fbcdn.net/v/t39.2365-6/369856151_1754812304950972_1159666448927483931_n.pdf?_nc_cat=107&ccb=1-7&_nc_sid=3c67a6&_nc_ohc=wURKmnWKaloAX-ib5XW&_nc_ht=scontent-zrh1-1.xx&oh=00_AfAN1GB2K_XwIz54PqXTr-dhilI3CfCwdQoaLMyaYEEECg&oe=64F0A68F)  | [Custom](https://github.com/facebookresearch/llama/blob/main/LICENSE) Free if you have under 700M users and you cannot use LLaMA outputs to train other LLMs besides LLaMA and its derivatives   | [HuggingChat](https://huggingface.co/blog/codellama) | 
| CodeT5 |  |  | [CodeT5+: Open Code Large Language Models for Code Understanding and Generation](https://arxiv.org/abs/2305.07922) |  |  |  |  |
| CodeT5+ | 2023/05 | [CodeT5+](https://github.com/salesforce/CodeT5/tree/main/CodeT5+)     | [CodeT5+: Open Code Large Language Models for Code Understanding and Generation](https://arxiv.org/abs/2305.07922) | 0.22 - 16 | [512](https://arxiv.org/abs/2305.07922)                                                                                | [BSD-3-Clause](https://github.com/salesforce/CodeT5/blob/main/LICENSE.txt)                                                           | [Codet5+-6B](https://github.com/slai-labs/get-beam/tree/main/examples/codeT5%2B)          |
| Cursor |  |  | [官网地址](https://www.cursor.so/) |  |  |  |  |
| DeciCoder-1B | 2023/08 | [DeciCoder-1B](https://huggingface.co/Deci/DeciCoder-1b#how-to-use) | [Introducing DeciCoder: The New Gold Standard in Efficient and Accurate Code Generation](https://deci.ai/blog/decicoder-efficient-and-accurate-code-generation-llm/) | 1.1 | [2048](https://huggingface.co/Deci/DeciCoder-1b#model-architecture) | Apache 2.0 |  [DeciCoder Demo](https://huggingface.co/spaces/Deci/DeciCoder-Demo)|
| GPT-Engineer |  |  | [GPT-Engineer Blog](https://mp.weixin.qq.com/s/rtsVsQbh7NnTh5vjgNMJHQ) |  |  |  | [GPT-Engineer Code](https://github.com/AntonOsika/gpt-engineer) |
| Replit Code | 2023/05 | [replit-code-v1-3b](https://huggingface.co/replit/replit-code-v1-3b) | [Training a SOTA Code LLM in 1 week and Quantifying the Vibes — with Reza Shabani of Replit](https://www.latent.space/p/reza-shabani#details) | 2.7 | [infinity? (ALiBi)](https://huggingface.co/replit/replit-code-v1-3b#model-description) | CC BY-SA-4.0 | [Replit-Code-v1-3B](https://github.com/slai-labs/get-beam/tree/main/examples/replit-code) |
| SantaCoder | 2023/01 | [santacoder](https://huggingface.co/bigcode/santacoder) |[SantaCoder: don't reach for the stars!](https://arxiv.org/abs/2301.03988) | 1.1 | [2048](https://huggingface.co/bigcode/santacoder/blob/main/README.md#model-summary)                | [OpenRAIL-M v1](https://huggingface.co/spaces/bigcode/bigcode-model-license-agreement) | [SantaCoder](https://github.com/slai-labs/get-beam/tree/main/examples/santacoder)         |
| StableCode |  | [4k代码补全模型](https://huggingface.co/stabilityai/stablecode-completion-alpha-3b-4k)，[指令模型](https://huggingface.co/stabilityai/stablecode-instruct-alpha-3b)，[16k代码补全模型](https://huggingface.co/stabilityai/stablecode-completion-alpha-3b) | [中文blog](https://mp.weixin.qq.com/s/aAGMwSyT7Kgj3FLbzebJaQ)，[英文blog](https://stability.ai/blog/stablecode-llm-generative-ai-coding) |  |  |  |  |
| StarCoder | 2023/05 | [starcoder](https://huggingface.co/bigcode/starcoder) | [StarCoder: A State-of-the-Art LLM for Code](https://huggingface.co/blog/starcoder), [StarCoder: May the source be with you!](https://drive.google.com/file/d/1cN-b9GnWtHzQRoE7M7gAEyivY0kl4BYs/view)，[StarCoder Blog](https://mp.weixin.qq.com/s/f-WwzLcEO-ZJczI-_bZh3Q) | 1.1-15 | [8192](https://huggingface.co/bigcode/starcoder#model-summary)                         | [OpenRAIL-M v1](https://huggingface.co/spaces/bigcode/bigcode-model-license-agreement) |                                                                                           |
| StarChat Alpha | 2023/05 | [starchat-alpha](https://huggingface.co/HuggingFaceH4/starchat-alpha) | [Creating a Coding Assistant with StarCoder](https://huggingface.co/blog/starchat-alpha) | 16 | [8192](https://huggingface.co/bigcode/starcoder#model-summary)  | [OpenRAIL-M v1](https://huggingface.co/spaces/bigcode/bigcode-model-license-agreement) |                                                                                           |
| XGen-7B | 2023/06 | [XGen-7B-8K-Base](https://huggingface.co/Salesforce/xgen-7b-8k-base) | [Long Sequence Modeling with XGen: A 7B LLM Trained on 8K Input Sequence Length](https://blog.salesforceairesearch.com/xgen/) | 7 | [8192](https://huggingface.co/Salesforce/xgen-7b-8k-base/blob/main/config.json) | [Apache 2.0](https://github.com/salesforce/xgen/blob/main/LICENSE) | 

---

### Universal LLMs for Picture/Video 

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length                                                                         | Licence | Code                                                                                    |
| --- | --- | --- | --- | --- |----------------------------------------------------------------------------------------| --- |-------------------------------------------------------------------------------------------|
| Bing Image Creator |  |  | [Bing Image Creator Blog](https://techcrunch.com/2023/03/21/microsoft-brings-openais-dall-e-image-creator-to-the-new-bing/) |  |  |  |  |
| BlenderGPT |  |  |  |  |  |  | [BlenderGPT Code](https://github.com/gd3kr/BlenderGPT)  |
| CHAMPAGNE |  |  | [CHAMPAGNE: Learning Real-world Conversation from Large-Scale Web Videos](https://arxiv.org/pdf/2303.09713.pdf)  |  |  |  | [CHAMPAGNE Code](https://seungjuhan.me/champagne) |
| CodeGen2 | 2023/04 | [codegen2 1B-16B](https://github.com/salesforce/CodeGen2) | [CodeGen2: Lessons for Training LLMs on Programming and Natural Languages](https://arxiv.org/abs/2305.02309) | 1 - 16 | [2048](https://arxiv.org/abs/2305.02309) | [Apache 2.0](https://github.com/salesforce/CodeGen2/blob/main/LICENSE)| 
| Consistency Models |  |  | [Consistency Models](https://arxiv.org/abs/2303.01469)，[Consistency Models Blog](https://hub.baai.ac.cn/view/25445) |  |  |  | [Consistency Models Code](https://github.com/openai/consistency_models) |
| ControlNet |  |  | [Adding Conditional Control to Text-to-Image Diffusion Models](https://arxiv.org/pdf/2302.05543.pdf)，[ControlNet Blog](https://mp.weixin.qq.com/s/k8rE9GrF97E-0TKJhih9kw)  |  |  |  | [ControlNet Code](https://github.com/lllyasviel/ControlNet) |
| Firefly |  |  | [Firefly Blog](https://www.theverge.com/2023/3/21/23648315/adobe-firefly-ai-image-generator-announced) |  |  |  |  |
| Genmo Chat |  |  | [Genmo Chat Blog](https://www.genmo.ai/)  |  |  |  |  |
| Gen-1 |  |  | [Structure and Content-Guided Video Synthesis with Diffusion Models](https://arxiv.org/pdf/2302.03011)，[Gen-1 site](https://research.runwayml.com/gen1) |  |  |  |  |
| Stable Diffusion |  |  | [High-resolution image reconstruction with latent diffusion models from human brain activity](https://sites.google.com/view/stablediffusion-with-brain/)，[Stable Diffusion Blog](https://mp.weixin.qq.com/s/gIwj2eqNph8jHWOhYYEXIg) |  |  |  |  |
| SegGPT |  |  | [SegGPT: Segmenting Everything In Context](https://arxiv.org/pdf/2304.03284.pdf) |  |  |  |  |
| text-to-video |  | [模型地址 ](https://modelscope.cn/models/damo/text-to-video-synthesis/summary) |  |  |  |  |  |
| NUWA-XL |  |  | [NUWA-XL: Diffusion over Diffusion for eXtremely Long Video Generation](https://arxiv.org/pdf/2303.12346.pdf)，[NUWA-XL Blog](https://msra-nuwa.azurewebsites.net/#/)  |  |  |  |  |

---  

### Universal LLMs for Audio

## 语音生成

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
 
| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length                                                                         | Licence | Code                                                                                    |
| --- | --- | --- | --- | --- |----------------------------------------------------------------------------------------| --- |-------------------------------------------------------------------------------------------|
| BLIP-2 |  |  | [paper](https://arxiv.org/abs/2301.12597)，[demo](https://huggingface.co/spaces/Salesforce/BLIP2)，[doc](https://huggingface.co/docs/transformers/main/en/model_doc/blip-2) |  |  | | [code](https://github.com/salesforce/LAVIS/tree/main/projects/blip2)，[fine-tuing](https://github.com/salesforce/LAVIS)，[hugging face spaces](https://hf.co/spaces/Salesforce/BLIP2) |
| CodeGen2 | 2023/04 | [codegen2 1B-16B](https://github.com/salesforce/CodeGen2) | [CodeGen2: Lessons for Training LLMs on Programming and Natural Languages](https://arxiv.org/abs/2305.02309) | 1 - 16 | [2048](https://arxiv.org/abs/2305.02309) | [Apache 2.0](https://github.com/salesforce/CodeGen2/blob/main/LICENSE)| 
| LLaVA |  |  | [Visual Instruction Tuning](https://arxiv.org/pdf/2304.08485.pdf)，[introduce](https://llava-vl.github.io/) |  |  |  | |
| UniDiffuser |  |  | [One Transformer Fits All Distributions in Multi-Modal Diffusion at Scale](https://ml.cs.tsinghua.edu.cn/diffusion/unidiffuser.pdf) |  |  |  | [UniDiffuser Code](https://github.com/thu-ml/unidiffuser) |
| Video-LLaMA |  |  | [Video-LLaMA: An Instruction-tuned Audio-Visual Language Model for Video Understanding](https://arxiv.org/abs/2306.02858) |  |  |  | |
| VisCPM |  |  | [VisCPM Blog](https://mp.weixin.qq.com/s/Fgfbs1vV7RF6kpyk4bfIYw) |  |  |  | [VisCPM Code](https://github.com/OpenBMB/VisCPM) |
| X-LLM |  |  | [X-LLM: Bootstrapping Advanced Large Language Models by Treating Multi-Modalities as Foreign Languages](https://arxiv.org/abs/2305.04160)，[项目主页](https://x-llm.github.io/) |  |  |  | |

---

## Domain LLMs
## LLM领域大模型

【论文】[[垂直领域大模型的一些思考及开源模型汇总](https://mp.weixin.qq.com/s/HiGkSwbGeo4sPZvQeKCJfQ)]，[[大模型时代-行业落地的再思考](https://mp.weixin.qq.com/s/wSQSjO_0OmIg2kBZUuXA4Q)]

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

                                                                                                           
### Domain LLMs for Medical

【医疗领域大模型的幻觉问题分析】[[blog](https://mp.weixin.qq.com/s/1o4u0Em0fFk9YndTaF2I7A)]

【基于中文金融知识的 LLaMA 系微调模型的智能问答系统：LLaMA大模型训练微调推理等详细教学】[[blog](https://mp.weixin.qq.com/s/lrKPUcS9GkSS20-Jda-8bA)]

【中文多模态医学大模型智能分析X光片，实现影像诊断，完成医生问诊多轮对话】[[blog](https://mp.weixin.qq.com/s/Spb_dbsHRyP9EvUaMYgHxw)]

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

### Domain LLMs for Finance

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length | Licence | Code                                                                                                                |
| --- | --- | --- | --- | --- | --- | --- |-----------------------------------------------------------------------------------------------------------------------|
| FinGPT |  |  | [FinGPT: Open-Source Financial Large Language Models](https://arxiv.org/pdf/2306.06031v1.pdf)，[FinGPT Blog](https://mp.weixin.qq.com/s/A9euFin675nxGGciiX6rJQ) |  |  |  | [FinGPT Code](https://github.com/ai4finance-foundation/fingpt) |     
| FinTuo |  |  |  |  |  |  | [FinTuo Code](https://github.com/qiyuan-chen/FinTuo-Chinese-Finance-LLM) |     

### Domain LLMs for Environment

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length | Licence | Code                                                                                                                |
| --- | --- | --- | --- | --- | --- | --- |-----------------------------------------------------------------------------------------------------------------------|
| NowcastNet |  |  | [Skilful nowcasting of extreme precipitation with NowcastNet](https://www.nature.com/articles/s41586-023-06184-4)，[NowcastNet Blog](https://mp.weixin.qq.com/s/Aygm03CdA0zFNf9F3_JU5A) |  |  |  |  |      

### Domain LLMs for Network Security

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length | Licence | Code                                                                                                                |
| --- | --- | --- | --- | --- | --- | --- |-----------------------------------------------------------------------------------------------------------------------|
| FraudGPT |  |  | [FraudGPT Blog](https://mp.weixin.qq.com/s/OtLNybsbxDlbVb-cs4Zk8g) |  |  |  |  |      

### Domain LLMs for Education

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length | Licence | Code                                                                                                                |
| --- | --- | --- | --- | --- | --- | --- |-----------------------------------------------------------------------------------------------------------------------|
| EduChat |  |  |  |  |  |  | [EduChat Code](https://github.com/icalk-nlp/EduChat) |       

### Domain LLMs for Traffic

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length | Licence | Code                                                                                                                |
| --- | --- | --- | --- | --- | --- | --- |-----------------------------------------------------------------------------------------------------------------------|
| TransGPT |  |  | [TransGPT Blog](https://mp.weixin.qq.com/s/WvzyjHqI0lOGIyPlCIFNQg) |  |  |  | [TransGPT Code](https://github.com/DUOMO/TransGPT) |       

### Domain LLMs for Other

| Language Model | Release Date | Checkpoints | Paper/Blog | Params (B) | Context Length | Licence | Code                                                                                                                |
| --- | --- | --- | --- | --- | --- | --- |-----------------------------------------------------------------------------------------------------------------------|
| Panda LLM |  |  | [Panda LLM: Training Data and Evaluation for Open-Sourced Chinese Instruction-Following Large Language Models](https://arxiv.org/pdf/2305.03025v1.pdf)，[Panda LLM Blog](https://mp.weixin.qq.com/s/IsWSPAvwgT263wjO7TYTZQ) |  |  |  | [Panda LLM Code](https://github.com/dandelionsllm/pandallm) |     
  
