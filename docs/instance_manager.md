# instance_manager.py 技术文档

## 实现意图

`instance_manager.py` 是Lightsail流量配额监控系统的**自动化响应组件**，专门负责对超出告警阈值的实例进行批量管理操作。该组件实现了从监控发现问题到自动化处理的完整闭环，是整个监控系统的执行臂。

### 核心目标
- 基于告警级别对实例进行分类批量管理
- 提供安全的模拟运行模式，避免误操作
- 支持批量停止/启动操作，快速响应告警
- 记录详细的操作日志，便于审计和回溯

## 实现原理

### 告警驱动的管理架构

```
告警文件 → 实例加载 → 操作确认 → 批量执行 → 日志记录
```

### 分级管理策略

```
Critical实例 (95%+) → 立即停止，避免超限费用
High实例 (85-94%) → 计划停止，控制风险
Medium实例 (75-84%) → 监控观察，可选操作
```

### 安全操作流程

```
模拟运行 → 结果预览 → 用户确认 → 实际执行 → 操作日志
```

## 代码逻辑详解

### 1. 告警实例加载 (`load_alert_instances`)

**文件映射**:
```python
filename_map = {
    'critical': 'alert_critical_instances.json',
    'high': 'alert_high_instances.json',
    'medium': 'alert_medium_instances.json'
}
```

**数据结构**:
```python
{
    'instance_name': 'web-server-01',
    'region': 'us-east-1',
    'usage_percent': 87.5,
    'predicted_percent': 92.3,
    'timestamp': '2024-01-15T10:30:00'
}
```

**加载特性**:
- 自动检测文件存在性
- 解析JSON格式的告警数据
- 提供友好的错误处理
- 支持空文件和格式错误的容错

### 2. 批量停止实例 (`stop_instances`)

**核心执行逻辑**:
```python
for instance_info in instances:
    if not dry_run:
        lightsail = boto3.client('lightsail', region_name=region)
        response = lightsail.stop_instance(instanceName=instance_name)
        print(f"✓ 已停止: {instance_name}")
    else:
        print(f"○ 模拟停止: {instance_name}")
```

**安全特性**:
- **模拟模式**: 默认启用，预览操作结果
- **确认机制**: 需要用户明确确认才执行
- **API延迟**: 遵守AWS API限制
- **错误处理**: 单个实例失败不影响整体操作

### 3. 批量启动实例 (`start_instances`)

**启动逻辑**:
```python
response = lightsail.start_instance(instanceName=instance_name)
```

**应用场景**:
- 告警解除后恢复实例运行
- 定时启动实例（如工作时间）
- 批量恢复误停止的实例

### 4. 操作日志记录 (`log_operation`)

**日志结构**:
```python
log_entry = {
    'timestamp': datetime.utcnow().isoformat(),
    'operation': 'stop_instances',
    'dry_run': False,
    'total_instances': 10,
    'success_count': 9,
    'failed_count': 1,
    'instances': [{'name': 'web-01', 'region': 'us-east-1'}]
}
```

**日志特性**:
- **时间戳**: 精确记录操作时间
- **操作类型**: 区分停止/启动操作
- **执行模式**: 记录是否为模拟运行
- **结果统计**: 成功和失败数量统计
- **实例详情**: 记录所有涉及的实例信息

### 5. 交互式管理界面 (`main`)

**菜单选项**:
```
1. 停止紧急告警实例 (critical)
2. 停止高级告警实例 (high)  
3. 停止中级告警实例 (medium)
4. 启动指定级别实例
5. 查看告警实例列表
```

**交互流程**:
1. 显示操作菜单
2. 用户选择操作类型
3. 加载对应级别的告警实例
4. 显示实例列表和使用率
5. 确认是否模拟运行
6. 执行操作并显示结果

## 安全机制

### 1. 模拟运行模式
```python
dry_run = input("是否先进行模拟运行? (y/n): ").lower() == 'y'
```

**安全特性**:
- **默认模拟**: 优先进行模拟运行
- **结果预览**: 显示将要执行的操作
- **二次确认**: 模拟后再次确认实际执行
- **操作可视**: 清晰显示每个实例的操作结果

### 2. 确认机制
```python
confirm = input(f"确认停止 {len(instances)} 个实例? (yes/no): ").lower()
if confirm == 'yes':
    # 执行实际操作
```

**确认特点**:
- **明确输入**: 需要输入完整的"yes"才执行
- **数量显示**: 明确显示将要操作的实例数量
- **取消保护**: 任何非"yes"输入都会取消操作

### 3. 错误处理
```python
try:
    response = lightsail.stop_instance(instanceName=instance_name)
    stopped_count += 1
except Exception as e:
    print(f"✗ 停止失败: {instance_name} - 错误: {e}")
    failed_count += 1
```

**容错特性**:
- **单点失败隔离**: 单个实例失败不影响其他实例
- **详细错误信息**: 记录具体的失败原因
- **统计反馈**: 提供成功和失败的统计信息

## 使用场景

### 1. 紧急响应场景
- **Critical告警**: 实例使用率≥95%，立即停止避免超限
- **自动化响应**: 结合监控系统实现自动化处理
- **快速止损**: 批量操作，快速控制成本风险

### 2. 计划维护场景
- **High告警**: 实例使用率85-94%，计划性停止
- **批量维护**: 统一时间窗口进行批量操作
- **资源优化**: 停止低优先级实例，释放流量配额

### 3. 恢复操作场景
- **告警解除**: 流量使用率下降后恢复实例
- **定时启动**: 工作时间自动启动实例
- **误操作恢复**: 快速恢复误停止的实例

## 操作流程示例

### 紧急告警处理流程
```bash
1. 运行监控系统发现Critical告警
2. 执行: python3 instance_manager.py
3. 选择: 1 (停止紧急告警实例)
4. 查看: 显示Critical实例列表
5. 模拟: 选择模拟运行预览结果
6. 确认: 输入"yes"执行实际停止
7. 完成: 查看操作结果和日志
```

### 恢复操作流程
```bash
1. 确认告警已解除
2. 执行: python3 instance_manager.py
3. 选择: 4 (启动指定级别实例)
4. 输入: critical (启动之前停止的Critical实例)
5. 确认: 执行启动操作
6. 验证: 检查实例状态
```

## 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| API_DELAY_SECONDS | 0.12 | API调用间隔时间(秒) |

## 输出文件

### 操作日志文件
- **文件名**: `instance_operations.log`
- **格式**: JSON Lines格式，每行一个操作记录
- **内容**: 操作时间、类型、结果、实例详情

### 日志示例
```json
{"timestamp": "2024-01-15T10:30:00", "operation": "stop_instances", "dry_run": false, "total_instances": 5, "success_count": 5, "failed_count": 0}
```

## 性能特性

### 批量操作性能
- **并发处理**: 串行处理确保操作稳定性
- **API限制**: 内置延迟控制，遵守AWS限制
- **错误恢复**: 单点失败不影响整体操作

### 扩展性
- **实例数量**: 支持任意数量的实例批量操作
- **区域支持**: 支持多区域的实例管理
- **操作类型**: 易于扩展其他管理操作

## 关键优势

1. **自动化响应**: 从监控到处理的完整自动化
2. **安全可靠**: 多重确认机制，避免误操作
3. **批量高效**: 支持大规模实例的批量管理
4. **操作可视**: 清晰的操作反馈和结果显示
5. **审计友好**: 详细的操作日志记录
6. **易于使用**: 友好的交互式界面

## 集成能力

### 与监控系统集成
- **数据源**: 直接读取监控系统生成的告警文件
- **触发机制**: 可以通过脚本自动触发
- **状态同步**: 操作结果可以反馈给监控系统

### 与告警系统集成
- **告警响应**: 可以作为告警的自动响应动作
- **通知集成**: 操作结果可以发送通知
- **工作流**: 可以集成到更大的运维工作流中

这个实例管理组件通过安全的批量操作和详细的日志记录，实现了从监控发现问题到自动化处理的完整闭环，是整个Lightsail流量配额监控系统的重要执行组件。