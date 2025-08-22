# precise_quota_monitor.py 技术文档

## 实现意图

`precise_quota_monitor.py` 是Lightsail流量配额监控系统的**精确监控引擎**，专门负责对所有实例进行高精度的配额使用率监控。与intelligent_monitoring的筛选策略不同，该组件提供全面、精确的实时监控能力。

### 核心目标
- 基于真实套餐包配额进行精确计算，避免"一刀切"的固定配额误判
- 实现月度计费周期的准确监控
- 提供三级告警机制，精确控制告警时机
- 集成CloudWatch指标推送，支持实时告警

## 实现原理

### 套餐包感知架构

```
实例信息 → 套餐包识别 → 配额映射 → 使用率计算 → 告警判断
```

### 精确监控流程

```
月度数据获取 → 流量累计计算 → 配额比较 → 分级告警 → CloudWatch推送
```

### CloudWatch指标优化

```
传统方式: 1000实例 = 1000指标
优化策略: 只为告警实例创建指标 + 区域聚合指标
结果: 1000实例 → <50指标 (减少95%+)
```

## 代码逻辑详解

### 1. 套餐包配额映射 (`get_instance_plan_quota`)

**配额映射表**:
```python
PLAN_QUOTAS = {
    'nano_2_0': 1024,    # $5套餐: 1TB
    'micro_2_0': 2048,   # $7套餐: 2TB  
    'small_2_0': 3072,   # $12套餐: 3TB
    'medium_2_0': 4096,  # $24套餐: 4TB
    'large_2_0': 5120,   # $44套餐: 5TB
    'xlarge_2_0': 6144   # $84套餐: 6TB
}
```

**核心逻辑**:
- 根据实例的`bundleId`自动识别套餐类型
- 返回对应套餐的真实流量配额
- 未知套餐使用默认配额(1TB)

### 2. 月度流量精确计算 (`get_monthly_usage`)

**时间范围**:
```python
now = datetime.utcnow()
start_of_month = datetime(now.year, now.month, 1)
```

**数据获取**:
- **指标**: NetworkOut (出站流量)
- **粒度**: 86400秒 (日级聚合)
- **统计**: Sum (累计总和)
- **单位转换**: Bytes → GB

**核心算法**:
```python
total_bytes = sum(point['sum'] for point in response['metricData'])
usage_gb = total_bytes / (1024**3)
```

### 3. 三级告警分类 (`monitor_critical_instances`)

**告警阈值**:
- **CRITICAL (95%+)**: 紧急告警，立即处理
- **HIGH (85-94%)**: 高级告警，需要行动  
- **MEDIUM (75-84%)**: 预警通知，建议关注

**告警数据结构**:
```python
alert = {
    'instance': instance_name,
    'region': region,
    'usage_gb': round(usage_gb, 2),
    'quota_gb': quota_gb,
    'usage_percent': round(usage_percent, 1),
    'severity': severity,
    'remaining_gb': round(quota_gb - usage_gb, 2)
}
```

### 4. CloudWatch指标优化 (`send_alert_metrics`)

**优化策略**:
- **智能筛选**: 只为告警实例(≥75%)创建指标
- **批量推送**: 每次最多20个指标，提高效率
- **维度增强**: 添加Severity维度，便于分级监控

**指标结构**:
```python
{
    'MetricName': 'QuotaUsagePercent',
    'Dimensions': [
        {'Name': 'InstanceName', 'Value': instance_name},
        {'Name': 'Region', 'Value': region},
        {'Name': 'Severity', 'Value': severity}
    ],
    'Value': usage_percent,
    'Unit': 'Percent'
}
```

### 5. 聚合监控指标 (`send_aggregated_metrics`)

**聚合指标类型**:
- `TotalInstances`: 区域总实例数
- `AlertInstances`: 告警实例数
- `CriticalAlerts`: 紧急告警数
- `HighAlerts`: 高级告警数
- `AlertRate`: 告警率百分比

**计算逻辑**:
```python
alert_rate = (alert_instances / total_instances * 100) if total_instances > 0 else 0
```

## 监控精度优势

### 1. 套餐包感知
- **传统方式**: 所有实例使用固定1TB配额
- **精确方式**: 根据实际套餐包动态配额
- **精度提升**: 避免nano套餐(1TB)和xlarge套餐(6TB)的误判

### 2. 月度计费周期
- **时间精确**: 严格按月1号到当前时间计算
- **周期对齐**: 与AWS计费周期完全一致
- **实时性**: 反映当前月度真实使用情况

### 3. 分级告警控制
- **75%**: 预警阶段，提醒关注
- **85%**: 行动阶段，需要处理
- **95%**: 紧急阶段，立即响应

## CloudWatch指标管理

### 指标优化效果
| 场景 | 传统方式 | 优化后 | 优化比例 |
|------|----------|--------|----------|
| 1000台机器 | 1000个指标 | <50个指标 | 减少95%+ |
| CloudWatch费用 | 高 | 低 | 大幅降低 |
| 管理复杂度 | 复杂 | 简单 | 显著简化 |

### 指标命名空间
- **告警指标**: `Lightsail/QuotaMonitor`
- **聚合指标**: `Lightsail/Aggregated`

## 性能特性

### API调用优化
- **串行处理**: 确保数据一致性和准确性
- **延迟控制**: 遵守AWS API限制
- **区域隔离**: 按区域独立处理，提高容错性

### 错误处理
- **实例级容错**: 单个实例失败不影响整体监控
- **区域级容错**: 单个区域失败不影响其他区域
- **优雅降级**: 获取失败时返回0使用量

## 集成能力

### SNS告警集成
- 自动发送紧急告警通知
- 支持邮件、短信等多种通知方式
- 告警消息包含详细的使用情况

### 文件输出
- **监控报告**: `quota_monitor_report.json`
- **告警统计**: 包含各级别告警数量
- **详细信息**: 每个告警实例的完整信息

## 使用场景

- **精确监控**: 需要基于真实套餐包的精确监控
- **实时告警**: 需要CloudWatch自动告警能力
- **合规要求**: 需要详细的监控记录和报告
- **成本控制**: 需要精确控制CloudWatch指标成本

## 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| ALERT_THRESHOLD_CRITICAL | 95 | 紧急告警阈值(%) |
| ALERT_THRESHOLD_HIGH | 85 | 高级告警阈值(%) |
| ALERT_THRESHOLD_MEDIUM | 75 | 中级告警阈值(%) |
| CLOUDWATCH_NAMESPACE_QUOTA | Lightsail/QuotaMonitor | 告警指标命名空间 |
| CLOUDWATCH_NAMESPACE_AGGREGATED | Lightsail/Aggregated | 聚合指标命名空间 |

## 关键优势

1. **套餐包感知**: 基于真实配额，避免误判
2. **月度精确**: 严格按计费周期监控
3. **指标优化**: 大幅减少CloudWatch指标数量
4. **分级告警**: 精确控制告警时机
5. **聚合监控**: 提供区域级别的总体视图
6. **成本优化**: 显著降低监控成本

这个精确监控组件通过套餐包感知和指标优化，实现了高精度、低成本的Lightsail流量配额监控，是整个监控系统的核心引擎。