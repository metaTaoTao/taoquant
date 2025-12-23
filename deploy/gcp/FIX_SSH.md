# 修复 SSH 密钥认证问题

你的公钥文件存在，但可能还没有添加到 GCP 服务器。以下是两种解决方案：

## 方案 1: 通过 GCP Console 添加公钥（推荐）

1. **登录 GCP Console**
   - 访问：https://console.cloud.google.com/
   - 进入 Compute Engine → VM instances

2. **编辑 VM 实例**
   - 选择你的 VM 实例（IP: 34.158.55.6）
   - 点击 "Edit"（编辑）按钮

3. **添加 SSH 密钥**
   - 展开 "SSH Keys" 部分
   - 点击 "Add Item"
   - 复制以下公钥内容并粘贴：

```
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQD32rHklYcVySn427fEtQJVpBtxszCDekTv/pYe5srnXEQI5VP5xQznrvwE6bIZTDa7x6WkvZLTp8nYvzD8wMXSoNiPynl6rZ4R7IiPpsQ0sRynAu6lZke2FdlKpWBq4yMBpWhGxwP+wf/glquLhhcWlSOBkoGKzVYSnX6SHrHVjgqN4J6JwHsPp77yZJECBN8sANrdURr9yHca+rxnnAG3El3GMkuRKsSgWWWgUztbGZywZybuOHM+0sQe02OfN8x3VwONbAdutZws08PS/DhCax64EYI3nanqKacZ24zOt0OFFZpjj2IVfIB22Pxd5U9r9hKMbYEnogpktGJjwP5PNgydCA4Tjoa7ONxSlC3lwtXsLZIBNYPpJSOGpuQ5NF5Cu/jb1j+S1jj4G1YPDeuJ7a/IF1iNIiat5wKQi8skfp4IUXYF/KF0bbzphkX/IKEj3Wv+7V/LGdBSjatZk32TBLWYiF/UOvuTUUE+QNokKcP2kdjkacdVF8tHcmzYrSi4ONbDMcRiGIUyubdI62FqaPjjEeLSb8zZov4zq+ffR0KWAhvliQocS4o6/XAR8hTUerzLzwS4Ny9iCgD/ycPVwvh6AyIzEiKPM4gDlcJl1g4owAaQOjCYUfT/Jl2FTAhZOyvUYy2daueYMeMfXfUzVOtKzPh3HnW2VsrtGlZXmw== cursor-gcp
```

4. **保存更改**
   - 点击 "Save" 保存

5. **测试连接**
   ```powershell
   ssh -i "C:\Users\uncczhangtao\.ssh\id_rsa" liandongtrading@34.158.55.6 "echo 'Connection successful'"
   ```

## 方案 2: 使用密码认证（临时方案）

如果服务器允许密码认证，你可以：

1. **直接使用密码连接**（脚本会提示输入密码）
2. **或者先手动 SSH 连接，然后添加公钥**：

```powershell
# 1. 手动 SSH 连接（会提示输入密码）
ssh liandongtrading@34.158.55.6

# 2. 在服务器上执行以下命令添加公钥
mkdir -p ~/.ssh
echo "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQD32rHklYcVySn427fEtQJVpBtxszCDekTv/pYe5srnXEQI5VP5xQznrvwE6bIZTDa7x6WkvZLTp8nYvzD8wMXSoNiPynl6rZ4R7IiPpsQ0sRynAu6lZke2FdlKpWBq4yMBpWhGxwP+wf/glquLhhcWlSOBkoGKzVYSnX6SHrHVjgqN4J6JwHsPp77yZJECBN8sANrdURr9yHca+rxnnAG3El3GMkuRKsSgWWWgUztbGZywZybuOHM+0sQe02OfN8x3VwONbAdutZws08PS/DhCax64EYI3nanqKacZ24zOt0OFFZpjj2IVfIB22Pxd5U9r9hKMbYEnogpktGJjwP5PNgydCA4Tjoa7ONxSlC3lwtXsLZIBNYPpJSOGpuQ5NF5Cu/jb1j+S1jj4G1YPDeuJ7a/IF1iNIiat5wKQi8skfp4IUXYF/KF0bbzphkX/IKEj3Wv+7V/LGdBSjatZk32TBLWYiF/UOvuTUUE+QNokKcP2kdjkacdVF8tHcmzYrSi4ONbDMcRiGIUyubdI62FqaPjjEeLSb8zZov4zq+ffR0KWAhvliQocS4o6/XAR8hTUerzLzwS4Ny9iCgD/ycPVwvh6AyIzEiKPM4gDlcJl1g4owAaQOjCYUfT/Jl2FTAhZOyvUYy2daueYMeMfXfUzVOtKzPh3HnW2VsrtGlZXmw== cursor-gcp" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
chmod 700 ~/.ssh
exit
```

## 完成后的下一步

添加公钥后，运行部署脚本：

```powershell
cd d:\Projects\PythonProjects\taoquant
.\deploy\gcp\deploy_interactive.ps1 -GCP_IP "34.158.55.6" -GCP_USER "liandongtrading" -SSH_KEY "C:\Users\uncczhangtao\.ssh\id_rsa"
```

或者告诉我你已经添加了公钥，我可以继续执行部署。
