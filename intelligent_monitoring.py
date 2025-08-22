import boto3
import time
from datetime import datetime, timedelta
import json
import os
from dotenv import load_dotenv
import concurrent.futures
import threading
from functools import lru_cache

load_dotenv()

def intelligent_quota_monitoring():
    """智能配额监控：优先监控高风险实例"""
    
    def get_instance_metrics(instance, region, cache_file='metrics_cache.json'):
        """获取单个实例的流量指标（带缓存）"""
        cache_key = f"{instance['name']}_{region}_{datetime.utcnow().strftime('%Y-%m-%d')}"
        
        # 尝试从缓存读取
        try:
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    cache = json.load(f)
                    if cache_key in cache:
                        return cache[cache_key]
        except:
            pass
        
        try:
            lightsail = boto3.client('lightsail', region_name=region)
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=7)
            
            response = lightsail.get_instance_metric_data(
                instanceName=instance['name'],
                metricName='NetworkOut',
                period=86400,
                startTime=start_time,
                endTime=end_time,
                statistics=['Sum'],
                unit='Bytes'
            )
            
            total_bytes = sum(point['sum'] for point in response['metricData'] if point.get('sum'))
            daily_avg_gb = (total_bytes / (1024**3)) / 7
            
            result = {
                'instance': instance['name'],
                'region': region,
                'daily_avg_gb': round(daily_avg_gb, 2),
                'bundle_id': instance.get('bundleId', 'unknown')
            }
            
            # 保存到缓存
            try:
                cache = {}
                if os.path.exists(cache_file):
                    with open(cache_file, 'r') as f:
                        cache = json.load(f)
                cache[cache_key] = result
                with open(cache_file, 'w') as f:
                    json.dump(cache, f)
            except:
                pass
            
            return result
            
        except Exception as e:
            print(f"获取 {instance['name']} 指标失败: {e}")
            return None
    
    def process_instances_batch(instances, region, batch_size=100):
        """分批并发处理实例"""
        high_risk_threshold = float(os.getenv('HIGH_RISK_DAILY_GB_THRESHOLD', '10'))
        max_workers = int(os.getenv('MAX_CONCURRENT_WORKERS', '10'))
        api_delay = float(os.getenv('API_DELAY_SECONDS', '0.1'))
        
        high_risk = []
        total_batches = (len(instances) + batch_size - 1) // batch_size
        
        for batch_idx in range(total_batches):
            start_idx = batch_idx * batch_size
            end_idx = min(start_idx + batch_size, len(instances))
            batch_instances = instances[start_idx:end_idx]
            
            print(f"  处理批次 {batch_idx + 1}/{total_batches} ({len(batch_instances)} 个实例)")
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任务
                future_to_instance = {}
                for instance in batch_instances:
                    future = executor.submit(self.get_instance_metrics, instance, region)
                    future_to_instance[future] = instance
                    time.sleep(api_delay / max_workers)  # 分散API调用
                
                # 收集结果
                for future in concurrent.futures.as_completed(future_to_instance):
                    result = future.result()
                    if result and result['daily_avg_gb'] > high_risk_threshold:
                        high_risk.append(result)
            
            # 批次间暂停
            if batch_idx < total_batches - 1:
                time.sleep(float(os.getenv('BATCH_DELAY_SECONDS', '2')))
        
        return high_risk
    
    def get_high_risk_instances():
        """识别高风险实例（优化版）"""
        regions = os.getenv('LIGHTSAIL_REGIONS', 'us-east-1').split(',')
        all_high_risk = []
        
        for region in regions:
            try:
                print(f"处理区域: {region}")
                lightsail = boto3.client('lightsail', region_name=region)
                instances = lightsail.get_instances()['instances']
                print(f"  发现 {len(instances)} 个实例")
                
                if not instances:
                    continue
                
                # 分批并发处理
                region_high_risk = process_instances_batch(instances, region)
                all_high_risk.extend(region_high_risk)
                
                print(f"  {region} 完成，发现 {len(region_high_risk)} 个高风险实例")
                
            except Exception as e:
                print(f"{region} 风险评估失败: {e}")
                continue
        
        return all_high_risk
    
    def get_precise_metrics(instance_info):
        """获取单个实例的精确监控数据"""
        region = instance_info['region']
        instance_name = instance_info['instance']
        
        try:
            lightsail = boto3.client('lightsail', region_name=region)
            now = datetime.utcnow()
            start_of_month = datetime(now.year, now.month, 1)
            
            response = lightsail.get_instance_metric_data(
                instanceName=instance_name,
                metricName='NetworkOut',
                period=3600,
                startTime=start_of_month,
                endTime=now,
                statistics=['Sum'],
                unit='Bytes'
            )
            
            hourly_data = response['metricData']
            total_bytes = sum(point['sum'] for point in hourly_data if point.get('sum'))
            usage_gb = total_bytes / (1024**3)
            
            quota_gb = int(os.getenv('DEFAULT_QUOTA_GB', '1024'))
            usage_percent = (usage_gb / quota_gb) * 100
            
            days_passed = now.day
            days_in_month = 31
            predicted_monthly_gb = usage_gb * (days_in_month / days_passed)
            predicted_percent = (predicted_monthly_gb / quota_gb) * 100
            
            alert_threshold = float(os.getenv('ALERT_USAGE_PERCENT_THRESHOLD', '75'))
            prediction_threshold = float(os.getenv('PREDICTION_ALERT_THRESHOLD', '90'))
            
            if usage_percent >= alert_threshold or predicted_percent >= prediction_threshold:
                return {
                    'instance': instance_name,
                    'region': region,
                    'current_usage_gb': round(usage_gb, 2),
                    'current_percent': round(usage_percent, 1),
                    'predicted_monthly_gb': round(predicted_monthly_gb, 2),
                    'predicted_percent': round(predicted_percent, 1),
                    'quota_gb': quota_gb,
                    'risk_level': 'HIGH' if predicted_percent >= 95 else 'MEDIUM'
                }
            
        except Exception as e:
            print(f"监控 {instance_name} 失败: {e}")
        
        return None
    
    def monitor_high_risk_precisely(high_risk_instances):
        """精确监控高风险实例（并发版）"""
        if not high_risk_instances:
            return []
        
        max_workers = int(os.getenv('MAX_CONCURRENT_WORKERS', '10'))
        api_delay = float(os.getenv('API_DELAY_SECONDS', '0.1'))
        alerts = []
        
        print(f"并发监控 {len(high_risk_instances)} 个高风险实例...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_instance = {}
            
            for instance_info in high_risk_instances:
                future = executor.submit(self.get_precise_metrics, instance_info)
                future_to_instance[future] = instance_info
                time.sleep(api_delay / max_workers)
            
            for future in concurrent.futures.as_completed(future_to_instance):
                result = future.result()
                if result:
                    alerts.append(result)
        
        return alerts
    
    def save_alert_instances_by_level(alerts):
        """按告警级别分类保存实例ID到不同文件"""
        medium_instances = []
        high_instances = []
        critical_instances = []
        
        critical_threshold = float(os.getenv('ALERT_THRESHOLD_CRITICAL', '95'))
        high_threshold = float(os.getenv('ALERT_THRESHOLD_HIGH', '85'))
        
        for alert in alerts:
            instance_info = {
                'instance_name': alert['instance'],
                'region': alert['region'],
                'usage_percent': alert['current_percent'],
                'predicted_percent': alert['predicted_percent'],
                'timestamp': datetime.utcnow().isoformat()
            }
            
            if alert['predicted_percent'] >= critical_threshold:
                critical_instances.append(instance_info)
            elif alert['predicted_percent'] >= high_threshold:
                high_instances.append(instance_info)
            else:
                medium_instances.append(instance_info)
        
        # 保存到不同文件
        if medium_instances:
            with open('alert_medium_instances.json', 'w') as f:
                json.dump(medium_instances, f, indent=2)
            print(f"中级告警实例已保存: {len(medium_instances)} 个")
        
        if high_instances:
            with open('alert_high_instances.json', 'w') as f:
                json.dump(high_instances, f, indent=2)
            print(f"高级告警实例已保存: {len(high_instances)} 个")
        
        if critical_instances:
            with open('alert_critical_instances.json', 'w') as f:
                json.dump(critical_instances, f, indent=2)
            print(f"紧急告警实例已保存: {len(critical_instances)} 个")
        
        return len(medium_instances), len(high_instances), len(critical_instances)
    
    # 绑定方法到当前作用域
    self = type('', (), {})()
    self.get_instance_metrics = get_instance_metrics
    self.get_precise_metrics = get_precise_metrics
    
    # 执行智能监控
    print("=== 智能配额监控（优化版）===")
    print("1. 识别高风险实例...")
    start_time = time.time()
    high_risk = get_high_risk_instances()
    elapsed = time.time() - start_time
    print(f"风险识别完成，耗时: {elapsed:.1f}秒")
    
    print(f"发现 {len(high_risk)} 个高风险实例:")
    for instance in high_risk:
        print(f"  {instance['instance']} ({instance['region']}): {instance['daily_avg_gb']} GB/天")
    
    if high_risk:
        print("\n2. 精确监控高风险实例...")
        alerts = monitor_high_risk_precisely(high_risk)
        
        if alerts:
            print(f"\n发现 {len(alerts)} 个配额告警:")
            for alert in alerts:
                print(f"  {alert['risk_level']}: {alert['instance']}")
                print(f"    当前: {alert['current_percent']}% ({alert['current_usage_gb']} GB)")
                print(f"    预测: {alert['predicted_percent']}% ({alert['predicted_monthly_gb']} GB)")
            
            # 按级别保存告警实例
            medium_count, high_count, critical_count = save_alert_instances_by_level(alerts)
            print(f"\n告警实例分类保存: 中级({medium_count}) 高级({high_count}) 紧急({critical_count})")
        
        # 保存结果
        report = {
            'timestamp': datetime.utcnow().isoformat(),
            'high_risk_instances': high_risk,
            'quota_alerts': alerts
        }
        
        report_file = os.getenv('INTELLIGENT_REPORT_FILE', 'intelligent_quota_report.json')
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        return alerts
    
    return []

if __name__ == "__main__":
    alerts = intelligent_quota_monitoring()
    if alerts:
        print(f"\n监控完成，发现 {len(alerts)} 个告警")
        print("请检查生成的告警文件: alert_medium_instances.json, alert_high_instances.json, alert_critical_instances.json")
        print("可使用 python3 instance_manager.py 批量管理实例")
    else:
        print("\n监控完成，未发现告警")