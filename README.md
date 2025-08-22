# Lightsail流量配额监控系统

## 方案概述

针对AWS Lightsail套餐包流量限制，提供高精度监控和告警系统，防止超出套餐包产生额外费用。

## 核心文件

### 1. 智能监控 (`intelligent_monitoring.py`)
- **用途**: 识别高风险实例，优化监控效率
- **特点**: 先筛选高流量实例，减少90% API调用
- **执行频率**: 每日运行

### 2. 精确配额监控 (`precise_quota_monitor.py`) 
- **用途**: 精确监控实例流量使用率
- **特点**: 按套餐包计算准确配额，多级告警
- **执行频率**: 每小时运行（仅高风险实例）

### 3. 实时告警系统 (`realtime_quota_alerts.py`)
- **用途**: 设置CloudWatch告警和SNS通知
- **特点**: 75%/85%/95%分级告警，智能指标管理
- **执行频率**: 一次性设置

### 4. 成本数据监控 (`cost_explorer_alternative.py`)
- **用途**: 基于账单数据的流量分析
- **特点**: 避免大量API调用，成本极低
- **执行频率**: 每日运行作为备用监控

### 5. 实例批量管理工具 (`instance_manager.py`)
- **用途**: 批量停止/启动超出告警阈值的实例
- **特点**: 支持模拟运行、分级管理、操作日志
- **执行频率**: 按需手动执行

## 权限配置

### 所需AWS权限
- Lightsail: 实例查看和指标获取权限
- CloudWatch: 创建告警和发送指标权限
- SNS: 创建主题和发送通知权限
- Cost Explorer: 成本数据查询权限（可选）

## 使用方法

### 初始设置
```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件设置你的配置
# 主要配置项:
# - LIGHTSAIL_REGIONS: 需要监控的区域
# - HIGH_RISK_DAILY_GB_THRESHOLD: 高风险实例阈值
# - 告警阈值: ALERT_THRESHOLD_MEDIUM/HIGH/CRITICAL

# 3. 确保AWS凭证配置
# 方式1: AWS CLI配置
aws configure

# 方式2: 环境变量
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1

# 4. 设置告警系统（一次性）
python3 realtime_quota_alerts.py
```

### 日常监控
```bash
# 每日运行 - 识别高风险实例
python3 intelligent_monitoring.py

# 每小时运行 - 精确监控高风险实例  
python3 precise_quota_monitor.py

# 备用监控 - 基于成本数据
python3 cost_explorer_alternative.py

# 批量管理告警实例
python3 instance_manager.py
```

## 告警实例管理

系统会按告警级别自动生成以下文件:
- `alert_medium_instances.json` - 中级告警实例 (75-84%)
- `alert_high_instances.json` - 高级告警实例 (85-94%)
- `alert_critical_instances.json` - 紧急告警实例 (95%+)

使用实例管理工具可以:
- 批量停止超出阈值的实例
- 模拟运行预览操作结果
- 记录操作日志便于审计

## 告警级别

- **75%**: 预警通知
- **85%**: 高级告警  
- **95%**: 紧急告警，建议立即行动

## 技术特点

1. **智能筛选**: 先识别高风险实例，减少90% API调用
2. **并发处理**: 支持10线程并发，大幅提升处理速度
3. **分批执行**: 每批100个实例，避免API限制
4. **缓存机制**: 自动缓存历史数据，避免重复查询
5. **精确监控**: 基于实际套餐包配额计算使用率
6. **分级告警**: 75%/85%/95%三级告警机制
7. **批量管理**: 支持按告警级别批量管理实例
8. **智能指标**: 只为告警实例创建CloudWatch指标，大幅减少指标数量

## 依赖要求

- Python 3.7+
- boto3 >= 1.26.0
- python-dotenv >= 1.0.0
- AWS CLI 配置或环境变量设置

## 适用场景

- 多region部署的大规模Lightsail环境
- 需要精确控制流量成本的场景
- 防止意外超出套餐包流量限制

## 常见问题排查

### 1. AWS凭证配置问题
```bash
# 检查AWS凭证是否配置
aws sts get-caller-identity

# 检查区域配置
aws configure list
```

### 2. 权限不足
确保你的AWS用户或角色具有以下权限:
- `lightsail:GetInstances`
- `lightsail:GetInstanceMetricData`
- `cloudwatch:PutMetricAlarm`
- `cloudwatch:PutMetricData`
- `sns:CreateTopic`
- `ce:GetCostAndUsage` (可选)

### 3. API限制问题
如果遇到API限制错误，可以调整 `.env` 中的参数:
```
API_DELAY_SECONDS=2  # 增加延迟时间
REGION_DELAY_SECONDS=10
```

### 4. 检查运行状态
```bash
# 检查生成的告警文件
ls -la alert_*.json

# 查看详细报告
cat intelligent_quota_report.json | jq .

# 性能测试
python3 performance_test.py
```

## 性能优化

### 大规模部署性能
- **1,000台机器**: 约5-10分钟
- **10,000台机器**: 约15-20分钟
- **优化前**: 1万台需要约1.8小时
- **优化后**: 1万台约20分钟

### 关键优化技术
1. **并发处理**: 10线程并发API调用
2. **分批执行**: 每批100个实例，避免API限制
3. **智能缓存**: 日级缓存，避免重复查询
4. **API优化**: 减少延迟时间至0.1秒

### 配置调优
```bash
# 高性能配置
MAX_CONCURRENT_WORKERS=10  # 并发线程数
BATCH_SIZE=100            # 批次大小
API_DELAY_SECONDS=0.1     # API延迟
BATCH_DELAY_SECONDS=2     # 批次间延迟
```

## CloudWatch指标优化

### 指标管理策略
- **传统方式**: 1000台机器 = 1000个CloudWatch指标
- **优化后**: 只为告警实例创建指标，通常 < 50个指标
- **聚合指标**: 区域级别的汇总监控指标

### 指标类型
1. **告警实例指标** (`Lightsail/QuotaMonitor`)
   - `QuotaUsagePercent` - 仅告警实例的使用率
   - 维度: InstanceName, Region, Severity

2. **聚合监控指标** (`Lightsail/Aggregated`)
   - `TotalInstances` - 区域总实例数
   - `AlertInstances` - 告警实例数
   - `CriticalAlerts` - 紧急告警数
   - `AlertRate` - 告警率百分比

### 成本优化效果
- **指标数量**: 减少95%+ (1000个 → <50个)
- **CloudWatch费用**: 大幅降低
- **管理复杂度**: 显著简化