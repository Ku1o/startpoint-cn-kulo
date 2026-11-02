# 本机客户端工具后台入口

此目录提供可独立使用的 Windows 后台执行入口。项目构建脚本无需导入它；由调用方从最外层包裹完整命令，子进程继承独立桌面。

Codex 在本机 Windows 执行 AIR/ADL 检查时，必须从此入口包裹完整最外层命令。适用于源仓、独立 worktree、临时脚本、离线 stage/Timer/trace，以及构建或测试间接启动 ADL；不以是否制作 APK/IPA 判断是否使用。源脚本保留普通 `subprocess.run/Popen`，其子进程继承外层后台桌面。

在实际源码或 worktree 目录运行，例如：

```powershell
python -B <repo>/tools/client-background/run_background.py --timeout 180 -- python -B -u <检查脚本> <原参数>
```

实际使用时替换功能路径及其参数。也可用 `--cwd <repo>` 明确工作目录；默认保留调用者工作目录、环境和参数。入口将整条命令放到独立且不切换前台的 Windows 桌面，普通子进程与 ADL 通过其原有启动代码运行。

正常结束透传退出码和标准输出/错误，整条命令超时返回124，中断返回130，并回收受管进程树；桌面创建失败直接报错。输出在命令结束后回传，超时只能保留已 flush 的输出，Python 诊断建议显式使用 `-u`。此入口不会替内部构建脚本重建其尚未写出的日志文件，不修改 AIR 启动图或许可证。

启动前核对最外层命令已使用此入口，保持原参数、cwd/env、日志路径和实际所需超时。失败或超时后禁止裸跑原命令回退到当前桌面。`initialWindow.visible=false`、输出重定向、控制台隐藏不隔离 AIR 自身启动画面。明确要求可见交互或 GPU/完整客户端验收时，遵循该任务要求并单独报告验证范围。

验证命令：

```powershell
python -B <repo>/tools/client-background/run_background.py --timeout 90 -- python -B -m unittest discover -s <repo>/tools/client-background/tests -p "test_*.py" -v
```

迁移前像和本批核验记录：`<workspace>/work/local-client-background-extract-20261017/`。普通构建检查与受控 AIR 夹具验证不代表完整客户端、GPU、设备或游戏功能验收。
