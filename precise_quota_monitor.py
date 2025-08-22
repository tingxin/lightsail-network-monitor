import boto3
import time
from datetime import datetime, timedelta
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from dotenv import load_dotenv

load_dotenv()

class LightsailQuotaMonitor:
    def __init__(self):
        # Lightsail套餐包流量限制 (GB) - 从环境变量加载
        self.PLAN_QUOTAS = {
            'nano_2_0': int(os.getenv('BUNDLE_NANO_QUOTA', '1024')),
            'micro_2_0': int(os.getenv('BUNDLE_MICRO_QUOTA', '2048')),
            'small_2_0': int(os.getenv('BUNDLE_SMALL_QUOTA', '3072')),
            'medium_2_0': int(os.getenv('BUNDLE_MEDIUM_QUOTA', '4096')),
            'large_2_0': int(os.getenv('BUNDLE_LARGE_QUOTA', '5120')),
            'xlarge_2_0': int(os.getenv('BUNDLE_XLARGE_QUOTA', '6144'))
        }
        
    def get_instance_plan_quota(self, instance):
        """获取实例套餐包流量配额"""
        bundle_id = instance.get('bundleId', '')
        default_quota = int(os.getenv('DEFAULT_QUOTA_GB', '1024'))
        
        return self.PLAN_QUOTAS.get(bundle_id, default_quota)
    
    def get_monthly_usage(self, region, instance_name):
        """获取实例本月累计流量"""
        lightsail = boto3.client('lightsail', region_name=region)
        
        # 本月1号到现在
        now = datetime.utcnow()
        start_of_month = datetime(now.year, now.month, 1)
        
        try:
            response = lightsail.get_instance_metric_data(
                instanceName=instance_name,
                metricName='NetworkOut',
                period=86400,  # 日聚合
                startTime=start_of_month,
                endTime=now,
                statistics=['Sum'],
                unit='Bytes'
            )
            
            total_bytes = sum(point['sum'] for point in response['metricData'] if point.get('sum'))
            return total_bytes / (1024**3)  # 转换为GB
            
        except Exception as e:
            print(f"获取 {instance_name} 流量失败: {e}")
            return 0
    
    def monitor_critical_instances(self, region):
        """监控接近配额的关键实例"""
        lightsail = boto3.client('lightsail', region_name=region)
        
        try:
            instances = lightsail.get_instances()['instances']
            critical_alerts = []
            
            for instance in instances:
                instance_name = instance['name']
                quota_gb = self.get_instance_plan_quota(instance)
                
                # 获取本月使用量
                time.sleep(float(os.getenv('API_DELAY_SECONDS', '0.12')))  # API限制
                usage_gb = self.get_monthly_usage(region, instance_name)
                usage_percent = (usage_gb / quota_gb) * 100
                
                # 分级告警
                critical_threshold = float(os.getenv('ALERT_THRESHOLD_CRITICAL', '95'))
                high_threshold = float(os.getenv('ALERT_THRESHOLD_HIGH', '85'))
                medium_threshold = float(os.getenv('ALERT_THRESHOLD_MEDIUM', '75'))
                
                if usage_percent >= critical_threshold:
                    severity = 'CRITICAL'
                elif usage_percent >= high_threshold:
                    severity = 'HIGH'
                elif usage_percent >= medium_threshold:
                    severity = 'MEDIUM'
                else:
                    continue
                
                alert = {
                    'instance': instance_name,
                    'region': region,
                    'usage_gb': round(usage_gb, 2),
                    'quota_gb': quota_gb,
                    'usage_percent': round(usage_percent, 1),
                    'severity': severity,
                    'remaining_gb': round(quota_gb - usage_gb, 2)
                }
                
                critical_alerts.append(alert)
            
            # 只为告警实例推送CloudWatch指标，减少指标数量
            if critical_alerts:
                self.send_alert_metrics(region, critical_alerts)
            
            # 发送区域聚合指标
            self.send_aggregated_metrics(region, instances, critical_alerts)
            
            return critical_alerts
            
        except Exception as e:
            print(f"{region} 监控失败: {e}")
            return []
    
    def send_alerts(self, alerts):
        """发送告警通知"""
        if not alerts:
            return 0, 0
        
        sns = boto3.client('sns', region_name='us-east-1')
        
        # 按严重程度分组
        critical = [a for a in alerts if a['severity'] == 'CRITICAL']
        high = [a for a in alerts if a['severity'] == 'HIGH']
        
        if critical:
            message = "🚨 CRITICAL: Lightsail实例即将超出流量配额!\n\n"
            for alert in critical:
                message += f"实例: {alert['instance']} ({alert['region']})\n"
                message += f"使用率: {alert['usage_percent']}% ({alert['usage_gb']}/{alert['quota_gb']} GB)\n"
                message += f"剩余: {alert['remaining_gb']} GB\n\n"
            
            topic_name = os.getenv('SNS_TOPIC_NAME', 'LightsailQuotaAlerts')
            try:
                sns.publish(
                    TopicArn=f'arn:aws:sns:us-east-1:YOUR_ACCOUNT:{topic_name}',
                    Subject='🚨 Lightsail流量配额紧急告警',
                    Message=message
                )
            except Exception as e:
                print(f"发送告警失败: {e}")
        
        return len(critical), len(high)
    
    def send_alert_metrics(self, region, alerts):
        """只为告警实例发送CloudWatch指标"""
        try:
            cloudwatch = boto3.client('cloudwatch', region_name=region)
            namespace = os.getenv('CLOUDWATCH_NAMESPACE_QUOTA', 'Lightsail/QuotaMonitor')
            
            metric_data = []
            for alert in alerts:
                metric_data.append({
                    'MetricName': 'QuotaUsagePercent',
                    'Dimensions': [
                        {'Name': 'InstanceName', 'Value': alert['instance']},
                        {'Name': 'Region', 'Value': region},
                        {'Name': 'Severity', 'Value': alert['severity']}
                    ],
                    'Value': alert['usage_percent'],
                    'Unit': 'Percent',
                    'Timestamp': datetime.utcnow()
                })
            
            # 批量发送，每次最多20个指标
            for i in range(0, len(metric_data), 20):
                batch = metric_data[i:i+20]
                cloudwatch.put_metric_data(
                    Namespace=namespace,
                    MetricData=batch
                )
                
        except Exception as e:
            print(f"发送告警指标失败: {e}")
    
    def send_aggregated_metrics(self, region, all_instances, alerts):
        """发送区域聚合指标，便于总体监控"""
        try:
            cloudwatch = boto3.client('cloudwatch', region_name=region)
            namespace = os.getenv('CLOUDWATCH_NAMESPACE_AGGREGATED', 'Lightsail/Aggregated')
            
            # 统计数据
            total_instances = len(all_instances)
            alert_instances = len(alerts)
            critical_count = len([a for a in alerts if a['severity'] == 'CRITICAL'])
            high_count = len([a for a in alerts if a['severity'] == 'HIGH'])
            medium_count = len([a for a in alerts if a['severity'] == 'MEDIUM'])
            
            # 聚合指标
            aggregated_metrics = [
                {
                    'MetricName': 'TotalInstances',
                    'Dimensions': [{'Name': 'Region', 'Value': region}],
                    'Value': total_instances,
                    'Unit': 'Count'
                },
                {
                    'MetricName': 'AlertInstances',
                    'Dimensions': [{'Name': 'Region', 'Value': region}],
                    'Value': alert_instances,
                    'Unit': 'Count'
                },
                {
                    'MetricName': 'CriticalAlerts',
                    'Dimensions': [{'Name': 'Region', 'Value': region}],
                    'Value': critical_count,
                    'Unit': 'Count'
                },
                {
                    'MetricName': 'HighAlerts',
                    'Dimensions': [{'Name': 'Region', 'Value': region}],
                    'Value': high_count,
                    'Unit': 'Count'
                },
                {
                    'MetricName': 'AlertRate',
                    'Dimensions': [{'Name': 'Region', 'Value': region}],
                    'Value': (alert_instances / total_instances * 100) if total_instances > 0 else 0,
                    'Unit': 'Percent'
                }
            ]
            
            cloudwatch.put_metric_data(
                Namespace=namespace,
                MetricData=aggregated_metrics
            )
            
        except Exception as e:
            print(f"发送聚合指标失败: {e}")

def main():
    monitor = LightsailQuotaMonitor()
    
    regions = os.getenv('LIGHTSAIL_REGIONS', 'us-east-1').split(',')
    all_alerts = []
    
    print("开始精确流量配额监控...")
    
    # 串行处理确保准确性
    for region in regions:
        print(f"\n检查 {region}...")
        alerts = monitor.monitor_critical_instances(region)
        all_alerts.extend(alerts)
        
        if alerts:
            print(f"发现 {len(alerts)} 个告警:")
            for alert in alerts:
                print(f"  {alert['severity']}: {alert['instance']} - {alert['usage_percent']}%")
        
        time.sleep(float(os.getenv('REGION_DELAY_SECONDS', '5')))  # region间暂停
    
    # 发送告警
    critical_count, high_count = monitor.send_alerts(all_alerts)
    
    # 保存详细报告
    report = {
        'timestamp': datetime.utcnow().isoformat(),
        'total_alerts': len(all_alerts),
        'critical_alerts': critical_count,
        'high_alerts': high_count,
        'details': all_alerts
    }
    
    report_file = os.getenv('QUOTA_REPORT_FILE', 'quota_monitor_report.json')
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n=== 监控完成 ===")
    print(f"总告警: {len(all_alerts)}")
    print(f"紧急告警: {critical_count}")
    print(f"高级告警: {high_count}")
    print(f"\n指标优化: 只为 {len(all_alerts)} 个告警实例创建CloudWatch指标")
    print(f"聚合指标: 已创建区域级别的汇总监控指标")

if __name__ == "__main__":
    main()