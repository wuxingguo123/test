# MCIFNet 论文中文翻译与代码对照指南

论文：Chunyu Zhu et al., "Mamba Collaborative Implicit Neural Representation for Hyperspectral and Multispectral Remote Sensing Image Fusion," IEEE TGRS, 2025.

对应代码主入口：

- 模型：`models/MCIFNet.py`
- 数据退化与数据集构造：`data_loader.py`
- 训练配置：`main.py`、`args_parser.py`、`train.py`
- 验证指标：`validate.py`、`metrics.py`

这份文档不是逐字硬翻译，而是“贴合代码的论文翻译”。读法是：先看每节中文意思，再看“代码怎么实现”，最后看“论文写法和当前代码的差异”。这样更适合做代码讲解、复现实验和毕业论文方法部分改写。

---

## 0. 论文与代码总览

论文要解决的问题是 HMIF，即高光谱图像和多光谱图像融合。

- HSI：Hyperspectral Image，高光谱图像。光谱维度高，空间分辨率低。
- MSI：Multispectral Image，多光谱图像。空间分辨率高，光谱维度低。
- LR-HSI：低空间分辨率高光谱图像。
- HR-MSI：高空间分辨率多光谱图像。
- HR-HSI：目标输出，高空间分辨率高光谱图像。

代码中的输入输出对应关系：

| 论文概念 | 代码变量 | 位置 | 形状含义 |
|---|---|---|---|
| LR-HSI | `HSI` / `image_lr` | `MCIFNet.forward(HSI, MSI)` | `(B, n_bands, h, w)` |
| HR-MSI | `MSI` / `image_hr` | `MCIFNet.forward(HSI, MSI)` | `(B, n_select_bands, H, W)` |
| HR-HSI | `INR_F` / `out` | `return INR_F, 0, 0, 0, 0, 0` | `(B, n_bands, H, W)` |

整体流程可以翻译成一句话：

> MCIFNet 先分别把 LR-HSI 和 HR-MSI 投影到统一的潜在特征空间，再用 Mamba/SSM 模块提取深层语义特征，最后用隐式神经表示 INR 在连续坐标域中逐点预测 HR-HSI。

代码中的实际流程：

```text
LR-HSI -> conv_first_HSI -> HSI ResidualGroup/SS2D/CAB -> HSI_encoder
HR-MSI -> conv_first_MSI -> MSI ResidualGroup/SS2D/CAB -> MSI_encoder
HSI_encoder + MSI_encoder + coord -> query() -> imnet(MLP) -> HR-HSI
```

---

## 1. 摘要翻译

高光谱遥感图像能够捕获地物细致的光谱特征，而多光谱遥感图像能够提供更清晰的空间分布。将二者融合，可以提高地物识别和分类的精度。现有深度学习融合算法虽然能取得较好的融合质量，但往往难以同时兼顾全局有效感知和轻量化计算。此外，很多算法以离散方式处理数据映射，而真实世界本身更接近连续空间。

Mamba 近年来在长距离建模方面表现出很大潜力，能够缓解全局感知带来的计算复杂度问题。与此同时，隐式神经表示 INR 能够为连续域建模提供高质量方案。因此，论文提出了一种结合 Mamba 和 INR 的网络结构，称为 Mamba 协同隐式神经表示融合网络 MCIFNet。

MCIFNet 能够有效捕获图像全局信息，并通过逐点预测在连续域中生成融合图像。网络主要包含两个单元：

- 潜在空间投影单元 LSPU：对 HSI 和 MSI 进行浅层编码，将它们映射到潜在特征空间。
- 语义提取与融合单元 SEFU：使用尺度自适应残差状态空间模块和隐式空间-光谱融合模块提取双模态深层特征，并逐点生成融合图像。

论文在 4 倍、8 倍、16 倍融合尺度上进行实验，结果表明 MCIFNet 在空间细节和光谱信息重建方面优于多种主流算法，同时参数量更轻。

代码对应：

- `conv_first_HSI`、`conv_first_MSI` 对应浅层编码。
- `ResidualGroup`、`BasicLayer`、`VSSBlock`、`SS2D` 对应 Mamba/SSM 深层特征提取。
- `query()` 和 `self.imnet` 对应 INR 逐点融合。
- `criterion = nn.L1Loss()` 对应论文中的 L1 重建损失。

---

## 2. 引言翻译与代码含义

论文指出，HMIF 的目标是利用 HR-MSI 的高空间分辨率来提升 HSI 的空间分辨率，同时尽量保持 HSI 的丰富光谱信息。传统方法通常基于成像退化模型，需要引入人工先验，例如稀疏先验、非局部相似先验、低秩先验等。这些先验可以约束优化过程，但难以准确建模复杂的非线性映射。

深度学习方法依靠神经网络强大的拟合能力，可以更好地学习 HSI 和 MSI 之间的复杂关系。CNN 擅长局部建模，Transformer 擅长全局交互，但 Transformer 的自注意力计算复杂度通常与输入规模呈二次关系，不利于轻量化。

Mamba 基于状态空间模型 SSM，具有线性时间复杂度，适合长序列建模。INR 使用连续可微函数把坐标映射到信号值，适合连续域重建。论文的核心观点是：

- Mamba 负责高效建模全局上下文。
- INR 负责在连续坐标上补充局部细节和逐点融合。
- 两者结合可以同时兼顾全局结构、局部细节和轻量化。

代码中这个思想的落地方式：

| 论文动机 | 代码实现 |
|---|---|
| Mamba 建模长距离依赖 | `SS2D.forward_core()` 做四方向 selective scan |
| 补充 Mamba 对局部信息不敏感的问题 | `CAB` 中使用 3x3 卷积和通道注意力 |
| INR 连续坐标逐点预测 | `make_coord()` 生成 `[-1, 1]` 坐标，`query()` 逐点采样并调用 `imnet` |
| 避免简单拼接/相加融合 | `query()` 中对四邻域预测值做 softmax 加权融合 |

---

## 3. 相关工作翻译

论文把相关工作分成四类。

### 3.1 基于 pansharpening 的 HMIF

这类方法最初用于多光谱图像和全色图像融合，可以看作 HMIF 的特殊情况。典型方法包括成分替换 CS 和多分辨率分析 MRA。它们结构简单、容易实现，但在大尺度融合任务中通常难以满足高质量重建要求。

代码关系：本项目没有实现 GSA 等传统 pansharpening 方法，论文里它们主要作为对比实验基线。

### 3.2 基于分解的 HMIF

分解方法通常把三维高光谱图像分解成二维光谱基和系数矩阵，再通过优化估计 HR-HSI。典型先验包括稀疏表示、低秩表示、张量分解等。优点是可解释性较强，缺点是优化复杂、速度慢，并且高倍数融合时精度有限。

代码关系：本项目的 `其他对比方法` 文件夹中有一些深度学习对比模型，但没有传统矩阵/张量分解流程。

### 3.3 基于深度学习的 HMIF

深度学习方法分为无监督和有监督两类。无监督方法常用自编码器、生成约束或物理退化约束；有监督方法则用已知参考图像作为标签进行训练。论文中的 MCIFNet 属于有监督深度学习范式：输入退化后的 LR-HSI 和 HR-MSI，目标是重建原始 HR-HSI。

代码关系：

- `data_loader.py` 先用原始 HSI 生成训练目标 `train_ref`。
- `generate_low_HSI()` 生成 LR-HSI。
- `generate_MSI()` 生成 HR-MSI。
- `train.py` 用 `criterion(out, image_ref)` 监督训练。

### 3.4 从 SSM 到 Mamba

SSM 源于控制理论，能够用线性复杂度处理长距离依赖。Mamba 在 SSM 基础上引入输入自适应选择机制，使状态空间参数随输入动态变化，因此比传统 Transformer 更高效。论文认为，将 Mamba 和 INR 用于 HMIF，可以结合离散特征建模与连续坐标重建的优势。

代码关系：

- `SS2D` 是视觉状态空间模块的核心。
- `selective_scan_fn` 来自 `mamba_ssm.ops.selective_scan_interface`。
- `forward_core()` 中把二维特征展开成四个方向的序列，再分别扫描。

---

## 4. 方法部分翻译与代码对照

### 4.1 SSM 预备知识

论文先介绍连续状态空间模型：

```text
x_dot(t) = A(t)x(t) + B(t)U(t)
y(t)     = C(t)x(t) + D(t)U(t)
```

其中 `x(t)` 是状态，`U(t)` 是输入，`y(t)` 是输出。为了在计算机中实现，需要把连续系统离散化，得到递归形式：

```text
h_t = A_bar h_{t-1} + B_bar x_t
y_t = C h_t
```

这可以理解成：当前输出不仅依赖当前输入，也依赖历史状态，因此可以建模长距离上下文。进一步展开后，输出可以写成类似卷积的形式，所以 Mamba 可以用高效扫描来处理长序列。

代码对应：

| 论文符号 | 代码变量/模块 | 说明 |
|---|---|---|
| 状态矩阵 A | `self.A_logs` | 在 `SS2D` 中初始化，多方向扫描各有一套参数 |
| 输入相关参数 B、C | `x_proj_weight` 切分出的 `Bs`、`Cs` | 由输入投影得到，体现 Mamba 的选择机制 |
| 步长 dt | `dt_projs_weight`、`dt_projs_bias` | 控制离散状态更新 |
| skip 参数 D | `self.Ds` | 对应 SSM 中的直接通路/残差项 |
| 扫描计算 | `selective_scan_fn` | CUDA selective scan 核函数 |

### 4.2 网络设计总翻译

论文中的 MCIFNet 包含两个核心单元：

1. LSPU，Latent Space Projection Unit，潜在空间投影单元。
2. SEFU，Semantic Extraction and Fusion Unit，语义提取与融合单元。

流程翻译：

> 首先，将 HSI 和 MSI 分别输入 LSPU，进行浅层编码并投影到潜在空间。然后，将投影后的 HSI 和 MSI 输入 SEFU，进行语义特征提取，并在连续域中做逐点特征融合，最终生成融合图像。

代码中的真实入口：

```python
HSI_first = self.conv_first_HSI(HSI)
HSI_encoder = self.forward_features_HSI(HSI_first) + HSI_first

MSI_first = self.conv_first_MSI(MSI)
MSI_encoder = self.forward_features_MSI(MSI_first) + MSI_first

coord = make_coord([H, W]).cuda()
INR_F = self.query(HSI_encoder, coord, MSI_encoder)
```

这里可以把 `conv_first_*` 看成 LSPU 的代码版本，把 `forward_features_* + query()` 看成 SEFU 的代码版本。

---

## 5. LSPU 潜在空间投影单元

论文翻译：

LSPU 的目标是对 HSI 和 MSI 做浅层编码，并把两种模态映射到同一个潜在特征空间。论文把 HSI 记为 `y in R^{h x w x S}`，把 MSI 记为 `z in R^{H x W x s}`。二者先经过局部展开，再通过投影矩阵映射到相同的特征维度 `D`：

```text
E_y = unfold(y) x P_y
E_z = unfold(z) x P_z
```

直观理解：HSI 和 MSI 原本通道数不同，一个光谱多、空间小，一个光谱少、空间大。LSPU 先把它们都变成统一维度的特征，便于后续用相同类型的网络提取深层特征。

代码实现：

```python
self.conv_first_MSI = nn.Conv2d(num_in_ch_MSI, embed_dim, 3, 1, 1)
self.conv_first_HSI = nn.Conv2d(num_in_ch_HSI, embed_dim, 3, 1, 1)
```

当前代码不是显式 `unfold + projection matrix`，而是用 `3x3 Conv2d` 完成局部感知和通道投影。这个实现可以理解为 LSPU 的卷积化版本。

需要注意的差异：

| 论文表述 | 当前代码 |
|---|---|
| `unfold + P_y/P_z` 投影 | `Conv2d(..., kernel_size=3, padding=1)` |
| 论文写 `D=64` | `main.py` 中 `embed_dim=96` |
| 论文强调局部 assemble | 代码的 3x3 卷积自然包含局部邻域 |

---

## 6. LESAM 局部增强与光谱注意力模块

论文翻译：

LESAM 受到 SENet 启发，用来弥补 Mamba 输出特征中局部信息不足的问题，并增强光谱维度表达。它分为两个阶段：

1. 局部增强：用两个 3x3 卷积压缩并恢复通道，增强局部细节。
2. 光谱注意力：用 1x1 卷积和 Sigmoid 生成每个通道的权重，再与局部增强特征相乘。

论文公式：

```text
B = Conv3D(Conv3D_s(Inp))
A = Sigmoid(Conv1D(Conv1D_s(B))) x B
```

代码实现对应 `CAB` 和 `ChannelAttention`：

```python
class CAB(nn.Module):
    self.cab = nn.Sequential(
        nn.Conv2d(num_feat, num_feat // compress_ratio, 3, 1, 1),
        nn.GELU(),
        nn.Conv2d(num_feat // compress_ratio, num_feat, 3, 1, 1),
        ChannelAttention(num_feat, squeeze_factor)
    )
```

```python
class ChannelAttention(nn.Module):
    nn.AdaptiveAvgPool2d(1)
    nn.Conv2d(num_feat, num_feat // squeeze_factor, 1)
    nn.ReLU(inplace=True)
    nn.Conv2d(num_feat // squeeze_factor, num_feat, 1)
    nn.Sigmoid()
```

翻译成代码语言：

> 论文中的 LESAM 在当前代码里没有直接使用这个名字，而是由 `CAB + ChannelAttention` 实现。`CAB` 负责局部卷积增强，`ChannelAttention` 负责光谱/通道注意力。

---

## 7. Vision SSM 与 SS2D

论文翻译：

VisionSSM 使用双路径结构增强特征表达。第一条路径先用线性层扩展通道，再通过深度卷积和 SiLU 激活增强局部特征，随后通过 SS2D 捕获长距离依赖。第二条路径保留原始信息，经过线性映射和 SiLU 激活后，与第一条路径做 Hadamard 乘积，得到更稳健的特征表示。

论文公式：

```text
f = Linear(Inp)
F = LN(SS2D(SiLU(DWConv(f)))) x SiLU(f)
```

代码对应 `SS2D.forward()`：

```python
xz = self.in_proj(x)
x, z = xz.chunk(2, dim=-1)
x = x.permute(0, 3, 1, 2).contiguous()
x = self.act(self.conv2d(x))
y = self.forward_core(x)
y = y * F.silu(z)
out = self.out_proj(y)
```

这里 `x` 路径对应论文中的局部卷积加 SS2D，`z` 路径对应门控保留信息，`y * F.silu(z)` 对应双路径融合。

### 7.1 SS2D 四方向扫描

论文翻译：

SS2D 会把二维图像特征展开成四个方向的序列，分别经过 SSM 处理，再把四个方向的结果相加，实现二维图像的全局感知。

论文公式：

```text
S_out = sum_i SSM_i(seq_i), i = 1..4
```

代码实现：

```python
x_hwwh = torch.stack([
    x.view(B, -1, L),
    torch.transpose(x, 2, 3).contiguous().view(B, -1, L)
], dim=1).view(B, 2, -1, L)

xs = torch.cat([x_hwwh, torch.flip(x_hwwh, dims=[-1])], dim=1)
```

四个方向可以理解为：

- 原图按行/宽方向扫描。
- 转置后按列/高方向扫描。
- 行方向反向扫描。
- 列方向反向扫描。

然后：

```python
y1 = out_y[:, 0]
y2 = inv_y[:, 0]
y3 = wh_y
y4 = invwh_y
y = y1 + y2 + y3 + y4
```

这就是论文中“四方向 SSM 输出相加”的代码实现。

---

## 8. SARSSB 与代码中的 ResidualGroup/VSSBlock

论文翻译：

SARSSB 是尺度自适应残差状态空间模块，用于从投影后的 HSI 和 MSI 中提取深层特征。它先对特征做归一化，再输入 VisionSSM，随后结合 LESAM 补充局部细节和光谱表达。论文写成：

```text
M_z = alpha * E_z + VSSM(LN(E_z))
F_z = beta  * M_z + LESAM(LN(M_z))

M_y = gamma * E_y + VSSM(LN(E_y))
F_y = delta * M_y + LESAM(LN(M_y))
```

代码中最接近的实现是 `VSSBlock`：

```python
x = input * self.skip_scale + self.drop_path(self.self_attention(x))
x = x * self.skip_scale2 + self.conv_blk(self.ln_2(x).permute(...))
```

对应关系：

| 论文模块 | 代码模块 | 说明 |
|---|---|---|
| SARSSB | `ResidualGroup` | 一组残差状态空间模块 |
| VSSM | `VSSBlock.self_attention = SS2D(...)` | 视觉状态空间扫描 |
| LESAM | `VSSBlock.conv_blk = CAB(...)` | 局部卷积和通道注意力 |
| `alpha/gamma` | `skip_scale` | 第一段可学习残差缩放 |
| `beta/delta` | `skip_scale2` | 第二段可学习残差缩放 |

代码结构：

```text
ResidualGroup
  -> BasicLayer
       -> VSSBlock
            -> LN
            -> SS2D
            -> residual scale
            -> LN
            -> CAB
            -> residual scale
```

当前代码中 HSI 和 MSI 使用两套独立的 `ResidualGroup` 列表：

```python
self.layers_MSI = nn.ModuleList()
self.layers_HSI = nn.ModuleList()
```

也就是说，两条分支结构相同，但参数不共享。

---

## 9. ISSF 隐式空间-光谱融合模块

这是论文和代码最关键的对应部分。

论文翻译：

ISSF 用高空间分辨率特征 `hr` 引导低空间分辨率特征 `lr` 在连续域中上采样，实现空间和光谱融合。对每一个查询点 `x_q`，先在低分辨率特征图中找到四个邻近点 `x_i`，再把下面三类信息送入 MLP：

1. 低分辨率 HSI 特征 `lr(x_i)`。
2. 高分辨率 MSI 引导特征 `hr(x_q)`。
3. 相对坐标 `x_q - x_i`。

MLP 输出两个东西：

- `v(q,i)`：该邻域点对查询点的光谱预测。
- `w(q,i)`：该邻域点的融合权重。

论文公式：

```text
v(q,i), w(q,i) = f_theta(lr(x_i), hr(x_q), x_q - x_i)
v = sum_i v(q,i) x softmax(w(q,i))
```

代码实现入口是 `query()`：

```python
def query(self, feat, coord, hr_guide):
```

参数含义：

| 参数 | 论文概念 | 说明 |
|---|---|---|
| `feat` | `lr` / `F_y` | HSI 分支深层特征，空间尺寸低 |
| `coord` | 查询坐标 `x_q` | HR 网格坐标，由 `make_coord([H, W])` 生成 |
| `hr_guide` | `hr` / `F_z` | MSI 分支深层特征，空间尺寸高 |

具体步骤：

1. 生成 LR 特征中心坐标：

```python
feat_coord = make_coord((h, w), flatten=False).to(feat.device)
```

2. 在 HR-MSI 引导特征上取查询点特征：

```python
q_guide_hr = F.grid_sample(hr_guide, coord.flip(-1).unsqueeze(1), mode='nearest')
```

3. 枚举四邻域：

```python
for vx in [-1, 1]:
    for vy in [-1, 1]:
```

4. 在 LR-HSI 特征上采样邻域特征：

```python
q_feat = F.grid_sample(feat, coord_.flip(-1).unsqueeze(1), mode='nearest')
q_coord = F.grid_sample(feat_coord, coord_.flip(-1).unsqueeze(1), mode='nearest')
```

5. 计算相对坐标：

```python
rel_coord = coord - q_coord
rel_coord[:, :, 0] *= h
rel_coord[:, :, 1] *= w
```

6. 拼接并送入隐式 MLP：

```python
inp = torch.cat([q_feat, q_guide_hr, rel_coord], dim=-1)
pred = self.imnet(inp.view(B * N, -1)).view(B, N, -1)
```

7. 对四邻域预测做 softmax 加权：

```python
preds = torch.stack(preds, dim=-1)
weight = F.softmax(preds[:, :, -1, :], dim=-1)
ret = (preds[:, :, 0:-1, :] * weight.unsqueeze(-2)).sum(-1)
```

8. 重塑成 HR-HSI：

```python
ret = ret.permute(0, 2, 1).view(b, -1, H, W)
```

最重要的一点：

```python
self.imnet = MLP(imnet_in_dim, out_dim=in_chans_HSI + 1, hidden_list=self.mlp_dim)
```

`+1` 的含义是：前 `in_chans_HSI` 维输出光谱预测，最后 1 维输出该邻域的权重。四个邻域的权重经过 softmax 后归一化。

---

## 10. 损失函数翻译与训练代码

论文翻译：

论文选择 L1 损失来衡量融合图像和参考图像之间的差距。相比 L2 损失，L1 对大误差和小误差的惩罚更均衡，有利于保持高频细节。

论文公式：

```text
Loss = mean(|Out - Ref|)
```

代码对应：

```python
criterion = nn.L1Loss().cuda()
loss = criterion(out, image_ref)
```

训练流程：

1. `main.py` 构建数据集和模型。
2. `train.py` 从训练图像中裁剪一个 patch。
3. 用 `generate_low_HSI()` 生成当前 patch 的 LR-HSI。
4. 把 LR-HSI 和 HR-MSI 输入模型。
5. 输出 HR-HSI，与 `image_ref` 计算 L1 损失。
6. 反向传播，并使用梯度裁剪。

代码：

```python
torch.nn.utils.clip_grad_norm_(
    parameters=model.parameters(),
    max_norm=0.5,
    norm_type=2
)
```

---

## 11. 数据仿真翻译与代码

论文翻译：

实验遵循 Wald 协议，把原始 HSI 作为参考图像。通过空间退化和光谱退化生成训练/测试所需的 LR-HSI 和 HR-MSI。

- 空间退化：用高斯滤波和下采样生成 LR-HSI。
- 光谱退化：用光谱响应函数 SRF 将 HSI 投影为 MSI。
- 每个数据集裁剪一个 `192 x 192` 区域作为测试集，其余区域作为训练集。
- 训练 patch 尺寸为 `128 x 128`。
- epoch 数为 `10000`。
- 学习率为 `0.0001`。
- 优化器为 Adam。

代码对应：

| 论文设置 | 代码位置 |
|---|---|
| Wald 协议 | `build_datasets()` 中从原始 HSI 生成 `test_ref/train_ref` |
| 空间退化 LR-HSI | `generate_low_HSI()`、`downsamplePSF()` |
| 高斯核 PSF | `matlab_style_gauss2D()` |
| 光谱退化 HR-MSI | `generate_MSI()` |
| SRF 光谱响应函数 | `get_spectral_response()` |
| 测试区域 192x192 | `args_parser.py` 中 `--test_size` 默认 192 |
| 训练 patch 128x128 | `args_parser.py` 中 `--image_size` 默认 128 |
| 训练 10000 轮 | `args_parser.py` 中 `--n_epochs` 默认 10000 |
| 学习率 1e-4 | `args_parser.py` 中 `--lr` 默认 1e-4 |
| Adam | `main.py` 中 `torch.optim.Adam(...)` |

需要注意的代码细节：

- 论文说空间退化包含高斯滤波和双线性插值；当前 `data_loader.py` 和 `train.py` 的主要实现是高斯 valid 卷积后按 stride 下采样，没有显式双线性插值步骤。
- `data_loader.py` 中测试集取的是图像右侧靠上的区域：`w_str = width - test_size`，`h_str = 0`。
- 训练区域会把测试区域置 0，避免训练和测试重叠。
- 当前默认数据集是 `IEEE2018`，论文实验数据集是 Chikusei、DFC2018、PaviaC、PaviaU。代码里也支持 TeaFarm、HongHu、HanChuan、XiongAn、realdata 等名称。

---

## 12. 评价指标翻译与代码

论文使用 RMSE、PSNR、ERGAS、SAM 评价融合质量。

### 12.1 RMSE

RMSE 衡量融合图像和参考图像的平均误差，越小越好。

代码：

```python
def calc_rmse(img_tgt, img_fus):
    rmse = np.sqrt(np.mean((img_tgt - img_fus) ** 2))
```

### 12.2 PSNR

PSNR 衡量重建质量，越大越好。

代码：

```python
def calc_psnr(img_tgt, img_fus):
    mse = np.mean((img_tgt - img_fus) ** 2)
    img_max = np.max(img_tgt)
    psnr = 10 * np.log10(img_max ** 2 / mse)
```

### 12.3 ERGAS

ERGAS 综合考虑误差和波段均值，用于衡量空间和光谱重建质量，越小越好。

代码：

```python
def calc_ergas(img_tgt, img_fus):
    rmse = np.mean((img_tgt - img_fus) ** 2, axis=1) ** 0.5
    mean = np.mean(img_tgt, axis=1)
    ergas = 100 / 4 * np.mean((rmse / mean) ** 2) ** 0.5
```

### 12.4 SAM

SAM 衡量光谱向量夹角，越小代表光谱越接近。

代码：

```python
AB = np.sum(img_tgt * img_fus, axis=0)
sam = np.arccos(AB / (A * B))
sam = np.mean(sam) * 180 / np.pi
```

验证入口：

```python
rmse = calc_rmse(ref, out)
psnr = calc_psnr(ref, out)
ergas = calc_ergas(ref, out)
sam = calc_sam(ref, out)
```

---

## 13. 实验结论翻译

论文在 Chikusei、DFC2018、PaviaC、PaviaU 数据集上，与 GSA、CNMF、HySure、LEMamba、DCT、MoGDCN、TSFN、3DT-Net 等方法比较。总体结论是：

1. 在 4x、8x、16x 不同尺度上，MCIFNet 大多数指标优于对比算法。
2. 低倍数融合时，传统物理模型方法有时仍有竞争力。
3. 高倍数融合时，深度学习方法更有优势，MCIFNet 的 Mamba 特征提取和 INR 融合更稳定。
4. 消融实验表明 ISSF、LESAM、SARSSB、SEFU、VSSM 都对结果有贡献。
5. 复杂度对比表明 MCIFNet 能较好平衡精度、FLOPs 和参数量。

和当前代码的关系：

- 本仓库主要保留 MCIFNet 和若干对比方法代码。
- 当前默认训练设置和论文基本一致：`image_size=128`、`n_epochs=10000`、`lr=1e-4`、`Adam`、`L1Loss`。
- 如果要严格复现实验表格，需要准备论文对应数据集、SRF 文件、随机 patch 坐标表和各对比方法完整依赖。

---

## 14. 消融实验如何对应代码

论文消融模块和代码关系：

| 论文消融项 | 含义 | 当前代码里怎么改 |
|---|---|---|
| 去掉 ISSF | 不用隐式逐点融合，改成普通加法/拼接/卷积 | 替换 `query()`，直接上采样 HSI 特征后与 MSI 特征融合 |
| 去掉 LESAM | 不用局部增强和光谱注意力 | 在 `VSSBlock` 中移除或替换 `self.conv_blk = CAB(...)` |
| 去掉 SARSSB | 不使用 Mamba 深层特征提取 | 跳过 `forward_features_HSI/MSI()`，直接用 `conv_first_*` 输出进入 `query()` |
| 去掉 VSSM | 不使用 `SS2D` | 将 `self.self_attention = SS2D(...)` 换成恒等映射或普通卷积 |
| 去掉 SEFU | 不进行语义提取和隐式融合 | 用双线性上采样对齐 HSI，再用卷积输出 HR-HSI |

本仓库中还出现了类似的消融模型名称：

- `ASSMamba_no_RSSG`
- `ASSMamba_no_CAB`
- `ASSMamba_no_GINS`
- `ASSMamba_no_VSSM`
- `ASSMamba_no_SEFU`

但 `args_parser.py` 当前 `choices` 里没有列出这些消融模型。如果要运行它们，需要同步修改 `args_parser.py` 的可选模型列表，或者直接在代码里手动实例化。

---

## 15. 当前代码与论文表述的关键差异

这部分很重要，写论文复现或答辩时不要直接照搬论文描述。

| 论文写法 | 当前代码实际情况 | 建议表述 |
|---|---|---|
| LSPU 使用 `unfold + projection matrix` | 代码用 `3x3 Conv2d` 映射到 `embed_dim` | “本代码以 3x3 卷积实现局部投影，等价承担 LSPU 的浅层编码功能。” |
| 论文中 `D=64` | `main.py` 里 MCIFNet 设置 `embed_dim=96` | “复现代码中潜在维度设为 96。” |
| 论文强调 SARSSB/SEFU 命名 | 代码里主要命名为 `ResidualGroup`、`VSSBlock`、`SS2D`、`CAB`、`query` | “代码沿用 MambaIR 命名，功能对应论文模块。” |
| 论文说使用 LESAM | 代码中名字是 `CAB` 和 `ChannelAttention` | “LESAM 在代码中实现为卷积注意力块 CAB。” |
| 论文实验数据集是 Chikusei、DFC2018、PaviaC、PaviaU | 当前默认数据集是 `IEEE2018` | “代码提供了可替换数据集接口，默认配置并非论文表格数据集。” |
| 论文说空间退化包含高斯滤波和双线性插值 | 代码主要是高斯卷积加 stride 下采样 | “本代码采用 PSF 高斯退化和步长采样生成 LR-HSI。” |
| 论文公式中有 `alpha/beta/gamma/delta` | 代码使用 `skip_scale` 和 `skip_scale2` | “可学习残差缩放参数在每个 VSSBlock 中实现。” |
| 论文 SEFU 可能暗示双模态深度协同 | 代码中 HSI/MSI 分支深层提取阶段参数独立，融合发生在 `query()` | “双分支分别编码，最终通过 ISSF/INR 逐点融合。” |
| `coord = make_coord([H, W]).cuda()` | 代码硬编码 `.cuda()` | 如果用 CPU 或多设备，建议改成 `.to(MSI.device)` |

---

## 16. 可以直接写进论文/报告的方法描述

下面是一段贴合当前代码的中文方法描述，可以直接作为报告初稿再润色。

本文采用 MCIFNet 完成高光谱与多光谱遥感图像融合。模型输入为低空间分辨率高光谱图像 LR-HSI 和高空间分辨率多光谱图像 HR-MSI，输出为高空间分辨率高光谱图像 HR-HSI。首先，网络分别使用 3x3 卷积对 LR-HSI 和 HR-MSI 进行浅层特征提取，并将二者映射到统一的潜在特征维度。随后，两个分支分别经过由 ResidualGroup、VSSBlock 和 SS2D 构成的状态空间特征提取模块。SS2D 将二维图像特征沿水平、垂直及其反向展开成四个序列，通过 selective scan 捕获长距离依赖，并将四个方向的输出融合，从而获得全局上下文信息。为增强 Mamba 对局部细节和光谱通道关系的表达能力，VSSBlock 中进一步引入卷积注意力块 CAB，通过 3x3 卷积和通道注意力补充局部空间细节与光谱响应。

在融合阶段，模型采用隐式神经表示思想进行逐点预测。网络首先在目标高分辨率网格上生成连续坐标，然后对每个查询坐标，从低分辨率 HSI 特征中采样四个邻域特征，并从高分辨率 MSI 特征中采样对应位置的引导特征。随后将 HSI 邻域特征、MSI 引导特征和相对坐标拼接后输入 MLP。MLP 同时输出该查询点的光谱预测值和邻域融合权重，四个邻域的权重经 softmax 归一化后对光谱预测进行加权求和，最终得到 HR-HSI。训练阶段采用 L1 损失约束融合结果与参考 HR-HSI 的差异，并使用 Adam 优化器进行参数更新。

---

## 17. 最短代码阅读路线

如果只想快速理解论文和代码怎么对应，建议按这个顺序读：

1. `models/MCIFNet.py` 中 `MCIFNet.forward()`：看整体输入输出。
2. `models/MCIFNet.py` 中 `query()`：看 ISSF/INR 融合。
3. `models/MCIFNet.py` 中 `SS2D.forward_core()`：看 Mamba 四方向扫描。
4. `models/MCIFNet.py` 中 `VSSBlock`：看 SS2D 和 CAB 怎么组合。
5. `data_loader.py` 中 `build_datasets()`：看 LR-HSI、HR-MSI、HR-HSI 怎么生成。
6. `train.py` 中 `train()`：看损失函数和训练 patch。
7. `metrics.py`：看论文指标怎么计算。

