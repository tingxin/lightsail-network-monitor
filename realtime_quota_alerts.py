import boto3
from datetime import datetime, timedelta
import json
import os
from dotenv import load_dotenv

load_dotenv()

def create_precise_alarms():
    """创建精确的配额告警"""
    # 获取当前默认区域
    session = boto3.Session()
    current_region = session.region_name or 'us-east-1'
    
    print(f"在区域 {current_region} 创建告警和SNS主题")
    
    cloudwatch = boto3.client('cloudwatch', region_name=current_region)
    sns = boto3.client('sns', region_name=current_region)
    
    # 创建SNS主题
    topic_name = os.getenv('SNS_TOPIC_NAME', 'LightsailQuotaAlerts')
    try:
        topic = sns.create_topic(Name=topic_name)
        topic_arn = topic['TopicArn']
        print(f"SNS主题: {topic_arn}")
    except Exception as e:
        print(f"SNS创建失败: {e}")
        return
    
    # 创建多级告警
    alarm_configs = [
        {
            'name': 'LightsailQuotaCriticalPercent',
            'threshold': float(os.getenv('ALERT_THRESHOLD_CRITICAL', '95')),
            'description': f'实例流量使用率达到{os.getenv("ALERT_THRESHOLD_CRITICAL", "95")}%',
            'comparison': 'GreaterThanOrEqualToThreshold'
        },
        {
            'name': 'LightsailQuotaHighPercent', 
            'threshold': float(os.getenv('ALERT_THRESHOLD_HIGH', '85')),
            'description': f'实例流量使用率达到{os.getenv("ALERT_THRESHOLD_HIGH", "85")}%',
            'comparison': 'GreaterThanOrEqualToThreshold'
        },
        {
            'name': 'LightsailQuotaMediumPercent',
            'threshold': float(os.getenv('ALERT_THRESHOLD_MEDIUM', '75')), 
            'description': f'实例流量使用率达到{os.getenv("ALERT_THRESHOLD_MEDIUM", "75")}%',
            'comparison': 'GreaterThanOrEqualToThreshold'
        }
    ]
    
    for config in alarm_configs:
        try:
            cloudwatch.put_metric_alarm(
                AlarmName=config['name'],
                ComparisonOperator=config['comparison'],
                EvaluationPeriods=1,
                MetricName='QuotaUsagePercent',
                Namespace=os.getenv('CLOUDWATCH_NAMESPACE_QUOTA', 'Lightsail/QuotaMonitor'),
                Period=3600,  # 1小时
                Statistic='Maximum',
                Threshold=config['threshold'],
                ActionsEnabled=True,
                AlarmActions=[topic_arn],
                AlarmDescription=config['description'],
                Unit='Percent',
                TreatMissingData='notBreaching'
            )
            print(f"告警创建成功: {config['name']}")
        except Exception as e:
            print(f"告警创建失败 {config['name']}: {e}")

def create_cost_budget_alert():
    """创建成本预算告警作为备用"""
    try:
        # 获取当前账户ID
        sts = boto3.client('sts')
        account_id = sts.get_caller_identity()['Account']
        
        # 检查是否配置了邮箱地址
        email_address = os.getenv('BUDGET_ALERT_EMAIL')
        if not email_address:
            print("跳过成本预算创建: 未配置BUDGET_ALERT_EMAIL环境变量")
            return
        
        # 获取当前默认区域  
        session = boto3.Session()
        current_region = session.region_name or 'us-east-1'
        
        budgets = boto3.client('budgets', region_name=current_region)
        
        budget_config = {
            'BudgetName': 'LightsailDataTransferBudget',
            'BudgetLimit': {
                'Amount': '100',  # $100
                'Unit': 'USD'
            },
            'TimeUnit': 'MONTHLY',
            'BudgetType': 'COST',
            'CostFilters': {
                'Service': ['Amazon Lightsail'],
                'UsageType': ['*DataTransfer*']
            }
        }
        
        budgets.create_budget(
            AccountId=account_id,
            Budget=budget_config,
            NotificationsWithSubscribers=[
                {
                    'Notification': {
                        'NotificationType': 'ACTUAL',
                        'ComparisonOperator': 'GREATER_THAN',
                        'Threshold': 80,
                        'ThresholdType': 'PERCENTAGE'
                    },
                    'Subscribers': [
                        {
                            'SubscriptionType': 'EMAIL',
                            'Address': email_address
                        }
                    ]
                }
            ]
        )
        print(f"成本预算告警创建成功 (账户: {account_id})")
        
    except Exception as e:
        print(f"成本预算创建失败: {e}")
        print("提示: 可在.env文件中设置BUDGET_ALERT_EMAIL=your-email@example.com")

def setup_lambda_scheduler():
    """设置Lambda定时执行"""
    lambda_code = '''
import boto3
import json
from datetime import datetime, timedelta

def lambda_handler(event, context):
    import os
    # 只监控高风险实例（使用率>70%的实例）
    regions = os.getenv('LIGHTSAIL_REGIONS', 'us-east-1').split(',')
    
    for region in regions:
        try:
            lightsail = boto3.client('lightsail', region_name=region)
            cloudwatch = boto3.client('cloudwatch', region_name=region)
            
            instances = lightsail.get_instances()['instances']
            
            for instance in instances:
                # 获取本月流量
                now = datetime.utcnow()
                start_of_month = datetime(now.year, now.month, 1)
                
                response = lightsail.get_instance_metric_data(
                    instanceName=instance['name'],
                    metricName='NetworkOut',
                    period=86400,
                    startTime=start_of_month,
                    endTime=now,
                    statistics=['Sum'],
                    unit='Bytes'
                )
                
                total_bytes = sum(point['sum'] for point in response['metricData'] if point.get('sum'))
                usage_gb = total_bytes / (1024**3)
                
                # 从环境变量获取配额
                quota_gb = int(os.getenv('DEFAULT_QUOTA_GB', '1024'))
                usage_percent = (usage_gb / quota_gb) * 100
                
                # 只为高风险实例发送指标
                if usage_percent > 70:
                    cloudwatch.put_metric_data(
                        Namespace=os.getenv('CLOUDWATCH_NAMESPACE_QUOTA', 'Lightsail/QuotaMonitor'),
                        MetricData=[{
                            'MetricName': 'QuotaUsagePercent',
                            'Dimensions': [
                                {'Name': 'InstanceName', 'Value': instance['name']},
                                {'Name': 'Region', 'Value': region}
                            ],
                            'Value': usage_percent,
                            'Unit': 'Percent'
                        }]
                    )
                
        except Exception as e:
            print(f"Region {region} error: {e}")
    
    return {'statusCode': 200}
'''
    
    # 创建tmp目录
    tmp_dir = 'tmp'
    if not os.path.exists(tmp_dir):
        os.makedirs(tmp_dir)
    
    lambda_file = os.path.join(tmp_dir, 'quota_monitor_lambda.py')
    with open(lambda_file, 'w') as f:
        f.write(lambda_code)
    
    print(f"Lambda代码已生成到 {lambda_file}")

if __name__ == "__main__":
    print("设置精确配额告警...")
    create_precise_alarms()
    create_cost_budget_alert()
    setup_lambda_scheduler()
    
    print("\n=== 设置完成 ===")
    print("✓ CloudWatch告警已创建")
    print("✓ SNS主题已创建")
    print("✓ Lambda代码已生成")
    print("\n后续步骤:")
    print("1. 运行 precise_quota_monitor.py 开始推送指标")
    print("2. 在CloudWatch中查看告警状态")
    print("3. 配置SNS主题的订阅者(邮箱/短信)")