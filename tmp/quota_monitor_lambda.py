
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
