# realtime_quota_alerts.py 技术文档

## 实现意图

`realtime_quota_alerts.py` 是Lightsail流量配额监控系统的**告警基础设施组件**，负责建立完整的实时告警体系。该组件是一次性设置工具，为整个监控系统提供CloudWatch告警、SNS通知和Lambda自动化的基础架构。

### 核心目标
- 建立分级CloudWatch告警机制，实现自动化监控
- 创建SNS通知渠道，支持多种通知方式
- 设置成本预算告警，作为监控的备用保障
- 生成Lambda函数代码，提供服务器less监控选项

## 实现原理

### 告警基础设施架构

```
CloudWatch告警 → SNS主题 → 通知订阅者
     ↑              ↓
  指标数据      邮件/短信/Lambda
     ↑
Lambda定时器 (可选)
```

### 三层告警体系

```
Level 1: CloudWatch告警 (自动触发)
Level 2: SNS通知 (实时推送)  
Level 3: 成本预算告警 (备用保障)
```

## 代码逻辑详解

### 1. CloudWatch告警创建 (`create_precise_alarms`)

**三级告警配置**:
```python
alarm_configs = [
    {
        'name': 'LightsailQuotaCriticalPercent',
        'threshold': 95,  # 紧急告警
        'description': '实例流量使用率达到95%'
    },
    {
        'name': 'LightsailQuotaHighPercent', 
        'threshold': 85,  # 高级告警
        'description': '实例流量使用率达到85%'
    },
    {
        'name': 'LightsailQuotaMediumPercent',
        'threshold': 75,  # 中级告警
        'description': '实例流量使用率达到75%'
    }
]
```

**告警参数配置**:
- **指标名称**: `QuotaUsagePercent`
- **命名空间**: `Lightsail/QuotaMonitor`
- **评估周期**: 1小时
- **统计方式**: Maximum (最大值)
- **缺失数据处理**: `notBreaching` (不触发告警)

**工作原理**:
1. 监听CloudWatch中的`QuotaUsagePercent`指标
2. 当指标值超过阈值时自动触发告警
3. 触发后向SNS主题发送通知
4. SNS主题将通知分发给所有订阅者

### 2. SNS通知主题创建

**主题创建**:
```python
topic = sns.create_topic(Name='LightsailQuotaAlerts')
topic_arn = topic['TopicArn']
```

**集成特性**:
- **自动关联**: 告警自动关联到SNS主题
- **多订阅者**: 支持邮件、短信、Lambda等多种订阅方式
- **扩展性**: 可以添加多个通知目标

### 3. 成本预算告警 (`create_cost_budget_alert`)

**预算配置**:
```python
budget_config = {
    'BudgetName': 'LightsailDataTransferBudget',
    'BudgetLimit': {'Amount': '100', 'Unit': 'USD'},
    'TimeUnit': 'MONTHLY',
    'BudgetType': 'COST',
    'CostFilters': {
        'Service': ['Amazon Lightsail'],
        'UsageType': ['*DataTransfer*']
    }
}
```

**告警机制**:
- **阈值**: 80%的预算使用率
- **通知类型**: 实际费用告警
- **过滤条件**: 仅Lightsail数据传输费用
- **备用保障**: 作为技术监控的补充

### 4. Lambda函数代码生成 (`setup_lambda_scheduler`)

**代码生成功能**:
- 自动生成完整的Lambda函数代码
- 保存到 `tmp/quota_monitor_lambda.py`
- 提供服务器less监控的部署选项

**生成的Lambda代码特点**:
- 简化版的监控逻辑，专为Lambda环境优化
- 固定使用默认配额(1TB)，不支持套餐包感知
- 只推送CloudWatch指标，不生成告警文件
- 适合轻量级的自动化监控需求

## quota_monitor_lambda.py 详细说明

### Lambda代码与precise_quota_monitor.py的差异

| 功能特性 | precise_quota_monitor.py | quota_monitor_lambda.py |
|----------|-------------------------|-------------------------|
| **套餐包感知** | ✓ 支持6种套餐包配额 | ✗ 固定使用DEFAULT_QUOTA_GB |
| **告警分级** | ✓ 三级告警(75%/85%/95%) | ✗ 固定70%阈值 |
| **文件输出** | ✓ 生成告警JSON文件 | ✗ 无文件输出 |
| **聚合指标** | ✓ 区域级聚合指标 | ✗ 仅基础指标 |
| **SNS通知** | ✓ 自动发送告警通知 | ✗ 依赖CloudWatch告警 |
| **错误处理** | ✓ 详细错误处理和日志 | ✓ 基础错误处理 |
| **性能优化** | ✓ 批量指标推送 | ✗ 逐个推送 |

### Lambda代码的核心逻辑

```python
def lambda_handler(event, context):
    # 1. 获取所有区域的Lightsail实例
    # 2. 计算本月流量使用率 (固定1TB配额)
    # 3. 筛选高风险实例 (>70%)
    # 4. 推送CloudWatch指标
    # 5. 依赖预设的CloudWatch告警触发通知
```

### 适用场景对比

**使用precise_quota_monitor.py的场景**:
- 需要精确的套餐包配额监控
- 要求详细的告警分级和文件输出
- 需要批量管理告警实例
- 大规模生产环境

**使用Lambda版本的场景**:
- 简单的自动化监控需求
- 所有实例使用相同配额
- 希望完全无服务器化
- 成本敏感的小规模环境

### Lambda部署和配置

#### 1. 部署步骤
```bash
# 打包Lambda代码
cd tmp
zip quota_monitor_lambda.zip quota_monitor_lambda.py

# 创建Lambda函数
aws lambda create-function \
  --function-name lightsail-quota-monitor \
  --runtime python3.9 \
  --handler quota_monitor_lambda.lambda_handler \
  --zip-file fileb://quota_monitor_lambda.zip
```

#### 2. 环境变量配置
```bash
aws lambda update-function-configuration \
  --function-name lightsail-quota-monitor \
  --environment Variables='{
    "LIGHTSAIL_REGIONS":"us-east-1,us-west-2",
    "DEFAULT_QUOTA_GB":"1024",
    "CLOUDWATCH_NAMESPACE_QUOTA":"Lightsail/QuotaMonitor"
  }'
```

#### 3. 定时触发器设置
```bash
# 创建EventBridge规则
aws events put-rule \
  --name lightsail-monitor-schedule \
  --schedule-expression "rate(1 hour)"

# 添加Lambda目标
aws events put-targets \
  --rule lightsail-monitor-schedule \
  --targets "Id"="1","Arn"="arn:aws:lambda:us-east-1:ACCOUNT:function:lightsail-quota-monitor"
```

### 性能和成本特性

- **执行频率**: 建议每1-2小时
- **执行时间**: 通常2-5分钟
- **成本估算**: 每月720次执行约$0.20
- **内存需求**: 128MB足够
- **超时设置**: 建议5分钟

### 权限要求

Lambda执行角色需要以下权限:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "lightsail:GetInstances",
                "lightsail:GetInstanceMetricData",
                "cloudwatch:PutMetricData"
            ],
            "Resource": "*"
        }
    ]
}
```

## 告警工作流程

### 完整告警链路
```
1. precise_quota_monitor.py 推送指标
   ↓
2. CloudWatch接收 QuotaUsagePercent 指标
   ↓
3. 告警规则评估指标值
   ↓
4. 超过阈值时触发告警
   ↓
5. SNS主题接收告警
   ↓
6. 通知分发给订阅者
   ↓
7. 用户收到告警通知
```

### 告警响应流程
```
收到告警 → 查看实例详情 → 执行 instance_manager.py → 停止高风险实例
```

## 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| SNS_TOPIC_NAME | LightsailQuotaAlerts | SNS主题名称 |
| ALERT_THRESHOLD_CRITICAL | 95 | 紧急告警阈值(%) |
| ALERT_THRESHOLD_HIGH | 85 | 高级告警阈值(%) |
| ALERT_THRESHOLD_MEDIUM | 75 | 中级告警阈值(%) |
| BUDGET_ALERT_EMAIL | 无 | 成本预算告警邮箱 |
| CLOUDWATCH_NAMESPACE_QUOTA | Lightsail/QuotaMonitor | CloudWatch命名空间 |

## 使用场景

### 1. 初始部署
- 新环境搭建时一次性运行
- 建立完整的告警基础设施
- 配置通知渠道

### 2. 自动化需求
- 希望实现无人值守监控
- 需要7×24小时告警能力
- 要求快速响应告警

### 3. 企业级部署
- 多团队协作环境
- 需要标准化告警流程
- 要求审计和合规

## 后续配置步骤

### 1. SNS订阅配置
```bash
# 添加邮件订阅
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:ACCOUNT:LightsailQuotaAlerts \
  --protocol email \
  --notification-endpoint your-email@example.com

# 添加短信订阅
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:ACCOUNT:LightsailQuotaAlerts \
  --protocol sms \
  --notification-endpoint +1234567890
```

### 2. Lambda部署(可选)
```bash
# 打包Lambda代码
cd tmp
zip quota_monitor_lambda.zip quota_monitor_lambda.py

# 上传到AWS Lambda
aws lambda create-function \
  --function-name lightsail-quota-monitor \
  --runtime python3.9 \
  --zip-file fileb://quota_monitor_lambda.zip
```

### 3. 权限配置
确保Lambda函数具有以下权限:
- `lightsail:GetInstances`
- `lightsail:GetInstanceMetricData`
- `cloudwatch:PutMetricData`

## 总结

### realtime_quota_alerts.py的核心价值

1. **一次设置**: 运行一次即可建立完整告警体系
2. **基础设施**: 为整个监控系统提供CloudWatch和SNS基础
3. **多渠道通知**: 支持邮件、短信、Lambda等多种通知方式
4. **可扩展性**: 易于添加新的告警规则和通知目标
5. **企业级**: 支持大规模部署和多团队协作

### Lambda vs Python脚本选择建议

**选择Lambda版本的情况**:
- 希望完全自动化，无需服务器维护
- 所有实例使用相同的流量配额
- 监控需求相对简单
- 成本敏感的小规模环境

**选择Python脚本的情况**:
- 需要精确的套餐包配额监控
- 要求详细的告警分级和批量管理
- 大规模生产环境
- 需要自定义监控逻辑

### 推荐部署策略

1. **初始部署**: 运行 `realtime_quota_alerts.py` 建立告警基础设施
2. **生产监控**: 使用 `precise_quota_monitor.py` 进行精确监控
3. **备用方案**: 部署Lambda版本作为自动化备用监控
4. **成本优化**: 根据实际需求选择合适的监控组合

这个告警设置组件通过建立完整的CloudWatch + SNS基础设施，并提供Lambda自动化选项，为整个Lightsail流量配额监控系统提供了灵活可靠的实时告警能力。