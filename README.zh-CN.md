[English](README.md) · [Русский](README.ru.md) · [简体中文](README.zh-CN.md) · [Ελληνικά](README.el.md) · [Italiano](README.it.md) · [Laconian Doric (reconstructed)](README.grc-x-laconian.md)

# Laconian

Laconian 追求最短的完整答案，而不是最短的答案。

## 状态

Laconian 是一个正在积极开发的公共哲学项目和开放基准。目前，仓库中包含一个可运行的
基础骨架：一个可移植技能、双语冒烟用例、四个对照组、离线重放路径、确定性评分、
可选的盲评语义判断，以及一个真实提供商适配器的模拟合约。

目前还没有可用的公开基准结果。冒烟测试夹具只用于验证架构；它们不能证明 `if` 获胜、
节省了某个具体数值，或比其他对照组表现更好。

## 为什么是“if”？

数百年后写作的普鲁塔克（Plutarch）在《论多言》（*On Talkativeness*）第 17 节
（*Moralia* 511A）中记载了一则关于腓力二世（Philip II）的轶事。腓力写信威胁要进入
拉科尼亚；拉科尼亚人则以书面形式只回复了一个多利亚词：`αἴκα`——“如果”。信件本身并未
留存。现存的是普鲁塔克后来的文学记述，而不是同时代的文献。

这个故事是项目的意象，并非其基准假设的证据。它也不是一个关于腓力最终未能进入
拉科尼亚的故事：波利比乌斯（Polybius）9.33 中的一位发言者承认，腓力曾率军进入拉科尼亚。

## 该技能的作用

[`skills/if/SKILL.md`](skills/if/SKILL.md) 要求智能体先确定完整答案，然后只删除那些不会
削弱正确性、安全性、需求满足程度、重要事实、不确定性说明、实际充分性、清晰度、语气或
自然语言表达的内容。

它会先删除问候语、对问题的复述、未经请求的过程叙述、重复和装饰，再考虑删减实质内容。
当精确形式很重要时，它会保留用户要求的细节，以及准确的代码、命令、错误、数字、版本、
URL、标识符、引文和机器可读结构。

该技能只有一个纯 Markdown 文件。它没有脚本、依赖、权限、引用资料、资源文件、网络调用，
也没有针对特定平台的工具说明。

## 该技能不做什么

`if` 不会把正常文字变成原始化表达，不会用自信取代证据，不会隐藏重要的限定条件，也不会
缩短工具调用、压缩代码、压缩输入上下文或执行操作。它不会覆盖用户对详细教程、固定结构、
证据、示例或规定篇幅的要求。它也不承诺每个智能体或模型都会作出完全相同的回答。

## 安装与卸载

推荐从仓库安装已固定版本的插件：

```bash
codex plugin marketplace add agent-axiom/laconian --ref v0.1.0-alpha.1 --json
codex plugin add laconian@laconian --json
```

安装后以 `$laconian:if` 调用该技能。如果没有立即显示，请新建任务或重启 Codex。
可用以下命令验证发现结果：

```bash
codex plugin list --marketplace laconian --json
```

卸载插件：

```bash
codex plugin remove laconian@laconian --json
codex plugin marketplace remove laconian --json
```

如需单独安装固定版本的单文件技能：

```bash
mkdir -p "$HOME/.agents/skills/if"
curl -fsSL "https://raw.githubusercontent.com/agent-axiom/laconian/v0.1.0-alpha.1/skills/if/SKILL.md" \
  -o "$HOME/.agents/skills/if/SKILL.md"
```

单文件技能以 `$if` 调用。验证复制结果：

```bash
test -s "$HOME/.agents/skills/if/SKILL.md"
```

卸载单文件版本时，只删除复制的目标文件，再删除已空的目录：

```bash
rm "$HOME/.agents/skills/if/SKILL.md"
rmdir "$HOME/.agents/skills/if"
```

## 四组对照基准

每个回答用例都在相同的模型、用户提示、生成设置、工具可用性和指令位置下进行比较。
唯一变化的是对照指令：

| 对照组 | 添加的指令 |
|---|---|
| `baseline` | 无 |
| `concise` | 完全一致的 `Answer concisely.` |
| `caveman` | 完整 Caveman 技能的按字节固定离线快照 |
| `if` | 本仓库 `skills/if/SKILL.md` 的精确字节内容 |

主要假设比较 `if` 与 `concise`。`baseline` 和 `caveman` 对照组用于提供背景；它们不是
主要比较的简化替代方案。激活情况和回答质量分别评估。

## 质量门槛与报告指标

先检查确定性约束，再衡量简洁程度。随后，可选的语义判断可以在看不到对照组名称的情况下，
评估必需事实和重要警告。失败的答案不能仅凭简短获胜；配对差值只纳入所选质量门槛下，
两个回答都通过的匹配用例与重复轮次组合。

报告分别保留硬性成功和语义成功指标、精确值和格式违规、提供商错误、重试、输出 token 或
字符数、原始产物中的延迟数据，以及配对的 `if` 与 `concise` 差值。项目不计算综合分数。
只有在提供明确注明日期的价格快照，并且提供商的 token 与缓存计量足够完整时，才会估算费用。
完整规则见[基准方法](benchmarks/methodology.md)。

## 快速开始

离线重放路径不需要网络访问或提供商凭据：

```bash
uv sync --all-extras
uv run laconian validate evals/cases/response-smoke.yaml
uv run laconian validate evals/cases/activation-smoke.yaml
uv run laconian validate evals/manifests/replay-smoke.yaml
uv run laconian run evals/manifests/replay-smoke.yaml --results-root benchmarks/results
```

最后一条命令会打印其唯一的运行目录。将该路径复制到 `RUN_DIR`，然后评分并生成报告：

```bash
RUN_DIR="benchmarks/results/PASTE_THE_PRINTED_DIRECTORY_NAME"
uv run laconian score "$RUN_DIR/raw.jsonl" --cases evals/cases/response-smoke.yaml --output "$RUN_DIR/scored"
uv run laconian report "$RUN_DIR/scored/scored.jsonl" --output "$RUN_DIR/report.md"
```

这些重放输出只是本地验证产物，不是已发布的基准证据。

### 可选的真实运行

```bash
export OPENAI_API_KEY="your key"
uv sync --extra openai
uv run laconian run evals/manifests/openai-example.yaml --results-root benchmarks/results
```

此命令会产生提供商费用。模型可用性可能因账户和日期而异。API 密钥只能放在配置的环境变量中；
绝不能把它们写入清单或已提交的结果文件。在模型标识符、原始产物、方法和局限性经过审查之前，
真实运行的结果还不能用于发布。

## 仓库结构

| 路径 | 用途 |
|---|---|
| `skills/if/SKILL.md` | 完整的可移植技能 |
| `src/laconian_eval/` | 与提供商无关的运行器、评分、判断边界和报告 |
| `evals/cases/` | 成对的英语/俄语回答和激活输入 |
| `evals/manifests/` | 可复现的运行配置 |
| `evals/baselines/caveman/` | 已固定的第三方基准夹具及其署名信息 |
| `tests/fixtures/` | 用于离线测试的合成重放和判断数据 |
| `benchmarks/methodology.md` | 可发布比较所遵循的规则 |
| `benchmarks/results/` | 未来不可变的公开运行产物 |
| `docs/` | 设计、理念和用例贡献指南 |

## 参与贡献

请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。新用例必须有证据支持、对各对照组保持中立，
并提供英语和俄语配对。任何基准结论都必须附带相应的原始产物。涉及安全的报告应遵循
[SECURITY.md](SECURITY.md)，而不是提交公开议题。

## 许可

许可方式遵循 [NOTICE](NOTICE) 中的映射：

- 代码、测试、工作流配置和 `skills/if/SKILL.md`：依据 [LICENSE](LICENSE) 使用 Apache-2.0；
- README 文件、项目文档、评测用例和清单、方法文档以及已发布的结果：使用
  [CC BY 4.0](LICENSES/CC-BY-4.0.txt)；
- 固定的 Caveman 快照：使用 [MIT](LICENSES/CAVEMAN-MIT.txt)，上游来源记录在
  [`evals/baselines/caveman/SOURCE.md`](evals/baselines/caveman/SOURCE.md) 中。

## 历史与语言学来源

- [普鲁塔克（Plutarch），《论多言》（*On Talkativeness*）第 17 节（*Moralia* 511A）](https://www.perseus.tufts.edu/hopper/text?doc=Perseus%3Atext%3A2008.01.0287%3Asection%3D17)，用于后来的文学记述和 `αἴκα`。
- [Eva A. Mitchell，*Laconian Dialect*，爱丁堡大学](https://era.ed.ac.uk/items/385e1ac5-539c-47f6-94b7-8ab83a94a139)，用于说明古代拉科尼亚方言证据的残缺性和异质性。
- [波利比乌斯（Polybius），*Histories* 9.33](https://penelope.uchicago.edu/Thayer/E/Roman/Texts/Polybius/9%2A.html)，用于证明古代已有腓力率军进入拉科尼亚的记载。
