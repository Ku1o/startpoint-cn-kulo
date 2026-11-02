# 本地语音实验环境重建资料

`requirements.freeze.txt` 记录原环境的 98 个精确包版本，Python 为 3.13.14。`model-inputs.json` 保存基础模型、语音 tokenizer 和 ASR 文件的大小与 SHA-256。它们是复现输入记录，不代表这些历史版本永远可下载，也不代表已经在新电脑完成重建。

## 重装环境

在仓外新建虚拟环境。原 CUDA 12.8 构建来源为 `https://download.pytorch.org/whl/cu128`，先在该索引确认版本可用，再安装 `torch==2.11.0+cu128` 与 `torchaudio==2.11.0+cu128`，再用同一解释器执行 `python -m pip install -r requirements.freeze.txt`。是否适合当前显卡和驱动必须按实际环境核对，不修改全局 Python。

基础模型来源为 `Qwen/Qwen3-TTS-12Hz-1.7B-Base`，tokenizer 来源为 `Qwen/Qwen3-TTS-Tokenizer-12Hz`。原模型快照提交号未保存，因此下载后需用清单核对文件内容，不能把最新同名模型直接称为原输入。

ASR 使用 `Systran/faster-whisper-small`，本机快照为 `536b0662742c02347bc0e980a01041f333bce120`。另一次转写使用 `dropbox-dash/faster-whisper-large-v3-turbo` 的 `0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf`；后者不属于本清单中的已安装 small 模型。

## 自制成果与基础模型分开

角色微调参数、说话人特征、筛选后的素材清单、自编训练器和采用的语音属于项目成果，不随可重装基础模型退出。历史中秋稻穗实验采用 LoRA rank 16，训练器需要保留残差音频码本的直接对齐交叉熵修正；仅训练损失下降不能证明读音、表演或声音质量通过。

训练器参考固定于 Qwen3-TTS 提交 `022e286b98fbec7e1e916cb940cdf532cd9f488e`。既有实验的最佳参数、后续采用语音和不同阶段的试听须按各自记录选择，不把实验权重自动当成最终游戏语音。

来源：[Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)、[PyTorch 安装说明](https://pytorch.org/get-started/locally/)。素材来源、许可和听感验收应随具体角色工程保留。
