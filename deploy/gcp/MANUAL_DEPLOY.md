# 手动部署指南（通过浏览器 SSH）

由于 Windows SSH 客户端的问题，我们可以通过浏览器 SSH 手动执行部署。

## 步骤 1: 准备部署文件

在**浏览器 SSH 终端**中执行：

```bash
# 创建目录
mkdir -p /tmp/taoquant-deploy
cd /tmp/taoquant-deploy

# 我会提供文件内容，你复制粘贴创建文件
```

## 步骤 2: 创建部署脚本

我会逐步提供文件内容，你在浏览器 SSH 中创建文件。

或者，如果你有 Git，可以直接 clone：

```bash
# 如果有 Git 仓库
git clone YOUR_REPO_URL /tmp/taoquant-source
cd /tmp/taoquant-source
```

## 步骤 3: 执行部署

```bash
cd /tmp/taoquant-deploy
chmod +x deploy.sh test_deployment.sh verify_live.sh
sudo ./deploy.sh all
```

---

**或者，我可以尝试另一种方法：使用 rsync 或直接通过 SSH 执行命令。**

请告诉我你想用哪种方式：
1. 通过浏览器 SSH 手动执行（我会提供命令）
2. 我继续尝试修复 Windows SSH 客户端问题
3. 使用其他工具（如 WinSCP）
