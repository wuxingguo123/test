# 代码严格审查报告

## 【总体结论】

代码存在 **多个会直接影响论文复现和指标可信度的问题**。最严重的集中在：
1. **ERGAS 指标公式中 scale 比例因子硬编码为 4**，换数据集/scale 后指标直接失真
2. **PSNR 使用数据依赖的 max 而非固定峰值**，导致绝对数值与其他论文不可比
3. **train.py 中 `_gauss2d_numpy` 参数顺序写反**（虽然当前为死代码路径，但表明 numpy 退化分支从未被正确测试）
4. **MCIFNet 中多个已定义但未使用的层**，浪费显存且说明 forward 流可能与设计意图不符
5. **训练集随机裁剪可能覆盖被置零的测试区域**，引入无效训练样本

---

## 【严重问题】

### S1. ERGAS 公式中 scale ratio 硬编码为 4

1. **问题位置**：[metrics.py L17](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/metrics.py#L17)
2. **当前代码做法**：
   ```python
   ergas = 100 / 4 * ergas ** 0.5
   ```
   `4` 被硬编码。
3. **论文/标准做法**：标准 ERGAS 公式为：
   $$\text{ERGAS} = \frac{100}{r} \sqrt{\frac{1}{N_b} \sum_{i=1}^{N_b} \left(\frac{\text{RMSE}_i}{\mu_i}\right)^2}$$
   其中 $r$ 是空间下采样比例（scale_ratio），应由参数传入。
4. **差异说明**：当 `scale_ratio` 不为 4（如 8、16）时，ERGAS 值与标准公式不一致。
5. **可能影响**：**论文中不同 scale 设置下的 ERGAS 值全部失真**，与其他论文的 ERGAS 完全不可比。
6. **建议**：给 `calc_ergas` 加 `scale_ratio` 参数，将 `100 / 4` 改为 `100 / scale_ratio`。
7. **严重程度**：🔴 **严重** — 直接影响论文表格指标。

---

### S2. PSNR 使用数据实际最大值而非固定峰值

1. **问题位置**：[metrics.py L23](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/metrics.py#L23)
2. **当前代码做法**：
   ```python
   img_max = np.max(img_tgt)
   psnr = 10 * np.log10(img_max ** 2 / mse)
   ```
   使用目标图像的实际最大像素值作为峰值。
3. **论文/标准做法**：PSNR 标准公式：$\text{PSNR} = 10 \log_{10}(\text{MAX}^2 / \text{MSE})$，其中 MAX 应为数据范围的固定上界。数据在 [data_loader.py L110](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/data_loader.py#L110) 已归一化到 `[0, 255]`，则 MAX 应为 255。
4. **差异说明**：测试集裁剪的 192×192 区域的实际最大像素值一般小于 255。例如如果实际 max=240，PSNR 会比 peak=255 时偏低约 $10\log_{10}(255^2/240^2) \approx 0.53$ dB。
5. **可能影响**：
   - 不同方法在同一数据集上比较时，如果各方法输出的 max 不同，PSNR 数值会有非实质性差异
   - 与其他论文使用 `peak=255` 或 `peak=1` 的 PSNR 不可直接对比
6. **建议**：改为 `img_max = 255.0`（与归一化范围一致），或在归一化到 `[0,1]` 时使用 `img_max = 1.0`。
7. **严重程度**：🔴 **严重** — 影响论文指标的绝对数值和跨论文可比性。

---

### S3. train.py 中 `_gauss2d_numpy` 调用参数顺序写反

1. **问题位置**：[train.py L89](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/train.py#L89)
2. **当前代码做法**：
   ```python
   h = _gauss2d_numpy((stride, stride), sigma)
   ```
   第一个参数传了 `(stride, stride)` 即 `(4, 4)`（元组），第二个参数传了 `sigma` 即 `2.0`（浮点数）。
3. **论文/标准做法**：函数签名（[train.py L19](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/train.py#L19)）为：
   ```python
   def _gauss2d_numpy(sigma, shape=(5, 5)):
   ```
   第一参数是标量 `sigma`，第二参数是元组 `shape`。data_loader.py 中的同名函数调用顺序正确（[L54](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/data_loader.py#L54)：`matlab_style_gauss2D(sigma, (stride,stride))`）。
4. **差异说明**：参数完全反了。若此分支被执行：
   - `sigma` 收到元组 `(4,4)` → `2.*sigma*sigma` 触发 `TypeError`
   - `shape` 收到浮点 `2.0` → `for ss in shape` 触发 `TypeError: 'float' object is not iterable`
5. **可能影响**：当前 `train_ref` 始终是 tensor（来自 `torch.from_numpy`），所以 torch 分支被走到，numpy 分支是死代码，**运行时不会崩溃**。但这表明 numpy 退化路径从未被测试过，如果未来有人传入 numpy 数组会立即报错。
6. **建议**：将 L89 改为 `h = _gauss2d_numpy(sigma, (stride, stride))`，与 data_loader 保持一致。
7. **严重程度**：🟡 **中等**（当前为死代码路径，但属于明确的 bug）。

---

### S4. 训练集随机裁剪可能覆盖被置零的测试区域

1. **问题位置**：[data_loader.py L139](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/data_loader.py#L139) + [train.py L143-L148](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/train.py#L143-L148)
2. **当前代码做法**：
   - data_loader 把测试区域（IEEE2018: 行 `[1008:1200]`，列 `[0:192]`）置零
   - train.py 从 Excel 读取 `(h_str, w_str)` 做 128×128 裁剪
   - **没有校验裁剪区域是否与置零的测试区域重叠**
3. **论文/标准做法**：训练数据不应包含无效（全零）区域。
4. **差异说明**：当 `h_str >= 880`（即 `1008 - 128`）**且** `w_str < 64`（即 `192 - 128`）时，裁剪 patch 会完全或部分落入置零区域。根据你的运行日志，epoch 4 的 `h_str=1009` 已经在危险范围内（但 `w_str=2733` 远离列 0-192 的测试区域所以没事）。
5. **可能影响**：如果 Excel 文件中存在 h_str 和 w_str 同时命中测试区域的坐标，模型会在全零 patch 上训练，相当于学习"输出零"，**拉低模型性能**。
6. **建议**：在 Excel 生成随机坐标时排除测试区域；或在 train.py 中加校验跳过重叠 patch。
7. **严重程度**：🔴 **严重** — 可能导致训练质量下降，且难以从指标上发现原因。

---

### S5. MCIFNet 中多个层定义了但 forward 从未调用

1. **问题位置**：[MCIFNet.py](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/models/MCIFNet.py)
2. **当前代码做法**：以下层在 `__init__` 中定义但 `forward` 中未使用：

   | 层 | 定义位置 | 说明 |
   |---|---|---|
   | `self.conv_after_body` | [L847](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/models/MCIFNet.py#L847) | 深度特征提取后的卷积，未使用 |
   | `self.conv_last` | [L868](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/models/MCIFNet.py#L868) | 最终输出卷积，未使用 |
   | `self.softmax` | [L768](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/models/MCIFNet.py#L768) | `nn.Softmax()` 未指定 dim 且未被调用 |
   | `self.norm` | [L843](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/models/MCIFNet.py#L843) | LayerNorm，forward 中未使用 |

3. **论文/标准做法**：模型的所有定义层应在 forward 中参与计算，否则为冗余。
4. **差异说明**：这些层的参数被包含在 `model.parameters()` 中，占用显存，且被 optimizer 更新（虽然梯度为零）。更重要的是，`conv_after_body` 和 `conv_last` 通常是 backbone 的关键组件，**未使用可能说明 forward 流与论文描述不一致**。
5. **可能影响**：浪费显存；如果论文中描述了这些组件的作用但代码未实现，**则代码实现与论文不一致**。
6. **建议**：确认论文中 MCIFNet 的网络结构图，对照检查 forward 流是否遗漏了这些层。
7. **严重程度**：🔴 **严重（需确认）** — 若论文描述了这些层的功能，则为实现遗漏。

---

### S6. `best_psnr` 初始化逻辑有缺陷：恢复训练时丢失历史最佳

1. **问题位置**：[main.py L314-L320](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/main.py#L314-L320)
2. **当前代码做法**：
   ```python
   best_psnr = 0                    # L314: 先设为 0
   best_psnr = validate(...)        # L315: 立即用当前模型的 PSNR 覆盖
   ```
   即使加载了 checkpoint（L304-L312），`best_psnr` 也被重置为当前 validate 结果，而非从 checkpoint 中恢复历史最佳值。
3. **论文/标准做法**：恢复训练时，`best_psnr` 应从保存的 checkpoint 中读取，或至少使用加载模型后 validate 的结果。
4. **差异说明**：当前代码在不加载 checkpoint 时（首次训练），L315 的 validate 结果即为初始 PSNR，后续只要优于它就保存，**逻辑上正确**。但如果加载 checkpoint 后继续训练，history best 被丢弃，可能导致中间训练产出的较差模型覆盖之前的最佳模型。
5. **可能影响**：恢复训练场景下，最佳模型可能被次优模型覆盖。
6. **建议**：将 `best_psnr` 一并保存到 checkpoint 中，加载时恢复。
7. **严重程度**：🟡 **中等** — 仅影响恢复训练场景。

---

## 【中等问题】

### M1. `validate.py` 在模块级重复解析命令行参数

1. **问题位置**：[validate.py L7](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/validate.py#L7)
2. **当前代码做法**：`args = args_parser.args_parser()` 在文件顶层执行（import 时触发），创建了一个独立于 `main.py` 的 `args` 对象。
3. **差异说明**：当前 validate 内部只用了 `args.scale_ratio`（[L26](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/validate.py#L26) 的 SwinCGAN 分支），实际跑 `_3DT_Net` 或 `MCIFNet` 时未触发该分支，所以暂时无影响。但如果未来新增模型需要 `args.scale_ratio`，此处的 args 对象可能与 main.py 的不一致。
4. **严重程度**：🟡 **中等**

### M2. `model.load_state_dict` 使用 `strict=False`

1. **问题位置**：[main.py L305](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/main.py#L305)
2. **当前代码做法**：`model.load_state_dict(torch.load(model_path), strict=False)`
3. **差异说明**：`strict=False` 会静默忽略不匹配的 key。如果模型结构改动后加载旧权重，部分层可能使用随机初始化权重却不报任何警告，导致性能异常且难以排查。
4. **严重程度**：🟡 **中等**

### M3. `_3DT_Net` 的 `self.up_factor` 未强制转 int

1. **问题位置**：[_3DT_Net.py L132](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/models/_3DT_Net.py#L132)
2. **当前代码做法**：`self.up_factor = factor`，直接存储传入值。
3. **差异说明**：如果 `args_parser.py` 中 `--scale_ratio` 的 type 被误改为 `float`（或通过其他方式传入浮点数），`nn.Conv2d` 的 `stride=self.up_factor` 会报 `tuple of (float, float)` 错误（你的第一次运行日志就是这个错误：`scale_ratio=4.0`）。
4. **可能影响**：你的第一次运行已经触发了此问题。
5. **建议**：在 `__init__` 中 `self.up_factor = int(factor)`。
6. **严重程度**：🟡 **中等**（已经观察到实际触发）

### M4. MCIFNet 中 `make_coord` 硬编码 `.cuda()`

1. **问题位置**：[MCIFNet.py L966](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/models/MCIFNet.py#L966)
2. **当前代码做法**：`coord = make_coord([H, W]).cuda()`
3. **差异说明**：应改为 `.to(MSI.device)` 以支持 CPU 推理和多 GPU。
4. **严重程度**：🟡 **中等**

### M5. MCIFNet 的 `img_size=64` 与实际输入尺寸不匹配

1. **问题位置**：[main.py L143](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/main.py#L143)（传入）和 [MCIFNet.py L740](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/models/MCIFNet.py#L740)（接收）
2. **当前代码做法**：`img_size=64` 硬编码传入 MCIFNet。
3. **差异说明**：
   - HSI 输入尺寸：`image_size / scale_ratio = 128/4 = 32`（训练）或 `192/4 = 48`（测试）
   - MSI 输入尺寸：`128`（训练）或 `192`（测试）
   - 都不等于 64
   - `PatchEmbed` 中的 `patches_resolution` 被计算为 `[64, 64]`，但实际 forward 中用的是动态 `x_size`。由于 SwinIR 的 PatchEmbed 只做 flatten 不做实际 patch 卷积，且 SwinTransformerBlock 在 `calum_dic` 中动态缓存 attention mask，**当前不会崩溃**
   - 但 `input_resolution` 错误可能导致某些依赖它的初始化（如 shift_size 判断）出现不一致
4. **严重程度**：🟡 **中等** — 当前因动态 mask 缓存机制不会报错，但属于不规范的做法

### M6. 无随机种子设置，实验不可复现

1. **问题位置**：整个项目中没有任何 `torch.manual_seed()`、`np.random.seed()`、`random.seed()` 的调用
2. **当前代码做法**：
   - 裁剪坐标来自 Excel 文件（固定）→ 可复现
   - 但 **权重初始化**（`xavier_normal_` at [_3DT_Net.py L237](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/models/_3DT_Net.py#L237)）、`Dropout`、`DropPath` 等全部使用随机状态 → 不可复现
3. **可能影响**：每次训练的初始权重不同，导致最终 PSNR 有波动，**论文中的结果无法精确复现**。
4. **严重程度**：🟡 **中等**

### M7. 全程无学习率衰减策略

1. **问题位置**：[main.py L300](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/main.py#L300)
2. **当前代码做法**：10000 个 epoch 全程使用 `lr=1e-4` 的 Adam。
3. **差异说明**：大多数 HSI 融合论文使用 CosineAnnealing、StepLR 或 MultiStepLR 来衰减学习率。没有衰减会导致后期 loss 震荡，难以收敛到更优解。
4. **严重程度**：🟡 **中等** — 影响最终收敛精度

### M8. `nn.Softmax()` 未指定 dim

1. **问题位置**：[MCIFNet.py L768](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/models/MCIFNet.py#L768)
2. **当前代码做法**：`self.softmax = nn.Softmax()` — 未指定 `dim` 参数。
3. **差异说明**：PyTorch 默认 `dim=None`（在新版本中会警告，在旧版本中可能默认 `dim=0`）。虽然此 `self.softmax` 在 forward 中未被调用（实际用的是 `F.softmax` at [L946](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/models/MCIFNet.py#L946)），但属于代码隐患。
4. **严重程度**：🟡 **中等**（死代码，但表明代码质量问题）

---

## 【轻微问题 / 代码规范问题】

### L1. `torch.set_default_tensor_type` 每 epoch 重复调用且已废弃

- **位置**：[train.py L128](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/train.py#L128)
- `torch.set_default_tensor_type(torch.cuda.FloatTensor)` 在每个 epoch 都被调用，污染全局状态，且 PyTorch 2.1+ 已废弃此 API。

### L2. `Variable` 已废弃

- **位置**：[utils.py L12, L20](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/utils.py#L12)
- `torch.autograd.Variable` 在 PyTorch 0.4+ 已废弃，`volatile` 参数也无效。直接用 tensor 即可。

### L3. `ConSSFCNN.txt` 硬编码文件名

- **位置**：[validate.py L38](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/validate.py#L38)
- 所有模型、所有数据集的验证结果全部追加到同一个文件，多次实验日志混在一起。应按实验配置区分文件名。

### L4. data_loader 中 `train_lr` 被预计算但从未使用

- **位置**：[data_loader.py L142](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/data_loader.py#L142) 和 [train.py L144](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/train.py#L144)
- data_loader 对整个训练图像计算了 `train_lr`（含零区域），但 train.py 每个 epoch 会从裁剪后的 `train_ref` 重新生成 `train_lr`，完全覆盖了预计算结果。
- 浪费了 data_loader 的计算时间，且预计算的 LR 包含了被置零测试区域的影响（零值区域经高斯模糊会向外扩散）。

### L5. `_3DT_Net` 中大量未使用的 delta/eta 参数

- **位置**：[_3DT_Net.py L138-L151](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/models/_3DT_Net.py#L138-L151)
- 定义了 `delta_0` 到 `delta_6` 和 `eta_0` 到 `eta_6`（共 14 个参数），但 forward 中只用到 `delta_0/eta_0` 和 `delta_3/eta_3`。`delta_1/eta_1, delta_2/eta_2, delta_4-6/eta_4-6` 全部未使用。

### L6. `_3DT_Net.acti` (PReLU) 定义了但未使用

- **位置**：[_3DT_Net.py L134](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/models/_3DT_Net.py#L134)
- `self.acti = torch.nn.PReLU()` 在 forward 中从未被调用。

### L7. 数据类型为 float64 导致不必要的精度和内存开销

- **位置**：[data_loader.py L146-L151](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/data_loader.py#L146-L151)
- `torch.from_numpy` 对 float64 数组生成 `DoubleTensor`，之后在 `to_var` 中才转为 float32。中间的裁剪、PSF 计算全程使用 float64，内存翻倍且计算更慢。

### L8. `model_path` 的 `.replace('dataset', ...)` 是多余操作

- **位置**：[main.py L303](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/main.py#L303)
- `model_path = args.model_path.replace('dataset', args.dataset).replace('arch', args.arch)`
- 由于 L87 已经把 `args.model_path` 设为 `os.path.join(args.expr_dir, "model.pkl")`，里面不包含字面量 `'dataset'` 或 `'arch'`，所以 replace 操作不会改变任何东西。这是旧版代码的残留。

---

## 【需要进一步确认的问题】

### C1. SAM 计算前的额外归一化是否影响结果

- **位置**：[metrics.py L37-L38](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/metrics.py#L37-L38)
- ```python
  img_tgt = img_tgt / np.max(img_tgt)
  img_fus = img_fus / np.max(img_fus)
  ```
- 理论上，SAM 是基于向量夹角的，对每幅图像整体除以一个标量不改变各像素光谱向量之间的夹角，数学上等价。但需要确认：
  - 这种归一化方式是否与论文中引用的 SAM 定义完全一致
  - 其他对比方法的 SAM 实现是否也做了这一步
- 如果对比方法不做此归一化而本代码做了，虽然理论上不影响结果，但浮点精度差异可能导致 SAM 值有微小不同。
- **状态**：需对照论文和对比方法的代码确认。

### C2. `_3DT_Net.spatial` 共享权重是否为刻意设计

- **位置**：[_3DT_Net.py L247-L266](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/models/_3DT_Net.py#L247-L266)
- `self.spatial`（Prior 模块，含完整 Swin Transformer）在 forward 中被调用 **6 次**，所有调用共享同一组权重。
- 需确认 3DT-Net 论文中是否明确要求权重共享。如果论文中是 6 个独立 Prior 模块，则当前实现的表征能力弱于论文设计。
- **状态**：需对照 3DT-Net 原论文确认。

### C3. 论文中的损失函数是否为 L1Loss

- **位置**：[main.py L298](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/main.py#L298)
- 当前对非 SSRNET 模型统一使用 `nn.L1Loss()`。
- 需确认 MCIFNet 和 _3DT_Net 各自论文中描述的损失函数是否为 L1。某些方法可能使用 L1+SAM、L1+SSIM、MSE 等组合。
- **状态**：需对照各方法原论文确认。

### C4. Excel 随机坐标文件是否保证不覆盖测试区域

- **位置**：`IEEE2018_rand.xlsx`
- 需检查文件中的所有 `(h_str, w_str)` 组合，验证是否存在 `h_str >= 880 and w_str <= 64` 的行（以 IEEE2018、image_size=128、test_size=192、scale_ratio=4 为例）。
- **状态**：需直接读取 Excel 数据验证。

### C5. `_3DT_Net` 的 `conv_downsample` 是否应该是可学习的

- **位置**：[_3DT_Net.py L162](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/models/_3DT_Net.py#L162)
- 论文中的下采样算子 $D$ 通常是固定的高斯模糊+strided 下采样（即 PSF），但代码用了**可学习的** `nn.Conv2d`。需确认 3DT-Net 论文中 $D$ 是固定退化矩阵还是可学习卷积。
- **状态**：需对照论文确认。

### C6. 梯度裁剪 `max_norm=0.5` 是否与论文一致

- **位置**：[train.py L184](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/train.py#L184)
- `torch.nn.utils.clip_grad_norm_(parameters=model.parameters(), max_norm=0.5, norm_type=2)`
- 梯度裁剪的阈值和范数类型需与论文一致。注释说"L2正则"但实际是梯度裁剪，不是 L2 正则化。
- **状态**：需对照论文确认。

---

## 【优先排查顺序】

| 优先级 | 文件 | 行号 | 问题 | 原因 |
|---|---|---|---|---|
| **1** | [metrics.py](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/metrics.py#L17) | L17 | ERGAS 中 `100/4` 硬编码 | **直接导致非 scale=4 场景下 ERGAS 指标失真**，改一行代码即可修复 |
| **2** | [metrics.py](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/metrics.py#L23) | L23 | PSNR 用 `np.max` 而非固定 peak | **影响所有 PSNR 数值**，改一行代码即可修复 |
| **3** | `IEEE2018_rand.xlsx` | 全部 | 检查是否有坐标落入测试区域 | 决定是否存在 S4 的实际影响 |
| **4** | [MCIFNet.py forward](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/models/MCIFNet.py#L951-L971) | L951-L971 | 对照论文检查 forward 流 | 确认 S5 中未使用的层是否应该参与计算 |
| **5** | [train.py](file:///C:/Users/ASUS/Desktop/MCIFNet/MCIFNet-main1/MCIFNet-main/MCIFNet-main/train.py#L89) | L89 | `_gauss2d_numpy` 参数顺序 | 虽然当前不触发，但修复成本极低（交换两个参数），消除隐患 |
