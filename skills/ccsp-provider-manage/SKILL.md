---
name: ccsp-provider-manage description: 管理写入 cc-switch SQLite 数据库的 ccs-plus 供应商配置。用于通过 ccs-plus 或 ccsp 查询、新增、查看、导出、导入、重置、删除或启动 Claude、Codex、Grok、OpenCode 供应商，尤其适用于需要保护凭据或确认破坏性操作的场景。
---

# CCSP 供应商管理

仅通过 `ccsp` 或 `ccs-plus` 管理供应商。不要直接修改 cc-switch SQLite 数据库、Provider 记录或受管运行时文件。

## 操作前

1. 在包含 `settings.yaml` 的 ccs-plus 仓库中执行命令。
2. 在任何写操作前先确认数据库状态：

   ```bash
   ccsp provider list --json
   ```

3. 请求限定应用时，使用 `claude`、`codex`、`grok` 或 `opencode` 过滤。
4. 非交互操作中不要直接执行 `ccsp`，因为无参数会打开 TUI。

## 查询供应商

先使用只读命令确认目标：

```bash
ccsp provider list
ccsp provider list --app codex --json
ccsp provider show "provider-name"
```

`provider show` 会先为自定义供应商输出带 `--yes` 的删除命令，再输出 API Key 已掩码的复用 新增命令。官方供应商不显示删除命令。除非用户明确要求在可信终端披露，否则不要使用 `--show-secret`。

列表中的快捷方式按应用独立编号：`c1`、`x1`、`g1`、`o1`。写操作后编号可能变化，使用 快捷方式前必须重新读取列表。

## 新增、导出与导入

新增前检查同一应用内是否已有同名供应商。名称会先去除首尾空白，再按大小写无关方式比较。 新增必须同时提供 `--name`、`--endpoint`、`--api-key` 和 `--model`：

```bash
ccsp provider add codex \
  --name "provider-name" \
  --endpoint "https://api.example.com/v1" \
  --api-key "$PROVIDER_API_KEY" \
  --model "model-id"
```

仅在用户提供时设置 `--effort` 和 `--notes`。不得在命令输出、源码、提交、日志或聊天记录中 回显 API Key；优先使用可信 shell 变量或交互式输入。

`export` 只备份自定义供应商，文件使用配置的 Fernet 密钥加密：

```bash
ccsp provider export
ccsp provider export codex data/providers-codex.json
```

导入必须使用生成备份时相同的加密密钥。即使限定应用，命令也会先验证整份加密备份，再筛选 指定应用：

```bash
ccsp provider import data/providers-all-YYYYMMDD-HHMMSS.json
ccsp provider import codex data/providers-codex.json
```

不要覆盖已有导出文件。导入前先处理重复名称。

## 删除与重置

将 `reset` 和 `delete` 视为破坏性数据库操作。

1. 先执行 `ccsp provider reset [app]`，检查 dry-run 输出。
2. 仅在获得明确确认后执行 `ccsp provider reset [app] --yes`。
3. 删除单个供应商时，必须指定精确应用和名称，并附带 `--yes`：

   ```bash
   ccsp provider delete codex "provider-name" --yes
   ```

`reset` 与 `delete` 只会移除非官方供应商。不要手动删除数据库记录或受管 profile 文件。

## 使用供应商启动

先检查列表，再使用已验证的快捷方式或精确名称：

```bash
ccsp run x1
ccsp launch codex --provider "provider-name" --cwd "/work/project"
```

`--model` 和 `--effort` 仅用于本次启动覆盖。临时试验不应改写供应商记录。

## 完成与汇报

新增、导入、重置或删除后，运行 `ccsp provider list --json` 验证结果。仅汇报非敏感元数据： 应用、名称、endpoint、模型、分类和快捷方式；同时说明操作、范围及验证结果。

Skill 安装或更新后，重启 Claude、Codex、Grok 的 agent session，使其重新发现新副本。
