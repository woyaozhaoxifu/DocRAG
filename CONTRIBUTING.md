# 贡献指南 Contributing

感谢你对 **DocRAG** 感兴趣！欢迎提 Issue、建议和 Pull Request。

## 提 Issue / Report Issues
- 在 GitHub 的 **Issues** 页面描述问题或建议。
- 尽量包含：复现步骤、操作系统与 Python 版本、报错信息或截图。
- 相关功能建议请先搜索是否已有类似 Issue，避免重复。

## 提交 Pull Request
1. Fork 本仓库到你的账号。
2. 创建特性分支：`git checkout -b feature/your-feature`。
3. 本地安装依赖：`pip install -r requirements.txt`。
4. 开发与自测完成后提交：`git commit -m "feat: 简述改动"`。
5. 推送到你的 Fork：`git push origin feature/your-feature`。
6. 在 GitHub 发起 Pull Request，描述改动目的与测试情况。

## 本地开发约定 Local Dev Conventions
- 建议使用 Python 3.10+ 与虚拟环境。
- 语义向量模型为**可选组件**，未下载不影响基础关键词检索。
- **请勿提交**个人文档、模型权重、以及本地配置文件：
  - `config.json`、`user_dict.txt`（仅提交 `config.example.json` / `user_dict.example.txt` 模板）
  - `data/`、`models/`、`venv/` 已在 `.gitignore` 中排除。
- 保持代码风格一致，关键改动请补充必要注释。

## 行为准则 Code of Conduct
请友善沟通、就事论事，尊重不同意见。我们致力于维护一个开放、包容的开源社区。

---
Thank you for contributing! Please be respectful and follow the guidelines above.
