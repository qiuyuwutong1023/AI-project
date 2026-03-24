# ReEvo 本次改动详细说明（Thoughts + Codes 与推理增强进化）

## 1. 改动背景

本次改动的核心目标是让 ReEvo 在“生成-评估-进化”过程中，不仅保留代码结果，还保留候选解背后的思路（Thoughts），并在后续进化中复用这些思路作为上下文，从而形成更稳定的“推理增强进化”闭环。

为达成该目标，需要同时解决三个问题：

1. 统一并强制 LLM 输出结构，避免返回格式漂移。
2. 在接收 LLM 响应时，可靠地拆分出 Thoughts 与 Codes 两部分并持久化。
3. 在“父母 -> 后代”生成流程中，把父母个体的 Thoughts 一并注入提示词，让后代不仅继承代码结构，也继承设计意图。

---

## 2. 本次需求与实现映射

### 2.1 需求一：强制 LLM 输出严格结构

目标结构：

Thoughts: ...
Codes: ...

实现方式：

- 将生成器系统提示词改为严格双段式输出约束。
- 将 seed / crossover / mutation 三类用户提示词同步改为同一结构要求，避免“系统层要求”和“任务层要求”不一致。

### 2.2 需求二：正确解析并保存思想与代码

实现方式：

- 在 ReEvo 中新增 `_extract_thoughts_and_codes` 函数。
- 优先使用严格正则匹配完整结构；若模型轻微偏离格式，则回退到关键词分割策略，增强鲁棒性。
- 在 `response_to_individual` 中统一调用该函数，把 thoughts 与 code 一起写入个体数据结构。

### 2.3 需求三：生成后代时把“父母思想”也加入上下文

实现方式：

- 扩展短期反思阶段返回值，除了 worse/better code 外，再携带 worse/better thoughts。
- 扩展 crossover 提示词模板，新增父母 thoughts 区块。
- 在 crossover 的提示词组装处注入对应 thoughts。

补充增强：

- mutation 路径也额外注入 elitist thoughts，使“历史优秀个体的思路”可在变异阶段继续传递。

---

## 3. 代码改动明细

## 3.1 文件：reevo.py

### 3.1.1 新增依赖

- 新增 `import re`，用于正则解析 Thoughts/Codes。

### 3.1.2 种子个体结构补充

- 在 `init_population` 中创建的 seed 个体新增字段：
  - `thoughts`: `"Seed heuristic baseline."`
- 目的：保证种子个体在后续流程中也具备统一数据字段，避免空键访问。

### 3.1.3 响应解析入口统一

- `response_to_individual` 原先直接 `extract_code_from_generator(response)`。
- 现在改为：
  - `thoughts, code = self._extract_thoughts_and_codes(response)`
  - 个体字典中新增 `thoughts` 字段。

### 3.1.4 新增函数 `_extract_thoughts_and_codes`

函数签名：

- `_extract_thoughts_and_codes(self, response: str) -> tuple[str, Optional[str]]`

解析逻辑：

1. 严格匹配优先：
   - 使用正则匹配 `Thoughts:` 到 `Codes:` 两段结构。
2. 回退匹配：
   - 若严格匹配失败，尝试按 `Codes:` 关键词切分。
   - 前半段去除可选 `Thoughts:` 前缀后作为 thoughts。
3. 代码提取：
   - 先对 `codes_part` 调用 `extract_code_from_generator`。
   - 若仍失败，再对完整 content 兜底提取。

设计意图：

- 在“严格格式”与“轻微偏离格式”之间取得兼容平衡。
- 让进化流程尽量不中断，同时持续引导模型回归标准输出。

### 3.1.5 短期反思数据链扩展

- `gen_short_term_reflection_prompt` 的返回值从三元扩展为五元：
  - message, worse_code, better_code, worse_thoughts, better_thoughts
- `short_term_reflection` 对应扩展保存列表并返回：
  - response_lst, worse_code_lst, better_code_lst, worse_thoughts_lst, better_thoughts_lst

### 3.1.6 crossover 上下文扩展

- `crossover` 接收的 tuple 类型扩展为五项。
- 在 `self.crossover_prompt.format(...)` 中新增注入：
  - `worse_thoughts`
  - `better_thoughts`

结果：

- 进入后代生成时，提示词上下文同时包含父母代码与父母思路。

### 3.1.7 mutation 路径补充（增强项）

- 在 `mutate` 的 prompt format 中新增：
  - `elitist_thoughts = self.elitist.get("thoughts", "")`

结果：

- 精英个体变异时，模型可同时参考历史最佳代码与其推理思路。

---

## 3.2 文件：prompts/common/system_generator.txt

改动点：

- 由“输出 python 代码块”改为“严格输出两段结构”：
  - Thoughts: ...
  - Codes: ```python ... ```
- 明确禁止输出额外段落。

影响：

- 从系统层统一约束所有生成类任务的输出外形。

---

## 3.3 文件：prompts/common/seed.txt

改动点：

- 输出要求改为严格 Thoughts/Codes 结构。

影响：

- 初始种群生成阶段即开始沉淀 thoughts。

---

## 3.4 文件：prompts/common/crossover.txt

改动点：

- 新增区块：
  - `[Worse thoughts] {worse_thoughts}`
  - `[Better thoughts] {better_thoughts}`
- 输出要求改为严格 Thoughts/Codes 结构。

影响：

- 父母思维上下文进入后代生成提示词，增强“思路级遗传”。

---

## 3.5 文件：prompts/common/mutation.txt

改动点：

- 新增区块：
  - `[Thoughts] {elitist_thoughts}`
- 输出要求改为严格 Thoughts/Codes 结构。

影响：

- 变异阶段可利用历史优秀个体思路，减少仅靠代码局部扰动的盲目性。

---

## 4. 数据流变化（关键）

## 4.1 变更前

- LLM 响应 -> 提取 code -> 评估 -> 选择 -> 交叉/变异
- thoughts 未显式存储，也未参与后续生成。

## 4.2 变更后

- LLM 响应 -> `_extract_thoughts_and_codes` -> 保存 `thoughts + code` -> 评估
- 选择后：
  - 父母 `worse/better code + thoughts` 一并进入 crossover prompt
- 变异时：
  - `elitist code + elitist thoughts` 一并进入 mutation prompt

结果：

- 进化由“仅代码遗传”升级为“代码 + 推理遗传”。

---

## 5. 兼容性与鲁棒性说明

1. 解析容错：
- 若模型偶发未严格遵循格式，解析函数仍尝试按 `Codes:` 分割并兜底提取代码。

2. 空 thoughts 兼容：
- 未解析到 thoughts 时，使用空字符串，不阻断执行。

3. 现有评估逻辑兼容：
- 评估仍以 `individual["code"]` 执行，核心评估路径不受破坏。

4. 类型与语法检查：
- 本次对 `reevo.py` 的改动已通过静态错误检查（无错误）。

---

## 6. 预期收益

1. 输出结构稳定：
- 降低因模型回复风格漂移导致的解析失败率。

2. 信息利用更完整：
- 历史优秀个体不再只贡献代码，还贡献可迁移的设计策略。

3. 推理增强进化：
- 在 crossover 与 mutation 两条生成路径中引入 thought context，增强后代生成的方向性与可解释性。

---

## 7. 已知限制与后续可优化项

1. 严格格式依赖提示词约束：
- 若模型严重偏离结构，当前回退策略只能尽力提取，无法保证 thoughts 完整性。

2. thoughts 质量门控尚未加入：
- 当前未对 thoughts 做质量评分或过滤，后续可增加“无效思路过滤器”。

3. 长期记忆机制可进一步增强：
- 当前已实现跨代传递，但尚未做“thoughts 摘要压缩”与“高价值思想库”聚合。

---

## 8. 结论

本次改动已完整覆盖三项需求，并额外将 mutation 路径也升级为“代码 + 思想”双通道上下文。至此，ReEvo 的候选个体从单一代码表示扩展为“思想-代码二元表示”，为后续推理增强进化（Reasoning-Augmented Evolution）提供了可落地的数据基础与调用链路。