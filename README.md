# Himawari Radiation API

## 项目来源
- 原始项目：[Open-Meteo](https://github.com/open-meteo/open-meteo)
  - DeepWiki👉 https://deepwiki.com/open-meteo/open-meteo
- Satellite-api
  - om20250206接入Himawari👉 [feat: JMA JAXA Himawari solar radiation](https://github.com/open-meteo/open-meteo/pull/1220)
  
## 📋 项目概述
本项目(计划)实现了一个自动化卫星辐射数据处理系统，用于下载、校正和存档 Himawari-8/9 卫星的短波辐射（SWR）数据，生成可直接用于光伏预测和辐射分析的高质量产品。

## 🎯 核心目标
- 构建稳定、可复现的近实时辐射处理流程
- 作为open-meteo的冗余备份
- 实现专业的卫星辐射校正算法
- 为超短期光伏功率预测提供可靠输入

## 📡 数据源说明

### 原始数据
- **卫星**：Himawari-8 / Himawari-9
- **产品**：L2 PAR（SWR）- 短波辐射产品
- **来源**：JAXA 官方 FTP
- **分辨率**：10分钟
- **状态**：Beta版（未质量保证）

**FTP 存储路径：**

/pub/himawari/L2/PAR/021/{year}{month}/{day}/{hour}

---

## 1. H8nc数据存档与二次读取

### 🔧 Open-Meteo存档方案
下载 - 内存读取 - 自定义OM格式，路径：[JaxaHimawariDownloader.swift](https://github.com/open-meteo/open-meteo/blob/main/Sources/App/JaxaHimawari/JaxaHimawariDownloader.swift)

### 本项目存档方案
实时下载nc - 提取SWR - 裁剪指定区域为tif    
**注意时区问题**：github actions运行时, datetime.now() 返回的是utc时间。  
- 实时数据，腾讯云函数触发，具体参考前一个项目[workflow](https://github.com/StorywithLove/workflow)
- 历史数据，服务器里按日触发，查询执行完成后触发下一个项目
```swift
def get_latest_run():
    url = f"https://api.github.com/repos/StorywithLove/Himawari_radiation_api/actions/workflows/hist.yml/runs?per_page=1"
    headers = {
        "Authorization": f"Bearer {GTOKEN}",
        "Accept": "application/vnd.github+json"
    }
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    run_info = r.json()["workflow_runs"][0]
    return run_info
    #return datetime.fromisoformat(run_info['created_at'].rstrip('Z')).replace(tzinfo=timezone.utc), run_info["status"], run_info["conclusion"]
```

---

## 2. 近实时辐射时间校正
原始 Himawari L2 SWR 数据存在两个关键问题，使其无法直接用于时间序列分析：
- **时间标签不一致**：文件名时间 = 扫描开始时间（如 10:00）、实际观测时间随扫描位置变化（南北差异可达 8-10 分钟，日本区域的像元实际在 10:08 才被观测到）
- **物理含义不匹配**：原始数据是瞬时辐射值、实际应用需要时间平均辐射值、扫描过程中太阳位置持续变化

### 🔧 Open-Meteo校正方案  
[JaxaHimawariDownloader.swift](https://github.com/open-meteo/open-meteo/blob/main/Sources/App/JaxaHimawari/JaxaHimawariDownloader.swift)  

#### 第一层：时间标签校正
将一次完整的扫描数据视为其后 10 分钟区间的平均辐射：

| 原始文件时间 | 实际观测时间 | 校正后时间 | 物理含义 |
|--------------|-------------|------------|-----------|
| 10:00        | 10:00-10:08 | 10:10      | 10:00-10:10 瞬时辐射(中间结果) |

---
#### 第二层：物理量校正  
将瞬时辐射值转换为 10 分钟(向后)平均：  
| 校正后时间 | 物理含义 |
|------------|-----------|
| 10:10      | 10:00-10:10 平均辐射|
  

## 3. 辐射转换
### 🔧 Open-Meteo转换方案：
[GHI - DHI - DNI - GTI/POV](https://github.com/open-meteo/open-meteo/tree/main/Sources/App/Helper/Solar)  

- Zensun.swift
  - calculateDiffuseRadiationBackwards(), 基于Razo, Müller Witwer分离模型, 从总辐射/地面短波辐射中分解出散射分量、直射分量
- DirectNormalIrradiance.swift
  - calculateInstantDNI，基于水平面直射分量, 逆向计算太阳法向DNI
- GlobalTilitedIrradiance.swift
  - calculateTiltedIrradiance(), 基于[DNI, DHI, tilt, azimuth]计算GTI/POA = 散射辐射-等向性天空, 地面反射-反射率0.2, 直接辐射-太阳入射角余弦, 通过积分平均法计算太阳位置
- SolarPositionAlgorithm.swift
  - SolarPositionAlgorithm(), 基于NREL SPA算法的太阳位置计算
- SunRiseSet.swift
  - calculateSunRiseSet, 基于太阳几何位置和时间, 计算日出日落时间

