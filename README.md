# Kimodo API Bridge

独立 Blender 插件，基于 Lewdineer 的 Kimodo Blender Bridge，采用 GPL-2.0-or-later

需要先在https://github.com/spawner1145/kimodo_inference_server这个项目部署并开启api对接使用

1. 先启动 `inference_server` 中的服务。
2. 在 Blender 的 3D 视图按 **N → Kimodo → 连接**。
3. 填写 **API 地址**，本机默认 `http://127.0.0.1:6600`；远程服务器填写它的地址。服务端启用认证时填写相同的 **API 令牌**。

连接面板的 **服务管理面板** 按钮会打开该 API 地址下的中文 WebUI，可以管理模型下载、默认配置、端口和显存选项。服务端更换端口并重启后，断开插件连接，修改 API 地址再重新连接。插件明确指定的采样设置优先于服务端默认值。
4. 选择 **服务端模型**和**文本编码器**，点击 **连接 API**；列表会从服务端刷新，缺失权重的条目标为“未下载”。支持 FP32、ConvRot INT8，以及 AWQ、原插件 NF4、原始 BF16 编码器配置。
5. 在 **生成动作** 中输入中文 → **中译英** → 设置时长、种子 → **生成动作**。完成后会下载 BVH 并导入 Blender。
6. **推理设置**可调整扩散步数、引导强度、**动作块交换数量**和**文本块交换数量**。块交换 `-1` 跟随服务端，`0` 关闭，正数减少常驻显存但通常更慢；v1.2 动作模型和 Llama 编码器均最多 32 块。当前本机未安装后处理扩展时，动作后处理选项会禁用。
7. **时间轴**模式支持多提示词拼接和各片段独立种子。**重定向**面板可将源骨架动作映射到自己的角色，然后烘焙动画。

**断开连接**只断开 Blender，服务进程继续运行。取消生成会向服务端提交取消请求。切换 .blend 文件或禁用插件时也会取消当前客户端任务，避免把旧动作导入新场景。

API 地址和令牌保存在插件偏好设置，不会写入 .blend。生成参数、提示词和骨骼映射随场景保存。远端的生成文件通过 HTTP 下载，不要求共享磁盘路径。

服务端配置覆盖 SOMA/SMPLX/G1；当前实际下载并联调的是 SOMA v1.2 FP32/INT8 与 AWQ 编码器。完整 NF4 与其他动作模型需要先在服务端显式下载，界面不会偷偷触发下载。SMPLX/G1 可导入并手动/同名骨骼重定向；场景约束编辑器当前仅有 SOMA 映射，不能跨骨架直接使用。

中文界面跟随 Blender 的简体中文界面翻译开关；词条在 `locales/zh_HANS.json`。中译英参考 WeiLin-Comfyui-Tools，使用阿里巴巴网页翻译，失败后尝试有道，无需 API Key；在线接口可能变更或限流。点击翻译时才发送提示词，支持全部片段翻译和还原中文。

本机安装模块沿用 `kimodo_blender_bridge`，更新时替换原插件，不要同时启用旧版本与本版本。便携安装包中的顶层目录也使用此模块名。

原项目：https://github.com/lewdineer/Kimodo_Blender_Bridge

## 上传 GitHub

本文件夹可作为独立插件仓库上传。保留 `.gitignore`、全部 Python 源码、`locales/zh_HANS.json`、README 和许可文件；`.gitignore` 已排除 Python 缓存、虚拟环境、Blender 工程及备份、生成动画、模型、日志、本机凭据与打包文件。发布给 Blender 安装的 ZIP 应以 `kimodo_blender_bridge/` 为顶层目录；若直接复制安装，将本目录复制并命名为 `kimodo_blender_bridge`，放入 Blender 的 `scripts/addons` 后启用。

模型下载由服务端 WebUI 管理；ConvRot INT8 已预设为公开 ModelScope 仓库，无需把权重放入插件仓库。
